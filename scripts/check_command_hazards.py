#!/usr/bin/env python3
"""Flag two authored-command shapes that produce a confident, silent false pass
(BT.ticket.authored-command-hazard-check).

Dependency-free on purpose: `jsonschema` is not installed anywhere in this fleet.

  H1 NEGATED-NON-POSIX: a negated invocation of a tool that is not POSIX-guaranteed
      (`! rg`, `! fd`, `! jq`, `! yq`, `! ag`). A missing tool exits 127; the leading `!`
      inverts that crash into a vacuous pass. Prescribed fix: `test -f <path> &&
      ! grep -q '<pat>' <path>`.

  H2 DISCARDED-UPSTREAM-STATUS: the command's final top-level pipe stage silently
      converts an upstream failure into a pass. Two resolved sub-shapes, chosen to explain
      every instance measured in task 1's corpus sweep without also flagging the two
      measured false positives:
        (a) the final stage is `tail`, `head`, or `cat` -- these near-unconditionally
            exit 0 regardless of what fed them, so whatever real assertion ran earlier in
            the pipe is silently converted to a pass. Flagged regardless of negation.
        (b) the final stage is `grep -q` or `rg -q` AND the whole pipe expression is
            negated with a leading `!` -- negating a match-test built on an upstream
            command conflates "upstream ran fine and found nothing" with "upstream
            crashed", and the negation then reports the crash as CLEARED.
      `set -o pipefail` anywhere in the command defuses both. NOT flagged: an un-negated
      pipe ending in `grep -q`/`rg -q` (upstream failing still yields no match, i.e. still
      fails closed) or a pipe ending in anything else (a count feeding a later comparison,
      not itself a pass/fail gate).

Reads every AUTHORED command string reachable from planning/: block records'
validation_commands[], spec tasks.json validation_commands[], harness.json
validation.checks[].command, and carryover[] typed clears_when.command predicates.

Usage:
    check_command_hazards.py [--planning DIR] [--fleet] [--quiet]

    --planning DIR   scan one repo's planning/ (default: planning)
    --fleet          walk every planning root under the brain root -- vaulted
                     (`_planning/<repo>/`, walked as the physical directory, never through
                     the `planning` symlink) and non-vaulted alike -- mirroring
                     check_lane_records.py's planning_roots_fleet()
    --quiet          print only findings and the summary

Exit code 1 if any hazard or stale allowlist entry is found. A repo with no
planning/blocks/ and no tasks.json (etc.) is silent and exits 0 -- matching
check_block_records.py's behaviour.

ALLOWLIST self-check: every entry must match at least one collected command in the scanned
corpus, or the check fails -- a stale exemption cannot silently widen the gate
(scripts/test_git_env_strip.py's rule).
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

SKIP_DIRS = {"node_modules", ".git", "archive", "target", ".fleet-locks", "sdlc", "trees"}

NON_POSIX_TOOLS = ("rg", "fd", "jq", "yq", "ag")
# Anchored to the START of a top-level clause (see _SPLIT_CLAUSE_RE below), not a bare
# substring search -- `! grep -rq -e '! rg ' <dir>` is grep SEARCHING FOR the literal text
# "! rg ", not an actual negated rg invocation, and a substring match flags it anyway
# (measured false positive: planning/state.json's own
# `authored-checks-use-rg-which-is-not-on-the-engines-path` carryover predicate).
H1_RE = re.compile(r"^!\s*(?:" + "|".join(NON_POSIX_TOOLS) + r")\b")

TAIL_FAMILY = {"tail", "head", "cat"}
MATCH_TOOLS = {"grep", "rg"}

H1_FIX = ("negated invocation of a non-POSIX tool -- a missing tool exits 127 and the "
          "negation inverts that into a vacuous pass. Prescribed fix: "
          "`test -f <path> && ! grep -q '<pat>' <path>`")
H2_FIX = ("the pipe's exit status discards the upstream command's failure. Prescribed "
          "fix: redirect to a file and check $? separately, or `set -o pipefail`")

# Every pattern below must match at least one command actually collected from the corpus,
# or main() fails -- see stale_allowlist_entries(). Comment each entry with why it is safe.
ALLOWLIST = []

_SPLIT_CLAUSE_RE = re.compile(r"\s*(?:\|\||&&|;)\s*")


def _first_word(segment):
    segment = segment.strip()
    if segment.startswith("!"):
        segment = segment[1:].strip()
    parts = segment.split()
    return parts[0] if parts else ""


def _clause_flags(command):
    """Split `command` into top-level &&/||/; clauses and, for each clause with a pipe,
    return (last_stage_cmd, clause_is_negated) tuples. `!` on a clause negates the whole
    pipeline in shell semantics, so only a `!` at the START of the clause counts."""
    out = []
    for clause in _SPLIT_CLAUSE_RE.split(command):
        if "|" not in clause:
            continue
        negated = clause.strip().startswith("!")
        stages = clause.split("|")
        last = stages[-1]
        out.append((_first_word(last), last, negated))
    return out


def detect_hazards(command):
    """Return a list of {"hazard": "H1"|"H2", "fix": str} findings for one command string.
    Empty list means clean."""
    findings = []

    if any(H1_RE.match(clause.strip()) for clause in _SPLIT_CLAUSE_RE.split(command)):
        findings.append({"hazard": "H1", "fix": H1_FIX})

    if "pipefail" not in command:
        for last_cmd, last_stage, negated in _clause_flags(command):
            if last_cmd in TAIL_FAMILY:
                findings.append({"hazard": "H2", "fix": H2_FIX})
                break
            if last_cmd in MATCH_TOOLS:
                last_tokens = last_stage.split()
                is_quiet = "-q" in last_tokens or "--quiet" in last_tokens or any(
                    t.startswith("-") and "q" in t[1:] for t in last_tokens)
                # An inverted match (`-v`) built on top of an upstream command has the same
                # shape as an explicit `!` negation: it reports "upstream produced no
                # matching line", which is indistinguishable from "upstream crashed and
                # produced no output at all" -- e.g. bastion's `engine-serve-token-is-a-
                # cli-arg` (`PlistBuddy ... | grep -qv -- --token`).
                is_inverted = negated or any(
                    t.startswith("-") and "v" in t[1:] for t in last_tokens)
                if is_quiet and is_inverted:
                    findings.append({"hazard": "H2", "fix": H2_FIX})
                    break

    return findings


def _is_allowed(command):
    for entry in ALLOWLIST:
        if re.search(entry["pattern"], command):
            return True
    return False


def stale_allowlist_entries(all_commands):
    """Return the ALLOWLIST pattern strings that match none of `all_commands`."""
    stale = []
    for entry in ALLOWLIST:
        pattern = entry["pattern"]
        if not any(re.search(pattern, cmd) for cmd in all_commands):
            stale.append(pattern)
    return stale


# ---------------------------------------------------------------------------
# Collection: the four authored-string containers.
# ---------------------------------------------------------------------------

def _load_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001 - a malformed file is another check's job to report
        return None


def _collect_block_commands(planning_root):
    out = []
    blocks_dir = os.path.join(planning_root, "blocks")
    if not os.path.isdir(blocks_dir):
        return out
    for name in sorted(os.listdir(blocks_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(blocks_dir, name)
        data = _load_json(path)
        if not isinstance(data, dict):
            continue
        for cmd in data.get("validation_commands") or []:
            if isinstance(cmd, str):
                out.append({"file": path, "container": "block.validation_commands", "command": cmd})
    return out


def _collect_tasks_commands(planning_root):
    out = []
    for dirpath, dirnames, filenames in os.walk(planning_root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and d != "blocks"]
        if "tasks.json" in filenames:
            path = os.path.join(dirpath, "tasks.json")
            data = _load_json(path)
            if not isinstance(data, list):
                continue
            for task in data:
                if not isinstance(task, dict):
                    continue
                for cmd in task.get("validation_commands") or []:
                    if isinstance(cmd, str):
                        out.append({"file": path, "container": "tasks.validation_commands",
                                    "command": cmd})
    return out


def _collect_harness_commands(planning_root):
    out = []
    path = os.path.join(planning_root, "harness.json")
    data = _load_json(path)
    if not isinstance(data, dict):
        return out
    checks = (data.get("validation") or {}).get("checks") or []
    for check_entry in checks:
        if not isinstance(check_entry, dict):
            continue
        cmd = check_entry.get("command")
        if isinstance(cmd, str):
            out.append({"file": path, "container": "harness.check", "command": cmd})
    return out


def _collect_carryover_commands(planning_root):
    out = []
    path = os.path.join(planning_root, "state.json")
    data = _load_json(path)
    if not isinstance(data, dict):
        return out
    for entry in data.get("carryover") or []:
        if not isinstance(entry, dict):
            continue
        clears_when = entry.get("clears_when")
        if isinstance(clears_when, dict):
            cmd = clears_when.get("command")
            if isinstance(cmd, str):
                out.append({"file": path, "container": "carryover.clears_when", "command": cmd})
    return out


def collect_commands(planning_root, fleet=False):
    """Return [{"file", "container", "command"}, ...] for every authored command string
    reachable from `planning_root`. A root with none of the four containers returns []."""
    out = []
    out.extend(_collect_block_commands(planning_root))
    out.extend(_collect_tasks_commands(planning_root))
    out.extend(_collect_harness_commands(planning_root))
    out.extend(_collect_carryover_commands(planning_root))
    return out


def planning_roots_fleet():
    """Best-effort --fleet discovery, mirroring check_lane_records.py's
    planning_roots_fleet(): find every planning/ root under the brain root -- vaulted
    (`_planning/<repo>/`, walked as the physical directory, never through the `planning`
    symlink) and non-vaulted alike."""
    cwd = Path.cwd()
    roots = []
    for dirpath, dirnames, _ in os.walk(cwd, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        p = Path(dirpath)
        if p.parent.name == "_planning":
            roots.append(p)
        elif p.name == "planning" and "_planning" not in p.parts:
            roots.append(p)
    return sorted(set(roots))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--planning", default="planning")
    ap.add_argument("--fleet", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    roots = planning_roots_fleet() if args.fleet else [Path(args.planning)]

    collected = []
    seen_files = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        for item in collect_commands(str(root)):
            key = (item["file"], item["container"], item["command"])
            if key in seen_files:
                continue
            seen_files.add(key)
            collected.append(item)

    if not collected:
        print("no authored command strings found (not a failure)")
        return 0

    all_commands = [c["command"] for c in collected]
    findings_total = 0
    for item in collected:
        if _is_allowed(item["command"]):
            continue
        for finding in detect_hazards(item["command"]):
            findings_total += 1
            print(f"FAIL {item['file']} [{item['container']}] {finding['hazard']}: "
                  f"{item['command']!r}")
            print(f"       fix: {finding['fix']}")

    stale = stale_allowlist_entries(all_commands)
    for pattern in stale:
        findings_total += 1
        print(f"FAIL allowlist entry matches nothing in the corpus: {pattern!r}")

    if not args.quiet and findings_total == 0:
        print(f"ok   {len(collected)} authored command string(s) checked, 0 hazards")

    print(f"\n{len(collected)} authored command string(s) checked, {findings_total} finding(s)")
    return 1 if findings_total else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
