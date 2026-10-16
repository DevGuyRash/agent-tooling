#!/usr/bin/env python3
"""Evidence gatherer for a Self-Healing pass: extraction, not interpretation.

Finds session logs from Codex, Claude Code, and Gemini CLI for a time window, and writes an
output directory an executor can read directly:

    index.md              one row per session: host, id, Claude's own subagent id where it has
                           one, start/end, cwd, message/tool-call counts, whether it is a
                           subagent/side thread or an archived one, size, and the paths of its
                           readable transcript and its raw log
    sessions/HOST-NAME.md  a faithful, timestamped transcript of that session. Its header
                           names the raw log, and every line says where in it the line came
                           from (file:line; a note gives its line or message, or a run's range).
                           Lines are user messages (including the ones typed while the agent
                           was working), agent messages, the agent's own reasoning where the
                           log keeps it in the clear (Claude Code's thinking blocks that carry
                           text, as "thinking" lines cut at 1,500 characters, or --max-chars if
                           smaller), tool calls with their commands or arguments, tool results
                           (trimmed if long, with a note pointing at the raw file and line),
                           compactions, hook output (name, event, and bounded content, stdout,
                           and stderr), exposure lines naming the instruction files and skills
                           delivered to the agent (not their text), and event lines for
                           background-task notices and messages from a coordinator or another
                           session. Provenance outranks content. What a record's own fields say
                           another wrote is never shown as the user's, however the log stores
                           it: the summary a compaction leaves is a "summary (agent-written)"
                           line, and a record whose origin names another sender is an event
                           line. No person speaks in a subagent or side thread, so in one the
                           first user-role record is a "brief (from the delegating agent)" line
                           and every later one a "message (from the delegating side)" line, or a
                           "message (from the harness)" line when the harness inserted it (a
                           record marked as a person's own is still the user's). None of them
                           counts as a user message. A record a person wrote stays the user's
                           message, counted, whatever its text begins with -- a person may paste
                           a system reminder, an AGENTS.md, or a state snapshot for review -- and
                           where its text begins with a block the harness may have added, the
                           line says so and keeps all of the text (a long block is cut short so
                           the words after it are not cut off), as it does for a Gemini user
                           message that begins with the CLI's own state snapshot, since that log
                           does not say who wrote a user message. Content alone labels a record
                           only where nothing says a person wrote it. Any record type this
                           script does not render as one of those becomes a note naming its
                           type -- never silently dropped. A run of consecutive notes is one
                           line: each type in it with its count, the first and last timestamps,
                           and where in the raw log it comes from (the range of raw lines and of
                           message numbers, as the run has them). The file name is the
                           session id with the raw log file's own identity added where two raw
                           logs share an id, because that id is not always unique (a Claude
                           subagent transcript carries its parent's sessionId).
    workspace.md           for each distinct working directory the sessions used that is a git
                           repository: its branches (merged or not into its default branch),
                           worktrees, and stashes; plus scheduled or recurring automations this
                           machine can list for the hosts and the OS -- facts only, no verdicts

It does no classification, ranking, scoring, or keyword matching of meaning: no "corrections",
"nudges", "stalls", or residue verdicts. Reading what the evidence means is the executor's job.
It masks obvious secrets (tokens, keys, bearer headers, basic/URL credentials, JSON-shaped
assignments) in everything it writes: each value taken from a log or a configuration as it is
composed into a line, a header, an index cell, or a workspace fact, and every line again, by shape,
as the file is written. It leaves a bare 40- or 64-character hex string (a git SHA, a sha256
digest) alone, since that is evidence a pass needs to check state, not a secret.

    gather.py [--since 7d|YYYY-MM-DD] [--until YYYY-MM-DD] [--out DIR] [--force]
              [--root HOST=PATH ...] [--max-chars N]

A session is selected by its own records' timestamps: it is in the window when its latest
record is at or after --since and its earliest record is before the end of --until's day (the
midnight after that date, which is itself out), so a log file rewritten recently without new
records is not selected. The file's modification time only pre-filters -- a file last modified
more than a day before --since is skipped unread, a day being more than the difference between
the clock that stamps a record and the one that stamps the file -- and decides alone for a
session whose records carry no timestamps.

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
import html
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
    r"(?<![A-Za-z0-9_])(?:sk-[A-Za-z0-9_-]{12,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|xox[abpr]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|AIza[0-9A-Za-z_-]{35}"
    r"|glpat-[0-9A-Za-z_-]{15,}"
    r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r"|(?i:bearer\s+(?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{10,})"
    r"|(?i:basic\s+(?=[A-Za-z0-9+/=]*\d)[A-Za-z0-9+/=]{10,}))"
    # An assignment to a credential's name: the name may continue an underscore- or hyphen-joined
    # one (client_secret, DB_PASSWORD) but not a camel-case one (a Rust CancellationToken::new()),
    # may be followed by its closing quote ("password": "x"), and either quote may be escaped (JSON
    # inside a JSON string), so a JSON-shaped assignment is masked like a plain one.
    r"|(?<![A-Za-z0-9])(?i:(?:api[_-]?key|secret|token|password)\\*[\"']?\s*[:=]\s*\\*[\"']?[^\s\"']{6,})"
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


# Every shape SPECIFIC_SECRETS and URL_CREDS find contains one of these (compared lower-cased), so
# a line with none of them needs neither pattern -- the writer checks every line it writes, and
# most hold nothing of the kind.
_SECRET_MARKERS = ("sk-", "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "xoxa-", "xoxb-", "xoxp-", "xoxr-", "akia",
                   "aiza", "glpat-", "eyj", "bearer", "basic", "apikey", "api_key", "api-key", "secret",
                   "token", "password", "://")


def mask_known(text: str) -> str:
    """Mask the secret shapes that have a literal anchor -- prefixed tokens, bearer and basic
    credentials, key=value assignments, URL userinfo -- but not mask()'s catch-all for long
    random-looking runs, which would also eat the file names and ids a transcript points back to
    its raw log with. This is what the writer applies to every line it writes."""
    low = text.lower()
    if not any(marker in low for marker in _SECRET_MARKERS):
        return text
    return SPECIFIC_SECRETS.sub("[masked]", URL_CREDS.sub(r"\1[masked]@", text))


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


def safe_label(value, limit: int = 200) -> str:
    """A short, masked, single-line description of a record's type, built from log content (a
    drifted log can put anything where a type name is expected), so it is masked and bounded
    like everything else this script writes."""
    text = " ".join(mask(str(value)[: limit + 200]).split())
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def parse_json(line: str):
    """(the decoded value, None) -- or (None, the error) for a line that cannot be decoded. The
    errors are not only json's: a number of thousands of digits raises a plain ValueError and a
    nesting deeper than the stack a RecursionError, and either must cost a file the one line, not
    its good records."""
    try:
        return json.loads(line), None
    except (ValueError, RecursionError) as exc:
        return None, exc


def unparseable(exc) -> str:
    """The note label for a line parse_json could not decode."""
    return "unparseable line" if isinstance(exc, json.JSONDecodeError) else f"unparseable line ({exc.__class__.__name__})"


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
    """One transcript entry. A "note" has no raw position in `ref`; it carries `loc` instead,
    (unit, first, last) with unit "line" or "msg" (None for a whole-file note), so a run of
    notes can be collapsed into one line. A `solo` note is already an aggregate and is never
    merged with its neighbors."""
    __slots__ = ("ts", "kind", "text", "ref", "loc", "solo")

    def __init__(self, ts, kind, text, ref, loc=None, solo=False):
        self.ts, self.kind, self.text, self.ref = ts, kind, text, ref
        self.loc, self.solo = loc, solo


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
        self.brief_ref = None  # the raw position of the record that was this thread's brief, once seen

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

    def add_user(self, ts, text, ref, delegated=False, inserted=False, tag=""):
        """A user-role record's words. In a thread another agent started (`delegated`) no person is
        speaking, so none of it is a user message and each line says whose it is: the first record the
        delegating agent wrote is its brief (every text block of that one record), a later one comes
        from the delegating side, and one the harness inserted (`inserted`) from the harness."""
        if not delegated:
            self.add(ts, "user", text + tag, ref)
        elif inserted:
            self.add(ts, "message (from the harness)", text, ref)
        elif self.brief_ref in (None, ref):
            self.brief_ref = ref
            self.add(ts, "brief (from the delegating agent)", text, ref)
        else:
            self.add(ts, "message (from the delegating side)", text, ref)

    def note(self, ts, label, loc=None, solo=False):
        """Record something this script does not render as a line of its own, named by `label`
        and located by `loc`: ("line", n), ("msg", i), a (unit, first, last) range, or None
        for the whole raw file."""
        t = self.touch(ts)
        if loc is not None and len(loc) == 2:
            loc = (loc[0], loc[1], loc[1])
        text = mask(label) if solo else safe_label(label)
        self.entries.append(Entry(iso(t), "note", text, "", loc, solo))


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


# What a user line says when its text begins with a block a harness (not the person) may have added.
# A flag, never a reason to move text out of the user's message or to leave it uncounted.
HARNESS_FLAG = "[begins with a block the harness may have added] "


# ---------------------------------------------------------------- Codex reader

# item_completed item types this script renders as a line of their own (user and agent
# messages, tool calls and results, compactions, hook output). Anything else -- Reasoning
# (whose content Codex keeps encrypted), EnteredReviewMode/ExitedReviewMode, and any item type
# Codex introduces after this script was written -- falls through to the generic note below,
# so a harness change never disappears silently.
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
    # Subagent tools: waiting on, messaging, or spawning another agent thread.
    "CollabAgentToolCall": "tool_call",
    "SubAgentActivity": "tool_call",
    # A host-app tool's result, and the prompt a hook (e.g. a Stop hook) injected.
    "FunctionCallOutput": "tool_result",
    "HookPrompt": "hook",
}

# A user-role response_item message that starts like this, and that no UserMessage item accounts
# for, is context the harness injected (the AGENTS.md text, the environment, a hook's prompt --
# which has its own HookPrompt item --, an open-page notice, an IDE file list), not words anyone
# typed or delegated: nothing says a person wrote it, so its content labels it. Every other such
# message is rendered, so an unrecognized new kind of injected block shows up as one rather than
# disappearing. A UserMessage item is a person's turn, and stays the user's message whatever it
# begins with (a person may paste an AGENTS.md for review); it is only flagged.
CODEX_INJECTED_USER_PREFIXES = (
    "# AGENTS.md instructions",
    "<environment_context",
    "<hook_prompt",
    "<external_codex_apps_open_page",
    "# Files mentioned by the user",
)

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
#     An image_generation_call has an id but no call_id, so it always renders too.
CODEX_RESPONSE_ITEM_ROLE_WITHOUT_COMMAND_EXECUTION = {
    "custom_tool_call": "tool_call",
    "custom_tool_call_output": "tool_result",
    "function_call": "tool_call",
    "function_call_output": "tool_result",
    "web_search_call": "tool_call",
    "image_generation_call": "tool_call",
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
    if kind == "CollabAgentToolCall":
        detail = {k: v for k, v in item.items() if k not in ("type", "id", "tool", "status")}
        head = f"collab {item.get('tool')} status={item.get('status')}"
        return trim(head + (f": {json.dumps(detail, default=str, ensure_ascii=False)}" if detail else ""),
                    limit, ref)
    if kind == "SubAgentActivity":
        facts = [f"thread {item.get('agent_thread_id')}"]
        for label, key in (("model", "model"), ("effort", "reasoning_effort")):
            if item.get(key):
                facts.append(f"{label} {item[key]}")
        return trim(f"subagent {item.get('kind')}: {item.get('agent_path')} ({', '.join(facts)})", limit, ref)
    if kind == "FunctionCallOutput":
        name = ".".join(str(x) for x in (item.get("namespace"), item.get("name")) if x)
        raw = item.get("output")
        body = raw if isinstance(raw, str) else _text(raw)
        return trim(f"call result ({name or 'unnamed'}): {body}" if body else f"call result ({name or 'unnamed'}) (no output)",
                    limit, ref)
    if kind == "HookPrompt":
        fragments = item.get("fragments")
        parts = []
        for frag in fragments if isinstance(fragments, list) else []:
            if isinstance(frag, dict):
                parts.append(f"{frag.get('hookRunId') or '(unnamed)'}: {frag.get('text') or ''}")
            else:
                parts.append(str(frag))
        return trim("hook prompt " + " | ".join(parts) if parts else "hook prompt (no fragments)", limit, ref)
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
    if kind == "image_generation_call":
        # The generated image's bytes sit in "result"; say how large they are, not what they are.
        detail = {k: v for k, v in payload.items() if k not in ("type", "id", "result")}
        if isinstance(payload.get("result"), str) and payload["result"]:
            detail["result"] = f"({len(payload['result'])} chars of image data)"
        return trim(f"image_generation_call: {json.dumps(detail, default=str, ensure_ascii=False)}", limit, ref)
    return trim(json.dumps(payload, default=str, ensure_ascii=False), limit, ref)


# How far apart, in seconds, Codex writes a response-stream message and the completed item that says
# the same thing (the largest gap seen in real rollouts is under 6 s). A message and an item with
# the same text further apart than this are two occurrences, not twins.
CODEX_TWIN_SECONDS = 30


def _codex_prescan(path: Path):
    """Pre-scan of one rollout: (the "id" of every item_completed/CommandExecution item, the line
    numbers of the response_item messages that repeat a UserMessage or AgentMessage item). Cheap
    and separate from the main pass below so that pass can decide, per response_item record,
    whether it only repeats something an item_completed record already says (left to the
    aggregate note) or is the only record of it (rendered in full): a custom_tool_call/-output
    whose call_id has a CommandExecution twin (see
    CODEX_RESPONSE_ITEM_ROLE_WITHOUT_COMMAND_EXECUTION), and a user- or assistant-role message --
    the case for a delegated agent's task, for a second "continue", and for some final answers,
    which exist only as a response_item message.

    A message is paired with an item of its own: the same role and text, written within
    CODEX_TWIN_SECONDS, each item taking at most one message, in the order they were written. Pairing
    by text alone would take a second "continue" an hour later for a twin of the first."""
    ids = set()
    items, messages = {}, {}  # (role, text) -> [(line number, seconds or None)], in file order
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                o, err = parse_json(line)
                if err is not None or not isinstance(o, dict):
                    continue
                p = o.get("payload")
                if not isinstance(p, dict):
                    continue
                when = stamp(o.get("timestamp"))
                at = when.timestamp() if when else None
                if o.get("type") == "response_item" and p.get("type") == "message" and p.get("role") in ("user", "assistant"):
                    text = _text(p.get("content")).strip()
                    if text:
                        messages.setdefault((p["role"], text), []).append((lineno, at))
                    continue
                if o.get("type") != "event_msg" or p.get("type") != "item_completed":
                    continue
                item = p.get("item")
                if not isinstance(item, dict):
                    continue
                kind = item.get("type")
                if kind == "CommandExecution":
                    idv = item.get("id")
                    if isinstance(idv, str) and idv:
                        ids.add(idv)
                elif kind in ("UserMessage", "AgentMessage"):
                    role = "user" if kind == "UserMessage" else "assistant"
                    items.setdefault((role, _text(item.get("content")).strip()), []).append((lineno, at))
    except OSError:
        pass
    paired = set()
    for key, mine in messages.items():
        free = list(items.get(key, ()))
        for lineno, at in mine:
            for j, (_, item_at) in enumerate(free):
                if at is None or item_at is None or abs(at - item_at) <= CODEX_TWIN_SECONDS:
                    paired.add(lineno)
                    del free[j]
                    break
    return ids, paired


def read_codex(path: Path, limit: int) -> Session:
    s = Session("codex", path)
    seen_session_meta = False
    command_execution_ids, paired_messages = _codex_prescan(path)
    response_item_counts = {}  # payload type -> [count, first lineno, last lineno]
    with path.open(encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            ref = f"{path}:{lineno}"
            loc = ("line", lineno)
            o, err = parse_json(line)
            if err is not None:
                s.note(None, unparseable(err), loc)
                continue
            try:
                if not isinstance(o, dict):
                    s.note(None, "unrecognized record shape", loc)
                    continue
                t = o.get("type")
                ts = o.get("timestamp")
                s.touch(ts)  # every record counts toward the session's start and end, rendered or not
                if t == "response_item":
                    p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
                    it = p.get("type", "(no type)")
                    call_id = p.get("call_id")
                    has_twin = isinstance(call_id, str) and call_id in command_execution_ids
                    role = (None if has_twin else
                            CODEX_RESPONSE_ITEM_ROLE_WITHOUT_COMMAND_EXECUTION.get(it))
                    message = (_codex_unrepeated_message(p, lineno in paired_messages) if it == "message" else None)
                    if role:
                        # No item_completed/CommandExecution in this rollout shares this call's
                        # id, so this custom_tool_call/-output is the only record of what ran --
                        # render it in full instead of folding it into the aggregate note below.
                        s.add(ts, role, codex_response_item_text(it, p, ref, limit), ref)
                    elif message:
                        kind, body = message
                        text = trim(body, limit, ref) + " (response_item message)"
                        if kind == "user":
                            s.add_user(ts, text, ref, s.subagent)
                        else:
                            s.add(ts, kind, text, ref)
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
                elif t == "compacted":
                    s.add(ts, "compaction", "compaction (session summarized)", ref)
                    # The summary the agent wrote sits in the record's message (the user messages Codex
                    # keeps are in its replacement_history, already lines of the transcript).
                    payload = o.get("payload") if isinstance(o.get("payload"), dict) else {}
                    if _nonblank_text(payload.get("message")):
                        s.add(ts, "summary (agent-written)", trim(payload["message"], limit, ref), ref)
                elif t in CODEX_SKIP_TOP:
                    continue
                elif t == "event_msg":
                    p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
                    et = p.get("type")
                    if et in CODEX_SKIP_EVENT:
                        continue
                    if et != "item_completed":
                        s.note(ts, f"type={et}", loc)
                        continue
                    item = p.get("item") if isinstance(p.get("item"), dict) else {}
                    kind = item.get("type")
                    role = CODEX_ITEM_ROLE.get(kind)
                    if role is None:
                        s.note(ts, f"type=item_completed/{kind}", loc)
                        continue
                    text = codex_item_text(kind, item, ref, limit)
                    if role == "user":
                        if _text(item.get("content")).lstrip().startswith(CODEX_INJECTED_USER_PREFIXES):
                            text = HARNESS_FLAG + text
                        s.add_user(ts, text, ref, s.subagent)
                    else:
                        s.add(ts, role, text, ref)
                else:
                    s.note(ts, f"type={t}", loc)
            except Exception as exc:  # a drifted/malformed record must not sink the whole run
                s.note(None, f"error reading record ({exc.__class__.__name__}: {exc})", loc)
    for it, (count, first, last) in sorted(response_item_counts.items()):
        s.note(None, f"response_item/{it}: {count} record(s) not individually rendered "
                     "(redundant with item_completed unless noted otherwise)",
               ("line", first, last), solo=True)
    return s


def _codex_unrepeated_message(payload: dict, paired: bool):
    """(kind, text) for a response_item message that is the only record of what a user (or the
    agent that delegated to this one) said or what the agent answered; None for a developer
    message, an injected context block (see CODEX_INJECTED_USER_PREFIXES), an empty message,
    or one that a UserMessage/AgentMessage item of its own already says (`paired`)."""
    if paired:
        return None
    role = payload.get("role")
    body = _text(payload.get("content")).strip()
    if not body:
        return None
    if role == "assistant":
        return "agent", body
    if role == "user" and not body.startswith(CODEX_INJECTED_USER_PREFIXES):
        return "user", body
    return None


# ---------------------------------------------------------------- Claude Code reader

def _nonblank_text(value) -> str:
    """A str field is expected here, but a drifted record can carry null or a list instead;
    treat anything that isn't a non-blank string as blank rather than crashing on .strip()."""
    return value if isinstance(value, str) and value.strip() else ""


def _joined_text(value) -> str:
    """Text of a field that is a string, a list of strings or content blocks, or absent; list
    items stay on separate lines rather than running together."""
    if isinstance(value, list):
        return "\n".join(part for part in (_text([b]) if not isinstance(b, str) else b for b in value) if part)
    return _text(value)


def _prompt_text(prompt) -> str:
    """Text of a queued command's prompt: a string, or content blocks where an image becomes a
    marker (its bytes would only bury the words around it)."""
    if isinstance(prompt, list):
        parts = []
        for b in prompt:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(b["text"] if isinstance(b.get("text"), str) else "")
                else:
                    parts.append(f"[{b.get('type') or 'content'} attached]")
        return " ".join(part for part in parts if part.strip())
    return _text(prompt)


# What a Claude Code attachment record's "attachment.type" renders as, instead of a note:
# hook output carries its name, event, and bounded content/stdout/stderr; the exposure types
# name the instruction files and skills that reached the agent; a queued_command is either the
# user's own words typed while the agent was working or a notice from elsewhere. The hook types
# are the ones the host writes (checked against its own code): each keeps its words in a field
# of its own.
CLAUDE_HOOK_OUTCOME = {
    "hook_success": "succeeded",
    "hook_non_blocking_error": "failed (non-blocking)",
    "hook_blocking_error": "blocked",
    "hook_stopped_continuation": "stopped the agent",
    "hook_error_during_execution": "errored while running",
    "hook_cancelled": "was cancelled",
    "hook_system_message": "system message",
    "hook_additional_context": "added context",
    "hook_permission_decision": "decided a permission request",
    "hook_deferred_tool": "deferred a tool call",
}
CLAUDE_HOOK_FIELDS = (("content", "content"), ("message", "message"), ("blockingError", "blocking error"),
                      ("decision", "decision"), ("toolName", "tool"), ("stdout", "stdout"), ("stderr", "stderr"))

# A host can list a few hundred skills; a skill-listing line names them all, since whether one
# skill was offered to the agent is the question, so it is bounded far above --max-chars.
SKILL_LISTING_LIMIT = 20000

# The agent's own reasoning, where a log keeps it in the clear, is rendered cut at this many
# characters (or --max-chars, if that is smaller): it is an account of how the agent read what
# guided it, not something a pass needs to read to the end of a long ramble.
THINKING_LIMIT = 1500

_TASK_NOTICE_FIELD = {name: re.compile(rf"<{name}>(.*?)</{name}>", re.S) for name in ("status", "summary")}


def claude_hook_line(a: dict, limit: int, ref: str) -> str:
    name = safe_label(_nonblank_text(a.get("hookName"))) if _nonblank_text(a.get("hookName")) else ""
    event = safe_label(_nonblank_text(a.get("hookEvent"))) if _nonblank_text(a.get("hookEvent")) else ""
    head = f"{name or event or '(unnamed hook)'}" + (f" ({event})" if name and event and event != name else "")
    head += f" {CLAUDE_HOOK_OUTCOME[a['type']]}"
    facts = []
    if a.get("exitCode") is not None:
        facts.append(f"exit={safe_label(a['exitCode'], 40)}")
    if a.get("timedOut"):
        facts.append(f"timed out after {safe_label(a.get('timeoutMs'), 40)}ms")
    parts = [head + (f" ({', '.join(facts)})" if facts else "")]
    command = _nonblank_text(a.get("command"))
    if command:
        parts.append(f"command: {trim(command, min(limit, 200), ref)}")
    for field, label in CLAUDE_HOOK_FIELDS:
        value = a.get(field)
        body = json.dumps(value, default=str, ensure_ascii=False) if isinstance(value, dict) else _joined_text(value)
        if body.strip():
            parts.append(f"{label}: {trim(body, limit, ref)}")
    return "; ".join(parts)


def claude_stop_hook_summary_line(o: dict, limit: int, ref: str):
    """A stop_hook_summary system record is bookkeeping unless a hook said something, blocked
    the stop, or failed: only then does it get a line; None leaves it to the note."""
    errors = _joined_text(o.get("hookErrors"))
    context = _joined_text(o.get("hookAdditionalContext"))
    reason = _nonblank_text(o.get("stopReason"))
    prevented = bool(o.get("preventedContinuation"))
    if not (errors.strip() or context.strip() or reason or prevented or o.get("hasOutput")):
        return None
    count = o.get("hookCount")
    parts = [f"stop hooks ran ({count} hook(s))" if isinstance(count, int) else "stop hooks ran"]
    if prevented:
        parts.append("prevented the agent from stopping")
    if reason:
        parts.append(f"stop reason: {trim(reason, limit, ref)}")
    if errors.strip():
        parts.append(f"errors: {trim(errors, limit, ref)}")
    if context.strip():
        parts.append(f"added context: {trim(context, limit, ref)}")
    if len(parts) == 1 and o.get("hasOutput"):
        parts.append("with output (see the raw record)")
    return "; ".join(parts)


def claude_task_notice(prompt: str, limit: int, ref: str) -> str:
    """One short line for a background-task notification: its status and summary when it has
    them (the notification's result body stays in the raw log), else its first words."""
    fields = {}
    prompt = prompt[:10_000]  # the status and summary come first; the result body after them is not wanted
    for name, rx in _TASK_NOTICE_FIELD.items():
        m = rx.search(prompt)
        if m and m.group(1).strip():
            fields[name] = " ".join(html.unescape(m.group(1)).split())  # the notice is XML-escaped
    short = min(limit, 300)
    status = f" ({trim(fields['status'], 40, ref)})" if "status" in fields else ""
    if "summary" in fields:
        return f"task notification{status}: {trim(fields['summary'], short, ref)}"
    return f"task notification{status}: {trim(prompt, min(short, 160), ref)}"


def _exposed(entries) -> str:
    """Name the files or skills in an exposure attachment's list (each a dict with a path and
    maybe a name and a type), never their text."""
    out = []
    for f in entries if isinstance(entries, list) else []:
        if not isinstance(f, dict):
            out.append(safe_label(f))
            continue
        name, where, kind = f.get("name"), f.get("path"), f.get("type")
        where = rel_or_abs(Path(where)) if isinstance(where, str) and where else ""
        label = f"{name} ({where})" if isinstance(name, str) and name and where else (
            name if isinstance(name, str) and name else where or "(unnamed)")
        out.append(label + (f" [{kind}]" if isinstance(kind, str) and kind else ""))
    return ", ".join(out)


# A harness wraps the context it adds to a user's message in <system-reminder> tags, ahead of the
# words -- but a person may paste such a block into a message, so the block is never moved out of
# the user's message or left uncounted: a message that begins with one says so, and keeps all of
# its text. Where complete blocks are followed by words, the blocks are cut short (INJECTED_EXCERPT
# characters, the usual marker) so that the bound does not cut the words off.
_LEADING_REMINDERS = re.compile(r"(?:\s*<system-reminder[^>]*>.*?</system-reminder>)+", re.S)
INJECTED_EXCERPT = 200


def claude_user_text(text: str, limit: int, ref: str) -> str:
    """All of a user-role record's text, as one line, flagged if it begins with a <system-reminder>
    block."""
    if not text.lstrip().startswith("<system-reminder"):
        return trim(text, limit, ref)
    leading = _LEADING_REMINDERS.match(text)
    if leading and text[leading.end():].strip():
        return (HARNESS_FLAG + trim(leading.group(0), min(limit, INJECTED_EXCERPT), ref) + " "
                + trim(text[leading.end():], limit, ref))
    return HARNESS_FLAG + trim(text, limit, ref)


def add_claude_user_words(s: Session, ts, text: str, prefix: str, tag: str, limit: int, ref: str,
                          delegated: bool = False, inserted: bool = False) -> bool:
    """The text of a user-role record whose sender is the user (or, in a thread another agent
    started, the delegating side or the harness). True if there was any."""
    if not text.strip():
        return False
    s.add_user(ts, prefix + claude_user_text(text, limit, ref), ref, delegated, inserted, tag)
    return True


def claude_sender(kind, origin: dict) -> str:
    """Who an origin object says sent something: its kind, and its name when it has one."""
    return safe_label(" ".join(str(x) for x in (kind or "unknown origin", origin.get("name")) if x))


def add_claude_user_text(s: Session, ts, text: str, tag: str, origin, limit: int, ref: str,
                         summary: bool = False, delegated: bool = False, inserted: bool = False) -> None:
    """Text in a user-type record is the user's words unless the record says otherwise: it is a
    compaction summary, which the agent wrote to carry its context forward, or its origin names
    another sender -- a background task's notification, or a message from a coordinator or another
    session. Those are not the user's. Shown as the user they would be read as the user's
    corrections and counted among the user's messages."""
    kind = origin.get("kind") if isinstance(origin, dict) else None
    if summary:
        s.add(ts, "summary (agent-written)", trim(text, limit, ref), ref)
    elif not (isinstance(kind, str) and kind) or kind == "human":
        add_claude_user_words(s, ts, text, "", tag, limit, ref, delegated and kind != "human", inserted)
    elif kind == "task-notification":
        s.add(ts, "event", claude_task_notice(text, limit, ref), ref)
    else:
        s.add(ts, "event", f"message from {claude_sender(kind, origin)}: " + trim(text, limit, ref), ref)


def render_claude_queued_command(s: Session, a: dict, ts, ref: str, limit: int) -> bool:
    """A queued_command attachment is something delivered to the agent mid-run. The user's own
    words (origin.kind "human") are a user message; a background-task notification is one short
    line; a message another agent queued is a line naming who sent it."""
    origin = a.get("origin") if isinstance(a.get("origin"), dict) else {}
    kind = origin.get("kind")
    prompt = _prompt_text(a.get("prompt"))
    if kind == "human" or (not origin and a.get("humanTurn") is True):
        if not add_claude_user_words(s, ts, prompt, "(sent while the agent was working) ", "", limit, ref):
            return False
    elif kind == "task-notification" or a.get("commandMode") == "task-notification":
        s.add(ts, "event", claude_task_notice(prompt, limit, ref), ref)
    elif prompt.strip():
        s.add(ts, "event", f"message queued while the agent was working, from {claude_sender(kind, origin)}: "
              + trim(prompt, limit, ref), ref)
    else:
        return False
    return True


def render_claude_hook(s: Session, a: dict, ts, ref: str, limit: int) -> bool:
    s.add(ts, "hook", claude_hook_line(a, limit, ref), ref)
    return True


def render_claude_instructions(s: Session, a: dict, ts, ref: str, limit: int) -> bool:
    why = [str(a["reason"])] if _nonblank_text(a.get("reason")) else []
    if a.get("changed"):
        why.append("changed")
    files = _exposed(a.get("files"))
    s.add(ts, "exposure", trim("instructions delivered" + (f" ({', '.join(why)})" if why else "")
                               + f": {files or '(no files listed)'}", limit, ref), ref)
    return True


def render_claude_invoked_skills(s: Session, a: dict, ts, ref: str, limit: int) -> bool:
    skills = _exposed(a.get("skills"))
    s.add(ts, "exposure", trim(f"skills invoked: {skills or '(none listed)'}", limit, ref), ref)
    return True


def render_claude_skill_listing(s: Session, a: dict, ts, ref: str, limit: int) -> bool:
    names = a.get("names")
    names = [str(n) for n in names] if isinstance(names, list) else []
    which = "initial" if a.get("isInitial") else "update"
    s.add(ts, "exposure", trim(f"skill listing ({which}, {len(names)} skill(s)): {', '.join(names) or '(no names)'}",
                               max(limit, SKILL_LISTING_LIMIT), ref), ref)
    return True


def render_claude_nested_memory(s: Session, a: dict, ts, ref: str, limit: int) -> bool:
    content = a.get("content") if isinstance(a.get("content"), dict) else {}
    where = _nonblank_text(a.get("path")) or _nonblank_text(content.get("path"))
    kind = content.get("type")
    s.add(ts, "exposure", trim("instructions delivered (nested): "
                               + (rel_or_abs(Path(where)) if where else "(no path)")
                               + (f" [{kind}]" if isinstance(kind, str) and kind else ""), limit, ref), ref)
    return True


CLAUDE_ATTACHMENT_RENDERERS = {
    "queued_command": render_claude_queued_command,
    "instructions": render_claude_instructions,
    "invoked_skills": render_claude_invoked_skills,
    "skill_listing": render_claude_skill_listing,
    "nested_memory": render_claude_nested_memory,
    **{hook_type: render_claude_hook for hook_type in CLAUDE_HOOK_OUTCOME},
}


def read_claude(path: Path, limit: int) -> Session:
    s = Session("claude", path)
    in_subagent_file = "subagents" in path.parts
    s.subagent = in_subagent_file
    with path.open(encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            ref = f"{path}:{lineno}"
            loc = ("line", lineno)
            o, err = parse_json(line)
            if err is not None:
                s.note(None, unparseable(err), loc)
                continue
            try:
                if not isinstance(o, dict):
                    s.note(None, "unrecognized record shape", loc)
                    continue
                t = o.get("type")
                ts = o.get("timestamp")
                s.touch(ts)
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
                        continue
                    summary = (claude_stop_hook_summary_line(o, limit, ref)
                               if o.get("subtype") == "stop_hook_summary" else None)
                    if summary:
                        s.add(ts, "hook", summary, ref)
                    else:
                        s.note(ts, f"type=system/{o.get('subtype')}", loc)
                    continue
                if t == "attachment":
                    a = o.get("attachment") if isinstance(o.get("attachment"), dict) else {}
                    render = CLAUDE_ATTACHMENT_RENDERERS.get(a.get("type")) if isinstance(a.get("type"), str) else None
                    if not (render and render(s, a, ts, ref, limit)):
                        s.note(ts, f"type=attachment/{a['type']}" if "type" in a else "type=attachment", loc)
                    continue
                if t not in ("user", "assistant"):
                    s.note(ts, f"type={t}", loc)
                    continue
                message = o.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                tag = " (meta)" if o.get("isMeta") else ""
                before = len(s.entries)
                if t == "user":
                    origin, summary = o.get("origin"), bool(o.get("isCompactSummary"))
                    # In a subagent's transcript every record is in a thread another agent started; one
                    # the harness inserted (isMeta) is the harness's, not that agent's writing.
                    delegated = in_subagent_file or bool(o.get("isSidechain"))
                    inserted = bool(o.get("isMeta"))
                    if isinstance(content, str):
                        if content.strip():
                            add_claude_user_text(s, ts, content, "", origin, limit, ref, summary, delegated, inserted)
                    elif isinstance(content, list):
                        words = []  # the text blocks of one record are one message, however many blocks it has

                        def say():
                            if words:
                                add_claude_user_text(s, ts, "\n".join(words), tag, origin, limit, ref, summary, delegated,
                                                     inserted)
                                words.clear()

                        for b in content:
                            if not isinstance(b, dict):
                                say()
                                s.note(ts, "unrecognized user content block shape", loc)
                            elif b.get("type") == "text" and _nonblank_text(b.get("text")):
                                words.append(b["text"])
                            elif b.get("type") == "tool_result":
                                say()
                                head = f"tool result (id={safe_label(b.get('tool_use_id'), 100)}, error={bool(b.get('is_error'))})"
                                body = trim(_text(b.get("content")), limit, ref)
                                s.add(ts, "tool_result", f"{head}: {body}", ref)
                            elif b.get("type") != "text":  # a non-text, non-tool_result block, e.g. an image
                                say()
                                s.note(ts, f"user content block type={b.get('type')}", loc)
                        say()
                    elif content:
                        s.note(ts, "unrecognized user content shape", loc)
                else:  # assistant
                    if isinstance(content, list):
                        for b in content:
                            if not isinstance(b, dict):
                                s.note(ts, "unrecognized assistant content block shape", loc)
                                continue
                            bt = b.get("type")
                            if bt == "text" and _nonblank_text(b.get("text")):
                                s.add(ts, "agent", trim(b["text"], limit, ref) + tag, ref)
                            elif bt == "thinking" and _nonblank_text(b.get("thinking")):
                                # Most thinking blocks keep only a signature; one with text is the agent's
                                # own account at the time, and a line of its own, not an agent message.
                                s.add(ts, "thinking", trim(b["thinking"], min(limit, THINKING_LIMIT), ref), ref)
                            elif bt == "tool_use":
                                args = mask(b.get("input") or {})
                                s.add(ts, "tool_call", trim(f"{b.get('name')}({args})", limit, ref), ref)
                            elif bt != "text":
                                s.note(ts, f"assistant content block type={bt}", loc)
                    elif content:
                        s.note(ts, "unrecognized assistant content shape", loc)
                if len(s.entries) == before:
                    # A recognized record whose content was empty or blank still gets one line,
                    # so a genuinely empty message is distinguishable from a missed record.
                    s.note(ts, f"{t} record had no renderable content", loc)
            except Exception as exc:  # a drifted/malformed record must not sink the whole run
                s.note(None, f"error reading record ({exc.__class__.__name__}: {exc})", loc)
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


# Gemini CLI compresses a long chat by replacing its history with a user-role message holding the
# summary an agent wrote, in the <state_snapshot> format its summarizer prompt requires, and
# records that message as it records any other "user" one (checked against the CLI's bundled code):
# nothing in the log says who wrote a user message, so one that begins like this is the user's, with
# a flag, in case a person pasted such a block for review.
GEMINI_SNAPSHOT_TAG = "<state_snapshot>"


def _render_gemini_messages(s: Session, messages, path: Path, limit: int, ref_prefix: str) -> None:
    if not isinstance(messages, list):
        s.note(None, "unrecognized messages shape")
        return
    for i, msg in enumerate(messages):
        ref = f"{ref_prefix}#msg{i}"
        loc = ("msg", i)
        if not isinstance(msg, dict):
            s.note(None, "unrecognized message shape", loc)
            continue
        try:
            ts, kind = msg.get("timestamp"), msg.get("type")
            text = _text(msg.get("content"))
            before = len(s.entries)
            if kind == "user":
                if text.strip():
                    flag = HARNESS_FLAG if text.lstrip().startswith(GEMINI_SNAPSHOT_TAG) else ""
                    # A subagent chat is driven by the CLI: its messages are the start query it builds
                    # (a templated query, or "Get Started!"), nudges, and answers it synthesizes.
                    s.add_user(ts, flag + trim(text, limit, ref), ref, s.subagent, inserted=True)
            elif kind in ("gemini", "model", "assistant"):
                if text.strip():
                    s.add(ts, "agent", trim(text, limit, ref), ref)
                for call in msg.get("toolCalls") or []:
                    if not isinstance(call, dict):
                        s.note(ts, "unrecognized toolCalls entry shape", loc)
                        continue
                    args = mask(call.get("args") or {})
                    head = f"{call.get('name')}({args}) status={call.get('status')}"
                    out = call.get("result")
                    s.add(ts, "tool_call", trim(head + (f"\n{out}" if out else ""), limit, ref), ref)
            else:
                s.note(ts, f"type={kind}", loc)
            if len(s.entries) == before:
                # A recognized message with no text and no tool calls still gets one line.
                s.note(ts, f"{kind} message had no renderable content", loc)
        except Exception as exc:  # a drifted/malformed message must not sink the whole run
            s.note(None, f"error reading message ({exc.__class__.__name__}: {exc})", loc)


def read_gemini(path: Path, limit: int, subagent: bool) -> Session:
    """The legacy single-JSON-blob chat format (one full snapshot per file)."""
    s = Session("gemini", path)
    s.subagent = subagent
    try:
        d = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, RecursionError) as exc:
        s.note(None, f"unreadable session file ({exc.__class__.__name__}: {exc})")
        return s
    if not isinstance(d, dict):
        s.note(None, f"unrecognized top-level shape ({type(d).__name__})")
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
        s.note(None, f"unreadable session file ({exc.__class__.__name__}: {exc})")
        return s
    with fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            loc = ("line", lineno)
            rec, err = parse_json(line)
            if err is not None:
                s.note(None, unparseable(err), loc)
                continue
            try:
                if not isinstance(rec, dict):
                    s.note(None, "unrecognized record shape", loc)
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
                    s.note(None, "unrecognized record shape", loc)
            except Exception as exc:  # a drifted/malformed record must not sink the whole run
                s.note(None, f"error reading record ({exc.__class__.__name__}: {exc})", loc)
    sid = meta.get("sessionId")
    if isinstance(sid, str) and sid:
        s.id = sid
    s.set_cwd(_gemini_cwd(path))
    s.touch(meta.get("startTime"))
    s.touch(meta.get("lastUpdated"))
    _render_gemini_messages(s, [by_id[i] for i in order], path, limit, str(path))
    return s


# ---------------------------------------------------------------- discovery

# A log file whose modification time is within this of --since is still read. A record is stamped
# by the clock of the process that wrote it and the file by the clock of the file system, and the
# two differ -- by seconds on one machine, by hours when a log is synced from another or a clock is
# set wrong -- so a file may be stamped earlier than a record it holds. Only a file last modified
# more than a day before --since is skipped unread.
MTIME_SLACK = dt.timedelta(days=1)


def in_window(path: Path, since, until) -> bool:
    """The file-modification-time rule: how a session whose records carry no timestamps is
    placed in the window."""
    try:
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return False
    if since and mtime < since:
        return False
    if until and mtime >= until + dt.timedelta(days=1):
        return False
    return True


def could_hold_window(path: Path, since) -> bool:
    """A cheap pre-filter that skips only a file that cannot hold a record in the window: one last
    modified more than MTIME_SLACK before --since, which no difference between clocks is expected
    to bridge. (Nothing can be said from the modification time about --until: a file rewritten
    today can still hold only old records.)"""
    try:
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return False
    return not since or mtime >= since - MTIME_SLACK


def session_in_window(s: Session, since, until) -> bool:
    """A session is in the window by its own records: its latest record is at or after --since
    and its earliest is before the end of --until's day (the midnight after it, exclusive). Only
    a session whose records carry no timestamps falls back to its file's modification time."""
    if s.start is None or s.end is None:
        return in_window(s.path, since, until)
    if since and s.end < since:
        return False
    if until and s.start >= until + dt.timedelta(days=1):
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


def _read_in_window(reader, path: Path, since, until, missing: list, host: str, *args):
    """The session in `path` if it is in the window (see session_in_window), else None."""
    if not could_hold_window(path, since):
        return None
    s = _read_or_note(reader, path, missing, host, *args)
    return s if s and session_in_window(s, since, until) else None


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
                s = _read_in_window(read_codex, p, since, until, missing, host, limit)
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
                    s = _read_in_window(read_codex, p, since, until, missing, host, limit)
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
                s = _read_in_window(read_claude, p, since, until, missing, host, limit)
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
            for reader, paths, subagent in ((read_gemini, json_main, False), (read_gemini, json_sub, True),
                                            (read_gemini_jsonl, jsonl_main, False),
                                            (read_gemini_jsonl, jsonl_sub, True)):
                for p in paths:
                    s = _read_in_window(reader, p, since, until, missing, host, limit, subagent)
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
    except (OSError, ValueError, subprocess.TimeoutExpired):  # ValueError: an argument the OS cannot take (a NUL, a lone surrogate)
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
            except ValueError:
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
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
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
    private evidence file (session transcripts), not something meant to be world-readable. Masking
    is a property of this writer: every line is masked by shape (see mask_known) on its way to
    disk, so no line, header, table cell, or fact reaches a file unmasked, however it was composed.
    The fields taken from a log or a configuration are also masked in full as they are composed."""
    content = "\n".join(mask_known(line) for line in content.split("\n"))
    # Valid JSON can decode to a lone surrogate ("\ud800"), which UTF-8 cannot encode: it is written
    # as the six characters \ud800 rather than raising and costing the run every later file.
    path.write_text(content, encoding="utf-8", errors="backslashreplace")
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
        base = f"{s.host}-{safe_name(mask(s.id))}"  # masked: an id is log content, and this is a file name
        name = base
        if name in used:
            # Prefer a meaningful discriminator (Claude's agentId) over an opaque hash when one
            # is available.
            disambiguator = safe_name(mask(s.agent_id)) if s.agent_id else short_hash(str(s.path.resolve()))
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
        lines.append(f"- {host}: {safe_label(note, 1000) if note else 'root ' + rel_or_abs(Path(roots[host]))}")
    for line in coverage_extra:
        lines.append(f"- {safe_label(line, 1000)}")
    lines += ["", "| host | session | agent | start | end | cwd | user msgs | agent msgs | tool calls | subagent | archived | size | readable | raw log |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in sorted(sessions, key=lambda x: (x.host, x.start or dt.datetime.min.replace(tzinfo=UTC))):
        try:
            size = human_size(s.path.stat().st_size)
        except OSError:
            size = "?"
        readable = f"sessions/{s.out_name}.md"
        cwd = safe_label(rel_or_abs(Path(s.cwd)), 1000) if s.cwd else ""
        lines.append(f"| {s.host} | {safe_label(s.id)} | {safe_label(s.agent_id)} | {iso(s.start)} | {iso(s.end)} | {cwd} | "
                     f"{s.user_messages} | {s.agent_messages} | {s.tool_calls} | {'yes' if s.subagent else 'no'} | "
                     f"{'yes' if s.archived else 'no'} | {size} | [{readable}]({readable}) | {rel_or_abs(s.path)} |")
    write_text_private(out / "index.md", "\n".join(lines) + "\n")


def format_loc(locs) -> str:
    """Where in the session's raw log (named once, in the transcript's header) a note, or a run of
    notes, comes from. `locs` holds each note's (unit, first, last), or None for the whole file;
    every unit that appears gets the range covering its notes (a run can hold both raw lines and
    message numbers), in the order the units first appear, and a whole-file note is kept too."""
    ranges, whole = {}, False
    for loc in locs:
        if loc is None:
            whole = True
            continue
        unit, first, last = loc
        low, high = ranges.get(unit, (first, last))
        ranges[unit] = (min(low, first), max(high, last))
    parts = []
    for unit, (first, last) in ranges.items():
        word = {"line": "line", "msg": "message"}.get(unit, unit)
        parts.append(f"{word} {first}" if first == last else f"{word}s {first}-{last}")
    if whole and parts:
        parts.append("whole file")
    return "raw log" + (" " + ", ".join(parts) if parts else "")


def group_notes(entries):
    """Yield (entry, None) for each entry that gets a line of its own and (None, notes) for each
    maximal run of consecutive plain notes, which gets one line between them."""
    notes = []
    for e in entries:
        if e.kind == "note" and not e.solo:
            notes.append(e)
            continue
        if notes:
            yield None, notes
            notes = []
        yield e, None
    if notes:
        yield None, notes


def format_note_run(notes) -> str:
    """One line for a run of notes: each type in it with how many there were (in the order they
    first appear), the first and last timestamps, and where in the raw log it comes from (see
    format_loc)."""
    counts = {}
    for e in notes:
        counts[e.text] = counts.get(e.text, 0) + 1
    what = ", ".join(f"{label} x{n}" if n > 1 else label for label, n in counts.items())
    stamps = [e.ts for e in notes if e.ts]
    through = f" through {stamps[-1]}" if len(stamps) > 1 and stamps[-1] != stamps[0] else ""
    return f"[{stamps[0] if stamps else ''}] note: {what}{through}  ({format_loc(e.loc for e in notes)})"


def session_lines(s: Session):
    """(is_note, line) for each line of the transcript body."""
    for e, notes in group_notes(s.entries):
        if notes is not None:
            yield True, format_note_run(notes)
        elif e.kind == "note":
            yield True, f"[{e.ts}] note: {e.text}  ({format_loc([e.loc])})"
        else:
            yield False, f"[{e.ts}] {e.kind}: {e.text}  ({e.ref})"


def write_session(out: Path, s: Session):
    lines = [f"# {s.host} {safe_label(s.id)}", "", f"cwd: {safe_label(s.cwd, 1000) if s.cwd else '(unknown)'}  ",
             f"raw log: {s.path}  ",
             f"subagent/side thread: {'yes' if s.subagent else 'no'}",
             f"archived: {'yes' if s.archived else 'no'}", ""]
    lines += [line for _, line in session_lines(s)]
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
            lines += [f"## {safe_label(rel_or_abs(repo), 1000)}", "",
                      f"- default branch: {safe_label(facts['default_branch'], 500) if facts['default_branch'] else '(none found)'}",
                      f"- local branches ({len(facts['branches'])}): {', '.join(safe_label(b, 500) for b in facts['branches']) or '(none)'}",
                      f"- merged into default ({len(facts['merged_branches'])}): "
                      f"{', '.join(safe_label(b, 500) for b in facts['merged_branches']) or '(none)'}",
                      f"- worktrees ({len(facts['worktrees'])}): "
                      f"{', '.join(safe_label(rel_or_abs(Path(w)), 1000) for w in facts['worktrees']) or '(none)'}",
                      f"- stashes ({len(facts['stashes'])}): {'; '.join(safe_label(x, 1000) for x in facts['stashes']) or '(none)'}", ""]

    lines += ["## Scheduled or recurring automations", ""]
    auto, auto_err = codex_automations(codex_sessions_root)
    if auto_err:
        lines.append(f"- codex automations: {safe_label(auto_err, 1000)}")
    elif not auto:
        lines.append("- codex automations: none found")
    else:
        for a in auto:
            f = {k: safe_label(v, 300) for k, v in a.items()}  # read from a configuration file: masked in full
            lines.append(f"- codex automation `{f['id']}`: kind={f['kind']}, status={f['status']}, "
                         f"schedule={f['schedule']}, thread={f['thread']}")
    for label, fn in (("cron", cron_entries), ("systemd --user timers", systemd_timers),
                      ("launchd agents", launchd_agents), ("Windows scheduled tasks", windows_tasks)):
        rows, err = fn()
        if rows is None and err is None:
            continue  # not applicable on this OS
        if err:
            lines.append(f"- {label}: {safe_label(err, 1000)}")
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
    ap.add_argument("--since", default="7d",
                    help="Nd or an ISO date/time; sessions with a record at or after it (default: 7d)")
    ap.add_argument("--until", help="a date, YYYY-MM-DD; sessions that began before the end of that day "
                                    "(the midnight after it is out)")
    ap.add_argument("--out", default=None,
                     help="default: a new private (0700) temp directory, printed on completion")
    ap.add_argument("--root", action="append", metavar="HOST=PATH")
    ap.add_argument("--max-chars", type=int, default=2000)
    ap.add_argument("--force", action="store_true",
                     help="write into an already-nonempty --out instead of refusing")
    args = ap.parse_args(argv)
    try:  # what is printed can hold text from a log (a lone surrogate); never fail on printing it
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass

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
    note_lines = sum(1 for s in sessions for e, notes in group_notes(s.entries) if notes is not None or e.kind == "note")
    by_host = {h: sum(1 for s in sessions if s.host == h) for h in HOSTS}
    print(f"wrote {out}")
    print("sessions: " + ", ".join(f"{h}={n}" for h, n in by_host.items())
          + f" (subagent/side: {sum(1 for s in sessions if s.subagent)}"
          + f", archived: {sum(1 for s in sessions if s.archived)})")
    print(f"unrendered-but-noted records: {notes} (in {note_lines} transcript lines)")
    if missing:
        print("missing or unreadable: " + safe_label("; ".join(missing), 4000))
    return 0


if __name__ == "__main__":
    sys.exit(main())
