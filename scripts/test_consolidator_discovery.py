#!/usr/bin/env python3
"""Pin the discovery invariants `/consolidate-run` depends on -- the checker that can fail.

WHY THIS EXISTS
----------------
`.claude/commands/consolidate-run.md` (Step 3) specifies discovery rules that have already
produced wrong answers once in this fleet: a naive sweep silently misses gitignored sub-repos,
silently misses symlinked `planning/` directories, and double- or triple-counts the same physical
record when it is reachable through more than one symlink chain (a repo's own `planning/` symlink,
plus -- inside a worktree -- a second chain that canonicalizes onto the same vault file, e.g.
`core/engine-rs/trees/sdlc/mev/planning/orchestration-run/notes.md` canonicalizes onto
`core/mev/planning/orchestration-run/notes.md`). This script proves those three properties hold,
using synthetic fixtures for the negative cases so each assertion is proven to actually fail when
the discipline it protects is violated -- a check that cannot fail is decoration.

This is `BT.ticket.orchestration-run-run-consolidator` task 3 (D57 section 5). It pins discovery
only; it deliberately does not implement or test dedup, similarity, ranking or staleness -- those
are `mev`'s (task 4 pins that restraint against `consolidate-run.md` itself).

SCOPE-BOUNDARY CHECKS (task 4)
-------------------------------
A second, independent check family reads `.claude/commands/consolidate-run.md` itself and asserts
the restraint the ticket exists to enforce -- grep-level, per the spec's Testing Strategy, but each
one is proven to actually fail on a synthetic negative fixture so it cannot rot into a no-op (same
discipline as `scripts/test_check_prompt_templates.py`):

1. **No reimplementation.** The command states it implements no dedup/similarity/ranking/staleness
   logic of its own and names `mev` as the source it consumes instead.
2. **No state writes.** The command states it writes no `state.json` in any repo, and that its only
   sanctioned write is the `lifecycle: consolidated` stamp.
3. **D43 cited, not paraphrased.** The command references D43 by name/path. The historical defect
   phrase `P0 = blocks other work` may appear only when flagged as the contradictory counter-example
   it is (the word `contradictory` nearby) -- never asserted as the document's own rubric.
4. **New carryover shape only.** `priority`, `blocks[]`, `clears_when` and `finding_id` are all
   named; `blocking: bool` may appear only inside an explicit prohibition (`no`/`never` nearby), never
   as a field the document instructs writing.
5. **Never auto-merges.** The command states the matcher only suggests -- it never merges findings
   on its own authority.

TWO MODES
---------
`--self-test`  -- synthetic fixtures under a temp dir: (a) realpath dedup collapsing a worktree
                  alias, (b) `-uu` discovering a gitignored sub-repo, (c) `-L` traversing a
                  symlinked `planning/`. Each fixture also proves the corresponding negative:
                  path-string dedup double-counts, a sweep without `-uu` misses the gitignored
                  fixture, a sweep without `-L` misses the symlinked fixture.
(default)      -- measures the real corpus from BRAIN_ROOT (walking up from cwd for `brain.toml`,
                  or `--root` to force it) with the exact command this docstring records, and
                  asserts the RELATION the spec calls for (naive count > distinct count, and every
                  hit routed through a `/trees/` segment collapses onto a non-`trees/` realpath) --
                  not a hard equality, because the fleet moves under concurrent lanes and a
                  constant would break on every new run record.

MEASURED SNAPSHOT (dated, not a magic constant)
------------------------------------------------
Measured 2026-08-12 from the brain root (`/Users/brandon/Dev/agentic-portfolio`) with:

    rg -L -uu --files -g '**/orchestration-run/**/*.md'

Result: **86** hits, **34** distinct files after `realpath` dedup, **20** of the 86 hits routed
through a `/trees/` segment -- every one of those 20 collapses onto a non-`trees/` realpath already
present in the distinct set. (The spec's Testing Strategy pins 65/23, and the ticket's own Amendment
Log already corrected that once to 84/33/20 on 2026-08-12 before `BT.ticket.orchestration-run-
record-contract` task 5's fleet migration landed a few more records; this script does not pin
either stale pair -- see the relation-only assertion above.)

DISCOVERY RULES CITED FROM `consolidate-run.md` STEP 3
---------------------------------------------------------
- `-L` (follow symlinks) -- every repo's `planning/` is a symlink into the vault, including inside
  worktrees.
- `-uu` (search hidden/gitignored paths) -- every sub-repo under the brain root is gitignored from
  the brain's own perspective; `-L` alone silently misses whole repos.
- Dedup by `realpath`, before reading -- path-string dedup triple-counts and can retain a stale
  worktree copy instead of the vault original.
- This script shells out to `rg` and captures output directly via
  `subprocess.run(..., capture_output=True)`, never through a pipe -- a piped command's `$?` is the
  pipe's exit status, not `rg`'s.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

MEASURED_DATE = "2026-08-12"
MEASURING_COMMAND = "rg -L -uu --files -g '**/orchestration-run/**/*.md'"


def find_brain_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk upward from `start` (default: cwd) looking for a directory containing brain.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "brain.toml").exists():
            return candidate
    return None


def _sweep_with_rg(root: Path, follow_symlinks: bool, hidden: bool) -> Optional[list[str]]:
    """Try a real `rg --files` sweep; None if no `rg` binary is on PATH.

    Captured via `subprocess.run(..., capture_output=True)` directly -- never piped -- so this
    script checks `rg`'s own exit code, not a pipe's (CLAUDE.md trap 1).
    """
    rg_bin = shutil.which("rg")
    if rg_bin is None:
        return None
    args = [rg_bin]
    if follow_symlinks:
        args.append("-L")
    if hidden:
        args.append("-uu")
    args += ["--files", "-g", "**/orchestration-run/**/*.md"]
    result = subprocess.run(args, cwd=root, capture_output=True, text=True)
    # rg exits 1 when it finds nothing, 0 when it finds matches, >1 on a real error.
    if result.returncode not in (0, 1):
        raise RuntimeError(f"rg discovery failed (exit {result.returncode}): {result.stderr}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def _gitignored_prefixes(root: Path) -> list[Path]:
    """Pure-Python `-uu`-equivalent bookkeeping: every directory a `.gitignore` excludes.

    Minimal by design -- reads simple `.gitignore` lines like `/planning` or `planning/` relative
    to the directory the `.gitignore` lives in. Good enough for this test's own fixtures; not a
    general gitignore engine.
    """
    prefixes: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=True):
        if ".gitignore" not in filenames:
            continue
        gi = Path(dirpath) / ".gitignore"
        for line in gi.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            prefixes.append((Path(dirpath) / line.strip("/")).resolve())
    return prefixes


# Directories the fallback walk never needs to descend into. None can contain an
# orchestration-run/ record, so pruning them changes no result -- it removes only the build and
# VCS trees that dominate an unpruned walk of the fleet. Same fix, same reason, as
# roadmap_status_discovery.py: with `rg` unavailable as a real binary in the agent sandbox this
# walk is the ONLY code path, and unpruned it ran 1m45s and timed out the SDLC test stage.
_WALK_PRUNE_DIRS = frozenset({
    ".git", "node_modules", "target", ".venv", "venv", "__pycache__",
    ".next", "dist", "build", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".cargo", ".rustup", "site-packages",
})


def _sweep_with_walk(root: Path, follow_symlinks: bool, hidden: bool) -> list[str]:
    """Pure-Python fallback sweep, used when no `rg` binary is on PATH.

    `os.walk(..., followlinks=...)` is the `-L` equivalent. `os.walk` never consults `.gitignore`
    on its own (so it is `-uu`-equivalent by default); when `hidden=False` this fallback excludes
    anything under a directory a `.gitignore` names, to keep the `-uu` negative case meaningful
    even without a real `rg` binary.
    """
    ignored = [] if hidden else _gitignored_prefixes(root)
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        dirnames[:] = [d for d in dirnames if d not in _WALK_PRUNE_DIRS]
        if not hidden:
            dp = Path(dirpath).resolve()
            if any(dp == p or p in dp.parents for p in ignored):
                dirnames[:] = []
                continue
        if Path(dirpath).name == "orchestration-run" or "orchestration-run" in Path(dirpath).parts:
            for name in filenames:
                if name.endswith(".md"):
                    found.append(str((Path(dirpath) / name).relative_to(root)))
    return found


def sweep_paths(root: Path, follow_symlinks: bool, hidden: bool) -> list[str]:
    """Raw sweep hits (relative path strings, NOT deduped) for orchestration-run/*.md.

    Prefers a real `rg -L -uu --files -g '**/orchestration-run/**/*.md'` invocation; falls back to
    a pure-Python walk (mirroring `test_orchestration_run_contract.py`'s `_sweep_with_walk`) when
    no `rg` binary is on PATH, so this check works the same in a sandboxed shell where `rg` is only
    a shell function, not an executable `subprocess.run` can invoke.
    """
    hits = _sweep_with_rg(root, follow_symlinks, hidden)
    if hits is not None:
        return hits
    return _sweep_with_walk(root, follow_symlinks, hidden)


def realpath_dedup(root: Path, hits: list[str]) -> list[Path]:
    """Dedup raw hits by `os.path.realpath`, returning the sorted distinct realpaths."""
    return sorted({Path(os.path.realpath(root / h)) for h in hits})


# ---------------------------------------------------------------------------
# Scope-boundary checks (task 4) -- read `.claude/commands/consolidate-run.md` and assert the
# restraint the ticket exists to enforce. Grep-level by design (per the spec's Testing Strategy),
# but every one is proven against a synthetic negative fixture in `self_test()` below.
# ---------------------------------------------------------------------------

COMMAND_DOC_PATH = REPO_ROOT / ".claude" / "commands" / "consolidate-run.md"


def read_command_doc() -> str:
    return COMMAND_DOC_PATH.read_text(encoding="utf-8")


def check_no_reimplementation(text: str) -> bool:
    """The doc must state it implements no dedup/similarity/ranking/staleness logic of its own,
    and must name `mev` as the thing it consumes instead of reimplementing."""
    lower = text.lower()
    prohibits = "no dedup" in lower or "implements **no**" in text
    names_mev_as_source = "mev" in lower and (
        "consumes" in lower or "never recomputes" in lower or "already building" in lower
    )
    return prohibits and names_mev_as_source


def check_no_state_writes(text: str) -> bool:
    """The doc must state it writes no state.json in any repo, and name the lifecycle stamp as
    the only sanctioned write."""
    lower = text.lower()
    prohibits_state_write = "writes no `state.json`" in lower or "writes no state.json" in lower
    names_only_write = "lifecycle: consolidated" in text
    return prohibits_state_write and names_only_write


def check_d43_cited_not_paraphrased(text: str) -> bool:
    """D43 must be cited. The historical defect phrase `P0 = blocks other work` may appear only
    when flagged nearby as the contradictory counter-example it is -- never asserted bare as the
    document's own rubric."""
    if "D43" not in text:
        return False
    idx = text.find("P0 = blocks other work")
    if idx == -1:
        return True
    window = text[max(0, idx - 200): idx]
    return "contradictory" in window


def check_new_carryover_shape(text: str) -> bool:
    """`priority`, `blocks[]`, `clears_when` and `finding_id` must all be named. `blocking: bool`
    may appear only inside an explicit prohibition (`no`/`never` nearby), never as an instruction
    to write it."""
    required_fields = ["priority", "blocks[]", "clears_when", "finding_id"]
    if not all(f in text for f in required_fields):
        return False
    lower = text.lower()
    idx = lower.find("blocking: bool")
    if idx == -1:
        return True
    window = lower[max(0, idx - 80): idx]
    return "no" in window or "never" in window


def check_never_auto_merges(text: str) -> bool:
    """The doc must state the matcher only suggests -- it never merges findings on its own
    authority."""
    lower = text.lower()
    return "never auto-merges" in lower or "never auto-merge" in lower


# ---------------------------------------------------------------------------
# --self-test: synthetic fixtures, no dependency on the real corpus.
# ---------------------------------------------------------------------------

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        FAILURES.append(name)


def _write_dummy_record(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nroadmap: demo\nlane: C1\nrun_started: 2026-08-12\nrun_ended: 2026-08-12\n"
        "lifecycle: active\ndoc_id: demo-repo-orchestration-run-demo\n---\n\n# demo record\n",
        encoding="utf-8",
    )


def case_realpath_dedup_collapses_worktree_copy() -> None:
    """(a) A `trees/<x>/` symlink chain onto a vault record must collapse under realpath dedup,
    and the retained path must be the vault original, not the worktree alias."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        vault_record = base / "core" / "mev" / "planning" / "orchestration-run" / "demo" / "notes.md"
        _write_dummy_record(vault_record)

        # Simulate the worktree alias: core/engine-rs/trees/sdlc/mev/planning/... symlinked onto
        # the same physical planning/ directory the vault record lives under.
        worktree_planning_parent = base / "core" / "engine-rs" / "trees" / "sdlc" / "mev"
        worktree_planning_parent.mkdir(parents=True, exist_ok=True)
        (worktree_planning_parent / "planning").symlink_to(vault_record.parent.parent.parent, target_is_directory=True)

        raw = sweep_paths(base, follow_symlinks=True, hidden=True)
        check("(a) naive sweep sees both the vault path and the worktree alias", len(raw) == 2)

        path_string_dedup = sorted(set(raw))
        check(
            "(a) path-string dedup double-counts (fails to collapse the alias)",
            len(path_string_dedup) == 2,
        )

        distinct = realpath_dedup(base, raw)
        check("(a) realpath dedup collapses to one distinct file", len(distinct) == 1)
        check(
            "(a) the retained realpath is the vault original, not the worktree alias",
            "/trees/" not in str(distinct[0]) and distinct[0] == vault_record.resolve(),
        )


def case_uu_finds_gitignored_subrepo() -> None:
    """(b) A record under a gitignored `planning/` (a `.gitignore` with `/planning`) must be
    found with `-uu` and missed without it."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo = base / "core" / "mev"
        (repo).mkdir(parents=True, exist_ok=True)
        (repo / ".gitignore").write_text("/planning\n", encoding="utf-8")
        record = repo / "planning" / "orchestration-run" / "demo" / "notes.md"
        _write_dummy_record(record)

        without_uu = sweep_paths(base, follow_symlinks=True, hidden=False)
        check("(b) sweep without -uu misses the gitignored record", len(without_uu) == 0)

        with_uu = sweep_paths(base, follow_symlinks=True, hidden=True)
        check("(b) sweep with -uu finds the gitignored record", len(with_uu) == 1)


def case_l_traverses_symlinked_planning() -> None:
    """(c) A record reachable ONLY through a symlinked `planning/` must be found with `-L` and
    missed without it. The vault storage lives OUTSIDE the swept root entirely -- reachable solely
    via the symlink -- so a walk that does not follow symlinks has no other path to it at all."""
    with tempfile.TemporaryDirectory() as outer_td, tempfile.TemporaryDirectory() as td:
        vault_target = Path(outer_td) / "vault" / "demo-repo"
        record = vault_target / "orchestration-run" / "demo" / "notes.md"
        _write_dummy_record(record)

        base = Path(td)
        repo = base / "demo-repo"
        repo.mkdir(parents=True, exist_ok=True)
        (repo / "planning").symlink_to(vault_target, target_is_directory=True)

        without_l = sweep_paths(base, follow_symlinks=False, hidden=True)
        check("(c) sweep without -L misses the symlinked planning/ record", len(without_l) == 0)

        with_l = sweep_paths(base, follow_symlinks=True, hidden=True)
        check("(c) sweep with -L finds the record through symlinked planning/", len(with_l) == 1)


def case_live_measured_snapshot() -> int:
    """(d) Live, dated measurement from BRAIN_ROOT. Asserts the RELATION (naive > distinct, every
    `/trees/` hit collapses onto a non-`trees/` realpath), never a hard equality -- a constant
    would break on every new orchestration-run record landed by a concurrent lane.

    Returns the process exit status contribution: 0 if brain root could not be resolved (this
    property is then simply skipped, not failed -- a clone of just this repo has no brain root to
    measure against), else the number of failed checks.
    """
    root = find_brain_root() or find_brain_root(REPO_ROOT)
    if root is None:
        print(
            "  skip (d) live measured snapshot: no brain.toml found walking up from cwd or "
            f"{REPO_ROOT} -- this property only applies inside the agentic-portfolio brain root"
        )
        return 0

    print(f"  measuring from {root} with: {MEASURING_COMMAND}  (dated {MEASURED_DATE})")
    raw = sweep_paths(root, follow_symlinks=True, hidden=True)
    naive = len(raw)
    distinct = realpath_dedup(root, raw)
    print(f"  naive={naive} distinct={len(distinct)}")

    trees_hits = [h for h in raw if "/trees/" in h]
    non_collapsing = [h for h in trees_hits if "/trees/" in str(Path(os.path.realpath(root / h)))]

    check(
        "(d) naive count exceeds realpath-distinct count (some duplication exists)",
        naive > len(distinct),
    )
    check(
        "(d) every /trees/-routed hit collapses onto a non-trees/ realpath",
        len(non_collapsing) == 0,
    )
    return 0


# -- synthetic fixtures for the scope-boundary checks: a GOOD text each check must pass, and a
# BAD text -- otherwise identical in spirit -- that must make it fail. Proving the negative is
# what keeps a grep-level check from rotting into a no-op.

_GOOD_NO_REIMPL = (
    "This command implements **no** dedup, similarity matching, priority ranking, or staleness "
    "logic of its own. `mev` is already building all three; this command calls `mev carryover` "
    "and consumes its output rather than shipping a second implementation."
)
_BAD_NO_REIMPL = (
    "This command sorts findings by a cosine-similarity score and merges near-duplicates "
    "automatically before proposing them."
)

_GOOD_NO_STATE = (
    "This command writes no `state.json` in any repo. The only write it makes is stamping "
    "`lifecycle: consolidated` on the records it consumed."
)
_BAD_NO_STATE = (
    "This command writes state.json in every repo it touches, updating carryover[] directly "
    "with the merged findings."
)

_GOOD_D43 = (
    "Cite D43 for the priority rubric; never paraphrase it. Restating D43's rubric is exactly "
    'how a stray file came to assert the contradictory "P0 = blocks other work" -- a divergence '
    "nothing caught."
)
_BAD_D43 = (
    "Cite D43. Priority follows a simple rule: P0 = blocks other work, P1 = blocks this repo "
    "only, P2 = routine, P3 = cosmetic."
)

_GOOD_CARRYOVER = (
    "Proposed entries carry priority, blocks[], a typed clears_when predicate, and finding_id. "
    "There is no `blocking: bool` field anywhere in a proposed entry."
)
_BAD_CARRYOVER = (
    "Proposed entries carry priority, blocks[], a typed clears_when predicate, and finding_id. "
    "Each proposed entry sets blocking: bool to true when it blocks other work."
)

_GOOD_NO_MERGE = (
    "Never auto-merges. The matcher mev runs only suggests links between findings; this command "
    "never merges two proposed entries into one on its own authority."
)
_BAD_NO_MERGE = (
    "This command automatically merges duplicate findings identified by mev's matcher before "
    "emitting the consolidated review."
)


def case_scope_boundary_checks() -> None:
    """Each of the five boundary checks must pass its GOOD fixture and fail its BAD one -- proof
    the check actually discriminates rather than always returning True."""
    check("no-reimplementation: passes compliant text", check_no_reimplementation(_GOOD_NO_REIMPL))
    check("no-reimplementation: fails violating text", not check_no_reimplementation(_BAD_NO_REIMPL))

    check("no-state-writes: passes compliant text", check_no_state_writes(_GOOD_NO_STATE))
    check("no-state-writes: fails violating text", not check_no_state_writes(_BAD_NO_STATE))

    check("d43-cited-not-paraphrased: passes compliant text", check_d43_cited_not_paraphrased(_GOOD_D43))
    check("d43-cited-not-paraphrased: fails paraphrased text", not check_d43_cited_not_paraphrased(_BAD_D43))

    check("new-carryover-shape: passes compliant text", check_new_carryover_shape(_GOOD_CARRYOVER))
    check("new-carryover-shape: fails violating text", not check_new_carryover_shape(_BAD_CARRYOVER))

    check("never-auto-merges: passes compliant text", check_never_auto_merges(_GOOD_NO_MERGE))
    check("never-auto-merges: fails violating text", not check_never_auto_merges(_BAD_NO_MERGE))


def case_command_doc_meets_boundary_checks() -> None:
    """The real `.claude/commands/consolidate-run.md` must itself pass all five checks -- the
    synthetic fixtures above prove the checks discriminate; this proves the actual command file
    honours the restraint they check for."""
    if not COMMAND_DOC_PATH.exists():
        check(f"command doc exists at {COMMAND_DOC_PATH}", False)
        return
    text = read_command_doc()
    check("consolidate-run.md: no reimplementation", check_no_reimplementation(text))
    check("consolidate-run.md: no state.json writes", check_no_state_writes(text))
    check("consolidate-run.md: D43 cited, not paraphrased", check_d43_cited_not_paraphrased(text))
    check("consolidate-run.md: new carryover shape only", check_new_carryover_shape(text))
    check("consolidate-run.md: never auto-merges", check_never_auto_merges(text))


def self_test() -> int:
    print("test_consolidator_discovery.py --self-test")
    case_realpath_dedup_collapses_worktree_copy()
    case_uu_finds_gitignored_subrepo()
    case_l_traverses_symlinked_planning()
    case_live_measured_snapshot()
    case_scope_boundary_checks()
    case_command_doc_meets_boundary_checks()

    if FAILURES:
        print(f"\n{len(FAILURES)} self-test case(s) failed: {FAILURES}")
        return 1
    print("\nall self-test cases passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run synthetic fixture cases only")
    parser.add_argument("--root", type=Path, default=None,
                         help="brain root to measure in default mode (default: walk up from cwd for brain.toml)")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    root = args.root or find_brain_root() or find_brain_root(REPO_ROOT)
    if root is None:
        print("could not resolve brain root (no brain.toml found walking up from cwd or "
              "REPO_ROOT); pass --root explicitly", file=sys.stderr)
        return 2

    print(f"test_consolidator_discovery.py: measuring {root}")
    rc = case_live_measured_snapshot()
    case_command_doc_meets_boundary_checks()
    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("\nall discovery invariants hold")
    return rc


if __name__ == "__main__":
    sys.exit(main())
