#!/usr/bin/env python3
"""Fixture suite for check_lane_records.py (D71).

Self-contained, no pytest dependency, in the same self-contained fixture style used across this
repo's other harness gates: builds a
synthetic corpus in a temp dir (a fake brain.toml + fake repo directories carrying real
planning/harness.json files, plus lane-*.json records in both the current
planning/roadmaps/<slug>/ layout and the legacy planning/<slug>/ layout) and drives the real
check_lane_records.py module against it -- both by calling its functions directly and by running
it as a subprocess, so both the validation logic and the CLI/exit-code contract are exercised.

A checker never observed going red is not evidence (D68): every negative fixture here asserts a
non-zero exit or a named diagnostic, not merely that the checker ran.

Run: python3 scripts/test_check_lane_records.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "check_lane_records.py"

_spec = importlib.util.spec_from_file_location("check_lane_records", MODULE_PATH)
check_lane_records = importlib.util.module_from_spec(_spec)
sys.modules["check_lane_records"] = check_lane_records
_spec.loader.exec_module(check_lane_records)

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{label}: {detail}")


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# --- synthetic corpus --------------------------------------------------------------------
#
#   <tmp>/brain.toml
#   <tmp>/light-repo/planning/harness.json      (no heavy signal)
#   <tmp>/heavy-repo/planning/harness.json      (uiTest.enabled -> heavy)
#   <tmp>/consumer-repo/planning/roadmaps/my-roadmap/lane-alpha.json   (positive, well-formed)
#   <tmp>/consumer-repo/planning/roadmaps/my-roadmap/lane-beta.json    (positive, two repos)
#   <tmp>/consumer-repo/planning/legacy-roadmap/lane-gamma.json        (legacy layout)
#
# brain.toml registers "ghost-repo" with a repo_path that never exists on disk, to prove a
# nonexistent path is reported as a named error, never as heavy:false.

def build_corpus(tmp: Path) -> Path:
    _write(tmp / "brain.toml", """
[[repos]]
slug = "light-repo"
repo_path = "light-repo"

[[repos]]
slug = "heavy-repo"
repo_path = "heavy-repo"

[[repos]]
slug = "consumer-repo"
repo_path = "consumer-repo"

[[repos]]
slug = "ghost-repo"
repo_path = "ghost-repo"
""")

    _write_json(tmp / "light-repo" / "planning" / "harness.json", {
        "validation": {"checks": [{"name": "unit", "command": "pytest", "gates": True}]},
    })
    _write_json(tmp / "heavy-repo" / "planning" / "harness.json", {
        "uiTest": {"enabled": True},
        "validation": {"checks": []},
    })
    # ghost-repo deliberately has no directory on disk at all.

    roadmaps_root = tmp / "consumer-repo" / "planning" / "roadmaps" / "my-roadmap"
    _write_json(roadmaps_root / "lane-alpha.json", {
        "lane": "alpha",
        "repo": "light-repo",
        "roadmap": "my-roadmap",
        "blocks": [
            {"id": "BT.1.A", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
        ],
        "budget": {"heavy": False},
    })
    _write_json(roadmaps_root / "lane-beta.json", {
        "lane": "beta",
        "repo": "consumer-repo",
        "roadmap": "my-roadmap",
        "blocks": [
            {"id": "BT.1.B", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
            {"id": "OK.2.C", "origin_roadmap": "my-roadmap", "repo": "other-repo"},
        ],
    })

    legacy_root = tmp / "consumer-repo" / "planning" / "legacy-roadmap"
    _write_json(legacy_root / "lane-gamma.json", {
        "lane": "gamma",
        "repo": "light-repo",
        "roadmap": "legacy-roadmap",
        "blocks": [
            {"id": "BT.2.A", "origin_roadmap": "legacy-roadmap", "repo": "consumer-repo"},
        ],
    })

    return tmp


# --- direct-function fixtures --------------------------------------------------------------

def check_no_records_is_not_a_failure() -> None:
    with tempfile.TemporaryDirectory() as td:
        empty_planning = Path(td) / "planning"
        empty_planning.mkdir()
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--planning", str(empty_planning), "--quiet"],
            capture_output=True, text=True,
        )
        check("empty corpus exits 0 (not a failure)", proc.returncode == 0, proc.stdout + proc.stderr)
        check("empty corpus says so explicitly", "no lane records found" in proc.stdout, proc.stdout)


def check_dependency_free() -> None:
    """The docstring is allowed to *mention* jsonschema (it explains why the script avoids it);
    what must never appear is an actual import of it or any other third-party package."""
    import ast

    tree = ast.parse(MODULE_PATH.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    stdlib_and_local = {
        "argparse", "json", "os", "re", "subprocess", "sys", "pathlib",
        "tomllib", "__future__", "check_lane_records",
    }
    third_party = imported - stdlib_and_local
    check("check_lane_records.py imports no third-party package (no jsonschema)",
          third_party == set(), f"unexpected imports: {sorted(third_party)}")


def check_positive_well_formed() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = build_corpus(Path(td))
        lane_path = tmp / "consumer-repo" / "planning" / "roadmaps" / "my-roadmap" / "lane-alpha.json"
        repo_paths = check_lane_records.repo_paths_for(lane_path)
        problems, _ = check_lane_records.check(lane_path, repo_paths)
        check("well-formed record with a matching budget.heavy validates cleanly",
              problems == [], f"problems: {problems}")


def check_positive_two_repos() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = build_corpus(Path(td))
        lane_path = tmp / "consumer-repo" / "planning" / "roadmaps" / "my-roadmap" / "lane-beta.json"
        repo_paths = check_lane_records.repo_paths_for(lane_path)
        problems, _ = check_lane_records.check(lane_path, repo_paths)
        check("a lane record whose blocks[] span two different repos validates",
              problems == [], f"problems: {problems}")


def check_legacy_and_roadmaps_discovery() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = build_corpus(Path(td))
        planning_root = tmp / "consumer-repo" / "planning"
        found = check_lane_records.discover_lane_files(planning_root)
        names = sorted(p.name for p in found)
        check("discovery finds the roadmaps/<slug>/ layout record",
              "lane-alpha.json" in names, f"found: {names}")
        check("discovery finds the legacy planning/<slug>/ layout record",
              "lane-gamma.json" in names, f"found: {names}")
        check("discovery finds all three fixture records",
              len(names) == 3, f"found: {names}")


def check_derived_artifacts_at_the_planning_root_are_not_lane_records() -> None:
    """mev's three DERIVED lane-*.json artifacts live directly in the planning root and match the
    lane-file glob exactly. Discovery must not pick them up, and a corpus holding them must still
    exit 0.

    This is the regression that made the real checker exit 1 over a corpus with ZERO authored lane
    records (measured at HQ 832b6747: 3 FAILs, all three of them mev artifacts), which would have
    red-gated the brain root the moment HQ.8.A registered it as a gated check.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = build_corpus(Path(td))
        planning_root = tmp / "consumer-repo" / "planning"

        # Exactly the shapes mev emits, straight into the planning root.
        _write_json(planning_root / "lane-segments.json",
                    {"derived_at": "2026-08-21T00:00:00Z", "degraded": False, "segments": []})
        _write_json(planning_root / "lane-availability.json",
                    {"derived_at": "2026-08-21T00:00:00Z", "degraded": False, "segments": []})
        _write_json(planning_root / "lane-frontier.json",
                    {"derived_at": "2026-08-21T00:00:00Z", "entries": [], "gate_ranks": {}})

        found = check_lane_records.discover_lane_files(planning_root)
        names = sorted(p.name for p in found)
        check("mev's derived artifacts are not discovered as lane records",
              not any(n.startswith("lane-segments") or n.startswith("lane-availability")
                      or n.startswith("lane-frontier") for n in names),
              f"found: {names}")
        check("the three real fixture records are still discovered",
              len(names) == 3, f"found: {names}")

        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--planning", str(planning_root), "--quiet"],
            capture_output=True, text=True,
        )
        check("a corpus carrying mev's derived artifacts still exits 0",
              proc.returncode == 0, proc.stdout + proc.stderr)


def check_a_lane_record_at_the_planning_root_is_the_deliberate_blind_spot() -> None:
    """The control for the fixture above. The exclusion is by LOCATION, so a well-formed lane
    record placed directly in the planning root is deliberately invisible. Pinned so the trade-off
    is a recorded decision rather than a silent hole: every real lane record, in both layouts,
    lives in a roadmap subdirectory.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = build_corpus(Path(td))
        planning_root = tmp / "consumer-repo" / "planning"
        _write_json(planning_root / "lane-rootlevel.json", {
            "lane": "rootlevel",
            "roadmap": "my-roadmap",
            "blocks": [{"id": "BT.9.Z", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"}],
        })
        names = sorted(p.name for p in check_lane_records.discover_lane_files(planning_root))
        check("a lane record directly in the planning root is not discovered (by design)",
              "lane-rootlevel.json" not in names, f"found: {names}")


def check_positive_no_top_level_repo() -> None:
    """A lane record with NO top-level `repo` validates.

    A lane is not single-repo in this corpus, so a lane-level repo is an optional default and
    never a source of inheritance -- requiring it would force every genuinely multi-repo lane to
    name one repo as if it owned the lane. Every blocks[] entry carries its own required `repo`.
    """
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lane-multi.json"
        _write_json(path, {
            "lane": "multi",
            "roadmap": "my-roadmap",
            "blocks": [
                {"id": "BT.1.A", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
                {"id": "OK.2.C", "origin_roadmap": "my-roadmap", "repo": "other-repo"},
            ],
        })
        problems, _ = check_lane_records.check(path, {})
        check("a lane record with no top-level repo validates",
              not problems, f"problems: {problems}")


def check_positive_notes_field() -> None:
    """A lane-level `notes` string (SPEC/RISK/EXCEPTION-class prose) validates cleanly."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lane-noted.json"
        _write_json(path, {
            "lane": "noted",
            "roadmap": "my-roadmap",
            "blocks": [
                {"id": "BT.1.A", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
            ],
            "notes": "MERGE, DO NOT INSTALL -- needs BT.5.A first.",
        })
        problems, _ = check_lane_records.check(path, {})
        check("a lane record carrying `notes` validates cleanly",
              problems == [], f"problems: {problems}")


def check_negative_per_block_note() -> None:
    """A per-block `note` is REJECTED, naming the offending key. This is the point of the
    fixture pair: rejecting a per-block note is a deliberate design decision (two lanes agreed
    on evidence that per-block briefings route to the block record, never a lane file), and a
    decision with no test is one the next author silently reverses for symmetry with `notes`."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lane-bad-note.json"
        _write_json(path, {
            "lane": "bad-note",
            "roadmap": "my-roadmap",
            "blocks": [
                {
                    "id": "BT.1.A",
                    "origin_roadmap": "my-roadmap",
                    "repo": "consumer-repo",
                    "note": "this per-block briefing must be rejected",
                },
            ],
        })
        problems, _ = check_lane_records.check(path, {})
        named = [p for p in problems if "blocks[0]" in p and "note" in p]
        check("a per-block `note` is rejected, naming the offending key",
              len(named) == 1, f"problems: {problems}")


def check_positive_leading_worktree_isolation() -> None:
    """Post-D81-lift: a lane record whose isolation LEADING TOKEN is --worktree validates cleanly
    -- the moratorium that once rejected this was lifted 2026-08-28 (BT.ticket.worktree-smoke-
    fixture verified a real --worktree run end to end)."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lane-worktree.json"
        _write_json(path, {
            "lane": "worktree-lane",
            "roadmap": "my-roadmap",
            "blocks": [
                {"id": "BT.1.A", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
            ],
            "isolation": "--worktree",
        })
        problems, _ = check_lane_records.check(path, {})
        check("a leading --worktree isolation directive validates cleanly post-D81-lift",
              problems == [], f"problems: {problems}")


def check_positive_d81_preserved_isolation() -> None:
    """A record still carrying the pre-lift D81-rewritten free text (leading --no-worktree,
    preserving the prior --worktree directive verbatim later in the string) still validates
    cleanly -- the field is free text and the old leading-token rejection is gone, so this
    historical shape is not penalized either. Copied verbatim from a real lane record
    (planning/roadmaps/cli-surface-to-skills/lane-factory.json in the brain root), not
    paraphrased."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lane-preserved.json"
        _write_json(path, {
            "lane": "preserved",
            "roadmap": "my-roadmap",
            "blocks": [
                {"id": "BT.1.A", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
            ],
            "isolation": (
                "--no-worktree — FORCED by D81 (worktree moratorium, 2026-08-23). Do not "
                "override until D81 is lifted. Prior directive, preserved verbatim for when it "
                "is: --worktree — POLICY, always. base-template owns .claude/workflows/"
                "sdlc-*.js; a chain here edits the engines while they are executing it."
            ),
        })
        problems, _ = check_lane_records.check(path, {})
        check("a D81-preserved isolation string (leading --no-worktree) validates cleanly",
              problems == [], f"problems: {problems}")


def check_positive_plain_no_worktree_isolation() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lane-plain.json"
        _write_json(path, {
            "lane": "plain",
            "roadmap": "my-roadmap",
            "blocks": [
                {"id": "BT.1.A", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
            ],
            "isolation": "--no-worktree",
        })
        problems, _ = check_lane_records.check(path, {})
        check("a plain --no-worktree isolation directive validates cleanly",
              problems == [], f"problems: {problems}")


def check_positive_absent_isolation() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lane-noisolation.json"
        _write_json(path, {
            "lane": "noisolation",
            "roadmap": "my-roadmap",
            "blocks": [
                {"id": "BT.1.A", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
            ],
        })
        problems, _ = check_lane_records.check(path, {})
        check("a lane record with no isolation field at all validates cleanly",
              problems == [], f"problems: {problems}")


def check_negative_missing_origin_roadmap() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        path = tmp / "lane-bad.json"
        _write_json(path, {
            "lane": "bad",
            "repo": "light-repo",
            "roadmap": "my-roadmap",
            "blocks": [
                {"id": "BT.1.A", "repo": "consumer-repo"},  # origin_roadmap missing
            ],
        })
        problems, _ = check_lane_records.check(path, {})
        check("a blocks[] entry missing origin_roadmap is rejected",
              any("origin_roadmap" in p for p in problems), f"problems: {problems}")


def check_negative_duplicate_block_id() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lane-bad.json"
        _write_json(path, {
            "lane": "bad",
            "repo": "light-repo",
            "roadmap": "my-roadmap",
            "blocks": [
                {"id": "BT.1.A", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
                {"id": "BT.1.A", "origin_roadmap": "my-roadmap", "repo": "other-repo"},
            ],
        })
        problems, _ = check_lane_records.check(path, {})
        check("a duplicated block id within a record is rejected",
              any("duplicate block id" in p for p in problems), f"problems: {problems}")


def check_negative_unknown_top_level_key() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lane-bad.json"
        _write_json(path, {
            "lane": "bad",
            "repo": "light-repo",
            "roadmap": "my-roadmap",
            "blocks": [
                {"id": "BT.1.A", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
            ],
            "COMMENT": "free-text prose directive, exactly what D71 forbids",
        })
        problems, _ = check_lane_records.check(path, {})
        check("an unknown top-level key is rejected",
              any("unknown top-level key" in p for p in problems), f"problems: {problems}")


def check_negative_budget_disagreement() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = build_corpus(Path(td))
        path = tmp / "consumer-repo" / "planning" / "roadmaps" / "my-roadmap" / "lane-disagree.json"
        _write_json(path, {
            "lane": "disagree",
            "repo": "light-repo",       # actually light
            "roadmap": "my-roadmap",
            "blocks": [
                {"id": "BT.1.A", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
            ],
            "budget": {"heavy": True},  # authored heavy -- disagrees
        })
        repo_paths = check_lane_records.repo_paths_for(path)
        problems, _ = check_lane_records.check(path, repo_paths)
        check("a budget.heavy that disagrees with the concurrency script is rejected",
              any("disagrees with" in p for p in problems), f"problems: {problems}")


def check_nonexistent_repo_path_is_an_error_not_heavy_false() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = build_corpus(Path(td))
        path = tmp / "consumer-repo" / "planning" / "roadmaps" / "my-roadmap" / "lane-ghost.json"
        _write_json(path, {
            "lane": "ghost",
            "repo": "ghost-repo",       # registered in brain.toml, but the directory never exists
            "roadmap": "my-roadmap",
            "blocks": [
                {"id": "BT.1.A", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
            ],
            "budget": {"heavy": True},
        })
        repo_paths = check_lane_records.repo_paths_for(path)
        problems, _ = check_lane_records.check(path, repo_paths)
        named_error = [p for p in problems if "does not exist" in p and "ghost-repo" in p]
        check("a nonexistent --repo-path is reported as a named error",
              len(named_error) == 1, f"problems: {problems}")
        check("the nonexistent-path error never reads as a heavy:false disagreement",
              not any("disagrees with" in p for p in problems), f"problems: {problems}")


def check_cli_named_path_and_reason_on_malformed_record() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = build_corpus(Path(td))
        bad_path = tmp / "consumer-repo" / "planning" / "roadmaps" / "my-roadmap" / "lane-broken.json"
        _write_json(bad_path, {
            "lane": "broken",
            "repo": "light-repo",
            "roadmap": "my-roadmap",
            "blocks": [
                {"id": "not-a-valid-id", "origin_roadmap": "my-roadmap", "repo": "consumer-repo"},
            ],
        })
        planning_dir = tmp / "consumer-repo" / "planning"
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--planning", str(planning_dir), "--quiet"],
            capture_output=True, text=True,
        )
        check("a malformed record makes the CLI exit non-zero", proc.returncode != 0, proc.stdout)
        check("the CLI names the failing path", str(bad_path) in proc.stdout, proc.stdout)
        check("the CLI names a reason (block ID grammar)",
              "block ID grammar" in proc.stdout, proc.stdout)


def check_cli_clean_corpus_exits_zero() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = build_corpus(Path(td))
        planning_dir = tmp / "consumer-repo" / "planning"
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--planning", str(planning_dir), "--quiet"],
            capture_output=True, text=True,
        )
        check("a clean fixture corpus (3 well-formed records) exits 0",
              proc.returncode == 0, proc.stdout + proc.stderr)



# --- prefix/repo agreement (2026-09-01) ----------------------------------------------------
#
# The defect: `sequence.md` filed the unattended-migration-runner block as `EN.14.H` with repo
# `agentic-portfolio`, reasoning "filed under HQ because the files are HQ's". EN is engine-rs's
# prefix, so registering that Wave 0 row files the block into engine-rs's namespace from HQ's
# graph. check_block_naming.py reads the same [[repos]] prefixes but validates SPEC DIRECTORY
# NAMES, so it is out of scope by construction and nothing downstream caught it.

_PREFIXES = {"EN": "engine-rs", "HQ": "brain", "BT": "base-template"}


def _prefix_lane(tmp: Path, block_id: str, repo: str) -> Path:
    path = tmp / "planning" / "roadmaps" / "r" / "lane-x.json"
    _write_json(path, {
        "lane": "x",
        "roadmap": "r",
        "blocks": [{"id": block_id, "origin_roadmap": "r", "repo": repo}],
    })
    return path


def check_negative_prefix_repo_mismatch() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = _prefix_lane(Path(td), "EN.14.H", "brain")
        problems, _ = check_lane_records.check(str(path), {}, _PREFIXES)
        hits = [p for p in problems if "PREFIX/REPO MISMATCH" in p]
        check("a block ID under another repo's prefix is an error",
              len(hits) == 1, f"problems: {problems}")
        check("the mismatch names both the prefix's owner and the authored repo",
              hits and "engine-rs" in hits[0] and "brain" in hits[0],
              f"message: {hits}")


def check_positive_prefix_repo_agreement() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = _prefix_lane(Path(td), "EN.14.H", "engine-rs")
        problems, _ = check_lane_records.check(str(path), {}, _PREFIXES)
        check("a block ID whose prefix matches its repo is clean",
              not [p for p in problems if "PREFIX/REPO" in p], f"problems: {problems}")


def check_unregistered_prefix_is_not_a_mismatch() -> None:
    """A prefix brain.toml does not declare cannot be attributed to anyone -- silence, not a
    guess. The ID grammar check already covers a malformed prefix."""
    with tempfile.TemporaryDirectory() as td:
        path = _prefix_lane(Path(td), "ZZ.1.A", "engine-rs")
        problems, _ = check_lane_records.check(str(path), {}, _PREFIXES)
        check("an unregistered prefix raises no mismatch",
              not [p for p in problems if "PREFIX/REPO" in p], f"problems: {problems}")


def check_prefix_map_resolves_from_brain_toml() -> None:
    """Positive control for the resolution path itself: the same mismatch must be caught with
    NO explicit map passed, reading prefixes off a real brain.toml by walking up from the file.
    Without this, every case above could pass against a hand-fed dict while the production call
    path resolved {} and checked nothing."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _write(tmp / "brain.toml", '''
[[repos]]
slug = "engine-rs"
prefix = "EN"
repo_path = "engine-rs"

[[repos]]
slug = "brain"
prefix = "HQ"
repo_path = "."
''')
        check_lane_records._REPO_PREFIX_CACHE.clear()
        resolved = check_lane_records.repo_prefixes_for(tmp)
        check("prefixes resolve from a real brain.toml", resolved.get("EN") == "engine-rs",
              f"resolved: {resolved}")

        path = _prefix_lane(tmp, "EN.14.H", "brain")
        problems, _ = check_lane_records.check(str(path))
        check("the mismatch is caught with no explicit prefix map (production call path)",
              any("PREFIX/REPO MISMATCH" in p for p in problems), f"problems: {problems}")
        check_lane_records._REPO_PREFIX_CACHE.clear()


def check_no_brain_toml_disables_the_check() -> None:
    """A standalone repo scaffolded from this template has no brain, so the check must be silent
    rather than failing every block."""
    with tempfile.TemporaryDirectory() as td:
        check_lane_records._REPO_PREFIX_CACHE.clear()
        path = _prefix_lane(Path(td), "EN.14.H", "brain")
        problems, _ = check_lane_records.check(str(path), {}, {})
        check("no brain.toml means no prefix check, not a failure",
              not [p for p in problems if "PREFIX/REPO" in p], f"problems: {problems}")


def main() -> int:
    check_no_records_is_not_a_failure()
    check_dependency_free()
    check_positive_well_formed()
    check_positive_two_repos()
    check_positive_no_top_level_repo()
    check_positive_notes_field()
    check_positive_leading_worktree_isolation()
    check_positive_d81_preserved_isolation()
    check_positive_plain_no_worktree_isolation()
    check_positive_absent_isolation()
    check_negative_per_block_note()
    check_legacy_and_roadmaps_discovery()
    check_derived_artifacts_at_the_planning_root_are_not_lane_records()
    check_a_lane_record_at_the_planning_root_is_the_deliberate_blind_spot()
    check_negative_missing_origin_roadmap()
    check_negative_duplicate_block_id()
    check_negative_unknown_top_level_key()
    check_negative_budget_disagreement()
    check_nonexistent_repo_path_is_an_error_not_heavy_false()
    check_cli_named_path_and_reason_on_malformed_record()
    check_cli_clean_corpus_exits_zero()
    check_negative_prefix_repo_mismatch()
    check_positive_prefix_repo_agreement()
    check_unregistered_prefix_is_not_a_mismatch()
    check_prefix_map_resolves_from_brain_toml()
    check_no_brain_toml_disables_the_check()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOK -- check_lane_records.py holds against the fixture corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
