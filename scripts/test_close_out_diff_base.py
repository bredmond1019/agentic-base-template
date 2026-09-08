#!/usr/bin/env python3
"""Fixture suite for /close-out Step 0.5's diff-base resolver.

BT.ticket.close-out-diff-base-underscopes-a-multi-block-run, task 1. Both of Step 0.5's two
"HEAD is the base branch" branches underscope a multi-block run:

  - the MERGE-COMMIT branch (`.claude/commands/close-out.md` around line 114) takes
    `RANGE="HEAD^1..HEAD"` unconditionally whenever `HEAD^2` exists, with no consultation of
    any block's persisted `base_sha` at all. When several blocks land IN PLACE on the base
    branch and only the LAST one is merged in via a real merge commit, `HEAD^1` is the base
    branch's tip right before that last merge -- which already contains every earlier
    in-place block. `HEAD^1..HEAD` then reports only the last block's diff, silently.
    Measured 2026-09-04: scoped a 6-block lane to 1 block.

  - the FALLBACK branch (no merge commit) recovers a candidate `base_sha` from
    `planning/*/sdlc/sdlc-task-state.json` matching on `branch` alone, with no check that the
    candidate is actually tied to the session being closed out. A stale sibling state file
    left by an unrelated, already-closed block on the same branch name is accepted as if it
    were this session's own base, sweeping unrelated history into the reported range.
    Measured 2026-08-19 (bastion-web BW.16): matched a block that had already closed.

This suite extracts the literal, runnable Step 0.5 bash block out of
`.claude/commands/close-out.md`, builds disposable git-repo fixtures for four shapes in a temp
dir (never touching this repo's own tracked git state), runs the extracted resolver against
each with `BASE_ARG=""` (auto-resolve, matching a plain `/close-out` with no `--base`), and
asserts:

  (a) multi-block in-place chain, last block merged via a real merge commit -- the resolved
      range must span every block's commits (the furthest-back base_sha candidate still an
      ancestor of HEAD), never `HEAD^1..HEAD` alone. REGRESSION CONTROL: today's script takes
      the unconditional `HEAD^1..HEAD` path and reports a 1-commit range against a 6-commit
      chain -- this case is expected to FAIL until task 2 lands.
  (b) squash merge (no merge commit) with a STALE SIBLING state file present that matches on
      `branch` alone but ties to an unrelated, already-closed session. The resolver must
      REFUSE (non-zero exit, no guess) rather than accept it. REGRESSION CONTROL: today's
      script has no "tied to this session" check and accepts the stale sibling, producing a
      confidently-wrong range -- this case is expected to FAIL until task 2 lands.
  (c) a single in-place block with its own state file -- already-correct baseline behaviour;
      expected to PASS today and after the fix.
  (d) a state file (an `sdlc-flow-state.json`, since no historical one on disk carries
      `base_sha` yet) whose `base_sha` key is ABSENT alongside a valid task-state candidate --
      the absent-key file must be treated as "no candidate from this file", never as an error;
      resolution must still succeed off the valid candidate. Expected to PASS today (the
      current script never reads `sdlc-flow-state.json` at all, so the file is simply inert)
      and after the fix (which must skip it without erroring).

Prints one FAIL line per failing case naming the fixture shape, the expected range/verdict and
the resolved one; exits 1 if any case fails. Keep this suite's red output (task 1) as the
`observed_red` evidence when task 3 registers it in planning/harness.json.

Run directly: python3 scripts/test_close_out_diff_base.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLOSE_OUT_MD = REPO_ROOT / ".claude" / "commands" / "close-out.md"

STEP_05_RE = re.compile(r"### Step 0\.5.*?\n```bash\n(.*?)\n```", re.S)
BASE_ARG_LINE_RE = re.compile(r'^BASE_ARG="<value of --base, or empty>"$', re.M)


def extract_step_05_script() -> str:
    """Pull the literal, runnable Step 0.5 resolver script out of close-out.md."""
    text = CLOSE_OUT_MD.read_text(encoding="utf-8")
    m = STEP_05_RE.search(text)
    if not m:
        raise AssertionError(f"could not find the Step 0.5 bash block in {CLOSE_OUT_MD}")
    script = m.group(1)
    if not BASE_ARG_LINE_RE.search(script):
        raise AssertionError(
            "expected script's first line to set BASE_ARG from the doc's placeholder text; "
            "the doc may have been reworded -- update BASE_ARG_LINE_RE to match"
        )
    # Substitute the doc's placeholder with a real, empty value: every fixture below exercises
    # auto-resolution (no --base passed), same as a plain `/close-out`.
    script = BASE_ARG_LINE_RE.sub('BASE_ARG=""', script)
    if "CLOSE_OUT_RANGE" not in script or "git rev-parse" not in script:
        raise AssertionError("extracted script does not look like the Step 0.5 resolver")
    return script


STEP_05_SCRIPT = extract_step_05_script()


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}: {result.stderr}")
    return result


def init_fixture_repo(tmp: Path) -> None:
    run_git(["init", "-b", "main"], tmp)
    run_git(["config", "user.email", "close-out-fixture@example.com"], tmp)
    run_git(["config", "user.name", "Close Out Fixture"], tmp)


def write_file(tmp: Path, relpath: str, content: str) -> None:
    p = tmp / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def commit_all(tmp: Path, message: str) -> str:
    run_git(["add", "-A"], tmp)
    run_git(["commit", "-m", message], tmp)
    return run_git(["rev-parse", "HEAD"], tmp).stdout.strip()


def rev_parse(tmp: Path, ref: str) -> str:
    return run_git(["rev-parse", ref], tmp).stdout.strip()


def commit_count(tmp: Path, rng: str) -> int:
    result = subprocess.run(
        ["git", "rev-list", "--count", rng], cwd=tmp, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise AssertionError(f"git rev-list --count {rng} failed: {result.stderr}")
    return int(result.stdout.strip())


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def write_task_state(tmp: Path, spec: str, branch: str, base_sha: str, updated_at: datetime) -> None:
    write_file(
        tmp,
        f"planning/{spec}/sdlc/sdlc-task-state.json",
        json.dumps(
            {
                "branch": branch,
                "base_sha": base_sha,
                "started_at": iso(updated_at),
                "updated_at": iso(updated_at),
                "status": "done",
            },
            indent=2,
        )
        + "\n",
    )


def write_flow_state_no_base_sha(tmp: Path, spec: str, branch: str, updated_at: datetime) -> None:
    """A flow-state file in the shape every historical one on disk is in: no base_sha key."""
    write_file(
        tmp,
        f"planning/{spec}/sdlc/sdlc-flow-state.json",
        json.dumps(
            {
                "branch": branch,
                "started_at": iso(updated_at),
                "updated_at": iso(updated_at),
                "status": "done",
            },
            indent=2,
        )
        + "\n",
    )


def run_step_05(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", STEP_05_SCRIPT], cwd=repo, capture_output=True, text=True, encoding="utf-8"
    )


def resolved_range(repo: Path) -> str:
    f = repo / ".git" / "CLOSE_OUT_RANGE"
    if not f.exists():
        raise AssertionError(f"{repo}: resolver exited 0 but wrote no .git/CLOSE_OUT_RANGE")
    return f.read_text(encoding="utf-8").strip()


FAILURES: list[str] = []


def fail(shape: str, expected: str, actual: str) -> None:
    FAILURES.append(f"FAIL {shape}: expected {expected}, got {actual}")


# ---------------------------------------------------------------------------
# (a) multi-block in-place chain, last block merged via a real merge commit
# ---------------------------------------------------------------------------
def case_a_multi_block_merge_commit(tmp: Path) -> None:
    shape = "(a) multi-block-in-place-merge-commit"
    init_fixture_repo(tmp)
    write_file(tmp, "README.md", "seed\n")
    c0 = commit_all(tmp, "seed")

    # Blocks 1-5 land IN PLACE straight onto main, each with its own state file.
    prev = c0
    block_shas = []
    for n in range(1, 6):
        write_file(tmp, f"block{n}.txt", f"block {n}\n")
        sha = commit_all(tmp, f"block {n}")
        write_task_state(
            tmp,
            spec=f"spec{n}",
            branch="main",
            base_sha=prev,
            updated_at=datetime(2026, 9, 4, 10, n, 0),
        )
        run_git(["add", "-A"], tmp)
        run_git(["commit", "--amend", "--no-edit"], tmp)
        block_shas.append(rev_parse(tmp, "HEAD"))
        prev = block_shas[-1]

    # Block 6 is done on its own branch, then merged into main via a real merge commit.
    run_git(["checkout", "-b", "block6-branch"], tmp)
    write_file(tmp, "block6.txt", "block 6\n")
    b6_pre_base = rev_parse(tmp, "HEAD")
    write_task_state(tmp, spec="spec6", branch="block6-branch", base_sha=b6_pre_base, updated_at=datetime(2026, 9, 4, 10, 6, 0))
    commit_all(tmp, "block 6")

    run_git(["checkout", "main"], tmp)
    run_git(["merge", "--no-ff", "-m", "merge block 6", "block6-branch"], tmp)

    result = run_step_05(tmp)
    if result.returncode != 0:
        fail(shape, "exit 0 spanning all 6 blocks", f"exit {result.returncode}: {result.stderr.strip()}")
        return
    rng = resolved_range(tmp)
    n_commits = commit_count(tmp, rng)
    if n_commits != 6:
        fail(shape, f"range spanning 6 commits (the whole chain), never HEAD^1..HEAD alone", f"range='{rng}' spanning {n_commits} commit(s)")


# ---------------------------------------------------------------------------
# (b) squash merge with a stale sibling state file matching on branch alone
# ---------------------------------------------------------------------------
def case_b_squash_stale_sibling(tmp: Path) -> None:
    shape = "(b) squash-merge-stale-sibling"
    init_fixture_repo(tmp)
    write_file(tmp, "README.md", "seed\n")
    c0 = commit_all(tmp, "seed")

    # An unrelated, ALREADY-CLOSED block finished long before this session -- its state file
    # is the only thing that matches CURRENT_BRANCH ("main"), and it is a red herring.
    write_file(tmp, "old-block.txt", "old block\n")
    c1 = commit_all(tmp, "old block (already closed)")
    write_task_state(tmp, spec="old-spec", branch="main", base_sha=c0, updated_at=datetime(2026, 8, 1, 9, 0, 0))
    run_git(["add", "-A"], tmp)
    run_git(["commit", "--amend", "--no-edit"], tmp)

    # Unrelated history between the old block and this session's start.
    write_file(tmp, "unrelated.txt", "unrelated\n")
    session_start = commit_all(tmp, "unrelated commit, not part of any block")

    # This session's real work happens on a feature branch, squash-merged in -- no merge
    # commit, and (realistically) no state file of its own on the base branch afterward.
    run_git(["checkout", "-b", "feature-branch"], tmp)
    write_file(tmp, "feature.txt", "feature work\n")
    commit_all(tmp, "feature work")

    run_git(["checkout", "main"], tmp)
    run_git(["merge", "--squash", "feature-branch"], tmp)
    run_git(["commit", "-m", "squash-merge feature work"], tmp)

    result = run_step_05(tmp)
    if result.returncode == 0:
        rng = resolved_range(tmp)
        fail(
            shape,
            "non-zero exit (refuse rather than guess -- old-spec's base_sha is not tied to this session)",
            f"exit 0 with range='{rng}' (accepted the stale sibling)",
        )


# ---------------------------------------------------------------------------
# (c) single in-place block -- already-correct baseline
# ---------------------------------------------------------------------------
def case_c_single_block(tmp: Path) -> None:
    shape = "(c) single-block-baseline"
    init_fixture_repo(tmp)
    write_file(tmp, "README.md", "seed\n")
    c0 = commit_all(tmp, "seed")

    write_file(tmp, "block1.txt", "block 1\n")
    commit_all(tmp, "block 1")
    write_task_state(tmp, spec="spec1", branch="main", base_sha=c0, updated_at=datetime(2026, 9, 6, 9, 0, 0))
    run_git(["add", "-A"], tmp)
    run_git(["commit", "--amend", "--no-edit"], tmp)

    result = run_step_05(tmp)
    if result.returncode != 0:
        fail(shape, "exit 0 with range base_sha..HEAD (1 commit)", f"exit {result.returncode}: {result.stderr.strip()}")
        return
    rng = resolved_range(tmp)
    n_commits = commit_count(tmp, rng)
    if n_commits != 1:
        fail(shape, "range spanning exactly 1 commit", f"range='{rng}' spanning {n_commits} commit(s)")


# ---------------------------------------------------------------------------
# (d) flow-state file present with base_sha ABSENT, alongside a valid candidate
# ---------------------------------------------------------------------------
def case_d_absent_base_sha_flow_state(tmp: Path) -> None:
    shape = "(d) flow-state-absent-base-sha"
    init_fixture_repo(tmp)
    write_file(tmp, "README.md", "seed\n")
    c0 = commit_all(tmp, "seed")

    write_file(tmp, "block1.txt", "block 1\n")
    commit_all(tmp, "block 1")
    write_task_state(tmp, spec="spec1", branch="main", base_sha=c0, updated_at=datetime(2026, 9, 6, 9, 0, 0))
    # A flow-state sibling in the shape every historical one on disk is in: no base_sha key.
    # Must be treated as "no candidate from this file" -- never an error -- and must not stop
    # resolution from succeeding off spec1's valid task-state candidate.
    write_flow_state_no_base_sha(tmp, spec="spec2", branch="main", updated_at=datetime(2026, 9, 6, 9, 5, 0))
    run_git(["add", "-A"], tmp)
    run_git(["commit", "--amend", "--no-edit"], tmp)

    result = run_step_05(tmp)
    if result.returncode != 0:
        fail(
            shape,
            "exit 0 (absent base_sha key skipped as 'no candidate', not an error)",
            f"exit {result.returncode}: {result.stderr.strip()}",
        )
        return
    rng = resolved_range(tmp)
    n_commits = commit_count(tmp, rng)
    if n_commits != 1:
        fail(shape, "range spanning exactly 1 commit (off spec1's valid candidate)", f"range='{rng}' spanning {n_commits} commit(s)")


CASES = [
    case_a_multi_block_merge_commit,
    case_b_squash_stale_sibling,
    case_c_single_block,
    case_d_absent_base_sha_flow_state,
]


def main() -> int:
    if shutil.which("git") is None:
        print("SKIP: git not found on PATH")
        return 1

    for case in CASES:
        tmp_dir = tempfile.mkdtemp(prefix="close-out-diff-base-")
        try:
            case(Path(tmp_dir))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    if FAILURES:
        for line in FAILURES:
            print(line)
        print(f"\n{len(FAILURES)} of {len(CASES)} case(s) FAILED")
        return 1

    print(f"OK: all {len(CASES)} diff-base fixture case(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
