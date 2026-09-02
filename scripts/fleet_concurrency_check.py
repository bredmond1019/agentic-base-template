#!/usr/bin/env python3
"""Real (mechanical) enforcement of the "at most two heavy-gate repos concurrently" rule.

Why this exists: `.claude/commands/orchestrate.md` and `.claude/commands/begin-orchestration.md`
both stated the two-heavy-repos rule as prose that nothing enforced ("Today that is a human
decision" / "Nothing enforces this."), and asked a lane agent to reason about sibling-lane state it
cannot observe — no lane can see a sibling lane's session. This script gives a lane a mechanical
answer instead: an advisory lockfile registry under the brain root that a lane checks before
starting a heavy repo, and releases when it finishes.

Design (recorded in full in planning/decisions/D61-fleet-concurrency-enforcement.md):

- **State**: one small JSON file per active heavy lane, in a shared lock directory. Each file
  records `{repo, pid, pid_source, started_at}`. The directory is resolved by walking up from the current
  working directory looking for `brain.toml` (the brain root's own marker file, already relied on
  elsewhere per base-template/CLAUDE.md) and using `<brain_root>/.fleet-locks/`; it can also be
  forced with `--lock-dir` / `FLEET_LOCK_DIR` (used by the test suite and by a caller that already
  knows the brain root).
- **Registration**: `register` first sweeps stale entries (see below), then counts what is left.
  If capacity (`MAX_HEAVY_LANES`, default 2) is not yet used, it writes its own lock file and
  reports allowed; otherwise it reports refused and names the lanes holding the slots.
- **Stale-entry expiry**: pid-liveness (checked via `os.kill(pid, 0)`) is trusted as a staleness
  signal ONLY for an entry whose `pid_source` is `"explicit"` — i.e. the caller passed a `--pid`
  that is not the writer process's own. The registering process is itself short-lived and exits as
  soon as the command returns, so its own pid is never a valid liveness signal for a *different*,
  later process to check — treating it as one is exactly the "dead on arrival" bug this design
  fixes (planning/decisions/D61 vs. the fix recorded in this ticket). An entry with `pid_source`
  `"self"` (the default — no `--pid` was passed) relies solely on `--ttl` expiry (default 5400s /
  90 minutes, matched to a real lane segment) plus an explicit `release`. Either way, an entry is
  removed during the sweep, unconditionally before it can block anyone, once it is stale by
  whichever rule applies to it.
- **Clean release**: `release` removes exactly the lock file this repo+agent (or, absent an
  `--agent`, repo+pid) registered — entries are keyed on the caller's `--agent` identity when one
  is supplied, precisely so that a `register` call and a LATER, separate-process `release` call for
  the same agent compute the identical on-disk path
  (BT.ticket.register-leaks-a-slot-and-the-commands-teach-it; before this, `release` computed its
  path from its OWN pid, which never matched the registering process's pid, so the entry survived
  and `release` still reported success). `release` reports `removed: true`/`false` for whether an
  entry genuinely existed and was deleted. A lane that exits cleanly should always call `release`;
  a lane that dies without calling it is caught by TTL expiry (or, for an explicit pid, liveness) on
  the next registration attempt instead. A long lane should re-register periodically as a
  heartbeat — `register` is idempotent-refresh, so a re-register of the same repo+agent+category
  bumps `started_at` instead of consuming a second slot.
- **Degrade to advisory, never hard-fail**: if the lock directory cannot be resolved, created, or
  written to for any reason (no brain.toml found, permission error, read-only filesystem, ...),
  every operation reports success with `degraded: true` and a reason — the caller proceeds exactly
  as it would have under the old prose-only rule. The mechanism only ever adds a capability; it
  never becomes a new way for a run to fail that the old rule didn't already have.
- **"Heavy" is derived from a repo's own `planning/harness.json`, never memorized, and comes in two
  categories with separate caps** (D66): `heavy_category` reads the target repo's harness config
  and returns `"browser-automation"` if `uiTest.enabled` is true or any validation check's command
  names a browser/production-build tool (Playwright, Cypress, Puppeteer, `next build`, `vite
  build`, `npm run build`, ...), `"native-build"` if a check names a native compile/link command
  (`cargo build --release`), or `None` if neither. Capacity (`MAX_LANES_BY_CATEGORY`) is counted
  per category — a native-build lane never competes with a browser-automation lane for a slot.

CLI:
  python3 scripts/fleet_concurrency_check.py register --repo <name> --agent <id> [--pid PID] [--ttl SECONDS] [--lock-dir DIR]
  python3 scripts/fleet_concurrency_check.py release  --repo <name> --agent <id> [--pid PID] [--lock-dir DIR]
  python3 scripts/fleet_concurrency_check.py status   [--lock-dir DIR]
  python3 scripts/fleet_concurrency_check.py is-heavy --repo-path <path>

Exit codes: `register` exits 0 when allowed (including degraded-advisory), 3 when refused at
capacity. `release` and `status` always exit 0. `is-heavy` exits 0 if heavy, 1 if not.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_TTL_SECONDS = 5400  # 90 minutes - matched to a real lane segment's length, not an afternoon
LOCK_SUBDIR = ".fleet-locks"

# Two distinct cost shapes get lumped under "heavy" in the old prose rule, but they are not
# equally dangerous (see planning/decisions/D66-tiered-heavy-lane-concurrency.md):
#
# - browser-automation: repeated, interactive-cost tooling (Playwright et al) that stacks CPU
#   pressure the whole time a lane runs. This is what motivated the original 2-lane ceiling
#   (three concurrent Next.js + Playwright lanes saturated the operator's MacBook Pro).
# - native-build: a compile/link step that is expensive once per lane (end/reconcile), not
#   per-task, per D57 measurement — cheap enough in practice that the operator routinely runs
#   3-4 Rust lanes concurrently without issue.
BROWSER_AUTOMATION_SIGNALS = (
    "playwright",
    "cypress",
    "puppeteer",
    "next build",
    "vite build",
    "npm run build",
    "yarn build",
    "pnpm build",
)

NATIVE_BUILD_SIGNALS = (
    "cargo build --release",
)

MAX_LANES_BY_CATEGORY = {
    "browser-automation": 2,
    "native-build": 4,
}

# Legacy name/value, kept for any external caller still importing it directly.
HEAVY_COMMAND_SIGNALS = BROWSER_AUTOMATION_SIGNALS
MAX_HEAVY_LANES = MAX_LANES_BY_CATEGORY["browser-automation"]


def _import_check_lane_agents():
    """Import check_lane_agents.py from this same scripts/ directory.

    Load-bearing: `<lock_dir>/leases/lease-*.json` is BT.6.A's shape (check_lane_agents.py),
    and this ticket is a READER of it, never a second implementation. Reusing that module's own
    `discover_lease_files`, `staleness_seconds` and `STALE_THRESHOLD_SECONDS` is how "reuse
    check_lane_agents.py's acquired_at staleness rule; add no third heuristic" is actually
    satisfied, rather than merely claimed. A plain `import check_lane_agents` is not reliable
    here: when this module is loaded via `importlib.util.spec_from_file_location` (the way the
    test suite loads it) this directory is never added to `sys.path`, so the import must locate
    it by this file's own path instead of trusting the caller's sys.path state.
    """
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import check_lane_agents  # noqa: E402 - deliberate late/local import, see docstring above

    return check_lane_agents


_LANE_AGENTS = _import_check_lane_agents()


def _safe_repo_name(repo: str) -> str:
    """Filesystem-safe stand-in for a repo name used in a lock filename."""
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in repo)


@dataclass
class LockResult:
    allowed: bool
    degraded: bool = False
    reason: str = ""
    active: list = field(default_factory=list)
    # Held `kind: exclusive` leases, reported distinctly from `active` (ordinary heavy-lane
    # entries) so a reader can tell WHY nothing may start -- see `status()` and the refusal
    # path in `register()`.
    exclusive_leases: list = field(default_factory=list)
    # Set only by `release()` -- whether an on-disk entry actually existed and was removed, as
    # opposed to the pre-fix behaviour of reporting `allowed: true` unconditionally regardless of
    # whether anything was there to remove (BT.ticket.register-leaks-a-slot-and-the-commands-teach-it).
    removed: bool = False

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "degraded": self.degraded,
            "reason": self.reason,
            "active": self.active,
            "exclusive_leases": self.exclusive_leases,
            "removed": self.removed,
        }


def find_brain_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk upward from `start` (default: cwd) looking for a directory containing brain.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "brain.toml").exists():
            return candidate
    return None


def resolve_lock_dir(explicit: Optional[str] = None) -> Optional[Path]:
    """Resolve the shared lock directory, or None if it cannot be determined/created.

    Precedence: explicit --lock-dir argument, then FLEET_LOCK_DIR env var, then a brain.toml
    discovered by walking up from cwd. Returns None (never raises) when nothing resolves or the
    directory cannot be created — callers must treat None as "degrade to advisory."
    """
    candidate: Optional[Path] = None
    if explicit:
        candidate = Path(explicit)
    elif os.environ.get("FLEET_LOCK_DIR"):
        candidate = Path(os.environ["FLEET_LOCK_DIR"])
    else:
        brain_root = find_brain_root()
        if brain_root is not None:
            candidate = brain_root / LOCK_SUBDIR

    if candidate is None:
        return None

    try:
        candidate.mkdir(parents=True, exist_ok=True)
        # Confirm it is actually writable, not just creatable.
        probe = candidate / f".probe-{os.getpid()}"
        probe.write_text("")
        probe.unlink()
    except OSError:
        return None

    return candidate


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by someone else - still running.
        return True
    except OSError:
        return False
    return True


def _lock_path(lock_dir: Path, repo: str, agent: Optional[str], pid: int) -> Path:
    """Filesystem path for `repo`'s lock entry.

    Keyed on the caller's AGENT identity when one is supplied
    (BT.ticket.register-leaks-a-slot-and-the-commands-teach-it) -- a `register` call and a LATER
    `release` call for the same agent then compute the identical path even though they run as two
    separate OS processes with two different pids, which is what makes `release` actually free the
    slot it was given instead of unlinking a path nothing ever wrote. Falls back to the old
    pid-keyed scheme when no `--agent` is supplied by either caller -- deliberately NOT migrated:
    a pre-existing old-scheme on-disk entry keeps its own pid-keyed filename and is still swept and
    counted identically by `_sweep_stale`/`register`'s capacity check, since both operate over
    every `*.json` file in the directory regardless of which naming scheme produced it.
    """
    if agent:
        return lock_dir / f"{_safe_repo_name(repo)}__agent-{_safe_repo_name(agent)}.json"
    return lock_dir / f"{_safe_repo_name(repo)}__{pid}.json"


def _sweep_stale(lock_dir: Path, ttl_seconds: int) -> list:
    """Remove stale entries in place; return the list of surviving entries as dicts."""
    survivors = []
    for entry_path in sorted(lock_dir.glob("*.json")):
        try:
            data = json.loads(entry_path.read_text())
        except (OSError, json.JSONDecodeError):
            # Unreadable/corrupt entry - treat as stale and remove it rather than let it block
            # the fleet forever.
            entry_path.unlink(missing_ok=True)
            continue

        pid = data.get("pid")
        started_at = data.get("started_at", 0)
        age = time.time() - started_at
        pid_source = data.get("pid_source", "self")
        # pid-liveness is a signal ONLY for an entry whose pid was EXPLICITLY supplied by the
        # caller (pid_source == "explicit") - that is a real, potentially long-lived process the
        # caller vouches for. A "self" entry's pid is the short-lived writer process's own
        # os.getpid(), which is gone by the time any other process checks it - using it as a
        # liveness signal is exactly the dead-on-arrival bug this model fixes. "self" entries rely
        # on TTL expiry plus an explicit release instead.
        pid_dead = pid_source == "explicit" and (
            (not isinstance(pid, int)) or (not _pid_running(pid))
        )
        stale = pid_dead or (age > ttl_seconds)
        if stale:
            entry_path.unlink(missing_ok=True)
            continue

        data["_path"] = str(entry_path)
        survivors.append(data)
    return survivors


def _readable_leases(lock_dir: Path) -> list:
    """Every syntactically-loadable lease record under `lock_dir`, fail-open.

    An absent `leases/` directory (the normal state before any lane has ever taken an exclusive
    lease -- true for every pre-existing test in this suite) or one that cannot be listed/read
    (permission error) yields an empty list rather than raising: exclusivity is a READ this
    script layers on top of BT.6.A's shape, and an unreadable/absent leases/ must never harden
    `register`/`status` into a new way for a run to fail (per the block record's degraded-path
    criterion). A malformed individual lease file is skipped the same way `_sweep_stale` skips a
    corrupt ordinary lock entry -- reported nowhere here (check_lane_agents.py's own gated check
    is what validates lease shape), just not treated as a live exclusive hold.
    """
    try:
        lease_paths = _LANE_AGENTS.discover_lease_files(lock_dir)
    except OSError:
        return []

    records = []
    for path in lease_paths:
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _non_stale_exclusive_leases(lock_dir: Path) -> list:
    """Held `kind: exclusive` leases whose liveness timestamp is not yet stale.

    Staleness reuses check_lane_agents.py's OWN rule verbatim --
    `staleness_seconds(record["heartbeat"] or record["acquired_at"])`, via its
    `lease_liveness_timestamp()` helper, compared against its `STALE_THRESHOLD_SECONDS` -- so an
    abandoned exclusive lease cannot park the fleet forever, and this script introduces no
    second/third staleness heuristic alongside check_lane_agents.py's and its own TTL rule for
    ordinary lock entries. Reusing `lease_liveness_timestamp()` (rather than reading `acquired_at`
    directly, as before `heartbeat` existed) is what keeps this script and check_lane_agents.py
    from ever disagreeing about which leases are live.
    """
    survivors = []
    for record in _readable_leases(lock_dir):
        if record.get("kind") != "exclusive":
            continue
        age = _LANE_AGENTS.staleness_seconds(_LANE_AGENTS.lease_liveness_timestamp(record))
        if age is not None and age > _LANE_AGENTS.STALE_THRESHOLD_SECONDS:
            continue
        survivors.append(record)
    return survivors


def _find_blocking_exclusive_lease(
    lock_dir: Path, requester_agent: Optional[str], requester_repo: Optional[str]
) -> Optional[dict]:
    """The first non-stale exclusive lease that blocks this requester, or None.

    A lease whose `agent` matches the requester is the holder re-registering (a heartbeat), not a
    conflict -- an agent can never be refused on account of its own hold. A requester with no
    agent identity supplied (`requester_agent is None`) can never match, by design: an
    unidentified caller cannot be recognized as the holder re-registering, so it is treated as a
    different agent and refused, same as any other outsider.

    Beyond that (BT.ticket.exclusive-lease-refuses-every-register): a lease only blocks when its
    `scope` is `"fleet"`, or its `repo` equals the requester's own repo. `scope` absent is
    treated as `"repo"` -- every lease already on disk omits the field and none may change
    meaning under this rule. This is what stops an ordinary lane's exclusive lease (protecting
    its own working tree) from parking every OTHER lane's register fleet-wide, while a
    `scope: fleet` lease still quiesces everything (the HQ.8.A case).
    """
    for record in _non_stale_exclusive_leases(lock_dir):
        if requester_agent is not None and record.get("agent") == requester_agent:
            continue
        scope = record.get("scope", "repo")
        if scope != "fleet" and record.get("repo") != requester_repo:
            continue
        return record
    return None


def register(
    repo: str,
    category: str = "browser-automation",
    pid: Optional[int] = None,
    agent: Optional[str] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    lock_dir_override: Optional[str] = None,
    max_heavy_lanes: Optional[int] = None,
) -> LockResult:
    """Register `repo` as an active heavy lane in `category`.

    Capacity is counted per category, not fleet-wide: a native-build lane never competes for a
    slot with a browser-automation lane. `max_heavy_lanes`, if given, overrides
    MAX_LANES_BY_CATEGORY[category]; otherwise the category's own default applies.

    BEFORE any of that: a non-stale `kind: exclusive` lease held by a DIFFERENT agent (see
    `_find_blocking_exclusive_lease`) refuses this call outright, in ANY category and regardless
    of whether `repo` is heavy-gated at all -- this is fleet-exclusive admission control, checked
    ahead of and independent from the per-category capacity count below. `agent` is this
    requester's own identity; passing the SAME agent that holds the exclusive lease is how the
    holder re-registers/heartbeats without refusing itself. The lease blocks this call only when
    it is `scope: fleet`, or its `repo` names THIS requester's own `repo` -- an ordinary
    `scope: repo` (or scope-absent) lease held on some OTHER repo never blocks this call.
    """
    own_pid = os.getpid()
    # pid_source records WHY this entry's pid should (or should not) be trusted as a liveness
    # signal: "explicit" only when the caller passed a --pid that is not the writer process's own
    # (a real, potentially long-lived process the caller vouches for); "self" when no pid was
    # supplied, or the supplied pid IS the writer's own - the short-lived process writing this
    # lock file, which will be gone long before anyone else checks it.
    pid_source = "explicit" if (pid is not None and pid != own_pid) else "self"
    pid = pid if pid is not None else own_pid
    lock_dir = resolve_lock_dir(lock_dir_override)
    cap = max_heavy_lanes if max_heavy_lanes is not None else MAX_LANES_BY_CATEGORY.get(
        category, MAX_HEAVY_LANES
    )

    if lock_dir is None:
        return LockResult(
            allowed=True,
            degraded=True,
            reason="fleet lock store unavailable (no brain.toml found / directory not writable) "
            "- degrading to advisory, same as the unenforced prose rule this replaces",
        )

    blocking_lease = _find_blocking_exclusive_lease(lock_dir, agent, repo)
    if blocking_lease is not None:
        lease_scope = blocking_lease.get("scope", "repo")
        scope_desc = (
            "fleet-wide - the fleet is quiesced"
            if lease_scope == "fleet"
            else f"scoped to repo `{blocking_lease.get('repo')}` - this repo is quiesced"
        )
        return LockResult(
            allowed=False,
            reason=(
                f"exclusive lease (scope: {lease_scope}) held on repo `{blocking_lease.get('repo')}` "
                f"by lane `{blocking_lease.get('lane')}` agent `{blocking_lease.get('agent')}` - "
                f"{scope_desc}; no register is granted until that lease is released or goes stale"
            ),
            active=[],
            # Name the lease that caused this refusal, in the SAME shape `status()` reports
            # leases in -- a caller that only reads the structured payload could otherwise not
            # say which lease blocked it (the field was left empty here, so a refusal and a
            # quiet fleet were indistinguishable in `exclusive_leases`).
            exclusive_leases=[
                f"{blocking_lease.get('repo')} (exclusive, scope `{lease_scope}`, "
                f"lane `{blocking_lease.get('lane')}`, agent `{blocking_lease.get('agent')}`)"
            ],
        )

    survivors = _sweep_stale(lock_dir, ttl_seconds)
    category_survivors = [e for e in survivors if e.get("category", "browser-automation") == category]

    # Idempotent: if this exact repo+agent (or, absent an agent, repo+pid) already holds a slot, re-registering succeeds without
    # consuming a second slot.
    own_path = _lock_path(lock_dir, repo, agent, pid)

    # Supersede, don't duplicate: an agent-keyed register for a repo that already holds an
    # OLD-SCHEME pid-keyed entry (agent: null) in this same category adopts that slot instead of
    # writing a second file beside it. Without this, one lane occupies two of the category's
    # slots -- measured as `register` leaving `probe__99999.json` AND
    # `probe__agent-probe-agent.json` where it should leave exactly one. Scoped deliberately:
    # only a null-agent entry is superseded (another agent's entry is another lane), and only
    # within this category (the same repo may legitimately hold a slot in a different one).
    if agent:
        for entry in list(category_survivors):
            if entry.get("repo") != repo or entry.get("agent") is not None:
                continue
            entry_path = entry.get("_path")
            if not entry_path or entry_path == str(own_path):
                continue
            try:
                Path(entry_path).unlink(missing_ok=True)
            except OSError:
                # Cannot remove it -- leave it in the count rather than double-book the slot.
                continue
            category_survivors.remove(entry)

    already_registered = any(entry.get("_path") == str(own_path) for entry in category_survivors)
    active_repos = [e["repo"] for e in category_survivors]

    if not already_registered and len(category_survivors) >= cap:
        return LockResult(
            allowed=False,
            reason=f"fleet at capacity for '{category}' ({len(category_survivors)}/{cap} lanes "
            f"active): {', '.join(active_repos)}",
            active=active_repos,
        )

    if not already_registered:
        own_path.write_text(
            json.dumps(
                {
                    "repo": repo,
                    "pid": pid,
                    "pid_source": pid_source,
                    "agent": agent,
                    "category": category,
                    "started_at": time.time(),
                },
                indent=2,
            )
        )
        active_repos.append(repo)
    else:
        # Idempotent-refresh: a re-register of the same repo+agent (or, absent an agent,
        # repo+pid)+category is a heartbeat, not a no-op - it bumps started_at so a long lane's
        # slot doesn't age past the TTL out from under it, and consumes no second slot.
        own_path.write_text(
            json.dumps(
                {
                    "repo": repo,
                    "pid": pid,
                    "pid_source": pid_source,
                    "agent": agent,
                    "category": category,
                    "started_at": time.time(),
                },
                indent=2,
            )
        )

    return LockResult(allowed=True, active=active_repos)


def release(
    repo: str,
    pid: Optional[int] = None,
    agent: Optional[str] = None,
    lock_dir_override: Optional[str] = None,
) -> LockResult:
    """Release `repo`'s heavy-lane slot.

    `agent`, when supplied, must match the identity `register` was called with -- `_lock_path`
    keys the entry on agent identity when one is given, which is what lets a release from a
    DIFFERENT process than the one that registered still compute the SAME on-disk path and
    actually free the slot (the measured defect this ticket fixes). Reports `removed: True` only
    when an entry genuinely existed and was deleted, never unconditionally -- the pre-fix
    behaviour of `allowed: true` regardless of whether anything was there to remove is what let a
    release-of-nothing look like a successful release.
    """
    pid = pid if pid is not None else os.getpid()
    lock_dir = resolve_lock_dir(lock_dir_override)

    if lock_dir is None:
        return LockResult(
            allowed=True,
            degraded=True,
            reason="fleet lock store unavailable - nothing to release",
        )

    own_path = _lock_path(lock_dir, repo, agent, pid)
    removed = own_path.exists()
    own_path.unlink(missing_ok=True)
    return LockResult(allowed=True, removed=removed)


def status(lock_dir_override: Optional[str] = None, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> LockResult:
    lock_dir = resolve_lock_dir(lock_dir_override)
    if lock_dir is None:
        return LockResult(
            allowed=True,
            degraded=True,
            reason="fleet lock store unavailable",
        )
    survivors = _sweep_stale(lock_dir, ttl_seconds)
    exclusive = _non_stale_exclusive_leases(lock_dir)
    return LockResult(
        allowed=True,
        active=[f"{e['repo']} ({e.get('category', 'browser-automation')})" for e in survivors],
        # Reported distinctly from `active` (ordinary heavy-lane entries) so a reader can tell
        # WHY nothing may start, per the block record's status criterion. Each entry also carries
        # its effective scope -- the authored value, or `repo` when the key is absent -- so a
        # reader can tell a fleet-quiesce hold from an ordinary same-repo hold without opening
        # the lease file (BT.ticket.exclusive-lease-refuses-every-register).
        exclusive_leases=[
            f"{e.get('repo')} (exclusive, scope `{e.get('scope', 'repo')}`, "
            f"lane `{e.get('lane')}`, agent `{e.get('agent')}`)"
            for e in exclusive
        ],
    )


def acquire_exclusive(
    lock_dir_override: Optional[str] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> LockResult:
    """Check whether it is safe to ACQUIRE a fleet-exclusive lease -- the reverse direction.

    This script does not write the lease itself (BT.6.E's lane-driver writers own that, and a
    gate that also minted its own leases would give one artifact two writers, which
    block-registration's C2 forbids). This is a pre-flight check only: a lane about to write
    `<lock_dir>/leases/lease-<repo>.json` with `kind: exclusive` calls this first, and proceeds
    to write only if `allowed` comes back true. Refusing here, rather than after the fact, is
    what keeps exclusivity pure admission control: a running ordinary lane is never pre-empted,
    only a NEW exclusive request is turned away while one is active.
    """
    lock_dir = resolve_lock_dir(lock_dir_override)
    if lock_dir is None:
        return LockResult(
            allowed=True,
            degraded=True,
            reason="fleet lock store unavailable - degrading to advisory, same as an "
            "unenforced rule",
        )

    survivors = _sweep_stale(lock_dir, ttl_seconds)
    if survivors:
        active_repos = [e["repo"] for e in survivors]
        return LockResult(
            allowed=False,
            reason=(
                f"cannot acquire a fleet-exclusive lease while {len(survivors)} ordinary "
                f"lane(s) are active: {', '.join(active_repos)} - exclusivity is admission "
                "control, never pre-emption of a lane already running"
            ),
            active=active_repos,
        )

    return LockResult(allowed=True)


def heavy_category(repo_path: str) -> Optional[str]:
    """The heavy-lane category for `repo_path`'s planning/harness.json, or None if light.

    `uiTest.enabled` and any browser-automation signal classify as "browser-automation" (checked
    first — it is the more resource-dangerous category, so a repo matching both is not
    under-counted). Otherwise a native-build signal classifies as "native-build". Neither -> None.
    """
    harness_path = Path(repo_path) / "planning" / "harness.json"
    if not harness_path.exists():
        return None
    try:
        data = json.loads(harness_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    if data.get("uiTest", {}).get("enabled"):
        return "browser-automation"

    checks = data.get("validation", {}).get("checks", [])
    commands = [str(check.get("command", "")).lower() for check in checks]

    if any(any(signal in command for signal in BROWSER_AUTOMATION_SIGNALS) for command in commands):
        return "browser-automation"

    if any(any(signal in command for signal in NATIVE_BUILD_SIGNALS) for command in commands):
        return "native-build"

    return None


def is_heavy_repo(repo_path: str) -> bool:
    """True if the target repo's planning/harness.json indicates any heavy gate (either
    category). Kept as a boolean convenience wrapper around heavy_category()."""
    return heavy_category(repo_path) is not None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    reg = sub.add_parser("register", help="Register this lane as starting a heavy repo.")
    reg.add_argument("--repo", required=True)
    reg.add_argument(
        "--category",
        choices=sorted(MAX_LANES_BY_CATEGORY),
        default="browser-automation",
        help="Heavy-lane category (capacity is counted per category, not fleet-wide). "
        "Determine via `is-heavy --repo-path`.",
    )
    reg.add_argument("--pid", type=int, default=None)
    reg.add_argument(
        "--agent",
        default=None,
        help="This requester's own agent identity. A non-stale `kind: exclusive` lease held by "
        "a DIFFERENT agent (any repo, any category) refuses this call with exit 3; a lease held "
        "by THIS agent is a re-registration/heartbeat, not a refusal.",
    )
    reg.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
    reg.add_argument("--lock-dir", default=None)
    reg.add_argument(
        "--max-heavy-lanes",
        type=int,
        default=None,
        help="Override the category's default cap (default: MAX_LANES_BY_CATEGORY[category]).",
    )

    rel = sub.add_parser("release", help="Release this lane's heavy-repo slot.")
    rel.add_argument("--repo", required=True)
    rel.add_argument("--pid", type=int, default=None)
    rel.add_argument(
        "--agent",
        default=None,
        help="This requester's own agent identity -- must match the --agent a prior register "
        "call used, so the entry it wrote can be found and actually freed.",
    )
    rel.add_argument("--lock-dir", default=None)

    stat = sub.add_parser("status", help="List active heavy lanes.")
    stat.add_argument("--lock-dir", default=None)
    stat.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)

    heavy = sub.add_parser("is-heavy", help="Check whether a repo's harness.json is heavy-gated.")
    heavy.add_argument("--repo-path", required=True)

    excl = sub.add_parser(
        "acquire-exclusive",
        help="Check (never writes) whether it is safe to acquire a fleet-exclusive lease -- "
        "refused (exit 3) while any ordinary heavy-lane entry is active.",
    )
    excl.add_argument("--lock-dir", default=None)
    excl.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.action == "register":
        result = register(
            args.repo,
            category=args.category,
            pid=args.pid,
            agent=args.agent,
            ttl_seconds=args.ttl,
            lock_dir_override=args.lock_dir,
            max_heavy_lanes=args.max_heavy_lanes,
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.allowed else 3

    if args.action == "release":
        result = release(
            args.repo, pid=args.pid, agent=args.agent, lock_dir_override=args.lock_dir
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    if args.action == "status":
        result = status(lock_dir_override=args.lock_dir, ttl_seconds=args.ttl)
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    if args.action == "is-heavy":
        category = heavy_category(args.repo_path)
        print(
            json.dumps(
                {"repo_path": args.repo_path, "heavy": category is not None, "category": category},
                indent=2,
            )
        )
        return 0 if category is not None else 1

    if args.action == "acquire-exclusive":
        result = acquire_exclusive(lock_dir_override=args.lock_dir, ttl_seconds=args.ttl)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.allowed else 3

    parser.error(f"unknown action: {args.action}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
