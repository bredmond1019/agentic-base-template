#!/usr/bin/env python3
"""Generate the .agents/skills/ mirror bodies from .claude/skills/ sources (BT.3.G-task2).

THE CONTRACT (planning/BT.3.G/decision.md, operator-decided 2026-09-08): a SKILL.md is
`<frontmatter block, fences included><body>`. This script replaces THE BODY ONLY, copied
verbatim from `.claude/skills/<slug>/SKILL.md`. It NEVER authors, reflows or rewrites the
frontmatter of an `.agents/` file that already has one -- that half is per-surface and is
preserved byte-for-byte, the same contract `scripts/regenerate_gemini.py` already implements
for its tail.

THE ONE AUTHORING CASE: a registry slug with a `.claude/` source and no `.agents/` file yet.
There is no frontmatter to preserve, so this script writes one -- `name`, `description`
(copied straight from the `.claude/` frontmatter, unfolded), and NO `allowed-tools` (absent
from `.agents/` in all real mirrored pairs).

THE MIRRORED SET, and the exclusion that matters most. The input set is
`AGENT_SKILL_SLUGS INTERSECT (directories under .claude/skills/)`, never AGENT_SKILL_SLUGS
alone. The registry (imported from `scripts/sync_downstream_harness.py`, never re-listed here)
holds slugs like `sdlc-task` / `sdlc-flow` with NO `.claude/skills/` source at all -- they are
the hand-authored manual-replication guides `scripts/check_skill_sync.py` hashes against the
engines. Such a slug is reported `skipped-no-source` and its `.agents/` file is left
byte-unchanged. Symmetrically, a `.claude/skills/` directory absent from the registry (e.g.
`epic`, `write-operating-doc`) is `.claude/`-only by choice and must never gain a mirror.
`CLAUDE_SKILL_SLUGS` in `sync_downstream_harness.py` is DELIBERATELY EMPTY (that file's own
docstring: `.claude/skills/` is distributed per-repo) -- this script does not read or populate it.

CLI: `python3 scripts/generate_skill_surfaces.py [--check] [--root DIR]`
Default writes. `--check` writes nothing and exits non-zero if any body would change (or a new
mirror would be created). One line per slug is printed: generated / unchanged / created /
skipped-no-source.

Usage:
  python3 scripts/generate_skill_surfaces.py            # write mode, this repo
  python3 scripts/generate_skill_surfaces.py --check     # report only, exit non-zero on drift
  python3 scripts/generate_skill_surfaces.py --root DIR  # operate against a different tree (tests)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_downstream_harness as sdh  # noqa: E402

# Anchored split of a SKILL.md into (frontmatter block, both `---` fences included) and
# (everything after it, the body). DOTALL so `.` crosses newlines inside the body.
_FRONTMATTER_RE = re.compile(r"\A(---\n.*?\n---\n)(.*)\Z", re.DOTALL)

# Pulls a single `description: <value>` scalar line out of a frontmatter block, for the one
# authoring case where no .agents/ frontmatter exists yet to copy description folding from.
_DESCRIPTION_LINE_RE = re.compile(r"^description:\s*(.+)$", re.MULTILINE)


def split_frontmatter(text: str) -> tuple[str, str] | None:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    return m.group(1), m.group(2)


def mirrored_slugs(root: Path) -> list[str]:
    """AGENT_SKILL_SLUGS intersect (directories under root/.claude/skills/), in registry order."""
    claude_dir = root / ".claude" / "skills"
    present = set()
    if claude_dir.is_dir():
        present = {p.name for p in claude_dir.iterdir() if p.is_dir()}
    return [slug for slug in sdh.AGENT_SKILL_SLUGS if slug in present]


def build_new_frontmatter(claude_frontmatter: str, slug: str) -> str:
    """The one authoring case: no .agents/ frontmatter exists to preserve, so write one.

    name + description only -- no allowed-tools, which is absent from .agents/ in every real
    mirrored pair.
    """
    m = _DESCRIPTION_LINE_RE.search(claude_frontmatter)
    description = m.group(1).strip() if m else ""
    return f"---\nname: {slug}\ndescription: {description}\n---\n"


def process_slug(root: Path, slug: str, write: bool) -> tuple[str, bool]:
    """Returns (status, changed) where status is one of the printed labels."""
    claude_path = root / ".claude" / "skills" / slug / "SKILL.md"
    agents_path = root / ".agents" / "skills" / slug / "SKILL.md"

    if not claude_path.is_file():
        # Registry slug with no .claude/ source (sdlc-task/sdlc-flow shape) -- never touched.
        return "skipped-no-source", False

    claude_text = claude_path.read_text(encoding="utf-8")
    claude_split = split_frontmatter(claude_text)
    if claude_split is None:
        raise SystemExit(f"error: {claude_path} has no anchored frontmatter block")
    _claude_frontmatter, claude_body = claude_split

    if agents_path.is_file():
        agents_text = agents_path.read_text(encoding="utf-8")
        agents_split = split_frontmatter(agents_text)
        if agents_split is None:
            raise SystemExit(f"error: {agents_path} has no anchored frontmatter block")
        agents_frontmatter, agents_body = agents_split

        if agents_body == claude_body:
            return "unchanged", False

        new_text = agents_frontmatter + claude_body
        if write:
            agents_path.write_text(new_text, encoding="utf-8")
        return "generated", True

    # Authoring case: no .agents/ file exists yet.
    new_frontmatter = build_new_frontmatter(_claude_frontmatter, slug)
    new_text = new_frontmatter + claude_body
    if write:
        agents_path.parent.mkdir(parents=True, exist_ok=True)
        agents_path.write_text(new_text, encoding="utf-8")
    return "created", True


def run(root: Path, check: bool) -> int:
    slugs = mirrored_slugs(root)
    any_changed = False
    for slug in slugs:
        status, changed = process_slug(root, slug, write=not check)
        any_changed = any_changed or changed
        print(f"{slug}: {status}")

    if check:
        return 1 if any_changed else 0
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit non-zero if any .agents/ mirror body would change",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repo root containing .claude/skills/ and .agents/skills/ (default: this repo)",
    )
    args = parser.parse_args()
    return run(args.root.resolve(), check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
