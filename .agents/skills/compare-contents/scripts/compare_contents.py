import os
import difflib

def clean_frontmatter(content):
    lines = content.strip().split("\n")
    if len(lines) > 0 and lines[0].strip() == "---":
        end_idx = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break
        if end_idx != -1:
            return "\n".join(lines[end_idx + 1:]).strip()
    return content.strip()

def normalize_text(text):
    # Replace parameters/variables difference to check if everything else is identical
    normalized = text.replace("## Parameters", "## Variables")
    normalized = normalized.replace("- **Correspondence Summary**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Lead info**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Work Summary** (optional):", "$ARGUMENTS —")
    normalized = normalized.replace("- **Project Description**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Flag** (optional):", "$ARGUMENTS —")
    normalized = normalized.replace("- **Company Info**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Slug** (optional):", "$ARGUMENTS —")
    normalized = normalized.replace("- **Update Description**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Update description**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Completion description**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Decision Description**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Idea Summary**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Project Info**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Ticket info**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Draft info**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Lead info**:", "$ARGUMENTS —")
    normalized = normalized.replace("- **Description**:", "$ARGUMENTS —")
    return normalized

def compare_files_detailed(file1, file2):
    if not os.path.exists(file1) or not os.path.exists(file2):
        return None, "One or both files do not exist"
    with open(file1, "r", encoding="utf-8") as f:
        c1 = f.read()
    with open(file2, "r", encoding="utf-8") as f:
        c2 = f.read()
        
    c1_clean = clean_frontmatter(c1)
    c2_clean = clean_frontmatter(c2)
    
    lines1 = [l.strip() for l in c1_clean.split("\n") if l.strip()]
    lines2 = [l.strip() for l in c2_clean.split("\n") if l.strip()]
    
    if lines1 == lines2:
        return "MATCH", ""
        
    # Check normalized match
    norm1 = [normalize_text(l) for l in lines1]
    norm2 = [normalize_text(l) for l in lines2]
    
    if norm1 == norm2:
        return "SEMANTIC_MATCH", "Matches semantically (differences only in Parameters vs Variables/ARGUMENTS structure)"
        
    # Generate diff on clean text (not normalized, to see exact differences)
    diff = list(difflib.unified_diff(lines1, lines2, fromfile=file1, tofile=file2, n=3))
    return "MISMATCH", diff

def main():
    os.chdir("~/agentic-portfolio")
    artifact_path = "~/agentic-portfolio"
    
    report = []
    report.append("# Command vs Skill Comparison Report\n")
    report.append("Detailed analysis comparing custom Gemini skills and Claude commands.\n")
    
    # ------------------ BASE TEMPLATE ------------------
    report.append("## 1. Base Template (`base-template/`)\n")
    base_skills_dir = "base-template/.agents/skills"
    base_commands_dir = "base-template/.claude/commands"
    base_workflows_dir = "base-template/.claude/workflows"
    
    skills = os.listdir(base_skills_dir) if os.path.exists(base_skills_dir) else []
    commands = [f[:-3] for f in os.listdir(base_commands_dir) if f.endswith(".md") and f != "README.md"] if os.path.exists(base_commands_dir) else []
    workflows = [f[:-3] for f in os.listdir(base_workflows_dir) if f.endswith(".js")] if os.path.exists(base_workflows_dir) else []
    
    report.append("### Directory Overviews\n")
    report.append(f"- **Gemini Skills ({len(skills)}):** `{', '.join(sorted(skills))}`\n")
    report.append(f"- **Claude Commands ({len(commands)}):** `{', '.join(sorted(commands))}`\n")
    report.append(f"- **Claude Workflows ({len(workflows)}):** `{', '.join(sorted(workflows))}`\n")
    
    # Missing files check
    missing_skills = []
    for cmd in commands:
        if cmd not in skills:
            if cmd.startswith("test_") or cmd == "e2e-templates-README" or cmd == "conditional_docs":
                continue
            missing_skills.append(cmd)
    for wf in workflows:
        if wf not in skills:
            missing_skills.append(wf)
            
    report.append("### Discrepancies in File Presence\n")
    if missing_skills:
        report.append(f"- **Commands/Workflows without corresponding skills:** `{', '.join(missing_skills)}`\n")
    else:
        report.append("- **Commands/Workflows without corresponding skills:** None\n")
        
    report.append("### File-by-File Content Analysis\n")
    report.append("| Skill Name | Status | Details / Notes |\n|---|---|---|\n")
    
    for skill in sorted(skills):
        skill_file = os.path.join(base_skills_dir, skill, "SKILL.md")
        command_file = os.path.join(base_commands_dir, f"{skill}.md")
        
        if os.path.exists(command_file):
            status_code, detail = compare_files_detailed(skill_file, command_file)
            if status_code == "MATCH":
                report.append(f"| `{skill}` | ✅ MATCH | Exact match (excluding frontmatter) |\n")
            elif status_code == "SEMANTIC_MATCH":
                report.append(f"| `{skill}` | ✅ SEMANTIC MATCH | {detail} |\n")
            else:
                report.append(f"| `{skill}` | ⚠️ MISMATCH | Content discrepancy! See diff section below. |\n")
        else:
            workflow_file = f"base-template/.claude/workflows/{skill}.js"
            if os.path.exists(workflow_file):
                report.append(f"| `{skill}` | ℹ️ WORKFLOW | Maps to JavaScript workflow (`{skill}.js`) |\n")
            else:
                report.append(f"| `{skill}` | ❌ NO COMMAND | No matching command or workflow found |\n")
                
    # ------------------ ROOT WORKSPACE ------------------
    report.append("\n## 2. Root Workspace (`/`)\n")
    root_skills_dir = ".agent/skills"
    root_commands_dir = ".claude/commands"
    
    skills = os.listdir(root_skills_dir) if os.path.exists(root_skills_dir) else []
    commands = [f[:-3] for f in os.listdir(root_commands_dir) if f.endswith(".md") and f != "README.md"] if os.path.exists(root_commands_dir) else []
    
    report.append("### Directory Overviews\n")
    report.append(f"- **Gemini Skills ({len(skills)}):** `{', '.join(sorted(skills))}`\n")
    report.append(f"- **Claude Commands ({len(commands)}):** `{', '.join(sorted(commands))}`\n")
    
    missing_skills = []
    for cmd in commands:
        if cmd not in skills:
            missing_skills.append(cmd)
            
    report.append("### Discrepancies in File Presence\n")
    if missing_skills:
        report.append(f"- **Commands without corresponding skills in root:** `{', '.join(missing_skills)}`\n")
    else:
        report.append("- **Commands without corresponding skills in root:** None\n")
        
    report.append("### File-by-File Content Analysis\n")
    report.append("| Skill Name | Status | Details / Notes |\n|---|---|---|\n")
    
    for skill in sorted(skills):
        skill_file = os.path.join(root_skills_dir, skill, "SKILL.md")
        command_file = os.path.join(root_commands_dir, f"{skill}.md")
        
        if os.path.exists(command_file):
            status_code, detail = compare_files_detailed(skill_file, command_file)
            if status_code == "MATCH":
                report.append(f"| `{skill}` | ✅ MATCH | Exact match (excluding frontmatter) |\n")
            elif status_code == "SEMANTIC_MATCH":
                report.append(f"| `{skill}` | ✅ SEMANTIC MATCH | {detail} |\n")
            else:
                report.append(f"| `{skill}` | ⚠️ MISMATCH | Content discrepancy! See diff section below. |\n")
        else:
            report.append(f"| `{skill}` | ❌ NO COMMAND | No matching command file found |\n")
            
    # Add detailed diffs section
    report.append("\n## Detailed Content Diffs for Mismatches\n")
    
    # Let's collect mismatches
    mismatches = []
    # Base template mismatches
    for skill in sorted(os.listdir(base_skills_dir) if os.path.exists(base_skills_dir) else []):
        skill_file = os.path.join(base_skills_dir, skill, "SKILL.md")
        command_file = os.path.join(base_commands_dir, f"{skill}.md")
        if os.path.exists(command_file):
            status_code, detail = compare_files_detailed(skill_file, command_file)
            if status_code == "MISMATCH":
                mismatches.append(("base-template", skill, detail))
                
    # Root mismatches
    for skill in sorted(os.listdir(root_skills_dir) if os.path.exists(root_skills_dir) else []):
        skill_file = os.path.join(root_skills_dir, skill, "SKILL.md")
        command_file = os.path.join(root_commands_dir, f"{skill}.md")
        if os.path.exists(command_file):
            status_code, detail = compare_files_detailed(skill_file, command_file)
            if status_code == "MISMATCH":
                mismatches.append(("root", skill, detail))
                
    if not mismatches:
        report.append("No active content discrepancies found (all are matches or semantic matches).\n")
    else:
        for scope, skill, diff in mismatches:
            report.append(f"### Mismatch in {scope} skill `{skill}`\n")
            report.append("```diff\n")
            report.extend(diff)
            report.append("```\n")
            
    with open(artifact_path, "w", encoding="utf-8") as f:
        f.writelines(report)
    print(f"Report written to {artifact_path}")

if __name__ == "__main__":
    main()
