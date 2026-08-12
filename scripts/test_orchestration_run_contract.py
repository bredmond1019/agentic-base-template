#!/usr/bin/env python3
"""The D57 run-record contract checker -- the check that can fail.

WHY THIS EXISTS
----------------
D57 (planning/decisions/D57-orchestration-run-artifact-contract.md) settles the
`orchestration-run/` artifact contract: records live at
`planning/orchestration-run/<roadmap-slug>/{notes.md,review.md}`, each carries a required
frontmatter block (`roadmap`, `lane`, `run_started`, `run_ended`, `lifecycle`), each `doc_id`
must be `<repo-slug>-orchestration-run-<roadmap-slug>`, and no two records anywhere in the
fleet may share a `doc_id` -- a collision red-gates `mev validate-brain --graph` for every
concurrent lane, not just the offending repo. Nothing enforced any of this before this script;
`BT.ticket.orchestration-run-record-contract` (this ticket) is what puts a check behind it that
can actually fail.

TWO MODES
---------
`--self-test`  -- synthetic fixtures under a temp dir, no dependency on the real corpus. This is
                  what proves the checker can fail: it exercises five cases (unnamespaced doc_id,
                  roadmap/directory mismatch, duplicate doc_id, invalid lifecycle, well-formed)
                  and asserts each negative case is REJECTED and the positive case PASSES. A check
                  that cannot fail is decoration.
(default)      -- sweeps the real corpus from BRAIN_ROOT (walking up from cwd looking for
                  `brain.toml`, or `--root` to force it) and asserts the same four rules hold
                  fleet-wide. NOT registered in planning/harness.json yet -- that is task 6 of
                  this ticket, once the fleet migration (task 5) has actually run. Do not add the
                  corpus-mode invocation to any task's `validation_commands` list either: a
                  task-level array REPLACES the harness check list rather than augmenting it,
                  which is the exact mistake that bailed `BT.ticket.generate-tasks-json-on-ticket`.

DISCOVERY RULES -- the parts that have already produced wrong answers
-----------------------------------------------------------------------
- Sweep with BOTH `-L` (follow symlinks -- every repo's `planning/` is a symlink into the vault,
  INCLUDING inside worktrees) AND `-uu` (search hidden/gitignored paths -- every sub-repo under
  the brain root is gitignored from the brain's own perspective, so `-L` alone silently misses
  whole repos; that already produced a wrong fleet-wide inventory once).
- Dedup by `os.path.realpath`. A naive sweep multi-counts: the same physical file is reachable
  through more than one symlink chain (a repo's own `planning/` symlink AND, from the brain root,
  the `_planning/<repo>/` vault path it points at), so counting raw matches double- or triple-
  counts. Realpath dedup is what collapses that back to distinct files.
- This script shells out to `rg`. A piped command's `$?` is the PIPE's exit status, not `rg`'s
  (e.g. `rg ... | tail` reports the pipe's success even when `rg` itself errored) -- so this
  script never pipes `rg`'s output through another process; it captures it directly via
  `subprocess.run(..., capture_output=True)` and checks that call's own return code.

MEASURED COUNT (regression fixture, not a hard gate)
------------------------------------------------------
A `-L -uu` realpath-deduped sweep from BRAIN_ROOT on 2026-08-11 returned **31 distinct files
across 10 `orchestration-run/` directories** (base-template, learn-ai, business/bastiel,
core/bastion-web, core/claude-code-rs, core/engine-rs, core/mev, core/okf-core,
core/orchestrator, and the HQ root's own `planning/orchestration-run/`). The ticket that filed
this task was itself opened against a stale count of nine (measured 2026-08-09); the fleet moves
under concurrent lanes, so this script MEASURES the count at run time rather than hard-coding
either number, and only reports it -- it is informational, not something corpus mode fails on.

This is a GATING check once registered (task 6). A failure means a real `orchestration-run/`
record violates the D57 contract -- fix the record, do not loosen this script.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

VALID_LIFECYCLES = {"active", "lane-complete", "consolidated"}

# Path segment names that are vault/index plumbing, not a repo's own name -- skipped when
# walking upward from an `orchestration-run/<roadmap-slug>/` record to find the repo slug.
_NON_REPO_SEGMENTS = {"planning", "_planning"}


@dataclass
class Record:
    path: Path
    repo_slug: str
    dir_roadmap_slug: str
    frontmatter_roadmap: Optional[str]
    doc_id: Optional[str]
    lifecycle: Optional[str]

    @property
    def expected_doc_id(self) -> str:
        base = f"{self.repo_slug}-orchestration-run-{self.dir_roadmap_slug}"
        # notes.md carries the bare `<repo-slug>-orchestration-run-<roadmap-slug>` id (D57 section
        # 2's literal pattern); review.md carries the same id with a `-review` suffix. Two files
        # cannot legitimately share one doc_id -- `mev validate-brain --graph` indexes per FILE, so
        # a shared id is a real E_GRAPH_DUPLICATE_DOC_ID, not a modeling nuance -- and this suffix
        # is the pre-existing convention every one of the nine repos already used before migration
        # (e.g. `bastion-web-orchestration-run-notes` / `-review`).
        if self.path.name == "review.md":
            return f"{base}-review"
        return base


def find_brain_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk upward from `start` (default: cwd) looking for a directory containing brain.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "brain.toml").exists():
            return candidate
    return None


def parse_frontmatter(text: str) -> dict:
    """Minimal OKF frontmatter parser: the `key: value` lines between the leading `---` fences.

    Deliberately not a full YAML parser -- the fields this script reads (`roadmap`, `doc_id`,
    `lifecycle`) are always simple scalars in these records, never lists or nested blocks, so a
    line-oriented parse avoids taking a PyYAML dependency for three scalar reads.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            fields[key] = value
    return fields


def repo_slug_for(record_dir: Path) -> Optional[str]:
    """Repo slug for a record at `.../<repo-anchor>/orchestration-run/<roadmap-slug>/`.

    Walks upward from the roadmap-slug directory, past `orchestration-run`, then skips any
    vault/index segment names (`planning`, `_planning`) to find the first real repo-name segment.
    Handles both the vaulted layout (`_planning/<repo>/orchestration-run/...` or
    `core/_planning/<repo>/orchestration-run/...`) and the HQ root's own unvaulted layout
    (`<brain-root>/planning/orchestration-run/...`, where the repo anchor is the brain root's own
    directory name).
    """
    parts = record_dir.parts
    try:
        idx = len(parts) - 1 - parts[::-1].index("orchestration-run")
    except ValueError:
        return None
    for i in range(idx - 1, -1, -1):
        if parts[i] not in _NON_REPO_SEGMENTS:
            return parts[i]
    return None


def load_record(path: Path) -> Optional[Record]:
    """Build a Record from a `notes.md`/`review.md` under `orchestration-run/<roadmap-slug>/`.

    Returns None for files that are not migrated-layout records at all -- e.g. a flat legacy
    `orchestration-run/notes.md` (roadmap-slug dir would resolve to `orchestration-run` itself)
    or a non-notes/review artifact (`index.md`, a dated legacy file). Those are out of scope for
    this contract check; migrating them into scope is task 5's job, not this script's.
    """
    if path.name not in ("notes.md", "review.md"):
        return None
    roadmap_dir = path.parent
    if roadmap_dir.name in ("orchestration-run",) or roadmap_dir.name == "":
        return None
    repo_slug = repo_slug_for(roadmap_dir)
    if repo_slug is None:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm = parse_frontmatter(text)
    return Record(
        path=path,
        repo_slug=repo_slug,
        dir_roadmap_slug=roadmap_dir.name,
        frontmatter_roadmap=fm.get("roadmap"),
        doc_id=fm.get("doc_id"),
        lifecycle=fm.get("lifecycle"),
    )


def check_records(records: list[Record]) -> list[str]:
    """Apply the four D57 rules across a set of records; return violation strings (empty = pass)."""
    violations: list[str] = []

    # `mev validate-brain --graph` indexes per FILE, so notes.md and review.md must carry
    # DIFFERENT doc_ids (see `expected_doc_id`'s `-review` suffix) -- two files sharing one id is
    # a real E_GRAPH_DUPLICATE_DOC_ID. Dedup owners by file path so any two files (whatever their
    # names) claiming the same doc_id are caught -- e.g. two roadmaps under the same repo whose
    # slugs happened to collide.
    doc_id_owners: dict[str, set[Path]] = {}

    for rec in records:
        loc = str(rec.path)

        if rec.frontmatter_roadmap != rec.dir_roadmap_slug:
            violations.append(
                f"{loc}: roadmap frontmatter {rec.frontmatter_roadmap!r} does not match "
                f"containing directory {rec.dir_roadmap_slug!r}"
            )

        if rec.doc_id != rec.expected_doc_id:
            violations.append(
                f"{loc}: doc_id {rec.doc_id!r} does not match required "
                f"<repo-slug>-orchestration-run-<roadmap-slug> form {rec.expected_doc_id!r}"
            )

        if rec.lifecycle not in VALID_LIFECYCLES:
            violations.append(
                f"{loc}: lifecycle {rec.lifecycle!r} is not one of {sorted(VALID_LIFECYCLES)}"
            )

        if rec.doc_id:
            doc_id_owners.setdefault(rec.doc_id, set()).add(rec.path)

    for doc_id, owner_paths in doc_id_owners.items():
        if len(owner_paths) > 1:
            paths = ", ".join(str(p) for p in sorted(owner_paths))
            violations.append(
                f"doc_id {doc_id!r} is shared by {len(owner_paths)} files: {paths}"
            )

    return violations


def _sweep_with_rg(root: Path) -> Optional[list[Path]]:
    """Try `rg -L -uu --files -g '**/orchestration-run/**'`; None if no `rg` binary is on PATH.

    `-L` follows symlinks (every repo's `planning/` is one, including inside worktrees) and
    `-uu` searches hidden/gitignored paths (every sub-repo under the brain root is gitignored
    from the brain's own perspective, so `-L` alone silently misses whole repos). Captured
    directly via `subprocess.run(..., capture_output=True)` rather than piped through another
    process -- a piped command's `$?` is the pipe's exit status, not `rg`'s.
    """
    rg_bin = shutil.which("rg")
    if rg_bin is None:
        return None
    result = subprocess.run(
        [rg_bin, "-L", "-uu", "--files", "-g", "**/orchestration-run/**"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    # rg exits 1 when it finds nothing, 0 when it finds matches, >1 on a real error.
    if result.returncode not in (0, 1):
        raise RuntimeError(f"rg discovery failed (exit {result.returncode}): {result.stderr}")
    return [root / line for line in result.stdout.splitlines() if line.strip()]


def _sweep_with_walk(root: Path) -> list[Path]:
    """Pure-Python fallback sweep, used when no `rg` binary is on PATH.

    `os.walk(..., followlinks=True)` is the `-L` equivalent (descends through symlinked
    `planning/` directories). `os.walk` never consults `.gitignore` in the first place, so every
    gitignored sub-repo is visited regardless -- the `-uu` equivalent needs no extra flag here.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        if Path(dirpath).name == "orchestration-run" or "orchestration-run" in Path(dirpath).parts:
            for name in filenames:
                found.append(Path(dirpath) / name)
    return found


def discover_records(root: Path) -> tuple[list[Record], int, int]:
    """Sweep `root` for orchestration-run/ records with -L -uu, dedup by realpath.

    Returns (records, distinct_file_count, directory_count).
    """
    raw_paths = _sweep_with_rg(root)
    if raw_paths is None:
        raw_paths = _sweep_with_walk(root)

    distinct = sorted({p.resolve() for p in raw_paths})

    run_dirs: set[Path] = set()
    for p in distinct:
        parts = p.parts
        if "orchestration-run" in parts:
            idx = len(parts) - 1 - parts[::-1].index("orchestration-run")
            run_dirs.add(Path(*parts[: idx + 1]))

    records = [r for r in (load_record(p) for p in distinct) if r is not None]
    return records, len(distinct), len(run_dirs)


# ---------------------------------------------------------------------------
# --self-test: synthetic fixtures, no dependency on the real corpus.
# ---------------------------------------------------------------------------

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        FAILURES.append(name)


def _write_record(base: Path, repo: str, roadmap: str, filename: str, fm: dict, vaulted: bool = True) -> Path:
    if vaulted:
        record_dir = base / "_planning" / repo / "orchestration-run" / roadmap
    else:
        record_dir = base / "planning" / "orchestration-run" / roadmap
    record_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {filename} for {repo}/{roadmap}")
    (record_dir / filename).write_text("\n".join(lines), encoding="utf-8")
    return record_dir / filename


def self_test() -> int:
    print("test_orchestration_run_contract.py --self-test")

    # (a) unnamespaced doc_id -> REJECTED
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        path = _write_record(
            base, "demo-repo", "demo-roadmap", "notes.md",
            {
                "roadmap": "demo-roadmap",
                "lane": "C1",
                "run_started": "2026-08-11",
                "run_ended": "2026-08-11",
                "lifecycle": "active",
                "doc_id": "orchestration-run-notes",  # bare -- the learn-ai defect
            },
        )
        rec = load_record(path)
        assert rec is not None
        violations = check_records([rec])
        check("(a) unnamespaced doc_id is rejected", any("doc_id" in v for v in violations))

    # (b) roadmap frontmatter disagrees with directory -> REJECTED
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        path = _write_record(
            base, "demo-repo", "demo-roadmap", "notes.md",
            {
                "roadmap": "some-other-roadmap",
                "lane": "C1",
                "run_started": "2026-08-11",
                "run_ended": "2026-08-11",
                "lifecycle": "active",
                "doc_id": "demo-repo-orchestration-run-demo-roadmap",
            },
        )
        rec = load_record(path)
        assert rec is not None
        violations = check_records([rec])
        check("(b) roadmap/directory mismatch is rejected", any("roadmap" in v for v in violations))

    # (c) two records sharing a doc_id -> REJECTED
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        p1 = _write_record(
            base, "demo-repo", "roadmap-one", "notes.md",
            {
                "roadmap": "roadmap-one",
                "lane": "C1",
                "run_started": "2026-08-11",
                "run_ended": "2026-08-11",
                "lifecycle": "active",
                "doc_id": "demo-repo-orchestration-run-shared",
            },
        )
        p2 = _write_record(
            base, "demo-repo", "roadmap-two", "notes.md",
            {
                "roadmap": "roadmap-two",
                "lane": "C1",
                "run_started": "2026-08-11",
                "run_ended": "2026-08-11",
                "lifecycle": "active",
                "doc_id": "demo-repo-orchestration-run-shared",
            },
        )
        recs = [load_record(p1), load_record(p2)]
        assert all(r is not None for r in recs)
        violations = check_records(recs)  # type: ignore[arg-type]
        check("(c) duplicate doc_id is rejected", any("shared by" in v for v in violations))

    # (d) missing / out-of-vocabulary lifecycle -> REJECTED
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        path = _write_record(
            base, "demo-repo", "demo-roadmap", "notes.md",
            {
                "roadmap": "demo-roadmap",
                "lane": "C1",
                "run_started": "2026-08-11",
                "run_ended": "2026-08-11",
                "lifecycle": "archived",  # pre-D57 vocabulary, no longer valid
                "doc_id": "demo-repo-orchestration-run-demo-roadmap",
            },
        )
        rec = load_record(path)
        assert rec is not None
        violations = check_records([rec])
        check("(d) invalid lifecycle is rejected", any("lifecycle" in v for v in violations))

        # missing entirely
        base2 = Path(td) / "missing-lifecycle"
        path2 = _write_record(
            base2, "demo-repo", "demo-roadmap", "notes.md",
            {
                "roadmap": "demo-roadmap",
                "lane": "C1",
                "run_started": "2026-08-11",
                "run_ended": "2026-08-11",
                "doc_id": "demo-repo-orchestration-run-demo-roadmap",
            },
        )
        rec2 = load_record(path2)
        assert rec2 is not None
        violations2 = check_records([rec2])
        check("(d) missing lifecycle is rejected", any("lifecycle" in v for v in violations2))

    # (e) a well-formed record -> PASSES
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        path = _write_record(
            base, "demo-repo", "demo-roadmap", "notes.md",
            {
                "roadmap": "demo-roadmap",
                "lane": "C1",
                "run_started": "2026-08-11",
                "run_ended": "2026-08-11",
                "lifecycle": "lane-complete",
                "doc_id": "demo-repo-orchestration-run-demo-roadmap",
            },
        )
        rec = load_record(path)
        assert rec is not None
        violations = check_records([rec])
        check("(e) well-formed record passes with no violations", violations == [])

    # (f) HQ-root-style unvaulted layout still resolves the right repo slug.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "agentic-portfolio"
        path = _write_record(
            base, "unused", "demo-roadmap", "review.md",
            {
                "roadmap": "demo-roadmap",
                "lane": "C1",
                "run_started": "2026-08-11",
                "run_ended": "2026-08-11",
                "lifecycle": "active",
                "doc_id": "agentic-portfolio-orchestration-run-demo-roadmap-review",
            },
            vaulted=False,
        )
        rec = load_record(path)
        assert rec is not None
        check("(f) unvaulted HQ-root layout resolves repo_slug", rec.repo_slug == "agentic-portfolio")
        check("(f) unvaulted HQ-root layout passes", check_records([rec]) == [])

    # (g) end-to-end discovery: -L -uu realpath-deduped sweep over a synthetic fleet.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _write_record(
            base, "repo-a", "roadmap-x", "notes.md",
            {
                "roadmap": "roadmap-x", "lane": "C1", "run_started": "2026-08-11",
                "run_ended": "2026-08-11", "lifecycle": "active",
                "doc_id": "repo-a-orchestration-run-roadmap-x",
            },
        )
        _write_record(
            base, "repo-a", "roadmap-x", "review.md",
            {
                "roadmap": "roadmap-x", "lane": "C1", "run_started": "2026-08-11",
                "run_ended": "2026-08-11", "lifecycle": "active",
                "doc_id": "repo-a-orchestration-run-roadmap-x-review",
            },
        )
        _write_record(
            base, "repo-b", "roadmap-y", "notes.md",
            {
                "roadmap": "roadmap-y", "lane": "C2", "run_started": "2026-08-11",
                "run_ended": "2026-08-11", "lifecycle": "consolidated",
                "doc_id": "repo-b-orchestration-run-roadmap-y",
            },
        )
        records, distinct_count, dir_count = discover_records(base)
        check("(g) discovery finds all synthetic records", len(records) == 3)
        check("(g) discovery dedups distinct files correctly", distinct_count == 3)
        check("(g) discovery counts orchestration-run directories correctly", dir_count == 2)
        check("(g) discovered synthetic fleet passes with no violations", check_records(records) == [])

    if FAILURES:
        print(f"\n{len(FAILURES)} self-test case(s) failed: {FAILURES}")
        return 1
    print("\nall self-test cases passed")
    return 0


def corpus_mode(root: Path) -> int:
    records, distinct_count, dir_count = discover_records(root)
    print(f"discovered {distinct_count} distinct file(s) across {dir_count} orchestration-run/ "
          f"director(y/ies) (measured live; 2026-08-11 baseline was 31 files / 10 directories)")
    print(f"{len(records)} of those are migrated-layout notes.md/review.md records in scope for "
          "this check")

    violations = check_records(records)
    if violations:
        print(f"\n{len(violations)} violation(s):")
        for v in violations:
            print(f"  FAIL {v}")
        return 1

    print("\nall in-scope records satisfy the D57 contract")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run synthetic fixture cases only")
    parser.add_argument("--root", type=Path, default=None,
                         help="brain root to sweep in corpus mode (default: walk up from cwd for brain.toml)")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    root = args.root or find_brain_root() or find_brain_root(REPO_ROOT)
    if root is None:
        print("could not resolve brain root (no brain.toml found walking up from cwd or "
              "REPO_ROOT); pass --root explicitly", file=sys.stderr)
        return 2
    return corpus_mode(root)


if __name__ == "__main__":
    sys.exit(main())
