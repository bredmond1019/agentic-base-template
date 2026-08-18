#!/usr/bin/env python3
"""Fixture suite for the extraction/port-block gate-capability authoring rule (D68).

WHAT THIS IS -- AND WHAT IT IS NOT
------------------------------------
`.claude/workflows/block-registration.md` Step 4 now requires an AGENT, at spec-authoring time,
to recognize when a block moves, copies, or forks existing code or data across a repo/crate/module
boundary ("extraction/port-shaped") and, for such a block, to name all four of: a moved-asset
content diff, a per-file test-count diff, a source-tree-measured-at-gate-time baseline for that
diff, and proof the stated gate is actually capable of failing on the shipped deliverable. That
judgment -- reading a spec in full context and deciding whether it moves code/data across a
boundary, and whether its stated AC set actually names all four constraints -- is made by an LLM.
This script cannot run that judgment, because there is no such agent to invoke headlessly in this
repo's own gate.

What this script CAN do, and does, is provide a **keyword/evidence-location classifier** that is a
PROXY for the rule -- a cheap, mechanical stand-in good enough to prove the rule's shape is sound
(it can fire, it can stay quiet, it can be shown wrong on a synthetic negative) and to show a real
historical instance (EN.9.A/EN.9.B) would have been flagged as needing the four checks. A green run
of this script is evidence that the PROXY behaves as specified. It is NOT evidence that a future
extraction/port block will actually apply the judgment correctly -- that is, and remains, checked
only by the agent authoring the spec and by a human reviewing it (D68's own declared un-gateable
criterion; see `planning/BT.ticket.extraction-port-gate-cannot-lie/tasks.md`).

REQUIRED CASES (from tasks.json task 3)
-----------------------------------------
1. FIRES      -- a synthetic AC-set description for an extraction/port block that is missing one
                 or more of the four constraints is flagged as non-compliant.
2. QUIET      -- block-registration.md's actual landed text (task 2 of this ticket) states all four
                 constraints and is NOT flagged; a curated set of ordinary, already-landed
                 non-extraction `planning/` specs is not even classified as extraction/port-shaped
                 (corpus-quiet case, walked with `os.walk(followlinks=True)` per the `planning/`
                 symlink trap).
3. NEGATIVE   -- the classifier can be shown wrong: fed the FIRES fixture again, it returns a hard
                 non-passing verdict, proving the mechanism is not decoration.
4. ANTI-DRIFT -- a judgment/importance-framed rewrite of the same rule text trips a drift detector
                 while the real landed text does not.
5. RETRO      -- a fixture built from the EN.9.A/EN.9.B failure text (four instances: dropped
                 `claude.toml` rule, wrong 114 baseline, wrong summed 257 total, feature-gated
                 deliverable never compiled by the workspace test command -- read live from
                 `core/engine-rs/planning/orchestration-run/engine-orchestration/notes.md` if
                 present on this machine, else an embedded fixture string citing that source) is
                 classified as extraction/port-shaped and as missing the four checks -- i.e. it
                 would have been flagged had the rule existed at authoring time.
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

# Does this text describe a block that moves, copies, or forks existing code or data across a
# repo/crate/module boundary? If not, none of the four constraints apply -- the rule is silent.
_EXTRACTION_PORT_PATTERNS = [
    re.compile(r"\bextraction[/-]port\b", re.IGNORECASE),
    re.compile(r"\bport-shaped\b", re.IGNORECASE),
    re.compile(r"\bmoves?,?\s*copies,?\s*or\s*forks\b", re.IGNORECASE),
    re.compile(r"\b(mov(?:e|ed|ing)|copi(?:ed|es)|port(?:ed|ing)?|extract(?:ed|ing|ion)?|fork(?:ed|ing)?)\b"
               r".{0,80}\b(repo|crate|module)\s*(?:/[a-z]+)*\s*boundary\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bterm-core\b.*\bport\b", re.IGNORECASE | re.DOTALL),
]

# Each entry: (constraint number, human label, any-of patterns that satisfy it).
_CONSTRAINT_PATTERNS: list[tuple[int, str, list[re.Pattern]]] = [
    (
        1,
        "moved-asset content diff",
        [
            re.compile(r"content diff\b.{0,80}(non-source|moved|asset|fixture)", re.IGNORECASE | re.DOTALL),
            re.compile(r"(non-source|moved).{0,40}asset.{0,40}content diff", re.IGNORECASE | re.DOTALL),
        ],
    ),
    (
        2,
        "per-file test-count diff",
        [
            re.compile(r"per-file test-?count diff", re.IGNORECASE),
            re.compile(r"per[- ]file\b.{0,40}test[- ]count\b.{0,20}diff", re.IGNORECASE | re.DOTALL),
        ],
    ),
    (
        3,
        "source-tree-measured-at-gate-time baseline",
        [
            re.compile(
                r"(measured|measur\w*)\b.{0,60}\bsource (repo|tree)\b.{0,40}\bgate time\b",
                re.IGNORECASE | re.DOTALL,
            ),
            re.compile(
                r"baseline\b.{0,80}\b(machine-measured|measured)\b.{0,40}\bgate time\b",
                re.IGNORECASE | re.DOTALL,
            ),
        ],
    ),
    (
        4,
        "gate shown capable of failing on the deliverable",
        [
            re.compile(
                r"(actually|must)\b.{0,20}(compile|run)\b.{0,60}\bvalidation command\b",
                re.IGNORECASE | re.DOTALL,
            ),
            re.compile(
                r"validation command\b.{0,60}\b(actually|must)\b.{0,20}(compile|run)\b",
                re.IGNORECASE | re.DOTALL,
            ),
            re.compile(r"gate\b.{0,40}capable of failing\b.{0,40}deliverable", re.IGNORECASE | re.DOTALL),
        ],
    ),
]

# Markers that indicate a "baseline" was read from planning prose rather than measured live --
# a signal the constraint-3 pattern above should NOT be satisfied even if other baseline language
# is present nearby.
_PLANNING_INVENTORY_BASELINE = re.compile(r"planning (inventory|prose|doc)", re.IGNORECASE)


def is_extraction_port_shaped(text: str) -> bool:
    """Return True if `text` describes a block that moves/copies/forks code or data across a
    repo/crate/module boundary -- the population D68's four constraints apply to."""
    return any(p.search(text) for p in _EXTRACTION_PORT_PATTERNS)


def missing_constraints(text: str) -> list[str]:
    """Return the human labels of any of the four D68 constraints NOT found in `text`."""
    missing = []
    for _num, label, patterns in _CONSTRAINT_PATTERNS:
        if not any(p.search(text) for p in patterns):
            missing.append(label)
    return missing


def check_extraction_ac_set(text: str) -> bool:
    """The compliance verdict a block-registration self-check would compute for one block
    description: True = compliant (not extraction/port-shaped, or all four constraints named),
    False = extraction/port-shaped and missing at least one constraint."""
    if not is_extraction_port_shaped(text):
        return True  # rule does not apply -- no ceremony required
    return not missing_constraints(text)


# ---------------------------------------------------------------------------
# Case 4 helper: judgment-trigger detector, applied to the RULE TEXT itself.
# ---------------------------------------------------------------------------

_JUDGMENT_WORDS = re.compile(r"\b(important|risky|risk)\b", re.IGNORECASE)
_NEGATIONS = ("never", "not ", "n't", " no ", "nor ", "instead of")


def uses_judgment_trigger(text: str) -> bool:
    """Return True if any sentence in `text` uses importance/risk as a POSITIVE trigger (i.e.
    without a nearby negation) -- the drift D68 explicitly forbids, matching D64's bar. A sentence
    that mentions importance/risk only to reject it as the trigger is safe and does not count."""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if not _JUDGMENT_WORDS.search(sentence):
            continue
        lowered = sentence.lower()
        if any(neg in lowered for neg in _NEGATIONS):
            continue
        return True
    return False


_SECTION_START = re.compile(
    r"Extraction/port-shaped blocks must declare (four )?gate-capability constraints", re.IGNORECASE
)
_SECTION_END_PHRASE = "EN.9.A/EN.9.B provenance"


def extract_rule_section(text: str) -> str | None:
    """Isolate the D68 rule's own prose from the rest of a doc, so the judgment-trigger check is
    not confused by unrelated text elsewhere in the same file. Returns None if the expected section
    markers are not found at all -- itself a form of drift."""
    start_match = _SECTION_START.search(text)
    if not start_match:
        return None
    start = start_match.start()
    end_idx = text.find(_SECTION_END_PHRASE, start)
    end = end_idx + len(_SECTION_END_PHRASE) if end_idx != -1 else len(text)
    return text[start:end]


def rule_keyed_on_evidence_location(text: str) -> bool:
    """True if `text` states the four-constraint rule AND does not use importance/risk as a
    positive trigger, scoped to the rule's own section of the document."""
    section = extract_rule_section(text)
    if section is None:
        return False
    has_all_four = not missing_constraints(section)
    return has_all_four and not uses_judgment_trigger(section)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def run_case_fires() -> None:
    ac_set = (
        "This block ports the parser module from crate-a to crate-b, moving existing code across "
        "the crate boundary. The acceptance criteria confirm the moved fixture files exist at the "
        "new path and that the port's test count (114) matches the plan's inventory total."
    )
    assert is_extraction_port_shaped(ac_set), "case 1 (FIRES): fixture must be recognized as extraction/port-shaped"
    missing = missing_constraints(ac_set)
    assert missing, "case 1 (FIRES): fixture is missing constraints and must be flagged"
    assert not check_extraction_ac_set(ac_set), (
        "case 1 (FIRES): an AC set naming only an existence check and a planning-inventory baseline "
        "must be flagged non-compliant"
    )


def run_case_quiet_landed_text() -> None:
    block_registration = (REPO_ROOT / ".claude" / "workflows" / "block-registration.md").read_text(encoding="utf-8")
    assert is_extraction_port_shaped(block_registration), (
        "case 2a (QUIET): block-registration.md must be recognized as containing extraction/port "
        "material (it names the rule and its scope)"
    )
    missing = missing_constraints(block_registration)
    assert not missing, (
        "case 2a (QUIET): block-registration.md's landed D68 paragraph must state all four "
        f"constraints; missing: {missing!r}"
    )
    assert check_extraction_ac_set(block_registration), (
        "case 2a (QUIET): the landed rule text itself must pass compliance"
    )


def run_case_negative() -> None:
    # Prove the mechanism can actually reject something -- feed it the case-1 fixture again and
    # assert the verdict is a hard False, not a pass-through.
    ac_set = (
        "This block ports the parser module from crate-a to crate-b, moving existing code across "
        "the crate boundary. The acceptance criteria confirm the moved fixture files exist at the "
        "new path and that the port's test count (114) matches the plan's inventory total."
    )
    verdict = check_extraction_ac_set(ac_set)
    assert verdict is False, "case 3 (NEGATIVE): classifier must be capable of rejecting -- got a pass"


# A curated, stable allowlist of already-landed, ordinary (non-extraction) specs -- chosen because
# they are not extraction/port-shaped at all, so they are exactly the population case 2b exists to
# prove stays quiet (never even classified as needing the four constraints). Deliberately NOT
# "every spec ever" (see module docstring): the wild corpus keeps growing under concurrent lanes,
# and pinning equality against it would make this gate flaky for reasons unrelated to the rule.
_ORDINARY_SPEC_RELATIVE_PATHS = [
    "archive/ticket-block-id-naming-convention-guard/tasks.md",
    "archive/ticket-harness-schema-realpath/tasks.md",
]


def run_case_quiet_corpus() -> None:
    # Reach the symlinked planning/ tree by following symlinks, per CLAUDE.md's symlink trap -- a
    # sweep without it would silently read nothing here and report a false pass.
    planning_dir = REPO_ROOT / "planning"
    found = []
    for dirpath, _dirnames, filenames in os.walk(planning_dir, followlinks=True):
        for fn in filenames:
            if fn == "tasks.md":
                found.append(str((Path(dirpath) / fn).relative_to(REPO_ROOT)))
    assert found, "case 2b (QUIET corpus): symlink-following sweep found zero tasks.md files -- traversal is broken"

    for rel in _ORDINARY_SPEC_RELATIVE_PATHS:
        candidates = [f for f in found if f.endswith(rel)]
        assert candidates, (
            f"case 2b (QUIET corpus): expected {rel} to be reachable via the -L sweep; "
            "found paths do not include it"
        )
        spec_path = REPO_ROOT / candidates[0]
        text = spec_path.read_text(encoding="utf-8")
        assert not is_extraction_port_shaped(text), (
            f"case 2b (QUIET corpus): {rel} is an ordinary, non-extraction spec and must not be "
            "classified as extraction/port-shaped"
        )
        assert check_extraction_ac_set(text), (
            f"case 2b (QUIET corpus): {rel} must pass compliance (the rule does not apply to it)"
        )


def run_case_anti_drift() -> None:
    block_registration = (REPO_ROOT / ".claude" / "workflows" / "block-registration.md").read_text(encoding="utf-8")
    assert rule_keyed_on_evidence_location(block_registration), (
        "case 4 (ANTI-DRIFT): block-registration.md must key the D68 rule on evidence location and "
        "gate capability, and must not use importance/risk as a positive trigger"
    )

    # Prove the guard can actually go red: two independent synthetic drift shapes.
    # (a) the rule keeps its constraint markers but is reworded into judgment framing.
    drifted_judgment = (
        "Extraction/port-shaped blocks must declare four gate-capability constraints (D68). "
        "Mark a block extraction/port-shaped if the move feels important or risky to the reviewer. "
        "Name a content diff of non-source moved asset fixtures, a per-file test-count diff "
        "measured from both trees at gate time with a baseline measured from the source repo at "
        "gate time, and a validation command that must actually compile and run the deliverable. "
        "See D68 for the EN.9.A/EN.9.B provenance this rule generalizes from."
    )
    assert not rule_keyed_on_evidence_location(drifted_judgment), (
        "case 4 (ANTI-DRIFT): a synthetic judgment-framed rewrite must trip the detector -- "
        "if this assertion is the one failing, the detector itself has gone decorative"
    )
    # (b) the rule section markers vanish entirely (e.g. renamed away without re-verification).
    drifted_missing = "This document no longer mentions the D68 rule by its expected name at all."
    assert not rule_keyed_on_evidence_location(drifted_missing), (
        "case 4 (ANTI-DRIFT): a document missing the rule section markers entirely must also "
        "count as drift, not silently pass"
    )


# Fallback fixture text if core/engine-rs is not checked out on this machine at test time. Cites
# the same four EN.9.A/EN.9.B instances as D68's Context section, sourced from
# core/engine-rs/planning/orchestration-run/engine-orchestration/notes.md (as read at authoring
# time of this ticket, 2026-08-17).
_RETRO_FALLBACK_TEXT = """
EN.9.A/EN.9.B ported term-core across the crate boundary from bastion, moving existing code and
data into the new crate. The block's acceptance criteria checked that the moved claude.toml file
existed at its new path and parsed -- it did, even though a [[rules]] entry inside it had silently
been dropped, deleting AskUserQuestion blocked-state detection on a production serve path. The
block's plan asserted the move carried 114 tests (tmux 27, model 36, claude_state 14, detect 37),
a number copied straight into the AC set from the plan document; the source tree actually carried
125. A second AC asserted a single combined total of 257 tests moved, which turned out to be the
sum of two independently wrong sub-counts (143 + 114) that happened to add up to a plausible
number. EN.9.B's entire deliverable -- driver, lease, hold, capture_cache -- shipped behind
term-core's non-default tokio feature; the block's stated acceptance command was
`cargo nextest run --workspace` (no --all-features), which does not enable that feature at all,
so the command reported success without ever touching the deliverable's code.
""".strip()

_NOTES_PATH = (
    REPO_ROOT.parent
    / "core"
    / "engine-rs"
    / "planning"
    / "orchestration-run"
    / "engine-orchestration"
    / "notes.md"
)


def _retro_fixture_text() -> str:
    # The fallback fixture is the classification input in both branches -- it is a tight summary
    # of the as-shipped failure (what the block's own AC set would have said had it named its
    # constraints the way it actually shipped), which is what "would this have been flagged"
    # needs to test. `notes.md`'s own prose is a multi-thousand-word retrospective that itself
    # discusses content diffs, baselines, and gate capability at length while diagnosing the bug
    # -- classifying that analysis text would test whether D68's own vocabulary matches D68's own
    # vocabulary, not whether the ORIGINAL failure would have tripped the rule. When notes.md is
    # present on this machine, corroborate the fallback fixture's facts against it instead of
    # substituting it as the classification input.
    if _NOTES_PATH.exists():
        notes_text = _NOTES_PATH.read_text(encoding="utf-8")
        for needle in ("114", "125", "257", "claude.toml", "capture_cache"):
            assert needle in notes_text, (
                f"case 5 (RETRO): notes.md is present but does not corroborate expected fact {needle!r} -- "
                "the fallback fixture may be stale relative to the source"
            )
    return _RETRO_FALLBACK_TEXT


def run_case_retro() -> None:
    text = _retro_fixture_text()
    assert is_extraction_port_shaped(text), (
        "case 5 (RETRO): the EN.9.A/EN.9.B failure text (or its fallback fixture) must be "
        "recognized as extraction/port-shaped"
    )
    missing = missing_constraints(text)
    assert missing, (
        "case 5 (RETRO): the EN.9.A/EN.9.B port -- as it actually shipped -- must be flagged as "
        f"missing constraints (it shipped without them); missing was empty, got: {missing!r}"
    )
    # All four constraints should be implicated by the real failure text: a dropped rule the
    # content-diff constraint would have caught, a wrong 114 baseline the source-tree-measured
    # constraint would have caught, a summed 257 total the per-file diff would have caught, and an
    # uncompiled feature-gated deliverable the gate-capability constraint would have caught.
    assert len(missing) >= 3, (
        "case 5 (RETRO): the EN.9.A/EN.9.B failure text implicates all four constraints; expected "
        f"at least 3 of 4 flagged as missing from the as-shipped description, got: {missing!r}"
    )


CASES = [
    ("fires", run_case_fires),
    ("quiet-landed-text", run_case_quiet_landed_text),
    ("negative", run_case_negative),
    ("quiet-corpus", run_case_quiet_corpus),
    ("anti-drift", run_case_anti_drift),
    ("retro-fixture", run_case_retro),
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
        print("FAIL: test_extraction_port_gate_rule.py")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"PASS: test_extraction_port_gate_rule.py ({len(CASES)} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
