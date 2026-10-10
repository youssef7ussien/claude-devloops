"""Valid sample documents for every schema in `loops/shared/schemas/`, reused across tests.

Each function returns a fresh copy, so a test can mutate it freely.
"""
import base64
import copy

# The smallest valid PNG: one transparent pixel.
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA"
                       "60e6kgAAAABJRU5ErkJggg==")

_PLAN = {
    "requirements_inventory": [
        {"ref": "FR-1", "summary": "List items"},
        {"ref": "FR-2", "summary": "Create an item"},
    ],
    "stack": {"summary": "Python stdlib HTTP server", "source": "proposed", "conflicts": []},
    "runtime": {
        "start_command": "python3 app.py 8765",
        "cwd": ".",
        "base_url": "http://127.0.0.1:8765",
        "ready_url": "http://127.0.0.1:8765/health",
        "openapi_path": "openapi.json",
    },
    "milestones": [
        {
            "id": "M01",
            "title": "List items",
            "goal": "Clients can list items",
            "depends_on": [],
            "tasks": [{"id": "M01-T01", "title": "GET /items", "description": "Return all items",
                       "requirement_refs": ["FR-1"]}],
            "acceptance_criteria": [{"id": "M01-AC1", "text": "GET /items returns 200 and a list",
                                     "requirement_refs": ["FR-1"]}],
        },
        {
            "id": "M02",
            "title": "Create items",
            "goal": "Clients can create items",
            "depends_on": ["M01"],
            "tasks": [{"id": "M02-T01", "title": "POST /items", "description": "Create an item",
                       "requirement_refs": ["FR-2"]}],
            "acceptance_criteria": [{"id": "M02-AC1", "text": "POST /items returns 201",
                                     "requirement_refs": ["FR-2"]}],
        },
    ],
    "open_questions": [],
    "assumptions": [{"id": "A1", "text": "Items are kept in memory", "source": "proposed"}],
}

_CHECKS = {
    "milestone_id": "M01",
    "checks": [{
        "id": "C1",
        "criteria": ["M01-AC1"],
        "request": {"method": "GET", "path": "/items", "headers": {"Accept": "application/json"}},
        "expect": {"status": 200, "body_contains": ["["], "json_equals": {}},
        "capture": {},
    }],
}

_VALIDATION = {
    "kind": "curl",
    "passed": True,
    "criteria": [{"criterion_id": "M01-AC1", "passed": True, "observed": "200 []",
                  "evidence": ["evidence/C1.body"]}],
    "checks": [{"check_id": "C1", "passed": True, "command": "curl -sS http://127.0.0.1:8765/items",
                "response": {"status": 200, "body_path": "evidence/C1.body"}, "failures": []}],
    "contract": {"passed": True, "unmatched_operations": []},
    "unit_tests": {"enabled": False},
    "boundary": {"passed": True, "violations": []},
}

_INVOCATION = {
    "seq": 1,
    "session_id": "11111111-1111-4111-8111-111111111111",
    "loop": "backend-dev",
    "step": "plan",
    "milestone_id": None,
    "trial": 1,
    "prompt_path": "state/prompts/0001-plan.md",
    "started_at": "2026-09-27T10:00:00.000Z",
    "ended_at": "2026-09-27T10:01:00.000Z",
    "duration_ms": 60000,
    "num_turns": 3,
    "tokens": {"input": 100, "output": 50, "cache_creation": 0, "cache_read": None},
    "cost_usd": 0.01,
    "is_error": False,
    "subtype": "success",
    "permission_denials": [],
    "timed_out": False,
    "api_error_status": None,
    "failure_class": "none",
    "redacted": False,
}

_RUN_STATE = {
    "loop": "backend-dev",
    "status": "awaiting-approval",
    "status_reason": None,
    "inputs": {"requirements": {"path": "/tmp/prd.md", "sha256": "ab" * 32, "mode": "prd",
                                "story_id": None}},
    "target_dir": "/tmp/target",
    "effective_config": {"max_trials": 3, "secrets": {"env": [], "literals": []}},
    "approval": None,
    "milestones": {},
    "invocation_count": 1,
    "resume_status": None,
    "grants": [],
}

_CONFIG = {
    "max_trials": 3,
    "max_invocations_per_run": 60,
    "invocation_timeout_seconds": 1800,
    "max_budget_usd_per_invocation": None,
    "model": None,
    "models": {},
    "implement_tools": ["Read", "Edit", "Write", "Glob", "Grep", "Bash"],
    "unit_tests": {"enabled": False, "command": None},
    "runtime": {"ready_timeout_seconds": 120},
    "backend": {},
    "playwright": {"mcp_command": ["npx", "@playwright/mcp@latest", "--headless"]},
    "git": {"commit_per_milestone": False},
    "secrets": {"env": [], "literals": []},
    "boundary": {"allowed_extra": []},
}


def plan():
    return copy.deepcopy(_PLAN)


def checks():
    return copy.deepcopy(_CHECKS)


def validation_result():
    return copy.deepcopy(_VALIDATION)


def invocation_record():
    return copy.deepcopy(_INVOCATION)


def run_state():
    return copy.deepcopy(_RUN_STATE)


def config():
    return copy.deepcopy(_CONFIG)


def project_config():
    """A `.devloops/devloops.json` with every key (002 contracts/project-config.schema.json)."""
    return {
        "schema_version": 1, "workspace": "main", "workspaces_dir": ".devloops/workspaces",
        "targets": {"backend-dev": "backend", "frontend-dev": None},
        "requirements": {"speckit_feature": "active"},
        "config": {"max_invocations_per_run": 40, "git": {"commit_per_milestone": True}},
    }


def manifest():
    """A `.devloops/manifest.json` (002 contracts/manifest.schema.json)."""
    return {
        "schema_version": 1, "devloops_version": "0.2.0", "kit_mode": "installed",
        "command": "devloops", "installed_at": "2026-10-06T10:00:00.000Z", "upgraded_at": None,
        "ignore_rules": [".devloops/workspaces/", ".devloops/dashboards/",
                         ".devloops/devloops.local.json"],
        "files": {".claude/skills/devloops-run/SKILL.md": "a" * 64},
    }
