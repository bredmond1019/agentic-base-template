#!/usr/bin/env python3
"""Runtime-inversion divergence gate for the generated .agents/skills/ mirrors (BT.3.G-task3).

THE EXIT CONDITION (planning/blocks/BT.3.G.json `description`): hand-edit a generated mirror
and the check exits 1; regenerate and it exits 0. This file proves that inversion actually
happens, rather than pinning a fixed red case.

WHY A RUNTIME INVERSION, NOT A COMMITTED RED FIXTURE: once a test file is registered
`gates: true`, pinning a permanently-red case inside it red-gates every concurrent lane in this
repo -- including whichever task would eventually turn it green (AGENTS.md-adjacent
/generate-tasks pitfall; measured to cost 40 minutes circularly on an earlier run). Instead, each
test method here BREAKS a precondition inside a temp copy of the real skill trees, asserts the
break is detected, then RESTORES it and asserts the check is clean again -- the suite itself is
never red at any commit, even though it exercises the red path every time it runs.

THE OTHER HALF OF THE CONTRACT (planning/BT.3.G/decision.md): frontmatter is per-surface and
explicitly OUTSIDE the gate. Reflowing a mirror's `description:` (wrap width, `>` vs `>-`) must
NOT trip --check -- a gate that reds on frontmatter formatting would recreate the unsatisfiable
bar this block already bailed on once (task 2 of BT.3.G). test_reflowed_frontmatter_stays_clean
pins that explicitly.

All three steps run against a `tempfile.mkdtemp()` COPY of this repo's real `.claude/skills/`
and `.agents/skills/` trees -- never the real trees themselves, which the generator write-mode
call in step (iii) would otherwise mutate.

Usage: python3 scripts/test_skill_surface_divergence.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "generate_skill_surfaces.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import generate_skill_surfaces as gss  # noqa: E402


def copy_real_skill_trees(dest: Path) -> None:
    """Copy this repo's real .claude/skills/ and .agents/skills/ into dest, for a tempdir tree
    the generator can safely be pointed at in both --check and write mode."""
    shutil.copytree(REPO_ROOT / ".claude" / "skills", dest / ".claude" / "skills")
    shutil.copytree(REPO_ROOT / ".agents" / "skills", dest / ".agents" / "skills")


def run_generator(root: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    args = [sys.executable, str(SCRIPT), "--root", str(root)]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(args, capture_output=True, text=True, cwd=str(REPO_ROOT))


class SkillSurfaceDivergenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="skill-surface-divergence-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        copy_real_skill_trees(self.tmp)

        slugs = gss.mirrored_slugs(self.tmp)
        self.assertTrue(slugs, "no mirrored slugs found in the copied tree -- fixture is broken")
        self.target_slug = slugs[0]
        self.target_path = self.tmp / ".agents" / "skills" / self.target_slug / "SKILL.md"

    # -- (i)+(iii): the tree starts clean, and stays clean after a no-op regenerate ----------

    def test_i_check_exits_zero_on_untouched_copy(self) -> None:
        result = run_generator(self.tmp, ["--check"])
        self.assertEqual(
            result.returncode,
            0,
            msg=f"--check should be clean on an untouched copy of the real trees\n"
            f"stdout={result.stdout!r} stderr={result.stderr!r}",
        )

    # -- (ii): editing a generated mirror's BODY makes --check fail, naming the slug ---------

    def test_ii_dirty_body_makes_check_exit_nonzero_and_names_slug(self) -> None:
        before = self.target_path.read_text(encoding="utf-8")
        dirtied = before + "\nDIVERGENCE-TEST: this line was appended directly to the mirror.\n"
        self.target_path.write_text(dirtied, encoding="utf-8")

        result = run_generator(self.tmp, ["--check"])
        self.assertNotEqual(
            result.returncode,
            0,
            msg=f"--check must fail once a generated mirror's body has drifted from its "
            f".claude/ source\nstdout={result.stdout!r} stderr={result.stderr!r}",
        )
        self.assertIn(
            self.target_slug,
            result.stdout,
            f"--check output must name the diverged slug {self.target_slug!r}: {result.stdout!r}",
        )

    # -- (iii): regenerating restores the mirror and --check is clean again ------------------

    def test_iii_regenerate_restores_clean_check(self) -> None:
        before = self.target_path.read_text(encoding="utf-8")
        dirtied = before + "\nDIVERGENCE-TEST: this line was appended directly to the mirror.\n"
        self.target_path.write_text(dirtied, encoding="utf-8")

        dirty_check = run_generator(self.tmp, ["--check"])
        self.assertNotEqual(dirty_check.returncode, 0, "precondition: dirty tree must fail --check first")

        write_result = run_generator(self.tmp)
        self.assertEqual(
            write_result.returncode,
            0,
            msg=f"write-mode regenerate should succeed\nstdout={write_result.stdout!r} "
            f"stderr={write_result.stderr!r}",
        )

        after = self.target_path.read_text(encoding="utf-8")
        self.assertEqual(
            after,
            before,
            "regenerating should restore the mirror to its pre-divergence bytes",
        )

        clean_check = run_generator(self.tmp, ["--check"])
        self.assertEqual(
            clean_check.returncode,
            0,
            msg=f"--check must be clean again after regenerating\n"
            f"stdout={clean_check.stdout!r} stderr={clean_check.stderr!r}",
        )

    # -- (iv): frontmatter formatting is explicitly OUTSIDE the gate -------------------------

    def test_iv_reflowed_frontmatter_stays_clean(self) -> None:
        before = self.target_path.read_text(encoding="utf-8")
        split = gss.split_frontmatter(before)
        self.assertIsNotNone(split, f"{self.target_path} has no anchored frontmatter block")
        frontmatter, body = split

        if ">-" in frontmatter:
            reflowed_frontmatter = frontmatter.replace(">-", ">", 1)
        elif "\n  " in frontmatter:
            # Reflow: collapse an existing folded continuation to a single unfolded line.
            reflowed_frontmatter = "\n".join(
                line for line in frontmatter.splitlines(keepends=False) if not line.startswith("  ")
            ) + "\n"
        else:
            # Single-line description -- fold it onto a continuation line instead, and swap
            # style. Either direction is a legitimate "reflow" for this contract's purposes.
            reflowed_frontmatter = frontmatter.replace("description:", "description: >-\n ", 1)

        self.assertNotEqual(
            reflowed_frontmatter,
            frontmatter,
            "test bug: the reflow transform did not actually change the frontmatter",
        )

        self.target_path.write_text(reflowed_frontmatter + body, encoding="utf-8")

        result = run_generator(self.tmp, ["--check"])
        self.assertEqual(
            result.returncode,
            0,
            msg=f"--check must NOT fail on a frontmatter-only reflow -- frontmatter is "
            f"per-surface and explicitly outside the gate\n"
            f"stdout={result.stdout!r} stderr={result.stderr!r}",
        )


if __name__ == "__main__":
    unittest.main()
