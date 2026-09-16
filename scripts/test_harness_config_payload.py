#!/usr/bin/env python3
"""Fixture suite for the harness-config unwrap + hard-bail added by
BT.ticket.harness-config-must-bail-not-warn-on-a-malformed-payload.

Drives the harness-config parsing path for BOTH engines (`.claude/workflows/sdlc-task.js` and
`.claude/workflows/sdlc-flow.js`) against three cases:

  (a) a present, valid config with gates:true checks -> resolves to that many gating checks
  (b) an ABSENT/refused harness.json -- `pr.harness_config` is null, or prepare-run itself
      refused -- must NOT bail; it degrades to null, the spec's `## Validation Commands` fallback
      (D5 / standing rule 1: the engine ships no stack defaults)
  (c) a PRESENT harness.json whose checks are all gates:false -- must hard-BAIL with the named
      `HARNESS_CONFIG_ZERO_GATING_CHECKS` diagnostic, not merely log a warning.

RECONCILED 2026-09-16 (fixing a drifted regex, `BT.chore.fix-pre-existing-test-defects`): as of
`BT.ticket.prepare-run-replaces-setup-agents` (task 6), `loadHarnessConfig()` no longer unwraps an
agent-returned `result` object at all -- `planning/harness.json` is now read and parsed directly by
Python's `prepare_run.py::load_harness_config()` (see that function's own docstring) and handed to
the engine pre-parsed via the `runPrepareRun()` cache. There is no longer a model in the loop that
could hand back a malformed double-wrapped payload, so the double-wrap unwrap this suite used to
drive (`test_*_flat_and_double_wrapped_agree`) tests a code path that no longer exists in either
engine -- `loadHarnessConfig()`'s body is now a straight `pr.harness_config` read (see the function
itself, extracted verbatim below by `LOAD_HARNESS_CONFIG_FN_RE`). That was a deliberate
simplification (the engine's own comment above `loadHarnessConfig()` says so explicitly), not a
regression, so the fix here is to extract and drive the CURRENT shape rather than resurrect
unwrap-testing dead code.

Mechanism, mirroring `scripts/test_work_assertion.py`'s pattern: extract the engine's OWN
`loadHarnessConfig()` function and its OWN `gatingChecks()` function straight out of the `.js`
source via regex (never re-typed), then execute them for real via `node -e` -- never reimplemented
in Python. `loadHarnessConfig()` depends on the module-level `runPrepareRun()` cache
(`_prepareRunCache` / `_prepareRunCacheSlug`); the probe seeds that cache directly per fixture
(mirroring the engine's own resume-time cache-seed path, see `_prepareRunCache = priorSetup` in
both engines) so no real `agent()` call is needed to drive `loadHarnessConfig()` for real.

A negative control (`test_bail_removed_regresses`) pins that the suite actually depends on the
current source: it asserts the named diagnostics and the "BAILED (" call sites are present, and
that the OLD warning-only text ("defines ZERO gates:true checks") is gone from both engines -- so
reverting either engine's bail back to a warning fails this suite, not just a live run.

Registered in planning/harness.json as `harness-config-payload-tests` --
run directly: python3 scripts/test_harness_config_payload.py
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SOURCE_FILES = {
    "sdlc-task.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js",
    "sdlc-flow.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js",
}

BAIL_BLOCK_RE = re.compile(
    r"const HARNESS_CONFIG_BAIL = \{\n(?:.*\n)*?\}\n",
    re.MULTILINE,
)

# loadHarnessConfig()'s CURRENT shape (BT.ticket.prepare-run-replaces-setup-agents task 6): a plain
# read of the runPrepareRun() cache's `harness_config` field, already parsed by Python -- no more
# agent-result unwrap. Extracted verbatim (whole function) so the probe drives the real body.
LOAD_HARNESS_CONFIG_FN_RE = re.compile(
    r"async function loadHarnessConfig\(cwd\) \{\n(?:.*\n)*?\}\n",
    re.MULTILINE,
)

GATING_CHECKS_FN_RE = re.compile(
    r"function gatingChecks\(cfg\) \{\n.*\n\}\n",
)


def _extract(pattern: re.Pattern, text: str, label: str, path: Path) -> str:
    m = pattern.search(text)
    if not m:
        raise AssertionError(f"{label} not found in {path}")
    return m.group(0)


def _read(name: str) -> str:
    return SOURCE_FILES[name].read_text(encoding="utf-8")


def build_harness_probe(engine_name: str) -> str:
    """Assemble a self-contained node program combining the engine's own extracted
    HARNESS_CONFIG_BAIL constant, its own (verbatim) loadHarnessConfig() function, and its own
    gatingChecks() function -- with a stub runPrepareRun() whose cache the probe seeds directly
    per fixture (never a real agent() call) -- then, for each of the fixtures on argv, print one
    JSON line: the outcome of feeding that fixture through loadHarnessConfig() and then the SAME
    zero-gating-checks bail test the real engine runs at its call site.
    """
    text = _read(engine_name)
    path = SOURCE_FILES[engine_name]

    bail_block = _extract(BAIL_BLOCK_RE, text, "HARNESS_CONFIG_BAIL block", path)
    load_fn = _extract(LOAD_HARNESS_CONFIG_FN_RE, text, "loadHarnessConfig() function", path)
    gating_fn = _extract(GATING_CHECKS_FN_RE, text, "gatingChecks() function", path)

    return f"""
{bail_block}
{gating_fn}
// Stub standing in for the engine's own runPrepareRun(): the probe seeds the cache directly per
// fixture (mirroring both engines' own resume-time `_prepareRunCache = priorSetup` seed path)
// rather than invoking a real agent() call, exactly as the old unwrap-block extraction avoided one.
let _prepareRunCache = null
let _prepareRunCacheSlug = undefined
async function runPrepareRun(specSlug) {{
  if (_prepareRunCache && _prepareRunCacheSlug === (specSlug || null)) return _prepareRunCache
  throw new Error('runPrepareRun stub: cache not seeded for this probe fixture')
}}

{load_fn}
async function main() {{
  const fixtures = JSON.parse(process.argv[1])
  const outcomes = []
  for (const pr of fixtures) {{
    _prepareRunCache = {{ prepareRun: pr }}
    _prepareRunCacheSlug = null
    const harnessCfg = await loadHarnessConfig('.')
    if (harnessCfg && harnessCfg.__bail) {{
      outcomes.push({{ bail: harnessCfg.__bail, checks: null }})
      continue
    }}
    if (harnessCfg && gatingChecks(harnessCfg).length === 0) {{
      outcomes.push({{ bail: HARNESS_CONFIG_BAIL.zeroGatingChecks, checks: 0 }})
      continue
    }}
    outcomes.push({{ bail: null, checks: harnessCfg ? gatingChecks(harnessCfg).length : null }})
  }}
  console.log(JSON.stringify(outcomes))
}}
main()
"""


# Fixtures are now the runPrepareRun() cache's `prepareRun` object shape directly --
# { refused: bool, harness_config: <parsed planning/harness.json, or null> } -- matching
# loadHarnessConfig()'s current read (`const pr = cache.prepareRun; ...; pr.harness_config`).

PRESENT_PAYLOAD = {
    "refused": False,
    "harness_config": {
        "validation": {
            "checks": [
                {"name": "build", "gates": True, "perTask": True},
                {"name": "test", "gates": True, "perTask": True},
                {"name": "lint", "gates": False, "perTask": True},
            ]
        }
    },
}

ABSENT_PAYLOAD = {"refused": False, "harness_config": None}

REFUSED_PAYLOAD = {"refused": True, "harness_config": None}

ZERO_GATES_PAYLOAD = {
    "refused": False,
    "harness_config": {
        "validation": {
            "checks": [
                {"name": "lint", "gates": False, "perTask": False},
                {"name": "smoke", "gates": False, "perTask": True},
            ]
        }
    },
}

FIXTURES = [PRESENT_PAYLOAD, ABSENT_PAYLOAD, REFUSED_PAYLOAD, ZERO_GATES_PAYLOAD]


class HarnessConfigPayloadTests(unittest.TestCase):
    def _run_fixtures(self, engine_name: str):
        script = build_harness_probe(engine_name)
        proc = subprocess.run(
            ["node", "-e", script, "--", json.dumps(FIXTURES)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            raise AssertionError(f"{engine_name} probe failed (rc={proc.returncode}):\n{proc.stderr}")
        return json.loads(proc.stdout.strip())

    def test_task_engine_present_config_resolves_gating_checks(self):
        outcomes = self._run_fixtures("sdlc-task.js")
        present = outcomes[0]
        self.assertIsNone(present["bail"], f"present payload should not bail: {present}")
        self.assertEqual(present["checks"], 2, "present payload: expected 2 gates:true checks (build, test)")

    def test_flow_engine_present_config_resolves_gating_checks(self):
        outcomes = self._run_fixtures("sdlc-flow.js")
        present = outcomes[0]
        self.assertIsNone(present["bail"], f"present payload should not bail: {present}")
        self.assertEqual(present["checks"], 2, "present payload: expected 2 gates:true checks (build, test)")

    def test_task_engine_absent_does_not_bail(self):
        outcomes = self._run_fixtures("sdlc-task.js")
        absent = outcomes[1]
        self.assertIsNone(absent["bail"], f"absent harness.json must NOT bail (D5 / standing rule 1): {absent}")
        self.assertIsNone(absent["checks"], "absent harness.json must resolve to null (spec fallback)")

    def test_flow_engine_absent_does_not_bail(self):
        outcomes = self._run_fixtures("sdlc-flow.js")
        absent = outcomes[1]
        self.assertIsNone(absent["bail"], f"absent harness.json must NOT bail (D5 / standing rule 1): {absent}")
        self.assertIsNone(absent["checks"], "absent harness.json must resolve to null (spec fallback)")

    def test_task_engine_refused_prepare_run_does_not_bail(self):
        outcomes = self._run_fixtures("sdlc-task.js")
        refused = outcomes[2]
        self.assertIsNone(refused["bail"], f"a refused prepare-run must degrade to null, not bail: {refused}")
        self.assertIsNone(refused["checks"], "refused prepare-run must resolve to null (spec fallback)")

    def test_flow_engine_refused_prepare_run_does_not_bail(self):
        outcomes = self._run_fixtures("sdlc-flow.js")
        refused = outcomes[2]
        self.assertIsNone(refused["bail"], f"a refused prepare-run must degrade to null, not bail: {refused}")
        self.assertIsNone(refused["checks"], "refused prepare-run must resolve to null (spec fallback)")

    def test_task_engine_zero_gates_bails_with_named_diagnostic(self):
        outcomes = self._run_fixtures("sdlc-task.js")
        zero = outcomes[3]
        self.assertEqual(zero["bail"], "HARNESS_CONFIG_ZERO_GATING_CHECKS", f"expected named bail, got {zero}")

    def test_flow_engine_zero_gates_bails_with_named_diagnostic(self):
        outcomes = self._run_fixtures("sdlc-flow.js")
        zero = outcomes[3]
        self.assertEqual(zero["bail"], "HARNESS_CONFIG_ZERO_GATING_CHECKS", f"expected named bail, got {zero}")

    def test_both_engines_share_the_same_diagnostic_strings(self):
        task_outcomes = self._run_fixtures("sdlc-task.js")
        flow_outcomes = self._run_fixtures("sdlc-flow.js")
        self.assertEqual(
            [o["bail"] for o in task_outcomes],
            [o["bail"] for o in flow_outcomes],
            "AC4: both engines must carry the same read and the same bail outcomes across all fixtures",
        )

    def test_bail_removed_regresses(self):
        """Negative control: this suite must fail if either engine's hard bail is reverted back to
        a D63-style warning. Pins (1) the named diagnostic constants exist, (2) each engine's
        top-level zero-gating bail actually raises via a 'BAILED (' log carrying the diagnostic,
        and (3) the OLD warning-only text is gone -- so a revert to the old behaviour is caught
        even if someone renames the diagnostic constant back to a warning without deleting it."""
        for name, path in SOURCE_FILES.items():
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "HARNESS_CONFIG_ZERO_GATING_CHECKS", text,
                f"{name}: named zero-gating-checks diagnostic missing -- bail may have been reverted to a warning",
            )
            self.assertIn(
                "HARNESS_CONFIG_UNPARSEABLE", text,
                f"{name}: named unparseable diagnostic missing -- kept as a defensive constant even though "
                "loadHarnessConfig() no longer sets __bail itself (BT.ticket.prepare-run-replaces-setup-agents "
                "task 6 moved parsing to Python, which degrades to null rather than raising)",
            )
            self.assertRegex(
                text,
                r"BAILED \(\$\{HARNESS_CONFIG_BAIL\.zeroGatingChecks\}\)",
                f"{name}: zero-gating-checks case no longer hard-bails via a BAILED( ) log",
            )
            self.assertNotIn(
                "defines ZERO gates:true checks",
                text,
                f"{name}: the old D63 warning-only text for zero gating checks is still present -- "
                "the bail may have been left alongside (or replaced by) the warning it was meant to retire",
            )

    def test_engines_declare_gatingChecks_identically(self):
        task_fn = _extract(GATING_CHECKS_FN_RE, _read("sdlc-task.js"), "gatingChecks()", SOURCE_FILES["sdlc-task.js"])
        flow_fn = _extract(GATING_CHECKS_FN_RE, _read("sdlc-flow.js"), "gatingChecks()", SOURCE_FILES["sdlc-flow.js"])
        self.assertEqual(task_fn, flow_fn, "gatingChecks() must be byte-identical across both engines")

    def test_engines_declare_loadHarnessConfig_identically(self):
        task_fn = _extract(
            LOAD_HARNESS_CONFIG_FN_RE, _read("sdlc-task.js"), "loadHarnessConfig()", SOURCE_FILES["sdlc-task.js"]
        )
        flow_fn = _extract(
            LOAD_HARNESS_CONFIG_FN_RE, _read("sdlc-flow.js"), "loadHarnessConfig()", SOURCE_FILES["sdlc-flow.js"]
        )
        self.assertEqual(task_fn, flow_fn, "loadHarnessConfig() must be byte-identical across both engines")


if __name__ == "__main__":
    unittest.main()
