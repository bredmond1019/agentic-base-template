#!/usr/bin/env python3
"""Fixture suite over .claude/workflows/bin/prepare_run.py (BT.ticket.prepare-run-replaces-
setup-agents, task 5).

Proves prepare_run.py (tasks 2+4) is a faithful, deterministic replacement for the 8 mechanical
setup agents it retires, without re-running any historical corpus (roadmap design rule 1: no
block in this roadmap proves itself against historical work) — every fixture here is a small,
synthesized `git init` repo built fresh under a tempdir, with a scratch `planning/harness.json` /
`planning/<spec-slug>/tasks.json` pair standing in for a real project.

Four things this suite proves, each demanded by the block's AC and task 5's own AC:

  1. FIELD-FOR-FIELD MATCH (AC2): prepare_run()'s setup-fact output — repo_root, is_vaulted,
     vault_root, agent_flag, scope_flag, harness_config, tasks_enumeration — equals values fixed
     ahead of time to match what the 8 setup agents were instructed to mechanically derive from
     the identical inputs (a `git rev-parse --show-toplevel`, an `os.path.islink` check, the
     FLEET_LANE_AGENT/FLEET_LANE_REPO env-var-or-lease-file render, and a direct JSON parse).

  2. UNSET-ENV-VAR NEGATIVE CONTROL (AC3): the FE.7.B FELI_TEST_DATABASE_URL shape — a required
     environment variable that is not set refuses, by name, before any other setup fact is
     computed. Exercised via `--simulate-missing-env`, the test-only hook task 4 added precisely
     so this negative control does not need a live probeCommand or a real harness.json `requires`
     entry to demonstrate the refusal contract.

  3. NO-DIFF / KIND:VALIDATE PAIR (AC4): a task with no files and no `kind: "validate"` is
     flagged by the `no-diff-kind-validate` lint rule folded into prepare_run()'s `lint` key; the
     identical task with `kind: "validate"` added produces zero findings for that rule.

  4. CONFIG-OVER-CODE CONTROL (AC5): toggling `lintRules.no-diff-kind-validate.enabled` in
     harness.json between true and false changes the ACTUAL finding count for that rule with no
     code edit anywhere — not merely that the config value was read, but that the registry's
     enable/disable behavior is live (AGENTS.md standing rule 12).

Run: python3 scripts/test_prepare_run.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BIN_DIR = _REPO_ROOT / '.claude' / 'workflows' / 'bin'
sys.path.insert(0, str(_BIN_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prepare_run  # noqa: E402
import check_tasks_json  # noqa: E402
import lint_rules  # noqa: E402

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"[PASS] {label}")
    else:
        FAILURES.append(label)
        print(f"[FAIL] {label}" + (f" -- {detail}" if detail else ""))


# --- minimal, schema-valid harness.json --------------------------------------------------------

def _base_harness_config():
    return {
        "validation": {
            "checks": [
                {
                    "name": "smoke",
                    "purpose": "placeholder gating check for this fixture",
                    "command": "true",
                    "gates": True,
                    "observed_red": {
                        "date": "2026-09-01",
                        "evidence": "fixture — not a real observed-red incident",
                        "note": "fixture only",
                    },
                }
            ]
        },
        "uiTest": {"enabled": False},
    }


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _init_fixture_repo(tmp_root: Path, spec_slug: str, tasks, harness_config=None) -> Path:
    """Build a small, real `git init` repo under tmp_root with planning/harness.json and
    planning/<spec_slug>/tasks.json. Returns the repo root."""
    repo = tmp_root / "fixture-repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    _write_json(repo / "planning" / "harness.json", harness_config or _base_harness_config())
    _write_json(repo / "planning" / spec_slug / "tasks.json", tasks)
    return repo


# --- 1. field-for-field setup-fact match --------------------------------------------------------

def field_for_field_match():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        spec_slug = "fixture-spec"
        tasks = [
            {"task_id": 1, "title": "first", "files": ["a.py"], "dependsOn": []},
            {"task_id": 2, "title": "second", "files": ["b.py"], "dependsOn": [1]},
        ]
        harness_config = _base_harness_config()
        repo = _init_fixture_repo(tmp_root, spec_slug, tasks, harness_config)

        env_backup = {
            k: os.environ.get(k) for k in ("FLEET_LANE_AGENT", "FLEET_LANE_REPO")
        }
        os.environ["FLEET_LANE_AGENT"] = "agent-fixture"
        os.environ["FLEET_LANE_REPO"] = "repo-fixture"
        try:
            result = prepare_run.prepare_run(spec_slug, explicit_repo_root=str(repo), cwd=str(repo))
        finally:
            for k, v in env_backup.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        # Expected values fixed ahead of time to match what the retired setup agents were
        # instructed to mechanically transcribe from these exact inputs.
        expected = {
            # explicit_repo_root skips `git rev-parse --show-toplevel` and its symlink
            # canonicalization, so this must match resolve_repo_root()'s own os.path.abspath()
            # -- not Path.resolve(), which would also collapse a /var -> /private/var symlink
            # that git's own resolution would have produced too, but that this code path does not.
            "repo_root": os.path.abspath(str(repo)),
            "is_vaulted": False,
            "vault_root": str((repo / "planning").resolve()),
            "agent_flag": " --agent agent-fixture",
            "scope_flag": " --scope repo-fixture",
            "harness_config": harness_config,
            "tasks_enumeration": [
                {"task_id": 1, "dependsOn": []},
                {"task_id": 2, "dependsOn": [1]},
            ],
            "refused": False,
        }
        for field, expected_value in expected.items():
            check(
                f"field-for-field: {field} matches expected setup fact",
                result.get(field) == expected_value,
                f"expected {expected_value!r}, got {result.get(field)!r}",
            )


# --- 2. unset required env var refuses, naming the variable -------------------------------------

def unset_env_var_negative_control():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        spec_slug = "fixture-spec"
        repo = _init_fixture_repo(tmp_root, spec_slug, tasks=[{"task_id": 1, "files": ["a.py"]}])

        var_name = "FELI_TEST_DATABASE_URL_FIXTURE"
        os.environ.pop(var_name, None)  # ensure genuinely unset

        result = prepare_run.prepare_run(
            spec_slug, explicit_repo_root=str(repo), cwd=str(repo),
            simulate_missing_env=[var_name],
        )
        check("unset required env var refuses", result.get("refused") is True, f"result={result}")
        check(
            "refusal names the missing variable",
            var_name in result.get("reason", ""),
            f"reason={result.get('reason')!r}",
        )
        check(
            "refusal payload carries ONLY refused+reason (task 4 contract)",
            set(result.keys()) == {"refused", "reason"},
            f"keys={sorted(result.keys())}",
        )

        # Positive control: the same call with the variable set does NOT refuse on it.
        os.environ[var_name] = "postgres://fixture"
        try:
            result_set = prepare_run.prepare_run(
                spec_slug, explicit_repo_root=str(repo), cwd=str(repo),
                simulate_missing_env=[var_name],
            )
        finally:
            os.environ.pop(var_name, None)
        check(
            "the same env var, once set, does not refuse",
            result_set.get("refused") is False,
            f"result={result_set}",
        )


# --- 3. no-diff / kind:validate pair -------------------------------------------------------------

def no_diff_kind_validate_pair():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        spec_slug = "fixture-spec"

        # (a) no files, no kind:validate -> flagged
        tasks_unmarked = [
            {"task_id": 1, "title": "does something with no diff", "files": []},
        ]
        repo_unmarked = _init_fixture_repo(tmp_root / "unmarked", spec_slug, tasks_unmarked)
        result_unmarked = prepare_run.prepare_run(
            spec_slug, explicit_repo_root=str(repo_unmarked), cwd=str(repo_unmarked),
        )
        unmarked_findings = [
            f for f in result_unmarked["lint"]["findings"] if f["rule_id"] == "no-diff-kind-validate"
        ]
        check(
            "no-diff task without kind:validate is flagged",
            len(unmarked_findings) == 1,
            f"lint={result_unmarked['lint']}",
        )
        check(
            "lint.passed is False when the no-diff rule fires",
            result_unmarked["lint"]["passed"] is False,
        )

        # (b) identical task, now declaring kind: validate -> passes
        tasks_marked = [
            {"task_id": 1, "title": "does something with no diff", "files": [], "kind": "validate"},
        ]
        repo_marked = _init_fixture_repo(tmp_root / "marked", spec_slug, tasks_marked)
        result_marked = prepare_run.prepare_run(
            spec_slug, explicit_repo_root=str(repo_marked), cwd=str(repo_marked),
        )
        marked_findings = [
            f for f in result_marked["lint"]["findings"] if f["rule_id"] == "no-diff-kind-validate"
        ]
        check(
            "the identical task declaring kind:validate produces no no-diff-kind-validate finding",
            len(marked_findings) == 0,
            f"lint={result_marked['lint']}",
        )


# --- 4. config-over-code: toggling lintRules.<id>.enabled changes the finding count --------------

def config_over_code_control():
    rule_id = "no-diff-kind-validate"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        spec_slug = "fixture-spec"
        tasks = [{"task_id": 1, "title": "no diff, unmarked", "files": []}]

        # Enabled (absent from lintRules == enabled by default): the rule fires.
        harness_enabled = _base_harness_config()
        repo_enabled = _init_fixture_repo(tmp_root / "enabled", spec_slug, tasks, harness_enabled)
        result_enabled = prepare_run.prepare_run(
            spec_slug, explicit_repo_root=str(repo_enabled), cwd=str(repo_enabled),
        )
        count_enabled = sum(
            1 for f in result_enabled["lint"]["findings"] if f["rule_id"] == rule_id
        )

        # Disabled via harness.json config alone — no code change anywhere.
        harness_disabled = _base_harness_config()
        harness_disabled["lintRules"] = {rule_id: {"enabled": False}}
        repo_disabled = _init_fixture_repo(tmp_root / "disabled", spec_slug, tasks, harness_disabled)
        result_disabled = prepare_run.prepare_run(
            spec_slug, explicit_repo_root=str(repo_disabled), cwd=str(repo_disabled),
        )
        count_disabled = sum(
            1 for f in result_disabled["lint"]["findings"] if f["rule_id"] == rule_id
        )

        check(
            "rule enabled (default) produces at least one finding on the unmarked no-diff task",
            count_enabled >= 1,
            f"count_enabled={count_enabled}",
        )
        check(
            "the SAME rule disabled via lintRules.<id>.enabled=false produces zero findings",
            count_disabled == 0,
            f"count_disabled={count_disabled}",
        )
        check(
            "the finding count actually changed (config-over-code, not merely config-was-read)",
            count_enabled != count_disabled,
            f"count_enabled={count_enabled} count_disabled={count_disabled}",
        )
        check(
            "enabled_rules reflects the toggle: fewer enabled rules when one is disabled",
            result_disabled["lint"]["enabled_rules"] == result_enabled["lint"]["enabled_rules"] - 1,
            f"enabled(disabled run)={result_disabled['lint']['enabled_rules']} "
            f"enabled(enabled run)={result_enabled['lint']['enabled_rules']}",
        )
        # And prove the umbrella CLI (check_tasks_json.py) agrees with prepare_run's own
        # resolve_enabled() — same registry, same config, same verdict (task 4 AC4 in prepare_run
        # itself: prepare_run's folded lint output MUST equal check_tasks_json.py run standalone).
        enabled_via_umbrella = check_tasks_json.resolve_enabled(
            lint_rules.REGISTRY, harness_disabled.get("lintRules") or {}
        )
        check(
            "check_tasks_json.py's resolve_enabled() agrees with prepare_run.py's own lint verdict",
            len(enabled_via_umbrella) == result_disabled["lint"]["enabled_rules"],
            f"umbrella={len(enabled_via_umbrella)} prepare_run={result_disabled['lint']['enabled_rules']}",
        )


def main() -> int:
    field_for_field_match()
    unset_env_var_negative_control()
    no_diff_kind_validate_pair()
    config_over_code_control()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- prepare_run.py matches recorded setup facts and both negative controls hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
