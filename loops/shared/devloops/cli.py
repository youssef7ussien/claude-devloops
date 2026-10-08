"""`devloops` command line (contracts/cli.md)."""
import argparse
import csv
import json
import os
import re
import shlex
import subprocess
import sys

from . import (__version__, checkcmd, dashboard, engine, fulldash, initcmd, orchestrator, prompts,
               render, serve, state, workspace)
from . import config as config_mod
from . import progress as progress_mod
from . import project as project_mod
from .kit import Kit
from .state import EXIT_USAGE, DevloopsError

LOOPS = ("backend-dev", "frontend-dev")


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # usage errors exit 2 (argparse's default too; kept explicit)
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def _positive_int(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not an integer")
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def _port(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a port number")
    if not 0 <= value <= 65535:
        raise argparse.ArgumentTypeError("must be from 0 to 65535 (0: any free port)")
    return value


def _add_requirements_options(cmd, text):
    req = cmd.add_mutually_exclusive_group()
    req.add_argument("--requirements", help=text)
    req.add_argument("--speckit-feature", nargs="?", const="active", metavar="DIR",
                     help="a spec-kit feature folder as the requirements (no value: the active "
                          "feature in .specify/feature.json)")


def _add_story_options(cmd):
    story = cmd.add_mutually_exclusive_group()
    story.add_argument("--story-id", help="implement only this story of --requirements (a PRD)")
    story.add_argument("--story-file", action="store_true",
                       help="--requirements is a standalone story file")


def _add_questions_option(parser):
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--review-plan", action="store_true",
                      help="pause after each plan for review, and stop on open questions (sets "
                           "questions: ask)")
    mode.add_argument("--accept-suggested", action="store_true",
                      help="approve plans and accept Claude's suggested answers without pausing "
                           "(questions: accept-suggested, the default; review them afterwards)")


def _questions_override(args):
    if getattr(args, "review_plan", False):
        return "ask"
    return "accept-suggested" if getattr(args, "accept_suggested", False) else None


def _add_decision_options(cmd):
    cmd.add_argument("--no-continue", action="store_true",
                     help="only record the decision; run nothing (the run continues on the next "
                          "`devloops run`)")
    _add_questions_option(cmd)


def _add_progress_options(cmd):
    level = cmd.add_mutually_exclusive_group()
    level.add_argument("--quiet", action="store_true",
                       help="print no progress lines, only the final summary")
    level.add_argument("--verbose", action="store_true",
                       help="also print each tool Claude uses")


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace",
                        help="workspace name (under the project's workspaces_dir) or path; created "
                             "on the first run (default: the project's `workspace`, else main)")
    common.add_argument("--config", help="config file merged over the defaults")
    common.add_argument("--json", action="store_true", help="print one JSON status object")

    parser = _Parser(prog="devloops", description="Reusable development loops driven by "
                                                  "headless Claude Code.")
    parser.add_argument("--version", action="version", version=f"devloops {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    # No abbreviations: the removed `--target` must not pass for `--target-root` (003 FR-008).
    run = sub.add_parser("run", parents=[common], allow_abbrev=False,
                         help="start or resume the run: backend-dev, then frontend-dev, as the "
                              "project configures")
    _add_requirements_options(run, "PRD or story Markdown file, passed to every loop (default: "
                                   "the recorded one, then the project's)")
    _add_story_options(run)
    run.add_argument("--target-root",
                     help="place the project's loops at <dir>/backend and <dir>/frontend (first "
                          "run)")
    run.add_argument("--backend-target", help="backend-dev's target (overrides --target-root)")
    run.add_argument("--frontend-target", help="frontend-dev's target (overrides --target-root)")
    run.add_argument("--max-trials", type=_positive_int,
                     help="override max_trials for every loop this command runs")
    _add_questions_option(run)
    _add_progress_options(run)
    run.add_argument("--force-unlock", action="store_true", help="clear a stale lock")

    for name, text in (("approve", "accept the stored plan and the answers, then continue"),
                       ("replan", "plan again with the answers, then continue")):
        cmd = sub.add_parser(name, parents=[common], help=text)
        _add_decision_options(cmd)
        _add_progress_options(cmd)
        cmd.add_argument("--force-unlock", action="store_true", help="clear a stale lock")

    retry = sub.add_parser("retry", parents=[common],
                           help="grant a failed milestone more trials, then continue (FR-063)")
    retry.add_argument("--milestone", required=True, help="the failed milestone, e.g. M01")
    retry.add_argument("--reason",
                       help="guidance for the next fix trial; recorded with the grant")
    retry.add_argument("--trials", type=_positive_int,
                       help="trials to grant (default: max_trials)")
    _add_decision_options(retry)
    _add_progress_options(retry)
    retry.add_argument("--force-unlock", action="store_true", help="clear a stale lock")

    export = sub.add_parser("export-sessions", parents=[common],
                            help="write every Claude invocation as CSV (FR-033)")
    export.add_argument("--csv", metavar="FILE", help="output file (default: standard output)")

    dash = sub.add_parser("dashboard", parents=[common],
                          help="refresh <workspace>/dashboard.html; --serve shows files and "
                               "conversations live, --export writes one shareable file")
    how = dash.add_mutually_exclusive_group()
    how.add_argument("--serve", action="store_true",
                     help="serve the dashboards of every workspace, with each file and "
                          "conversation, live, until Ctrl+C (read-only)")
    how.add_argument("--export", action="store_true",
                     help="write a self-contained full dashboard (every file and conversation "
                          "embedded) to share or keep")
    how.add_argument("--light", action="store_true", help=argparse.SUPPRESS)  # the default now
    dash.add_argument("--host", help="with --serve: the address to listen on (default: "
                                     "127.0.0.1; 0.0.0.0 for every network, with a token)")
    dash.add_argument("--port", type=_port, help=f"with --serve: the port (default: "
                                                  f"{serve.DEFAULT_PORT}, or the next free one)")
    dash.add_argument("--open", action="store_true", help="with --serve: open it in a browser")
    dash.add_argument("--token", help="with --serve: the token to require (default: a random one "
                                      "when listening beyond this machine)")
    dash.add_argument("--no-token", action="store_true",
                      help="with --serve: require no token, even beyond this machine")
    dash.add_argument("--out", metavar="FILE",
                      help="with --export: the file to write (default: a new file in the "
                           "dashboards folder)")

    status = sub.add_parser("status", parents=[common], help="show run status (read-only)")
    status.add_argument("loop", nargs="?", choices=LOOPS)

    check = sub.add_parser("check", help="report whether this environment is ready for the loops")
    check.add_argument("--json", action="store_true", help="print the result as JSON")

    init = sub.add_parser("init", help="set up a directory as a devloops project")
    init.add_argument("dir", nargs="?", default=".", help="the project root (default: .)")
    init.add_argument("--backend-target", help="backend-dev's target (default: backend)")
    init.add_argument("--frontend-target", help="frontend-dev's target (default: frontend)")
    req = init.add_mutually_exclusive_group()
    req.add_argument("--requirements", help="default requirements file (PRD or story)")
    req.add_argument("--speckit-feature", nargs="?", const="active", metavar="DIR",
                     help="default spec-kit feature folder (no value: the active feature)")
    init.add_argument("--no-prompt", action="store_true",
                      help="never ask (implied when stdin or stdout is not a terminal)")
    init.add_argument("--no-models", action="store_true",
                      help="write no model choice into devloops.json (default: opus to plan and "
                           "write checks, sonnet to build); Claude Code then picks the model")
    init.add_argument("--track-workspaces", action="store_true",
                      help="do not git-ignore the workspaces folder")
    init.add_argument("--track-dashboards", action="store_true",
                      help="do not git-ignore the full dashboards folder")
    init.add_argument("--allow-skills", action="store_true",
                      help="add the devloops permission rule to .claude/settings.json (also on "
                           "an initialized project)")
    init.add_argument("--upgrade", action="store_true",
                      help="update the installed files of an initialized project, keeping the "
                           "ones changed here")
    init.add_argument("--restore", action="store_true",
                      help="with --upgrade, re-create installed files that were deleted")
    init.add_argument("--json", action="store_true", help="print the result as JSON")
    return parser


LARGE_EVIDENCE_BYTES = 1024 * 1024


def large_evidence(ws, loops=LOOPS):
    """Evidence files over 1 MB, the likeliest place for a secret to hide (research R-21).

    `[{path, bytes}]`, largest first, with paths relative to the workspace. Read-only.
    """
    found = []
    for loop in loops:
        milestones = os.path.join(ws.loop_dir(loop), "state", "milestones")
        for dirpath, _, names in os.walk(milestones):
            if "evidence" not in os.path.relpath(dirpath, milestones).split(os.sep):
                continue
            for name in names:
                path = os.path.join(dirpath, name)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                if size > LARGE_EVIDENCE_BYTES:
                    found.append({"path": os.path.relpath(path, ws.path), "bytes": size})
    return sorted(found, key=lambda item: (-item["bytes"], item["path"]))


SESSION_COLUMNS = ("workspace", "loop", "step", "model", "milestone", "trial", "session_id",
                   "prompt_path", "input_tokens", "output_tokens", "cache_creation_tokens",
                   "cache_read_tokens", "cost_usd", "started_at", "ended_at")


def session_rows(ws):
    """One row per invocation in every loop's `state/invocations.jsonl`, in loop then call order.

    `prompt_path` is relative to the workspace. A token count or cost Claude did not report is
    left empty, and so is `model` when the call ran on Claude Code's default model.
    """
    for loop in LOOPS:
        loop_dir = ws.loop_dir(loop)
        records = state.read_jsonl(os.path.join(loop_dir, "state", "invocations.jsonl"))
        for rec in sorted(records, key=lambda r: r.get("seq") or 0):
            tokens = rec.get("tokens") or {}
            prompt = rec.get("prompt_path")
            yield {
                "workspace": ws.name, "loop": rec.get("loop") or loop, "step": rec.get("step"),
                "model": rec.get("model"), "milestone": rec.get("milestone_id"), "trial": rec.get("trial"),
                "session_id": rec.get("session_id"),
                "prompt_path": os.path.join(loop, prompt) if prompt else None,
                "input_tokens": tokens.get("input"), "output_tokens": tokens.get("output"),
                "cache_creation_tokens": tokens.get("cache_creation"),
                "cache_read_tokens": tokens.get("cache_read"), "cost_usd": rec.get("cost_usd"),
                "started_at": rec.get("started_at"), "ended_at": rec.get("ended_at"),
            }


def _export_sessions(args, ws):
    rows = list(session_rows(ws))
    out = open(args.csv, "w", encoding="utf-8", newline="") if args.csv else sys.stdout
    try:
        writer = csv.DictWriter(out, fieldnames=SESSION_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if args.csv:
            out.close()
    if args.csv and args.json:
        _dump(args, {"workspace": ws.name, "csv": os.path.abspath(args.csv),
                     "invocations": len(rows)})
    elif args.csv:
        print(f"{len(rows)} invocation(s) written to {os.path.abspath(args.csv)}")
    return 0


def _version_warnings(project, kit):
    """The FR-029 warning when the project was set up with another devloops version."""
    manifest = project.manifest() if project else None
    installed = (manifest or {}).get("devloops_version")
    if not installed or installed == kit.version:
        return []
    try:
        newer = initcmd.version_tuple(installed) > initcmd.version_tuple(kit.version)
    except ValueError:
        newer = False
    advice = f"Install devloops {installed} or later." if newer else \
        'Run "devloops init --upgrade".'
    return [f"this project was set up with devloops {installed}; running {kit.version}. {advice}"]


def _dump(args, obj):
    """Print one `--json` object, with the command's warnings (FR-029) when there are any."""
    if getattr(args, "warnings", None):
        obj = dict(obj, warnings=list(args.warnings))
    print(json.dumps(obj, indent=2))


def _print_status(obj, message=None):
    if message:
        print(message)
    print(f"{obj['loop']}: {obj['status']}")
    reason = obj.get("status_reason")
    if reason:
        print(f"  reason: {reason.get('code')}: {reason.get('message')}")
    if obj.get("next_milestone"):
        print(f"  next milestone: {obj['next_milestone']} (trials used {obj['trials_used']} of "
              f"{obj['trial_limit']})")
    elif obj.get("trial_limit") is not None:
        print(f"  planning trials used: {obj['trials_used']} of {obj['trial_limit']}")
    failure = obj.get("last_failure")
    if failure:
        where = f"{failure['milestone_id']} trial {failure['trial']}" if failure["milestone_id"] \
            else f"planning trial {failure['trial']}"
        print(f"  last failure: {where}: {failure.get('reason')}: "
              f"{(failure.get('detail') or '')[:300]}")
    if obj.get("speckit_feature"):
        print(f"  spec-kit feature: {obj['speckit_feature']}")
    if obj.get("ui_url"):
        print(f"  UI URL: {obj['ui_url']}")
    if obj.get("openapi_artifact"):
        print(f"  OpenAPI artifact: {obj['openapi_artifact'].get('path')}")
    if obj.get("config_drift"):
        print(f"  configuration changed since the first run (not applied): "
              f"{', '.join(obj['config_drift'])}")
    if obj.get("prompt_drift"):
        print(f"  prompt parts changed since the first run (used from the next start): "
              f"{', '.join(obj['prompt_drift'])}")
    if obj["status"] != "not-started":
        print(f"  progress: {obj['progress']}")


def _dashboard_path(ws):
    path = os.path.join(ws.path, dashboard.FILENAME)
    return path if os.path.exists(path) and _light_on(ws) else None


def _light_on(ws):
    """Whether commands write `dashboard.html` (`dashboard.light`, on by default). A view
    preference, so it is read from the configuration files as they are now (config.LIVE_KEYS)."""
    try:
        value = config_mod.live_value(ws.project, ws.config_path(), "dashboard.light",
                                      ws.kit.path("shared", "config", "defaults.json"))
    except (AttributeError, DevloopsError):
        return True
    return value is not False


def _files_hint(args, ws):
    """Where to see files and conversations: the running server's URL, or the command to start
    one (the same command the summary page names)."""
    rec = serve.running(ws.project, getattr(args, "env", None))
    if rec:
        return f"files and conversations: {serve.url_for(rec, ws.name)} (dashboard server running)"
    return f"files and conversations: {dashboard.serve_command(ws)}"


def _emit(args, ws, loop, message, code, full=None):
    obj = engine.status_object(ws, loop)
    obj["dashboard"] = _dashboard_path(ws)
    if full:
        obj["full_dashboard"] = {"path": full["path"], "bytes": full["bytes"]}
    if args.json:
        obj["exit_code"] = code
        if message:
            obj["message"] = message
        _dump(args, obj)
    else:
        _print_status(obj, message)
        _print_dashboards(args, ws, obj["dashboard"], full)


def _print_dashboards(args, ws, path, full):
    """Where to look next: the summary page, a full dashboard written at the stop, and where
    files and conversations are."""
    if path:
        print(f"dashboard: {path}")
    if full:
        _print_full(full)
    print(_files_hint(args, ws))


def _start_hint(progress, args, ws, loops):
    """Before a command runs loops: where to look while it works (the summary page is written
    when it pauses, stops, or ends)."""
    progress.note(_files_hint(args, ws))
    for loop in loops:
        progress.note(f"log{f' ({loop})' if len(loops) > 1 else ''}: "
                      f"{progress_mod.log_path(ws.loop_dir(loop))}")


def _full_on_stop(ws, project, kit):
    """Whether to write a full dashboard at a final status (`dashboard.full_on_stop`, off by
    default: `devloops dashboard` writes one on demand). A view preference, so it is read from the
    configuration files as they are now (config.LIVE_KEYS), not from the run's frozen copy."""
    return bool(config_mod.live_value(project, ws.config_path(), "dashboard.full_on_stop",
                                      kit.path("shared", "config", "defaults.json")))


def _print_full(full, largest=False):
    if not full:
        return
    print(f"full dashboard: {full['path']} ({fulldash.human_bytes(full['bytes'])})")
    if largest and full["largest"]:
        print("  largest embedded items:")
        for item in full["largest"]:
            print(f"    {item['path']} ({fulldash.human_bytes(item['bytes'])})")
    if full["unavailable"]:
        print(f"  {full['unavailable']} conversation(s) unavailable")
    if full.get("not_embedded"):
        print(f"  not embedded (over {fulldash.human_bytes(fulldash.MAX_EMBED_BYTES)}):")
        for item in full["not_embedded"]:
            print(f"    {item['path']} ({fulldash.human_bytes(item['bytes'])})")


def _ends_final(error, status):
    """Whether a command ended in a final status (FR-039).

    Not when it was refused (a lock or a usage error) or interrupted: an interrupt must not wait
    for a page that embeds every conversation.
    """
    if error is not None and (not isinstance(error, DevloopsError) or
                              isinstance(error, (state.LockHeld, state.UsageError))):
        return False
    return fulldash.is_final(status)


def _event_marks(ws, loops):
    """The size of each loop's event log: a command that changed a run recorded an event, so a
    command that did nothing (a run already ended) writes no new full dashboard."""
    def size(loop):
        try:
            return os.path.getsize(os.path.join(ws.loop_dir(loop), "state", "events.jsonl"))
        except OSError:
            return 0
    return [size(loop) for loop in loops]


def _write_full_dashboard(ws, trigger, env, out=None):
    """Write a new full dashboard; a failure only warns, like the lightweight one (FR-039)."""
    try:
        return fulldash.write(ws, trigger=trigger, env=env, out=out)
    except Exception as e:  # noqa: BLE001 - a view; the command's result stands
        print(f"devloops: warning: could not write the full dashboard: {e}", file=sys.stderr)
        return None


def _speckit_flag(value):
    """A `--speckit-feature` value: `active`, or a folder relative to the current directory."""
    return value if value in (None, "active") else os.path.abspath(value)


def _project_defaults(project, ws, requirements, speckit_feature, story_id, story_file):
    """Fill the requirements the command line left out (FR-011).

    What the workspace `ws` recorded comes first (a first start that stopped early still recorded
    it; `ws` is None before the first run), then the project configuration. So a later edit of the
    configuration is drift, not a mismatch (FR-015). The requirements are a file or a spec-kit
    feature (002 FR-023). Returns `(requirements, speckit_feature, story_id, story_file)`.
    """
    if speckit_feature and story_file:
        raise state.UsageError("--speckit-feature and --story-file are mutually exclusive "
                               "(select a spec-kit story with --story-id US<n>)")
    if requirements or speckit_feature:
        return requirements, speckit_feature, story_id, story_file
    recorded = (ws.data.get("requirements") if ws else None) or {}
    configured = project.requirements or {}
    no_story_flags = story_id is None and not story_file
    if recorded:
        speckit_feature = ws.speckit_feature()
        requirements = None if speckit_feature else ws.requirements_path()
        if no_story_flags:
            story_id, story_file = recorded.get("story_id"), recorded.get("mode") == "story-file"
    elif configured.get("path"):
        requirements = configured["path"]
        if no_story_flags:
            story_file = bool(configured.get("story_file"))
    elif configured.get("speckit_feature"):
        value = configured["speckit_feature"]
        speckit_feature = value if value == "active" else project.resolve(value)
    return requirements, speckit_feature, story_id, story_file


def _existing_workspace(args, project, kit):
    """The command's workspace, or None before its first run (nothing is created)."""
    path, _ = workspace.resolve_path(args.workspace, project)
    if not os.path.exists(os.path.join(path, "workspace.json")):
        return None
    return workspace.open_workspace(args.workspace, project, kit, create=False)


def _run(args, kit, project, env, action=None, selected=None):
    """`devloops run`, or a decision continuing the run (`action`, see `Orchestrator.run`, with
    the loops `_decide` selected; its args lack the run flags) (003 FR-001-007)."""
    for loop in orchestrator.LOOP_ORDER:
        engine.load_loop_def(kit, loop)  # before a workspace is created
    ws = _existing_workspace(args, project, kit)
    if selected is None:
        selected = orchestrator.select_loops(
            project, ws, getattr(args, "backend_target", None),
            getattr(args, "frontend_target", None), getattr(args, "target_root", None))
    try:  # also for a decision's selection: the same loops, the same checks
        orchestrator.check_selection(selected)  # FR-006: before anything is created
    except state.StopRun as e:
        if not args.json:
            raise
        _dump(args, {"exit_code": e.exit_code, "status_reason": e.status_reason()})
        return e.exit_code
    requirements, feature, story_id, story_file = _project_defaults(
        project, ws, getattr(args, "requirements", None),
        _speckit_flag(getattr(args, "speckit_feature", None)),
        getattr(args, "story_id", None), getattr(args, "story_file", False))
    ws = ws or workspace.open_workspace(args.workspace, project, kit, create=True)
    orch = orchestrator.Orchestrator(ws, orchestrator.OrchestrateOptions(
        requirements=requirements, speckit_feature=feature, story_id=story_id,
        story_file=story_file, config_path=args.config, force_unlock=args.force_unlock,
        questions=_questions_override(args), max_trials=getattr(args, "max_trials", None),
        selected=selected), kit=kit, env=env)
    orch.progress = progress_mod.from_args(args, env)
    loops = list(selected)
    _start_hint(orch.progress, args, ws, loops)
    error = full = None
    before = _event_marks(ws, loops)
    try:
        code = orch.run(action)
    except BaseException as e:
        error = e
        raise
    finally:
        # Once, at the end, covering every loop, when the loop this command ran last ended in a
        # final status: a loop skipped because an earlier run completed it does not count (FR-039).
        last = orch.last_run
        if last and _ends_final(error, engine.status_object(ws, last)["status"]) \
                and _event_marks(ws, loops) != before \
                and _full_on_stop(ws, project, kit):
            full = _write_full_dashboard(ws, "run", env)
        _write_dashboard(ws, announce=False, light=True)
    statuses = {loop: engine.status_object(ws, loop) for loop in loops}
    if args.json:
        obj = {"workspace": ws.name, "run": orch.state, "loops": statuses,
               "exit_code": code, "message": orch.message, "dashboard": _dashboard_path(ws)}
        if action:
            obj["decision"] = {"command": args.command, "loop": action[0]}
        if full:
            obj["full_dashboard"] = {"path": full["path"], "bytes": full["bytes"]}
        _dump(args, obj)
    else:
        if orch.message:
            print(orch.message)
        print(f"run: {orch.state['status']}")
        for obj in statuses.values():
            _print_status(obj)
        _print_dashboards(args, ws, _dashboard_path(ws), full)
    if code == state.EXIT_CODES["awaiting-approval"] and orch.last_run and _interactive(args):
        return _review(args, kit, project, env, ws, orch.last_run)
    return code


# --- the review prompt ----------------------------------------------------------------------------

def _interactive(args):
    """Whether a plan pause may ask in the terminal: never with --json or without a terminal."""
    if getattr(args, "json", False):
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


REVIEW_CHOICES = "[a]pprove  [e]dit answers  [r]eplan  [q]uit"


def _plan_line(ws, loop):
    loop_dir = ws.loop_dir(loop)
    plan = state.read_json(os.path.join(loop_dir, "state", "plan.json")) or {}
    questions = render.load_questions(loop_dir)
    sources = {qid: render.effective_answer(q)[1] for qid, q in questions.items()}
    answered = sum(1 for source in sources.values() if source in ("developer", "accepted"))
    suggested = sum(1 for source in sources.values() if source == "suggested")
    neither = [qid for qid, source in sources.items() if not source]
    text = (f"{loop} plan: {len(plan.get('milestones') or [])} milestone(s), "
            f"{len(questions)} question(s)")
    if questions:
        parts = [f"{answered} answered"] if answered else []
        parts += [f"{suggested} with a suggested answer"] if suggested else []
        parts += [f"{', '.join(neither)} with neither"] if neither else []
        text += ": " + ", ".join(parts)
    return text


def _edit(path, env):
    editor = env.get("VISUAL") or env.get("EDITOR")
    if not editor:
        try:
            input(f"Edit {path}, then press Enter: ")
        except EOFError:
            pass
        return
    try:
        subprocess.call(shlex.split(editor) + [path])
    except OSError as e:
        print(f"devloops: could not start {editor!r}: {e}", file=sys.stderr)


def _review(args, kit, project, env, ws, loop):
    """Ask at `loop`'s plan pause: approve or replan (and continue), edit the answers, or quit
    with the pause's exit code 10."""
    outputs = os.path.join(ws.loop_dir(loop), "outputs")
    print()
    print(_plan_line(ws, loop))
    print(f"Review: {os.path.join(outputs, 'plan-summary.md')}")
    while True:
        try:
            choice = input(f"{REVIEW_CHOICES}: ").strip().lower()[:1]
        except EOFError:
            choice = "q"
        if choice == "e":
            _edit(os.path.join(outputs, "open-questions.md"), env)
            print(_plan_line(ws, loop))
        elif choice in ("a", "r"):
            break
        elif choice == "q":
            print("The plan awaits approval: `devloops approve` approves it and continues.")
            return state.EXIT_CODES["awaiting-approval"]
    # Only what `devloops approve|replan` would get: the run's inputs and targets are recorded,
    # and its questions mode is already frozen (or recorded in run/state.json).
    decided = argparse.Namespace(
        command="approve" if choice == "a" else "replan", workspace=args.workspace,
        config=args.config, json=args.json, force_unlock=args.force_unlock, no_continue=False,
        review_plan=False, accept_suggested=False, warnings=getattr(args, "warnings", []),
        quiet=getattr(args, "quiet", False), verbose=getattr(args, "verbose", False),
        workspace_flag=getattr(args, "workspace_flag", ""), env=getattr(args, "env", None))
    return _decide(decided, kit, project, env)


# --- approve, replan, retry -----------------------------------------------------------------------

# The status of the loop each decision applies to (003 FR-009).
DECISION_STATUS = {"approve": "awaiting-approval", "replan": "awaiting-approval",
                   "retry": "stopped-on-failure"}


def _run_status(ws):
    """The run's status from `run/state.json`, for messages; `not started` without one."""
    return (orchestrator.read_state(ws) or {}).get("status") or "not started"


def _decide(args, kit, project, env):
    """`approve`, `replan`, or `retry` (003 FR-009, FR-010, research R-4): the decision goes to
    the run's loop that waits for it, then the whole run continues, unless --no-continue (the
    decision is only recorded; the next `devloops run` continues)."""
    continuing = not getattr(args, "no_continue", False)
    if not continuing and _questions_override(args):
        raise state.UsageError("--review-plan and --accept-suggested apply to the continued run; "
                               "with --no-continue, pass them to the next `devloops run`")
    ws = workspace.open_workspace(args.workspace, project, kit, create=False)
    selected = orchestrator.select_loops(project, ws)
    wanted = DECISION_STATUS[args.command]
    loop = next((name for name in selected
                 if engine.status_object(ws, name)["status"] == wanted), None)
    if loop is None:
        what = "nothing awaits approval" if wanted == "awaiting-approval" \
            else "no loop is stopped on failure"
        raise state.UsageError(f"{what} (run: {_run_status(ws)})")

    def decide(eng):
        if args.command == "retry":
            return eng.retry(args.milestone, args.reason, args.trials, continue_run=continuing)
        return getattr(eng, args.command)(continue_run=continuing)

    if continuing:
        return _run(args, kit, project, env, action=(loop, decide), selected=selected)
    engine.load_loop_def(kit, loop)
    options = engine.Options(config_path=args.config, force_unlock=args.force_unlock,
                             cli_overrides={"questions": None})
    eng = engine.Engine(loop, ws, options, kit=kit, project=project, env=env)
    eng.progress = progress_mod.from_args(args, env)
    eng.resume_command = "devloops run"
    error = full = None
    before = _event_marks(ws, [loop])
    try:
        code = decide(eng)
    except BaseException as e:
        error = e
        raise
    finally:
        if _ends_final(error, engine.status_object(ws, loop)["status"]) \
                and _event_marks(ws, [loop]) != before \
                and _full_on_stop(ws, project, kit):
            full = _write_full_dashboard(ws, args.command, env)
        _write_dashboard(ws, announce=False, light=True)
    orchestrator.Orchestrator(ws, kit=kit, env=env).sync_step(loop)
    _emit(args, ws, loop, eng.message, code, full)
    return code


def _write_dashboard(ws, announce, light=False):
    """Refresh the workspace's summary page, when a command pauses, stops, or ends (`light`: only
    if `dashboard.light` is on) or on demand. A failure only warns: it never changes a run's
    outcome."""
    if light and not _light_on(ws):
        return None
    try:
        path = dashboard.write(ws)
    except Exception as e:  # noqa: BLE001 - the dashboard is a view; the run's result stands
        print(f"devloops: warning: could not write the dashboard: {e}", file=sys.stderr)
        return None
    if announce:
        print(f"dashboard: {path}")
    return path


def _dashboard(args, kit, project, env):
    """`devloops dashboard [--serve | --export]` (contracts/cli.md)."""
    for flag, given in (("--host", args.host), ("--port", args.port is not None),
                        ("--open", args.open), ("--token", args.token),
                        ("--no-token", args.no_token)):
        if given and not args.serve:
            raise state.UsageError(f"{flag} goes with --serve")
    if args.out and not args.export:
        raise state.UsageError("--out goes with --export")
    if args.token is not None and args.no_token:
        raise state.UsageError("--token and --no-token cannot go together")
    if args.token is not None and not re.fullmatch(r"[A-Za-z0-9._~-]{8,}", args.token):
        raise state.UsageError("--token must be at least 8 characters from A-Z a-z 0-9 . _ ~ -")
    try:
        ws = workspace.open_workspace(args.workspace, project, kit, create=False)
    except state.UsageError:
        # A server covers every workspace: without --workspace it opens on any of them.
        names = serve.Site(project, kit, env).workspaces() if args.serve else {}
        if not names or args.workspace_given:
            raise
        ws = workspace.open_workspace(next(iter(names)), project, kit, create=False)
    if args.serve:
        return serve.serve(project, kit, ws, host=args.host or "127.0.0.1", port=args.port,
                           token=args.token, use_token=False if args.no_token else None,
                           open_browser=args.open, as_json=args.json, env=env)
    if args.export:
        full = _write_full_dashboard(ws, "dashboard command", env, out=args.out)
        # The summary page links the exported dashboards (FR-036a): refresh it to list this one.
        path = _write_dashboard(ws, announce=False, light=True)
        if args.json:
            _dump(args, {"workspace": ws.name, "dashboard": path, "full_dashboard": full and {
                k: full[k] for k in ("path", "bytes", "largest", "unavailable", "not_embedded")}})
        else:
            _print_full(full, largest=True)
        return 0 if full else 1
    path = _write_dashboard(ws, announce=not args.json)
    rec = serve.running(project, env)
    if args.json:
        _dump(args, {"workspace": ws.name, "dashboard": path,
                     "serving": serve.url_for(rec, ws.name) if rec else None})
    else:
        print(_files_hint(args, ws))
    return 0 if path else 1


def _init(args, kit):
    """`devloops init` (contracts/cli.md): needs no project; exit 0, 30, or 2."""
    opts = initcmd.InitOptions(
        backend_target=args.backend_target, frontend_target=args.frontend_target,
        requirements=args.requirements, speckit_feature=args.speckit_feature,
        no_prompt=args.no_prompt or args.json, track_workspaces=args.track_workspaces,
        track_dashboards=args.track_dashboards, allow_skills=args.allow_skills,
        models=not args.no_models)
    root = os.path.abspath(args.dir)
    if args.restore and not args.upgrade:
        raise state.UsageError("--restore needs --upgrade")
    if args.upgrade:
        given = [flag for flag, value in (
            ("--backend-target", args.backend_target), ("--frontend-target", args.frontend_target),
            ("--requirements", args.requirements), ("--speckit-feature", args.speckit_feature),
            ("--track-workspaces", args.track_workspaces),
            ("--track-dashboards", args.track_dashboards),
            ("--no-models", args.no_models)) if value]
        if given:
            raise state.UsageError(f"--upgrade does not change the project configuration "
                                   f"({', '.join(given)}): edit .devloops/devloops.json instead")
    try:
        answers = None
        if args.upgrade:
            result = _upgrade(args, kit, root)
            return _print_init(args, result)
        # Nothing to ask once the project is initialized, or when devloops.json is kept as it is.
        if not any(os.path.exists(os.path.join(root, project_mod.DIRNAME, name))
                   for name in (project_mod.MANIFEST_NAME, project_mod.CONFIG_NAME)):
            answers = initcmd.ask_missing(opts, root, kit, sys.stdin, sys.stdout)
        result = initcmd.init(root, kit, opts, answers)
    except (initcmd.InitError, state.StopRun, project_mod.ProjectConfigError) as e:
        message = f"{e.code}: {e.message}" if isinstance(e, state.StopRun) else e.message
        if not args.json:
            print(f"devloops: {message}", file=sys.stderr)
            return e.exit_code
        result = initcmd._result(project_mod.Project(root), kit, exit_code=e.exit_code,
                                 message=message, conflicts=getattr(e, "conflicts", []))
    return _print_init(args, result)


def _upgrade(args, kit, root):
    """`init --upgrade [--restore] [--allow-skills]`."""
    proj = project_mod.Project(root)
    if args.allow_skills:  # refuse unreadable settings before anything is written
        initcmd._read_settings(os.path.join(root, initcmd.SETTINGS_PATH),
                               initcmd.permission_rule(kit.command_for(root)))
    result = initcmd.upgrade_result(proj, kit, initcmd.upgrade(root, kit, args.restore))
    if args.allow_skills:
        allowed = initcmd.allow_skills(root, kit.command_for(root))
        if allowed["changed"]:
            result["created" if allowed["created"] else "changed"].append(allowed["path"])
        result["skills_allowed"] = True
        result["message"] += "; " + initcmd._allowed_note(allowed)
    return result


def _print_init(args, result):
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        initcmd.print_result(result, sys.stdout)
    return result["exit_code"]


def _check(args, kit, project, env):
    """`devloops check` (contracts/cli.md): works outside a project; exit 0 or 30."""
    if project is None:
        try:
            project = project_mod.find(os.getcwd(), env)
        except state.UsageError:
            if env.get("DEVLOOPS_PROJECT"):
                raise  # an explicit project that is not one is an error, as for every command
            project = None  # outside a project: the packaged defaults (FR-019)
    if project is not None:
        project.merged  # an invalid configuration is reported like everywhere else (exit 30)
    result = checkcmd.run_checks(project, kit, env)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        checkcmd.print_result(result, sys.stdout)
    return 0 if result["ready"] else state.EXIT_CODES["stopped-on-input-error"]


def main(argv=None, kit=None, project=None, env=None):
    """Run one command. `kit`, `project`, and `env` are for tests; by default the kit this
    devloops runs from, the project found from the current directory (FR-008), and os.environ."""
    args = build_parser().parse_args(argv)
    env = os.environ if env is None else env
    kit = kit or Kit.resolve()
    if args.command in ("init", "check"):
        try:
            return _init(args, kit) if args.command == "init" else \
                _check(args, kit, project, env)
        except DevloopsError as e:
            print(f"devloops: {e.message}", file=sys.stderr)
            return e.exit_code
    try:
        project = project or project_mod.find(os.getcwd(), env)
        project.merged  # validate both configuration files before anything is written (FR-016)
        args.warnings = _version_warnings(project, kit)
        if args.command == "status":  # a misspelled override is visible (002 FR-030)
            args.warnings += prompts.ignored_warnings(project.root)
        for warning in args.warnings if not args.json else ():
            print(f"devloops: warning: {warning}", file=sys.stderr)
        args.env = env  # where a dashboard server records itself (serve.record_path)
        args.workspace_given = args.workspace is not None
        args.workspace = args.workspace or project.default_workspace
        # What the hints add so a printed command reaches this workspace too.
        args.workspace_flag = ("" if args.workspace == project.default_workspace
                               else f" --workspace {shlex.quote(args.workspace)}")

        if args.command == "status":
            ws = workspace.open_workspace(args.workspace, project, kit, create=False)
            # Without a loop: the loops the run includes (003 FR-016b), and the run's status.
            loops = [args.loop] if args.loop else list(orchestrator.select_loops(project, ws))
            run = None if args.loop else orchestrator.read_state(ws)
            large = large_evidence(ws, loops)
            if args.json:
                objs = {loop: engine.status_object(ws, loop) for loop in loops}
                obj = objs[args.loop] if args.loop else {
                    "workspace": ws.name, "loops": objs,
                    "full_dashboards": engine.full_dashboards(ws)}
                if run:
                    obj["run"] = run
                obj["large_evidence"] = large
                _dump(args, obj)
            else:
                if run:
                    print(f"run: {run.get('status')}")
                for loop in loops:
                    _print_status(engine.status_object(ws, loop))
                full = engine.full_dashboards(ws)
                if full["count"]:
                    print(f"full dashboards: {full['count']} "
                          f"({fulldash.human_bytes(full['bytes'])}), latest {full['latest']}")
                if large:
                    print("evidence files over 1 MB (review them for secrets before committing "
                          "the workspace):")
                    for item in large:
                        print(f"  {item['path']} ({item['bytes']} bytes)")
            return 0

        if args.command == "dashboard":
            return _dashboard(args, kit, project, env)
        if args.command == "export-sessions":
            return _export_sessions(args, workspace.open_workspace(args.workspace, project, kit,
                                                                   create=False))
        if args.command == "run":
            return _run(args, kit, project, env)
        return _decide(args, kit, project, env)
    except DevloopsError as e:
        if args.json:
            _dump(args, {"error": e.message, "exit_code": e.exit_code})
        else:
            print(f"devloops: {e.message}", file=sys.stderr)
        return e.exit_code
    except KeyboardInterrupt:
        print("devloops: interrupted", file=sys.stderr)
        return 130


def entry():
    """The installed `devloops` console script (pyproject.toml); `bin/devloops` from a checkout."""
    if sys.version_info < (3, 10):
        sys.stderr.write("devloops: Python 3.10 or newer is required (found %d.%d)\n"
                         % sys.version_info[:2])
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    entry()
