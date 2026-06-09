#!/usr/bin/env python3
"""Stop hook: require final evidence fields and contract hash integrity."""
from __future__ import annotations

import json
import re
from pathlib import Path

from _hook_common import SCRIPTS  # noqa: F401
from common import REPORT_FIELDS, active_goal_paths, current_hash_status, load_json_stdin

CLAIM_WORDS = re.compile(r"\b(done|complete|completed|fixed|implemented|achieved|finished)\b", re.I)


def main() -> int:
    event = load_json_stdin()
    cwd = event.get("cwd")
    stop_hook_active = bool(event.get("stop_hook_active"))
    last = event.get("last_assistant_message") or ""
    _, current, lock = active_goal_paths(cwd)
    if not current.exists():
        print(json.dumps({"continue": True}))
        return 0

    status = current_hash_status(cwd)
    if status.get("matched") is False:
        print(json.dumps({
            "decision": "block",
            "reason": "GoalSpec audit gate: .goals/current.md hash no longer matches .goals/current.sha256. Do not claim success. Report 'contract mutated' with the expected/current hashes and stop for user review."
        }))
        return 0

    # Avoid forcing twice in a row; if already continued by Stop, let it end.
    if stop_hook_active:
        print(json.dumps({"continue": True}))
        return 0

    if CLAIM_WORDS.search(last):
        required_phrases = [
            "files changed",
            "commands run",
            "budget used",
            "follow-up",
        ]
        missing = [p for p in required_phrases if p not in last.lower()]
        # Evidence can be phrased as raw results, test results, or artifact paths.
        if not any(p in last.lower() for p in ["evidence", "raw result", "test result", "artifact", "exit code"]):
            missing.append("evidence/raw results/artifact paths")
        if missing:
            print(json.dumps({
                "decision": "block",
                "reason": "GoalSpec final-report gate: before stopping, provide the required final report fields from .goals/current.md: files changed, commands run with raw pass/fail results or artifact paths, budget used, remaining risks, and follow-up candidates. Missing: " + ", ".join(missing)
            }))
            return 0

    print(json.dumps({"continue": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
