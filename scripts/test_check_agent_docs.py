#!/usr/bin/env python3
"""Fixture tests for check_agent_docs.py — the gate over the AGENTS.md/CLAUDE.md/GEMINI.md split.

Registered in planning/harness.json as `agent-docs-tests`. The checker it covers GATES, so a
regression in it does not fail loudly — it silently stops enforcing, and the split it protects
drifts exactly the way the pre-split files did (session-continuity forked four ways,
response-style twice).

The case that matters most is `test_dangling_import_is_caught`. Measured 2026-09-03 on Claude
Code 2.1.259: a `@AGENTS.md` import pointing at a missing file produces NO error and NO warning
at runtime — the session just loses every shared convention while looking completely normal.
This checker is the only thing that would ever tell you, so a regression that stops detecting it
is invisible twice over.

Each test builds a throwaway repo in tmp. Nothing here touches the real fleet.
"""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_agent_docs.py"
_spec = importlib.util.spec_from_file_location("check_agent_docs", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

BANNER = "> **GENERATED FILE — do not edit by hand.**\n"
SHARED = "# AGENTS.md — test\n\nSome shared, surface-neutral guidance.\n\n"
TAIL = "## Fleet & Core Skills\n\n| Skill | Focus |\n|---|---|\n"


def build(root, *, agents=SHARED, claude="# CLAUDE.md — test\n\n@AGENTS.md\n",
          gemini=None, agent_singular=None):
    if agents is not None:
        (root / "AGENTS.md").write_text(agents, encoding="utf-8")
    if claude is not None:
        (root / "CLAUDE.md").write_text(claude, encoding="utf-8")
    if gemini is None and agents is not None:
        gemini = agents.replace("# AGENTS.md", "# GEMINI.md", 1) + "\n" + BANNER + "\n" + TAIL
    if gemini is not None:
        (root / "GEMINI.md").write_text(gemini, encoding="utf-8")
    if agent_singular is not None:
        (root / "AGENT.md").write_text(agent_singular, encoding="utf-8")


class CheckAgentDocsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check(self):
        return mod.check(self.tmp, quiet=True)

    # --- the positive control -------------------------------------------------
    def test_a_correct_repo_passes(self):
        """Without this, every test below would pass on a checker that flags everything."""
        build(self.tmp)
        self.assertEqual(self.check(), [], "a correctly-split repo must produce no problems")

    # --- the four things it must catch ---------------------------------------
    def test_missing_import_is_caught(self):
        build(self.tmp, claude="# CLAUDE.md — test\n\nNo import here.\n")
        self.assertTrue(any("no '@AGENTS.md' import" in p for p in self.check()))

    def test_dangling_import_is_caught(self):
        """The silent-failure case: the import line is present, the target is not."""
        build(self.tmp)
        (self.tmp / "AGENTS.md").unlink()
        problems = self.check()
        self.assertTrue(
            any("does not exist" in p for p in problems),
            "a @AGENTS.md import with no target must be caught — it fails silently at runtime",
        )

    def test_tool_specific_path_in_agents_is_caught(self):
        build(self.tmp, agents=SHARED + "See `.claude/skills/foo/SKILL.md` for details.\n")
        self.assertTrue(any("surface-neutral" in p for p in self.check()))

    def test_gemini_drift_is_caught(self):
        build(self.tmp)
        g = (self.tmp / "GEMINI.md")
        g.write_text(g.read_text(encoding="utf-8").replace("shared, surface-neutral",
                                                           "HAND EDITED"), encoding="utf-8")
        self.assertTrue(any("drifted from AGENTS.md" in p for p in self.check()))

    def test_missing_generated_banner_is_caught(self):
        build(self.tmp)
        g = (self.tmp / "GEMINI.md")
        g.write_text(g.read_text(encoding="utf-8").replace(BANNER, ""), encoding="utf-8")
        self.assertTrue(any("generated-file banner" in p for p in self.check()))

    def test_singular_agent_md_is_caught(self):
        build(self.tmp, agent_singular="# AGENT.md\n\nstale\n")
        self.assertTrue(any("was retired" in p for p in self.check()))

    # --- the allowlist -------------------------------------------------------
    def test_allowlisted_mention_is_permitted(self):
        """A tool-specific path used as a FACT both readers need, not an instruction."""
        line = "the engine snapshot lives at `~/.claude/projects/<proj>/...` — see rule 10.\n"
        self.assertTrue(any(a in line for a in mod.ALLOWED_SURFACE_MENTIONS),
                        "fixture must actually exercise the allowlist")
        build(self.tmp, agents=SHARED + line)
        self.assertEqual(self.check(), [])

    def test_allowlist_entries_all_carry_a_reason(self):
        """An entry with no reason is a shrug; the point is that adding one is a decision."""
        for token, reason in mod.ALLOWED_SURFACE_MENTIONS.items():
            self.assertTrue(reason and len(reason) > 40,
                            f"allowlist entry {token!r} needs a real reason, got {reason!r}")

    # --- a repo with no CLAUDE.md at all -------------------------------------
    def test_repo_without_claude_md_is_reported(self):
        build(self.tmp, claude=None)
        self.assertTrue(any("no CLAUDE.md" in p for p in self.check()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
