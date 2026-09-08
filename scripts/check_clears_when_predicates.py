#!/usr/bin/env python3
"""Authoring-time lint: resolve every `clears_when` command_exits_zero predicate's paths.

WHY THIS EXISTS
---------------
A `clears_when` predicate can name a path that resolves against the wrong git root, or against no
root at all, and nothing catches it until a sweep runs it and gets a wrong answer — sometimes a
FALSE CLEAR, which is the dangerous direction: a live finding is silently deleted.

Measured 2026-08-25: a predicate beginning `cd "$(git rev-parse --show-toplevel)"` resolves to
`base-template`, not the brain root, because base-template is its own git repo living inside the
brain's directory tree. Five entries in one state.json were affected in BOTH directions — two of
them wrapped the (wrong) path in `! grep ...`, so a grep against a nonexistent path failed, the `!`
negated that to exit 0, and the entry reported CLEARED while the finding was still live.

Separately, a probe written against this exact class of entry keyed on `kind` instead of `type` and
printed a confident "command_exits_zero: 0" — the discriminator for a typed `clears_when` is the
`type` key (`{"type": "command_exits_zero", "command": ..., "note": ...}`), never `kind`, which is
the field used elsewhere in a carryover entry for its own `deferred`/`defect`/`drift`/`env`
classification. A lint keyed on the wrong field finds nothing and exits clean — the same false-clean
shape this lint exists to prevent, reproduced while scoping the block that produced it.

WHAT THIS DOES
--------------
For every carryover[] entry whose `clears_when` is a typed object with `"type":
"command_exits_zero"`:
  Rule A — every repo-relative path referenced in the predicate's `command` must resolve on disk.
    A path that does not resolve is reported, naming the entry (slug/finding_id + scope) and the
    unresolved path — including the `! grep <nonexistent path>` shape, which must be reported as a
    violation rather than read as satisfied just because the shell negation would exit 0.
    A path is accepted if it resolves under EITHER this repo's own root OR the BRAIN root one
    level up (see `path_resolves()`) — this corpus does not author `cross_repo` predicates
    consistently against one fixed root, so guessing from the scope tag alone produces false
    positives; only a path that resolves under neither root is a genuine violation.
  Rule B — a predicate whose `command` contains the substring `git rev-parse --show-toplevel` is
    rejected outright, regardless of whether its paths happen to resolve, because which root that
    resolves to depends on where the predicate is evaluated from and this fleet nests git repos
    inside git repos.

Prose-string and null `clears_when` values are skipped entirely — they carry no path to resolve.
Every typed `command_exits_zero` predicate examined is counted and reported in a one-line summary,
so a run that saw none is visibly distinguishable from a run that saw many and found nothing wrong.

This is a STATIC read only. It never executes a predicate's command.

Usage:
  python3 scripts/check_clears_when_predicates.py [state.json ...] [--repo-root DIR] [--quiet]

  With no positional argument, checks this repo's own planning/state.json against this repo's own
  root (the script's own location — never `git rev-parse --show-toplevel`, which is the exact
  defect Rule B rejects). Pass one or more state.json paths to check others (e.g. a fixture tree);
  pass --repo-root to resolve their predicate paths against a different root than this script's own
  repo (needed for a self-contained fixture whose paths are relative to its own temp tree, not to
  base-template).

Exit 0 — no typed command_exits_zero predicate has an unresolved path or a git-root assumption.
Exit 1 — at least one violation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Same extension allowlist as scripts/check_spec_validation_commands.py, deliberately kept in sync
# — both lints extract path-shaped tokens out of free-form shell command strings and must agree on
# what counts as a repo-owned path candidate, not a flag value, a URL, or prose noise.
CANDIDATE_EXTENSIONS = {
    ".py", ".sh", ".js", ".md", ".json", ".yml", ".yaml", ".toml", ".ts", ".txt",
}

TOKEN_RE = re.compile(r"[A-Za-z0-9_./-]+")

GIT_TOPLEVEL_MARKER = "git rev-parse --show-toplevel"


def looks_repo_relative(token: str) -> bool:
    if not token or "/" not in token:
        return False
    return token[0] not in "-$/~"


def is_path_candidate(token: str) -> bool:
    if not looks_repo_relative(token):
        return False
    return Path(token).suffix in CANDIDATE_EXTENSIONS


def extract_path_candidates(command: str):
    """Yield path-shaped, repo-ownable tokens out of a free-form predicate command string."""
    for raw in TOKEN_RE.findall(command):
        tok = raw.strip(",;")
        if is_path_candidate(tok):
            yield tok


def entry_label(entry: dict) -> str:
    slug = entry.get("slug") or entry.get("finding_id") or "<unnamed carryover entry>"
    scope = entry.get("scope")
    if isinstance(scope, dict):
        bits = [f"{k}={v}" for k, v in scope.items() if v is not None]
        scope_str = ",".join(bits) if bits else "none"
    else:
        scope_str = "none"
    return f"{slug} (scope: {scope_str})"


def load_carryover(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        co = data.get("carryover")
        if isinstance(co, list):
            return co
    return []


def path_resolves(tok: str, repo_root: Path) -> bool:
    """A candidate path resolves if it exists relative to THIS repo's root, or — the fallback that
    matters for a `cross_repo` scoped entry — relative to the BRAIN root one level up.

    `predicate-root-resolution-is-ambiguous` is this block's own origin slug for a reason: a
    cross_repo entry's command is not evaluated the same way twice in this corpus. Some are
    authored brain-root-relative (`written-constraints-do-not-gate-installs`'s own note says so
    outright: "cwd is the brain root (scope cross_repo)" — its path
    `base-template/.claude/workflows/block.schema.json` only exists under the brain root, not
    under `<brain root>/base-template/base-template/...`). Others are explicitly `cd base-template
    && ...` or annotated "Evaluated per-repo: each repo clears its own entry"
    (`six-block-dirs-need-a-naming-decision`, `task-files-backlog-blocks-gating-the-work-assertion-
    guard`) — repo-root-relative like every non-cross_repo entry. Scope alone does not say which,
    so a path is accepted if it resolves under EITHER root rather than guessing from the scope tag;
    only a path that resolves under neither is a genuine violation.
    """
    if (repo_root / tok).exists():
        return True
    return (repo_root.parent / tok).exists()


def check_state_file(path: Path, repo_root: Path):
    """Return (violations, examined_count) for one state.json's typed command_exits_zero entries."""
    try:
        carryover = load_carryover(path)
    except Exception as e:
        return [f"{path}: unreadable ({e})"], 0

    violations = []
    examined = 0

    for entry in carryover:
        if not isinstance(entry, dict):
            continue
        clears_when = entry.get("clears_when")
        # Skip prose strings and null — only a typed object carries a `type` key at all. This is
        # the discriminator the block record's re-derivation insists on: keying on `kind` (the
        # entry's own defect/deferred/drift/env classification) matches zero entries here.
        if not isinstance(clears_when, dict):
            continue
        if clears_when.get("type") != "command_exits_zero":
            continue

        examined += 1
        command = clears_when.get("command")
        command = command if isinstance(command, str) else ""
        label = entry_label(entry)

        if GIT_TOPLEVEL_MARKER in command:
            violations.append(
                f"{path}: {label}: clears_when command assumes `{GIT_TOPLEVEL_MARKER}`, which "
                f"resolves to whichever nested repo the predicate happens to run from, not a fixed "
                f"root — command: {command!r}"
            )
            # Rejected outright per Rule B; still worth reporting any unresolved paths too, but the
            # git-root violation alone is sufficient to fail this entry, so continue to the next
            # entry rather than double-reporting the same command under Rule A as well.
            continue

        for tok in extract_path_candidates(command):
            if path_resolves(tok, repo_root):
                continue
            violations.append(
                f"{path}: {label}: clears_when path {tok!r} does not resolve under {repo_root} "
                f"or {repo_root.parent} (command: {command!r})"
            )

    return violations, examined


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "state_files",
        nargs="*",
        default=["planning/state.json"],
        help="state.json path(s) to check (default: this repo's own planning/state.json)",
    )
    ap.add_argument(
        "--repo-root",
        default=None,
        help="root to resolve predicate paths against (default: this script's own repo root, "
        "never `git rev-parse --show-toplevel`)",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else REPO_ROOT

    all_violations = []
    total_examined = 0
    files_checked = 0

    for raw_path in args.state_files:
        path = Path(raw_path)
        if not path.exists():
            if not args.quiet:
                print(f"clears-when-predicate-paths: no {path} — nothing to check there")
            continue
        files_checked += 1
        violations, examined = check_state_file(path, repo_root)
        total_examined += examined
        all_violations.extend(violations)

    print(
        f"clears-when-predicate-paths: examined {total_examined} typed command_exits_zero "
        f"predicate(s) across {files_checked} state.json file(s)"
    )

    if not all_violations:
        if not args.quiet:
            print("clears-when-predicate-paths: OK — no unresolved path or git-root assumption")
        return 0

    print(f"clears-when-predicate-paths: FAILED — {len(all_violations)} violation(s)")
    for v in all_violations:
        print(f"  {v}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
