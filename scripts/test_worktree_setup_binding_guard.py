#!/usr/bin/env python3
"""Fixture for BT.ticket.worktree-setup-can-adopt-the-brain-root-as-repo-root, task 1.

D68: this fixture is written and run FIRST, against the UNMODIFIED engines, and is expected to
FAIL -- a fixture first observed passing proves nothing. Tasks 2-4 change the engine source until
every assertion below passes; task 5 registers this script as a gating check once it is green.

Six named, independent assertions per engine file (A-F), each checked against the engine SOURCE
as plain text -- this repo has no way to execute either engine (D64), so source-level structure is
the only observable signal:

  A. the literal placeholder string '[repoRoot]' appears ZERO times.
  B. a `resolveRepoRoot` helper is defined, and is CALLED before that file's setup-stage
     `tracedAgent(` invocation (the one immediately following `const setupResult = await
     tracedAgent(`) -- compared by source offset, never by line number.
  C. the setup prompt contains the given-not-derived sentinel phrase 'repoRoot is GIVEN'.
  D. a binding-guard region exists (matched by a `BINDING GUARD` sentinel) and sits textually
     BEFORE the per-task loop (`for (const taskNum of taskList)`).
  E. a population-guard region exists (matched by a `POPULATION GUARD` sentinel).
  F. every guard's abort path returns the engine's ordinary error object shape -- an object
     literal carrying an `error` key -- within a short window of each guard sentinel, so
     check_failure_output_shape.py stays satisfiable.

Each assertion fails independently and prints its own PASS/FAIL line; the script exits non-zero
if any assertion fails for any engine. Never piped -- this script's own exit code is the answer
(CLAUDE.md standing rule / trap 1), so callers must check `$?` directly, not through `| tail` or
similar.

Registered in planning/harness.json (task 5) as `worktree-setup-binding-guard` --
run directly: python3 scripts/test_worktree_setup_binding_guard.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ENGINES = {
    "sdlc-flow.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js",
    "sdlc-task.js": REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js",
}

PLACEHOLDER_RE = re.compile(r"\[repoRoot\]")
RESOLVE_FN_DEF_RE = re.compile(r"\basync\s+function\s+resolveRepoRoot\s*\(")
RESOLVE_FN_CALL_RE = re.compile(r"\bresolveRepoRoot\s*\(")
SETUP_AGENT_RE = re.compile(r"const\s+setupResult\s*=\s*await\s+tracedAgent\s*\(")
SENTINEL_GIVEN_RE = re.compile(r"repoRoot is GIVEN")
BINDING_GUARD_RE = re.compile(r"BINDING GUARD")
POPULATION_GUARD_RE = re.compile(r"POPULATION GUARD")
PER_TASK_LOOP_RE = re.compile(r"for\s*\(\s*const\s+taskNum\s+of\s+taskList\s*\)")
# An object literal carrying an `error` key, e.g. `return { error: '...', ... }` or
# `return {\n  error: ...`. Loose on whitespace/newlines, strict on the `error` key itself.
ERROR_SHAPE_RE = re.compile(r"\{[^{}]*\berror\s*:", re.DOTALL)

# How many characters after a guard sentinel to search for its error-shape return. Wide enough
# to span a multi-line guard body, narrow enough not to accidentally match an unrelated abort
# belonging to a completely different stage further down the file.
GUARD_ABORT_WINDOW = 4000


class Result:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes: list[str] = []

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passes.append(label)
        else:
            self.failures.append(f"{label}: {detail}" if detail else label)


def assertion_a(text: str, name: str, r: Result) -> None:
    count = len(PLACEHOLDER_RE.findall(text))
    r.check(f"{name} A (no '[repoRoot]' placeholder)", count == 0, f"found {count} occurrence(s)")


def assertion_b(text: str, name: str, r: Result) -> None:
    def_m = RESOLVE_FN_DEF_RE.search(text)
    if not def_m:
        r.check(f"{name} B (resolveRepoRoot defined + called before setup)", False,
                 "resolveRepoRoot() is not defined")
        return

    setup_m = SETUP_AGENT_RE.search(text)
    if not setup_m:
        r.check(f"{name} B (resolveRepoRoot defined + called before setup)", False,
                 "setup tracedAgent(...) call site (`const setupResult = await tracedAgent(`) "
                 "not found")
        return

    # A call to resolveRepoRoot( that occurs before the setup agent call site, and after (or at)
    # the function's own definition -- i.e. an actual invocation, not merely the definition site
    # matching its own name.
    call_before_setup = None
    for call_m in RESOLVE_FN_CALL_RE.finditer(text):
        if call_m.start() == def_m.start() + len("async function "):
            # skip the definition's own name token if regex overlap ever occurs
            continue
        if call_m.start() < setup_m.start():
            call_before_setup = call_m
    if call_before_setup is None:
        r.check(f"{name} B (resolveRepoRoot defined + called before setup)", False,
                 "resolveRepoRoot() is defined but not called before the setup tracedAgent(...) "
                 "call site")
        return

    r.check(f"{name} B (resolveRepoRoot defined + called before setup)", True)


def assertion_c(text: str, name: str, r: Result) -> None:
    r.check(f"{name} C (sentinel 'repoRoot is GIVEN' present)", bool(SENTINEL_GIVEN_RE.search(text)))


def assertion_d(text: str, name: str, r: Result) -> None:
    guard_m = BINDING_GUARD_RE.search(text)
    loop_m = PER_TASK_LOOP_RE.search(text)
    if not guard_m:
        r.check(f"{name} D (binding guard present, before per-task loop)", False,
                 "no 'BINDING GUARD' region found")
        return
    if not loop_m:
        r.check(f"{name} D (binding guard present, before per-task loop)", False,
                 "per-task loop (`for (const taskNum of taskList)`) not found")
        return
    r.check(f"{name} D (binding guard present, before per-task loop)", guard_m.start() < loop_m.start(),
             f"guard at offset {guard_m.start()} does not precede loop at offset {loop_m.start()}")


def assertion_e(text: str, name: str, r: Result) -> None:
    r.check(f"{name} E (population guard present)", bool(POPULATION_GUARD_RE.search(text)))


def assertion_f(text: str, name: str, r: Result) -> None:
    missing = []
    for label, pattern in (("binding", BINDING_GUARD_RE), ("population", POPULATION_GUARD_RE)):
        m = pattern.search(text)
        if not m:
            missing.append(f"{label} guard sentinel not found")
            continue
        window = text[m.start(): m.start() + GUARD_ABORT_WINDOW]
        if not ERROR_SHAPE_RE.search(window):
            missing.append(
                f"no `{{ ... error: ... }}` abort shape found within "
                f"{GUARD_ABORT_WINDOW} chars after the {label} guard sentinel"
            )
    r.check(f"{name} F (guard aborts use the ordinary {{error, ...}} shape)", not missing,
             "; ".join(missing))


def check_engine(name: str, path: Path, r: Result) -> None:
    if not path.exists():
        r.check(f"{name} (file exists)", False, f"{path} not found")
        return
    text = path.read_text(encoding="utf-8")
    assertion_a(text, name, r)
    assertion_b(text, name, r)
    assertion_c(text, name, r)
    assertion_d(text, name, r)
    assertion_e(text, name, r)
    assertion_f(text, name, r)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true", help="only print output on failure")
    args = ap.parse_args(argv)

    r = Result()
    for name, path in ENGINES.items():
        check_engine(name, path, r)

    if not args.quiet:
        for p in r.passes:
            print(f"PASS  {p}")
    for f in r.failures:
        print(f"FAIL  {f}")

    if r.failures:
        print(f"\n{len(r.failures)} assertion(s) failed, {len(r.passes)} passed.")
        return 1

    if not args.quiet:
        print(f"\nOK -- all {len(r.passes)} assertions passed across {len(ENGINES)} engine(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
