#!/usr/bin/env python3
"""Fixture suite for the engines' vault-commit checker's self-inflicted annotation bug.

WHY THIS EXISTS
----------------
`vaultRelPathsFrom` (byte-identical today in both .claude/workflows/sdlc-task.js and
sdlc-flow.js, and NOT yet in prompts/shared.js) filters a task/stage's self-reported
`filesModified` to entries starting with "planning/" and slices off exactly that prefix. An
implement stage sometimes self-reports a path with its own "(vault: <path>)" annotation
attached -- e.g. "planning/harness.json (vault: side/_planning/price-scout/harness.json)" --
which still startsWith "planning/", so the slice yields the mangled string
"harness.json (vault: side/_planning/price-scout/harness.json)". That string is then stat-ed
verbatim by `verifyVaultCommit`'s stat loop, misses both the vault branch and the BRAIN_ROOT
branch, and falls through to `else echo "UNCOMMITTED:$p"` -- reporting a genuinely committed
vault file as uncommitted and bailing the task. Measured instance: price-scout PS.6.B task 9,
2026-08-30 (see planning/blocks/BT.chore.vault-commit-checker-misparses-its-own-annotation.json).

TWO HALVES
----------
A. RESOLVER BEHAVIOUR (`vaultRelPathsFrom`): the function source is extracted from each engine
   verbatim and evaluated in a real `node` subprocess -- never a Python re-implementation
   standing in for it -- against a plain path, an annotated path (today's RED), a non-planning
   path, and a path with legitimate non-annotation parentheses that must survive un-truncated.
   Both engines' outputs must agree on every case.

B. STAT-LOOP POSITIVE CONTROL (`verifyVaultCommit`'s embedded shell script): extracted from
   shared.js, its `${...}` JS interpolations substituted with real values, and run verbatim via
   `bash` against a throwaway git repo (under `mktemp -d`) holding one committed file and one
   uncommitted file. This proves the underlying stat/git-status logic itself is sound and that a
   later fix to `vaultRelPathsFrom` must not (and does not need to) touch it -- a fix that always
   reports VAULT_OK would pass half A trivially but must fail this half.

RUNNING THIS AGAINST THE UNFIXED TREE (2026-09-06) IS EXPECTED TO FAIL:
half A's annotated-path case fails; half B (independent of the defect) passes.

Once .claude/workflows/prompts/shared.js gains a `<<shared:vaultRelPathsFrom>>` block with the
annotation stripped and both engines are rebuilt via `python3 scripts/build_engines.py --write`,
this suite is registered in planning/harness.json as the gating check `vault-commit-annotation`
(see BT.chore.vault-commit-checker-misparses-its-own-annotation task 3) -- mirroring the
registration note scripts/test_engines_pass_agent.py carries about itself.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SDLC_TASK_JS = ROOT / ".claude" / "workflows" / "sdlc-task.js"
SDLC_FLOW_JS = ROOT / ".claude" / "workflows" / "sdlc-flow.js"
SHARED_JS = ROOT / ".claude" / "workflows" / "prompts" / "shared.js"

FUNC_NAME = "vaultRelPathsFrom"

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg: str) -> None:
    print(f"OK:   {msg}")


# ----------------------------------------------------------------------------
# Extraction helpers
# ----------------------------------------------------------------------------


def extract_function(text: str, name: str) -> str | None:
    """Extract `function <name>(...) { ... }` via balanced-brace matching.

    A plain regex to the first "^}" is not safe in general, but neither engine's copy of this
    function nests any braces inside its body (filter/map/filter with arrow-expression bodies,
    no blocks), so brace counting from the function's own opening brace is exact here and does
    not depend on that assumption holding -- it counts real braces, so it would also work if a
    future rewrite added nested blocks.
    """
    m = re.search(rf"function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", text)
    if not m:
        return None
    start = m.end() - 1  # index of the opening '{'
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[m.start() : i + 1]
    return None


def extract_git_const(text: str) -> str:
    m = re.search(r"const GIT = '([^']*)'", text)
    return m.group(1) if m else "git"


def extract_verify_vault_commit_script(text: str) -> str | None:
    """Pull the raw shell-script template literal out of `verifyVaultCommit`, with the JS
    `${...}` interpolations it actually contains substituted for literal shell text -- never
    re-derived logic, the literal source the engine renders."""
    m = re.search(r"const script = `(.*?)`\n\s*const result", text, re.S)
    return m.group(1) if m else None


# ----------------------------------------------------------------------------
# Part A: vaultRelPathsFrom resolver behaviour (real node subprocess)
# ----------------------------------------------------------------------------

RESOLVER_CASES = [
    # (label, filesModified entry, expected result list)
    ("plain path (control)", "planning/harness.json", ["harness.json"]),
    (
        "annotated path (the RED)",
        "planning/harness.json (vault: side/_planning/price-scout/harness.json)",
        ["harness.json"],
    ),
    ("non-planning path", "src/main.rs", []),
    (
        "legitimate parentheses, not an annotation",
        "planning/notes(v2).md",
        ["notes(v2).md"],
    ),
]


def node_eval_vault_rel_paths(source: str, entry: str) -> tuple[list | None, str]:
    """Run `source` (must define vaultRelPathsFrom) in a real node subprocess and call it with
    a single-entry filesModified array and vault = {vaulted: true}. Returns (result, stderr)."""
    script = (
        source
        + "\n"
        + f"process.stdout.write(JSON.stringify({FUNC_NAME}({json.dumps([entry])}, {{vaulted: true}})));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(script)
        tmp_path = f.name
    try:
        proc = subprocess.run(
            ["node", tmp_path], capture_output=True, text=True, timeout=15
        )
        if proc.returncode != 0:
            return None, f"node exited {proc.returncode}: {proc.stderr.strip()}"
        try:
            return json.loads(proc.stdout), ""
        except Exception as exc:  # pragma: no cover - diagnostic path
            return None, f"could not parse node stdout {proc.stdout!r}: {exc}"
    except FileNotFoundError:
        return None, "node is not installed"
    except subprocess.TimeoutExpired:
        return None, "node eval timed out"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def run_part_a() -> None:
    print("\n=== Part A: vaultRelPathsFrom resolver behaviour ===")

    if not SDLC_TASK_JS.exists() or not SDLC_FLOW_JS.exists():
        fail("one or both engine files are missing")
        return

    task_src = extract_function(SDLC_TASK_JS.read_text(), FUNC_NAME)
    flow_src = extract_function(SDLC_FLOW_JS.read_text(), FUNC_NAME)

    if not task_src:
        fail(f"could not extract {FUNC_NAME} from sdlc-task.js")
        return
    if not flow_src:
        fail(f"could not extract {FUNC_NAME} from sdlc-flow.js")
        return

    ok(f"extracted {FUNC_NAME} from both engines ({len(task_src)} / {len(flow_src)} bytes)")

    for engine_name, src in (("sdlc-task.js", task_src), ("sdlc-flow.js", flow_src)):
        for label, entry, expected in RESOLVER_CASES:
            result, diag = node_eval_vault_rel_paths(src, entry)
            if diag:
                fail(f"[{engine_name}] {label}: node error: {diag}")
                continue
            if result == expected:
                ok(f"[{engine_name}] {label}: {entry!r} -> {result!r}")
            else:
                fail(
                    f"[{engine_name}] {label}: {entry!r} -> {result!r} "
                    f"(expected {expected!r}) -- the stat loop would have received "
                    f"the mangled path(s) {result!r} instead of {expected!r}"
                )

    # Cross-engine agreement on every case in one shot.
    combined_entries = [c[1] for c in RESOLVER_CASES]

    def eval_all(src: str) -> tuple[list | None, str]:
        script = (
            src
            + "\n"
            + f"process.stdout.write(JSON.stringify({FUNC_NAME}({json.dumps(combined_entries)}, {{vaulted: true}})));\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(script)
            tmp_path = f.name
        try:
            proc = subprocess.run(["node", tmp_path], capture_output=True, text=True, timeout=15)
            if proc.returncode != 0:
                return None, f"node exited {proc.returncode}: {proc.stderr.strip()}"
            return json.loads(proc.stdout), ""
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    task_combined, task_diag2 = eval_all(task_src)
    flow_combined, flow_diag2 = eval_all(flow_src)
    if task_diag2 or flow_diag2:
        fail(f"cross-engine agreement check: node error(s): {task_diag2!r} {flow_diag2!r}")
    elif task_combined != flow_combined:
        fail(
            f"engines DISAGREE on identical input: sdlc-task.js -> {task_combined!r}, "
            f"sdlc-flow.js -> {flow_combined!r}"
        )
    else:
        ok(f"both engines agree on the combined input set: {task_combined!r}")


# ----------------------------------------------------------------------------
# Part B: verifyVaultCommit stat-loop positive control (throwaway git repo)
# ----------------------------------------------------------------------------


def run_part_b() -> None:
    print("\n=== Part B: verifyVaultCommit stat-loop positive control ===")

    if not SHARED_JS.exists():
        fail("prompts/shared.js is missing")
        return

    shared_text = SHARED_JS.read_text()
    git_bin = extract_git_const(SDLC_TASK_JS.read_text()) if SDLC_TASK_JS.exists() else "git"
    script_template = extract_verify_vault_commit_script(shared_text)
    if not script_template:
        fail("could not extract verifyVaultCommit's shell script template from shared.js")
        return
    ok(f"extracted verifyVaultCommit's shell script template ({len(script_template)} bytes)")

    with tempfile.TemporaryDirectory(prefix="vault-commit-fixture-") as tmp:
        vault_path = Path(tmp) / "vault-planning"
        vault_path.mkdir()

        def run_git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-C", str(vault_path), *args],
                capture_output=True,
                text=True,
                check=True,
            )

        run_git("init", "-q")
        run_git("config", "user.email", "test@example.com")
        run_git("config", "user.name", "Test")

        committed_rel = "committed.md"
        uncommitted_rel = "uncommitted.md"
        (vault_path / committed_rel).write_text("committed content\n")
        run_git("add", committed_rel)
        run_git("commit", "-q", "-m", "seed committed file")

        (vault_path / uncommitted_rel).write_text("uncommitted content\n")
        # Deliberately never added/committed -- this is the negative control.

        vault_rel_paths = [committed_rel, uncommitted_rel]
        joined = " ".join(json.dumps(p) for p in vault_rel_paths)

        script = script_template
        script = script.replace(
            "${vaultRelPaths.map(p => JSON.stringify(p)).join(' ')}", joined
        )
        script = script.replace("${vault.planningPath}", str(vault_path))
        script = script.replace("${GIT}", git_bin)

        if "${" in script:
            fail(
                "unsubstituted JS interpolation(s) remain in the extracted script -- "
                f"cannot run it as bash verbatim: {script!r}"
            )
            return

        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, dir=tmp) as f:
            f.write(script)
            sh_path = f.name

        try:
            proc = subprocess.run(
                ["bash", sh_path], capture_output=True, text=True, timeout=15
            )
        finally:
            Path(sh_path).unlink(missing_ok=True)

        if proc.returncode != 0:
            fail(f"stat-loop script exited {proc.returncode}: {proc.stderr.strip()}")
            return

        lines = [l for l in proc.stdout.splitlines() if l.strip()]
        buckets = {}
        for line in lines:
            if ":" not in line:
                continue
            bucket, path = line.split(":", 1)
            buckets[path] = bucket

        if buckets.get(committed_rel) in ("VAULT_OK", "BRAIN_ROOT_OK"):
            ok(f"committed file reported {buckets.get(committed_rel)}")
        else:
            fail(
                f"committed file '{committed_rel}' reported {buckets.get(committed_rel)!r}, "
                f"expected VAULT_OK -- raw output: {proc.stdout!r}"
            )

        if buckets.get(uncommitted_rel) == "UNCOMMITTED":
            ok(f"uncommitted file reported UNCOMMITTED (negative control holds)")
        else:
            fail(
                f"uncommitted file '{uncommitted_rel}' reported "
                f"{buckets.get(uncommitted_rel)!r}, expected UNCOMMITTED -- a check that "
                f"always reports OK would pass Part A trivially but must fail here -- "
                f"raw output: {proc.stdout!r}"
            )


def main() -> int:
    run_part_a()
    run_part_b()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
