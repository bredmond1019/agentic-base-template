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

DELTA ATTRIBUTION (BT.ticket.corpus-checks-delta-attribution)
---------------------------------------------------------------
Corpus mode still DISCOVERS the whole corpus -- that breadth is the point, a doc_id collision
red-gates every concurrent lane regardless of which repo wrote it. What changed is what the
EXIT CODE reflects. The corpus is written by every lane in the fleet concurrently, so gating on
the raw violation count makes base-template's pipeline depend on the authoring hygiene of repos
it does not own and cannot see (measured 2026-08-12: an `operator-surface` doc_id typo blocked
two unrelated base-template runs). This ports D64's push-gate design
(`agentic-portfolio/hooks/pre-push` stage 1, `docs/decisions/D64-push-gate-delta-attribution.md`):
compute the violation set twice -- once against the corpus as it is now, once against the corpus
as of a resolved baseline commit -- and block only on violations that are NEW relative to that
baseline. A violation present in both sets is pre-existing: reported, not blocking.

Attribution is by DELTA, never by PATH. The two violation sets are compared as whole strings
(which already embed the offending file's path), never filtered down to "files this tree
touched" -- a deletion or rename can surface a violation on a file the change never opened (e.g.
two records swapping which one legitimately owns a doc_id), and a path-scoped filter would miss
exactly that class. D64 has a test pinning the same rule; this script's --self-test case (c3)
mirrors it (task 2).

Baseline resolution (the brain repo IS the corpus's git repo -- every `planning/` dir in the
fleet, including every `core/<repo>/planning`, is tracked by the one HQ git repo per CLAUDE.md
standing rule 10, so one `git` invocation set against BRAIN_ROOT covers the whole corpus):
  1. merge-base(HEAD, upstream-tracking-branch), if HEAD has an upstream (`@{u}`) configured.
  2. Else, HEAD itself -- "the last commit reachable from it" per the ticket's task 1 wording.
     This means uncommitted local changes in the brain repo are treated as this tree's delta.
  3. Baseline UNRESOLVABLE (not a git repo, or HEAD itself doesn't resolve -- a truly fresh
     clone/init with zero commits) -- documented choice: FAIL CLOSED. Every violation found is
     treated as NEW, i.e. corpus mode falls back to the pre-delta-attribution whole-corpus-blocks
     behavior. This is printed loudly, never silent. The alternative (fail OPEN: no baseline means
     nothing can be "new", so nothing ever blocks) turns the gate into a silent no-op the moment a
     rare edge case is hit -- worse than the occasional over-block a truly baseline-less run
     produces, and the whole reason this script exists is that a check nobody trusts gets bypassed
     forever. Case (e5) in --self-test (task 2) pins this exact behavior.
"""

from __future__ import annotations

import argparse
import contextlib
import io
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


def record_from_content(path: Path, text: str) -> Optional[Record]:
    """Build a Record from a path + its already-read content -- shared by `load_record`
    (reads off disk) and `read_baseline_records` (reads via `git show <sha>:<path>`, since a
    baseline commit's tree has no filesystem path to `.read_text()`).

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
    fm = parse_frontmatter(text)
    return Record(
        path=path,
        repo_slug=repo_slug,
        dir_roadmap_slug=roadmap_dir.name,
        frontmatter_roadmap=fm.get("roadmap"),
        doc_id=fm.get("doc_id"),
        lifecycle=fm.get("lifecycle"),
    )


def load_record(path: Path) -> Optional[Record]:
    """Build a Record from a `notes.md`/`review.md` under `orchestration-run/<roadmap-slug>/`,
    reading its content off disk. See `record_from_content` for the shared parse logic.
    """
    if path.name not in ("notes.md", "review.md"):
        return None
    roadmap_dir = path.parent
    if roadmap_dir.name in ("orchestration-run",) or roadmap_dir.name == "":
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return record_from_content(path, text)


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


# ---------------------------------------------------------------------------
# Writer-command checks (BT.ticket.orchestration-record-write-time-validation task 3) -- assert
# that `/begin-orchestration` and `/orchestrate` each carry the verify-after-write step this
# ticket adds, so the step cannot silently rot out of one of the two copies (the same defect
# shape the three D16 derive prompts had -- a fix landing in N-1 of N places is the likely
# failure, so each command is asserted SEPARATELY, never with a combined any-match check).
# ---------------------------------------------------------------------------

BEGIN_ORCHESTRATION_PATH = REPO_ROOT / ".claude" / "commands" / "begin-orchestration.md"
ORCHESTRATE_PATH = REPO_ROOT / ".claude" / "commands" / "orchestrate.md"


def check_names_checker(text: str) -> bool:
    """The step must name this checker by its real script path, not a vague 'validate the
    record' instruction an agent could satisfy by reading the file and deciding it looks fine."""
    return "test_orchestration_run_contract.py" in text


def check_fix_then_rerun(text: str) -> bool:
    """On a violation, the step must instruct fixing the record and re-running the checker --
    not merely running it once and proceeding regardless of the result."""
    lower = text.lower()
    return "fix" in lower and ("re-run" in lower or "rerun" in lower)


def check_no_delete_to_pass(text: str) -> bool:
    """Deleting or emptying the record to make the checker pass must be explicitly forbidden,
    not merely never mentioned."""
    lower = text.lower()
    return "delet" in lower and ("never" in lower or "not " in lower or "not\n" in lower)


# -- synthetic fixtures: a GOOD text each check must pass, and a BAD text -- otherwise identical
# in spirit -- that must make it fail. Proving the negative is what keeps a grep-level check from
# rotting into a no-op.

_GOOD_NAMES_CHECKER = (
    "After writing the record, run `python3 scripts/test_orchestration_run_contract.py` and "
    "confirm it exits 0."
)
_BAD_NAMES_CHECKER = (
    "After writing the record, validate that it looks correct before continuing."
)

_GOOD_FIX_RERUN = (
    "On a violation attributable to the record just written, fix it (correct the doc_id, "
    "roadmap, or lifecycle field) and re-run the checker -- do not proceed with a known violation."
)
_BAD_FIX_RERUN = (
    "Run the checker once after writing the record; if it fails, note the failure in the log "
    "and continue with the run."
)

_GOOD_NO_DELETE = (
    "Deleting or emptying the record is never an acceptable way to make the check pass -- the "
    "record is the run's evidence."
)
_BAD_NO_DELETE = (
    "If the checker keeps failing on the record, delete the record and start the run fresh."
)


def case_writer_command_checks_discriminate() -> None:
    """Each of the three writer-command checks must pass its GOOD fixture and fail its BAD one --
    proof the check actually discriminates rather than always returning True."""
    check("names-checker: passes compliant text", check_names_checker(_GOOD_NAMES_CHECKER))
    check("names-checker: fails violating text", not check_names_checker(_BAD_NAMES_CHECKER))

    check("fix-then-rerun: passes compliant text", check_fix_then_rerun(_GOOD_FIX_RERUN))
    check("fix-then-rerun: fails violating text", not check_fix_then_rerun(_BAD_FIX_RERUN))

    check("no-delete-to-pass: passes compliant text", check_no_delete_to_pass(_GOOD_NO_DELETE))
    check("no-delete-to-pass: fails violating text", not check_no_delete_to_pass(_BAD_NO_DELETE))


def case_writer_commands_carry_verify_step() -> None:
    """The real `.claude/commands/begin-orchestration.md` and `.claude/commands/orchestrate.md`
    must each pass all three checks, asserted SEPARATELY per file -- a fix landing in one of the
    two copies is the likely failure, and a combined any-match assertion would hide it."""
    for label, path in (
        ("begin-orchestration.md", BEGIN_ORCHESTRATION_PATH),
        ("orchestrate.md", ORCHESTRATE_PATH),
    ):
        if not path.exists():
            check(f"{label}: file exists at {path}", False)
            continue
        text = path.read_text(encoding="utf-8")
        check(f"{label}: names the checker by its real path", check_names_checker(text))
        check(f"{label}: states fix-then-rerun behavior", check_fix_then_rerun(text))
        check(f"{label}: forbids deleting the record to pass", check_no_delete_to_pass(text))


# ---------------------------------------------------------------------------
# Roadmap-location checks (BT.ticket.roadmaps-get-a-home-and-a-registry task 4) -- assert that
# the writer (`/generate-roadmap`) emits the new `planning/roadmaps/<slug>/` location and that
# every reader (`/begin-orchestration`, `/orchestrate`, `/consolidate-run`) resolves a roadmap
# slug rather than hardcoding either location, per-file, so a fix landing in N-1 of the readers
# is caught rather than hidden behind a combined any-match assertion (the same D16-derive-prompt
# defect shape the writer-command checks above already guard against). This is NOT a new gating
# check -- it extends this script's existing scope-boundary assertions, which already read
# command files for the D57 writers.
# ---------------------------------------------------------------------------

GENERATE_ROADMAP_PATH = REPO_ROOT / ".claude" / "commands" / "generate-roadmap.md"
CONSOLIDATE_RUN_PATH = REPO_ROOT / ".claude" / "commands" / "consolidate-run.md"

ROADMAP_READER_COMMANDS = (
    ("begin-orchestration.md", BEGIN_ORCHESTRATION_PATH),
    ("orchestrate.md", ORCHESTRATE_PATH),
    ("consolidate-run.md", CONSOLIDATE_RUN_PATH),
)


def check_resolves_roadmap_location(text: str) -> bool:
    """A reader must name the new location AND acknowledge a legacy fallback -- naming only the
    new location (or only 'legacy' with no path) is what a hardcoded-not-resolved reader would
    still satisfy by accident, so both must be present together."""
    return "planning/roadmaps/" in text and "legacy" in text.lower()


def check_both_locations_is_error(text: str) -> bool:
    """The both-locations-is-an-error rule must be stated, not merely implied -- a reader that
    silently prefers one location over the other is exactly the ambiguity hazard the ticket
    calls out (a lane appending to the wrong lane log)."""
    lower = text.lower()
    return "both" in lower and "error" in lower


def check_writer_emits_new_location(text: str) -> bool:
    """The writer must instruct creating the roadmap folder at the new location."""
    return "planning/roadmaps/<slug>/" in text


# -- synthetic fixtures: a GOOD text each check must pass, and a BAD text that must fail it.

_GOOD_RESOLVES_ROADMAP = (
    "Resolve <slug> to planning/roadmaps/<slug>/ if it exists; otherwise, legacy "
    "planning/<slug>/ if that exists instead."
)
_BAD_RESOLVES_ROADMAP = (
    "Read the lane log from planning/<slug>/lane-log.jsonl."
)

_GOOD_BOTH_LOCATIONS_ERROR = (
    "A slug present in both locations is an error -- stop and report rather than silently "
    "choosing one."
)
_BAD_BOTH_LOCATIONS_ERROR = (
    "If both locations exist, prefer the new one and continue without stopping."
)

_GOOD_WRITER_NEW_LOCATION = (
    "Add the folder at planning/roadmaps/<slug>/roadmap.md, replacing the old layout."
)
_BAD_WRITER_NEW_LOCATION = (
    "Add the folder at planning/<slug>/roadmap.md."
)


def case_roadmap_location_checks_discriminate() -> None:
    """Each roadmap-location check must pass its GOOD fixture and fail its BAD one -- proof the
    check actually discriminates rather than always returning True."""
    check(
        "resolves-roadmap-location: passes compliant text",
        check_resolves_roadmap_location(_GOOD_RESOLVES_ROADMAP),
    )
    check(
        "resolves-roadmap-location: fails hardcoded-legacy-only text",
        not check_resolves_roadmap_location(_BAD_RESOLVES_ROADMAP),
    )

    check(
        "both-locations-is-error: passes compliant text",
        check_both_locations_is_error(_GOOD_BOTH_LOCATIONS_ERROR),
    )
    check(
        "both-locations-is-error: fails silent-preference text",
        not check_both_locations_is_error(_BAD_BOTH_LOCATIONS_ERROR),
    )

    check(
        "writer-emits-new-location: passes compliant text",
        check_writer_emits_new_location(_GOOD_WRITER_NEW_LOCATION),
    )
    check(
        "writer-emits-new-location: fails legacy-only text",
        not check_writer_emits_new_location(_BAD_WRITER_NEW_LOCATION),
    )


def case_writer_emits_new_roadmap_location() -> None:
    """The real `/generate-roadmap` command must instruct writing to the new location."""
    if not GENERATE_ROADMAP_PATH.exists():
        check(f"generate-roadmap.md: file exists at {GENERATE_ROADMAP_PATH}", False)
        return
    text = GENERATE_ROADMAP_PATH.read_text(encoding="utf-8")
    check("generate-roadmap.md: emits planning/roadmaps/<slug>/", check_writer_emits_new_location(text))


def case_readers_resolve_roadmap_location() -> None:
    """Each real reader command must resolve a roadmap slug rather than hardcode a path, and
    state the both-locations-is-an-error rule -- asserted SEPARATELY per file, matching the
    writer-command-checks discipline above: a fix landing in one of the three is the likely
    failure, and a combined any-match assertion would hide it."""
    for label, path in ROADMAP_READER_COMMANDS:
        if not path.exists():
            check(f"{label}: file exists at {path}", False)
            continue
        text = path.read_text(encoding="utf-8")
        check(f"{label}: resolves roadmap location (new + legacy)", check_resolves_roadmap_location(text))
        check(f"{label}: states both-locations-is-an-error", check_both_locations_is_error(text))


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


_WALK_PRUNE_DIRS = frozenset({
    ".git", "node_modules", "target", ".venv", "venv", "__pycache__",
    ".next", "dist", "build", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".cargo", ".rustup", "site-packages",
})


def _sweep_with_walk(root: Path) -> list[Path]:
    """Pure-Python fallback sweep, used when no `rg` binary is on PATH.

    `os.walk(..., followlinks=True)` is the `-L` equivalent (descends through symlinked
    `planning/` directories). `os.walk` never consults `.gitignore` in the first place, so every
    gitignored sub-repo is visited regardless -- the `-uu` equivalent needs no extra flag here.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        # Prune build/VCS trees: none can hold an orchestration-run/ record, so this changes no
        # result. Same fix and same reason as roadmap_status_discovery.py and
        # test_consolidator_discovery.py -- with `rg` unavailable as a real binary in the agent
        # sandbox this walk is the only code path, and unpruned it ran 123s, well into the range
        # that SIGKILLs an SDLC test stage.
        dirnames[:] = [d for d in dirnames if d not in _WALK_PRUNE_DIRS]
        if Path(dirpath).name == "orchestration-run" or "orchestration-run" in Path(dirpath).parts:
            for name in filenames:
                found.append(Path(dirpath) / name)
    return found


def _inside_linked_worktree(path: Path, root: Path) -> bool:
    """True when `path` sits inside a linked git worktree below `root`.

    A linked worktree's root has a `.git` FILE (gitdir pointer); a normal repo has a `.git`
    DIRECTORY. Walking up from the record to `root`, the first `.git` we meet decides it. The
    scan root itself is never treated as a linked worktree, so running the checker from inside
    one still validates that tree's own records.
    """
    try:
        rel_parent = path.resolve().parent
        root_res = root.resolve()
    except OSError:
        return False
    cur = rel_parent
    while True:
        if cur == root_res or cur == cur.parent:
            return False
        dot_git = cur / ".git"
        if dot_git.is_file():
            return True
        if dot_git.is_dir():
            return False
        cur = cur.parent


def discover_records(root: Path) -> tuple[list[Record], int, int]:
    """Sweep `root` for orchestration-run/ records with -L -uu, dedup by realpath.

    Returns (records, distinct_file_count, directory_count).
    """
    raw_paths = _sweep_with_rg(root)
    if raw_paths is None:
        raw_paths = _sweep_with_walk(root)

    distinct = sorted({p.resolve() for p in raw_paths})

    # Archived records are cold and must never gate. `/archive` moves a finished
    # `orchestration-run/<roadmap>/` under `planning/archive/`, which puts an `archive` segment
    # above `orchestration-run` -- and `repo_slug_for()` walks upward past `orchestration-run` to
    # the first non-`planning` segment, so it resolves the repo slug to `archive` and every
    # archived record reports a doc_id mismatch it can never satisfy. This is not hypothetical:
    # the 2026-08-16 fleet archive pass moved one such record and turned this check red for a
    # reason unrelated to any live contract. `check_block_naming.py` already excludes archived
    # directories for the same reason; this mirrors it.
    distinct = [p for p in distinct if "archive" not in p.parts]

    # Records inside a LINKED GIT WORKTREE are the same records, checked out a second time --
    # not a second corpus. A linked worktree's root carries a `.git` FILE (a gitdir pointer)
    # where a normal clone carries a `.git` DIRECTORY, which is what distinguishes them here.
    # HQ tracks every repo's planning/ directory itself, so a worktree of the brain root gets a
    # real second copy of every orchestration-run record on disk -- realpath dedup does NOT
    # collapse them, because they genuinely are two files.
    #
    # Measured 2026-08-22: with mev's trees/MV.ticket.op-slug-rendering-and-sweep-flow/ checked
    # out, this checker reported 97 NEW blocking duplicate-doc_id violations, every one of them
    # pairing a real record with its copy under that worktree and NONE between two real files.
    # It then attributed them to "this tree's changes", so an unrelated lane's open worktree
    # red-gated whoever ran the suite next -- and it bailed a live block that had nothing to do
    # with it. Do NOT fix this by dropping the -L symlink follow in the sweep: that follow is
    # what finds the records at all.
    distinct = [p for p in distinct if not _inside_linked_worktree(p, root)]

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


def _git_ok(args: list[str], cwd: Path) -> None:
    """Like `_run_git`, but raises loudly on failure -- fixture setup, not the thing under test."""
    rc, _, err = _run_git(args, cwd)
    assert rc == 0, f"git {args} failed in fixture setup: {err}"


def _init_git_repo(base: Path) -> None:
    """A real (but throwaway) git repo -- delta attribution's baseline resolution and
    `git show`-based reconstruction are exercised for real here, not mocked, since the whole
    point of this fixture suite is to prove the production code path (not a stand-in for it).
    """
    base.mkdir(parents=True, exist_ok=True)
    _git_ok(["init", "-q"], base)
    _git_ok(["config", "user.email", "test@example.com"], base)
    _git_ok(["config", "user.name", "Delta Attribution Fixture"], base)


def _commit_all(base: Path, message: str) -> None:
    _git_ok(["add", "-A"], base)
    _git_ok(["commit", "-q", "-m", message], base)


def _run_corpus_mode(root: Path) -> tuple[int, str]:
    """Run the real `corpus_mode` against `root`, capturing stdout (never a mock) so cases can
    assert both on the exit code and on the human-readable NEW/pre-existing labeling.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = corpus_mode(root)
    return rc, buf.getvalue()


_WELL_FORMED_FM = {
    "roadmap": "demo-roadmap",
    "lane": "C1",
    "run_started": "2026-08-11",
    "run_ended": "2026-08-11",
    "lifecycle": "active",
    "doc_id": "demo-repo-orchestration-run-demo-roadmap",
}


def _bad_lifecycle_fm() -> dict:
    fm = dict(_WELL_FORMED_FM)
    fm["lifecycle"] = "archived"  # pre-D57 vocabulary, no longer valid -- a real violation
    return fm


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

    # -----------------------------------------------------------------------------------
    # Delta attribution (BT.ticket.corpus-checks-delta-attribution task 2): all five cases
    # from the ticket's Testing Strategy, each built against a real (throwaway) git repo so
    # `resolve_baseline_commit` / `read_baseline_records` / `classify_violations` are exercised
    # for real, not mocked. Each case is paired with a proven negative so the suite cannot rot
    # into a no-op (same discipline as scripts/test_check_prompt_templates.py).
    # -----------------------------------------------------------------------------------

    # (h) Pre-existing violation reports but does not block: the bad record is already in the
    # baseline commit, and the working tree introduces no further change.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _init_git_repo(base)
        _write_record(base, "demo-repo", "demo-roadmap", "notes.md", _bad_lifecycle_fm())
        _commit_all(base, "baseline already carries the violation")
        rc, out = _run_corpus_mode(base)
        check("(h) pre-existing violation does not block (exit 0)", rc == 0)
        check("(h) pre-existing violation is labeled in output", "pre-existing" in out)

        # Proven negative: the SAME violation, but introduced only after the baseline commit
        # (i.e. genuinely new). It must NOT be reported as pre-existing/non-blocking -- proving
        # this case actually discriminates baseline-membership rather than always passing.
        base2 = Path(td) / "negative"
        _init_git_repo(base2)
        _write_record(base2, "demo-repo", "demo-roadmap", "notes.md", dict(_WELL_FORMED_FM))
        _commit_all(base2, "clean baseline")
        _write_record(base2, "demo-repo", "demo-roadmap", "notes.md", _bad_lifecycle_fm())
        rc2, out2 = _run_corpus_mode(base2)
        check("(h) negative: a newly introduced violation is NOT reported as pre-existing", rc2 == 1)

    # (i) New violation blocks: baseline is clean, the working tree introduces the violation.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _init_git_repo(base)
        _write_record(base, "demo-repo", "demo-roadmap", "notes.md", dict(_WELL_FORMED_FM))
        _commit_all(base, "clean baseline")
        _write_record(base, "demo-repo", "demo-roadmap", "notes.md", _bad_lifecycle_fm())
        rc, out = _run_corpus_mode(base)
        check("(i) new violation blocks (exit non-zero)", rc == 1)
        check("(i) new violation is labeled NEW in output", "NEW (blocking)" in out)

        # Proven negative: revert the on-disk content back to exactly the baseline (working
        # tree is now clean again) -- must return to exit 0, proving the block tracks the
        # violation state, not merely "a file's mtime changed".
        _write_record(base, "demo-repo", "demo-roadmap", "notes.md", dict(_WELL_FORMED_FM))
        rc2, _ = _run_corpus_mode(base)
        check("(i) negative: reverting to the baseline content returns to exit 0", rc2 == 0)

    # (j) By-delta, not by-path -- the load-bearing case. A duplicate-doc_id violation is
    # introduced by adding a NEW record whose doc_id collides with an EXISTING, untouched record.
    # The violation string names both files (including the one the change never opened), and a
    # path-scoped implementation that only re-checks touched files would miss it entirely.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _init_git_repo(base)
        _write_record(
            base, "repo-a", "roadmap-x", "notes.md",
            {**_WELL_FORMED_FM, "doc_id": "repo-a-orchestration-run-roadmap-x"},
        )
        _write_record(
            base, "repo-b", "roadmap-y", "notes.md",
            {**_WELL_FORMED_FM, "roadmap": "roadmap-y", "doc_id": "repo-b-orchestration-run-roadmap-y"},
        )
        _commit_all(base, "two unrelated, well-formed records")

        # The change: a NEW record (repo-c) whose doc_id collides with repo-a's UNTOUCHED record.
        colliding_path = _write_record(
            base, "repo-c", "roadmap-z", "notes.md",
            {**_WELL_FORMED_FM, "roadmap": "roadmap-z", "doc_id": "repo-a-orchestration-run-roadmap-x"},
        )
        rc, out = _run_corpus_mode(base)
        check("(j) cross-file duplicate blocks even though one owner file is untouched", rc == 1)

        # Proven negative: a deliberately PATH-SCOPED classifier -- one that only re-runs
        # check_records() over records at changed paths -- misses this violation, because the
        # collision only becomes visible when the untouched owner (repo-a's record) is included
        # in the same check_records() call. This is the exact failure mode D64 pins against.
        records, _, _ = discover_records(base)
        path_scoped_records = [r for r in records if r.path == colliding_path]
        path_scoped_violations = check_records(path_scoped_records)
        check(
            "(j) negative: a path-scoped implementation misses the cross-file collision "
            "(proves by-delta discriminates from by-path)",
            path_scoped_violations == [],
        )

    # (k) A clean tree over a dirty corpus exits 0 and states the reported-not-blocked count
    # explicitly, so a green run cannot be misread as "the whole corpus is clean".
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _init_git_repo(base)
        _write_record(base, "demo-repo", "demo-roadmap", "notes.md", _bad_lifecycle_fm())
        _write_record(
            base, "demo-repo", "other-roadmap", "notes.md",
            {**_bad_lifecycle_fm(), "roadmap": "other-roadmap",
             "doc_id": "demo-repo-orchestration-run-other-roadmap"},
        )
        _commit_all(base, "baseline with two pre-existing violations")
        rc, out = _run_corpus_mode(base)
        check("(k) clean tree over a dirty corpus exits 0", rc == 0)
        check("(k) output states the pre-existing count explicitly", "2 pre-existing" in out)

        # Proven negative: introduce one genuinely new violation on top -- must stop being "0"
        # and the summary must now report exactly 1 NEW alongside the 2 pre-existing.
        _write_record(
            base, "demo-repo", "third-roadmap", "notes.md",
            {**_bad_lifecycle_fm(), "roadmap": "third-roadmap",
             "doc_id": "demo-repo-orchestration-run-third-roadmap"},
        )
        rc2, out2 = _run_corpus_mode(base)
        check("(k) negative: adding a new violation on top stops the exit-0 result", rc2 == 1)
        check("(k) negative: summary reports 1 NEW / 2 pre-existing", "1 NEW" in out2 and "2 " in out2 and "pre-existing" in out2)

    # (l) Baseline unresolvable (no git repo at all) -- documented fallback is FAIL CLOSED:
    # every violation found is treated as NEW.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)  # deliberately NOT a git repo
        _write_record(base, "demo-repo", "demo-roadmap", "notes.md", _bad_lifecycle_fm())
        rc, out = _run_corpus_mode(base)
        check("(l) baseline-unresolvable + a violation fails closed (blocks)", rc == 1)
        check("(l) baseline-unresolvable is reported with a WARNING", "WARNING" in out and "FAIL CLOSED" in out)

        # Proven negative: baseline still unresolvable, but the corpus is well-formed -- fail
        # closed must not block UNCONDITIONALLY, only when there is an actual violation to find.
        base2 = Path(td) / "negative"
        _write_record(base2, "demo-repo", "demo-roadmap", "notes.md", dict(_WELL_FORMED_FM))
        rc2, _ = _run_corpus_mode(base2)
        check("(l) negative: baseline-unresolvable with no violations still exits 0", rc2 == 0)

    # (m) Writer-command checks (BT.ticket.orchestration-record-write-time-validation task 3):
    # the checks discriminate on synthetic fixtures, and the two real writer commands both carry
    # the verify-after-write step, asserted separately per file.
    case_writer_command_checks_discriminate()
    case_writer_commands_carry_verify_step()

    # (n) Roadmap-location family (BT.ticket.roadmaps-get-a-home-and-a-registry task 4): the
    # writer emits the new location, and every reader resolves rather than hardcodes, each
    # asserted separately against the real command files.
    case_roadmap_location_checks_discriminate()
    case_writer_emits_new_roadmap_location()
    case_readers_resolve_roadmap_location()

    if FAILURES:
        print(f"\n{len(FAILURES)} self-test case(s) failed: {FAILURES}")
        return 1
    print("\nall self-test cases passed")
    return 0


def _run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run a git command captured directly (never piped) so `$?` reflects git's own exit code,
    not a pipe's (CLAUDE.md trap 1). Never raises -- git-not-on-PATH and any other OSError are
    folded into a non-zero return so callers can treat them the same as "git said no".
    """
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
        )
    except OSError as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def resolve_baseline_commit(root: Path) -> tuple[Optional[str], str]:
    """Resolve the baseline commit for delta attribution (see module docstring for the full
    rationale). Returns (commit_sha, description) on success, or (None, reason) when
    unresolvable -- callers must treat None as "fail closed", not "no baseline == nothing new".
    """
    rc, _, _ = _run_git(["rev-parse", "--is-inside-work-tree"], root)
    if rc != 0:
        return None, f"{root} is not inside a git working tree"

    rc, head, _ = _run_git(["rev-parse", "HEAD"], root)
    if rc != 0 or not head:
        return None, "HEAD does not resolve (no commits reachable -- a truly fresh repo)"

    rc, upstream, _ = _run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], root
    )
    if rc == 0 and upstream:
        rc2, merge_base, _ = _run_git(["merge-base", "HEAD", upstream], root)
        if rc2 == 0 and merge_base:
            return merge_base, f"merge-base(HEAD, {upstream})"

    # No upstream tracking branch configured -- fall back to "the last commit reachable from
    # HEAD", i.e. HEAD itself. Anything not yet committed in the brain repo is this tree's delta.
    return head, "HEAD (no upstream tracking branch configured)"


def read_baseline_records(root: Path, baseline_sha: str) -> list[Record]:
    """Reconstruct the in-scope records as they existed at `baseline_sha`, via `git show` --
    never via `git checkout`, so this never mutates the caller's working tree or index.

    `git ls-tree -r` walks the whole tree at that commit (this repo's git root already covers
    the whole corpus per CLAUDE.md standing rule 10 -- every `planning/` dir in the fleet,
    including every `core/<repo>/planning`, is tracked by the same HQ git repo), so this needs
    no symlink-following of its own the way `discover_records`'s live filesystem sweep does.
    """
    rc, out, err = _run_git(["ls-tree", "-r", "--name-only", baseline_sha], root)
    if rc != 0:
        raise RuntimeError(f"git ls-tree failed for baseline {baseline_sha}: {err}")

    records: list[Record] = []
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel or "orchestration-run/" not in rel:
            continue
        if not (rel.endswith("/notes.md") or rel.endswith("/review.md")):
            continue
        rc2, content, err2 = _run_git(["show", f"{baseline_sha}:{rel}"], root)
        if rc2 != 0:
            # File existed in the tree listing but couldn't be read (e.g. it's a symlink entry,
            # not a blob) -- skip rather than fail the whole baseline reconstruction over it.
            continue
        # Resolved (realpath) to match `discover_records`'s own realpath-deduped paths --
        # otherwise a `root` reached through a symlink (e.g. a macOS tmp dir, or a repo path
        # itself behind a symlink) makes the same logical file compare as two different strings
        # between the current sweep and the baseline reconstruction, and every baseline record
        # looks spuriously "new". Violation-string equality in `classify_violations` depends on
        # both sides using the same path form for the same file.
        rec = record_from_content((root / rel).resolve(), content)
        if rec is not None:
            records.append(rec)
    return records


def classify_violations(current: list[str], baseline: list[str]) -> tuple[list[str], list[str]]:
    """Split `current` violations into (new, pre_existing) against the `baseline` set.

    Comparison is by the full violation string (which already embeds the offending file's path),
    never by filtering `current` down to paths this tree touched -- that is the by-delta-never-
    by-path rule: a rename/deletion can surface a violation on a file the change never opened,
    and a path-scoped filter would miss exactly that class.
    """
    baseline_set = set(baseline)
    new = [v for v in current if v not in baseline_set]
    pre_existing = [v for v in current if v in baseline_set]
    return new, pre_existing


def corpus_mode(root: Path) -> int:
    records, distinct_count, dir_count = discover_records(root)
    print(f"discovered {distinct_count} distinct file(s) across {dir_count} orchestration-run/ "
          f"director(y/ies) (measured live; 2026-08-11 baseline was 31 files / 10 directories)")
    print(f"{len(records)} of those are migrated-layout notes.md/review.md records in scope for "
          "this check")

    current_violations = check_records(records)

    baseline_sha, baseline_desc = resolve_baseline_commit(root)
    if baseline_sha is None:
        print(f"\nWARNING: baseline unresolvable ({baseline_desc}).")
        print("WARNING: falling back to FAIL CLOSED -- every violation found is treated as NEW "
              "(the pre-delta-attribution whole-corpus-blocks behavior). This is a documented "
              "edge case (a truly fresh clone/init with zero commits), not a silent no-op.")
        new_violations = current_violations
        pre_existing_violations: list[str] = []
    else:
        print(f"\nbaseline resolved: {baseline_desc} ({baseline_sha[:12]})")
        baseline_records = read_baseline_records(root, baseline_sha)
        baseline_violations = check_records(baseline_records)
        new_violations, pre_existing_violations = classify_violations(
            current_violations, baseline_violations
        )

    if current_violations:
        pre_existing_set = set(pre_existing_violations)
        print(f"\n{len(current_violations)} violation(s) found in the current corpus "
              f"({len(new_violations)} NEW / blocking, {len(pre_existing_violations)} "
              "pre-existing / not blocking):")
        for v in current_violations:
            if v in pre_existing_set:
                print(f"  pre-existing (reported, not blocking): {v}")
            else:
                print(f"  NEW (blocking): {v}")
    else:
        print("\nno violations found in the current corpus")

    if new_violations:
        print(f"\nBLOCKED: {len(new_violations)} NEW violation(s) attributable to this tree's "
              "changes.")
        return 1

    if pre_existing_violations:
        print(f"\nno NEW violations. {len(pre_existing_violations)} pre-existing violation(s) "
              "were reported above but are NOT blocking -- this is a report of what this tree "
              "did not break, not a claim the whole corpus is clean.")
    else:
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
