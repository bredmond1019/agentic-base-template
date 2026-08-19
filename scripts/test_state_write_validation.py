#!/usr/bin/env python3
"""Fixture suite for the state.json validate-then-commit contract (ticket-engine-state-write-
validates-before-commit).

WHY THIS EXISTS
----------------
Tasks 1-3 of this ticket made `sdlc-task.js`'s bookkeep stage and `sdlc-flow.js`'s wrap-up stage
each embed the SAME scripted Python mutation (two other engines got the same embed at the time but
have since been retired as effectively unused -- BT.ticket.retire-unused-engines): capture the
pre-write bytes of `planning/state.json`, flip one block's `status`
field in memory, run `mev validate-brain --state` BEFORE and AFTER writing the mutated bytes to
disk, and reject (byte-exact rollback) any write that introduces diagnostic lines NOT present in
the BEFORE baseline (D64-style delta attribution). Before this ticket, the only check was
`json.load(open('planning/state.json'))` -- proof of PARSE validity, not SCHEMA validity. On
2026-08-09 a scalar `"origin": "D57"` where the schema types `origin` as a struct parsed fine as
JSON, passed that check, and cascaded into 31 `validate-brain` errors that blocked every other
repo's push gate.

This is a source-assertion-plus-execution suite, not a live-agent suite: the mutation script is
embedded inside each engine's LLM-facing prompt template as literal Python source (the agent
copies and runs it verbatim; the engine's own `.js` code never executes it). There is nothing to
import and unit-test the way `scripts/check_skill_sync.py` tests a real Python module -- so this
suite EXTRACTS the literal script text from each engine's live source (by content markers, never a
disposable hand-copy) and actually runs it as a subprocess against synthetic fixtures, with a stub
`mev` binary standing in for the real tool so every case is hermetic and has no dependence on the
live corpus or on `mev` being installed. If the embedded script in any engine drifts from what
these fixtures exercise, extraction either fails outright (source assertion) or the behavioural
assertions fail against the drifted text -- either way this suite goes red, which is the point.

REQUIRED CASES (each demonstrably able to fail; see the docstring on each test method):
  1. THE CONTRAST THAT IS THE WHOLE TICKET -- the 2026-08-09 payload (`"origin": "D57"` where the
     schema wants an `Origin` struct) passes `json.load` and is rejected by `mev validate-brain
     --state`.
  2. Rollback is byte-exact: a rejected write leaves `state.json` identical to its pre-write bytes.
  3. A rejected write surfaces (REJECTED:<id>, exit 1, NET_NEW: lines) rather than silently
     swallowing the block close.
  4. Delta attribution: a fixture corpus already red before the write is not blocked by a write
     that introduces no NEW errors.
  5. Worktree mode: the mutation script contains no worktree-conditional branch -- task 1 decided
     this validation step runs identically in place and in a worktree (only `mev emit-state
     --write`, which this script never calls, is deferred).
  6. Absent `mev` degrades to a stated warning (UNVALIDATED:, exit 0), never a run failure.

Run: python3 scripts/test_state_write_validation.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".claude" / "workflows"

# Every surviving engine confirmed (task 3 audit) to embed the validate-then-commit mutation
# script. Two other engines formerly embedded it too but have since been retired as
# effectively unused (see the block record superseding D39 for the retirement rationale).
ENGINE_FILES = ["sdlc-task.js", "sdlc-flow.js"]
PARAMETRIC_STATUS_ENGINES: set[str] = set()

SCRIPT_START_MARKER = "import json, subprocess, sys, shutil"
SCRIPT_END_MARKER = "print('FLIPPED:' + bid)"


def extract_mutation_script(engine_filename: str) -> str:
    """Pull the literal validate-then-commit Python source out of an engine's live prompt text.

    Extraction is content-anchored (not a line number, not a hand-maintained copy) so this suite
    tests the SAME bytes the agent would actually run, and so an engine drifting away from the
    contract (e.g. losing the mev-before/after diff, or reverting to a bare json.load check) makes
    extraction fail loudly instead of silently testing stale text.
    """
    path = WORKFLOWS / engine_filename
    source = path.read_text(encoding="utf-8")
    start = source.find(SCRIPT_START_MARKER)
    if start == -1:
        raise AssertionError(
            f"{engine_filename}: could not find the state-write mutation script "
            f"(marker {SCRIPT_START_MARKER!r} not present) -- has the validate-then-commit "
            f"contract been removed or rewritten?"
        )
    # SCRIPT_END_MARKER ("print('FLIPPED:' + bid)") appears TWICE in the live script: once inside
    # the "mev not on PATH" early-return branch, and once as the script's final line after the
    # net-new diff. The genuine end is the LAST occurrence before the script's closing quote (which
    # is what a plain .find() from `start` would miss) -- anchor off the diff line instead and take
    # the next end-marker occurrence after that, which is unambiguous.
    diff_marker_pos = source.find("net_new = after - baseline", start)
    if diff_marker_pos == -1:
        raise AssertionError(
            f"{engine_filename}: found the script start but not the net-new diff line -- "
            f"the script may have been truncated or rewritten."
        )
    end_marker_pos = source.find(SCRIPT_END_MARKER, diff_marker_pos)
    if end_marker_pos == -1:
        raise AssertionError(
            f"{engine_filename}: found the script start but not its end marker "
            f"({SCRIPT_END_MARKER!r}) -- the script may have been truncated or rewritten."
        )
    end = end_marker_pos + len(SCRIPT_END_MARKER)
    script = source[start:end]
    # Sanity-check the extraction landed on the real contract, not a coincidental substring match.
    for required in (
        "mev_available = shutil.which('mev')",
        "def diagnostics():",
        "'mev', 'validate-brain', '--state'",
        "net_new = after - baseline",
        "print('REJECTED:' + bid)",
        "print('UNVALIDATED:",
    ):
        if required not in script:
            raise AssertionError(
                f"{engine_filename}: extracted script is missing {required!r} -- "
                f"extraction markers matched the wrong region or the contract changed shape."
            )
    return script


def state_json_bytes(blocks) -> bytes:
    data = {"tracks": [{"name": "main", "blocks": blocks}]}
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write_fake_mev_schema_mode(bin_dir: Path) -> Path:
    """A stub `mev validate-brain --state` that inspects planning/state.json for real: any block
    whose `origin` field is present and is not an object is reported as `[E_STATE_MALFORMED_JSON]`
    -- the exact 2026-08-09 shape (schema wants an `Origin` struct `{type, slug}`; a bare string
    parses as valid JSON but is not a valid struct). This is what makes case 1's contrast genuine
    rather than asserted-by-fiat: the same stub's exit code is what the extracted script's
    `diagnostics()` helper consumes.
    """
    body = f'''#!{sys.executable}
import json, sys

try:
    with open("planning/state.json", encoding="utf-8") as fh:
        data = json.load(fh)
except Exception as exc:
    print("[E_STATE_MALFORMED_JSON] planning/state.json: " + str(exc))
    sys.exit(1)

errors = []
for track in data.get("tracks", []):
    for block in track.get("blocks", []):
        origin = block.get("origin")
        if origin is not None and not isinstance(origin, dict):
            errors.append(
                "[E_STATE_MALFORMED_JSON] planning/state.json: block '" + str(block.get("id"))
                + "' origin must be an Origin struct {{type, slug}}, found "
                + type(origin).__name__
            )
for line in errors:
    print(line)
sys.exit(1 if errors else 0)
'''
    mev_path = bin_dir / "mev"
    mev_path.write_text(body, encoding="utf-8")
    mev_path.chmod(0o755)
    return mev_path


def write_fake_mev_callseq(bin_dir: Path, before_error: str, after_error: str) -> Path:
    """A stub `mev` whose two successive invocations return controlled, call-order-keyed output --
    the FIRST call (the script's pre-write baseline diagnostics) returns `before_error`, the
    SECOND (the post-write diagnostics) returns `after_error`. Each is '' for "no diagnostics" or a
    literal `[E_...]`/`[W_...]` line. This isolates rollback/surfacing/delta-attribution behaviour
    from schema semantics, which case 1 already covers directly.
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

outputs = [{before_error!r}, {after_error!r}]
out = outputs[n] if n < len(outputs) else outputs[-1]
if out:
    print(out)
    sys.exit(1)
sys.exit(0)
'''
    mev_path = bin_dir / "mev"
    mev_path.write_text(body, encoding="utf-8")
    mev_path.chmod(0o755)
    return mev_path


def run_mutation_script(
    engine_filename: str,
    run_dir: Path,
    block_id: str,
    *,
    new_status: str = "closed",
    mev_bin_dir: Path | None = None,
):
    """Execute the extracted mutation script exactly as the agent would, in `run_dir` (which must
    already contain `planning/state.json`). Returns the CompletedProcess.

    `mev_bin_dir=None` means "mev absent": PATH is scrubbed of any directory containing a real
    `mev` binary (this machine has one on `~/.cargo/bin` -- CLAUDE.md notes `mev` is a real
    fleet-wide tool) so `shutil.which('mev')` genuinely returns None inside the child, exactly as
    it would on an environment where `mev` was never installed.
    """
    script = extract_mutation_script(engine_filename)
    argv = [sys.executable, "-c", script, block_id]
    if engine_filename in PARAMETRIC_STATUS_ENGINES:
        argv.append(new_status)

    env = os.environ.copy()
    if mev_bin_dir is not None:
        env["PATH"] = str(mev_bin_dir)
    else:
        env["PATH"] = os.defpath  # stdlib default (/bin:/usr/bin-ish) -- no cargo/homebrew dirs
    return subprocess.run(argv, cwd=run_dir, env=env, capture_output=True, text=True)


class ExtractionSanity(unittest.TestCase):
    """The extraction itself must succeed for all four audited engines -- if it can't find the
    contract, every downstream case in this file is testing nothing."""

    def test_all_four_engines_carry_the_extractable_contract(self):
        failures = []
        for engine in ENGINE_FILES:
            try:
                extract_mutation_script(engine)
            except AssertionError as exc:
                failures.append(str(exc))
        if failures:
            self.fail("\n  ".join(failures))


class Case1JsonLoadVsMevContrast(unittest.TestCase):
    """The contrast that is the whole ticket: the 2026-08-09 payload passes json.load and is
    rejected by mev validate-brain --state. If this fails, either the malformed payload is not
    actually valid JSON (fixture bug) or the fake mev / real contract stopped discriminating it."""

    def test_malformed_origin_passes_json_load_but_fails_mev(self):
        payload = state_json_bytes(
            [{"id": "BT.1.a", "status": "open", "origin": "D57"}]  # scalar where a struct belongs
        )
        # Half 1: json.load succeeds -- this is the trap. A scalar where a struct belongs is
        # perfectly valid JSON; only typed deserialization (mev) can tell the difference.
        parsed = json.loads(payload)
        self.assertEqual(parsed["tracks"][0]["blocks"][0]["origin"], "D57")

        # Half 2: the new check (mev validate-brain --state) rejects it.
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "planning").mkdir()
            (run_dir / "planning" / "state.json").write_bytes(payload)
            bin_dir = run_dir / "bin"
            bin_dir.mkdir()
            write_fake_mev_schema_mode(bin_dir)
            env = os.environ.copy()
            env["PATH"] = str(bin_dir)
            result = subprocess.run(
                ["mev", "validate-brain", "--state"], cwd=run_dir, env=env,
                capture_output=True, text=True,
            )
            self.assertNotEqual(
                result.returncode, 0,
                "mev validate-brain --state must reject a scalar origin field; "
                f"stdout={result.stdout!r} stderr={result.stderr!r}",
            )
            self.assertIn("E_STATE_MALFORMED_JSON", result.stdout)


class Case2RollbackIsByteExact(unittest.TestCase):
    """A rejected write must leave state.json on disk byte-identical to its pre-write content --
    across all four engines' extracted scripts."""

    def test_rejected_write_restores_exact_pre_write_bytes(self):
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                pre_bytes = state_json_bytes([{"id": "BT.1.a", "status": "open"}])
                with tempfile.TemporaryDirectory() as td:
                    run_dir = Path(td)
                    (run_dir / "planning").mkdir()
                    (run_dir / "planning" / "state.json").write_bytes(pre_bytes)
                    bin_dir = run_dir / "bin"
                    bin_dir.mkdir()
                    # before-call sees no diagnostics; after-call (post-write) reports one -- a
                    # net-new error, which must trigger rollback.
                    write_fake_mev_callseq(bin_dir, before_error="", after_error="[E_FAKE] boom")

                    result = run_mutation_script(
                        engine, run_dir, "BT.1.a", mev_bin_dir=bin_dir
                    )
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("REJECTED:BT.1.a", result.stdout)

                    on_disk = (run_dir / "planning" / "state.json").read_bytes()
                    self.assertEqual(
                        on_disk, pre_bytes,
                        f"{engine}: state.json was not restored byte-exact after rejection",
                    )


class Case3RejectionSurfaces(unittest.TestCase):
    """A rejected write must be reported (REJECTED:<id>, non-zero exit, NET_NEW: lines) -- never
    silently swallowed as if the block closed."""

    def test_rejection_reports_net_new_lines_and_nonzero_exit(self):
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                pre_bytes = state_json_bytes([{"id": "BT.1.a", "status": "open"}])
                with tempfile.TemporaryDirectory() as td:
                    run_dir = Path(td)
                    (run_dir / "planning").mkdir()
                    (run_dir / "planning" / "state.json").write_bytes(pre_bytes)
                    bin_dir = run_dir / "bin"
                    bin_dir.mkdir()
                    write_fake_mev_callseq(bin_dir, before_error="", after_error="[E_FAKE] boom")

                    result = run_mutation_script(
                        engine, run_dir, "BT.1.a", mev_bin_dir=bin_dir
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("REJECTED:BT.1.a", result.stdout)
                    self.assertIn("NET_NEW: [E_FAKE] boom", result.stdout)
                    # It must not ALSO print a FLIPPED line -- that would be the silent-swallow bug.
                    self.assertNotIn("FLIPPED:", result.stdout)


class Case4DeltaAttribution(unittest.TestCase):
    """A corpus already red before the write must not block a write that adds no NEW errors --
    the D64-style delta-attribution rule this ticket ports."""

    def test_pre_existing_error_does_not_block_a_clean_write(self):
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                pre_bytes = state_json_bytes([{"id": "BT.1.a", "status": "open"}])
                with tempfile.TemporaryDirectory() as td:
                    run_dir = Path(td)
                    (run_dir / "planning").mkdir()
                    (run_dir / "planning" / "state.json").write_bytes(pre_bytes)
                    bin_dir = run_dir / "bin"
                    bin_dir.mkdir()
                    # SAME error before and after the write -- a sibling lane's pre-existing
                    # breakage, unrelated to this write. Must not be treated as net-new.
                    write_fake_mev_callseq(
                        bin_dir,
                        before_error="[E_SIBLING] unrelated pre-existing error",
                        after_error="[E_SIBLING] unrelated pre-existing error",
                    )

                    result = run_mutation_script(
                        engine, run_dir, "BT.1.a", mev_bin_dir=bin_dir
                    )
                    self.assertEqual(
                        result.returncode, 0,
                        f"{engine}: a pre-existing, unchanged error incorrectly blocked the write: "
                        f"{result.stdout}{result.stderr}",
                    )
                    self.assertIn("FLIPPED:BT.1.a", result.stdout)
                    self.assertNotIn("REJECTED:", result.stdout)

                    on_disk = json.loads((run_dir / "planning" / "state.json").read_bytes())
                    new_status = "closed"
                    self.assertEqual(
                        on_disk["tracks"][0]["blocks"][0]["status"], new_status,
                        f"{engine}: write should have landed since it introduced no net-new errors",
                    )


class Case5WorktreeModeIsNotConditional(unittest.TestCase):
    """Task 1 decided (not deferred) that this validation step runs IDENTICALLY in place and in a
    worktree -- only `mev emit-state --write` (never called by this script) is deferred to merge.
    That decision is falsifiable here: the extracted script text must not branch on worktree state,
    and running it inside a directory standing in for a linked worktree must behave exactly like
    running it in place."""

    def test_extracted_script_has_no_worktree_conditional(self):
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                script = extract_mutation_script(engine)
                lowered = script.lower()
                self.assertNotIn(
                    "worktree", lowered,
                    f"{engine}: the mutation script itself must not branch on worktree state -- "
                    f"that decision belongs to the surrounding prompt text (step 5's emit-state "
                    f"deferral), not this script",
                )

    def test_script_behaves_identically_in_a_simulated_worktree_directory(self):
        # A linked worktree is just another directory on disk from this script's point of view --
        # it reads/writes planning/state.json relative to cwd and never inspects .git. Naming the
        # run_dir like a worktree path and running from there is a faithful stand-in.
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                pre_bytes = state_json_bytes([{"id": "BT.1.a", "status": "open"}])
                with tempfile.TemporaryDirectory() as td:
                    run_dir = Path(td) / "trees" / "some-spec-task"
                    run_dir.mkdir(parents=True)
                    (run_dir / "planning").mkdir()
                    (run_dir / "planning" / "state.json").write_bytes(pre_bytes)
                    bin_dir = Path(td) / "bin"
                    bin_dir.mkdir()
                    write_fake_mev_callseq(bin_dir, before_error="", after_error="")

                    result = run_mutation_script(
                        engine, run_dir, "BT.1.a", mev_bin_dir=bin_dir
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("FLIPPED:BT.1.a", result.stdout)
                    self.assertNotIn("UNVALIDATED:", result.stdout)


class Case6MevAbsentDegrades(unittest.TestCase):
    """Absent mev must degrade to a stated warning and exit 0 (the write still lands, unchecked),
    never a hard failure -- matching how the harness treats other absent tooling."""

    def test_absent_mev_writes_unvalidated_and_exits_zero(self):
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                pre_bytes = state_json_bytes([{"id": "BT.1.a", "status": "open"}])
                with tempfile.TemporaryDirectory() as td:
                    run_dir = Path(td)
                    (run_dir / "planning").mkdir()
                    (run_dir / "planning" / "state.json").write_bytes(pre_bytes)

                    result = run_mutation_script(
                        engine, run_dir, "BT.1.a", mev_bin_dir=None  # PATH scrubbed of real mev
                    )
                    self.assertEqual(
                        result.returncode, 0,
                        f"{engine}: absent mev must not fail the run: {result.stdout}{result.stderr}",
                    )
                    self.assertIn("FLIPPED:BT.1.a", result.stdout)
                    self.assertIn("UNVALIDATED: mev not on PATH", result.stdout)

                    on_disk = json.loads((run_dir / "planning" / "state.json").read_bytes())
                    self.assertEqual(
                        on_disk["tracks"][0]["blocks"][0]["status"], "closed",
                        f"{engine}: the write should still land (unchecked) when mev is absent",
                    )


class NotFoundIsAlsoByteUnchanged(unittest.TestCase):
    """Not one of the six required cases, but a cheap regression guard on a path the scripts share:
    a block id that doesn't exist must leave the file untouched and report NOT_FOUND, never
    fabricate a block entry."""

    def test_unknown_block_id_is_a_byte_unchanged_noop(self):
        for engine in ENGINE_FILES:
            with self.subTest(engine=engine):
                pre_bytes = state_json_bytes([{"id": "BT.1.a", "status": "open"}])
                with tempfile.TemporaryDirectory() as td:
                    run_dir = Path(td)
                    (run_dir / "planning").mkdir()
                    (run_dir / "planning" / "state.json").write_bytes(pre_bytes)

                    result = run_mutation_script(
                        engine, run_dir, "BT.99.z", mev_bin_dir=None
                    )
                    self.assertEqual(result.returncode, 0)
                    self.assertIn("NOT_FOUND", result.stdout)
                    self.assertEqual(
                        (run_dir / "planning" / "state.json").read_bytes(), pre_bytes
                    )


if __name__ == "__main__":
    unittest.main()
