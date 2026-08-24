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
    check_negative_direct_write_to_processing()
    check_negative_done_missing_second_receipt()
    check_boundary_filename_uuid_mismatch()
    check_foreign_malformed_filename_reports_but_is_not_fatal()
    check_own_malformed_filename_is_still_fatal()
    check_concurrent_drain_exactly_once()
    check_interleaved_drain_race()
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
