#!/usr/bin/env python3
"""Roadmap-scoped discovery for `/roadmap-status --roadmap <slug>`.

WHY THIS EXISTS
----------------
A roadmap runs as several concurrent lanes, one per repo, each in its own agent session. The
live state is already on disk, but scattered across four artifact families that nothing joins:

  1. the roadmap's `lane-log.jsonl` (roadmap-addressed)
  2. `planning/orchestration-run/<roadmap>/{notes.md,review.md}` (repo x roadmap-addressed, D57)
  3. `planning/<spec>/sdlc/sdlc-*state.json` (spec-slug-addressed)
  4. `planning/state.json` per repo (repo-addressed: depends_on operator/approval edges, carryover)

This module joins all four for ONE roadmap slug and emits structured data. It renders nothing --
`.claude/commands/roadmap-status.md` owns interpretation and output shape. It implements no
ranking, dedup-by-similarity, or staleness SCORING of its own beyond the liveness-from-updated_at
rule the ticket requires; `mev` owns derivation, this is a fourth (after `/consolidate-run`) plain
projector. It writes nothing, ever -- no state file, no lock, no cache.

MEASURED FACTS THIS IMPLEMENTATION IS BUILT AROUND (ticket `ticket-roadmap-status-command`)
---------------------------------------------------------------------------------------------
- Realpath dedup: measured 2026-08-12 from the brain root, `rg -L -uu --files` discovery for
  run-state-shaped files returns roughly 2x raw hits vs. realpath-distinct files, because every
  `planning/` is a symlink into the vault, including inside worktrees (`trees/`). Never dedup by
  path string.
- Status vocabulary has seven observed values across the corpus (`done`, absent, `blocked`,
  `docs`, `running`, `passed`, `completed`). Liveness must come from `updated_at` age against a
  named threshold, never from `status` alone -- a killed run leaves `running` behind forever.
- Operator/approval edges are mid-rename from an older slug convention to `operator-<slug>` slugs;
  match on the edge `type` field only, never a slug prefix.

TWO MODES
---------
`--self-test`               -- synthetic fixtures under a temp dir; no dependency on the real
                                corpus or a `brain.toml`.
`--roadmap <slug> [--root]` -- real discovery. Resolves `BRAIN_ROOT` by walking up from cwd for
                                `brain.toml` unless `--root` is given, then joins the four artifact
                                families for that roadmap and prints the result as JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

# Liveness threshold: an `updated_at` older than this many hours is reported STALE regardless of
# what `status` says. Named and centralized here (not scattered as a magic number) so the command
# layer and any future tuning read one constant. 6 hours covers a normal single-run lane with
# margin; a lane genuinely alive past that has usually written a fresher state file anyway.
STALE_THRESHOLD_HOURS = 6

# Edge types this module treats as "needs the operator". Matched on this field only -- never on a
# slug prefix -- because the fleet is mid-rename from an older slug convention to `operator-<slug>`
# and a prefix match would silently miss half the population depending on how far the rename has
# reached.
OPERATOR_EDGE_TYPES = ("operator", "approval")

KNOWN_STATUS_VALUES = {"done", "blocked", "docs", "running", "passed", "completed"}

# BT.6.A/B shared advisory lock directory layout (leases, lane-agent registry, message queues) --
# same subdirectory names check_lane_agents.py and check_messages.py already use, cited here
# rather than reinvented so a rename in either place is a single-file change, not three.
LOCK_SUBDIR = ".fleet-locks"
REGISTRY_SUBDIR = "lane-agents"
LEASE_SUBDIR = "leases"
QUEUE_SUBDIR = "queue"


def _import_check_lane_agents():
    """Import check_lane_agents.py from this same scripts/ directory.

    Load-bearing, same discipline as fleet_concurrency_check.py's helper of the same name: this
    module is a READER of BT.6.A's shapes (lease.schema.json / lane-agent.schema.json), never a
    second implementation. Reusing `lease_liveness_timestamp`, `staleness_seconds` and
    `STALE_THRESHOLD_SECONDS` from check_lane_agents.py is how "project state, don't re-implement
    validation" (this module's own docstring) is actually satisfied rather than merely claimed --
    check_lane_agents.py owns the staleness rule and the duplicate-exclusive-lease check; this
    module only reports what is currently on disk. A plain `import check_lane_agents` is not
    reliable when this file is loaded by path (e.g. via `importlib.util.spec_from_file_location`)
    rather than run as `python3 roadmap_status_discovery.py`, so the import locates its sibling by
    this file's own path instead of trusting the caller's sys.path state.
    """
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import check_lane_agents  # noqa: E402 - deliberate late/local import, see docstring above

    return check_lane_agents


_LANE_AGENTS = _import_check_lane_agents()

# Dated snapshot for the realpath-dedup relation (never a hard constant -- the fleet moves under
# concurrent lanes and any fixed pair would go stale the moment a new spec runs). The self-test's
# live-measurement case re-runs this exact command against the real corpus at test time and asserts
# the RELATION (raw > distinct, every /trees/-routed hit collapses onto a non-trees/ realpath), not
# these numbers -- they are recorded here only as the ticket's own dated provenance.
MEASURING_COMMAND = "rg -L -uu --files -g '**/sdlc/sdlc-*state.json'"
MEASURED_DATE = "2026-08-12"
MEASURED_RAW = 861
MEASURED_DISTINCT = 438


# ---------------------------------------------------------------------------
# Brain root + generic sweep/dedup plumbing (mirrors scripts/test_consolidator_discovery.py's
# proven approach: prefer a real `rg` invocation captured directly via subprocess.run, never
# through a pipe -- a piped command's $? is the pipe's, not rg's -- with a pure-Python os.walk
# fallback for sandboxes with no `rg` binary on PATH).
# ---------------------------------------------------------------------------


def find_brain_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk upward from `start` (default: cwd) looking for a directory containing brain.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "brain.toml").exists():
            return candidate
    return None


def _gitignored_prefixes(root: Path) -> list[Path]:
    """Pure-Python `-uu`-equivalent bookkeeping for the os.walk fallback sweep."""
    prefixes: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=True):
        if ".gitignore" not in filenames:
            continue
        gi = Path(dirpath) / ".gitignore"
        try:
            text = gi.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            prefixes.append((Path(dirpath) / line.strip("/")).resolve())
    return prefixes


def _sweep_with_rg(root: Path, glob: str, follow_symlinks: bool, hidden: bool) -> Optional[list[str]]:
    """Try a real `rg --files -g <glob>` sweep; None if no `rg` binary is on PATH."""
    rg_bin = shutil.which("rg")
    if rg_bin is None:
        return None
    args = [rg_bin]
    if follow_symlinks:
        args.append("-L")
    if hidden:
        args.append("-uu")
    args += ["--files", "-g", glob]
    result = subprocess.run(args, cwd=root, capture_output=True, text=True)
    # rg exits 1 when it finds nothing, 0 when it finds matches, >1 on a real error.
    if result.returncode not in (0, 1):
        raise RuntimeError(f"rg discovery failed (exit {result.returncode}): {result.stderr}")
    return [line for line in result.stdout.splitlines() if line.strip()]


# Directories the fallback walk never needs to descend into. None of them can contain a
# planning/<slug>/sdlc/ run-state file or a planning/state.json, so pruning them changes no
# result -- it only removes the build/VCS trees that dominate an unpruned walk of the fleet.
_WALK_PRUNE_DIRS = frozenset({
    ".git", "node_modules", "target", ".venv", "venv", "__pycache__",
    ".next", "dist", "build", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".cargo", ".rustup", "site-packages",
})


def _sweep_with_walk(root: Path, glob_suffix_parts: tuple[str, ...], follow_symlinks: bool, hidden: bool) -> list[str]:
    """Pure-Python fallback sweep. `glob_suffix_parts` is a tuple of path-component substrings that
    must all appear, in order, somewhere in the relative path (a minimal glob stand-in sufficient
    for this module's fixed patterns)."""
    ignored = [] if hidden else _gitignored_prefixes(root)
    found: list[str] = []
    root_str = str(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        # Prune directories that structurally cannot hold this module's targets (run-state files
        # under a planning/<slug>/sdlc/ path, or planning/state.json). This is the difference
        # between a usable check and one that SIGKILLs its caller: with rg unavailable as a real
        # binary -- which is the norm inside the agent sandbox, where `rg` is only a zsh function
        # `subprocess.run` cannot invoke -- this walk is the ONLY code path, and unpruned it spent
        # 195s per call, reliably bailing unrelated /sdlc-task and /sdlc-flow runs on 2026-08-19.
        # `trees/` is deliberately NOT pruned: case_live_measured_snapshot asserts precisely that
        # trees/-routed hits collapse onto non-trees/ realpaths, so pruning it would gut the test.
        dirnames[:] = [d for d in dirnames if d not in _WALK_PRUNE_DIRS]
        if not hidden:
            dp = Path(dirpath).resolve()
            if any(dp == p or p in dp.parents for p in ignored):
                dirnames[:] = []
                continue
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), root_str)
            if all(part in rel for part in glob_suffix_parts):
                found.append(rel)
    return found


def sweep(root: Path, glob: str, glob_suffix_parts: tuple[str, ...], follow_symlinks: bool = True, hidden: bool = True) -> list[str]:
    """Raw sweep hits (relative path strings, NOT deduped) for `glob`.

    Prefers a real `rg -L -uu --files -g <glob>` invocation; falls back to a pure-Python walk when
    no `rg` binary is on PATH (a sandboxed shell where `rg` is only a shell function, not an
    executable `subprocess.run` can invoke).
    """
    hits = _sweep_with_rg(root, glob, follow_symlinks, hidden)
    if hits is not None:
        return hits
    return _sweep_with_walk(root, glob_suffix_parts, follow_symlinks, hidden)


def realpath_dedup(root: Path, hits: list[str]) -> list[Path]:
    """Dedup raw hits by `os.path.realpath`, returning the sorted distinct realpaths. Because every
    `planning/` symlink -- including a worktree's -- canonicalizes onto the same vault file, this
    naturally retains the vault original: a `trees/` alias's realpath IS the vault path.

    Parent directories are resolved once and cached, because the thing that is symlinked here is
    always a DIRECTORY (`planning/`), never the state file itself. Resolving per-file instead made
    this the single slowest thing in the harness: 1749 hits x a full symlink-chain walk each
    measured 194s of the self-test's 195s, which reliably SIGKILLed the /sdlc-task and /sdlc-flow
    test stages and bailed two unrelated blocks on 2026-08-19 before the cause was found. A file
    that is ITSELF a symlink still gets a full realpath, so the result is unchanged in every case."""
    parent_cache: dict[str, str] = {}
    out = set()
    for h in hits:
        p = root / h
        parent = str(p.parent)
        resolved_parent = parent_cache.get(parent)
        if resolved_parent is None:
            resolved_parent = os.path.realpath(parent)
            parent_cache[parent] = resolved_parent
        candidate = os.path.join(resolved_parent, p.name)
        # The parent is canonical now, so only a symlinked LEAF can still need resolving.
        if os.path.islink(candidate):
            candidate = os.path.realpath(candidate)
        out.add(Path(candidate))
    return sorted(out)


# ---------------------------------------------------------------------------
# 1. Roadmap directory resolution -- cites /begin-orchestration Step 1C rather than restating it
#    with independent logic that could drift.
# ---------------------------------------------------------------------------


class AmbiguousRoadmapError(RuntimeError):
    pass


def resolve_roadmap_dir(root: Path, slug: str) -> Path:
    """Resolve a roadmap slug to its directory per /begin-orchestration Step 1C's fixed order:
    1. planning/roadmaps/<slug>/ if it exists
    2. otherwise legacy planning/<slug>/ if it exists
    3. present in BOTH -> AmbiguousRoadmapError (never a silent preference)
    """
    new_dir = root / "planning" / "roadmaps" / slug
    legacy_dir = root / "planning" / slug
    new_exists = new_dir.is_dir()
    legacy_exists = legacy_dir.is_dir()
    if new_exists and legacy_exists:
        raise AmbiguousRoadmapError(
            f"roadmap slug '{slug}' exists in both {new_dir} and {legacy_dir} -- ambiguous, not resolving"
        )
    if new_exists:
        return new_dir
    if legacy_exists:
        return legacy_dir
    raise FileNotFoundError(f"no roadmap directory found for slug '{slug}' at {new_dir} or {legacy_dir}")


def list_candidate_roadmaps(root: Path) -> list[dict[str, Any]]:
    """When --roadmap is omitted: list candidate roadmap slugs with last-activity, never guess."""
    candidates: dict[str, Path] = {}
    roadmaps_dir = root / "planning" / "roadmaps"
    if roadmaps_dir.is_dir():
        for child in sorted(roadmaps_dir.iterdir()):
            if child.is_dir():
                candidates[child.name] = child
    legacy_dir = root / "planning"
    if legacy_dir.is_dir():
        for child in sorted(legacy_dir.iterdir()):
            if child.is_dir() and child.name not in candidates and (child / "roadmap.md").exists():
                candidates[child.name] = child
    out = []
    for slug, path in sorted(candidates.items()):
        log = path / "lane-log.jsonl"
        last_activity = None
        if log.exists():
            try:
                mtime = log.stat().st_mtime
                last_activity = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            except OSError:
                pass
        out.append({"slug": slug, "path": str(path), "last_activity": last_activity})
    return out


# ---------------------------------------------------------------------------
# 2. lane-log.jsonl -- already roadmap-addressed.
# ---------------------------------------------------------------------------


def read_lane_log(roadmap_dir: Path) -> list[dict[str, Any]]:
    """Read <roadmap_dir>/lane-log.jsonl. Tolerant of malformed lines (skipped, never crash)."""
    log_path = roadmap_dir / "lane-log.jsonl"
    if not log_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def repos_from_lane_log(entries: list[dict[str, Any]]) -> list[str]:
    """Distinct repo slugs named by lane-log entries, order-preserving first-seen."""
    seen: list[str] = []
    for e in entries:
        repo = e.get("repo")
        if repo and repo not in seen:
            seen.append(repo)
    return seen


# ---------------------------------------------------------------------------
# 3. Block ID -> spec slug, per /orchestrate step 3's existing convention (cited, not
#    reinvented). `XX.<phase>.<letter>` master-plan blocks cannot be resolved generically without
#    reading that repo's master-plan.md, so this returns None for that shape rather than guessing
#    -- an unresolved slug is reported as such, never silently wrong.
# ---------------------------------------------------------------------------

_TICKET_RE = re.compile(r"^[A-Za-z]{1,4}\.ticket\.(?P<slug>[a-z0-9][a-z0-9-]*)$")
_CHORE_RE = re.compile(r"^[A-Za-z]{1,4}\.chore\.(?P<slug>[a-z0-9][a-z0-9-]*)$")
_PHASE_LETTER_RE = re.compile(r"^[A-Za-z]{1,4}\.\d+\.[A-Za-z]$")


def resolve_block_to_spec_slug(block_id: str) -> Optional[str]:
    """`XX.ticket.<slug>` -> `ticket-<slug>`; `XX.chore.<slug>` -> `chore-<slug>`;
    `XX.<phase>.<letter>` -> unresolved (None) -- that shape needs the repo's own master-plan.md,
    which this function does not have access to; the caller reports it as unresolved rather than
    fabricating a slug."""
    m = _TICKET_RE.match(block_id)
    if m:
        return f"ticket-{m.group('slug')}"
    m = _CHORE_RE.match(block_id)
    if m:
        return f"chore-{m.group('slug')}"
    if _PHASE_LETTER_RE.match(block_id):
        return None
    return None


# ---------------------------------------------------------------------------
# 4. Run records: planning/orchestration-run/<roadmap>/{notes.md,review.md} per repo (D57,
#    repo x roadmap addressed). Discovered fleet-wide via realpath-deduped sweep, same discipline
#    as /consolidate-run.
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_OPEN_ROW_RE = re.compile(r"\*\*OPEN\*\*", re.IGNORECASE)
_HELD_ROW_RE = re.compile(r"\*\*HELD\*\*", re.IGNORECASE)


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip().strip('"')
    return out


def discover_run_records(root: Path, roadmap_slug: str) -> dict[str, dict[str, Any]]:
    """Sweep for planning/orchestration-run/<roadmap_slug>/{notes.md,review.md}, realpath-deduped,
    grouped by owning repo. Returns {repo_dirname: {"notes": {...}|None, "review": {...}|None}}.
    Repo attribution uses the path segment immediately before /planning/, which is the repo's own
    directory name on disk -- adequate for grouping; it does not need to match a state.json 'repo'
    field exactly, since discover_repos() below does that join for the operator-edge section."""
    glob = f"**/orchestration-run/{roadmap_slug}/*.md"
    raw = sweep(root, glob, ("orchestration-run", roadmap_slug), follow_symlinks=True, hidden=True)
    distinct = realpath_dedup(root, raw)

    by_repo: dict[str, dict[str, Any]] = {}
    for path in distinct:
        parts = path.parts
        try:
            planning_idx = parts.index("planning")
        except ValueError:
            planning_idx = None
        repo_name = parts[planning_idx - 1] if planning_idx is not None and planning_idx > 0 else path.parent.parent.parent.name
        entry = by_repo.setdefault(repo_name, {"notes": None, "review": None})
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        record = {
            "path": str(path),
            "lifecycle": fm.get("lifecycle", "<absent>"),
            "run_started": fm.get("run_started", "<absent>"),
            "run_ended": fm.get("run_ended", "<absent>"),
            "open_count": len(_OPEN_ROW_RE.findall(text)),
            "held_count": len(_HELD_ROW_RE.findall(text)),
        }
        if path.name == "notes.md":
            entry["notes"] = record
        elif path.name == "review.md":
            entry["review"] = record
    return by_repo


# ---------------------------------------------------------------------------
# 5. planning/<spec>/sdlc/sdlc-*state.json -- spec-slug-addressed. Liveness from updated_at, never
#    status alone. Unknown status values pass through verbatim; absent fields tolerated.
# ---------------------------------------------------------------------------


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # Accept trailing 'Z' as UTC.
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def compute_liveness(status: Any, updated_at: Any, now: Optional[datetime] = None) -> dict[str, Any]:
    """Liveness is computed from `updated_at` age against STALE_THRESHOLD_HOURS -- `status` is a
    hint only, never the source of truth (a killed session leaves `status: running` forever)."""
    now = now or datetime.now(timezone.utc)
    dt = _parse_iso(updated_at) if isinstance(updated_at, str) else None
    if dt is None:
        return {"liveness": "unknown", "age_hours": None}
    age_hours = (now - dt).total_seconds() / 3600.0
    liveness = "live" if age_hours <= STALE_THRESHOLD_HOURS else "stale"
    return {"liveness": liveness, "age_hours": round(age_hours, 2)}


def read_sdlc_state(spec_dir: Path) -> Optional[dict[str, Any]]:
    """Find planning/<spec>/sdlc/sdlc-*state.json (first match; there is normally exactly one
    engine's state file per spec directory) and return its normalized fields, tolerant of absent
    keys. Unknown `status` values pass through verbatim -- never silently bucketed."""
    sdlc_dir = spec_dir / "sdlc"
    if not sdlc_dir.is_dir():
        return None
    candidates = sorted(sdlc_dir.glob("sdlc-*state.json"))
    if not candidates:
        return None
    path = candidates[0]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"path": str(path), "status": "<unreadable>", "updated_at": None,
                 "current_task": None, "tasks_run": [], "liveness": "unknown", "age_hours": None}
    status = data.get("status", "<absent>")
    updated_at = data.get("updated_at")
    liveness = compute_liveness(status, updated_at)
    return {
        "path": str(path),
        "status": status,
        "status_known": status in KNOWN_STATUS_VALUES,
        "updated_at": updated_at,
        "current_task": data.get("current_task"),
        "tasks_run": data.get("tasks_run", []),
        **liveness,
    }


# ---------------------------------------------------------------------------
# 6. planning/state.json per repo -- authored block status, depends_on operator/approval edges,
#    carryover[]. Repo discovery via realpath-deduped sweep for state.json, matched to lane-log
#    repo slugs via the file's own "repo" field (never by directory name, which can differ).
# ---------------------------------------------------------------------------


def discover_repos(root: Path) -> dict[str, Path]:
    """Sweep for planning/state.json fleet-wide, realpath-deduped, keyed by each file's own
    top-level "repo" field (the authoritative slug -- never the directory name, which can differ)."""
    raw = sweep(root, "**/planning/state.json", ("planning", "state.json"), follow_symlinks=True, hidden=True)
    distinct = realpath_dedup(root, raw)
    repos: dict[str, Path] = {}
    for path in distinct:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        slug = data.get("repo")
        if slug:
            repos[slug] = path
    return repos


def _iter_edges(node: Any):
    """Yield every dict found anywhere in a state.json tree that looks like a depends_on edge
    (i.e. carries a "type" key) -- walks depends_on lists and blocked_by lists alike, since both
    carry the same edge shape in this schema."""
    if isinstance(node, dict):
        if "type" in node and isinstance(node.get("type"), str):
            yield node
        for v in node.values():
            yield from _iter_edges(v)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_edges(item)


def discover_operator_gates(state_json_path: Path) -> dict[str, Any]:
    """Find every depends_on/blocked_by edge whose type is 'operator' or 'approval' -- matched on
    TYPE only, never a slug prefix, so the in-flight rename to the `operator-<slug>` convention
    does not hide half the population. Returns the edges found plus a coverage count."""
    try:
        data = json.loads(state_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"gates": [], "coverage_count": 0}
    gates = []
    seen_slugs: set[str] = set()
    for edge in _iter_edges(data):
        if edge.get("type") in OPERATOR_EDGE_TYPES:
            slug = edge.get("slug", "<unnamed>")
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            gates.append({
                "type": edge.get("type"),
                "slug": slug,
                "exit": edge.get("exit"),
                "start": edge.get("start"),
                "what": edge.get("what"),
            })
    return {"gates": gates, "coverage_count": len(gates)}


def discover_carryover(state_json_path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(state_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("carryover", [])
    return items if isinstance(items, list) else []


# ---------------------------------------------------------------------------
# 7. Leases + lane-agent registry (BT.6.A), under the shared advisory lock directory. This module
#    PROJECTS current state only -- check_lane_agents.py owns validation (schema conformance,
#    duplicate-exclusive-lease detection); reusing its staleness helpers and
#    STALE_THRESHOLD_SECONDS constant here (imported, not copied) means the two can never quietly
#    disagree about what counts as stale.
# ---------------------------------------------------------------------------


def resolve_lock_dir(root: Path) -> Path:
    """Shared advisory lock directory for one already-resolved brain `root`. Mirrors
    check_lane_agents.py's resolve_lock_dir() precedence (FLEET_LOCK_DIR env override, else
    <brain_root>/.fleet-locks) minus its walk-up-from-cwd step, which is unnecessary here --
    `root` passed to discover() IS the resolved brain root already."""
    override = os.environ.get("FLEET_LOCK_DIR")
    if override:
        return Path(override)
    return root / LOCK_SUBDIR


def lane_names_by_repo(entries: list[dict[str, Any]]) -> dict[str, str]:
    """First-seen lane name per repo from lane-log entries. Needed because both the message
    queue (`queue/<repo>/<lane>/`) and the lane-agent registry are lane-addressed, not merely
    repo-addressed, and lane-log.jsonl is the only one of the four already-joined artifact
    families that carries the lane name at all."""
    out: dict[str, str] = {}
    for e in entries:
        repo = e.get("repo")
        lane = e.get("lane")
        if repo and lane and repo not in out:
            out[repo] = lane
    return out


def discover_lane_registry(lock_dir: Path, roadmap_slug: str, now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Project every lane-agent registry claim under <lock_dir>/lane-agents/agent-*.json whose
    own `roadmap` field matches this roadmap -- registry.schema.json carries a `roadmap` field, so
    (unlike leases) claims can be scoped without relying on the repo-membership fallback. Heartbeat
    age comes from check_lane_agents.py's own `staleness_seconds`/`STALE_THRESHOLD_SECONDS` --
    liveness is judged on that age, never on an authored status field, same rule
    `compute_liveness()` above applies to sdlc state. A record that fails to parse is reported with
    an explicit error, never silently dropped."""
    registry_dir = lock_dir / REGISTRY_SUBDIR
    out: list[dict[str, Any]] = []
    if not registry_dir.is_dir():
        return out
    for path in sorted(registry_dir.glob("agent-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            out.append({"path": str(path), "error": f"does not parse: {exc}"})
            continue
        if data.get("roadmap") != roadmap_slug:
            continue
        heartbeat = data.get("heartbeat")
        age = _LANE_AGENTS.staleness_seconds(heartbeat, now) if heartbeat else None
        out.append({
            "path": str(path),
            "agent_name": data.get("agent_name"),
            "repo": data.get("repo"),
            "lane": data.get("lane"),
            "roadmap": data.get("roadmap"),
            "started_at": data.get("started_at"),
            "heartbeat": heartbeat,
            "heartbeat_age_seconds": round(age, 1) if age is not None else None,
            "stale": age is not None and age > _LANE_AGENTS.STALE_THRESHOLD_SECONDS,
            "current_block": data.get("current_block"),
        })
    return out


def discover_leases(lock_dir: Path, repos: set[str], now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Project every lease under <lock_dir>/leases/lease-*.json scoped to `repos` (the repos this
    roadmap touches) -- lease.schema.json carries no `roadmap` field, so repo membership is the
    only filter available, unlike the registry join above. Heartbeat age is via
    `lease_liveness_timestamp()`'s heartbeat-else-acquired_at fallback, imported from
    check_lane_agents.py so the two modules can never disagree about which timestamp a lease's
    liveness is judged on. `kind` (exclusive/shared) and `holder` are reported verbatim -- this
    module does not flag a duplicate exclusive lease; that verdict stays check_lane_agents.py's."""
    lease_dir = lock_dir / LEASE_SUBDIR
    out: list[dict[str, Any]] = []
    if not lease_dir.is_dir():
        return out
    for path in sorted(lease_dir.glob("lease-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            out.append({"path": str(path), "error": f"does not parse: {exc}"})
            continue
        if data.get("repo") not in repos:
            continue
        liveness_ts = _LANE_AGENTS.lease_liveness_timestamp(data)
        age = _LANE_AGENTS.staleness_seconds(liveness_ts, now) if liveness_ts else None
        out.append({
            "path": str(path),
            "repo": data.get("repo"),
            "lane": data.get("lane"),
            "holder": data.get("agent"),
            "kind": data.get("kind"),
            "scope": data.get("scope"),
            "acquired_at": data.get("acquired_at"),
            "heartbeat": data.get("heartbeat"),
            "heartbeat_age_seconds": round(age, 1) if age is not None else None,
            "stale": age is not None and age > _LANE_AGENTS.STALE_THRESHOLD_SECONDS,
        })
    return out


# ---------------------------------------------------------------------------
# 8. Message queue depth (BT.6.B), `<lock_dir>/queue/<repo>/<lane>/{inbox,processing,done}`. A
#    MISSING queue directory is reported as an explicit state distinct from zero ("exists": False,
#    "inbox_count": None) -- the liaison retro measured 3 of 6 lanes launching with no queue dir at
#    all (no durable address), and a silent 0 there would hide exactly that finding. This function
#    only counts and ages inbox/ files; it does not validate receipts or state transitions --
#    check_messages.py owns that.
# ---------------------------------------------------------------------------


def discover_queue_state(lock_dir: Path, repo: str, lane: str, now: Optional[datetime] = None) -> dict[str, Any]:
    """Unread (inbox/) depth and the age of the oldest unread item for one repo x lane queue."""
    queue_dir = lock_dir / QUEUE_SUBDIR / repo / lane
    if not queue_dir.is_dir():
        return {
            "queue_dir": str(queue_dir),
            "exists": False,
            "inbox_count": None,
            "oldest_unread_sent_at": None,
            "oldest_unread_age_seconds": None,
        }
    inbox_dir = queue_dir / "inbox"
    files = sorted(inbox_dir.glob("*.json")) if inbox_dir.is_dir() else []
    now = now or datetime.now(timezone.utc)
    oldest_sent_at: Optional[str] = None
    oldest_dt: Optional[datetime] = None
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sent_at = data.get("sent_at")
        dt = _parse_iso(sent_at) if isinstance(sent_at, str) else None
        if dt is None:
            continue
        if oldest_dt is None or dt < oldest_dt:
            oldest_dt = dt
            oldest_sent_at = sent_at
    oldest_age = round((now - oldest_dt).total_seconds(), 1) if oldest_dt is not None else None
    return {
        "queue_dir": str(queue_dir),
        "exists": True,
        "inbox_count": len(files),
        "oldest_unread_sent_at": oldest_sent_at,
        "oldest_unread_age_seconds": oldest_age,
    }


# ---------------------------------------------------------------------------
# 9. `validate-brain --state` exit code for the WHOLE corpus, once per sweep -- NOT per repo.
#    `bastion validate-brain --help` documents [PATH] as "Path to search from when locating
#    brain.toml (walks up to find it)": it always validates the whole corpus, never a single
#    repo, no matter what path is passed. A per-repo join is therefore not merely redundant, it
#    is a FALSE GREEN for every repo but one -- confirmed empirically (2026-08-26): invoking it
#    against a vault-collapsed path and against a real repo root produces byte-identical output
#    and the same exit code either way, because the binary ignores everything about the path
#    except "where do I start walking up". One flag per invocation -- validate-brain's flags do
#    not compose (`main.rs` is an if/else-if chain, first flag wins, per CLAUDE.md's standing
#    rule) -- so this NEVER combines --state with another flag. Uses a direct list-form
#    subprocess.run (no shell=True, no pipe), so the captured returncode IS validate-brain's own
#    exit code, not a pipe's -- the exact trap CLAUDE.md warns about ("a piped command's $? is
#    the pipe's, not the command's"). `runner` is injectable so --self-test can shim this call
#    and never invoke the real binary against the real corpus.
# ---------------------------------------------------------------------------


def run_validate_brain(root: Path, runner=subprocess.run) -> dict[str, Any]:
    cmd = ["bastion", "validate-brain", "--state", str(root)]
    try:
        result = runner(cmd, capture_output=True, text=True)
    except (OSError, FileNotFoundError) as exc:
        return {"cmd": " ".join(cmd), "exit_code": None,
                "error": f"could not invoke: {exc}"}
    return {
        "cmd": " ".join(cmd),
        "exit_code": result.returncode,
    }


# ---------------------------------------------------------------------------
# Top-level join.
# ---------------------------------------------------------------------------


@dataclass
class LaneResult:
    repo: str
    blocks: list[dict[str, Any]] = field(default_factory=list)
    run_record: Optional[dict[str, Any]] = None
    operator_gates: dict[str, Any] = field(default_factory=lambda: {"gates": [], "coverage_count": 0})
    carryover: list[dict[str, Any]] = field(default_factory=list)
    lane_registry: list[dict[str, Any]] = field(default_factory=list)
    leases: list[dict[str, Any]] = field(default_factory=list)
    message_queue: dict[str, Any] = field(default_factory=dict)


def discover(root: Path, roadmap_slug: str, *, now: Optional[datetime] = None,
             validate_brain_runner=subprocess.run) -> dict[str, Any]:
    """The full join for one roadmap. Writes nothing. Returns a plain-dict result the command
    layer renders; empty sections are represented explicitly (empty list/dict), never omitted.

    `now` and `validate_brain_runner` are injectable so --self-test can pin a clock and shim the
    `bastion validate-brain` invocation -- neither is meant to be passed by real callers."""
    roadmap_dir = resolve_roadmap_dir(root, roadmap_slug)
    lane_entries = read_lane_log(roadmap_dir)
    repos_in_log = repos_from_lane_log(lane_entries)

    run_records = discover_run_records(root, roadmap_slug)
    # Union: repos named in the log, plus repos that wrote a run record but logged nothing --
    # that mismatch is itself a finding (D57 section 5's cross-check), not something to silently
    # union away.
    all_repos = sorted(set(repos_in_log) | set(run_records.keys()))

    repo_registry = discover_repos(root)

    lanes: dict[str, LaneResult] = {r: LaneResult(repo=r) for r in all_repos}

    for entry in lane_entries:
        repo = entry.get("repo")
        if repo not in lanes:
            continue
        block_id = entry.get("block", "")
        spec_slug = resolve_block_to_spec_slug(block_id) if block_id else None
        block_info: dict[str, Any] = {
            "block": block_id,
            "status": entry.get("status", "<absent>"),
            "note": entry.get("note"),
            "ts": entry.get("ts"),
            "spec_slug": spec_slug,
            "sdlc_state": None,
        }
        repo_path = repo_registry.get(repo)
        if repo_path is not None and spec_slug:
            spec_dir = repo_path.parent / spec_slug
            block_info["sdlc_state"] = read_sdlc_state(spec_dir)
        lanes[repo].blocks.append(block_info)

    for repo, record in run_records.items():
        if repo in lanes:
            lanes[repo].run_record = record
        else:
            lanes.setdefault(repo, LaneResult(repo=repo)).run_record = record

    coverage_total = 0
    for repo, path in repo_registry.items():
        if repo not in lanes:
            continue
        gates = discover_operator_gates(path)
        lanes[repo].operator_gates = gates
        coverage_total += gates["coverage_count"]
        lanes[repo].carryover = discover_carryover(path)

    # 7/8/9: leases + lane-agent registry, message queue depth, validate-brain exit code -- each
    # joined per repo, same as the operator-gates/carryover loop above.
    lock_dir = resolve_lock_dir(root)
    lane_names = lane_names_by_repo(lane_entries)
    registry_entries = discover_lane_registry(lock_dir, roadmap_slug, now=now)
    lease_entries = discover_leases(lock_dir, set(lanes.keys()), now=now)

    for repo in lanes:
        lanes[repo].lane_registry = [r for r in registry_entries if r.get("repo") == repo]
        lanes[repo].leases = [l for l in lease_entries if l.get("repo") == repo]

        lane_name = lane_names.get(repo)
        if lane_name:
            lanes[repo].message_queue = discover_queue_state(lock_dir, repo, lane_name, now=now)
        else:
            # No lane name known for this repo (absent from lane-log.jsonl) -- reported as an
            # explicit distinct state, same discipline as the missing-queue-dir case, rather than
            # guessing at a lane or silently omitting the field.
            lanes[repo].message_queue = {
                "queue_dir": None,
                "exists": None,
                "inbox_count": None,
                "oldest_unread_sent_at": None,
                "oldest_unread_age_seconds": None,
                "note": "no lane name known for this repo (absent from lane-log.jsonl)",
            }

    # One corpus-wide validate-brain call per sweep, reported once at the top level of the
    # result -- never per lane. See the block comment on run_validate_brain() for why a
    # per-repo join cannot work: the binary always validates the whole corpus regardless of
    # the path given, so a per-repo field would be a false green for every repo but one, and
    # it would also mean N full-corpus validations per sweep instead of one.
    validate_brain = run_validate_brain(root, runner=validate_brain_runner)

    return {
        "roadmap": roadmap_slug,
        "roadmap_dir": str(roadmap_dir),
        "lanes": {r: asdict(lanes[r]) for r in sorted(lanes)},
        "repos_in_lane_log": repos_in_log,
        "repos_with_run_record_only": sorted(set(run_records.keys()) - set(repos_in_log)),
        "operator_coverage_total": coverage_total,
        "coverage_caveat": (
            "gates recorded only in roadmap prose tables (e.g. planning/operator-surface/roadmap.md) "
            "are invisible to this graph-only read"
        ),
        "validate_brain": validate_brain,
    }


# ---------------------------------------------------------------------------
# --self-test
# ---------------------------------------------------------------------------

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        FAILURES.append(name)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class _FakeCompletedProcess:
    """Minimal subprocess.CompletedProcess stand-in for the validate-brain shim below."""

    def __init__(self, returncode: int):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


def _fake_validate_brain_runner(exit_code: int = 0, calls: Optional[list] = None):
    """Build a `runner` for `run_validate_brain()`/`discover()`'s `validate_brain_runner` param
    that never invokes the real `bastion` binary -- required by this module's own contract (never
    writes, and --self-test must not depend on the real corpus or an installed binary). `calls`,
    when given, collects each invoked cmd list so a case can assert the exact command shape (one
    flag, `--state`, never combined with another)."""
    def _runner(cmd, **kwargs):
        if calls is not None:
            calls.append(cmd)
        return _FakeCompletedProcess(exit_code)
    return _runner


def case_roadmap_dir_resolution() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "planning" / "roadmaps" / "alpha").mkdir(parents=True)
        (base / "planning" / "beta").mkdir(parents=True)

        check("new-location roadmap resolves", resolve_roadmap_dir(base, "alpha") == base / "planning" / "roadmaps" / "alpha")
        check("legacy-location roadmap resolves", resolve_roadmap_dir(base, "beta") == base / "planning" / "beta")

        (base / "planning" / "roadmaps" / "gamma").mkdir(parents=True)
        (base / "planning" / "gamma").mkdir(parents=True)
        ambiguous = False
        try:
            resolve_roadmap_dir(base, "gamma")
        except AmbiguousRoadmapError:
            ambiguous = True
        check("slug present in both locations raises AmbiguousRoadmapError", ambiguous)

        missing = False
        try:
            resolve_roadmap_dir(base, "nope")
        except FileNotFoundError:
            missing = True
        check("unknown slug raises FileNotFoundError", missing)


def case_realpath_dedup_state_json() -> None:
    """A worktree's planning/ symlink onto the same vault state.json must collapse to one repo."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        vault_state = base / "core" / "widget" / "planning" / "state.json"
        _write(vault_state, json.dumps({"repo": "widget", "tracks": []}))

        worktree_parent = base / "core" / "widget" / "trees" / "sdlc" / "spec"
        worktree_parent.mkdir(parents=True, exist_ok=True)
        (worktree_parent / "planning").symlink_to(vault_state.parent, target_is_directory=True)

        raw = sweep(base, "**/planning/state.json", ("planning", "state.json"))
        check("naive sweep sees both vault and worktree alias", len(raw) == 2)
        distinct = realpath_dedup(base, raw)
        check("realpath dedup collapses to one distinct file", len(distinct) == 1)
        check("retained path is the vault original, not a trees/ copy", "/trees/" not in str(distinct[0]))

        repos = discover_repos(base)
        check("discover_repos reports exactly one 'widget' entry (no double count)", repos == {"widget": distinct[0]})


def case_liveness_from_updated_at_not_status() -> None:
    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)
    stale = compute_liveness("running", "2026-08-12T00:00:00Z", now=now)
    check("a 12h-old 'running' file reports stale, not live", stale["liveness"] == "stale")
    check("stale result carries its age in hours", stale["age_hours"] is not None and stale["age_hours"] > STALE_THRESHOLD_HOURS)

    live = compute_liveness("running", "2026-08-12T11:00:00Z", now=now)
    check("a 1h-old 'running' file reports live", live["liveness"] == "live")

    unknown = compute_liveness("done", None, now=now)
    check("missing updated_at reports unknown liveness, not a crash", unknown["liveness"] == "unknown")


def case_unknown_status_passthrough() -> None:
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "planning" / "some-spec"
        state_path = spec_dir / "sdlc" / "sdlc-task-state.json"
        _write(state_path, json.dumps({"status": "quantum-flux", "updated_at": "2026-01-01T00:00:00Z"}))
        result = read_sdlc_state(spec_dir)
        check("unseen status value passes through verbatim", result["status"] == "quantum-flux")
        check("unseen status value is flagged not-known", result["status_known"] is False)

        # absent-field tolerance
        spec_dir2 = Path(td) / "planning" / "another-spec"
        state_path2 = spec_dir2 / "sdlc" / "sdlc-task-state.json"
        _write(state_path2, json.dumps({}))
        result2 = read_sdlc_state(spec_dir2)
        check("missing status/updated_at does not crash the join", result2 is not None and result2["status"] == "<absent>")

        # no sdlc/ dir at all
        spec_dir3 = Path(td) / "planning" / "no-sdlc-spec"
        spec_dir3.mkdir(parents=True)
        result3 = read_sdlc_state(spec_dir3)
        check("spec with no sdlc/ directory returns None, not a crash", result3 is None)


def case_operator_match_by_type_not_slug_prefix() -> None:
    with tempfile.TemporaryDirectory() as td:
        state_path = Path(td) / "planning" / "state.json"
        payload = {
            "repo": "demo",
            "tracks": [{
                "blocks": [{
                    "id": "DE.1.A",
                    "depends_on": [
                        {"type": "operator", "slug": "legacy-pre-rename-slug", "exit": "x", "start": "y"},
                        {"type": "approval", "slug": "operator-new-slug", "exit": "x2", "start": "y2"},
                        {"type": "block", "target": "DE.1.B"},
                    ],
                }],
            }],
        }
        _write(state_path, json.dumps(payload))
        result = discover_operator_gates(state_path)
        check("both legacy and new-convention slugs are found (type match, not prefix)", result["coverage_count"] == 2)
        found_slugs = {g["slug"] for g in result["gates"]}
        check("legacy-named operator edge is present", "legacy-pre-rename-slug" in found_slugs)
        check("new-named approval edge is present", "operator-new-slug" in found_slugs)
        check("a plain block-type edge is not counted as an operator gate", all(g["type"] in OPERATOR_EDGE_TYPES for g in result["gates"]))


def case_block_to_spec_slug_resolution() -> None:
    check("ticket block resolves", resolve_block_to_spec_slug("BT.ticket.roadmap-status-command") == "ticket-roadmap-status-command")
    check("chore block resolves", resolve_block_to_spec_slug("HQ.chore.tidy-index") == "chore-tidy-index")
    check("phase-letter block is unresolved (needs master-plan.md, not fabricated)", resolve_block_to_spec_slug("EN.8.B") is None)


def case_roadmap_isolation() -> None:
    """The primary axis of the command: two roadmaps sharing the same fixture tree must never leak
    into each other's result, in either direction."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)

        roadmap_a = base / "planning" / "roadmaps" / "roadmap-a"
        roadmap_a.mkdir(parents=True)
        _write(roadmap_a / "lane-log.jsonl",
               '{"ts":"2026-08-12T00:00:00Z","lane":"a","repo":"repo-alpha","block":"BT.ticket.thing-a",'
               '"status":"closed","note":"n"}\n')

        roadmap_b = base / "planning" / "roadmaps" / "roadmap-b"
        roadmap_b.mkdir(parents=True)
        _write(roadmap_b / "lane-log.jsonl",
               '{"ts":"2026-08-12T00:00:00Z","lane":"b","repo":"repo-beta","block":"BT.ticket.thing-b",'
               '"status":"closed","note":"n"}\n')

        notes_a = base / "core" / "repo-alpha" / "planning" / "orchestration-run" / "roadmap-a" / "notes.md"
        _write(notes_a, "---\nlifecycle: lane-complete\n---\n\n| # | Item |\n|---|---|\n| 1 | a |\n")
        notes_b = base / "core" / "repo-beta" / "planning" / "orchestration-run" / "roadmap-b" / "notes.md"
        _write(notes_b, "---\nlifecycle: lane-complete\n---\n\n| # | Item |\n|---|---|\n| 1 | b |\n")

        result_a = discover(base, "roadmap-a", validate_brain_runner=_fake_validate_brain_runner())
        check("--roadmap A reports A's lane (repo-alpha)", "repo-alpha" in result_a["lanes"])
        check("--roadmap A never leaks B's lane (repo-beta)", "repo-beta" not in result_a["lanes"])
        check("--roadmap A's roadmap_dir is A's own directory", result_a["roadmap_dir"] == str(roadmap_a))

        result_b = discover(base, "roadmap-b", validate_brain_runner=_fake_validate_brain_runner())
        check("--roadmap B reports B's lane (repo-beta)", "repo-beta" in result_b["lanes"])
        check("--roadmap B never leaks A's lane (repo-alpha)", "repo-alpha" not in result_b["lanes"])
        check("--roadmap B's roadmap_dir is B's own directory", result_b["roadmap_dir"] == str(roadmap_b))


def case_live_measured_snapshot() -> None:
    """(8) Live, dated measurement from BRAIN_ROOT for run-state-shaped files
    (`**/sdlc/sdlc-*state.json`). Asserts the RELATION -- naive raw count exceeds realpath-distinct
    count, and every hit routed through a `/trees/` segment collapses onto a non-`trees/` realpath
    -- never a hard equality against MEASURED_RAW/MEASURED_DISTINCT, which are a dated snapshot
    that goes stale as the fleet accumulates runs. Skipped (not failed) when no brain.toml is
    reachable, e.g. a clone of only this repo with no vault sibling."""
    root = find_brain_root(REPO_ROOT) or find_brain_root()
    if root is None:
        print(
            "  skip (8) live measured snapshot: no brain.toml found walking up from "
            f"{REPO_ROOT} or cwd -- this property only applies inside the agentic-portfolio brain root"
        )
        return

    print(f"  measuring from {root} with: {MEASURING_COMMAND}  (dated {MEASURED_DATE}, "
          f"snapshot was raw={MEASURED_RAW} distinct={MEASURED_DISTINCT})")
    raw = sweep(root, "**/sdlc/sdlc-*state.json", ("sdlc", "sdlc-", "state.json"),
                follow_symlinks=True, hidden=True)
    naive = len(raw)
    distinct = realpath_dedup(root, raw)
    print(f"  naive={naive} distinct={len(distinct)}")

    trees_hits = [h for h in raw if "/trees/" in h]
    non_collapsing = [h for h in trees_hits if "/trees/" in str(Path(os.path.realpath(root / h)))]

    # SCOPED TO THIS REPO ON PURPOSE (2026-08-20). The collapse property holds only for a repo
    # whose worktrees carry the vault `planning/` symlink; a sibling repo whose worktree has a
    # REAL planning/ directory breaks it, and that is a fact about that repo's checkout, not about
    # this module. Measured that day: this case went red in every concurrent lane because
    # core/engine-rs and core/bastion each had a live worktree -- i.e. a gating check failed
    # precisely BECAUSE other lanes were running, which is the condition it normally runs under.
    # A cross-repo hygiene assertion does not belong in this module's unit self-test; it is filed
    # as BT.ticket.fleet-worktree-planning-symlink-hygiene. Foreign hits are still PRINTED, so the
    # signal is not lost -- only its power to red-gate an unrelated lane is.
    try:
        own_prefix = str(REPO_ROOT.resolve().relative_to(root)) + os.sep
    except ValueError:
        own_prefix = ""
    own_non_collapsing = [h for h in non_collapsing if own_prefix and h.startswith(own_prefix)]
    foreign = [h for h in non_collapsing if h not in own_non_collapsing]
    if foreign:
        foreign_repos = sorted({h.split("/trees/")[0] for h in foreign})
        print(f"  note: {len(foreign)} non-collapsing /trees/ hit(s) in other repos "
              f"({', '.join(foreign_repos)}) -- reported, not gated (see "
              f"BT.ticket.fleet-worktree-planning-symlink-hygiene)")

    check("(8) naive raw count exceeds realpath-distinct count", naive > len(distinct))
    check("(8) every /trees/-routed hit in THIS repo collapses onto a non-trees/ realpath",
          len(own_non_collapsing) == 0)


def case_no_writes() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "planning" / "roadmaps" / "demo").mkdir(parents=True)
        _write(base / "planning" / "roadmaps" / "demo" / "lane-log.jsonl",
               '{"ts":"2026-08-12T00:00:00Z","lane":"a","repo":"widget","block":"BT.ticket.x","status":"closed","note":"n"}\n')
        before = sorted(str(p) for p in base.rglob("*"))
        discover(base, "demo", validate_brain_runner=_fake_validate_brain_runner())
        after = sorted(str(p) for p in base.rglob("*"))
        check("discover() creates or modifies no files", before == after)


def case_empty_roadmap_is_explicit() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "planning" / "roadmaps" / "ghost").mkdir(parents=True)
        result = discover(base, "ghost", validate_brain_runner=_fake_validate_brain_runner())
        check("empty lane-log yields explicit empty lanes dict, not a missing key", result["lanes"] == {})
        check("repos_in_lane_log is explicitly empty list", result["repos_in_lane_log"] == [])
        check("operator_coverage_total is explicitly 0, not an omitted key", result["operator_coverage_total"] == 0)
        check("coverage caveat is always present", "coverage_caveat" in result and result["coverage_caveat"])


def case_full_join_end_to_end() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        roadmap_dir = base / "planning" / "roadmaps" / "demo"
        roadmap_dir.mkdir(parents=True)
        _write(roadmap_dir / "lane-log.jsonl",
               '{"ts":"2026-08-12T00:00:00Z","lane":"a","repo":"widget","block":"BT.ticket.thing","status":"closed","note":"n"}\n')

        state_path = base / "core" / "widget" / "planning" / "state.json"
        _write(state_path, json.dumps({
            "repo": "widget",
            "carryover": [{"priority": "P2", "note": "leftover"}],
            "tracks": [{"blocks": [{"id": "BT.ticket.thing", "depends_on": []}]}],
        }))

        spec_state = base / "core" / "widget" / "planning" / "ticket-thing" / "sdlc" / "sdlc-task-state.json"
        _write(spec_state, json.dumps({"status": "done", "updated_at": "2026-08-12T00:00:00Z",
                                        "current_task": 3, "tasks_run": [1, 2, 3]}))

        notes = base / "core" / "widget" / "planning" / "orchestration-run" / "demo" / "notes.md"
        _write(notes, "---\nlifecycle: lane-complete\nrun_started: 2026-08-11\nrun_ended: 2026-08-12\n---\n\n"
                       "| # | Item | Owner | Priority | Status |\n|---|---|---|---|---|\n"
                       "| 1 | thing | widget | P2 | **OPEN** |\n")

        now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)

        registry_path = base / LOCK_SUBDIR / REGISTRY_SUBDIR / "agent-widget-a.json"
        _write(registry_path, json.dumps({
            "agent_name": "widget-a", "repo": "widget", "lane": "a", "roadmap": "demo",
            "started_at": "2026-08-12T10:00:00Z", "heartbeat": "2026-08-12T11:55:00Z",
        }))

        lease_path = base / LOCK_SUBDIR / LEASE_SUBDIR / "lease-widget.json"
        _write(lease_path, json.dumps({
            "repo": "widget", "lane": "a", "agent": "widget-a",
            "acquired_at": "2026-08-12T10:00:00Z", "kind": "exclusive",
        }))

        inbox_msg = base / LOCK_SUBDIR / QUEUE_SUBDIR / "widget" / "a" / "inbox" / "20260812T113000Z-msg1.json"
        _write(inbox_msg, json.dumps({
            "message_id": "msg1", "sender": {"agent_name": "peer", "repo": "widget", "lane": "b",
                                              "roadmap": "demo"},
            "sent_at": "2026-08-12T11:30:00Z", "kind": "QUERY", "subject": {"repo": "widget"},
            "body": "x", "durable_home": {"channel": "run-record", "ref": "x"},
            "verified_by": "UNVERIFIED: peer",
        }))

        calls: list = []
        result = discover(base, "demo", now=now,
                           validate_brain_runner=_fake_validate_brain_runner(exit_code=0, calls=calls))
        check("end-to-end: one lane discovered", list(result["lanes"].keys()) == ["widget"])
        lane = result["lanes"]["widget"]
        check("end-to-end: block resolved to spec slug", lane["blocks"][0]["spec_slug"] == "ticket-thing")
        check("end-to-end: sdlc state joined onto the block", lane["blocks"][0]["sdlc_state"]["status"] == "done")
        check("end-to-end: run record joined with open_count", lane["run_record"]["notes"]["open_count"] == 1)
        check("end-to-end: carryover joined", lane["carryover"] == [{"priority": "P2", "note": "leftover"}])

        check("end-to-end: lane-agent registry claim joined", len(lane["lane_registry"]) == 1
              and lane["lane_registry"][0]["agent_name"] == "widget-a")
        check("end-to-end: registry heartbeat age is live (5 min old)", lane["lane_registry"][0]["stale"] is False)
        check("end-to-end: lease joined with holder + kind", len(lane["leases"]) == 1
              and lane["leases"][0]["holder"] == "widget-a" and lane["leases"][0]["kind"] == "exclusive")
        check("end-to-end: message queue exists with one unread item", lane["message_queue"]["exists"] is True
              and lane["message_queue"]["inbox_count"] == 1)
        check("end-to-end: oldest unread age computed (30 min)", lane["message_queue"]["oldest_unread_age_seconds"] == 1800.0)
        check("end-to-end: validate-brain exit code joined once at top level (shimmed, exit 0)",
              result["validate_brain"]["exit_code"] == 0)
        check("end-to-end: validate-brain is NOT a per-lane field", "validate_brain" not in lane)
        check("end-to-end: validate-brain invoked with exactly one flag (--state)",
              len(calls) == 1 and calls[0].count("--state") == 1
              and not any(c.startswith("--") and c != "--state" for c in calls[0]))
        check("end-to-end: validate-brain invoked with the corpus root, not a vault-collapsed repo path",
              calls[0] == ["bastion", "validate-brain", "--state", str(base)])


def case_stale_heartbeat_and_lease_kinds() -> None:
    """(7) Lease + lane-agent registry join: a heartbeat past STALE_THRESHOLD_SECONDS is flagged
    stale (age from `_LANE_AGENTS.staleness_seconds`, never from a status field -- same rule as
    `compute_liveness()` applied to heartbeats), and exclusive vs. shared leases are both reported
    verbatim with their `kind` intact (this module does not adjudicate the duplicate-exclusive
    case -- that stays check_lane_agents.py's)."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        roadmap_dir = base / "planning" / "roadmaps" / "demo2"
        roadmap_dir.mkdir(parents=True)
        _write(roadmap_dir / "lane-log.jsonl",
               '{"ts":"2026-08-12T00:00:00Z","lane":"a","repo":"repo-x","block":"BT.ticket.thing",'
               '"status":"closed","note":"n"}\n'
               '{"ts":"2026-08-12T00:00:00Z","lane":"b","repo":"repo-y","block":"BT.ticket.other",'
               '"status":"closed","note":"n"}\n')

        now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)

        # repo-x: a registry claim whose heartbeat is 4 hours old -- past STALE_THRESHOLD_SECONDS
        # (3 hours) -- must be flagged stale even though nothing calls it "abandoned" anywhere.
        _write(base / LOCK_SUBDIR / REGISTRY_SUBDIR / "agent-repo-x-a.json", json.dumps({
            "agent_name": "repo-x-a", "repo": "repo-x", "lane": "a", "roadmap": "demo2",
            "started_at": "2026-08-12T06:00:00Z", "heartbeat": "2026-08-12T08:00:00Z",
        }))
        # A registry claim for a DIFFERENT roadmap must never leak in.
        _write(base / LOCK_SUBDIR / REGISTRY_SUBDIR / "agent-repo-x-foreign.json", json.dumps({
            "agent_name": "repo-x-foreign", "repo": "repo-x", "lane": "a", "roadmap": "other-roadmap",
            "started_at": "2026-08-12T06:00:00Z", "heartbeat": "2026-08-12T11:59:00Z",
        }))

        # repo-x holds an exclusive lease; repo-y holds a shared one -- both must round-trip
        # verbatim, `kind` intact.
        _write(base / LOCK_SUBDIR / LEASE_SUBDIR / "lease-repo-x.json", json.dumps({
            "repo": "repo-x", "lane": "a", "agent": "repo-x-a",
            "acquired_at": "2026-08-12T06:00:00Z", "kind": "exclusive",
        }))
        _write(base / LOCK_SUBDIR / LEASE_SUBDIR / "lease-repo-y.json", json.dumps({
            "repo": "repo-y", "lane": "b", "agent": "repo-y-b",
            "acquired_at": "2026-08-12T11:50:00Z", "kind": "shared",
        }))

        calls: list = []
        result = discover(base, "demo2", now=now,
                           validate_brain_runner=_fake_validate_brain_runner(calls=calls))

        check("stale heartbeat: two repos in this roadmap yield exactly ONE validate-brain call, not one per repo",
              len(calls) == 1)

        rx_registry = result["lanes"]["repo-x"]["lane_registry"]
        check("stale heartbeat: only the matching-roadmap claim is joined (foreign roadmap excluded)",
              len(rx_registry) == 1 and rx_registry[0]["agent_name"] == "repo-x-a")
        check("stale heartbeat: a 4h-old heartbeat is flagged stale", rx_registry[0]["stale"] is True)
        check("stale heartbeat: age is reported in seconds", rx_registry[0]["heartbeat_age_seconds"] == 4 * 3600.0)

        rx_leases = result["lanes"]["repo-x"]["leases"]
        ry_leases = result["lanes"]["repo-y"]["leases"]
        check("lease kind: repo-x's lease reports kind=exclusive", rx_leases[0]["kind"] == "exclusive")
        check("lease kind: repo-y's lease reports kind=shared", ry_leases[0]["kind"] == "shared")
        check("lease kind: repo-y's lease (10 min old) is not stale", ry_leases[0]["stale"] is False)


def case_missing_queue_dir_is_distinct_from_zero() -> None:
    """(8) A repo/lane with no queue directory at all reports `exists: False` and
    `inbox_count: None` -- distinct from an existing-but-empty queue reporting `inbox_count: 0`.
    Conflating the two would hide exactly what the liaison retro measured: 3 of 6 lanes launched
    with no queue dir, i.e. no durable address, not merely an empty one."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        roadmap_dir = base / "planning" / "roadmaps" / "demo3"
        roadmap_dir.mkdir(parents=True)
        _write(roadmap_dir / "lane-log.jsonl",
               '{"ts":"2026-08-12T00:00:00Z","lane":"a","repo":"repo-nolane","block":"BT.ticket.x",'
               '"status":"closed","note":"n"}\n')
        # No .fleet-locks/queue/repo-nolane/a/ at all on disk.

        result = discover(base, "demo3", validate_brain_runner=_fake_validate_brain_runner())
        mq = result["lanes"]["repo-nolane"]["message_queue"]
        check("missing queue dir: exists is explicitly False, not omitted", mq["exists"] is False)
        check("missing queue dir: inbox_count is None, never a silent 0", mq["inbox_count"] is None)
        check("missing queue dir: queue_dir path is still reported for debugging", mq["queue_dir"])


def case_validate_brain_nonzero_exit_joined() -> None:
    """(9) A non-zero validate-brain exit code is captured and joined ONCE, at the top level of
    the result -- never per repo -- via the injectable `runner`. Proves the shim path a real
    failing corpus would take without ever invoking the real binary, and pins the corpus-wide
    collapse: a per-repo `exit_code` field would be a false green for every repo but one, since
    `bastion validate-brain --help` documents [PATH] as merely "where to start walking up to
    find brain.toml" -- the result is corpus-wide regardless of which path is passed."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        roadmap_dir = base / "planning" / "roadmaps" / "demo4"
        roadmap_dir.mkdir(parents=True)
        _write(roadmap_dir / "lane-log.jsonl",
               '{"ts":"2026-08-12T00:00:00Z","lane":"a","repo":"repo-broken","block":"BT.ticket.x",'
               '"status":"closed","note":"n"}\n')

        calls: list = []
        result = discover(base, "demo4",
                           validate_brain_runner=_fake_validate_brain_runner(exit_code=1, calls=calls))
        vb = result["validate_brain"]
        check("validate-brain: non-zero exit code is captured, not swallowed", vb["exit_code"] == 1)
        check("validate-brain: not a per-lane field", "validate_brain" not in result["lanes"]["repo-broken"])
        check("validate-brain: exactly one invocation for the whole sweep, not one per repo touched", len(calls) == 1)
        check("validate-brain: never combines --state with a second flag",
              calls[0].count("--state") == 1
              and not any(c.startswith("--") and c != "--state" for c in calls[0]))
        check("validate-brain: invoked with the corpus root, not a vault-collapsed repo path",
              calls[0] == ["bastion", "validate-brain", "--state", str(base)])


def self_test() -> int:
    print("roadmap_status_discovery.py --self-test")
    case_roadmap_dir_resolution()
    case_realpath_dedup_state_json()
    case_liveness_from_updated_at_not_status()
    case_unknown_status_passthrough()
    case_operator_match_by_type_not_slug_prefix()
    case_block_to_spec_slug_resolution()
    case_roadmap_isolation()
    case_live_measured_snapshot()
    case_no_writes()
    case_empty_roadmap_is_explicit()
    case_full_join_end_to_end()
    case_stale_heartbeat_and_lease_kinds()
    case_missing_queue_dir_is_distinct_from_zero()
    case_validate_brain_nonzero_exit_joined()

    if FAILURES:
        print(f"\n{len(FAILURES)} self-test case(s) failed: {FAILURES}")
        return 1
    print("\nall self-test cases passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run synthetic fixture cases only")
    parser.add_argument("--roadmap", type=str, default=None, help="roadmap slug to discover")
    parser.add_argument("--root", type=Path, default=None,
                         help="brain root (default: walk up from cwd for brain.toml)")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    root = args.root or find_brain_root()
    if root is None:
        print("could not resolve brain root (no brain.toml found walking up from cwd); pass --root",
              file=sys.stderr)
        return 2

    if not args.roadmap:
        candidates = list_candidate_roadmaps(root)
        print(json.dumps({"candidates": candidates}, indent=2))
        return 0

    try:
        result = discover(root, args.roadmap)
    except (AmbiguousRoadmapError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
