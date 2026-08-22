#!/usr/bin/env bash
#
# test_commander_drain.sh — commit-scope and orphan-routing coverage for the orchestration
# commander (BT.6.D), with git, bastion and emit_state_write.sh shimmed so NOTHING is
# committed, emitted or sent by this suite.
#
# WHAT THIS TESTS AND WHY: the commander's own wrapper (scripts/commander_drain.sh) does not
# itself decide what to commit — that decision is made by the BRAIN's already-shipped
# emit_state_write.sh / commit_routine_updates.sh, which the drain's turn calls per step 3 of
# .claude/commands/orchestration-commander.md ("call that machinery and trust its manifest, not
# reinvent detection"). So cases 1-3 below run the REAL commit_routine_updates.sh (copied
# byte-for-byte into an isolated scratch tree, never the checked-out repo) with `git` shimmed on
# PATH ahead of the real one — this is "the caller" the command file's step 3 refers to, and case
# 3 is the same assertion HQ.ticket.commit-routine-updates-sweeps-staged-work pins upstream,
# re-asserted here because the commander calls that script routinely and turns a rare edge case
# into a scheduled one. Case 4 pins the three-way authored-orphan lease-routing contract from the
# command file's step 4 as a reference classifier (`classify_orphan()` below) that any future
# non-LLM implementation of that step must match. Case 5 exercises scripts/commander_drain.sh
# itself (the one piece of this block that IS a real, testable shell script) with `bastion`
# shimmed so no tmux session or Claude turn is ever launched.
#
# Per D68 (base-template's "a gate must be shown capable of failing on the deliverable"
# discipline): every negative case below (2, 3, and each non-silent route in 4) was run first
# against a deliberately-wrong stand-in — case 2 against a version of commit_routine_updates.sh
# with the manifest check removed (it wrongly staged the authored file); case 3 against a version
# that used `git add -A` instead of the resolved pathspec loop (it wrongly swept the pre-staged
# unrelated file); case 4 against a classifier that only checked heartbeat age (it wrongly
# labeled a stale-but-live agent as "alert") — and observed FAILING before the real logic here was
# confirmed to make each one pass.
#
# Shape follows scripts/test_send_alert.sh: a PATH-prepended shim dir, one scratch tempdir per
# case, one PASS/FAIL line per case via check(), non-zero exit on any failure.
#
#   ./scripts/test_commander_drain.sh
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0
n=0
check() { # check <description> <result: 0=pass>
  n=$((n + 1))
  if [ "$2" -eq 0 ]; then printf 'PASS (%d): %s\n' "$n" "$1"
  else printf 'FAIL (%d): %s\n' "$n" "$1"; fail=1; fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- resolve the brain root this checked-out worktree already lives under -------------------
# We copy the REAL brain scripts (never the checked-out repo's own tree) into isolated scratch
# dirs below — this suite never touches the actual planning/state.json, .fleet-locks, or logs.
BRAIN_ROOT_REAL="$(cd "$REPO_ROOT" && python3 - <<'PY'
import os
d = os.getcwd()
while d != "/":
    if os.path.exists(os.path.join(d, "brain.toml")):
        print(d)
        break
    d = os.path.dirname(d)
PY
)"
if [ -z "$BRAIN_ROOT_REAL" ] || [ ! -f "$BRAIN_ROOT_REAL/scripts/commit_routine_updates.sh" ]; then
  echo "FATAL: could not locate the real brain scripts (commit_routine_updates.sh) by walking up from $REPO_ROOT" >&2
  exit 1
fi

# ==============================================================================================
# Cases 1-3: commit scope, via the REAL commit_routine_updates.sh with git shimmed.
# ==============================================================================================

setup_commit_case() { # setup_commit_case <case-dir> -> prints "<brain>" (the scratch brain root)
  local case_dir="$1"
  mkdir -p "$case_dir/brain/scripts" "$case_dir/brain/logs" "$case_dir/bin"
  cp "$BRAIN_ROOT_REAL/scripts/lib.sh" "$case_dir/brain/scripts/lib.sh"
  cp "$BRAIN_ROOT_REAL/scripts/commit_routine_updates.sh" "$case_dir/brain/scripts/commit_routine_updates.sh"
  chmod +x "$case_dir/brain/scripts/commit_routine_updates.sh"
  echo "primary" > "$case_dir/brain/.brain-role"

  # git shim: records every invocation's argv verbatim to $GIT_ARGV_LOG, one line per call, and
  # returns the exit code the case needs to drive commit_routine_updates.sh down the right
  # branch — this is what lets the assertions below inspect the ACTUAL argv the wrapper would
  # have run, not prose in a log line.
  cat > "$case_dir/bin/git" <<'SH'
#!/usr/bin/env bash
printf 'git %s\n' "$*" >> "$GIT_ARGV_LOG"
case "$1" in
  add) exit 0 ;;
  diff) exit "${GIT_DIFF_EXIT:-1}" ;;   # 1 = "there is a staged diff" (git diff --quiet convention)
  commit) exit 0 ;;
  branch) echo "main"; exit 0 ;;
  push) exit 0 ;;
  *) exit 0 ;;
esac
SH
  chmod +x "$case_dir/bin/git"
  echo "$case_dir/brain"
}

# --- Case 1: a DERIVED file left dirty is rewritten, named in the manifest, and IS committed --
# with the manifest as the exact commit pathspec.
CASE1="$WORK/case1"
BRAIN1="$(setup_commit_case "$CASE1")"
DERIVED_FILE="$BRAIN1/planning/state.json"
mkdir -p "$(dirname "$DERIVED_FILE")"
echo '{"derived": true}' > "$DERIVED_FILE"
echo "$DERIVED_FILE" > "$BRAIN1/logs/.emit_wrote"
# commit_routine_updates.sh resolves every manifest path with `realpath` before staging (its own
# comment: bastion's I_EMIT_WROTE lines can name a symlinked path) — assert against that resolved
# form, since that is what actually reaches git's argv.
DERIVED_FILE_REAL="$(realpath "$DERIVED_FILE")"

GIT_ARGV_LOG="$CASE1/git_argv.log"
: > "$GIT_ARGV_LOG"
( cd "$BRAIN1" && PATH="$CASE1/bin:$PATH" GIT_ARGV_LOG="$GIT_ARGV_LOG" GIT_DIFF_EXIT=1 \
    bash scripts/commit_routine_updates.sh >/dev/null 2>&1 )
CASE1_EXIT=$?

if [ "$CASE1_EXIT" -eq 0 ] \
  && grep -qF "git add -- $DERIVED_FILE_REAL" "$GIT_ARGV_LOG" \
  && grep -q "^git commit -o -m .* -- $DERIVED_FILE_REAL\$" "$GIT_ARGV_LOG"; then
  r=0
else
  r=1
fi
check "derived file dirty -> committed, with the manifest as the commit pathspec" "$r"

# --- Case 2: an AUTHORED file left dirty by another lane is reported and is NOT staged / ------
# NOT committed. The manifest names only the derived file; the authored file never appears in
# any git invocation's argv, and the index (the shimmed `git add` call log) is never touched
# for it.
CASE2="$WORK/case2"
BRAIN2="$(setup_commit_case "$CASE2")"
DERIVED_FILE2="$BRAIN2/planning/state.json"
AUTHORED_FILE="$BRAIN2/docs/authored-by-a-lane.md"
mkdir -p "$(dirname "$DERIVED_FILE2")" "$(dirname "$AUTHORED_FILE")"
echo '{"derived": true}' > "$DERIVED_FILE2"
echo "# authored, mid-work" > "$AUTHORED_FILE"
echo "$DERIVED_FILE2" > "$BRAIN2/logs/.emit_wrote"   # AUTHORED_FILE deliberately absent from the manifest

GIT_ARGV_LOG="$CASE2/git_argv.log"
: > "$GIT_ARGV_LOG"
( cd "$BRAIN2" && PATH="$CASE2/bin:$PATH" GIT_ARGV_LOG="$GIT_ARGV_LOG" GIT_DIFF_EXIT=1 \
    bash scripts/commit_routine_updates.sh >/dev/null 2>&1 )

if ! grep -qF "$AUTHORED_FILE" "$GIT_ARGV_LOG"; then
  r=0
else
  r=1
fi
check "authored file dirty -> reported, never staged or committed (absent from every git argv)" "$r"

# --- Case 3: a PRE-STAGED UNRELATED FILE is NOT swept into the commit -------------------------
# Simulates a sibling lane having already run `git add` on its own file before this drain's
# commit_routine_updates.sh call. Because that script only ever stages the resolved manifest
# pathspec (never `-A`/`.`), the unrelated file must be absent from the `git commit -- <paths>`
# argv even though nothing here un-stages it.
CASE3="$WORK/case3"
BRAIN3="$(setup_commit_case "$CASE3")"
DERIVED_FILE3="$BRAIN3/planning/state.json"
UNRELATED_FILE="$BRAIN3/docs/sibling-lane-in-flight.md"
mkdir -p "$(dirname "$DERIVED_FILE3")" "$(dirname "$UNRELATED_FILE")"
echo '{"derived": true}' > "$DERIVED_FILE3"
echo "# pre-staged by a sibling lane, not this drain" > "$UNRELATED_FILE"
echo "$DERIVED_FILE3" > "$BRAIN3/logs/.emit_wrote"

GIT_ARGV_LOG="$CASE3/git_argv.log"
: > "$GIT_ARGV_LOG"
( cd "$BRAIN3" && PATH="$CASE3/bin:$PATH" GIT_ARGV_LOG="$GIT_ARGV_LOG" GIT_DIFF_EXIT=1 \
    bash scripts/commit_routine_updates.sh >/dev/null 2>&1 )

COMMIT_LINE="$(grep '^git commit ' "$GIT_ARGV_LOG" || true)"
if [ -n "$COMMIT_LINE" ] && ! printf '%s' "$COMMIT_LINE" | grep -qF "$UNRELATED_FILE"; then
  r=0
else
  r=1
fi
check "pre-staged unrelated file is absent from the commit pathspec, at the caller" "$r"

# ==============================================================================================
# Case 4: the three authored-orphan lease routes, as a reference classifier pinning the
# command file's step 4 contract (no shell implementation exists elsewhere in this block —
# routing an actual drain's orphans is the Claude turn's job; this pins what "correct" means).
# ==============================================================================================

# classify_orphan <lease_present:0|1> <agent_in_listagents:0|1> <heartbeat_stale:0|1>
#   -> prints one of: silent | recovery | alert
# Mirrors orchestration-commander.md step 4 exactly:
#   no lease at all                                -> alert
#   lease held, agent absent from ListAgents        -> recovery
#   lease held, agent live but heartbeat stale      -> recovery
#   lease held, agent live, heartbeat not stale     -> silent
classify_orphan() {
  local lease_present="$1" agent_live="$2" heartbeat_stale="$3"
  if [ "$lease_present" -eq 0 ]; then
    echo "alert"
    return
  fi
  if [ "$agent_live" -eq 0 ] || [ "$heartbeat_stale" -eq 1 ]; then
    echo "recovery"
    return
  fi
  echo "silent"
}

r=0
[ "$(classify_orphan 1 1 0)" = "silent" ] || r=1
check "lease held, agent live, heartbeat fresh -> silent" "$r"

r=0
[ "$(classify_orphan 1 0 0)" = "recovery" ] || r=1
check "lease held, agent absent from ListAgents -> named recovery item" "$r"

r=0
[ "$(classify_orphan 1 1 1)" = "recovery" ] || r=1
check "lease held, agent live but heartbeat stale -> named recovery item" "$r"

r=0
[ "$(classify_orphan 0 0 0)" = "alert" ] || r=1
check "no lease at all -> alert" "$r"

# ==============================================================================================
# Case 5: a drain with an EMPTY inbox exits clean and still stamps the heartbeat.
# Exercises the real scripts/commander_drain.sh, with `bastion` shimmed so no tmux session or
# Claude turn is ever launched.
# ==============================================================================================

CASE5="$WORK/case5"
mkdir -p "$CASE5/brain/repo/scripts" "$CASE5/brain/repo/.claude/commands" "$CASE5/brain/scripts" "$CASE5/bin"
touch "$CASE5/brain/brain.toml"
cp "$BRAIN_ROOT_REAL/scripts/lib.sh" "$CASE5/brain/scripts/lib.sh"
cp "$REPO_ROOT/scripts/commander_drain.sh" "$CASE5/brain/repo/scripts/commander_drain.sh"
cp "$REPO_ROOT/.claude/commands/orchestration-commander.md" \
   "$CASE5/brain/repo/.claude/commands/orchestration-commander.md"
chmod +x "$CASE5/brain/repo/scripts/commander_drain.sh"

# lib.sh (sourced by commander_drain.sh) unconditionally re-exports PATH as
# "$HOME/.cargo/bin:...:$PATH" -- putting the REAL installed `bastion` (this machine's
# ~/.cargo/bin/bastion) ahead of any shim dir we merely prepend beforehand. Give this
# subshell its own fake HOME instead, with the shim at ~/.cargo/bin/bastion, so lib.sh's
# own PATH re-export resolves to our shim first without touching the real ~/.cargo/bin or
# launching the real `bastion ask` (which would open a real tmux session).
FAKE_HOME="$CASE5/fake_home"
mkdir -p "$FAKE_HOME/.cargo/bin"

BASTION_LOG="$CASE5/bastion.log"
: > "$BASTION_LOG"
cat > "$FAKE_HOME/.cargo/bin/bastion" <<SH
#!/usr/bin/env bash
echo "BASTION \$*" >> "$BASTION_LOG"
if [ "\$1" = "ask" ]; then
  # find the --out path and drop a minimal, well-formed turn result so a real caller
  # inspecting it would not choke; this shim never launches a tmux session or a Claude turn.
  out=""
  while [ \$# -gt 0 ]; do
    if [ "\$1" = "--out" ]; then out="\$2"; fi
    shift
  done
  [ -n "\$out" ] && echo '{"status":"ok"}' > "\$out"
  exit 0
fi
exit 0
SH
chmod +x "$FAKE_HOME/.cargo/bin/bastion"

HEARTBEAT_DIR="$CASE5/brain/.fleet-locks/commander-heartbeats"
HEARTBEAT_FILE="$HEARTBEAT_DIR/repo-main.heartbeat"

DRAIN_LOG_OUT="$CASE5/drain_stdout.log"
( cd "$CASE5/brain/repo" && HOME="$FAKE_HOME" PATH="$FAKE_HOME/.cargo/bin:$PATH" \
    bash scripts/commander_drain.sh --repo repo --lane main > "$DRAIN_LOG_OUT" 2>&1 )
CASE5_EXIT=$?

r=0
[ "$CASE5_EXIT" -eq 0 ] || r=1
[ -f "$HEARTBEAT_FILE" ] || r=1
grep -qi "empty" "$DRAIN_LOG_OUT" || r=1
check "empty inbox: drain exits 0, stamps the heartbeat, and logs that it was empty" "$r"

# footer --------------------------------------------------------------------------------------
echo
if [ "$fail" -eq 0 ]; then echo "ALL PASS ($n cases)"; else echo "FAILURES ($n cases)"; fi
exit "$fail"
