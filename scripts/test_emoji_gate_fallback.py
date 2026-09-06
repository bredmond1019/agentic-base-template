#!/usr/bin/env python3
"""Fixture suite pinning the no-commits emoji-gate fallback's ATTRIBUTION fix.

BT.ticket.emoji-gate-fallback-must-attribute-a-range-it-did-not-author, task 1.

`renderEmojiGate`'s `<<shared:renderEmojiGate>>` block in `.claude/workflows/prompts/shared.js`
(inlined byte-for-byte into `.claude/workflows/sdlc-task.js` and `.claude/workflows/sdlc-flow.js`)
promises to be diff-scoped to the commit SHAs THIS run itself recorded, precisely so that "neither
a legacy file's pre-existing emoji nor a concurrent sibling session's commit on a shared in-place
branch can fail a diff this run never touched." The `if not RUN_COMMITS:` fallback -- the branch
that runs when a run has recorded NO commits yet -- does the opposite: it diffs the whole
`BASE_SHA..HEAD` range and refuses on ANY non-empty result, including a range containing nothing
but a sibling's already-committed, already-reviewed work. Measured 2026-08-28:
`BT.ticket.bookkeep-leaves-derived-output-uncommitted` bailed at task 1 on exactly this -- two
commits (`494bcd7`, `74d8bf0`) that were HQ's own fleet-wide README rewrite landing mid-run, not
this lane's work, with a bail message asking the operator to "commit or revert them" when they were
already committed before the bail printed.

THE CONTRACT THIS SUITE ENCODES (task 1's description, so task 2 has one unambiguous target):

  - When RUN_COMMITS is empty, this run authored NO commits, so no commit in BASE_SHA..HEAD is
    attributable to it and the committed range contributes nothing to judge. The gate must NOT
    refuse on that range.
  - It must instead judge this run's UNCOMMITTED work: the emoji scan runs over added lines in the
    working tree's uncommitted diff against HEAD (tracked modifications plus untracked files),
    restricted to *.md / *.mdx, exempting the "Generated with Claude Code" footer exactly as the
    RUN_COMMITS path already does.
  - Emoji in an uncommitted file therefore still FAILS (an in-flight sibling's uncommitted file is
    indistinguishable from this run's own, and failing closed there is the deliberate choice);
    emoji present only in a foreign COMMIT in the range PASSES.
  - The non-empty-RUN_COMMITS path is unchanged in every respect.

This suite extracts the REAL, runnable gate script out of all three sites (undoing the JS
template-literal double-backslash escaping, substituting the `${baseSha}` / `${stateFile}` /
`${recordedCommitsJson}` placeholders with real values), builds disposable git-repo fixtures under
`mktemp -d` (never this repo), executes the extracted script in a real subprocess against each
fixture, and asserts the verdict -- never a Python re-implementation of the gate's own logic.

Run against the UNFIXED source (2026-09-06 baseline), case 1 below fails with the real
"cannot scope diff" message -- this is task 1's expected RED. Task 2 makes every case here pass.

Run directly: python3 scripts/test_emoji_gate_fallback.py
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
    "shared.js": REPO_ROOT / ".claude" / "workflows" / "prompts" / "shared.js",
    "sdlc-task.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js",
    "sdlc-flow.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js",
}
SITE_NAMES = ["shared.js", "sdlc-task.js", "sdlc-flow.js"]

SHARED_BLOCK_RE = re.compile(
    r"// <<shared:renderEmojiGate>>\n(.*?)\n// <</shared:renderEmojiGate>>", re.DOTALL
)
PYEOF_BLOCK_RE = re.compile(r"<<'PYEOF'\n(.*?)\nPYEOF", re.DOTALL)

PLACEHOLDERS = ("${baseSha}", "${stateFile}", "${recordedCommitsJson}")


def extract_shared_block_text(site: str) -> str:
    """The raw `<<shared:renderEmojiGate>> ... <</shared:renderEmojiGate>>` block, UNMODIFIED --
    used only for the byte-identical cross-site assertion, never executed directly."""
    path = SOURCE_FILES[site]
    text = path.read_text(encoding="utf-8")
    m = SHARED_BLOCK_RE.search(text)
    if m is None:
        raise AssertionError(f"{site}: no <<shared:renderEmojiGate>> block found in {path}")
    return m.group(1)


def extract_gate_script(site: str) -> str:
    """Pull the literal, runnable `python3 - <<'PYEOF' ... PYEOF` gate script out of `site`'s
    `<<shared:renderEmojiGate>>` block and undo the JS template-literal double-backslash escaping,
    leaving the `${baseSha}` / `${stateFile}` / `${recordedCommitsJson}` placeholders in place for
    run_gate() to substitute per-scenario."""
    block = extract_shared_block_text(site)
    candidates = PYEOF_BLOCK_RE.findall(block)
    if len(candidates) != 1:
        raise AssertionError(
            f"{site}: expected exactly one PYEOF gate script in its <<shared:renderEmojiGate>> "
            f"block, found {len(candidates)}"
        )
    script = candidates[0]
    # `\\U0001F300` on disk (JS template-literal escaping) -> `\U0001F300` at runtime.
    script = script.replace("\\\\", "\\")
    for placeholder in PLACEHOLDERS:
        if placeholder not in script:
            raise AssertionError(f"{site}: expected placeholder {placeholder!r} in extracted script")
    if "EMOJI = re.compile" not in script or "git" not in script:
        raise AssertionError(f"{site}: extracted script does not look like the emoji gate")
    return script


GATE_SCRIPTS = {site: extract_gate_script(site) for site in SITE_NAMES}

DEFAULT_STATE_FILE = "planning/fixture-block/sdlc/sdlc-task-state.json"


def run_gate(
    site: str,
    repo: Path,
    base_sha: str,
    run_commits: list[str] | None = None,
    state_file: str = DEFAULT_STATE_FILE,
) -> subprocess.CompletedProcess:
    script = GATE_SCRIPTS[site]
    script = script.replace("${baseSha}", base_sha)
    script = script.replace("${stateFile}", state_file)
    script = script.replace("${recordedCommitsJson}", json.dumps(run_commits or []))
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def run_all_sites(
    repo: Path, base_sha: str, run_commits: list[str] | None = None
) -> dict[str, subprocess.CompletedProcess]:
    return {site: run_gate(site, repo, base_sha, run_commits=run_commits) for site in SITE_NAMES}


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
    run_git(["config", "core.quotepath", "false"], tmp)
    run_git(["config", "commit.gpgsign", "false"], tmp)


def write_file(tmp: Path, relpath: str, content: str) -> None:
    p = tmp / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


class Fixture:
    """One disposable git repo. `commit()` is this run's own attributable work; `foreign_commit()`
    simulates a concurrent sibling session's already-landed, already-reviewed commit; `leave_dirty()`
    leaves work in the tree WITHOUT committing it (tracked-modification or untracked-new-file)."""

    def __init__(self, tmpdir: str):
        self.path = Path(tmpdir)
        init_fixture_repo(self.path)

    def commit(self, files: dict, message: str = "work") -> str:
        for relpath, content in files.items():
            write_file(self.path, relpath, content)
        run_git(["add", "-A"], self.path)
        run_git(["commit", "-m", message], self.path)
        return run_git(["rev-parse", "HEAD"], self.path).stdout.strip()

    def foreign_commit(self, files: dict, message: str = "sibling work") -> str:
        for relpath, content in files.items():
            write_file(self.path, relpath, content)
        run_git(["add", "-A"], self.path)
        run_git(
            [
                "-c", "user.name=Sibling Session",
                "-c", "user.email=sibling@example.com",
                "commit", "-m", message,
            ],
            self.path,
        )
        return run_git(["rev-parse", "HEAD"], self.path).stdout.strip()

    def leave_untracked(self, relpath: str, content: str) -> None:
        write_file(self.path, relpath, content)

    def leave_tracked_modification(self, relpath: str, content: str) -> None:
        # relpath must already be committed; this edits it without staging or committing.
        write_file(self.path, relpath, content)

    def head(self) -> str:
        return run_git(["rev-parse", "HEAD"], self.path).stdout.strip()


class EmojiGateFallbackTest(unittest.TestCase):
    def setUp(self):
        self._tmpdirs: list[str] = []

    def tearDown(self):
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def new_fixture(self) -> Fixture:
        tmpdir = tempfile.mkdtemp(prefix="emoji-gate-fallback-fixture-")
        self._tmpdirs.append(tmpdir)
        return Fixture(tmpdir)

    def assert_all_sites(
        self,
        repo: Path,
        base_sha: str,
        expect_pass: bool,
        msg: str,
        run_commits: list[str] | None = None,
    ) -> dict[str, subprocess.CompletedProcess]:
        results = run_all_sites(repo, base_sha, run_commits=run_commits)
        codes = {site: r.returncode for site, r in results.items()}
        unique = set(codes.values())
        self.assertEqual(
            len(unique), 1,
            f"{msg}: the three sites DISAGREE on verdict -- {codes}\n"
            + "\n".join(f"--- {s} ---\n{r.stdout}{r.stderr}" for s, r in results.items()),
        )
        expected_code = 0 if expect_pass else 1
        actual_code = unique.pop()
        self.assertEqual(
            actual_code, expected_code,
            f"{msg}: expected exit {expected_code} ({'PASS' if expect_pass else 'FAIL'}), "
            f"got {actual_code} from all three sites.\n"
            + "\n".join(f"--- {s} ---\n{r.stdout}{r.stderr}" for s, r in results.items()),
        )
        return results

    # -- case 1: foreign commits only, RUN_COMMITS empty -> must PASS (TODAY THIS IS THE RED) ----

    def test_foreign_commits_only_with_empty_run_commits_passes(self):
        """A range containing nothing but a sibling session's already-committed emoji must not
        bail a run that recorded no commits of its own. Today the fallback diffs the whole
        BASE_SHA..HEAD range and refuses on this exact case -- the case its own comment names as
        the reason it exists."""
        fx = self.new_fixture()
        base_sha = fx.commit({"README.md": "hello\n"})
        fx.foreign_commit({"docs/sibling.md": "sibling line with emoji \U0001F680\n"})
        results = self.assert_all_sites(
            fx.path, base_sha, expect_pass=True, run_commits=[],
            msg="a foreign-committed range with no run-recorded commits must PASS, not refuse",
        )
        for site, result in results.items():
            self.assertNotIn(
                "cannot scope diff", result.stdout,
                f"{site}: must not print the refuse-on-non-empty diagnostic for a range this run "
                f"did not author. Got:\n{result.stdout}",
            )

    # -- case 2: own uncommitted emoji, RUN_COMMITS empty -> must FAIL ---------------------------
    # The control against an unconditional-pass fix: without this, `sys.exit(0)` on any empty
    # RUN_COMMITS would pass case 1 perfectly while making the gate blind to this run's own,
    # never-yet-committed work.

    def test_own_uncommitted_untracked_file_with_emoji_fails(self):
        fx = self.new_fixture()
        base_sha = fx.commit({"README.md": "hello\n"})
        fx.leave_untracked("docs/mine.md", "my own new file with emoji \U0001F389\n")
        self.assert_all_sites(
            fx.path, base_sha, expect_pass=False, run_commits=[],
            msg="an untracked file this run itself wrote, containing emoji, must still FAIL even "
            "though this run recorded no commits yet",
        )

    def test_own_uncommitted_tracked_modification_with_emoji_fails(self):
        fx = self.new_fixture()
        base_sha = fx.commit({"docs/notes.md": "line one\n"})
        fx.leave_tracked_modification("docs/notes.md", "line one\nline two has emoji ✅\n")
        self.assert_all_sites(
            fx.path, base_sha, expect_pass=False, run_commits=[],
            msg="an uncommitted MODIFICATION to a tracked file, containing emoji, must still FAIL "
            "even though this run recorded no commits yet",
        )

    # -- case 3: clean tree, foreign commits present, RUN_COMMITS empty -> must PASS -------------

    def test_clean_tree_with_foreign_commits_passes(self):
        """No uncommitted work at all -- the foreign commits are the ENTIRE BASE_SHA..HEAD range,
        and the working tree is byte-identical to HEAD. Must PASS: there is nothing of this run's
        own to judge."""
        fx = self.new_fixture()
        base_sha = fx.commit({"README.md": "hello\n"})
        fx.foreign_commit({"docs/one.md": "sibling emoji one \U0001F680\n"})
        fx.foreign_commit({"docs/two.md": "sibling emoji two ✅\n"})
        status = run_git(["status", "--porcelain"], fx.path).stdout
        self.assertEqual(status, "", "fixture setup left an unexpectedly dirty tree")
        self.assert_all_sites(
            fx.path, base_sha, expect_pass=True, run_commits=[],
            msg="a perfectly clean tree with only foreign commits in the range must PASS",
        )

    # -- case 4: non-empty RUN_COMMITS, unchanged behaviour (regression control) -----------------

    def test_non_empty_run_commits_with_emoji_still_fails(self):
        fx = self.new_fixture()
        base_sha = fx.commit({"docs/notes.md": "line one\n"})
        mine = fx.commit({"docs/notes.md": "line one\nrun's own line ✅\n"}, message="task work")
        self.assert_all_sites(
            fx.path, base_sha, expect_pass=False, run_commits=[mine],
            msg="the non-empty-RUN_COMMITS path must be unchanged: a run-authored commit adding "
            "emoji still FAILS",
        )

    def test_non_empty_run_commits_without_emoji_still_passes(self):
        fx = self.new_fixture()
        base_sha = fx.commit({"docs/notes.md": "line one\n"})
        mine = fx.commit({"docs/notes.md": "line one\nclean run line\n"}, message="task work")
        self.assert_all_sites(
            fx.path, base_sha, expect_pass=True, run_commits=[mine],
            msg="the non-empty-RUN_COMMITS path must be unchanged: a run-authored commit with no "
            "emoji still PASSES",
        )

    # -- case 5: footer exemption still honoured in the new uncommitted path ---------------------

    def test_footer_exemption_honoured_for_uncommitted_work(self):
        fx = self.new_fixture()
        base_sha = fx.commit({"README.md": "hello\n"})
        fx.leave_untracked(
            "docs/footer.md", "\U0001F916 Generated with Claude Code\n"
        )
        self.assert_all_sites(
            fx.path, base_sha, expect_pass=True, run_commits=[],
            msg="the literal 'Generated with Claude Code' PR-footer phrase must stay exempt in "
            "the uncommitted-diff fallback path too, even though it carries the robot emoji",
        )

    # -- case 6: all three sites carry byte-identical gate text -----------------------------------

    def test_all_three_sites_are_byte_identical(self):
        blocks = {site: extract_shared_block_text(site) for site in SITE_NAMES}
        canonical = blocks["shared.js"]
        for site in ("sdlc-task.js", "sdlc-flow.js"):
            self.assertEqual(
                blocks[site], canonical,
                f"{site}: <<shared:renderEmojiGate>> block diverges from shared.js's canonical "
                "copy -- run `python3 scripts/build_engines.py --write` to re-inline",
            )


class ExtractionSanityTest(unittest.TestCase):
    """The extraction itself must be honest: fail loudly if a source file no longer contains
    exactly one recognizable emoji-gate PYEOF script, rather than silently testing stale text."""

    def test_all_three_sites_extract_a_single_script(self):
        for site in SITE_NAMES:
            script = GATE_SCRIPTS[site]
            self.assertIn("EMOJI = re.compile", script)
            self.assertIn("git", script)
            self.assertIn("diff", script)
            for placeholder in PLACEHOLDERS:
                self.assertIn(
                    placeholder, script,
                    f"{site}: extracted script must still carry the unsubstituted placeholder "
                    f"{placeholder!r} -- run_gate() substitutes it per-scenario",
                )

    def test_run_gate_leaves_no_unsubstituted_placeholder(self):
        for site in SITE_NAMES:
            script = GATE_SCRIPTS[site]
            for placeholder in PLACEHOLDERS:
                script = script.replace(placeholder, "SUBSTITUTED")
            self.assertNotIn(
                "${", script,
                f"{site}: an unaccounted-for template placeholder leaked through extraction",
            )


if __name__ == "__main__":
    unittest.main()
