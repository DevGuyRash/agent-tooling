#!/usr/bin/env python3
"""Stop hook: once per Codex turn that changed its repository, ask for a review of the work before the turn ends.

Codex only: the stop payload's turn_id marks a Codex turn. On Claude, where the same review gained little and
hurt clean reports in trials, the hook does nothing."""
import json, os, subprocess, sys, tempfile

REVIEW = ("Before you finish, review your work as a careful reviewer of this codebase would: look for other places that "
          "implement or depend on what you changed and make them agree; check that the change holds under the conditions "
          "its callers will run it in; and check that your tests exercise what the request relies on. "
          "Fix what you find, then reply to the user.")
try:
    data = json.load(sys.stdin)
except ValueError:
    data = {}
harness = os.environ.get("TRIAL_HARNESS")
if harness and os.path.isdir(harness):
    with open(os.path.join(harness, "stop-hook.jsonl"), "a") as f:
        f.write(json.dumps(data) + "\n")
if data.get("stop_hook_active") or "turn_id" not in data:
    sys.exit(0)


def turn_start():
    """When this turn began: the timestamp of the task_started record Codex writes for it in the session's transcript."""
    start = None
    try:
        with open(data.get("transcript_path") or "", encoding="utf-8", errors="replace") as transcript:
            for line in transcript:
                if '"task_started"' in line and str(data["turn_id"]) in line:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if (record.get("payload") or {}).get("turn_id") == data["turn_id"]:
                        start = record.get("timestamp")
    except OSError:
        return None
    return start if isinstance(start, str) else None


# A turn with no repository, or one that changed nothing in it (a question, a plan), has nothing to review. A turn
# that committed its work leaves a clean tree, so a commit on a branch since the turn began is a change too.
try:
    git = ["git", "-C", data.get("cwd") or os.getcwd()]
    status = subprocess.run(git + ["status", "--porcelain"], capture_output=True, text=True, timeout=10)
    if status.returncode != 0:
        sys.exit(0)
    if not status.stdout.strip():
        start = turn_start()
        made = start and subprocess.run(git + ["log", "--branches", f"--since={start}", "-1", "--format=%H"],
                                        capture_output=True, text=True, timeout=10)
        if not (made and made.returncode == 0 and made.stdout.strip()):
            sys.exit(0)
except (OSError, subprocess.SubprocessError):
    sys.exit(0)
key = str(data.get("turn_id") or data.get("session_id") or "session").replace("/", "_")
marker = os.path.join(os.environ.get("CODEX_HOME") or tempfile.gettempdir(), f".review-turn-{key}")
if os.path.exists(marker):
    sys.exit(0)
open(marker, "w").close()
print(json.dumps({"decision": "block", "reason": REVIEW}))
