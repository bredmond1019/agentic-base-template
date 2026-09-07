#!/usr/bin/env python3
"""Regression pin: the render-identity schema must be declared above the calls that reach it.

WHY THIS EXISTS
---------------
On 2026-09-07 both SDLC engines crashed at their bookkeep/state-write stage with

    ReferenceError: Cannot access 'RENDER_IDENTITY_SCHEMA' before initialization

after ~18 minutes, 17 agents and 1.24M subagent tokens of completed work per run. The
`<<shared:RENDER_IDENTITY_SCHEMA>>` region sat near the END of each engine. The bookkeep prompt --
a top-level statement around line 3302 -- interpolates `${await renderStateFlipScript(...)}`, which
calls `renderAgentFlag()`, whose body reads the const declared ~150 lines BELOW that call site. An
engine's main body is top-level code containing top-level `await`, so evaluation suspends there
while agents run and resumes in source order; it reached the use having never evaluated the
declaration. `async function` declarations hoist, so both functions were callable -- a top-level
`const` does not, so the binding was still in its temporal dead zone.

A temporal dead zone is a RUNTIME error, which is why nothing caught it: `node --check` exits 0 on
both engines, so `engines-parse` was green; the prompt regions parse in isolation, so
`prompt-template-parse` was green; the library inlined identically, so `build_engines.py` was
green. Every gate in the repo passed over two engines that could not finish a single run.

SCOPE -- READ THIS BEFORE EXTENDING IT
--------------------------------------
This is a REGRESSION PIN for one known defect, not a general temporal-dead-zone analyser, and the
narrowness is deliberate rather than lazy. Two broader versions were written and thrown away while
fixing this:

  * scanning every top-level line for every top-level const name -> 49 findings on these two
    engines, essentially all of them names appearing in comments and in prompt PROSE;
  * call-graph reachability with regex reference detection -> 8 findings on the FIXED engines,
    all false: `\\btestDepth\\b` also matches `cfg.testDepth`, `{ testDepth }`, and names inside
    string literals.

A general check needs a real JS parser and scope analysis, which is filed as its own block rather
than approximated here. A gate that cries wolf gets switched off, and a switched-off gate is worse
than no gate -- doubly so in this repo, where a false red blocks every concurrent lane.

Both directions are exercised by --selftest, which requires a pre-fix copy to fail.
"""
from __future__ import annotations
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINES = [ROOT / ".claude/workflows/sdlc-task.js", ROOT / ".claude/workflows/sdlc-flow.js"]

DECL = re.compile(r"^const RENDER_IDENTITY_SCHEMA\s*=")
# The two top-level interpolations that reach it, through hoisted helpers.
REACHES = ("${await renderStateFlipScript(", "${await renderAgentFlag()", "${await renderScopeFlag()")


def check(path: Path) -> list[str]:
    lines = path.read_text().split("\n")

    decl = next((i for i, l in enumerate(lines) if DECL.match(l)), None)
    if decl is None:
        return [f"FAIL {path.name}: no top-level `const RENDER_IDENTITY_SCHEMA =` found -- the "
                f"pin has lost its subject; re-point or retire it deliberately, never delete it "
                f"to go green."]

    failures = []
    for i, line in enumerate(lines):
        for needle in REACHES:
            if needle in line and i < decl:
                failures.append(
                    f"FAIL {path.name}:{i+1}: `{needle}...` reaches RENDER_IDENTITY_SCHEMA, which "
                    f"is declared below at line {decl+1} -- temporal dead zone; this engine throws "
                    f"ReferenceError at its bookkeep stage while node --check passes. Move the "
                    f"<<shared:RENDER_IDENTITY_SCHEMA>> region above line {i+1}."
                )
    return failures


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--selftest"]
    selftest = "--selftest" in sys.argv
    targets = [Path(a) for a in args] or ENGINES

    all_failures = []
    for engine in targets:
        if not engine.exists():
            print(f"FAIL {engine} does not exist")
            return 1
        all_failures.extend(check(engine))

    if selftest:
        # Positive control: a synthetic pre-fix copy (declaration moved to the end) MUST fail.
        import tempfile
        for engine in targets:
            lines = engine.read_text().split("\n")
            d = next(i for i, l in enumerate(lines) if DECL.match(l))
            end = next((j for j in range(d, len(lines)) if lines[j].startswith("// <</shared:RENDER_IDENTITY_SCHEMA>>")), d)
            start = next(j for j in range(d, -1, -1) if lines[j].startswith("// <<shared:RENDER_IDENTITY_SCHEMA>>"))
            broken = lines[:start] + lines[end + 1:] + [""] + lines[start:end + 1]
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
                fh.write("\n".join(broken))
                probe = Path(fh.name)
            got = check(probe)
            probe.unlink()
            if not got:
                print(f"FAIL selftest: moving the declaration below its use in {engine.name} did "
                      f"NOT trip this check -- the pin is decorative.")
                return 1
        print(f"selftest OK -- the pin fires on a synthetic pre-fix copy of each engine.")

    if all_failures:
        print("\n".join(all_failures))
        return 1
    print(f"OK -- RENDER_IDENTITY_SCHEMA is declared above every call that reaches it, "
          f"across {len(targets)} engine(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
