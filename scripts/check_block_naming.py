#!/usr/bin/env python3
"""The block-ID naming-convention guard -- the check that can fail.

WHY THIS EXISTS
----------------
`BT.ticket.block-id-naming-convention-guard` settles the naming convention for a block of work
(larger than a `/ticket` or `/chore`): `<REPO>.<phase>.<block>` -- a repo-unique two-or-three-
letter code taken from `brain.toml`'s `[[repos]] prefix` field, a phase number, and a block letter
or number (`BW.10.B`, `EN.8.A`, `OK.3.2`). Measured 2026-08-12, the fleet does not follow it: of
39 block-shaped spec directories, only 13 are canonical -- the other 26 are one of two error
shapes (`<phase>.<block>-<title>` or `<repo>-<phase><block>-<title>`), plus two unclassified.
This script is what turns that convention into something that can actually fail a build, going
forward, without failing every build today.

WHAT IT CHECKS
--------------
Every spec directory (one carrying a `tasks.json` or `tasks.md`) that is NOT `ticket-`/`chore-`/
`plan-`-prefixed must match `<REPO>.<phase>.<block>` EXACTLY -- the directory name equals the
block ID, no title suffix. `<REPO>` must be one of the prefixes declared in `brain.toml`'s
`[[repos]]` entries (never a hardcoded list), `<phase>` is one or more digits, `<block>` is one or
more letters/digits (`B`, `2`, `K2`, `B2` all valid). `ticket-`/`chore-`/`plan-` directories are
smaller units with their own already-working convention; this guard never touches them -- flagging
them would flag ~90 correct directories.

This guard makes NO assertion about file CONTENT -- only directory NAMES. Old-form strings like
`10.B-foo` legitimately appear in roadmap prose, closed specs' bodies, `log.md` history, and
`state.json` as historical IDs; a blanket content grep over a literal with legitimate other uses is
exactly how `BT.ticket.roadmaps-get-a-home-and-a-registry` task 3 shipped an unsatisfiable check.

TWO MODES
---------
`--self-test` -- synthetic fixtures under a temp dir, no dependency on the real corpus.
(default)     -- gates ONLY the repo this script is invoked from (resolved from the script's own
                  location, i.e. the repo `scripts/check_block_naming.py` was copied into --
                  override with `--root`). Blocks on ANY non-conforming block directory found
                  there, regardless of when it was created.
`--fleet`     -- sweeps the WHOLE corpus from the brain root and REPORTS every non-conforming
                  block directory across every repo. Always exits 0 unless `--strict` is also
                  passed.

WHY SCOPE, NOT DELTA (read this before "fixing" it to copy D64)
-----------------------------------------------------------------
The obvious move is to copy `BT.ticket.corpus-checks-delta-attribution`'s D64 baseline model from
`scripts/test_orchestration_run_contract.py` -- attribute violations by comparing the corpus now
against a resolved baseline commit, and block only on what's NEW. **That was tried here and it
failed, on 2026-08-12** (see the ticket's Amendment Log): a fleet-wide delta gate is racy against
concurrent lanes (six non-conforming directories appeared between a resolved baseline and the run,
created by other lanes still using an old convention -- each legitimately "new", so the gate
blocked this repo for work it did not do) and blind to gitignored trees (`git ls-tree` cannot see
`core/engine-rs/crates/engine-core/planning` at any baseline, so it is permanently misclassified as
new).

D64's by-delta-never-by-path rule exists to protect corpus-integrity classes with ACTION AT A
DISTANCE -- deleting a doc can surface a dangling-link error on a completely different file, so a
path-scoped gate would miss exactly the class it exists to catch. **A badly named directory has no
action at a distance: it can only ever be wrong about itself.** Scoping the gate to the repo being
gated is therefore exact and loses nothing -- and it sidesteps both failure modes above, because
"this repo's own directories, right now" needs no baseline and no cross-repo visibility at all.

PROVENANCE, NOT BASELINE
-------------------------
A non-conforming directory git cannot see (gitignored, or present on disk but never `git add`ed)
is reported as **unknown provenance** and never blocks or counts toward `--fleet --strict`'s exit
code -- the guard cannot respect a naming convention decision made about something it cannot prove
exists in the tracked corpus. This is a provenance check against the CURRENT tree only; there is no
baseline commit anywhere in this module.

DISCOVERY RULES (copied from `scripts/test_orchestration_run_contract.py`, the already-ported D64
sibling -- see that module's docstring for the fuller rationale; only the DISCOVERY plumbing is
shared, not the delta-attribution model above it)
-----------------------------------------------------------------------
- Sweep with BOTH `-L` (follow symlinks -- every repo's `planning/` is one) AND `-uu` (search
  hidden/gitignored paths -- every sub-repo under the brain root is gitignored from the brain's own
  perspective, so `-L` alone silently misses whole repos).
- Dedup by `os.path.realpath` -- the same physical file is reachable through more than one symlink
  chain (a repo's own `planning/` symlink AND, from the brain root, the `_planning/<repo>/` vault
  path it points at), so a raw sweep multi-counts.
- This script shells out to `rg` captured directly via `subprocess.run(..., capture_output=True)`,
  never piped through another process -- a piped command's `$?` is the pipe's exit status, not
  `rg`'s (CLAUDE.md trap 1).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

# Smaller units than a block -- their own already-working convention. This guard never touches
# them: flagging `ticket-foo` / `chore-foo` / `plan-foo` would flag ~90 correct directories.
_IGNORED_PREFIXES = ("ticket-", "chore-", "plan-")


def find_brain_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk upward from `start` (default: cwd) looking for a directory containing brain.toml."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "brain.toml").exists():
            return candidate
    return None


def load_repo_prefixes(root: Optional[Path]) -> list[str]:
    """Read every `[[repos]] prefix = "XX"` from `root/brain.toml`.

    Never a hardcoded list -- a new repo is picked up the moment it registers a `[[repos]]` entry,
    no edit to this script required. stdlib-only (`tomllib`, py3.11+).
    """
    if root is None:
        return []
    toml_path = root / "brain.toml"
    if not toml_path.exists():
        return []
    with toml_path.open("rb") as f:
        data = tomllib.load(f)
    prefixes: list[str] = []
    for repo in data.get("repos", []):
        prefix = repo.get("prefix")
        if prefix:
            prefixes.append(prefix)
    return prefixes


def block_id_pattern(prefixes: list[str]) -> re.Pattern:
    """`^(?:PREFIX1|PREFIX2|...)\\.\\d+\\.[A-Za-z0-9]+$` -- an exact, anchored match against the
    known prefixes (longest first, so no prefix can shadow a longer sibling). Matching against the
    literal known set -- rather than a generic "two-or-three uppercase letters" shape -- means an
    unregistered two-letter string never accidentally passes as canonical.
    """
    ordered = sorted(set(prefixes), key=len, reverse=True)
    alternation = "|".join(re.escape(p) for p in ordered)
    return re.compile(rf"^(?:{alternation})\.\d+\.[A-Za-z0-9]+$")


def is_ignored_dir(name: str) -> bool:
    """`ticket-`/`chore-`/`plan-` directories are not blocks; the convention does not apply."""
    return name.startswith(_IGNORED_PREFIXES)


def classify_dir(name: str, pattern: re.Pattern) -> bool:
    """True if `name` conforms to the canonical block-ID pattern."""
    return pattern.match(name) is not None


def _sweep_with_rg(root: Path) -> Optional[list[Path]]:
    """Try `rg -L -uu --files -g '**/tasks.json' -g '**/tasks.md'`; None if no `rg` on PATH."""
    rg_bin = shutil.which("rg")
    if rg_bin is None:
        return None
    result = subprocess.run(
        [rg_bin, "-L", "-uu", "--files", "-g", "**/tasks.json", "-g", "**/tasks.md"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    # rg exits 1 when it finds nothing, 0 when it finds matches, >1 on a real error.
    if result.returncode not in (0, 1):
        raise RuntimeError(f"rg discovery failed (exit {result.returncode}): {result.stderr}")
    return [root / line for line in result.stdout.splitlines() if line.strip()]


def _sweep_with_walk(root: Path) -> list[Path]:
    """Pure-Python fallback sweep, used when no `rg` binary is on PATH.

    `os.walk(..., followlinks=True)` is the `-L` equivalent. `os.walk` never consults
    `.gitignore` in the first place, so every gitignored sub-repo is visited regardless -- the
    `-uu` equivalent needs no extra flag here.
    """
    found: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=True):
        for name in filenames:
            if name in ("tasks.json", "tasks.md"):
                found.append(Path(dirpath) / name)
    return found


def discover_spec_dirs(root: Path) -> tuple[list[Path], int]:
    """Sweep `root` for spec directories (one carrying `tasks.json` or `tasks.md`), -L -uu,
    realpath-deduped. Returns (spec_dir_paths, distinct_file_count).
    """
    raw_paths = _sweep_with_rg(root)
    if raw_paths is None:
        raw_paths = _sweep_with_walk(root)

    distinct_files = sorted({p.resolve() for p in raw_paths})
    dirs = sorted({p.parent for p in distinct_files})
    return dirs, len(distinct_files)


def find_violations(dirs: list[Path], prefixes: list[str]) -> list[Path]:
    """Apply the naming rule across a set of spec directories; return the non-conforming ones.
    `ticket-`/`chore-`/`plan-` directories are skipped entirely -- the convention does not apply
    to them.
    """
    pattern = block_id_pattern(prefixes)
    return [
        d for d in dirs
        if not is_ignored_dir(d.name) and not classify_dir(d.name, pattern)
    ]


# ---------------------------------------------------------------------------
# Gitignore skip -- current tree only, no baseline, and NOT a tracked-vs-untracked test. Under a
# scope-based blocking rule (see WHY SCOPE, NOT DELTA above), whether a directory has been
# `git add`ed carries no information: a non-conforming directory in this repo's scope is wrong
# whether or not it has been committed yet. The only thing that legitimately exempts a directory
# is being permanently unclassifiable -- genuinely `.gitignore`d. Every other non-conforming
# directory blocks, regardless of git status. See the module docstring's "PROVENANCE, NOT
# BASELINE" section.
#
# The gitignore check resolves the repository that OWNS each path, not the invoking repo's root
# -- every repo's `planning/` is a symlink into a DIFFERENT git repo (HQ's vault), so a query
# rooted at the invoking repo reports `fatal: ... is outside repository` (or simply "not ignored")
# for content the vault genuinely tracks or ignores. That mismatch -- not tracked-vs-untracked --
# was the actual bug: a query against the wrong repo can never see the right answer.
# ---------------------------------------------------------------------------


def _run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run a git command captured directly (never piped) so `$?` reflects git's own exit code,
    not a pipe's (CLAUDE.md trap 1). Never raises -- git-not-on-PATH and any other OSError are
    folded into a non-zero return so callers can treat them the same as "git said no".
    """
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except OSError as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def owning_repo_root(path: Path) -> Optional[Path]:
    """Resolve the git repository that OWNS `path` -- `git -C path rev-parse --show-toplevel`,
    i.e. asked of the path itself, never of some other invocation root. `None` if `path` is not
    inside any git work tree at all.
    """
    rc, out, _ = _run_git(["rev-parse", "--show-toplevel"], path)
    if rc != 0 or not out:
        return None
    return Path(out)


def is_gitignored(spec_dir: Path) -> bool:
    """True only if `spec_dir` is genuinely ignored by git, per `git check-ignore` run against the
    repository that OWNS `spec_dir` (resolved per path -- never a fixed invocation root). A path
    with no owning git repo at all is NOT treated as ignored: there is no `.gitignore` rule to
    honor, so it falls through to blocking like any other non-conforming directory.
    """
    owning_root = owning_repo_root(spec_dir)
    if owning_root is None:
        return False
    rc_ignore, _, _ = _run_git(["check-ignore", "-q", str(spec_dir)], owning_root)
    return rc_ignore == 0


def partition_by_gitignore(violations: list[Path]) -> tuple[list[Path], list[Path]]:
    """Split `violations` into (blocking, gitignored). Gitignored paths are reported separately
    and never block; every other violation blocks, regardless of tracked/staged/untracked status.
    """
    blocking: list[Path] = []
    gitignored: list[Path] = []
    for d in violations:
        (gitignored if is_gitignored(d) else blocking).append(d)
    return blocking, gitignored


# ---------------------------------------------------------------------------
# The two run modes.
# ---------------------------------------------------------------------------


def repo_mode(repo_root: Path, brain_root: Optional[Path]) -> tuple[int, str]:
    """Default mode: gate ONLY `repo_root` (the repo this guard was invoked from). Blocks on ANY
    non-conforming block directory found there, regardless of git status (tracked, staged, or
    brand-new on disk) -- the only exemption is a genuinely gitignored path, checked against the
    repository that owns it.
    """
    buf = io.StringIO()

    def out(s: str = "") -> None:
        print(s, file=buf)

    prefixes = load_repo_prefixes(brain_root)
    dirs, file_count = discover_spec_dirs(repo_root)
    out(
        f"discovered {file_count} distinct tasks.json/tasks.md file(s) across {len(dirs)} spec "
        f"director(y/ies) under {repo_root}"
    )
    out(f"{len(prefixes)} repo prefix(es) loaded from brain.toml")

    violations = find_violations(dirs, prefixes)
    blocking, gitignored = partition_by_gitignore(violations)

    if blocking:
        out(f"\n{len(blocking)} non-conforming block director(y/ies) in this repo (blocking):")
        for d in blocking:
            out(f"  blocking (this repo): {d}: does not match <REPO>.<phase>.<block>")
    if gitignored:
        out(f"\n{len(gitignored)} director(y/ies) of unknown provenance (never blocking):")
        for d in gitignored:
            out(f"  unknown provenance (gitignored): {d}")
    if not blocking and not gitignored:
        out("\nall block directories in this repo conform to <REPO>.<phase>.<block>")

    if blocking:
        out(
            f"\nBLOCKED: {len(blocking)} non-conforming block director(y/ies) in this repo. "
            "Rename to <REPO>.<phase>.<block> (directory name equals the block ID exactly)."
        )
        return 1, buf.getvalue()

    out("\nno blocking violations in this repo")
    return 0, buf.getvalue()


def fleet_mode(brain_root: Path, strict: bool) -> tuple[int, str]:
    """`--fleet`: reports non-conforming block directories across the WHOLE corpus. Reporting
    only by default -- always exits 0 unless `strict` is also passed, because a fleet-wide gate is
    racy against concurrent lanes (see module docstring) and this is not the repo-scoped guard.
    """
    buf = io.StringIO()

    def out(s: str = "") -> None:
        print(s, file=buf)

    prefixes = load_repo_prefixes(brain_root)
    dirs, file_count = discover_spec_dirs(brain_root)
    out(
        f"discovered {file_count} distinct tasks.json/tasks.md file(s) across {len(dirs)} spec "
        f"director(y/ies) fleet-wide from {brain_root}"
    )
    out(f"{len(prefixes)} repo prefix(es) loaded from brain.toml")

    violations = find_violations(dirs, prefixes)
    reportable, gitignored = partition_by_gitignore(violations)

    if reportable:
        out(
            f"\n{len(reportable)} non-conforming block director(y/ies) fleet-wide "
            "(reported, --fleet):"
        )
        for d in reportable:
            out(f"  reported (--fleet): {d}: does not match <REPO>.<phase>.<block>")
    if gitignored:
        out(f"\n{len(gitignored)} director(y/ies) of unknown provenance (never blocking):")
        for d in gitignored:
            out(f"  unknown provenance (gitignored): {d}")
    if not reportable and not gitignored:
        out("\nall block directories fleet-wide conform to <REPO>.<phase>.<block>")

    if not strict:
        out(
            f"\n--fleet is reporting-only: exiting 0 regardless of the {len(reportable)} "
            "finding(s) above (pass --strict to gate on them)."
        )
        return 0, buf.getvalue()

    if reportable:
        out(f"\n--strict: BLOCKED on {len(reportable)} fleet-wide non-conforming director(y/ies).")
        return 1, buf.getvalue()
    out("\n--strict: no fleet-wide violations")
    return 0, buf.getvalue()


# ---------------------------------------------------------------------------
# --self-test: synthetic fixtures, no dependency on the real corpus.
# ---------------------------------------------------------------------------

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        FAILURES.append(name)


_FIXTURE_PREFIXES = ["BW", "EN", "OKF"]  # OKF: proves 3-letter prefixes work, not just 2


def _write_brain_toml(base: Path, prefixes: list[str] = _FIXTURE_PREFIXES) -> None:
    base.mkdir(parents=True, exist_ok=True)
    lines = []
    for p in prefixes:
        lines.append("[[repos]]")
        lines.append(f'slug = "{p.lower()}"')
        lines.append(f'prefix = "{p}"')
        lines.append("")
    (base / "brain.toml").write_text("\n".join(lines), encoding="utf-8")


def _write_spec_dir(base: Path, name: str, filename: str = "tasks.json", body: str = "{}") -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(body, encoding="utf-8")
    return d


def _git_ok(args: list[str], cwd: Path) -> None:
    """Like `_run_git`, but raises loudly on failure -- fixture setup, not the thing under test."""
    rc, _, err = _run_git(args, cwd)
    assert rc == 0, f"git {args} failed in fixture setup: {err}"


def _init_git_repo(base: Path) -> None:
    """A real (but throwaway) git repo -- provenance checks are exercised for real here, not
    mocked.
    """
    base.mkdir(parents=True, exist_ok=True)
    _git_ok(["init", "-q"], base)
    _git_ok(["config", "user.email", "test@example.com"], base)
    _git_ok(["config", "user.name", "Block Naming Fixture"], base)


def _commit_all(base: Path, message: str) -> None:
    _git_ok(["add", "-A"], base)
    _git_ok(["commit", "-q", "-m", message], base)


def _run_repo_mode(root: Path, brain_root: Optional[Path] = None) -> tuple[int, str]:
    return repo_mode(root, brain_root if brain_root is not None else root)


def _run_fleet_mode(root: Path, strict: bool = False) -> tuple[int, str]:
    return fleet_mode(root, strict)


def self_test() -> int:
    print("check_block_naming.py --self-test")

    # (a) Canonical passes: letter block, numeric block, and a three-letter prefix.
    prefixes = _FIXTURE_PREFIXES
    pattern = block_id_pattern(prefixes)
    check("(a) letter block BW.10.B is canonical", classify_dir("BW.10.B", pattern))
    check("(a) numeric block EN.3.2 is canonical", classify_dir("EN.3.2", pattern))
    check(
        "(a) three-letter prefix OKF.1.A is canonical",
        classify_dir("OKF.1.A", pattern),
    )
    check(
        "(a) mixed alnum block BW.8.K2 is canonical",
        classify_dir("BW.8.K2", pattern),
    )
    # Proven negative: same shape, but with a title suffix -- must NOT pass, since the
    # directory name must equal the block ID exactly.
    check(
        "(a) negative: a title suffix (EN.0.A-cargo-workspace) is rejected",
        not classify_dir("EN.0.A-cargo-workspace", pattern),
    )

    # (b) A non-conforming directory in this repo blocks -- regardless of when it was created.
    # No baseline is consulted anywhere in this module; a fresh `10.B-foo` dir created moments ago
    # blocks exactly like one that has existed for a year.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _init_git_repo(base)
        _write_brain_toml(base)
        _write_spec_dir(base, "BW.1.A")
        _commit_all(base, "clean baseline")
        # Created AFTER any notion of a baseline commit -- and never committed at all.
        _write_spec_dir(base, "10.B-brand-new")
        _git_ok(["add", "-A"], base)  # tracked (staged), so provenance is known
        rc, output = _run_repo_mode(base)
        check("(b) a brand-new non-conforming dir blocks (exit 1)", rc == 1)
        check("(b) it is labeled 'blocking (this repo)' in output", "blocking (this repo)" in output)

        # Proven negative: remove the offending directory -- must return to exit 0, proving the
        # block tracks the violation's presence, not some unrelated state.
        shutil.rmtree(base / "10.B-brand-new")
        rc2, _ = _run_repo_mode(base)
        check("(b) negative: removing the violation returns to exit 0", rc2 == 0)

    # (c) Repo scoping -- a non-conforming directory in ANOTHER repo never affects this repo's
    # verdict, proven in both directions. `repo_mode` only ever sweeps the root it is given, so
    # two sibling roots are naturally isolated from each other.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_brain_toml(root)  # shared brain.toml one level up, as in the real fleet

        repo_a = root / "repo-a"
        _init_git_repo(repo_a)
        _write_spec_dir(repo_a, "BW.1.A")  # repo A is clean
        _commit_all(repo_a, "clean")

        repo_b = root / "repo-b"
        _init_git_repo(repo_b)
        _write_spec_dir(repo_b, "10.B-legacy")  # repo B is non-conforming
        _commit_all(repo_b, "dirty")

        rc_a, _ = _run_repo_mode(repo_a, root)
        check("(c) repo A's verdict is unaffected by repo B's violation (exit 0)", rc_a == 0)

        rc_b, _ = _run_repo_mode(repo_b, root)
        check("(c) repo B still blocks on its own violation (exit 1)", rc_b == 1)

        # Other direction: repo A gets a violation, repo B is clean of its own -- each repo's
        # verdict tracks only itself.
        _write_spec_dir(repo_a, "hq-4a-oops")
        _git_ok(["add", "-A"], repo_a)
        rc_a2, _ = _run_repo_mode(repo_a, root)
        check("(c) negative: repo A now blocks on its OWN new violation", rc_a2 == 1)
        rc_b2, _ = _run_repo_mode(repo_b, root)
        check(
            "(c) repo B's verdict is still driven only by its own directories",
            rc_b2 == 1,  # repo B's own pre-existing violation is still there
        )

    # (d) ticket-/chore-/plan- directories are ignored entirely, even though they never match the
    # canonical shape.
    check("(d) ticket-foo is ignored", is_ignored_dir("ticket-foo"))
    check("(d) chore-foo is ignored", is_ignored_dir("chore-foo"))
    check("(d) plan-foo is ignored", is_ignored_dir("plan-foo"))
    # Proven negative: a directory that merely CONTAINS one of those words, but isn't prefixed
    # with it, is NOT ignored -- it still must conform.
    check(
        "(d) negative: a directory containing 'ticket' but not prefixed is not ignored",
        not is_ignored_dir("my-ticket-followup"),
    )
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _init_git_repo(base)
        _write_brain_toml(base)
        _write_spec_dir(base, "ticket-some-fix")
        _write_spec_dir(base, "chore-cleanup")
        _write_spec_dir(base, "plan-explore")
        _commit_all(base, "only ignored-shape dirs")
        rc, _ = _run_repo_mode(base)
        check("(d) a repo with only ticket-/chore-/plan- dirs never blocks", rc == 0)

    # (e) Prefixes come from brain.toml, not a hardcoded list -- a fixture declaring a NEW prefix
    # accepts directories using it without editing this script.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _write_brain_toml(base, ["ZQ"])
        loaded = load_repo_prefixes(base)
        check("(e) a novel prefix (ZQ) round-trips from brain.toml", loaded == ["ZQ"])
        pattern = block_id_pattern(loaded)
        check("(e) ZQ.1.A is canonical once declared in brain.toml", classify_dir("ZQ.1.A", pattern))
        # Proven negative: an UNREGISTERED prefix of the same shape is rejected.
        check(
            "(e) negative: an unregistered prefix (QQ.1.A) is rejected",
            not classify_dir("QQ.1.A", pattern),
        )

    # (f) No content assertion -- a spec directory with a canonical NAME whose tasks.md BODY
    # contains an old-style string (`10.B-foo`) still passes; this guard inspects names only.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        d = _write_spec_dir(
            base, "BW.10.B", "tasks.md",
            body="See legacy block 10.B-foo for context; also hq-4a-legacy is referenced here.",
        )
        violations = find_violations([d], _FIXTURE_PREFIXES)
        check("(f) canonical dir with old-style strings in its BODY still passes", violations == [])

    # (g) Unknown provenance -- a gitignored directory is reported in its own section and never
    # blocks, even though its name is non-conforming.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _init_git_repo(base)
        _write_brain_toml(base)
        _write_spec_dir(base, "BW.1.A")
        (base / ".gitignore").write_text("ignored-tree/\n", encoding="utf-8")
        _commit_all(base, "clean baseline with a gitignore rule")
        _write_spec_dir(base, "ignored-tree/10.B-hidden")
        rc, output = _run_repo_mode(base)
        check("(g) a gitignored non-conforming dir never blocks (exit 0)", rc == 0)
        check("(g) it is reported as unknown provenance", "unknown provenance" in output)

        # Proven negative: the SAME directory NAME, but tracked (not gitignored) -- must block,
        # proving this case discriminates provenance rather than always passing.
        base2 = Path(td) / "negative"
        _init_git_repo(base2)
        _write_brain_toml(base2)
        _write_spec_dir(base2, "BW.1.A")
        _commit_all(base2, "clean baseline")
        _write_spec_dir(base2, "10.B-hidden")
        _git_ok(["add", "-A"], base2)
        rc2, out2 = _run_repo_mode(base2)
        check("(g) negative: the same shape, tracked, DOES block", rc2 == 1)
        check("(g) negative: it is reported as blocking, not unknown provenance", "blocking (this repo)" in out2)

        # Untracked (present on disk, never `git add`ed, and not gitignored either) now BLOCKS --
        # tracked-vs-untracked carries no information under the scope-based blocking rule; only a
        # genuine gitignore rule exempts a directory.
        base3 = Path(td) / "untracked"
        _init_git_repo(base3)
        _write_brain_toml(base3)
        _write_spec_dir(base3, "BW.1.A")
        _commit_all(base3, "clean baseline")
        _write_spec_dir(base3, "10.B-untracked")  # deliberately never `git add`ed
        rc3, out3 = _run_repo_mode(base3)
        check("(g) an untracked (but not gitignored) non-conforming dir now blocks (exit 1)", rc3 == 1)
        check(
            "(g) it is reported as blocking, not unknown provenance",
            "blocking (this repo)" in out3 and "unknown provenance" not in out3,
        )

    # (h) --fleet reports fleet-wide and exits 0 unless --strict is passed; End-to-end discovery
    # also proves the -L -uu realpath-deduped sweep finds spec dirs reachable via a symlink
    # (mirrors every repo's `planning/` being a symlink into the vault).
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _init_git_repo(base)
        _write_brain_toml(base)
        real_target = base / "_vault" / "BW.2.A"
        real_target.mkdir(parents=True)
        (real_target / "tasks.json").write_text("{}", encoding="utf-8")
        symlinked_planning = base / "planning"
        symlinked_planning.mkdir()
        os.symlink(real_target, symlinked_planning / "BW.2.A")
        _commit_all(base, "clean, symlinked layout")
        dirs, file_count = discover_spec_dirs(base)
        check("(h) symlinked spec dir is discovered", file_count == 1)
        check("(h) discovered dir realpath-resolves to the vault target", dirs == [real_target.resolve()])

        _write_spec_dir(base, "10.B-fleet-violation")
        _git_ok(["add", "-A"], base)
        rc_report, out_report = _run_fleet_mode(base, strict=False)
        check("(h) --fleet without --strict exits 0 despite a violation", rc_report == 0)
        check("(h) --fleet reports the violation", "reported (--fleet)" in out_report)
        rc_strict, _ = _run_fleet_mode(base, strict=True)
        check("(h) --fleet --strict blocks on the same violation", rc_strict == 1)

        # Proven negative: --fleet --strict with no violations exits 0.
        shutil.rmtree(base / "10.B-fleet-violation")
        rc_strict_clean, _ = _run_fleet_mode(base, strict=True)
        check("(h) negative: --fleet --strict with no violations exits 0", rc_strict_clean == 0)

    # (i) Live snapshot, dated -- re-measure against the REAL fleet at implementation time and
    # pin the RELATION (canonical + non-conforming accounts for every block-shaped dir), not a
    # hard-coded count -- a hard-coded count breaks the moment any repo adds a block. The
    # corresponding command is printed alongside the count so a future reader can re-measure by
    # hand.
    # Measured 2026-08-12: `python3 scripts/check_block_naming.py --fleet` against the real fleet
    # found 39 block-shaped directories, 13 canonical, 26 non-conforming (21
    # `<phase>.<block>-<title>`, 5 `<repo>-<phase><block>-<title>`), plus 2 unclassified.
    #
    # NOTE: `self_test()`'s own contract (see the module's TWO MODES section) is synthetic
    # fixtures with NO dependency on the real corpus -- the real corpus is written by every lane
    # in the fleet concurrently, so it is not a hermetic input. This case therefore hard-asserts
    # only the RELATION (a structural invariant, true by construction) and PRINTS -- rather than
    # hard-asserts -- the live repo-scoped result for base-template, so a concurrent lane's
    # unrelated commit elsewhere in the fleet can never flip this self-test red. No acceptance
    # criterion requires the live fleet (`--fleet`) to exit 0 -- other lanes add non-conforming
    # directories continuously, so that is unsatisfiable by construction; only THIS repo's
    # (base-template's) plain invocation is asserted, separately, by the harness's own
    # validation command.
    real_brain_root = find_brain_root() or find_brain_root(REPO_ROOT)
    if real_brain_root is None:
        check("(i) live snapshot: brain root resolves for re-measurement", False)
    else:
        prefixes = load_repo_prefixes(real_brain_root)
        dirs, _file_count = discover_spec_dirs(real_brain_root)
        block_shaped = [d for d in dirs if not is_ignored_dir(d.name)]
        pattern = block_id_pattern(prefixes)
        canonical = [d for d in block_shaped if classify_dir(d.name, pattern)]
        non_conforming = [d for d in block_shaped if not classify_dir(d.name, pattern)]
        print(
            "  (i) live snapshot (measuring command: "
            "`python3 scripts/check_block_naming.py --fleet`): "
            f"{len(block_shaped)} block-shaped director(y/ies), {len(canonical)} canonical, "
            f"{len(non_conforming)} non-conforming"
        )
        check(
            "(i) live snapshot: canonical + non-conforming accounts for every block-shaped dir "
            "(the relation, not a hard-coded count)",
            len(canonical) + len(non_conforming) == len(block_shaped),
        )
        rc, _out = repo_mode(REPO_ROOT, real_brain_root)
        print(
            "  (i) live snapshot: `python3 scripts/check_block_naming.py` "
            f"(repo-scoped, base-template) currently exits {rc}"
        )

    # (j) TASK 1 of `BT.ticket.block-naming-guard-provenance-fix` -- the discriminating cases that
    # expose the provenance bug: every repo's `planning/` is a symlink into HQ's vault, a
    # DIFFERENT git repo, so a provenance query rooted at the invoking repo cannot see what the
    # vault actually tracks. These pin the CORRECT (post-fix) behaviour and are expected to FAIL
    # against the current (pre-fix) implementation -- see the ticket's Amendment Log for the
    # captured failure output.

    # Case A: a non-conforming directory in the invoking repo blocks -- no staging, no
    # committing, no provenance consulted at all. Currently, an untracked-but-not-gitignored
    # directory is classified "unknown provenance" and never blocks -- that is the bug.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _init_git_repo(base)
        _write_brain_toml(base)
        _write_spec_dir(base, "BW.1.A")
        _commit_all(base, "clean baseline")
        # Deliberately NOT `git add`ed -- brand-new, on disk only.
        _write_spec_dir(base, "10.B-untracked-should-block")
        rc, output = _run_repo_mode(base)
        check(
            "(j) Case A: an untracked non-conforming dir in the invoking repo still blocks "
            "(exit 1), with no staging/committing/provenance involved",
            rc == 1,
        )
        check(
            "(j) Case A: it is labeled 'blocking (this repo)', not unknown provenance",
            "blocking (this repo)" in output and "unknown provenance" not in output,
        )

    # Case B: a directory tracked in a DIFFERENT git repo than the invocation root (the real vault
    # topology) must not be misreported as unknown provenance. Currently, provenance is always
    # queried against the invocation root's git, so a directory that is genuinely tracked -- just
    # in another repo -- is indistinguishable from one that was never committed anywhere.
    with tempfile.TemporaryDirectory() as td:
        vault = Path(td) / "vault"
        _init_git_repo(vault)
        _write_spec_dir(vault, "10.B-vault-legacy")
        _commit_all(vault, "tracked in the vault repo")

        outer = Path(td) / "outer-repo"
        _init_git_repo(outer)
        _write_brain_toml(outer)
        _write_spec_dir(outer, "BW.1.A")
        _commit_all(outer, "clean baseline")
        # `outer`'s own index has no knowledge of this symlink -- exactly the real topology,
        # where `planning/` is a symlink the outer repo does not (and cannot) track through to
        # the vault repo's own tracked content.
        os.symlink(vault / "10.B-vault-legacy", outer / "10.B-vault-legacy")

        rc, output = _run_repo_mode(outer)
        check(
            "(j) Case B: a directory tracked in a DIFFERENT (vault) repo is not misreported as "
            "unknown provenance",
            "unknown provenance" not in output,
        )
        check(
            "(j) Case B: it is reported as blocking, since its name doesn't conform",
            "blocking (this repo)" in output,
        )

    # Case C: a genuinely gitignored directory never blocks, verified with a REAL `git
    # check-ignore` call against the repo that owns it -- not inferred from a failed `ls-files`.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _init_git_repo(base)
        _write_brain_toml(base)
        _write_spec_dir(base, "BW.1.A")
        (base / ".gitignore").write_text("ignored-tree/\n", encoding="utf-8")
        _commit_all(base, "clean baseline with a gitignore rule")
        ignored_dir = _write_spec_dir(base, "ignored-tree/10.B-really-ignored")
        rc_ignore, _out_ignore, _err_ignore = _run_git(
            ["check-ignore", "-q", str(ignored_dir)], base
        )
        check(
            "(j) Case C: git check-ignore itself confirms the directory is ignored",
            rc_ignore == 0,
        )
        rc, output = _run_repo_mode(base)
        check(
            "(j) Case C: a genuinely gitignored non-conforming dir never blocks (exit 0)",
            rc == 0,
        )
        check("(j) Case C: it is reported as unknown provenance", "unknown provenance" in output)

    if FAILURES:
        print(f"\n{len(FAILURES)} self-test case(s) failed: {FAILURES}")
        return 1
    print("\nall self-test cases passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run synthetic fixture cases only")
    parser.add_argument(
        "--fleet", action="store_true",
        help="report non-conforming block directories fleet-wide (reporting only unless --strict)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="with --fleet, exit non-zero if any fleet-wide violation is found",
    )
    parser.add_argument(
        "--root", type=Path, default=None,
        help=(
            "override the root to gate/sweep (default: this script's own repo for the default "
            "mode, the resolved brain root for --fleet)"
        ),
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if args.fleet:
        brain_root = args.root or find_brain_root() or find_brain_root(REPO_ROOT)
        if brain_root is None:
            print(
                "could not resolve brain root (no brain.toml found walking up from cwd or "
                "REPO_ROOT); pass --root explicitly",
                file=sys.stderr,
            )
            return 2
        rc, output = fleet_mode(brain_root, args.strict)
        print(output, end="")
        return rc

    repo_root = args.root or REPO_ROOT
    brain_root = find_brain_root(repo_root) or find_brain_root()
    rc, output = repo_mode(repo_root, brain_root)
    print(output, end="")
    return rc


if __name__ == "__main__":
    sys.exit(main())
