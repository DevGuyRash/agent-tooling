"""Print one command a reference behavior ran as a Codex `command_execution` event on stdout.

The command executor records stdout as the run's events.jsonl, so this exercises the parts of check.py
that read the agent's commands (run.commands) the way a Codex run's record would. It qualifies that
parsing, not any agent's behavior.

    _event.py COMMAND OUTPUT EXIT_STATUS
"""
import json
import shlex
import sys
import uuid

command, output, status = sys.argv[1:4]
print(json.dumps({"type": "item.completed", "item": {
    "id": f"item_{uuid.uuid4().hex[:12]}", "type": "command_execution",
    "command": f"/bin/sh -lc {shlex.quote(command)}", "aggregated_output": output,
    "exit_code": int(status), "status": "completed" if status == "0" else "failed"}}))
