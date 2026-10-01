#!/usr/bin/env python3
"""Evidence gatherer for a Self-Healing pass: extraction, not interpretation.

Finds session logs from Codex, Claude Code, and Gemini CLI for a time window, and writes an
output directory an executor can read directly:

    index.md              one row per session: host, id, Claude's own subagent id where it has
                           one, start/end, cwd, message/tool-call counts, whether it is a
                           subagent/side thread or an archived one, size, and the paths of its
                           readable transcript and its raw log
    sessions/HOST-NAME.md  a faithful, timestamped transcript of that session, with a raw
                           file:line reference on every line: user messages, agent messages,
                           tool calls with their commands or arguments, tool results (trimmed
                           if long, with a note pointing at the raw file and line),
                           compactions, and any record type this script does not render as one
                           of those, as a one-line (or, for a high-volume type, one aggregated)
                           note naming its type and raw location -- never silently dropped. The
                           file name comes from the raw log file's own identity, not from the
                           id inside its records, because that id is not always unique (a
                           Claude subagent transcript carries its parent's sessionId).
    workspace.md           for each distinct working directory the sessions used that is a git
                           repository: its branches (merged or not into its default branch),
                           worktrees, and stashes; plus scheduled or recurring automations this
                           machine can list for the hosts and the OS -- facts only, no verdicts

It does no classification, ranking, scoring, or keyword matching of meaning: no "corrections",
"nudges", "stalls", or residue verdicts. Reading what the evidence means is the executor's job.
It masks obvious secrets (tokens, keys, bearer headers, basic/URL credentials) in everything it
writes, while leaving a bare 40- or 64-character hex string (a git SHA, a sha256 digest) alone,
since that is evidence a pass needs to check state, not a secret.

    gather.py [--since 7d|YYYY-MM-DD] [--until YYYY-MM-DD] [--out DIR] [--force]
              [--root HOST=PATH ...] [--max-chars N]

With no --out, output goes to a new private (mode 0700) temporary directory, printed on
completion -- never the current directory, which risks landing transcripts in a git worktree.
An explicit --out that already exists and is non-empty is refused unless --force, so a rerun
cannot silently mix an earlier run's files with this one's.

Each host's log root defaults to that host's own convention, honoring its home override where
it has one:

    codex   ${CODEX_HOME:-~/.codex}/sessions and .../archived_sessions (rollout-*.jsonl)
    claude  ${CLAUDE_CONFIG_DIR:-~/.claude}/projects (*.jsonl, plus */subagents/*.jsonl)
    gemini  ${GEMINI_CLI_HOME:-~}/.gemini/tmp, or .../.cache/.gemini/tmp under macOS Seatbelt
            (SANDBOX=sandbox-exec) (*/chats/*.json[l], plus */chats/*/*.json[l])

Any host's default can also be overridden with --root, e.g.
--root codex=/mnt/other-home/.codex/sessions.

A host or OS surface this script has no reader for is not silently skipped: read that host's
own session files directly, the way this script's own references/running-passes.md describes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

UTC = dt.timezone.utc
HOSTS = ("codex", "claude", "gemini")

# ---------------------------------------------------------------- secret masking

HEXRUN = re.compile(r"^[0-9a-fA-F]+$")

# A negative lookbehind on every prefixed alternative keeps a prefix from matching mid-word
# (e.g. the "sk-" in "task-management" or "ask-for-confirmation"): it must start at a token
# boundary. These are all anchored by a rare literal prefix, so they cost no more than one
# pass over the text.
SPECIFIC_SECRETS = re.compile(
    r"(?<![A-Za-z0-9_])(sk-[A-Za-z0-9_-]{12,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|xox[abpr]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|AIza[0-9A-Za-z_-]{35}"
    r"|glpat-[0-9A-Za-z_-]{15,}"
    r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r"|(?i:bearer\s+(?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{10,})"
    r"|(?i:basic\s+(?=[A-Za-z0-9+/=]*\d)[A-Za-z0-9+/=]{10,})"
    r"|(?i:(?:api[_-]?key|secret|token|password)\s*[:=]\s*[\"']?[^\s\"']{6,}))"
)
# The generic catch-all is a PLAIN quantified char class with no lookahead: on a long run of
# one repeated character (common in build output -- padding, separators, progress bars) an
# unanchored lookahead-based alternative re-tries its lookahead at every position, which is
# quadratic in the run's length (40k chars measured at ~2s; a multi-MB line would hang the
# whole gather run). A plain "{40,}" match is linear regardless of content, so the "needs a
# digit and a letter" and "leave a bare 40/64-char hex run alone" checks move into the
# replacement callback instead of the pattern.
GENERIC_LONG_RUN = re.compile(r"[A-Za-z0-9+_=-]{40,}")
# scheme://user:pass@host -- URL userinfo credentials, a separate pattern because the generic
# rule above never sees the "://" context and the password half is often short. The scheme is
# capped at 16 chars (real ones are a handful of letters, e.g. "postgres", "https") rather than
# left as an unbounded "*": on a long run of scheme-like characters with no "://" anywhere (an
# unmatched prefix), an unbounded quantifier before a required literal is retried from every
# position and is quadratic in the run's length -- 100k chars measured at ~12.5s with "*".
URL_CREDS = re.compile(r"([A-Za-z][A-Za-z0-9+.-]{0,15}://)([^/\s:@]+):([^/\s@]+)@")


def _mask_generic(m: re.Match) -> str:
    s = m.group(0)
    if HEXRUN.fullmatch(s) and len(s) in (40, 64):
        return s  # a bare git SHA or sha256 digest: evidence, not a secret
    if any(c.isdigit() for c in s) and any(c.isalpha() for c in s):
        return "[masked]"
    return s  # a plain word or a uniform run (all letters, or all digits, or all punctuation)


def mask(text) -> str:
    """Replace obvious secret-shaped substrings; never a judgment about the surrounding text."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = json.dumps(text, default=str, ensure_ascii=False)
    text = URL_CREDS.sub(r"\1[masked]@", text)
    text = SPECIFIC_SECRETS.sub("[masked]", text)
    return GENERIC_LONG_RUN.sub(_mask_generic, text)


def trim(text, limit: int, ref: str) -> str:
    """Mask, then cut to `limit` chars -- but bound *what* gets masked to `limit` plus a
    margin, not however much text a huge command output or MCP result happens to contain: the
    rest is discarded by the cut regardless, so scanning it first only wastes time (the masking
    regexes' cost is otherwise unbounded in the input size)."""
    if not isinstance(text, str):
        text = mask(text)  # dict/list/etc.: mask() does its own (usually short) json.dumps
        text = " ".join(text.split())
        return text if len(text) <= limit else text[:limit].rstrip() + f"... [trimmed; full text at {ref}]"
    was_long = len(text) > limit + 200
    # The margin (not just `limit` raw chars) gives the masking patterns enough trailing
    # context to fully match a secret that starts near the cutoff, so truncation can happen
    # *after* masking without splitting a token mid-match.
    buffer = " ".join(text[: limit + 200].split())
    masked = mask(buffer)
    if not was_long and len(masked) <= limit:
        return masked
    return masked[:limit].rstrip() + f"... [trimmed; full text at {ref}]"


def stamp(ts):
    """Parse an epoch number or ISO-ish string into an aware UTC datetime, or None."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        try:
            return dt.datetime.fromtimestamp(ts / 1000 if ts > 10_000_000_000 else ts, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def iso(ts_dt) -> str:
    return ts_dt.isoformat(timespec="seconds") if ts_dt else ""


def parse_when(value, default=None):
    if not value:
        return default
    m = re.fullmatch(r"(\d+)d", value)
    if m:
        return dt.datetime.now(UTC) - dt.timedelta(days=int(m.group(1)))
    try:
        # A manual "Z" swap, not native fromisoformat() "Z" support, because that is a 3.11+
        # feature and this script's compatibility line promises 3.9+.
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit(
            f"error: invalid --since/--until value {value!r}\n"
            "hint: use Nd (e.g. 7d) or an ISO date/time, e.g. 2026-01-01 or 2026-01-01T00:00:00Z"
        )
    # A naive value is assumed UTC; an already-offset value keeps its own offset instead of
    # being silently relabeled as UTC (which would shift the instant it names).
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def safe_name(value) -> str:
    """Sanitize any value (not just a well-behaved str -- drifted logs put ints, None, or other
    JSON scalars where an id is expected) into a filesystem-safe fragment."""
    text = str(value) if value not in (None, "") else "unknown"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "unknown"


def short_hash(value: str) -> str:
    return hashlib.sha1(str(value).encode("utf-8", "surrogateescape")).hexdigest()[:8]


# ---------------------------------------------------------------- default log roots

def default_root(host: str) -> Path:
    if host == "codex":
        base = os.environ.get("CODEX_HOME")
        return (Path(base).expanduser() if base else Path.home() / ".codex") / "sessions"
    if host == "claude":
        base = os.environ.get("CLAUDE_CONFIG_DIR")
        return (Path(base).expanduser() if base else Path.home() / ".claude") / "projects"
    if host == "gemini":
        # Gemini CLI honors GEMINI_CLI_HOME as a home-directory override (checked against its
        # bundled source), and under macOS Seatbelt (SANDBOX=sandbox-exec) it writes to
        # ~/.cache/.gemini instead of ~/.gemini regardless of that override. --root gemini=PATH
        # covers any other relocation.
        base = os.environ.get("GEMINI_CLI_HOME")
        home = Path(base).expanduser() if base else Path.home()
        gemini_dir = (home / ".cache" / ".gemini") if os.environ.get("SANDBOX") == "sandbox-exec" else (home / ".gemini")
        return gemini_dir / "tmp"
    raise ValueError(host)


def automations_root(codex_sessions_root=None) -> Path:
    # Prefer a sibling of the actual (possibly --root-overridden) codex sessions root, so
    # relocating one relocates the other; fall back to CODEX_HOME/default only when the
    # sessions root doesn't look like the conventional "<codex home>/sessions" layout.
    if codex_sessions_root is not None:
        p = Path(codex_sessions_root)
        if p.name == "sessions":
            return p.parent / "automations"
    base = os.environ.get("CODEX_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".codex") / "automations"


# ---------------------------------------------------------------- one transcript entry

class Entry:
    __slots__ = ("ts", "kind", "text", "ref")

    def __init__(self, ts, kind, text, ref):
        self.ts, self.kind, self.text, self.ref = ts, kind, text, ref


class Session:
    def __init__(self, host, path):
        self.host = host
        self.path = path
        self.id = path.stem
        self.agent_id = ""  # Claude's per-subagent id; distinct from the shared sessionId
        self.cwd = ""
        self.subagent = False
        self.archived = False
        self.out_name = ""  # assigned by assign_output_names(); the file this session writes to
        self.start = self.end = None
        self.entries = []
        self.user_messages = self.agent_messages = self.tool_calls = 0

    def set_cwd(self, value):
        # A drifted or malformed record can put a list, dict, or number where cwd should be a
        # string; keep the last good value rather than letting a bad one break Path(s.cwd) later.
        if isinstance(value, str) and value:
            self.cwd = value

    def touch(self, ts):
        t = stamp(ts)
        if t:
            self.start = t if not self.start or t < self.start else self.start
            self.end = t if not self.end or t > self.end else self.end
        return t

    def add(self, ts, kind, text, ref):
        t = self.touch(ts)
        self.entries.append(Entry(iso(t), kind, text, ref))
        if kind == "user":
            self.user_messages += 1
        elif kind == "agent":
            self.agent_messages += 1
        elif kind == "tool_call":
            self.tool_calls += 1


def _text(content) -> str:
    """Best-effort plain text from a content field: a string, or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if isinstance(b.get("text"), str):
                    parts.append(b["text"])
            elif isinstance(b, str):
                parts.append(b)
        return "".join(parts)
    return "" if content is None else str(content)


# ---------------------------------------------------------------- Codex reader

# item_completed item types this script renders as one of the four faithful categories.
# Anything else -- Reasoning, SubAgentActivity, EnteredReviewMode/ExitedReviewMode, and any
# item type Codex introduces after this script was written -- falls through to the generic
# one-line note below, so a harness change never disappears silently.
CODEX_ITEM_ROLE = {
    "UserMessage": "user",
    "AgentMessage": "agent",
    "CommandExecution": "tool_call",
    "FileChange": "tool_call",
    "McpToolCall": "tool_call",
    "Plan": "tool_call",
    "WebSearch": "tool_call",
    "ImageView": "tool_call",
    "ContextCompaction": "compaction",
    # A newer rollout format's own exec/web-search/sleep events: a terse item_completed marker
    # (kind, duration, and -- for web.search -- query/action/results) with no twin elsewhere.
    "Extension": "tool_call",
}

# Top-level record types that are Codex's own turn/token bookkeeping, not conversation
# content. Known and deliberately excluded, unlike an unrecognized type, which always gets a
# note. "response_item" -- the lower-level model-API replay stream -- is NOT in this set: on
# real logs some of its function_call/agent_message content has no "event_msg"/"item_completed"
# twin, so it is counted and noted per type at the end of the file instead of skipped outright.
CODEX_SKIP_TOP = {"turn_context", "token_usage_record"}
CODEX_SKIP_EVENT = {"token_count"}

# Several response_item payload kinds carry a tool/command call's real content with no
# guarantee of an item_completed twin:
#   - custom_tool_call/-output: a newer "unified exec" channel (freeform code calling
#     tools.exec_command(...), tools.apply_patch(...), etc.).
#   - function_call/-output: the classic structured tool-call channel (name + a JSON
#     "arguments" string, e.g. exec_command's {"cmd": "..."}), still in use alongside the
#     newer channel.
# Some of those do carry an item_completed/CommandExecution twin sharing the same call_id/id
# (genuinely redundant detail, already rendered more richly via that item), but on real logs
# most do not -- a rollout can freely mix the two, and a CommandExecution item that *is* present
# is often unrelated startup housekeeping (an automatic context read), not a twin of any
# particular call at all. So the check below is per call_id against the rollout's own
# CommandExecution ids, not a whole-file "does this rollout have any CommandExecution at all"
# flag -- that cruder check under-renders real mixed-format sessions (confirmed against
# rollouts on this machine, see the gather task's survey) by treating every call in the file as
# redundant the moment a single, unrelated CommandExecution item shows up anywhere in it.
#   - web_search_call carries no call_id/id at all on this machine's rollouts (so it can never
#     match a CommandExecution id -- it always renders in full, the same as an Extension item).
CODEX_RESPONSE_ITEM_ROLE_WITHOUT_COMMAND_EXECUTION = {
    "custom_tool_call": "tool_call",
    "custom_tool_call_output": "tool_result",
    "function_call": "tool_call",
    "function_call_output": "tool_result",
    "web_search_call": "tool_call",
}


def codex_item_text(kind: str, item: dict, ref: str, limit: int) -> str:
    if kind in ("UserMessage", "AgentMessage"):
        return trim(_text(item.get("content")), limit, ref)
    if kind == "CommandExecution":
        cmd = item.get("command")
        cmd = " ".join(cmd) if isinstance(cmd, list) else str(cmd or "")
        head = f"$ {cmd} (cwd={item.get('cwd') or '?'}, exit={item.get('exit_code')})"
        out = item.get("aggregated_output") or ""
        return trim(head + ("\n" + out if out else ""), limit, ref)
    if kind == "FileChange":
        changes = item.get("changes") or {}
        paths = list(changes.keys()) if isinstance(changes, dict) else [str(changes)]
        head = f"apply_patch: {', '.join(paths) or '(no paths)'} (status={item.get('status')})"
        out = item.get("stdout") or ""
        return trim(head + ("\n" + out if out else ""), limit, ref)
    if kind == "McpToolCall":
        args = mask(item.get("arguments"))
        head = f"mcp {item.get('server')}.{item.get('tool')}({args}) status={item.get('status')}"
        out = item.get("result") or item.get("error") or ""
        return trim(head + ("\n" + str(out) if out else ""), limit, ref)
    if kind == "Plan":
        return trim("update_plan: " + str(item.get("text") or ""), limit, ref)
    if kind == "WebSearch":
        return trim(f"web_search: {item.get('query')}", limit, ref)
    if kind == "ImageView":
        return trim(f"view_image: {item.get('path')}", limit, ref)
    if kind == "Extension":
        ext_kind = item.get("kind") or "(unknown)"
        detail = {k: v for k, v in item.items() if k not in ("type", "kind", "id")}
        head = f"extension {ext_kind}"
        return trim(head + (f": {json.dumps(detail, default=str, ensure_ascii=False)}" if detail else ""),
                    limit, ref)
    return trim(json.dumps(item, default=str, ensure_ascii=False), limit, ref)


def codex_response_item_text(kind: str, payload: dict, ref: str, limit: int) -> str:
    """Render the response_item payload kinds that CODEX_RESPONSE_ITEM_ROLE_WITHOUT_COMMAND_
    EXECUTION covers. custom_tool_call's real "input" is a freeform code/text snippet (e.g. a
    JS-shaped `tools.exec_command({"cmd": "..."})` call, or an apply_patch body) rather than a
    clean structured argument -- extracting a specific sub-field out of it would be fragile
    across Codex versions, so the whole snippet is rendered (masked and trimmed like everything
    else), which is where the actual command text lives. function_call's "arguments" is already
    a compact JSON string (e.g. exec_command's {"cmd": "..."}), so it is rendered the same way,
    uninterpreted, rather than parsed for a specific field -- consistent with this reader's
    "extraction, not interpretation" rule and robust to Codex adding or renaming argument keys."""
    if kind == "custom_tool_call":
        name = payload.get("name") or "custom_tool_call"
        raw = payload.get("input")
        body = raw if isinstance(raw, str) else (_text(raw) if raw is not None else "")
        head = f"exec({name})"
        return trim(f"{head}: {body}" if body else head, limit, ref)
    if kind == "custom_tool_call_output":
        body = _text(payload.get("output"))
        return trim(f"exec result: {body}" if body else "exec result (no output)", limit, ref)
    if kind == "function_call":
        name = payload.get("name") or "function_call"
        raw = payload.get("arguments")
        body = raw if isinstance(raw, str) else (_text(raw) if raw is not None else "")
        return trim(f"{name}({body})" if body else f"{name}()", limit, ref)
    if kind == "function_call_output":
        raw = payload.get("output")
        body = raw if isinstance(raw, str) else _text(raw)
        return trim(f"call result: {body}" if body else "call result (no output)", limit, ref)
    if kind == "web_search_call":
        detail = {k: v for k, v in payload.items() if k not in ("type",)}
        return trim(f"web_search_call: {json.dumps(detail, default=str, ensure_ascii=False)}" if detail
                    else "web_search_call", limit, ref)
    return trim(json.dumps(payload, default=str, ensure_ascii=False), limit, ref)


def _codex_command_execution_ids(path: Path) -> set:
    """Pre-scan: the "id" of every item_completed/CommandExecution item in this rollout. Cheap
    and separate from the main pass below so that pass can decide, per response_item record,
    whether a custom_tool_call/-output's own call_id already has a CommandExecution twin
    somewhere in the file (redundant detail, left to the aggregate note) or not (the only record
    of what ran, rendered in full) -- see CODEX_RESPONSE_ITEM_ROLE_WITHOUT_COMMAND_EXECUTION."""
    ids = set()
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(o, dict) or o.get("type") != "event_msg":
                    continue
                p = o.get("payload")
                if not isinstance(p, dict) or p.get("type") != "item_completed":
                    continue
                item = p.get("item")
                if isinstance(item, dict) and item.get("type") == "CommandExecution":
                    idv = item.get("id")
                    if isinstance(idv, str) and idv:
                        ids.add(idv)
    except OSError:
        pass
    return ids


def read_codex(path: Path, limit: int) -> Session:
    s = Session("codex", path)
    seen_session_meta = False
    command_execution_ids = _codex_command_execution_ids(path)
    response_item_counts = {}  # payload type -> [count, first lineno, last lineno]
    with path.open(encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            ref = f"{path}:{lineno}"
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                s.add(None, "note", f"unparseable line ({ref})", ref)
                continue
            try:
                if not isinstance(o, dict):
                    s.add(None, "note", f"unrecognized record shape -- see {ref}", ref)
                    continue
                t = o.get("type")
                ts = o.get("timestamp")
                if t == "response_item":
                    p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
                    it = p.get("type", "(no type)")
                    call_id = p.get("call_id")
                    has_twin = isinstance(call_id, str) and call_id in command_execution_ids
                    role = (None if has_twin else
                            CODEX_RESPONSE_ITEM_ROLE_WITHOUT_COMMAND_EXECUTION.get(it))
                    if role:
                        # No item_completed/CommandExecution in this rollout shares this call's
                        # id, so this custom_tool_call/-output is the only record of what ran --
                        # render it in full instead of folding it into the aggregate note below.
                        s.add(ts, role, codex_response_item_text(it, p, ref, limit), ref)
                    else:
                        # Counted, not rendered per-record: see the aggregated note emitted
                        # below (redundant with an item_completed twin sharing this call's id,
                        # or not a kind this script renders in full at all).
                        entry = response_item_counts.setdefault(it, [0, lineno, lineno])
                        entry[0] += 1
                        entry[2] = lineno
                elif t == "session_meta":
                    p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
                    if not seen_session_meta:
                        # A forked or resumed rollout can carry more than one session_meta
                        # record; the first one is this thread's own identity.
                        s.set_cwd(p.get("cwd"))
                        s.id = p.get("id", s.id)
                        src = p.get("source")
                        s.subagent = bool(isinstance(src, dict) and src.get("subagent")) or (
                            isinstance(src, str) and "subagent" in src
                        )
                        seen_session_meta = True
                    s.touch(ts)
                elif t == "compacted":
                    s.add(ts, "compaction", "compaction (session summarized)", ref)
                elif t in CODEX_SKIP_TOP:
                    continue
                elif t == "event_msg":
                    p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
                    et = p.get("type")
                    if et in CODEX_SKIP_EVENT:
                        continue
                    if et != "item_completed":
                        s.add(ts, "note", f"type={et} -- see {ref}", ref)
                        continue
                    item = p.get("item") if isinstance(p.get("item"), dict) else {}
                    kind = item.get("type")
                    role = CODEX_ITEM_ROLE.get(kind)
                    if role is None:
                        s.add(ts, "note", f"type=item_completed/{kind} -- see {ref}", ref)
                        continue
                    s.add(ts, role, codex_item_text(kind, item, ref, limit), ref)
                else:
                    s.add(ts, "note", f"type={t} -- see {ref}", ref)
            except Exception as exc:  # a drifted/malformed record must not sink the whole run
                s.add(None, "note", f"error reading record ({exc.__class__.__name__}: {exc}) -- see {ref}", ref)
    for it, (count, first, last) in sorted(response_item_counts.items()):
        rng = f"{path}:{first}" if first == last else f"{path}:{first}-{last}"
        s.add(None, "note",
              f"response_item/{it}: {count} record(s) not individually rendered "
              f"(redundant with item_completed unless noted otherwise) -- see {rng}", rng)
    return s


# ---------------------------------------------------------------- Claude Code reader

def _nonblank_text(value) -> str:
    """A str field is expected here, but a drifted record can carry null or a list instead;
    treat anything that isn't a non-blank string as blank rather than crashing on .strip()."""
    return value if isinstance(value, str) and value.strip() else ""


def read_claude(path: Path, limit: int) -> Session:
    s = Session("claude", path)
    s.subagent = "subagents" in path.parts
    with path.open(encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            ref = f"{path}:{lineno}"
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                s.add(None, "note", f"unparseable line ({ref})", ref)
                continue
            try:
                if not isinstance(o, dict):
                    s.add(None, "note", f"unrecognized record shape -- see {ref}", ref)
                    continue
                t = o.get("type")
                ts = o.get("timestamp")
                s.set_cwd(o.get("cwd"))
                sid = o.get("sessionId")
                if isinstance(sid, str) and sid:
                    s.id = sid
                aid = o.get("agentId")
                if isinstance(aid, str) and aid:
                    s.agent_id = aid
                if o.get("isSidechain"):
                    s.subagent = True
                if t == "system":
                    if "compact" in str(o.get("subtype", "")):
                        s.add(ts, "compaction", "compaction (session summarized)", ref)
                    else:
                        s.add(ts, "note", f"type=system/{o.get('subtype')} -- see {ref}", ref)
                    continue
                if t not in ("user", "assistant"):
                    s.add(ts, "note", f"type={t} -- see {ref}", ref)
                    continue
                message = o.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                tags = []
                if o.get("isMeta"):
                    tags.append("meta")
                if o.get("isCompactSummary"):
                    tags.append("compact summary")
                tag = f" ({', '.join(tags)})" if tags else ""
                before = len(s.entries)
                if t == "user":
                    if isinstance(content, str):
                        if content.strip():
                            s.add(ts, "user", trim(content, limit, ref), ref)
                    elif isinstance(content, list):
                        for b in content:
                            if not isinstance(b, dict):
                                s.add(ts, "note", f"unrecognized user content block shape -- see {ref}", ref)
                            elif b.get("type") == "text" and _nonblank_text(b.get("text")):
                                s.add(ts, "user", trim(b["text"], limit, ref) + tag, ref)
                            elif b.get("type") == "tool_result":
                                head = f"tool result (id={b.get('tool_use_id')}, error={bool(b.get('is_error'))})"
                                body = trim(_text(b.get("content")), limit, ref)
                                s.add(ts, "tool_result", f"{head}: {body}", ref)
                            elif b.get("type") != "text":  # a non-text, non-tool_result block, e.g. an image
                                s.add(ts, "note", f"user content block type={b.get('type')} -- see {ref}", ref)
                    elif content:
                        s.add(ts, "note", f"unrecognized user content shape -- see {ref}", ref)
                else:  # assistant
                    if isinstance(content, list):
                        for b in content:
                            if not isinstance(b, dict):
                                s.add(ts, "note", f"unrecognized assistant content block shape -- see {ref}", ref)
                                continue
                            bt = b.get("type")
                            if bt == "text" and _nonblank_text(b.get("text")):
                                s.add(ts, "agent", trim(b["text"], limit, ref) + tag, ref)
                            elif bt == "tool_use":
                                args = mask(b.get("input") or {})
                                s.add(ts, "tool_call", trim(f"{b.get('name')}({args})", limit, ref), ref)
                            elif bt != "text":
                                s.add(ts, "note", f"assistant content block type={bt} -- see {ref}", ref)
                    elif content:
                        s.add(ts, "note", f"unrecognized assistant content shape -- see {ref}", ref)
                if len(s.entries) == before:
                    # A recognized record whose content was empty or blank still gets one line,
                    # so a genuinely empty message is distinguishable from a missed record.
                    s.add(ts, "note", f"{t} record had no renderable content -- see {ref}", ref)
            except Exception as exc:  # a drifted/malformed record must not sink the whole run
                s.add(None, "note", f"error reading record ({exc.__class__.__name__}: {exc}) -- see {ref}", ref)
    return s


# ---------------------------------------------------------------- Gemini CLI reader

def _gemini_cwd(path: Path) -> str:
    # .project_root sits beside the "chats" directory, above the session file itself:
    # <projectTempDir>/.project_root and <projectTempDir>/chats/session-*.json[l] (one level
    # deeper again for a subagent chat under chats/<parentSessionId>/). It is only written for
    # some project temp directories on this machine, so cwd may still end up blank.
    for root_file in (path.parent.parent / ".project_root", path.parent.parent.parent / ".project_root"):
        if root_file.is_file():
            try:
                return root_file.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                pass
            break
    return ""


def _render_gemini_messages(s: Session, messages, path: Path, limit: int, ref_prefix: str) -> None:
    if not isinstance(messages, list):
        s.add(None, "note", f"unrecognized messages shape -- see {ref_prefix}", ref_prefix)
        return
    for i, msg in enumerate(messages):
        ref = f"{ref_prefix}#msg{i}"
        if not isinstance(msg, dict):
            s.add(None, "note", f"unrecognized message shape -- see {ref}", ref)
            continue
        try:
            ts, kind = msg.get("timestamp"), msg.get("type")
            text = _text(msg.get("content"))
            before = len(s.entries)
            if kind == "user":
                if text.strip():
                    s.add(ts, "user", trim(text, limit, ref), ref)
            elif kind in ("gemini", "model", "assistant"):
                if text.strip():
                    s.add(ts, "agent", trim(text, limit, ref), ref)
                for call in msg.get("toolCalls") or []:
                    if not isinstance(call, dict):
                        s.add(ts, "note", f"unrecognized toolCalls entry shape -- see {ref}", ref)
                        continue
                    args = mask(call.get("args") or {})
                    head = f"{call.get('name')}({args}) status={call.get('status')}"
                    out = call.get("result")
                    s.add(ts, "tool_call", trim(head + (f"\n{out}" if out else ""), limit, ref), ref)
            else:
                s.add(ts, "note", f"type={kind} -- see {ref}", ref)
            if len(s.entries) == before:
                # A recognized message with no text and no tool calls still gets one line.
                s.add(ts, "note", f"{kind} message had no renderable content -- see {ref}", ref)
        except Exception as exc:  # a drifted/malformed message must not sink the whole run
            s.add(None, "note", f"error reading message ({exc.__class__.__name__}: {exc}) -- see {ref}", ref)


def read_gemini(path: Path, limit: int, subagent: bool) -> Session:
    """The legacy single-JSON-blob chat format (one full snapshot per file)."""
    s = Session("gemini", path)
    s.subagent = subagent
    try:
        d = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        s.add(None, "note", f"unreadable session file ({exc.__class__.__name__}: {exc}) -- see {path}", str(path))
        return s
    if not isinstance(d, dict):
        s.add(None, "note", f"unrecognized top-level shape ({type(d).__name__}) -- see {path}", str(path))
        return s
    sid = d.get("sessionId")
    if isinstance(sid, str) and sid:
        s.id = sid
    s.set_cwd(_gemini_cwd(path))
    s.touch(d.get("startTime"))
    s.touch(d.get("lastUpdated"))
    _render_gemini_messages(s, d.get("messages") or [], path, limit, str(path))
    return s


def read_gemini_jsonl(path: Path, limit: int, subagent: bool) -> Session:
    """The current append-only chat log: a metadata line, then message records keyed by "id"
    (a later record with the same id replaces it), "$set" updates (including a bulk
    "$set": {"messages": [...]} rewrite on resume), and "$rewindTo": "<id>" truncation."""
    s = Session("gemini", path)
    s.subagent = subagent
    meta = {}
    order = []       # message ids, in first-seen order
    by_id = {}       # id -> message dict
    try:
        fh = path.open(encoding="utf-8", errors="replace")
    except OSError as exc:
        s.add(None, "note", f"unreadable session file ({exc.__class__.__name__}: {exc}) -- see {path}", str(path))
        return s
    with fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            ref = f"{path}:{lineno}"
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                s.add(None, "note", f"unparseable line ({ref})", ref)
                continue
            try:
                if not isinstance(rec, dict):
                    s.add(None, "note", f"unrecognized record shape -- see {ref}", ref)
                    continue
                rewind = rec.get("$rewindTo")
                setv = rec.get("$set")
                mid = rec.get("id")
                if isinstance(rewind, str):
                    if rewind in by_id:
                        idx = order.index(rewind)
                        for removed in order[idx:]:
                            by_id.pop(removed, None)
                        order = order[:idx]
                    else:
                        by_id, order = {}, []
                elif isinstance(setv, dict):
                    if isinstance(setv.get("messages"), list):
                        by_id, order = {}, []
                        for m in setv["messages"]:
                            if isinstance(m, dict) and isinstance(m.get("id"), str):
                                by_id[m["id"]] = m
                                order.append(m["id"])
                    for k in ("sessionId", "startTime", "lastUpdated"):
                        if k in setv:
                            meta[k] = setv[k]
                elif isinstance(mid, str):
                    if mid not in by_id:
                        order.append(mid)
                    by_id[mid] = rec
                elif isinstance(rec.get("sessionId"), str):
                    meta.update(rec)  # the initial metadata line: sessionId, startTime, ...
                else:
                    s.add(None, "note", f"unrecognized record shape -- see {ref}", ref)
            except Exception as exc:  # a drifted/malformed record must not sink the whole run
                s.add(None, "note", f"error reading record ({exc.__class__.__name__}: {exc}) -- see {ref}", ref)
    sid = meta.get("sessionId")
    if isinstance(sid, str) and sid:
        s.id = sid
    s.set_cwd(_gemini_cwd(path))
    s.touch(meta.get("startTime"))
    s.touch(meta.get("lastUpdated"))
    _render_gemini_messages(s, [by_id[i] for i in order], path, limit, str(path))
    return s


# ---------------------------------------------------------------- discovery

def in_window(path: Path, since, until) -> bool:
    try:
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return False
    if since and mtime < since:
        return False
    if until and mtime > until + dt.timedelta(days=1):
        return False
    return True


def _read_or_note(reader, path: Path, missing: list, host: str, *args):
    """Call a per-file reader, turning a reader bug or an unreadable file into a coverage note
    instead of crashing the whole run -- one bad file must not cost every host's evidence."""
    try:
        return reader(path, *args)
    except Exception as exc:
        missing.append(f"{host}: failed to read {rel_or_abs(path)} ({exc.__class__.__name__}: {exc})")
        return None


def discover(roots: dict, since, until, limit: int):
    """Return (sessions, missing, coverage_extra). `missing` entries note a host or file that
    is unusable; `coverage_extra` adds informational lines (e.g. archived-session counts) that
    are not failures."""
    sessions, missing, coverage_extra = [], [], []
    for host, root in roots.items():
        root = Path(root)
        if not root.is_dir():
            missing.append(f"{host}: not found, tried {root}")
            continue
        if host == "codex":
            paths = sorted(root.rglob("*.jsonl"))
            if not paths:
                missing.append(f"{host}: no *.jsonl logs under {root}")
            for p in paths:
                if in_window(p, since, until):
                    s = _read_or_note(read_codex, p, missing, host, limit)
                    if s:
                        sessions.append(s)
            # A session moved to CODEX_HOME/archived_sessions (a sibling of the sessions root
            # this script otherwise reads) is still evidence; it is marked archived, not skipped.
            archived_root = root.parent / "archived_sessions"
            if archived_root.is_dir():
                apaths = sorted(archived_root.rglob("*.jsonl"))
                coverage_extra.append(
                    f"codex archived: root {rel_or_abs(archived_root)} ({len(apaths)} session file(s))")
                for p in apaths:
                    if in_window(p, since, until):
                        s = _read_or_note(read_codex, p, missing, host, limit)
                        if s:
                            s.archived = True
                            sessions.append(s)
            else:
                coverage_extra.append(f"codex archived: not found, tried {archived_root}")
        elif host == "claude":
            paths = sorted(root.rglob("*.jsonl"))
            if not paths:
                missing.append(f"{host}: no *.jsonl logs under {root}")
            for p in paths:
                if in_window(p, since, until):
                    s = _read_or_note(read_claude, p, missing, host, limit)
                    if s:
                        sessions.append(s)
        elif host == "gemini":
            json_main = sorted(root.glob("*/chats/*.json"))
            json_sub = sorted(root.glob("*/chats/*/*.json"))
            jsonl_main = sorted(root.glob("*/chats/*.jsonl"))
            jsonl_sub = sorted(root.glob("*/chats/*/*.jsonl"))
            matched = set(json_main) | set(json_sub) | set(jsonl_main) | set(jsonl_sub)
            if not matched:
                missing.append(f"{host}: no chats/*.json or chats/*.jsonl logs under {root}")
            for p in json_main:
                if in_window(p, since, until):
                    s = _read_or_note(read_gemini, p, missing, host, limit, False)
                    if s:
                        sessions.append(s)
            for p in json_sub:
                if in_window(p, since, until):
                    s = _read_or_note(read_gemini, p, missing, host, limit, True)
                    if s:
                        sessions.append(s)
            for p in jsonl_main:
                if in_window(p, since, until):
                    s = _read_or_note(read_gemini_jsonl, p, missing, host, limit, False)
                    if s:
                        sessions.append(s)
            for p in jsonl_sub:
                if in_window(p, since, until):
                    s = _read_or_note(read_gemini_jsonl, p, missing, host, limit, True)
                    if s:
                        sessions.append(s)
            # A structure this script's two known chat-file shapes don't cover (e.g. a future
            # extension or file kind) is reported by name rather than silently absent.
            all_under_chats = [p for p in root.glob("*/chats/**/*") if p.is_file()]
            unmatched = [p for p in all_under_chats if p not in matched]
            if unmatched:
                coverage_extra.append(
                    f"gemini: {len(unmatched)} file(s) under {rel_or_abs(root)} matched no reader "
                    f"(e.g. {rel_or_abs(unmatched[0])})")
    return sessions, missing, coverage_extra


# ---------------------------------------------------------------- workspace facts (git)

def git(repo: Path, *args):
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def repo_root_for(cwd: str):
    if not cwd:
        return None
    out = git(Path(cwd), "rev-parse", "--show-toplevel")
    return Path(out) if out else None


def git_facts(repo: Path) -> dict:
    default = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    default = default.removeprefix("origin/") if default else None
    if not default:
        default = next((b for b in ("main", "master") if git(repo, "rev-parse", "--verify", "-q", b) is not None), None)
    branches = [b for b in (git(repo, "branch", "--format=%(refname:short)") or "").splitlines() if b]
    merged = []
    if default:
        # "git branch --merged" marks the current branch with "*" and a branch checked out in
        # another worktree with "+"; strip both, not just "*", or the marker stays in the name.
        merged_out = git(repo, "branch", "--merged", default) or ""
        merged = [b.strip("*+ ").strip() for b in merged_out.splitlines() if b.strip("*+ ").strip() and b.strip("*+ ").strip() != default]
    all_trees = [l[9:] for l in (git(repo, "worktree", "list", "--porcelain") or "").splitlines() if l.startswith("worktree ")]
    # "git worktree list" always includes the repo's own primary working tree; report the rest.
    worktrees = [w for w in all_trees if Path(w).resolve() != repo.resolve()]
    stashes = [l for l in (git(repo, "stash", "list") or "").splitlines() if l]
    return {
        "default_branch": default,
        "branches": [b for b in branches if b != default],
        "merged_branches": merged,
        "worktrees": worktrees,
        "stashes": stashes,
    }


# ---------------------------------------------------------------- workspace facts (automations)

def parse_flat_toml(text: str) -> dict:
    """A minimal parser for this file's flat `key = value` shape (no tables/arrays)."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)\s*=\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val.startswith('"'):
            try:
                out[key] = json.loads(val)
                continue
            except json.JSONDecodeError:
                pass
        if val in ("true", "false"):
            out[key] = val == "true"
            continue
        try:
            out[key] = int(val)
            continue
        except ValueError:
            pass
        try:
            out[key] = float(val)
            continue
        except ValueError:
            pass
        out[key] = val.strip('"')
    return out


def codex_automations(codex_sessions_root=None):
    root = automations_root(codex_sessions_root)
    rows = []
    if not root.is_dir():
        return rows, f"codex automations: not found, tried {root}"
    for f in sorted(root.glob("*/automation.toml")):
        try:
            d = parse_flat_toml(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        rows.append({
            "id": d.get("id", f.parent.name), "kind": d.get("kind"), "status": d.get("status"),
            "schedule": d.get("rrule"), "thread": d.get("target_thread_id"),
        })
    return rows, None


def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or f"exit {r.returncode}").strip()
        return None, (msg.splitlines()[0] if msg else f"exit {r.returncode}")
    return r.stdout, None


def cron_entries():
    if not shutil.which("crontab"):
        return None, "crontab: not found on PATH"
    out, err = run(["crontab", "-l"])
    if out is None:
        # "no crontab for <user>" is the normal empty case, not a failure; anything else
        # (permission denied, a broken crontab binary, ...) is a real error worth reporting.
        if err and "no crontab" in err.lower():
            return [], None
        return None, err or "crontab -l failed"
    return [l for l in out.splitlines() if l.strip() and not l.strip().startswith("#")], None


def systemd_timers():
    if not shutil.which("systemctl"):
        return None, "systemctl: not found on PATH"
    out, err = run(["systemctl", "--user", "list-timers", "--all", "--no-legend", "--no-pager"])
    if out is None:
        return None, f"systemctl --user list-timers failed: {err}"
    return [l for l in out.splitlines() if l.strip()], None


def launchd_agents():
    if sys.platform != "darwin":
        return None, None
    rows = []
    for base in (Path.home() / "Library/LaunchAgents", Path("/Library/LaunchAgents")):
        if not base.is_dir():
            continue
        for f in sorted(base.glob("*.plist")):
            try:
                with f.open("rb") as fh:
                    d = plistlib.load(fh)
                if not isinstance(d, dict):
                    rows.append(f"{f} (unexpected plist shape: {type(d).__name__})")
                    continue
            except Exception as exc:
                # plistlib can raise several exception types (ExpatError included) for a
                # truncated or malformed file; any of them is one bad file, not a dead run.
                rows.append(f"{f} (unreadable plist: {exc.__class__.__name__})")
                continue
            rows.append(f"{d.get('Label', f.stem)}: program={d.get('Program') or d.get('ProgramArguments')}, "
                        f"interval={d.get('StartInterval')}, calendar={d.get('StartCalendarInterval')}")
    return rows, None


def windows_tasks():
    if not shutil.which("schtasks"):
        return None, None  # not Windows, or not on PATH; not an error worth reporting
    out, err = run(["schtasks", "/Query", "/FO", "CSV", "/NH"])
    if out is None:
        return None, f"schtasks /Query failed: {err}"
    return [l for l in out.splitlines() if l.strip()], None


# ---------------------------------------------------------------- rendering

def rel_or_abs(p: Path) -> str:
    home = str(Path.home())
    s = str(p)
    if s == home:
        return "~"
    # Require the path separator right after `home`, or "<home>-other/project" would render
    # as "~-other/project" -- a sibling directory, not one under the user's home.
    if s.startswith(home + os.sep):
        return "~" + s[len(home):]
    return s


def write_text_private(path: Path, content: str) -> None:
    """Write text as UTF-8 and, where the platform supports it, as 0600: this is often a
    private evidence file (session transcripts), not something meant to be world-readable."""
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def assign_output_names(sessions) -> None:
    """Set each session's `out_name`, the file it writes to under sessions/. Two distinct raw
    files can carry the same in-record session id (a Claude subagent shares its parent's
    sessionId; a forked Codex rollout can share session_meta.id); when that happens the later
    one gets a disambiguating suffix instead of silently overwriting the first one's transcript."""
    used = {}
    for s in sorted(sessions, key=lambda x: (x.host, str(x.path))):
        base = f"{s.host}-{safe_name(s.id)}"
        name = base
        if name in used:
            # Prefer a meaningful discriminator (Claude's agentId) over an opaque hash when one
            # is available.
            disambiguator = safe_name(s.agent_id) if s.agent_id else short_hash(str(s.path.resolve()))
            name = f"{base}-{disambiguator}"
            n = 2
            while name in used:
                name = f"{base}-{disambiguator}-{n}"
                n += 1
        used[name] = s
        s.out_name = name


def write_index(out: Path, sessions, missing, roots, coverage_extra=()):
    lines = ["# Session index", "", "Coverage:"]
    for host in HOSTS:
        note = next((m for m in missing if m.startswith(host + ":")), None)
        lines.append(f"- {host}: {note if note else 'root ' + rel_or_abs(Path(roots[host]))}")
    for line in coverage_extra:
        lines.append(f"- {line}")
    lines += ["", "| host | session | agent | start | end | cwd | user msgs | agent msgs | tool calls | subagent | archived | size | readable | raw log |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in sorted(sessions, key=lambda x: (x.host, x.start or dt.datetime.min.replace(tzinfo=UTC))):
        try:
            size = human_size(s.path.stat().st_size)
        except OSError:
            size = "?"
        readable = f"sessions/{s.out_name}.md"
        lines.append(f"| {s.host} | {s.id} | {s.agent_id} | {iso(s.start)} | {iso(s.end)} | {rel_or_abs(Path(s.cwd)) if s.cwd else ''} | "
                     f"{s.user_messages} | {s.agent_messages} | {s.tool_calls} | {'yes' if s.subagent else 'no'} | "
                     f"{'yes' if s.archived else 'no'} | {size} | [{readable}]({readable}) | {rel_or_abs(s.path)} |")
    write_text_private(out / "index.md", "\n".join(lines) + "\n")


def write_session(out: Path, s: Session):
    lines = [f"# {s.host} {s.id}", "", f"cwd: {s.cwd or '(unknown)'}  ", f"raw log: {s.path}  ",
             f"subagent/side thread: {'yes' if s.subagent else 'no'}",
             f"archived: {'yes' if s.archived else 'no'}", ""]
    for e in s.entries:
        lines.append(f"[{e.ts}] {e.kind}: {e.text}  ({e.ref})")
    write_text_private(out / "sessions" / f"{s.out_name}.md", "\n".join(lines) + "\n")


def write_workspace(out: Path, sessions, codex_sessions_root=None):
    lines = ["# Workspace facts", ""]
    if shutil.which("git") is None:
        lines.append("git was not found on PATH; branch, worktree, and stash facts are unavailable.")
        lines.append("")
    else:
        roots_seen = {}
        for s in sessions:
            r = repo_root_for(s.cwd)
            if r:
                roots_seen.setdefault(str(r), r)
        if not roots_seen:
            lines.append("No session recorded a working directory that resolves to a git repository.")
        for path, repo in sorted(roots_seen.items()):
            facts = git_facts(repo)
            lines += [f"## {rel_or_abs(repo)}", "", f"- default branch: {facts['default_branch'] or '(none found)'}",
                      f"- local branches ({len(facts['branches'])}): {', '.join(facts['branches']) or '(none)'}",
                      f"- merged into default ({len(facts['merged_branches'])}): {', '.join(facts['merged_branches']) or '(none)'}",
                      f"- worktrees ({len(facts['worktrees'])}): {', '.join(rel_or_abs(Path(w)) for w in facts['worktrees']) or '(none)'}",
                      f"- stashes ({len(facts['stashes'])}): {'; '.join(mask(x) for x in facts['stashes']) or '(none)'}", ""]

    lines += ["## Scheduled or recurring automations", ""]
    auto, auto_err = codex_automations(codex_sessions_root)
    if auto_err:
        lines.append(f"- codex automations: {auto_err}")
    elif not auto:
        lines.append("- codex automations: none found")
    else:
        for a in auto:
            lines.append(f"- codex automation `{a['id']}`: kind={a['kind']}, status={a['status']}, "
                         f"schedule={a['schedule']}, thread={a['thread']}")
    for label, fn in (("cron", cron_entries), ("systemd --user timers", systemd_timers),
                      ("launchd agents", launchd_agents), ("Windows scheduled tasks", windows_tasks)):
        rows, err = fn()
        if rows is None and err is None:
            continue  # not applicable on this OS
        if err:
            lines.append(f"- {label}: {err}")
        elif not rows:
            lines.append(f"- {label}: none found")
        else:
            for r in rows:
                lines.append(f"- {label}: {mask(r)}")
    write_text_private(out / "workspace.md", "\n".join(lines) + "\n")


# ---------------------------------------------------------------- main

def parse_roots(pairs):
    roots = {h: str(default_root(h)) for h in HOSTS}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"error: --root needs HOST=PATH, got {pair!r}\nhint: --root codex=/path/to/sessions")
        host, path = pair.split("=", 1)
        if host not in HOSTS:
            raise SystemExit(f"error: unknown host {host!r} in --root\nvalid hosts: {', '.join(HOSTS)}")
        # Expand `~` explicitly: an unquoted --root on a shell that doesn't expand it itself
        # (or when the value is quoted, e.g. from a config file) would otherwise be used
        # literally, producing a misleading "not found, tried ~/whatever".
        roots[host] = str(Path(path).expanduser())
    return roots


def prepare_out_dir(path, force: bool) -> Path:
    """No --out: a private (0700) temp directory, never the current directory (which risks
    landing real transcripts in a git worktree). An explicit --out that already has content in
    it is refused unless --force, so a rerun cannot silently mix old and new output."""
    if path is None:
        return Path(tempfile.mkdtemp(prefix="heal-gather-"))
    out = Path(path)
    if out.is_symlink():
        raise SystemExit(f"error: --out {out} is a symlink\nhint: point --out at a real directory, not a symlink")
    if out.exists():
        if not out.is_dir():
            raise SystemExit(f"error: --out {out} exists and is not a directory")
        if not force and any(out.iterdir()):
            raise SystemExit(
                f"error: --out {out} already exists and is not empty\n"
                "hint: pass --force to write into it anyway, or choose a different --out")
        return out
    out.mkdir(parents=True)
    try:
        os.chmod(out, 0o700)
    except OSError:
        pass
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", default="7d")
    ap.add_argument("--until")
    ap.add_argument("--out", default=None,
                     help="default: a new private (0700) temp directory, printed on completion")
    ap.add_argument("--root", action="append", metavar="HOST=PATH")
    ap.add_argument("--max-chars", type=int, default=2000)
    ap.add_argument("--force", action="store_true",
                     help="write into an already-nonempty --out instead of refusing")
    args = ap.parse_args(argv)

    since = parse_when(args.since)
    until = parse_when(args.until)
    roots = parse_roots(args.root)
    out = prepare_out_dir(Path(args.out) if args.out else None, args.force)
    (out / "sessions").mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(out / "sessions", 0o700)
    except OSError:
        pass

    sessions, missing, coverage_extra = discover(roots, since, until, args.max_chars)
    assign_output_names(sessions)
    write_index(out, sessions, missing, roots, coverage_extra)
    for s in sessions:
        write_session(out, s)
    write_workspace(out, sessions, roots.get("codex"))

    notes = sum(1 for s in sessions for e in s.entries if e.kind == "note")
    by_host = {h: sum(1 for s in sessions if s.host == h) for h in HOSTS}
    print(f"wrote {out}")
    print("sessions: " + ", ".join(f"{h}={n}" for h, n in by_host.items())
          + f" (subagent/side: {sum(1 for s in sessions if s.subagent)}"
          + f", archived: {sum(1 for s in sessions if s.archived)})")
    print(f"unrendered-but-noted records: {notes}")
    if missing:
        print("missing or unreadable: " + "; ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
