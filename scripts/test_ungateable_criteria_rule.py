#!/usr/bin/env python3
"""Fixture suite for the un-gateable-acceptance-criteria authoring rule (D64).

WHAT THIS IS -- AND WHAT IT IS NOT
------------------------------------
`.claude/commands/ticket.md` step 4.5 and `.claude/commands/generate-tasks.md`'s step-8 property
require an AGENT, at spec-authoring time, to apply a mechanical evidence-location test to every
Acceptance Criterion: does its evidence live in this repo/this language/observable in-process
(gated, say nothing), or in another process, another repo, a generated artifact, or an installed
artefact (declare it explicitly and pair it with a named failing command or a fixture-evidence
task)? That judgment is made by an LLM reading a spec in full context -- this script cannot run
that judgment, because there is no such agent to invoke headlessly in this repo's own gate.

What this script CAN do, and does, is provide a **keyword/evidence-location classifier** that is a
PROXY for the rule -- a cheap, mechanical stand-in good enough to prove the rule's shape is sound
(it can fire, it can stay quiet, it can be shown wrong on a synthetic negative) and to catch a real
historical instance the rule was written to catch. A green run of this script is evidence that the
PROXY behaves as specified. It is NOT evidence that a future `/ticket` or `/generate-tasks` run
actually applied the judgment correctly to a real spec -- that is, and remains, only ever checked by
the agent authoring the spec and by a human reviewing it. Reporting this suite as proof that "the
authoring rule changes how future specs are written" would be exactly the failure this ticket exists
to prevent (see `planning/ticket-declare-ungateable-acceptance-criteria/tasks.md`'s own declared
un-gateable criteria table) -- so this suite is deliberately scoped to the retro-fixture and
corpus-quiet cases as its evidence, never to the rule's real-world effect.

REQUIRED CASES (from tasks.json task 5)
-----------------------------------------
1. FIRES    -- an AC whose evidence is "the PR is actually merged" is flagged as needing
               declaration.
2. QUIET    -- an AC of "this function returns X" (backed by a unit test) is not flagged. This is
               the MORE LIKELY failure mode of the whole ticket (over-firing destroys the lean
               lane), so it gets equal weight to case 1.
3. NEGATIVE -- the classifier can reject: fed the case-1 fixture, it returns a non-passing verdict,
               proving the mechanism is not decoration.
4. RETRO    -- the real, as-authored AC text from the archived
               `ticket-auto-merge-returns-null-pr` spec ("The engine independently verifies that a
               PR exists ...") is read live off disk and flagged. That AC shipped inert and green;
               this is the instance the whole ticket is a response to.
5. ANTI-DRIFT GUARD -- the rule text landed in `ticket.md` and `generate-tasks.md` is keyed on
               evidence location, not on an "is this important/risky" framing. Proven two ways:
               (a) the real landed text does not trip a judgment-trigger detector, and (b) a
               synthetic fixture written in judgment-framing DOES trip it -- so the guard is shown
               capable of going red, not just capable of staying green today.
6. CORPUS QUIET -- classifying the Acceptance Criteria of a curated set of existing, ordinary,
               already-landed `planning/` specs (reached by following symlinks per CLAUDE.md trap
               2, since every `planning/` is a symlink) produces zero flags.

Case 6 walks the tree with `os.walk(..., followlinks=True)` rather than shelling out to `rg -L`:
this repo's sandbox does not always have a real `rg` binary on `PATH` (only a shell-function
wrapper that itself resolves to nothing here), and a subprocess call bypasses shell functions
entirely. `followlinks=True` is the same symlink-traversal discipline CLAUDE.md trap 2 asks for,
applied without depending on an external binary being present.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# The classifier -- a PROXY for the agent-executed rule. See module docstring.
# ---------------------------------------------------------------------------

# Patterns whose presence in an Acceptance Criterion's text suggests its evidence lives outside
# this repo's in-process, in-language boundary: another process (an external CLI), another repo
# (a sibling git index), a generated artifact, or an installed artefact.
_EXTERNAL_EVIDENCE_PATTERNS = [
    re.compile(r"\bgh\b", re.IGNORECASE),
    re.compile(r"\bpr\b.{0,20}\b(merged|exists|created)\b", re.IGNORECASE),
    re.compile(r"\b(merged|exists|created)\b.{0,20}\bpr\b", re.IGNORECASE),
    re.compile(r"another (repo|process)", re.IGNORECASE),
    re.compile(r"sibling git", re.IGNORECASE),
    re.compile(r"status\.md", re.IGNORECASE),
    re.compile(r"emit-state", re.IGNORECASE),
    re.compile(r"installed (artefact|artifact|binary)", re.IGNORECASE),
    re.compile(r"distributed copy", re.IGNORECASE),
    re.compile(r"independently verif", re.IGNORECASE),
]

# Markers that indicate a criterion has already been paired with a named failing command or a
# dedicated fixture-evidence task, i.e. it has been DECLARED per the rule, not left un-gated.
_DECLARATION_MARKERS = [
    re.compile(r"un-?gateable", re.IGNORECASE),
    re.compile(r"fixture[- ]evidence", re.IGNORECASE),
    re.compile(r"retro-fixture", re.IGNORECASE),
    re.compile(r"named (failing )?command", re.IGNORECASE),
]


def needs_declaration(ac_text: str) -> bool:
    """Return True if `ac_text`'s evidence appears to live outside the in-repo/in-language
    boundary -- i.e. it falls in the 'declare it' row of the evidence-location table."""
    return any(p.search(ac_text) for p in _EXTERNAL_EVIDENCE_PATTERNS)


def is_declared(ac_text: str) -> bool:
    """Return True if `ac_text` already carries a declaration marker (un-gateable / fixture-
    evidence / retro-fixture / named failing command)."""
    return any(p.search(ac_text) for p in _DECLARATION_MARKERS)


def check_ac(ac_text: str) -> bool:
    """The compliance verdict a `/ticket` or `/generate-tasks` self-check would compute for one
    Acceptance Criterion: True = compliant (either in-repo, or declared), False = violates the
    rule (evidence lives outside the boundary and it was not declared)."""
    if not needs_declaration(ac_text):
        return True  # ordinary, in-repo criterion -- no ceremony required
    return is_declared(ac_text)


# ---------------------------------------------------------------------------
# Case 5 helper: judgment-trigger detector, applied to the RULE TEXT itself (not an AC).
# ---------------------------------------------------------------------------

_JUDGMENT_WORDS = re.compile(r"\b(important|risky|risk)\b", re.IGNORECASE)
_NEGATIONS = ("never", "not ", "n't", " no ", "nor ", "instead of")


def uses_judgment_trigger(text: str) -> bool:
    """Return True if any sentence in `text` uses importance/risk as a POSITIVE trigger (i.e.
    without a nearby negation) -- the drift this ticket explicitly forbids. A sentence that
    mentions importance/risk only to reject it as the trigger (e.g. 'never on how important or
    risky it feels') is safe and does not count."""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if not _JUDGMENT_WORDS.search(sentence):
            continue
        lowered = sentence.lower()
        if any(neg in lowered for neg in _NEGATIONS):
            continue
        return True
    return False


_SECTION_START = re.compile(r"un-?gateable (acceptance )?criteria (must be declared|are declared)", re.IGNORECASE)
_SECTION_END_PHRASE = "invisible unless named"


def extract_rule_section(text: str) -> str | None:
    """Isolate the un-gateable-criteria rule's own prose from the rest of a command doc, so the
    judgment-trigger check is not confused by unrelated text elsewhere in the same file (e.g.
    `/ticket`'s model-selection rubric mentions 'high-risk' in a completely different step).
    Returns None if the expected section markers are not found at all -- itself a form of drift."""
    start_match = _SECTION_START.search(text)
    if not start_match:
        return None
    start = start_match.start()
    end_idx = text.find(_SECTION_END_PHRASE, start)
    end = end_idx + len(_SECTION_END_PHRASE) if end_idx != -1 else len(text)
    return text[start:end]


def rule_keyed_on_evidence_location(text: str) -> bool:
    """True if `text` states the evidence-location table AND does not use importance/risk as a
    positive trigger, scoped to the rule's own section of the document."""
    section = extract_rule_section(text)
    if section is None:
        return False
    has_table = "evidence location" in section.lower()
    return has_table and not uses_judgment_trigger(section)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def run_case_fires() -> None:
    ac = "The engine confirms the PR is actually merged before closing the block."
    assert needs_declaration(ac), "case 1 (FIRES): expected external-evidence pattern to match"
    assert not check_ac(ac), (
        "case 1 (FIRES): an undeclared external-process criterion must be flagged, "
        "in a repo whose own checks are node --check plus Python"
    )


def run_case_quiet() -> None:
    ac = "get_widget_count() returns the correct integer for an empty collection (unit test: test_widget_count_empty)."
    assert not needs_declaration(ac), "case 2 (QUIET): ordinary in-repo criterion must not match external-evidence patterns"
    assert check_ac(ac), "case 2 (QUIET): ordinary criterion with a unit test must pass with no ceremony"


def run_case_negative() -> None:
    # Prove the mechanism can actually reject something -- feed it the case-1 fixture again and
    # assert the verdict is a hard False, not a pass-through.
    ac = "The engine confirms the PR is actually merged before closing the block."
    verdict = check_ac(ac)
    assert verdict is False, "case 3 (NEGATIVE): classifier must be capable of rejecting -- got a pass"


def run_case_retro() -> None:
    spec_path = REPO_ROOT / "planning" / "archive" / "ticket-auto-merge-returns-null-pr" / "tasks.md"
    assert spec_path.exists(), f"case 4 (RETRO): expected archived spec at {spec_path}"
    text = spec_path.read_text(encoding="utf-8")
    match = re.search(
        r"The engine \*\*independently verifies\*\* that a PR exists[^\n]*", text
    )
    assert match, "case 4 (RETRO): could not find the as-authored AC text in the archived spec"
    ac_text = match.group(0)
    assert needs_declaration(ac_text), (
        "case 4 (RETRO): the real as-authored AC must trip the external-evidence classifier"
    )
    assert not check_ac(ac_text), (
        "case 4 (RETRO): the real as-authored AC shipped with no declaration and no fixture task -- "
        "it must be flagged as non-compliant, exactly as it should have been at authoring time"
    )


def run_case_anti_drift() -> None:
    ticket_md = (REPO_ROOT / ".claude" / "commands" / "ticket.md").read_text(encoding="utf-8")
    generate_tasks_md = (REPO_ROOT / ".claude" / "commands" / "generate-tasks.md").read_text(encoding="utf-8")

    for name, text in (("ticket.md", ticket_md), ("generate-tasks.md", generate_tasks_md)):
        assert rule_keyed_on_evidence_location(text), (
            f"case 5 (ANTI-DRIFT): {name} must key the rule on evidence location and must not use "
            "importance/risk as a positive trigger"
        )

    # Prove the guard can actually go red: two independent synthetic drift shapes.
    # (a) the rule section keeps its markers but is reworded into judgment framing.
    drifted_judgment = (
        "Un-gateable criteria are declared (D64) -- can fail. Mark the criterion un-gateable if it "
        "seems important or risky to the reviewer. There is no evidence location table here, only "
        "this evidence location sentence to satisfy the has-table probe. "
        "the divergence is invisible unless named."
    )
    assert not rule_keyed_on_evidence_location(drifted_judgment), (
        "case 5 (ANTI-DRIFT): a synthetic judgment-framed rewrite must trip the detector -- "
        "if this assertion is the one failing, the detector itself has gone decorative"
    )
    # (b) the rule section markers vanish entirely (e.g. renamed away without re-verification).
    drifted_missing = "This document no longer mentions the rule by its expected name at all."
    assert not rule_keyed_on_evidence_location(drifted_missing), (
        "case 5 (ANTI-DRIFT): a document missing the rule section markers entirely must also "
        "count as drift, not silently pass"
    )


# A curated, stable allowlist of already-landed, ordinary specs -- chosen because their Acceptance
# Criteria are all observable in-repo (grep/parse assertions over this repo's own files), so they
# are exactly the population case 6 exists to prove stays quiet. Deliberately NOT "every spec ever"
# (see module docstring): the wild corpus keeps growing under concurrent lanes, and pinning
# equality against it would make this gate flaky for reasons unrelated to the rule under test.
_ORDINARY_SPEC_RELATIVE_PATHS = [
    "ticket-block-id-naming-convention-guard/tasks.md",
    "ticket-harness-schema-realpath/tasks.md",
]


def run_case_corpus_quiet() -> None:
    # Reach the symlinked planning/ tree by following symlinks, per CLAUDE.md trap 2 -- a sweep
    # without it would silently read nothing here and report a false pass.
    planning_dir = REPO_ROOT / "planning"
    found = []
    for dirpath, _dirnames, filenames in os.walk(planning_dir, followlinks=True):
        for fn in filenames:
            if fn == "tasks.md":
                found.append(str((Path(dirpath) / fn).relative_to(REPO_ROOT)))
    assert found, "case 6 (CORPUS QUIET): symlink-following sweep found zero tasks.md files -- traversal is broken"

    for rel in _ORDINARY_SPEC_RELATIVE_PATHS:
        candidates = [f for f in found if f.endswith(rel)]
        assert candidates, (
            f"case 6 (CORPUS QUIET): expected {rel} to be reachable via the -L sweep; "
            "found paths do not include it"
        )
        spec_path = REPO_ROOT / candidates[0]
        text = spec_path.read_text(encoding="utf-8")
        ac_section = re.search(
            r"## Acceptance Criteria\n(.*?)\n## ", text, re.DOTALL
        )
        assert ac_section, f"case 6 (CORPUS QUIET): {rel} has no Acceptance Criteria section"
        bullets = [
            line.strip("- ").strip()
            for line in ac_section.group(1).splitlines()
            if line.strip().startswith("-")
        ]
        assert bullets, f"case 6 (CORPUS QUIET): {rel} parsed zero AC bullets"
        for bullet in bullets:
            assert check_ac(bullet), (
                f"case 6 (CORPUS QUIET): {rel} is a curated ordinary spec and must stay silent, "
                f"but this bullet was flagged: {bullet!r}"
            )


CASES = [
    ("fires", run_case_fires),
    ("quiet", run_case_quiet),
    ("negative", run_case_negative),
    ("retro-fixture", run_case_retro),
    ("anti-drift", run_case_anti_drift),
    ("corpus-quiet", run_case_corpus_quiet),
]


def main() -> int:
    failures = []
    for name, fn in CASES:
        try:
            fn()
        except AssertionError as exc:
            failures.append(f"{name}: {exc}")
        except Exception as exc:  # noqa: BLE001 -- report any unexpected error as a failure too
            failures.append(f"{name}: unexpected error: {exc}")

    if failures:
        print("FAIL: test_ungateable_criteria_rule.py")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"PASS: test_ungateable_criteria_rule.py ({len(CASES)} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
