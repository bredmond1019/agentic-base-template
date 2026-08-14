#!/usr/bin/env python3
"""Fleet audit: every `harness.json`'s `$schema` must resolve from BOTH faces.

WHY THIS EXISTS
----------------
Every vaulted repo's `planning/harness.json` declares
`"$schema": "../.claude/workflows/harness.schema.json"`. That string is a single
`../`-relative reference, but it is read from two different physical parents depending on
which face the reader walks:

- The LEXICAL face: `<repo>/planning/harness.json`, reached through the repo's own
  `planning` symlink into the brain vault. A pure *textual* normaliser (`os.path.normpath`,
  no filesystem calls) collapsing `<repo>/planning/..` lands on `<repo>/.claude/...` -- and
  every synced repo carries its own `.claude/workflows/harness.schema.json` copy there, so
  this reading resolves.
- The PHYSICAL face: the file's real, `realpath`-canonicalized location,
  `core/_planning/<repo>/harness.json` (or the sibling vault roots). Its `../` is
  `core/_planning/`, which has no `.claude` directory at all. This reading dangles.

Critically, **no real filesystem read ever produces the lexical answer** -- `open()`/`stat()`
resolve `..` via the kernel's view of the actual directory, which is the vault, regardless of
which path string you started from (verified directly: `cd core/mev/planning && cat
../.claude/workflows/harness.schema.json` fails even though the shell's own `$PWD` still
prints the symlinked string). Only a tool that manipulates the path as pure text before ever
touching the filesystem -- exactly what most JSON-schema `$ref` resolvers and editor language
servers do -- sees the lexical answer. So "resolves lexically" here means "the textually
normalised target path exists on disk", not "a symlink-aware `open()` succeeds partway
through". Tooling that instead canonicalizes the whole ref (realpath-style) gets the physical
answer and finds nothing, then silently falls back to NO schema validation. That silent
fallback is the actual defect this ticket fixes; this script is the fleet-wide proof of it.

RED-FIRST
----------
This script is written and run BEFORE any path is changed (task 1 of
`ticket-harness-schema-realpath`). At the time of writing it reports the fleet broken -- see
the measured baseline recorded in `planning/ticket-harness-schema-realpath/tasks.md`'s
Amendment Log. It is intentionally NOT registered in `planning/harness.json` yet (that is
task 5, once the fix has actually landed) -- a red gate would block every unrelated task in
this same spec from committing.

THE SCAFFOLD TEMPLATE IS NOT A LIVE CONFIG
-------------------------------------------
`base-template/scaffold/planning/harness.json` is discovered by the walk like every other
file, but it is a TEMPLATE, not a live project config -- its `"$schema"` string is correct at
its DESTINATION (in a generated project, `.claude/` is a sibling of `planning/`), and it can
never resolve inside `base-template/scaffold/`, because `.claude/` ships from the harness half
and `scaffold/.claude/` must never exist (would violate the two-halves rule in CLAUDE.md).
Asserting resolution on it here would be asserting a false thing about a template. It is
therefore EXCLUDED from the pass/fail resolution assertion and reported on its own line
instead -- never silently dropped from the discovery count, since a file that vanishes from a
report is indistinguishable from a file that was never discovered. The gate is **18 of 18
live configs**, not 19 of 19.

DISCOVERY
---------
Walks the brain root (found by walking up from this script's own location looking for
`brain.toml`, the same technique `sync_downstream_harness.py` uses for `find_brain_root`)
with `os.walk(..., followlinks=True)`. Stdlib `os.walk` never consults `.gitignore`, so it
does not have `rg`'s "silently skips gitignored trees" failure mode (`base-template/` itself
is gitignored from the brain repo's perspective, which is exactly how a naive `rg` sweep
without `--no-ignore` misses `base-template/scaffold/planning/harness.json` -- the single most
important file in this ticket, since it is what a newly scaffolded repo inherits). A small,
named set of directory names is pruned during the walk (`.git`, dependency/build caches, and
`trees/` -- SDLC worktrees, which would otherwise multiply every entry underneath
`core/engine-rs/trees/...` and this very repo's own `trees/<slug>/` by however many worktrees
happen to be checked out at run time, which is not part of the fleet this audit is about).

Because the walk follows symlinks, most vaulted repos are discovered via TWO distinct path
strings that name the same physical file: the vault-direct path (`core/_planning/mev/
harness.json`, no symlink component) and the repo's own symlinked path (`core/mev/planning/
harness.json`). Both are grouped by `os.path.realpath(os.path.dirname(path))` into one
canonical entry per physical file; the group's `planning`-named path string (if any) is kept
as the LEXICAL representative, since that is the one that actually walks through a `planning`
symlink and is what "the lexical face" means in this ticket. This keeps the report at one row
per repo (matching how the ticket enumerates the broken set) instead of one row per raw
filesystem path.

Run: python3 scripts/test_harness_schema_realpath.py
"""

from __future__ import annotations

import json
import os
import sys

EXPECTED_SCHEMA_URI = "http://json-schema.org/draft-07/schema#"
EXPECTED_SCHEMA_ID = "https://agentic-portfolio/base-template/harness.schema.json"

# Directory names pruned during the walk. Not the fleet: SDLC worktrees (`trees/`) and
# ordinary dependency/build/VCS caches that would otherwise slow the walk or multiply entries.
_EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "target",
    ".next",
    "coverage",
    ".turbo",
    ".pytest_cache",
    ".mypy_cache",
    "trees",
}

# The measured minimum fleet size (2026-08-09): 16 broken vaulted repos + the one passing
# brain-root file + base-template's own scaffold stub = 18. A discovery walk that regresses to
# being symlink-blind (or silently skips a gitignored tree) finds far fewer than this and would
# report a falsely "clean" fleet -- pinning a floor here is what catches that regression. This
# is a floor on DISCOVERY, not on the resolution assertion -- see LIVE_EXPECTED_FILES below for
# the count the pass/fail gate actually applies to.
MIN_EXPECTED_FILES = 18

# Of the discovered files, exactly one is the scaffold template
# (`base-template/scaffold/planning/harness.json`) -- excluded from the resolution assertion
# per the module docstring. The remaining files are live project configs, and the fleet gate is
# "18 of 18 live configs resolve", not "19 of 19 discovered files resolve".
#
# This is a closed-corpus census, the same failure mode test_d16_tasks_json_fallback.py's
# MeasuredBaseline class already documents: it goes stale the moment a legitimate new project is
# scaffolded (bumped 17 -> 18 on 2026-08-14 when client/jardins-fitness landed), and it will need
# bumping again the next time the fleet grows. That is expected maintenance, not a sign the check
# is wrong -- do not raise it speculatively ahead of a real new repo, and do not delete the exact
# count in favor of a floor just to stop having to bump it; the whole point is catching a file
# that silently STOPPED resolving, which a floor cannot detect.
LIVE_EXPECTED_FILES = 18

# Suffix identifying the scaffold template's lexical path, regardless of which brain-root
# absolute prefix it is discovered under.
_SCAFFOLD_SUFFIX = os.path.join("base-template", "scaffold", "planning", "harness.json")


def is_scaffold_template(lexical_path: str) -> bool:
    """True if `lexical_path` is the scaffold template, not a live project config."""
    return os.path.normpath(lexical_path).endswith(_SCAFFOLD_SUFFIX)


def find_brain_root(start: str) -> str:
    """Walk up from `start` looking for brain.toml, the brain repo's root marker."""
    current = os.path.realpath(start)
    while True:
        if os.path.isfile(os.path.join(current, "brain.toml")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise SystemExit(
                "ERROR: no brain.toml found walking up from " + start
            )
        current = parent


def discover_harness_json(brain_root: str) -> list[str]:
    """Every `harness.json` reachable from `brain_root`, following symlinks.

    Returns raw (non-realpath'd) path strings, exactly as encountered by the walk -- callers
    that need the canonicalized physical location apply `os.path.realpath` themselves.
    """
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(brain_root, followlinks=True):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS]
        if "harness.json" in filenames:
            found.append(os.path.join(dirpath, "harness.json"))
    return found


def group_by_physical_location(raw_paths: list[str]) -> dict[str, str]:
    """Collapse raw discovered paths into one canonical entry per physical file.

    Keyed by `os.path.realpath(os.path.dirname(path))` (the PHYSICAL parent directory).
    Value is the group's chosen LEXICAL representative: the raw path string whose immediate
    parent directory is literally named `planning` (i.e. one that actually walks through a
    `planning` symlink, or -- for the brain root's own file -- a real `planning` directory).
    Falls back to an arbitrary member of the group if none qualifies (still a valid, just less
    illustrative, physical-only entry).
    """
    groups: dict[str, list[str]] = {}
    for raw in raw_paths:
        physical_dir = os.path.realpath(os.path.dirname(raw))
        groups.setdefault(physical_dir, []).append(raw)

    canonical: dict[str, str] = {}
    for physical_dir, raws in groups.items():
        preferred = next(
            (r for r in raws if os.path.basename(os.path.dirname(r)) == "planning"),
            raws[0],
        )
        canonical[physical_dir] = preferred
    return canonical


def read_schema_value(harness_json_path: str) -> str | None:
    try:
        with open(harness_json_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERROR: could not parse {harness_json_path}: {exc}") from exc
    value = data.get("$schema")
    if not isinstance(value, str):
        return None
    return value


class Result:
    __slots__ = (
        "physical_dir",
        "lexical_path",
        "schema_value",
        "physical_target",
        "physical_ok",
        "lexical_target",
        "lexical_ok",
    )

    def __init__(self, physical_dir: str, lexical_path: str, schema_value: str) -> None:
        self.physical_dir = physical_dir
        self.lexical_path = lexical_path
        self.schema_value = schema_value

        lexical_dir = os.path.dirname(lexical_path)

        if os.path.isabs(schema_value):
            self.physical_target = os.path.normpath(schema_value)
            self.lexical_target = os.path.normpath(schema_value)
        else:
            # PHYSICAL face: joined against the realpath-canonicalized parent directory.
            self.physical_target = os.path.normpath(os.path.join(physical_dir, schema_value))
            # LEXICAL face: joined against the RAW (non-realpath) parent directory string, so
            # this is a pure textual normalisation -- exactly what a naive `$ref` resolver
            # does, and never what a real `open()`/`stat()` call does.
            self.lexical_target = os.path.normpath(os.path.join(lexical_dir, schema_value))

        self.physical_ok = os.path.exists(self.physical_target)
        self.lexical_ok = os.path.exists(self.lexical_target)


def evaluate(canonical: dict[str, str]) -> list[Result]:
    results = []
    for physical_dir, lexical_path in canonical.items():
        schema_value = read_schema_value(lexical_path)
        if schema_value is None:
            raise SystemExit(f"ERROR: {lexical_path} has no string \"$schema\" key")
        results.append(Result(physical_dir, lexical_path, schema_value))
    return results


def validate_schema_content(target_path: str) -> str | None:
    """Return an error string if `target_path` is not a well-formed copy of the canonical
    harness schema, else None. Only called on targets that already exist."""
    try:
        with open(target_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return f"{target_path}: not valid JSON ({exc})"
    if data.get("$schema") != EXPECTED_SCHEMA_URI:
        return f"{target_path}: \"$schema\" is {data.get('$schema')!r}, expected {EXPECTED_SCHEMA_URI!r}"
    if data.get("$id") != EXPECTED_SCHEMA_ID:
        return f"{target_path}: \"$id\" is {data.get('$id')!r}, expected {EXPECTED_SCHEMA_ID!r}"
    return None


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    brain_root = find_brain_root(here)

    raw_paths = discover_harness_json(brain_root)
    canonical = group_by_physical_location(raw_paths)

    failures: list[str] = []

    if len(canonical) < MIN_EXPECTED_FILES:
        failures.append(
            f"SYMLINK-BLINDNESS GUARD: discovered only {len(canonical)} distinct harness.json "
            f"files (raw paths: {len(raw_paths)}), expected at least {MIN_EXPECTED_FILES}. A "
            "discovery walk that regresses to being symlink-blind (or skips a gitignored tree "
            "such as base-template/) silently reports a falsely clean fleet -- this is that "
            "regression."
        )

    results = evaluate(canonical)
    results.sort(key=lambda r: r.physical_dir)

    scaffold_results = [r for r in results if is_scaffold_template(r.lexical_path)]
    live_results = [r for r in results if not is_scaffold_template(r.lexical_path)]

    if len(scaffold_results) != 1:
        failures.append(
            f"SCAFFOLD DETECTION: expected exactly 1 discovered file matching the scaffold "
            f"template suffix {_SCAFFOLD_SUFFIX!r}, found {len(scaffold_results)}. Either the "
            "scaffold stub moved/vanished or a live repo's path now collides with the suffix -- "
            "both need a human look, not a silent pass."
        )

    if len(live_results) != LIVE_EXPECTED_FILES:
        failures.append(
            f"LIVE CONFIG COUNT: expected exactly {LIVE_EXPECTED_FILES} live harness.json "
            f"configs (excluding the scaffold template), found {len(live_results)}."
        )

    broken_physical: list[Result] = []
    broken_lexical: list[Result] = []
    content_errors: list[str] = []

    for r in live_results:
        if not r.physical_ok:
            broken_physical.append(r)
        else:
            err = validate_schema_content(r.physical_target)
            if err:
                content_errors.append(f"[physical] {err}")
        if not r.lexical_ok:
            broken_lexical.append(r)
        else:
            err = validate_schema_content(r.lexical_target)
            if err:
                content_errors.append(f"[lexical] {err}")

    print(f"Discovered {len(canonical)} distinct harness.json files "
          f"({len(raw_paths)} raw paths before dedup) under {brain_root}: "
          f"{len(live_results)} live config(s) + {len(scaffold_results)} scaffold template\n")

    for r in scaffold_results:
        print(
            f"SCAFFOLD TEMPLATE (excluded from resolution assert -- correct at its destination, "
            f"never resolvable inside base-template/scaffold/): {r.lexical_path}"
        )
    print()

    print(f"PHYSICAL face (realpath-canonicalized): {len(live_results) - len(broken_physical)}/"
          f"{len(live_results)} live configs resolve")
    for r in broken_physical:
        print(f"  BROKEN (physical): {r.physical_dir}/harness.json -> {r.physical_target}")

    print(f"\nLEXICAL face (planning/ symlink face, textual normalisation): "
          f"{len(live_results) - len(broken_lexical)}/{len(live_results)} live configs resolve")
    for r in broken_lexical:
        print(f"  BROKEN (lexical):  {r.lexical_path} -> {r.lexical_target}")

    if content_errors:
        print("\nSchema content mismatches on resolved targets:")
        for err in content_errors:
            print(f"  {err}")

    if failures:
        print()
        for f in failures:
            print(f"FAILURE: {f}")

    if broken_physical or broken_lexical or failures or content_errors:
        print(
            f"\nFAIL: {len(broken_physical)} broken on the physical face, "
            f"{len(broken_lexical)} broken on the lexical face, "
            f"{len(content_errors)} content mismatch(es)."
        )
        return 1

    print(f"\nPASS: all {len(live_results)} live harness.json files resolve on both faces "
          f"(1 scaffold template reported separately, asserted at its destination instead).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
