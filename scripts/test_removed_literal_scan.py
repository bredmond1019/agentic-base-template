#!/usr/bin/env python3
"""Fixture suite for the engines' removed-literal scan (renderRemovedLiteralScanScript, shared.js).

The scan lists string literals / identifiers a task's commit REMOVED and reports any that still
appear in a test file outside the task's declared files[] -- a test still asserting on something the
task deleted. Base-template 93cfe68 (2026-09-18) stopped counting a literal as removed when it
reappears on the same diff's '+' side: editing one line in place (inserting a flag into an existing
command string) shows the whole line as '-' and '+', and every unchanged token on it used to be
reported, bailing a correct task twice (BT.ticket.work-assertion-base-sha-self-comparison task 1).

Pinned here, against the REAL rendered script (extracted from shared.js's region markers, rendered
through node, executed in a throwaway git repo):
  1. IN-PLACE EDIT  -- a line edited in place does not report its surviving tokens (the 93cfe68 fix).
     Runtime inversion: the same fixture run through the script with the subtraction removed DOES
     report them, so this case discriminates.
  2. GENUINE REMOVAL (regression control) -- a line deleted outright still reports its literal when a
     foreign test file references it.

Known gap, deliberately NOT pinned (carryover removed-literal-scan-same-commit-subtraction-is-
untested): a literal removed from one line but newly referenced on a '+' line elsewhere in the same
commit is subtracted too. Pinning today's behaviour there would bless a false negative.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SHARED = REPO_ROOT / '.claude' / 'workflows' / 'prompts' / 'shared.js'
START = '// <<shared:renderRemovedLiteralScanScript>>'
END = '// <</shared:renderRemovedLiteralScanScript>>'
SUBTRACTION = 'literals = removed_literals - added_literals'


def render_script(range_: str, tasks_path: str, task_num: int) -> str:
    src = SHARED.read_text()
    region = src[src.index(START) + len(START):src.index(END)]
    js = (
        "const GIT = 'git';\n" + region
        + f"\nprocess.stdout.write(renderRemovedLiteralScanScript({{ range: {json.dumps(range_)}, "
        f"tasksJsonPath: {json.dumps(tasks_path)}, taskNum: {task_num}, "
        "testGlobRegex: '(^|/)tests?/|_test\\\\.py$|^test_', minLiteralLen: 4, identifierMinLen: 12 }));\n"
    )
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as f:
        f.write(js)
        path = f.name
    try:
        out = subprocess.run(['node', path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    if out.returncode != 0:
        raise AssertionError(out.stderr)
    shell = out.stdout
    # The rendered text is a bash snippet writing a python heredoc; keep only the python body.
    body = shell[shell.index("<<'PYEOF'\n") + len("<<'PYEOF'\n"):shell.index('\nPYEOF\n')]
    return body


def git(cwd, *args):
    subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True)


def make_repo(before: str, after: str) -> tuple[str, str]:
    d = tempfile.mkdtemp(prefix='rls-')
    git(d, 'init', '-q')
    git(d, 'config', 'user.email', 't@t')
    git(d, 'config', 'user.name', 't')
    Path(d, 'src.py').write_text(before)
    Path(d, 'tests').mkdir()
    Path(d, 'tests', 'test_src.py').write_text('assert "ALPHA_CONST"\nassert "BETA_CONST"\n')
    Path(d, 'tasks.json').write_text(json.dumps([{'task_id': 1, 'files': ['src.py']}]))
    git(d, 'add', '.')
    git(d, 'commit', '-q', '-m', 'base')
    base = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=d, capture_output=True, text=True).stdout.strip()
    Path(d, 'src.py').write_text(after)
    git(d, 'commit', '-q', '-am', 'task')
    return d, base


def run_scan(body: str, cwd: str) -> str:
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:
        f.write(body)
        path = f.name
    try:
        return subprocess.run(['python3', path], cwd=cwd, capture_output=True, text=True, timeout=30).stdout
    finally:
        os.unlink(path)


class RemovedLiteralScan(unittest.TestCase):
    def test_in_place_edit_does_not_report_surviving_tokens(self):
        d, base = make_repo('run("ALPHA_CONST", "--x")\n', 'run("ALPHA_CONST", "--x", "--y")\n')
        body = render_script(base, 'tasks.json', 1)
        out = run_scan(body, d)
        self.assertNotIn('HIT:ALPHA_CONST', out, out)
        # Runtime inversion: without the same-commit subtraction the identical fixture reports it.
        self.assertIn(SUBTRACTION, body)
        inverted = run_scan(body.replace(SUBTRACTION, 'literals = removed_literals'), d)
        self.assertIn('HIT:ALPHA_CONST', inverted, 'fixture does not discriminate: ' + inverted)

    def test_genuine_removal_still_reports(self):
        d, base = make_repo('run("ALPHA_CONST")\nrun("BETA_CONST")\n', 'run("ALPHA_CONST")\n')
        out = run_scan(render_script(base, 'tasks.json', 1), d)
        self.assertIn('HIT:BETA_CONST|tests/test_src.py|2', out, out)
        self.assertNotIn('HIT:ALPHA_CONST', out, out)


if __name__ == '__main__':
    unittest.main()
