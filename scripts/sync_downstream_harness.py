#!/usr/bin/env python3
"""Pull base-template's harness (.claude/commands/*.md flat + .claude/workflows/) AND the brain's
tracked git hooks (hooks/) into every downstream repo that has already been scaffolded from
base-template.

Downstream repos do not auto-sync by design (see base-template/CLAUDE.md, "The update loop").
This script automates the previously-manual "update loop" documented in
base-template/docs/using-the-template.md: copy changed harness files, never delete a file a repo
added on its own (project-specific commands survive), and stamp planning/.template-version so
every repo's drift from base-template is visible at a glance.

What gets synced, for every file that exists at its source, into the same relative path in the
target repo:
  - from base-template/.claude/ (base-template -> target):
      - commands/*.md               (flat root only - NOT commands/brain/, which is
                                       brain-only reference content, never propagated downstream)
      - workflows/*.js               (the SDLC engines)
      - workflows/*.json             (e.g. harness.schema.json - an authoring aid for editors/
                                       linters that resolve $schema; the engines never validate
                                       planning/harness.json against it at runtime, they just cat
                                       + JSON.parse it as data. Mechanism, not policy.)
      - workflows/templates/*.md
  - from base-template/.agents/skills/ (base-template -> target's .agents/skills/), one slug at a
    time via AGENT_SKILL_SLUGS (explicit, like HOOK_FILENAMES - not a directory glob, so a new
    skill dropped in base-template's .agents/skills/ isn't silently propagated before it's been
    reviewed):
      - <slug>/SKILL.md              the manual-replication guide a shell-less agent (Gemini/
                                       Antigravity - no `claude` CLI access) follows to reproduce
                                       the matching .claude/workflows/<slug>.js engine by hand.
                                       Mechanism, not project fact - synced to EVERY target
                                       including the brain root (never gated by engines_only, same
                                       as workflows/*.js: these mirror the engine, they are not a
                                       brain-specific command like commands/*.md).
  - from the brain's hooks/ (brain root -> target's hooks/, widened by the validate-brain
    push-gate chore, deliberate):
      - pre-push                     (the validate-brain drift gate)
      - test_pre_push.sh             (its self-contained regression test)
      - README.md                    (hook documentation)
    hooks/validate-baseline.json is deliberately EXCLUDED — the baseline is corpus-wide and
    singular (validate-brain always resolves the brain root and validates the entire corpus
    regardless of cwd), so it lives in HQ only and every repo's synced pre-push hook reads it
    read-only from the brain root it resolves at push time. Distributing a copy per repo would
    let it drift out of sync with the one that actually governs the gate.

What never gets touched:
  - Any file in the target that this script never wrote (a repo's own customizations, e.g.
    bastion's .claude/commands/feature.md). Those are invisible to it and are never touched.
  - Any file it DID write that the repo has since modified locally ("stale-conflict") - reported
    for the operator to resolve by hand, never deleted.

  It DOES delete one narrow class: a file this script wrote, recorded in the manifest, that the
  source no longer ships and whose on-disk content still matches the recorded hash
  ("stale-safe" - see FileDiff below). That is what makes a rename in base-template propagate as
  a rename rather than leaving a duplicate command in all 16 repos.
  - planning/, CLAUDE.md, harness.json, or anything else that is project fact, not mechanism.

Note: copying hooks/pre-push into a repo is inert until that repo's git is actually pointed at
it. This script prints a per-repo notice (and the exact fix) whenever it syncs a hook into a
repo whose `core.hooksPath` is not already set to `hooks` - see the printed report below.
Running `git config core.hooksPath hooks` in each repo is a deliberate, separate, manual step
(not part of this script, and not part of this chore's acceptance either).

Usage:
  python3 scripts/sync_downstream_harness.py                     # dry run, all eligible repos
  python3 scripts/sync_downstream_harness.py --repo bastion       # dry run, one repo
  python3 scripts/sync_downstream_harness.py --apply              # write changes, all repos
  python3 scripts/sync_downstream_harness.py --repo bastion --apply --message "D44-D47 tasks.json fix"

Run from anywhere inside the brain (walks up to find brain.toml); intended to be run from
base-template's own root, since that's where the source-of-truth .claude/ lives.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


# Where the content-hash manifest lives inside each synced downstream repo, colocated with the
# .claude/ tree it tracks (parallel in spirit to planning/.template-version). Records exactly the
# set of paths this script has previously written plus each one's content hash, so a later run can
# tell "this script put this here and it's unmodified, safe to remove" apart from "this repo added
# this itself, never touch it" - see diff_repo()/apply_repo().
MANIFEST_REL_PATH = ".claude/.harness-manifest.json"


def hash_file(path: Path) -> str:
    """sha256 hex digest of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(repo_path: Path) -> dict:
    """Read repo_path/MANIFEST_REL_PATH. Never raises - a missing or malformed manifest is
    treated as "no prior sync recorded", not an error, since this script must remain safe to run
    against a repo that predates the manifest's introduction."""
    manifest_path = repo_path / MANIFEST_REL_PATH
    default: dict = {"version": None, "generated": None, "files": {}}
    if not manifest_path.is_file():
        return default
    try:
        data = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return default
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return default
    return data


def write_manifest(repo_path: Path, version: str, files: dict[str, str]) -> None:
    """Write {"version": version, "generated": <today, ISO>, "files": files} as pretty JSON to
    repo_path/MANIFEST_REL_PATH, creating parent dirs as needed."""
    manifest_path = repo_path / MANIFEST_REL_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": version,
        "generated": date.today().isoformat(),
        "files": files,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def find_brain_root(start: Path) -> Path:
    """Walk up from `start` looking for brain.toml (its first line begins '# brain.toml')."""
    current = start.resolve()
    for candidate in [current, *current.parents]:
        toml_path = candidate / "brain.toml"
        if toml_path.is_file():
            return candidate
    raise SystemExit("ERROR: no brain.toml found walking up from " + str(start))


def find_base_template_root(start: Path) -> Path:
    """Walk up from `start` looking for the base-template root.

    NOT `.claude/workflows/sdlc-flow.js` alone - every downstream repo has a copy of that file
    (that's the whole point of this script), so checking for it would misidentify any scaffolded
    repo as base-template if the script were ever run from inside one. `scripts/` is never part of
    the sync target set (see harness_files()), so `scripts/sync_downstream_harness.py` existing is
    a reliable base-template-only anchor.
    """
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "scripts" / "sync_downstream_harness.py").is_file():
            return candidate
    raise SystemExit("ERROR: could not find base-template root (no scripts/sync_downstream_harness.py) walking up from " + str(start))


@dataclass
class RepoTarget:
    slug: str
    repo_path: Path  # absolute
    engines_only: bool = False  # receive .claude/workflows/ but never .claude/commands/


def discover_targets(brain_root: Path, base_template_root: Path) -> list[RepoTarget]:
    """Read brain.toml; a repo is an eligible sync target iff it has its own .claude/workflows/
    directory already (that's what marks it as having pulled the full SDLC-engine harness, as
    opposed to the lighter session/planning-only set some tiers get) and it isn't base-template
    itself.

    The brain root (HQ) is a target but an `engines_only` one: it runs the SDLC engines while
    authoring its own brain-specific commands. See harness_files() for why syncing commands
    there would be destructive."""
    with (brain_root / "brain.toml").open("rb") as f:
        config = tomllib.load(f)

    targets: list[RepoTarget] = []
    for repo in config.get("repos", []):
        repo_path = (brain_root / repo["repo_path"]).resolve()
        if repo_path == base_template_root:
            continue
        if not (repo_path / ".claude" / "workflows").is_dir():
            continue
        targets.append(
            RepoTarget(
                slug=repo["slug"],
                repo_path=repo_path,
                engines_only=repo_path == brain_root.resolve(),
            )
        )
    return targets


@dataclass
class FileDiff:
    rel_path: str  # relative to the file's source root (either .claude/ or hooks/)
    status: str  # "new" | "changed" | "stale-safe" | "stale-conflict"
    # "new"/"changed": present at source, add/update as before.
    # "stale-safe": this script wrote it before (recorded in the manifest) but source no longer
    #   ships it, and its on-disk content still matches the recorded hash - safe to delete.
    # "stale-conflict": same as stale-safe, but the on-disk content has diverged from the
    #   recorded hash (the repo locally modified it after receiving it) - never delete, report
    #   as a conflict for the operator to resolve by hand instead.
    dest_prefix: str = ".claude"  # ".claude" or "hooks" - which target subtree this belongs to


@dataclass
class RepoReport:
    target: RepoTarget
    diffs: list[FileDiff] = field(default_factory=list)
    error: str | None = None
    hooks_path_unset: bool = False  # target's core.hooksPath is not "hooks" (see hook_files())


# Commands that never sync downstream, to any target, regardless of engines_only. Explicitly
# enumerated (not a glob exclusion) so a new HQ-only command is a deliberate addition here, not an
# accidental one. generate-roadmap.md authors a roadmap SPANNING repos and its own Step 1A requires
# running from BRAIN_ROOT ("This command runs at HQ") - it has no meaning inside a single leaf repo,
# so it stays single-copy at base-template rather than fanning out to all 17 (see
# planning/ticket-generate-roadmap-command/review.md, Task 3 decision).
EXCLUDED_COMMAND_FILENAMES: set[str] = {"generate-roadmap.md"}


def harness_files(root: Path, engines_only: bool = False) -> list[Path]:
    """The exact base-template harness file set this script owns, relative to `root/.claude`.

    `engines_only` drops commands/*.md from the set. It exists for the brain root (HQ), which
    runs the SDLC engines but authors its OWN brain-specific commands: HQ's /prime, /log-work,
    /handoff, /capture and 9 others share a filename with base-template's generic versions and
    differ substantially (HQ's /prime is 164 lines to base-template's 55; HQ's /log-work carries
    the cross-repo brain sync). Syncing commands into HQ would silently overwrite all twelve.

    Separately, `EXCLUDED_COMMAND_FILENAMES` drops specific commands from every target regardless
    of `engines_only` - for commands that are HQ-only by nature rather than by target.

    `skills/<slug>/SKILL.md` (CLAUDE_SKILL_SLUGS) is NOT gated on `engines_only` - see that
    constant for why.
    """
    files: list[Path] = []
    commands_dir = root / ".claude" / "commands"
    if commands_dir.is_dir() and not engines_only:
        files.extend(
            p
            for p in commands_dir.glob("*.md")
            if p.is_file() and p.name not in EXCLUDED_COMMAND_FILENAMES
        )
    workflows_dir = root / ".claude" / "workflows"
    if workflows_dir.is_dir():
        files.extend(p for p in workflows_dir.glob("*.js") if p.is_file())
        files.extend(p for p in workflows_dir.glob("*.json") if p.is_file())
        # workflows/*.md — shared procedures the commands include BY REFERENCE, e.g.
        # block-registration.md, which /plan, /ticket and /chore all tell the agent to read
        # instead of carrying their own copy (D65). These are mechanism, not project fact, and
        # they sync to EVERY target including the brain root — same rule as workflows/*.js.
        # Gating them on engines_only would leave HQ's producers pointing at a file that does
        # not exist there, and HQ now runs real SDLC work (D63).
        files.extend(p for p in workflows_dir.glob("*.md") if p.is_file())
    templates_dir = workflows_dir / "templates"
    if templates_dir.is_dir():
        files.extend(p for p in templates_dir.glob("*.md") if p.is_file())
    # .claude/skills/<slug>/SKILL.md - model-triggered authoring guides. Like workflows/*.md these
    # are mechanism rather than project fact, so they are NOT gated on engines_only: the brain root
    # needs them as much as any leaf repo, and it is where both were authored.
    skills_dir = root / ".claude" / "skills"
    if skills_dir.is_dir():
        files.extend(
            skills_dir / slug / "SKILL.md"
            for slug in CLAUDE_SKILL_SLUGS
            if (skills_dir / slug / "SKILL.md").is_file()
        )
    files.extend(collect_script_files(root))
    return files


# The base-template scripts/ files this script distributes downstream. Explicitly enumerated
# (not a glob over scripts/) for the same reason as HOOK_FILENAMES and AGENT_SKILL_SLUGS: most
# of scripts/ is base-template's OWN test and gate tooling, which is project fact and must never
# propagate. Only scripts a downstream command actually invokes belong here, and each addition
# is a deliberate widening.
#
# render_spec.py was REMOVED from this list on 2026-08-20 by BT.ticket.engines-read-block-record:
# the engines now read planning/blocks/<BlockID>.json + tasks.json directly, /ticket, /chore and
# /generate-tasks no longer have a render step, and the script itself is deleted. Dropping it here
# makes this script REMOVE the stale downstream copies on the next sync (it reconciles removals,
# not just copies -- the same pass that retires sdlc-block.js and sdlc-run.js). Do not re-add it.
# check_block_records.py is the interim block-record gate until mev's W_BLOCK_* checks ship.
SCRIPT_FILENAMES: list[str] = ["check_block_records.py"]


def collect_script_files(root: Path) -> list[Path]:
    """The scripts/ files a downstream command invokes at runtime."""
    scripts_dir = root / "scripts"
    if not scripts_dir.is_dir():
        return []
    return [scripts_dir / name for name in SCRIPT_FILENAMES
            if (scripts_dir / name).is_file()]


# The brain hooks/ files this script distributes downstream. Explicitly enumerated (not a glob
# over hooks/) so a new file dropped into the brain's hooks/ directory for HQ-only reasons is
# never accidentally propagated - each addition here is a deliberate widening. Notably excludes
# hooks/validate-baseline.json (see module docstring: the baseline is corpus-wide and HQ-only).
HOOK_FILENAMES: list[str] = ["pre-push", "test_pre_push.sh", "README.md"]


def hook_files(brain_root: Path) -> list[Path]:
    """The tracked brain hook files this script owns, relative to `brain_root/hooks`."""
    hooks_dir = brain_root / "hooks"
    if not hooks_dir.is_dir():
        return []
    return [hooks_dir / name for name in HOOK_FILENAMES if (hooks_dir / name).is_file()]


# The .agents/skills/<slug>/SKILL.md guides this script distributes downstream. Explicitly
# enumerated (not a glob over .agents/skills/) so a skill added to base-template for reasons
# unrelated to the SDLC engines (or one that hasn't been reviewed against its matching .js the way
# sdlc-task/sdlc-flow were in the 2026-08 audit) is never accidentally propagated - widen this
# deliberately, per-slug, once a guide has actually been checked.
AGENT_SKILL_SLUGS: list[str] = [
    "sdlc-task",
    "sdlc-flow",
    # Mirrors of .claude/skills/<slug>/SKILL.md for the vendor-neutral surface. Their BODIES are
    # byte-identical to the .claude copies by design and only the frontmatter differs (folded
    # `description:`, no `allowed-tools:`) - the mirror was made by hand precisely because the
    # usual blind word substitution corrupts them: every "claude" string in these bodies is a
    # literal path or filename (`CLAUDE.md` in the corpus-membership rule, `.claude` in
    # skip_dirs), and rewriting them would make the rules they state false.
    "write-okf-markdown",
    "edit-state-json",
    "commit-in-this-fleet",
    "derive-state-safely",
    "run-the-gates",
    "stop-or-continue",
]


# The .claude/skills/<slug>/SKILL.md guides this script distributes downstream. Enumerated per-slug
# for the same reason as AGENT_SKILL_SLUGS: base-template's .claude/skills/ may hold skills specific
# to the factory, and a glob would fan those out to 17 repos on the next sync.
#
# NOT gated on engines_only - these sync to EVERY target including the brain root, same rule as
# workflows/*.md. They describe fleet-wide authoring mechanism (the OKF corpus-membership rule, the
# state.json schema), which is identical in every repo; the D54 exclusion exists for commands that
# DIVERGE per repo, and these do not. HQ authored both, so its copies are the source of these.
#
# Both are deliberately path-portable: they carry a "paths are relative to the brain root" banner
# instead of repo-relative links, because a ../../../ link is correct in exactly one of 17 repos.
CLAUDE_SKILL_SLUGS: list[str] = [
    "report-to-the-operator",
    "write-okf-markdown",
    "edit-state-json",
    "commit-in-this-fleet",
    "derive-state-safely",
    "run-the-gates",
    "stop-or-continue",
]


def agent_skill_files(root: Path) -> list[Path]:
    """The tracked .agents/skills/<slug>/SKILL.md files this script owns, relative to
    `root/.agents`."""
    skills_dir = root / ".agents" / "skills"
    if not skills_dir.is_dir():
        return []
    return [
        skills_dir / slug / "SKILL.md"
        for slug in AGENT_SKILL_SLUGS
        if (skills_dir / slug / "SKILL.md").is_file()
    ]


def repo_hooks_path(repo_path: Path) -> str | None:
    """The target repo's configured `core.hooksPath`, or None if unset/unreadable."""
    result = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    return value or None


def diff_repo(base_template_root: Path, brain_root: Path, target: RepoTarget) -> RepoReport:
    report = RepoReport(target=target)
    if not (target.repo_path / ".claude").is_dir():
        report.error = "no .claude/ directory"
        return report

    for src in harness_files(base_template_root, target.engines_only):
        # harness_files now returns two roots: .claude/** and scripts/** (the scripts a
        # downstream command invokes at runtime). Resolve the destination prefix per file
        # rather than assuming everything lives under .claude/.
        if src.is_relative_to(base_template_root / "scripts"):
            prefix = "scripts"
            rel = src.relative_to(base_template_root / "scripts")
        else:
            prefix = ".claude"
            rel = src.relative_to(base_template_root / ".claude")
        dst = target.repo_path / prefix / rel
        if not dst.exists():
            report.diffs.append(FileDiff(rel_path=str(rel), status="new", dest_prefix=prefix))
        elif not filecmp.cmp(src, dst, shallow=False):
            report.diffs.append(FileDiff(rel_path=str(rel), status="changed", dest_prefix=prefix))

    skill_diffs: list[FileDiff] = []
    for src in agent_skill_files(base_template_root):
        rel = src.relative_to(base_template_root / ".agents")
        dst = target.repo_path / ".agents" / rel
        if not dst.exists():
            skill_diffs.append(FileDiff(rel_path=str(rel), status="new", dest_prefix=".agents"))
        elif not filecmp.cmp(src, dst, shallow=False):
            skill_diffs.append(FileDiff(rel_path=str(rel), status="changed", dest_prefix=".agents"))
    report.diffs.extend(skill_diffs)

    hooks_diffs: list[FileDiff] = []
    for src in hook_files(brain_root):
        rel = src.relative_to(brain_root / "hooks")
        dst = target.repo_path / "hooks" / rel
        if not dst.exists():
            hooks_diffs.append(FileDiff(rel_path=str(rel), status="new", dest_prefix="hooks"))
        elif not filecmp.cmp(src, dst, shallow=False):
            hooks_diffs.append(FileDiff(rel_path=str(rel), status="changed", dest_prefix="hooks"))
    report.diffs.extend(hooks_diffs)

    if hooks_diffs and (target.repo_path / ".git").exists():
        configured = repo_hooks_path(target.repo_path)
        report.hooks_path_unset = configured != "hooks"

    # Stale detection: paths this script wrote in a prior run (recorded in the manifest) that the
    # current source set no longer ships. Diff the manifest's path set against the CURRENT
    # source-derived path set (not the "new"/"changed" diffs above, which only cover paths that
    # differ - a manifest path that's unchanged at source must not be treated as stale).
    manifest = load_manifest(target.repo_path)
    current_keys: set[str] = set()
    for src in harness_files(base_template_root, target.engines_only):
        if src.is_relative_to(base_template_root / "scripts"):
            current_keys.add(f"scripts/{src.relative_to(base_template_root / 'scripts')}")
        else:
            current_keys.add(f".claude/{src.relative_to(base_template_root / '.claude')}")
    for src in agent_skill_files(base_template_root):
        rel = src.relative_to(base_template_root / ".agents")
        current_keys.add(f".agents/{rel}")
    for src in hook_files(brain_root):
        rel = src.relative_to(brain_root / "hooks")
        current_keys.add(f"hooks/{rel}")

    for key, recorded_hash in manifest.get("files", {}).items():
        if key in current_keys:
            continue
        dest_prefix, _, rel = key.partition("/")
        dst = target.repo_path / dest_prefix / rel
        if not dst.is_file():
            # Nothing on disk to delete; it'll simply be dropped from the next manifest.
            continue
        if hash_file(dst) == recorded_hash:
            report.diffs.append(FileDiff(rel_path=rel, status="stale-safe", dest_prefix=dest_prefix))
        else:
            report.diffs.append(FileDiff(rel_path=rel, status="stale-conflict", dest_prefix=dest_prefix))

    return report


def apply_repo(base_template_root: Path, brain_root: Path, report: RepoReport, version: str) -> None:
    """Write every 'new'/'changed' diff, delete every 'stale-safe' diff (never 'stale-conflict'),
    then write the updated content-hash manifest reflecting the post-apply state of every
    currently-source-tracked path. 'stale-conflict' paths are left untouched on disk and dropped
    from the manifest so they stop being managed going forward - the operator resolves them by
    hand."""
    for d in report.diffs:
        if d.status == "stale-conflict":
            continue
        dst = report.target.repo_path / d.dest_prefix / d.rel_path
        if d.status == "stale-safe":
            dst.unlink(missing_ok=True)
            continue
        src_root = {
            ".claude": base_template_root / ".claude",
            ".agents": base_template_root / ".agents",
            "scripts": base_template_root / "scripts",
            "hooks": brain_root / "hooks",
        }[d.dest_prefix]
        src = src_root / d.rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # Recompute the manifest's files dict from scratch: every path in the CURRENT source set (not
    # just the ones that had a diff this run - unchanged files must stay recorded too), hashed from
    # its now-current on-disk content in the target repo. stale-conflict paths are intentionally
    # omitted (see docstring).
    files: dict[str, str] = {}
    for src in harness_files(base_template_root, report.target.engines_only):
        if src.is_relative_to(base_template_root / "scripts"):
            prefix, rel = "scripts", src.relative_to(base_template_root / "scripts")
        else:
            prefix, rel = ".claude", src.relative_to(base_template_root / ".claude")
        dst = report.target.repo_path / prefix / rel
        if dst.is_file():
            files[f"{prefix}/{rel}"] = hash_file(dst)
    for src in agent_skill_files(base_template_root):
        rel = src.relative_to(base_template_root / ".agents")
        dst = report.target.repo_path / ".agents" / rel
        if dst.is_file():
            files[f".agents/{rel}"] = hash_file(dst)
    for src in hook_files(brain_root):
        rel = src.relative_to(brain_root / "hooks")
        dst = report.target.repo_path / "hooks" / rel
        if dst.is_file():
            files[f"hooks/{rel}"] = hash_file(dst)

    write_manifest(report.target.repo_path, version, files)


def base_template_head_hash(base_template_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=base_template_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def update_template_version(target: RepoTarget, commit_hash: str, message: str) -> None:
    """Update planning/.template-version's commit + synced fields. Preserve the `generated:`
    line (initial scaffold provenance) if present; never invent one if absent."""
    tv_path = target.repo_path / "planning" / ".template-version"
    lines: list[str] = []
    if tv_path.is_file():
        lines = tv_path.read_text().splitlines()

    new_lines: list[str] = []
    seen_template = seen_commit = seen_synced = False
    today = date.today().isoformat()
    for line in lines:
        if line.startswith("template:"):
            new_lines.append("template: base-template")
            seen_template = True
        elif line.startswith("commit:"):
            new_lines.append(f"commit: {commit_hash}")
            seen_commit = True
        elif line.startswith("synced:"):
            new_lines.append(f"synced: {today} — {message}")
            seen_synced = True
        else:
            new_lines.append(line)

    if not seen_template:
        new_lines.insert(0, "template: base-template")
    if not seen_commit:
        new_lines.append(f"commit: {commit_hash}")
    if not seen_synced:
        new_lines.append(f"synced: {today} — {message}")

    tv_path.parent.mkdir(parents=True, exist_ok=True)
    tv_path.write_text("\n".join(new_lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", action="append", dest="repos", help="Limit to this repo slug (repeatable). Default: all eligible repos.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run (report only).")
    parser.add_argument("--message", default="harness pull", help="Description recorded in planning/.template-version's synced: line.")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    base_template_root = find_base_template_root(script_dir)
    brain_root = find_brain_root(base_template_root)

    targets = discover_targets(brain_root, base_template_root)
    if args.repos:
        wanted = set(args.repos)
        unknown = wanted - {t.slug for t in targets}
        if unknown:
            print(f"ERROR: unknown repo slug(s) or repo has no .claude/workflows/: {', '.join(sorted(unknown))}", file=sys.stderr)
            print(f"Eligible repos: {', '.join(sorted(t.slug for t in targets))}", file=sys.stderr)
            sys.exit(1)
        targets = [t for t in targets if t.slug in wanted]

    if not targets:
        print("No eligible downstream repos found (none have their own .claude/workflows/).")
        return

    commit_hash = base_template_head_hash(base_template_root) if args.apply else "(dry-run)"

    print(f"base-template root: {base_template_root}")
    print(f"mode: {'APPLY' if args.apply else 'DRY RUN (pass --apply to write)'}")
    print()

    total_changed = 0
    for target in targets:
        report = diff_repo(base_template_root, brain_root, target)
        if report.error:
            print(f"[{target.slug}] SKIPPED — {report.error}")
            continue
        if not report.diffs:
            print(f"[{target.slug}] up to date")
            continue

        actionable = [d for d in report.diffs if d.status != "stale-conflict"]
        conflicts = [d for d in report.diffs if d.status == "stale-conflict"]

        if actionable:
            print(f"[{target.slug}] {len(actionable)} file(s) {'to sync' if not args.apply else 'synced'}:")
            for d in actionable:
                label = "removed" if d.status == "stale-safe" else d.status
                print(f"    {label:>7}  {d.dest_prefix}/{d.rel_path}")
            total_changed += len(actionable)
        else:
            print(f"[{target.slug}] 0 file(s) to sync (all pending diffs are conflicts):")

        if conflicts:
            conflict_paths = ", ".join(f"{d.dest_prefix}/{d.rel_path}" for d in conflicts)
            print(
                f"    NOTICE: {len(conflicts)} file(s) base-template no longer ships were locally "
                f"modified in {target.slug} and were NOT deleted — resolve by hand: {conflict_paths}"
            )

        if report.hooks_path_unset:
            print(
                f"    NOTICE: {target.slug}'s core.hooksPath is not set to 'hooks' — the synced "
                f"pre-push gate will not run until you enable it. Run:"
            )
            print(f"        (cd {target.repo_path} && git config core.hooksPath hooks)")

        if args.apply:
            apply_repo(base_template_root, brain_root, report, commit_hash)
            update_template_version(target, commit_hash, args.message)
            print(f"    -> planning/.template-version updated (commit {commit_hash[:12]})")

    print()
    if args.apply:
        print(f"Done. {total_changed} file(s) written across {len(targets)} repo(s).")
        print("Review the diff in each repo and commit there — this script does not commit for you.")
    else:
        print(f"Dry run complete. {total_changed} file(s) would change across {len(targets)} repo(s).")
        print("Re-run with --apply to write.")


if __name__ == "__main__":
    main()
