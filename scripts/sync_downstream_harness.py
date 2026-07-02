#!/usr/bin/env python3
"""Pull base-template's harness (.claude/commands/*.md flat + .claude/workflows/) into every
downstream repo that has already been scaffolded from it.

Downstream repos do not auto-sync by design (see base-template/CLAUDE.md, "The update loop").
This script automates the previously-manual "update loop" documented in
base-template/docs/using-the-template.md: copy changed harness files, never delete a file a repo
added on its own (project-specific commands survive), and stamp planning/.template-version so
every repo's drift from base-template is visible at a glance.

What gets synced (base-template -> target), for every file that exists in base-template:
  - .claude/commands/*.md          (flat root only - NOT .claude/commands/brain/, which is
                                     brain-only reference content, never propagated downstream)
  - .claude/workflows/*.js         (the SDLC engines)
  - .claude/workflows/templates/*.md

What never gets touched:
  - Any file in the target that doesn't exist in base-template (a repo's own customizations,
    e.g. bastion's .claude/commands/feature.md) - this script only ever adds/updates, never deletes.
  - planning/, CLAUDE.md, harness.json, or anything else that is project fact, not mechanism.

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
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


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


def discover_targets(brain_root: Path, base_template_root: Path) -> list[RepoTarget]:
    """Read brain.toml; a repo is an eligible sync target iff it has its own .claude/workflows/
    directory already (that's what marks it as having pulled the full SDLC-engine harness, as
    opposed to the lighter session/planning-only set some tiers get) and it isn't base-template
    itself."""
    with (brain_root / "brain.toml").open("rb") as f:
        config = tomllib.load(f)

    targets: list[RepoTarget] = []
    for repo in config.get("repos", []):
        repo_path = (brain_root / repo["repo_path"]).resolve()
        if repo_path == base_template_root:
            continue
        if not (repo_path / ".claude" / "workflows").is_dir():
            continue
        targets.append(RepoTarget(slug=repo["slug"], repo_path=repo_path))
    return targets


@dataclass
class FileDiff:
    rel_path: str  # relative to .claude/
    status: str  # "new" | "changed"


@dataclass
class RepoReport:
    target: RepoTarget
    diffs: list[FileDiff] = field(default_factory=list)
    error: str | None = None


def harness_files(root: Path) -> list[Path]:
    """The exact file set this script owns, relative to `root`."""
    files: list[Path] = []
    commands_dir = root / ".claude" / "commands"
    if commands_dir.is_dir():
        files.extend(p for p in commands_dir.glob("*.md") if p.is_file())
    workflows_dir = root / ".claude" / "workflows"
    if workflows_dir.is_dir():
        files.extend(p for p in workflows_dir.glob("*.js") if p.is_file())
    templates_dir = workflows_dir / "templates"
    if templates_dir.is_dir():
        files.extend(p for p in templates_dir.glob("*.md") if p.is_file())
    return files


def diff_repo(base_template_root: Path, target: RepoTarget) -> RepoReport:
    report = RepoReport(target=target)
    if not (target.repo_path / ".claude").is_dir():
        report.error = "no .claude/ directory"
        return report

    for src in harness_files(base_template_root):
        rel = src.relative_to(base_template_root / ".claude")
        dst = target.repo_path / ".claude" / rel
        if not dst.exists():
            report.diffs.append(FileDiff(rel_path=str(rel), status="new"))
        elif not filecmp.cmp(src, dst, shallow=False):
            report.diffs.append(FileDiff(rel_path=str(rel), status="changed"))
    return report


def apply_repo(base_template_root: Path, report: RepoReport) -> None:
    for d in report.diffs:
        src = base_template_root / ".claude" / d.rel_path
        dst = report.target.repo_path / ".claude" / d.rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


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
        report = diff_repo(base_template_root, target)
        if report.error:
            print(f"[{target.slug}] SKIPPED — {report.error}")
            continue
        if not report.diffs:
            print(f"[{target.slug}] up to date")
            continue

        print(f"[{target.slug}] {len(report.diffs)} file(s) {'to sync' if not args.apply else 'synced'}:")
        for d in report.diffs:
            print(f"    {d.status:>7}  {d.rel_path}")
        total_changed += len(report.diffs)

        if args.apply:
            apply_repo(base_template_root, report)
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
