#!/usr/bin/env bash
#
# commander_drain.sh — wakes one orchestration-commander drain (BT.6.D).
#
# Composes a prompt file from .claude/commands/orchestration-commander.md plus the current
# on-disk situation, then hands it to `bastion ask` for a single Claude Code turn against a
# persistent tmux session. The turn itself does the six drain steps (see that command file);
# this wrapper's only job is to wake it correctly, with a wait budget long enough to survive a
# corpus-wide emit-state run, and to prove — via the heartbeat file — that drains are still
# happening at all.
#
# Usage:
#   ./scripts/commander_drain.sh [--repo NAME] [--lane NAME]
#
# `--repo`/`--lane` default to this repo's own basename and "main" respectively — override
# when driving a commander for a different lane's queue (see check_messages.py's
# `<lock_dir>/queue/<repo>/<lane>/` layout, which this wrapper mirrors for the inbox count
# below).
#
# The `timeout`(1) command does NOT exist on this macOS shell (base-template CLAUDE.md standing
# rule 10 / the base-template CLAUDE.md "Traps" list) — this script never calls it. The only
# wait budget enforced here is `bastion ask`'s own `--timeout` flag, applied by the binary
# itself.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- resolve <brain_root> by walking up for brain.toml --------------------------------------
# scripts/emit_state_write.sh, scripts/lib.sh and scripts/commit_routine_updates.sh (which the
# commander's step 3 calls) live in the BRAIN repo, not here — never assume a repo-relative
# path to them. This mirrors scripts/check_lane_agents.py's find_brain_root() /
# scripts/check_messages.py's identical precedence, so every mechanism in the fleet that needs
# "where is the brain root" agrees on the same answer without hardcoding another's path. A
# plain "cd .." count would also break the moment this script runs from a worktree nested one
# level deeper (base-template/trees/<name>/scripts/), which is exactly where a worktree-run
# commander drain executes from.
find_brain_root() {
    local dir="$1"
    while [ "$dir" != "/" ]; do
        if [ -f "$dir/brain.toml" ]; then
            printf '%s\n' "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    return 1
}

BRAIN_ROOT="$(find_brain_root "$REPO_ROOT")" || {
    echo "FATAL: no brain.toml found walking up from $REPO_ROOT — cannot locate the brain repo" >&2
    exit 1
}

# shellcheck source=/dev/null
source "$BRAIN_ROOT/scripts/lib.sh"   # gives us send_alert(), LOG_DIR, colors.

# --- args -------------------------------------------------------------------------------------

REPO_NAME="$(basename "$REPO_ROOT")"
LANE="main"

while [ $# -gt 0 ]; do
    case "$1" in
        --repo) REPO_NAME="$2"; shift 2 ;;
        --lane) LANE="$2"; shift 2 ;;
        *) echo "FATAL: unrecognized argument '$1'" >&2; exit 1 ;;
    esac
done

DRAIN_LOG="$LOG_DIR/commander_drain_${REPO_NAME}_$(date +%Y%m%d_%H%M%S).log"

log() { echo -e "$1" | tee -a "$DRAIN_LOG"; }

log "${BLUE}commander_drain.sh — repo=${REPO_NAME} lane=${LANE} brain_root=${BRAIN_ROOT}${NC}"

# --- heartbeat: check staleness of the PREVIOUS drain before we stamp a new one -------------
# One file per (repo, lane) under the brain's shared advisory-lock directory — the same root
# check_lane_agents.py's registry/lease records live under — so every commander's heartbeat is
# discoverable in one place without this repo owning a second layout. A missing or stale
# heartbeat is the signal that drains have stopped happening (cron not firing, `bastion ask`
# wedged, etc.) — see the command file's step 6.
HEARTBEAT_DIR="$BRAIN_ROOT/.fleet-locks/commander-heartbeats"
mkdir -p "$HEARTBEAT_DIR"
HEARTBEAT_FILE="$HEARTBEAT_DIR/${REPO_NAME}-${LANE}.heartbeat"

# Same threshold check_lane_agents.py uses for lease/registry staleness (90 minutes) — one
# number for "how long is too long" across the fleet's advisory mechanisms, per that script's
# own comment on STALE_THRESHOLD_SECONDS. A commander's own cadence is a 20-30 minute heartbeat
# plus kind-triggered wakes, so 90 minutes clears a normal gap with margin.
HEARTBEAT_STALE_SECS=$((90 * 60))

if [ -f "$HEARTBEAT_FILE" ]; then
    PREV_EPOCH="$(cat "$HEARTBEAT_FILE" 2>/dev/null || echo 0)"
    NOW_EPOCH="$(date -u +%s)"
    AGE=$((NOW_EPOCH - PREV_EPOCH))
    if [ "$AGE" -gt "$HEARTBEAT_STALE_SECS" ]; then
        send_alert "commander_drain.sh: previous drain heartbeat for ${REPO_NAME}/${LANE} is ${AGE}s old (threshold ${HEARTBEAT_STALE_SECS}s) — drains may have stopped happening." \
            "$DRAIN_LOG" "🚨 Commander drain heartbeat stale (${REPO_NAME}/${LANE})"
    fi
else
    log "No prior heartbeat for ${REPO_NAME}/${LANE} — first drain, or heartbeat file was never written."
fi

# --- inbox count, for the log only — the drain turn itself (step 1) is what actually acts ---
# on it via check_messages.py's drain_queue(). An empty inbox is a normal, clean outcome, not
# an error: we still run the full drain below (steps 3-6 do not depend on the inbox having had
# anything in it), we just say so in the log rather than treating it as a special case.
LOCK_DIR="${FLEET_LOCK_DIR:-$BRAIN_ROOT/.fleet-locks}"
INBOX_DIR="$LOCK_DIR/queue/${REPO_NAME}/${LANE}/inbox"
if [ -d "$INBOX_DIR" ]; then
    INBOX_COUNT="$(find "$INBOX_DIR" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
else
    INBOX_COUNT=0
fi
if [ "$INBOX_COUNT" -eq 0 ]; then
    log "Inbox for ${REPO_NAME}/${LANE} is empty — normal, clean outcome; draining anyway to re-derive and report."
else
    log "Inbox for ${REPO_NAME}/${LANE} has ${INBOX_COUNT} message(s) to drain."
fi

# --- compose the prompt file ------------------------------------------------------------------

PROMPT_FILE="$LOG_DIR/commander_drain_prompt_${REPO_NAME}_$(date +%Y%m%d_%H%M%S).md"
{
    cat "$REPO_ROOT/.claude/commands/orchestration-commander.md"
    echo
    echo "---"
    echo
    echo "## This drain's situation"
    echo
    echo "- repo: ${REPO_NAME}"
    echo "- lane: ${LANE}"
    echo "- repo_root: ${REPO_ROOT}"
    echo "- brain_root: ${BRAIN_ROOT}"
    echo "- lock_dir: ${LOCK_DIR}"
    echo "- inbox_count (informational, re-check on your own — this may be stale by the time you run): ${INBOX_COUNT}"
    echo "- drain_started_at (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "- heartbeat_file_to_stamp: ${HEARTBEAT_FILE} (write the current UTC epoch seconds, unconditionally, as step 6)"
} > "$PROMPT_FILE"

# --- invoke bastion ask -------------------------------------------------------------------------

SESSION="commander-${REPO_NAME}-${LANE}"
OUT_FILE="$LOG_DIR/commander_drain_out_${REPO_NAME}_$(date +%Y%m%d_%H%M%S).json"

# DRAIN_TIMEOUT_SECS is explicit and NOT `bastion ask`'s 180s default (core/bastion/src/main.rs).
# A drain that runs emit-state over the whole corpus (scripts/emit_state_write.sh, step 3) can
# run well past 180s; a silently expired budget would look exactly like a commander that did nothing.
# Overridable via env for a slower or faster host.
DRAIN_TIMEOUT_SECS="${COMMANDER_DRAIN_TIMEOUT_SECS:-900}"

# MODEL SELECTION — settled at the block-record level (BT.6.D notes), do not re-litigate here:
# Sonnet by default, via bastion ask's --launch-cmd knob. The dangerous operation (the commit)
# is deliberately judgement-free (exactly the I_EMIT_WROTE manifest, never a "does this look
# derived" call), BT.6.C rule 1 already caps the blast radius of a wrong routing call, and this
# drain runs ~48+ times a day, most near-empty — a stronger model buys no safety here and costs
# real money at that frequency.
#
# ESCALATION HOOK — deliberately NOT built in this task. A future revision of this wrapper could
# read the `kind` of each file already sitting in `${INBOX_DIR}` before invoking `bastion ask`
# and pick the model deterministically, without an agent deciding: escalate to Opus only when
# the drain carries a FINDING needing D43 priority/ownership routing, or an abandoned-lane
# recovery call (case 2 in the command file's step 4); Sonnet otherwise. Left unbuilt per the
# block record: start Sonnet everywhere and let the queue measure whether it is ever wrong.
LAUNCH_CMD="${COMMANDER_LAUNCH_CMD:-claude --model sonnet --permission-mode bypassPermissions}"

log "Invoking bastion ask: session=${SESSION} timeout=${DRAIN_TIMEOUT_SECS}s launch_cmd='${LAUNCH_CMD}'"

set +e
bastion ask \
    --session "$SESSION" \
    --prompt-file "$PROMPT_FILE" \
    --out "$OUT_FILE" \
    --dir "$REPO_ROOT" \
    --timeout "$DRAIN_TIMEOUT_SECS" \
    --launch-cmd "$LAUNCH_CMD" \
    >> "$DRAIN_LOG" 2>&1
ASK_EXIT=$?
set -e

if [ "$ASK_EXIT" -ne 0 ]; then
    log "${RED}bastion ask exited ${ASK_EXIT} for ${REPO_NAME}/${LANE}${NC}"
    send_alert "commander_drain.sh: bastion ask failed (exit ${ASK_EXIT}) for ${REPO_NAME}/${LANE} — see ${DRAIN_LOG}" \
        "$DRAIN_LOG" "🚨 Commander drain failed (${REPO_NAME}/${LANE})"
    # Still stamp the heartbeat below — the drain attempt happened even though it failed, and a
    # missing heartbeat on top of a failed drain would hide the failure behind a second, less
    # specific alarm (staleness) on the NEXT run instead of the specific one on this run.
fi

# --- stamp the heartbeat, unconditionally ------------------------------------------------------
# Even a drain that did nothing (empty inbox, nothing dirty, no orphans) or one whose turn
# failed still proves an attempt happened — a missing/stale heartbeat is itself the signal that
# drains have stopped, per the command file's step 6.
date -u +%s > "$HEARTBEAT_FILE"
log "Heartbeat stamped: ${HEARTBEAT_FILE}"

log "${GREEN}commander_drain.sh done for ${REPO_NAME}/${LANE} (bastion ask exit ${ASK_EXIT}).${NC}"

exit "$ASK_EXIT"
