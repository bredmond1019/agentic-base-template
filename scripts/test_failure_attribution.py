#!/usr/bin/env python3
"""Fixture suite for the attribution decision (BT.ticket.failure-attribution-and-gate-cache,
task 6) — replays RECORDED bail-meta inputs through the `decideAttribution`/
`buildTaskGateHistory` functions extracted in task 3 and the gate-cache `lookup`/`warm`
verbs from task 2. No engine launch, no network, no real cache warm against this repo's own
state.

`decideAttribution` and `buildTaskGateHistory` are extracted VERBATIM from each built engine's
source (brace-matched around their declarations, same technique as
scripts/test_bail_check_id.py) and executed for real under `node -e`, rather than reimplemented
in Python — a reimplementation could silently drift from what the engines actually do and pass
while the real function is broken.

Fixtures drawn from the classified bail set (HQ
planning/open-work/orchestration-runs/retros/bail-classification-2026-09-13.json):
  - PRE-EXISTING-RED entries (synapse OR.ticket.publishable-eval-report task 1; base-template
    ticket.task-gate-boundaries-are-unenforced task 2) -> ownership=foreign, no attempt burned.
  - FE.7.D (feli FE.7.D task 3: task 2 changed get_api_key_identity's return value and left
    tests/api/test_v1_approvals.py's decided_by assertion stale, explicitly deferring the fix to
    task 7; task 3 inherits the already-red check) -> in-spec debt, failure_class=fixable, NOT a
    bail, declaredByTask=2, writable set includes the failing test file.
  - A green-at-N-1 / red-at-N fixture -> the ordinary fix loop, unchanged (the regression
    control — this MUST stay a genuine negative control, i.e. it must NOT also satisfy the
    in-spec-debt or foreign shape).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINES = {
    "sdlc-task": ROOT / ".claude/workflows/sdlc-task.js",
    "sdlc-flow": ROOT / ".claude/workflows/sdlc-flow.js",
}
GATE_CACHE_PATH = ROOT / ".claude/workflows/bin/gate_cache.py"

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# JS extraction + real execution (never a Python reimplementation — see module docstring)
# ---------------------------------------------------------------------------


def extract_function(src: str, signature: str) -> str:
    """Return the full `function name(...) { ... }` body, brace-matched.

    `signature` must end in the function body's OWN opening brace (the last `{` in the string) —
    a destructured-parameter signature like `decideAttribution({ checkId, ... }) {` contains an
    earlier `{` for the parameter pattern itself, so brace-matching must start from the body's
    brace, not the first `{` after the signature's start index.
    """
    assert signature.rstrip().endswith("{"), f"signature must end with the body's opening brace: {signature!r}"
    idx = src.index(signature)
    start = idx + len(signature) - 1
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[idx : i + 1]
    raise ValueError(f"unterminated function body for signature {signature!r}")


def decide_attribution_fn(src: str) -> str:
    return extract_function(
        src,
        "function decideAttribution({ checkId, taskGateHistory, cacheStatus = null, "
        "currentTaskFiles = [] }) {",
    )


def build_task_gate_history_fn(src: str) -> str:
    return extract_function(src, "function buildTaskGateHistory(stateTasks, beforeTaskNum) {")


def run_decide_attribution(fn_src: str, args: dict) -> dict | None:
    node_src = f"""
{fn_src}
const result = decideAttribution({json.dumps(args)});
process.stdout.write(JSON.stringify(result));
"""
    proc = subprocess.run(["node", "-e", node_src], capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout.strip())


def run_build_task_gate_history(fn_src: str, state_tasks: dict, before_task_num: int) -> list:
    node_src = f"""
{fn_src}
const result = buildTaskGateHistory({json.dumps(state_tasks)}, {before_task_num});
process.stdout.write(JSON.stringify(result));
"""
    proc = subprocess.run(["node", "-e", node_src], capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout.strip())


# ---------------------------------------------------------------------------
# gate_cache.py — imported directly (task 2 kept its decision logic importable for exactly
# this reason), never shelled out to as a subprocess here.
# ---------------------------------------------------------------------------


def _load_gate_cache_module():
    spec = importlib.util.spec_from_file_location("gate_cache", GATE_CACHE_PATH)
    assert spec and spec.loader, f"could not load module spec from {GATE_CACHE_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate_cache = _load_gate_cache_module()


# ---------------------------------------------------------------------------
# Fixtures — decideAttribution / buildTaskGateHistory
# ---------------------------------------------------------------------------


def test_pre_existing_red_decides_foreign_no_attempt_burned() -> None:
    """Recorded PRE-EXISTING-RED cases (bail-classification-2026-09-13.json) -> ownership=foreign,
    the run continues, and the attempt counter is unchanged (no writable set, no fix loop)."""
    fixtures = [
        {
            "name": "synapse OR.ticket.publishable-eval-report task 1 (skip-count baseline "
            "defaulted to 0, 7 pre-existing skips unrelated to task 1)",
            "checkId": "skip-count-regression",
        },
        {
            "name": "base-template ticket.task-gate-boundaries-are-unenforced task 2 "
            "(CHECK13 whole-corpus violations in an unrelated project's docs)",
            "checkId": "okf-structure",
        },
    ]
    for engine, path in ENGINES.items():
        fn = decide_attribution_fn(path.read_text())
        for fx in fixtures:
            result = run_decide_attribution(
                fn,
                {
                    "checkId": fx["checkId"],
                    "taskGateHistory": [],
                    "cacheStatus": "fail",
                    "currentTaskFiles": ["some/task/file.py"],
                },
            )
            label = f"{engine}: pre-existing-red ({fx['name']}) -> foreign, no attempt burned"
            check(
                label,
                result is not None
                and result.get("ownership") == "foreign"
                and result.get("failure_class") is None
                and result.get("inSpecDebt") is False
                and result.get("writableSet") == [],
            )


def test_fe_7_d_decides_in_spec_debt_not_a_bail() -> None:
    """FE.7.D (feli, task 3): task 2 changed get_api_key_identity's return value and left
    tests/api/test_v1_approvals.py's `decided_by == 'test-secret-key'` assertion stale, task 2's
    own notes deferring the fix to task 7. Task 3 (which never touches auth) inherits the
    already-red check -> in-spec debt, failure_class=fixable, declaredByTask=2, and the failing
    test file is in the fix agent's writable set. This is explicitly NOT a bail."""
    check_id = "pytest-api"
    failing_test = "tests/api/test_v1_approvals.py::test_approve_with_current_digest_resumes_and_sets_approved"
    current_task_files = ["app/routes/approvals.py"]
    for engine, path in ENGINES.items():
        fn = decide_attribution_fn(path.read_text())
        result = run_decide_attribution(
            fn,
            {
                "checkId": check_id,
                "taskGateHistory": [
                    {
                        "taskId": 2,
                        "gateResults": [
                            {
                                "check_id": check_id,
                                "status": "fail",
                                "failing_ids": [failing_test],
                            }
                        ],
                    }
                ],
                "cacheStatus": None,
                "currentTaskFiles": current_task_files,
            },
        )
        label = f"{engine}: FE.7.D -> in-spec debt (fixable), declared by task 2, not a bail"
        check(
            label,
            result is not None
            and result.get("ownership") == "self"
            and result.get("failure_class") == "fixable"
            and result.get("inSpecDebt") is True
            and result.get("declaredByTask") == 2
            and failing_test in (result.get("writableSet") or [])
            and all(f in (result.get("writableSet") or []) for f in current_task_files),
        )


def test_green_at_n_minus_1_red_at_n_is_the_ordinary_fix_loop() -> None:
    """The regression control: a check green at task N-1's own recorded gate_results and red at
    task N decides today's ordinary fix loop, UNCHANGED — and must NOT also read as in-spec debt
    or foreign. A fixture that matches nothing must FAIL, never pass vacuously, so this asserts
    the full positive shape AND the negative shape in the same check."""
    check_id = "unit-tests"
    for engine, path in ENGINES.items():
        fn = decide_attribution_fn(path.read_text())
        result = run_decide_attribution(
            fn,
            {
                "checkId": check_id,
                "taskGateHistory": [
                    {"taskId": 4, "gateResults": [{"check_id": check_id, "status": "pass"}]}
                ],
                "cacheStatus": None,
                "currentTaskFiles": ["this/task/file.py"],
            },
        )
        label = f"{engine}: green at task 4, red at task 5 -> ordinary fix loop (regression control)"
        check(
            label,
            result is not None
            and result.get("ownership") == "self"
            and result.get("failure_class") == "fixable"
            and result.get("inSpecDebt") is False
            and result.get("declaredByTask") is None
            and result.get("introducedAfterTask") == 4,
        )


def test_no_history_and_unknown_cache_decides_nothing() -> None:
    """Nothing decides (no history record AND cacheStatus unknown/None with an empty history) ->
    the function returns null, and the caller's existing triage flow is the fallback. A negative
    control proving the fixture suite can distinguish "decided null" from "decided something"."""
    for engine, path in ENGINES.items():
        fn = decide_attribution_fn(path.read_text())
        result = run_decide_attribution(
            fn,
            {
                "checkId": "some-check",
                "taskGateHistory": [],
                "cacheStatus": None,
                "currentTaskFiles": [],
            },
        )
        check(f"{engine}: no history + no cache status -> decides null (fallback to caller's triage)", result is None)


def test_build_task_gate_history_orders_and_filters() -> None:
    """buildTaskGateHistory: only earlier tasks (task_id < beforeTaskNum) that actually recorded a
    non-empty gate_results array, oldest first; `__pendingBails` and empty-history tasks are
    absent from the result entirely (not zero-length entries)."""
    state_tasks = {
        "1": {"gate_results": [{"check_id": "a", "status": "pass"}]},
        "2": {"gate_results": [{"check_id": "b", "status": "fail"}]},
        "3": {"gate_results": []},
        "4": {"gate_results": [{"check_id": "c", "status": "pass"}]},
        "__pendingBails": [{"note": "not a task"}],
    }
    for engine, path in ENGINES.items():
        fn = build_task_gate_history_fn(path.read_text())
        result = run_build_task_gate_history(fn, state_tasks, 4)
        task_ids = [entry["taskId"] for entry in result]
        check(
            f"{engine}: buildTaskGateHistory(before=4) -> [1, 2] oldest first, task 3/4/__pendingBails excluded",
            task_ids == [1, 2],
        )


# ---------------------------------------------------------------------------
# Fixtures — gate_cache.py lookup/warm (task 2), imported directly
# ---------------------------------------------------------------------------


def test_cache_miss_reruns_only_the_requested_ids() -> None:
    """A cache miss re-runs ONLY the failing check ids it was asked about — assert the exact id
    set, never a count."""
    with tempfile.TemporaryDirectory() as cache_dir:
        result = gate_cache.lookup(
            cache_dir, "example-repo", "deadbeef", "no-lockfile", ["check-a", "check-b", "check-c"]
        )
        check(
            "gate_cache.lookup: empty cache -> misses == exact requested id set, no hits",
            result["hits"] == {} and result["misses"] == ["check-a", "check-b", "check-c"],
        )


def test_cache_hit_reruns_nothing() -> None:
    """A cache hit re-runs nothing: every id that was warmed comes back as a hit with its exact
    recorded status, and none of them appear in misses."""
    with tempfile.TemporaryDirectory() as cache_dir:
        gate_cache.warm(
            cache_dir, "example-repo", "deadbeef", "no-lockfile", {"check-a": "pass", "check-b": "fail"}
        )
        result = gate_cache.lookup(
            cache_dir, "example-repo", "deadbeef", "no-lockfile", ["check-a", "check-b", "check-c"]
        )
        check(
            "gate_cache.lookup: warmed ids come back as hits with recorded status, unwarmed id is the only miss",
            result["hits"] == {"check-a": "pass", "check-b": "fail"} and result["misses"] == ["check-c"],
        )


def test_cache_location_honours_config_override_chain() -> None:
    """The cache location resolves through the env-var override -> harness.json config ->
    documented default chain (task 2), never a literal at the call site."""
    with tempfile.TemporaryDirectory() as repo_root, tempfile.TemporaryDirectory() as override_dir:
        env_resolved = gate_cache.resolve_cache_dir(
            repo_root, harness_config=None, env={"GATE_CACHE_DIR": override_dir}
        )
        check(
            "gate_cache.resolve_cache_dir: GATE_CACHE_DIR env override wins over the default",
            env_resolved == override_dir,
        )

        harness_cfg = {"gateCache": {"dir": "custom/.cache-dir"}}
        cfg_resolved = gate_cache.resolve_cache_dir(repo_root, harness_config=harness_cfg, env={})
        check(
            "gate_cache.resolve_cache_dir: harness.json gateCache.dir honoured when no env override",
            cfg_resolved == str(Path(repo_root) / "custom" / ".cache-dir"),
        )

        default_resolved = gate_cache.resolve_cache_dir(repo_root, harness_config={}, env={})
        check(
            "gate_cache.resolve_cache_dir: falls back to the documented default when neither is set",
            default_resolved == str(Path(repo_root) / ".claude" / "workflows" / ".gate-cache"),
        )


def test_corrupt_cache_file_is_a_miss_not_an_exception() -> None:
    """A corrupt cache entry degrades to a miss for every requested id rather than raising
    (task 2 AC4) — an attribution look-back must never be blocked by cache state."""
    with tempfile.TemporaryDirectory() as cache_dir:
        entry_path = Path(cache_dir) / "example-repo" / "deadbeef__no-lockfile.json"
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        entry_path.write_text("{ this is not valid json")
        result = gate_cache.lookup(cache_dir, "example-repo", "deadbeef", "no-lockfile", ["check-a"])
        check(
            "gate_cache.lookup: corrupt cache file degrades to a miss, not an exception",
            result["hits"] == {} and result["misses"] == ["check-a"],
        )


def main() -> int:
    print("test_failure_attribution")
    test_pre_existing_red_decides_foreign_no_attempt_burned()
    test_fe_7_d_decides_in_spec_debt_not_a_bail()
    test_green_at_n_minus_1_red_at_n_is_the_ordinary_fix_loop()
    test_no_history_and_unknown_cache_decides_nothing()
    test_build_task_gate_history_orders_and_filters()
    test_cache_miss_reruns_only_the_requested_ids()
    test_cache_hit_reruns_nothing()
    test_cache_location_honours_config_override_chain()
    test_corrupt_cache_file_is_a_miss_not_an_exception()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
