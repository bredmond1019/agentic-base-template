#!/usr/bin/env python3
"""Fixture suite for the harness-config unwrap + hard-bail added by
BT.ticket.harness-config-must-bail-not-warn-on-a-malformed-payload.

Drives the harness-config parsing path for BOTH engines (`.claude/workflows/sdlc-task.js` and
`.claude/workflows/sdlc-flow.js`) against four cases:

  (a) the flat payload   {present:true, config:{validation:{checks:[...]}}}
  (b) the double-wrapped payload {config:{present:true, config:{validation:{checks:[...]}}}}
  (c) an ABSENT harness.json     {present:false}
  (d) a PRESENT harness.json whose checks are all gates:false

(a) and (b) must resolve to the SAME found-check count (the unwrap is transparent). (c) must NOT
bail — it degrades to null, the spec's `## Validation Commands` fallback (D5 / standing rule 1:
the engine ships no stack defaults). (d) must hard-BAIL with the named
`HARNESS_CONFIG_ZERO_GATING_CHECKS` diagnostic, not merely log a warning.

Mechanism, mirroring `scripts/test_work_assertion.py`'s pattern: extract the engine's OWN
post-agent unwrap logic (from `loadHarnessConfig()`) and its OWN `gatingChecks()` function
straight out of the `.js` source via regex (never re-typed), then execute them for real via
`node -e` — never re-implemented in Python. This is the only way to drive case (b) — an actual
`agent()` LLM call cannot run in a fixture suite, but the unwrap logic that runs on ITS result can.

A negative control (`test_bail_removed_regresses`) pins that the suite actually depends on the
current source: it asserts the named diagnostics and the "BAILED (" call sites are present, and
that the OLD warning-only text ("defines ZERO gates:true checks") is gone from both engines — so
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

# The post-agent-call body of loadHarnessConfig(): from the absent/invalid-JSON early-return
# through the defensive unwrap and the final unparseable-bail, to the function's closing brace.
# Deliberately starts AFTER the `const result = await agent(...)` call so it can be exercised with
# a plain `result` object, standing in for what the (unmockable) LLM call returned.
UNWRAP_BLOCK_RE = re.compile(
    r"if \(!result \|\| !result\.present\) return null\n(?:.*\n)*?  return cfg\n\}\n",
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
    HARNESS_CONFIG_BAIL constant, its own loadHarnessConfig() post-agent unwrap logic (wrapped as
    a plain function taking `result`), and its own gatingChecks() function -- then, for each of
    the four JSON-encoded fixtures on argv, print one JSON line: the outcome of feeding that
    fixture through unwrap() and then the SAME zero-gating-checks bail test the real engine runs.
    """
    text = _read(engine_name)
    path = SOURCE_FILES[engine_name]

    bail_block = _extract(BAIL_BLOCK_RE, text, "HARNESS_CONFIG_BAIL block", path)
    unwrap_block = _extract(UNWRAP_BLOCK_RE, text, "loadHarnessConfig unwrap block", path)
    gating_fn = _extract(GATING_CHECKS_FN_RE, text, "gatingChecks() function", path)

    return f"""
{bail_block}
{gating_fn}
function unwrapResult(result) {{
{unwrap_block}
const fixtures = JSON.parse(process.argv[1])
const outcomes = fixtures.map(result => {{
  const harnessCfg = unwrapResult(result)
  if (harnessCfg && harnessCfg.__bail) return {{ bail: harnessCfg.__bail, checks: null }}
  if (harnessCfg && gatingChecks(harnessCfg).length === 0) return {{ bail: HARNESS_CONFIG_BAIL.zeroGatingChecks, checks: 0 }}
  return {{ bail: null, checks: harnessCfg ? gatingChecks(harnessCfg).length : null }}
}})
console.log(JSON.stringify(outcomes))
"""


FLAT_PAYLOAD = {
    "present": True,
    "config": {
        "validation": {
            "checks": [
                {"name": "build", "gates": True, "perTask": True},
                {"name": "test", "gates": True, "perTask": True},
                {"name": "lint", "gates": False, "perTask": True},
            ]
        }
    },
}

DOUBLE_WRAPPED_PAYLOAD = {
    "present": True,
    "config": {
        "present": True,
        "config": {
            "validation": {
                "checks": [
                    {"name": "build", "gates": True, "perTask": True},
                    {"name": "test", "gates": True, "perTask": True},
                    {"name": "lint", "gates": False, "perTask": True},
                ]
            }
        },
    },
}

ABSENT_PAYLOAD = {"present": False}

ZERO_GATES_PAYLOAD = {
    "present": True,
    "config": {
        "validation": {
            "checks": [
                {"name": "lint", "gates": False, "perTask": False},
                {"name": "smoke", "gates": False, "perTask": True},
            ]
        }
    },
}

FIXTURES = [FLAT_PAYLOAD, DOUBLE_WRAPPED_PAYLOAD, ABSENT_PAYLOAD, ZERO_GATES_PAYLOAD]


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

    def test_task_engine_flat_and_double_wrapped_agree(self):
        outcomes = self._run_fixtures("sdlc-task.js")
        flat, doubled = outcomes[0], outcomes[1]
        self.assertIsNone(flat["bail"], f"flat payload should not bail: {flat}")
        self.assertEqual(flat["checks"], 2, "flat payload: expected 2 gates:true checks (build, test)")
        self.assertIsNone(doubled["bail"], f"double-wrapped payload should not bail: {doubled}")
        self.assertEqual(
            doubled["checks"], flat["checks"],
            "double-wrapped payload must unwrap to the SAME found-check count as the flat payload",
        )

    def test_flow_engine_flat_and_double_wrapped_agree(self):
        outcomes = self._run_fixtures("sdlc-flow.js")
        flat, doubled = outcomes[0], outcomes[1]
        self.assertIsNone(flat["bail"], f"flat payload should not bail: {flat}")
        self.assertEqual(flat["checks"], 2, "flat payload: expected 2 gates:true checks (build, test)")
        self.assertIsNone(doubled["bail"], f"double-wrapped payload should not bail: {doubled}")
        self.assertEqual(
            doubled["checks"], flat["checks"],
            "double-wrapped payload must unwrap to the SAME found-check count as the flat payload",
        )

    def test_task_engine_absent_does_not_bail(self):
        outcomes = self._run_fixtures("sdlc-task.js")
        absent = outcomes[2]
        self.assertIsNone(absent["bail"], f"absent harness.json must NOT bail (D5 / standing rule 1): {absent}")
        self.assertIsNone(absent["checks"], "absent harness.json must resolve to null (spec fallback)")

    def test_flow_engine_absent_does_not_bail(self):
        outcomes = self._run_fixtures("sdlc-flow.js")
        absent = outcomes[2]
        self.assertIsNone(absent["bail"], f"absent harness.json must NOT bail (D5 / standing rule 1): {absent}")
        self.assertIsNone(absent["checks"], "absent harness.json must resolve to null (spec fallback)")

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
            "AC4: both engines must carry the same unwrap and the same bail outcomes across all fixtures",
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
                f"{name}: named unparseable diagnostic missing -- unwrap bail may have been removed",
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


if __name__ == "__main__":
    unittest.main()
