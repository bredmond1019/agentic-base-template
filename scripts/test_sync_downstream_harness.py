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
        # Not in CLAUDE_SKILL_SLUGS — a factory-only skill must never fan out. Since
        # BT.chore.skills-go-global nothing under .claude/skills fans out, so this case is
        # now subsumed by test_no_claude_skills_sync_per_repo; kept because it is the
        # narrower, more legible statement of the same rule.
        _write(
            self.bt / ".claude" / "skills" / "factory-only" / "SKILL.md",
            "base-template internal\n",
        )
        # The .agents mirrors ARE still distributed per-repo. One registered slug, so the
        # nesting regression (skills/<slug>/SKILL.md, never a flattened .agents/SKILL.md)
        # still has something to assert against after the .claude half stopped syncing.
        _write(
            self.bt / ".agents" / "skills" / sync.AGENT_SKILL_SLUGS[0] / "SKILL.md",
            "agent-surface guide\n",
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
        """D54's core guarantee, NARROWED (not weakened) by
        BT.chore.session-commands-are-one-source: engines_only still drops every command HQ
        authors its own version of. log-work.md moved out of this assertion deliberately — it is
        depth-agnostic by construction and is now in ENGINES_ONLY_COMMAND_ALLOWLIST, which
        EnginesOnlyCommandAllowlistGuard pins to exactly four entries."""
        names = {p.name for p in sync.harness_files(self.bt, engines_only=True)}
        self.assertNotIn("prime.md", names)
        self.assertIn(
            "log-work.md", sync.ENGINES_ONLY_COMMAND_ALLOWLIST,
            "log-work is exempted here only because it is allowlisted; if it leaves the "
            "allowlist this assertion must go back to assertNotIn",
        )

    def test_harness_files_keeps_engines_when_engines_only(self):
        names = {p.name for p in sync.harness_files(self.bt, engines_only=True)}
        self.assertIn("sdlc-task.js", names)
        self.assertIn("harness.schema.json", names)
        self.assertIn("t.md", names)

    def test_harness_files_includes_commands_by_default(self):
        names = {p.name for p in sync.harness_files(self.bt)}
        self.assertIn("prime.md", names)

    def test_no_claude_skills_sync_per_repo(self):
        """INVERTED by BT.chore.skills-go-global (2026-09-03).

        These used to assert that .claude/skills/<slug>/SKILL.md reached every target. The 17
        fleet-mechanism skills now install ONCE into ~/.claude/skills/ instead, so NOTHING under
        .claude/skills/ may be distributed per-repo. CLAUDE_SKILL_SLUGS is deliberately empty.

        Why the old model had to go, beyond the 323 duplicate files: skills offer no picker, and
        a same-named repo-local skill LOSES to the global one - measured by body, not by listing.
        Per-repo copies were therefore unreachable once a global install existed, so they bought
        staleness and nothing else. The freshness of the one remaining surface is watched by the
        non-gating `global-skills-fresh` check.
        """
        for engines_only in (True, False):
            rels = {
                str(p.relative_to(self.bt / ".claude"))
                for p in sync.harness_files(self.bt, engines_only=engines_only)
            }
            leaked = sorted(r for r in rels if r.startswith("skills/"))
            self.assertEqual(
                leaked,
                [],
                "nothing under .claude/skills/ may sync per-repo any more - these install "
                "globally to ~/.claude/skills/. If you are re-adding per-repo distribution, "
                "restore CLAUDE_SKILL_SLUGS deliberately and update this test.",
            )

    def test_claude_skill_slugs_is_empty_by_design(self):
        """Positive control for the test above: it would also pass if harness_files() were
        broken and returned nothing at all. Pin the actual cause."""
        self.assertEqual(
            list(sync.CLAUDE_SKILL_SLUGS),
            [],
            "CLAUDE_SKILL_SLUGS must stay empty - .claude/skills installs globally",
        )
        self.assertTrue(
            sync.AGENT_SKILL_SLUGS,
            "AGENT_SKILL_SLUGS must NOT be empty - the Antigravity mirrors are still "
            "distributed per-repo, and an empty list here would mean the sync stopped "
            "shipping them without anyone noticing",
        )

    def test_non_allowlisted_skill_never_syncs(self):
        """The allowlist is the whole point: a skill added to base-template for factory-internal
        reasons must not fan out to 17 repos on the next sync."""
        for engines_only in (True, False):
            rels = {
                str(p.relative_to(self.bt / ".claude"))
                for p in sync.harness_files(self.bt, engines_only=engines_only)
            }
            self.assertNotIn("skills/factory-only/SKILL.md", rels)

    def test_agent_skills_land_under_dot_agents_with_their_slug_directory(self):
        """Regression: the destination must keep the skills/<slug>/ nesting. A flattened copy
        lands at .agents/SKILL.md and is never discovered.

        Re-pointed from .claude to .agents by BT.chore.skills-go-global: .claude/skills no longer
        syncs per-repo at all, but the .agents mirrors still do and the nesting rule is the same.
        """
        report = sync.diff_repo(self.bt.resolve(), self.brain.resolve(), self._targets()["leaf"])
        slug = sync.AGENT_SKILL_SLUGS[0]
        entry = next(
            d for d in report.diffs
            if d.dest_prefix == ".agents" and d.rel_path == f"skills/{slug}/SKILL.md"
        )
        self.assertEqual(entry.dest_prefix, ".agents")
        self.assertEqual(entry.rel_path, f"skills/{slug}/SKILL.md")
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
        cmds = [c for c in changed if "commands" in c]
        allowed = {f"commands/{n}" for n in sync.ENGINES_ONLY_COMMAND_ALLOWLIST}
        unexpected = [c for c in cmds if c not in allowed]
        self.assertEqual(
            unexpected,
            [],
            f"HQ commands would be overwritten: {unexpected}. Only the four depth-agnostic "
            f"session commands may reach the brain root (D54's narrow exception); anything else "
            f"here means an HQ-authored command is about to be silently replaced.",
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


class EnginesOnlyCommandAllowlistGuard(unittest.TestCase):
    """BT.chore.session-commands-are-one-source — the narrow D54 exception must stay narrow.

    D54 makes the brain root engines_only because HQ's commands genuinely diverge (/prime is 193
    lines to base-template's 77). ENGINES_ONLY_COMMAND_ALLOWLIST punches a hole in that for four
    commands which are depth-agnostic by construction. The hole is only safe while it stays small,
    and the failure mode of widening it is silent: HQ's authored command is simply overwritten on
    the next sync, and nothing says so.
    """

    # Commands HQ authors its own version of, measured 2026-09-04. Adding any of these to the
    # allowlist would have base-template overwrite HQ's copy — exactly what D54 forbids.
    KNOWN_DIVERGENT = {
        "prime.md", "update-state.md", "archive.md", "capture.md", "commit.md",
        "assess.md", "seams.md", "sequence.md", "session-recap.md", "backlog-ticket.md",
        "roadmap-status.md", "define-design-system.md", "README.md",
    }

    def test_allowlist_contains_only_the_four_session_commands(self):
        self.assertEqual(
            sync.ENGINES_ONLY_COMMAND_ALLOWLIST,
            {"handoff.md", "wrap-up.md", "log-work.md", "begin-session.md"},
            "the D54 exception must stay narrow — widening it silently overwrites an "
            "HQ-authored command on the next sync",
        )

    def test_no_known_divergent_command_is_allowlisted(self):
        overlap = sync.ENGINES_ONLY_COMMAND_ALLOWLIST & self.KNOWN_DIVERGENT
        self.assertEqual(
            overlap, set(),
            f"{sorted(overlap)} are commands HQ authors its own version of. Allowlisting one "
            f"makes base-template overwrite HQ's copy — the exact D54 violation. If HQ needs "
            f"different behaviour the command is not depth-agnostic and cannot be shared.",
        )

    def test_allowlisted_commands_reach_an_engines_only_target(self):
        """Positive control: the allowlist must actually DO something."""
        root = Path(sync.__file__).resolve().parent.parent
        names = {
            p.name for p in sync.harness_files(root, engines_only=True) if p.suffix == ".md"
        }
        for cmd in sorted(sync.ENGINES_ONLY_COMMAND_ALLOWLIST):
            self.assertIn(cmd, names, f"{cmd} is allowlisted but does not reach an engines_only target")

    def test_a_non_allowlisted_command_still_does_not(self):
        """The other half: engines_only must still drop everything else."""
        root = Path(sync.__file__).resolve().parent.parent
        names = {
            p.name for p in sync.harness_files(root, engines_only=True) if p.suffix == ".md"
        }
        self.assertNotIn(
            "prime.md", names,
            "engines_only must still drop HQ-authored commands — D54's whole point",
        )


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
        "sync-skills": "the generator that populates .agents/skills from .claude/commands; "
                        "shipping it downstream would ship the generator, not a guide",
    }

    def setUp(self) -> None:
        self.root = Path(sync.__file__).resolve().parent.parent

    def _command_stems(self) -> set[str]:
        commands_dir = self.root / ".claude" / "commands"
        return {p.stem for p in commands_dir.rglob("*.md")}

    def test_notify_operator_reaches_both_surfaces(self):
        """Case A, restated for the post-2026-09-03 model.

        The Claude surface is now the GLOBAL install, so the invariant is that the skill is
        authored in .claude/skills/ (whence /sync-global-skills installs it), not that it is
        listed for per-repo distribution. The Antigravity surface is still per-repo.
        """
        self.assertTrue(
            (self.root / ".claude" / "skills" / "notify-operator" / "SKILL.md").is_file(),
            "notify-operator must exist in .claude/skills/ to reach ~/.claude/skills/",
        )
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
        # .claude/skills is no longer distributed per-repo (BT.chore.skills-go-global), so the
        # "authored but undistributed" failure this guards moved: a skill authored here reaches
        # every session via ~/.claude/skills/, and the thing that can now go wrong is a directory
        # with no SKILL.md, which installs as an empty skill and resolves to nothing.
        claude_skills_dir = self.root / ".claude" / "skills"
        for entry in sorted(claude_skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            self.assertTrue(
                (entry / "SKILL.md").is_file(),
                f".claude/skills/{entry.name}/ exists but has no SKILL.md — it would install "
                "to ~/.claude/skills/ as an empty skill and resolve to nothing",
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
        # Derived from what is on disk in BOTH trees, not from the two lists: CLAUDE_SKILL_SLUGS
        # is empty since the global-install move, so intersecting the lists now yields nothing
        # and the case would silently stop testing anything.
        mirrored = sorted(
            d.name
            for d in (self.root / ".claude" / "skills").iterdir()
            if d.is_dir()
            and (d / "SKILL.md").is_file()
            and (self.root / ".agents" / "skills" / d.name / "SKILL.md").is_file()
        )
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



class CommitFlag(unittest.TestCase):
    """--commit: the two-repo split, the explicit pathspec, and the --apply precondition.

    These build REAL git repos in a temp dir and make REAL commits. Nothing touches the fleet:
    every path is under tempfile.TemporaryDirectory(), and git is given -C explicitly so it can
    never walk up into agentic-portfolio.

    The failure this suite exists to catch is not "the commit did not happen" -- it is
    "`git add` hit the planning/ symlink, aborted the whole add, and the run reported success
    while committing nothing." That is why test_symlinked_stamp_is_staged_via_the_vault_path
    exists and why it asserts on the brain's log, not on the script's own output.
    """

    def _git(self, *args, cwd):
        import subprocess
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
        return r

    def _init_repo(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        self._git("init", "-q", "-b", "main", cwd=path)
        self._git("config", "user.email", "t@example.com", cwd=path)
        self._git("config", "user.name", "T", cwd=path)
        self._git("config", "commit.gpgsign", "false", cwd=path)
        # core.hooksPath is deliberately left alone; these repos have no hooks.
        return path

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()

        # The brain: owns the vault, therefore owns every repo's planning/.template-version.
        self.brain = self._init_repo(self.tmp / "brain")
        _write(self.brain / "brain.toml", "# brain.toml\n")
        _write(self.brain / "_planning" / "leaf" / ".template-version",
               "template: base-template\ncommit: old\nsynced: 2026-01-01 — before\n")
        self._git("add", "-A", cwd=self.brain)          # fixture setup only, not script behaviour
        self._git("commit", "-qm", "fixture", cwd=self.brain)

        # The leaf repo: owns .claude/, and reaches its planning/ through a symlink into the vault.
        self.leaf = self._init_repo(self.brain / "leaf")
        _write(self.leaf / ".claude" / "workflows" / "block-registration.md", "v2\n")
        _write(self.leaf / ".claude" / ".harness-manifest.json", '{"files": {}}\n')
        (self.leaf / "planning").symlink_to(self.brain / "_planning" / "leaf")
        self._git("add", "-A", cwd=self.leaf)
        self._git("commit", "-qm", "fixture", cwd=self.leaf)

        self.target = sync.RepoTarget(slug="leaf", repo_path=self.leaf)
        self.report = sync.RepoReport(
            target=self.target,
            diffs=[sync.FileDiff(rel_path="workflows/block-registration.md", status="changed",
                                 dest_prefix=".claude")],
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # --- the pathspec ----------------------------------------------------------------------

    def test_commit_paths_are_explicit_and_include_the_manifest(self):
        paths = sync.repo_commit_paths(self.report)
        self.assertEqual(paths, [".claude/.harness-manifest.json",
                                 ".claude/workflows/block-registration.md"])

    def test_stale_conflict_paths_are_never_committed(self):
        """apply_repo() deliberately leaves a conflict on disk for the operator; committing it
        would launder an unresolved conflict into a routine sync commit."""
        self.report.diffs.append(
            sync.FileDiff(rel_path="commands/local-edit.md", status="stale-conflict"))
        self.assertNotIn(".claude/commands/local-edit.md", sync.repo_commit_paths(self.report))

    def test_deletions_are_committed(self):
        self.report.diffs.append(
            sync.FileDiff(rel_path="commands/retired.md", status="stale-safe"))
        self.assertIn(".claude/commands/retired.md", sync.repo_commit_paths(self.report))

    # --- the repo half ---------------------------------------------------------------------

    def test_repo_half_commits_its_own_files(self):
        (self.leaf / ".claude" / "workflows" / "block-registration.md").write_text("v3\n")
        out = sync.commit_repo_half(self.report, self.brain, "test sync")
        self.assertIsNone(out.error, out.error)
        self.assertIsNotNone(out.sha)
        left = self._git("status", "--porcelain", "--", ".claude", cwd=self.leaf).stdout.strip()
        self.assertEqual(left, "", f"leaf still dirty after commit: {left}")

    def test_repo_half_is_a_no_op_when_nothing_changed(self):
        out = sync.commit_repo_half(self.report, self.brain, "test sync")
        self.assertIsNone(out.error)
        self.assertIsNone(out.sha, "committed an empty change")

    def test_a_repo_owned_by_the_brain_is_folded_into_the_brain_commit(self):
        """The engines_only brain-root case: its harness files are in the BRAIN's index, so
        committing them from the per-repo loop would split one index across two commits."""
        report = sync.RepoReport(target=sync.RepoTarget(slug="brain", repo_path=self.brain),
                                 diffs=list(self.report.diffs))
        out = sync.commit_repo_half(report, self.brain, "test sync")
        self.assertIsNone(out.sha)
        self.assertEqual(out.skipped, "brain-owned; folded into the brain commit")

    def test_a_non_git_directory_is_reported_not_crashed(self):
        loose = self.tmp / "loose"
        (loose / ".claude").mkdir(parents=True)
        report = sync.RepoReport(target=sync.RepoTarget(slug="loose", repo_path=loose),
                                 diffs=list(self.report.diffs))
        out = sync.commit_repo_half(report, self.brain, "test sync")
        self.assertIsNone(out.sha)
        self.assertIsNotNone(out.skipped)

    # --- the brain half and the symlink trap ------------------------------------------------

    def test_template_version_resolves_to_the_vault_path_not_the_symlink(self):
        rel = sync.template_version_vault_path(self.target, self.brain)
        self.assertEqual(rel, "_planning/leaf/.template-version")
        self.assertNotIn("leaf/planning", rel)

    def test_symlinked_stamp_is_staged_via_the_vault_path(self):
        """The whole reason --commit is N+1 commits. Staging <repo>/planning/.template-version
        fails with 'beyond a symbolic link' and aborts the entire `git add`; the vault path is
        what git actually tracks. Asserted on the brain's committed tree, not on stdout."""
        sync.update_template_version(self.target, "abc123", "test sync")
        rel = sync.template_version_vault_path(self.target, self.brain)
        out = sync.commit_brain_half(self.brain, [rel], [], "test sync")
        self.assertIsNone(out.error, out.error)
        self.assertIsNotNone(out.sha)
        shown = self._git("show", "--stat", "--format=", "HEAD", cwd=self.brain).stdout
        self.assertIn("_planning/leaf/.template-version", shown)
        # Scoped to the vault, deliberately: the leaf repo is an untracked directory inside the
        # brain here (as sub-repos are, gitignored, in the real fleet), and a bare status would
        # report it. Gitignoring it in the fixture instead would make
        # test_staging_the_symlinked_face_really_does_fail pass for the WRONG reason -- git would
        # refuse the path as ignored rather than as beyond a symlink.
        left = self._git("status", "--porcelain", "--", "_planning", cwd=self.brain).stdout.strip()
        self.assertEqual(left, "", f"vault still dirty after brain commit: {left}")

    def test_staging_the_symlinked_face_really_does_fail(self):
        """Positive control for the claim above -- without this, the vault-path test could pass
        for reasons unrelated to the symlink, and the N+1 split would look like superstition."""
        sync.update_template_version(self.target, "abc123", "test sync")
        r = self._git("add", "--", "leaf/planning/.template-version", cwd=self.brain)
        self.assertNotEqual(r.returncode, 0,
                            "staging through the symlink SUCCEEDED — the split may be unnecessary")
        self.assertIn("symbolic link", (r.stderr + r.stdout).lower())

    def test_brain_half_is_a_no_op_with_no_stamps(self):
        out = sync.commit_brain_half(self.brain, [], [], "test sync")
        self.assertIsNone(out.error)
        self.assertIsNone(out.sha)


    # --- gitignored harness trees (D8 published-repo hygiene) --------------------------------

    def _portfolio_tier_leaf(self) -> Path:
        """rag-engine-rs's real shape: `.claude/` is gitignored and was NEVER committed, so its
        files are untracked AND ignored. (A tracked-then-ignored file is a different case entirely
        -- git keeps tracking it and `commit -o` handles it with no `add` at all, which is why the
        first version of this fixture passed for the wrong reason.)"""
        leaf = self._init_repo(self.tmp / "portfolio-leaf")
        _write(leaf / ".gitignore", ".claude/\n")
        _write(leaf / "README.md", "x\n")
        self._git("add", "--", ".gitignore", "README.md", cwd=leaf)
        self._git("commit", "-qm", "fixture", cwd=leaf)
        _write(leaf / ".claude" / "workflows" / "block-registration.md", "v2\n")
        _write(leaf / ".claude" / ".harness-manifest.json", '{"files": {}}\n')
        return leaf

    def test_a_gitignored_harness_tree_is_skipped_not_failed(self):
        """Portfolio-tier repos gitignore .claude/ on purpose (D8). `git add` on a path under an
        ignored directory fails the whole add; reporting that as a commit FAILURE (and exiting 1)
        would make every sync red for a repo behaving exactly as designed. Found on this flag's
        first live run against rag-engine-rs."""
        leaf = self._portfolio_tier_leaf()
        report = sync.RepoReport(
            target=sync.RepoTarget(slug="portfolio-leaf", repo_path=leaf),
            diffs=[sync.FileDiff(rel_path="workflows/block-registration.md", status="changed",
                                 dest_prefix=".claude")],
        )
        out = sync.commit_repo_half(report, self.brain, "test sync")
        self.assertIsNone(out.error, f"a gitignored tree was reported as an error: {out.error}")
        self.assertIsNone(out.sha)
        self.assertIn("gitignored", out.skipped or "")

    def test_a_partially_ignored_repo_still_commits_what_it_tracks(self):
        """rag-engine-rs's real shape: .claude/ ignored, scripts/ tracked. The tracked half must
        still land -- dropping the whole commit because one path is ignored loses real work."""
        leaf = self._portfolio_tier_leaf()
        _write(leaf / "scripts" / "check_block_records.py", "v2\n")
        self._git("add", "--", "scripts", cwd=leaf)
        self._git("commit", "-qm", "fixture", cwd=leaf)
        (leaf / "scripts" / "check_block_records.py").write_text("v3\n")
        report = sync.RepoReport(
            target=sync.RepoTarget(slug="portfolio-leaf", repo_path=leaf),
            diffs=[sync.FileDiff(rel_path="check_block_records.py", status="changed",
                                 dest_prefix="scripts"),
                   sync.FileDiff(rel_path="workflows/block-registration.md", status="changed",
                                 dest_prefix=".claude")],
        )
        out = sync.commit_repo_half(report, self.brain, "test sync")
        self.assertIsNone(out.error, out.error)
        self.assertIsNotNone(out.sha, "the tracked half was dropped along with the ignored one")
        shown = self._git("show", "--stat", "--format=", "HEAD", cwd=leaf).stdout
        self.assertIn("scripts/check_block_records.py", shown)
        self.assertNotIn(".claude/workflows", shown)

    def test_tracked_probe_is_false_for_an_unknown_path(self):
        """A path git cannot classify must not be treated as tracked -- that would skip the `add`
        a genuinely new file needs and commit nothing."""
        self.assertFalse(sync.path_is_tracked(self.leaf, ".claude/never-existed.md"))

    def test_check_ignore_is_the_wrong_probe_and_this_pins_why(self):
        """Positive control for the comment in commit_repo_half: on a TRACKED file under an
        IGNORED directory, `git check-ignore` answers "not ignored" while `git add` still
        refuses. If git ever changes that, this fails and the simpler probe becomes available."""
        _write(self.leaf / ".gitignore", ".claude/\n")
        self._git("add", "--", ".gitignore", cwd=self.leaf)
        self._git("commit", "-qm", "ignore .claude", cwd=self.leaf)
        ci = self._git("check-ignore", "-q", "--", ".claude/workflows/block-registration.md",
                       cwd=self.leaf)
        self.assertEqual(ci.returncode, 1, "check-ignore now calls the tracked file ignored")
        add = self._git("add", "--", ".claude/workflows/block-registration.md", cwd=self.leaf)
        self.assertNotEqual(add.returncode, 0, "git add now accepts it; the workaround is stale")


    # --- --commit-pending: the catch-up case ------------------------------------------------
    #
    # Measured 2026-09-02: 103 base-template-owned paths sat uncommitted across 18 repos, six per
    # repo, written by an earlier --apply that was never committed. They never appear in a dry run
    # because their content already MATCHES base-template -- current on disk, unrecorded in git.

    def _owned_pending(self, rel=".claude/commands/orchestrate.md", body="synced body\n"):
        """Put an owned path on disk in the leaf, dirty and matching a base-template source."""
        src_root = self.tmp / "bt"
        src = src_root / rel.replace(".claude/", ".claude/", 1)
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(body)
        dst = self.leaf / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(body)
        return src_root, rel

    def test_pending_owned_picks_up_a_matching_dirty_owned_path(self):
        src_root, rel = self._owned_pending()
        owned = {rel: src_root / rel}
        orig = sync.owned_dest_paths
        sync.owned_dest_paths = lambda a, b, c: owned
        try:
            keep, held = sync.pending_owned(src_root, self.brain, self.report, set())
        finally:
            sync.owned_dest_paths = orig
        self.assertEqual(keep, [rel], f"keep={keep} held={held}")
        self.assertEqual(held, [])

    def test_a_dirty_owned_path_that_DIFFERS_is_withheld_not_committed(self):
        """The safety property: an owned path whose bytes diverge is a LOCAL EDIT, not a pending
        sync. Committing it under a 'sync base-template' subject buries a real change."""
        src_root, rel = self._owned_pending()
        (self.leaf / rel).write_text("locally edited\n")
        owned = {rel: src_root / rel}
        orig = sync.owned_dest_paths
        sync.owned_dest_paths = lambda a, b, c: owned
        try:
            keep, held = sync.pending_owned(src_root, self.brain, self.report, set())
        finally:
            sync.owned_dest_paths = orig
        self.assertEqual(keep, [], f"a diverged path was staged: {keep}")
        self.assertEqual([r for r, _ in held], [rel])
        self.assertIn("local edit", held[0][1])

    def test_a_repos_OWN_file_is_never_pending(self):
        """The whole safety property of the flag: ownership comes from base-template's source set,
        so a repo's own dirty file is invisible to it however dirty it is."""
        (self.leaf / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
        (self.leaf / ".claude" / "commands" / "repo-local.md").write_text("mine\n")
        orig = sync.owned_dest_paths
        sync.owned_dest_paths = lambda a, b, c: {}
        try:
            keep, held = sync.pending_owned(self.tmp / "bt", self.brain, self.report, set())
        finally:
            sync.owned_dest_paths = orig
        self.assertEqual(keep, [], f"a repo-local file was staged: {keep}")
        self.assertEqual(held, [])

    def test_untracked_directories_are_expanded_to_files(self):
        """`git status --porcelain` reports an untracked DIRECTORY as one entry with a trailing
        slash, so a bare read misses every file inside it -- and that is exactly the shape the real
        backlog took (an untracked .claude/skills/record-a-bail/ in 17 repos)."""
        d = self.leaf / ".claude" / "skills" / "record-a-bail"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("x\n")
        paths = sync.dirty_paths(self.leaf)
        self.assertIn(".claude/skills/record-a-bail/SKILL.md", paths, str(paths))
        self.assertNotIn(".claude/skills/record-a-bail/", paths, str(paths))

    def test_paths_this_run_already_commits_are_not_double_counted(self):
        src_root, rel = self._owned_pending()
        owned = {rel: src_root / rel}
        orig = sync.owned_dest_paths
        sync.owned_dest_paths = lambda a, b, c: owned
        try:
            keep, _ = sync.pending_owned(src_root, self.brain, self.report, {rel})
        finally:
            sync.owned_dest_paths = orig
        self.assertEqual(keep, [])

    def test_commit_pending_requires_commit(self):
        import subprocess
        r = subprocess.run([sys.executable, str(_MODULE_PATH), "--apply", "--commit-pending"],
                           capture_output=True, text=True, cwd=str(_MODULE_PATH.parent))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--commit-pending requires --commit", r.stderr)

    def test_ownership_map_is_built_from_the_real_source_sets(self):
        """Not a mock: the map must actually contain paths base-template ships, or the flag would
        silently pick up nothing and read as 'no pending work'."""
        bt = _MODULE_PATH.parent.parent
        owned = sync.owned_dest_paths(bt, bt.parent, sync.RepoTarget(slug="x", repo_path=self.leaf))
        self.assertTrue(any(p.startswith(".claude/commands/") for p in owned), "no commands owned")
        self.assertTrue(any(p.startswith(".agents/skills/") for p in owned), "no agent skills owned")
        self.assertIn(".claude/workflows/sdlc-task.js", owned, "the engines must be owned")


    def test_an_up_to_date_repo_with_a_pending_path_is_not_skipped(self):
        """The hole this flag shipped with. main() used to `continue` on empty diffs BEFORE the
        commit block, so a repo whose owned files are current on disk but uncommitted -- exactly
        the backlog --commit-pending exists to clear -- reported 'up to date' and was skipped.
        rag-engine-rs kept one path in limbo through two consecutive --commit runs that way."""
        src = self.leaf / ".claude" / "commands" / "orchestrate.md"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("current\n")
        empty = sync.RepoReport(target=self.target, diffs=[])
        self.assertEqual(sync.repo_commit_paths(empty), [".claude/.harness-manifest.json"],
                         "an empty report should carry only the manifest")
        owned = {".claude/commands/orchestrate.md": src}
        orig = sync.owned_dest_paths
        sync.owned_dest_paths = lambda a, b, c: owned
        try:
            keep, _ = sync.pending_owned(self.tmp / "bt", self.brain, empty, set())
        finally:
            sync.owned_dest_paths = orig
        self.assertEqual(keep, [".claude/commands/orchestrate.md"],
                         "a pending path must be found even when the run has zero diffs")

    def test_the_up_to_date_branch_is_guarded_on_all_three_flags(self):
        """Source-level: the early `continue` must only be bypassed under
        --apply AND --commit AND --commit-pending, never on --apply alone."""
        src = _MODULE_PATH.read_text()
        self.assertIn("if not (args.apply and args.commit and args.commit_pending):", src)

    # --- the CLI precondition ---------------------------------------------------------------

    def test_commit_without_apply_is_a_usage_error(self):
        import subprocess
        r = subprocess.run([sys.executable, str(_MODULE_PATH), "--commit"],
                           capture_output=True, text=True, cwd=str(_MODULE_PATH.parent))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("--commit requires --apply", r.stderr)

    def test_the_script_never_runs_git_add_dash_a(self):
        """A bare `git add -A` here would sweep concurrent sessions' in-flight vault work into a
        sync commit. Asserted against the module source so it cannot creep back in."""
        src = _MODULE_PATH.read_text()
        for banned in ('"add", "-A"', '"add", "."', "'add', '-A'", "'add', '.'"):
            self.assertNotIn(banned, src, f"sync script must never {banned}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
