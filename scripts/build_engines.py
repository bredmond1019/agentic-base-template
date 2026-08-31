#!/usr/bin/env python3
"""Inline the shared engine library into both SDLC engines, in place.

WHY THIS EXISTS
---------------
`sdlc-task.js` and `sdlc-flow.js` are self-contained by necessity: the Workflow
harness copies ONE .js file per engine into a per-session snapshot and executes
that copy (base-template standing rule 10), so an `import` is not available to
them. The consequence is that every shared stage prompt, schema and helper
exists TWICE on disk, and the two copies drift.

They had drifted. A 2026-08-30 audit found eight divergences between the two
engines, including `expect_red` (D68) implemented in one engine only -- which
made a whole class of block unrunnable under `/sdlc-flow` -- and the D8
completeness self-check being a real checklist in one engine and a single
sentence in the other. Every one of those was a copy that stopped matching its
twin, silently, because nothing compared them.

WHAT THIS DOES
--------------
`.claude/workflows/prompts/shared.js` holds the master copy of each block that
is identical in both engines, delimited by `// <<shared:NAME>> ... <</shared:NAME>>`.
Each engine carries the same markers around its own inlined copy. This script
replaces each engine's marked region with the library's version, IN PLACE --
position is never changed, so `const` ordering and TDZ behaviour are preserved
exactly.

`--check` (the default, and what the gate runs) rebuilds in memory and reports
any engine whose on-disk bytes differ. `--write` applies the build.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not force a block into the library to make the engines "match". Where
the engines genuinely must differ -- the run-root variable, worklog vs no
worklog, review vs terminal reconcile -- the block stays engine-local and the
difference is recorded as INTENDED in docs/workflows/prompt-parity.md section 2.
A shared library that needs a per-engine flag on every second line has not
removed the duplication, only moved it somewhere harder to read.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY = REPO_ROOT / ".claude/workflows/prompts/shared.js"
ENGINES = [
    REPO_ROOT / ".claude/workflows/sdlc-task.js",
    REPO_ROOT / ".claude/workflows/sdlc-flow.js",
]

OPEN = re.compile(r"^// <<shared:(\w+)>>$")
CLOSE = re.compile(r"^// <</shared:(\w+)>>$")


def parse_regions(text: str, label: str) -> dict[str, tuple[int, int, str]]:
    """Return {name: (open_idx, close_idx, body)} for every marked region."""
    lines = text.split("\n")
    regions: dict[str, tuple[int, int, str]] = {}
    open_at: tuple[str, int] | None = None
    for idx, line in enumerate(lines):
        m_open = OPEN.match(line)
        m_close = CLOSE.match(line)
        if m_open:
            if open_at is not None:
                raise SystemExit(
                    f"{label}: nested/unclosed shared region -- "
                    f"'{open_at[0]}' still open at line {idx + 1}"
                )
            open_at = (m_open.group(1), idx)
        elif m_close:
            if open_at is None:
                raise SystemExit(f"{label}: closing marker with no opener at line {idx + 1}")
            name, start = open_at
            if m_close.group(1) != name:
                raise SystemExit(
                    f"{label}: marker mismatch at line {idx + 1} -- "
                    f"opened '{name}', closed '{m_close.group(1)}'"
                )
            if name in regions:
                raise SystemExit(f"{label}: duplicate shared region '{name}'")
            regions[name] = (start, idx, "\n".join(lines[start + 1 : idx]))
            open_at = None
    if open_at is not None:
        raise SystemExit(f"{label}: unclosed shared region '{open_at[0]}'")
    return regions


def build(engine_text: str, library: dict[str, tuple[int, int, str]], label: str) -> str:
    regions = parse_regions(engine_text, label)
    unknown = sorted(set(regions) - set(library))
    if unknown:
        raise SystemExit(
            f"{label}: shared region(s) {unknown} have no master in {LIBRARY.name}. "
            "Either add the block to the library or remove the markers."
        )
    lines = engine_text.split("\n")
    for name, (start, end, _) in sorted(regions.items(), key=lambda kv: -kv[1][0]):
        lines[start + 1 : end] = library[name][2].split("\n")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="apply the build (default: check only)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    library = parse_regions(LIBRARY.read_text(), LIBRARY.name)
    if not library:
        raise SystemExit(f"{LIBRARY.name}: no shared regions found -- refusing to blank the engines.")

    stale: list[str] = []
    for engine in ENGINES:
        rel = engine.relative_to(REPO_ROOT)
        current = engine.read_text()
        built = build(current, library, str(rel))
        if built == current:
            continue
        if args.write:
            engine.write_text(built)
            if not args.quiet:
                print(f"rebuilt {rel}")
        else:
            stale.append(str(rel))

    if stale:
        print("engines-inlined FAILED -- these engines differ from the shared library:")
        for rel in stale:
            print(f"  - {rel}")
        print(
            f"\nThe master copy is {LIBRARY.relative_to(REPO_ROOT)}. Edit the block THERE, then run:\n"
            "  python3 scripts/build_engines.py --write\n"
            "and commit the library and both engines in the same change. If you edited the inlined\n"
            "copy inside an engine instead, that edit is what this is reporting -- move it to the\n"
            "library rather than re-running the build to erase it."
        )
        return 1

    if not args.quiet:
        n = len(library)
        print(f"OK -- {n} shared block(s) inlined identically across {len(ENGINES)} engines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
