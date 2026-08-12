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
`--self-test`  -- synthetic fixtures under a temp dir, no dependency on the real corpus.
(default)      -- sweeps the real corpus from BRAIN_ROOT (walking up from cwd looking for
                  `brain.toml`, or `--root` to force it) and reports every non-conforming block
                  directory, exiting non-zero only for the ones new since the resolved baseline.

DISCOVERY RULES (copied from `scripts/test_orchestration_run_contract.py`, the already-ported D64
sibling -- see that module's docstring for the fuller rationale)
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

DELTA ATTRIBUTION (D64 / `BT.ticket.corpus-checks-delta-attribution`)
-----------------------------------------------------------------------
Corpus mode still discovers the WHOLE corpus -- that breadth is the point. What changed is what
the EXIT CODE reflects. The corpus is written by every lane in the fleet concurrently, so gating
on the raw non-conforming count makes base-template's pipeline depend on every other repo's
migration status (and there are 26 pre-existing non-conforming directories today). Compute the
violation set twice -- once against the corpus as it is now, once against the corpus as of a
resolved baseline commit -- and block only on violations NEW relative to that baseline. A
violation present in both sets is pre-existing: reported, not blocking.

Attribution is by DELTA, never by PATH: the two violation sets are compared as whole strings
(which already embed the offending directory's path), never filtered down to "directories this
tree touched" -- a rename/deletion can surface a violation on a directory the change never opened,
and a path-scoped filter would miss exactly that class.

Baseline resolution (the brain repo IS the corpus's git repo -- every `planning/` dir in the
fleet, including every `core/<repo>/planning`, is tracked by the one HQ git repo per CLAUDE.md
standing rule 10, so one `git` invocation set against BRAIN_ROOT covers the whole corpus):
  1. merge-base(HEAD, upstream-tracking-branch), if HEAD has an upstream (`@{u}`) configured.
  2. Else, HEAD itself -- "the last commit reachable from it".
  3. Baseline UNRESOLVABLE (not a git repo, or HEAD itself doesn't resolve -- a truly fresh
     clone/init with zero commits): FAIL CLOSED. Every violation found is treated as NEW. This is
     printed loudly, never silent -- the alternative (fail OPEN) turns the gate into a silent
     no-op the moment a rare edge case is hit.
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


def load_repo_prefixes(root: Path) -> list[str]:
    """Read every `[[repos]] prefix = "XX"` from `root/brain.toml`.

    Never a hardcoded list -- a new repo is picked up the moment it registers a `[[repos]]` entry,
    no edit to this script required. stdlib-only (`tomllib`, py3.11+).
    """
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


def check_dirs(dirs: list[Path], prefixes: list[str]) -> list[str]:
    """Apply the naming rule across a set of spec directories; return violation strings (empty =
    all conform). `ticket-`/`chore-`/`plan-` directories are skipped entirely.
    """
    pattern = block_id_pattern(prefixes)
    violations: list[str] = []
    for d in dirs:
        name = d.name
        if is_ignored_dir(name):
            continue
        if classify_dir(name, pattern):
            continue
        violations.append(
            f"{d}: directory name {name!r} does not match <REPO>.<phase>.<block>"
        )
    return violations


# ---------------------------------------------------------------------------
# Delta attribution -- baseline resolution copied from
# scripts/test_orchestration_run_contract.py (the already-ported D64 model).
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


def resolve_baseline_commit(root: Path) -> tuple[Optional[str], str]:
    """Resolve the baseline commit for delta attribution (see module docstring). Returns
    (commit_sha, description) on success, or (None, reason) when unresolvable -- callers must
    treat None as "fail closed", not "no baseline == nothing new".
    """
    rc, _, _ = _run_git(["rev-parse", "--is-inside-work-tree"], root)
    if rc != 0:
        return None, f"{root} is not inside a git working tree"

    rc, head, _ = _run_git(["rev-parse", "HEAD"], root)
    if rc != 0 or not head:
        return None, "HEAD does not resolve (no commits reachable -- a truly fresh repo)"

    rc, upstream, _ = _run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], root
    )
    if rc == 0 and upstream:
        rc2, merge_base, _ = _run_git(["merge-base", "HEAD", upstream], root)
        if rc2 == 0 and merge_base:
            return merge_base, f"merge-base(HEAD, {upstream})"

    # No upstream tracking branch configured -- fall back to "the last commit reachable from
    # HEAD", i.e. HEAD itself. Anything not yet committed in the brain repo is this tree's delta.
    return head, "HEAD (no upstream tracking branch configured)"


def read_baseline_dirs(root: Path, baseline_sha: str) -> list[Path]:
    """Reconstruct the in-scope spec directories as they existed at `baseline_sha`, via
    `git ls-tree` -- never via `git checkout`, so this never mutates the caller's working tree or
    index.

    `git ls-tree -r` walks the whole tree at that commit (this repo's git root already covers the
    whole corpus per CLAUDE.md standing rule 10), so this needs no symlink-following of its own the
    way `discover_spec_dirs`'s live filesystem sweep does.
    """
    rc, out, err = _run_git(["ls-tree", "-r", "--name-only", baseline_sha], root)
    if rc != 0:
        raise RuntimeError(f"git ls-tree failed for baseline {baseline_sha}: {err}")

    dirs: set[Path] = set()
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        if os.path.basename(rel) not in ("tasks.json", "tasks.md"):
            continue
        # Resolved (realpath) to match `discover_spec_dirs`'s own realpath-deduped paths --
        # otherwise a `root` reached through a symlink makes the same logical directory compare
        # as two different strings between the current sweep and the baseline reconstruction, and
        # every baseline entry looks spuriously "new".
        dirs.add((root / os.path.dirname(rel)).resolve())
    return sorted(dirs)


def classify_violations(current: list[str], baseline: list[str]) -> tuple[list[str], list[str]]:
    """Split `current` violations into (new, pre_existing) against the `baseline` set.

    Comparison is by the full violation string (which already embeds the offending directory's
    path), never by filtering `current` down to directories this tree touched -- the by-delta-
    never-by-path rule.
    """
    baseline_set = set(baseline)
    new = [v for v in current if v not in baseline_set]
    pre_existing = [v for v in current if v in baseline_set]
    return new, pre_existing


def corpus_mode(root: Path) -> int:
    prefixes = load_repo_prefixes(root)
    dirs, file_count = discover_spec_dirs(root)
    print(
        f"discovered {file_count} distinct tasks.json/tasks.md file(s) across {len(dirs)} spec "
        "director(y/ies)"
    )
    print(f"{len(prefixes)} repo prefix(es) loaded from brain.toml")

    current_violations = check_dirs(dirs, prefixes)

    baseline_sha, baseline_desc = resolve_baseline_commit(root)
    if baseline_sha is None:
        print(f"\nWARNING: baseline unresolvable ({baseline_desc}).")
        print(
            "WARNING: falling back to FAIL CLOSED -- every violation found is treated as NEW "
            "(the pre-delta-attribution whole-corpus-blocks behavior). This is a documented "
            "edge case (a truly fresh clone/init with zero commits), not a silent no-op."
        )
        new_violations = current_violations
        pre_existing_violations: list[str] = []
    else:
        print(f"\nbaseline resolved: {baseline_desc} ({baseline_sha[:12]})")
        baseline_dirs = read_baseline_dirs(root, baseline_sha)
        baseline_violations = check_dirs(baseline_dirs, prefixes)
        new_violations, pre_existing_violations = classify_violations(
            current_violations, baseline_violations
        )

    if current_violations:
        pre_existing_set = set(pre_existing_violations)
        print(
            f"\n{len(current_violations)} non-conforming block director(y/ies) found "
            f"({len(new_violations)} NEW / blocking, {len(pre_existing_violations)} "
            "pre-existing / reported, not blocking):"
        )
        for v in current_violations:
            if v in pre_existing_set:
                print(f"  pre-existing (reported): {v}")
            else:
                print(f"  NEW (blocking): {v}")
    else:
        print("\nall block directories conform to <REPO>.<phase>.<block>")

    if new_violations:
        print(
            f"\nBLOCKED: {len(new_violations)} NEW non-conforming block director(y/ies) "
            "attributable to this tree's changes."
        )
        return 1

    if pre_existing_violations:
        print(
            f"\nno NEW violations. {len(pre_existing_violations)} pre-existing non-conforming "
            "director(y/ies) were reported above but are NOT blocking -- this is a report of "
            "what this tree did not break, not a claim the whole fleet is migrated."
        )
    else:
        print("\nno non-conforming block directories at all")
    return 0


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
    """A real (but throwaway) git repo -- delta attribution's baseline resolution and
    `git ls-tree`-based reconstruction are exercised for real here, not mocked.
    """
    base.mkdir(parents=True, exist_ok=True)
    _git_ok(["init", "-q"], base)
    _git_ok(["config", "user.email", "test@example.com"], base)
    _git_ok(["config", "user.name", "Block Naming Fixture"], base)


def _commit_all(base: Path, message: str) -> None:
    _git_ok(["add", "-A"], base)
    _git_ok(["commit", "-q", "-m", message], base)


def _run_corpus_mode(root: Path) -> tuple[int, str]:
    """Run the real `corpus_mode` against `root`, capturing stdout (never a mock) so cases can
    assert both the exit code and the human-readable NEW/pre-existing labeling.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = corpus_mode(root)
    return rc, buf.getvalue()


def self_test() -> int:
    print("check_block_naming.py --self-test")

    # (a) Canonical passes: letter block, numeric block, and a three-letter prefix.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
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
        del base  # unused in this pure-function case

    # (b) ticket-/chore-/plan- directories are ignored entirely, even though they never match the
    # canonical shape.
    check("(b) ticket-foo is ignored", is_ignored_dir("ticket-foo"))
    check("(b) chore-foo is ignored", is_ignored_dir("chore-foo"))
    check("(b) plan-foo is ignored", is_ignored_dir("plan-foo"))
    # Proven negative: a directory that merely CONTAINS one of those words, but isn't prefixed
    # with it, is NOT ignored -- it still must conform.
    check(
        "(b) negative: a directory containing 'ticket' but not prefixed is not ignored",
        not is_ignored_dir("my-ticket-followup"),
    )

    # (c) Prefixes come from brain.toml, not a hardcoded list -- a fixture declaring a NEW prefix
    # accepts directories using it without editing this script.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _write_brain_toml(base, ["ZQ"])
        loaded = load_repo_prefixes(base)
        check("(c) a novel prefix (ZQ) round-trips from brain.toml", loaded == ["ZQ"])
        pattern = block_id_pattern(loaded)
        check("(c) ZQ.1.A is canonical once declared in brain.toml", classify_dir("ZQ.1.A", pattern))
        # Proven negative: an UNREGISTERED prefix of the same shape is rejected.
        check(
            "(c) negative: an unregistered prefix (QQ.1.A) is rejected",
            not classify_dir("QQ.1.A", pattern),
        )

    # (d) No content assertion -- a spec directory with a canonical NAME whose tasks.md BODY
    # contains an old-style string (`10.B-foo`) still passes; this guard inspects names only.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        d = _write_spec_dir(
            base, "BW.10.B", "tasks.md",
            body="See legacy block 10.B-foo for context; also hq-4a-legacy is referenced here.",
        )
        violations = check_dirs([d], _FIXTURE_PREFIXES)
        check("(d) canonical dir with old-style strings in its BODY still passes", violations == [])

    # (e) Delta attribution: pre-existing non-conforming reports but does not block -- the bad
    # directory is already in the baseline commit, and the working tree introduces no further
    # change. This is the case that keeps the fleet green today.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _init_git_repo(base)
        _write_brain_toml(base)
        _write_spec_dir(base, "10.B-legacy-block")
        _commit_all(base, "baseline already carries the violation")
        rc, out = _run_corpus_mode(base)
        check("(e) pre-existing non-conforming dir does not block (exit 0)", rc == 0)
        check("(e) pre-existing non-conforming dir is labeled in output", "pre-existing" in out)

        # Proven negative: the SAME violation, but introduced only AFTER the baseline commit --
        # must NOT be reported as pre-existing, proving this case discriminates baseline
        # membership rather than always passing.
        base2 = Path(td) / "negative"
        _init_git_repo(base2)
        _write_brain_toml(base2)
        _write_spec_dir(base2, "BW.1.A")
        _commit_all(base2, "clean baseline")
        _write_spec_dir(base2, "10.B-legacy-block")
        rc2, _out2 = _run_corpus_mode(base2)
        check("(e) negative: a newly introduced violation is NOT reported as pre-existing", rc2 == 1)

    # (f) New violation blocks: baseline is clean, the working tree introduces a non-conforming
    # directory.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _init_git_repo(base)
        _write_brain_toml(base)
        _write_spec_dir(base, "BW.1.A")
        _commit_all(base, "clean baseline")
        _write_spec_dir(base, "hq-4a-new-block")
        rc, out = _run_corpus_mode(base)
        check("(f) new non-conforming dir blocks (exit non-zero)", rc == 1)
        check("(f) new violation is labeled NEW in output", "NEW (blocking)" in out)

        # Proven negative: remove the offending directory entirely -- must return to exit 0,
        # proving the block tracks the violation's presence, not some unrelated state.
        shutil.rmtree(base / "hq-4a-new-block")
        rc2, _ = _run_corpus_mode(base)
        check("(f) negative: removing the new violation returns to exit 0", rc2 == 0)

    # (g) Baseline unresolvable (no git repo at all) -- documented fallback is FAIL CLOSED: every
    # violation found is treated as NEW.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)  # deliberately NOT a git repo
        _write_brain_toml(base)
        _write_spec_dir(base, "10.B-legacy-block")
        rc, out = _run_corpus_mode(base)
        check("(g) baseline-unresolvable + a violation fails closed (blocks)", rc == 1)
        check(
            "(g) baseline-unresolvable is reported with a WARNING",
            "WARNING" in out and "FAIL CLOSED" in out,
        )

        # Proven negative: baseline still unresolvable, but the corpus is well-formed -- fail
        # closed must not block UNCONDITIONALLY, only when there is an actual violation to find.
        base2 = Path(td) / "negative"
        _write_brain_toml(base2)
        _write_spec_dir(base2, "BW.1.A")
        rc2, _ = _run_corpus_mode(base2)
        check("(g) negative: baseline-unresolvable with no violations still exits 0", rc2 == 0)

    # (h) End-to-end discovery: -L -uu realpath-deduped sweep finds spec dirs reachable via a
    # symlink (mirrors every repo's `planning/` being a symlink into the vault).
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        real_target = base / "_vault" / "BW.2.A"
        real_target.mkdir(parents=True)
        (real_target / "tasks.json").write_text("{}", encoding="utf-8")
        symlinked_planning = base / "planning"
        symlinked_planning.mkdir()
        os.symlink(real_target, symlinked_planning / "BW.2.A")
        dirs, file_count = discover_spec_dirs(base)
        check("(h) symlinked spec dir is discovered", file_count == 1)
        check("(h) discovered dir realpath-resolves to the vault target", dirs == [real_target.resolve()])

    # (i) Live snapshot, dated -- re-measure against the REAL fleet at implementation time and
    # pin the RELATION (total block-shaped dirs == canonical + non-conforming), not a hard-coded
    # count -- a hard-coded count breaks the moment any repo adds a block. The corresponding
    # command is printed alongside the count so a future reader can re-measure by hand.
    # Measured 2026-08-12: `python3 scripts/check_block_naming.py` against the real fleet found
    # 39 block-shaped directories, 13 canonical, 26 non-conforming (21 `<phase>.<block>-<title>`,
    # 5 `<repo>-<phase><block>-<title>`), all pre-existing at that measurement's baseline.
    #
    # NOTE: `self_test()`'s own contract (see the module's TWO MODES section) is synthetic
    # fixtures with NO dependency on the real corpus -- the real corpus is written by every lane
    # in the fleet concurrently, so it is not a hermetic input. This case therefore hard-asserts
    # only the RELATION (a structural invariant of `check_dirs`'s partition, true by
    # construction) and PRINTS -- rather than hard-asserts -- the live delta-mode result, so a
    # concurrent lane's unrelated commit to the shared brain repo can never flip this self-test
    # red. "today's fleet exits 0 (all pre-existing)" is separately proven, hermetically, by
    # synthetic case (e) above; this case's job is only to record and re-measure the live count.
    real_root = find_brain_root() or find_brain_root(REPO_ROOT)
    if real_root is None:
        check("(i) live snapshot: brain root resolves for re-measurement", False)
    else:
        prefixes = load_repo_prefixes(real_root)
        dirs, _file_count = discover_spec_dirs(real_root)
        block_shaped = [d for d in dirs if not is_ignored_dir(d.name)]
        pattern = block_id_pattern(prefixes)
        canonical = [d for d in block_shaped if classify_dir(d.name, pattern)]
        non_conforming = [d for d in block_shaped if not classify_dir(d.name, pattern)]
        print(
            f"  (i) live snapshot (measuring command: `python3 scripts/check_block_naming.py`): "
            f"{len(block_shaped)} block-shaped director(y/ies), {len(canonical)} canonical, "
            f"{len(non_conforming)} non-conforming"
        )
        check(
            "(i) live snapshot: canonical + non-conforming accounts for every block-shaped dir "
            "(the relation, not a hard-coded count)",
            len(canonical) + len(non_conforming) == len(block_shaped),
        )
        rc, _out = _run_corpus_mode(real_root)
        print(
            f"  (i) live snapshot: `python3 scripts/check_block_naming.py` currently exits {rc} "
            f"({'no NEW violations' if rc == 0 else 'NEW violations present -- see plain run'})"
        )

    if FAILURES:
        print(f"\n{len(FAILURES)} self-test case(s) failed: {FAILURES}")
        return 1
    print("\nall self-test cases passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run synthetic fixture cases only")
    parser.add_argument(
        "--root", type=Path, default=None,
        help="brain root to sweep in corpus mode (default: walk up from cwd for brain.toml)",
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    root = args.root or find_brain_root() or find_brain_root(REPO_ROOT)
    if root is None:
        print(
            "could not resolve brain root (no brain.toml found walking up from cwd or "
            "REPO_ROOT); pass --root explicitly",
            file=sys.stderr,
        )
        return 2
    return corpus_mode(root)


if __name__ == "__main__":
    sys.exit(main())
