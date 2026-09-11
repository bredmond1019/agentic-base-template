#!/usr/bin/env python3
"""Fixture suite for check_messages.py (BT.6.B).

Self-contained, no pytest dependency, matching the fixture style of test_check_lane_agents.py and
test_check_lane_records.py: builds a synthetic `.fleet-locks/queue/<repo>/<lane>/` corpus in a
temp dir (never the repo's real `.fleet-locks/`) and drives the real check_messages.py module
against it, both by calling its functions directly (check_message_record, drain_queue,
complete_message, load_receipts) and by running it as a subprocess against `--lock-dir`, so both
the validation logic and the CLI/exit-code contract are exercised.

D68 applies: a checker never observed going red is not evidence. Each of the five negative
fixtures below (unknown kind, missing durable_home, a priority field present, a message written
directly into processing/, a done/ file missing its processing->done receipt) was run against a
deliberately-broken record BEFORE the corresponding check_messages.py logic caught it, during this
block's development -- each was observed to fail open (pass when it should not) before the
catching logic in check_message_record / _check_one_queue existed, and to fail closed (report the
named error) once it did. This file re-asserts that same behavior as a standing fixture, the same
discipline test_check_lane_agents.py documents for its own negative fixtures.

Run: python3 scripts/test_check_messages.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "check_messages.py"

_spec = importlib.util.spec_from_file_location("check_messages", MODULE_PATH)
check_messages = importlib.util.module_from_spec(_spec)
sys.modules["check_messages"] = check_messages
_spec.loader.exec_module(check_messages)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts_basic(dt: datetime) -> str:
    """ISO-8601 basic-form UTC stamp used in message filenames: YYYYMMDDTHHMMSSZ."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _valid_sender(**overrides) -> dict:
    sender = {
        "agent_name": "base-template-b6",
        "repo": "base-template",
        "lane": "lane-coordination",
        "roadmap": "lane-coordination-roadmap",
    }
    sender.update(overrides)
    return sender


def _valid_message(kind: str, message_id: str | None = None, **overrides) -> dict:
    """A full, valid envelope for `kind`, grounded in the incident its kind was derived from
    (block record BT.6.B `why`) rather than filler text."""
    bodies = {
        "EDGE_RELEASED": (
            "bastion:BA.21.A is now unblocked on the engine side -- previously this was only "
            "visible by reading a run record in prose, never signalled, so the waiting lane idled."
        ),
        "FINDING": (
            "cross-lane observation, matching the corpus's one real measured ping: see "
            "base-template/planning/orchestration-run/autonomous-foundation/notes.md (2026-08-21)."
        ),
        "RENDEZVOUS": (
            "the D62 downstream check against bastion is DEFERRED until this lane is idle -- "
            "rendezvous needed before either lane proceeds."
        ),
        "LEASE_RELEASE": (
            "releasing the exclusive lease on base-template held by base-template-b6, one of the "
            "four sweep incidents behind BT.6.A's registry."
        ),
        "QUERY": (
            "is the engine-side unblock for BA.21.A also visible from the bastion lane's own "
            "state.json, or only from base-template's run record?"
        ),
    }
    durable_homes = {
        "EDGE_RELEASED": {"channel": "state-edge", "ref": "bastion#BA.21.A depends_on"},
        "FINDING": {
            "channel": "run-record",
            "ref": "base-template/planning/orchestration-run/autonomous-foundation/notes.md",
        },
        "RENDEZVOUS": {"channel": "carryover", "ref": "rendezvous-d62-downstream-check"},
        "LEASE_RELEASE": {"channel": "lane-log", "ref": "lane-lane-coordination.jsonl#42"},
        "QUERY": {"channel": "lane-log", "ref": "lane-lane-coordination.jsonl#43"},
    }
    record = {
        "message_id": message_id or str(uuid_mod.uuid4()),
        "sender": _valid_sender(),
        "sent_at": _iso(_now()),
        "kind": kind,
        "subject": {"repo": "bastion", "block": "BA.21.A"},
        "body": bodies[kind],
        "durable_home": durable_homes[kind],
        "verified_by": "$ ls -la core/bastion/trees/\ntotal 0 -- directory is empty",
    }
    record.update(overrides)
    return record


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _write_message_file(state_dir: Path, record: dict, ts: datetime | None = None,
                         uuid_override: str | None = None) -> Path:
    """Write `record` into `state_dir` under the `<ts>-<uuid>.json` filename convention. Pass
    `uuid_override` to deliberately build a filename<->message_id mismatch."""
    stamp = _ts_basic(ts or _now())
    uuid_part = uuid_override if uuid_override is not None else record["message_id"]
    path = state_dir / f"{stamp}-{uuid_part}.json"
    _write_json(path, record)
    return path


def _run_cli(lock_dir: Path, extra: list[str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), "--lock-dir", str(lock_dir), "--quiet",
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
        "argparse", "json", "os", "re", "sys", "datetime", "pathlib", "typing",
        "__future__", "check_messages", "tomllib",
    }
    third_party = imported - stdlib_and_local
    check("check_messages.py imports no third-party package (no jsonschema)",
          third_party == set(), f"unexpected imports: {sorted(third_party)}")


# --- positive: one round-trip per kind --------------------------------------------------------

def check_positive_round_trip_per_kind() -> None:
    for kind in ("EDGE_RELEASED", "FINDING", "RENDEZVOUS", "LEASE_RELEASE", "QUERY"):
        problems = check_messages.check_message_record(_valid_message(kind))
        check(f"a valid {kind} envelope round-trips with no problems",
              problems == [], f"problems: {problems}")


# --- negative (a): unknown kind value ---------------------------------------------------------

def check_negative_unknown_kind() -> None:
    record = _valid_message("EDGE_RELEASED")
    record["kind"] = "URGENT_PING"
    problems = check_messages.check_message_record(record)
    check("an unknown `kind` value is rejected",
          any("kind" in p and "URGENT_PING" in p for p in problems), f"problems: {problems}")


# --- negative (b): missing durable_home --------------------------------------------------------

def check_negative_missing_durable_home() -> None:
    record = _valid_message("FINDING")
    del record["durable_home"]
    problems = check_messages.check_message_record(record)
    check("a message missing `durable_home` is rejected",
          any("durable_home" in p for p in problems), f"problems: {problems}")


# --- negative (c): a priority field present -----------------------------------------------------

def check_negative_priority_field_present() -> None:
    record = _valid_message("QUERY")
    record["priority"] = "urgent"
    problems = check_messages.check_message_record(record)
    check("a message carrying `priority` is rejected",
          any("priority" in p and "D43" in p for p in problems), f"problems: {problems}")

    nested = _valid_message("RENDEZVOUS")
    nested["sender"]["urgency"] = "high"
    nested_problems = check_messages.check_message_record(nested)
    check("`urgency` nested inside `sender` is also rejected, naming D43",
          any("urgency" in p and "D43" in p for p in nested_problems),
          f"problems: {nested_problems}")


# --- host: additive optional field (BT.8.A task 2) ----------------------------------------------

def check_host_field_accepted() -> None:
    record = _valid_message("QUERY", host="mac-mini-01")
    problems = check_messages.check_message_record(record)
    check("a message carrying `host` validates green",
          problems == [], f"problems: {problems}")


def check_hostt_field_rejected() -> None:
    record = _valid_message("QUERY", hostt="mac-mini-01")
    problems = check_messages.check_message_record(record)
    check("a message carrying `hostt` (typo) is rejected as an unknown key",
          any("unknown key" in p and "hostt" in p for p in problems), f"problems: {problems}")


# --- BT.ticket.messages-must-carry-verified-by: the evidence field ----------------------------
#
# One case per accepted shape and one per rejected shape. The bare-adjective case (b1) is the
# exact measured defect (three relays believed an adjective in place of evidence) and is proved
# capable of failing in check_defect_reproduction_and_fix_demonstrated() below, which reverts
# `_check_verified_by` in-process to the pre-fix (unvalidated) behaviour and shows the SAME record
# validate clean under it -- without ever leaving a gated check red, since the revert and the
# re-check both happen inside this one test process.

def check_verified_by_accepted_command_and_output() -> None:
    record = _valid_message(
        "FINDING",
        verified_by="$ ls -la core/bastion/trees/\ntotal 0 -- directory is empty, refuting the "
                     "relayed claim",
    )
    problems = check_messages.check_message_record(record)
    check("a `verified_by` carrying a command and its real output validates",
          problems == [], f"problems: {problems}")


def check_verified_by_accepted_unverified_prefix() -> None:
    record = _valid_message("FINDING", verified_by="UNVERIFIED: base-template-b6")
    problems = check_messages.check_message_record(record)
    check("a `verified_by` of `UNVERIFIED: <claimant>` validates",
          problems == [], f"problems: {problems}")


def check_verified_by_rejected_missing() -> None:
    record = _valid_message("FINDING")
    del record["verified_by"]
    problems = check_messages.check_message_record(record)
    check("an envelope omitting `verified_by` fails validation",
          any("verified_by" in p for p in problems), f"problems: {problems}")


def check_verified_by_rejected_empty() -> None:
    record = _valid_message("FINDING", verified_by="")
    problems = check_messages.check_message_record(record)
    check("an envelope with `verified_by` as an empty string fails validation",
          any("verified_by" in p for p in problems), f"problems: {problems}")


def check_verified_by_rejected_whitespace() -> None:
    record = _valid_message("FINDING", verified_by="   \n\t  ")
    problems = check_messages.check_message_record(record)
    check("an envelope with `verified_by` as whitespace-only fails validation",
          any("verified_by" in p for p in problems), f"problems: {problems}")


def check_verified_by_rejected_bare_adjective() -> None:
    """THE MEASURED DEFECT: a bare adjective like 'measured' asserted with nothing behind it --
    exactly what the sending envelope in the bastion incident carried (block record `why`, case
    1). Must be rejected by the fixed logic; check_defect_reproduction_and_fix_demonstrated()
    below shows it PASSING under the pre-fix logic, in-process, as the reproduction."""
    record = _valid_message("FINDING", verified_by="measured")
    problems = check_messages.check_message_record(record)
    check("a bare adjective `verified_by` such as 'measured' fails validation "
          "(the measured defect)",
          any("verified_by" in p for p in problems), f"problems: {problems}")

    verified_record = _valid_message("FINDING", verified_by="verified")
    verified_problems = check_messages.check_message_record(verified_record)
    check("a bare adjective `verified_by` such as 'verified' also fails validation",
          any("verified_by" in p for p in verified_problems), f"problems: {verified_problems}")


def check_defect_reproduction_and_fix_demonstrated() -> None:
    """Demonstrates, in-process, that the bare-adjective fixture is capable of failing --
    without ever leaving a gated check red. Mirrors the pattern test_bail_path_runtime.py's
    runtime half uses (and BT.ticket.notify-operator-skill task 4's correct specification of it):
    temporarily revert the fix, show the SAME fixture record now validates clean (the pre-fix
    defect, reproduced), then restore the fix and show it fails again (the fixed behaviour, which
    every other check in this file already exercises against the real, un-reverted module)."""
    record = _valid_message("FINDING", verified_by="measured")

    original_required = list(check_messages.MESSAGE_REQUIRED)
    original_check_fn = check_messages._check_verified_by
    try:
        # Pre-fix simulation: `verified_by` was neither required nor validated.
        check_messages.MESSAGE_REQUIRED = [f for f in original_required if f != "verified_by"]
        check_messages.MESSAGE_ALLOWED = set(check_messages.MESSAGE_REQUIRED) | {"verified_by"}
        check_messages._check_verified_by = lambda value: []

        pre_fix_problems = check_messages.check_message_record(record)
        check("REPRODUCED pre-fix: the bare-adjective envelope validates clean when `verified_by` "
              "is neither required nor checked -- this is the measured defect",
              pre_fix_problems == [], f"problems: {pre_fix_problems}")
    finally:
        check_messages.MESSAGE_REQUIRED = original_required
        check_messages.MESSAGE_ALLOWED = set(original_required)
        check_messages._check_verified_by = original_check_fn

    post_fix_problems = check_messages.check_message_record(record)
    check("FIXED: the same bare-adjective envelope fails validation once restored",
          any("verified_by" in p for p in post_fix_problems), f"problems: {post_fix_problems}")


# --- BT.ticket.messages-must-carry-verified-by: legacy envelope, built from a real one on disk --

def check_legacy_envelope_without_verified_by_does_not_crash() -> None:
    """A real envelope already on disk before this field existed (no synthesized fixture): copied
    verbatim from .fleet-locks/queue/base-template/base-template/done/ as it was measured
    2026-08-24. It lacks `verified_by`. Per the block's stated deterministic choice (out_of_scope:
    no retrofit migration onto envelopes already on disk), an otherwise schema-valid legacy
    envelope missing ONLY `verified_by` is reported -- tagged LEGACY -- but does not fail the
    gating verdict and never crashes the checker or the drain machinery. At the `check_message_
    record()` level (schema conformance, no legacy exemption) it still reports the missing field
    by name, which is what a NEW envelope omitting the field is held to."""
    legacy_record = {
        "message_id": "drain-log-call-site-unwired",
        "sender": {
            "agent_name": "agentic-portfolio-01",
            "repo": "hq",
            "lane": "brain",
            "roadmap": "autonomous-foundation",
        },
        "sent_at": "2026-08-23T13:10:44Z",
        "kind": "FINDING",
        "subject": {"repo": "base-template"},
        "body": (
            "HQ closed HQ.ticket.fleet-locks-have-no-history and shipped scripts/drain_log.py "
            "in the brain repo. The call site is unwired and is yours."
        ),
        "durable_home": {
            "channel": "carryover",
            "ref": "hq:planning/state.json carryover[] drain-does-not-write-the-durable-drain-log",
        },
        # verified_by deliberately absent -- this is the pre-field shape.
    }
    assert "verified_by" not in legacy_record

    problems = check_messages.check_message_record(legacy_record)
    check("a real pre-existing envelope missing `verified_by` is reported as failing, not exempt",
          any("verified_by" in p for p in problems), f"problems: {problems}")

    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        queue_dir = lock_dir / "queue" / "base-template" / "lane-coordination"
        try:
            _write_message_file(queue_dir / "done", legacy_record)
            check_messages.append_receipt(queue_dir, legacy_record["message_id"], "inbox",
                                           "processing")
            check_messages.append_receipt(queue_dir, legacy_record["message_id"], "processing",
                                           "done")
            proc = _run_cli(lock_dir)
            crashed = proc.returncode not in (0, 1)
            check("the CLI does not crash (exits 0 or 1, never a traceback/other code) reading a "
                  "legacy envelope without `verified_by`",
                  not crashed, f"rc: {proc.returncode}, output: {proc.stdout + proc.stderr}")
            check("the CLI does NOT fail the gating verdict (rc == 0) for a legacy envelope "
                  "missing only `verified_by` -- the stated deterministic choice, so a real "
                  "pre-existing corpus does not red-gate the harness",
                  proc.returncode == 0, f"rc: {proc.returncode}, output: {proc.stdout + proc.stderr}")
            check("the CLI still names the field, tagged LEGACY, in its report",
                  "verified_by" in (proc.stdout + proc.stderr)
                  and "LEGACY" in (proc.stdout + proc.stderr),
                  proc.stdout + proc.stderr)
        except Exception as exc:                    # noqa: BLE001 -- a raise here IS the failure
            check("the drain machinery does not crash on a legacy envelope without `verified_by`",
                  False, f"raised: {exc!r}")

        # drain_queue()/complete_message() never inspect verified_by -- confirm no crash there.
        try:
            replay_dir = lock_dir / "queue" / "base-template" / "lane-replay"
            inbox_dir = replay_dir / "inbox"
            _write_message_file(inbox_dir, legacy_record)
            moved = check_messages.drain_queue(replay_dir)
            check("drain_queue() moves a legacy envelope without `verified_by` without raising",
                  len(moved) == 1, f"moved: {moved}")
            done = check_messages.complete_message(replay_dir, legacy_record["message_id"])
            check("complete_message() completes a legacy envelope without `verified_by` without "
                  "raising",
                  done is True)
        except Exception as exc:                    # noqa: BLE001 -- a raise here IS the failure
            check("drain/complete do not crash on a legacy envelope without `verified_by`",
                  False, f"raised: {exc!r}")


# --- negative (d): message written directly into processing/, no receipt ----------------------

def check_negative_direct_write_to_processing() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        queue_dir = lock_dir / "queue" / "base-template" / "lane-coordination"
        record = _valid_message("EDGE_RELEASED")
        _write_message_file(queue_dir / "processing", record)

        proc = _run_cli(lock_dir)
        check("a message file written directly into processing/ makes the CLI exit non-zero",
              proc.returncode != 0, proc.stdout + proc.stderr)
        check("the failure names the missing inbox->processing receipt",
              "no inbox->processing" in proc.stdout or "no inbox->processing" in proc.stderr,
              proc.stdout + proc.stderr)


# --- negative (e): done/ file missing its processing->done receipt -----------------------------

def check_negative_done_missing_second_receipt() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        queue_dir = lock_dir / "queue" / "base-template" / "lane-coordination"
        record = _valid_message("LEASE_RELEASE")
        _write_message_file(queue_dir / "done", record)
        # Only the first-leg receipt exists -- the file was moved to done/ without ever being
        # receipted through processing -> done.
        check_messages.append_receipt(queue_dir, record["message_id"], "inbox", "processing")

        proc = _run_cli(lock_dir)
        check("a done/ file missing its processing->done receipt makes the CLI exit non-zero",
              proc.returncode != 0, proc.stdout + proc.stderr)
        check("the failure names the missing processing->done receipt",
              "no processing->done" in proc.stdout or "no processing->done" in proc.stderr,
              proc.stdout + proc.stderr)


# --- boundary: filename uuid disagrees with in-file message_id ---------------------------------

def check_boundary_filename_uuid_mismatch() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        queue_dir = lock_dir / "queue" / "base-template" / "lane-coordination"
        record = _valid_message("QUERY")
        mismatched_uuid = str(uuid_mod.uuid4())
        assert mismatched_uuid != record["message_id"]
        _write_message_file(queue_dir / "inbox", record, uuid_override=mismatched_uuid)

        proc = _run_cli(lock_dir)
        check("a filename uuid that disagrees with message_id makes the CLI exit non-zero",
              proc.returncode != 0, proc.stdout + proc.stderr)
        check("the failure names the mismatch",
              "does not match in-file message_id" in proc.stdout
              or "does not match in-file message_id" in proc.stderr,
              proc.stdout + proc.stderr)


# --- BT.ticket.ping-agent-never-specifies-the-message-timestamp-format: rejection literal -------
#
# Task 3: pin the concrete expected literal (`YYYYMMDDThhmmssZ-<uuid>.json`) added to the
# FILENAME_RE rejection message in task 2, and replay the motivating incident's two forms: an
# extended-form stamp with colons stripped (dashes still intact) must be REJECTED, while a stamp
# produced by `date -u +%Y%m%dT%H%M%SZ` (basic form) must be ACCEPTED.

def check_filename_rejection_message_carries_expected_literal() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        queue_dir = lock_dir / "queue" / "base-template" / "lane-coordination"
        inbox_dir = queue_dir / "inbox"
        inbox_dir.mkdir(parents=True)
        record = _valid_message("EDGE_RELEASED")
        # bastion-61's exact mistake: derive the stamp as iso_utc.replace(':', ''), which strips
        # colons but leaves the dashes -- extended form, still rejected by FILENAME_RE (basic
        # form only).
        extended_stamp = _iso(_now()).replace(":", "")
        assert "-" in extended_stamp.split("T")[0], "fixture must retain dashes to be a fair test"
        bad_path = inbox_dir / f"{extended_stamp}-{record['message_id']}.json"
        _write_json(bad_path, record)

        proc = _run_cli(lock_dir)
        output = proc.stdout + proc.stderr
        check("rejection message carries the concrete expected literal "
              "`YYYYMMDDThhmmssZ-<uuid>.json`, not only the prose description",
              "YYYYMMDDThhmmssZ-<uuid>.json" in output, output)
        check("a colons-stripped-but-dashes-intact (extended-form) stamp is REJECTED",
              proc.returncode != 0, output)


def check_basic_form_stamp_from_incantation_is_accepted() -> None:
    """The `date -u +%Y%m%dT%H%M%SZ` incantation's output form must be ACCEPTED -- the positive
    half of the same incident, so the fixture can't pass merely by rejecting everything."""
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        queue_dir = lock_dir / "queue" / "base-template" / "lane-coordination"
        inbox_dir = queue_dir / "inbox"
        inbox_dir.mkdir(parents=True)
        record = _valid_message("EDGE_RELEASED")
        # Basic form, exactly what `date -u +%Y%m%dT%H%M%SZ` produces: no dashes, no colons.
        basic_stamp = _ts_basic(_now())
        good_path = inbox_dir / f"{basic_stamp}-{record['message_id']}.json"
        _write_json(good_path, record)

        proc = _run_cli(lock_dir)
        output = proc.stdout + proc.stderr
        check("a basic-form stamp (as produced by `date -u +%Y%m%dT%H%M%SZ`) is ACCEPTED "
              "(no filename-format problem reported)",
              "does not match" not in output, output)


# --- BT.ticket.fleet-wide-gates-red-on-another-lanes-data: foreign vs. own verdict scope -----
#
# Task 1 of that block: replay the block record's measured instance (1) as a FAILING fixture
# against the UNCHANGED checker. The measured incident: `bastion-61` wrote a message into
# ENGINE-RS's inbox with an extended-form timestamp (`2026-08-23T025258Z-<uuid>.json`) where
# FILENAME_RE requires basic form (`20260823T025258Z-<uuid>.json`) -- one lane's sender bug, in a
# THIRD lane's queue, bailed base-template's task. These two functions assert the TARGET
# (post-task-3) behavior, so the foreign one is expected to be RED until the verdict is scoped:
#   - the foreign case (queue/engine-rs/...) asserts rc == 0 -- FAILS today, because today it is
#     fatal regardless of which repo's queue the bad file sits in.
#   - the own case (queue/base-template/...) asserts rc != 0 -- PASSES today AND after the fix.

def check_foreign_malformed_filename_reports_but_is_not_fatal() -> None:
    """TARGET behavior (task 3): a malformed filename in ANOTHER repo's queue is reported but
    does not fail the gating verdict. RED today."""
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        queue_dir = lock_dir / "queue" / "engine-rs" / "lane-coordination"
        inbox_dir = queue_dir / "inbox"
        inbox_dir.mkdir(parents=True)
        record = _valid_message("EDGE_RELEASED", sender=_valid_sender(agent_name="bastion-61"))
        # Extended-form timestamp (dashes in the date), exactly the measured sender bug -- basic
        # form is required by FILENAME_RE.
        bad_path = inbox_dir / f"2026-08-23T025258Z-{record['message_id']}.json"
        _write_json(bad_path, record)

        proc = _run_cli(lock_dir)
        check("a malformed filename in ANOTHER repo's queue is still REPORTED in the output",
              "does not match" in proc.stdout or "does not match" in proc.stderr,
              proc.stdout + proc.stderr)
        check("EXPECTED RED before task 3: a malformed filename in ANOTHER repo's queue must NOT "
              "fail the gating verdict (rc == 0) -- today it does, because the verdict is not yet "
              "scoped by record ownership",
              proc.returncode == 0, f"rc: {proc.returncode}, output: {proc.stdout + proc.stderr}")


def check_own_malformed_filename_is_still_fatal() -> None:
    """The other direction: a malformed filename in THIS repo's own queue (base-template) must
    still fail the gating verdict, both today and after task 3."""
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        queue_dir = lock_dir / "queue" / "base-template" / "lane-coordination"
        inbox_dir = queue_dir / "inbox"
        inbox_dir.mkdir(parents=True)
        record = _valid_message("EDGE_RELEASED")
        bad_path = inbox_dir / f"2026-08-23T025258Z-{record['message_id']}.json"
        _write_json(bad_path, record)

        proc = _run_cli(lock_dir)
        check("a malformed filename in THIS repo's own queue is REPORTED in the output",
              "does not match" in proc.stdout or "does not match" in proc.stderr,
              proc.stdout + proc.stderr)
        check("a malformed filename in THIS repo's own queue still fails the gating verdict "
              "(rc != 0), both today and after task 3",
              proc.returncode != 0, f"rc: {proc.returncode}, output: {proc.stdout + proc.stderr}")


# --- concurrent-drain: two messages, one drain, both processed exactly once --------------------

def check_concurrent_drain_exactly_once() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        queue_dir = lock_dir / "queue" / "base-template" / "lane-coordination"
        inbox_dir = queue_dir / "inbox"

        msg_a = _valid_message("EDGE_RELEASED")
        msg_b = _valid_message("FINDING")
        # Distinct timestamps so filename ordering is deterministic.
        _write_message_file(inbox_dir, msg_a, ts=_now() - timedelta(seconds=2))
        _write_message_file(inbox_dir, msg_b, ts=_now() - timedelta(seconds=1))

        moved = check_messages.drain_queue(queue_dir)
        check("a single drain_queue() call moves both messages out of inbox/",
              len(moved) == 2, f"moved: {moved}")
        check("inbox/ is empty after the drain",
              list(inbox_dir.iterdir()) == [], f"remaining: {list(inbox_dir.iterdir())}")

        done_a = check_messages.complete_message(queue_dir, msg_a["message_id"])
        done_b = check_messages.complete_message(queue_dir, msg_b["message_id"])
        check("complete_message() succeeds for message A", done_a is True)
        check("complete_message() succeeds for message B", done_b is True)

        done_dir = queue_dir / "done"
        done_files = list(done_dir.iterdir())
        check("both message_ids land in done/ exactly once",
              len(done_files) == 2, f"done files: {done_files}")

        receipts = check_messages.load_receipts(queue_dir)
        counts = check_messages._receipt_counts(receipts)
        check("exactly two inbox->processing receipts total, one per message, no duplicates",
              counts.get((msg_a["message_id"], "inbox", "processing")) == 1
              and counts.get((msg_b["message_id"], "inbox", "processing")) == 1,
              f"counts: {counts}")
        check("exactly two processing->done receipts total, one per message, no duplicates",
              counts.get((msg_a["message_id"], "processing", "done")) == 1
              and counts.get((msg_b["message_id"], "processing", "done")) == 1,
              f"counts: {counts}")

        # Full checker pass over the drained-and-completed queue must be clean.
        proc = _run_cli(lock_dir)
        check("the checker accepts the fully-drained, fully-completed queue",
              proc.returncode == 0, proc.stdout + proc.stderr)


# --- interleaved race: a second drain over the same inbox returns nothing ----------------------

def check_interleaved_drain_race() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        queue_dir = lock_dir / "queue" / "base-template" / "lane-coordination"
        inbox_dir = queue_dir / "inbox"

        msg = _valid_message("RENDEZVOUS")
        _write_message_file(inbox_dir, msg)

        first = check_messages.drain_queue(queue_dir)
        check("the first drain_queue() call over the inbox picks up the message",
              len(first) == 1, f"first: {first}")

        # A second drainer races over the same inbox before the first message is completed.
        # It must not re-return a file already moved into processing/ -- the file is simply
        # gone from inbox/ by the time the second call runs, which is the entire point of the
        # rename-based design (no shared read cursor for two drainers to disagree over).
        second = check_messages.drain_queue(queue_dir)
        check("a second drain_queue() call over the same inbox before completion returns nothing",
              second == [], f"second: {second}")

        receipts = check_messages.load_receipts(queue_dir)
        counts = check_messages._receipt_counts(receipts)
        check("only one inbox->processing receipt was appended, not two",
              counts.get((msg["message_id"], "inbox", "processing")) == 1,
              f"counts: {counts}")


# --- BT.ticket.message-envelope-field-caps: schema-derived maxLength enforcement --------------
#
# One field is enough to exercise the cap logic without tripping unrelated pattern/enum checks:
# `durable_home.ref` (cap 400, free text, no pattern restriction). OBSERVED RED: run
# check_field_over_cap_fails_after_effective_date against the pre-task-2 checker (before
# _check_field_caps existed) -- it exits 0 (does not detect the over-cap field). Recorded here and
# in the task commit message per the task's OBSERVED RED requirement.

def check_field_at_cap_passes() -> None:
    cap = check_messages.schema_field_caps()["durable_home.ref"]
    record = _valid_message(
        "QUERY",
        durable_home={"channel": "lane-log", "ref": "x" * cap},
    )
    problems = check_messages.check_message_record(record)
    check(f"a `durable_home.ref` value at exactly its cap ({cap} chars) has no cap violation",
          not any(check_messages._is_cap_violation(p) for p in problems),
          f"problems: {problems}")


def check_field_over_cap_fails_after_effective_date() -> None:
    cap = check_messages.schema_field_caps()["durable_home.ref"]
    on_or_after = check_messages.FIELD_CAP_EFFECTIVE_DATE + "T00:00:00Z"
    record = _valid_message(
        "QUERY",
        sent_at=on_or_after,
        durable_home={"channel": "lane-log", "ref": "x" * (cap + 1)},
    )
    problems = check_messages.check_message_record(record)
    check("a `durable_home.ref` one character over its cap is reported, naming the field",
          any("durable_home.ref" in p and "exceeding its cap" in p for p in problems),
          f"problems: {problems}")

    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        queue_dir = lock_dir / "queue" / "base-template" / "lane-coordination"
        _write_message_file(queue_dir / "inbox", record)

        proc = _run_cli(lock_dir)
        output = proc.stdout + proc.stderr
        check("an over-cap envelope sent on/after the effective date makes "
              "`check_messages.py --quiet` exit non-zero",
              proc.returncode != 0, output)
        check("the failure names `durable_home.ref`", "durable_home.ref" in output, output)


def check_over_cap_before_effective_date_is_tagged_not_gating() -> None:
    cap = check_messages.schema_field_caps()["durable_home.ref"]
    before = "2026-01-01T00:00:00Z"
    assert before[:10] < check_messages.FIELD_CAP_EFFECTIVE_DATE, \
        "fixture must genuinely predate the effective date"
    record = _valid_message(
        "QUERY",
        sent_at=before,
        durable_home={"channel": "lane-log", "ref": "x" * (cap + 1)},
    )
    problems = check_messages.check_message_record(record)
    check("check_message_record still reports the over-cap field even before the effective date "
          "(gating is decided by the CLI/_check_one_queue layer, not here)",
          any("durable_home.ref" in p and "exceeding its cap" in p for p in problems),
          f"problems: {problems}")

    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        queue_dir = lock_dir / "queue" / "base-template" / "lane-coordination"
        _write_message_file(queue_dir / "inbox", record)

        proc = _run_cli(lock_dir)
        output = proc.stdout + proc.stderr
        check("an over-cap envelope sent BEFORE the effective date does NOT change the exit code "
              "(rc == 0)", proc.returncode == 0, output)
        check("the report still names the field and tags it LEGACY / pre-dates field-cap "
              "effective date",
              "durable_home.ref" in output and "LEGACY" in output
              and "field-cap effective date" in output,
              output)


def check_schema_capped_fields_equal_checker_fields() -> None:
    schema_paths = check_messages.schema_capped_field_paths()
    checker_paths = set(check_messages.CAPPED_FIELD_PATHS)
    check("the set of fields carrying `maxLength` in message.schema.json equals the set "
          "check_message_record enforces",
          schema_paths == checker_paths,
          f"schema: {sorted(schema_paths)}, checker: {sorted(checker_paths)}")


# --- no records is not a failure ----------------------------------------------------------------

def check_no_records_is_not_a_failure() -> None:
    with tempfile.TemporaryDirectory() as td:
        lock_dir = Path(td) / ".fleet-locks"
        proc = _run_cli(lock_dir)
        check("an empty corpus exits 0 (not a failure)",
              proc.returncode == 0, proc.stdout + proc.stderr)
        check("an empty corpus says so explicitly",
              "no message records found" in proc.stdout, proc.stdout)


def main() -> int:
    check_dependency_free()
    check_positive_round_trip_per_kind()
    check_negative_unknown_kind()
    check_negative_missing_durable_home()
    check_negative_priority_field_present()
    check_host_field_accepted()
    check_hostt_field_rejected()
    check_verified_by_accepted_command_and_output()
    check_verified_by_accepted_unverified_prefix()
    check_verified_by_rejected_missing()
    check_verified_by_rejected_empty()
    check_verified_by_rejected_whitespace()
    check_verified_by_rejected_bare_adjective()
    check_defect_reproduction_and_fix_demonstrated()
    check_legacy_envelope_without_verified_by_does_not_crash()
    check_negative_direct_write_to_processing()
    check_negative_done_missing_second_receipt()
    check_boundary_filename_uuid_mismatch()
    check_filename_rejection_message_carries_expected_literal()
    check_basic_form_stamp_from_incantation_is_accepted()
    check_foreign_malformed_filename_reports_but_is_not_fatal()
    check_own_malformed_filename_is_still_fatal()
    check_concurrent_drain_exactly_once()
    check_interleaved_drain_race()
    check_field_at_cap_passes()
    check_field_over_cap_fails_after_effective_date()
    check_over_cap_before_effective_date_is_tagged_not_gating()
    check_schema_capped_fields_equal_checker_fields()
    check_no_records_is_not_a_failure()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- check_messages.py holds against the fixture corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
