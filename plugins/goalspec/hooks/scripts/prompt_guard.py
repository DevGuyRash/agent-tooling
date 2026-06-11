#!/usr/bin/env python3
"""UserPromptSubmit hook: nudge/block unsafe direct /goal launches."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from _hook_common import SCRIPTS  # noqa: F401
from common import load_json_stdin, active_goal_paths


def main() -> int:
    event = load_json_stdin()
    prompt = event.get("prompt", "") or ""
    cwd = event.get("cwd")
    _, current, lock = active_goal_paths(cwd)
    lowered = prompt.lower().strip()
    if lowered.startswith("/goal"):
        safe_refs = [".goals/current.md", ".goals/campaign", "$authoring-goals", "authoring-goals"]
        if not any(ref in prompt for ref in safe_refs):
            msg = "GoalSpec: direct /goal detected. For long-running work, first use $authoring-goals to create/validate .goals/current.md, then run /goal against that frozen contract."
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": msg
                }
            }))
            return 0
        if ".goals/current.md" in prompt and not current.exists():
            print(json.dumps({
                "decision": "block",
                "reason": "GoalSpec: .goals/current.md is referenced but does not exist. Use $authoring-goals to create it first."
            }))
            return 0
        if current.exists() and not lock.exists():
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": "GoalSpec: .goals/current.md exists but is not locked. Run validate_goal.py .goals/current.md --write-hash before launching /goal."
                }
            }))
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
