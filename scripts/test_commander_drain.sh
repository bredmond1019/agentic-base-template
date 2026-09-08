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

# --- unique per-run fixture identity, so two concurrent runs of this suite cannot collide ----
# commander_drain.sh:145 derives SESSION="commander-${REPO_NAME}-${LANE}" -- a FIXED name if the
# fixture always passes the same --repo. $WORK is already unique per run (mktemp -d), so derive
# the fixture repo name from it rather than hardcoding "repo" as case 5 used to.
#
# $WORK's basename (from macOS mktemp -d, e.g. "tmp.XXXXXXXX") contains a literal "." --
# tmux's target syntax treats "." as the session.window separator, so a session name built
# from it verbatim is misparsed by `tmux has-session`/`kill-session` (measured: both silently
# no-op against the dotted name). Strip anything that is not alnum/dash before using it.
FIXTURE_REPO="drainfix-$(basename "$WORK" | tr -c 'A-Za-z0-9' '-')"
FIXTURE_SESSION="commander-${FIXTURE_REPO}-main"

# tmux_has_session <name> -> 0 (true) if a session by that name exists, 1 otherwise.
# A host with no tmux binary at all is treated as "no session" -- the suite must still run there.
tmux_has_session() {
  command -v tmux >/dev/null 2>&1 || return 1
  tmux has-session -t "$1" 2>/dev/null
}

# --- pre-flight guard: refuse to run into a known hang rather than proceeding into one --------
# On 2026-08-23 a leftover session of this exact fixed name hung the suite at case 8 for >70s.
# Fail loudly and immediately instead.
if tmux_has_session "$FIXTURE_SESSION"; then
  echo "FATAL: a tmux session named '$FIXTURE_SESSION' already exists -- a previous run of this" >&2
  echo "suite did not clean up. Kill it before re-running: tmux kill-session -t '$FIXTURE_SESSION'" >&2
  exit 1
fi

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
if [ -z "$BRAIN_ROOT_REAL" ] || [ ! -f "$BRAIN_ROOT_REAL/scripts/sync/commit_routine_updates.sh" ]; then
  echo "FATAL: could not locate the real brain scripts (commit_routine_updates.sh) by walking up from $REPO_ROOT" >&2
  exit 1
fi

# ==============================================================================================
# Cases 1-3: commit scope, via the REAL commit_routine_updates.sh with git shimmed.
# ==============================================================================================

setup_commit_case() { # setup_commit_case <case-dir> -> prints "<brain>" (the scratch brain root)
  local case_dir="$1"
  # lib.sh resolves HQ_ROOT by climbing two levels from its own location (it lives in
  # scripts/sync/ in the real repo, not scripts/) — this fake tree must mirror that exact
  # depth, or HQ_ROOT/LOG_DIR resolve outside "$case_dir/brain" entirely and every assertion
  # below silently sees the wrong (or a nonexistent) .emit_wrote/logs path.
  mkdir -p "$case_dir/brain/scripts/sync" "$case_dir/brain/logs" "$case_dir/bin"
  cp "$BRAIN_ROOT_REAL/scripts/sync/lib.sh" "$case_dir/brain/scripts/sync/lib.sh"
  cp "$BRAIN_ROOT_REAL/scripts/sync/commit_routine_updates.sh" "$case_dir/brain/scripts/sync/commit_routine_updates.sh"
  chmod +x "$case_dir/brain/scripts/sync/commit_routine_updates.sh"
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
    bash scripts/sync/commit_routine_updates.sh >/dev/null 2>&1 )
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
    bash scripts/sync/commit_routine_updates.sh >/dev/null 2>&1 )

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
    bash scripts/sync/commit_routine_updates.sh >/dev/null 2>&1 )

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
mkdir -p "$CASE5/brain/$FIXTURE_REPO/scripts" "$CASE5/brain/$FIXTURE_REPO/.claude/commands" "$CASE5/brain/scripts/sync" "$CASE5/bin"
touch "$CASE5/brain/brain.toml"
cp "$BRAIN_ROOT_REAL/scripts/sync/lib.sh" "$CASE5/brain/scripts/sync/lib.sh"
cp "$REPO_ROOT/scripts/commander_drain.sh" "$CASE5/brain/$FIXTURE_REPO/scripts/commander_drain.sh"
cp "$REPO_ROOT/.claude/commands/orchestration-commander.md" \
   "$CASE5/brain/$FIXTURE_REPO/.claude/commands/orchestration-commander.md"
chmod +x "$CASE5/brain/$FIXTURE_REPO/scripts/commander_drain.sh"

# lib.sh (sourced by commander_drain.sh) unconditionally re-exports PATH as
# "$HOME/.cargo/bin:...:$PATH" -- putting the REAL installed `bastion` (this machine's
# ~/.cargo/bin/bastion) ahead of any shim dir we merely prepend beforehand. Give this
# subshell its own fake HOME instead, with the shim at ~/.cargo/bin/bastion, so lib.sh's
# own PATH re-export resolves to our shim first without touching the real ~/.cargo/bin or
# launching the real `bastion ask` (which would open a real tmux session).
FAKE_HOME="$CASE5/fake_home"
mkdir -p "$FAKE_HOME/.cargo/bin"

HEARTBEAT_DIR="$CASE5/brain/.fleet-locks/commander-heartbeats"
HEARTBEAT_FILE="$HEARTBEAT_DIR/${FIXTURE_REPO}-main.heartbeat"
mkdir -p "$HEARTBEAT_DIR"

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
  # BT.8.A task 3: ONE heartbeat writer. In a real turn, step 6 (inside the Claude session
  # bastion ask launches) stamps the heartbeat itself -- this shim stands in for that step so
  # the case below still proves a successful drain ends up with a heartbeat, without the
  # WRAPPER being the one that writes it (see the sequence case further down, which asserts the
  # wrapper itself never overwrites what a completed turn already wrote).
  date -u +%s > "$HEARTBEAT_FILE"
  exit 0
fi
exit 0
SH
chmod +x "$FAKE_HOME/.cargo/bin/bastion"

DRAIN_LOG_OUT="$CASE5/drain_stdout.log"
( cd "$CASE5/brain/$FIXTURE_REPO" && HOME="$FAKE_HOME" PATH="$FAKE_HOME/.cargo/bin:$PATH" \
    bash scripts/commander_drain.sh --repo "$FIXTURE_REPO" --lane main > "$DRAIN_LOG_OUT" 2>&1 )
CASE5_EXIT=$?

r=0
[ "$CASE5_EXIT" -eq 0 ] || r=1
[ -f "$HEARTBEAT_FILE" ] || r=1
grep -qi "empty" "$DRAIN_LOG_OUT" || r=1
check "empty inbox: drain exits 0, ends up with a heartbeat, and logs that it was empty" "$r"

# ==============================================================================================
# Case: ONE HEARTBEAT WRITER (BT.8.A task 3) -- the drain no longer overwrites the heartbeat the
# registry step (the turn's own step 6) already wrote. Sequence: pre-stamp the heartbeat file
# with a known sentinel epoch (as if a turn's step 6 had already written it), then run the
# wrapper with `bastion ask` shimmed to succeed WITHOUT touching the heartbeat file itself --
# isolating exactly what changed in commander_drain.sh from what a real turn does internally.
# Assert the heartbeat on disk afterward is still the sentinel, unchanged.
# ==============================================================================================

CASE_SEQ="$WORK/case_sequence"
mkdir -p "$CASE_SEQ/brain/$FIXTURE_REPO/scripts" "$CASE_SEQ/brain/$FIXTURE_REPO/.claude/commands" "$CASE_SEQ/brain/scripts/sync" "$CASE_SEQ/bin"
touch "$CASE_SEQ/brain/brain.toml"
cp "$BRAIN_ROOT_REAL/scripts/sync/lib.sh" "$CASE_SEQ/brain/scripts/sync/lib.sh"
cp "$REPO_ROOT/scripts/commander_drain.sh" "$CASE_SEQ/brain/$FIXTURE_REPO/scripts/commander_drain.sh"
cp "$REPO_ROOT/.claude/commands/orchestration-commander.md" \
   "$CASE_SEQ/brain/$FIXTURE_REPO/.claude/commands/orchestration-commander.md"
chmod +x "$CASE_SEQ/brain/$FIXTURE_REPO/scripts/commander_drain.sh"

SEQ_HEARTBEAT_DIR="$CASE_SEQ/brain/.fleet-locks/commander-heartbeats"
SEQ_HEARTBEAT_FILE="$SEQ_HEARTBEAT_DIR/${FIXTURE_REPO}-main.heartbeat"
mkdir -p "$SEQ_HEARTBEAT_DIR"

# "the registry step" -- a FRESH (within-threshold) but deliberately offset epoch, so this
# case never crosses the staleness-alert path (send_alert requires alerting env vars this
# suite does not set, and exercising that path is not what this case is about) while still
# being trivially distinguishable from an accidental overwrite (which would land within a
# second or two of "now", not ~2 minutes behind it).
REGISTRY_EPOCH="$(( $(date -u +%s) - 120 ))"
printf '%s' "$REGISTRY_EPOCH" > "$SEQ_HEARTBEAT_FILE"

SEQ_FAKE_HOME="$CASE_SEQ/fake_home"
mkdir -p "$SEQ_FAKE_HOME/.cargo/bin"
cat > "$SEQ_FAKE_HOME/.cargo/bin/bastion" <<'SH'
#!/usr/bin/env bash
if [ "$1" = "ask" ]; then
  out=""
  while [ $# -gt 0 ]; do
    if [ "$1" = "--out" ]; then out="$2"; fi
    shift
  done
  # Deliberately does NOT touch the heartbeat file -- this shim represents a successful ask
  # call whose registry write already happened (the pre-stamped sentinel above); the point of
  # this case is that commander_drain.sh itself must not touch the file on a successful exit.
  [ -n "$out" ] && echo '{"status":"ok"}' > "$out"
  exit 0
fi
exit 0
SH
chmod +x "$SEQ_FAKE_HOME/.cargo/bin/bastion"

SEQ_DRAIN_LOG_OUT="$CASE_SEQ/drain_stdout.log"
( cd "$CASE_SEQ/brain/$FIXTURE_REPO" && HOME="$SEQ_FAKE_HOME" PATH="$SEQ_FAKE_HOME/.cargo/bin:$PATH" \
    bash scripts/commander_drain.sh --repo "$FIXTURE_REPO" --lane main > "$SEQ_DRAIN_LOG_OUT" 2>&1 )
CASE_SEQ_EXIT=$?

SEQ_HEARTBEAT_AFTER="$(cat "$SEQ_HEARTBEAT_FILE" 2>/dev/null || echo "MISSING")"

r=0
[ "$CASE_SEQ_EXIT" -eq 0 ] || r=1
[ "$SEQ_HEARTBEAT_AFTER" = "$REGISTRY_EPOCH" ] || r=1
check "commander_drain.sh no longer overwrites the heartbeat the registry step already wrote" "$r"

# ==============================================================================================
# Case: heartbeat FORMAT/STALENESS -- an epoch-seconds heartbeat passes; an ISO-8601 heartbeat
# (this script's own drain_started_at format, historically also used to stamp brain-commander's
# heartbeat -- the real cross-format bug BT.6.D fixed) goes RED, naming the format, rather than
# being silently mis-parsed by bash integer arithmetic. Exercises `--check-heartbeat` directly.
# ==============================================================================================

FMT_DIR="$(mktemp -d)"

EPOCH_FILE="$FMT_DIR/epoch.heartbeat"
date -u +%s > "$EPOCH_FILE"
EPOCH_OUTPUT="$(bash "$REPO_ROOT/scripts/commander_drain.sh" --check-heartbeat "$EPOCH_FILE" 5400)"
EPOCH_EXIT=$?

r=0
[ "$EPOCH_EXIT" -eq 0 ] || r=1
printf '%s' "$EPOCH_OUTPUT" | grep -qi "FRESH" || r=1
check "epoch-seconds heartbeat passes the staleness check" "$r"

ISO_FILE="$FMT_DIR/iso.heartbeat"
date -u +%Y-%m-%dT%H:%M:%SZ > "$ISO_FILE"
ISO_OUTPUT="$(bash "$REPO_ROOT/scripts/commander_drain.sh" --check-heartbeat "$ISO_FILE" 5400)"
ISO_EXIT=$?

r=0
[ "$ISO_EXIT" -eq 2 ] || r=1
printf '%s' "$ISO_OUTPUT" | grep -qi "RED" || r=1
printf '%s' "$ISO_OUTPUT" | grep -qi "epoch" || r=1
check "ISO-8601 heartbeat goes RED, naming that it is not epoch seconds" "$r"

rm -rf "$FMT_DIR"

# ==============================================================================================
# Cases 6-12: BT.ticket.commander-prompt-must-read-the-board — the command file must instruct
# the drain to read the open-work board FIRST, report a recurring finding as an instance count
# against the existing row rather than a new row, and carry a forward-looking note naming the
# eventual bail-record source. Each positive assertion is paired with a NEGATIVE FIXTURE: a copy
# of the real (fixed) command file with exactly that instruction stripped back out — i.e. the
# fix reverted in-process — so the assertion is shown capable of failing, not only of matching.
# ==============================================================================================

CMD_FILE="$REPO_ROOT/.claude/commands/orchestration-commander.md"
CMD_SCRATCH="$WORK/cmd_fixtures"
mkdir -p "$CMD_SCRATCH"

# --- assertion 1: step 1 names planning/open-work/index.md as a read, before the queue sweep ---
check_step1_reads_board() { # check_step1_reads_board <file> -> 0 if the board read precedes the sweep
  local f="$1"
  # Slice from the "### 1." header up to (not including) the queue-sweep invocation; the board
  # read must appear somewhere in that slice, i.e. before the sweep runs.
  awk '/^### 1\./{flag=1} flag{print} /check_messages\.py --quiet/{exit}' "$f" \
    | grep -q 'planning/open-work/index\.md'
}

r=0; check_step1_reads_board "$CMD_FILE" || r=1
check "step 1 names planning/open-work/index.md as a read, before the queue sweep" "$r"

# Negative fixture: strip the step-0 board-read paragraph back out (revert the fix in-process).
FIXTURE_NO_STEP0="$CMD_SCRATCH/no-step0-board-read.md"
awk '
  /^\*\*0\. Read the open-work board FIRST/ { skip=1 }
  skip && /^\*\*a\. Validate every message record/ { skip=0 }
  !skip { print }
' "$CMD_FILE" > "$FIXTURE_NO_STEP0"

r=0; check_step1_reads_board "$FIXTURE_NO_STEP0" && r=1
check "negative fixture (step-0 board read removed) fails the same assertion" "$r"

# --- assertion 2: a recurring item is reported as an instance count against the existing row ---
check_instance_count_instruction() { # 0 if the instance-count instruction is present
  grep -qF 'instance N of <row>' "$1"
}

r=0; check_instance_count_instruction "$CMD_FILE" || r=1
check "command instructs reporting a recurring item as an instance count against the existing row" "$r"

FIXTURE_NO_INSTANCE="$CMD_SCRATCH/no-instance-count.md"
grep -vF 'instance N of <row>' "$CMD_FILE" \
  | grep -v 'A recurring cause updates its existing row instead of appending a new one' \
  | grep -v 'Before filing any of the four cases below as a fresh finding' \
  > "$FIXTURE_NO_INSTANCE"

r=0; check_instance_count_instruction "$FIXTURE_NO_INSTANCE" && r=1
check "negative fixture (instance-count instruction removed) fails the same assertion" "$r"

# --- assertion 3: a forward-looking note names the bail record by block id -----------------
check_forward_looking_note() { # 0 if the note names the bail-record block id
  grep -qF 'BT.ticket.bails-must-be-append-only' "$1"
}

r=0; check_forward_looking_note "$CMD_FILE" || r=1
check "forward-looking note names BT.ticket.bails-must-be-append-only as the eventual count source" "$r"

FIXTURE_NO_NOTE="$CMD_SCRATCH/no-forward-note.md"
grep -vF 'BT.ticket.bails-must-be-append-only' "$CMD_FILE" > "$FIXTURE_NO_NOTE"

r=0; check_forward_looking_note "$FIXTURE_NO_NOTE" && r=1
check "negative fixture (forward-looking note removed) fails the same assertion" "$r"

# --- assertion 4: the quiet-pass one-line report rule is byte-unchanged ---------------------
QUIET_PASS_EXPECTED='Silence on the empty lines is the normal case for most of the ~48+ drains a day; do not pad the
report to look busy.'

check_quiet_pass_unchanged() { # 0 if the exact two-line rule is present verbatim
  local f="$1"
  local actual
  actual="$(awk '/^Silence on the empty lines/{flag=1} flag{print} flag && /report to look busy\.$/{exit}' "$f")"
  [ "$actual" = "$QUIET_PASS_EXPECTED" ]
}

r=0; check_quiet_pass_unchanged "$CMD_FILE" || r=1
check "quiet-pass one-line report rule is byte-unchanged" "$r"

# ==============================================================================================
# Case: the pre-flight guard is shown capable of FAILING (D68 discipline), by runtime inversion
# rather than a committed red case -- commander-drain-tests already gates:true, so a committed
# red case would red-gate every concurrent lane. We create a decoy tmux session under exactly
# this run's unique fixture name, observe the guard detect it, kill ONLY that decoy (a wildcard
# kill would touch a real, unrelated live session on this machine, see the safety note below),
# then observe the guard report clean again.
# ==============================================================================================

if command -v tmux >/dev/null 2>&1; then
  tmux new-session -d -s "$FIXTURE_SESSION" 2>/dev/null

  r=0; tmux_has_session "$FIXTURE_SESSION" || r=1
  check "pre-flight guard detects a decoy session under this run's fixture name" "$r"

  # SAFETY: kill ONLY the exact decoy session this run created -- never a wildcard kill verb.
  # A live tmux session on this machine (commander-bastion-test-gate) hosts a real interactive
  # agent session and must never be touched by this suite.
  tmux kill-session -t "$FIXTURE_SESSION" 2>/dev/null || true

  r=0; tmux_has_session "$FIXTURE_SESSION" && r=1
  check "guard reports clean again once the decoy is killed" "$r"
else
  echo "SKIP: no tmux binary on this host -- guard-inversion case not exercised"
fi

# --- final assertion: no tmux session matching this run's fixture survives the suite ----------
r=0; tmux_has_session "$FIXTURE_SESSION" && r=1
check "no tmux session survives the suite (fixture: $FIXTURE_SESSION)" "$r"

# footer --------------------------------------------------------------------------------------
echo
if [ "$fail" -eq 0 ]; then echo "ALL PASS ($n cases)"; else echo "FAILURES ($n cases)"; fi
exit "$fail"
