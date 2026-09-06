#!/usr/bin/env python3
"""Whole-file syntax check for the SDLC engine `.js` files.

WHY THIS EXISTS
---------------
`node --check` exits 0 on a syntax error placed AFTER the first top-level
`export` in this fleet's Node (v26). Reproduced directly: a copy of
sdlc-task.js with `const __bogus = (;` appended after its `export const meta`
line exits 0 under `node --check`; the identical break inserted before the
export exits 1. Node's ambiguous CommonJS/ESM detection concludes "this is a
module" the moment it sees `export`, and does not appear to fully re-validate
everything that follows -- so `engines-parse` (gates:true, the only thing
between a malformed engine and the 18 repos it syncs to) was effectively blind
to almost the whole file.

WHAT THIS DOES
--------------
The engines are not plain ESM or plain CommonJS: each file has exactly one
top-level `export const meta = {...}` (read by the Workflow tool's own script
loader) followed by a large body that uses top-level `return` and top-level
`await` -- both only legal inside a function, and `await` specifically only
inside an ASYNC function. That is the real execution shape the Workflow tool
gives these scripts: an async-function body, with `export const meta` special-
cased on top.

So this script strips the single leading `export ` token, wraps the rest in
`(async function(){ ... })`, and compiles the whole thing with Node's
`vm.Script` (a real, non-lazy-on-detection V8 parse of the complete source --
not `node --check`'s ambiguous-module heuristic). A syntax error anywhere in
the file, before or after the export line, surfaces as a compile failure.

This is a GATING check (engines-parse in planning/harness.json). A failure
means an engine file does not parse; fix the syntax, do not re-baseline
anything. Out of scope: `scripts/check_prompt_templates.py` /
`prompt-template-parse` (a different failure -- bare backticks inside a
prompt template) and the Node version pin.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ENGINES = [
    ".claude/workflows/sdlc-task.js",
    ".claude/workflows/sdlc-flow.js",
]

# Compiled once, written to a temp file, and invoked with `node <checker> <target>`.
# Kept as a separate script (rather than `node -e ...`) to avoid quoting/escaping
# hazards -- the target engines themselves contain heavy backtick/quote content.
_NODE_CHECKER = r"""
const vm = require('vm');
const fs = require('fs');

const filename = process.argv[2];
let src;
try {
  src = fs.readFileSync(filename, 'utf8');
} catch (e) {
  console.log(JSON.stringify({ ok: false, readError: String(e && e.message || e) }));
  process.exit(2);
}

// Strip exactly one leading top-level `export ` token (these engines carry a
// single `export const meta = {...}` for the Workflow tool's loader) and wrap
// the remainder as an async function body -- the shape the Workflow tool
// actually executes these files as (top-level `return` / `await` throughout).
const body = src.replace(/^export\s+/m, '');
const wrapped = '(async function(){\n' + body + '\n})';

try {
  new vm.Script(wrapped, { filename });
  console.log(JSON.stringify({ ok: true }));
} catch (e) {
  const stack = String((e && e.stack) || (e && e.message) || e);
  const stackLines = stack.split('\n');
  // vm.Script's SyntaxError stack starts: "<filename>:<line>\n<source line>\n<caret>\n\nSyntaxError: ..."
  let line = null;
  let column = null;
  const head = stackLines[0] || '';
  const headMatch = head.match(/:(\d+)$/);
  if (headMatch) {
    // -1 to undo the single header line ("(async function(){") this script prepended.
    line = parseInt(headMatch[1], 10) - 1;
  }
  const caretLine = stackLines[2] || '';
  const caretIdx = caretLine.indexOf('^');
  if (caretIdx >= 0) {
    column = caretIdx + 1;
  }
  const messageLine = stackLines.find((l) => l.includes('SyntaxError') || l.includes('Error')) || stackLines[stackLines.length - 1] || String(e);
  console.log(JSON.stringify({ ok: false, line, column, message: messageLine.trim() }));
  process.exit(1);
}
"""


def check_file(rel: str) -> str | None:
    """Compile `rel` (repo-relative) with the whole-file checker.

    Returns None on success, or a one-line failure description (path:line:col
    plus the parser's message) on failure.
    """
    path = REPO_ROOT / rel
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(_NODE_CHECKER)
        checker_path = fh.name
    try:
        proc = subprocess.run(
            ["node", checker_path, str(path)],
            capture_output=True,
            text=True,
        )
        stdout = (proc.stdout or "").strip()
        if not stdout:
            stderr = (proc.stderr or "").strip() or "(no output)"
            return f"{rel}: checker produced no output -- {stderr}"
        try:
            result = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError:
            return f"{rel}: could not parse checker output -- {stdout}"
        if result.get("ok"):
            return None
        if "readError" in result:
            return f"{rel}: {result['readError']}"
        line = result.get("line")
        column = result.get("column")
        message = result.get("message", "unknown syntax error")
        loc = rel
        if line is not None:
            loc += f":{line}"
            if column is not None:
                loc += f":{column}"
        return f"{loc} -- {message}"
    finally:
        Path(checker_path).unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    raw_args = argv[1:]
    targets = [t for t in raw_args if t.endswith(".js")] if raw_args else ENGINES

    failures: list[str] = []
    checked = 0
    for rel in targets:
        path = REPO_ROOT / rel
        if not path.exists():
            print(f"ERROR: {rel} not found", file=sys.stderr)
            return 2
        err = check_file(rel)
        checked += 1
        if err is not None:
            failures.append(err)

    if failures:
        print("Whole-file engine syntax check FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
