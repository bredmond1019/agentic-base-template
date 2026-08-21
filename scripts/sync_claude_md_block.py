#!/usr/bin/env python3
"""Distribute a named managed block into every canonical CLAUDE.md in the fleet.

The `<!-- BEGIN:<name> --> ... <!-- END:<name> -->` convention in this fleet's CLAUDE.md files
(response-style, session-continuity) was hand-maintained across ~24 repos, which is how a rule
lands in some of them and not others. This makes the distribution idempotent and reviewable.

CLAUDE.md is project fact and is deliberately NOT synced by sync_downstream_harness.py -- only a
NAMED, delimited block is touched here, never the surrounding file.

Usage:
    sync_claude_md_block.py --name session-continuity --body <file> [--after response-style]
                            [--apply] [--repo-root <path>]

Default is a dry run. Worktree copies under a /trees/ path and nested repo checkouts are skipped:
they are transient, and writing to them corrupts a sibling lane's tree.
"""
import argparse
import re
import sys
from pathlib import Path


def find_brain_root(start: Path) -> Path | None:
    for c in [start.resolve(), *start.resolve().parents]:
        if (c / "brain.toml").exists():
            return c
    return None


def targets(root: Path) -> list[Path]:
    """Every canonical CLAUDE.md: tracked repos and tier sub-brains, never a worktree copy."""
    found = []
    for p in root.rglob("CLAUDE.md"):
        parts = p.relative_to(root).parts
        if any(seg in {"trees", "node_modules", "target", "archive", ".git"} for seg in parts):
            continue
        # A nested repo checkout (core/bastion/portfolio/...) repeats a top-level tier name deeper
        # in the path. Those are stray copies, not canonical files.
        if len(parts) > 3:
            continue
        found.append(p)
    return sorted(found)


def apply_block(text: str, name: str, body: str, after: str | None) -> tuple[str, str]:
    """Return (new_text, action). Never touches anything outside the named markers."""
    begin, end = f"<!-- BEGIN:{name} -->", f"<!-- END:{name} -->"
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    if pattern.search(text):
        new = pattern.sub(lambda _: body.strip(), text)
        return new, ("unchanged" if new == text else "updated")
    if after:
        anchor = f"<!-- END:{after} -->"
        if anchor in text:
            return text.replace(anchor, anchor + "\n\n" + body.strip(), 1), "inserted-after-anchor"
    return text.rstrip("\n") + "\n\n" + body.strip() + "\n", "appended"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--body", required=True, type=Path)
    ap.add_argument("--after", default=None, help="insert after this block's END marker")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument(
        "--require-anchor",
        action="store_true",
        help="skip any CLAUDE.md that carries neither this block nor the --after anchor. A file "
             "without the sibling convention is not a target -- appending to it is a drive-by "
             "edit. example-repo/qm and learn-ai/lib are the two that surface this way.",
    )
    ap.add_argument("--repo-root", default=None)
    args = ap.parse_args()

    root = Path(args.repo_root) if args.repo_root else find_brain_root(Path.cwd())
    if root is None:
        print("ERROR: no brain.toml found walking up from cwd. Pass --repo-root.", file=sys.stderr)
        return 2
    if not args.body.is_file():
        print(f"ERROR: body file {args.body} does not exist.", file=sys.stderr)
        return 2

    body = args.body.read_text(encoding="utf-8")
    counts: dict[str, int] = {}
    for path in targets(root):
        text = path.read_text(encoding="utf-8")
        new, action = apply_block(text, args.name, body, args.after)
        if args.require_anchor and action == "appended":
            action, new = "skipped-no-anchor", text
        counts[action] = counts.get(action, 0) + 1
        if action not in ("unchanged", "skipped-no-anchor"):
            print(f"{action:22} {path.relative_to(root)}")
            if args.apply:
                path.write_text(new, encoding="utf-8")

    total = sum(counts.values())
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    print(f"\n{total} CLAUDE.md file(s): {summary}")
    if not args.apply:
        print("DRY RUN — re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
