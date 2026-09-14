#!/usr/bin/env python3
"""Recover recorded work-assertion bails from the HQ brain's bail-classification retro into
meta.schema.json (kind: bail) fixture files under scripts/fixtures/bail_meta/work_assertion/.

Source data: the HQ brain repo's
planning/open-work/orchestration-runs/retros/bail-classification-2026-09-13.json — reachable from
this script as `Path(__file__).resolve().parent.parent.parent / 'planning/open-work/...'`, since
base-template is a direct child of the agentic-portfolio HQ root (the same "reach the parent HQ
checkout read-only" pattern scripts/test_escalation_writer_example.py already uses for its own
`../planning` reference).

The classification file is a flat JSON array of 141 records, one per bail an earlier retro
classified. This script filters to the subset whose text mentions work-assertion machinery
(`work assertion` / `WORK_ASSERTION` / `workAssertionPassed`, case-insensitively) by grepping the
raw record content — never hand-picked — then, for each match, tries to deterministically recover
enough of the original shape to replay it as a fixture:

    - `repo` / `engine` / `task_id` / `primary_class` / `specific_rule` / `source` come straight off
      the classification record.
    - `declared_files` is read from the sibling `tasks.json` next to the referenced state file
      (`<spec_dir>/tasks.json`, where the state file lives at `<spec_dir>/sdlc/<engine>-state.json`).
    - `name_status` (the literal `git diff --name-status` lines) is recovered from the ACTUAL git
      history of the repo the bail happened in:
        * sdlc-task state files record a `commit` sha per task. A non-empty commit is resolved
          against that project's own git checkout (`core/<repo>/` or `<repo>/` under the HQ root,
          or the HQ root itself for repo == "HQ") via `git diff --name-status <prev>..<sha>` (or
          `git show --name-status` when there is no usable previous sha); an empty `commit` field
          means the attempt made no commit, which is itself a legitimate, meaningful empty-diff
          value, not a stand-in for "unrecoverable".
        * sdlc-flow state files never record a per-task commit sha at all (verified structurally
          against a real archived flow-state.json) — the only case this script can recover without
          guessing is the bailing task itself sitting in a non-terminal status ("pending"/"failed"),
          which means no commit was made for it either. A flow task recorded as complete carries no
          sha this script could resolve, so that shape is reported UNRECOVERABLE rather than
          invented.
    - `task_kind` is inferred from `declared_files` (`validate-only` when empty, else
      `code-change`).
    - `validation_exit_codes` is intentionally omitted — none of these historical records carry
      per-command exit codes to recover.

A record is written as a fixture only when every required field for meta.schema.json's `bail`
object was actually recovered. Anything else is reported UNRECOVERABLE on stdout, by name and
specific reason, and never silently dropped or padded with an invented value.

Run: python3 scripts/extract_bail_meta_fixtures.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
HQ_ROOT = REPO_ROOT.parent

BAIL_CLASSIFICATION_PATH = (
    HQ_ROOT / "planning" / "open-work" / "orchestration-runs" / "retros" / "bail-classification-2026-09-13.json"
)
OUT_DIR = REPO_ROOT / "scripts" / "fixtures" / "bail_meta" / "work_assertion"

WORK_ASSERTION_PATTERN = re.compile(r"work[- _]?assertion|WORK_ASSERTION|workAssertionPassed", re.I)

VALID_ENGINES = ("task", "flow")
DONE_STATUSES = ("done", "passed", "completed", "complete")


def find_work_assertion_records(records: list[dict]) -> list[tuple[int, dict]]:
    """Deterministic case-insensitive substring filter over each record's raw JSON text."""
    matches = []
    for i, rec in enumerate(records):
        blob = json.dumps(rec)
        if WORK_ASSERTION_PATTERN.search(blob):
            matches.append((i, rec))
    return matches


def resolve_repo_git_root(repo: str) -> Path | None:
    candidates = []
    if repo == "HQ":
        candidates.append(HQ_ROOT)
    candidates.append(HQ_ROOT / "core" / repo)
    candidates.append(HQ_ROOT / repo)
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate
    return None


def load_state_file(f_rel: str) -> tuple[dict | None, Path | None, str | None]:
    if not f_rel:
        return None, None, "classification record has no 'f' (source state-file path)"
    path = HQ_ROOT / f_rel
    if not path.is_file():
        return None, path, f"source state file not found at {f_rel}"
    try:
        return json.loads(path.read_text()), path, None
    except (json.JSONDecodeError, OSError) as exc:
        return None, path, f"source state file at {f_rel} is not parseable JSON ({exc})"


def load_declared_files(state_path: Path, task_id) -> tuple[list | None, str | None]:
    spec_dir = state_path.parent.parent
    tasks_json_path = spec_dir / "tasks.json"
    if not tasks_json_path.is_file():
        return None, f"no sibling tasks.json at {tasks_json_path.relative_to(HQ_ROOT)}"
    try:
        tasks = json.loads(tasks_json_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"sibling tasks.json at {tasks_json_path.relative_to(HQ_ROOT)} is not parseable JSON ({exc})"
    tid_str = str(task_id)
    for t in tasks:
        if str(t.get("task_id")) == tid_str:
            files = t.get("files")
            if files is None:
                return None, f"task {tid_str} in {tasks_json_path.relative_to(HQ_ROOT)} has no 'files' key"
            return files, None
    return None, f"task_id {tid_str} not found in {tasks_json_path.relative_to(HQ_ROOT)}"


def git_rev_exists(repo_root: Path, sha: str) -> bool:
    if not sha:
        return False
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def git_name_status(repo_root: Path, prev_sha: str | None, this_sha: str) -> list[str] | None:
    if prev_sha:
        cmd = ["git", "-C", str(repo_root), "diff", "--name-status", f"{prev_sha}..{this_sha}"]
    else:
        cmd = ["git", "-C", str(repo_root), "show", "--name-status", "--format=", this_sha]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return [line for line in proc.stdout.splitlines() if line.strip()]


def recover_name_status(
    engine: str,
    task_entry: dict | None,
    repo_root: Path | None,
    prev_commit: str | None,
) -> tuple[list[str] | None, str | None, str | None]:
    """Returns (name_status, commit_range, unrecoverable_reason)."""
    if engine == "task":
        commit = (task_entry or {}).get("commit") or ""
        if not commit:
            # No commit was made for this attempt -- a legitimate, meaningful empty diff.
            return [], None, None
        if repo_root is None:
            return None, None, f"no git repo checkout found to resolve commit {commit}"
        if not git_rev_exists(repo_root, commit):
            return None, None, f"commit {commit} not reachable in {repo_root.name}'s git history"
        usable_prev = prev_commit if (prev_commit and git_rev_exists(repo_root, prev_commit)) else None
        lines = git_name_status(repo_root, usable_prev, commit)
        if lines is None:
            return None, None, f"git diff/show against {repo_root.name} failed for commit {commit}"
        commit_range = f"{usable_prev}..{commit}" if usable_prev else commit
        return lines, commit_range, None
    if engine == "flow":
        status = (task_entry or {}).get("status")
        if status in DONE_STATUSES:
            return (
                None,
                None,
                "sdlc-flow state records no per-task commit sha; cannot recover name_status for a "
                f"task recorded as status={status!r}",
            )
        # The bailing task never reached a terminal status, so no commit was made for it either.
        return [], None, None
    return None, None, f"unrecognized engine {engine!r} (expected 'task' or 'flow')"


def normalize_engine(raw: str | None) -> str | None:
    if raw in VALID_ENGINES:
        return raw
    return None


def build_fixture(repo, engine, task_id, name_status, declared_files, task_kind, source, commit_range, primary_class, specific_rule) -> dict:
    bail: dict = {
        "repo": repo,
        "engine": engine,
        "task_id": task_id,
        "name_status": name_status,
        "declared_files": declared_files,
        "task_kind": task_kind,
        "source": source,
    }
    if commit_range:
        bail["commit_range"] = commit_range
    if primary_class:
        bail["primary_class"] = primary_class
    if specific_rule:
        bail["specific_rule"] = specific_rule
    return {"schema_version": 1, "kind": "bail", "bail": bail}


def slugify(value) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-") or "unknown"


def main() -> int:
    if not BAIL_CLASSIFICATION_PATH.is_file():
        print(f"ERROR: bail-classification source not found at {BAIL_CLASSIFICATION_PATH}", file=sys.stderr)
        return 1

    try:
        records = json.loads(BAIL_CLASSIFICATION_PATH.read_text())
    except json.JSONDecodeError as exc:
        print(f"ERROR: bail-classification source is not parseable JSON: {exc}", file=sys.stderr)
        return 1

    matches = find_work_assertion_records(records)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    name_counts: dict[str, int] = {}

    recovered = 0
    unrecoverable = 0

    for index, rec in matches:
        repo = rec.get("repo")
        engine = normalize_engine(rec.get("eng"))
        raw_task_id = rec.get("task_id")
        f_rel = rec.get("f")
        primary_class = rec.get("primary_class")
        specific_rule = rec.get("specific_rule")

        label = f"record[{index}] repo={repo!r} eng={rec.get('eng')!r} task_id={raw_task_id!r} f={f_rel!r}"

        reasons: list[str] = []

        if raw_task_id is None:
            reasons.append("task_id is null in classification record")
        if engine is None:
            reasons.append(f"engine field 'eng'={rec.get('eng')!r} is not one of {VALID_ENGINES}")
        if not repo:
            reasons.append("classification record has no 'repo'")

        state = None
        state_path = None
        if not reasons or f_rel:
            state, state_path, state_reason = load_state_file(f_rel)
            if state_reason:
                reasons.append(state_reason)

        declared_files = None
        if state is not None and state_path is not None and raw_task_id is not None:
            declared_files, declared_reason = load_declared_files(state_path, raw_task_id)
            if declared_reason:
                reasons.append(declared_reason)

        repo_root = resolve_repo_git_root(repo) if repo else None

        name_status = None
        commit_range = None
        if state is not None and engine is not None and raw_task_id is not None:
            task_entry = (state.get("tasks") or {}).get(str(raw_task_id))
            prev_commit = None
            if engine == "task":
                try:
                    prev_id = str(int(raw_task_id) - 1)
                except (TypeError, ValueError):
                    prev_id = None
                if prev_id is not None:
                    prev_entry = (state.get("tasks") or {}).get(prev_id)
                    if prev_entry:
                        prev_commit = prev_entry.get("commit") or None
                if not prev_commit:
                    prev_commit = state.get("base_sha") or None
            name_status, commit_range, ns_reason = recover_name_status(engine, task_entry, repo_root, prev_commit)
            if ns_reason:
                reasons.append(ns_reason)

        task_kind = None
        if declared_files is not None:
            task_kind = "validate-only" if len(declared_files) == 0 else "code-change"

        if reasons:
            print(f"UNRECOVERABLE: {label} -- {'; '.join(reasons)}")
            unrecoverable += 1
            continue

        fixture = build_fixture(
            repo=repo,
            engine=engine,
            task_id=raw_task_id,
            name_status=name_status,
            declared_files=declared_files,
            task_kind=task_kind,
            source=f_rel,
            commit_range=commit_range,
            primary_class=primary_class,
            specific_rule=specific_rule,
        )

        base_name = f"{slugify(repo)}-{slugify(engine)}-{slugify(raw_task_id)}"
        name_counts[base_name] = name_counts.get(base_name, 0) + 1
        n = name_counts[base_name]
        filename = f"{base_name}.json" if n == 1 else f"{base_name}-{n}.json"
        out_path = OUT_DIR / filename
        out_path.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n")

        recovered += 1

    print(f"recovered: {recovered} unrecoverable: {unrecoverable}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
