"""The kit: the packaged devloops files (loop definitions, prompts, schemas, hooks, defaults,
skill and project templates). Read-only to runs (002 FR-009).

From a checkout the kit is `<checkout>/loops`; when installed it is the `devloops_kit` package
(002 research P-1, P-2). Code builds kit paths with `Kit.path(...)`, never from a repository root.
"""
import functools
import os

from . import __version__

_PACKAGE_DIR = os.path.dirname(os.path.realpath(__file__))


class Kit:
    def __init__(self, root, mode, reserved):
        self.root = os.path.realpath(root)
        self.mode = mode
        self.reserved = [os.path.realpath(p) for p in reserved]

    def __repr__(self):
        return f"Kit(root={self.root!r}, mode={self.mode!r})"

    @property
    def version(self):
        return __version__

    @property
    def checkout(self):
        """The checkout containing the kit (source mode), else None."""
        return os.path.dirname(self.root) if self.mode == "source" else None

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def command_for(self, project_root):
        """How skills in `project_root` invoke devloops (research P-7).

        Installed: `devloops`. From a checkout: its `bin/devloops`, relative to the project root
        when the checkout is the project or inside it, absolute otherwise.
        """
        if self.mode != "source":
            return "devloops"
        script = os.path.join(os.path.dirname(self.root), "bin", "devloops")
        project_root = os.path.realpath(project_root)
        if script.startswith(project_root.rstrip(os.sep) + os.sep):
            return os.path.relpath(script, project_root)
        return script

    @classmethod
    def from_checkout(cls, checkout):
        """Source mode for the checkout at `checkout` (its `loops/` and `bin/` are reserved)."""
        checkout = os.path.realpath(checkout)
        return cls(os.path.join(checkout, "loops"), "source",
                   [os.path.join(checkout, "loops"), os.path.join(checkout, "bin")])

    @classmethod
    def resolve(cls):
        """The kit this devloops runs from (cached; research P-2)."""
        return _resolve()


@functools.lru_cache(maxsize=None)
def _resolve():
    # loops/shared/devloops -> loops/: a checkout has loops/backend-dev/loop.json beside shared/.
    loops_dir = os.path.dirname(os.path.dirname(_PACKAGE_DIR))
    if os.path.isfile(os.path.join(loops_dir, "backend-dev", "loop.json")):
        return Kit.from_checkout(os.path.dirname(loops_dir))
    import devloops_kit  # type: ignore[import-not-found]  # installed: a namespace package of data files only
    root = list(devloops_kit.__path__)[0]
    return Kit(root, "installed", [root, _PACKAGE_DIR])
