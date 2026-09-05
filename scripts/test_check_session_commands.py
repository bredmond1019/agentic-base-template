#!/usr/bin/env python3
"""Fixture tests for check_session_commands.py — the gate keeping the four session commands one source.

Registered as `session-commands-tests`. The checker it covers GATES, so a regression in it does not
fail loudly: it stops enforcing, and handoff/wrap-up/log-work/begin-session quietly re-fork the way
they had three times over before 2026-09-04. A fork is only discoverable by diffing files nobody
diffs, so this checker is the only thing that would ever find the next one.

`test_a_missing_tier_source_is_not_agreement` is the one that matters most: "absent" and "identical"
are different answers, and treating a missing commands/brain/ source as agreement would let the five
tiers keep whatever stale copy they already hold while the gate reported green.
"""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_session_commands.py"
_spec = importlib.util.spec_from_file_location("check_session_commands", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class SessionCommandsTests(unittest.TestCase):
    def test_the_command_list_is_the_four_depth_agnostic_ones(self):
        self.assertEqual(
            sorted(mod.SESSION_COMMANDS),
            ["begin-session.md", "handoff.md", "log-work.md", "wrap-up.md"],
        )

    def test_begin_session_is_tier_exempt(self):
        """It is not a tier command; a missing tier copy of it is correct, not drift."""
        self.assertIn("begin-session.md", mod.TIER_EXEMPT)

    def test_tier_exempt_is_a_subset_of_the_command_list(self):
        """An exemption for a command not being checked would be silently meaningless."""
        self.assertTrue(mod.TIER_EXEMPT <= set(mod.SESSION_COMMANDS))

    def test_brain_root_walks_up_and_returns_none_outside_a_brain(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            deep = tmp / "a" / "b"
            deep.mkdir(parents=True)
            self.assertIsNone(mod.brain_root(deep), "no brain.toml above — must be None, not a guess")
            (tmp / "brain.toml").write_text("# brain.toml\n", encoding="utf-8")
            self.assertEqual(mod.brain_root(deep), tmp.resolve())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_real_repo_is_currently_in_sync(self):
        """Positive control: every case above would pass on a checker that never looks at disk."""
        self.assertEqual(mod.main.__module__, "check_session_commands")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            import sys
            argv = sys.argv
            sys.argv = ["check_session_commands.py", "--quiet"]
            try:
                rc = mod.main()
            finally:
                sys.argv = argv
        self.assertEqual(rc, 0, f"the live check should be green here; output was:\n{buf.getvalue()}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
