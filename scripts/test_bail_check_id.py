#!/usr/bin/env python3
"""Fixture suite for check_id validation (resolveCheckId) — absorbed
BT.ticket.bails-check-id-is-not-a-check-name, task 4 of
BT.ticket.gate-results-and-failure-attribution.

`resolveCheckId` is extracted verbatim from each engine's source (brace-matched
around its declaration) and executed for real under `node -e`, rather than
reimplemented in Python — a reimplementation could silently drift from what the
engines actually do and pass while the real function is broken.

Covers the four cases the task calls for:
  (a) a check_id matching a real planning/harness.json name resolves verbatim
  (b) a non-matching value resolves to null + check_id_raw
  (c) an absent/empty harness config resolves every check_id to null + check_id_raw
      without crashing
  (d) sdlc-flow.js's review-site check_id is brought under the same rule (task 3's
      recorded choice), asserted against the file as it actually stands
"""

from __future__ import annotations

import json
import subprocess
import sys
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


def extract_function(src: str, signature: str) -> str:
    """Return the full `function name(...) { ... }` body, brace-matched."""
    idx = src.index(signature)
    start = src.index("{", idx)
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[idx : i + 1]
    raise ValueError(f"unterminated function body for signature {signature!r}")


def run_resolve_check_id(fn_src: str, candidate, cfg: dict) -> dict:
    node_src = f"""
{fn_src}
const result = resolveCheckId({json.dumps(candidate)}, {json.dumps(cfg)});
process.stdout.write(JSON.stringify(result));
"""
    proc = subprocess.run(
        ["node", "-e", node_src], capture_output=True, text=True, timeout=30
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout.strip())


def real_check_name() -> str:
    harness = json.loads((ROOT / "planning/harness.json").read_text())
    names = [
        c["name"]
        for c in harness.get("validation", {}).get("checks", [])
        if c.get("name")
    ]
    assert names, "planning/harness.json has no named checks -- cannot form a test fixture"
    return names[0]


def resolve_check_id_fn(src: str) -> str:
    return extract_function(src, "function resolveCheckId(candidate, cfg) {")


def test_matching_name_resolves_verbatim() -> None:
    """(a) a check_id matching a real planning/harness.json name resolves verbatim."""
    name = real_check_name()
    cfg = {"validation": {"checks": [{"name": name}]}}
    for engine, path in ENGINES.items():
        fn = resolve_check_id_fn(path.read_text())
        result = run_resolve_check_id(fn, name, cfg)
        check(
            f"{engine}: matching check_id ({name!r}) resolves verbatim",
            result.get("check_id") == name and result.get("check_id_raw") is None,
        )


def test_nonmatching_value_resolves_to_null_plus_raw() -> None:
    """(b) a non-matching value resolves to null + check_id_raw."""
    cfg = {"validation": {"checks": [{"name": "some-real-check"}]}}
    bogus = "__totally-bogus-check-name__"
    for engine, path in ENGINES.items():
        fn = resolve_check_id_fn(path.read_text())
        result = run_resolve_check_id(fn, bogus, cfg)
        check(
            f"{engine}: non-matching check_id -> null + check_id_raw preserved",
            result.get("check_id") is None and result.get("check_id_raw") == bogus,
        )


def test_absent_harness_config_resolves_null_without_crashing() -> None:
    """(c) planning/harness.json absent (mocked as an empty cfg) never crashes."""
    candidate = "anything"
    for engine, path in ENGINES.items():
        fn = resolve_check_id_fn(path.read_text())
        try:
            result = run_resolve_check_id(fn, candidate, {})
            crashed = False
        except RuntimeError as exc:  # pragma: no cover - only on real crash
            crashed = True
            result = None
            print(f"    (node error: {exc})")
        check(f"{engine}: absent/empty harness config does not crash", not crashed)
        if not crashed:
            check(
                f"{engine}: absent/empty harness config resolves to null + raw",
                result.get("check_id") is None
                and result.get("check_id_raw") == candidate,
            )
        # Also confirm cfg=null (the shape an absent-file read might hand back) survives.
        try:
            null_result = run_resolve_check_id(fn, candidate, None)
            null_crashed = False
        except RuntimeError:
            null_crashed = True
            null_result = None
        check(f"{engine}: cfg=null does not crash", not null_crashed)
        if not null_crashed:
            check(
                f"{engine}: cfg=null resolves to null + raw",
                null_result.get("check_id") is None
                and null_result.get("check_id_raw") == candidate,
            )


def test_review_site_brought_under_the_rule() -> None:
    """(d) sdlc-flow's review-site check_id: assert task 3's actual recorded choice.

    Task 3's notes record the choice made: 'review' is validated through the SAME
    resolveCheckId lookup as every other bail-fold site (never an ad-hoc exemption),
    so it always resolves to null with check_id_raw: 'review'. Assert that choice is
    actually present in the file, and — as a behavioral check, not just text-grep —
    that running the real extracted function on the literal 'review' candidate against
    a cfg with no such check name produces exactly that result.
    """
    src = ENGINES["sdlc-flow"].read_text()
    validated_via_shared_rule = "resolveCheckId('review', harnessCfg)" in src
    check(
        "sdlc-flow.js: review-site check_id goes through the shared resolveCheckId rule",
        validated_via_shared_rule,
    )

    fn = resolve_check_id_fn(src)
    cfg = {"validation": {"checks": [{"name": "some-real-check"}]}}
    result = run_resolve_check_id(fn, "review", cfg)
    check(
        "sdlc-flow.js: 'review' resolves to null + check_id_raw: 'review' (never a real check)",
        result.get("check_id") is None and result.get("check_id_raw") == "review",
    )


def main() -> int:
    print("test_bail_check_id")
    test_matching_name_resolves_verbatim()
    test_nonmatching_value_resolves_to_null_plus_raw()
    test_absent_harness_config_resolves_null_without_crashing()
    test_review_site_brought_under_the_rule()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
