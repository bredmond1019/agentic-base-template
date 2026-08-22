#!/usr/bin/env python3
"""Validate cross-lane message envelopes and the inbox/processing/done queue layout (BT.6.B).

Dependency-free on purpose, same discipline as check_lane_agents.py, check_lane_records.py and
check_block_records.py: `jsonschema` is not installed anywhere in this fleet, so a validator that
imports it validates nothing and reports success. This checks the constraints in
message.schema.json -- required/allowed keys at every object level, the slug and timestamp
grammars, the five-value kind enum, and the explicit absence of a priority/urgency field -- by
hand, plus the queue layout invariants message.schema.json cannot express on its own.

FILE LAYOUT: queues live under the same shared advisory lock directory check_lane_agents.py and
fleet_concurrency_check.py already resolve -- this script mirrors their identical --lock-dir /
FLEET_LOCK_DIR / brain.toml-walk-up precedence, so all three agree on one location without any of
them hardcoding another's path. A queue is `<lock_dir>/queue/<repo>/<lane>/`, holding three state
directories -- `inbox/`, `processing/`, `done/` -- plus an append-only transition ledger,
`receipts.jsonl`, one JSON object per line: `{message_id, from, to, ts}`.

THE RECIPIENT IS THE DIRECTORY: message.schema.json carries no `to` field. The inbox a message
file sits in (`queue/<repo>/<lane>/inbox/`) IS the message's address -- BT.6.C sends by writing
into a specific lane's inbox, not by naming a recipient inside the envelope. Draining the queue is
BT.6.D's job; this block ships the shape, this checker, and the drain/complete helpers only.

FILENAMES: `<ts>-<uuid>.json`, where `<ts>` is the ISO-8601 basic-form UTC stamp
(`YYYYMMDDTHHMMSSZ`, no colons or dashes, so it never collides with the uuid's own dashes when
splitting the filename) and `<uuid>` must equal the record's `message_id`. That agreement is what
makes "exactly once" assertable by identity rather than by path -- a filename whose uuid half
disagrees with the in-file `message_id` is a named error.

LAYOUT INVARIANT: a message file's location must be justified by receipts. A file in `inbox/`
needs no receipt. A file in `processing/` must have exactly one `inbox->processing` receipt for
its message_id. A file in `done/` must have exactly one `inbox->processing` AND exactly one
`processing->done` receipt for its message_id. A message file placed directly into `processing/`
or `done/` -- skipping the receipted transition -- has no matching receipt and is rejected by
name. A second receipt for a transition already recorded for the same message_id is also an
error: that duplicate is the double-processing signal this layout exists to catch.

PRIORITY IS DELIBERATELY ABSENT: a record carrying a `priority` or `urgency` key anywhere in the
envelope is a NAMED error, not merely an "unknown key" -- the message states the field is
deliberately absent and that D43 owns priority in this fleet, matching message.schema.json's
top-level description.

Usage:
    check_messages.py [--lock-dir DIR] [--quiet]

    --lock-dir DIR   override the shared lock directory (default: resolved the same way
                     check_lane_agents.py resolves it -- FLEET_LOCK_DIR env var, else a
                     brain.toml discovered by walking up from cwd, joined with .fleet-locks)
    --quiet          print only failures and the summary

Exit code 1 if any record fails validation or any layout invariant is violated. Exit code 0 on a
clean corpus, INCLUDING a corpus with zero queues -- that is the state of every repo today, before
BT.6.C ever writes a message, and must stay silent (matches check_lane_agents.py's precedent).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
FILENAME_RE = re.compile(r"^(\d{8}T\d{6}(?:\.\d+)?Z)-(.+)\.json$")

KIND_VALUES = ["EDGE_RELEASED", "FINDING", "RENDEZVOUS", "LEASE_RELEASE", "QUERY"]
DURABLE_HOME_CHANNELS = {"lane-log", "state-edge", "carryover", "run-record"}

MESSAGE_REQUIRED = ["message_id", "sender", "sent_at", "kind", "subject", "body", "durable_home"]
MESSAGE_ALLOWED = set(MESSAGE_REQUIRED)

SENDER_REQUIRED = ["agent_name", "repo", "lane", "roadmap"]
SENDER_ALLOWED = set(SENDER_REQUIRED)
SENDER_SLUG_FIELDS = ("repo", "lane", "roadmap")

SUBJECT_REQUIRED = ["repo"]
SUBJECT_ALLOWED = {"repo", "block"}

DURABLE_HOME_REQUIRED = ["channel", "ref"]
DURABLE_HOME_ALLOWED = set(DURABLE_HOME_REQUIRED)

FORBIDDEN_KEYS = {"priority", "urgency"}
FORBIDDEN_KEY_MESSAGE = (
    "field `{key}` is not allowed anywhere in a message envelope -- priority is deliberately "
    "absent from message.schema.json: a sender-declared priority inflates to always-urgent and "
    "forks a second rubric alongside D43, which owns priority in this fleet"
)

LOCK_SUBDIR = ".fleet-locks"
QUEUE_SUBDIR = "queue"
STATE_DIRS = ("inbox", "processing", "done")
RECEIPTS_FILE = "receipts.jsonl"


# --- lock-dir resolution (mirrors check_lane_agents.py's precedence exactly) -----------------

def find_brain_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk upward from `start` (default: cwd) looking for a directory containing brain.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "brain.toml").exists():
            return candidate
    return None


def resolve_lock_dir(explicit: Optional[str] = None) -> Optional[Path]:
    """Resolve the shared lock directory. Precedence: explicit --lock-dir, then FLEET_LOCK_DIR
    env var, then a brain.toml discovered by walking up from cwd. Returns None (never raises) if
    nothing resolves -- callers must then treat "no queues found" as the (silent) result rather
    than erroring, since an unresolved lock dir with zero queues is indistinguishable from a repo
    that has never written one."""
    if explicit:
        return Path(explicit)
    if os.environ.get("FLEET_LOCK_DIR"):
        return Path(os.environ["FLEET_LOCK_DIR"])
    brain_root = find_brain_root()
    if brain_root is not None:
        return brain_root / LOCK_SUBDIR
    return None


# --- recursive forbidden-key scan -------------------------------------------------------------

def _find_forbidden_keys(node, path="$") -> list:
    """Return problems for any `priority`/`urgency` key found anywhere in `node`, at any nesting
    depth, so a forbidden field slipped into a nested object (sender/subject/durable_home) is
    caught the same as one at the top level."""
    problems = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in FORBIDDEN_KEYS:
                problems.append(f"{path}.{key}: " + FORBIDDEN_KEY_MESSAGE.format(key=key))
            problems.extend(_find_forbidden_keys(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            problems.extend(_find_forbidden_keys(item, f"{path}[{i}]"))
    return problems


# --- record validation --------------------------------------------------------------------

def _check_object(record, required, allowed, label) -> list:
    problems = []
    if not isinstance(record, dict):
        return [f"{label}: must be an object"]
    unknown = sorted(set(record) - allowed)
    if unknown:
        problems.append(f"{label}: unknown key(s): {', '.join(unknown)}")
    for field in required:
        v = record.get(field)
        if v is None or (isinstance(v, str) and not v):
            problems.append(f"{label}: required field `{field}` is missing or empty")
    return problems


def check_message_record(record) -> list:
    """Return every error for one message envelope, against message.schema.json's constraints."""
    problems = _check_object(record, MESSAGE_REQUIRED, MESSAGE_ALLOWED, "message")
    problems.extend(_find_forbidden_keys(record))

    if not isinstance(record, dict):
        return problems

    message_id = record.get("message_id")
    if message_id is not None and not (isinstance(message_id, str) and message_id):
        problems.append("`message_id` must be a non-empty string")

    sent_at = record.get("sent_at")
    if isinstance(sent_at, str) and sent_at and not TIMESTAMP_RE.match(sent_at):
        problems.append(f"`sent_at` value `{sent_at}` is not an ISO-8601 timestamp with timezone")

    kind = record.get("kind")
    if kind is not None and kind not in KIND_VALUES:
        problems.append(f"`kind` value `{kind}` is not one of {KIND_VALUES}")

    body = record.get("body")
    if body is not None and not (isinstance(body, str) and body):
        problems.append("`body` must be a non-empty string")

    sender = record.get("sender")
    if sender is not None:
        problems.extend(_check_object(sender, SENDER_REQUIRED, SENDER_ALLOWED, "sender"))
        if isinstance(sender, dict):
            agent_name = sender.get("agent_name")
            if agent_name is not None and not (isinstance(agent_name, str) and agent_name):
                problems.append("`sender.agent_name` must be a non-empty string")
            for field in SENDER_SLUG_FIELDS:
                v = sender.get(field)
                if isinstance(v, str) and v and not SLUG_RE.match(v):
                    problems.append(f"`sender.{field}` value `{v}` does not match slug pattern")

    subject = record.get("subject")
    if subject is not None:
        problems.extend(_check_object(subject, SUBJECT_REQUIRED, SUBJECT_ALLOWED, "subject"))
        if isinstance(subject, dict):
            repo = subject.get("repo")
            if isinstance(repo, str) and repo and not SLUG_RE.match(repo):
                problems.append(f"`subject.repo` value `{repo}` does not match slug pattern")
            block = subject.get("block")
            if block is not None and not (isinstance(block, str) and block):
                problems.append("`subject.block` must be a non-empty string")

    durable_home = record.get("durable_home")
    if durable_home is not None:
        problems.extend(
            _check_object(durable_home, DURABLE_HOME_REQUIRED, DURABLE_HOME_ALLOWED,
                           "durable_home")
        )
        if isinstance(durable_home, dict):
            channel = durable_home.get("channel")
            if channel is not None and channel not in DURABLE_HOME_CHANNELS:
                problems.append(
                    f"`durable_home.channel` value `{channel}` is not one of "
                    f"{sorted(DURABLE_HOME_CHANNELS)}"
                )
            ref = durable_home.get("ref")
            if ref is not None and not (isinstance(ref, str) and ref):
                problems.append("`durable_home.ref` must be a non-empty string")

    return problems


def _load(path: Path):
    """Return (record, error). error is a named string on any read/parse failure -- a
    nonexistent or unreadable path is reported, never silently treated as absent."""
    try:
        with open(path) as fh:
            return json.load(fh), None
    except FileNotFoundError:
        return None, f"path does not exist: {path}"
    except Exception as exc:                       # noqa: BLE001 - report, never raise
        return None, f"does not parse: {exc}"


# --- queue discovery ------------------------------------------------------------------------

def discover_queues(lock_dir: Path) -> list:
    """Return every `<lock_dir>/queue/<repo>/<lane>/` directory that exists on disk."""
    queue_root = lock_dir / QUEUE_SUBDIR
    if not queue_root.is_dir():
        return []
    found = []
    for repo_dir in sorted(queue_root.iterdir()):
        if not repo_dir.is_dir():
            continue
        for lane_dir in sorted(repo_dir.iterdir()):
            if lane_dir.is_dir():
                found.append(lane_dir)
    return found


def _discover_message_files(state_dir: Path) -> list:
    if not state_dir.is_dir():
        return []
    return sorted(p for p in state_dir.iterdir() if p.suffix == ".json")


def load_receipts(queue_dir: Path) -> list:
    """Parse receipts.jsonl into a list of dicts. A malformed line is reported via a synthetic
    dict carrying `_error` rather than raising -- one bad line must not hide every other one."""
    receipts_path = queue_dir / RECEIPTS_FILE
    if not receipts_path.is_file():
        return []
    receipts = []
    with open(receipts_path) as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                receipts.append(json.loads(line))
            except Exception as exc:                # noqa: BLE001 - report, never raise
                receipts.append({"_error": f"{receipts_path}:{lineno} does not parse: {exc}"})
    return receipts


def _receipt_counts(receipts: list) -> dict:
    """Map (message_id, from, to) -> count, over well-formed receipt lines only."""
    counts: dict = {}
    for r in receipts:
        if "_error" in r:
            continue
        key = (r.get("message_id"), r.get("from"), r.get("to"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def append_receipt(queue_dir: Path, message_id: str, frm: str, to: str) -> None:
    receipt = {
        "message_id": message_id,
        "from": frm,
        "to": to,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    with open(queue_dir / RECEIPTS_FILE, "a") as fh:
        fh.write(json.dumps(receipt) + "\n")


# --- drain / complete helpers (importable; BT.6.D is the consumer) --------------------------

def drain_queue(queue_dir: Path, limit: Optional[int] = None) -> list:
    """Move every file currently in `queue_dir/inbox/` into `queue_dir/processing/` by atomic
    os.rename, append one inbox->processing receipt per file actually moved, and return the
    parsed message records that were moved (in filename order).

    A rename that fails with FileNotFoundError means another drainer already won the race for
    that file -- it is skipped silently and the loop continues. That race-loss-is-silent
    behavior is the entire point of the rename-based design: it gives at-least-once delivery
    without a shared read cursor that two concurrent drainers could corrupt."""
    queue_dir = Path(queue_dir)
    inbox_dir = queue_dir / "inbox"
    processing_dir = queue_dir / "processing"
    processing_dir.mkdir(parents=True, exist_ok=True)

    files = _discover_message_files(inbox_dir)
    if limit is not None:
        files = files[:limit]

    moved = []
    for path in files:
        dest = processing_dir / path.name
        try:
            os.rename(path, dest)
        except FileNotFoundError:
            # Another drainer won this file first -- at-least-once, not exactly-once, at the
            # filesystem layer; the receipt ledger is what makes exactly-once assertable.
            continue
        record, err = _load(dest)
        if err:
            continue
        append_receipt(queue_dir, record.get("message_id"), "inbox", "processing")
        moved.append(record)
    return moved


def complete_message(queue_dir: Path, message_id: str) -> bool:
    """Move the file for `message_id` from `queue_dir/processing/` to `queue_dir/done/` and
    append one processing->done receipt. Returns False (without raising) if no matching file is
    found in processing/ -- e.g. it was already completed by another drainer."""
    queue_dir = Path(queue_dir)
    processing_dir = queue_dir / "processing"
    done_dir = queue_dir / "done"
    done_dir.mkdir(parents=True, exist_ok=True)

    match = None
    for path in _discover_message_files(processing_dir):
        m = FILENAME_RE.match(path.name)
        if m and m.group(2) == message_id:
            match = path
            break
    if match is None:
        return False

    dest = done_dir / match.name
    try:
        os.rename(match, dest)
    except FileNotFoundError:
        return False
    append_receipt(queue_dir, message_id, "processing", "done")
    return True


# --- main check pass ------------------------------------------------------------------------

def _check_one_queue(queue_dir: Path, quiet: bool) -> tuple:
    """Validate every message file in one queue's inbox/processing/done directories against the
    schema, the filename<->message_id identity, and the receipt-backed layout invariant. Returns
    (total, failed, lines)."""
    total = 0
    failed = 0
    lines: list = []

    receipts = load_receipts(queue_dir)
    for r in receipts:
        if "_error" in r:
            failed += 1
            lines.append(f"FAIL {r['_error']}")
    counts = _receipt_counts(receipts)

    for state in STATE_DIRS:
        state_dir = queue_dir / state
        for path in _discover_message_files(state_dir):
            total += 1
            record, load_err = _load(path)
            problems = [load_err] if load_err else check_message_record(record)

            message_id = record.get("message_id") if isinstance(record, dict) else None

            m = FILENAME_RE.match(path.name)
            if not m:
                problems.append(
                    f"filename `{path.name}` does not match `<ts>-<uuid>.json` "
                    f"(ISO-8601 basic-form UTC timestamp, then a dash, then the uuid)"
                )
            elif not problems and message_id is not None and m.group(2) != message_id:
                problems.append(
                    f"filename uuid `{m.group(2)}` does not match in-file message_id "
                    f"`{message_id}`"
                )

            if not problems and message_id is not None:
                inbox_to_processing = counts.get((message_id, "inbox", "processing"), 0)
                processing_to_done = counts.get((message_id, "processing", "done"), 0)

                if inbox_to_processing > 1:
                    problems.append(
                        f"duplicate receipt: {inbox_to_processing} inbox->processing receipts "
                        f"for message_id `{message_id}` (double-processing signal)"
                    )
                if processing_to_done > 1:
                    problems.append(
                        f"duplicate receipt: {processing_to_done} processing->done receipts "
                        f"for message_id `{message_id}` (double-processing signal)"
                    )

                if state == "processing" and inbox_to_processing < 1:
                    problems.append(
                        f"message file sits in processing/ but has no inbox->processing "
                        f"receipt for message_id `{message_id}` -- it must have been written "
                        f"directly into processing/, skipping the receipted transition"
                    )
                if state == "done":
                    if inbox_to_processing < 1:
                        problems.append(
                            f"message file sits in done/ but has no inbox->processing receipt "
                            f"for message_id `{message_id}`"
                        )
                    if processing_to_done < 1:
                        problems.append(
                            f"message file sits in done/ but has no processing->done receipt "
                            f"for message_id `{message_id}` -- it must have been written "
                            f"directly into done/, skipping the receipted transition"
                        )

            if problems:
                failed += 1
                lines.append(f"FAIL {path}")
                lines.extend(f"       {p}" for p in problems)
            elif not quiet:
                lines.append(f"ok   {path}")

    return total, failed, lines


def run(lock_dir: Optional[Path], quiet: bool) -> int:
    total = 0
    failed = 0
    lines: list = []

    queues = discover_queues(lock_dir) if lock_dir else []

    for queue_dir in queues:
        q_total, q_failed, q_lines = _check_one_queue(queue_dir, quiet)
        total += q_total
        failed += q_failed
        lines.extend(q_lines)

    for line in lines:
        print(line)

    if total == 0:
        print("no message records found (not a failure)")
        return 0

    print(f"\n{total} record(s) checked, {failed} failed")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lock-dir", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    lock_dir = resolve_lock_dir(args.lock_dir)
    return run(lock_dir, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
