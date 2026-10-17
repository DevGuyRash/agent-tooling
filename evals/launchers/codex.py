#!/usr/bin/env python3
"""Launcher for Codex CLI arms and judges of this repository's evals (see the split-testing skill's
references/launching.md for the contract). It writes a private ~/.codex holding only the model provider settings
it was given and the arm's instructions as AGENTS.md, runs `codex exec` (and `codex exec resume` for each
follow-up), and converts Codex's own event stream and session rollout into the trial record.

The plan gives it:
- "copy": {".launcher/host-codex.toml": "~/.codex/config.toml"}: this machine's Codex configuration, from which
  setup keeps only the model provider block and then deletes the copy, before the agent starts;
- "api_key_var": the provider's key variable (its env_key);
- "binary": "codex";
- optionally a resource at ~/.launcher/settings.json: {"config": ["key=value", ...], "args": ["--flag", ...]},
  extra configuration overrides and command-line flags (for example hooks and the flag that trusts them).
As a judge (TRIAL_SCHEMA_FILE set) it runs read-only with the schema as Codex's output schema and prints the
verdict alone on standard output.
"""
import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path

HOME = Path(os.environ.get("HOME", "/nonexistent"))
CODEX = HOME / ".codex"
STATE = HOME / ".launcher-state"
TRANSIENT = ("502 Bad Gateway", "503 Service", "failed to connect", "Connection reset", "stream disconnected",
             "timed out", "Too Many Requests", "429", "overloaded", "error sending request")


def provider_config(model: str, effort: str, host_config: str) -> str:
    """A minimal Codex config: the model and effort, the provider block of this machine's own config, and
    nothing that loads instructions, plugins, apps, memories, or web search."""
    lines = [f'model = "{model}"', f'model_reasoning_effort = "{effort}"', 'model_reasoning_summary = "detailed"',
             'web_search = "disabled"', "[features]", "plugins = false", "remote_plugin = false", "apps = false",
             "memories = false", ""]
    cfg = tomllib.loads(host_config) if host_config.strip() else {}
    name = cfg.get("model_provider")
    block = cfg.get("model_providers", {}).get(name) if name else None
    if block:
        lines.insert(4, f'model_provider = "{name}"')
        lines.append(f"[model_providers.{name}]")
        lines += [f"{k} = {json.dumps(v)}" for k, v in block.items()]
    return "\n".join(lines) + "\n"


def effort() -> str:
    """The arm's effort, or the default the old Codex driver used: high for a judge, medium otherwise."""
    return os.environ.get("TRIAL_EFFORT") or ("high" if os.environ.get("TRIAL_SCHEMA_FILE") else "medium")


def settings() -> dict:
    path = HOME / ".launcher" / "settings.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def setup() -> int:
    """Turn 0: write ~/.codex before the agent starts, refusing a file already in the way."""
    CODEX.mkdir(exist_ok=True)
    STATE.mkdir(exist_ok=True)
    for name in ("config.toml", "AGENTS.md"):
        if (CODEX / name).exists():
            print(f"launcher: {CODEX / name} is already there; refusing to overwrite it", file=sys.stderr)
            return 1
    host = HOME / ".launcher" / "host-codex.toml"
    host_text = host.read_text() if host.is_file() else ""
    if host.is_file():
        host.unlink()  # only the provider block stays, before the agent can read the rest
    (STATE / "config.toml").write_text(provider_config(os.environ["TRIAL_MODEL"], effort(), host_text))
    seed()
    return 0


def seed():
    """(Re)write the configuration and instructions before every turn, the same bytes each time."""
    (CODEX / "config.toml").write_text((STATE / "config.toml").read_text())
    instructions = os.environ.get("TRIAL_INSTRUCTIONS")
    if instructions:
        (CODEX / "AGENTS.md").write_text(Path(instructions).read_text())


def run_turn(turn: int) -> int:
    seed()
    extra = settings()
    judge = os.environ.get("TRIAL_SCHEMA_FILE")
    common = ["--skip-git-repo-check", "-s", "read-only" if judge else "danger-full-access", "-m", os.environ["TRIAL_MODEL"],
              "-c", f"model_reasoning_effort={effort()}", "--json"]
    for item in extra.get("config", []):
        common += ["-c", item]
    common += list(extra.get("args", []))
    reply = os.environ.get("TRIAL_REPLY") or str(STATE / f"reply-{turn}.md")
    if judge:
        common += ["--ephemeral", "--output-schema", judge]
    thread = (STATE / "thread").read_text().strip() if (STATE / "thread").exists() else None
    if turn == 1:
        cmd = [os.environ.get("TRIAL_BINARY", "codex"), "exec", *common, "-C", os.getcwd(), "-o", reply, "-"]
    elif thread:
        cmd = [os.environ.get("TRIAL_BINARY", "codex"), "exec", *common, "-o", reply, "resume", thread, "-"]
    else:
        print("launcher: no thread to continue", file=sys.stderr)
        return 1
    env = dict(os.environ, CODEX_HOME=str(CODEX))
    var = os.environ.get("TRIAL_API_KEY_VAR")
    if var and var in os.environ:
        env[var] = os.environ[var]
    message = Path(os.environ["TRIAL_PROMPT_FILE"]).read_bytes()
    events = STATE / f"events-{turn}.jsonl"
    with events.open("wb") as out:
        done = subprocess.run(cmd, input=message, stdout=out, stderr=subprocess.PIPE, env=env)
    sys.stderr.write(done.stderr.decode(errors="replace"))
    stream = events.read_text(errors="replace")
    if not thread:
        m = re.search(r'"type":\s*"thread\.started",\s*"thread_id":\s*"([^"]+)"', stream)
        if m:
            (STATE / "thread").write_text(m.group(1))
    if judge:
        try:
            verdict = json.loads(Path(reply).read_text())
        except (OSError, json.JSONDecodeError):
            verdict = None
        if isinstance(verdict, dict):
            print(json.dumps(verdict))
    else:
        sys.stdout.write(stream)
    write_record(turn)
    if done.returncode != 0:
        err = done.stderr.decode(errors="replace") + stream[-4000:]
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


# The main agent's items in Codex's event stream and the same items its rollout records, with their times.
ROLLOUT_KINDS = {"command_execution": "CommandExecution", "agent_message": "AgentMessage", "file_change": "FileChange",
                 "collab_tool_call": "CollabAgentToolCall"}
# Rollout items that are no action of the agent's own.
NOT_ACTIONS = ("Reasoning", "UserMessage", "HookPrompt", "SubAgentActivity")


def record_from(turn_events: list, rollout_files: list, instructions: bool, cwd: str) -> dict:
    """The trial record from Codex's own event stream, one list of events per turn, and its session rollouts, one
    list of records per file. Codex's turn.completed usage is a running total across the whole thread, so only the
    last one counts; its input_tokens already include cached ones and its output_tokens include reasoning.

    Actions take the order in which they started; one that started and never completed is kept with an unknown
    outcome. The main agent's come from the event stream, in its order. A subagent's appear only in its own rollout,
    whose first session_meta names its thread (the parent's follows it): its commands, edits, messages and other
    calls, and the skills Codex injected for it, each in the turn it started in and placed among the main agent's
    actions by when it started, after the call that started the subagent. The rollouts give the times: an item
    started when the model called it, or its duration before it completed, or when it was recorded; the main
    agent's completed items take the times its own rollout gives the same items in the same turn, in order. A skill
    Codex injected for a $name mention reached the model as a user message of its rollout."""
    main, usage, finished, thread, spawned = [], None, False, None, {}
    for turn, events in enumerate(turn_events, 1):
        finished, items, order = False, {}, []
        for e in events:
            t = e.get("type")
            if t == "thread.started":
                thread = e.get("thread_id")
            elif t == "turn.completed":
                usage, finished = e.get("usage") or {}, True
            elif t == "turn.failed":
                finished = False
            item = e.get("item") if isinstance(e.get("item"), dict) else None
            if not item or t not in ("item.started", "item.completed"):
                continue
            key = item.get("id")
            if key not in items:
                order.append(key)
            if t == "item.completed" or key not in items:
                items[key] = (t == "item.completed", item)
        for key in order:
            completed, item = items[key]
            main.append({"turn": turn, "type": item.get("type"), "actions": action(turn, item, completed), "at": None,
                         "completed": completed})
            if item.get("type") == "collab_tool_call":  # the first call naming a thread is the one that started it
                for spawned_thread in item.get("receiver_thread_ids") or []:
                    spawned.setdefault(spawned_thread, len(main) - 1)
    own = [rec for records in rollout_files if records and _session_of(records) == thread for rec in records]
    starts = sorted(s for s in (_seconds(r.get("timestamp")) for r in own if _event(r) == "task_started") if s is not None)
    times: dict = {}  # (turn, kind) -> when each item the rollout saw complete in that turn started, in order
    called, turn = _calls(own), 0
    for rec in own:
        turn += _event(rec) == "task_started"
        item = _completed(rec)
        if item and item.get("type") in ROLLOUT_KINDS.values():
            times.setdefault((turn, item["type"]), []).append(_started(rec, item, called))
    for key in times:
        times[key].sort(key=lambda s: (s is None, s or 0))
    for entry in main:  # an item the stream never saw complete has no completion in the rollout to take
        queue = times.get((entry["turn"], ROLLOUT_KINDS.get(entry["type"])), []) if entry["completed"] else []
        entry["at"] = queue.pop(0) if queue else None
    loads_by_turn, turn = {}, 0
    for rec in own:  # a skill injected into the main agent's context comes at the start of the turn it was sent in
        turn += _event(rec) == "task_started"
        name = _injected(rec)
        if name:
            loads_by_turn.setdefault(max(turn, 1), []).append({"turn": max(turn, 1), "kind": "load", "name": name, "ok": True})
    subs = []
    for records in rollout_files:
        agent = _session_of(records) if records else None
        if not agent or agent == thread:
            continue
        floor = spawned.get(agent, -1)
        called, done = _calls(records), set()
        for rec in records:
            name, item = _injected(rec), _completed(rec)
            if name:
                subs.append((_seconds(rec.get("timestamp")), floor, {"kind": "load", "agent": agent, "name": name, "ok": True}))
            elif item and item.get("type") not in NOT_ACTIONS:
                done.add(item.get("id") or item.get("call_id"))
                subs += [(_started(rec, item, called), floor, dict(a, agent=agent)) for a in _sub_actions(item)]
        for call_id, (at, call) in called.items():  # a command the model called that never completed
            if call_id not in done and call.get("name") in ("exec_command", "shell"):
                subs.append((at, floor, {"kind": "command", "agent": agent, "command": _call_command(call),
                                         "exit_code": None, "ok": None, "output": ""}))
    timed = []
    for at, floor, a in subs:
        spawn_turn = main[floor]["turn"] if 0 <= floor < len(main) else 1
        turn = spawn_turn  # never before the turn that started it
        if at is not None and starts:
            turn = max(turn, min(len(turn_events), sum(1 for s in starts if s <= at)))
        timed.append((turn, at, floor, spawn_turn, a))
    timed.sort(key=lambda s: (s[0], s[1] is None, s[1] or 0))
    actions, at_main, placed = [], 0, set()

    def opening(turn):
        if turn not in placed:  # a turn's injected skills come before anything done in it
            placed.add(turn)
            actions.extend(loads_by_turn.pop(turn, []))

    def emit(entry):
        opening(entry["turn"])
        actions.extend(entry["actions"])

    for turn, at, floor, spawn_turn, a in timed:
        def before(m) -> bool:
            """Whether the main agent's action `m` started before this one."""
            if at_main <= floor or m["turn"] < turn:
                return True
            if m["turn"] > turn:
                return False
            if at is not None and m["at"] is not None:
                return m["at"] <= at
            return turn > spawn_turn  # no time: right after the call that started it, or at the end of a later turn

        while at_main < len(main) and before(main[at_main]):
            emit(main[at_main])
            at_main += 1
        opening(turn)
        actions.append(dict(a, turn=turn))
    for entry in main[at_main:]:
        emit(entry)
    for turn in sorted(loads_by_turn):
        actions += loads_by_turn[turn]
    models = [p.get("model") for rec in own if rec.get("type") == "turn_context"
              for p in [rec.get("payload") if isinstance(rec.get("payload"), dict) else {}] if p.get("model")]
    record = {"finished": finished,
              "turns": [{"session": thread, "model": models[min(i, len(models) - 1)] if models else None,
                         "instructions": "system" if instructions else "none", "cwd": cwd}
                        for i in range(len(turn_events))],
              "actions": actions, "covers": ["message", "command", "edit", "read", "load", "other"]}
    if usage is not None:
        record["usage"] = {k: v for k, v in (("input_tokens", usage.get("input_tokens")),
                                             ("cached_input_tokens", usage.get("cached_input_tokens")),
                                             ("output_tokens", usage.get("output_tokens")),
                                             ("reasoning_tokens", usage.get("reasoning_output_tokens")))
                           if isinstance(v, (int, float))}
    listed = skills_listed(own)
    if listed is not None:
        record["listed"] = listed
    return record


def _payload(rec: dict) -> dict:
    return rec.get("payload") if isinstance(rec.get("payload"), dict) else {}


def _event(rec: dict):
    return _payload(rec).get("type") if rec.get("type") == "event_msg" else None


def _completed(rec: dict):
    """The item a rollout record says completed: an item_completed event's item, or an older exec_command_end."""
    p = _payload(rec)
    if _event(rec) == "item_completed" and isinstance(p.get("item"), dict):
        return p["item"]
    if _event(rec) == "exec_command_end":
        return dict(p, type="CommandExecution", id=p.get("call_id"))
    return None


def _calls(records: list) -> dict:
    """{call id: (when it started, the call)} for every tool call the model made in a rollout."""
    calls = {}
    for rec in records:
        p = _payload(rec)
        if (rec.get("type") == "response_item" and p.get("type") in ("function_call", "custom_tool_call")) \
                or _event(rec) == "exec_command_begin":
            calls.setdefault(p.get("call_id"), (_seconds(rec.get("timestamp")), p))
    return calls


def _call_command(call: dict) -> str:
    try:
        args = json.loads(call.get("arguments") or "{}")
    except json.JSONDecodeError:
        args = {}
    command = (args.get("cmd") or args.get("command")) if isinstance(args, dict) else None
    command = command if command is not None else call.get("command")
    return " ".join(str(c) for c in command) if isinstance(command, list) else str(command or "")


def _injected(rec: dict):
    """The skill a rollout record put into the model's context (a user message Codex sent for a $name mention)."""
    p = _payload(rec)
    if rec.get("type") != "response_item" or p.get("type") != "message" or p.get("role") != "user":
        return None
    text = content_text(p.get("content"))
    m = re.search(r"<name>\s*([^<\s]+)\s*</name>", text) if text.lstrip().startswith("<skill>") else None
    return m.group(1) if m else None


def _seconds(stamp):
    """A rollout timestamp in seconds, or None."""
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _started(rec: dict, item: dict, called: dict):
    """When a rollout item started: when the model called it, else its duration before it completed, else when it
    was recorded."""
    call = called.get(item.get("id")) or called.get(item.get("call_id"))
    if call and call[0] is not None:
        return call[0]
    done, took = _seconds(rec.get("timestamp")), item.get("duration")
    if done is not None and isinstance(took, dict) and isinstance(took.get("secs"), (int, float)):
        return done - took["secs"] - (took.get("nanos") or 0) / 1e9
    return done


def _sub_actions(item: dict) -> list:
    """A subagent's actions for one completed rollout item."""
    kind = item.get("type")
    if kind == "CommandExecution":
        command, code = item.get("command"), item.get("exit_code")
        return [{"kind": "command", "command": " ".join(str(c) for c in command) if isinstance(command, list) else str(command or ""),
                 "exit_code": code, "ok": None if code is None else str(code) == "0",
                 "output": str(item.get("aggregated_output") or item.get("stdout") or "")}]
    if kind == "FileChange":
        changes = item.get("changes")
        paths = list(changes) if isinstance(changes, dict) else [c.get("path") for c in changes or [] if isinstance(c, dict)]
        return [{"kind": "edit", "path": str(path or ""), "ok": item.get("status") != "failed"} for path in paths]
    if kind == "AgentMessage":
        text = content_text(item.get("content")) if item.get("content") is not None else str(item.get("text") or "")
        return [{"kind": "message", "role": "assistant", "text": text}] if text else []
    return [{"kind": "other", "name": str(item.get("tool") or item.get("kind") or kind), "ok": item.get("status") != "failed"}]


def _session_of(records: list):
    """The thread a rollout file belongs to: the id its first session_meta names."""
    return next((r["payload"].get("id") for r in records if r.get("type") == "session_meta" and isinstance(r.get("payload"), dict)), None)


def action(turn: int, item: dict, completed: bool = True) -> list:
    """The record's actions for one Codex item; one that only started has an unknown outcome."""
    kind = item.get("type")
    if kind == "agent_message":
        return [{"turn": turn, "kind": "message", "role": "assistant", "text": str(item.get("text", ""))}] if completed else []
    if kind == "command_execution":
        code = item.get("exit_code") if completed else None
        return [{"turn": turn, "kind": "command", "command": str(item.get("command", "")), "exit_code": code,
                 "ok": code == 0 if code is not None else None, "output": str(item.get("aggregated_output") or "")}]
    if kind == "file_change":
        ok = item.get("status") != "failed" if completed else None
        return [{"turn": turn, "kind": "edit", "path": str(c.get("path", "")), "ok": ok}
                for c in item.get("changes") or [] if isinstance(c, dict)]
    if kind in ("reasoning", "error"):
        return []
    return [{"turn": turn, "kind": "other", "name": str(item.get("tool") or kind),
             "ok": item.get("status") != "failed" if completed else None}]


def content_text(content) -> str:
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return str(content or "")


def skills_listed(rollouts: list):
    """The skills section Codex sent the model (a developer message), as {name: description}, or None."""
    listed, seen = {}, False
    for rec in rollouts:
        p = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        text = content_text(p.get("content")) if p.get("type") == "message" and p.get("role") == "developer" else ""
        if "<skills_instructions>" in text:
            seen = True
            for line in text.splitlines():  # "- <name>: <description> (file: <path>)" or "- <name> (file: <path>)"
                m = re.match(r"- (\S+?)(?::\s+(.*?))?\s*\(file: [^)]*\)\s*$", line)
                if m:
                    listed[m.group(1)] = (m.group(2) or "").strip()
    return listed if seen else None


def write_record(turn: int):
    turn_events = [read_jsonl((STATE / f"events-{n}.jsonl").read_text(errors="replace"))
                   for n in range(1, turn + 1) if (STATE / f"events-{n}.jsonl").exists()]
    files = sorted((CODEX / "sessions").rglob("rollout-*.jsonl")) if (CODEX / "sessions").is_dir() else []
    rollouts = [read_jsonl(f.read_text(errors="replace")) for f in files]
    record = record_from(turn_events, rollouts, bool(os.environ.get("TRIAL_INSTRUCTIONS")), os.getcwd())
    job = os.environ.get("TRIAL_JOB_DIR")
    record["transcripts"] = [os.path.relpath(f, job) for f in files] if job else []
    if not record["transcripts"]:
        record["limits"] = ["Codex wrote no session rollout"]
    Path(os.environ["TRIAL_RECORD"]).write_text(json.dumps(record))


def main() -> int:
    turn = int(os.environ["TRIAL_TURN"])
    if turn == 0:
        return setup()
    code = run_turn(turn)
    if turn == int(os.environ.get("TRIAL_TURNS", turn)):  # caches that hold no evidence
        for pattern in ("*.sqlite", "*.sqlite-wal", "*.sqlite-shm", "*.sqlite-journal", "models_cache.json"):
            for f in CODEX.glob(pattern):
                f.unlink(missing_ok=True)
        for d in (CODEX / ".tmp", CODEX / "skills"):
            subprocess.run(["rm", "-rf", str(d)])
    return code


if __name__ == "__main__":
    sys.exit(main())
