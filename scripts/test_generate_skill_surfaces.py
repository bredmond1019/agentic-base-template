#!/usr/bin/env python3
"""Contract for scripts/generate_skill_surfaces.py, written BEFORE the generator exists
(BT.3.G-task1). This file specifies the generator so it is written to a fixed contract rather
than to whatever it happens to produce.

THE TRANSFORM (measured 2026-09-08 across all 17 currently-mirrored .claude/skills/<slug> ->
.agents/skills/<slug> pairs — see planning/blocks/BT.3.G.json): the BODIES (everything after the
closing `---` of the frontmatter) are byte-identical in 17 of 17. The only differences are in the
frontmatter:
  (a) `.claude/` writes `description:` as a single long plain-scalar line; `.agents/` writes it
      as a folded block scalar (`description: >`) with the text re-wrapped and indented two
      spaces.
  (b) `.claude/` carries an `allowed-tools:` line; `.agents/` never does.
So the generator is: emit `name` verbatim, emit `description` folded, DROP `allowed-tools`, copy
the body verbatim. NOTHING ELSE — in particular there is no word substitution anywhere. That is
deliberate: every "claude" string in a mirrored body is a literal path or filename (`CLAUDE.md`,
`.claude/skills/`), and rewriting them would make the rules those bodies state false (carryover
`agent-doc-mirrors-drift-and-skills-corruption`). A verbatim body copy avoids that trap by
construction — case (b) below asserts it explicitly.

THE MIRRORED SET, and the exclusion that matters most: the generator's input set is
`AGENT_SKILL_SLUGS INTERSECT (directories under .claude/skills/)` — imported from
scripts/sync_downstream_harness.py, never re-listed. AGENT_SKILL_SLUGS also holds `sdlc-task` and
`sdlc-flow`, which have NO .claude/skills/ source at all: they are the hand-authored
manual-replication guides scripts/check_skill_sync.py hashes against the engines. A generator fed
the bare registry would overwrite and destroy both on its first run — case (c) below pins that a
registry slug with no source is SKIPPED and its existing .agents/ file is left byte-for-byte
unchanged. Symmetrically, a .claude/skills/ directory that is NOT in the registry (the shape of
`epic` / `write-operating-doc`, which are .claude/-only by choice) must generate nothing —
case (d).

THE GENERATOR CONTRACT this test pins (scripts/generate_skill_surfaces.py, once it exists, must
expose exactly this):

  compute_mirror_content(claude_skill_md: str) -> str
      Pure function. Given the full text of a .claude/skills/<slug>/SKILL.md file, returns the
      full text of the .agents/skills/<slug>/SKILL.md mirror: `name` verbatim, `description`
      folded (see fold_description below), no `allowed-tools` line, then the body verbatim
      (including its leading blank line after the closing `---`).

  fold_description(description: str, width: int = 95) -> str
      Pure function. Returns the frontmatter fragment for a folded description: the literal line
      `description: >` followed by the description word-wrapped to `width` columns, each wrapped
      line indented two spaces. (textwrap.wrap with break_long_words=False,
      break_on_hyphens=False reproduces this exactly — see _fold_description_reference below,
      which this test uses to build its own expectations rather than hand-typing wrapped text.)

  discover_slugs(claude_skills_dir: Path, registry: list[str]) -> list[str]
      Returns the slugs that are in BOTH `registry` and are directories under
      `claude_skills_dir` containing a SKILL.md — i.e. the intersection, preserving no particular
      order requirement (this test sorts before comparing).

  run(root: Path, check: bool = False, registry: list[str] | None = None) -> dict[str, str]
      root is a directory containing .claude/skills/ and .agents/skills/ (a real repo root, or a
      tempfile.mkdtemp() tree shaped like one in these tests — NEVER the real repo in this test
      file). registry defaults to sync_downstream_harness.AGENT_SKILL_SLUGS when None.
      For every slug in discover_slugs(root/.claude/skills, registry): compute the mirror
      content and compare it to root/.agents/skills/<slug>/SKILL.md's current bytes (missing
      file counts as different). If different and check is False, write it. Returns a dict
      mapping slug -> one of "generated" (written or would-be-written and changed),
      "unchanged" (already matched), "skipped-no-source" (registry slug, no .claude/ source —
      untouched). A .claude/ skill directory NOT in the registry is invisible to run() entirely:
      it is not a key in the returned dict and nothing under .agents/skills/ is touched for it.
      When check is True, nothing is ever written to disk regardless of status.

Run: python3 scripts/test_generate_skill_surfaces.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent / "generate_skill_surfaces.py"
_spec = importlib.util.spec_from_file_location("generate_skill_surfaces", _MODULE_PATH)
gen = importlib.util.module_from_spec(_spec)
sys.modules["generate_skill_surfaces"] = gen
_spec.loader.exec_module(gen)


def _fold_description_reference(description: str, width: int = 95) -> str:
    """The reference folding algorithm this test's expectations are built from.
    scripts/generate_skill_surfaces.py's fold_description must reproduce this line-for-line."""
    wrapped = textwrap.wrap(description, width=width, break_long_words=False,
                             break_on_hyphens=False)
    lines = ["description: >"]
    for line in wrapped:
        lines.append("  " + line)
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# A description long enough to force wrapping under fold_description's default width, so the
# fixture actually exercises folding rather than accidentally fitting on one line.
_LONG_DESCRIPTION = (
    "How to use this fixture skill for the generator's contract test — it exists only to prove "
    "the frontmatter transform, never to document anything real, and it is deliberately long "
    "enough that folding it at ninety-five columns produces more than one wrapped line so the "
    "test actually exercises the wrap, not just the presence of the folded header."
)

_CLAUDE_SOURCE = (
    "---\n"
    "name: fixture-mirrored\n"
    f"description: {_LONG_DESCRIPTION}\n"
    "allowed-tools: Bash(mev:*) Bash(python3:*)\n"
    "---\n"
    "\n"
    "# Fixture mirrored skill\n"
    "\n"
    "This body mentions `CLAUDE.md` and `.claude/skills/` on purpose — both are literal path\n"
    "strings the mirror must carry through UNCHANGED, never rewritten to an `.agents/` "
    "equivalent.\n"
)


def _expected_mirror(claude_source: str, description: str) -> str:
    """Build the expected mirror content the same way compute_mirror_content is contracted to:
    name verbatim, description folded, allowed-tools dropped, body verbatim."""
    body_start = claude_source.index("---\n", claude_source.index("---\n") + 4) + len("---\n")
    body = claude_source[body_start:]
    return (
        "---\n"
        "name: fixture-mirrored\n"
        + _fold_description_reference(description)
        + "---\n"
        + body
    )


class ComputeMirrorContent(unittest.TestCase):
    """Case (a) + case (b): the pure per-file transform."""

    def test_name_verbatim_description_folded_allowed_tools_dropped(self):
        actual = gen.compute_mirror_content(_CLAUDE_SOURCE)
        expected = _expected_mirror(_CLAUDE_SOURCE, _LONG_DESCRIPTION)
        self.assertEqual(actual, expected)
        self.assertNotIn("allowed-tools", actual)
        self.assertIn("description: >", actual)

    def test_literal_claude_paths_in_body_survive_unchanged(self):
        """The substitution trap the block record warns about: every 'claude' string in a
        mirrored body is a literal path or filename, never a word to rewrite."""
        actual = gen.compute_mirror_content(_CLAUDE_SOURCE)
        self.assertIn("`CLAUDE.md`", actual)
        self.assertIn("`.claude/skills/`", actual)


class Discovery(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gen-skill-surfaces-discover-"))

    def test_intersection_of_registry_and_claude_skills_dirs(self):
        claude_skills = self.tmp / ".claude" / "skills"
        _write(claude_skills / "in-both" / "SKILL.md", _CLAUDE_SOURCE)
        _write(claude_skills / "claude-only" / "SKILL.md", _CLAUDE_SOURCE)
        # "registry-only" is in the registry below but has no .claude/skills/ dir at all.
        registry = ["in-both", "registry-only"]
        slugs = sorted(gen.discover_slugs(claude_skills, registry))
        self.assertEqual(slugs, ["in-both"])


class Run(unittest.TestCase):
    """Cases (c) and (d), plus the end-to-end generated/unchanged/skipped-no-source contract,
    all against a tempfile.mkdtemp() tree — never the repo's real .claude/skills/ or
    .agents/skills/."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gen-skill-surfaces-run-"))
        self.claude_skills = self.tmp / ".claude" / "skills"
        self.agent_skills = self.tmp / ".agents" / "skills"

    def test_case_a_generated_for_a_mirrored_slug(self):
        _write(self.claude_skills / "fixture-mirrored" / "SKILL.md", _CLAUDE_SOURCE)
        statuses = gen.run(self.tmp, check=False, registry=["fixture-mirrored"])
        self.assertEqual(statuses["fixture-mirrored"], "generated")
        written = (self.agent_skills / "fixture-mirrored" / "SKILL.md").read_text()
        self.assertEqual(written, _expected_mirror(_CLAUDE_SOURCE, _LONG_DESCRIPTION))

    def test_rerun_is_unchanged(self):
        _write(self.claude_skills / "fixture-mirrored" / "SKILL.md", _CLAUDE_SOURCE)
        gen.run(self.tmp, check=False, registry=["fixture-mirrored"])
        statuses = gen.run(self.tmp, check=False, registry=["fixture-mirrored"])
        self.assertEqual(statuses["fixture-mirrored"], "unchanged")

    def test_case_c_registry_slug_with_no_source_is_skipped_and_untouched(self):
        """The sdlc-task/sdlc-flow protection: a registry slug with NO .claude/skills/ source
        must be left completely alone. Asserted on the file's bytes before and after, not merely
        on the absence of an exception."""
        existing = (
            "---\n"
            "name: fixture-guide-only\n"
            "description: Hand-authored replication guide, never generated.\n"
            "---\n"
            "\n"
            "# Fixture guide-only skill\n"
            "\n"
            "This file has no .claude/skills/ counterpart and must never be overwritten.\n"
        )
        target = self.agent_skills / "fixture-guide-only" / "SKILL.md"
        _write(target, existing)
        before = target.read_bytes()

        statuses = gen.run(self.tmp, check=False, registry=["fixture-guide-only"])

        after = target.read_bytes()
        self.assertEqual(before, after,
                          "a registry slug with no .claude/ source must leave its .agents/ file "
                          "byte-for-byte unchanged (the sdlc-task/sdlc-flow shape)")
        self.assertEqual(statuses["fixture-guide-only"], "skipped-no-source")

    def test_case_d_claude_only_skill_absent_from_registry_generates_nothing(self):
        """The epic/write-operating-doc shape: a .claude/skills/ dir that is not in the registry
        must not gain a mirror, and must not even appear in run()'s result."""
        _write(self.claude_skills / "fixture-claude-only" / "SKILL.md", _CLAUDE_SOURCE)
        statuses = gen.run(self.tmp, check=False, registry=["some-other-slug"])
        self.assertNotIn("fixture-claude-only", statuses)
        self.assertFalse((self.agent_skills / "fixture-claude-only").exists())

    def test_check_mode_writes_nothing_and_reports_generated(self):
        _write(self.claude_skills / "fixture-mirrored" / "SKILL.md", _CLAUDE_SOURCE)
        statuses = gen.run(self.tmp, check=True, registry=["fixture-mirrored"])
        self.assertEqual(statuses["fixture-mirrored"], "generated")
        self.assertFalse((self.agent_skills / "fixture-mirrored" / "SKILL.md").exists(),
                          "--check must never write to disk")

    def test_check_mode_reports_unchanged_once_generated(self):
        _write(self.claude_skills / "fixture-mirrored" / "SKILL.md", _CLAUDE_SOURCE)
        gen.run(self.tmp, check=False, registry=["fixture-mirrored"])
        statuses = gen.run(self.tmp, check=True, registry=["fixture-mirrored"])
        self.assertEqual(statuses["fixture-mirrored"], "unchanged")


if __name__ == "__main__":
    unittest.main(verbosity=2)
