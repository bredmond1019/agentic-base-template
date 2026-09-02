#!/usr/bin/env python3
"""Validate lane records against lane.schema.json (D71).

Dependency-free on purpose, same discipline as check_block_records.py: `jsonschema` is not
installed anywhere in this fleet, so a validator that imports it validates nothing and reports
success. This checks the constraints that actually matter -- required/allowed keys at every
object level, the slug and block-ID grammars, no duplicate block ids, and a budget.heavy
cross-check against fleet_concurrency_check.py -- by hand.

FILE LAYOUT (D71): one record per lane, at <roadmap_dir>/lane-<name>.json. Discovery walks BOTH
the current `planning/roadmaps/<slug>/` layout and the legacy `planning/<slug>/` layout, because
mev's `discover_lane_files` walks both (core/mev/src/brain/lane_segments.rs around line 406) and
27 of the corpus's 63 lane files are in the legacy layout -- a checker scoped to `roadmaps/` only
would silently pass the larger half.

BUDGET CROSS-CHECK: when a record authors `budget.heavy`, this shells out to
`fleet_concurrency_check.py is-heavy --repo-path <ABSOLUTE PATH>` for the lane's top-level `repo`
and fails if the authored value disagrees. The repo slug is resolved to a path via the brain
root's `brain.toml` `[[repos]]` table (slug -> repo_path), found by walking upward from the lane
file. This script checks the resolved path exists BEFORE shelling out, and reports a nonexistent path
as a named ERROR, never silently as `heavy:false`. `is-heavy` itself now distinguishes the third
answer -- it exits 2 with `"heavy": null, "unknown": true` when there is no readable manifest to
classify -- and this script reports that as a WARNING ("could not be cross-checked"), never
silently as agreement with an authored `heavy: false`
(carryover `is-heavy-answers-light-for-a-nonexistent-repo-path`).

Usage:
    check_lane_records.py [--planning DIR] [--fleet] [--quiet]

    --planning DIR   validate one repo's planning/ tree (default: planning)
    --fleet          walk every repo's planning/ tree under the brain root (best-effort,
                     mirrors check_block_records.py's --fleet discovery)
    --quiet          print only failures and the summary

Exit code 1 if any record fails. A corpus with no lane-*.json files is NOT a failure -- that is
the state of every repo today, before HQ.8.A converts the first legacy .txt lane file -- and must
stay silent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
BLOCK_ID_RE = re.compile(r"^[A-Z]{2,3}\.(?:\d+[A-Z]?|ticket|chore)\.[A-Za-z0-9][A-Za-z0-9-]*$")
# held_until (D71, retyped by BT.ticket.lane-schema-has-no-home-for-the-briefing task 1): the
# retired `.txt` `# HELD-UNTIL:` directive carried a block ID or an operator-gate slug, never a
# date -- so this accepts either, matching lane.schema.json's pattern exactly rather than the
# stale DATE_RE this checker used to hold.
HELD_UNTIL_RE = re.compile(
    r"^(operator-[a-z0-9][a-z0-9-]*|[A-Z]{2,3}\.(?:\d+[A-Z]?|ticket|chore)\.[A-Za-z0-9][A-Za-z0-9-]*)$"
)
LANE_FILE_RE = re.compile(r"^lane-.*\.json$")

TOP_LEVEL_REQUIRED = ["lane", "roadmap", "blocks"]
# `repo` is deliberately NOT required at the top level: a lane is not single-repo in this
# corpus, so a lane-level repo is an optional default and never a source of inheritance.
# Every blocks[] entry carries its own required `repo` (BLOCK_ENTRY_REQUIRED below).
# `notes` is lane-level free text ONLY (SPEC/RISK/EXCEPTION/TRAPS-class prose); a per-block
# `note` is deliberately absent from BLOCK_ENTRY_ALLOWED below -- do not add one here either.
TOP_LEVEL_ALLOWED = {
    "lane", "repo", "roadmap", "blocks", "budget", "notes",
    "held_until", "isolation", "exclusive_repos", "spec_source", "cut_blocks",
}
BLOCK_ENTRY_REQUIRED = ["id", "origin_roadmap", "repo"]
BLOCK_ENTRY_ALLOWED = {"id", "origin_roadmap", "repo"}
BUDGET_ALLOWED = {"heavy", "not_with"}

SKIP_DIRS = {"node_modules", ".git", "archive", "target", ".fleet-locks", "sdlc"}

CONCURRENCY_SCRIPT = Path(__file__).resolve().parent / "fleet_concurrency_check.py"


# --- brain.toml / repo-path resolution --------------------------------------------------

def find_brain_root(start) -> Path | None:
    """Walk upward from `start` (a file or directory) looking for brain.toml."""
    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "brain.toml").exists():
            return candidate
    return None


def load_repo_prefixes(brain_root: Path) -> dict:
    """prefix -> repo slug, from brain.toml's [[repos]] table. {} if unreadable.

    A block ID's prefix declares which repo's NAMESPACE the block lives in; the entry's `repo`
    field declares which repo OWNS the work. When they disagree the block is registered into
    another repo's namespace, and nothing else in the fleet catches it: check_block_naming.py
    reads these same prefixes but validates SPEC DIRECTORY NAMES, so a lane entry's `repo` field
    is out of its scope by construction. Measured 2026-09-01 on the context-handling-between-nodes
    run -- `sequence.md` filed the unattended-migration-runner block as `EN.14.H` with repo
    `agentic-portfolio`, reasoning "filed under HQ because the files are HQ's". EN is engine-rs's
    prefix; an agent copying that Wave 0 row registers it into HQ's graph under engine-rs's
    namespace. Measured the same day across 84 live lane records / 962 block entries: zero
    mismatches, so this is a hard ERROR and not a warning -- it fails only on the defect.
    """
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python < 3.11 fallback, not expected in this fleet
        return {}
    try:
        with open(brain_root / "brain.toml", "rb") as fh:
            data = tomllib.load(fh)
    except Exception:                              # noqa: BLE001 - report, never raise
        return {}
    out = {}
    for entry in data.get("repos", []):
        prefix, slug = entry.get("prefix"), entry.get("slug")
        if prefix and slug:
            out[prefix] = slug
    return out


def load_repo_paths(brain_root: Path) -> dict:
    """slug -> absolute repo path, from brain.toml's [[repos]] table. {} if unreadable."""
    toml_path = brain_root / "brain.toml"
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python < 3.11 fallback, not expected in this fleet
        return {}
    try:
        with open(toml_path, "rb") as fh:
            data = tomllib.load(fh)
    except Exception:                              # noqa: BLE001 - report, never raise
        return {}
    out = {}
    for entry in data.get("repos", []):
        slug = entry.get("slug")
        repo_path = entry.get("repo_path")
        if slug and repo_path:
            out[slug] = (brain_root / repo_path).resolve()
    return out


_REPO_PATH_CACHE: dict = {}


def repo_paths_for(start) -> dict:
    """Cached slug->path map for the brain root reached by walking up from `start`."""
    brain_root = find_brain_root(start)
    if brain_root is None:
        return {}
    key = str(brain_root)
    if key not in _REPO_PATH_CACHE:
        _REPO_PATH_CACHE[key] = load_repo_paths(brain_root)
    return _REPO_PATH_CACHE[key]


_REPO_PREFIX_CACHE: dict = {}


def repo_prefixes_for(start) -> dict:
    """Cached prefix->slug map for the brain root reached by walking up from `start`."""
    brain_root = find_brain_root(start)
    if brain_root is None:
        return {}
    key = str(brain_root)
    if key not in _REPO_PREFIX_CACHE:
        _REPO_PREFIX_CACHE[key] = load_repo_prefixes(brain_root)
    return _REPO_PREFIX_CACHE[key]


def cross_check_heavy(lane_repo, authored_heavy: bool, repo_paths: dict):
    """Cross-check an authored `budget.heavy` against fleet_concurrency_check.py.

    Returns `(error, warning)`, either of which may be None:
      - error   -- the authored value DISAGREES with a verdict we actually computed, or the repo
                   cannot be resolved to a real path at all.
      - warning -- the verdict could not be computed (`is-heavy` reports `unknown`: no readable
                   planning/harness.json). That is not the same as disagreeing, and it is not the
                   lane record's fault, so it is surfaced rather than gated on.
    """
    if not isinstance(lane_repo, str) or not lane_repo:
        return ("budget.heavy is authored but lane `repo` is missing/invalid, cannot cross-check",
                None)

    repo_path = repo_paths.get(lane_repo)
    if repo_path is None:
        return (f"budget.heavy cross-check failed: repo `{lane_repo}` is not registered in "
                f"brain.toml's [[repos]] table, cannot resolve a --repo-path", None)
    if not Path(repo_path).is_dir():
        return (f"budget.heavy cross-check failed: resolved repo path for `{lane_repo}` does "
                f"not exist: {repo_path}", None)

    abs_path = str(Path(repo_path).resolve())
    try:
        proc = subprocess.run(
            [sys.executable, str(CONCURRENCY_SCRIPT), "is-heavy", "--repo-path", abs_path],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as exc:                       # noqa: BLE001 - report, never raise
        return (f"budget.heavy cross-check errored shelling out to fleet_concurrency_check.py: "
                f"{exc}", None)

    try:
        result = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return (f"budget.heavy cross-check: could not parse fleet_concurrency_check.py output: "
                f"{proc.stdout!r}", None)

    if result.get("unknown"):
        # is-heavy could not read a manifest at all (exit 2). Unknown is not light -- so this must
        # NOT be compared against the authored value as if it were `heavy: false`. It is also not
        # the lane record's defect, so it warns rather than fails.
        return (None,
                f"budget.heavy={authored_heavy} could not be cross-checked: "
                f"fleet_concurrency_check.py cannot classify repo `{lane_repo}` at {abs_path} "
                f"({result.get('error') or 'no readable planning/harness.json'})")

    actual_heavy = bool(result.get("heavy"))
    if actual_heavy != authored_heavy:
        return (f"budget.heavy={authored_heavy} disagrees with fleet_concurrency_check.py "
                f"is-heavy (heavy={actual_heavy}) for repo `{lane_repo}` at {abs_path}", None)
    return (None, None)


# --- record validation --------------------------------------------------------------------

def check(path, repo_paths: dict | None = None, repo_prefixes: dict | None = None):
    """Return (errors, warnings) for one lane record file."""
    problems = []
    warnings = []
    if repo_prefixes is None:
        repo_prefixes = repo_prefixes_for(path)

    try:
        with open(path) as fh:
            record = json.load(fh)
    except Exception as exc:                       # noqa: BLE001 - report, never raise
        return [f"does not parse: {exc}"], []

    if not isinstance(record, dict):
        return ["top level must be an object"], []

    unknown = sorted(set(record) - TOP_LEVEL_ALLOWED)
    if unknown:
        problems.append(f"unknown top-level key(s): {', '.join(unknown)}")

    for field in TOP_LEVEL_REQUIRED:
        v = record.get(field)
        if v is None or (isinstance(v, (str, list, dict)) and len(v) == 0):
            problems.append(f"required field `{field}` is missing or empty")

    for field in ("lane", "repo", "roadmap"):
        v = record.get(field)
        if isinstance(v, str) and v and not SLUG_RE.match(v):
            problems.append(f"`{field}` value `{v}` does not match slug pattern")

    blocks = record.get("blocks")
    if isinstance(blocks, list):
        if len(blocks) == 0:
            problems.append("blocks[] must have at least one entry")
        seen_ids = set()
        for i, b in enumerate(blocks):
            if not isinstance(b, dict):
                problems.append(f"blocks[{i}] must be an object")
                continue
            unknown_b = sorted(set(b) - BLOCK_ENTRY_ALLOWED)
            if unknown_b:
                problems.append(f"blocks[{i}] unknown key(s): {', '.join(unknown_b)}")
            for field in BLOCK_ENTRY_REQUIRED:
                v = b.get(field)
                if not v:
                    problems.append(f"blocks[{i}] missing required field `{field}`")

            bid = b.get("id")
            if isinstance(bid, str) and bid:
                if not BLOCK_ID_RE.match(bid):
                    problems.append(f"blocks[{i}] id `{bid}` does not match the block ID grammar")
                if bid in seen_ids:
                    problems.append(f"duplicate block id `{bid}` in blocks[]")
                seen_ids.add(bid)

            for field in ("origin_roadmap", "repo"):
                v = b.get(field)
                if isinstance(v, str) and v and not SLUG_RE.match(v):
                    problems.append(f"blocks[{i}].{field} value `{v}` does not match slug pattern")

            # The block ID's prefix must name the same repo as the entry's `repo` field.
            brepo = b.get("repo")
            if isinstance(bid, str) and bid and isinstance(brepo, str) and brepo and repo_prefixes:
                pfx = bid.split(".")[0]
                owner = repo_prefixes.get(pfx)
                if owner and owner != brepo:
                    problems.append(
                        f"blocks[{i}] PREFIX/REPO MISMATCH: id `{bid}` uses {owner}'s prefix "
                        f"`{pfx}` but repo is `{brepo}` — registering this row files the block "
                        f"into {owner}'s namespace. Renumber it under `{brepo}`'s own prefix, or "
                        f"correct `repo` to `{owner}`")
    elif blocks is not None:
        problems.append("blocks must be an array")

    budget = record.get("budget")
    if budget is not None:
        if not isinstance(budget, dict):
            problems.append("budget must be an object")
        else:
            unknown_bud = sorted(set(budget) - BUDGET_ALLOWED)
            if unknown_bud:
                problems.append(f"budget unknown key(s): {', '.join(unknown_bud)}")

            heavy = budget.get("heavy")
            if heavy is not None:
                if not isinstance(heavy, bool):
                    problems.append("budget.heavy must be a boolean")
                else:
                    err, warn = cross_check_heavy(record.get("repo"), heavy, repo_paths or {})
                    if err:
                        problems.append(err)
                    if warn:
                        warnings.append(warn)

            not_with = budget.get("not_with")
            if not_with is not None and not isinstance(not_with, list):
                problems.append("budget.not_with must be an array")

    v = record.get("held_until")
    if v is not None and not HELD_UNTIL_RE.match(str(v)):
        problems.append(f"held_until `{v}` is not a block ID or an operator-gate slug")

    for field in ("isolation", "spec_source", "notes"):
        v = record.get(field)
        if v is not None and not (isinstance(v, str) and v):
            problems.append(f"`{field}` must be a non-empty string")

    for field in ("exclusive_repos", "cut_blocks"):
        v = record.get(field)
        if v is not None and not isinstance(v, list):
            problems.append(f"`{field}` must be an array")

    return problems, warnings


# --- discovery ----------------------------------------------------------------------------

def discover_lane_files(root) -> list:
    """Recursively find every lane-*.json file in a ROADMAP DIRECTORY under `root` -- covers both
    the current planning/roadmaps/<slug>/ layout and the legacy planning/<slug>/ layout.

    A lane record is identified by name AND by living in a subdirectory of the planning root, never
    directly in it. That second half is load-bearing, not tidiness: `mev emit-state --write` emits
    three DERIVED artifacts straight into the brain root's `planning/` whose names match this
    module's `lane-*.json` glob exactly --

        planning/lane-segments.json      (mev, lane_segments.rs)
        planning/lane-availability.json  (mev, main.rs -- "never writes ... that is `mev emit-state`")
        planning/lane-frontier.json      (mev, frontier.rs LANE_FRONTIER_ARTIFACT)

    -- and they are not lane records: they carry `derived_at`/`segments`/`entries`/`gate_ranks` and
    no `lane`/`roadmap`/`blocks`. Name-only discovery therefore made this checker exit 1 over a
    corpus with ZERO authored lane records, which would red-gate the brain root the moment HQ.8.A
    registered it as a gated check -- and via the push gate, every concurrent lane with it.
    Measured at HQ 832b6747: 3 FAILs, all three of them mev's derived artifacts.

    The rule is structural rather than a list of three basenames on purpose: mev is free to emit a
    fourth derived `lane-*.json` and it will land in the same place, where this still excludes it.
    Every real lane record -- both layouts, all 70 of the .txt files HQ.8.A converts -- lives one or
    more levels down, so none is lost.
    """
    root = Path(root)
    found = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if Path(dirpath) == root:
            # The planning root itself holds mev's derived artifacts, never a lane record.
            continue
        for name in filenames:
            if LANE_FILE_RE.match(name):
                found.append(Path(dirpath) / name)
    return sorted(set(found))


def planning_roots_fleet() -> list:
    """Best-effort --fleet discovery, mirroring check_block_records.py's blocks_dirs(): find
    every planning/ root under the brain root -- vaulted (`_planning/<repo>/`, walked as the
    physical directory, never through the `planning` symlink) and non-vaulted alike."""
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--planning", default="planning")
    ap.add_argument("--fleet", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    roots = planning_roots_fleet() if args.fleet else [Path(args.planning)]

    total = failed = 0
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        for lane_path in discover_lane_files(root):
            rp = lane_path.resolve()
            if rp in seen:
                continue
            seen.add(rp)

            total += 1
            repo_paths = repo_paths_for(lane_path)
            problems, warnings = check(lane_path, repo_paths)
            if problems:
                failed += 1
                print(f"FAIL {lane_path}")
                for p in problems:
                    print(f"       {p}")
            elif not args.quiet:
                print(f"ok   {lane_path}")
            for w in warnings:
                if problems or not args.quiet:
                    print(f"       (warn) {w}")

    if total == 0:
        print("no lane records found (not a failure)")
        return 0
    print(f"\n{total} record(s) checked, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
