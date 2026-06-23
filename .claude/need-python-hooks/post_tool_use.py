#!/usr/bin/env -S uv run python
"""Post-tool-use session usage logger. Appends a JSON line per tool call. Never raises."""

import json
import os
import sys
from datetime import datetime, timezone


def main() -> None:
    try:
        data = json.load(sys.stdin)
        session_id = data.get("session_id", "unknown")
        tool_name = data.get("tool_name", "unknown")

        log_dir = ".claude/logs"
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(log_dir, f"tool-usage-{session_id}.jsonl")
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # never break the main session


main()
