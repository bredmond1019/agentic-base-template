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
- **Clean release**: `release` removes exactly the lock file this repo+pid registered. A lane that
  exits cleanly should always call this; a lane that dies without calling it is caught by TTL
  expiry (or, for an explicit pid, liveness) on the next registration attempt instead. A long lane
  should re-register periodically as a heartbeat — `register` is idempotent-refresh, so a
  re-register of the same repo+pid+category bumps `started_at` instead of consuming a second slot.
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
  python3 scripts/fleet_concurrency_check.py register --repo <name> [--pid PID] [--ttl SECONDS] [--lock-dir DIR]
  python3 scripts/fleet_concurrency_check.py release  --repo <name> [--pid PID] [--lock-dir DIR]
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


def _safe_repo_name(repo: str) -> str:
    """Filesystem-safe stand-in for a repo name used in a lock filename."""
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in repo)


@dataclass
class LockResult:
    allowed: bool
    degraded: bool = False
    reason: str = ""
    active: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "degraded": self.degraded,
            "reason": self.reason,
            "active": self.active,
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


def _lock_path(lock_dir: Path, repo: str, pid: int) -> Path:
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


def register(
    repo: str,
    category: str = "browser-automation",
    pid: Optional[int] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    lock_dir_override: Optional[str] = None,
    max_heavy_lanes: Optional[int] = None,
) -> LockResult:
    """Register `repo` as an active heavy lane in `category`.

    Capacity is counted per category, not fleet-wide: a native-build lane never competes for a
    slot with a browser-automation lane. `max_heavy_lanes`, if given, overrides
    MAX_LANES_BY_CATEGORY[category]; otherwise the category's own default applies.
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

    survivors = _sweep_stale(lock_dir, ttl_seconds)
    category_survivors = [e for e in survivors if e.get("category", "browser-automation") == category]

    # Idempotent: if this exact repo+pid already holds a slot, re-registering succeeds without
    # consuming a second slot.
    own_path = _lock_path(lock_dir, repo, pid)
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
                    "category": category,
                    "started_at": time.time(),
                },
                indent=2,
            )
        )
        active_repos.append(repo)
    else:
        # Idempotent-refresh: a re-register of the same repo+pid+category is a heartbeat, not a
        # no-op - it bumps started_at so a long lane's slot doesn't age past the TTL out from
        # under it.
        own_path.write_text(
            json.dumps(
                {
                    "repo": repo,
                    "pid": pid,
                    "pid_source": pid_source,
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
    lock_dir_override: Optional[str] = None,
) -> LockResult:
    pid = pid if pid is not None else os.getpid()
    lock_dir = resolve_lock_dir(lock_dir_override)

    if lock_dir is None:
        return LockResult(
            allowed=True,
            degraded=True,
            reason="fleet lock store unavailable - nothing to release",
        )

    own_path = _lock_path(lock_dir, repo, pid)
    own_path.unlink(missing_ok=True)
    return LockResult(allowed=True)


def status(lock_dir_override: Optional[str] = None, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> LockResult:
    lock_dir = resolve_lock_dir(lock_dir_override)
    if lock_dir is None:
        return LockResult(
            allowed=True,
            degraded=True,
            reason="fleet lock store unavailable",
        )
    survivors = _sweep_stale(lock_dir, ttl_seconds)
    return LockResult(
        allowed=True,
        active=[f"{e['repo']} ({e.get('category', 'browser-automation')})" for e in survivors],
    )


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
    rel.add_argument("--lock-dir", default=None)

    stat = sub.add_parser("status", help="List active heavy lanes.")
    stat.add_argument("--lock-dir", default=None)
    stat.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)

    heavy = sub.add_parser("is-heavy", help="Check whether a repo's harness.json is heavy-gated.")
    heavy.add_argument("--repo-path", required=True)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.action == "register":
        result = register(
            args.repo,
            category=args.category,
            pid=args.pid,
            ttl_seconds=args.ttl,
            lock_dir_override=args.lock_dir,
            max_heavy_lanes=args.max_heavy_lanes,
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.allowed else 3

    if args.action == "release":
        result = release(args.repo, pid=args.pid, lock_dir_override=args.lock_dir)
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

    parser.error(f"unknown action: {args.action}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
