#!/usr/bin/env python3
"""PreToolUse guard for Bash: no process killing by name or pattern.

A Claude call runs with the driver's context in its own command line (the prompt, the target
path, `--add-dir` inputs), and so does the driver, so `pkill -f <target path>` or
`ps aux | grep app | xargs kill` can match the Claude process itself and end the trial with
exit 143. Processes a step started must be stopped by their PID.

Claude Code passes the hook input as JSON on stdin; the command is `tool_input.command`. The
command is split into simple commands (at `;`, `&`, `|`, newlines, and parentheses outside
quotes, and inside `$(...)` and backticks), and each one's command word is looked at, so a mere
mention (`grep -rn pkill .`, `echo "a; ps"`) is fine. Blocked (exit 2, the reason on stderr):

- `pkill`, `killall`, `killall5` (by name or pattern, or everything), also behind a launcher
  (`sudo -u me pkill`, `timeout 5 pkill`) or in `sh -c '...'`;
- `kill 0`, `kill -1`, and `kill -- -PGID` (the process group, or every process of the user);
- `kill` (or `xargs kill`) anywhere in a command that also looks processes up by name or pattern
  (`pgrep`, `pidof`, `ps` other than `ps -p`), whichever comes first:
  `P=$(pgrep -f app); kill $P` too.

Killing by PID (`kill $(cat app.pid)`, `kill 4242`) and by port (`fuser -k 8000/tcp`,
`kill $(lsof -t -i:8000)`) is allowed: only the application listens on its port. Unreadable
input is allowed, since this guard protects the trial rather than a boundary (the write guard
fails closed).
"""
import json
import os
import re
import shlex
import sys

BY_NAME = {"pkill", "killall", "killall5"}
LOOKUPS = {"pgrep", "pidof", "ps"}
# Launchers that run the command after them; their own options and option values are skipped by
# looking for the first word that is a command this guard cares about.
WRAPPERS = {"sudo", "doas", "exec", "nohup", "command", "builtin", "time", "env", "nice",
            "setsid", "timeout", "stdbuf", "ionice", "chrt", "taskset", "unbuffer", "xargs"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
SEPARATOR = re.compile(r"^[;&|()\n]+$")
SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
WATCHED = BY_NAME | LOOKUPS | {"kill"}

REASON = ("devloops guard: {what} stops processes by name or pattern (or all of them), which can "
          "match this Claude call or the devloops driver (their command lines contain the target "
          "path) and end the trial. Stop only processes you started, by their PID: start a "
          "server with `cmd > app.log 2>&1 & echo $! > app.pid`, stop it with "
          "`kill $(cat app.pid)`, and check it stopped with `kill -0 $(cat app.pid)` or "
          "`ps -p $(cat app.pid)`. Freeing a port with `fuser -k <port>/tcp` is fine.")


def _tokens(command):
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:  # an unbalanced quote: fall back to a plain split
        return re.split(r"\s+|(?=[;&|()])|(?<=[;&|()])", command)


def commands(command, depth=0):
    """`[(name, args)]` for each simple command, `name` being the command word's basename.

    Command substitutions (`$(...)`, backticks, also inside quotes) and `sh -c '...'` strings are
    looked into as well.
    """
    found, words = [], []
    if depth < 5:  # in the raw text, so quoted ones (`kill "$(pgrep x)"`) are found too
        for inner in SUBSTITUTION.findall(command):
            found += commands(inner[0] or inner[1], depth + 1)
    for token in _tokens(command) + [";"]:
        if not token:
            continue
        if SEPARATOR.match(token):
            found += _simple(words, depth)
            words = []
        else:
            words.append(token)
    return found


def _simple(words, depth):
    while words and ASSIGNMENT.match(words[0]):
        words = words[1:]
    if not words:
        return []
    name = os.path.basename(words[0])
    if name in SHELLS and "-c" in words[1:] and depth < 5:
        i = words.index("-c")
        return commands(words[i + 1], depth + 1) if i + 1 < len(words) else []
    if name in WRAPPERS:
        for i, word in enumerate(words[1:], 1):
            if os.path.basename(word) in WATCHED:  # `sudo -u me pkill`, `timeout 5 kill -1`
                return _simple(words[i:], depth) + ([("xargs", ["kill"])]
                                                    if name == "xargs" else [])
        return [(name, words[1:])]
    return [(name, words[1:])]


def _kill_targets(args):
    """The PIDs a `kill` names: its first `-X` is the signal, `-s`/`-n` take a value, `--` ends
    the options; a later `-N` is a process group."""
    targets, i, options = [], 0, True
    while i < len(args):
        arg = args[i]
        if options and arg == "--":
            options = False
        elif options and arg in ("-s", "-n"):
            i += 1
        elif options and arg.startswith("-") and i == 0:
            pass  # the signal (-9, -TERM); `-l` lists signals
        else:
            targets.append(arg)
        i += 1
    return targets


def decide(payload):
    """Return None to allow the command, or the reason to block it."""
    cmds = commands((payload.get("tool_input") or {}).get("command") or "")
    names = {name for name, _ in cmds}
    by_name = sorted(names & BY_NAME)
    if by_name:
        return REASON.format(what="/".join(by_name))
    for name, args in cmds:
        if name == "kill" and any(t in ("0", "-1") or t.startswith("-")
                                  for t in _kill_targets(args)):
            return REASON.format(what=f"kill {' '.join(args)}")
    kills = "kill" in names or ("xargs", ["kill"]) in cmds
    lookups = sorted({name for name, args in cmds if name in LOOKUPS
                      and not (name == "ps" and {"-p", "--pid", "q"} & set(args))})
    if kills and lookups:
        return REASON.format(what=f"kill with {'/'.join(lookups)}")
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    reason = decide(payload)
    if reason is None:
        return 0
    sys.stderr.write(reason + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
