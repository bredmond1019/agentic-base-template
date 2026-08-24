#!/usr/bin/env bash
#
# test_drain_log.sh — asserts .claude/commands/orchestration-commander.md's step 6 names
# scripts/drain_log.py (BT.ticket.commander-never-calls-the-drain-log).
#
# drain_log.py itself is not owned by this repo (it lives in the brain repo, gated by HQ's own
# drain-log-tests) — this suite tests exactly one thing base-template DOES own: whether the
# command file this repo ships actually calls the writer. A command file that stops naming
# scripts/drain_log.py is a silent regression back to the unrecorded-drain state the ticket
# fixed, so this is a wiring assertion, not a behavior test of the writer.
#
# Two independent fixtures make the check trustworthy rather than merely present:
#   - a synthetic POSITIVE fixture (mentions the writer) must PASS the check
#   - a synthetic NEGATIVE fixture (same shape, mention stripped) must FAIL the check
# Those two prove the check can actually distinguish present from absent, independent of
# whatever state the real command file happens to be in today. The real command file is then
# checked against the same function — BEFORE step 2 of this ticket lands, it is expected to
# read as absent (RED); this run records that.
#
#   ./scripts/test_drain_log.sh
#
# Exit status 0 = all cases pass; non-zero = at least one failure (including the expected-red
# real-file case before task 2 lands).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMAND_FILE="$REPO_ROOT/.claude/commands/orchestration-commander.md"

fail=0
n=0
check() { # check <description> <result: 0=pass>
  n=$((n + 1))
  if [ "$2" -eq 0 ]; then printf 'PASS (%d): %s\n' "$n" "$1"
  else printf 'FAIL (%d): %s\n' "$n" "$1"; fail=1; fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- the check under test --------------------------------------------------------------------
# Names the writer by its repo-relative path, the same form the ticket's acceptance criteria
# require in the real command file's step 6 — a bare "drain_log" mention (e.g. in this test's
# own filename) does not satisfy it.
names_drain_log() { # names_drain_log <file> -> 0 if it names scripts/drain_log.py, 1 otherwise
  grep -q 'scripts/drain_log\.py' "$1"
}

# --- fixtures ----------------------------------------------------------------------------------

POSITIVE_FIXTURE="$WORK/positive-orchestration-commander.md"
cat > "$POSITIVE_FIXTURE" <<'EOF'
### 6. Stamp the heartbeat
Write the last-drain heartbeat file, unconditionally. Also append this drain's record by running:
python3 scripts/drain_log.py record --roadmap "$ROADMAP" --drained "$DRAINED" --routed "$ROUTED" --completed "$COMPLETED"
EOF

NEGATIVE_FIXTURE="$WORK/negative-orchestration-commander.md"
sed '/drain_log\.py/d' "$POSITIVE_FIXTURE" > "$NEGATIVE_FIXTURE"

# --- Case 1: positive fixture (mentions the writer) passes the check ------------------------
names_drain_log "$POSITIVE_FIXTURE"
check "synthetic fixture naming scripts/drain_log.py passes the wiring check" "$?"

# --- Case 2: negative fixture (mention stripped) fails the check, proving the check can
# distinguish present from absent rather than always passing ---------------------------------
names_drain_log "$NEGATIVE_FIXTURE"
NEG_RC=$?
if [ "$NEG_RC" -ne 0 ]; then R=0; else R=1; fi
check "negative fixture with the mention removed fails the wiring check (present vs absent distinguished)" "$R"

# --- Case 3: the real command file names the writer -------------------------------------------
# Expected RED until step 6 is wired (task 2 of this ticket) -- this run records that failure,
# it does not paper over it.
names_drain_log "$COMMAND_FILE"
check "orchestration-commander.md step 6 names scripts/drain_log.py" "$?"

echo
if [ "$fail" -eq 0 ]; then
  echo "ALL PASS ($n cases)"
else
  echo "FAILURES ($n cases run)"
fi
exit "$fail"
