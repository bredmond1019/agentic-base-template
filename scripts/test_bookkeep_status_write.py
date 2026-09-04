#!/usr/bin/env python3
"""Fixture suite for the bookkeep/wrap-up stage's `planning/`-relative `status.md` write
(BT.ticket.bookkeep-writes-invalid-status-frontmatter, task 1).

WHY THIS EXISTS
----------------
One engine-rs session on 2026-08-18 hit three distinct corpus breaks from sdlc-task/sdlc-flow's
bookkeep stage, each red-gating pre-push stage 1 for EVERY concurrent lane in the fleet, not just
the authoring one:

  1. FRONTMATTER-DESTROYING INSERT (EN.ticket.term-core-real-tmux-option-reads) -- a Recent Work /
     Current focus row inserted immediately after status.md's OPENING `---` instead of the CLOSING
     one, which destroys the frontmatter block entirely (mev: E_SYNC_WATERMARK_MALFORMED, "no
     frontmatter block found").
  2. BARE-DATE TIMESTAMP (EN.9.F) -- `timestamp: "2026-08-18"` written into the frontmatter, not a
     full RFC3339 value (mev: E_SYNC_WATERMARK_MALFORMED, "not valid RFC3339: premature end of
     input").
  3. SYNCED_FROM DRIFT (EN.9.D) -- status.md's `timestamp` moved while the HQ cache doc's
     `synced_from` was left behind (mev: E_SYNC_DRIFT).

One root cause: a generator that writes into the corpus and never validates its own output (the
rule already written down in the brain root's CLAUDE.md). Tasks 2-4 of this ticket make both
engines' bookkeep/wrap-up stage embed ONE scripted, validated status.md mutation -- named
`renderStatusWriteScript`, the direct sibling of the existing `renderStateFlipScript` this repo
already uses for the analogous `planning/state.json` write (see scripts/test_state_write_validation
.py) -- that:

  - never writes into the frontmatter block at all (the body `**Last updated:**` line is the only
    date field this stage owns; `timestamp` is derived by `mev emit-state` and is off-limits, per
    task 2's re-derivation);
  - inserts new body content strictly AFTER the closing `---` fence, never the opening one;
  - runs `mev validate-brain` (base + `--sync`, one flag per invocation, never combined) BEFORE and
    AFTER the write and rejects -- byte-exact rollback -- any write that introduces a diagnostic
    line NOT present in the BEFORE baseline (D64-style delta attribution, the same rule
    hooks/pre-push stage 1 and the state.json flip script already implement).

This is a source-assertion-plus-execution suite, not a live-agent suite, on exactly the same
footing as scripts/test_state_write_validation.py: the mutation script is embedded inside each
engine's LLM-facing prompt template as literal Python source (the agent copies and runs it
verbatim; the engine's own `.js` code never executes it). There is nothing to import and
unit-test the way scripts/check_skill_sync.py tests a real Python module, so this suite EXTRACTS
the literal script text from each engine's live source (by content markers, never a disposable
hand-copy) and actually runs it as a subprocess against synthetic fixtures, with a stub `mev`
standing in for the real tool so every case is hermetic.

TASK 1 SCOPE: this suite is written and run RED against the UNFIXED engines (neither currently
embeds `renderStatusWriteScript` at all -- tasks 2-4 add it). Per BT.ticket.gates-must-be-observed-
red, a suite green on its first run against the unfixed tree has detected nothing. This suite is
run only against a DISPOSABLE fake repo tree under a tempdir -- never against the real corpus, and
never against this repo's own live status.md under planning/.

Run: python3 scripts/test_bookkeep_status_write.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".claude" / "workflows"

ENGINE_FILES = ["sdlc-task.js", "sdlc-flow.js"]

# Markers the embedded status-write mutation script (added by tasks 2-4, function
# `renderStatusWriteScript`) is expected to carry. Content-anchored, not a line number or a
# hand-copy, so this suite tests the SAME bytes the agent would actually run.
SCRIPT_START_MARKER = "import re, subprocess, sys, shutil"
SCRIPT_END_MARKER = "print('STATUS_WRITE:' + outcome)"


def extract_status_write_script(engine_filename: str) -> str:
    """Pull the literal validated status.md-write mutation script out of an engine's live prompt
    text. Raises AssertionError (not a bare KeyError/None) when the contract is absent or has
    drifted, so a caller can report WHY extraction failed rather than crash opaquely -- exactly
    the failure this suite is meant to surface while the unfixed engines carry no such script at
    all.
    """
    path = WORKFLOWS / engine_filename
    source = path.read_text(encoding="utf-8")
    start = source.find(SCRIPT_START_MARKER)
    if start == -1:
        raise AssertionError(
            f"{engine_filename}: could not find the status-write mutation script "
            f"(marker {SCRIPT_START_MARKER!r} not present) -- the bookkeep/wrap-up stage does not "
            f"yet embed a validated status.md write under planning/ (BT.ticket.bookkeep-writes-invalid-"
            f"status-frontmatter tasks 2-4 add it)."
        )
    end_marker_pos = source.find(SCRIPT_END_MARKER, start)
    if end_marker_pos == -1:
        raise AssertionError(
            f"{engine_filename}: found the script start but not its end marker "
            f"({SCRIPT_END_MARKER!r}) -- the script may have been truncated or rewritten."
        )
    end = end_marker_pos + len(SCRIPT_END_MARKER)
    script = source[start:end]
    for required in (
        "mev_available = shutil.which('mev')",
        "net_new = after - baseline",
        "print('STATUS_REJECTED:",
        "frontmatter",
    ):
        if required not in script:
            raise AssertionError(
                f"{engine_filename}: extracted script is missing {required!r} -- extraction "
                f"markers matched the wrong region or the contract changed shape."
            )
    return script


GOOD_STATUS_MD = """---
type: ProjectStatus
title: Fake Status
description: fixture only.
doc_id: fake-status
layer: [factory]
status: active
timestamp: 2026-09-01T10:00:00-03:00
---

# STATUS

**Last updated:** 2026-09-01 (nothing yet)

## Current focus

- 2026-09-01: initial fixture line
"""


def write_fake_mev(bin_dir: Path, before_error: str, after_error: str) -> Path:
    """A stub `mev` whose successive invocations return controlled, call-order-keyed output -- the
    FIRST call (pre-write baseline) returns `before_error`, every call after returns `after_error`.
    Isolates rollback/surfacing/delta-attribution behaviour from real validate-brain semantics.
    """
    counter_path = bin_dir / ".mev_call_count"
    body = f'''#!{sys.executable}
import sys

counter_path = {str(counter_path)!r}
try:
    with open(counter_path) as fh:
        n = int(fh.read().strip() or "0")
except FileNotFoundError:
    n = 0
with open(counter_path, "w") as fh:
    fh.write(str(n + 1))

out = {before_error!r} if n == 0 else {after_error!r}
if out:
    print(out)
    sys.exit(1)
sys.exit(0)
'''
    mev_path = bin_dir / "mev"
    mev_path.write_text(body, encoding="utf-8")
    mev_path.chmod(0o755)
    return mev_path


def run_status_write_script(
    engine_filename: str,
    run_dir: Path,
    recent_work_line: str,
    last_updated_date: str,
    *,
    mev_bin_dir: Path | None,
):
    """Execute the extracted mutation script exactly as the agent would, in `run_dir` (which must
    already contain a `status.md` under `planning/`). Returns the CompletedProcess.

    `mev_bin_dir=None` means "mev absent": PATH is scrubbed of any directory containing a real
    `mev` binary so `shutil.which('mev')` genuinely returns None inside the child.
    """
    script = extract_status_write_script(engine_filename)
    argv = [sys.executable, "-c", script, recent_work_line, last_updated_date]
    env = os.environ.copy()
    env["PATH"] = str(mev_bin_dir) if mev_bin_dir is not None else os.defpath
    return subprocess.run(argv, cwd=run_dir, env=env, capture_output=True, text=True)


def make_run_dir(td: str, status_md: str = GOOD_STATUS_MD) -> Path:
    run_dir = Path(td)
    (run_dir / "planning").mkdir(parents=True, exist_ok=True)
    (run_dir / "planning" / "status.md").write_text(status_md, encoding="utf-8")
    return run_dir


class ExtractionSanity(unittest.TestCase):
    """The extraction itself must succeed for both engines -- if it can't find the contract, every
    downstream case in this file is testing nothing. THIS is expected to fail against the unfixed
    engines (task 1's observed-red evidence): neither sdlc-task.js nor sdlc-flow.js embeds
    `renderStatusWriteScript` yet."""

    def test_both_engines_carry_the_extractable_contract(self):
        failures = []
        for engine in ENGINE_FILES:
            try:
                extract_status_write_script(engine)
            except AssertionError as exc:
                failures.append(str(exc))
        if failures:
            self.fail("\n  ".join(failures))


class Case1FrontmatterDestroyingInsert(unittest.TestCase):
    """EN.ticket.term-core-real-tmux-option-reads: a Recent Work row inserted immediately after
    status.md's OPENING `---` destroys the frontmatter block. The script's own insert must land
    after the CLOSING `---` so the frontmatter survives, and this suite proves it both ways: a
    hand-corrupted 'insert after opening fence' fixture is caught (mev sees a missing/undelimited
    frontmatter block and reports it as a net-new error), while the script's OWN insert -- run
    against clean input -- lands after the closing fence and passes."""

    def test_script_insert_lands_after_closing_fence_not_opening(self):
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                with tempfile.TemporaryDirectory() as td:
                    run_dir = make_run_dir(td)
                    bin_dir = Path(td) / "bin"
                    bin_dir.mkdir()
                    write_fake_mev(bin_dir, before_error="", after_error="")

                    result = run_status_write_script(
                        engine, run_dir, "- 2026-09-02: fixture row", "2026-09-02",
                        mev_bin_dir=bin_dir,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    written = (run_dir / "planning" / "status.md").read_text(encoding="utf-8")

                    fences = [i for i, line in enumerate(written.splitlines())
                              if line.strip() == "---"]
                    self.assertGreaterEqual(
                        len(fences), 2,
                        f"{engine}: frontmatter block did not survive the write:\n{written}",
                    )
                    insert_line = next(
                        i for i, line in enumerate(written.splitlines())
                        if "fixture row" in line
                    )
                    self.assertGreater(
                        insert_line, fences[1],
                        f"{engine}: the new row landed at or before the CLOSING fence "
                        f"(line {insert_line} vs closing fence at {fences[1]}) -- this is exactly "
                        f"the EN.ticket.term-core-real-tmux-option-reads break",
                    )

    def test_opening_fence_insert_is_caught_as_a_net_new_error(self):
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                # Simulate the historical break directly: mev reports a net-new diagnostic on the
                # AFTER call only, standing in for "the frontmatter block is gone / malformed".
                with tempfile.TemporaryDirectory() as td:
                    run_dir = make_run_dir(td)
                    bin_dir = Path(td) / "bin"
                    bin_dir.mkdir()
                    write_fake_mev(
                        bin_dir, before_error="",
                        after_error="[E_SYNC_WATERMARK_MALFORMED] no frontmatter block found",
                    )
                    result = run_status_write_script(
                        engine, run_dir, "- 2026-09-02: fixture row", "2026-09-02",
                        mev_bin_dir=bin_dir,
                    )
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("STATUS_REJECTED", result.stdout)
                    self.assertIn("E_SYNC_WATERMARK_MALFORMED", result.stdout)


class Case2BareDateTimestamp(unittest.TestCase):
    """EN.9.F: `timestamp: "2026-08-18"` written into the frontmatter -- a bare date, not RFC3339.
    Per task 2's re-derivation, the frontmatter block (including `timestamp`) is not this stage's
    to write at all -- so the script's own write must leave it byte-identical, and a fixture where
    it was hand-corrupted to a bare date is caught."""

    def test_script_never_touches_the_frontmatter_timestamp_field(self):
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                with tempfile.TemporaryDirectory() as td:
                    run_dir = make_run_dir(td)
                    bin_dir = Path(td) / "bin"
                    bin_dir.mkdir()
                    write_fake_mev(bin_dir, before_error="", after_error="")

                    result = run_status_write_script(
                        engine, run_dir, "- 2026-09-02: fixture row", "2026-09-02",
                        mev_bin_dir=bin_dir,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    written = (run_dir / "planning" / "status.md").read_text(encoding="utf-8")
                    self.assertIn(
                        "timestamp: 2026-09-01T10:00:00-03:00", written,
                        f"{engine}: frontmatter timestamp changed -- this stage must never write "
                        f"it (mev emit-state owns it)",
                    )

    def test_bare_date_in_frontmatter_is_caught(self):
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                with tempfile.TemporaryDirectory() as td:
                    run_dir = make_run_dir(td)
                    bin_dir = Path(td) / "bin"
                    bin_dir.mkdir()
                    write_fake_mev(
                        bin_dir, before_error="",
                        after_error='[E_SYNC_WATERMARK_MALFORMED] not valid RFC3339: '
                                    'premature end of input',
                    )
                    result = run_status_write_script(
                        engine, run_dir, "- 2026-09-02: fixture row", "2026-09-02",
                        mev_bin_dir=bin_dir,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("STATUS_REJECTED", result.stdout)
                    self.assertIn("not valid RFC3339", result.stdout)


class Case3SyncedFromDrift(unittest.TestCase):
    """EN.9.D: status.md's `timestamp` moved while the HQ cache doc's `synced_from` was left
    behind -- mev's E_SYNC_DRIFT. The script never moves `timestamp` at all (Case 2), which is
    what keeps the two from going out of step in the first place; this case pins that a drift
    diagnostic occurring anyway (e.g. from a sibling write this stage doesn't control) is still
    caught by the same before/after delta check, not silently absorbed."""

    def test_synced_from_drift_diagnostic_is_caught(self):
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                with tempfile.TemporaryDirectory() as td:
                    run_dir = make_run_dir(td)
                    bin_dir = Path(td) / "bin"
                    bin_dir.mkdir()
                    write_fake_mev(
                        bin_dir, before_error="",
                        after_error="[E_SYNC_DRIFT] docs/projects/fake.md: synced_from "
                                    "2026-09-01 does not match status.md (under planning/) timestamp "
                                    "2026-09-02T10:00:00-03:00",
                    )
                    result = run_status_write_script(
                        engine, run_dir, "- 2026-09-02: fixture row", "2026-09-02",
                        mev_bin_dir=bin_dir,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("STATUS_REJECTED", result.stdout)
                    self.assertIn("E_SYNC_DRIFT", result.stdout)

                    # Byte-exact rollback, same contract as the state.json flip script.
                    on_disk = (run_dir / "planning" / "status.md").read_text(encoding="utf-8")
                    self.assertEqual(on_disk, GOOD_STATUS_MD)


class Case4DeltaAttributionNegative(unittest.TestCase):
    """THE MOST IMPORTANT CASE. A pre-existing, UNRELATED corpus error present before the stage
    runs must NOT fail the stage -- delta attribution asserted in the negative direction, per D64
    and per hooks/pre-push stage 1. A stage that fails on absolute error count refuses to close
    any block whenever a sibling lane has left the corpus red, which is a worse failure than the
    one this block fixes and is exactly how a check gets disabled. This mirrors the live instance
    measured 2026-09-03 in this lane: another session's untracked
    docs/sandbox/run-verification-ledger-prompt.md produced E_STRUCT_ORPHAN_FILE on every commit,
    and the pre-commit hook correctly did not block."""

    def test_pre_existing_unrelated_error_does_not_block_the_write(self):
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                with tempfile.TemporaryDirectory() as td:
                    run_dir = make_run_dir(td)
                    bin_dir = Path(td) / "bin"
                    bin_dir.mkdir()
                    # SAME error before and after -- a sibling lane's pre-existing breakage,
                    # unrelated to this write. Must not be treated as net-new.
                    write_fake_mev(
                        bin_dir,
                        before_error="[E_STRUCT_ORPHAN_FILE] docs/sandbox/unrelated.md: "
                                     "orphaned, not referenced by any index.md",
                        after_error="[E_STRUCT_ORPHAN_FILE] docs/sandbox/unrelated.md: "
                                    "orphaned, not referenced by any index.md",
                    )
                    result = run_status_write_script(
                        engine, run_dir, "- 2026-09-02: fixture row", "2026-09-02",
                        mev_bin_dir=bin_dir,
                    )
                    self.assertEqual(
                        result.returncode, 0,
                        f"{engine}: a pre-existing, unchanged error incorrectly blocked the "
                        f"write: {result.stdout}{result.stderr}",
                    )
                    self.assertIn("STATUS_WRITE:written", result.stdout)
                    self.assertNotIn("STATUS_REJECTED", result.stdout)

                    written = (run_dir / "planning" / "status.md").read_text(encoding="utf-8")
                    self.assertIn("fixture row", written)


if __name__ == "__main__":
    unittest.main()
