#!/usr/bin/env python3
"""nextest_artifact_wrapper.py -- BT.ticket.checks-must-name-their-failing-artifact task 3.

`cargo nextest` reports a failure by TEST NAME, not by the corpus file the test consulted --
the measured counter-example docs/harness.md's per-check audit cites for the `FAIL <path>
<text>` format (see "The FAIL line format"). A test name is not an artifact path: two
unrelated defects surfacing as two different test names look like two clusters even when both
tests read the same broken file, and a fabricated/guessed path is worse than none, because it
can wrongly UNIFY two unrelated defects instead of correctly failing to unify them.

WHAT THIS DOES
--------------
Reads `cargo nextest run --message-format libtest-json`-shaped, newline-delimited JSON events
(one JSON object per line -- the format nextest calls "libtest-json"; see
https://nexte.st/docs/machine-readable/libtest-json/) from a file or stdin, finds every event
reporting a FAILED test, and for each one emits a `FAIL <path> <text>` (or
`FAIL <no-artifact> <text>`) line per docs/harness.md's format.

THE MAPPING -- explicit, never inferred
----------------------------------------
There is no reliable way to derive "the corpus path a test consulted" from the test's name or
its stdout in general -- that would be exactly the kind of guess this ticket exists to forbid
(block spec: "a wrong path is worse than a null one, since it clusters two unrelated defects
together"). Instead this wrapper is handed an explicit test-name -> corpus-path MAPPING as a
small JSON file (`--mapping path/to/map.json`, `{"<test name>": "<corpus path>", ...}`) that the
owning repo's test suite maintains for the tests it wants clustered by artifact -- e.g. a
fixture-driven test whose name embeds or is registered against the fixture file it reads. A
failing test with no entry in the mapping emits the explicit `<no-artifact>` token, never a
guess.

Matching is exact on the full nextest test name first; if the mapping file also carries prefix
entries (a key ending in `::`), the longest matching prefix wins, so a whole test module can be
mapped to one artifact without enumerating every test in it.

No mapping file at all (`--mapping` omitted, or the file is absent) is not an error -- every
failing test is reported `<no-artifact>`, which is the conservative, always-correct fallback
this ticket requires when "that mapping is genuinely unavailable" (block spec `what`).

USAGE
-----
    cargo nextest run --workspace --message-format libtest-json-diff \\
        | python3 scripts/nextest_artifact_wrapper.py --mapping nextest_artifact_map.json

    python3 scripts/nextest_artifact_wrapper.py --events events.jsonl --mapping map.json

Exit code mirrors nextest's own semantics for this wrapper's purpose: 0 if no FAILED event was
seen, 1 if at least one was (matching every other check registered in planning/harness.json,
where a printed FAIL line is what the shape gate looks for, and a nonzero exit is what the
engines' Test stage / hooks/pre-push stage 2 key their pass/fail decision on).

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import IO, Iterable, Optional

NO_ARTIFACT = "<no-artifact>"


def load_mapping(path: Optional[str]) -> dict:
    """Load the test-name -> corpus-path mapping. Missing/absent `path` is NOT an error --
    every failing test then falls back to `<no-artifact>` (see module docstring)."""
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: mapping file must be a JSON object of test-name -> path")
    return data


def resolve_artifact(test_name: str, mapping: dict) -> str:
    """Exact match first; else the longest `prefix::`-keyed entry that `test_name` starts
    with; else the explicit `<no-artifact>` token. Never fabricates a path."""
    if test_name in mapping:
        return mapping[test_name]

    best_prefix = None
    for key in mapping:
        if key.endswith("::") and test_name.startswith(key):
            if best_prefix is None or len(key) > len(best_prefix):
                best_prefix = key
    if best_prefix is not None:
        return mapping[best_prefix]

    return NO_ARTIFACT


def _iter_failed_tests(events: Iterable[str]) -> Iterable[tuple]:
    """Parse newline-delimited JSON nextest/libtest-json events and yield
    (test_name, detail) for every FAILED test event. Tolerant of the small vocabulary
    variance between nextest's `type`/`event` fields and plain libtest-json (`type: "test"`,
    `event: "failed"`, name in `name` or `test_name`) -- lines that don't parse as JSON or
    don't look like a failed-test event are silently skipped, matching cargo nextest's own
    stream, which interleaves suite-level and human-readable lines with the JSON events when
    `--message-format libtest-json` is combined with default terminal output."""
    for raw in events:
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") != "test":
            continue
        if event.get("event") != "failed":
            continue
        name = event.get("name") or event.get("test_name")
        if not name:
            continue
        detail = event.get("stdout") or event.get("message") or "test failed"
        # Collapse to one line for the FAIL line's human-text tail; a parser only needs the
        # first `FAIL <path>` line per finding (docs/harness.md), so multi-line stdout is
        # summarized to its first non-empty line rather than dumped raw.
        first_line = next((ln for ln in str(detail).splitlines() if ln.strip()), "test failed")
        yield name, first_line.strip()


def run(events: Iterable[str], mapping: dict) -> int:
    saw_failure = False
    for test_name, detail in _iter_failed_tests(events):
        saw_failure = True
        artifact = resolve_artifact(test_name, mapping)
        print(f"FAIL {artifact} {test_name}: {detail}")
    return 1 if saw_failure else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", default=None,
                     help="path to a newline-delimited JSON nextest/libtest-json events file; "
                          "defaults to stdin")
    ap.add_argument("--mapping", default=None,
                     help="path to a JSON {test-name-or-prefix::: corpus-path} mapping file; "
                          "omitted or absent means every failure is reported <no-artifact>")
    args = ap.parse_args()

    mapping = load_mapping(args.mapping)

    source: IO[str]
    if args.events:
        with open(args.events, "r", encoding="utf-8") as f:
            return run(f.readlines(), mapping)
    return run(sys.stdin.readlines(), mapping)


if __name__ == "__main__":
    sys.exit(main())
