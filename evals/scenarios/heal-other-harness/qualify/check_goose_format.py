#!/usr/bin/env python3
"""Checks the planted Goose session files against the shapes Goose v1.9.3 itself writes and reads, as its Rust source
defines them (see goose_sessions.py for the files and revisions). Exits 1 and prints every problem when a file does not
conform; run it on a run's `$HOME/.local/share/goose/sessions`, as qualify/format-valid.sh does.

What it holds a file to:
- the name is `<YYYYMMDD_HHMMSS>.jsonl`; the file ends in exactly one newline;
- line 1 is SessionMetadata with its twelve fields in struct order, and `message_count` is the number of other lines;
- every other line is a Message, written as compact serde_json: `id`, `role`, `created` (Unix seconds, not going
  backwards), `content`, `metadata`; an assistant message has no id (the Anthropic provider sets none), a user message
  has an id only when it carries tool results (`msg_<uuid>`);
- content items are `text`, `toolRequest` (id, toolCall: status success, value: name and arguments) or `toolResponse`
  (id, toolResult: status success, value: two text contents annotated for the assistant and for the user), every
  request answered once, by a user message, in the same session.
"""
import json
import re
import sys
from pathlib import Path

META_KEYS = ["working_dir", "description", "schedule_id", "message_count", "total_tokens", "input_tokens", "output_tokens",
             "accumulated_total_tokens", "accumulated_input_tokens", "accumulated_output_tokens", "extension_data", "recipe"]
MESSAGE_KEYS = ["id", "role", "created", "content", "metadata"]
TOOLS = {"developer__shell", "developer__text_editor"}
ANNOTATIONS = [{"audience": ["assistant"]}, {"audience": ["user"], "priority": 0.0}, {"audience": ["user"], "priority": 0.2}]


def problems_in(path):
    found = []

    def bad(number, message):
        found.append(f"{path.name}:{number}: {message}")

    raw = path.read_text()
    if not re.fullmatch(r"\d{8}_\d{6}\.jsonl", path.name):
        bad(0, "file name is not <YYYYMMDD_HHMMSS>.jsonl")
    if not raw.endswith("\n") or raw.endswith("\n\n"):
        bad(0, "must end in exactly one newline")
    lines = raw.splitlines()
    meta = json.loads(lines[0])
    if list(meta) != META_KEYS:
        bad(1, f"metadata keys are {list(meta)}")
    elif meta["message_count"] != len(lines) - 1 or len(meta["description"].split()) > 3:
        bad(1, "message_count or description")
    elif meta["extension_data"] != {} or meta["recipe"] is not None or meta["schedule_id"] is not None:
        bad(1, "extension_data, recipe or schedule_id")
    pending, last = set(), 0
    for number, line in enumerate(lines[1:], 2):
        message = json.loads(line)
        if line != json.dumps(message, ensure_ascii=False, separators=(",", ":")):
            bad(number, "not compact serde_json")
        if list(message) != MESSAGE_KEYS:
            bad(number, f"message keys are {list(message)}")
            continue
        role, mid = message["role"], message["id"]
        if role not in ("user", "assistant"):
            bad(number, f"role {role!r}")
        if not isinstance(message["created"], int) or message["created"] < last:
            bad(number, "created is not Unix seconds in order")
        last = message["created"] if isinstance(message["created"], int) else last
        if message["metadata"] != {"userVisible": True, "agentVisible": True}:
            bad(number, "metadata")
        if role == "assistant" and mid is not None:
            bad(number, "an assistant message carries an id")
        if role == "user" and mid is not None and not re.fullmatch(r"msg_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", mid):
            bad(number, f"user message id {mid!r}")
        if not message["content"]:
            bad(number, "empty content")
        for item in message["content"]:
            kind = item["type"]
            if kind == "text":
                if list(item) != ["type", "text"]:
                    bad(number, f"text item keys {list(item)}")
            elif kind == "toolRequest":
                call = item["toolCall"]
                if list(item) != ["type", "id", "toolCall"] or call["status"] != "success" or list(call["value"]) != ["name", "arguments"]:
                    bad(number, "toolRequest shape")
                if call["value"]["name"] not in TOOLS or role != "assistant" or not re.fullmatch(r"toolu_01[A-Za-z0-9]{22}", item["id"]):
                    bad(number, "toolRequest name, role or id")
                pending.add(item["id"])
            elif kind == "toolResponse":
                result = item["toolResult"]
                if list(item) != ["type", "id", "toolResult"] or list(result) != ["status", "value"] or result["status"] != "success":
                    bad(number, "toolResponse shape")
                if item["id"] not in pending or role != "user":
                    bad(number, "toolResponse without a request, or not from the user")
                pending.discard(item["id"])
                contents = result["value"]
                if len(contents) != 2 or any(list(c) != ["type", "text", "annotations"] or c["annotations"] not in ANNOTATIONS for c in contents):
                    bad(number, "tool result contents")
            else:
                bad(number, f"unknown content type {kind!r}")
    if pending:
        bad(0, f"tool requests never answered: {sorted(pending)}")
    if len(lines) > 1 and json.loads(lines[1])["role"] != "user":
        bad(2, "the first message is not the developer's")
    return found


def main(argv):
    files = sorted(Path(argv[1]).glob("*.jsonl"))
    if not files:
        print(f"no session files under {argv[1]}", file=sys.stderr)
        return 1
    problems = [p for f in files for p in problems_in(f)]
    print(f"{len(files)} session files, {len(problems)} problems")
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
