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
FLAG_INTERP = "${" + RESOLVER_NAME + "()}"

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
FROZEN_BASELINE = {
    str(TASK_JS): {
        3251: '     : `- This run is IN PLACE on main, so emit-state is safe: cd ${runDir} && mev emit-state --write . If \\`mev\\` or brain.toml is absent (standalone repo), skip it silently and set emitStateRan=false; else emitStateRan=true. Do NOT hand-reimplement focus/rollup derivation.`}',
    },
    str(FLOW_JS): {
        3496: "      : `- This run is IN PLACE on branch ${branchName} (in the main repo tree, not an isolated worktree) — emit-state is safe to run right here on the branch, the same way \\`git commit\\` already lands right here: cd ${worktreePath} && mev emit-state --write . If \\`mev\\` or brain.toml is absent (standalone repo), skip it silently and set emitStateRan=false; else emitStateRan=true. Do NOT hand-reimplement focus/rollup derivation. (This is separate from the --auto-merge path's own emit-state call in step 5 below, which re-derives again on ${prBase} after the PR merges — that call is unaffected and still runs unconditionally there.)`}",
        3785: "   mev emit-state --write",
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


def node_eval_resolver(source: str, env_overrides: dict) -> tuple[str | None, str]:
    """Run `source` (must define renderAgentFlag) in a real node subprocess and call it.

    Returns (result_or_None, stderr_or_diagnostic). A real subprocess, not a Python
    re-implementation, so this exercises the actual JS the engines will run.

    Run with `cwd` set to a hermetic scratch directory with no `brain.toml` anywhere in its
    ancestry (never this repo's own cwd). `renderAgentFlag()`'s no-FLEET_LANE_AGENT fallback
    walks up from cwd looking for a lease this caller might already hold -- exactly the
    self-exemption this suite's own repo is running under whenever this suite runs inside a
    live `/sdlc-task` lane (this block's own subject: a lane holding its own exclusive lease).
    Leaving cwd at the real repo root would make the '' (no-identity) assertion depend on
    whether THIS run happens to hold a fleet lease at the moment the suite executes, which is
    not what "no identity available" is supposed to test.
    """
    import os

    script = source + f"\nprocess.stdout.write(JSON.stringify({RESOLVER_NAME}()));\n"
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
    shared_src = extract_shared_block(RESOLVER_NAME)
    if shared_src is None:
        failures.append(
            f"shared.js has no `<<shared:{RESOLVER_NAME}>>` block -- the resolver referenced at "
            "all three sites is not defined anywhere build_engines.py can inline from"
        )
    else:
        for engine_path in (TASK_JS, FLOW_JS):
            engine_text = engine_path.read_text()
            if shared_src not in engine_text:
                failures.append(
                    f"{engine_path.relative_to(REPO_ROOT)} does not contain the shared "
                    f"`{RESOLVER_NAME}` block byte-for-byte -- run `python3 "
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
