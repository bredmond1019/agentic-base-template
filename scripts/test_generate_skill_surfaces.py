#!/usr/bin/env python3
"""Fixture suite pinning scripts/generate_skill_surfaces.py's contract (BT.3.G-task1).

THE CONTRACT (planning/BT.3.G/decision.md, operator-decided 2026-09-08): a SKILL.md is
`<frontmatter block, fences included><body>`. The generator replaces THE BODY ONLY, copied
verbatim from .claude/skills/<slug>/SKILL.md. It NEVER authors, reflows or rewrites the
frontmatter of an .agents/ file that already has one -- that half is per-surface and preserved
byte-for-byte, the same contract scripts/regenerate_gemini.py already implements for its tail.

This file intentionally contains NO assertion that the generator authors or reformats an
existing file's frontmatter -- that was the superseded, unsatisfiable contract this block
bailed on once (see decision.md).

THE MIRRORED SET. Input is `AGENT_SKILL_SLUGS INTERSECT (directories under .claude/skills/)`,
never AGENT_SKILL_SLUGS alone:
  - `sdlc-task` / `sdlc-flow` are in AGENT_SKILL_SLUGS with NO .claude/ source -- hand-authored
    manual-replication guides scripts/check_skill_sync.py hashes against the engines. A
    generator fed the bare registry would destroy both on its first run. Case (c) pins this.
  - `epic` / `write-operating-doc` are .claude/-only, absent from AGENT_SKILL_SLUGS, and must
    not gain mirrors. Case (d) pins this.

Every fixture runs under tempfile.mkdtemp() and never reads or writes this repo's real
.claude/skills/ or .agents/skills/ trees. Run against main (no scripts/generate_skill_surfaces.py
yet) this file MUST fail -- that failing output is the observed-red evidence for D68.

Usage: python3 scripts/test_generate_skill_surfaces.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "generate_skill_surfaces.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import sync_downstream_harness as sdh  # noqa: E402

# The regex the generator is expected to implement: an anchored split of a SKILL.md into its
# frontmatter block (both `---` fences included) and everything after it (the body). Used here
# ONLY to build expected fixture content from source bytes -- never imported from the generator
# itself, since the generator does not exist yet on task 1.
_FRONTMATTER_RE = re.compile(r"\A(---\n.*?\n---\n)(.*)\Z", re.DOTALL)


def split_frontmatter(text: str) -> tuple[str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise AssertionError(f"fixture text has no anchored frontmatter block: {text[:80]!r}")
    return m.group(1), m.group(2)


def write_skill(root: Path, surface: str, slug: str, content: str) -> Path:
    """surface is 'claude' or 'agents'."""
    d = root / f".{surface}" / "skills" / slug
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(content, encoding="utf-8")
    return p


def run_generator(root: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    args = [sys.executable, str(SCRIPT), "--root", str(root)]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(args, capture_output=True, text=True, cwd=str(REPO_ROOT))


# Fixture bodies/frontmatter, held as module constants so every test method builds the same
# byte-exact inputs it later asserts against.

CLAUDE_BODY_A = (
    "\n# Fixture Title A\n\nThis body will be copied verbatim into the .agents/ mirror.\n"
    "It changes between runs to prove the copy is live, not a one-time snapshot.\n"
)

AGENTS_FRONTMATTER_A_ODD = (
    "---\n"
    "name: brain-graph\n"
    "description: >-\n"
    "  Deliberately odd fixture folding: an unusual continuation width and the\n"
    "  '>-' chomping style, on purpose, to prove frontmatter formatting is never\n"
    "  touched by the generator.\n"
    "---\n"
)

CLAUDE_BODY_B = (
    "\n# Fixture Title B\n\n"
    "This body cites `CLAUDE.md` and `.claude/skills/` as real, correct paths on BOTH\n"
    "surfaces -- translating them would make the documented rule false. See the\n"
    "`agent-doc-mirrors-drift-and-skills-corruption` carryover hazard.\n"
)

CLAUDE_FRONTMATTER_B = (
    "---\n"
    "name: write-okf-markdown\n"
    "description: fixture claude-side description for case (b)\n"
    "allowed-tools: Bash(git:*)\n"
    "---\n"
)

AGENTS_FRONTMATTER_B = (
    "---\n"
    "name: write-okf-markdown\n"
    "description: >\n"
    "  fixture agents-side description for case (b), folded differently than the\n"
    "  claude-side copy on purpose\n"
    "---\n"
)

AGENTS_ONLY_C = (
    "---\n"
    "name: sdlc-task\n"
    "description: hand-authored manual-replication guide, no .claude/ source exists\n"
    "---\n"
    "\n# sdlc-task (Antigravity replication guide)\n\n"
    "This file must be byte-unchanged after the generator runs: it has no .claude/\n"
    "counterpart in this fixture tree, matching the real sdlc-task/sdlc-flow shape.\n"
)

CLAUDE_ONLY_D = (
    "---\n"
    "name: epic\n"
    "description: .claude/-only skill, deliberately absent from AGENT_SKILL_SLUGS\n"
    "---\n"
    "\n# epic\n\nThis skill must never gain an .agents/ mirror.\n"
)

CLAUDE_ONLY_E = (
    "---\n"
    "name: stamp-workflow-run-id\n"
    "description: fixture claude-side description for the authoring case (e)\n"
    "allowed-tools: Bash(python3:*)\n"
    "---\n"
    "\n# stamp-workflow-run-id\n\n"
    "First-time mirror: no .agents/ file exists yet for this slug in the fixture tree.\n"
)


class GenerateSkillSurfacesFixtures(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="skill-surfaces-fixture-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    # -- self-checks on the real registry, so the fixture slugs chosen below stay valid ------

    def test_fixture_slugs_are_registry_members_where_claimed(self) -> None:
        for slug in ("brain-graph", "write-okf-markdown", "sdlc-task", "stamp-workflow-run-id"):
            self.assertIn(
                slug,
                sdh.AGENT_SKILL_SLUGS,
                f"fixture assumes {slug!r} is in AGENT_SKILL_SLUGS",
            )
        self.assertNotIn(
            "epic",
            sdh.AGENT_SKILL_SLUGS,
            "fixture assumes 'epic' is absent from AGENT_SKILL_SLUGS (.claude/-only skill)",
        )

    # -- case (a): existing pair, odd .agents/ frontmatter preserved byte-identical ----------

    def test_case_a_existing_frontmatter_preserved_body_replaced(self) -> None:
        claude_frontmatter_a = (
            "---\nname: brain-graph\ndescription: fixture\nallowed-tools: Bash(bastion:*)\n---\n"
        )
        write_skill(self.tmp, "claude", "brain-graph", claude_frontmatter_a + CLAUDE_BODY_A)
        agents_path = write_skill(
            self.tmp, "agents", "brain-graph", AGENTS_FRONTMATTER_A_ODD + "\n# OLD BODY\n\nstale.\n"
        )

        result = run_generator(self.tmp)
        self.assertEqual(result.returncode, 0, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")

        after = agents_path.read_text(encoding="utf-8")
        got_frontmatter, got_body = split_frontmatter(after)

        self.assertEqual(
            got_frontmatter,
            AGENTS_FRONTMATTER_A_ODD,
            "existing .agents/ frontmatter (including odd '>-' folding) must be byte-identical",
        )
        self.assertEqual(
            got_body,
            CLAUDE_BODY_A,
            "the .agents/ body must be replaced verbatim with the .claude/ body",
        )

    # -- case (b): literal path strings inside the body round-trip unchanged ----------------

    def test_case_b_path_literals_round_trip_unchanged(self) -> None:
        write_skill(self.tmp, "claude", "write-okf-markdown", CLAUDE_FRONTMATTER_B + CLAUDE_BODY_B)
        agents_path = write_skill(
            self.tmp, "agents", "write-okf-markdown", AGENTS_FRONTMATTER_B + "\n# stale body\n"
        )

        result = run_generator(self.tmp)
        self.assertEqual(result.returncode, 0, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")

        after = agents_path.read_text(encoding="utf-8")
        got_frontmatter, got_body = split_frontmatter(after)

        self.assertEqual(got_frontmatter, AGENTS_FRONTMATTER_B)
        self.assertIn("CLAUDE.md", got_body)
        self.assertIn(".claude/skills/", got_body)
        self.assertEqual(got_body, CLAUDE_BODY_B)

    # -- case (c): registry slug with NO .claude/ source is skipped, bytes unchanged --------

    def test_case_c_no_claude_source_is_skipped_bytes_unchanged(self) -> None:
        agents_path = write_skill(self.tmp, "agents", "sdlc-task", AGENTS_ONLY_C)
        before_bytes = agents_path.read_bytes()
        # Deliberately no .claude/skills/sdlc-task fixture -- matches the real sdlc-task shape.

        result = run_generator(self.tmp)
        self.assertEqual(result.returncode, 0, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")

        after_bytes = agents_path.read_bytes()
        self.assertEqual(
            before_bytes,
            after_bytes,
            "a registry slug with no .claude/ source must be skipped and left byte-unchanged "
            "(the sdlc-task/sdlc-flow protection)",
        )

    # -- case (d): a .claude/-only skill absent from the registry generates nothing ---------

    def test_case_d_unregistered_claude_skill_generates_nothing(self) -> None:
        write_skill(self.tmp, "claude", "epic", CLAUDE_ONLY_D)
        agents_epic_path = self.tmp / ".agents" / "skills" / "epic" / "SKILL.md"
        self.assertFalse(agents_epic_path.exists())

        result = run_generator(self.tmp)
        self.assertEqual(result.returncode, 0, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")

        self.assertFalse(
            agents_epic_path.exists(),
            "'epic' has a .claude/ source but is absent from AGENT_SKILL_SLUGS and must not "
            "gain an .agents/ mirror",
        )

    # -- case (e): the one authoring case -- new mirror created, no allowed-tools -----------

    def test_case_e_new_mirror_created_with_no_allowed_tools(self) -> None:
        write_skill(self.tmp, "claude", "stamp-workflow-run-id", CLAUDE_ONLY_E)
        agents_path = self.tmp / ".agents" / "skills" / "stamp-workflow-run-id" / "SKILL.md"
        self.assertFalse(agents_path.exists())

        result = run_generator(self.tmp)
        self.assertEqual(result.returncode, 0, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")

        self.assertTrue(agents_path.exists(), "a new mirror must be created for the authoring case")
        created = agents_path.read_text(encoding="utf-8")
        created_frontmatter, created_body = split_frontmatter(created)

        self.assertIn("name: stamp-workflow-run-id", created_frontmatter)
        self.assertIn("description:", created_frontmatter)
        self.assertNotIn(
            "allowed-tools:",
            created_frontmatter,
            "a newly authored mirror must never carry an allowed-tools key "
            "(absent from .agents/ in all real pairs)",
        )
        _, claude_body = split_frontmatter(CLAUDE_ONLY_E)
        self.assertEqual(created_body, claude_body)


if __name__ == "__main__":
    unittest.main()
