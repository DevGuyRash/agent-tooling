#!/usr/bin/env python3
"""Stop hook: require final evidence fields and contract hash integrity."""
from __future__ import annotations

import json
import re

from _hook_common import SCRIPTS  # noqa: F401
from common import active_goal_paths, current_hash_status, load_json_stdin

CLAIM_WORDS = re.compile(r"\b(done|complete|completed|fixed|implemented|achieved|finished)\b", re.I)


def _already_blocked(event: dict, cwd, cause: str) -> bool:
    """True when this cause already blocked a stop for the current contract.

    Every block branch must be once-per-cause or the gate livelocks the run:
    a mutated contract cannot be un-mutated by the executor, so re-blocking
    forever turns the anti-runaway gate into the runaway (observed live on
    Codex: 71 consecutive Stop blocks until an external timeout killed the
    run). The marker is persisted under .goals/evidence/ because the
    harness-provided stop_hook_active field is not guaranteed off Claude Code.
    Fails open (treat as already-blocked) — the audit hash is the real gate.
    """
    if event.get("stop_hook_active"):
        return True
    try:
        goals, _, _ = active_goal_paths(cwd)
        state_path = goals / "evidence" / "stop_guard_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        blocked = state.setdefault("blocked", {})
        if cause in blocked:
            return True
        blocked[cause] = 1
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return False
    except Exception:
        return True


def main() -> int:
    event = load_json_stdin()
    cwd = event.get("cwd")
    last = event.get("last_assistant_message") or ""
    _, current, lock = active_goal_paths(cwd)
    # Codex Stop semantics: allow/no-op is exit 0 with NO stdout; emit JSON only
    # to continue (block the stop). A bare {"continue": true} is a Claude-ism that
    # Codex treats as ambiguous, so allow paths stay silent here.
    if not current.exists():
        return 0

    status = current_hash_status(cwd)
    if status.get("matched") is False:
        cause = f"contract-mutated:{str(status.get('expected_hash', ''))[:12]}"
        if _already_blocked(event, cwd, cause):
            return 0
        print(json.dumps({
            "decision": "block",
            "reason": "GoalSpec audit gate: .goals/current.md hash no longer matches .goals/current.sha256. Do not claim success. Report 'contract mutated' with the expected/current hashes and stop for user review."
        }))
        return 0

    if CLAIM_WORDS.search(last):
        if not lock.exists():
            if _already_blocked(event, cwd, "unlocked-claim"):
                return 0
            print(json.dumps({
                "decision": "block",
                "reason": "GoalSpec audit gate: completion claimed but .goals/current.md is not locked (no .goals/current.sha256). An unlocked contract cannot be certified as achieved. Lock it with validate_goal.py .goals/current.md --write-hash and audit, or report the result as inconclusive/blocked, not achieved."
            }))
            return 0
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
        # An achievement claim must reference the verifier pass/fail oracle, not
        # merely that files changed. Evidence presence is not verification success.
        if not any(p in last.lower() for p in ["verifier", "passed", "pass/fail", "exit 0", "overall_passed", "exit code"]):
            missing.append("verifier pass/fail result (the oracle, e.g. 'verifier passed' or 'exit 0')")
        if missing:
            cause = f"final-report:{str(status.get('current_hash', ''))[:12]}"
            if _already_blocked(event, cwd, cause):
                return 0
            print(json.dumps({
                "decision": "block",
                "reason": "GoalSpec final-report gate: before stopping, provide the required final report fields from .goals/current.md: files changed, commands run with the verifier pass/fail result (achievement requires passing verifier evidence, not just changed files), budget used, remaining risks, and follow-up candidates. Missing: " + ", ".join(missing)
            }))
            return 0

    # Allow the stop: exit 0 with no stdout.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
