#!/usr/bin/env python3
"""Regression tests for check_prompt_templates.py.

Synthetic fixtures, not the real engines -- these pin the DETECTOR's behaviour so
it cannot rot into a no-op. The historical defect it exists for is reproduced
verbatim in `test_bare_backtick_in_prose_is_caught`: that exact shape shipped in
four places across sdlc-task.js and sdlc-flow.js, passed a whole-file
`node --check`, and silently removed two engines from the Workflow registry.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_prompt_templates import extract_regions, check_region  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        FAILURES.append(name)


GOOD = """\
const r = await agent(`${W}
Stage the files, then commit them explicitly to \\`git commit\\` itself
(not merely to \\`git add\\`), so nothing else is swept in.
`, withModel({ label: 'x' }, MODEL.a))
"""

# The exact historical defect: bare backticks around a shell command in prose.
BAD = """\
const r = await agent(`${W}
Stage the files, then commit them explicitly to `git commit` itself
(not merely to `git add`), so nothing else is swept in.
`, withModel({ label: 'x' }, MODEL.a))
"""

# Interpolation inside an escaped span must still be allowed.
GOOD_INTERP = """\
const r = await agent(`${W}
Do NOT pass \\`--head ${branchName}\\` -- it is a \\`gh pr list\\`-only flag.
`, withModel({ label: 'x' }, MODEL.a))
"""


def regions_of(src: str):
    return extract_regions(src.split("\n"))


def parse_fails(src: str) -> bool:
    lines = src.split("\n")
    regions = regions_of(src)
    return any(check_region(lines, s, e) is not None for s, e in regions)


def test_extractor_pairs_opener_with_closer() -> None:
    regions = regions_of(GOOD)
    check("extractor finds exactly one region", len(regions) == 1)
    check("region starts at the opener line", regions and regions[0][0] == 1)
    check("region ends at the column-0 closer", regions and regions[0][1] == 4)


def test_escaped_backticks_pass() -> None:
    check("well-escaped prose passes", not parse_fails(GOOD))


def test_bare_backtick_in_prose_is_caught() -> None:
    check("bare-backtick prose is caught", parse_fails(BAD))


def test_region_check_is_strictly_stronger_than_file_check() -> None:
    """The gate's premise, stated honestly.

    In the REAL engines, whole-file `node --check` returned 0 while three regions
    were broken -- verified at commit 441bd26~1, where sdlc-task.js and
    sdlc-flow.js both passed `node --check` yet failed a region-scoped parse at
    lines 1396-1479, 1629-1707 and 2074-2133 respectively.

    That parity-preserving arrangement depends on surrounding code and is NOT
    reproducible in a minimal fixture -- this file's own BAD fixture is rejected
    at file level too. So rather than fake it, assert the weaker property that is
    actually true of the fixture and is what the gate relies on: a broken region
    is caught by the region check. The file-level gap is documented above with
    the commit that demonstrates it.
    """
    check("broken region is caught by the region check", parse_fails(BAD))


def test_interpolation_inside_escaped_span() -> None:
    check("escaped span containing ${...} passes", not parse_fails(GOOD_INTERP))


def test_unclosed_template_is_reported() -> None:
    src = "const r = await agent(`${W}\nno closer here\n"
    check("opener with no closer still yields a region", len(regions_of(src)) == 1)


def main() -> int:
    print("test_check_prompt_templates")
    test_extractor_pairs_opener_with_closer()
    test_escaped_backticks_pass()
    test_bare_backtick_in_prose_is_caught()
    test_region_check_is_strictly_stronger_than_file_check()
    test_interpolation_inside_escaped_span()
    test_unclosed_template_is_reported()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("\nall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
