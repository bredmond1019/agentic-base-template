#!/usr/bin/env python3
"""Fixture suite for check_frontmatter_presence.py (BT.ticket.engine-docs-drift-tripwire, task 2).

Self-contained, no pytest dependency, in the fixture style of scripts/test_check_lane_records.py
and scripts/test_check_messages.py: no synthetic corpus tree is needed here since the checker
takes a path (for display/scope only) and content on stdin, so fixtures are plain strings driven
through the module's `check()` function directly, plus one subprocess invocation to exercise the
CLI/exit-code contract.

THE CENTRAL CASE IS A RETRO-FIXTURE, not a synthesized one — the real content the sdlc-task
bookkeep stage wrote into base-template/planning/status.md on 2026-08-22, preserved at
planning/BT.ticket.engine-docs-drift-tripwire/evidence/_status-md-frontmatter-displaced-2026-08-22.txt
(a .txt copy with a leading underscore so it never itself enters the corpus and red-gates it). That
file had its "Current focus" paragraph written twice in the wrong place: once as line 1, ABOVE the
opening `---` fence, and once between `related:` and the closing fence, inside the block.

This suite asserts the actual TRANSITION, which is the only real evidence that this checker closes
a gap the existing gate does not: the BRAIN's hooks/check_frontmatter.py (resolved by walking up
from this repo for a directory containing brain.toml — this repo can be cloned without the brain
present, so that case is a printed SKIP, not a failure) exits 0 on the retro-fixture's bytes, and
the new check_frontmatter_presence.py exits 1 on the *same* bytes. A suite that only shows the new
check failing proves nothing about what was missing before it existed.

D68 discipline: every reject case below (DISPLACED via the retro-fixture, UNTERMINATED, ABSENT) was
observed FAILING OPEN (exit 0, no rejection) against a pre-detection stub of check() during this
script's development, before the corresponding branch in check_frontmatter_presence.check() existed
-- each was then observed FAILING CLOSED (the named exit-1 diagnostic) once the branch landed. That
observation is not re-run here (it is a one-time development-time discipline, not a repeatable
fixture), but is recorded here per the standing convention this repo's other checker suites use.

No case writes into the real corpus or the real hooks/ directory — the retro-fixture is read
read-only from its preserved evidence path, and the brain hook (if present) is invoked read-only
via `git show`-free subprocess with content piped on stdin, never writing anything.

Run: python3 scripts/test_check_frontmatter_presence.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "check_frontmatter_presence.py"
RETRO_FIXTURE_PATH = (
    REPO_ROOT
    / "planning"
    / "BT.ticket.engine-docs-drift-tripwire"
    / "evidence"
    / "_status-md-frontmatter-displaced-2026-08-22.txt"
)

_spec = importlib.util.spec_from_file_location("check_frontmatter_presence", MODULE_PATH)
cfp = importlib.util.module_from_spec(_spec)
sys.modules["check_frontmatter_presence"] = cfp
_spec.loader.exec_module(cfp)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def _find_brain_hook() -> Path | None:
    """Walk up from REPO_ROOT looking for a directory carrying brain.toml + hooks/check_frontmatter.py.
    Returns None (never raises) if not found -- this repo can be cloned standalone."""
    candidate = REPO_ROOT
    for _ in range(6):
        candidate = candidate.parent
        if (candidate / "brain.toml").is_file():
            hook = candidate / "hooks" / "check_frontmatter.py"
            return hook if hook.is_file() else None
    return None


VALID_FRONTMATTER = """---
type: Reference
title: A Valid Doc
description: A file with clean, well-formed frontmatter.
---

# Body

Nothing unusual here.
"""

UNTERMINATED = """---
type: Reference
title: Unterminated
description: No closing fence follows.

# Body
"""

ABSENT_IN_CORPUS = """# A Planning Doc

This lives under planning/ but never opens a frontmatter fence at all.
"""

VALID_FRONTMATTER_WITH_BODY_RULE = """---
type: Reference
title: A Doc With A Body Rule
description: Valid frontmatter at line 1, and a bare horizontal rule later in the prose body.
---

# Section One

Some introductory text.

---

More prose after a bare horizontal rule, with no key-looking lines following it. This is the
realistic false-positive shape the DISPLACED heuristic must not misfire on: a normal in-corpus
OKF document that happens to use `---` as a section divider in its body. Because valid frontmatter
already closes at line 1, the checker never even reaches the later-block scan for this file --
which is exactly why this shape is safe.
"""

# An in-corpus file that lacks frontmatter at line 1 (so it is correctly rejected -- every
# in-corpus .md is obliged to carry frontmatter) but whose only fence-shaped content is a bare
# horizontal rule with NO key-looking line after it. This exercises the DISPLACED heuristic's own
# false-positive boundary directly: the rejection must come back as ABSENT, never as a wrongly
# confident DISPLACED (which would name a fence line that isn't really a frontmatter block).
IN_SCOPE_NO_FRONTMATTER_BUT_HAS_BARE_RULE = """# A Prose Document

Some introductory text with no frontmatter at the top at all.

---

More prose after a bare horizontal rule. No key-looking lines follow the rule, so the DISPLACED
scan must not mistake this bare rule for a frontmatter fence.
"""


def main() -> int:
    # --- retro-fixture: the central case ------------------------------------------------
    if not RETRO_FIXTURE_PATH.is_file():
        check("retro-fixture file exists", False, f"missing: {RETRO_FIXTURE_PATH}")
    else:
        retro_content = RETRO_FIXTURE_PATH.read_text()

        brain_hook = _find_brain_hook()
        if brain_hook is None:
            print("[SKIP] old brain hook exits 0 on retro-fixture -- brain repo not reachable")
        else:
            old_proc = subprocess.run(
                [sys.executable, str(brain_hook), "planning/status.md"],
                input=retro_content,
                capture_output=True,
                text=True,
            )
            check(
                "old brain hook (check_frontmatter.py) exits 0 on the retro-fixture",
                old_proc.returncode == 0,
                f"exit={old_proc.returncode} stderr={old_proc.stderr!r}",
            )

        new_exit = cfp.check("planning/status.md", retro_content)
        check(
            "new check_frontmatter_presence.py exits 1 (DISPLACED) on the same retro-fixture bytes",
            new_exit == 1,
            f"exit={new_exit}",
        )

        # Also exercise the CLI/subprocess contract on the retro-fixture.
        new_proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "planning/status.md"],
            input=retro_content,
            capture_output=True,
            text=True,
        )
        check(
            "new check CLI exits 1 and names DISPLACED on the retro-fixture",
            new_proc.returncode == 1 and "DISPLACED" in new_proc.stderr,
            f"exit={new_proc.returncode} stderr={new_proc.stderr!r}",
        )

    # --- remaining cases ------------------------------------------------------------------
    check(
        "valid frontmatter (in-corpus) accepted",
        cfp.check("planning/foo.md", VALID_FRONTMATTER) == 0,
    )

    check(
        "unterminated frontmatter (in-corpus) rejected",
        cfp.check("planning/bar.md", UNTERMINATED) == 1,
    )

    check(
        "absent frontmatter (in-corpus, no fence at all) rejected",
        cfp.check("planning/baz.md", ABSENT_IN_CORPUS) == 1,
    )

    # --- ABSENT_EXEMPT_NAMES: root README.md/CLAUDE.md with zero frontmatter is a valid
    # corpus leaf, mirroring mev's is_root_instruction_file (core/mev/src/brain/okf.rs) --
    # base-template's own CLAUDE.md is exactly this case and validate-brain --structure
    # reports 0 errors on it today; an unconditional ABSENT reject would red-gate it.
    check(
        "root CLAUDE.md with no frontmatter at all is accepted (mirrors mev's "
        "is_root_instruction_file exemption)",
        cfp.check("CLAUDE.md", ABSENT_IN_CORPUS) == 0,
    )
    check(
        "root README.md with no frontmatter at all is accepted (same exemption)",
        cfp.check("README.md", ABSENT_IN_CORPUS) == 0,
    )
    check(
        "a nested CLAUDE.md (not unit root) is NOT exempt -- ABSENT still rejected",
        cfp.check("planning/subdir/CLAUDE.md", ABSENT_IN_CORPUS) == 1,
    )
    check(
        "root index.md with no frontmatter is NOT exempt (mev requires it) -- ABSENT rejected",
        cfp.check("index.md", ABSENT_IN_CORPUS) == 1,
    )
    check(
        "root CLAUDE.md is still rejected as UNTERMINATED, not swept into the ABSENT "
        "exemption (deliberately stricter than mev here -- see ABSENT_EXEMPT_NAMES docstring)",
        cfp.check("CLAUDE.md", UNTERMINATED) == 1,
    )

    check(
        "leading-underscore file accepted regardless of content (out of corpus)",
        cfp.check("planning/_scratch.md", ABSENT_IN_CORPUS) == 0,
    )

    check(
        "non-.md file accepted regardless of content (out of corpus)",
        cfp.check("planning/notes.txt", ABSENT_IN_CORPUS) == 0,
    )

    check(
        "valid frontmatter with a bare horizontal rule later in the body is NOT rejected "
        "(false-positive guard)",
        cfp.check("planning/essay.md", VALID_FRONTMATTER_WITH_BODY_RULE) == 0,
    )

    absent_rule_proc = subprocess.run(
        [sys.executable, str(MODULE_PATH), "planning/no-fm-but-rule.md"],
        input=IN_SCOPE_NO_FRONTMATTER_BUT_HAS_BARE_RULE,
        capture_output=True,
        text=True,
    )
    check(
        "in-corpus doc with no frontmatter and only a bare (keyless) rule is rejected as "
        "ABSENT, never misreported as DISPLACED",
        absent_rule_proc.returncode == 1
        and "ABSENT" in absent_rule_proc.stderr
        and "DISPLACED" not in absent_rule_proc.stderr,
        f"stderr={absent_rule_proc.stderr!r}",
    )

    # --- scope helper direct checks ---------------------------------------------------------
    check("is_in_scope: docs/ path is in scope", cfp.is_in_scope("docs/guide.md") is True)
    check("is_in_scope: planning/ path is in scope", cfp.is_in_scope("planning/x.md") is True)
    check("is_in_scope: root README.md is in scope", cfp.is_in_scope("README.md") is True)
    check(
        "is_in_scope: unrelated root .md (not README/CLAUDE/index) is out of scope",
        cfp.is_in_scope("NOTES.md") is False,
    )
    check(
        "is_in_scope: src/lib.md (no planning/docs, not root-special) is out of scope",
        cfp.is_in_scope("src/lib.md") is False,
    )
    check(
        "is_in_scope: handoff.md is ephemeral, out of scope even under planning/",
        cfp.is_in_scope("planning/foo/handoff.md") is False,
    )

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1

    print(f"\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
