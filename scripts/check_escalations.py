#!/usr/bin/env python3
"""Validate `planning/roadmaps/<roadmap>/escalations.jsonl` records (scripted-liaison-sweep).

Dependency-free on purpose, same discipline as check_messages.py, check_lane_agents.py and
check_lane_records.py: `jsonschema` is not installed anywhere in this fleet, so a validator that
imports it validates nothing and reports success. This checks the constraints in
escalation.schema.json -- required/allowed keys, the `kind`/`severity` enums, the `channel`
pattern, the `verified_by` evidence field's two accepted shapes (same contract as
check_messages.py's field of the same name), the `verified_at_sha` short-SHA pattern, the
`summary` length cap, and the explicit absence of a `priority`/`urgency` field -- by hand.

FILE LAYOUT: one append-only file per roadmap, `<roadmaps_dir>/<roadmap>/escalations.jsonl`,
never rewritten, never rotated -- mirrors `lane-log.jsonl` and `drain-log.jsonl`. Unlike
check_messages.py's queue directories (which live under a shared, fleet-wide `.fleet-locks/`),
`escalations.jsonl` is roadmap-local: `planning/roadmaps/` lives in the repo that owns the
roadmap (today, always HQ). `--roadmaps-dir` overrides the default, which is resolved via the
same brain-root walk-up as check_messages.py / check_lane_agents.py / commander_drain.sh, joined
with `planning/roadmaps`.

ONE JSON OBJECT PER LINE: a line that fails `json.loads` is a named error citing the file and
line number, and does not abort the rest of the file -- one bad line must not hide every other
one (same discipline as check_messages.py's `load_receipts`).

PRIORITY IS DELIBERATELY ABSENT: a record carrying a `priority` or `urgency` key anywhere in the
envelope, at any nesting depth, is a NAMED error, not merely an "unknown key" -- same rule and
same rationale as check_messages.py (D43 owns priority in this fleet).

Usage:
    check_escalations.py [--roadmaps-dir DIR] [--roadmap SLUG] [--quiet]

    --roadmaps-dir DIR   override the default `planning/roadmaps` directory (default: resolved
                         by walking up from cwd for a brain.toml, then joining `planning/roadmaps`)
    --roadmap SLUG       check only `<roadmaps-dir>/<SLUG>/escalations.jsonl` instead of every
                         roadmap directory found
    --quiet              print only failures and the summary

Exit code 1 if any record fails validation. Exit code 0 on a clean corpus, INCLUDING a corpus
with zero `escalations.jsonl` files -- that is the state of every roadmap today, before the
scripted sweep (block 5) ever writes one, and must stay silent (matches check_messages.py's
"no message records found" precedent).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
CHANNEL_RE = re.compile(r"^(notification|session:.+)$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

KIND_VALUES = ["operator-gate", "bail", "disagreement", "cross-repo-edit", "interrupt-request", "finding"]
SEVERITY_VALUES = ["blocking", "advisory"]

ESCALATION_REQUIRED = [
    "ts_utc", "repo", "lane", "kind", "severity", "channel", "gate_id", "summary",
    "verified_by", "durable_home", "verified_at_sha",
]
ESCALATION_ALLOWED = set(ESCALATION_REQUIRED) | {"block", "clears_when", "options"}

# options: the operator's response options for a `channel: notification` escalation -- declared
# by the lane at gate-definition time, never composed by the sweep script (scripted-liaison-
# sweep-design section 5). Required when channel is exactly "notification"; forbidden otherwise
# (a `session:<slug>` channel is never reduced to buttons -- Invariant 2,
# core/engine-rs/crates/engine-core/src/operator/channel.rs:4). Mirrors the real `bastion notify
# ask` CLI limits: 2-3 options (OPERATOR_MIN_RESPONSE_OPTIONS=2, WHATSAPP_MAX_REPLY_BUTTONS=3,
# limits.rs:47,40 -- a single option is rejected the same as zero), each label at most 20 chars
# (WHATSAPP_MAX_BUTTON_LABEL_CHARS, limits.rs:51).
OPTIONS_MIN = 2
OPTIONS_MAX = 3
OPTION_LABEL_MAX_CHARS = 20
OPTION_ALLOWED_KEYS = {"key", "label"}

# verified_by: same two accepted shapes as check_messages.py's field of the same name -- a
# command-plus-output block, or `UNVERIFIED: <who claimed it>`. A bare adjective like "measured"
# matches neither.
VERIFIED_BY_UNVERIFIED_RE = re.compile(r"^UNVERIFIED: \S[\s\S]*$")
VERIFIED_BY_EVIDENCE_RE = re.compile(r"^[\s\S]*\S[\s\S]*\n[\s\S]*\S[\s\S]*$")

FORBIDDEN_KEYS = {"priority", "urgency"}
FORBIDDEN_KEY_MESSAGE = (
    "field `{key}` is not allowed anywhere in an escalation record -- priority is deliberately "
    "absent: a lane-declared priority inflates to always-urgent and forks a second rubric "
    "alongside D43, which owns priority in this fleet"
)

ROADMAPS_SUBDIR = Path("planning") / "roadmaps"
ESCALATIONS_FILENAME = "escalations.jsonl"


# --- brain-root / roadmaps-dir resolution (mirrors check_messages.py's precedence) -----------

def find_brain_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk upward from `start` (default: cwd) looking for a directory containing brain.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "brain.toml").exists():
            return candidate
    return None


def resolve_roadmaps_dir(explicit: Optional[str] = None) -> Optional[Path]:
    """Resolve the `planning/roadmaps` directory to scan. Precedence: explicit --roadmaps-dir,
    else a brain.toml discovered by walking up from cwd, joined with `planning/roadmaps`.
    Returns None (never raises) if nothing resolves -- callers must then treat "no escalation
    files found" as the (silent) result, the same convention check_messages.py's
    resolve_lock_dir() documents for its own unresolved case."""
    if explicit:
        return Path(explicit)
    brain_root = find_brain_root()
    if brain_root is not None:
        return brain_root / ROADMAPS_SUBDIR
    return None


# --- recursive forbidden-key scan (identical shape to check_messages.py's) -------------------

def _find_forbidden_keys(node, path="$") -> list:
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


def _check_verified_by(value) -> list:
    if not isinstance(value, str) or not value.strip():
        return ["`verified_by` must be a non-empty, non-whitespace string"]
    if VERIFIED_BY_UNVERIFIED_RE.match(value) or VERIFIED_BY_EVIDENCE_RE.match(value):
        return []
    return [
        f"`verified_by` value `{value}` is neither `UNVERIFIED: <claimant>` nor a "
        f"command-plus-output block (a command line, then its output on a following line) -- "
        f"a bare adjective such as 'measured' does not satisfy this field"
    ]


def _check_options(value, present: bool, channel) -> list:
    """`options` is required exactly when `channel == "notification"`, forbidden otherwise --
    never a decision the sweep script gets to compose (see the field's comment above). Channel
    validity itself is reported separately by the `channel` check; this only gates presence."""
    is_notification = channel == "notification"

    if not present:
        if is_notification:
            return ["`options` is required when `channel` is `notification` -- the lane declares "
                    "the response options at gate-definition time, the sweep never composes them"]
        return []

    if not is_notification:
        return [f"`options` is only allowed when `channel` is `notification` (channel is "
                f"`{channel}`) -- a `session:<slug>` channel is never reduced to buttons "
                f"(Invariant 2: declared at gate-definition time, never degraded)"]

    if not isinstance(value, list):
        return ["`options` must be an array of {key, label} objects"]

    problems: list = []
    if len(value) < OPTIONS_MIN or len(value) > OPTIONS_MAX:
        problems.append(
            f"`options` has {len(value)} entries -- must have between {OPTIONS_MIN} and "
            f"{OPTIONS_MAX} (bastion notify ask allows at most 3 response options, and a single "
            f"option is rejected the same as zero: a 'decision, never a task' payload must offer "
            f"a real choice)"
        )

    for i, opt in enumerate(value):
        if not isinstance(opt, dict):
            problems.append(f"`options[{i}]` must be an object with `key` and `label`")
            continue
        unknown = sorted(set(opt) - OPTION_ALLOWED_KEYS)
        if unknown:
            problems.append(f"`options[{i}]`: unknown key(s): {', '.join(unknown)}")
        for req_key in ("key", "label"):
            v = opt.get(req_key)
            if not isinstance(v, str) or not v:
                problems.append(f"`options[{i}].{req_key}` is missing or empty")
        label = opt.get("label")
        if isinstance(label, str) and len(label) > OPTION_LABEL_MAX_CHARS:
            problems.append(
                f"`options[{i}].label` (\"{label}\") is {len(label)} chars, over the "
                f"{OPTION_LABEL_MAX_CHARS}-char WhatsApp reply-button title limit"
            )

    return problems


# --- record validation --------------------------------------------------------------------

def check_escalation_record(record) -> list:
    """Return every error for one escalation record, against escalation.schema.json's
    constraints."""
    if not isinstance(record, dict):
        return ["escalation record must be an object"]

    problems: list = []
    unknown = sorted(set(record) - ESCALATION_ALLOWED)
    if unknown:
        problems.append(f"escalation record: unknown key(s): {', '.join(unknown)}")
    for field in ESCALATION_REQUIRED:
        v = record.get(field)
        if v is None or (isinstance(v, str) and not v):
            problems.append(f"escalation record: required field `{field}` is missing or empty")

    problems.extend(_find_forbidden_keys(record))

    ts_utc = record.get("ts_utc")
    if isinstance(ts_utc, str) and ts_utc and not TIMESTAMP_RE.match(ts_utc):
        problems.append(
            f"`ts_utc` value `{ts_utc}` is not a full ISO-8601 timestamp with a `Z` or numeric "
            f"offset (a date-only value is not enough -- OKF frontmatter trap #4)"
        )

    for field in ("repo", "lane"):
        v = record.get(field)
        if isinstance(v, str) and v and not SLUG_RE.match(v):
            problems.append(f"`{field}` value `{v}` does not match slug pattern")

    kind = record.get("kind")
    if kind is not None and kind not in KIND_VALUES:
        problems.append(f"`kind` value `{kind}` is not one of {KIND_VALUES}")

    severity = record.get("severity")
    if severity is not None and severity not in SEVERITY_VALUES:
        problems.append(f"`severity` value `{severity}` is not one of {SEVERITY_VALUES}")

    block = record.get("block")
    if block is not None and not (isinstance(block, str) and block):
        problems.append("`block` must be a non-empty string when present")

    channel = record.get("channel")
    if isinstance(channel, str) and channel and not CHANNEL_RE.match(channel):
        problems.append(
            f"`channel` value `{channel}` does not match `^(notification|session:.+)$`"
        )

    problems.extend(_check_options(record.get("options"), "options" in record, channel))

    gate_id = record.get("gate_id")
    if gate_id is not None and not (isinstance(gate_id, str) and gate_id):
        problems.append("`gate_id` must be a non-empty string")

    summary = record.get("summary")
    if isinstance(summary, str):
        if not summary:
            problems.append("`summary` must be a non-empty string")
        elif len(summary) > 1024:
            problems.append(
                f"`summary` is {len(summary)} chars, over the 1024-char limit (mirrors the "
                f"WhatsApp body-text limit so a `notification`-channel escalation is composable "
                f"without truncation)"
            )

    verified_by = record.get("verified_by")
    if verified_by is not None:
        problems.extend(_check_verified_by(verified_by))

    verified_at_sha = record.get("verified_at_sha")
    if isinstance(verified_at_sha, str) and verified_at_sha and not SHA_RE.match(verified_at_sha):
        problems.append(
            f"`verified_at_sha` value `{verified_at_sha}` is not a plausible short git SHA "
            f"(7-40 lowercase hex characters)"
        )

    durable_home = record.get("durable_home")
    if durable_home is not None:
        if isinstance(durable_home, str) and not durable_home:
            problems.append("`durable_home` must be a non-empty string when given as a string")
        elif not isinstance(durable_home, (str, dict)):
            problems.append("`durable_home` must be an object or a non-empty string")

    clears_when = record.get("clears_when")
    if clears_when is not None and not isinstance(clears_when, str):
        problems.append("`clears_when` must be a string or null when present")

    return problems


# --- file / corpus discovery ------------------------------------------------------------------

def discover_escalation_files(roadmaps_dir: Path, roadmap: Optional[str] = None) -> list:
    """Return every `escalations.jsonl` path under `roadmaps_dir`. If `roadmap` is given, only
    that one roadmap's file is considered (even if it does not exist -- callers report that as
    "no file found", not an error)."""
    if roadmap:
        path = roadmaps_dir / roadmap / ESCALATIONS_FILENAME
        return [path] if path.is_file() else []
    if not roadmaps_dir.is_dir():
        return []
    found = []
    for entry in sorted(roadmaps_dir.iterdir()):
        if not entry.is_dir():
            continue
        candidate = entry / ESCALATIONS_FILENAME
        if candidate.is_file():
            found.append(candidate)
    return found


def _check_one_file(path: Path, quiet: bool) -> tuple:
    """Validate every line of one escalations.jsonl file. Returns (total, failed, lines)."""
    total = 0
    failed = 0
    lines: list = []

    with open(path) as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw_stripped = raw.strip()
            if not raw_stripped:
                continue
            total += 1
            try:
                record = json.loads(raw_stripped)
            except Exception as exc:                # noqa: BLE001 - report, never raise
                failed += 1
                lines.append(f"FAIL {path}:{lineno}")
                lines.append(f"       does not parse: {exc}")
                continue

            problems = check_escalation_record(record)
            if problems:
                failed += 1
                lines.append(f"FAIL {path}:{lineno}")
                lines.extend(f"       {p}" for p in problems)
            elif not quiet:
                lines.append(f"ok   {path}:{lineno}")

    return total, failed, lines


def run(roadmaps_dir: Optional[Path], quiet: bool, roadmap: Optional[str] = None) -> int:
    total = 0
    failed = 0
    lines: list = []

    files = discover_escalation_files(roadmaps_dir, roadmap) if roadmaps_dir else []

    for path in files:
        f_total, f_failed, f_lines = _check_one_file(path, quiet)
        total += f_total
        failed += f_failed
        lines.extend(f_lines)

    for line in lines:
        print(line)

    if total == 0:
        print("no escalation records found (not a failure)")
        return 0

    print(f"\n{total} record(s) checked, {failed} failed")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roadmaps-dir", default=None)
    ap.add_argument("--roadmap", default=None,
                     help="check only this roadmap's escalations.jsonl instead of every "
                          "roadmap directory found")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    roadmaps_dir = resolve_roadmaps_dir(args.roadmaps_dir)
    return run(roadmaps_dir, args.quiet, roadmap=args.roadmap)


if __name__ == "__main__":
    sys.exit(main())
