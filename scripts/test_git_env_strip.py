#!/usr/bin/env python3
"""Fixture suite for the nine-variable git-environment strip added by
BT.ticket.worktree-run-can-commit-an-empty-tree, task 3/4 (the `GIT` prefix constant in
`.claude/workflows/sdlc-flow.js` and `.claude/workflows/sdlc-task.js`).

This is the D64 fixture-evidence for the one criterion this repo's checks structurally cannot
observe: that the engines' nine-variable list still matches mev's `GIT_REPO_ENV_VARS`
(`core/mev/src/shared.rs:103`). That evidence lives in ANOTHER REPO, so no in-repo check can gate
it -- the pinned list below plus the recorded manual sweep command are the fixture standing in for
the missing gate. A green suite here is NOT itself proof the lists still agree; re-run the manual
command:

    grep -n -A 12 'GIT_REPO_ENV_VARS' ../core/mev/src/shared.rs

against mev's SOURCE (never an installed `mev` binary -- the two diverge and the divergence is
invisible unless this command is actually run).

Four assertion groups:
  (a) both engines define the GIT constant and the two strings are byte-identical.
  (b) the constant unsets exactly the nine pinned variable names, in order.
  (c) a source scan of both engines finds no UNPREFIXED executable git invocation in any recipe
      line -- using an explicit, commented allowlist for prose/prohibition lines rather than a
      loose regex. Every allowlist pattern must actually match something in the corpus, or the
      exemption is stale and the check fails (so a widened allowlist can't silently swallow a
      real regression).
  (d) a positive control: the same commit, run through the extracted GIT prefix against a
      GIT_INDEX_FILE-poisoned scratch repo, lands a full tree; run WITHOUT the prefix, it lands an
      empty tree -- proving this suite can actually tell prefixed from unprefixed.

Registered in planning/harness.json as `git-env-strip-tests` --
run directly: python3 scripts/test_git_env_strip.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE_FILES = {
    "sdlc-flow.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js",
    "sdlc-task.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js",
}

# Pinned per core/mev/src/shared.rs:103 GIT_REPO_ENV_VARS -- the upstream source of this list.
# PORTED, never re-derived; a future edit to either side must be checked against the other by
# hand (grep -n -A 12 'GIT_REPO_ENV_VARS' ../core/mev/src/shared.rs), since that repo is outside
# this one's reach.
EXPECTED_VARS = [
    "GIT_DIR",
    "GIT_COMMON_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
    "GIT_CEILING_DIRECTORIES",
]

GIT_CONST_RE = re.compile(r"^const GIT = '([^']*)'", re.MULTILINE)


def extract_git_const(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = GIT_CONST_RE.search(text)
    if not m:
        raise AssertionError(f"const GIT = '...' definition not found in {path}")
    return m.group(1)


def run(cmd, cwd, env=None, check=True):
    return subprocess.run(
        cmd, cwd=str(cwd), env=env, capture_output=True, text=True, check=check,
        shell=isinstance(cmd, str),
    )


def init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q"], cwd=path)
    run(["git", "config", "user.email", "t@t"], cwd=path)
    run(["git", "config", "user.name", "t"], cwd=path)


# ---------------------------------------------------------------------------------------------
# (c) source scan: no unprefixed executable git invocation in any recipe line.
# ---------------------------------------------------------------------------------------------

# A candidate line: the word "git" followed by a subcommand this repo's engines actually
# execute, NOT immediately preceded by the ${GIT} prefix constant.
CANDIDATE_RE = re.compile(
    r"(?<!\$\{GIT\}\s)"
    r"\bgit\s+"
    r"(add|commit|checkout|switch|branch|worktree|rev-parse|ls-tree|ls-files|"
    r"status|diff|log|push|pull|remote|config|sparse-checkout)\b"
)

# Explicit, commented allowlist. Each entry is (label, regex, "why this is prose, not an
# executable invocation"). Every entry must match at least one candidate line across the two
# engines, or it is stale and the check fails -- see module docstring.
ALLOWLIST = [
    (
        "js-comment",
        re.compile(r"^\s*//"),
        "a `//` line comment -- never executed.",
    ),
    (
        "escaped-backtick-prohibition",
        re.compile(r"\\`git"),
        "a prose prohibition inside a prompt template, backtick-escaped per standing rule 6 "
        "(e.g. 'do NOT run \\`git add\\`, \\`git commit\\`, ...') -- reproduces the forbidden "
        "command as TEXT for the agent to read, never runs it.",
    ),
    (
        "never-prohibition",
        re.compile(r"(?i)never[a-z .]{0,25}\bgit\s"),
        "a 'never git add -A' / 'NEVER git add -A, git add ., git reset, ...' style prohibition "
        "sentence -- instructs the agent NOT to run the bare form, itself never executed.",
    ),
    (
        "manual-instruction-to-human",
        re.compile(r"(?i)(manually|not guess|never guess|integrate it when ready)"),
        "a log() message telling the OPERATOR what to type by hand (e.g. after a failed PR "
        "creation, or when discovering a worktree externally) -- the engine prints this string, "
        "it does not execute the git command inside it.",
    ),
    (
        "noun-phrase-worktree-or-branch",
        re.compile(r"(?i)\b(isolated|plain|linked) git (worktree|branch)\b"),
        "a descriptive noun phrase ('ONE isolated git worktree' / 'ONE plain git branch' / "
        "'a linked git worktree') in a recipe's title-line or explanatory description, not a "
        "command.",
    ),
    (
        "workspace-state-list",
        re.compile(r"harness-created workspace state \(git worktree"),
        "'harness-created workspace state (git worktree, sparse-checkout, ...)' -- a list of "
        "noun phrases describing what was set up, not a command being run.",
    ),
    (
        "conditional-git-add-failure",
        re.compile(r"(?i)if a git add fails"),
        "'if a git add fails, report the failure...' -- describes handling a possible failure "
        "of the (separately, correctly prefixed) add step; not itself an invocation.",
    ),
    (
        "steps-git-diff-noun",
        re.compile(r"(?i)step \d.?s git diff"),
        "'every source file from step 1's git diff' -- refers back to an already-run, prefixed "
        "diff read; not a second invocation.",
    ),
    (
        "example-fence-placeholder",
        re.compile(r"\[git log --oneline"),
        "an illustrative placeholder inside a log.md entry's example code fence "
        "('[git log --oneline -8 -- the commits from this run]'), never executed.",
    ),
]


def scan_unprefixed_git(path: Path, allowlist_hits: dict[str, int]) -> list[str]:
    violations = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not CANDIDATE_RE.search(line):
            continue
        allowed = False
        for label, pattern, _why in allowlist:
            if pattern.search(line):
                allowlist_hits[label] = allowlist_hits.get(label, 0) + 1
                allowed = True
                # A line can legitimately match more than one allowlist entry (e.g. a comment
                # that also says "never"); count all matches so staleness detection stays
                # accurate, but only need one to allow the line.
        if not allowed:
            violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    return violations


allowlist = ALLOWLIST  # local alias so scan_unprefixed_git's default-arg style reads cleanly


class GitConstTests(unittest.TestCase):
    def setUp(self):
        for name, path in SOURCE_FILES.items():
            if not path.exists():
                raise AssertionError(f"engine source missing: {path}")

    # -- (a) cross-engine agreement ---------------------------------------------------------

    def test_a_const_defined_in_both_engines(self):
        for name, path in SOURCE_FILES.items():
            extract_git_const(path)  # raises if missing

    def test_a_const_byte_identical_across_engines(self):
        flow = extract_git_const(SOURCE_FILES["sdlc-flow.js"])
        task = extract_git_const(SOURCE_FILES["sdlc-task.js"])
        self.assertEqual(flow, task, "GIT constant has drifted between sdlc-flow.js and sdlc-task.js")

    # -- (b) exactly the nine pinned variable names, in order -------------------------------

    def test_b_unsets_exactly_the_nine_pinned_vars_in_order(self):
        for name, path in SOURCE_FILES.items():
            const = extract_git_const(path)
            self.assertTrue(const.startswith("env "), f"{name}: GIT constant does not start with 'env '")
            self.assertTrue(const.endswith(" git"), f"{name}: GIT constant does not end with ' git'")
            unset_names = re.findall(r"-u ([A-Z_]+)", const)
            self.assertEqual(
                unset_names, EXPECTED_VARS,
                f"{name}: unset variable list does not match mev's GIT_REPO_ENV_VARS "
                f"(core/mev/src/shared.rs:103). Got {unset_names}",
            )

    # -- (c) no unprefixed executable git invocation in any recipe line ---------------------

    def test_c_no_unprefixed_git_invocation_outside_allowlist(self):
        allowlist_hits: dict[str, int] = {}
        violations: list[str] = []
        for name, path in SOURCE_FILES.items():
            violations.extend(scan_unprefixed_git(path, allowlist_hits))

        if violations:
            self.fail(
                "unprefixed executable git invocation(s) found outside the allowlist "
                "(should be ${GIT} ...):\n  " + "\n  ".join(violations)
            )

        # Staleness guard: an allowlist entry that no longer matches anything must itself fail
        # this check, so a stale exemption can't silently widen to cover a real future
        # regression.
        stale = [label for label, _pattern, _why in ALLOWLIST if allowlist_hits.get(label, 0) == 0]
        self.assertEqual(
            stale, [],
            f"allowlist entries matched nothing in either engine (stale, remove them): {stale}",
        )

    # -- (d) positive control: prove this suite can tell prefixed from unprefixed ----------

    def test_d_positive_control_prefix_saves_the_tree_unprefixed_loses_it(self):
        git_const = extract_git_const(SOURCE_FILES["sdlc-flow.js"])

        def poisoned_commit_tree_size(use_prefix: bool) -> int:
            root = Path(tempfile.mkdtemp(prefix="git-env-strip-test-"))
            self.addCleanup(shutil.rmtree, root, ignore_errors=True)
            repo = root / "repo"
            init_repo(repo)
            (repo / "a.txt").write_text("a\n")
            (repo / "b.txt").write_text("b\n")
            run(["git", "add", "-A"], cwd=repo)
            run(["git", "commit", "-qm", "init"], cwd=repo)

            run(["git", "worktree", "add", "-q", "--no-checkout", "../wt", "-b", "wtb"], cwd=repo)
            wt = root / "wt"
            run(["git", "sparse-checkout", "init", "--cone"], cwd=wt, check=False)
            run(["git", "checkout", "-q"], cwd=wt)
            (wt / "c.txt").write_text("c\n")

            env = dict(os.environ)
            env["GIT_INDEX_FILE"] = str(root / "does-not-exist-index")

            # No `git add` here, deliberately -- matches
            # evidence/git-index-file-minimal-repro.sh exactly: the worktree checkout already
            # populated the REAL index with a.txt/b.txt/c.txt via sparse-checkout + checkout; the
            # bug is that GIT_INDEX_FILE redirects `git commit` itself to a nonexistent (so
            # freshly-empty) index, not that anything failed to `add`.
            prefix = git_const if use_prefix else "git"
            run(f"{prefix} commit -qm wrap-up", cwd=wt, env=env, check=False)

            out = run(["git", "ls-tree", "-r", "wtb"], cwd=repo, check=False).stdout
            return len([l for l in out.splitlines() if l.strip()])

        unprefixed_files = poisoned_commit_tree_size(use_prefix=False)
        prefixed_files = poisoned_commit_tree_size(use_prefix=True)

        self.assertEqual(
            unprefixed_files, 0,
            "positive control broken: an UNPREFIXED commit against a poisoned "
            "GIT_INDEX_FILE was expected to land an EMPTY tree",
        )
        self.assertGreater(
            prefixed_files, 0,
            "the ${GIT} prefix did not save the tree against a poisoned GIT_INDEX_FILE",
        )


class GitStatusUnchangedTest(unittest.TestCase):
    """Every fixture above builds and tears down its own tempdir repo -- confirm this repo's own
    git state is untouched by a test run (spec acceptance criterion)."""

    def test_repo_status_clean_apart_from_this_files_own_changes(self):
        result = run(
            ["git", "status", "--porcelain", "--", "scripts/test_git_env_strip.py"],
            cwd=REPO_ROOT, check=False,
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
