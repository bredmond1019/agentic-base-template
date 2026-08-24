#!/usr/bin/env python3
"""Regression tests for sync_downstream_harness.py's engines-only guard (D54) and its skill
slug registration (CLAUDE_SKILL_SLUGS / AGENT_SKILL_SLUGS).

The guard exists because HQ authors its own brain-specific commands under names that
base-template also ships — /prime, /log-work, /handoff, /capture and 8 others. Since the sync
script only ever adds/updates and never deletes, a regression here would overwrite all twelve
and report it as a routine "changed" line in a 17-repo run. These tests fail loudly instead.

SkillSlugRegistrationGuard below covers the other failure mode: CLAUDE_SKILL_SLUGS and
AGENT_SKILL_SLUGS are hand-enumerated (deliberately — see their own docstrings), so a skill
authored but not registered, or registered but never authored, is a silent no-op on the next
17-repo sync. Each of its four cases was shown capable of failing before this suite existed to
catch it (D68):

  - Case A (a known slug present in both lists): at commit 1e3f822 (the parent of the commit
    that registered notify-operator), loading that revision's sync_downstream_harness.py in
    isolation and checking `"notify-operator" in CLAUDE_SKILL_SLUGS` returned False, and the
    AGENT_SKILL_SLUGS check returned False too — confirmed 2026-08-24 by importing the historical
    file directly, not by inspection.
  - Case B (every registered slug has its file): exercised by hand against a scratch copy of the
    module with an extra slug appended to CLAUDE_SKILL_SLUGS that has no matching SKILL.md on
    disk — the loop-based check in test_every_registered_slug_has_its_file raised AssertionError
    for that slug.
  - Case C (every skill directory on disk is registered or allowlisted): exercised by hand by
    creating a scratch `.claude/skills/zz-scratch-unregistered/SKILL.md` with no corresponding
    list entry — the loop-based reverse check in
    test_every_skill_directory_is_registered_or_allowlisted flagged it.
  - Case D (mirror bodies match, computed generically): MirroredSkillBodiesMatch already covers
    this over a hardcoded MIRRORED list that does not include notify-operator;
    test_mirrored_bodies_match_generically instead derives the mirrored-slug set from
    CLAUDE_SKILL_SLUGS ∩ AGENT_SKILL_SLUGS, so a newly-registered mirrored slug needs no second
    manual edit. Checked 2026-08-24: all ten currently-mirrored pairs already match byte-for-byte
    after the frontmatter block, so there is no pre-existing violation to except.

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
        _write(
            self.bt / ".claude" / "skills" / "write-okf-markdown" / "SKILL.md",
            "okf authoring guide\n",
        )
        _write(
            self.bt / ".claude" / "skills" / "edit-state-json" / "SKILL.md",
            "state.json authoring guide\n",
        )
        # Not in CLAUDE_SKILL_SLUGS — a factory-only skill must never fan out.
        _write(
            self.bt / ".claude" / "skills" / "factory-only" / "SKILL.md",
            "base-template internal\n",
        )

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

    def test_allowlisted_skills_sync_to_every_target_including_engines_only(self):
        """.claude/skills/<slug>/SKILL.md describe fleet-wide authoring mechanism, identical in
        every repo. D54's engines_only exclusion is for commands that DIVERGE per repo; skills do
        not, and the brain root needs them as much as any leaf."""
        rels = {
            str(p.relative_to(self.bt / ".claude"))
            for p in sync.harness_files(self.bt, engines_only=True)
        }
        self.assertIn("skills/write-okf-markdown/SKILL.md", rels)
        self.assertIn("skills/edit-state-json/SKILL.md", rels)

    def test_allowlisted_skills_sync_to_a_normal_repo_too(self):
        rels = {str(p.relative_to(self.bt / ".claude")) for p in sync.harness_files(self.bt)}
        self.assertIn("skills/write-okf-markdown/SKILL.md", rels)
        self.assertIn("skills/edit-state-json/SKILL.md", rels)

    def test_non_allowlisted_skill_never_syncs(self):
        """The allowlist is the whole point: a skill added to base-template for factory-internal
        reasons must not fan out to 17 repos on the next sync."""
        for engines_only in (True, False):
            rels = {
                str(p.relative_to(self.bt / ".claude"))
                for p in sync.harness_files(self.bt, engines_only=engines_only)
            }
            self.assertNotIn("skills/factory-only/SKILL.md", rels)

    def test_skills_land_under_dot_claude_with_their_slug_directory(self):
        """Regression: the destination must keep the skills/<slug>/ nesting. A flattened copy
        lands at .claude/SKILL.md and Claude Code never discovers it."""
        report = sync.diff_repo(self.bt.resolve(), self.brain.resolve(), self._targets()["leaf"])
        entry = next(
            d for d in report.diffs if d.rel_path.endswith("write-okf-markdown/SKILL.md")
        )
        self.assertEqual(entry.dest_prefix, ".claude")
        self.assertEqual(entry.rel_path, "skills/write-okf-markdown/SKILL.md")
        self.assertEqual(entry.status, "new")

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

        check_block_records.py is the interim block-record gate a downstream command runs, so it
        must reach every scaffolded repo. The rest of scripts/ is base-template's own gate and
        test tooling — project fact, and propagating it would drop dead checks into 17 repos.

        render_spec.py is asserted ABSENT, not present: BT.ticket.engines-read-block-record
        deleted it on 2026-08-20 when the engines moved to reading the block record directly, so
        /ticket, /chore and /generate-tasks no longer have a render step. Shipping a renderer that
        no longer exists to 17 repos would be the drift this whole list exists to prevent.
        """
        _write(self.bt / "scripts" / "check_block_records.py", "# block-record gate\n")
        _write(self.bt / "scripts" / "render_spec.py", "# retired renderer\n")
        _write(self.bt / "scripts" / "test_sync_downstream_harness.py", "# own tooling\n")
        for engines_only in (False, True):
            names = {p.name for p in sync.harness_files(self.bt, engines_only=engines_only)}
            self.assertIn("check_block_records.py", names,
                          f"missing with engines_only={engines_only}")
            self.assertNotIn("render_spec.py", names,
                             "the retired renderer must not propagate, even if a stale copy "
                             "still sits in base-template's scripts/")
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


class MirroredSkillBodiesMatch(unittest.TestCase):
    """Repo invariant, not a fixture test: the .agents/skills mirrors of the .claude/skills
    authoring guides must stay body-identical to their source.

    The mirror exists for the vendor-neutral surface and differs ONLY in frontmatter (folded
    `description:`, no `allowed-tools:`). It was made by hand because the usual mirror transform is
    a blind word substitution, and every "claude" string in these bodies is a literal path or
    filename - `CLAUDE.md` in the corpus-membership rule, `.claude` in skip_dirs. Substituting them
    makes the documented rules false. This test is what catches that."""

    MIRRORED = [
        "report-to-the-operator",
        "write-okf-markdown",
        "edit-state-json",
        "commit-in-this-fleet",
        "derive-state-safely",
        "run-the-gates",
        "ping-agent",
        "stop-or-continue",
        "write-repo-doc",
    ]

    def _body(self, path: Path) -> str:
        return path.read_text(encoding="utf-8").split("---", 2)[2]

    def test_agents_mirror_body_matches_claude_source(self):
        root = Path(sync.__file__).resolve().parent.parent
        checked = 0
        for slug in self.MIRRORED:
            src = root / ".claude" / "skills" / slug / "SKILL.md"
            mirror = root / ".agents" / "skills" / slug / "SKILL.md"
            if not src.is_file() or not mirror.is_file():
                continue
            checked += 1
            self.assertEqual(
                self._body(src),
                self._body(mirror),
                f"{slug}: .agents mirror body has drifted from its .claude source",
            )
        self.assertEqual(checked, len(self.MIRRORED), "a mirrored skill is missing from one surface")

    def test_agents_mirror_drops_claude_only_frontmatter(self):
        root = Path(sync.__file__).resolve().parent.parent
        for slug in self.MIRRORED:
            mirror = root / ".agents" / "skills" / slug / "SKILL.md"
            if not mirror.is_file():
                continue
            fm = mirror.read_text(encoding="utf-8").split("---", 2)[1]
            self.assertNotIn("allowed-tools", fm, f"{slug}: allowed-tools is Claude-only")


class SkillSlugRegistrationGuard(unittest.TestCase):
    """Generic, list-driven checks over CLAUDE_SKILL_SLUGS / AGENT_SKILL_SLUGS — see the module
    docstring for how each case was shown capable of failing (D68)."""

    # .agents/skills/<slug> directories that are NOT registered in AGENT_SKILL_SLUGS and are
    # deliberately undistributed — factory-local tooling for base-template's OWN skill/command
    # sync process, never meant to reach the 17 scaffolded repos. Checked by hand 2026-08-24:
    # every OTHER unregistered .agents/skills/<slug> corresponds one-to-one to a
    # .claude/commands/**/<slug>.md file and is populated by a wholly separate mechanism
    # (.agents/skills/sync-skills/scripts/sync_skills.py, invoked by
    # scripts/sync_all_skills_commands.py) that mirrors commands into Gemini-style skills — out
    # of this script's remit entirely, so those are excluded from the reverse check below by
    # matching against .claude/commands rather than allowlisted one slug at a time.
    UNDISTRIBUTED_AGENT_SKILL_DIRS = {
        "compare": "base-template's own drift check between .agents/skills and .claude "
                   "commands/workflows — a tool ABOUT the sync, not a guide to be synced",
        "compare-contents": "text-diff companion to `compare`, same reason",
        "record-a-bail": "documents this repo's own bail-recording convention; not authored "
                          "for downstream distribution",
        "sync-skills": "the generator that populates .agents/skills from .claude/commands; "
                        "shipping it downstream would ship the generator, not a guide",
    }

    def setUp(self) -> None:
        self.root = Path(sync.__file__).resolve().parent.parent

    def _command_stems(self) -> set[str]:
        commands_dir = self.root / ".claude" / "commands"
        return {p.stem for p in commands_dir.rglob("*.md")}

    def test_notify_operator_is_registered_in_both_lists(self):
        """Case A."""
        self.assertIn("notify-operator", sync.CLAUDE_SKILL_SLUGS)
        self.assertIn("notify-operator", sync.AGENT_SKILL_SLUGS)

    def test_every_registered_slug_has_its_file(self):
        """Case B — a loop over both lists, not a hardcoded slug, so it also protects the
        existing nine (plus sdlc-task/sdlc-flow on the .agents side)."""
        for slug in sync.CLAUDE_SKILL_SLUGS:
            path = self.root / ".claude" / "skills" / slug / "SKILL.md"
            self.assertTrue(
                path.is_file(),
                f"CLAUDE_SKILL_SLUGS has '{slug}' but {path} is missing",
            )
        for slug in sync.AGENT_SKILL_SLUGS:
            path = self.root / ".agents" / "skills" / slug / "SKILL.md"
            self.assertTrue(
                path.is_file(),
                f"AGENT_SKILL_SLUGS has '{slug}' but {path} is missing",
            )

    def test_every_skill_directory_is_registered_or_allowlisted(self):
        """Case C — the reverse direction. A directory that is neither registered, nor a
        command mirror populated by the separate sync_skills.py process, nor named in the
        explicit UNDISTRIBUTED_AGENT_SKILL_DIRS allowlist is exactly the "authored but
        undistributed" failure this block exists to prevent."""
        claude_skills_dir = self.root / ".claude" / "skills"
        for entry in sorted(claude_skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            self.assertIn(
                entry.name,
                sync.CLAUDE_SKILL_SLUGS,
                f".claude/skills/{entry.name}/ exists but is not in CLAUDE_SKILL_SLUGS — "
                "register it or add it to an explicit allowlist",
            )

        agent_skills_dir = self.root / ".agents" / "skills"
        command_stems = self._command_stems()
        for entry in sorted(agent_skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name in sync.AGENT_SKILL_SLUGS:
                continue
            if entry.name in command_stems:
                # Populated by sync_skills.py mirroring .claude/commands/**, not by this
                # script's AGENT_SKILL_SLUGS — out of scope for this registration guard.
                continue
            self.assertIn(
                entry.name,
                self.UNDISTRIBUTED_AGENT_SKILL_DIRS,
                f".agents/skills/{entry.name}/ exists, is not registered in AGENT_SKILL_SLUGS, "
                "does not mirror a .claude/commands file, and is not in the explicit "
                "UNDISTRIBUTED_AGENT_SKILL_DIRS allowlist — register it or add it with a "
                "one-line reason",
            )

    def test_mirrored_bodies_match_generically(self):
        """Case D, computed from the lists themselves (CLAUDE_SKILL_SLUGS ∩ AGENT_SKILL_SLUGS)
        instead of MirroredSkillBodiesMatch's hardcoded MIRRORED constant, so a newly-registered
        mirrored slug (notify-operator, absent from that constant) is covered without a second
        manual edit."""
        mirrored = sorted(set(sync.CLAUDE_SKILL_SLUGS) & set(sync.AGENT_SKILL_SLUGS))
        self.assertTrue(mirrored, "expected at least one slug registered in both lists")
        checked = 0
        for slug in mirrored:
            src = self.root / ".claude" / "skills" / slug / "SKILL.md"
            mirror = self.root / ".agents" / "skills" / slug / "SKILL.md"
            if not src.is_file() or not mirror.is_file():
                continue
            checked += 1
            src_body = src.read_text(encoding="utf-8").split("---", 2)[2]
            mirror_body = mirror.read_text(encoding="utf-8").split("---", 2)[2]
            self.assertEqual(
                src_body,
                mirror_body,
                f"{slug}: .agents mirror body has drifted from its .claude source",
            )
        self.assertEqual(
            checked, len(mirrored), "a mirrored slug is missing its file on one side"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
