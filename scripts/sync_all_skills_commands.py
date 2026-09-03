import argparse
import os
import sys
import re
import subprocess

def find_workspace_root():
    cwd = os.getcwd()
    while cwd != os.path.dirname(cwd):
        if os.path.exists(os.path.join(cwd, "brain.toml")):
            return cwd
        cwd = os.path.dirname(cwd)
    return None

DRY_RUN = False


def run_cmd(cmd, cwd=None):
    """Run a command, honouring DRY_RUN.

    For rsync invocations --dry-run is translated into rsync's own -n, so the output is a real
    per-file report of what would transfer or be deleted rather than an echo of the command.
    For the python sub-scripts it is forwarded as --dry-run, which they implement natively.
    """
    if DRY_RUN:
        if isinstance(cmd, list):
            cmd = cmd + ["--dry-run"]
        elif cmd.startswith("rsync -av"):
            cmd = cmd.replace("rsync -av", "rsync -avn", 1)
        else:
            print(f"[dry-run] would run: {cmd}")
            return True
    print(f"Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, shell=not isinstance(cmd, list), cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error executing command: {res.stderr}")
        return False
    print(res.stdout)
    return True

def main():
    global DRY_RUN
    parser = argparse.ArgumentParser(
        description=(
            "Sync base-template's commands and skills to the global installs and every "
            "sub-brain tier."
        ),
        epilog=(
            "This script had NO argument parsing at all until 2026-09-03. Any flag - including "
            "--help - was ignored and the script ran a full fleet sync: on 2026-09-02 that "
            "produced 1,329 unreviewed insertions across base-template, HQ and five tiers, all "
            "reverted by hand. An unrecognised flag now exits 2 without touching anything."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report everything that would change; write nothing",
    )
    args = parser.parse_args()
    DRY_RUN = args.dry_run
    if DRY_RUN:
        print("=== DRY RUN — nothing will be written ===")

    root = find_workspace_root()
    if not root:
        print("ERROR: brain.toml not found. Must run from within the agentic-portfolio workspace.")
        sys.exit(1)
        
    os.chdir(root)
    print(f"Workspace root: {root}")
    
    # 1. Run local skills/commands sync script
    sync_skills_script = "base-template/.agents/skills/sync-skills/scripts/sync_skills.py"
    if os.path.exists(sync_skills_script):
        print("=== Running sync_skills.py ===")
        if not run_cmd([sys.executable, sync_skills_script]):
            sys.exit(1)
    else:
        print(f"Warning: {sync_skills_script} not found.")

    # 2. Sync global commands
    print("=== Syncing global commands (exclude brain/) ===")
    global_commands_cmd = "rsync -av --delete --exclude='brain/' base-template/.claude/commands/ ~/.claude/commands/"
    run_cmd(global_commands_cmd)

    # 3. Sync global skills
    print("=== Syncing global skills ===")
    global_skills_cmd = "rsync -av --delete base-template/.agents/skills/ ~/.gemini/config/skills/"
    run_cmd(global_skills_cmd)

    # 4. Discover sub-brain tiers from brain.toml
    tiers = set()
    with open("brain.toml", "r", encoding="utf-8") as f:
        for line in f:
            match = re.search(r'tier\s*=\s*"([^"]+)"', line)
            if match:
                t = match.group(1)
                if t != "_root" and not t.startswith("_"):
                    tiers.add(t)

    # 5. Sync brain commands & skills to sub-brain tiers
    for tier in sorted(tiers):
        if not os.path.exists(tier):
            print(f"Skipping missing tier folder: {tier}")
            continue
            
        print(f"=== Syncing brain commands for tier: {tier} ===")
        # Ensure destination folder exists
        if not DRY_RUN:
            os.makedirs(f"{tier}/.claude/commands", exist_ok=True)
        tier_commands_cmd = (
            f"rsync -av --delete "
            f"--include='archive.md' --include='capture.md' --include='commit.md' "
            f"--include='handoff.md' --include='log-work.md' --include='prime.md' "
            f"--include='session-recap.md' --include='wrap-up.md' "
            f"--include='backlog-ticket.md' --include='generate-master-plan.md' "
            f"--include='log-decision.md' --include='sync-status.md' --include='update-progress.md' "
            f"--include='update-state.md' --include='attention.md' --include='snooze.md' --include='next.md' "
            f"--exclude='*' "
            f"base-template/.claude/commands/brain/ {tier}/.claude/commands/"
        )
        run_cmd(tier_commands_cmd)

    # 6. Regenerate each tier's skills from its OWN (just-updated) commands.
    # NOTE: this deliberately does not rsync from base-template/.agents/skills/ —
    # several brain/-scoped commands (capture, backlog-ticket, handoff, update-state)
    # have a DIFFERENT flat (leaf-project) variant at base-template's top level, and
    # base-template's own generated skills are derived from that flat variant, not
    # the brain/ one. Rsyncing tier skills from there would silently swap a tier's
    # skill content for the wrong (leaf-project) variant. Re-running sync_skills.py
    # here regenerates each tier's skills directly from the brain-scoped commands
    # that were just synced into that tier's own .claude/commands/ above.
    print("=== Regenerating tier skills from tier commands ===")
    if not run_cmd([sys.executable, sync_skills_script]):
        sys.exit(1)

    if DRY_RUN:
        print("\nDry run complete. Nothing was written.")
    else:
        print("\nAll syncs completed successfully!")

if __name__ == "__main__":
    main()
