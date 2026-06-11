#!/usr/bin/env python3
"""PreToolUse hook: block obvious edits to the frozen contract and protected .goals files."""
from __future__ import annotations

import json
import os
import re

from _hook_common import SCRIPTS  # noqa: F401
from common import (
    active_goal_paths,
    command_mentions_write_to_protected,
    extract_patch_paths,
    goal_workspace_locked,
    load_json_stdin,
)

PROTECTED = [
    ".goals/current.md",
    ".goals/current.sha256",
    ".goals/GOALS.md",
    ".goals/graph.json",
    ".goals/frontier.md",
]
ALLOWED_GOALS_PREFIXES = [".goals/evidence/", ".goals/reports/"]
DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\s+/(?:\s|$)",
    r"\brm\s+-rf\s+\.goals(?:/|\s|$)",
    r"\bchmod\s+-R\s+777\b",
    r"\bmkfs\.",
    r"\bdd\s+if=",
]


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def context(msg: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": msg,
        }
    }))


def _mention_is_allowed(mention: str) -> bool:
    return any(mention == prefix.rstrip("/") or mention.startswith(prefix)
               for prefix in ALLOWED_GOALS_PREFIXES)


def path_is_protected(path: str) -> bool:
    p = path.strip()
    if p.startswith("./"):
        p = p[2:]
    # Keep the leading dot in .goals; do not use lstrip("./").
    if any(p.startswith(prefix) for prefix in ALLOWED_GOALS_PREFIXES):
        return False
    if any(p == item or p.startswith(item + "/") for item in PROTECTED):
        return True
    # Everything else under .goals/ is frozen during a run (evidence/ and reports/ returned above).
    return p.startswith(".goals/")


def main() -> int:
    event = load_json_stdin()
    cwd = event.get("cwd")
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    goals_dir, _, _ = active_goal_paths(cwd)
    # Arms on a complete root contract+lock pair OR a campaign lock (campaign-only
    # runs have no root current.md but their children must stay frozen too).
    locked = goal_workspace_locked(goals_dir) \
        and os.environ.get("GOALSPEC_ALLOW_CONTRACT_WRITE") != "1"

    for pat in DANGEROUS_PATTERNS:
        if command and re.search(pat, command):
            deny(f"GoalSpec blocked dangerous command matching {pat!r}.")
            return 0

    if not locked:
        # Before lock, authoring can create/update current.md.
        return 0

    if tool.startswith("mcp__"):
        # MCP calls are now matched (parity with PostToolUse) but their I/O is
        # opaque, so there is no deterministic protected-path check here. The
        # audit hash and render-refuse-unlocked remain the freeze backstop.
        return 0

    if tool in {"apply_patch", "Edit", "Write"}:
        paths = extract_patch_paths(command)
        protected_hits = [p for p in paths if path_is_protected(p)]
        if protected_hits:
            deny("GoalSpec blocked modification to frozen goal artifacts: " + ", ".join(protected_hits) + ". Executor may only write .goals/evidence/ and .goals/reports/ during a run.")
            return 0

    if tool == "Bash" and command:
        # Bash only exposes the raw command string, so mirror path_is_protected's
        # allow-list here: mentions under .goals/evidence|reports are executor
        # space. The previous bare ".goals/" entry denied the plugin's own
        # run_verifiers/audit invocations and any allowed-path command carrying
        # an incidental redirect like 2>&1.
        mentions = re.findall(r"\.goals/[^\s'\"`;|&)]*", command)
        frozen_mentions = sorted({m for m in mentions if not _mention_is_allowed(m)})
        if frozen_mentions:
            hit = command_mentions_write_to_protected(command, frozen_mentions)
            if hit:
                deny(f"GoalSpec blocked write-like command touching protected goal artifact: {hit}. Use $authoring-goals to revise and re-lock the contract before execution.")
                return 0
        if re.search(r"\b(git\s+checkout|git\s+reset|git\s+clean)\b", command) and (frozen_mentions or re.search(r"\.goals(?!/)", command)):
            deny("GoalSpec blocked git command targeting .goals artifacts during an active run.")
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
