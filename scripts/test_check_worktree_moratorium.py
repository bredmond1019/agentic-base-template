#!/usr/bin/env python3
"""Fixtures over check_worktree_moratorium.py.

Dependency-free, same discipline as scripts/test_check_block_records.py
(jsonschema is installed nowhere in this fleet).

Every case that can be asserted in both directions is: a fixture engine
carrying the --worktree parse AND a working refusal guard must PASS, and a
fixture carrying the parse with NO refusal must FAIL naming the file. A
one-directional suite cannot tell a working checker from one that passes
everything.

Case (d) -- the real engines -- asserts they PASS the checker. Task 1 of
BT.ticket.engines-must-refuse-worktree-under-D81 recorded this assertion as a
FAIL (the refusal had not landed yet); task 2 of that same spec adds the
refusal to both engines and tightens this exact assertion to expect PASS, per
the task 2 acceptance criterion that `check_worktree_moratorium.py` exits 0
against the real engines once the guard lands.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_worktree_moratorium as mod  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"[PASS] {label}")
    else:
        FAILURES.append(label)
        print(f"[FAIL] {label}" + (f" -- {detail}" if detail else ""))


FIXTURE_WITH_REFUSAL = """\
const tokens = rawArgs.split(/\\s+/)
function hasFlag(name) { return tokens.includes(name) }

const useWorktree = hasFlag('--worktree')
const resumeMode  = hasFlag('--resume')

if (useWorktree) {
  log(`ERROR: --worktree is suspended fleet-wide (D81). Run on a plain branch.`)
  return { error: '--worktree suspended (D81)', blockId }
}

const VALID_TEST_DEPTHS = ['fast', 'full']
"""

FIXTURE_NO_REFUSAL = """\
const tokens = rawArgs.split(/\\s+/)
function hasFlag(name) { return tokens.includes(name) }

const useWorktree = hasFlag('--worktree')
const resumeMode  = hasFlag('--resume')

const VALID_TEST_DEPTHS = ['fast', 'full']
const testDepthFlag = flagStr('--test-depth')
if (testDepthFlag && !VALID_TEST_DEPTHS.includes(testDepthFlag)) {
  log(`ERROR: unknown --test-depth "${testDepthFlag}".`)
  return { error: 'Invalid --test-depth', testDepthFlag, blockId }
}
"""

FIXTURE_NO_PARSE_AT_ALL = """\
const tokens = rawArgs.split(/\\s+/)
function hasFlag(name) { return tokens.includes(name) }
const resumeMode = hasFlag('--resume')
"""


def write(tmpdir: Path, name: str, content: str) -> Path:
    p = tmpdir / name
    p.write_text(content)
    return p


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)

        # (a) fixture WITH the parse AND a refusal -> PASS.
        good = write(tmpdir, "good-engine.js", FIXTURE_WITH_REFUSAL)
        err = mod.check_worktree_guard(good, "good-engine.js")
        check("fixture with parse + refusal passes", err is None, str(err))

        # (b) fixture WITH the parse, NO refusal -> FAIL, diagnostic names the file.
        bad = write(tmpdir, "bad-engine.js", FIXTURE_NO_REFUSAL)
        err = mod.check_worktree_guard(bad, "bad-engine.js")
        check("fixture with parse, no refusal fails", err is not None, "expected a failure string")
        check("failure diagnostic names the file", err is not None and "bad-engine.js" in err, str(err))

        # (b') a file that doesn't even parse --worktree also fails, distinctly.
        noparse = write(tmpdir, "no-parse-engine.js", FIXTURE_NO_PARSE_AT_ALL)
        err = mod.check_worktree_guard(noparse, "no-parse-engine.js")
        check("fixture with no --worktree parse at all fails", err is not None, "expected a failure string")

        # (c) an ABSENT engine file -> FAILURE, never a silent pass.
        missing = tmpdir / "does-not-exist.js"
        err = mod.check_worktree_guard(missing, "does-not-exist.js")
        check("missing engine file fails rather than passing vacuously", err is not None, str(err))
        check("missing-file diagnostic names the file", err is not None and "does-not-exist.js" in err, str(err))

        # main() end-to-end over the fixtures, exercising the CLI exit-code contract too.
        rc = mod.main([str(good), "--quiet"])
        check("main() exits 0 for the passing fixture", rc == 0, f"rc={rc}")
        rc = mod.main([str(bad), "--quiet"])
        check("main() exits 1 for the failing fixture", rc == 1, f"rc={rc}")

    # (d) the REAL engines, as of task 2: the refusal now landed in both -> must PASS.
    real_task = REPO_ROOT / ".claude/workflows/sdlc-task.js"
    real_flow = REPO_ROOT / ".claude/workflows/sdlc-flow.js"
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/check_worktree_moratorium.py"), "--quiet"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    check(
        "real engines (post-refusal, task 2 state) now PASS the checker",
        proc.returncode == 0,
        f"rc={proc.returncode}, stdout={proc.stdout!r}",
    )
    err_task = mod.check_worktree_guard(real_task, ".claude/workflows/sdlc-task.js")
    err_flow = mod.check_worktree_guard(real_flow, ".claude/workflows/sdlc-flow.js")
    check("sdlc-task.js refuses --worktree", err_task is None, str(err_task))
    check("sdlc-flow.js refuses --worktree", err_flow is None, str(err_flow))

    print(f"\n{'ALL PASS' if not FAILURES else f'{len(FAILURES)} FAILED'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
