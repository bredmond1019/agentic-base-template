#!/usr/bin/env python3
"""Cross-site fixture suite for the diff-scoped universal emoji gate.

ticket-emoji-gate-diff-scoped, task 2. Task 1 moved all FOUR emoji-gate sites from
whole-file scoping (`git diff --name-only` + scan the whole file) to added-line scoping
(`git diff -M -U0 ... -- '*.md' '*.mdx'` + scan only `+` content lines). This suite proves
the four sites actually agree, mechanically, rather than by eye:

  - `.claude/commands/test.md`            (executable, hardcoded `main..HEAD`)
  - `.claude/workflows/sdlc-block.js`     (executable, `${baseRef}...HEAD`)
  - `.claude/workflows/sdlc-task.js`      (prose-to-agent, `${baseSha}..HEAD`)
  - `.claude/workflows/sdlc-flow.js`      (prose-to-agent, `${prBase}..HEAD`)

Each site embeds a real, runnable `python3 - <<'PYEOF' ... PYEOF` block. This suite extracts
that literal script text out of each source file (undoing the JS template-literal double-
backslash escaping the three `.js` sites carry, and substituting the site's base-ref placeholder
with a real git ref), builds a real git-repo fixture per scenario, executes each extracted
script against it with `cwd` set to the fixture, and asserts:

  1. the exit code matches the expected verdict for that scenario, and
  2. all four sites produce the SAME exit code for every scenario.

A case where the four disagree is exactly the bug this ticket exists to remove, so this
suite must be ABLE to fail on it -- it does not special-case around a real divergence.

NOT registered in planning/harness.json yet (that happens in task 4, "register at the end") --
run directly: python3 scripts/test_emoji_gate_diff_scoped.py
"""

from __future__ import annotations

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
    "sdlc-block.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-block.js",
    "sdlc-task.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js",
    "sdlc-flow.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js",
}

# The template-literal placeholder each JS site substitutes for the diff base ref.
# test.md has none -- it hardcodes `main..HEAD` directly.
BASE_REF_PLACEHOLDER = {
    "sdlc-block.js": "${baseRef}",
    "sdlc-task.js": "${baseSha}",
    "sdlc-flow.js": "${prBase}",
}

SITE_NAMES = ["test.md", "sdlc-block.js", "sdlc-task.js", "sdlc-flow.js"]

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

    if site != "test.md":
        # The three .js sites embed this script inside a JS template literal, where every
        # literal backslash is doubled (`\\U0001F300` on disk -> `\U0001F300` at runtime).
        # Undo that so the extracted text is valid, directly-executable Python.
        script = script.replace("\\\\", "\\")
        placeholder = BASE_REF_PLACEHOLDER[site]
        if placeholder not in script:
            raise AssertionError(f"{site}: expected base-ref placeholder {placeholder!r} in extracted script")
        script = script.replace(placeholder, "main")

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


def run_site_script(site: str, repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", EMOJI_SCRIPTS[site]],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class EmojiGateFixture:
    """One disposable git repo: a `main` commit (the "already-merged legacy state") plus a
    `feature` branch commit (the "task's own diff"). All four sites diff feature-branch HEAD
    against `main`."""

    def __init__(self, tmpdir: str):
        self.path = Path(tmpdir)
        init_fixture_repo(self.path)

    def base_commit(self, files: dict) -> None:
        for relpath, content in files.items():
            write_file(self.path, relpath, content)
        commit_all(self.path, "base (legacy state)")
        run_git(["checkout", "-b", "feature"], self.path)

    def task_commit(self, files: dict | None = None, renames: list[tuple[str, str]] | None = None) -> None:
        for old, new in renames or []:
            run_git(["mv", old, new], self.path)
        for relpath, content in (files or {}).items():
            write_file(self.path, relpath, content)
        commit_all(self.path, "task work")


def run_all_sites(repo: Path) -> dict[str, subprocess.CompletedProcess]:
    return {site: run_site_script(site, repo) for site in SITE_NAMES}


class EmojiGateDiffScopedTest(unittest.TestCase):
    """Every test asserts BOTH the expected verdict AND that all four sites agree."""

    def setUp(self):
        self._tmpdirs: list[str] = []

    def tearDown(self):
        for d in self._tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    def new_fixture(self) -> EmojiGateFixture:
        tmpdir = tempfile.mkdtemp(prefix="emoji-gate-fixture-")
        self._tmpdirs.append(tmpdir)
        return EmojiGateFixture(tmpdir)

    def assert_all_sites(self, repo: Path, expect_pass: bool, msg: str) -> dict[str, subprocess.CompletedProcess]:
        results = run_all_sites(repo)
        codes = {site: r.returncode for site, r in results.items()}
        unique = set(codes.values())
        self.assertEqual(
            len(unique), 1,
            f"{msg}: the four sites DISAGREE on verdict -- {codes}\n"
            + "\n".join(f"--- {s} ---\n{r.stdout}{r.stderr}" for s, r in results.items()),
        )
        expected_code = 0 if expect_pass else 1
        actual_code = unique.pop()
        self.assertEqual(
            actual_code, expected_code,
            f"{msg}: expected exit {expected_code} ({'PASS' if expect_pass else 'FAIL'}), "
            f"got {actual_code} from all four sites.\n"
            + "\n".join(f"--- {s} ---\n{r.stdout}{r.stderr}" for s, r in results.items()),
        )
        return results

    # -- headline case ------------------------------------------------------------------

    def test_clean_line_added_to_file_with_preexisting_emoji_passes(self):
        fx = self.new_fixture()
        fx.base_commit({
            "docs/legacy.md": "# Legacy\n\nAlready shipped line one \U0001F680\n"
            "Already shipped line two ✅\n"
            "Already shipped line three \U0001F389\n",
        })
        fx.task_commit(files={
            "docs/legacy.md": "# Legacy\n\nAlready shipped line one \U0001F680\n"
            "Already shipped line two ✅\n"
            "Already shipped line three \U0001F389\n"
            "One brand-new, perfectly clean line.\n",
        })
        self.assert_all_sites(
            fx.path, expect_pass=True,
            msg="a clean line appended to a legacy file with pre-existing emoji must PASS",
        )

    # -- the gate can still fail, and must say where ------------------------------------

    def test_line_with_emoji_added_fails_and_names_file_and_line(self):
        fx = self.new_fixture()
        fx.base_commit({"docs/notes.md": "line one\nline two\n"})
        fx.task_commit(files={"docs/notes.md": "line one\nline two\nline three has an emoji ✅\n"})
        results = self.assert_all_sites(
            fx.path, expect_pass=False,
            msg="a newly added line containing an emoji must FAIL",
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
        fx.task_commit(renames=[("docs/legacy.md", "docs/renamed.md")])
        self.assert_all_sites(
            fx.path, expect_pass=True,
            msg="a pure rename of a file containing emoji (no content change) must PASS",
        )

    # -- new file -----------------------------------------------------------------------

    def test_new_file_with_emoji_fails(self):
        fx = self.new_fixture()
        fx.base_commit({"README.md": "hello\n"})
        fx.task_commit(files={"docs/brand_new.md": "This whole file is new \U0001F680\n"})
        self.assert_all_sites(
            fx.path, expect_pass=False,
            msg="a brand-new file containing an emoji must FAIL (its added lines are its whole content)",
        )

    # -- diff header artifact ------------------------------------------------------------

    def test_plus_plus_plus_header_never_treated_as_content(self):
        fx = self.new_fixture()
        fx.base_commit({"README.md": "hello\n"})
        # The new file's PATH itself carries an emoji-range character, so the `+++ b/<path>`
        # diff header line contains an emoji -- but the file's CONTENT is clean. If the header
        # were ever mistaken for an added-content line, this would wrongly FAIL.
        fx.task_commit(files={"docs/notes✅.md": "perfectly clean content\nsecond clean line\n"})
        self.assert_all_sites(
            fx.path, expect_pass=True,
            msg="the `+++ b/<path>` diff header must never be scanned as added content, "
            "even when the path itself contains an emoji character",
        )

    # -- PR-footer exemption --------------------------------------------------------------

    def test_pr_footer_phrase_is_exempt(self):
        fx = self.new_fixture()
        fx.base_commit({"docs/notes.md": "line one\n"})
        fx.task_commit(files={
            "docs/notes.md": "line one\n\U0001F916 Generated with Claude Code\n",
        })
        self.assert_all_sites(
            fx.path, expect_pass=True,
            msg="the literal 'Generated with Claude Code' PR-footer phrase must stay exempt "
            "at every site, even though it carries the robot emoji",
        )

    # -- .mdx parity ------------------------------------------------------------------

    def test_mdx_file_with_emoji_fails_same_as_md(self):
        fx = self.new_fixture()
        fx.base_commit({"README.md": "hello\n"})
        fx.task_commit(files={"docs/guide.mdx": "This is new mdx content \U0001F680\n"})
        self.assert_all_sites(
            fx.path, expect_pass=False,
            msg=".mdx files must be scanned identically to .md files at all four sites",
        )

    # -- the suite must be able to detect real disagreement ------------------------------

    def test_suite_can_detect_disagreement(self):
        """Not a gate scenario -- proves assert_all_sites actually fails on divergence,
        so a future regression that makes the four sites disagree cannot pass silently."""
        fake_results = {
            "test.md": subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            "sdlc-block.js": subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=""),
            "sdlc-task.js": subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            "sdlc-flow.js": subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        }
        codes = {site: r.returncode for site, r in fake_results.items()}
        self.assertNotEqual(
            len(set(codes.values())), 1,
            "sanity check itself is broken: this synthetic fixture must show disagreement",
        )


class ExtractionSanityTest(unittest.TestCase):
    """The extraction itself must be honest: fail loudly if a source file no longer contains
    exactly one recognizable emoji-gate script, rather than silently testing stale text."""

    def test_all_four_sites_extract_a_single_script(self):
        for site in SITE_NAMES:
            script = EMOJI_SCRIPTS[site]
            self.assertIn("EMOJI = re.compile", script)
            self.assertIn("git", script)
            self.assertIn("diff", script)
            # Added-line scoping, not whole-file scoping -- the regression this ticket fixes.
            self.assertIn("-U0", script, f"{site}: script must use -U0 (added-line hunks only)")
            self.assertNotIn("--name-only", script, f"{site}: script must not fall back to file-list scoping")
            if site != "test.md":
                self.assertNotIn("${", script, f"{site}: unsubstituted template placeholder leaked through")


if __name__ == "__main__":
    unittest.main()
