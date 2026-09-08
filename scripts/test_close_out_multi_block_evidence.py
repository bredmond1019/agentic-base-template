#!/usr/bin/env python3
"""Fixture evidence for the un-gateable live-run criterion on
BT.ticket.close-out-diff-base-underscopes-a-multi-block-run.

That block's fourth acceptance criterion reads:

    "A real multi-block lane closed out after the change reports a diff range spanning
    every block in the chain" -- evidence: requires a live multi-block run; gateable: false

D64: a criterion that can only be confirmed by a real, live orchestration run does not get folded
into an ordinary fixture task and marked satisfied by a green exit code -- it gets its OWN
fixture-evidence artefact, kept honestly separate from the criterion it stands in for.

WHAT THIS MODULE DOES: builds a disposable git repo reproducing the measured 2026-09-04 shape as
closely as a fixture can -- six blocks landed IN PLACE on the base branch, each with its own
sdlc-task-state.json / sdlc-flow-state.json carrying its own base_sha, with the sixth merged in via
a real `--no-ff` merge commit -- then runs the FIXED Step 0.5 resolver (extracted live out of
`.claude/commands/close-out.md`, same extraction path as scripts/test_close_out_diff_base.py) and
asserts the reported range's commit count equals the fixture's full chain length (7: six blocks'
own commits plus the merge commit itself), never the 1-commit `HEAD^1..HEAD` a merge-commit floor
alone would produce.

WHAT THIS MODULE DOES NOT DO: it does not prove the fix works on a real, live /orchestrate chain.
A fixture repo built by this script is a stand-in for that shape, assembled by this script's own
`git` calls in a temp directory -- it is not evidence that a genuine multi-block session, with its
own real timing, state-file contents and merge history, resolves the same way. THE GATEABLE:FALSE
CRITERION STAYS OPEN. It is closed only when an operator reads a real lane's `/close-out` output
("CLOSE-OUT: resolved diff range = ...") against that lane's actual `git log` and confirms every
block's commits are included -- not by this script exiting 0.

Run directly: python3 scripts/test_close_out_multi_block_evidence.py
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

BLOCK_COUNT = 6
# 6 blocks' own commits + the --no-ff merge commit that lands the last one.
EXPECTED_TOTAL_COMMITS = BLOCK_COUNT + 1


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


def run_step_05(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", STEP_05_SCRIPT], cwd=repo, capture_output=True, text=True, encoding="utf-8"
    )


def resolved_range(repo: Path) -> str:
    f = repo / ".git" / "CLOSE_OUT_RANGE"
    if not f.exists():
        raise AssertionError(f"{repo}: resolver exited 0 but wrote no .git/CLOSE_OUT_RANGE")
    return f.read_text(encoding="utf-8").strip()


def build_six_block_merge_commit_fixture(tmp: Path) -> None:
    """Reproduce the measured 2026-09-04 shape: 6 blocks in place, last one via merge commit."""
    init_fixture_repo(tmp)
    write_file(tmp, "README.md", "seed\n")
    c0 = commit_all(tmp, "seed")

    prev = c0
    for n in range(1, BLOCK_COUNT):  # blocks 1..5, landed straight onto main
        write_file(tmp, f"block{n}.txt", f"block {n}\n")
        commit_all(tmp, f"block {n}")
        write_task_state(
            tmp,
            spec=f"spec{n}",
            branch="main",
            base_sha=prev,
            updated_at=datetime(2026, 9, 4, 10, n, 0),
        )
        run_git(["add", "-A"], tmp)
        run_git(["commit", "--amend", "--no-edit"], tmp)
        prev = rev_parse(tmp, "HEAD")

    # Block 6 done on its own branch, then merged into main via a real merge commit.
    run_git(["checkout", "-b", "block6-branch"], tmp)
    write_file(tmp, "block6.txt", f"block {BLOCK_COUNT}\n")
    b6_pre_base = rev_parse(tmp, "HEAD")
    write_task_state(
        tmp,
        spec=f"spec{BLOCK_COUNT}",
        branch="block6-branch",
        base_sha=b6_pre_base,
        updated_at=datetime(2026, 9, 4, 10, BLOCK_COUNT, 0),
    )
    commit_all(tmp, f"block {BLOCK_COUNT}")

    run_git(["checkout", "main"], tmp)
    run_git(["merge", "--no-ff", "-m", f"merge block {BLOCK_COUNT}", "block6-branch"], tmp)


def main() -> int:
    if shutil.which("git") is None:
        print("SKIP: git not found on PATH")
        return 1

    tmp_dir = tempfile.mkdtemp(prefix="close-out-multi-block-evidence-")
    tmp = Path(tmp_dir)
    try:
        build_six_block_merge_commit_fixture(tmp)

        result = run_step_05(tmp)
        if result.returncode != 0:
            print(
                f"FAIL: resolver exited {result.returncode} against the {BLOCK_COUNT}-block "
                f"merge-commit fixture: {result.stderr.strip()}"
            )
            return 1

        rng = resolved_range(tmp)
        n_commits = commit_count(tmp, rng)

        if n_commits == 1:
            print(
                f"FAIL: resolved range '{rng}' spans exactly 1 commit -- this is the pre-fix "
                f"HEAD^1..HEAD answer that silently scoped a {BLOCK_COUNT}-block lane to its last "
                "block alone. The fix did not take effect."
            )
            return 1

        if n_commits != EXPECTED_TOTAL_COMMITS:
            print(
                f"FAIL: resolved range '{rng}' spans {n_commits} commit(s); expected exactly "
                f"{EXPECTED_TOTAL_COMMITS} ({BLOCK_COUNT} blocks' own commits + the merge commit)."
            )
            return 1

        print(
            f"OK: resolved range '{rng}' spans all {n_commits} commits of the "
            f"{BLOCK_COUNT}-block merge-commit fixture (evidence only -- see module docstring; "
            "the gateable:false criterion is still closed only by a real lane's live /close-out)."
        )
        return 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
