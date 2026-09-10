#!/usr/bin/env python3
"""Source-assertion suite: both SDLC engines must pass --agent to `mev emit-state --write`.

WHY THIS EXISTS
----------------
`mev`'s `refuse_if_quiesced` refuses an identity-less `emit-state --write` caller against ANY
live exclusive lease, including one the calling lane wrote itself. sdlc-task.js and sdlc-flow.js
invoke `mev emit-state --write` with no `--agent`, so a lane that took a Step 4 exclusive lease
has its own bookkeep emit silently refused and its closed blocks keep an open graph status. See
planning/blocks/BT.ticket.engines-must-pass-agent-to-mev.json for the full record.

THE THREE REAL INVOCATION SITES
--------------------------------
`emit-state` appears many times in each engine, but almost all of those are prose: schema
`description` strings, log lines, comments. The real `mev emit-state --write` INVOCATION sites --
text meant to be run, not text describing the mechanism -- are exactly THREE:
  - .claude/workflows/sdlc-task.js  (bookkeep step 5, in-place branch)         `cd ${x} && mev
    emit-state --write . If ...`
  - .claude/workflows/sdlc-flow.js  (wrap-up step 2c, in-place branch)         same shape
  - .claude/workflows/sdlc-flow.js  (--auto-merge step 5, on the PR base)      standalone
    `mev emit-state --write` on its own line
This suite locates them structurally (the `&& mev emit-state --write` chained-command shape, and
the bare-line standalone shape) rather than by line number, and REFUSES to proceed if it finds a
count other than 3 -- a site added or removed later must break this test, not slip past it.

THE CONTRACT THIS SUITE ENCODES (for the task that fixes this to implement against)
-------------------------------------------------------------------------------------
This is the design call the block record flags as ungrounded; it is decided here, in the test,
so the fix has one unambiguous target instead of inventing its own shape:

  - `.claude/workflows/prompts/shared.js` defines ONE identity resolver, a zero-argument function
    named `renderAgentFlag`, inlined into both engines the usual way via
    `// <<shared:renderAgentFlag>> ... // <</shared:renderAgentFlag>>` (scripts/build_engines.py).
  - `renderAgentFlag()` returns '' (empty string) when no identity resolves, and the literal
    string ' --agent <id>' (one leading space, no trailing) when one does.
  - Identity resolution order: the `FLEET_LANE_AGENT` environment variable if set and non-empty;
    else the `agent` field of `<lock_dir>/leases/lease-<repo>.json`; else no identity resolves.
    `<lock_dir>` uses the SAME precedence scripts/check_lane_agents.py's `find_lock_dir()` already
    uses: `FLEET_LOCK_DIR` env var, else a `brain.toml` found by walking up from cwd, joined with
    `.fleet-locks`. No new precedence is introduced.
  - Every one of the three invocation sites interpolates the call immediately after the literal
    `--write`, as `--write${renderAgentFlag()}` -- no other character sits between `--write` and
    the interpolation. That is what lets this suite's byte-identity check work by textual
    subtraction: strip exactly that substring back out and the line must equal the frozen
    pre-change baseline captured below, character for character.

WHAT THIS SUITE ASSERTS
-------------------------
1. Exactly 3 invocation sites are found (printed before anything else is asserted, per AC1 --
   no single site is ever judged in isolation).
2. Each site interpolates `${renderAgentFlag()}` immediately after `--write`. Today none do --
   this is the load-bearing RED this suite exists to prove, per BT.ticket.gates-must-be-observed-red.
3. Once all three do: stripping that exact substring from each site's line reproduces the frozen
   pre-change baseline byte-for-byte (the negative control -- an unconditional flag would change
   every non-lane, non-fleet run of these engines, and 18+ downstream repos run them standalone).
4. `renderAgentFlag` is defined identically (byte-for-byte) as a `<<shared:renderAgentFlag>>` block
   in shared.js AND inlined identically into both engine files (build_engines.py parity).
5. The extracted resolver actually behaves per the contract: '' with no identity available, and
   ' --agent <id>' when `FLEET_LANE_AGENT=<id>` is set -- exercised by evaluating the extracted
   source in a real `node` subprocess (never a Python re-implementation standing in for it).

This is a GATING check once registered (task 4 of this block) -- it is deliberately NOT registered
in planning/harness.json by this file; that registration is a separate, later task.

Usage:
    python3 scripts/test_engines_pass_agent.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_JS = REPO_ROOT / ".claude" / "workflows" / "sdlc-task.js"
FLOW_JS = REPO_ROOT / ".claude" / "workflows" / "sdlc-flow.js"
SHARED_JS = REPO_ROOT / ".claude" / "workflows" / "prompts" / "shared.js"

RESOLVER_NAME = "renderAgentFlag"
FLAG_INTERP = "${await " + RESOLVER_NAME + "()}"

# --- locate the 3 real invocation sites -------------------------------------------------------
# Real invocations look like either:
#   `... && mev emit-state --write . If ...`                 (chained after a `cd`, task/flow)
#   `   mev emit-state --write`                               (standalone, flow's --auto-merge)
# Once fixed, an optional `${renderAgentFlag()}` sits immediately after `--write` in both shapes,
# and once BT.ticket.engines-pass-scope-to-emit-state also lands, a second interpolation
# (`${renderScopeFlag()}`) sits immediately after that one -- so the interpolation group allows
# ZERO OR MORE contiguous `${...}` chunks, not just zero-or-one, or this locator stops matching
# the moment a second flag is appended. Every OTHER mention of "emit-state --write" in these
# files is prose wrapped in backticks (`` `mev emit-state --write` `` in a schema description,
# comment, or log line) and is excluded by requiring the literal, un-backticked shapes below.

CD_SITE_RE = re.compile(
    r"^(?P<line>.*&&\s*mev emit-state --write(?:\$\{[^}]+\})*\s*\.\s*If\b.*)$", re.M
)
STANDALONE_SITE_RE = re.compile(
    r"^(?P<line>[ \t]*mev emit-state --write(?:\$\{[^}]+\})*[ \t]*)$", re.M
)

# The frozen pre-change baseline: the exact three lines as they exist BEFORE this fix, captured
# 2026-09-03 (BT.ticket.engines-must-pass-agent-to-mev, task 1). After the fix, each corresponding
# line with the `${renderAgentFlag()}` substring removed must equal one of these, character for
# character. Recorded now because after task 2 lands, the pre-change text is only recoverable
# from git history.
#
# Line numbers re-pinned 2026-09-06 (BT.ticket.harness-config-must-bail-not-warn-on-a-malformed-
# payload, tasks 1-2): those tasks inserted 52 net lines above this site in sdlc-task.js and 62
# net lines above both sites in sdlc-flow.js, shifting them from 2898->2950 / 3328->3390 /
# 3617->3679. Text unchanged (confirmed via diff against the pre-shift content) -- only the keys
# moved.
#
# Re-pinned again 2026-09-06 (BT.ticket.sdlc-bookkeep-writes-block-status-deterministically,
# tasks 1-3): the new renderStateFlipScript region (the deterministic `mev set-block-status`
# dispatch) was inlined ABOVE these sites in both engines, shifting them from 2950->3025 in
# sdlc-task.js and 3390->3464 / 3679->3753 in sdlc-flow.js. Text unchanged (diffed against the
# pre-shift content) -- only the keys moved.
#
# Re-pinned again 2026-09-06 (BT.ticket.sdlc-task-must-verify-its-blocks-acceptance-criteria,
# task 1): the new acceptanceCriteriaVerdicts function (70 net lines) was inlined at the engine
# source level ABOVE these sites in sdlc-task.js, shifting it from 3025->3095. Text unchanged
# (pre-change bytes extracted via diff) -- only the key moved. sdlc-flow.js unaffected.
# Re-pinned again 2026-09-06 (BT.ticket.sdlc-task-must-verify-its-blocks-acceptance-criteria,
# task 2): the new Criteria stage prompt (123 net lines) was inlined at the engine source level
# ABOVE this site in sdlc-task.js, shifting it from 3095->3218. Text unchanged (diffed against the
# pre-shift content) -- only the key moved. sdlc-flow.js unaffected.
# Re-pinned again 2026-09-06 (BT.ticket.engines-must-not-author-unverified-records, task 1): the
# new <<shared:renderOperatorGatedACRule>> block was inlined ABOVE these sites in both engines --
# net +16 lines in sdlc-task.js (3221->3237) and net +18 lines in sdlc-flow.js (3464->3482,
# 3753->3771). Text unchanged (diffed against the pre-shift content) -- only the keys moved.
# Re-pinned again 2026-09-06 (BT.ticket.engines-must-not-author-unverified-records, task 2): the
# renderImplementPrompt() shared region (prompts/shared.js) grew by 14 lines and both engines
# inline it, shifting the site ABOVE by the same amount -- net +14 lines in sdlc-task.js
# (3237->3251) and net +14 lines in sdlc-flow.js (3482->3496, 3771->3785). Text unchanged
# (diffed against the pre-shift content) -- only the keys moved.
# Re-pinned again 2026-09-07 (BT.ticket.criteria-verdict-stage-silently-no-ops-and-is-never-
# persisted, task 2 fix pass): the loadBlockRecordAcceptanceCriteria reason plumbing inserted 30 net lines
# into sdlc-task.js ABOVE this site, shifting it from 3251->3281. Text unchanged (diffed against
# the pre-shift content) -- only the key moved. sdlc-flow.js unaffected.
# Re-pinned again 2026-09-07 (BT.ticket.criteria-verdict-stage-silently-no-ops-and-is-never-
# persisted, task 3): the criteriaVerdicts state-literal field + its comment block, plus the
# state.criteriaVerdicts assignment at the point verdicts are computed, inserted 18 net lines into
# sdlc-task.js ABOVE this site, shifting it from 3281->3299. Text unchanged (diffed against the
# pre-shift content) -- only the key moved. sdlc-flow.js unaffected.
# Re-pinned again 2026-09-07 (BT.ticket.engine-helpers-call-require-which-the-workflow-runtime-
# does-not-define): loadBlockRecordAcceptanceCriteria's agent-based rewrite (the CRITERIA_LOAD_
# SCHEMA constant + the new async body, expanded again once the classification logic moved into
# a deterministic probe script) added net 32 lines into sdlc-task.js ABOVE this site, shifting it
# from 3312->3344. Text unchanged (diffed against the pre-shift content) -- only the key moved.
# sdlc-flow.js unaffected (its two sites carry no such site-local change).
# BT.ticket.engine-render-identity-schema-tdz (2026-09-07): the <<shared:RENDER_IDENTITY_SCHEMA>>
# region moved up to just after <</shared:BAIL_REASONS>> in both engines (it was declared BELOW the
# top-level awaits that reach it, throwing a temporal-dead-zone ReferenceError at the bookkeep
# stage). That inserted 10 net lines above all three sites: 3344->3354 in sdlc-task.js, 3496->3506
# and 3785->3795 in sdlc-flow.js. Text unchanged -- verified by diffing each old line in a pre-fix
# copy of the engine against the new line in the fixed file, byte-identical at all three. Only the
# keys moved.
# Re-pinned again 2026-09-07 (BT.ticket.sdlc-flow-records-no-base-sha, task 2): the STEP 5.5
# emoji-gate-diff-base capture (both the worktreeRecipe and branchRecipe variants) plus a new
# setupWorkdir const were inlined ABOVE both sdlc-flow.js sites, net +13 lines: 3506->3519 and
# 3795->3808. Text unchanged (diffed the old line against the new line at both sites, byte-
# identical) -- only the keys moved. sdlc-task.js unaffected (this task touches sdlc-flow.js only).
# Re-pinned again 2026-09-08 (BT.ticket.sdlc-task-worktree-flag-is-intermittently-ignored,
# tasks 1-2): the new currentBranch and worktreeListPorcelain SETUP_SCHEMA fields plus task 2's
# parseWorktreeListPorcelain() helper and cross-check logic were inlined ABOVE this site in
# sdlc-task.js, net +66 lines: 3396->3462. Text unchanged (diffed against the pre-shift content)
# -- only the key moved. sdlc-flow.js unaffected.
# Re-pinned again 2026-09-08 (BT.ticket.engines-forbid-attribution-trailers, task 2): the new
# renderNoAttributionTrailer() function and its references at all 14 commit-heredoc sites were
# inlined ABOVE these sites in all three engine files (prompts/shared.js plus sdlc-task.js and
# sdlc-flow.js), net +14 lines in each: 3462->3476 in sdlc-task.js and 3531->3546 / 3820->3836
# in sdlc-flow.js. The actual line text is unchanged from when renderAgentFlag was added --
# task 2 added renderNoAttributionTrailer references and the commit-safety guard prompts, not
# the emit-state interpolations themselves. Only the line numbers moved.
# LINE NUMBERS RE-PICKED 2026-09-08 (lane base-template-75): +4 on all three sites, from
# `da72104 fix: rebuild engines from shared library`. Verified by confirming each baseline STRING
# is byte-identical at its new line before renumbering -- the numbers were moved to follow the
# content, never the content adjusted to fit the numbers.
# Re-pinned again 2026-09-08 (BT.ticket.lane-heartbeat-goes-stale-mid-block, task 4): the new
# `heartbeatRecipe` param + doc comment on the shared renderTestPrompt() region, inlined ABOVE
# these sites in both engines, shifted all three by +7: 3480->3487 in sdlc-task.js and
# 3550->3557 / 3840->3847 in sdlc-flow.js. Text unchanged (diffed against the pre-shift content,
# byte-identical) -- only the keys moved. The new renderLaneHeartbeatRecipe() shared block that
# same task added sits AFTER renderScopeFlag() (end of file, below all three sites), so it does
# not shift these lines at all.
# Re-pinned again 2026-09-10 (BT.ticket.sdlc-state-status-vocabulary, task 3): the
# renderStateFlipScript doc-comment rewrite (FLIP_REFUSED contract) + the mev-absent fallback's
# refusal rewrite inserted 9 net lines into sdlc-task.js entirely ABOVE this site, shifting it
# 3487->3496. Text unchanged once the flag interpolation is stripped (verified by diffing the old
# line against the new line, byte-identical) -- only the key moved. sdlc-flow.js is untouched by
# this block (out of scope) and needs no re-pick.
FROZEN_BASELINE = {
    str(TASK_JS): {
        3496: '     : `- This run is IN PLACE on main, so emit-state is safe: cd ${runDir} && mev emit-state --write . If \\`mev\\` or brain.toml is absent (standalone repo), skip it silently and set emitStateRan=false; else emitStateRan=true. Do NOT hand-reimplement focus/rollup derivation.`}',
    },
    str(FLOW_JS): {
        3557: "      : `- This run is IN PLACE on branch ${branchName} (in the main repo tree, not an isolated worktree) — emit-state is safe to run right here on the branch, the same way \\`git commit\\` already lands right here: cd ${worktreePath} && mev emit-state --write . If \\`mev\\` or brain.toml is absent (standalone repo), skip it silently and set emitStateRan=false; else emitStateRan=true. Do NOT hand-reimplement focus/rollup derivation. (This is separate from the --auto-merge path's own emit-state call in step 5 below, which re-derives again on ${prBase} after the PR merges — that call is unaffected and still runs unconditionally there.)`}",
        3847: "   mev emit-state --write",
    },
}


def find_sites(path: Path):
    text = path.read_text()
    lines = text.splitlines()
    sites = []
    for regex in (CD_SITE_RE, STANDALONE_SITE_RE):
        for m in regex.finditer(text):
            lineno = text.count("\n", 0, m.start()) + 1
            sites.append((path, lineno, lines[lineno - 1]))
    sites.sort(key=lambda s: s[1])
    return sites


def flag_expr(line: str) -> str | None:
    """The contiguous run of ONE OR MORE `${...}` chunks immediately after `--write`, or None if
    absent. A later flag (e.g. `${renderScopeFlag()}`) is appended immediately after an earlier
    one (`${renderAgentFlag()}`) with no separator, so this must capture the WHOLE run, not just
    the first chunk -- capturing only the first would leave the second uncounted for `missing_agent`
    and unstripped for the baseline comparison, silently breaking the moment a second interpolation
    is added in either order.
    """
    m = re.search(r"--write((?:\$\{[^}]+\})+)", line)
    return m.group(1) if m else None


def strip_flag(line: str, expr: str) -> str:
    return line.replace(expr, "", 1)


def extract_shared_block(name: str) -> str | None:
    if not SHARED_JS.exists():
        return None
    text = SHARED_JS.read_text()
    m = re.search(
        rf"// <<shared:{re.escape(name)}>>\n(.*?)\n// <</shared:{re.escape(name)}>>",
        text,
        re.S,
    )
    return m.group(1) if m else None


# The Workflow runtime the real engines execute in has no `process`, `require`, or filesystem
# access at all (measured 2026-09-07, BT.ticket.engine-helpers-call-require-which-the-workflow-
# runtime-does-not-define) -- the ONLY thing it provides for file/env inspection is `agent()`, a
# call that hands a prompt to a real subagent and gets back a StructuredOutput object. A plain
# `node` subprocess is the exact opposite sandbox: it has `process`/`require`/fs, but no `agent`.
# Evaluating the extracted resolver source unmodified in such a subprocess (the pre-fix version of
# this suite) is precisely how two previous fixes shipped past a green suite while dead in the
# real runtime -- the suite exercised a sandbox the engine never runs in.
#
# The fix here is NOT to write a Python/JS re-implementation of the resolution logic (AC5
# forbids that, for good reason -- a re-implementation can silently drift from what the prompt
# text actually says to run). Instead, `agent()` is stubbed to do exactly what a real subagent is
# instructed to do: extract the ONE fenced ```...``` script from the prompt verbatim and execute
# it for real via `bash -c` -- so the exact probe script the engine ships (TOML parsing, lease
# lookup, env fallback, all of it) is what actually runs, under its real interpreter (python3),
# with only the "a subagent conversation happened" step stubbed out (unavoidable without spawning
# a real Claude session). This exercises both halves of the real path: the async JS wrapper that
# calls `agent()` with this exact prompt shape, and the exact script text that prompt carries.
AGENT_STUB_JS = r"""
global.agent = async function (prompt, opts) {
  const { execSync } = require('child_process')
  const m = prompt.match(/```\n([\s\S]*?)\n```/)
  if (!m) return { value: '' }
  let out
  try {
    out = execSync(m[1], { shell: '/bin/bash' }).toString()
  } catch (e) {
    out = (e.stdout || '').toString()
  }
  const vm = out.match(/^VALUE:(.*)$/m)
  return { value: vm ? vm[1] : '' }
};
"""


def node_eval_resolver(source: str, env_overrides: dict) -> tuple[str | None, str]:
    """Run `source` (must define an async renderAgentFlag() that calls agent(prompt, opts)) in a
    real node subprocess, with `agent()` stubbed per AGENT_STUB_JS above, and call it.

    Returns (result_or_None, stderr_or_diagnostic). Exercises the engine's own async/agent()-based
    path -- never a Python re-implementation of the resolution logic, and never a bare node
    subprocess pretending `process`/`require` are what the real runtime provides.

    Run with `cwd` set to a hermetic scratch directory with no `brain.toml` anywhere in its
    ancestry (never this repo's own cwd) -- see the original note this replaces: the no-identity
    case must not depend on whether this suite happens to run inside a live fleet lease.
    """
    import os

    script = (
        source
        + AGENT_STUB_JS
        + f"\n;(async () => {{ const r = await {RESOLVER_NAME}(); process.stdout.write(JSON.stringify(r)); }})();\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(script)
        tmp_path = f.name
    scratch_dir = tempfile.mkdtemp(prefix="render-agent-flag-eval-")
    try:
        env = dict(os.environ)
        env.pop("FLEET_LANE_AGENT", None)
        env.pop("FLEET_LOCK_DIR", None)
        env.update(env_overrides)
        proc = subprocess.run(
            ["node", tmp_path], capture_output=True, text=True, timeout=15, env=env, cwd=scratch_dir
        )
        if proc.returncode != 0:
            return None, f"node exited {proc.returncode}: {proc.stderr.strip()}"
        try:
            import json as _json

            return _json.loads(proc.stdout), ""
        except Exception as exc:  # pragma: no cover - diagnostic path
            return None, f"could not parse node stdout {proc.stdout!r}: {exc}"
    except FileNotFoundError:
        return None, "node is not installed"
    except subprocess.TimeoutExpired:
        return None, "node eval timed out"
    finally:
        Path(tmp_path).unlink(missing_ok=True)
        try:
            os.rmdir(scratch_dir)
        except OSError:
            pass


def main() -> int:
    failures: list[str] = []

    sites = find_sites(TASK_JS) + find_sites(FLOW_JS)
    print(f"invocation sites discovered: {len(sites)}")
    for path, lineno, line in sites:
        print(f"  - {path.relative_to(REPO_ROOT)}:{lineno}")
    if len(sites) != 3:
        print(
            f"FAIL: expected exactly 3 `mev emit-state --write` invocation sites, found "
            f"{len(sites)}. A site was added or removed -- update this suite's locator regexes "
            f"and FROZEN_BASELINE, do not just change this number.",
            file=sys.stderr,
        )
        return 1

    missing_agent: list[str] = []
    per_site_expr: dict[tuple[str, int], str] = {}
    for path, lineno, line in sites:
        expr = flag_expr(line)
        if expr is None:
            missing_agent.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
        else:
            per_site_expr[(str(path), lineno)] = expr

    if missing_agent:
        failures.append(
            "sites missing an --agent-rendering interpolation right after `--write`: "
            + ", ".join(missing_agent)
            + f" (expected `{FLAG_INTERP}` immediately after `--write` at each site)"
        )

    # Byte-identity: with the interpolation stripped back out, each site must match the frozen
    # pre-change baseline exactly. Only meaningful once all sites carry the interpolation, but we
    # can still check it on any site that already does, so a partial fix gets partial signal.
    for path, lineno, line in sites:
        baseline = FROZEN_BASELINE.get(str(path), {}).get(lineno)
        if baseline is None:
            failures.append(
                f"no frozen baseline recorded for {path.relative_to(REPO_ROOT)}:{lineno} -- "
                "the locator regex matched a line this suite does not have a baseline for"
            )
            continue
        expr = per_site_expr.get((str(path), lineno))
        candidate = strip_flag(line, expr) if expr else line
        if candidate != baseline:
            failures.append(
                f"{path.relative_to(REPO_ROOT)}:{lineno} does not match the frozen no-identity "
                f"baseline once the flag interpolation is stripped.\n"
                f"    baseline: {baseline!r}\n"
                f"    got:      {candidate!r}"
            )

    if missing_agent:
        # The resolver plumbing cannot be evaluated yet if the call sites don't even reference
        # it -- report the RED cleanly instead of piling on cascading resolver failures.
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    # All three sites reference the resolver -- verify it exists, is inlined identically into
    # both engines (build_engines.py parity), and actually behaves per the contract.
    resolver_src = extract_shared_block(RESOLVER_NAME)
    schema_src = extract_shared_block("RENDER_IDENTITY_SCHEMA")
    if resolver_src is None:
        failures.append(
            f"shared.js has no `<<shared:{RESOLVER_NAME}>>` block -- the resolver referenced at "
            "all three sites is not defined anywhere build_engines.py can inline from"
        )
    elif schema_src is None:
        failures.append(
            f"shared.js has no `<<shared:RENDER_IDENTITY_SCHEMA>>` block -- {RESOLVER_NAME}() "
            "references it as an agent() schema and cannot run without it"
        )
    else:
        shared_src = schema_src + "\n" + resolver_src
        for engine_path in (TASK_JS, FLOW_JS):
            engine_text = engine_path.read_text()
            if resolver_src not in engine_text:
                failures.append(
                    f"{engine_path.relative_to(REPO_ROOT)} does not contain the shared "
                    f"`{RESOLVER_NAME}` block byte-for-byte -- run `python3 "
                    "scripts/build_engines.py --write` to re-inline it"
                )
            if schema_src not in engine_text:
                failures.append(
                    f"{engine_path.relative_to(REPO_ROOT)} does not contain the shared "
                    "`RENDER_IDENTITY_SCHEMA` block byte-for-byte -- run `python3 "
                    "scripts/build_engines.py --write` to re-inline it"
                )

        no_identity, diag = node_eval_resolver(shared_src, {})
        if no_identity != "":
            failures.append(
                f"{RESOLVER_NAME}() with no identity resolvable returned {no_identity!r}, "
                f"expected '' (empty string). {diag}"
            )

        with_identity, diag = node_eval_resolver(shared_src, {"FLEET_LANE_AGENT": "test-agent-x"})
        if with_identity != " --agent test-agent-x":
            failures.append(
                f"{RESOLVER_NAME}() with FLEET_LANE_AGENT=test-agent-x returned "
                f"{with_identity!r}, expected ' --agent test-agent-x'. {diag}"
            )

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("OK: all 3 invocation sites pass --agent; no-identity argv is byte-identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
