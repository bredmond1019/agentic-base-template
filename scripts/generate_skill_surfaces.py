#!/usr/bin/env python3
"""generate_skill_surfaces.py — derive .agents/skills/<slug>/SKILL.md mirrors from their
.claude/skills/<slug>/SKILL.md sources (BT.3.G-task2).

THE TRANSFORM (pinned by scripts/test_generate_skill_surfaces.py, BT.3.G-task1 — see that file's
module docstring for the full measured rationale): copy `name` verbatim, fold `description` into
a YAML block scalar (`description: >`, wrapped to 95 columns, each wrapped line indented two
spaces, via textwrap.wrap(break_long_words=False, break_on_hyphens=False)), DROP `allowed-tools`
entirely, and copy the body (everything after the closing `---`) byte-for-byte. Nothing else —
in particular there is no word substitution of any kind, so a literal path like `CLAUDE.md` or
`.claude/skills/` inside a mirrored body survives unchanged (the trap the block record names).

THE MIRRORED SET: `AGENT_SKILL_SLUGS INTERSECT (directories under .claude/skills/ containing a
SKILL.md)`. AGENT_SKILL_SLUGS is imported from scripts/sync_downstream_harness.py rather than
re-listed here — a second copy of the registry is a second thing to drift. Two slugs in that
registry (`sdlc-task`, `sdlc-flow`) have no `.claude/skills/` source at all: they are the
hand-authored manual-replication guides scripts/check_skill_sync.py hashes against the engines,
and this generator must never touch them — they come back as "skipped-no-source". Symmetrically a
`.claude/skills/` directory that is not in the registry (`epic`, `write-operating-doc`) must never
gain a mirror.

CLAUDE_SKILL_SLUGS in sync_downstream_harness.py is DELIBERATELY EMPTY (that file's own docstring
says so) — this script never reads it.

KNOWN DIVERGENCE (measured 2026-09-08, BT.3.G-task2): the 17 mirrors currently on disk are
hand-authored, not machine-generated, and their `description:` folding is NOT uniformly at 95
columns with hyphen-breaking disabled — several wrap at other widths, a few keep the description
on a single unfolded line, and one uses the `>-` (strip) chomping indicator instead of `>`. No
single width/break-parameter combination reproduces all 17 byte-for-byte (checked widths 70-105
against every break_long_words/break_on_hyphens combination; best case matched 7 of 13 already-
folded mirrors). This generator implements the ONE canonical transform pinned by task 1's
contract rather than overfitting per-file parameters to mask the inconsistency — running
`--check` against the real repo today will therefore report several of the 17 as needing a
regenerate. That divergence is real, pre-existing, and out of this task's file scope to fix (no
task in this block's tasks.json lists .agents/skills/*/SKILL.md as an editable path); it is
reported here rather than silently reproduced by picking a bespoke width per file, per the block
record's own instruction: "if one genuinely cannot be reproduced, stop and report it rather than
excluding it quietly."

CLI: `python3 scripts/generate_skill_surfaces.py [--check] [--root DIR]`
  (no flags)  writes every changed mirror under DIR (default: this repo's root).
  --check     writes nothing; reports what would change; exits non-zero if anything would.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_registry() -> list[str]:
    """Import AGENT_SKILL_SLUGS from sync_downstream_harness.py without re-listing it here."""
    module_path = REPO_ROOT / "scripts" / "sync_downstream_harness.py"
    spec = importlib.util.spec_from_file_location("sync_downstream_harness", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Register in sys.modules BEFORE exec — sync_downstream_harness.py defines @dataclass
    # classes, and dataclasses resolves `cls.__module__` back through sys.modules while
    # processing them, which raises AttributeError on None if the module isn't registered yet.
    sys.modules["sync_downstream_harness"] = module
    spec.loader.exec_module(module)
    return list(module.AGENT_SKILL_SLUGS)


def fold_description(description: str, width: int = 95) -> str:
    """Return the frontmatter fragment for a folded description: `description: >` followed by
    the text word-wrapped to `width` columns, each wrapped line indented two spaces."""
    wrapped = textwrap.wrap(
        description, width=width, break_long_words=False, break_on_hyphens=False
    )
    lines = ["description: >"]
    for line in wrapped:
        lines.append("  " + line)
    return "\n".join(lines) + "\n"


def compute_mirror_content(claude_skill_md: str) -> str:
    """Given the full text of a .claude/skills/<slug>/SKILL.md file, return the full text of the
    .agents/skills/<slug>/SKILL.md mirror: `name` verbatim, `description` folded, no
    `allowed-tools` line, then the body verbatim (including its leading blank line)."""
    parts = claude_skill_md.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError("SKILL.md is missing its opening/closing frontmatter fences")
    frontmatter, body = parts[1], parts[2]

    name = None
    description = None
    for line in frontmatter.splitlines():
        if line.startswith("name:"):
            name = line[len("name:"):].strip()
        elif line.startswith("description:"):
            description = line[len("description:"):].strip()

    if name is None:
        raise ValueError("SKILL.md frontmatter is missing a `name:` field")
    if description is None:
        raise ValueError("SKILL.md frontmatter is missing a `description:` field")

    return "---\n" f"name: {name}\n" + fold_description(description) + "---\n" + body


def discover_slugs(claude_skills_dir: Path, registry: list[str]) -> list[str]:
    """Slugs that are BOTH in `registry` AND a directory under `claude_skills_dir` holding a
    SKILL.md — the intersection AGENT_SKILL_SLUGS ∩ (dirs under .claude/skills/)."""
    return [
        slug for slug in registry
        if (claude_skills_dir / slug / "SKILL.md").is_file()
    ]


def run(root: Path, check: bool = False, registry: list[str] | None = None) -> dict[str, str]:
    """Generate (or, with check=True, merely report) every mirror in discover_slugs()'s set.

    Returns slug -> "generated" | "unchanged" | "skipped-no-source". A registry slug with no
    .claude/ source is reported skipped-no-source and its .agents/ file (if any) is left
    completely untouched. A .claude/ skill directory NOT in the registry is invisible to this
    function entirely — it is not a key in the returned dict and nothing under .agents/skills/
    is touched for it.
    """
    if registry is None:
        registry = _load_registry()

    claude_skills_dir = root / ".claude" / "skills"
    agent_skills_dir = root / ".agents" / "skills"

    mirrored_slugs = discover_slugs(claude_skills_dir, registry)
    statuses: dict[str, str] = {}

    for slug in mirrored_slugs:
        source_path = claude_skills_dir / slug / "SKILL.md"
        mirror_content = compute_mirror_content(source_path.read_text())
        target_path = agent_skills_dir / slug / "SKILL.md"
        current_content = target_path.read_text() if target_path.exists() else None

        if current_content == mirror_content:
            statuses[slug] = "unchanged"
        else:
            statuses[slug] = "generated"
            if not check:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(mirror_content)

    for slug in registry:
        if slug not in mirrored_slugs:
            statuses[slug] = "skipped-no-source"

    return statuses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="report what would change without writing anything; exit non-zero if anything would",
    )
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT,
        help="repo root containing .claude/skills/ and .agents/skills/ (default: this repo)",
    )
    args = parser.parse_args(argv)

    statuses = run(args.root, check=args.check, registry=None)

    changed = []
    for slug in sorted(statuses):
        status = statuses[slug]
        print(f"{slug}: {status}")
        if status == "generated":
            changed.append(slug)

    if changed:
        verb = "would change" if args.check else "changed"
        print(f"\n{len(changed)} mirror(s) {verb}: {', '.join(sorted(changed))}", file=sys.stderr)
        return 1

    print(f"\nall {len(statuses)} tracked slug(s) up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
