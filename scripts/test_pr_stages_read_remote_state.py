#!/usr/bin/env python3
"""Fixture for BT.ticket.pr-stages-read-draft-and-checks-from-github, task 1.

D68: this fixture is written and run FIRST, against the UNMODIFIED engine, and is expected to
FAIL -- a fixture first observed passing proves nothing. Task 2 changes
`.claude/workflows/sdlc-flow.js` until every assertion below passes; task 3 registers this script
as a gating check once it is green.

Six named, independent assertions (A-F), each checked against the engine SOURCE as plain text --
this repo has no way to execute the engine (D64), so source-level structure is the only
observable signal:

  A. the pr-verify stage's `gh pr view` field list (the `--json number,url,state` argument on the
     same line as `gh pr view`, within the pr-verify prompt) includes `isDraft`.
  B. `PR_VERIFY_SCHEMA.properties` declares `isDraft` with `type: 'boolean'`.
  C. the auto-merge stage's prompt contains a `gh pr checks` poll.
  D. the auto-merge stage's prompt contains a conditional `gh pr ready`.
  E. the `gh pr checks` poll appears at a LOWER source offset than the merge invocation
     (`gh pr merge`) within the auto-merge prompt -- compared by `str.find`/regex `.start()`
     offset, never by line number, since line numbers move with every edit above them.
  F. `MERGE_SCHEMA` carries a field distinguishing a non-merge caused by a FAILING check from one
     caused by an attempt made BEFORE checks finished -- matched by the two literal marker
     substrings `checks-failed` and `attempted-too-early` appearing somewhere in the
     `MERGE_SCHEMA` object literal (the exact field name is an implementation choice made when
     the schema is authored; these two substrings are the stable contract this fixture pins).

Each assertion fails independently and prints its own PASS/FAIL line; the script exits non-zero
if any assertion fails. Never piped -- this script's own exit code is the answer (CLAUDE.md
standing rule / trap 1), so callers must check `$?` directly, not through `| tail` or similar.

Stages are located by their `label: 'pr-verify'` / `label: 'auto-merge'` markers (via the
`<name> = await tracedAgent(...)` call-site anchors immediately preceding each prompt), never by
line number or a fragile surrounding phrase.

Run directly: python3 scripts/test_pr_stages_read_remote_state.py
Registered in planning/harness.json (task 3) as `pr-stages-remote-state-tests`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js"

# Anchors for each stage's prompt region: from the `<var> = await tracedAgent(` call site up to
# (but not including) that same call's `withModel({ label: '<stage>', ...` marker -- i.e. the
# prompt text the agent actually receives, nothing more.
PR_VERIFY_CALL_RE = re.compile(r"prVerify\s*=\s*await\s+tracedAgent\s*\(")
PR_VERIFY_LABEL_RE = re.compile(r"withModel\(\{\s*label:\s*'pr-verify'")
AUTO_MERGE_CALL_RE = re.compile(r"mergeInfo\s*=\s*await\s+tracedAgent\s*\(")
AUTO_MERGE_LABEL_RE = re.compile(r"withModel\(\{\s*label:\s*'auto-merge'")

PR_VERIFY_SCHEMA_RE = re.compile(
    r"const\s+PR_VERIFY_SCHEMA\s*=\s*\{.*?\n\}\n", re.DOTALL
)
MERGE_SCHEMA_RE = re.compile(
    r"const\s+MERGE_SCHEMA\s*=\s*\{.*?\n\}\n", re.DOTALL
)

GH_PR_VIEW_LINE_RE = re.compile(r"gh pr view [^\n]*--json\s+([^\s\"]+)")
ISDRAFT_BOOLEAN_PROP_RE = re.compile(r"isDraft\s*:\s*\{[^}]*type:\s*'boolean'")
GH_PR_CHECKS_RE = re.compile(r"gh pr checks\b")
GH_PR_READY_RE = re.compile(r"gh pr ready\b")
GH_PR_MERGE_RE = re.compile(r"gh pr merge\b")


class Result:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes: list[str] = []

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passes.append(label)
        else:
            self.failures.append(f"{label}: {detail}" if detail else label)


def extract_region(text: str, call_re: re.Pattern, label_re: re.Pattern, region_name: str,
                    r: Result) -> str | None:
    call_m = call_re.search(text)
    if not call_m:
        r.check(f"locate {region_name} call site", False,
                 f"pattern {call_re.pattern!r} not found")
        return None
    label_m = label_re.search(text, call_m.end())
    if not label_m:
        r.check(f"locate {region_name} label marker", False,
                 f"pattern {label_re.pattern!r} not found after call site")
        return None
    return text[call_m.end():label_m.start()]


def assertion_a(pr_verify_region: str | None, r: Result) -> None:
    if pr_verify_region is None:
        r.check("A (pr-verify gh pr view field list includes isDraft)", False,
                 "pr-verify prompt region could not be located")
        return
    m = GH_PR_VIEW_LINE_RE.search(pr_verify_region)
    if not m:
        r.check("A (pr-verify gh pr view field list includes isDraft)", False,
                 "no `gh pr view ... --json <fields>` line found in pr-verify prompt")
        return
    fields = m.group(1).split(",")
    r.check("A (pr-verify gh pr view field list includes isDraft)", "isDraft" in fields,
             f"field list was: {fields}")


def assertion_b(text: str, r: Result) -> None:
    m = PR_VERIFY_SCHEMA_RE.search(text)
    if not m:
        r.check("B (PR_VERIFY_SCHEMA.properties declares isDraft as boolean)", False,
                 "PR_VERIFY_SCHEMA definition not found")
        return
    r.check("B (PR_VERIFY_SCHEMA.properties declares isDraft as boolean)",
             bool(ISDRAFT_BOOLEAN_PROP_RE.search(m.group(0))))


def assertion_c(auto_merge_region: str | None, r: Result) -> None:
    if auto_merge_region is None:
        r.check("C (auto-merge prompt contains a `gh pr checks` poll)", False,
                 "auto-merge prompt region could not be located")
        return
    r.check("C (auto-merge prompt contains a `gh pr checks` poll)",
             bool(GH_PR_CHECKS_RE.search(auto_merge_region)))


def assertion_d(auto_merge_region: str | None, r: Result) -> None:
    if auto_merge_region is None:
        r.check("D (auto-merge prompt contains a conditional `gh pr ready`)", False,
                 "auto-merge prompt region could not be located")
        return
    r.check("D (auto-merge prompt contains a conditional `gh pr ready`)",
             bool(GH_PR_READY_RE.search(auto_merge_region)))


def assertion_e(auto_merge_region: str | None, r: Result) -> None:
    if auto_merge_region is None:
        r.check("E (`gh pr checks` poll precedes `gh pr merge` by source offset)", False,
                 "auto-merge prompt region could not be located")
        return
    checks_m = GH_PR_CHECKS_RE.search(auto_merge_region)
    merge_m = GH_PR_MERGE_RE.search(auto_merge_region)
    if not checks_m:
        r.check("E (`gh pr checks` poll precedes `gh pr merge` by source offset)", False,
                 "no `gh pr checks` found in auto-merge prompt")
        return
    if not merge_m:
        r.check("E (`gh pr checks` poll precedes `gh pr merge` by source offset)", False,
                 "no `gh pr merge` found in auto-merge prompt")
        return
    r.check("E (`gh pr checks` poll precedes `gh pr merge` by source offset)",
             checks_m.start() < merge_m.start(),
             f"checks at offset {checks_m.start()} does not precede merge at offset {merge_m.start()}")


def assertion_f(text: str, r: Result) -> None:
    m = MERGE_SCHEMA_RE.search(text)
    if not m:
        r.check("F (MERGE_SCHEMA distinguishes checks-failed from attempted-too-early)", False,
                 "MERGE_SCHEMA definition not found")
        return
    schema_text = m.group(0)
    missing = []
    for marker in ("checks-failed", "attempted-too-early"):
        if marker not in schema_text:
            missing.append(marker)
    r.check("F (MERGE_SCHEMA distinguishes checks-failed from attempted-too-early)", not missing,
             f"missing marker(s): {missing}" if missing else "")


def main() -> int:
    if not ENGINE_PATH.exists():
        print(f"FAIL  engine file not found: {ENGINE_PATH}")
        return 1

    text = ENGINE_PATH.read_text(encoding="utf-8")
    r = Result()

    pr_verify_region = extract_region(text, PR_VERIFY_CALL_RE, PR_VERIFY_LABEL_RE, "pr-verify", r)
    auto_merge_region = extract_region(text, AUTO_MERGE_CALL_RE, AUTO_MERGE_LABEL_RE, "auto-merge", r)

    assertion_a(pr_verify_region, r)
    assertion_b(text, r)
    assertion_c(auto_merge_region, r)
    assertion_d(auto_merge_region, r)
    assertion_e(auto_merge_region, r)
    assertion_f(text, r)

    for p in r.passes:
        print(f"PASS  {p}")
    for f in r.failures:
        print(f"FAIL  {f}")

    if r.failures:
        print(f"\n{len(r.failures)} assertion(s) failed, {len(r.passes)} passed.")
        return 1

    print(f"\nOK -- all {len(r.passes)} assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
