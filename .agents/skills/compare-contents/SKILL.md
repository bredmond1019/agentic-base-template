---
name: compare-contents
description: >
  Compare text contents of custom skills against Claude commands (ignoring YAML frontmatter) to identify instruction mismatches.
---

# Compare Contents — Custom Python Script Skill

This skill allows the agent to run the helper python script `compare_contents.py` to automate the analysis and syncing of custom skills.

## Instructions

Run the Python script:
`python3 .agents/skills/compare-contents/scripts/compare_contents.py`
