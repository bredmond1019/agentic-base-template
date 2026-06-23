#!/usr/bin/env -S uv run python
"""Pre-tool-use security guard. Blocks .env reads and destructive rm commands."""

import json
import sys


def block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def main() -> None:
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name == "Bash":
        command = tool_input.get("command", "")

        # Block direct .env reads; allow .env.example
        if ".env" in command and ".env.example" not in command:
            block("Blocked: direct .env read. Use os.environ or a config loader.")

        # Block destructive root/home rm -rf
        if "rm -rf /" in command or "rm -rf ~" in command:
            block("Blocked: destructive rm -rf detected.")


main()
