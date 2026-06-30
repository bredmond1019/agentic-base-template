import os

def analyze_base_template():
    base_skills_dir = "base-template/.agents/skills"
    base_commands_dir = "base-template/.claude/commands"
    base_workflows_dir = "base-template/.claude/workflows"

    skills = os.listdir(base_skills_dir) if os.path.exists(base_skills_dir) else []
    commands = [f[:-3] for f in os.listdir(base_commands_dir) if f.endswith(".md") and f != "README.md"] if os.path.exists(base_commands_dir) else []
    workflows = [f[:-3] for f in os.listdir(base_workflows_dir) if f.endswith(".js")] if os.path.exists(base_workflows_dir) else []

    print("--- BASE TEMPLATE ANALYSIS ---")
    print(f"Skills ({len(skills)}): {sorted(skills)}")
    print(f"Commands ({len(commands)}): {sorted(commands)}")
    print(f"Workflows ({len(workflows)}): {sorted(workflows)}")

    # Check for commands/workflows that don't have corresponding skills
    missing_skills = []
    for cmd in commands:
        if cmd not in skills:
            # Check if it's a test file or readme helper
            if cmd.startswith("test_") or cmd == "e2e-templates-README" or cmd == "conditional_docs":
                continue
            missing_skills.append(cmd)
    for wf in workflows:
        if wf not in skills:
            missing_skills.append(wf)
            
    print(f"Commands/Workflows without corresponding skills: {missing_skills}")

    # Check for skills without corresponding commands/workflows
    extra_skills = []
    for skill in skills:
        if skill not in commands and skill not in workflows:
            # Note: workflows are typically sdlc-task, sdlc-run, sdlc-block etc.
            extra_skills.append(skill)
    print(f"Skills without corresponding commands/workflows: {extra_skills}")
    print()

def analyze_root():
    root_skills_dir = ".agent/skills"
    root_commands_dir = ".claude/commands"
    
    skills = os.listdir(root_skills_dir) if os.path.exists(root_skills_dir) else []
    commands = [f[:-3] for f in os.listdir(root_commands_dir) if f.endswith(".md") and f != "README.md"] if os.path.exists(root_commands_dir) else []
    
    print("--- ROOT WORKSPACE ANALYSIS ---")
    print(f"Skills ({len(skills)}): {sorted(skills)}")
    print(f"Commands ({len(commands)}): {sorted(commands)}")
    
    missing_skills = []
    for cmd in commands:
        if cmd not in skills:
            missing_skills.append(cmd)
            
    print(f"Commands without corresponding skills in root: {missing_skills}")
    
    extra_skills = []
    for skill in skills:
        if skill not in commands:
            extra_skills.append(skill)
    print(f"Skills without corresponding commands in root: {extra_skills}")
    print()

if __name__ == "__main__":
    os.chdir("~/agentic-portfolio")
    analyze_base_template()
    analyze_root()
