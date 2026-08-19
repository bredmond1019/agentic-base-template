#!/usr/bin/env python3
"""Fixture suite for the engine-parse-safety gate's .js-only extension filter (ticket
BT.ticket.engine-parse-gate-non-js-false-positive).

WHY THIS EXISTS
----------------
`renderEngineParseChecks()` in sdlc-task.js, sdlc-flow.js, and sdlc-run.js renders one `node
--check` CHECK per `.claude/workflows/` file a task's `files[]` names. `node --check` throws
ERR_UNKNOWN_FILE_EXTENSION on any non-.js path regardless of content, so before this ticket a task
that merely touched block-registration.md, block.schema.json, or harness.schema.json (the three
non-JS files that currently live under `.claude/workflows/`) bailed the whole verdict on a false
positive unrelated to its actual change. Tasks 1-3 added an identical one-line filter
(`files = (files || []).filter(f => f.endsWith('.js'))`) to the top of all three copies of the
function. This suite extracts each engine's live `renderEngineParseChecks()` source by content
marker (mirroring test_state_write_validation.py's extraction pattern) and actually executes it
under Node against fixture inputs, so a regression in any of the three copies goes red here rather
than silently reappearing at spec-authoring time.

Run: python3 scripts/test_engine_parse_gate_extension_filter.py
"""

from __future__ import annotations

import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".claude" / "workflows"

FUNCTION_START_MARKER = "function renderEngineParseChecks("
FUNCTION_NAME = "renderEngineParseChecks"

# sdlc-task.js/sdlc-flow.js: (files, cd, startIndex). sdlc-run.js: (files, startIndex) -- no `cd`.
ENGINES_WITH_CD = {"sdlc-task.js", "sdlc-flow.js"}
ENGINES_WITHOUT_CD = {"sdlc-run.js"}
ALL_ENGINES = sorted(ENGINES_WITH_CD | ENGINES_WITHOUT_CD)

NON_JS_PATHS = [
    ".claude/workflows/block-registration.md",
    ".claude/workflows/block.schema.json",
    ".claude/workflows/harness.schema.json",
]
JS_PATH = ".claude/workflows/some-modified-engine.js"


def extract_render_function(engine_filename: str) -> str:
    """Pull the literal `function renderEngineParseChecks(...) { ... }` source out of an engine's
    live file, by scanning braces from the signature line to its matching closing brace -- content-
    anchored, not a line number, so a reflow elsewhere in the file cannot silently break extraction.
    """
    path = WORKFLOWS / engine_filename
    source = path.read_text(encoding="utf-8")
    start = source.find(FUNCTION_START_MARKER)
    if start == -1:
        raise AssertionError(
            f"{engine_filename}: could not find {FUNCTION_START_MARKER!r} -- has "
            f"{FUNCTION_NAME}() been removed or renamed?"
        )
    # Walk forward from the first '{' after the signature, tracking brace depth (naive but
    # sufficient here: the function body contains no braces inside string/template literals that
    # would throw off a depth count -- verified against current source).
    brace_open = source.find("{", start)
    if brace_open == -1:
        raise AssertionError(f"{engine_filename}: found the signature but no opening brace.")
    depth = 0
    i = brace_open
    end = -1
    while i < len(source):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    if end == -1:
        raise AssertionError(f"{engine_filename}: could not find the matching closing brace.")
    func_src = source[start:end]
    if ".endsWith('.js')" not in func_src and '.endsWith(".js")' not in func_src:
        raise AssertionError(
            f"{engine_filename}: extracted {FUNCTION_NAME}() does not filter to .js files -- "
            f"has the extension filter been removed?"
        )
    return func_src


def run_render(engine_filename: str, files: list[str]) -> str:
    """Execute the extracted function under Node with a small harness appended, matching each
    engine's real call signature, and return the rendered string."""
    func_src = extract_render_function(engine_filename)
    files_json = json.dumps(files)
    if engine_filename in ENGINES_WITH_CD:
        call = f"{FUNCTION_NAME}({files_json}, '', 1)"
    else:
        call = f"{FUNCTION_NAME}({files_json}, 1)"
    harness = f"\n\nconsole.log(JSON.stringify({call}))\n"
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node is not on PATH")
    with tempfile.NamedTemporaryFile(
        "w", suffix=".js", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(func_src + harness)
        tmp_path = fh.name
    try:
        result = subprocess.run(
            [node, tmp_path], capture_output=True, text=True, timeout=30
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    if result.returncode != 0:
        raise AssertionError(
            f"{engine_filename}: node execution failed: {result.stdout}{result.stderr}"
        )
    return json.loads(result.stdout.strip())


class ExtractionSanity(unittest.TestCase):
    """Extraction must succeed and land on the .js-filtered function for all three engines --
    if it can't find the contract, every downstream case here tests nothing."""

    def test_all_three_engines_carry_the_js_only_filter(self):
        failures = []
        for engine in ALL_ENGINES:
            try:
                extract_render_function(engine)
            except AssertionError as exc:
                failures.append(str(exc))
        if failures:
            self.fail("\n  ".join(failures))


class MixedInputRendersOnlyTheJsPath(unittest.TestCase):
    """A mixed files[] (one .js path + the three real non-JS .claude/workflows/ paths) must
    render exactly one CHECK block, referencing only the .js path."""

    def test_mixed_input(self):
        for engine in ALL_ENGINES:
            with self.subTest(engine=engine):
                rendered = run_render(engine, [JS_PATH] + NON_JS_PATHS)
                # Count CHECK-block headers, not "node --check" occurrences: the block's prose
                # legitimately names the command more than once when warning the test agent not
                # to substitute its own unguarded form.
                self.assertEqual(
                    len(re.findall(r"^CHECK \d+ \u2014 engine-parse-safety", rendered, re.M)), 1,
                    f"{engine}: expected exactly one CHECK block, got: {rendered!r}",
                )
                self.assertIn(
                    JS_PATH, rendered,
                    f"{engine}: rendered output must reference the .js path",
                )
                for non_js in NON_JS_PATHS:
                    self.assertNotIn(
                        non_js, rendered,
                        f"{engine}: rendered output must NOT reference non-JS path {non_js}",
                    )


class AllNonJsInputRendersEmpty(unittest.TestCase):
    """An all-non-JS files[] (the three real non-JS .claude/workflows/ paths, no .js path at
    all) must render '' -- the same no-op as the pre-existing empty-input case."""

    def test_all_non_js_input(self):
        for engine in ALL_ENGINES:
            with self.subTest(engine=engine):
                rendered = run_render(engine, list(NON_JS_PATHS))
                self.assertEqual(
                    rendered, "",
                    f"{engine}: all-non-JS input must render '', got: {rendered!r}",
                )


class EmptyInputStillRendersEmpty(unittest.TestCase):
    """Regression guard: the pre-existing empty/falsy-input no-op must still hold after the
    filter was added."""

    def test_empty_list_renders_empty(self):
        for engine in ALL_ENGINES:
            with self.subTest(engine=engine):
                rendered = run_render(engine, [])
                self.assertEqual(rendered, "")


class DeletedEngineFileIsNotAParseFailure(unittest.TestCase):
    """A task that DELETES an SDLC engine legitimately names it in its own tasks.json files[],
    so this gate would run `node --check` on a path that no longer exists and get
    MODULE_NOT_FOUND -- a check that can never pass, whatever the task does.

    That is not hypothetical: it bailed BT.ticket.retire-unused-engines twice on 2026-08-19,
    a ticket whose entire purpose is deleting sdlc-block.js and sdlc-run.js. The only escapes
    were to lie in files[] (omitting the very files the acceptance criteria say must be gone)
    or to hand-edit the shared engine mid-run. The gate now guards on existence first: a file
    that is gone has no syntax to be wrong.

    The two survivors are the only engines that can carry the fix -- sdlc-run.js is itself
    being retired, so it is excluded here rather than patched.
    """

    GUARDED_ENGINES = sorted(ENGINES_WITH_CD)

    def test_render_guards_on_existence_before_parsing(self):
        for engine in self.GUARDED_ENGINES:
            with self.subTest(engine=engine):
                rendered = run_render(engine, [".claude/workflows/sdlc-block.js"])
                self.assertIn(
                    "if [ -f", rendered,
                    f"{engine}: engine-parse check must test for the file's existence before "
                    "running node --check, or a deleting task can never pass its own gate",
                )
                self.assertIn("does not exist", rendered)
                self.assertIn(
                    "node --check", rendered,
                    f"{engine}: the guard must still parse the file when it IS present -- "
                    "guarding must not disable the check",
                )

    def test_guard_shell_passes_when_absent_and_still_fails_on_bad_syntax(self):
        """Execute the rendered guard's shell semantics for real: absent -> 0, valid -> 0,
        syntactically broken -> non-zero. Without the last assertion this suite would happily
        accept a guard that had been neutered into always passing."""
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.js")
            bad = os.path.join(tmp, "bad.js")
            missing = os.path.join(tmp, "missing.js")
            with open(good, "w", encoding="utf-8") as fh:
                fh.write("const a = 1\n")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write("const = =\n")

            def guard_exit(path: str) -> int:
                script = (
                    f'if [ -f {path} ]; then node --check {path}; '
                    f'else echo "does not exist"; fi'
                )
                return subprocess.run(
                    ["bash", "-c", script], capture_output=True, text=True
                ).returncode

            self.assertEqual(guard_exit(missing), 0, "a deleted file must not fail the gate")
            self.assertEqual(guard_exit(good), 0, "a valid engine must still pass")
            self.assertNotEqual(
                guard_exit(bad), 0,
                "a syntactically broken engine must STILL fail -- the existence guard must not "
                "have turned this gate into one that cannot fail",
            )


if __name__ == "__main__":
    unittest.main()
