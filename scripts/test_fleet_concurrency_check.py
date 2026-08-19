#!/usr/bin/env python3
"""Regression tests for fleet_concurrency_check.py (item 6 of
ticket-orchestrate-command-improvements): the mechanical replacement for the unenforced
"at most two heavy-gate repos concurrently" prose rule.

Covers, per the task 5 spec: two heavy lanes registering successfully; a third refused while both
are live; a lane that exits cleanly releasing its slot; a stale (killed-lane) entry expiring rather
than blocking the fleet; graceful degradation when the lock directory is unavailable.

Run: python3 scripts/test_fleet_concurrency_check.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

_MODULE_PATH = Path(__file__).resolve().parent / "fleet_concurrency_check.py"
_spec = importlib.util.spec_from_file_location("fleet_concurrency_check", _MODULE_PATH)
fcc = importlib.util.module_from_spec(_spec)
sys.modules["fleet_concurrency_check"] = fcc
_spec.loader.exec_module(fcc)

# The tests below stand in for "another lane's process" with synthetic pids derived from
# os.getpid() (e.g. os.getpid() + 1) - values that do not correspond to a real running process.
# `_pid_running` (used by the stale-entry sweep) checks liveness via `os.kill(pid, 0)`, which is
# genuinely non-deterministic for made-up pids: whether that number happens to belong to some
# unrelated process already running on the machine depends on the OS's pid-allocation state at
# test time, not on anything the test controls. That flakiness previously surfaced as synthetic
# "still active" lanes being swept as stale mid-test (e.g. `repo-b` vanishing from `active`,
# a refused registration being wrongly allowed, or the CLI's exit code not reflecting a refusal),
# purely as a function of which pids happened to be in use on the host at the moment the suite
# ran. Only pid 999999 is ever used in this file to mean "a definitely-dead process" (see
# StaleEntryExpiry below); every other pid used here is meant to represent a still-running lane.
# Patching `_pid_running` module-wide removes the dependency on real OS process state entirely,
# while preserving every test's actual intent.
_pid_running_patch = mock.patch.object(fcc, "_pid_running", side_effect=lambda pid: pid != 999999)


def setUpModule() -> None:
    _pid_running_patch.start()


def tearDownModule() -> None:
    _pid_running_patch.stop()


class TwoLanesOk(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.lock_dir = str(Path(self._tmp.name) / "locks")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_two_heavy_lanes_register_successfully(self) -> None:
        r1 = fcc.register("repo-a", pid=os.getpid(), lock_dir_override=self.lock_dir)
        r2 = fcc.register("repo-b", pid=os.getpid() + 1, lock_dir_override=self.lock_dir)
        self.assertTrue(r1.allowed)
        self.assertFalse(r1.degraded)
        self.assertTrue(r2.allowed)
        self.assertFalse(r2.degraded)
        self.assertEqual(sorted(r2.active), ["repo-a", "repo-b"])

    def test_reregistering_same_lane_is_idempotent(self) -> None:
        pid = os.getpid()
        fcc.register("repo-a", pid=pid, lock_dir_override=self.lock_dir)
        r2 = fcc.register("repo-a", pid=pid, lock_dir_override=self.lock_dir)
        r3 = fcc.register("repo-c", pid=pid + 5, lock_dir_override=self.lock_dir)
        self.assertTrue(r2.allowed)
        self.assertTrue(r3.allowed)  # only one slot consumed by repo-a, so a second is free


class ThirdRefused(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.lock_dir = str(Path(self._tmp.name) / "locks")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_third_heavy_lane_is_refused_while_two_are_live(self) -> None:
        fcc.register("repo-a", pid=os.getpid(), lock_dir_override=self.lock_dir)
        fcc.register("repo-b", pid=os.getpid() + 1, lock_dir_override=self.lock_dir)
        r3 = fcc.register("repo-c", pid=os.getpid() + 2, lock_dir_override=self.lock_dir)
        self.assertFalse(r3.allowed)
        self.assertIn("capacity", r3.reason)
        self.assertEqual(sorted(r3.active), ["repo-a", "repo-b"])

    def test_cli_exits_3_on_refusal(self) -> None:
        fcc.register("repo-a", pid=os.getpid(), lock_dir_override=self.lock_dir)
        fcc.register("repo-b", pid=os.getpid() + 1, lock_dir_override=self.lock_dir)
        rc = fcc.main(
            [
                "register",
                "--repo",
                "repo-c",
                "--pid",
                str(os.getpid() + 2),
                "--lock-dir",
                self.lock_dir,
            ]
        )
        self.assertEqual(rc, 3)


class CleanRelease(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.lock_dir = str(Path(self._tmp.name) / "locks")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_release_frees_the_slot_for_a_new_lane(self) -> None:
        pid_a = os.getpid()
        pid_b = os.getpid() + 1
        fcc.register("repo-a", pid=pid_a, lock_dir_override=self.lock_dir)
        fcc.register("repo-b", pid=pid_b, lock_dir_override=self.lock_dir)

        rel = fcc.release("repo-a", pid=pid_a, lock_dir_override=self.lock_dir)
        self.assertTrue(rel.allowed)

        r3 = fcc.register("repo-c", pid=os.getpid() + 2, lock_dir_override=self.lock_dir)
        self.assertTrue(r3.allowed)
        self.assertEqual(sorted(r3.active), ["repo-b", "repo-c"])

    def test_release_of_unknown_lane_is_a_noop(self) -> None:
        rel = fcc.release("never-registered", pid=999999, lock_dir_override=self.lock_dir)
        self.assertTrue(rel.allowed)


class StaleEntryExpiry(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.lock_dir = str(Path(self._tmp.name) / "locks")
        Path(self.lock_dir).mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_raw_lock(
        self, repo: str, pid: int, started_at: float, pid_source: str = "self"
    ) -> None:
        path = Path(self.lock_dir) / f"{repo}__{pid}.json"
        path.write_text(
            json.dumps(
                {"repo": repo, "pid": pid, "pid_source": pid_source, "started_at": started_at}
            )
        )

    def test_explicit_dead_pid_entry_expires_and_does_not_block_the_fleet(self) -> None:
        # A pid that (almost certainly) does not correspond to a running process, EXPLICITLY
        # supplied by whatever caller wrote this entry - pid-liveness only ever applies to
        # explicit entries.
        dead_pid = 999999
        self._write_raw_lock("repo-a", dead_pid, time.time(), pid_source="explicit")
        self._write_raw_lock("repo-b", os.getpid(), time.time(), pid_source="explicit")

        # Without the sweep this would be "at capacity"; the dead entry must be swept first.
        r3 = fcc.register("repo-c", pid=os.getpid() + 1, lock_dir_override=self.lock_dir)
        self.assertTrue(r3.allowed)
        self.assertEqual(sorted(r3.active), ["repo-b", "repo-c"])

    def test_self_entry_with_dead_pid_is_NOT_swept_by_pid_liveness(self) -> None:
        # A "self" entry's pid is the short-lived writer process's own os.getpid() - it is
        # ALWAYS gone by the time a later, separate process checks it. Treating that as a
        # liveness signal is exactly the dead-on-arrival bug this model fixes: pid-liveness must
        # never apply to a "self" entry, only TTL + explicit release.
        dead_pid = 999999
        self._write_raw_lock("repo-a", dead_pid, time.time(), pid_source="self")
        self._write_raw_lock("repo-b", os.getpid(), time.time(), pid_source="self")

        # Both are within TTL and neither is "explicit", so both entries must survive the sweep -
        # the fleet is already at the 2-lane cap.
        r3 = fcc.register("repo-c", pid=os.getpid() + 1, lock_dir_override=self.lock_dir)
        self.assertFalse(r3.allowed)
        self.assertEqual(sorted(r3.active), ["repo-a", "repo-b"])

    def test_ttl_expired_entry_is_swept_even_if_pid_is_alive(self) -> None:
        # Use our own pid (definitely alive) but an ancient started_at with a tiny TTL.
        self._write_raw_lock("repo-old", os.getpid(), time.time() - 100000)
        r = fcc.register(
            "repo-new",
            pid=os.getpid() + 1,
            ttl_seconds=10,
            lock_dir_override=self.lock_dir,
        )
        self.assertTrue(r.allowed)
        self.assertEqual(r.active, ["repo-new"])

    def test_corrupt_entry_is_removed_rather_than_blocking(self) -> None:
        bad_path = Path(self.lock_dir) / "corrupt__1.json"
        bad_path.write_text("{not valid json")
        r = fcc.register("repo-a", pid=os.getpid(), lock_dir_override=self.lock_dir)
        self.assertTrue(r.allowed)
        self.assertFalse(bad_path.exists())


class GracefulDegradation(unittest.TestCase):
    def test_missing_lock_dir_env_and_no_brain_toml_degrades_to_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # A directory with no brain.toml anywhere above it (use tmp itself, which has no
            # brain.toml parents in a sane test environment) and no explicit override / env var.
            old_cwd = Path.cwd()
            old_env = os.environ.pop("FLEET_LOCK_DIR", None)
            try:
                os.chdir(tmp)
                r = fcc.register("repo-a", pid=os.getpid())
                self.assertTrue(r.allowed)
                self.assertTrue(r.degraded)
                self.assertIn("unavailable", r.reason)
            finally:
                os.chdir(old_cwd)
                if old_env is not None:
                    os.environ["FLEET_LOCK_DIR"] = old_env

    def test_unwritable_lock_dir_degrades_to_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            unwritable = Path(tmp) / "locked"
            unwritable.mkdir()
            os.chmod(unwritable, 0o400)
            try:
                r = fcc.register("repo-a", pid=os.getpid(), lock_dir_override=str(unwritable / "sub"))
                self.assertTrue(r.allowed)
                self.assertTrue(r.degraded)
            finally:
                os.chmod(unwritable, 0o700)

    def test_release_degrades_gracefully_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            old_env = os.environ.pop("FLEET_LOCK_DIR", None)
            try:
                os.chdir(tmp)
                rel = fcc.release("repo-a", pid=os.getpid())
                self.assertTrue(rel.allowed)
                self.assertTrue(rel.degraded)
            finally:
                os.chdir(old_cwd)
                if old_env is not None:
                    os.environ["FLEET_LOCK_DIR"] = old_env


class HeavyRepoDetection(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        (self.repo / "planning").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_harness(self, data: dict) -> None:
        (self.repo / "planning" / "harness.json").write_text(json.dumps(data))

    def test_ui_test_enabled_is_heavy(self) -> None:
        self._write_harness({"uiTest": {"enabled": True}, "validation": {"checks": []}})
        self.assertTrue(fcc.is_heavy_repo(str(self.repo)))
        self.assertEqual(fcc.heavy_category(str(self.repo)), "browser-automation")

    def test_playwright_check_command_is_heavy(self) -> None:
        self._write_harness(
            {
                "uiTest": {"enabled": False},
                "validation": {"checks": [{"name": "e2e", "command": "npx playwright test"}]},
            }
        )
        self.assertTrue(fcc.is_heavy_repo(str(self.repo)))
        self.assertEqual(fcc.heavy_category(str(self.repo)), "browser-automation")

    def test_docs_only_repo_is_not_heavy(self) -> None:
        self._write_harness(
            {
                "uiTest": {"enabled": False},
                "validation": {"checks": [{"name": "lint", "command": "node --check foo.js"}]},
            }
        )
        self.assertFalse(fcc.is_heavy_repo(str(self.repo)))
        self.assertIsNone(fcc.heavy_category(str(self.repo)))

    def test_missing_harness_json_is_not_heavy(self) -> None:
        self.assertFalse(fcc.is_heavy_repo(str(self.repo)))
        self.assertIsNone(fcc.heavy_category(str(self.repo)))

    def test_cargo_build_release_is_native_build_heavy(self) -> None:
        self._write_harness(
            {
                "uiTest": {"enabled": False},
                "validation": {
                    "checks": [
                        {"name": "fmt", "command": "cargo fmt --check"},
                        {"name": "clippy", "command": "cargo clippy -- -D warnings"},
                        {"name": "test", "command": "cargo nextest run --workspace"},
                        {"name": "build", "command": "cargo build --release"},
                    ]
                },
            }
        )
        self.assertTrue(fcc.is_heavy_repo(str(self.repo)))
        self.assertEqual(fcc.heavy_category(str(self.repo)), "native-build")

    def test_mixed_browser_and_native_signals_classify_browser_automation(self) -> None:
        # A repo gating on both is the more dangerous (browser-automation) category, so it
        # must not be under-counted against the smaller pool.
        self._write_harness(
            {
                "uiTest": {"enabled": False},
                "validation": {
                    "checks": [
                        {"name": "build", "command": "cargo build --release"},
                        {"name": "e2e", "command": "npx playwright test"},
                    ]
                },
            }
        )
        self.assertEqual(fcc.heavy_category(str(self.repo)), "browser-automation")


class RealFleetHarnessShapes(unittest.TestCase):
    """Classifies real harness.json files from the fleet, when present on this machine.

    Skips (rather than fails) any repo whose harness.json isn't found — these live outside this
    repo, in sibling checkouts, and their presence is environment-dependent.
    """

    _BRAIN_ROOT_CANDIDATES = [
        Path(__file__).resolve().parents[2],  # base-template/../.. -> agentic-portfolio
    ]

    def _repo_path(self, relative: str) -> Path:
        for root in self._BRAIN_ROOT_CANDIDATES:
            candidate = root / relative
            if (candidate / "planning" / "harness.json").exists():
                return candidate
        self.skipTest(f"{relative}/planning/harness.json not found on this machine")

    def test_rust_repos_classify_native_build_heavy(self) -> None:
        for relative in ("core/engine-rs", "core/bastion", "core/mev", "core/okf-core"):
            with self.subTest(repo=relative):
                repo = self._repo_path(relative)
                self.assertEqual(fcc.heavy_category(str(repo)), "native-build")

    def test_base_template_and_hq_are_light(self) -> None:
        base_template = Path(__file__).resolve().parents[1]
        self.assertIsNone(fcc.heavy_category(str(base_template)))

        hq = self._BRAIN_ROOT_CANDIDATES[0]
        if not (hq / "planning" / "harness.json").exists():
            self.skipTest("HQ planning/harness.json not found on this machine")
        self.assertIsNone(fcc.heavy_category(str(hq)))


class TieredCapacity(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.lock_dir = str(Path(self._tmp.name) / "locks")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_native_build_pool_allows_four_concurrent_lanes(self) -> None:
        results = [
            fcc.register(
                f"repo-{i}",
                category="native-build",
                pid=os.getpid() + i,
                lock_dir_override=self.lock_dir,
            )
            for i in range(4)
        ]
        self.assertTrue(all(r.allowed for r in results))

    def test_fifth_native_build_lane_is_refused(self) -> None:
        for i in range(4):
            fcc.register(
                f"repo-{i}",
                category="native-build",
                pid=os.getpid() + i,
                lock_dir_override=self.lock_dir,
            )
        r5 = fcc.register(
            "repo-5", category="native-build", pid=os.getpid() + 5, lock_dir_override=self.lock_dir
        )
        self.assertFalse(r5.allowed)
        self.assertIn("native-build", r5.reason)

    def test_native_build_and_browser_automation_pools_are_independent(self) -> None:
        # Fill the browser-automation pool (cap 2)...
        fcc.register(
            "web-a", category="browser-automation", pid=os.getpid(), lock_dir_override=self.lock_dir
        )
        fcc.register(
            "web-b",
            category="browser-automation",
            pid=os.getpid() + 1,
            lock_dir_override=self.lock_dir,
        )
        # ...a native-build lane must still be allowed, since it draws from a separate pool.
        r = fcc.register(
            "engine-rs", category="native-build", pid=os.getpid() + 2, lock_dir_override=self.lock_dir
        )
        self.assertTrue(r.allowed)

        # And a third browser-automation lane is still refused.
        r_third_web = fcc.register(
            "web-c",
            category="browser-automation",
            pid=os.getpid() + 3,
            lock_dir_override=self.lock_dir,
        )
        self.assertFalse(r_third_web.allowed)

    def test_max_heavy_lanes_override_still_works_per_category(self) -> None:
        fcc.register(
            "repo-a",
            category="native-build",
            pid=os.getpid(),
            lock_dir_override=self.lock_dir,
            max_heavy_lanes=1,
        )
        r2 = fcc.register(
            "repo-b",
            category="native-build",
            pid=os.getpid() + 1,
            lock_dir_override=self.lock_dir,
            max_heavy_lanes=1,
        )
        self.assertFalse(r2.allowed)

    def test_cli_is_heavy_reports_category(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            (repo / "planning").mkdir(parents=True)
            (repo / "planning" / "harness.json").write_text(
                json.dumps(
                    {
                        "uiTest": {"enabled": False},
                        "validation": {
                            "checks": [{"name": "build", "command": "cargo build --release"}]
                        },
                    }
                )
            )
            rc = fcc.main(["is-heavy", "--repo-path", str(repo)])
            self.assertEqual(rc, 0)

    def test_cli_register_accepts_category_flag(self) -> None:
        rc = fcc.main(
            [
                "register",
                "--repo",
                "repo-a",
                "--category",
                "native-build",
                "--pid",
                str(os.getpid()),
                "--lock-dir",
                self.lock_dir,
            ]
        )
        self.assertEqual(rc, 0)


class CrossProcessSurvival(unittest.TestCase):
    """Drives fleet_concurrency_check.py through SEPARATE subprocess invocations - the exact
    dead-on-arrival regression from planning/BT.ticket.fleet-lock-pid-liveness/sdlc/reports/
    liveness-baseline.md, now asserted as a test. A within-one-process assertion cannot see this
    bug (register and _sweep_stale share the same live os.getpid() the whole time), which is why
    the pre-fix suite passed despite the defect. Each `_run` call is its own OS process; by the
    time a later call's status/register runs, any earlier call's process has already exited.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.lock_dir = str(Path(self._tmp.name) / "locks")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(_MODULE_PATH), *args, "--lock-dir", self.lock_dir],
            capture_output=True,
            text=True,
        )

    def test_registered_lane_survives_a_later_separate_process_status_call(self) -> None:
        reg = self._run("register", "--repo", "probe-dead-on-arrival")
        self.assertEqual(reg.returncode, 0)
        reg_out = json.loads(reg.stdout)
        self.assertTrue(reg_out["allowed"])
        self.assertIn("probe-dead-on-arrival", reg_out["active"])

        # A SEPARATE, later process. The `register` process above has already exited by now, so
        # under the pre-fix model (which trusted os.getpid() of the writer as the liveness
        # signal) this entry would already be gone.
        stat = self._run("status")
        self.assertEqual(stat.returncode, 0)
        stat_out = json.loads(stat.stdout)
        self.assertTrue(any("probe-dead-on-arrival" in entry for entry in stat_out["active"]))

    def test_nplus1_registration_across_separate_processes_is_refused(self) -> None:
        r1 = self._run("register", "--repo", "cross-a")
        r2 = self._run("register", "--repo", "cross-b")
        self.assertEqual(r1.returncode, 0)
        self.assertEqual(r2.returncode, 0)

        # A third, in a THIRD separate process, while the first two lanes' registering processes
        # have both already exited - capacity must still be enforced.
        r3 = self._run("register", "--repo", "cross-c")
        self.assertEqual(r3.returncode, 3)
        r3_out = json.loads(r3.stdout)
        self.assertFalse(r3_out["allowed"])
        self.assertEqual(sorted(r3_out["active"]), ["cross-a", "cross-b"])

    def test_reregister_across_separate_processes_refreshes_heartbeat_without_new_slot(
        self,
    ) -> None:
        r1 = self._run("register", "--repo", "heartbeat-a")
        self.assertEqual(r1.returncode, 0)

        lock_files = list(Path(self.lock_dir).glob("heartbeat-a__*.json"))
        self.assertEqual(len(lock_files), 1)
        first_started_at = json.loads(lock_files[0].read_text())["started_at"]

        time.sleep(0.05)

        # Re-register the SAME repo from a different process. Since no explicit --pid was passed
        # either time, both write under the "self" pid convention this CLI uses today
        # (os.getpid() of whichever process is running) - but the lock filename is keyed on
        # repo+pid, so a genuinely different process pid would create a second file. What must
        # hold regardless is that the fleet never reports more than one active entry for this
        # repo+category, and an explicit heartbeat re-register of the same file bumps started_at.
        same_pid = json.loads(lock_files[0].read_text())["pid"]
        r2 = self._run("register", "--repo", "heartbeat-a", "--pid", str(same_pid))
        self.assertEqual(r2.returncode, 0)
        r2_out = json.loads(r2.stdout)
        self.assertEqual(r2_out["active"].count("heartbeat-a"), 1)

        second_started_at = json.loads(lock_files[0].read_text())["started_at"]
        self.assertGreater(second_started_at, first_started_at)

    def test_release_across_separate_processes_removes_exactly_its_own_entry(self) -> None:
        r1 = self._run("register", "--repo", "release-a")
        r1_out = json.loads(r1.stdout)
        lock_files = list(Path(self.lock_dir).glob("release-a__*.json"))
        self.assertEqual(len(lock_files), 1)
        pid = json.loads(lock_files[0].read_text())["pid"]

        r2 = self._run("register", "--repo", "release-b")
        self.assertEqual(r2.returncode, 0)

        rel = self._run("release", "--repo", "release-a", "--pid", str(pid))
        self.assertEqual(rel.returncode, 0)
        self.assertFalse((Path(self.lock_dir) / f"release-a__{pid}.json").exists())

        stat = self._run("status")
        stat_out = json.loads(stat.stdout)
        self.assertTrue(any("release-b" in entry for entry in stat_out["active"]))
        self.assertFalse(any("release-a" in entry for entry in stat_out["active"]))


if __name__ == "__main__":
    unittest.main()
