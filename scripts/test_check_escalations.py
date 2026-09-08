#!/usr/bin/env python3
"""Fixture suite for check_escalations.py (scripted-liaison-sweep, block 2).

Self-contained, no pytest dependency, matching the fixture style of test_check_messages.py:
builds a synthetic `planning/roadmaps/<roadmap>/escalations.jsonl` corpus in a temp dir (never
the real corpus), and drives the real check_escalations.py module against it, both by calling its
functions directly (check_escalation_record) and by running it as a subprocess against
`--roadmaps-dir`, so both the validation logic and the CLI/exit-code contract are exercised.

Never touches the real corpus, never runs git against the real repo, never sends anything.

Covers: one positive round-trip per `kind` value, one negative fixture per failure mode listed in
the block record (unknown kind, unknown severity, malformed channel, missing required field,
summary over 1024 chars, a bare-adjective verified_by, field creep via priority/urgency,
malformed JSON on a line, verified_at_sha absent or not a plausible short SHA), and a positive
control proving the validator CAN fail (a corpus that must go red, showing failure is observable
before the corpus is claimed clean).

Run: python3 scripts/test_check_escalations.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "check_escalations.py"

_spec = importlib.util.spec_from_file_location("check_escalations", MODULE_PATH)
check_escalations = importlib.util.module_from_spec(_spec)
sys.modules["check_escalations"] = check_escalations
_spec.loader.exec_module(check_escalations)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def _valid_record(kind: str, **overrides) -> dict:
    """A full, valid escalation record for `kind`, grounded in begin-orchestration.md Rule 6's
    'what you still must not decide alone' list. `operator-gate`, `bail`, `disagreement`, and
    `cross-repo-edit` each map to one of that list's four cases; `interrupt-request` and
    `finding` do not come from that list."""
    bodies = {
        "operator-gate": (
            "BA.21.A needs an operator call on whether the data-contract bump is backward-"
            "compatible enough to skip a migration."
        ),
        "bail": "BA.14.C bailed: the spec's validation_command references a file deleted upstream.",
        "disagreement": (
            "bastion-c4 and engine-rs-b2 disagree about whether BA.21.A's contract bump is "
            "backward compatible -- adjudication needed."
        ),
        "cross-repo-edit": (
            "bastion-c4's lane needs a change in engine-rs's data-contract.md that bastion does "
            "not own -- pinging the owning lane rather than deciding it alone."
        ),
        "interrupt-request": (
            "A P0 defect surfaced mid-run in bastion-c4's lane; requesting an interrupt of the "
            "in-flight block to adopt it."
        ),
        "finding": (
            "roadmap_status_discovery.py currently has zero references to lease, queue, or "
            "validate-brain -- worth a block, not yet escalated."
        ),
    }
    record = {
        "ts_utc": "2026-08-26T03:10:00Z",
        "repo": "bastion",
        "lane": "d62-downstream-check",
        "kind": kind,
        "severity": "blocking",
        "block": "BA.21.A",
        "channel": "session:bastion-d62-gate",
        "gate_id": "autonomous-foundation/bastion/BA.21.A",
        "summary": bodies[kind],
        "verified_by": "UNVERIFIED: relayed from bastion-c4 lane close notice",
        "durable_home": {
            "channel": "run-record",
            "ref": "bastion/planning/orchestration-run/autonomous-foundation/notes.md#ba-21-a-gate",
        },
        "verified_at_sha": "fbda55a1",
        "clears_when": None,
    }
    record.update(overrides)
    return record


def _write_jsonl(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _run_cli(roadmaps_dir: Path, extra: list[str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), "--roadmaps-dir", str(roadmaps_dir), "--quiet",
         *(extra or [])],
        capture_output=True, text=True,
    )


# --- dependency hygiene ----------------------------------------------------------------------

def check_dependency_free() -> None:
    import ast

    tree = ast.parse(MODULE_PATH.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    stdlib_and_local = {
        "argparse", "json", "re", "sys", "pathlib", "typing", "__future__", "check_escalations",
    }
    third_party = imported - stdlib_and_local
    check("check_escalations.py imports no third-party package (no jsonschema)",
          third_party == set(), f"unexpected imports: {sorted(third_party)}")


# --- positive: one round-trip per kind --------------------------------------------------------

def check_positive_round_trip_per_kind() -> None:
    for kind in ("operator-gate", "bail", "disagreement", "cross-repo-edit", "interrupt-request",
                 "finding"):
        problems = check_escalations.check_escalation_record(_valid_record(kind))
        check(f"a valid {kind} escalation round-trips with no problems",
              problems == [], f"problems: {problems}")


# --- negative: unknown kind ---------------------------------------------------------------------

def check_negative_unknown_kind() -> None:
    record = _valid_record("operator-gate")
    record["kind"] = "URGENT_PING"
    problems = check_escalations.check_escalation_record(record)
    check("an unknown `kind` value is rejected",
          any("kind" in p and "URGENT_PING" in p for p in problems), f"problems: {problems}")


# --- negative: unknown severity ------------------------------------------------------------------

def check_negative_unknown_severity() -> None:
    record = _valid_record("finding", severity="urgent")
    problems = check_escalations.check_escalation_record(record)
    check("an unknown `severity` value is rejected",
          any("severity" in p and "urgent" in p for p in problems), f"problems: {problems}")


# --- negative: malformed channel -----------------------------------------------------------------

def check_negative_malformed_channel() -> None:
    record = _valid_record("operator-gate", channel="urgent-ping")
    problems = check_escalations.check_escalation_record(record)
    check("a `channel` not matching `^(notification|session:.+)$` is rejected",
          any("channel" in p for p in problems), f"problems: {problems}")

    empty_session = _valid_record("bail", channel="session:")
    empty_problems = check_escalations.check_escalation_record(empty_session)
    check("`channel: session:` with an empty slug is rejected",
          any("channel" in p for p in empty_problems), f"problems: {empty_problems}")


# --- negative: missing required field (one representative + a sweep) ----------------------------

def check_negative_missing_required_field() -> None:
    for field in check_escalations.ESCALATION_REQUIRED:
        record = _valid_record("finding")
        del record[field]
        problems = check_escalations.check_escalation_record(record)
        check(f"an escalation missing required field `{field}` is rejected",
              any(field in p for p in problems), f"problems: {problems}")


# --- negative: summary over 1024 chars -----------------------------------------------------------

def check_negative_summary_too_long() -> None:
    record = _valid_record("finding", summary="x" * 1025)
    problems = check_escalations.check_escalation_record(record)
    check("a `summary` over 1024 chars is rejected",
          any("summary" in p and "1024" in p for p in problems), f"problems: {problems}")

    boundary = _valid_record("finding", summary="x" * 1024)
    boundary_problems = check_escalations.check_escalation_record(boundary)
    check("a `summary` at exactly 1024 chars is accepted",
          boundary_problems == [], f"problems: {boundary_problems}")


# --- negative: bare-adjective verified_by --------------------------------------------------------

def check_negative_bare_adjective_verified_by() -> None:
    record = _valid_record("finding", verified_by="measured")
    problems = check_escalations.check_escalation_record(record)
    check("a bare adjective `verified_by` such as 'measured' fails validation",
          any("verified_by" in p for p in problems), f"problems: {problems}")

    command_and_output = _valid_record(
        "finding",
        verified_by="$ grep -c lease base-template/scripts/roadmap_status_discovery.py\n0",
    )
    ok_problems = check_escalations.check_escalation_record(command_and_output)
    check("a `verified_by` carrying a command and its real output validates",
          ok_problems == [], f"problems: {ok_problems}")


# --- negative: field creep (priority / urgency) --------------------------------------------------

def check_negative_field_creep() -> None:
    record = _valid_record("operator-gate")
    record["priority"] = "P0"
    problems = check_escalations.check_escalation_record(record)
    check("an escalation carrying `priority` is rejected, naming D43",
          any("priority" in p and "D43" in p for p in problems), f"problems: {problems}")

    nested = _valid_record("disagreement")
    nested["durable_home"]["urgency"] = "high"
    nested_problems = check_escalations.check_escalation_record(nested)
    check("`urgency` nested inside `durable_home` is also rejected, naming D43",
          any("urgency" in p and "D43" in p for p in nested_problems),
          f"problems: {nested_problems}")


# --- host: additive optional field (BT.8.A task 2) ----------------------------------------------

def check_host_field_accepted() -> None:
    record = _valid_record("finding", host="mac-mini-01")
    problems = check_escalations.check_escalation_record(record)
    check("an escalation carrying `host` validates green",
          problems == [], f"problems: {problems}")


def check_hostt_field_rejected() -> None:
    record = _valid_record("finding", hostt="mac-mini-01")
    problems = check_escalations.check_escalation_record(record)
    check("an escalation carrying `hostt` (typo) is rejected as an unknown key",
          any("unknown key" in p and "hostt" in p for p in problems), f"problems: {problems}")


# --- negative: malformed JSON on a line -----------------------------------------------------------

def check_negative_malformed_json_line() -> None:
    with tempfile.TemporaryDirectory() as td:
        roadmaps_dir = Path(td) / "roadmaps"
        path = roadmaps_dir / "autonomous-foundation" / "escalations.jsonl"
        path.parent.mkdir(parents=True)
        good = _valid_record("finding")
        with open(path, "w") as fh:
            fh.write(json.dumps(good) + "\n")
            fh.write("{not valid json\n")

        proc = _run_cli(roadmaps_dir)
        check("a corpus with one malformed JSON line makes the CLI exit non-zero",
              proc.returncode != 0, proc.stdout + proc.stderr)
        check("the failure names the parse error and its line number",
              "does not parse" in proc.stdout or "does not parse" in proc.stderr,
              proc.stdout + proc.stderr)
        check("the failure cites line 2, not line 1 (one bad line does not hide the report of "
              "which line it is)",
              ":2" in proc.stdout or ":2" in proc.stderr, proc.stdout + proc.stderr)


# --- negative: verified_at_sha absent or malformed -------------------------------------------------

def check_negative_verified_at_sha() -> None:
    missing = _valid_record("finding")
    del missing["verified_at_sha"]
    problems = check_escalations.check_escalation_record(missing)
    check("an escalation missing `verified_at_sha` is rejected",
          any("verified_at_sha" in p for p in problems), f"problems: {problems}")

    too_short = _valid_record("finding", verified_at_sha="abc")
    short_problems = check_escalations.check_escalation_record(too_short)
    check("a `verified_at_sha` shorter than 7 hex chars is rejected",
          any("verified_at_sha" in p for p in short_problems), f"problems: {short_problems}")

    not_hex = _valid_record("finding", verified_at_sha="zzzzzzz")
    not_hex_problems = check_escalations.check_escalation_record(not_hex)
    check("a `verified_at_sha` with non-hex characters is rejected",
          any("verified_at_sha" in p for p in not_hex_problems), f"problems: {not_hex_problems}")

    valid_sha = _valid_record("finding", verified_at_sha="fbda55a1abc")
    valid_problems = check_escalations.check_escalation_record(valid_sha)
    check("a plausible 11-char short SHA is accepted",
          valid_problems == [], f"problems: {valid_problems}")


# --- positive control: prove the validator CAN fail via the CLI ----------------------------------

def check_positive_control_cli_can_fail() -> None:
    with tempfile.TemporaryDirectory() as td:
        roadmaps_dir = Path(td) / "roadmaps"
        bad = _valid_record("operator-gate")
        bad["kind"] = "URGENT_PING"
        _write_jsonl(roadmaps_dir / "autonomous-foundation" / "escalations.jsonl", [bad])

        proc = _run_cli(roadmaps_dir)
        check("POSITIVE CONTROL: a deliberately-broken record makes the CLI exit non-zero -- "
              "proves the validator CAN fail, so the clean-corpus result below is trustworthy",
              proc.returncode != 0, proc.stdout + proc.stderr)


# --- CLI: a clean multi-kind corpus is accepted ---------------------------------------------------

def check_cli_accepts_clean_corpus() -> None:
    with tempfile.TemporaryDirectory() as td:
        roadmaps_dir = Path(td) / "roadmaps"
        records = [_valid_record(k) for k in
                   ("operator-gate", "bail", "disagreement", "cross-repo-edit",
                    "interrupt-request", "finding")]
        _write_jsonl(roadmaps_dir / "autonomous-foundation" / "escalations.jsonl", records)

        proc = _run_cli(roadmaps_dir)
        check("a clean, multi-kind escalations.jsonl exits 0",
              proc.returncode == 0, proc.stdout + proc.stderr)


# --- no records is not a failure ------------------------------------------------------------------

def check_no_records_is_not_a_failure() -> None:
    with tempfile.TemporaryDirectory() as td:
        roadmaps_dir = Path(td) / "roadmaps"
        proc = _run_cli(roadmaps_dir)
        check("an empty/nonexistent roadmaps dir exits 0 (not a failure)",
              proc.returncode == 0, proc.stdout + proc.stderr)
        check("an empty corpus says so explicitly",
              "no escalation records found" in proc.stdout, proc.stdout)


# --- --roadmap scoping: only the named roadmap's file is checked ----------------------------------

def check_roadmap_flag_scopes_to_one_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        roadmaps_dir = Path(td) / "roadmaps"
        good = _valid_record("finding")
        bad = _valid_record("operator-gate")
        bad["kind"] = "URGENT_PING"
        _write_jsonl(roadmaps_dir / "clean-roadmap" / "escalations.jsonl", [good])
        _write_jsonl(roadmaps_dir / "broken-roadmap" / "escalations.jsonl", [bad])

        proc_clean = _run_cli(roadmaps_dir, ["--roadmap", "clean-roadmap"])
        check("--roadmap scoped to the clean roadmap exits 0 even though a sibling roadmap "
              "is broken",
              proc_clean.returncode == 0, proc_clean.stdout + proc_clean.stderr)

        proc_broken = _run_cli(roadmaps_dir, ["--roadmap", "broken-roadmap"])
        check("--roadmap scoped to the broken roadmap exits non-zero",
              proc_broken.returncode != 0, proc_broken.stdout + proc_broken.stderr)

        proc_all = _run_cli(roadmaps_dir)
        check("scanning every roadmap directory (no --roadmap) exits non-zero because the "
              "broken roadmap is included",
              proc_all.returncode != 0, proc_all.stdout + proc_all.stderr)


# --- options field (channel-declared response options, FIX 2) ---------------------------------

def check_positive_options_valid() -> None:
    record = _valid_record(
        "operator-gate",
        channel="notification",
        options=[{"key": "yes", "label": "Yes, skip it"}, {"key": "no", "label": "No, migrate"}],
    )
    problems = check_escalations.check_escalation_record(record)
    check("a valid notification escalation with 2 options round-trips with no problems",
          problems == [], f"problems: {problems}")


def check_negative_options_over_three() -> None:
    record = _valid_record(
        "operator-gate",
        channel="notification",
        options=[
            {"key": "a", "label": "A"}, {"key": "b", "label": "B"},
            {"key": "c", "label": "C"}, {"key": "d", "label": "D"},
        ],
    )
    problems = check_escalations.check_escalation_record(record)
    check("more than 3 options is rejected (bastion notify ask allows at most 3)",
          any("options" in p for p in problems), f"problems: {problems}")


def check_negative_options_label_too_long() -> None:
    record = _valid_record(
        "operator-gate",
        channel="notification",
        options=[
            {"key": "yes", "label": "This label is definitely over twenty characters"},
            {"key": "no", "label": "No"},
        ],
    )
    problems = check_escalations.check_escalation_record(record)
    check("an option label over 20 chars is rejected (WhatsApp reply-button title limit)",
          any("label" in p for p in problems), f"problems: {problems}")


def check_negative_options_missing_when_notification() -> None:
    record = _valid_record("operator-gate", channel="notification")
    problems = check_escalations.check_escalation_record(record)
    check("a `channel: notification` escalation with no `options` is rejected",
          any("options" in p and "required" in p for p in problems), f"problems: {problems}")


def check_negative_options_present_when_session() -> None:
    record = _valid_record(
        "operator-gate",
        channel="session:bastion-d62-gate",
        options=[{"key": "yes", "label": "Yes"}, {"key": "no", "label": "No"}],
    )
    problems = check_escalations.check_escalation_record(record)
    check("a `channel: session:<slug>` escalation carrying `options` is rejected (never reduce "
          "a session-channel decision to buttons)",
          any("options" in p for p in problems), f"problems: {problems}")


def check_negative_options_below_min() -> None:
    record = _valid_record(
        "operator-gate", channel="notification",
        options=[{"key": "yes", "label": "Yes"}],
    )
    problems = check_escalations.check_escalation_record(record)
    check("a single option is rejected the same as zero (OPERATOR_MIN_RESPONSE_OPTIONS=2)",
          any("options" in p for p in problems), f"problems: {problems}")


# --- --repo attribution: gate narrows to one repo's own records, reporting stays whole -------
#
# D68: these four cases describe a `--repo <slug>` flag that does not exist yet in
# check_escalations.py. Task 1's deliverable IS these cases observed FAILING (the flag is an
# unrecognised argparse argument today, so the CLI exits non-zero via argparse's own usage error
# rather than the behaviour described below) -- expect_red inverts the verdict for this task.
# Case B is the load-bearing one: without it, a --repo implementation that unconditionally exits
# 0 would pass every other case here.

def check_repo_attribution_foreign_only_exits_zero_but_still_reports() -> None:
    """Case A: the only malformed records carry a `repo` OTHER than the gated slug -- under
    `--repo <slug>` the CLI must exit 0, AND every one of those failures must still appear in
    the output, each naming its owning (foreign) repo. Going quiet is as wrong as exiting 1."""
    with tempfile.TemporaryDirectory() as td:
        roadmaps_dir = Path(td) / "roadmaps"
        foreign_bad_one = _valid_record("operator-gate", repo="bastion")
        foreign_bad_one["kind"] = "URGENT_PING"
        foreign_bad_two = _valid_record("finding", repo="mev")
        del foreign_bad_two["verified_at_sha"]
        _write_jsonl(
            roadmaps_dir / "attribution-fixture" / "escalations.jsonl",
            [foreign_bad_one, foreign_bad_two],
        )

        proc = _run_cli(roadmaps_dir, ["--repo", "base-template"])
        check("Case A: foreign-only failures under --repo <slug> exit 0",
              proc.returncode == 0, proc.stdout + proc.stderr)
        check("Case A: the foreign `kind` failure still appears in the output, naming `bastion`",
              "bastion" in (proc.stdout + proc.stderr) and "URGENT_PING" in (proc.stdout + proc.stderr),
              proc.stdout + proc.stderr)
        check("Case A: the foreign `verified_at_sha` failure still appears in the output, "
              "naming `mev`",
              "mev" in (proc.stdout + proc.stderr) and "verified_at_sha" in (proc.stdout + proc.stderr),
              proc.stdout + proc.stderr)


def check_repo_attribution_own_repo_failure_still_gates() -> None:
    """Case B, THE POSITIVE CONTROL: the only malformed record carries `repo` EQUAL to the
    gated slug -- `--repo <slug>` must still exit 1. Without this case, a --repo implementation
    that unconditionally returns 0 would pass every other case in this section."""
    with tempfile.TemporaryDirectory() as td:
        roadmaps_dir = Path(td) / "roadmaps"
        own_bad = _valid_record("operator-gate", repo="base-template")
        own_bad["kind"] = "URGENT_PING"
        _write_jsonl(roadmaps_dir / "attribution-fixture" / "escalations.jsonl", [own_bad])

        proc = _run_cli(roadmaps_dir, ["--repo", "base-template"])
        check("Case B (POSITIVE CONTROL): an own-repo malformed record under --repo <slug> "
              "still exits 1 -- proves the flag narrows the gate rather than disabling it",
              proc.returncode != 0, proc.stdout + proc.stderr)


def check_repo_attribution_no_flag_is_unchanged() -> None:
    """Case C: the same fixture as Case A, run with no --repo flag at all -- must reproduce
    today's exit code (non-zero) unchanged. The corpus-wide sweep is not affected by this flag."""
    with tempfile.TemporaryDirectory() as td:
        roadmaps_dir = Path(td) / "roadmaps"
        foreign_bad_one = _valid_record("operator-gate", repo="bastion")
        foreign_bad_one["kind"] = "URGENT_PING"
        foreign_bad_two = _valid_record("finding", repo="mev")
        del foreign_bad_two["verified_at_sha"]
        _write_jsonl(
            roadmaps_dir / "attribution-fixture" / "escalations.jsonl",
            [foreign_bad_one, foreign_bad_two],
        )

        proc = _run_cli(roadmaps_dir)
        check("Case C: omitting --repo entirely reproduces today's exit code (non-zero) on the "
              "same fixture Case A used -- the corpus-wide sweep is unchanged",
              proc.returncode != 0, proc.stdout + proc.stderr)


def check_repo_attribution_missing_repo_field_is_foreign() -> None:
    """Case D: a record with no `repo` field at all. DECISION (not a default): such a record is
    treated as FOREIGN (non-gating) under `--repo <slug>` -- it cannot be attributed to the
    gated repo, so it must not be able to fail the gate on that repo's behalf -- but it still
    gates (exits 1) when no --repo is given at all, exactly like today."""
    with tempfile.TemporaryDirectory() as td:
        roadmaps_dir = Path(td) / "roadmaps"
        no_repo_bad = _valid_record("operator-gate")
        del no_repo_bad["repo"]
        no_repo_bad["kind"] = "URGENT_PING"
        _write_jsonl(roadmaps_dir / "attribution-fixture" / "escalations.jsonl", [no_repo_bad])

        proc_scoped = _run_cli(roadmaps_dir, ["--repo", "base-template"])
        check("Case D: a record missing `repo` entirely is treated as FOREIGN under --repo "
              "<slug> and does not gate",
              proc_scoped.returncode == 0, proc_scoped.stdout + proc_scoped.stderr)
        check("Case D: the missing-`repo` failure still appears in the output even though it "
              "does not gate",
              "URGENT_PING" in (proc_scoped.stdout + proc_scoped.stderr),
              proc_scoped.stdout + proc_scoped.stderr)

        proc_unscoped = _run_cli(roadmaps_dir)
        check("Case D: the same record still gates (exits non-zero) with no --repo flag",
              proc_unscoped.returncode != 0, proc_unscoped.stdout + proc_unscoped.stderr)


def main() -> int:
    check_dependency_free()
    check_positive_round_trip_per_kind()
    check_negative_unknown_kind()
    check_negative_unknown_severity()
    check_negative_malformed_channel()
    check_negative_missing_required_field()
    check_negative_summary_too_long()
    check_negative_bare_adjective_verified_by()
    check_negative_field_creep()
    check_host_field_accepted()
    check_hostt_field_rejected()
    check_negative_malformed_json_line()
    check_negative_verified_at_sha()
    check_positive_control_cli_can_fail()
    check_cli_accepts_clean_corpus()
    check_no_records_is_not_a_failure()
    check_roadmap_flag_scopes_to_one_file()
    check_positive_options_valid()
    check_negative_options_over_three()
    check_negative_options_label_too_long()
    check_negative_options_missing_when_notification()
    check_negative_options_present_when_session()
    check_negative_options_below_min()
    check_repo_attribution_foreign_only_exits_zero_but_still_reports()
    check_repo_attribution_own_repo_failure_still_gates()
    check_repo_attribution_no_flag_is_unchanged()
    check_repo_attribution_missing_repo_field_is_foreign()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- check_escalations.py holds against the fixture corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
