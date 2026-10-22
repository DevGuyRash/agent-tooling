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


def _time(obj):
    """The time an object carries in one of TIME_KEYS, as an aware datetime, or None."""
    stamp = next((obj[k] for k in TIME_KEYS if isinstance(obj.get(k), str)), None)
    try:
        when = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None
    except ValueError:
        return None
    return when if when and when.tzinfo else None


def _bodies(record):
    """The record and the objects that are its own body: each object directly in it, or in a list directly in it. A
    turn named deeper is a reference to it from some other content, not the record's own turn."""
    yield record
    for value in record.values():
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict):
                yield item


def turn_start():
    """The first whole second after this turn began: the earliest time on a record of the session's transcript whose
    own body names the turn in a turn-id field, the time taken from that body or else the record, or None. A transcript
    that names a turn in a record's body before the turn begins would move the start earlier and could take an older
    commit for the turn's work; that asks for one review more, never one fewer. Git compares commit times in whole
    seconds, so rounding up keeps a commit from just before the turn out of it."""
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
                if not isinstance(record, dict):
                    continue
                for body in _bodies(record):
                    if any(k.replace("_", "").lower() == "turnid" and v == turn for k, v in body.items()):
                        when = _time(body) or _time(record)
                        if when and (earliest is None or when < earliest):
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
# A turn id may be numbered within its session, so the session names the marker too.
key = "-".join(str(data.get(k)) for k in ("session_id", "turn_id") if data.get(k)).replace("/", "_") or "session"
# The user's cache directory outlives each stop of the turn, wherever the harness runs the hook.
cache = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache"), "review-turn")
try:
    os.makedirs(cache, exist_ok=True)
except OSError:
    try:
        cache = tempfile.gettempdir()
    except (OSError, ValueError):  # nowhere to keep a marker: without one the review would be asked at every stop
        sys.exit(0)
marker = os.path.join(cache, f".review-turn-{key}")
if os.path.exists(marker):
    sys.exit(0)
try:
    open(marker, "w").close()
except OSError:  # without its marker the review would be asked at every stop of the turn
    sys.exit(0)
print(json.dumps({"decision": "block", "reason": REVIEW}))
