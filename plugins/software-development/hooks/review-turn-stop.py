#!/usr/bin/env python3
"""Stop hook: once per turn that changed its repository, ask for a review of the work before the turn ends.

It acts only where the harness's stop event names the turn (a turn_id); where it does not, the hook does nothing.
In trials the review helped a GPT model at low effort; with a Claude model it gained little and hurt clean
reports."""
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


TIME_KEYS = ("timestamp", "time", "ts", "created_at", "createdAt")


def _names_turn(value, turn, depth=0) -> bool:
    """Whether an object, or one nested in it (three levels at most), names this turn in a turn-id field."""
    if not isinstance(value, dict) or depth > 3:
        return False
    if any(k.replace("_", "").lower() == "turnid" and v == turn for k, v in value.items()):
        return True
    return any(_names_turn(v, turn, depth + 1) for v in value.values())


def turn_start():
    """The first whole second after this turn began: the earliest time on a record of the session's transcript that
    names the turn in a turn-id field, or None. A record names its turn only once the turn has begun, so this is never
    before the turn's start. Git compares commit times in whole seconds, so rounding up keeps a commit from just before
    the turn out of it."""
    path = data.get("transcript_path")
    if not isinstance(path, str) or not os.path.isfile(path):
        return None
    turn, earliest = data["turn_id"], None
    try:
        with open(path, encoding="utf-8", errors="replace") as transcript:
            for line in transcript:
                if str(turn) not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not _names_turn(record, turn):
                    continue
                stamp = next((record[k] for k in TIME_KEYS if isinstance(record.get(k), str)), None)
                try:
                    when = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None
                except ValueError:
                    continue
                if when and when.tzinfo and (earliest is None or when < earliest):
                    earliest = when
    except OSError:
        return None
    return (earliest.replace(microsecond=0) + datetime.timedelta(seconds=1)).isoformat() if earliest else None


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
# The user's cache directory outlives each stop of the turn, wherever the harness runs the hook.
cache = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache"), "review-turn")
try:
    os.makedirs(cache, exist_ok=True)
except OSError:
    cache = tempfile.gettempdir()
marker = os.path.join(cache, f".review-turn-{key}")
if os.path.exists(marker):
    sys.exit(0)
try:
    open(marker, "w").close()
except OSError:  # without its marker the review would be asked at every stop of the turn
    sys.exit(0)
print(json.dumps({"decision": "block", "reason": REVIEW}))
