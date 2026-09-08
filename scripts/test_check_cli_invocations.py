#!/usr/bin/env python3
"""Fixture suite for check_cli_invocations.py (BT.3.H).

Builds a throwaway repo tree (a .claude/commands/*.md file per case) and runs the checker against
it directly via its importable functions, rather than shelling the real corpus -- keeps the suite
independent of whatever this repo's live .claude/.agents/ content happens to contain.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_cli_invocations as cci  # noqa: E402


def make_repo(tmp: Path, content: str) -> Path:
    cmds = tmp / ".claude" / "commands"
    cmds.mkdir(parents=True)
    (cmds / "example.md").write_text(content, encoding="utf-8")
    return tmp


class TestCheckCliInvocations(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mev_verbs = cci.get_verbs("mev")
        self.bastion_verbs = cci.get_verbs("bastion")
        if self.mev_verbs is None or self.bastion_verbs is None:
            self.skipTest("mev/bastion not on PATH -- cannot run against the real binaries")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self, content: str) -> int:
        make_repo(self.tmp, content)
        return cci.check(self.tmp, quiet=True)

    def test_real_verb_passes(self):
        self.assertEqual(self.run_check("Run `mev frontier` to see the frontier.\n"), 0)

    def test_bad_verb_fails(self):
        self.assertEqual(
            self.run_check("Run `mev lane-frontier --repo engine-rs` to see the frontier.\n"), 1
        )

    def test_bad_flag_on_flag_checked_verb_fails(self):
        self.assertEqual(
            self.run_check("```\nbastion validate-brain --okf-structure\n```\n"), 1
        )

    def test_real_flag_on_flag_checked_verb_passes(self):
        self.assertEqual(
            self.run_check("```\nbastion validate-brain --structure\n```\n"), 0
        )

    def test_piped_invocation_passes(self):
        self.assertEqual(self.run_check("`mev frontier | grep engine-rs`\n"), 0)

    def test_midsentence_prose_is_not_flagged(self):
        # D68 negative proof for the false-positive class this checker's first draft produced:
        # "mev"/"bastion" as a plain-English subject mid-line inside a code span/fence, not as an
        # invocation -- the real corpus instances that motivated the line/span-start anchor were
        # `"notes": "Exclusive against mev because this block writes..."` (mid-JSON-value, inside
        # a fenced block) and `print('...mev not on PATH...')` (mid Python string literal).
        content = (
            "```\n"
            "  \"notes\": \"Exclusive against mev because this block writes planning/harness.json\"\n"
            "  print('UNVALIDATED: mev not on PATH -- schema check skipped')\n"
            "```\n"
        )
        self.assertEqual(self.run_check(content), 0)

    def test_binary_as_first_word_of_real_sentence_is_flagged(self):
        # The anchor is necessarily blunt: if "mev"/"bastion" IS the first token of a line/span,
        # this checker treats it as an invocation even in a hypothetical case like `mev refuses
        # to...` (a sentence that happens to start that way). This is the documented tradeoff
        # (module docstring), not a bug -- pin it here so a future "fix" doesn't quietly widen
        # the anchor and reintroduce the false-positive class test_midsentence_prose_is_not_flagged
        # guards against.
        self.assertEqual(self.run_check("`mev refuses to start without a lock`\n"), 1)

    def test_bastion_brain_real_flag_passes(self):
        self.assertEqual(
            self.run_check("`bastion brain --dependents X`\n"), 0
        )

    def test_bastion_brain_bad_flag_fails(self):
        self.assertEqual(
            self.run_check("`bastion brain --depends-on X`\n"), 1
        )

    def test_unchecked_verb_flags_are_not_flagged(self):
        # frontier is a real verb but not in FLAG_CHECKED_VERBS -- an invented flag on it must not
        # be flagged, since this gate deliberately does not cover every verb's flags (see module
        # docstring). Extending coverage is a follow-up, not a bug in this test.
        self.assertEqual(self.run_check("`mev frontier --nonexistent-flag`\n"), 0)


if __name__ == "__main__":
    unittest.main()
