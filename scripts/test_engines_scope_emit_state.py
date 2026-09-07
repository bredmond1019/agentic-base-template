#!/usr/bin/env python3
"""Source-assertion suite: both SDLC engines must pass --scope to `mev emit-state --write`.

WHY THIS EXISTS
----------------
`mev emit-state` grew a `--scope <REPO>` flag that bounds regeneration to one repo's derived
surfaces (core/mev/src/main.rs, filter_plan_by_scope in src/brain/emit.rs). Neither engine passes
it: every in-place wrap-up/bookkeep rewrites derived surfaces across ALL repos in the corpus from
inside a single lane's run. See planning/blocks/BT.ticket.engines-pass-scope-to-emit-state.json
for the full record. This is the sibling of scripts/test_engines_pass_agent.py (read that file
first — it already contains the locator regexes and the node-subprocess evaluator this suite
reuses) for the `--scope` flag instead of `--agent`.

THE THREE REAL INVOCATION SITES
--------------------------------
`emit-state` appears many times in each engine, but almost all of that is prose: schema
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
  - `.claude/workflows/prompts/shared.js` defines a zero-argument function named
    `renderScopeFlag`, inlined into both engines the usual way via
    `// <<shared:renderScopeFlag>> ... // <</shared:renderScopeFlag>>` (scripts/build_engines.py),
    placed beside the existing `<<shared:renderAgentFlag>>` block.
  - `renderScopeFlag()` returns '' (empty string) when no repo slug resolves, and the literal
    string ' --scope <slug>' (one leading space, no trailing) when one does.
  - Resolution order: the `FLEET_LANE_REPO` environment variable if set and non-empty (mirroring
    renderAgentFlag()'s FLEET_LANE_AGENT branch); else the brain.toml [[repos]] walk-up
    renderAgentFlag() already implements (deepest repo_path that is cwd or an ancestor of it);
    else no identity resolves and '' is returned. Every failure path (no brain.toml, unreadable
    file, no matching repo) falls through to '' inside a try/catch -- this function must never be
    the reason an emit-state call does not run, and 18+ downstream repos run these engines
    standalone with no brain.toml at all.

WHAT THIS SUITE ASSERTS
-------------------------
1. Exactly 3 invocation sites are found (printed before anything else is asserted -- no single
   site is ever judged in isolation).
2. STRUCTURAL PARITY, per file: the count of `mev emit-state --write` invocation sites in that
   file equals the count of `renderScopeFlag()` references in that same file. This is a DERIVED
   equality, never a frozen literal -- a fourth call site added later without the flag fails this
   check, which is the suite's real value.
3. `renderScopeFlag` is defined as a `<<shared:renderScopeFlag>>` block in shared.js AND inlined
   identically (byte-for-byte) into both engine files (build_engines.py inlining parity).
4. The extracted resolver actually behaves per the contract: '' with no repo slug resolvable, and
   ' --scope <slug>' when `FLEET_LANE_REPO=<slug>` is set -- exercised by evaluating the extracted
   source in a real `node` subprocess (never a Python re-implementation standing in for it).

Run today, against the unfixed tree: 3 invocation sites, 0 renderScopeFlag references, exit 1.
This is the intended RED for task 1 of this block; task 2 wires the fix to make it exit 0.

This IS a registered GATING check: `engines-scope-emit-state` in planning/harness.json (task 3
of this block). Registration lives in harness.json, not in this file -- this docstring only
records the fact for a reader of the source.

Usage:
    python3 scripts/test_engines_scope_emit_state.py
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

RESOLVER_NAME = "renderScopeFlag"
FLAG_INTERP = "${await " + RESOLVER_NAME + "()}"

# --- locate the 3 real invocation sites -------------------------------------------------------
# Real invocations look like either:
#   `... && mev emit-state --write . If ...`                 (chained after a `cd`, task/flow)
#   `   mev emit-state --write`                               (standalone, flow's --auto-merge)
# Each may already carry a `${renderAgentFlag()}` interpolation (and, once fixed, a
# `${renderScopeFlag()}` one too) immediately after `--write`. Every OTHER mention of
# "emit-state --write" in these files is prose wrapped in backticks (`` `mev emit-state --write`
# `` in a schema description, comment, or log line) and is excluded by requiring the literal,
# un-backticked shapes below. The interpolation group allows one OR MORE `${...}` chunks in a
# row so this locator still matches once a second flag is appended after the first.

CD_SITE_RE = re.compile(
    r"^(?P<line>.*&&\s*mev emit-state --write(?:\$\{[^}]+\})*\s*\.\s*If\b.*)$", re.M
)
STANDALONE_SITE_RE = re.compile(
    r"^(?P<line>[ \t]*mev emit-state --write(?:\$\{[^}]+\})*[ \t]*)$", re.M
)


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


def count_scope_refs_at_sites(site_lines: list[str]) -> int:
    """How many of the given `mev emit-state --write` invocation-site LINES carry a
    `${renderScopeFlag()}` interpolation.

    Deliberately scoped to just the invocation-site lines, not a whole-file textual tally: as of
    BT.ticket.sdlc-bookkeep-writes-block-status-deterministically, `renderScopeFlag()` also has a
    genuine, unrelated call site inside `renderStateFlipScript` (resolving the `<repo>` half of
    its `mev set-block-status <repo>:<id>` key) plus a prose comment mentioning the function name
    -- neither is an emit-state invocation, and counting them would break site-count parity for a
    reason that has nothing to do with this suite's actual contract (every emit-state --write call
    passes --scope, and only such calls are counted).
    """
    return sum(1 for line in site_lines if FLAG_INTERP in line)


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


# See test_engines_pass_agent.py's identical constant for why `agent()` is stubbed to execute the
# prompt's own fenced script for real (via bash/python3) rather than being reimplemented, and why
# a bare `node` subprocess with unmodified source is the wrong sandbox entirely -- it has
# `process`/`require`, which the real Workflow runtime does NOT have, and lacks `agent()`, which
# is the ONLY thing the real runtime provides for file/env inspection.
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
    """Run `source` (must define an async renderScopeFlag() that calls agent(prompt, opts)) in a
    real node subprocess, with `agent()` stubbed per AGENT_STUB_JS above, and call it.

    Returns (result_or_None, stderr_or_diagnostic). Exercises the engine's own async/agent()-based
    path -- never a Python re-implementation of the resolution logic.

    Run with `cwd` set to a hermetic scratch directory with no `brain.toml` anywhere in its
    ancestry (never this repo's own cwd) -- mirrors test_engines_pass_agent.py's
    node_eval_resolver() reasoning: the no-identity case must not depend on whether this suite
    happens to run inside a real repo with a live fleet lease/registration.
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
    scratch_dir = tempfile.mkdtemp(prefix="render-scope-flag-eval-")
    try:
        env = dict(os.environ)
        env.pop("FLEET_LANE_REPO", None)
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
            f"{len(sites)}. A site was added or removed -- update this suite's locator regexes, "
            "do not just change this number.",
            file=sys.stderr,
        )
        return 1

    # Per-file structural parity: invocation-site count must equal renderScopeFlag() reference
    # count AT THOSE SITES, for each file independently.
    per_file_site_lines: dict[Path, list[str]] = {}
    for path, _lineno, line in sites:
        per_file_site_lines.setdefault(path, []).append(line)

    scope_refs_total = 0
    for path, site_lines in sorted(per_file_site_lines.items(), key=lambda kv: str(kv[0])):
        site_count = len(site_lines)
        ref_count = count_scope_refs_at_sites(site_lines)
        scope_refs_total += ref_count
        print(
            f"{path.relative_to(REPO_ROOT)}: {site_count} invocation site(s), "
            f"{ref_count} {RESOLVER_NAME}() reference(s)"
        )
        if ref_count != site_count:
            failures.append(
                f"{path.relative_to(REPO_ROOT)} has {site_count} `mev emit-state --write` "
                f"invocation site(s) but {ref_count} `{FLAG_INTERP}` reference(s) -- these must "
                "be equal (every invocation site must reference the scope-flag resolver, and "
                "vice versa)"
            )

    print(f"total: {len(sites)} invocation sites, {scope_refs_total} {RESOLVER_NAME}() references")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    # All sites carry the reference count parity -- verify the resolver exists, is inlined
    # identically into both engines (build_engines.py parity), and actually behaves per contract.
    resolver_src = extract_shared_block(RESOLVER_NAME)
    schema_src = extract_shared_block("RENDER_IDENTITY_SCHEMA")
    if resolver_src is None:
        failures.append(
            f"shared.js has no `<<shared:{RESOLVER_NAME}>>` block -- the resolver referenced at "
            "the invocation sites is not defined anywhere build_engines.py can inline from"
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
                f"{RESOLVER_NAME}() with no repo slug resolvable returned {no_identity!r}, "
                f"expected '' (empty string). {diag}"
            )

        with_identity, diag = node_eval_resolver(shared_src, {"FLEET_LANE_REPO": "test-repo-x"})
        if with_identity != " --scope test-repo-x":
            failures.append(
                f"{RESOLVER_NAME}() with FLEET_LANE_REPO=test-repo-x returned "
                f"{with_identity!r}, expected ' --scope test-repo-x'. {diag}"
            )

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print(f"OK: all {len(sites)} invocation sites carry matching {RESOLVER_NAME}() references")
    return 0


if __name__ == "__main__":
    sys.exit(main())
