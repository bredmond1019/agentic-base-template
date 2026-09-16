#!/usr/bin/env python3
"""Fixture suite for the baseline-diff check kind (BT.ticket.failure-attribution-and-gate-cache,
task 5) — replays fixture file trees through the EXACT Python fail-closed logic extracted from
both built engines' `renderBaselineDiffCheck` region, executed for real via `python3`, never
reimplemented here (a reimplementation could silently drift from what the engines actually run
and pass while the real gate is broken — same rule as scripts/test_failure_attribution.py).

`renderBaselineDiffCheck` is a JS function that RENDERS a shell/python snippet as a string (it does
not itself decide anything at render time), so the extraction here is two-stage:
  1. Extract the JS function body (brace-matched) from each built engine's source and invoke it for
     real under `node -e`, passing concrete header/n/cd/command/currentPath/baselinePath/baseSha/
     compareKeys — this produces the exact rendered check text the engine would emit for a real run.
  2. Pull the embedded `python3 << 'PYEOF' ... PYEOF` body out of that rendered text (the JS template
     has already substituted every `${...}` placeholder with the concrete values passed in step 1,
     so the extracted Python is the literal, fully-resolved script the engine would actually run) and
     execute it for real against fixture files built under `mktemp -d`.

Eight cases (acceptance criteria for task 7 / BT.ticket.sdlc-reconcile-gate-runs-validate-brain-
with-no-baseline, absorbed into this block per its own notes):
  1. pre-existing E1 (baseline == current) PASSES.
  2. net-new E2 on an untouched file (current adds one item absent from baseline) FAILS naming E2.
  3. a ruff-shaped array (different compareKeys) passes when unchanged and fails as before when a
     net-new item appears.
  4. a JSON-object current output (not a list) FAILS naming the non-array cause.
  5. empty / unparseable current output FAILS naming the specific cause (two sub-cases).
  6. a missing baseline FAILS naming the path.
  7. a base-SHA mismatch FAILS naming both SHAs.
  8. a baseline with no `.sha` sidecar FAILS naming "baseline predates base-SHA stamping".

Every failing case asserts the SPECIFIC cause text the gate must name, never merely a non-zero exit
— a fail-closed gate that fails for the wrong reason is still a bug (task 7 acceptance criteria).
"""

from __future__ import annotations

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

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# JS extraction + real execution (never a Python reimplementation — see module docstring)
# ---------------------------------------------------------------------------

RENDER_SIGNATURE = (
    "function renderBaselineDiffCheck({ header, n, cd, command, currentPath, baselinePath, "
    "baseSha, compareKeys }) {"
)


def extract_function(src: str, signature: str) -> str:
    """Return the full `function name(...) { ... }` body, brace-matched.

    `signature` must end in the function body's OWN opening brace (the last `{` in the string) —
    a destructured-parameter signature contains an earlier `{` for the parameter pattern itself,
    so brace-matching must start from the body's brace, not the first `{` after signature start.
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


def render_baseline_diff_fn(src: str) -> str:
    return extract_function(src, RENDER_SIGNATURE)


def render_check_text(fn_src: str, args: dict) -> str:
    node_src = f"""
{fn_src}
const result = renderBaselineDiffCheck({json.dumps(args)});
process.stdout.write(result);
"""
    proc = subprocess.run(["node", "-e", node_src], capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return proc.stdout


def extract_python_body(rendered_text: str) -> str:
    """Pull the fully-resolved `python3 << 'PYEOF' ... PYEOF` body out of a rendered check."""
    marker = "python3 << 'PYEOF'\n"
    assert marker in rendered_text, f"no python3 heredoc found in rendered check text: {rendered_text!r}"
    after = rendered_text.split(marker, 1)[1]
    assert "\nPYEOF" in after, "no closing PYEOF found in rendered check text"
    return after.split("\nPYEOF", 1)[0]


def run_python_body(py_src: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-c", py_src], capture_output=True, text=True, timeout=30)
    return proc.returncode, proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# Fixture helper
# ---------------------------------------------------------------------------


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def render_for_engine(fn_src: str, tmp: Path, *, baseline, baseline_sha, current, base_sha, compare_keys, skip_baseline=False, skip_sha=False, skip_current=False) -> str:
    baseline_path = tmp / "baseline.json"
    current_path = tmp / "current.json"
    if not skip_baseline:
        write_json(baseline_path, baseline)
    if not skip_sha and not skip_baseline:
        (tmp / "baseline.json.sha").write_text(baseline_sha if baseline_sha is not None else base_sha)
    if not skip_current:
        if isinstance(current, str):
            current_path.write_text(current)
        else:
            write_json(current_path, current)
    rendered = render_check_text(
        fn_src,
        {
            "header": "CHECK 1 — baseline-diff-fixture",
            "n": 1,
            "cd": "",
            "command": "true",
            "currentPath": str(current_path),
            "baselinePath": str(baseline_path),
            "baseSha": base_sha,
            "compareKeys": compare_keys,
        },
    )
    return extract_python_body(rendered)


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

E1 = {"file": "src/a.py", "line": 10, "rule": "E1", "message": "pre-existing"}
E2 = {"file": "src/b.py", "line": 4, "rule": "E2", "message": "net-new"}


def test_pre_existing_e1_passes() -> None:
    for engine, path in ENGINES.items():
        fn = render_baseline_diff_fn(path.read_text())
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            py_src = render_for_engine(
                fn, tmp, baseline=[E1], baseline_sha="deadbeef", current=[E1], base_sha="deadbeef", compare_keys=["file", "line", "rule"]
            )
            code, out = run_python_body(py_src)
            check(
                f"{engine}: pre-existing E1 (baseline == current) PASSES",
                code == 0 and "CHECK 1 PASSED" in out and "no net-new items" in out,
            )


def test_net_new_e2_fails_naming_e2() -> None:
    for engine, path in ENGINES.items():
        fn = render_baseline_diff_fn(path.read_text())
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            py_src = render_for_engine(
                fn, tmp, baseline=[E1], baseline_sha="deadbeef", current=[E1, E2], base_sha="deadbeef", compare_keys=["file", "line", "rule"]
            )
            code, out = run_python_body(py_src)
            check(
                f"{engine}: net-new E2 on an untouched file FAILS naming E2",
                code != 0 and "NET-NEW" in out and json.dumps(E2) in out,
            )


def test_ruff_shaped_array_passes_and_fails_as_before() -> None:
    ruff_baseline_item = {"filename": "app/x.py", "code": "F401", "location": {"row": 3}}
    ruff_new_item = {"filename": "app/y.py", "code": "E501", "location": {"row": 9}}
    for engine, path in ENGINES.items():
        fn = render_baseline_diff_fn(path.read_text())
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            py_src = render_for_engine(
                fn, tmp, baseline=[ruff_baseline_item], baseline_sha="feedface",
                current=[ruff_baseline_item], base_sha="feedface", compare_keys=["filename", "code"],
            )
            code, out = run_python_body(py_src)
            check(f"{engine}: ruff-shaped array unchanged PASSES", code == 0 and "CHECK 1 PASSED" in out)
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            py_src = render_for_engine(
                fn, tmp, baseline=[ruff_baseline_item], baseline_sha="feedface",
                current=[ruff_baseline_item, ruff_new_item], base_sha="feedface", compare_keys=["filename", "code"],
            )
            code, out = run_python_body(py_src)
            check(
                f"{engine}: ruff-shaped array with a net-new item FAILS naming it (as before)",
                code != 0 and "NET-NEW" in out and json.dumps(ruff_new_item) in out,
            )


def test_json_object_current_output_fails_naming_non_array() -> None:
    for engine, path in ENGINES.items():
        fn = render_baseline_diff_fn(path.read_text())
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            py_src = render_for_engine(
                fn, tmp, baseline=[E1], baseline_sha="deadbeef",
                current={"error": "not a list"}, base_sha="deadbeef", compare_keys=["file", "line", "rule"],
            )
            code, out = run_python_body(py_src)
            check(
                f"{engine}: JSON-object current output FAILS naming the non-array cause "
                f"(reproduces the recorded observed_red)",
                code != 0
                and "not a JSON array" in out
                and "got dict" in out
                and "non-array output fails closed" in out,
            )


def test_empty_and_unparseable_current_output_fail_closed() -> None:
    for engine, path in ENGINES.items():
        fn = render_baseline_diff_fn(path.read_text())
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            py_src = render_for_engine(
                fn, tmp, baseline=[E1], baseline_sha="deadbeef",
                current="", base_sha="deadbeef", compare_keys=["file", "line", "rule"],
            )
            code, out = run_python_body(py_src)
            check(
                f"{engine}: empty current output FAILS naming 'current output is empty'",
                code != 0 and "current output is empty" in out,
            )
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            py_src = render_for_engine(
                fn, tmp, baseline=[E1], baseline_sha="deadbeef",
                current="{ not valid json", base_sha="deadbeef", compare_keys=["file", "line", "rule"],
            )
            code, out = run_python_body(py_src)
            check(
                f"{engine}: unparseable current output FAILS naming the JSON parse cause "
                f"(never treated as zero items)",
                code != 0
                and "current output is not valid JSON" in out
                and "unparseable output fails closed, never treated as zero items" in out,
            )


def test_missing_baseline_fails_naming_the_path() -> None:
    for engine, path in ENGINES.items():
        fn = render_baseline_diff_fn(path.read_text())
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            py_src = render_for_engine(
                fn, tmp, baseline=None, baseline_sha=None, current=[E1], base_sha="deadbeef",
                compare_keys=["file", "line", "rule"], skip_baseline=True,
            )
            code, out = run_python_body(py_src)
            expected_path = str(tmp / "baseline.json")
            check(
                f"{engine}: missing baseline FAILS naming the path",
                code != 0 and f"missing baseline at {expected_path}" in out,
            )


def test_base_sha_mismatch_fails_naming_both_shas() -> None:
    for engine, path in ENGINES.items():
        fn = render_baseline_diff_fn(path.read_text())
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            py_src = render_for_engine(
                fn, tmp, baseline=[E1], baseline_sha="oldsha123", current=[E1], base_sha="newsha456",
                compare_keys=["file", "line", "rule"],
            )
            code, out = run_python_body(py_src)
            check(
                f"{engine}: base-SHA mismatch FAILS naming both SHAs",
                code != 0
                and "base-SHA mismatch" in out
                and "baseline=oldsha123" in out
                and "run=newsha456" in out,
            )


def test_baseline_with_no_sha_sidecar_fails_naming_predates_stamping() -> None:
    for engine, path in ENGINES.items():
        fn = render_baseline_diff_fn(path.read_text())
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            py_src = render_for_engine(
                fn, tmp, baseline=[E1], baseline_sha=None, current=[E1], base_sha="deadbeef",
                compare_keys=["file", "line", "rule"], skip_sha=True,
            )
            code, out = run_python_body(py_src)
            check(
                f"{engine}: baseline with no .sha sidecar FAILS naming 'baseline predates base-SHA stamping'",
                code != 0 and "baseline predates base-SHA stamping" in out,
            )


def main() -> int:
    print("test_baseline_diff_gate")
    test_pre_existing_e1_passes()
    test_net_new_e2_fails_naming_e2()
    test_ruff_shaped_array_passes_and_fails_as_before()
    test_json_object_current_output_fails_naming_non_array()
    test_empty_and_unparseable_current_output_fail_closed()
    test_missing_baseline_fails_naming_the_path()
    test_base_sha_mismatch_fails_naming_both_shas()
    test_baseline_with_no_sha_sidecar_fails_naming_predates_stamping()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
