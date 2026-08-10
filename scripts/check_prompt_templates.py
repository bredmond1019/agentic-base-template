#!/usr/bin/env python3
"""Parse-check every agent-prompt template literal in the SDLC engines.

WHY THIS EXISTS
---------------
D60 added the sentence "pass them explicitly to `git commit` itself (not merely
to `git add`)" to five vault-commit sites across sdlc-task.js and sdlc-flow.js.
Three of them shipped with BARE backticks. Inside a template literal a bare
backtick TERMINATES the template, and the following `git` is parsed as an
identifier -- so the prose silently became code and the prompt stopped rendering
as written.

A whole-file `node --check` DOES NOT CATCH THIS. The stray backticks come in
pairs on adjacent lines, so file-level backtick parity survives and the parser
resolves the prose into tagged-template expressions instead of erroring. The
file "compiles" while the template boundaries have silently shifted. That is
exactly what happened: `engines-parse` (this repo's only build gate) returned
green for a full session while sdlc-task and sdlc-flow were both absent from the
Workflow/Skill registries, because the registry loader is stricter than
`node --check`. The outage was misdiagnosed as a stale launcher cache.

WHAT THIS DOES
--------------
Extracts each prompt template region -- from an `agent(` / `tracedAgent(`
backtick opener to its matching column-0 "`, " closer -- wraps it alone in an
async function, and runs `node --check` on JUST that region. A region-scoped
parse sees the imbalance that the whole-file parse absorbs.

Undefined identifiers are irrelevant here: `node --check` is syntax-only, so the
stubs a real run would need are unnecessary.

This is a GATING check. A failure means an engine's prompt text is not what the
source appears to say -- fix the escaping (prose backticks inside a template
literal must be written \\`), do not re-baseline anything.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ENGINES = [
    ".claude/workflows/sdlc-task.js",
    ".claude/workflows/sdlc-flow.js",
    ".claude/workflows/sdlc-block.js",
    ".claude/workflows/sdlc-run.js",
]

# `const x = await tracedAgent(` / `await agent(` immediately followed by a backtick.
OPENER = re.compile(r"(?:tracedAgent|agent)\(`")
# The closing delimiter the engines use, always at column 0: "`, withModel({...".
CLOSER = re.compile(r"^`,\s")


def extract_regions(lines: list[str]) -> list[tuple[int, int]]:
    """Return (start_line, end_line) 1-indexed inclusive for each prompt template."""
    regions: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if OPENER.search(lines[i]):
            for j in range(i + 1, len(lines)):
                if CLOSER.match(lines[j]):
                    regions.append((i + 1, j + 1))
                    i = j
                    break
            else:
                # An opener with no closer is itself a defect worth reporting.
                regions.append((i + 1, len(lines)))
                break
        i += 1
    return regions


def check_region(lines: list[str], start: int, end: int) -> str | None:
    """node --check the region alone. Return stderr on failure, None on success."""
    body = "\n".join(lines[start - 1 : end])
    src = "async function __region__() {\n" + body + "\n}\n"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        tmp = fh.name
    try:
        proc = subprocess.run(
            ["node", "--check", tmp], capture_output=True, text=True
        )
        if proc.returncode == 0:
            return None
        return proc.stderr.strip()
    finally:
        Path(tmp).unlink(missing_ok=True)


def check_file(path: Path, rel: str) -> list[str]:
    lines = path.read_text(encoding="utf-8").split("\n")
    failures: list[str] = []
    for start, end in extract_regions(lines):
        err = check_region(lines, start, end)
        if err is None:
            continue
        detail = next(
            (ln for ln in err.splitlines() if "SyntaxError" in ln), err.splitlines()[0]
        )
        failures.append(f"  - {rel}:{start}-{end} -> {detail}")
    return failures


def main(argv: list[str]) -> int:
    targets = argv[1:] or ENGINES
    all_failures: list[str] = []
    checked = 0

    for rel in targets:
        path = REPO_ROOT / rel
        if not path.exists():
            print(f"ERROR: {rel} not found", file=sys.stderr)
            return 2
        regions = extract_regions(path.read_text(encoding="utf-8").split("\n"))
        checked += len(regions)
        all_failures.extend(check_file(path, rel))

    if all_failures:
        print("Prompt-template parse check FAILED:\n")
        print("\n".join(all_failures))
        print(
            "\nA prompt template does not parse in isolation. The usual cause is a\n"
            "BARE backtick in prose inside the template (e.g. `git commit`), which\n"
            "terminates the template early. Escape it as \\` .\n"
            "\n"
            "Note: `node --check` on the whole file can still pass while this fails --\n"
            "paired stray backticks keep file-level parity. That is the whole reason\n"
            "this check is region-scoped."
        )
        return 1

    print(f"OK -- {checked} prompt templates parse cleanly across {len(targets)} engines.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
