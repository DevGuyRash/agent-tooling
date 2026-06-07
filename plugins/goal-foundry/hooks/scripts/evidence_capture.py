#!/usr/bin/env python3
"""PostToolUse hook: persist tool events as evidence when a goal contract is active."""
from __future__ import annotations

import json
import os
from pathlib import Path

from _hook_common import SCRIPTS  # noqa: F401
from common import active_goal_paths, git_root_or_cwd, load_json_stdin, relpath, write_event


def main() -> int:
    event = load_json_stdin()
    cwd = event.get("cwd") or os.getcwd()
    _, current, lock = active_goal_paths(cwd)
    if not current.exists():
        return 0
    # Keep a compact but raw-enough evidence event. The transcript is not treated as a stable interface.
    payload = {
        "hook_event_name": event.get("hook_event_name"),
        "turn_id": event.get("turn_id"),
        "tool_name": event.get("tool_name"),
        "tool_input": event.get("tool_input"),
        "tool_response": event.get("tool_response") or event.get("tool_result") or event.get("result"),
        "permission_mode": event.get("permission_mode"),
        "cwd": cwd,
    }
    path = write_event(cwd, payload, prefix=(event.get("tool_name") or "tool").replace("/", "_"))
    # Maintain a simple runtime state file for audits and budget reports.
    root = git_root_or_cwd(cwd)
    state_path = root / ".goals" / "run_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"tool_events": 0, "tools": {}}
        state["tool_events"] = int(state.get("tool_events", 0)) + 1
        tool = event.get("tool_name") or "unknown"
        state.setdefault("tools", {})[tool] = int(state.setdefault("tools", {}).get(tool, 0)) + 1
        state["latest_evidence"] = relpath(path, root)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        pass
    msg = f"Goal Foundry captured tool evidence at `{relpath(path, Path(cwd))}`. Use raw command results/artifact paths in the final goal report."
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
