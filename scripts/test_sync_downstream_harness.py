#!/usr/bin/env python3
"""Regression tests for sync_downstream_harness.py's engines-only guard (D54).

The guard exists because HQ authors its own brain-specific commands under names that
base-template also ships — /prime, /log-work, /handoff, /capture and 8 others. Since the sync
script only ever adds/updates and never deletes, a regression here would overwrite all twelve
and report it as a routine "changed" line in a 17-repo run. These tests fail loudly instead.

Run: python3 scripts/test_sync_downstream_harness.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent / "sync_downstream_harness.py"
_spec = importlib.util.spec_from_file_location("sync_downstream_harness", _MODULE_PATH)
sync = importlib.util.module_from_spec(_spec)
sys.modules["sync_downstream_harness"] = sync
_spec.loader.exec_module(sync)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class EnginesOnlyGuard(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = Path(self._tmp.name) / "brain"
        self.bt = self.brain / "base-template"
        self.leaf = self.brain / "core" / "leaf"

        # base-template: the source of truth for the harness.
        _write(self.bt / "scripts" / "sync_downstream_harness.py", "# anchor\n")
        _write(self.bt / ".claude" / "commands" / "prime.md", "base-template's generic prime\n")
        _write(self.bt / ".claude" / "commands" / "log-work.md", "base-template's generic log-work\n")
        _write(
            self.bt / ".claude" / "commands" / "generate-roadmap.md",
            "authors a roadmap spanning repos; HQ-only, single-copy\n",
        )
        _write(self.bt / ".claude" / "workflows" / "sdlc-task.js", "// engine\n")
        _write(self.bt / ".claude" / "workflows" / "harness.schema.json", "{}\n")
        _write(self.bt / ".claude" / "workflows" / "templates" / "t.md", "template\n")

        # HQ (brain root) — has workflows, and its OWN commands that differ.
        _write(self.brain / ".claude" / "commands" / "prime.md", "HQ's 164-line brain prime\n")
        _write(self.brain / ".claude" / "commands" / "log-work.md", "HQ's cross-repo sync log-work\n")
        _write(self.brain / ".claude" / "workflows" / "sdlc-task.js", "// engine\n")

        # A normal downstream leaf repo — should still receive commands.
        _write(self.leaf / ".claude" / "commands" / "prime.md", "stale copy\n")
        _write(self.leaf / ".claude" / "workflows" / "sdlc-task.js", "// engine\n")

        _write(
            self.brain / "brain.toml",
            '# brain.toml\n'
            '[[repos]]\nslug = "brain"\nrepo_path = "."\n\n'
            '[[repos]]\nslug = "base-template"\nrepo_path = "base-template"\n\n'
            '[[repos]]\nslug = "leaf"\nrepo_path = "core/leaf"\n',
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _targets(self) -> dict[str, sync.RepoTarget]:
        found = sync.discover_targets(self.brain.resolve(), self.bt.resolve())
        return {t.slug: t for t in found}

    def test_brain_root_is_marked_engines_only(self):
        self.assertTrue(self._targets()["brain"].engines_only)

    def test_leaf_repo_is_not_engines_only(self):
        self.assertFalse(self._targets()["leaf"].engines_only)

    def test_base_template_is_never_a_target(self):
        self.assertNotIn("base-template", self._targets())

    def test_harness_files_drops_commands_when_engines_only(self):
        names = {p.name for p in sync.harness_files(self.bt, engines_only=True)}
        self.assertNotIn("prime.md", names)
        self.assertNotIn("log-work.md", names)

    def test_harness_files_keeps_engines_when_engines_only(self):
        names = {p.name for p in sync.harness_files(self.bt, engines_only=True)}
        self.assertIn("sdlc-task.js", names)
        self.assertIn("harness.schema.json", names)
        self.assertIn("t.md", names)

    def test_harness_files_includes_commands_by_default(self):
        names = {p.name for p in sync.harness_files(self.bt)}
        self.assertIn("prime.md", names)

    def test_workflows_md_syncs_to_every_target_including_engines_only(self):
        """workflows/*.md are shared procedures the commands include by reference.

        block-registration.md is read by /plan, /ticket and /chore instead of each carrying
        its own copy (D65). If it were gated on engines_only, HQ's producers would point at
        a file that does not exist there — and HQ runs real SDLC work (D63). Same rule as
        workflows/*.js: mechanism, never gated.
        """
        _write(self.bt / ".claude" / "workflows" / "block-registration.md", "shared proc\n")
        for engines_only in (False, True):
            names = {p.name for p in sync.harness_files(self.bt, engines_only=engines_only)}
            self.assertIn("block-registration.md", names,
                          f"missing with engines_only={engines_only}")

    def test_invoked_scripts_sync_but_base_template_own_tooling_does_not(self):
        """Only scripts a downstream command actually invokes propagate.

        /ticket, /chore and /generate-tasks shell out to render_spec.py; without it they fail
        at their render step in every scaffolded repo. The rest of scripts/ is base-template's
        own gate and test tooling — project fact, and propagating it would drop dead checks
        into 17 repos.
        """
        _write(self.bt / "scripts" / "render_spec.py", "# renderer\n")
        _write(self.bt / "scripts" / "test_sync_downstream_harness.py", "# own tooling\n")
        for engines_only in (False, True):
            names = {p.name for p in sync.harness_files(self.bt, engines_only=engines_only)}
            self.assertIn("render_spec.py", names,
                          f"missing with engines_only={engines_only}")
            self.assertNotIn("test_sync_downstream_harness.py", names,
                             "base-template's own tooling must never propagate")

    def test_harness_files_excludes_generate_roadmap_for_any_target(self):
        """generate-roadmap.md is HQ-only by nature (Step 1A: 'this command runs at HQ') and
        stays single-copy at base-template — excluded regardless of engines_only, unlike
        prime.md/log-work.md which sync everywhere except the brain root."""
        self.assertNotIn(
            "generate-roadmap.md", {p.name for p in sync.harness_files(self.bt, engines_only=False)}
        )
        self.assertNotIn(
            "generate-roadmap.md", {p.name for p in sync.harness_files(self.bt, engines_only=True)}
        )

    def test_diff_reports_no_generate_roadmap_for_a_leaf_repo(self):
        report = sync.diff_repo(self.bt.resolve(), self.leaf.resolve(), self._targets()["leaf"])
        self.assertIsNone(report.error)
        rel_paths = [d.rel_path for d in report.diffs]
        self.assertNotIn("commands/generate-roadmap.md", rel_paths)

    def test_diff_reports_no_command_changes_for_the_brain_root(self):
        """The end-to-end guarantee: HQ's differing commands never appear as a diff."""
        report = sync.diff_repo(self.bt.resolve(), self.brain.resolve(), self._targets()["brain"])
        self.assertIsNone(report.error)
        changed = [d.rel_path for d in report.diffs if d.dest_prefix == ".claude"]
        self.assertEqual(
            [c for c in changed if "commands" in c],
            [],
            f"HQ commands would be overwritten: {changed}",
        )

    def test_diff_still_reports_command_changes_for_a_normal_repo(self):
        """The guard must be selective — proving the test above isn't passing vacuously."""
        report = sync.diff_repo(self.bt.resolve(), self.brain.resolve(), self._targets()["leaf"])
        changed = [d.rel_path for d in report.diffs if d.dest_prefix == ".claude"]
        self.assertTrue(
            any("commands" in c and "prime.md" in c for c in changed),
            f"expected leaf to receive prime.md, got {changed}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
