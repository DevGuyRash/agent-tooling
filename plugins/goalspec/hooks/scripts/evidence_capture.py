#!/usr/bin/env python3
"""PostToolUse hook: persist tool events as evidence when a goal contract is active.

PostToolUse cannot undo side effects, so this capture is write-once: secrets are
redacted and oversized output is truncated BEFORE anything touches disk. Redaction
is best-effort and intentionally over-redacts — a stray [REDACTED] is cheaper than
a leaked credential.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from _hook_common import SCRIPTS  # noqa: F401
from common import git_root_or_cwd, goal_mission_active, load_json_stdin, relpath, write_event

# Per-string capture ceiling; override with GOALSPEC_EVIDENCE_MAX_BYTES.
DEFAULT_MAX_BYTES = 16384

_SECRET_VALUE = r"([^\s'\"&]+)"
REDACTIONS = [
    (re.compile(r"(Authorization:\s*Bearer\s+)" + _SECRET_VALUE, re.I), r"\1[REDACTED]"),
    (re.compile(r"(\b\w*API_KEY\s*[=:]\s*)" + _SECRET_VALUE, re.I), r"\1[REDACTED]"),
    (re.compile(r"(\bpassword\s*[=:]\s*)" + _SECRET_VALUE, re.I), r"\1[REDACTED]"),
    (re.compile(r"(\btoken\s*[=:]\s*)" + _SECRET_VALUE, re.I), r"\1[REDACTED]"),
    (re.compile(r"(\bsecret\s*[=:]\s*)" + _SECRET_VALUE, re.I), r"\1[REDACTED]"),
]


def redact_text(text: str) -> str:
    for pattern, repl in REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def sanitize(value, max_bytes: int):
    """Recursively redact secret patterns and truncate oversized strings."""
    if isinstance(value, str):
        out = redact_text(value)
        encoded = out.encode("utf-8", "replace")
        if len(encoded) > max_bytes:
            out = encoded[:max_bytes].decode("utf-8", "ignore") + f"...[truncated {len(encoded) - max_bytes} bytes]"
        return out
    if isinstance(value, list):
        return [sanitize(v, max_bytes) for v in value]
    if isinstance(value, dict):
        return {k: sanitize(v, max_bytes) for k, v in value.items()}
    return value


def goal_workspace_for_event(event: dict, cwd: str):
    """Workspace of the files the tool touched, when one holds an active contract.

    The event's cwd is the session cwd, which can sit in a different directory
    than the files the tool acted on (multi-workspace sessions, subagents).
    Anchoring evidence to the tool's target paths keeps each goal workspace's
    evidence stream self-contained; the session cwd remains the fallback.
    """
    candidates: list[str] = []
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("file_path", "path", "notebook_path"):
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
        command = tool_input.get("command")
        if isinstance(command, str):
            candidates.extend(re.findall(r"/[^\s'\"`;|&)]+", command))
    for raw in candidates:
        p = Path(raw)
        if not p.is_absolute():
            p = Path(cwd) / p
        for parent in [p, *p.parents]:
            if goal_mission_active(parent / ".goals"):
                return parent
    return None


def main() -> int:
    event = load_json_stdin()
    cwd = event.get("cwd") or os.getcwd()
    root = goal_workspace_for_event(event, cwd) or git_root_or_cwd(cwd)
    # Active mission = a root contract OR a locked campaign chain; either one
    # makes tool events evidence-worthy.
    if not goal_mission_active(root / ".goals"):
        return 0
    try:
        max_bytes = int(os.environ.get("GOALSPEC_EVIDENCE_MAX_BYTES", DEFAULT_MAX_BYTES))
    except ValueError:
        max_bytes = DEFAULT_MAX_BYTES
    # Keep a compact but raw-enough evidence event, redacted and size-capped first.
    payload = {
        "hook_event_name": event.get("hook_event_name"),
        "turn_id": event.get("turn_id"),
        "tool_name": event.get("tool_name"),
        "tool_input": sanitize(event.get("tool_input"), max_bytes),
        "tool_response": sanitize(event.get("tool_response") or event.get("tool_result") or event.get("result"), max_bytes),
        "permission_mode": event.get("permission_mode"),
        "cwd": cwd,
    }
    path = write_event(cwd, payload, prefix=(event.get("tool_name") or "tool").replace("/", "_"), root=root)
    # Maintain a simple runtime state file for audits and budget reports.
    state_path = root / ".goals" / "evidence" / "run_state.json"
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"tool_events": 0, "tools": {}}
        state["tool_events"] = int(state.get("tool_events", 0)) + 1
        tool = event.get("tool_name") or "unknown"
        state.setdefault("tools", {})[tool] = int(state.setdefault("tools", {}).get(tool, 0)) + 1
        state["latest_evidence"] = relpath(path, root)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        pass
    msg = f"GoalSpec captured tool evidence at `{relpath(path, root)}`. Use raw command results/artifact paths in the final goal report."
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
