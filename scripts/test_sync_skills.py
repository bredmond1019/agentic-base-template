#!/usr/bin/env python3
"""Fixture tests for sync_skills.py and sync_all_skills_commands.py.

Registered in planning/harness.json as `sync-skills-tests`. Three defects are pinned here,
each of which shipped and cost real work (BT.chore.harness-sync-sharp-edges):

  1. IDEMPOTENCY. sync_workflow_skills() reads its own previous output back out of the file,
     so an unstripped guide grew sdlc-task/SKILL.md and sdlc-flow/SKILL.md by two blank lines
     on every run - forever. Both files were therefore dirty after every "successful" sync,
     and no freshness check could be built on the script: it would report drift immediately
     after a clean sync.
  2. ARGV. Neither script parsed arguments at all. Invoking either with an unrecognised flag
     - including --help - ran a full fleet sync. On 2026-09-02 that produced 1,329 unreviewed
     insertions across base-template, HQ and five tier sub-brains, reverted by hand.
  3. THE EXCLUSION GUARD. sync_command_skills() must not mirror files in .claude/commands/
     that are not commands: the two directory READMEs and the four test_* E2E templates.
     The guard exists and is correct; it had no test, so nothing stopped an edit dropping it.

These run against a throwaway tree in tmp. Nothing here touches the real fleet, the global
installs, or the user's home directory.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SYNC_SKILLS = REPO / ".agents/skills/sync-skills/scripts/sync_skills.py"
SYNC_ALL = REPO / "scripts/sync_all_skills_commands.py"


def load_module(path):
    spec = importlib.util.spec_from_file_location("sync_skills_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ExclusionGuardTests(unittest.TestCase):
    """Defect 3 — the six non-commands must never become skills."""

    NOT_COMMANDS = [
        "README.md",
        "e2e-templates-README.md",
        "test_auth_gate.md",
        "test_crud_api.md",
        "test_error_handling.md",
        "test_ui_form.md",
    ]

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.commands = self.tmp / "commands"
        self.skills = self.tmp / "skills"
        self.commands.mkdir()
        for name in self.NOT_COMMANDS:
            (self.commands / name).write_text("# not a command\n\nbody\n", encoding="utf-8")
        (self.commands / "real-command.md").write_text(
            "---\ndescription: A real command\n---\n\n# Real\n\nbody\n", encoding="utf-8"
        )
        self.mod = load_module(SYNC_SKILLS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_non_commands_produce_no_mirror(self):
        self.mod.sync_command_skills(str(self.skills), str(self.commands))
        for name in self.NOT_COMMANDS:
            slug = name[:-3]
            self.assertFalse(
                (self.skills / slug).exists(),
                f"{name} must not be mirrored as a skill - the guard at sync_skills.py's "
                f"sync_command_skills() loop head was dropped or narrowed",
            )

    def test_a_real_command_is_mirrored(self):
        """Positive control: without this, the test above passes if NOTHING is ever mirrored."""
        self.mod.sync_command_skills(str(self.skills), str(self.commands))
        self.assertTrue(
            (self.skills / "real-command" / "SKILL.md").is_file(),
            "a normal command must still produce a mirror",
        )


class ArgvTests(unittest.TestCase):
    """Defect 2 — an unrecognised flag must exit non-zero and sync nothing."""

    def _run(self, script, *args):
        return subprocess.run(
            [sys.executable, str(script), *args],
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )

    def test_sync_skills_rejects_unknown_flag(self):
        r = self._run(SYNC_SKILLS, "--definitely-not-a-flag")
        self.assertEqual(r.returncode, 2, "argparse must reject an unknown flag")
        self.assertIn("unrecognized arguments", r.stderr)

    def test_sync_all_rejects_unknown_flag(self):
        r = self._run(SYNC_ALL, "--definitely-not-a-flag")
        self.assertEqual(r.returncode, 2, "argparse must reject an unknown flag")
        self.assertIn("unrecognized arguments", r.stderr)

    def test_help_does_not_sync(self):
        """--help was the exact invocation that ran a 1,329-insertion fleet sync."""
        for script in (SYNC_SKILLS, SYNC_ALL):
            r = self._run(script, "--help")
            self.assertEqual(r.returncode, 0, f"{script.name} --help must succeed")
            self.assertIn("usage:", r.stdout)
            self.assertNotIn("Syncing command skills", r.stdout)
            self.assertNotIn("Syncing global commands", r.stdout)


class IdempotencyTests(unittest.TestCase):
    """Defect 1 — a second run against an unchanged source must change nothing."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.skills = self.tmp / "skills"
        self.workflows = self.tmp / "workflows"
        self.workflows.mkdir()
        # A minimal engine file: sync_workflow_skills reads the leading // comment block.
        (self.workflows / "sdlc-task.js").write_text(
            "// sdlc-task\n// A tiny engine header.\n\nconst x = 1;\n", encoding="utf-8"
        )
        self.mod = load_module(SYNC_SKILLS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _skill(self):
        return self.skills / "sdlc-task" / "SKILL.md"

    def test_repeated_runs_are_byte_identical(self):
        self.mod.sync_workflow_skills(str(self.skills), str(self.workflows))
        first = self._skill().read_bytes()

        # Seed a guide section, as the real files carry, then re-run twice. This is the
        # path that grew: the guide is read back out of the file the function itself wrote.
        self._skill().write_bytes(
            first.rstrip() + b"\n\n## Antigravity Execution Guide\n\nDo the thing.\n"
        )
        self.mod.sync_workflow_skills(str(self.skills), str(self.workflows))
        second = self._skill().read_bytes()
        self.mod.sync_workflow_skills(str(self.skills), str(self.workflows))
        third = self._skill().read_bytes()

        self.assertEqual(
            second,
            third,
            "sync_workflow_skills is not idempotent: a second run against an unchanged "
            "source changed the file. The guide must be rstrip()ed before re-emission.",
        )

    def test_guide_is_preserved_across_runs(self):
        """Positive control: idempotency is trivial if the guide is simply dropped."""
        self.mod.sync_workflow_skills(str(self.skills), str(self.workflows))
        self._skill().write_bytes(
            self._skill().read_bytes().rstrip()
            + b"\n\n## Antigravity Execution Guide\n\nDo the thing.\n"
        )
        self.mod.sync_workflow_skills(str(self.skills), str(self.workflows))
        self.assertIn("## Antigravity Execution Guide", self._skill().read_text(encoding="utf-8"))
        self.assertIn("Do the thing.", self._skill().read_text(encoding="utf-8"))


class GlobalTargetTests(unittest.TestCase):
    """The ~/agentic-portfolio orphan must not come back."""

    def test_no_bare_home_target(self):
        src = SYNC_SKILLS.read_text(encoding="utf-8")
        self.assertNotIn(
            'expanduser("~/agentic-portfolio")',
            src,
            "sync_skills.py must not write to ~/agentic-portfolio - a bare home directory "
            "nothing reads, which accumulated 66 orphaned skill folders before being caught",
        )

    def test_hand_authored_filter_exists(self):
        """The copy into the HQ brain root must be filtered to hand-authored skills only.

        Copying every .agents/skills entry would overwrite HQ's OWN command mirrors with
        base-template's - the D54 overwrite that sync_downstream_harness.py's engines_only
        flag exists to prevent.
        """
        src = SYNC_SKILLS.read_text(encoding="utf-8")
        self.assertIn("copy_hand_authored_skills", src)
        self.assertIn("base-template/.claude/skills", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
