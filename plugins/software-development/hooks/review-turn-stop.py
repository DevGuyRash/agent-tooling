#!/usr/bin/env python3
"""Stop hook: once per Codex turn that changed its repository, ask for a review of the work before the turn ends.

Codex only: the stop payload's turn_id marks a Codex turn. On Claude, where the same review gained little and
hurt clean reports in trials, the hook does nothing."""
import datetime, json, os, subprocess, sys, tempfile

REVIEW = ("Before you finish, review your work as a careful reviewer of this codebase would: look for other places that "
          "implement or depend on what you changed and make them agree; check that the change holds under the conditions "
          "its callers will run it in; and check that your tests exercise what the request relies on. "
          "Fix what you find, then reply to the user.")
try:
    data = json.load(sys.stdin)
except ValueError:
    data = {}
if not isinstance(data, dict):
    data = {}
harness = os.environ.get("TRIAL_HARNESS")
if harness and os.path.isdir(harness):
    with open(os.path.join(harness, "stop-hook.jsonl"), "a") as f:
        f.write(json.dumps(data) + "\n")
if data.get("stop_hook_active") or "turn_id" not in data:
    sys.exit(0)


def turn_start():
    """The first whole second after this turn began, from the task_started record Codex writes for the turn in the
    session's transcript (its earliest, should the turn be resumed), or None. Git compares commit times in whole
    seconds, so rounding up keeps a commit from just before the turn out of it."""
    path = data.get("transcript_path")
    if not isinstance(path, str) or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as transcript:
            for line in transcript:
                if '"task_started"' not in line or str(data["turn_id"]) not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(record, dict) or record.get("type") != "event_msg":
                    continue
                payload = record.get("payload")
                if (isinstance(payload, dict) and payload.get("type") == "task_started"
                        and payload.get("turn_id") == data["turn_id"] and isinstance(record.get("timestamp"), str)):
                    began = datetime.datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
                    return (began.replace(microsecond=0) + datetime.timedelta(seconds=1)).isoformat()
    except (OSError, ValueError):
        return None
    return None


# A turn with no repository, or one that changed nothing in it (a question, a plan), has nothing to review. A turn
# that committed its work leaves a clean tree, so a commit on the checked-out history since the turn began is a
# change too.
try:
    git = ["git", "-C", data.get("cwd") if isinstance(data.get("cwd"), str) else os.getcwd()]
    status = subprocess.run(git + ["status", "--porcelain"], capture_output=True, text=True, timeout=10)
    if status.returncode != 0:
        sys.exit(0)
    if not status.stdout.strip():
        start = turn_start()
        made = start and subprocess.run(git + ["log", "HEAD", f"--since={start}", "-1", "--format=%H"],
                                        capture_output=True, text=True, timeout=10)
        if not (made and made.returncode == 0 and made.stdout.strip()):
            sys.exit(0)
except (OSError, subprocess.SubprocessError):
    sys.exit(0)
key = str(data.get("turn_id") or data.get("session_id") or "session").replace("/", "_")
marker = os.path.join(os.environ.get("CODEX_HOME") or tempfile.gettempdir(), f".review-turn-{key}")
if os.path.exists(marker):
    sys.exit(0)
try:
    open(marker, "w").close()
except OSError:  # without its marker the review would be asked at every stop of the turn
    sys.exit(0)
print(json.dumps({"decision": "block", "reason": REVIEW}))
