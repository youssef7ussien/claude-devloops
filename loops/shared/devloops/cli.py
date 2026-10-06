"""`devloops` command line (contracts/cli.md)."""
import argparse
import csv
import json
import os
import sys

from . import (__version__, checkcmd, dashboard, engine, fulldash, initcmd, orchestrator, state,
               workspace)
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


def _add_story_options(cmd):
    story = cmd.add_mutually_exclusive_group()
    story.add_argument("--story-id", help="implement only this story of --requirements (a PRD)")
    story.add_argument("--story-file", action="store_true",
                       help="--requirements is a standalone story file")


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

    run = sub.add_parser("run", parents=[common], help="start or resume one loop")
    run.add_argument("loop", choices=LOOPS)
    run.add_argument("--requirements", help="PRD or story Markdown file (required on the first run)")
    _add_story_options(run)
    run.add_argument("--target", help="directory for this loop's application code (first run)")
    run.add_argument("--api-spec", help="OpenAPI JSON document (required for frontend-dev)")
    run.add_argument("--max-trials", type=_positive_int, help="override max_trials")
    run.add_argument("--force-unlock", action="store_true", help="clear a stale lock")

    orch = sub.add_parser("orchestrate", parents=[common],
                          help="run backend-dev, then frontend-dev, in one workspace")
    orch.add_argument("--requirements", help="PRD or story Markdown file, passed to both loops")
    _add_story_options(orch)
    orch.add_argument("--target-root",
                      help="default targets: <dir>/backend and <dir>/frontend (first run)")
    orch.add_argument("--backend-target", help="backend-dev's target (overrides --target-root)")
    orch.add_argument("--frontend-target", help="frontend-dev's target (overrides --target-root)")
    orch.add_argument("--force-unlock", action="store_true", help="clear a stale lock")

    for name, text in (("approve", "accept the stored plan and the answers"),
                       ("replan", "plan again with the answers, then pause again")):
        cmd = sub.add_parser(name, parents=[common], help=text)
        cmd.add_argument("loop", choices=LOOPS)
        cmd.add_argument("--force-unlock", action="store_true", help="clear a stale lock")

    retry = sub.add_parser("retry", parents=[common],
                           help="grant a failed milestone more trials (FR-063)")
    retry.add_argument("loop", choices=LOOPS)
    retry.add_argument("--milestone", required=True, help="the failed milestone, e.g. M01")
    retry.add_argument("--reason", required=True,
                       help="why; recorded with the grant and passed to later fix prompts")
    retry.add_argument("--trials", type=_positive_int,
                       help="trials to grant (default: max_trials)")
    retry.add_argument("--force-unlock", action="store_true", help="clear a stale lock")

    export = sub.add_parser("export-sessions", parents=[common],
                            help="write every Claude invocation as CSV (FR-033)")
    export.add_argument("--csv", metavar="FILE", help="output file (default: standard output)")

    dash = sub.add_parser("dashboard", parents=[common],
                          help="write a new full dashboard, then refresh <workspace>/dashboard.html")
    dash.add_argument("--light", action="store_true",
                      help="only refresh <workspace>/dashboard.html (no full dashboard)")

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
    init.add_argument("--track-workspaces", action="store_true",
                      help="do not git-ignore the workspaces folder")
    init.add_argument("--track-dashboards", action="store_true",
                      help="do not git-ignore the full dashboards folder")
    init.add_argument("--allow-skills", action="store_true",
                      help="add the devloops permission rule to .claude/settings.json (also on "
                           "an initialized project)")
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


SESSION_COLUMNS = ("workspace", "loop", "step", "milestone", "trial", "session_id",
                   "prompt_path", "input_tokens", "output_tokens", "cache_creation_tokens",
                   "cache_read_tokens", "cost_usd", "started_at", "ended_at")


def session_rows(ws):
    """One row per invocation in every loop's `state/invocations.jsonl`, in loop then call order.

    `prompt_path` is relative to the workspace. A token count or cost Claude did not report is
    left empty.
    """
    for loop in LOOPS:
        loop_dir = ws.loop_dir(loop)
        records = state.read_jsonl(os.path.join(loop_dir, "state", "invocations.jsonl"))
        for rec in sorted(records, key=lambda r: r.get("seq") or 0):
            tokens = rec.get("tokens") or {}
            prompt = rec.get("prompt_path")
            yield {
                "workspace": ws.name, "loop": rec.get("loop") or loop, "step": rec.get("step"),
                "milestone": rec.get("milestone_id"), "trial": rec.get("trial"),
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
    if installed and installed != kit.version:
        return [f"this project was set up with devloops {installed}; running {kit.version}. "
                f'Run "devloops init --upgrade".']
    return []


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
    if obj.get("ui_url"):
        print(f"  UI URL: {obj['ui_url']}")
    if obj.get("openapi_artifact"):
        print(f"  OpenAPI artifact: {obj['openapi_artifact'].get('path')}")
    if obj.get("config_drift"):
        print(f"  configuration changed since the first run (not applied): "
              f"{', '.join(obj['config_drift'])}")
    if obj["status"] != "not-started":
        print(f"  progress: {obj['progress']}")


def _dashboard_path(ws):
    path = os.path.join(ws.path, dashboard.FILENAME)
    return path if os.path.exists(path) else None


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
        if obj["dashboard"]:
            print(f"dashboard: {obj['dashboard']}")
        _print_full(full)


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


def _ends_final(error, status):
    """Whether a command ended in a final status (FR-039).

    Not when it was refused (a lock or a usage error) or interrupted: an interrupt must not wait
    for a page that embeds every conversation.
    """
    if error is not None and (not isinstance(error, DevloopsError) or
                              isinstance(error, (state.LockHeld, state.UsageError))):
        return False
    return fulldash.is_final(status)


def _write_full_dashboard(ws, trigger, env):
    """Write a new full dashboard; a failure only warns, like the lightweight one (FR-039)."""
    try:
        return fulldash.write(ws, trigger=trigger, env=env)
    except Exception as e:  # noqa: BLE001 - a view; the command's result stands
        print(f"devloops: warning: could not write the full dashboard: {e}", file=sys.stderr)
        return None


def _project_defaults(project, ws, loop, requirements, story_id, story_file):
    """Fill `loop`'s target and requirements the command line left out (FR-011).

    What the workspace recorded comes first (a first start that stopped early still recorded
    it), then the project configuration. So a later edit of the configuration is drift, not a
    mismatch (FR-015). Returns `(target, requirements, story_id, story_file)`; the spec-kit form
    of the configured requirements is not a file (T050).
    """
    target = ws.target(loop) or project.targets.get(loop)
    if requirements:
        return target, requirements, story_id, story_file
    recorded = ws.data.get("requirements") or {}
    configured = project.requirements or {}
    no_story_flags = story_id is None and not story_file
    if recorded:
        requirements = ws.requirements_path()
        if no_story_flags:
            story_id, story_file = recorded.get("story_id"), recorded.get("mode") == "story-file"
    elif configured.get("path"):
        requirements = configured["path"]
        if no_story_flags:
            story_file = bool(configured.get("story_file"))
    return target, requirements, story_id, story_file


def _orchestrate(args, kit, project, env):
    for loop in orchestrator.LOOP_ORDER:
        engine.load_loop_def(kit, loop)  # before a workspace is created
    root = os.path.abspath(args.target_root) if args.target_root else None
    targets = {"backend": args.backend_target, "frontend": args.frontend_target}
    for name, given in targets.items():
        targets[name] = os.path.abspath(given) if given else \
            (os.path.join(root, name) if root else None)
    ws = workspace.open_workspace(args.workspace, project, kit, create=True)
    requirements, story_id, story_file = args.requirements, args.story_id, args.story_file
    for name, loop in (("backend", "backend-dev"), ("frontend", "frontend-dev")):
        target, requirements, story_id, story_file = _project_defaults(
            project, ws, loop, requirements, story_id, story_file)
        targets[name] = targets[name] or target
    orch = orchestrator.Orchestrator(ws, orchestrator.OrchestrateOptions(
        requirements=requirements, story_id=story_id, story_file=story_file,
        backend_target=targets["backend"], frontend_target=targets["frontend"],
        config_path=args.config, force_unlock=args.force_unlock), kit=kit, env=env)
    error = full = None
    try:
        code = orch.run()
    except BaseException as e:
        error = e
        raise
    finally:
        # Once, at the end, covering both loops, when the loop this command ran last ended in a
        # final status: a loop skipped because an earlier run completed it does not count (FR-039).
        last = orch.last_run
        if last and _ends_final(error, engine.status_object(ws, last)["status"]):
            full = _write_full_dashboard(ws, "orchestrate", env)
        _write_dashboard(ws, announce=False)
    loops = {loop: engine.status_object(ws, loop) for loop in orchestrator.LOOP_ORDER}
    if args.json:
        obj = {"workspace": ws.name, "orchestrator": orch.state, "loops": loops,
               "exit_code": code, "message": orch.message, "dashboard": _dashboard_path(ws)}
        if full:
            obj["full_dashboard"] = {"path": full["path"], "bytes": full["bytes"]}
        _dump(args, obj)
    else:
        if orch.message:
            print(orch.message)
        print(f"orchestrator: {orch.state['status']}")
        for obj in loops.values():
            _print_status(obj)
        if _dashboard_path(ws):
            print(f"dashboard: {_dashboard_path(ws)}")
        _print_full(full)
    return code


def _write_dashboard(ws, announce):
    """Refresh the workspace dashboard. A failure only warns: it never changes a run's outcome."""
    try:
        path = dashboard.write(ws)
    except Exception as e:  # noqa: BLE001 - the dashboard is a view; the run's result stands
        print(f"devloops: warning: could not write the dashboard: {e}", file=sys.stderr)
        return None
    if announce:
        print(f"dashboard: {path}")
    return path


def _init(args, kit):
    """`devloops init` (contracts/cli.md): needs no project; exit 0, 30, or 2."""
    opts = initcmd.InitOptions(
        backend_target=args.backend_target, frontend_target=args.frontend_target,
        requirements=args.requirements, speckit_feature=args.speckit_feature,
        no_prompt=args.no_prompt or args.json, track_workspaces=args.track_workspaces,
        track_dashboards=args.track_dashboards, allow_skills=args.allow_skills)
    root = os.path.abspath(args.dir)
    try:
        answers = None
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
        for warning in args.warnings if not args.json else ():
            print(f"devloops: warning: {warning}", file=sys.stderr)
        args.workspace = args.workspace or project.default_workspace

        if args.command == "status":
            ws = workspace.open_workspace(args.workspace, project, kit, create=False)
            loops = [args.loop] if args.loop else list(LOOPS)
            large = large_evidence(ws, loops)
            if args.json:
                objs = {loop: engine.status_object(ws, loop) for loop in loops}
                obj = objs[args.loop] if args.loop else {
                    "workspace": ws.name, "loops": objs,
                    "full_dashboards": engine.full_dashboards(ws)}
                obj["large_evidence"] = large
                _dump(args, obj)
            else:
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
            ws = workspace.open_workspace(args.workspace, project, kit, create=False)
            full = None if args.light else _write_full_dashboard(ws, "dashboard command", env)
            path = _write_dashboard(ws, announce=not args.json)
            if args.json:
                obj = {"workspace": ws.name, "dashboard": path}
                if not args.light:
                    obj["full_dashboard"] = full and {k: full[k] for k in
                                                      ("path", "bytes", "largest", "unavailable")}
                _dump(args, obj)
            else:
                _print_full(full, largest=True)
            return 0 if path and (args.light or full) else 1
        if args.command == "export-sessions":
            return _export_sessions(args, workspace.open_workspace(args.workspace, project, kit,
                                                                   create=False))
        if args.command == "orchestrate":
            return _orchestrate(args, kit, project, env)

        engine.load_loop_def(kit, args.loop)  # before a workspace is created
        ws = workspace.open_workspace(args.workspace, project, kit,
                                      create=args.command == "run")
        requirements = getattr(args, "requirements", None)
        story_id = getattr(args, "story_id", None)
        story_file = getattr(args, "story_file", False)
        target = getattr(args, "target", None)
        if args.command == "run":
            default_target, requirements, story_id, story_file = _project_defaults(
                project, ws, args.loop, requirements, story_id, story_file)
            target = target or default_target
        options = engine.Options(
            requirements=requirements,
            story_id=story_id,
            story_file=story_file,
            target=target,
            api_spec=getattr(args, "api_spec", None),
            config_path=args.config,
            cli_overrides={"max_trials": getattr(args, "max_trials", None)},
            force_unlock=args.force_unlock,
        )
        eng = engine.Engine(args.loop, ws, options, kit=kit, project=project, env=env)
        error = full = None
        try:
            if args.command == "retry":
                code = eng.retry(args.milestone, args.reason, args.trials)
            else:
                code = {"run": eng.run, "approve": eng.approve,
                        "replan": eng.replan}[args.command]()
        except BaseException as e:
            error = e
            raise
        finally:
            if _ends_final(error, engine.status_object(ws, args.loop)["status"]):
                full = _write_full_dashboard(ws, f"{args.command} {args.loop}", env)
            _write_dashboard(ws, announce=False)
        _emit(args, ws, args.loop, eng.message, code, full)
        return code
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
