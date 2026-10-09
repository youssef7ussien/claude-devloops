"""What a command is doing, as it does it: one line per step on stderr, and in `state/run.log`.

The engine reports each recorded event (`event`), and `ClaudeRunner` reports each Claude call
(`call_started`, `tool_use`, `call_ended`). Lines go to stderr, so `--json` output on stdout stays
one object. While a call runs, a terminal gets a status line redrawn in place (elapsed time, tool
calls, the last tool); a pipe or a log gets a plain "still ..." line every minute instead.

Levels: `quiet` prints nothing (the command's final summary still does), `normal` prints events
and calls, `verbose` also prints each tool Claude uses. Every line except the status line is
appended to the loop's `state/run.log` whatever the level, so a run started in the background can
be followed with `tail -f`. A failure to write the log or the terminal never changes a run.

`LiveCall` keeps the running call in `state/live.json` for the dashboard's "now" panel.
"""
import os
import sys
import threading
import time
from datetime import datetime

from . import state

LOG_NAME = "run.log"
LIVE_NAME = "live.json"  # the running call, for the dashboard's "now" panel (LiveCall)
LIVE_TOOLS = 200  # the tools a live call keeps, the newest
HEARTBEAT_SECONDS = 60  # without a terminal: one "still ..." line this often
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
TERMINAL_LINE_CHARS = 400  # longer messages are cut on the terminal; the log keeps them whole

VERBS = {"plan": "planning", "replan": "replanning", "author-checks": "writing checks",
         "implement": "implementing", "fix": "fixing", "validate-ui": "checking the UI"}

# Event types whose line stands out: (ANSI color, mark).
TONES = {"validation-failed": ("31", "✕"), "boundary-violation": ("31", "✕"),
         "service-error": ("33", "!"), "trial-voided": ("33", "!"), "stopped": ("31", "■"),
         "needs-input": ("33", "?"), "paused": ("33", "‖"), "validation-passed": ("32", "✓"),
         "milestone-achieved": ("32", "✓"), "completed": ("32", "■"), "approved": ("32", "✓")}


# Events whose message reads alone only with its kind in front.
PREFIXES = {"plan-stored": "plan stored: ", "task-implemented": "task ",
            "milestone-achieved": "milestone achieved: ", "retry-granted": "retry granted: ",
            "service-error": "service error: ", "git-commit": "git commit: ",
            "config-override": "config override: ", "lock-cleared": "lock cleared: "}


def duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"


def tool_summary(name, tool_input, target_dir=None):
    """`Bash: pytest -q`, `Edit app/models.py`: one short line for a tool call."""
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if name == "Bash":
        command = str(tool_input.get("command") or "").strip().splitlines()
        return f"Bash: {command[0][:120]}" if command else "Bash"
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if path:
        path = str(path)
        if target_dir and os.path.isabs(path):
            rel = os.path.relpath(path, target_dir)
            path = rel if not rel.startswith("..") else path
        return f"{name} {path}"
    if tool_input.get("pattern"):
        return f"{name} {str(tool_input['pattern'])[:80]}"
    if name.startswith("mcp__"):
        return name.split("__", 2)[-1]
    return name


class Progress:
    def __init__(self, level="normal", stream=None, env=None, tty=None):
        self.level = level
        self.stream = stream if stream is not None else sys.stderr
        env = os.environ if env is None else env
        if tty is None:
            try:
                tty = self.stream.isatty()
            except (AttributeError, ValueError):
                tty = False
        self.tty = tty
        self.color = tty and not env.get("NO_COLOR") and env.get("TERM") != "dumb"
        self._lock = threading.RLock()
        self._call = None       # the call running now: {label, started, tools, last, log_path}
        self._status_shown = False
        self._ticker = None
        self._stop = threading.Event()

    # --- lines -------------------------------------------------------------------------------------

    def _paint(self, code, text):
        return f"\x1b[{code}m{text}\x1b[0m" if self.color else text

    @staticmethod
    def _where(loop, milestone=None, trial=None):
        where = loop or ""
        if milestone:
            where += f" {milestone}"
        elif trial is not None:
            where += " plan"  # a planning trial
        if trial is not None:
            where += f" #{trial}"
        return where

    def line(self, where, message, log_path=None, tone=None, terminal=True):
        """Print `HH:MM:SS <where> <message>` (unless quiet), and append it to `log_path`."""
        now = datetime.now()
        if log_path:
            self._append(log_path, f"{now.isoformat(timespec='seconds')} {where}  {message}")
        if self.level == "quiet" or not terminal:
            return
        color, mark = tone or (None, None)
        text = message if len(message) <= TERMINAL_LINE_CHARS else \
            message[:TERMINAL_LINE_CHARS - 1] + "…"
        if mark:
            text = f"{mark} {text}"
        if color:
            text = self._paint(color, text)
        self._write(f"{self._paint('2', now.strftime('%H:%M:%S'))} {self._paint('1', where)}  "
                    f"{text}")

    def note(self, message):
        """An indented hint under the lines (the dashboard), terminal only."""
        if self.level != "quiet":
            self._write(f"         {self._paint('2', message)}")

    def event(self, loop, type, message, milestone=None, trial=None, log_path=None):
        self.line(self._where(loop, milestone, trial), PREFIXES.get(type, "") + message, log_path,
                  TONES.get(type))

    def _write(self, text):
        with self._lock:
            try:
                if self._status_shown:
                    self.stream.write("\r\x1b[2K")
                    self._status_shown = False
                self.stream.write(text + "\n")
                self._draw_status()
                self.stream.flush()
            except (OSError, ValueError):
                pass

    @staticmethod
    def _append(path, text):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass

    # --- calls -------------------------------------------------------------------------------------

    def call_started(self, loop, step, milestone=None, trial=None, model=None, log_path=None,
                     target_dir=None):
        label = VERBS.get(step, step)
        where = self._where(loop, milestone, trial)
        self.line(where, label + (f" ({model})" if model else ""), log_path)
        with self._lock:
            self._call = {"where": where, "label": label, "started": time.monotonic(),
                          "tools": 0, "last": None, "log_path": log_path,
                          "target_dir": target_dir, "beat": time.monotonic()}
        # Also when quiet: the log still gets a "still ..." line every minute. Each call has its
        # own stop signal, so a ticker still finishing a previous call never runs on for the next.
        self._stop = threading.Event()
        self._ticker = threading.Thread(target=self._tick, args=(self._stop,), daemon=True)
        self._ticker.start()

    def tool_use(self, name, tool_input=None):
        with self._lock:
            call = self._call
            if call is None:
                return
            call["tools"] += 1
            call["last"] = tool_summary(name, tool_input, call["target_dir"])
            summary, where, log_path = call["last"], call["where"], call["log_path"]
        if self.level == "verbose":
            self.line(where, "  " + summary, log_path)
        elif log_path:
            self.line(where, "  " + summary, log_path, terminal=False)

    def call_ended(self, step, seconds, cost=None, failure=None, tools=None):
        with self._lock:
            call, self._call = self._call, None
            self._stop.set()
            if self._status_shown:
                try:
                    self.stream.write("\r\x1b[2K")
                    self.stream.flush()
                except (OSError, ValueError):
                    pass
                self._status_shown = False
        if call is None:
            return
        tools = call["tools"] if tools is None else tools
        parts = [duration(seconds)]
        if cost is not None:
            parts.append(f"${cost:,.2f}")
        if tools:
            parts.append(f"{tools} tool call(s)")
        if failure:
            message, tone = f"{step} failed: {failure} ({', '.join(parts)})", TONES["stopped"]
        else:
            message, tone = f"{step} done ({', '.join(parts)})", None
        self.line(call["where"], message, call["log_path"], tone)

    def _status_text(self, call):
        elapsed = duration(time.monotonic() - call["started"])
        text = f"{call['where']}  {call['label']} · {elapsed}"
        if call["tools"]:
            text += f" · {call['tools']} tool call(s)"
        if call["last"]:
            text += f" · last: {call['last']}"
        return text

    def _draw_status(self):
        """Redraw the status line under the last line (terminal only; the lock is held)."""
        call = self._call
        if not (self.tty and call and self.level != "quiet"):
            return
        frame = SPINNER[int(time.monotonic() * 8) % len(SPINNER)]
        try:
            columns = os.get_terminal_size(self.stream.fileno()).columns
        except (AttributeError, OSError, ValueError):
            columns = 100
        text = f"{frame} {self._status_text(call)}"[:max(columns - 1, 20)]
        self.stream.write("\r\x1b[2K" + self._paint("36", text))
        self._status_shown = True

    def _tick(self, stop):
        while not stop.wait(0.25 if self.tty else 1):
            with self._lock:
                call = self._call
                if call is None or stop.is_set():
                    return
                if self.tty:
                    try:
                        self._draw_status()
                        self.stream.flush()
                    except (OSError, ValueError):
                        pass
                if time.monotonic() - call["beat"] < HEARTBEAT_SECONDS:
                    continue
                call["beat"] = time.monotonic()
                text = self._status_text(call).split("  ", 1)[1]
                # Every minute in the log (so `tail -f` shows a long call is alive), and on the
                # stream too when it has no status line. The lock is reentrant.
                self.line(call["where"], f"still {text}", call["log_path"], terminal=not self.tty)


class LiveCall:
    """The call running now, as `<loop>/state/live.json` (specs/005 data-model Live call, research
    R-8): `{loop, step, milestone_id, trial, model, session_id, started_at, pid, tools: [{at,
    name, summary}]}`. Written when the call starts, replaced after each tool Claude uses (the
    last LIVE_TOOLS kept), removed when it ends. A view file only: the engine never reads it, and
    a failure to write it never changes a run. `tool` is called from the thread reading Claude's
    output."""

    def __init__(self):
        self.path = None
        self.doc = None
        self.target_dir = None
        self._lock = threading.Lock()

    def start(self, loop_dir, loop, step, milestone_id=None, trial=None, model=None,
              session_id=None, target_dir=None):
        with self._lock:
            self.path = os.path.join(loop_dir, "state", LIVE_NAME)
            self.target_dir = target_dir
            self.doc = {"loop": loop, "step": step, "milestone_id": milestone_id, "trial": trial,
                        "model": model, "session_id": session_id, "started_at": state.now_iso(),
                        "pid": os.getpid(), "tools": []}
            self.write()

    def tool(self, name, tool_input=None, target_dir=None):
        with self._lock:
            if self.doc is None:
                return
            tools = self.doc["tools"]
            tools.append({"at": state.now_iso(), "name": name, "summary": tool_summary(
                name, tool_input, target_dir or self.target_dir)})
            del tools[:-LIVE_TOOLS]
            self.write()

    def end(self):
        with self._lock:
            if self.doc is None:
                return
            self.doc = None
            try:
                os.remove(self.path)
            except OSError:
                pass

    def write(self):
        """Replace the file atomically (`state.write_json_atomic`: a hidden temp file, then
        `os.replace`), so a reader never sees half of it. Called with the lock held."""
        try:
            state.write_json_atomic(self.path, self.doc)
        except OSError:
            pass


def log_path(loop_dir):
    return os.path.join(loop_dir, "state", LOG_NAME)


def from_args(args, env=None):
    """The command's `Progress`, from `--quiet` / `--verbose`. `--json` is quiet too, unless
    `--verbose`: a script reading the JSON object wants nothing else (run.log is still written)."""
    if getattr(args, "verbose", False):
        level = "verbose"
    elif getattr(args, "quiet", False) or getattr(args, "json", False):
        level = "quiet"
    else:
        level = "normal"
    return Progress(level, env=env)
