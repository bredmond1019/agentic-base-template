#!/usr/bin/env python3
"""test_nextest_artifact_wrapper.py -- fixture suite for scripts/nextest_artifact_wrapper.py.

BT.ticket.checks-must-name-their-failing-artifact task 3's testing_strategy: "a fixture for
nextest_artifact_wrapper.py covering: a test whose corpus path is derivable, and one whose path
is not, asserting <no-artifact> rather than a guess." Both cases are exercised at the unit level
(`resolve_artifact`) and at the CLI level (subprocess over a real libtest-json-shaped events
file), because the CLI path is what the real integration (`cargo nextest run --message-format
libtest-json | python3 scripts/nextest_artifact_wrapper.py`) actually exercises.

Standard library only; no cargo/nextest binary required -- the events fed in are hand-built
JSON, the same shape nextest emits, not a real cargo invocation.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import nextest_artifact_wrapper as naw  # noqa: E402

failures: list[str] = []


def check(desc: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {desc}")
    if not cond:
        failures.append(f"{desc}: {detail}")


# --- unit level: resolve_artifact -----------------------------------------------------------

MAPPING = {
    "fleet_regression::test_lane_agent_stale": ".fleet-locks/lane-agents/agent-known.json",
    "fleet_corpus::": "planning/known-corpus-dir",
}

check(
    "exact test name match resolves to its mapped corpus path",
    naw.resolve_artifact("fleet_regression::test_lane_agent_stale", MAPPING)
    == ".fleet-locks/lane-agents/agent-known.json",
)

check(
    "prefix-keyed entry resolves a test not individually listed",
    naw.resolve_artifact("fleet_corpus::test_something_unlisted", MAPPING)
    == "planning/known-corpus-dir",
)

check(
    "a test with no mapping entry and no matching prefix resolves to <no-artifact>, never a "
    "guess",
    naw.resolve_artifact("totally_unmapped::test_mystery", MAPPING) == naw.NO_ARTIFACT,
)

check(
    "an empty mapping (the no-mapping-file default) resolves every test to <no-artifact>",
    naw.resolve_artifact("anything::at_all", {}) == naw.NO_ARTIFACT,
)


# --- CLI level: real libtest-json-shaped events, one derivable, one not ---------------------

EVENTS = "\n".join([
    json.dumps({"type": "suite", "event": "started", "test_count": 2}),
    json.dumps({
        "type": "test", "event": "failed",
        "name": "fleet_regression::test_lane_agent_stale",
        "stdout": "assertion failed: heartbeat too old\nat fleet_regression.rs:42",
    }),
    json.dumps({
        "type": "test", "event": "failed",
        "name": "totally_unmapped::test_mystery",
        "stdout": "assertion failed: mystery condition",
    }),
    json.dumps({"type": "suite", "event": "failed", "passed": 0, "failed": 2}),
]) + "\n"

with tempfile.TemporaryDirectory() as tmp:
    events_path = Path(tmp) / "events.jsonl"
    events_path.write_text(EVENTS, encoding="utf-8")
    mapping_path = Path(tmp) / "map.json"
    mapping_path.write_text(json.dumps(MAPPING), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "nextest_artifact_wrapper.py"),
         "--events", str(events_path), "--mapping", str(mapping_path)],
        capture_output=True, text=True,
    )

    check(
        "CLI exits 1 when at least one failed test was reported",
        proc.returncode == 1,
        f"returncode={proc.returncode} stdout={proc.stdout!r}",
    )
    check(
        "CLI FAIL line for the derivable test names its real corpus path, not a guess",
        "FAIL .fleet-locks/lane-agents/agent-known.json "
        "fleet_regression::test_lane_agent_stale:" in proc.stdout,
        f"stdout={proc.stdout!r}",
    )
    check(
        "CLI FAIL line for the underivable test emits the explicit <no-artifact> token, never "
        "a fabricated path",
        "FAIL <no-artifact> totally_unmapped::test_mystery:" in proc.stdout,
        f"stdout={proc.stdout!r}",
    )

    # --- no mapping file at all: every failure still reports cleanly, all <no-artifact> -----
    proc_no_map = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "nextest_artifact_wrapper.py"),
         "--events", str(events_path)],
        capture_output=True, text=True,
    )
    check(
        "with no --mapping at all, both failures resolve to <no-artifact> rather than erroring",
        proc_no_map.returncode == 1
        and proc_no_map.stdout.count(f"FAIL {naw.NO_ARTIFACT} ") == 2,
        f"returncode={proc_no_map.returncode} stdout={proc_no_map.stdout!r}",
    )

    # --- a clean run (no failures) exits 0 and prints nothing --------------------------------
    clean_events_path = Path(tmp) / "clean.jsonl"
    clean_events_path.write_text(
        json.dumps({"type": "suite", "event": "started", "test_count": 1}) + "\n"
        + json.dumps({"type": "test", "event": "ok", "name": "some::test_that_passed"}) + "\n"
        + json.dumps({"type": "suite", "event": "ok", "passed": 1, "failed": 0}) + "\n",
        encoding="utf-8",
    )
    proc_clean = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "nextest_artifact_wrapper.py"),
         "--events", str(clean_events_path), "--mapping", str(mapping_path)],
        capture_output=True, text=True,
    )
    check(
        "a clean nextest run (no failed test events) exits 0 with no FAIL line",
        proc_clean.returncode == 0 and "FAIL" not in proc_clean.stdout,
        f"returncode={proc_clean.returncode} stdout={proc_clean.stdout!r}",
    )

    # --- malformed/non-JSON lines interleaved (nextest's real stream does this) are skipped -
    noisy_events_path = Path(tmp) / "noisy.jsonl"
    noisy_events_path.write_text(
        "running 1 test\n"
        + json.dumps({
            "type": "test", "event": "failed",
            "name": "fleet_regression::test_lane_agent_stale",
            "stdout": "boom",
        }) + "\n"
        + "not json at all {{{\n",
        encoding="utf-8",
    )
    proc_noisy = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "nextest_artifact_wrapper.py"),
         "--events", str(noisy_events_path), "--mapping", str(mapping_path)],
        capture_output=True, text=True,
    )
    check(
        "non-JSON lines interleaved in the events stream are skipped, not fatal",
        proc_noisy.returncode == 1
        and "FAIL .fleet-locks/lane-agents/agent-known.json" in proc_noisy.stdout,
        f"returncode={proc_noisy.returncode} stdout={proc_noisy.stdout!r} "
        f"stderr={proc_noisy.stderr!r}",
    )


if failures:
    print(f"\n{len(failures)} failure(s):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print(f"\nall checks passed")
sys.exit(0)
