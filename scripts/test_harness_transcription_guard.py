#!/usr/bin/env python3
"""Regression suite for the prepare-run harness-config transcription gap (2026-09-18).

runPrepareRun() hands prepare_run.py's stdout to a model turn that is asked to copy it VERBATIM.
With planning/harness.json embedded whole, that stdout was ~193 KB and the copy never was
verbatim: four consecutive sdlc-task launches received 1-of-113 or 0-of-113 gating checks, and
the 1-check runs went on to gate silently on that one check. Two fixes, both pinned here:

  1. prepare_run.py strips prose-only keys (compact_harness_config) and prints compact JSON, so
     the payload a model must carry shrinks ~10x -- while every key an engine reads survives.
  2. prepare_run.py reports harness_check_count, and BOTH engines' loadHarnessConfig() fail closed
     (HARNESS_CONFIG_TRANSCRIPTION_INCOMPLETE) when the copy they received holds a different
     number of checks. Extracted verbatim from each engine and run through node -- never re-typed.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / '.claude' / 'workflows' / 'bin'
sys.path.insert(0, str(BIN_DIR))
import prepare_run  # noqa: E402

ENGINES = [REPO_ROOT / '.claude' / 'workflows' / 'sdlc-task.js',
           REPO_ROOT / '.claude' / 'workflows' / 'sdlc-flow.js']


def extract_function(src: str, signature: str) -> str:
    """Return the full text of the function starting at `signature`, by balanced-brace scanning."""
    start = src.index(signature)
    depth = 0
    for i in range(src.index('{', start), len(src)):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError(f'unbalanced function body for {signature!r}')


def extract_const_object(src: str, name: str) -> str:
    start = src.index(f'const {name} = {{')
    return src[start:src.index('\n}\n', start) + 3]


def run_load_harness_config(engine: Path, prepare_run_obj) -> dict:
    src = engine.read_text()
    script = '\n'.join([
        'const logs = []; function log(m) { logs.push(m) }',
        extract_const_object(src, 'HARNESS_CONFIG_BAIL'),
        f'async function runPrepareRun() {{ return {{ prepareRun: {json.dumps(prepare_run_obj)} }} }}',
        extract_function(src, 'async function loadHarnessConfig('),
        '(async () => { const r = await loadHarnessConfig("."); process.stdout.write(JSON.stringify({ r, logs })) })()',
    ])
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as f:
        f.write(script)
        path = f.name
    try:
        out = subprocess.run(['node', path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    if out.returncode != 0:
        raise AssertionError(f'node failed for {engine.name}: {out.stderr}')
    return json.loads(out.stdout)


def cfg_with(n: int) -> dict:
    return {'validation': {'checks': [{'name': f'c{i}', 'command': 'true', 'gates': True} for i in range(n)]}}


class CompactHarnessConfig(unittest.TestCase):
    def test_strips_prose_keeps_engine_fields(self):
        cfg = {
            '$schema': 'x', '_comment': 'drop me', 'stack': 'node-docs',
            'validation': {'checks': [{
                'name': 'a', 'command': 'run', 'fastCommand': 'fast', 'gates': True, 'perTask': False,
                'kind': 'baseline-diff', 'baselineCommand': 'b', 'purpose': 'long prose',
                'observed_red': {'date': 'd', 'evidence': 'e'}, 'evidence': 'x', 'gates_reason': 'y',
                'rationale': 'z', '_note': 'n',
            }]},
            'flow': {'bailReasons': ['r'], 'testDepth': 'fast'},
        }
        out = prepare_run.compact_harness_config(cfg)
        check = out['validation']['checks'][0]
        for kept in ('name', 'command', 'fastCommand', 'gates', 'perTask', 'kind', 'baselineCommand'):
            self.assertIn(kept, check)
        for dropped in ('purpose', 'observed_red', 'evidence', 'gates_reason', 'rationale', '_note'):
            self.assertNotIn(dropped, check)
        self.assertNotIn('_comment', out)
        self.assertEqual(out['flow'], {'bailReasons': ['r'], 'testDepth': 'fast'})
        self.assertIsNone(prepare_run.compact_harness_config(None))

    def test_real_harness_payload_is_small_and_counted(self):
        out = subprocess.run([sys.executable, str(BIN_DIR / 'prepare_run.py'), '--repo-root', str(REPO_ROOT)],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        on_disk = json.loads((REPO_ROOT / 'planning' / 'harness.json').read_text())
        self.assertEqual(data['harness_check_count'], len(on_disk['validation']['checks']))
        self.assertEqual(len(data['harness_config']['validation']['checks']), data['harness_check_count'])
        # Derived bound, not a frozen literal: the compacted stdout must be well under a third of the
        # raw harness.json it embeds (measured ~7% on 2026-09-18).
        raw = len((REPO_ROOT / 'planning' / 'harness.json').read_text())
        self.assertLess(len(out.stdout), raw / 3, 'prepare_run.py stdout is not compacted')


class LoadHarnessConfigGuard(unittest.TestCase):
    def test_mismatch_bails_in_both_engines(self):
        for engine in ENGINES:
            res = run_load_harness_config(engine, {'harness_config': cfg_with(1), 'harness_check_count': 113})
            self.assertEqual(res['r'], {'__bail': 'HARNESS_CONFIG_TRANSCRIPTION_INCOMPLETE'}, engine.name)

    def test_empty_copy_bails_in_both_engines(self):
        for engine in ENGINES:
            res = run_load_harness_config(engine, {'harness_config': cfg_with(0), 'harness_check_count': 5})
            self.assertEqual(res['r'], {'__bail': 'HARNESS_CONFIG_TRANSCRIPTION_INCOMPLETE'}, engine.name)

    def test_match_returns_config(self):
        for engine in ENGINES:
            res = run_load_harness_config(engine, {'harness_config': cfg_with(3), 'harness_check_count': 3})
            self.assertEqual(len(res['r']['validation']['checks']), 3, engine.name)

    def test_absent_count_is_backward_compatible(self):
        for engine in ENGINES:
            res = run_load_harness_config(engine, {'harness_config': cfg_with(2)})
            self.assertEqual(len(res['r']['validation']['checks']), 2, engine.name)


if __name__ == '__main__':
    unittest.main()
