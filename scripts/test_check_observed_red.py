#!/usr/bin/env python3
"""Fixture suite for check_observed_red.py (BT.ticket.gates-must-be-observed-red).

Self-contained, no pytest dependency, matching the fixture style of test_check_escalations.py /
test_check_lane_agents.py: a `check(label, condition, detail)` helper printing `[PASS]`/`[FAIL]`,
a `FAILURES` list gating the exit code, and `importlib.util` loading of the module under test.

Every case builds a THROWAWAY harness.json in a temp dir -- this suite never reads this repo's
own live `planning/harness.json`, so it stays independent of the backfill (tasks 3-5) and must
pass identically before and after it.

Cases (per the block's task-2 description):
  (a) a gates:true check with a valid observed_red passes
  (b) a gates:true check with no observed_red fails
  (c) a gates:false check with no observed_red passes
  (d) empty/whitespace evidence fails
  (e) a malformed date fails
  (f) the detector flags its own inline known-bad self-probe
  (g) POSITIVE CONTROL: a fixture that MUST go red does go red (subprocess/CLI exit-code path),
      so an all-green run can never be mistaken for a suite that cannot fail.

TRAP (re-confirmed twice in this ticket's source run): a piped command's exit code is the
pipe's, not the subprocess's. Every subprocess call here reads `proc.returncode` directly --
never a shell pipe whose `$?` would report the pipe's own exit status instead.

Run: python3 scripts/test_check_observed_red.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "check_observed_red.py"

_spec = importlib.util.spec_from_file_location("check_observed_red", MODULE_PATH)
check_observed_red = importlib.util.module_from_spec(_spec)
sys.modules["check_observed_red"] = check_observed_red
_spec.loader.exec_module(check_observed_red)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def _valid_observed_red(**overrides) -> dict:
    record = {
        "date": "2026-09-02",
        "evidence": "ran `python3 scripts/known_bad.py`; it printed FAIL as expected",
        "note": "provoked with a malformed fixture",
    }
    record.update(overrides)
    return record


def _gated_check(name: str = "some-check", **overrides) -> dict:
    check_dict = {
        "name": name,
        "command": f"python3 scripts/{name}.py",
        "purpose": "a fixture check",
        "gates": True,
    }
    check_dict.update(overrides)
    return check_dict


def _write_harness(tmp_path: Path, checks: list[dict]) -> Path:
    harness_path = tmp_path / "harness.json"
    harness_path.write_text(
        json.dumps({"validation": {"checks": checks}}, indent=2),
        encoding="utf-8",
    )
    return harness_path


def _run_cli(harness_path: Path, quiet: bool = True) -> subprocess.CompletedProcess:
    args = [sys.executable, str(MODULE_PATH), "--harness", str(harness_path)]
    if quiet:
        args.append("--quiet")
    return subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True)


def main() -> int:
    # (a) a gates:true check with a valid observed_red passes.
    check_a = _gated_check("check-a", observed_red=_valid_observed_red())
    detail_a = check_observed_red.evaluate_check(check_a)
    check("(a) valid observed_red on gates:true check conforms", detail_a is None, str(detail_a))

    # (b) a gates:true check with no observed_red fails.
    check_b = _gated_check("check-b")
    detail_b = check_observed_red.evaluate_check(check_b)
    check("(b) missing observed_red on gates:true check fails", detail_b is not None)

    # (c) a gates:false check with no observed_red passes.
    check_c = _gated_check("check-c", gates=False)
    detail_c = check_observed_red.evaluate_check(check_c)
    check("(c) gates:false check with no observed_red conforms", detail_c is None, str(detail_c))

    # (d) empty/whitespace evidence fails.
    check_d1 = _gated_check("check-d1", observed_red=_valid_observed_red(evidence=""))
    detail_d1 = check_observed_red.evaluate_check(check_d1)
    check("(d) empty evidence fails", detail_d1 is not None)

    check_d2 = _gated_check("check-d2", observed_red=_valid_observed_red(evidence="   \n\t "))
    detail_d2 = check_observed_red.evaluate_check(check_d2)
    check("(d) whitespace-only evidence fails", detail_d2 is not None)

    # (e) a malformed date fails.
    check_e1 = _gated_check("check-e1", observed_red=_valid_observed_red(date="09-02-2026"))
    detail_e1 = check_observed_red.evaluate_check(check_e1)
    check("(e) malformed date (wrong format) fails", detail_e1 is not None)

    check_e2 = _gated_check("check-e2", observed_red=_valid_observed_red(date="2026-9-2"))
    detail_e2 = check_observed_red.evaluate_check(check_e2)
    check("(e) malformed date (unpadded) fails", detail_e2 is not None)

    check_e3 = _gated_check("check-e3", observed_red=_valid_observed_red(date="not-a-date"))
    detail_e3 = check_observed_red.evaluate_check(check_e3)
    check("(e) malformed date (nonsense) fails", detail_e3 is not None)

    # (f) the detector flags its own inline known-bad self-probe.
    self_probe_detail = check_observed_red.evaluate_check(check_observed_red.SELF_PROBE_CHECK)
    check(
        "(f) detector flags its own inline known-bad self-probe",
        self_probe_detail is not None,
        "SELF_PROBE_CHECK (gates:true, no observed_red) was reported as conforming",
    )
    # And the self-probe fixture itself is gates:true with no observed_red key, i.e. genuinely
    # the same shape as case (b) -- pin that so the fixture can't quietly drift into something
    # that no longer resembles a known-bad input.
    check(
        "(f) self-probe fixture is gates:true with no observed_red",
        check_observed_red.SELF_PROBE_CHECK.get("gates") is True
        and "observed_red" not in check_observed_red.SELF_PROBE_CHECK,
    )

    # run() end-to-end: self-probe passes silently (no GATE BUG) when driven against a harness
    # whose only check is fully conforming -- confirms the self-probe doesn't itself corrupt a
    # clean run.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        clean_harness = _write_harness(tmp_path, [_gated_check("clean-check",
                                                                 observed_red=_valid_observed_red())])
        exit_code_clean = check_observed_red.run(clean_harness, quiet=True)
        check("clean harness (one conforming gates:true check) exits 0", exit_code_clean == 0)

        # (g) POSITIVE CONTROL: a fixture that MUST go red does go red, via the real CLI/exit-code
        # path (subprocess), not just the in-process evaluate_check() helper -- proves the whole
        # gate -- argument parsing, file read, exit code -- can actually fail, not merely agree.
        bad_harness = _write_harness(tmp_path, [_gated_check("bad-check")])  # no observed_red
        proc_bad = _run_cli(bad_harness)
        check(
            "(g) positive control: known-bad harness exits 1 via CLI",
            proc_bad.returncode == 1,
            f"returncode={proc_bad.returncode} stdout={proc_bad.stdout!r}",
        )
        check(
            "(g) positive control: CLI prints a FAIL <path> line naming the bad check",
            f"FAIL {bad_harness}" in proc_bad.stdout and "bad-check" in proc_bad.stdout,
            proc_bad.stdout,
        )

        # And the CLI/exit-code path also confirms a fully-conforming harness exits 0 -- this is
        # what makes (g)'s red result meaningful rather than "this CLI always exits 1".
        good_harness = _write_harness(tmp_path, [_gated_check("good-check",
                                                                observed_red=_valid_observed_red())])
        proc_good = _run_cli(good_harness)
        check(
            "conforming harness exits 0 via CLI",
            proc_good.returncode == 0,
            f"returncode={proc_good.returncode} stdout={proc_good.stdout!r}",
        )

        # A harness mixing a conforming gates:false check (no observed_red, case c) alongside a
        # conforming gates:true check must still exit 0 -- gates:false must never be penalized.
        mixed_harness = _write_harness(tmp_path, [
            _gated_check("mixed-gated", observed_red=_valid_observed_red()),
            _gated_check("mixed-ungated", gates=False),
        ])
        proc_mixed = _run_cli(mixed_harness)
        check(
            "mixed harness (gates:false check has no observed_red) still exits 0",
            proc_mixed.returncode == 0,
            f"returncode={proc_mixed.returncode} stdout={proc_mixed.stdout!r}",
        )

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1

    print("\nall cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
