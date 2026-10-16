#!/usr/bin/env python3
"""Launcher for Claude Code arms and judges of this repository's evals (see the split-testing skill's
references/launching.md for the contract). It runs `claude -p` in bare mode (no hooks, plugins, memory, or
CLAUDE.md discovery) with the arm's instructions appended to the system prompt, resumes the same session for
each follow-up, and converts Claude Code's stream-json events and session transcript into the trial record.

The plan gives it "binary": "claude" and "api_key_var" (the variable holding an Anthropic API key, renamed to
ANTHROPIC_API_KEY for the CLI; "base_url" becomes ANTHROPIC_BASE_URL). Optionally a resource at
~/.launcher/settings.json: {"bare": false, "args": [...]}: without bare mode Claude Code discovers skills,
settings and memory in the run's private home, for selection trials (then hide /etc/claude-code with "hide");
"args" adds command-line flags. As a judge (TRIAL_SCHEMA_FILE set) it runs with no tools and the schema as its
JSON schema, and prints the verdict alone on standard output.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("HOME", "/nonexistent"))
STATE = HOME / ".launcher-state"
TRANSIENT = ("overloaded", "Overloaded", "529", "502", "503", "Connection error", "ECONNRESET", "rate_limit",
             "Request timed out", "fetch failed")
WRITING_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def settings() -> dict:
    path = HOME / ".launcher" / "settings.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def run_turn(turn: int) -> int:
    extra = settings()
    judge = os.environ.get("TRIAL_SCHEMA_FILE")
    mode = "bypassPermissions" if os.environ.get("TRIAL_CONFINED") == "1" else "acceptEdits"
    cmd = [os.environ.get("TRIAL_BINARY", "claude"), "-p", *([] if extra.get("bare") is False else ["--bare"]), "--output-format", "stream-json",
           "--verbose", "--model", os.environ["TRIAL_MODEL"], "--permission-mode", mode]
    if os.environ.get("TRIAL_EFFORT"):
        cmd += ["--effort", os.environ["TRIAL_EFFORT"]]
    if os.environ.get("TRIAL_INSTRUCTIONS"):
        cmd += ["--append-system-prompt-file", os.environ["TRIAL_INSTRUCTIONS"]]
    if judge:
        cmd += ["--tools", "", "--json-schema", Path(judge).read_text()]
    cmd += list(extra.get("args", []))
    session = (STATE / "session").read_text().strip() if (STATE / "session").exists() else None
    if turn > 1:
        if not session:
            print("launcher: no session to continue", file=sys.stderr)
            return 1
        cmd += ["--resume", session]
    env = dict(os.environ)
    var = os.environ.get("TRIAL_API_KEY_VAR")
    if var and os.environ.get(var):
        env["ANTHROPIC_API_KEY"] = os.environ[var]
    if os.environ.get("TRIAL_BASE_URL"):
        env["ANTHROPIC_BASE_URL"] = os.environ["TRIAL_BASE_URL"]
    if extra.get("bare") is False:
        env["CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL"] = "1"
    message = Path(os.environ["TRIAL_PROMPT_FILE"]).read_bytes()
    events = STATE / f"events-{turn}.jsonl"
    with events.open("wb") as out:
        done = subprocess.run(cmd, input=message, stdout=out, stderr=subprocess.PIPE, env=env)
    sys.stderr.write(done.stderr.decode(errors="replace"))
    turn_events = read_jsonl(events.read_text(errors="replace"))
    result = next((e for e in reversed(turn_events) if e.get("type") == "result"), {})
    init = next((e for e in turn_events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    if init.get("session_id") and not session:
        (STATE / "session").write_text(init["session_id"])
    if judge:
        verdict = result.get("structured_output")
        if not isinstance(verdict, dict):
            try:
                verdict = json.loads(result.get("result") or "")
            except (TypeError, json.JSONDecodeError):
                verdict = None
        if isinstance(verdict, dict):
            print(json.dumps(verdict))
    else:
        sys.stdout.write(events.read_text(errors="replace"))
        if isinstance(result.get("result"), str) and os.environ.get("TRIAL_REPLY"):
            Path(os.environ["TRIAL_REPLY"]).write_text(result["result"])
    write_record(turn)
    if done.returncode != 0:
        err = done.stderr.decode(errors="replace") + json.dumps(result)[:4000]
        return 75 if any(t in err for t in TRANSIENT) else done.returncode
    return 0


def read_jsonl(text: str) -> list:
    out = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def tool_output(content) -> str:
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return str(content or "")


def record_from(turn_events: list, transcripts: list, instructions: bool) -> dict:
    """The trial record from Claude Code's stream-json events, one list per turn, and the records of its session
    transcripts. Each result event's usage covers its own turn, so turns are summed; its input_tokens leave out
    cache reads and writes, which are added back; its total_cost_usd is a running total, so the last one counts."""
    actions, turns, totals, cost, finished = [], [], {}, None, False
    for turn, events in enumerate(turn_events, 1):
        results, index = {}, {}
        for e in events:
            message = e.get("message") if isinstance(e.get("message"), dict) else {}
            if e.get("type") == "user" and isinstance(message.get("content"), list):
                for b in message["content"]:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        results[b.get("tool_use_id")] = (not b.get("is_error"), tool_output(b.get("content")))
        init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
        result = next((e for e in reversed(events) if e.get("type") == "result"), None)
        models = sorted((result or {}).get("modelUsage") or {}) or ([init["model"]] if init.get("model") else [])
        turns.append({"session": init.get("session_id") or (result or {}).get("session_id"),
                      "model": models[0] if len(models) == 1 else init.get("model"),
                      "instructions": "system" if instructions else "none", "cwd": init.get("cwd")})
        for e in events:
            message = e.get("message") if isinstance(e.get("message"), dict) else {}
            if e.get("type") != "assistant" or not isinstance(message.get("content"), list):
                continue
            for b in message["content"]:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text"):
                    actions.append({"turn": turn, "kind": "message", "role": "assistant", "text": str(b["text"])})
                elif b.get("type") == "tool_use":
                    index[b.get("id")] = len(actions)
                    actions.append(tool_action(turn, b, results.get(b.get("id"))))
        finished = bool(result) and result.get("subtype") == "success" and not result.get("is_error")
        usage = (result or {}).get("usage") or {}
        for key, value in (("input_tokens", sum(usage.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens",
                                                                              "cache_creation_input_tokens"))),
                           ("cached_input_tokens", usage.get("cache_read_input_tokens") or 0),
                           ("output_tokens", usage.get("output_tokens") or 0),
                           ("reasoning_tokens", (usage.get("output_tokens_details") or {}).get("thinking_tokens") or 0)):
            if usage:
                totals[key] = totals.get(key, 0) + value
        if result and isinstance(result.get("total_cost_usd"), (int, float)):
            cost = result["total_cost_usd"]
    if cost is not None:
        totals["cost_usd"] = cost
    record = {"finished": finished, "turns": turns, "actions": actions,
              "covers": ["message", "command", "edit", "read", "load", "other"]}
    if totals:
        record["usage"] = totals
    listed = skills_listed(transcripts)
    if listed is not None:
        record["listed"] = listed
    return record


def tool_action(turn: int, block: dict, result) -> dict:
    name = str(block.get("name"))
    inp = block.get("input")
    inp = inp if isinstance(inp, dict) else {}
    ok, output = result if result else (None, "")
    if name == "Bash":
        return {"turn": turn, "kind": "command", "command": str(inp.get("command", "")), "exit_code": None, "ok": ok,
                "output": output}
    if name == "Read":
        return {"turn": turn, "kind": "read", "path": str(inp.get("file_path", "")), "ok": ok, "output": output}
    if name in WRITING_TOOLS:
        return {"turn": turn, "kind": "edit", "path": str(inp.get("file_path") or inp.get("notebook_path") or ""), "ok": ok}
    if name == "Skill":
        return {"turn": turn, "kind": "load", "name": str(inp.get("skill", "")).lstrip("/"), "ok": ok, "output": output}
    return {"turn": turn, "kind": "other", "name": name, "ok": ok, "output": output}


def skills_listed(transcripts: list):
    """The skill listing Claude Code sent the model (skill_listing attachments), as {name: description}, or None."""
    listed, seen = {}, False
    for rec in transcripts:
        att = rec.get("attachment") if isinstance(rec.get("attachment"), dict) else {}
        if att.get("type") != "skill_listing":
            continue
        seen = True
        shown = {}
        for line in str(att.get("content") or "").splitlines():  # "- <name>: <description>" or "- <name>"
            if line.startswith("- "):
                name, _, desc = line[2:].partition(": ")
                shown[name.strip()] = desc.strip()
        names = att.get("names")
        names = names if isinstance(names, list) else list(shown)
        listed.update({str(n): shown.get(str(n), "") for n in names})
    return listed if seen else None


def write_record(turn: int):
    turn_events = [read_jsonl((STATE / f"events-{n}.jsonl").read_text(errors="replace"))
                   for n in range(1, turn + 1) if (STATE / f"events-{n}.jsonl").exists()]
    root = HOME / ".claude" / "projects"
    files = sorted(root.rglob("*.jsonl")) if root.is_dir() else []
    transcripts = [r for f in files for r in read_jsonl(f.read_text(errors="replace"))]
    record = record_from(turn_events, transcripts, bool(os.environ.get("TRIAL_INSTRUCTIONS")))
    job = os.environ.get("TRIAL_JOB_DIR")
    record["transcripts"] = [os.path.relpath(f, job) for f in files] if job else []
    if not record["transcripts"]:
        record["limits"] = ["Claude Code wrote no session transcript"]
    Path(os.environ["TRIAL_RECORD"]).write_text(json.dumps(record))


def main() -> int:
    turn = int(os.environ["TRIAL_TURN"])
    if turn == 0:
        STATE.mkdir(exist_ok=True)
        return 0
    code = run_turn(turn)
    if turn == int(os.environ.get("TRIAL_TURNS", turn)):  # caches that hold no evidence
        for d in (HOME / ".cache", HOME / ".claude" / "plugins", HOME / ".claude" / "statsig"):
            subprocess.run(["rm", "-rf", str(d)])
    return code


if __name__ == "__main__":
    sys.exit(main())
