#!/usr/bin/env python3
"""Codex Stop hook: once per turn, ask for a review of the work before the turn ends."""
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
if data.get("stop_hook_active"):
    sys.exit(0)
# A turn that changed nothing in its repository (a question, a plan) has nothing to review.
try:
    status = subprocess.run(["git", "-C", data.get("cwd") or os.getcwd(), "status", "--porcelain"],
                            capture_output=True, text=True, timeout=10)
    if status.returncode == 0 and not status.stdout.strip():
        sys.exit(0)
except (OSError, subprocess.SubprocessError):
    pass
key = str(data.get("turn_id") or data.get("session_id") or "session").replace("/", "_")
marker = os.path.join(os.environ.get("CODEX_HOME") or tempfile.gettempdir(), f".review-turn-{key}")
if os.path.exists(marker):
    sys.exit(0)
open(marker, "w").close()
print(json.dumps({"decision": "block", "reason": REVIEW}))
