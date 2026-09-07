#!/usr/bin/env python3
"""Fixture suite for check_repo_lease.py (BT.ticket.the-repo-lease-stops-nobody).

Self-contained, no pytest dependency, matching the fixture style of test_check_lane_agents.py:
builds a synthetic lock-dir corpus inside a `tempfile.TemporaryDirectory()` per case (NEVER the
real `.fleet-locks`) and drives the real check_repo_lease.py module against it, both by calling
its functions directly and by running it as a subprocess against `--lock-dir`, so both the
warning logic and the CLI/exit-code contract are exercised.

Covers the five cases named in the block record's testing strategy:
    (a) no lease file at all
    (b) the caller's OWN lease
    (c) another agent's FRESH exclusive lease
    (d) another agent's STALE exclusive lease
    (e) an unreadable / unparseable store -- empty file, malformed JSON, a lease path that is a
        directory, and (where permission bits are meaningful on this OS) an unreadable file

Every case in every category asserts EXIT CODE 0 -- including (e). Failing closed there is the
one outcome that would make this check worse than nothing (BT.ticket.the-repo-lease-stops-nobody
AC2); that assertion is explicit and named in the failure message below, not merely implied by an
absent crash.

--- Observed firing (BT.ticket.gates-must-be-observed-red AC3), recorded 2026-09-07 ---

Run by hand against a fixture lock dir holding another agent's fresh exclusive lease (repo
`base-template`, holder `base-template-zz`, lane `lane-observed-firing`, heartbeat 3 minutes old,
a lane-agent registry record naming `current_block: BT.ticket.some-other-block`), caller identity
`base-template-caller`:

    $ python3 scripts/check_repo_lease.py --lock-dir <tmp> --repo base-template \
          --agent base-template-caller
    ========================================================================
    WARNING: repo `base-template` has an EXCLUSIVE LEASE held by ANOTHER agent
    ========================================================================
      holder:         base-template-zz
      lane:           lane-observed-firing
      heartbeat age:  3m
      current block:  BT.ticket.some-other-block
    This is a WARNING, not a block -- the repo lease is advisory. Nothing enforces it at commit
    time; proceeding is permitted, but the tree may move underneath you.
    ========================================================================
    $ echo $?
    0

That is the literal captured output, not a paraphrase -- a warning never seen firing is
decoration. `test_another_agent_fresh_lease_warns` below reproduces the same fixture shape and
asserts on the same substrings.

Run: python3 scripts/test_check_repo_lease.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "check_repo_lease.py"

_spec = importlib.util.spec_from_file_location("check_repo_lease", MODULE_PATH)
check_repo_lease = importlib.util.module_from_spec(_spec)
sys.modules["check_repo_lease"] = check_repo_lease
_spec.loader.exec_module(check_repo_lease)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _valid_lease(**overrides) -> dict:
    record = {
        "repo": "base-template",
        "lane": "lane-observed-firing",
        "agent": "base-template-zz",
        "acquired_at": _iso(_now() - timedelta(minutes=20)),
        "heartbeat": _iso(_now() - timedelta(minutes=3)),
        "kind": "exclusive",
    }
    record.update(overrides)
    return record


def _run_cli(lock_dir: Path, repo: str = "base-template", agent: str = "base-template-caller",
             extra_args: list | None = None) -> subprocess.CompletedProcess:
    args = [
        sys.executable, str(MODULE_PATH),
        "--lock-dir", str(lock_dir),
        "--repo", repo,
        "--agent", agent,
    ]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(args, capture_output=True, text=True)


# --- (a) no lease file at all ------------------------------------------------------------------

def test_no_lease_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_dir = Path(tmp)
        (lock_dir / "leases").mkdir(parents=True)
        result = _run_cli(lock_dir)
        check("no-lease: exits 0", result.returncode == 0, f"exit={result.returncode}")
        check("no-lease: no warning printed", result.stdout.strip() == "",
              f"stdout={result.stdout!r}")

    # Also cover a lock dir that does not exist at all (not even a `leases/` subdir).
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "does-not-exist"
        result = _run_cli(missing)
        check("missing-lock-dir: exits 0", result.returncode == 0, f"exit={result.returncode}")
        check("missing-lock-dir: no warning printed", result.stdout.strip() == "",
              f"stdout={result.stdout!r}")


# --- (b) the caller's own lease --------------------------------------------------------------

def test_own_lease_silent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_dir = Path(tmp)
        lease = _valid_lease(agent="base-template-caller")
        _write_json(lock_dir / "leases" / "lease-base-template.json", lease)
        result = _run_cli(lock_dir, agent="base-template-caller")
        check("own-lease: exits 0", result.returncode == 0, f"exit={result.returncode}")
        check("own-lease: no warning printed", result.stdout.strip() == "",
              f"stdout={result.stdout!r}")


# --- (c) another agent's fresh exclusive lease -------------------------------------------------

def test_another_agent_fresh_lease_warns() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_dir = Path(tmp)
        lease = _valid_lease()
        _write_json(lock_dir / "leases" / "lease-base-template.json", lease)
        _write_json(
            lock_dir / "lane-agents" / "agent-base-template-zz.json",
            {
                "agent_name": "base-template-zz",
                "repo": "base-template",
                "lane": "lane-observed-firing",
                "current_block": "BT.ticket.some-other-block",
                "started_at": _iso(_now() - timedelta(minutes=20)),
                "heartbeat": _iso(_now() - timedelta(minutes=3)),
            },
        )
        result = _run_cli(lock_dir)
        check("fresh-foreign-lease: exits 0", result.returncode == 0, f"exit={result.returncode}")
        out = result.stdout
        check("fresh-foreign-lease: names holder", "base-template-zz" in out, out)
        check("fresh-foreign-lease: names lane", "lane-observed-firing" in out, out)
        check("fresh-foreign-lease: names heartbeat age", "heartbeat age" in out, out)
        check("fresh-foreign-lease: names current block", "BT.ticket.some-other-block" in out, out)
        check("fresh-foreign-lease: states advisory", "advisory" in out, out)


# --- (d) another agent's stale exclusive lease -------------------------------------------------

def test_another_agent_stale_lease_warns() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_dir = Path(tmp)
        lease = _valid_lease(
            agent="base-template-stale-holder",
            lane="lane-long-gone",
            acquired_at=_iso(_now() - timedelta(hours=6)),
            heartbeat=_iso(_now() - timedelta(hours=5)),
        )
        _write_json(lock_dir / "leases" / "lease-base-template.json", lease)
        result = _run_cli(lock_dir)
        check("stale-foreign-lease: exits 0", result.returncode == 0, f"exit={result.returncode}")
        out = result.stdout
        check("stale-foreign-lease: names holder", "base-template-stale-holder" in out, out)
        check("stale-foreign-lease: names lane", "lane-long-gone" in out, out)
        check("stale-foreign-lease: names heartbeat age", "heartbeat age" in out, out)
        check("stale-foreign-lease: reports hours-scale age", "h" in out.split("heartbeat age:")[1].splitlines()[0], out)
        check("stale-foreign-lease: states advisory", "advisory" in out, out)


# --- (e) unreadable / unparseable store, never fails closed ------------------------------------

def test_empty_lease_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_dir = Path(tmp)
        _write(lock_dir / "leases" / "lease-base-template.json", "")
        result = _run_cli(lock_dir)
        check("empty-file: exits 0 (never fails closed)", result.returncode == 0,
              f"exit={result.returncode}")
        check("empty-file: no warning printed", result.stdout.strip() == "",
              f"stdout={result.stdout!r}")


def test_malformed_json_lease_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_dir = Path(tmp)
        _write(lock_dir / "leases" / "lease-base-template.json", "{not valid json,,,")
        result = _run_cli(lock_dir)
        check("malformed-json: exits 0 (never fails closed)", result.returncode == 0,
              f"exit={result.returncode}")
        check("malformed-json: no warning printed", result.stdout.strip() == "",
              f"stdout={result.stdout!r}")


def test_lease_path_is_a_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_dir = Path(tmp)
        lease_path = lock_dir / "leases" / "lease-base-template.json"
        lease_path.mkdir(parents=True)
        result = _run_cli(lock_dir)
        check("lease-is-directory: exits 0 (never fails closed)", result.returncode == 0,
              f"exit={result.returncode}")
        check("lease-is-directory: no warning printed", result.stdout.strip() == "",
              f"stdout={result.stdout!r}")


def test_lease_missing_agent_field() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lock_dir = Path(tmp)
        lease = _valid_lease()
        del lease["agent"]
        _write_json(lock_dir / "leases" / "lease-base-template.json", lease)
        result = _run_cli(lock_dir)
        check("lease-missing-agent: exits 0 (never fails closed)", result.returncode == 0,
              f"exit={result.returncode}")
        check("lease-missing-agent: no warning printed (can't attribute)", result.stdout.strip() == "",
              f"stdout={result.stdout!r}")


def test_unreadable_lease_file() -> None:
    if os.name != "posix" or os.geteuid() == 0:
        check("unreadable-file: skipped (non-posix or running as root)", True)
        return
    with tempfile.TemporaryDirectory() as tmp:
        lock_dir = Path(tmp)
        lease_path = lock_dir / "leases" / "lease-base-template.json"
        _write_json(lease_path, _valid_lease())
        os.chmod(lease_path, 0o000)
        try:
            result = _run_cli(lock_dir)
            check("unreadable-file: exits 0 (never fails closed)", result.returncode == 0,
                  f"exit={result.returncode}")
            check("unreadable-file: no warning printed", result.stdout.strip() == "",
                  f"stdout={result.stdout!r}")
        finally:
            os.chmod(lease_path, 0o644)


def test_no_lock_dir_resolved() -> None:
    """Direct call (not CLI) with lock_dir=None, mirroring what happens when neither --lock-dir
    nor FLEET_LOCK_DIR is set and no brain.toml is found walking up from cwd."""
    message = check_repo_lease.check_repo_lease(None, "base-template", "base-template-caller")
    check("no-lock-dir-resolved: returns empty string, never raises", message == "", repr(message))


def main() -> int:
    test_no_lease_file()
    test_own_lease_silent()
    test_another_agent_fresh_lease_warns()
    test_another_agent_stale_lease_warns()
    test_empty_lease_file()
    test_malformed_json_lease_file()
    test_lease_path_is_a_directory()
    test_lease_missing_agent_field()
    test_unreadable_lease_file()
    test_no_lock_dir_resolved()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
