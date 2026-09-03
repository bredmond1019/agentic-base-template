import argparse
import filecmp
import os
import shutil
import re

# Custom descriptions for new skills if frontmatter is missing or not extracted
NEW_SKILLS_DESCRIPTIONS = {
    "capture": "Scaffold a pre-plan notes file and add a backlog pointer",
    "conditional_docs": "Task-type documentation router",
    "patch": "Lightweight hotfix pipeline",
    "sync-global-commands": "Install harness commands into ~/.claude/commands/",
    "sdlc-flow": "Run a spec sequentially in one shared worktree with a per-task test→fix loop, one end review, a docs patch, and a PR",
    "apply": "Tailor the résumé + cover letter to a specific job posting",
    "generate-master-plan": "Superseded by /plan --founding (D65) — master-plan.md is now generated from the block graph, not hand-authored. This skill only explains the redirect; use /plan --founding to actually author an initiative.",
    "handoff": "Write handoff + log work + commit; hands off to a fresh session",
    "session-recap": "Briefing: recent Log entries, where you left off, next step",
    "next": "Show what's up next, what's blocked and by what, and recommend the next action based on company and sub-brain goals",
    "sync-brain-commands": "Reads brain.toml to discover sub-brain tiers and rsyncs base-template brain/ session/planning/projects commands into each tier's .claude/commands/",
    "wrap-up": "Log work + commit; clean close without a handoff file",
    "archive": "Retire a folder or file into planning/archive/, distilling its durable residue into knowledge.md/memory.md/decisions/ first. Use when a planning directory or file is finished and ready to leave the live corpus — never delete without archiving through this.",
    "assess": "Fan out recon agents over an existing codebase to produce one dated, cited, independently re-checked assessment.md — evidence only, no plan. Use as stage 1 of the pre-plan pipeline (assess -> seams -> sequence -> plan) before planning work on a system large enough that the cut isn't obvious.",
    "backlog-ticket": "Capture a queued idea, improvement, or research thread into the HQ backlog with a repo, type, and status tag. Use to park work that isn't ready to become a real plan yet, without losing it to prose.",
    "blocked": "Record a newly discovered blocker on a block or track by appending a depends_on entry (external or block-type) to planning/state.json and regenerating derived state. Use the moment you discover a block is blocked by something new, so the graph reflects it instead of a stray note.",
    "breakdown": "Decompose a block's spec into a granular, execution-precise breakdown naming exact file paths, function/class names, and what to write — a reading aid for the implementer, not something the SDLC engines execute. Use before implementing a block whose tasks.json steps are too coarse to act on without interpretation.",
    "chore": "Plan a maintenance or housekeeping task with no behavior change, producing a block record + task list for lean /sdlc-task. Use for cleanup/refactor work where tests are incidental rather than required — for behavior changes use /ticket instead.",
    "clean-worktree": "Merge a completed SDLC worktree branch into main and remove the worktree. Use after /sdlc-task or /sdlc-flow finishes work in an isolated worktree and it's ready to land.",
    "close-out": "Run the full test suite, fill coverage gaps, patch stale docs, then produce a clean handoff — the quality-closing loop after an implementation session. Use after /sdlc-run, /sdlc-flow, or any implementation session before handing work off.",
    "commit": "Stage and commit changes with a conventional commit message, splitting code and docs/planning changes into separate commits and confirming with the user before committing. Use for an ordinary git commit in this repo instead of hand-running git commands.",
    "define-design-system": "For a UI that does not exist yet, produce the design tokens, theme config, component inventory, icon set, and consistency rules a new product is built from, then prove it on one real screen. Use when starting a new client/side/app UI from scratch — if the product already has a discernible system in use, use /define-polish-standard instead.",
    "define-polish-standard": "Write a falsifiable polish-standard.md describing what 'good' looks like for a specific existing product, precise enough that two reviewers shown the same screenshot agree. Use before a UI review, a ticket's acceptance criteria, or a reviewer's checklist needs an objective bar to judge against.",
    "generate-tasks": "Decompose a block definition (from master-plan.md or a standalone plan file) into planning/<BlockID>/tasks.json — the task list the SDLC engines actually execute. Use after a block record exists and before running /sdlc-task or /sdlc-flow against it.",
    "init-worktree": "Create an isolated git worktree at trees/<spec-slug>[-taskN]/ for an SDLC spec or task, checked out on its own branch. Use when a spec or task needs isolated execution rather than running in place on the main branch.",
    "initial-research": "Conduct deep reconnaissance on a topic — code, docs, and architectural decisions — and report back with file paths, signatures, snippets, and rationale detailed enough for another agent to dig in without re-investigating. Use before planning or implementing something whose context isn't already understood; pass --capture to save it as a pre-plan notes file.",
    "log-work": "Append a Log entry, sync status.md, and regenerate the freshness spine via mev emit-state — the standard end-of-session bookkeeping step. Use whenever completed work needs to be recorded and the repo's derived state kept current.",
    "orchestrate": "Drive an ordered chain of blocks end-to-end through the SDLC engines in one session — spec, breakdown, engine run, integrate, verify state, advance — running engines as background workflows so later blocks' specs prepare while earlier ones build. Use to run a lane-file or an inline list of block IDs through the pipeline without babysitting each one by hand.",
    "plan": "Author one initiative in one repo: the narrative (goal, sequencing rationale, cut list) plus a block record per member block, without decomposing tasks yet. Use for multi-block work confined to a single repo — for a multi-repo program use /generate-roadmap, for one block use /ticket or /chore.",
    "prime": "Deeply orient to the current project at session start: read the key docs, check for an active handoff, run the brain freshness gate, and load warm memory by budget. Use for the first session in a repo, returning after a long gap, or when /session-recap's summary isn't enough — not for routine session starts.",
    "review-PR": "Check out a branch-train PR, run the project's gating suite and emoji gate, review the diff against the block's acceptance criteria, and post a structured verdict via gh pr review. Use to review a PR produced by /sdlc-block (or any spec-based block) against its spec before merging.",
    "seams": "Classify every capability the planned work depends on as built/half-built/absent, map where new work attaches to the existing system, and name what breaks if the attachment is wrong. Use as stage 2 of the pre-plan pipeline (assess -> seams -> sequence -> plan) after an assessment exists and before cutting a sequence.",
    "sequence": "Cut a verified seam map into an ordered set of candidate blocks, each with an owning repo and each shipping something usable on its own, sequenced by dependency. Use as stage 3 of the pre-plan pipeline (assess -> seams -> sequence -> plan) — its sequence.md is the only input /plan or /generate-roadmap needs.",
    "start-block": "Mark a block as in-progress in status.md and flip its status in state.json, after checking that any preceding blocks are already Done. Use when beginning work on a specific block to keep status.md and the state graph in sync.",
    "sync-brain-skills": "Discover sub-brain tiers from brain.toml and rsync base-template's shared generic session/planning skills into each tier's .agents/skills/. Use after updating base-template's own .agents/skills/ to propagate the change to every sub-brain tier.",
    "sync-global-skills": "Install all harness skills from .agents/skills/ into ~/.gemini/config/skills/, mirroring what /sync-global-commands does for Claude Code. Use after adding or changing a skill in .agents/skills/ so vendor-neutral agent tools (e.g. Gemini) pick it up globally.",
    "ticket": "Plan a small, well-scoped behavior-change with observable acceptance criteria, producing a block record plus a task list feeding directly into lean /sdlc-task. Use for a bug fix or targeted enhancement that requires new or modified tests — for non-behavior-changing maintenance use /chore instead.",
    "update-docs": "Audit the documentation set against the current codebase and recent git history, producing a gap report of stale/missing/confirmed-current sections, with --patch to fix stale sections and create missing docs. Use for periodic doc health checks or bootstrapping outside the SDLC pipeline — inside the pipeline use /document instead.",
    "update-state": "The canonical workflow for safely hand-editing a repo's planning/state.json — the authoritative work-block dependency graph — covering the authored-vs-derived field split and the schema rules. Use before any non-trivial state.json edit: adding/closing a block, appending carryover, promoting a backlog item, or fixing a validator warning.",
    "update-task": "Mark a task-spec step done and/or append a note to a spec's Amendment Log (planning/<spec-slug>/amendments.md), auto-detecting the current spec from status.md if not given. Use to record progress or a deviation mid-task without editing tasks.md/tasks.json directly.",
}

SDLC_FLOW_GUIDE = """
## Antigravity Execution Guide

When the user asks you to run `/sdlc-flow <spec-slug> [range]`, do NOT run `sdlc-flow.js`. Instead, perform the flow execution yourself:

1. **Worktree Setup**:
   - Create (or re-attach) the one shared worktree at `trees/<spec-slug>-flow` and checkout branch `sdlc-flow/<spec-slug>`.
2. **Execute Tasks sequentially in the worktree**:
   - For each task in the specified range (or all if not specified):
     - Run `/update-task` to flip status to `In progress` in the worklog and local files.
     - Implement the task following instructions.
     - Run fast validation tests.
     - Fix failures (up to 3 triage/fix attempts).
     - Commit the task state on the branch (`feat: implement <slug> task N`).
3. **Consolidated End-Review**:
   - Once all tasks are complete, run the full validation/test suite.
   - Run the acceptance criteria check.
   - If PASS -> proceed to docs. If FAIL/PARTIAL -> run targeted fix loop.
4. **Docs & Wrap-up**:
   - If PASS, run `/update-docs --patch` to update documentation.
   - Update the status and log.
   - Create a pull request (PR) using git CLI or GitHub CLI (unless `--no-pr` is specified).
"""


# Set by main() from --dry-run. When true, nothing is written or deleted; every would-be change is
# reported instead. This exists because the script's only "inspect" mode used to be running it:
# invoking it with an unrecognised flag (e.g. --help) silently ran a full fleet sync, which on
# 2026-09-02 produced 1,329 unreviewed insertions across base-template, HQ and five tiers.
DRY_RUN = False
_CHANGES = []


def _write_text(path, content):
    """Write `content` to `path` unless DRY_RUN, reporting whether it is a real change."""
    existing = None
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
    if existing == content:
        return False
    _CHANGES.append(("create" if existing is None else "modify", path))
    if DRY_RUN:
        print(f"  [dry-run] would {'create' if existing is None else 'modify'}: {path}")
        return True
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True



def _dirs_match(a, b):
    """True if two skill folders hold the same file names and byte-identical contents."""
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    match, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(_dirs_match(os.path.join(a, d), os.path.join(b, d)) for d in cmp.common_dirs)

def _makedirs(path):
    if DRY_RUN:
        return
    os.makedirs(path, exist_ok=True)

def extract_js_header(filepath):
    header_lines = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("//"):
                header_lines.append(line[2:].rstrip())
            else:
                break
    # Strip leading/trailing blank lines in the extracted comment block
    content = "\n".join(header_lines).strip()
    return content

def parse_frontmatter(content):
    lines = content.strip().split("\n")
    frontmatter = {}
    body = content
    if len(lines) > 0 and lines[0].strip() == "---":
        end_idx = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break
        if end_idx != -1:
            fm_text = "\n".join(lines[1:end_idx])
            body = "\n".join(lines[end_idx + 1:]).strip()
            # Simple YAML parser supporting multiline indented values
            current_key = None
            current_value_lines = []
            for line in fm_text.split("\n"):
                if not line.strip():
                    continue
                if line.startswith(" ") or line.startswith("\t"):
                    if current_key:
                        current_value_lines.append(line.strip())
                elif ":" in line:
                    if current_key:
                        frontmatter[current_key] = " ".join(current_value_lines).strip()
                    k, v = line.split(":", 1)
                    current_key = k.strip()
                    val = v.strip().strip("'\"")
                    if val == ">" or val == "|":
                        current_value_lines = []
                    else:
                        current_value_lines = [val]
            if current_key:
                frontmatter[current_key] = " ".join(current_value_lines).strip()
    return frontmatter, body

def get_skill_frontmatter(skill_name, existing_skill_path, command_filepath=None):
    name = skill_name
    description = NEW_SKILLS_DESCRIPTIONS.get(skill_name, f"Custom skill: {skill_name}")
    
    # 1. Try to read existing skill frontmatter
    has_valid_desc = False
    if os.path.exists(existing_skill_path):
        with open(existing_skill_path, "r", encoding="utf-8") as f:
            existing_content = f.read()
        fm, _ = parse_frontmatter(existing_content)
        if "name" in fm:
            name = fm["name"]
        if "description" in fm and fm["description"].strip() not in ("", ">", "|"):
            description = fm["description"]
            has_valid_desc = True
            
    # 2. Try to read command frontmatter if description is generic or missing
    if not has_valid_desc and command_filepath and os.path.exists(command_filepath):
        with open(command_filepath, "r", encoding="utf-8") as f:
            cmd_content = f.read()
        fm, _ = parse_frontmatter(cmd_content)
        if "description" in fm and fm["description"].strip() not in ("", ">", "|"):
            description = fm["description"]
        elif "title" in fm:
            description = fm["title"]
            
    # Build YAML frontmatter string
    return f"---\nname: {name}\ndescription: >\n  {description}\n---\n\n"

def sync_command_skills(skills_dir, commands_dir):
    print(f"Syncing command skills from {commands_dir} to {skills_dir}...")
    _makedirs(skills_dir)
        
    for filename in os.listdir(commands_dir):
        if not filename.endswith(".md") or filename == "README.md" or filename == "e2e-templates-README.md" or filename.startswith("test_"):
            continue
            
        skill_name = filename[:-3]
        command_path = os.path.join(commands_dir, filename)
        skill_folder = os.path.join(skills_dir, skill_name)
        skill_file = os.path.join(skill_folder, "SKILL.md")
        
        if not os.path.exists(skill_folder):
            _makedirs(skill_folder)
            print(f"  {'[dry-run] would create' if DRY_RUN else 'Created'} skill folder: {skill_name}")
            
        frontmatter = get_skill_frontmatter(skill_name, skill_file, command_path)
        
        with open(command_path, "r", encoding="utf-8") as f:
            command_content = f.read()
            
        # Strip frontmatter from command file if present
        _, body = parse_frontmatter(command_content)
        
        if _write_text(skill_file, frontmatter + body + "\n") and not DRY_RUN:
            print(f"  Updated skill: {skill_name}")

def sync_workflow_skills(skills_dir, workflows_dir):
    print(f"Syncing workflow skills from {workflows_dir} to {skills_dir}...")
    _makedirs(skills_dir)
        
    workflows = ["sdlc-block", "sdlc-run", "sdlc-task", "sdlc-flow"]
    
    for wf in workflows:
        js_file = os.path.join(workflows_dir, f"{wf}.js")
        if not os.path.exists(js_file):
            print(f"  Workflow source {js_file} does not exist. Skipping.")
            continue
            
        skill_folder = os.path.join(skills_dir, wf)
        skill_file = os.path.join(skill_folder, "SKILL.md")
        
        if not os.path.exists(skill_folder):
            _makedirs(skill_folder)
            print(f"  {'[dry-run] would create' if DRY_RUN else 'Created'} workflow skill folder: {wf}")
            
        # 1. Get frontmatter
        frontmatter = get_skill_frontmatter(wf, skill_file)
        
        # 2. Extract JS header comment
        js_header = extract_js_header(js_file)
        
        # 3. Handle guide
        guide = ""
        # If it's a new or existing skill, let's look for existing Antigravity Execution Guide
        if os.path.exists(skill_file):
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()
            # Find the guide section
            idx = content.find("## Antigravity Execution Guide")
            if idx != -1:
                # rstrip() is load-bearing for IDEMPOTENCY, not cosmetic. The guide is read back
                # out of the file this function itself wrote, so any trailing newlines it carries
                # are re-emitted alongside the "\n" suffix below - and grow by one on every run.
                # Before this, each sync appended blank lines to sdlc-task/SKILL.md and
                # sdlc-flow/SKILL.md forever, leaving both permanently dirty after a "successful"
                # sync. That also blocked any freshness check being built on this script: a check
                # would report drift immediately after a clean sync, which is the fastest way to
                # make a check ignored.
                guide = "\n" + content[idx:].rstrip()
        
        # If no guide was found and it's sdlc-flow, use our defined one
        if not guide and wf == "sdlc-flow":
            guide = SDLC_FLOW_GUIDE.rstrip()
            
        if _write_text(skill_file, frontmatter + js_header + "\n" + guide + "\n") and not DRY_RUN:
            print(f"  Updated workflow skill: {wf}")

def copy_hand_authored_skills(skills_dir, dest_skills_dir, authored_dir):
    """Copy ONLY the hand-authored skills into `dest_skills_dir`.

    `authored_dir` is base-template/.claude/skills - the source of truth for what is a real,
    hand-written skill as opposed to a mirror this script generated from a command. The slug
    list is derived from that directory rather than hardcoded, so a new skill needs no edit here.

    Why the filter is load-bearing: this function rmtree+copytree's each slug, and `skills_dir`
    (.agents/skills) holds ~50 command mirrors alongside the hand-authored skills. Copying all of
    them into the HQ brain root would overwrite HQ's OWN command mirrors with base-template's -
    HQ's /prime mirror replaced by base-template's - which is exactly the overwrite
    sync_downstream_harness.py's `engines_only` flag exists to prevent (D54). HQ authors its own
    brain-specific commands and main() already regenerates its mirrors from them.
    """
    if not os.path.isdir(authored_dir):
        print(f"  Authored-skill source {authored_dir} not found; copying nothing.")
        return

    authored = sorted(
        d for d in os.listdir(authored_dir)
        if os.path.isdir(os.path.join(authored_dir, d))
    )
    print(f"Copying {len(authored)} hand-authored skills from {skills_dir} to {dest_skills_dir}...")
    _makedirs(dest_skills_dir)

    for folder in authored:
        src_folder = os.path.join(skills_dir, folder)
        if not os.path.isdir(src_folder):
            print(f"  Skipping {folder}: no .agents mirror exists yet")
            continue

        dest_folder = os.path.join(dest_skills_dir, folder)
        # Compare before reporting: an unconditional "would replace" makes --dry-run useless,
        # since it reports every slug on every invocation whether or not anything differs.
        identical = os.path.isdir(dest_folder) and not filecmp.dircmp(
            src_folder, dest_folder
        ).diff_files and _dirs_match(src_folder, dest_folder)
        if identical:
            continue
        if DRY_RUN:
            print(f"  [dry-run] would replace: {dest_folder}")
            _CHANGES.append(("replace", dest_folder))
            continue
        if os.path.exists(dest_folder):
            shutil.rmtree(dest_folder)

        shutil.copytree(src_folder, dest_folder)
        print(f"  Copied {folder}")

def main():
    global DRY_RUN
    parser = argparse.ArgumentParser(
        description="Generate .agents/skills mirrors from .claude/commands and .claude/workflows."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report every file that would be created or modified; write nothing",
    )
    args = parser.parse_args()
    DRY_RUN = args.dry_run

    os.chdir(os.path.expanduser("~/Dev/agentic-portfolio"))
    
    # 1. Base template
    base_skills = "base-template/.agents/skills"
    base_commands = "base-template/.claude/commands"
    base_workflows = "base-template/.claude/workflows"
    
    sync_command_skills(base_skills, base_commands)
    sync_workflow_skills(base_skills, base_workflows)
    
    # 2. Root workspace (.agents/skills)
    root_skills = ".agents/skills"
    root_commands = ".claude/commands"
    
    sync_command_skills(root_skills, root_commands)
    
    # 3. Copy base-template's hand-authored skills into the HQ brain root's .agents/skills.
    #    NOT ~/agentic-portfolio, which is a bare home directory nothing reads: that was the
    #    original target and it accumulated 66 orphaned skill folders before being caught. An
    #    earlier variant of the same bug never expanduser'd the string at all and wrote 65 files
    #    to a literal ./~ directory at the HQ root, invisible to every git-based check because
    #    .gitignore's `*~` rule matches it (HQ.7.B, scripts/check_no_stray_tilde.sh).
    copy_hand_authored_skills(base_skills, root_skills, "base-template/.claude/skills")
    
    # 4. Sub-brain tiers (core, portfolio, side, client)
    tiers = set()
    if os.path.exists("brain.toml"):
        with open("brain.toml", "r", encoding="utf-8") as f:
            for line in f:
                match = re.search(r'tier\s*=\s*"([^"]+)"', line)
                if match:
                    t = match.group(1)
                    if t != "_root" and not t.startswith("_"):
                        tiers.add(t)
                        
    for tier in sorted(tiers):
        tier_commands = f"{tier}/.claude/commands"
        tier_skills = f"{tier}/.agents/skills"
        if os.path.exists(tier_commands):
            sync_command_skills(tier_skills, tier_commands)
            
    if DRY_RUN:
        print(f"\n[dry-run] {len(_CHANGES)} path(s) would change. Nothing was written.")
    else:
        print(f"\nSync and migration complete! {len(_CHANGES)} path(s) changed.")

if __name__ == "__main__":
    main()
