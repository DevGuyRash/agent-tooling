"""Add one step a reference behavior took to the run's record (TRIAL_RECORD), the way a launcher records what its
executor did: a command with its output and exit status (or, with RECORD_OUTCOME_ONLY set, only whether it
succeeded, as some executors' records give), or an edit. A command arm's record is read like a launcher's, so this
exercises the parts of check.py that read the record, not any agent's behavior.

    record.py command COMMAND OUTPUT EXIT_STATUS
    record.py edit PATH
"""
import json
import os
import sys
from pathlib import Path


def main(kind, *args):
    path = Path(os.environ["TRIAL_RECORD"])
    record = json.loads(path.read_text()) if path.is_file() else {
        "finished": True, "actions": [], "covers": ["message", "command", "edit", "read", "load", "other"],
        "limits": ["a reference behavior keeps no session record"]}
    if kind == "command":
        command, output, status = args
        action = {"kind": "command", "command": command, "output": output, "ok": status == "0"}
        if not os.environ.get("RECORD_OUTCOME_ONLY"):
            action["exit_code"] = int(status)
    elif kind == "edit":
        (edited,) = args
        action = {"kind": "edit", "path": edited, "ok": True}
    else:
        print(f"error: unknown step {kind!r}\nhint: use command or edit", file=sys.stderr)
        return 2
    record["actions"].append(dict(action, turn=1))
    path.write_text(json.dumps(record))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
