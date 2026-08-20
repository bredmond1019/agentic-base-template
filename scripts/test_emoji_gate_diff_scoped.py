#!/usr/bin/env python3
"""Cross-site fixture suite for the diff-scoped universal emoji gate.

ticket-emoji-gate-diff-scoped, task 2, extended by ticket-emoji-gate-close-out-site-drift,
task 2. The original task 1 moved four emoji-gate sites from whole-file scoping
(`git diff --name-only` + scan the whole file) to added-line scoping
(`git diff -M -U0 ... -- '*.md' '*.mdx'` + scan only `+` content lines). `/close-out`'s inline
gate (`.claude/commands/close-out.md`) was a fifth, undiscovered site that had neither the
added-line scoping nor the PR-footer exemption; it has since been brought into line with the
other four sites. This suite proves all FIVE sites actually agree, mechanically, rather than by eye.

BT.ticket.emoji-gate-diff-window-concurrent-sessions, task 2, split the five sites into TWO
classes with different scoping capability, because a single shared `<base>..HEAD` range is
provably wrong for two of them:

  - RUN_STATE_SITES  -- `.claude/workflows/sdlc-task.js` (`${baseSha}` base) and
                         `.claude/workflows/sdlc-flow.js` (`${prBase}` base) run their per-task
                         emoji gate on an in-place (`--no-worktree`) run's shared branch, where a
                         concurrent sibling session's commit can land inside `<base>..HEAD`
                         without the run itself having touched it. These two now scope to the
                         commit SHAs THIS run itself recorded in its own run-state
                         (`state.tasks[N].commit`, substituted at prompt-build time as a JSON
                         array literal -- see the `RUN_COMMITS = ...` line in each site's
                         extracted script), diffing each recorded commit against its own parent,
                         never `<base>..HEAD` as a whole. An anti-vacuous guard fires if the
                         recorded commit set is empty while `<base>..HEAD` is non-empty, rather
                         than silently passing on an unscoped diff.
  - BASE_REF_SITES    -- `.claude/commands/test.md` and `.claude/commands/close-out.md` are
                         operator-invoked against a feature branch cut FROM the base, with no
                         run-state to scope by and no shared-branch window to be exposed to (see
                         the block record's "Out of Scope"). These two keep diffing
                         `<base>..HEAD` as a whole, exactly as before.

Cross-site agreement is therefore asserted WITHIN each class, not across all five: the whole
point of the concurrent-sibling scenario below is that the two classes are now EXPECTED to
disagree (RUN_STATE_SITES pass; BASE_REF_SITES still fail, correctly, since a real feature-branch
checkout is never exposed to a sibling's commits in the first place). A case where two sites of
the SAME class disagree is still exactly the kind of bug this suite exists to catch -- it does not
special-case around a real intra-class divergence.

Each site embeds a real, runnable `python3 - <<'PYEOF' ... PYEOF` block. This suite extracts
that literal script text out of each source file (undoing the JS template-literal double-
backslash escaping the three `.js` sites carry, and substituting each site's base-ref and, for
the two RUN_STATE_SITES, run-state-path placeholders with real values -- `close-out.md` takes its
range as `sys.argv[1]` instead of a substituted literal, so it is invoked with an explicit
`main...HEAD` argument matching what Step 0.5 would actually compute for a feature branch cut
from `main`), builds a real git-repo fixture per scenario, executes each extracted script against
it with `cwd` set to the fixture, and asserts:

  1. the exit code matches the expected verdict for that scenario, and
  2. all sites WITHIN A CLASS produce the SAME exit code for every scenario.

Registered in planning/harness.json as `emoji-gate-diff-scoped-tests` --
run directly: python3 scripts/test_emoji_gate_diff_scoped.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE_FILES = {
    "test.md": REPO_ROOT / ".claude" / "commands" / "test.md",
    "sdlc-task.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js",
    "sdlc-flow.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js",
    "close-out.md": REPO_ROOT / ".claude" / "commands" / "close-out.md",
}

# The template-literal placeholder each JS site substitutes for the diff base ref.
# test.md has none -- it hardcodes `main..HEAD` directly. close-out.md has none either --
# it takes its range as `sys.argv[1]` (see ARGV_SITES below) rather than a substituted literal.
BASE_REF_PLACEHOLDER = {
    "sdlc-task.js": "${baseSha}",
    "sdlc-flow.js": "${prBase}",
}

# Sites whose script reads its diff range from argv instead of a literal embedded in the
# script text -- these get the range passed as an extra command-line argument at run time.
ARGV_SITES = {"close-out.md": "main...HEAD"}

SITE_NAMES = ["test.md", "sdlc-task.js", "sdlc-flow.js", "close-out.md"]

# The two-class split (BT.ticket.emoji-gate-diff-window-concurrent-sessions, task 2). See the
# module docstring for why cross-class agreement is no longer asserted.
RUN_STATE_SITES = ["sdlc-task.js", "sdlc-flow.js"]
BASE_REF_SITES = ["test.md", "close-out.md"]
assert set(RUN_STATE_SITES) | set(BASE_REF_SITES) == set(SITE_NAMES)
assert set(RUN_STATE_SITES) & set(BASE_REF_SITES) == set()

# The `${recordedCommitsJson}` placeholder each RUN_STATE_SITES script substitutes with a JSON
# array literal of the commit SHAs THIS run recorded (Object.values(state.tasks).map(t=>t.commit)
# at prompt-build time). Extraction replaces it with a sentinel; run_site_script() replaces the
# sentinel with the scenario's actual commit list just before execution, so each scenario can
# supply a different recorded-commit set against the SAME extracted script text.
RUN_COMMITS_PLACEHOLDER = "${recordedCommitsJson}"
RUN_COMMITS_SENTINEL = "'__RUN_COMMITS_SENTINEL__'"

# The `${stateFile}` placeholder each RUN_STATE_SITES script substitutes with the real run-state
# path, purely for the anti-vacuous diagnostic's text -- the script never reads this file (see
# the module docstring: the commit list itself arrives as a substituted literal, not a disk read).
STATE_FILE_SUBSTITUTE = {
    "sdlc-task.js": "planning/<block>/sdlc/sdlc-task-state.json",
    "sdlc-flow.js": "planning/<block>/sdlc/sdlc-flow-state.json",
}

PYEOF_BLOCK_RE = re.compile(r"<<'PYEOF'\n(.*?)\nPYEOF", re.DOTALL)


def extract_emoji_gate_script(site: str) -> str:
    """Pull the literal, runnable emoji-gate python script out of `site`'s source file.

    Two sites (sdlc-flow.js, sdlc-task.js) contain more than one `<<'PYEOF' ... PYEOF` block
    (a baseline-diff check helper too) -- disambiguate by requiring the emoji-gate marker.
    """
    path = SOURCE_FILES[site]
    text = path.read_text(encoding="utf-8")
    blocks = PYEOF_BLOCK_RE.findall(text)
    candidates = [b for b in blocks if "EMOJI = re.compile" in b]
    if len(candidates) != 1:
        raise AssertionError(
            f"{site}: expected exactly one emoji-gate PYEOF block in {path}, "
            f"found {len(candidates)}"
        )
    script = candidates[0]

    if site in BASE_REF_PLACEHOLDER:
        # The three .js sites embed this script inside a JS template literal, where every
        # literal backslash is doubled (`\\U0001F300` on disk -> `\U0001F300` at runtime).
        # Undo that so the extracted text is valid, directly-executable Python.
        script = script.replace("\\\\", "\\")
        placeholder = BASE_REF_PLACEHOLDER[site]
        if placeholder not in script:
            raise AssertionError(f"{site}: expected base-ref placeholder {placeholder!r} in extracted script")
        script = script.replace(placeholder, "main")
    elif site in ARGV_SITES:
        # Plain markdown-embedded bash (no JS template escaping), and the range comes from
        # sys.argv[1] at run time rather than a literal baked into the script text.
        if "sys.argv[1]" not in script:
            raise AssertionError(f"{site}: expected script to read its range from sys.argv[1]")

    if site in RUN_STATE_SITES:
        if RUN_COMMITS_PLACEHOLDER not in script:
            raise AssertionError(f"{site}: expected run-state commits placeholder {RUN_COMMITS_PLACEHOLDER!r}")
        script = script.replace(RUN_COMMITS_PLACEHOLDER, RUN_COMMITS_SENTINEL)
        state_file_sub = STATE_FILE_SUBSTITUTE[site]
        if "${stateFile}" not in script:
            raise AssertionError(f"{site}: expected run-state path placeholder '${{stateFile}}'")
        script = script.replace("${stateFile}", state_file_sub)

    if "EMOJI = re.compile" not in script or "git" not in script:
        raise AssertionError(f"{site}: extracted script does not look like the emoji gate")
    return script


EMOJI_SCRIPTS = {site: extract_emoji_gate_script(site) for site in SITE_NAMES}


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}: {result.stderr}")
    return result


def init_fixture_repo(tmp: Path) -> None:
    run_git(["init", "-b", "main"], tmp)
    run_git(["config", "user.email", "gate-fixture@example.com"], tmp)
    run_git(["config", "user.name", "Gate Fixture"], tmp)
    # Keep unicode filenames literal in `git diff` output instead of octal-escaped/quoted --
    # the header-artifact scenario needs an emoji byte-for-byte inside a `+++ b/<path>` line.
    run_git(["config", "core.quotepath", "false"], tmp)


def write_file(tmp: Path, relpath: str, content: str) -> None:
    p = tmp / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def commit_all(tmp: Path, message: str) -> None:
    run_git(["add", "-A"], tmp)
    run_git(["commit", "-m", message], tmp)


def run_site_script(site: str, repo: Path, run_commits: list[str] | None = None) -> subprocess.CompletedProcess:
    script = EMOJI_SCRIPTS[site]
    if site in RUN_STATE_SITES:
        commits = run_commits if run_commits is not None else []
        script = script.replace(RUN_COMMITS_SENTINEL, json.dumps(commits))
    argv = [ARGV_SITES[site]] if site in ARGV_SITES else []
    return subprocess.run(
        [sys.executable, "-c", script, *argv],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class EmojiGateFixture:
    """One disposable git repo: a `main` commit (the "already-merged legacy state") plus a
    `feature` branch commit (the "task's own diff"). All five sites diff feature-branch HEAD
    against `main` (BASE_REF_SITES always; RUN_STATE_SITES only via the anti-vacuous fallback
    check, never for the actual content scan)."""

    def __init__(self, tmpdir: str):
        self.path = Path(tmpdir)
        init_fixture_repo(self.path)
        self.commit_shas: list[str] = []   # SHAs of every task_commit() call, in order (1-based)

    def base_commit(self, files: dict) -> None:
        for relpath, content in files.items():
            write_file(self.path, relpath, content)
        commit_all(self.path, "base (legacy state)")
        run_git(["checkout", "-b", "feature"], self.path)

    def task_commit(self, files: dict | None = None, renames: list[tuple[str, str]] | None = None) -> str:
        for old, new in renames or []:
            run_git(["mv", old, new], self.path)
        for relpath, content in (files or {}).items():
            write_file(self.path, relpath, content)
        commit_all(self.path, "task work")
        sha = run_git(["rev-parse", "HEAD"], self.path).stdout.strip()
        self.commit_shas.append(sha)
        return sha

    def write_run_state_file(self, site: str, tasks: dict[str, str]) -> list[str]:
        """Synthesise a real run-state file (state.tasks[N].commit shape) into the fixture repo,
        at the same relative path the real orchestrator would use, and return the commit SHA
        list it records -- exactly what Object.values(state.tasks).map(t=>t.commit).filter(Boolean)
        would compute from it. This is the fixture-side stand-in for the in-memory `state.tasks`
        object each engine's runTests() reads to build its RUN_COMMITS substitution; the extracted
        script itself never reads this file back (see the module docstring), so the two are kept
        deliberately in sync by construction: this helper's return value IS what gets substituted.
        """
        payload = {"tasks": {task_id: {"commit": sha} for task_id, sha in tasks.items()}}
        state_relpath = "planning/fixture-block/sdlc/" + (
            "sdlc-task-state.json" if site == "sdlc-task.js" else "sdlc-flow-state.json"
        )
        state_path = self.path / state_relpath
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return [t["commit"] for t in payload["tasks"].values() if t.get("commit")]


def run_all_sites(repo: Path, run_commits: list[str] | None = None) -> dict[str, subprocess.CompletedProcess]:
    """Run every site. `run_commits`, when given, is substituted for RUN_STATE_SITES only --
    BASE_REF_SITES always diff `main..HEAD` as a whole and ignore it."""
    return {site: run_site_script(site, repo, run_commits=run_commits) for site in SITE_NAMES}


class EmojiGateDiffScopedTest(unittest.TestCase):
    """Scenarios that do not involve a concurrent sibling commit assert full 5-site agreement,
    with `run_commits` set to every commit the fixture made (so the RUN_STATE_SITES' recorded
    set is exactly what BASE_REF_SITES would see in `main..HEAD` for a single-commit fixture --
    the two classes coincide whenever there is nothing for them to disagree about). Scenarios
    that DO involve a concurrent sibling assert within-class agreement only -- see
    assert_class_verdicts."""

    def setUp(self):
        self._tmpdirs: list[str] = []

    def tearDown(self):
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def new_fixture(self) -> EmojiGateFixture:
        tmpdir = tempfile.mkdtemp(prefix="emoji-gate-fixture-")
        self._tmpdirs.append(tmpdir)
        return EmojiGateFixture(tmpdir)

    def assert_all_sites(
        self, repo: Path, expect_pass: bool, msg: str, run_commits: list[str] | None = None
    ) -> dict[str, subprocess.CompletedProcess]:
        results = run_all_sites(repo, run_commits=run_commits)
        codes = {site: r.returncode for site, r in results.items()}
        unique = set(codes.values())
        self.assertEqual(
            len(unique), 1,
            f"{msg}: the five sites DISAGREE on verdict -- {codes}\n"
            + "\n".join(f"--- {s} ---\n{r.stdout}{r.stderr}" for s, r in results.items()),
        )
        expected_code = 0 if expect_pass else 1
        actual_code = unique.pop()
        self.assertEqual(
            actual_code, expected_code,
            f"{msg}: expected exit {expected_code} ({'PASS' if expect_pass else 'FAIL'}), "
            f"got {actual_code} from all five sites.\n"
            + "\n".join(f"--- {s} ---\n{r.stdout}{r.stderr}" for s, r in results.items()),
        )
        return results

    def assert_class_verdicts(
        self,
        repo: Path,
        run_commits: list[str],
        expect_run_state_pass: bool,
        expect_base_ref_pass: bool,
        msg: str,
    ) -> dict[str, subprocess.CompletedProcess]:
        """Assert agreement WITHIN each class, and the expected verdict for each class -- the two
        classes may legitimately differ from each other (that is the point of task 2's fix), but
        a divergence WITHIN a class is still the bug this suite exists to catch."""
        results = run_all_sites(repo, run_commits=run_commits)

        def check_class(names: list[str], expect_pass: bool, label: str) -> None:
            codes = {s: results[s].returncode for s in names}
            unique = set(codes.values())
            self.assertEqual(
                len(unique), 1,
                f"{msg}: {label} sites DISAGREE on verdict -- {codes}\n"
                + "\n".join(f"--- {s} ---\n{results[s].stdout}{results[s].stderr}" for s in names),
            )
            expected_code = 0 if expect_pass else 1
            actual_code = unique.pop()
            self.assertEqual(
                actual_code, expected_code,
                f"{msg}: {label} sites expected exit {expected_code} "
                f"({'PASS' if expect_pass else 'FAIL'}), got {actual_code}.\n"
                + "\n".join(f"--- {s} ---\n{results[s].stdout}{results[s].stderr}" for s in names),
            )

        check_class(RUN_STATE_SITES, expect_run_state_pass, "RUN_STATE_SITES")
        check_class(BASE_REF_SITES, expect_base_ref_pass, "BASE_REF_SITES")
        return results

    # -- headline case ------------------------------------------------------------------

    def test_clean_line_added_to_file_with_preexisting_emoji_passes(self):
        fx = self.new_fixture()
        fx.base_commit({
            "docs/legacy.md": "# Legacy\n\nAlready shipped line one \U0001F680\n"
            "Already shipped line two ✅\n"
            "Already shipped line three \U0001F389\n",
        })
        sha = fx.task_commit(files={
            "docs/legacy.md": "# Legacy\n\nAlready shipped line one \U0001F680\n"
            "Already shipped line two ✅\n"
            "Already shipped line three \U0001F389\n"
            "One brand-new, perfectly clean line.\n",
        })
        self.assert_all_sites(
            fx.path, expect_pass=True,
            msg="a clean line appended to a legacy file with pre-existing emoji must PASS",
            run_commits=[sha],
        )

    # -- the gate can still fail, and must say where ------------------------------------

    def test_line_with_emoji_added_fails_and_names_file_and_line(self):
        fx = self.new_fixture()
        fx.base_commit({"docs/notes.md": "line one\nline two\n"})
        sha = fx.task_commit(files={"docs/notes.md": "line one\nline two\nline three has an emoji ✅\n"})
        results = self.assert_all_sites(
            fx.path, expect_pass=False,
            msg="a newly added line containing an emoji must FAIL",
            run_commits=[sha],
        )
        for site, result in results.items():
            self.assertIn(
                "docs/notes.md:3", result.stdout,
                f"{site}: failure report must name the file and a usable line number, got:\n{result.stdout}",
            )

    # -- rename -----------------------------------------------------------------------

    def test_pure_rename_of_file_with_emoji_passes(self):
        fx = self.new_fixture()
        fx.base_commit({"docs/legacy.md": "line one \U0001F680\nline two ✅\n"})
        sha = fx.task_commit(renames=[("docs/legacy.md", "docs/renamed.md")])
        self.assert_all_sites(
            fx.path, expect_pass=True,
            msg="a pure rename of a file containing emoji (no content change) must PASS",
            run_commits=[sha],
        )

    # -- new file -----------------------------------------------------------------------

    def test_new_file_with_emoji_fails(self):
        fx = self.new_fixture()
        fx.base_commit({"README.md": "hello\n"})
        sha = fx.task_commit(files={"docs/brand_new.md": "This whole file is new \U0001F680\n"})
        self.assert_all_sites(
            fx.path, expect_pass=False,
            msg="a brand-new file containing an emoji must FAIL (its added lines are its whole content)",
            run_commits=[sha],
        )

    # -- diff header artifact ------------------------------------------------------------

    def test_plus_plus_plus_header_never_treated_as_content(self):
        fx = self.new_fixture()
        fx.base_commit({"README.md": "hello\n"})
        # The new file's PATH itself carries an emoji-range character, so the `+++ b/<path>`
        # diff header line contains an emoji -- but the file's CONTENT is clean. If the header
        # were ever mistaken for an added-content line, this would wrongly FAIL.
        sha = fx.task_commit(files={"docs/notes✅.md": "perfectly clean content\nsecond clean line\n"})
        self.assert_all_sites(
            fx.path, expect_pass=True,
            msg="the `+++ b/<path>` diff header must never be scanned as added content, "
            "even when the path itself contains an emoji character",
            run_commits=[sha],
        )

    # -- PR-footer exemption --------------------------------------------------------------

    def test_pr_footer_phrase_is_exempt(self):
        fx = self.new_fixture()
        fx.base_commit({"docs/notes.md": "line one\n"})
        sha = fx.task_commit(files={
            "docs/notes.md": "line one\n\U0001F916 Generated with Claude Code\n",
        })
        self.assert_all_sites(
            fx.path, expect_pass=True,
            msg="the literal 'Generated with Claude Code' PR-footer phrase must stay exempt "
            "at every site, even though it carries the robot emoji",
            run_commits=[sha],
        )

    # -- .mdx parity ------------------------------------------------------------------

    def test_mdx_file_with_emoji_fails_same_as_md(self):
        fx = self.new_fixture()
        fx.base_commit({"README.md": "hello\n"})
        sha = fx.task_commit(files={"docs/guide.mdx": "This is new mdx content \U0001F680\n"})
        self.assert_all_sites(
            fx.path, expect_pass=False,
            msg=".mdx files must be scanned identically to .md files at all five sites",
            run_commits=[sha],
        )

    # -- concurrent sibling (the defect this ticket removes) ------------------------------

    def test_concurrent_sibling_commit_does_not_bail_the_run(self):
        """The run's own recorded commit is clean; a SECOND, un-recorded commit (a concurrent
        sibling session landing on the same shared in-place branch) adds an emoji to a file the
        run never touched. RUN_STATE_SITES must PASS -- they scope to the recorded commit only.
        BASE_REF_SITES must still FAIL -- `main..HEAD` legitimately contains both commits, and
        that class has no run-state to scope by (see the block record's Out of Scope)."""
        fx = self.new_fixture()
        fx.base_commit({"README.md": "hello\n"})
        mine = fx.task_commit(files={"docs/mine.md": "clean line one\nclean line two\n"})
        fx.task_commit(files={"docs/sibling.md": "sibling line ✅\n"})   # NOT recorded
        self.assert_class_verdicts(
            fx.path, run_commits=[mine],
            expect_run_state_pass=True, expect_base_ref_pass=False,
            msg="a concurrent sibling's un-recorded commit must not bail the run at the "
            "run-state-scoped sites, but base-ref sites (no run-state, no concurrent-sibling "
            "window by design) still see it in main..HEAD and correctly still fail",
        )

    # -- the run's own commit can still fail (narrowing is not blindness) -----------------

    def test_run_recorded_commit_with_emoji_still_fails(self):
        """The run's OWN recorded commit adds the emoji this time -- proving the narrowed
        RUN_STATE_SITES scope has not been made incapable of catching a real violation made by
        the run itself."""
        fx = self.new_fixture()
        fx.base_commit({"docs/notes.md": "line one\n"})
        mine = fx.task_commit(files={"docs/notes.md": "line one\nrun's own line ✅\n"})
        self.assert_class_verdicts(
            fx.path, run_commits=[mine],
            expect_run_state_pass=False, expect_base_ref_pass=False,
            msg="an emoji added by the run's OWN recorded commit must still FAIL at every site "
            "-- the narrowed scope must not be able to hide a real violation",
        )

    # -- empty run-state must never pass vacuously -----------------------------------------

    def test_empty_run_state_with_nonempty_diff_cannot_scope(self):
        """No commits are recorded for this run (an empty RUN_COMMITS list), but main..HEAD is
        non-empty (some commit landed on the branch). RUN_STATE_SITES must exit non-zero with a
        cannot-scope diagnostic naming the run-state file -- never print 'EMOJI CHECK: OK'. This
        is the anti-vacuous guard: an unwritten run-state must degrade loudly, not into a silent
        pass on an unscoped diff."""
        fx = self.new_fixture()
        fx.base_commit({"README.md": "hello\n"})
        fx.task_commit(files={"docs/something.md": "clean, but nothing was recorded for it\n"})
        results = run_all_sites(fx.path, run_commits=[])   # empty recorded-commit set
        for site in RUN_STATE_SITES:
            result = results[site]
            self.assertNotEqual(
                result.returncode, 0,
                f"{site}: an empty recorded-commit set with a non-empty main..HEAD must exit "
                f"non-zero (cannot-scope), not pass. Got:\n{result.stdout}{result.stderr}",
            )
            self.assertNotIn(
                "EMOJI CHECK: OK", result.stdout,
                f"{site}: must never print 'EMOJI CHECK: OK' when it cannot scope the diff at all",
            )
            self.assertIn(
                "cannot scope", result.stdout.lower(),
                f"{site}: must print an explicit cannot-scope diagnostic, got:\n{result.stdout}",
            )
            state_file_sub = STATE_FILE_SUBSTITUTE[site]
            self.assertIn(
                state_file_sub, result.stdout,
                f"{site}: cannot-scope diagnostic must name the run-state file, got:\n{result.stdout}",
            )

    def test_empty_run_state_synthesised_via_write_run_state_file(self):
        """Same guard, but exercised through write_run_state_file() -- the fixture synthesises a
        real run-state JSON with an empty tasks map, proving the helper's derived commit list
        (empty here) is exactly what gets substituted and exactly what trips the guard."""
        fx = self.new_fixture()
        fx.base_commit({"README.md": "hello\n"})
        fx.task_commit(files={"docs/something.md": "clean, but nothing was recorded for it\n"})
        commits = fx.write_run_state_file("sdlc-task.js", tasks={})
        self.assertEqual(commits, [])
        results = run_all_sites(fx.path, run_commits=commits)
        result = results["sdlc-task.js"]
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("EMOJI CHECK: OK", result.stdout)

    # -- the suite must be able to detect real disagreement ------------------------------

    def test_suite_can_detect_disagreement_within_a_class(self):
        """Not a gate scenario -- proves assert_class_verdicts actually fails on an intra-class
        divergence, so a future regression that makes two sites of the SAME class disagree cannot
        pass silently. Cross-class disagreement (RUN_STATE_SITES vs BASE_REF_SITES) is expected
        and is NOT what this checks -- see test_concurrent_sibling_commit_does_not_bail_the_run
        for that."""
        fake_results = {
            "sdlc-task.js": subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            "sdlc-flow.js": subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=""),
        }
        codes = {site: r.returncode for site, r in fake_results.items()}
        self.assertNotEqual(
            len(set(codes.values())), 1,
            "sanity check itself is broken: this synthetic fixture must show intra-class disagreement",
        )


class ExtractionSanityTest(unittest.TestCase):
    """The extraction itself must be honest: fail loudly if a source file no longer contains
    exactly one recognizable emoji-gate script, rather than silently testing stale text."""

    def test_all_five_sites_extract_a_single_script(self):
        for site in SITE_NAMES:
            script = EMOJI_SCRIPTS[site]
            self.assertIn("EMOJI = re.compile", script)
            self.assertIn("git", script)
            self.assertIn("diff", script)
            # Added-line scoping, not whole-file scoping -- the regression this ticket fixes.
            self.assertIn("-U0", script, f"{site}: script must use -U0 (added-line hunks only)")
            if site in BASE_REF_SITES:
                self.assertNotIn(
                    "--name-only", script,
                    f"{site}: base-ref site must not fall back to file-list scoping",
                )
            self.assertNotIn("${", script, f"{site}: unsubstituted template placeholder leaked through")

    def test_run_state_sites_carry_the_anti_vacuous_guard(self):
        for site in RUN_STATE_SITES:
            script = EMOJI_SCRIPTS[site]
            self.assertIn(
                "--name-only", script,
                f"{site}: the anti-vacuous guard's existence check uses --name-only "
                "(distinct from the added-line content scan, which stays -U0)",
            )
            self.assertIn("RUN_COMMITS", script)
            self.assertIn(RUN_COMMITS_SENTINEL, script, f"{site}: sentinel not left for run-time substitution")


class RunCommitPopulationTest(unittest.TestCase):
    """The gate is only as good as the SHA list it is handed.

    `RUN_COMMITS` is built from `state.tasks[N].commit`, which the engine sets from the
    implement/fix stage's StructuredOutput. That payload's field is `commitHash` (see
    STAGE_SCHEMA in both engines) -- it has never been called `commit`. Reading
    `stageResult.commit` therefore left `t.commit` unset on every run in this fleet's
    history: harmless while the field only fed the state file's at-a-glance index, and
    load-bearing the moment the emoji gate started scoping to those SHAs, where an empty
    set trips the cannot-scope abort and hard-fails every task after the first commit.

    Caught live on this very ticket's own /sdlc-task run, where all four tasks reported
    green while the shipped gate, executed verbatim, exits 1. These assertions exist so
    that regression cannot recur silently.
    """

    ENGINES = ("sdlc-task.js", "sdlc-flow.js")

    def _engine_source(self, engine: str) -> str:
        return (REPO_ROOT / ".claude" / "workflows" / engine).read_text(encoding="utf-8")

    def test_engines_read_commitHash_not_commit(self):
        for engine in self.ENGINES:
            src = self._engine_source(engine)
            self.assertNotIn(
                "stageResult.commit)", src,
                f"{engine}: reads stageResult.commit, but the stage schema's field is "
                "commitHash -- t.commit stays unset and the emoji gate's RUN_COMMITS is "
                "always empty",
            )
            self.assertIn(
                "stageResult.commitHash", src,
                f"{engine}: must populate t.commit from the schema's commitHash field",
            )

    def test_commitHash_field_is_what_the_stage_schema_declares(self):
        for engine in self.ENGINES:
            src = self._engine_source(engine)
            self.assertIn(
                "commitHash:", src,
                f"{engine}: STAGE_SCHEMA must still declare commitHash -- if this field is "
                "ever renamed, the assignment above must be renamed in lockstep",
            )

    def test_only_hash_shaped_values_are_recorded(self):
        """A stage has been observed returning the literal quoted empty string '""'.

        Truthiness alone would record that as a commit SHA and hand the gate a range git
        cannot resolve, so the assignment must validate the shape.
        """
        for engine in self.ENGINES:
            src = self._engine_source(engine)
            self.assertRegex(
                src, r"\[0-9a-f\]\{7,40\}",
                f"{engine}: must validate that a recorded commit actually looks like a "
                "short hash, not merely that it is truthy",
            )


if __name__ == "__main__":
    unittest.main()
