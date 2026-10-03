"""Print one command a reference behavior ran as an agent event on stdout.

The command executor records stdout as the run's events.jsonl, so this exercises the parts of check.py
that read the agent's commands and their results the way a host's record would. By default it prints a
Codex `command_execution` item; with EVENT_FORMAT=claude in the environment it prints Claude's stream-json
pair instead (an assistant `tool_use` block for Bash, then a user `tool_result` block with `is_error`). It
qualifies that parsing, not any agent's behavior.

    _event.py COMMAND OUTPUT EXIT_STATUS
"""
import json
import os
import shlex
import sys
import uuid

command, output, status = sys.argv[1:4]
if os.environ.get("EVENT_FORMAT") == "claude":
    tool_id = f"toolu_{uuid.uuid4().hex[:24]}"
    print(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tool_id, "name": "Bash", "input": {"command": command}}]}}))
    print(json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_id, "content": output, "is_error": status != "0"}]}}))
else:
    print(json.dumps({"type": "item.completed", "item": {
        "id": f"item_{uuid.uuid4().hex[:12]}", "type": "command_execution",
        "command": f"/bin/sh -lc {shlex.quote(command)}", "aggregated_output": output,
        "exit_code": int(status), "status": "completed" if status == "0" else "failed"}}))
