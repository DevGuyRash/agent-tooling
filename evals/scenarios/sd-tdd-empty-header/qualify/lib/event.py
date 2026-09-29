"""Print one step of a reference behavior as agent event JSON lines on stdout.

The command executor records stdout as the run's events.jsonl, so a reference
script that reports each real step here (an edit, or a command with its actual
output and exit status) exercises the event-based measures in check.py the way
a Codex (`codex exec --json`) or Claude Code (`--output-format stream-json`)
run would. This qualifies the measure's parsing, not any agent's behavior.

    event.py codex-edit PATH
    event.py codex-run COMMAND OUTPUT EXIT_STATUS
    event.py claude-edit PATH TOOL          (TOOL: Edit or Write)
    event.py claude-run COMMAND OUTPUT EXIT_STATUS
"""
import json
import shlex
import sys
import uuid


def main(kind, *args):
    uid = uuid.uuid4().hex[:12]
    if kind == "codex-edit":
        (path,) = args
        events = [{"type": "item.completed", "item": {"id": f"item_{uid}", "type": "file_change",
                                                      "changes": [{"path": path, "kind": "update"}],
                                                      "status": "completed"}}]
    elif kind == "codex-run":
        command, output, status = args
        events = [{"type": "item.completed", "item": {"id": f"item_{uid}", "type": "command_execution",
                                                      "command": f"/bin/sh -lc {shlex.quote(command)}",
                                                      "aggregated_output": output, "exit_code": int(status),
                                                      "status": "completed" if status == "0" else "failed"}}]
    elif kind == "claude-edit":
        path, tool = args
        events = [{"type": "assistant", "message": {"content": [
                      {"type": "tool_use", "id": f"toolu_{uid}", "name": tool, "input": {"file_path": path}}]}},
                  {"type": "user", "message": {"content": [
                      {"type": "tool_result", "tool_use_id": f"toolu_{uid}", "content": "ok", "is_error": False}]}}]
    elif kind == "claude-run":
        command, output, status = args
        text = output if status == "0" else f"Exit code {status}\n{output}"
        events = [{"type": "assistant", "message": {"content": [
                      {"type": "tool_use", "id": f"toolu_{uid}", "name": "Bash",
                       "input": {"command": command, "description": "Run the tests"}}]}},
                  {"type": "user", "message": {"content": [
                      {"type": "tool_result", "tool_use_id": f"toolu_{uid}", "content": text,
                       "is_error": status != "0"}]}}]
    else:
        print(f"error: unknown event kind {kind!r}\nhint: use codex-edit, codex-run, claude-edit, or claude-run",
              file=sys.stderr)
        return 2
    for event in events:
        print(json.dumps(event))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
