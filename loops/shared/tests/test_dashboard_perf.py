"""How fast the server answers the overview's data for a large workspace (specs/005-dashboard-redesign
SC-001, server side). Skipped when DEVLOOPS_SKIP_PERF=1 (a slow or busy machine)."""
import json
import os
import time
import unittest

import helpers  # noqa: F401 - puts the package on sys.path
from devloops import serve, workspace
from stub_loop import WS, StubLoopMixin

CALLS = 200
FILES = 5000


@unittest.skipIf(os.environ.get("DEVLOOPS_SKIP_PERF") == "1", "DEVLOOPS_SKIP_PERF=1")
class SummaryPerfTest(StubLoopMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.approved()
        self.assertEqual(self.cli("run"), 0, self.last_output)
        self.grow()

    def grow(self):
        """200 more calls, each with its copied conversation, and 5,000 small files."""
        state_dir = os.path.join(self.loop_dir, "state")
        path = os.path.join(state_dir, "invocations.jsonl")
        with open(path, encoding="utf-8") as f:
            seq = len(f.readlines())
        os.makedirs(os.path.join(state_dir, "conversations"), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for k in range(CALLS):
                seq += 1
                rel = os.path.join("state", "conversations", f"{seq:04d}-implement.jsonl")
                with open(os.path.join(self.loop_dir, rel), "w", encoding="utf-8") as c:
                    c.write("".join(json.dumps({"type": "assistant", "message": {
                        "role": "assistant", "content": [{"type": "text", "text": f"line {n}"}]}})
                        + "\n" for n in range(20)))
                f.write(json.dumps({
                    "seq": seq, "step": "implement", "milestone_id": "M02", "trial": 1,
                    "session_id": f"s-{seq}", "model": "sonnet",
                    "started_at": "2026-01-01T00:00:00Z", "ended_at": "2026-01-01T00:00:05Z",
                    "duration_ms": 5000, "cost_usd": 0.01, "failure_class": "none",
                    "tokens": {"input": 10, "output": 5, "cache_creation": 1, "cache_read": 20},
                    "conversation": "copied", "conversation_path": rel}) + "\n")
        notes = os.path.join(self.t.workspace_dir, "notes")
        for k in range(FILES):
            folder = os.path.join(notes, f"d{k // 100:02d}")
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, f"n{k:04d}.md"), "w", encoding="utf-8") as f:
                f.write(f"# Note {k}\n\nSome text.\n")

    def test_summary_cold_and_warm(self):
        ws = workspace.open_workspace(WS, self.t.project(), self.t.kit(), create=False)
        site = serve.Site(self.t.project(), self.t.kit(), self.t.env)
        start = time.perf_counter()
        status, body, _ = site.answer(ws, "summary")
        cold = time.perf_counter() - start
        self.assertEqual(status, 200, body)
        self.assertGreaterEqual(json.loads(body)["counts"]["calls"], CALLS)
        start = time.perf_counter()
        site.answer(ws, "summary")
        warm = time.perf_counter() - start
        self.assertLess(cold, 1.0, f"cold summary took {cold:.2f}s")
        self.assertLess(warm, 0.1, f"warm summary took {warm:.3f}s")


if __name__ == "__main__":
    unittest.main()
