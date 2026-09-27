"""Nothing in the files that steer the loops names an application or a stack (T069; FR-037,
FR-059).

Scanned: `loops/*/{Loop-instructions.md,task.md,loop.json}`, `loops/shared/prompts/**`,
`loops/shared/config/defaults.json`, `loops/shared/devloops/**/*.py`, and `bin/devloops`.

Not scanned: `loops/README.md`, `loops/orchestrator/README.md`, and `loops/shared/tests/`, because
documentation and tests may show example commands and fixtures.

A term matches case-insensitively and as a whole word: no letter, digit, or `_` touches it. So a
stack default must appear in its stack-specific form (`npm install`, `from 'react'`, `express()`)
to match; plain English such as "express" or "react" does not.
"""
import glob
import os
import re
import unittest

import helpers

# Words that would tie the loops to one application.
APPLICATION_TERMS = ("quickflow", "habit", "todo plan", "learning resource")

# Stack defaults, in the forms that only appear when a stack is being assumed.
STACK_TERMS = (
    "npm install", "npm run", "react-dom", "create-react-app", "from 'react'",
    "require('express')", "from 'express'", "express()", "fastapi", "django", "flask", "vite",
    "next.js",
)

# Accepted phrases that contain a term but assume nothing (none are needed today). Each entry is
# removed from a file's text before the scan, so keep entries as specific as possible.
ALLOWED_PHRASES = ()

SCANNED_GLOBS = (
    "loops/*/Loop-instructions.md",
    "loops/*/task.md",
    "loops/*/loop.json",
    "loops/shared/prompts/**/*",
    "loops/shared/config/defaults.json",
    "loops/shared/devloops/**/*.py",
    "bin/devloops",
)
NOT_SCANNED = ("loops/README.md", "loops/orchestrator/README.md", "loops/shared/tests/")


def term_pattern(term):
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", re.IGNORECASE)


PATTERNS = [(term, term_pattern(term)) for term in APPLICATION_TERMS + STACK_TERMS]


def findings(text):
    """`[(term, line_number, line)]` for every term in `text`, after the allowed phrases."""
    for phrase in ALLOWED_PHRASES:
        text = re.sub(re.escape(phrase), lambda m: " " * len(m.group(0)), text,
                      flags=re.IGNORECASE)
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        for term, pattern in PATTERNS:
            if pattern.search(line):
                found.append((term, n, line.strip()))
    return found


def scanned_files(root):
    paths = set()
    for pattern in SCANNED_GLOBS:
        paths.update(p for p in glob.glob(os.path.join(root, pattern), recursive=True)
                     if os.path.isfile(p))
    return sorted(paths)


class NoAppSpecificsTest(unittest.TestCase):
    def test_the_steering_files_name_no_application_or_stack(self):
        files = scanned_files(helpers.REPO_ROOT)
        rel = [os.path.relpath(p, helpers.REPO_ROOT) for p in files]
        # The scan covers every kind of steering file, and none of the excluded ones.
        for expected in ("bin/devloops", "loops/shared/config/defaults.json",
                         "loops/shared/prompts/common.md", "loops/shared/devloops/engine.py",
                         "loops/backend-dev/Loop-instructions.md", "loops/frontend-dev/task.md",
                         "loops/frontend-dev/loop.json"):
            self.assertIn(expected, rel)
        self.assertFalse([r for r in rel if r.startswith(NOT_SCANNED)], rel)

        problems = []
        for path, relpath in zip(files, rel):
            with open(path, encoding="utf-8", errors="replace") as f:
                for term, n, line in findings(f.read()):
                    problems.append(f"{relpath}:{n}: {term!r} in: {line}")
        self.assertEqual(problems, [], "application or stack specifics in the loops:\n"
                         + "\n".join(problems))

    def test_terms_match_as_whole_words_in_their_specific_form(self):
        for text in ("run `npm install` first", "import React from 'react'",
                     "const app = express()", "Uses FastAPI.", "a Vite config",
                     "QuickFlow requirements", "(habit)", "built on Next.js"):
            with self.subTest(text=text):
                self.assertTrue(findings(text), text)
        for text in ("Express the result as JSON.", "React to a failed check.",
                     "habitual", "an invitation", "flasks", "npm installer",
                     "the npx @playwright/mcp launcher"):
            with self.subTest(text=text):
                self.assertEqual(findings(text), [], text)


if __name__ == "__main__":
    unittest.main()
