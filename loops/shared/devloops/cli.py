"""`devloops` command line (contracts/cli.md)."""
import argparse
import json
import os
import sys

from . import __version__, engine, orchestrator, state, workspace
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
    common.add_argument("--workspace", required=True,
                        help="workspace name (under workspaces/) or path; created on the first run")
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

    status = sub.add_parser("status", parents=[common], help="show run status (read-only)")
    status.add_argument("loop", nargs="?", choices=LOOPS)
    return parser


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))


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
    if obj["status"] != "not-started":
        print(f"  progress: {obj['progress']}")


def _emit(args, ws, loop, message, code):
    obj = engine.status_object(ws, loop)
    if args.json:
        obj["exit_code"] = code
        if message:
            obj["message"] = message
        print(json.dumps(obj, indent=2))
    else:
        _print_status(obj, message)


def _orchestrate(args, repo_root):
    for loop in orchestrator.LOOP_ORDER:
        engine.load_loop_def(repo_root, loop)  # before a workspace is created
    root = os.path.abspath(args.target_root) if args.target_root else None
    targets = {"backend": args.backend_target, "frontend": args.frontend_target}
    for name, given in targets.items():
        targets[name] = os.path.abspath(given) if given else \
            (os.path.join(root, name) if root else None)
    ws = workspace.open_workspace(args.workspace, repo_root, create=True)
    orch = orchestrator.Orchestrator(ws, orchestrator.OrchestrateOptions(
        requirements=args.requirements, story_id=args.story_id, story_file=args.story_file,
        backend_target=targets["backend"], frontend_target=targets["frontend"],
        config_path=args.config, force_unlock=args.force_unlock), repo_root=repo_root)
    code = orch.run()
    loops = {loop: engine.status_object(ws, loop) for loop in orchestrator.LOOP_ORDER}
    if args.json:
        print(json.dumps({"workspace": ws.name, "orchestrator": orch.state, "loops": loops,
                          "exit_code": code, "message": orch.message}, indent=2))
    else:
        if orch.message:
            print(orch.message)
        print(f"orchestrator: {orch.state['status']}")
        for obj in loops.values():
            _print_status(obj)
    return code


def main(argv=None, repo_root=None):
    args = build_parser().parse_args(argv)
    repo_root = repo_root or _repo_root()
    try:
        if args.command == "status":
            ws = workspace.open_workspace(args.workspace, repo_root, create=False)
            loops = [args.loop] if args.loop else list(LOOPS)
            if args.json:
                objs = {loop: engine.status_object(ws, loop) for loop in loops}
                print(json.dumps(objs[args.loop] if args.loop else
                                 {"workspace": ws.name, "loops": objs}, indent=2))
            else:
                for loop in loops:
                    _print_status(engine.status_object(ws, loop))
            return 0

        if args.command == "orchestrate":
            return _orchestrate(args, repo_root)

        engine.load_loop_def(repo_root, args.loop)  # before a workspace is created
        ws = workspace.open_workspace(args.workspace, repo_root, create=args.command == "run")
        options = engine.Options(
            requirements=getattr(args, "requirements", None),
            story_id=getattr(args, "story_id", None),
            story_file=getattr(args, "story_file", False),
            target=getattr(args, "target", None),
            api_spec=getattr(args, "api_spec", None),
            config_path=args.config,
            cli_overrides={"max_trials": getattr(args, "max_trials", None)},
            force_unlock=args.force_unlock,
        )
        eng = engine.Engine(args.loop, ws, options, repo_root=repo_root)
        if args.command == "retry":
            code = eng.retry(args.milestone, args.reason, args.trials)
        else:
            code = {"run": eng.run, "approve": eng.approve, "replan": eng.replan}[args.command]()
        _emit(args, ws, args.loop, eng.message, code)
        return code
    except DevloopsError as e:
        if args.json:
            print(json.dumps({"error": e.message, "exit_code": e.exit_code}, indent=2))
        else:
            print(f"devloops: {e.message}", file=sys.stderr)
        return e.exit_code
    except KeyboardInterrupt:
        print("devloops: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
