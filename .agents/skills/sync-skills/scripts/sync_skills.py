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
    "generate-master-plan": "Author the full roadmap as canonical block definitions",
    "handoff": "Write handoff + log work + commit; hands off to a fresh session",
    "session-recap": "Briefing: recent Log entries, where you left off, next step",
    "sync-brain-commands": "Reads brain.toml to discover sub-brain tiers and rsyncs base-template brain/ session/planning/projects commands into each tier's .claude/commands/",
    "wrap-up": "Log work + commit; clean close without a handoff file"
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
            # Simple YAML parser for key-value
            for line in fm_text.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    frontmatter[k.strip()] = v.strip().strip("'\"")
    return frontmatter, body

def get_skill_frontmatter(skill_name, existing_skill_path, command_filepath=None):
    name = skill_name
    description = NEW_SKILLS_DESCRIPTIONS.get(skill_name, f"Custom skill: {skill_name}")
    
    # 1. Try to read existing skill frontmatter
    if os.path.exists(existing_skill_path):
        with open(existing_skill_path, "r", encoding="utf-8") as f:
            existing_content = f.read()
        fm, _ = parse_frontmatter(existing_content)
        if "name" in fm:
            name = fm["name"]
        if "description" in fm:
            description = fm["description"]
            
    # 2. Try to read command frontmatter if description is generic
    elif command_filepath and os.path.exists(command_filepath):
        with open(command_filepath, "r", encoding="utf-8") as f:
            cmd_content = f.read()
        fm, _ = parse_frontmatter(cmd_content)
        if "description" in fm:
            description = fm["description"]
        elif "title" in fm:
            description = fm["title"]
            
    # Build YAML frontmatter string
    return f"---\nname: {name}\ndescription: >\n  {description}\n---\n\n"

def sync_command_skills(skills_dir, commands_dir):
    print(f"Syncing command skills from {commands_dir} to {skills_dir}...")
    if not os.path.exists(skills_dir):
        os.makedirs(skills_dir)
        
    for filename in os.listdir(commands_dir):
        if not filename.endswith(".md") or filename == "README.md" or filename == "e2e-templates-README.md" or filename.startswith("test_"):
            continue
            
        skill_name = filename[:-3]
        command_path = os.path.join(commands_dir, filename)
        skill_folder = os.path.join(skills_dir, skill_name)
        skill_file = os.path.join(skill_folder, "SKILL.md")
        
        if not os.path.exists(skill_folder):
            os.makedirs(skill_folder)
            print(f"  Created new skill folder: {skill_name}")
            
        frontmatter = get_skill_frontmatter(skill_name, skill_file, command_path)
        
        with open(command_path, "r", encoding="utf-8") as f:
            command_content = f.read()
            
        # Strip frontmatter from command file if present
        _, body = parse_frontmatter(command_content)
        
        # Write skill file
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(frontmatter + body + "\n")
        print(f"  Updated skill: {skill_name}")

def sync_workflow_skills(skills_dir, workflows_dir):
    print(f"Syncing workflow skills from {workflows_dir} to {skills_dir}...")
    if not os.path.exists(skills_dir):
        os.makedirs(skills_dir)
        
    workflows = ["sdlc-block", "sdlc-run", "sdlc-task", "sdlc-flow"]
    
    for wf in workflows:
        js_file = os.path.join(workflows_dir, f"{wf}.js")
        if not os.path.exists(js_file):
            print(f"  Workflow source {js_file} does not exist. Skipping.")
            continue
            
        skill_folder = os.path.join(skills_dir, wf)
        skill_file = os.path.join(skill_folder, "SKILL.md")
        
        if not os.path.exists(skill_folder):
            os.makedirs(skill_folder)
            print(f"  Created new workflow skill folder: {wf}")
            
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
                guide = "\n" + content[idx:]
        
        # If no guide was found and it's sdlc-flow, use our defined one
        if not guide and wf == "sdlc-flow":
            guide = SDLC_FLOW_GUIDE
            
        # Write skill file
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(frontmatter + js_header + "\n" + guide + "\n")
        print(f"  Updated workflow skill: {wf}")

def copy_to_global(skills_dir, global_skills_dir):
    print(f"Copying skills from {skills_dir} to global directory {global_skills_dir}...")
    if not os.path.exists(global_skills_dir):
        os.makedirs(global_skills_dir)
        
    for folder in os.listdir(skills_dir):
        src_folder = os.path.join(skills_dir, folder)
        if not os.path.isdir(src_folder):
            continue
            
        dest_folder = os.path.join(global_skills_dir, folder)
        if os.path.exists(dest_folder):
            shutil.rmtree(dest_folder)
            
        shutil.copytree(src_folder, dest_folder)
        print(f"  Copied {folder} -> global")

def main():
    os.chdir("~/agentic-portfolio")
    
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
    
    # 3. Copy base-template skills to global config
    global_skills = "~/agentic-portfolio"
    copy_to_global(base_skills, global_skills)
    
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
            
    print("\nSync and migration complete!")

if __name__ == "__main__":
    main()
