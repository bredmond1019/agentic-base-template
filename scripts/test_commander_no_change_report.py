#!/usr/bin/env python3
"""Source-assertion fixture over `.claude/commands/orchestration-commander.md`'s `## Report`
section (BT.ticket.commander-report-has-no-no-change-shape).

`/orchestration-commander` is a command document an agent reads, not a program this repo can
execute, so the document SOURCE as plain text is the only observable signal -- the same
constraint every other command check in this repo works under (see
`scripts/check_command_hazards.py`, `scripts/check_command_docs_no_write_path.py`).

Per D68 this fixture is written and run FIRST against the UNMODIFIED document and is expected to
FAIL: assertions A, B, C, D1, D2 and D3 should all report FAIL, while assertion E -- the fixture's
own positive control, proving the heading slice actually found text -- should report PASS. Once
task 2 edits the command doc to add the collapsed shape, all seven assertions must pass.

Seven named, independently-reported assertions:
  A  -- the `## Report` section specifies a collapsed shape containing `no change since` and a
        timestamp of the matched drain.
  B  -- it names the drain-log's last `record: "drain"` line (`drain-log.jsonl`) as the
        comparison basis, and states that basis is on-disk, not carried between drains.
  C  -- it requires the full (non-collapsed) shape on any delta, not merely prefers it.
  D1 -- never-collapse case: any of the three conditional sections is non-empty.
  D2 -- never-collapse case: no roadmap resolved.
  D3 -- never-collapse case: no prior `drain` record in the log.
  E  -- `## Stateless per drain` still contains its "nothing is carried between drains" sentence
        (positive control: if this fails, the heading slice came back empty and A-D3 failing
        proves nothing about the document).

D1/D2/D3 are three separate assertions, not one combined check, so a later regression names
WHICH never-collapse case was dropped -- that is the assertion that stops this ticket turning a
bored operator into an unread P0.

Sections are located by `## ` heading text, never by line number, because this document is edited
often and line numbers move.

Usage:
    python3 scripts/test_commander_no_change_report.py [--command PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_COMMAND = REPO_ROOT / ".claude" / "commands" / "orchestration-commander.md"

REPORT_HEADING = "## Report"
STATELESS_HEADING = "## Stateless per drain"


class SectionNotFoundError(Exception):
    """Raised when a `## ` heading cannot be located -- always an error, never a silent pass."""


def slice_section(document_text: str, heading: str) -> str:
    """Return the text of the section starting at `heading` (inclusive) up to (but not
    including) the next top-level `## ` heading, or end of document if `heading` is last.
    Raises SectionNotFoundError if `heading` is not present."""
    start = document_text.find(heading)
    if start == -1:
        raise SectionNotFoundError(f"heading not found: {heading!r}")
    # Search for the next "## " heading strictly after this one's first line.
    after_heading = start + len(heading)
    next_match = re.search(r"\n## ", document_text[after_heading:])
    if next_match is None:
        return document_text[start:]
    end = after_heading + next_match.start()
    return document_text[start:end]


def assert_true(name: str, condition: bool, detail: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status} {name}: {detail}")
    return condition


def run_assertions(document_text: str) -> list[bool]:
    results: list[bool] = []

    try:
        report = slice_section(document_text, REPORT_HEADING)
    except SectionNotFoundError as exc:
        print(f"FAIL A: could not slice `{REPORT_HEADING}` section: {exc}")
        print(f"FAIL B: could not slice `{REPORT_HEADING}` section: {exc}")
        print(f"FAIL C: could not slice `{REPORT_HEADING}` section: {exc}")
        print(f"FAIL D1: could not slice `{REPORT_HEADING}` section: {exc}")
        print(f"FAIL D2: could not slice `{REPORT_HEADING}` section: {exc}")
        print(f"FAIL D3: could not slice `{REPORT_HEADING}` section: {exc}")
        results.extend([False] * 6)
        report = ""
    else:
        report_lower = report.lower()

        # A -- collapsed shape containing "no change since" and a timestamp placeholder.
        has_no_change_since = "no change since" in report_lower
        has_timestamp_marker = bool(
            re.search(r"no change since\s*[<`]", report, re.IGNORECASE)
        ) or ("timestamp" in report_lower and has_no_change_since)
        results.append(assert_true(
            "A", has_no_change_since and has_timestamp_marker,
            "collapsed shape contains `no change since` plus a matched-drain timestamp",
        ))

        # B -- drain-log's last `drain` record named as the on-disk comparison basis.
        names_drain_log = "drain-log.jsonl" in report
        names_last_drain_record = bool(
            re.search(r"last\s+`?record:\s*\"drain\"`?|last\s+`?drain`?\s+record", report,
                      re.IGNORECASE)
        )
        states_on_disk = "on-disk" in report_lower or "on disk" in report_lower
        states_not_carried = bool(
            re.search(r"not\b[^.\n]{0,60}\bcarried between drains", report_lower)
        )
        results.append(assert_true(
            "B",
            names_drain_log and names_last_drain_record and states_on_disk and states_not_carried,
            "names drain-log's last `drain` record as the comparison basis and states it is "
            "on-disk, not carried between drains",
        ))

        # C -- full shape required (not merely preferred) on any delta.
        requires_full_on_delta = bool(
            re.search(r"full shape[^.\n]{0,80}\bdelta\b|\bdelta\b[^.\n]{0,80}full shape",
                      report, re.IGNORECASE)
        )
        unsure_emits_full = bool(re.search(r"unsure[^.\n]{0,40}full shape", report, re.IGNORECASE))
        results.append(assert_true(
            "C", requires_full_on_delta and unsure_emits_full,
            "requires the full shape on any delta, and an unsure drain emits the full shape",
        ))

        # D1/D2/D3 -- the three never-collapse cases, each its own assertion.
        d1 = bool(re.search(r"non-empty[^.\n]{0,80}conditional section", report, re.IGNORECASE))
        results.append(assert_true(
            "D1", d1, "never-collapse case: any non-empty conditional section",
        ))

        # "no roadmap resolved" already appears in the unmodified doc as part of the manifest
        # line's field enum (`drain-log: <recorded to <roadmap> | no roadmap resolved, skipped>`)
        # -- that is NOT a statement of a never-collapse rule, so require it to appear near
        # "collapse" to count as the rule this ticket adds.
        d2 = bool(
            re.search(r"no roadmap resolved[^.\n]{0,200}collapse"
                      r"|collapse[^.\n]{0,200}no roadmap resolved", report, re.IGNORECASE)
        )
        results.append(assert_true(
            "D2", d2, "never-collapse case: no roadmap resolved",
        ))

        d3 = bool(
            re.search(r"no prior[^.\n]{0,40}\bdrain\b[^.\n]{0,40}record", report, re.IGNORECASE)
        )
        results.append(assert_true(
            "D3", d3, "never-collapse case: no prior `drain` record in the log",
        ))

    # E -- positive control: `## Stateless per drain` still holds its statelessness sentence.
    try:
        stateless = slice_section(document_text, STATELESS_HEADING)
    except SectionNotFoundError as exc:
        print(f"FAIL E: could not slice `{STATELESS_HEADING}` section: {exc}")
        results.append(False)
    else:
        e = "nothing is carried between drains" in stateless.lower()
        results.append(assert_true(
            "E", e,
            "`## Stateless per drain` still contains its "
            "\"nothing is carried between drains\" sentence",
        ))

    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--command", type=Path, default=DEFAULT_COMMAND)
    args = ap.parse_args()

    if not args.command.is_file():
        print(f"FAIL: command file not found: {args.command}")
        return 1

    document_text = args.command.read_text()
    results = run_assertions(document_text)

    if all(results):
        print("ok   all seven assertions pass")
        return 0
    failed = results.count(False)
    print(f"FAIL: {failed} of {len(results)} assertions failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
