#!/usr/bin/env python3
"""Evidence gatherer for a Self-Healing pass: extraction, not interpretation.

Reads the session records of any agent harness from the places it is given, and writes an output
directory an executor can read directly:

    index.md              what each place held, then one row per session file: its id, the place it
                           was found under, its first and last record times, the working directory its
                           records name, how many records it holds, how many text lines come from
                           records whose label names a user and how many from others, how many tool
                           calls, its size, and the paths of its readable transcript and its raw log
    sessions/s-HASH.md     a faithful, timestamped transcript of that file. Its header names the raw
                           log, the working directory, and the facts most of its records share; every
                           line says where in the raw log it came from (file:line, or the record's
                           number in a JSON document). The file name is a short hash of the raw log's
                           path, so that no masking touches it and the index's link always leads to it.
    workspace.md           for each git repository the sessions name as a working directory, and the
                           one gather.py runs in: its branches (merged or not into its default branch),
                           worktrees, and stashes; plus the scheduled or recurring jobs the operating
                           system can list -- facts only, no verdicts

A place is a file of records or a directory searched for them: JSON Lines (.jsonl, .ndjson; a record
per line) or a JSON document (.json) whose records are its longest list of objects that carry a type,
a role, or a time. gather.py knows no harness; each record is shown in its own words:

    label     the values of its "type", "role", "subtype" and "kind" fields, at its top level and down
              the objects that hold its message (the field its own type names, else the first of
              "message", "payload", "item", "data", "msg" and "event"), each once, joined by " > ".
    facts     short values it carries that few records in its file share (a flag such as a meta or a
              summary marker, an origin's kind, a branch that differs); what most records share is
              named once, in the header.
    content   its text (a "content" or "parts" string or list of parts; else a "text", "message",
              "prompt", "summary" or "body" string), each part as what it says it is: text; thinking
              or reasoning, cut at 1,500 characters (or --max-chars if smaller); a tool call, a name
              with its input or arguments, or a command; a tool result, with its exit status where it
              has one, from a result part or from output, stdout and stderr fields. Lists of tool calls
              and of thoughts beside the message are shown too.

A record with none of these, or whose label recurs at least five times with the same text except for
its digits (a reminder a harness repeats every turn), is a note naming its label; a run of consecutive
notes is one line with each label's count and the range of raw lines or record numbers it covers, so
nothing is silently dropped. Who wrote a record is not decided here: a record's role says which side
of the exchange it sits on, and a harness, a hook or a delegating agent can write a user-role record;
its facts and the file it lies in are the evidence, for the executor to weigh.

It does no classification, ranking, scoring, or keyword matching of meaning: no "corrections",
"nudges", "stalls", or residue verdicts. Reading what the evidence means is the executor's job.
It masks obvious secrets (tokens, keys, bearer headers, basic/URL credentials, and key=value or
JSON-shaped assignments, a quoted value to its closing quote however many words it has) in
everything it writes: each value taken from a log as it is composed into a line, a header, an index
cell, or a workspace fact, and every line again as the file is written. A text is masked whole and
then cut to --max-chars, so that nothing is shown that was not read, and a document the cut would
split is already masked. JSON in a text, or in a value, is decoded and masked as the values it holds,
at the level of escaping each was written at, before anything is rendered: every object and array in
it, and every string with an escape in it (a document encoded again is one), whatever escapes it uses
and however long it is, within bounds -- to 100 levels of nesting (an object, an array, or a string
that holds JSON is a level), and until the brackets that look like the start of JSON and are not
count more than a thousand, and one more for every 128 characters of the text, each counting one more
for every 2,048 characters from it to where the decoder failed (the end of the text, where the decoder
does not say: a nest too deep to read). Past a bound only the patterns see an escaped secret, and they
follow a quote escaped up to five levels (32 backslashes). The writer's pass is by shape, and for a
long random-looking run as a pointer needs it, so that a path or a reference into a raw log is masked
too but keeps working: a token-shaped run in it is masked, whole, unless it is part of the name of a
file this run read or of a place it was given, which is a pointer, not a secret; a UUID, a hex id or
a date is shorter than a run. It leaves a bare 40- or 64-character hex string (a git SHA, a sha256
digest) alone, since that is evidence a pass needs to check state, not a secret. Masking recognizes
the shapes secrets commonly have; it cannot catch every secret (a password in plain words, a token a
few characters short of a run, one split across lines), and the output is as sensitive as the logs it
came from.

    gather.py PLACE ... [--since 7d|YYYY-MM-DD] [--until YYYY-MM-DD] [--out DIR] [--force]
              [--max-chars N]

A session is selected by its own records' times: it is in the window when its latest record is at or
after --since and its earliest record is before the end of --until's day (--until takes a date,
YYYY-MM-DD, and refuses a time of day; the midnight after that date is itself out), so a log file
rewritten recently without new records is not selected. A record's time is the first plausible time
(after the year 2000) in a "timestamp", "time", "ts", "created", "date", "updated" or "started" field
(or a variant such as "created_at" or "createdAt"), at its top level or in an object under it. Only
a JSON-lines file that was neither written since --since (by its file's time) nor ends with a record
from then (read from the end of the file) is skipped without being parsed: the file's time alone is
no evidence, since a synced or mis-clocked log can have it days before its last record, and nor is
the last record alone, since the newest can sit ahead of older ones. A log whose last records and
file's time both predate the window is skipped unread, so a recent record placed before older ones in
such a file is not seen: an accepted limit. The file's time decides alone only for a session whose
records carry no times.

With no --out, output goes to a new private (mode 0700) temporary directory, printed on completion --
never the current directory, which risks landing transcripts in a git worktree. An explicit --out
that already exists and is non-empty is refused unless --force, so a rerun cannot silently mix an
earlier run's files with this one's.

A store this script cannot read (a database, a format that is not JSON) is not silently skipped: the
index says what each place held that it did not read, and the executor reads that store directly.
"""
from __future__ import annotations

import argparse
import datetime as dt
import functools
import hashlib
import itertools
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
    # inside a JSON string), so a JSON-shaped assignment is masked like a plain one. A quoted value
    # is masked whole, spaces and all, up to the quote that closes it -- the same quote, escaped as
    # many times as the opening one was, and not itself escaped one level deeper (inside JSON in
    # JSON a quote of the inner string is written with more backslashes than the one that ends it)
    # -- or to the end of the line when none does; a bare one, up to its first space or quote. A
    # quote is escaped by at most 32 backslashes (five levels), so that looking for its twin at
    # every character stays linear.
    r"|(?<![A-Za-z0-9])(?i:(?:api[_-]?key|secret|token|password)\\*[\"']?\s*[:=]\s*"
    r"(?:(?P<q>\\{0,32}[\"'])(?:(?!(?<!\\)(?P=q))[^\n]){6,}"
    r"|\\*[\"']?[^\s\"']{6,}))"
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


def _token_shaped(run: str, minimum: int = 40) -> bool:
    """Whether the catch-all takes `run` for a secret: `minimum` or more characters with a digit and
    a letter in them -- not a bare git SHA or sha256 digest (evidence, not a secret), and not a
    plain word or a uniform run (all letters, or all digits, or all punctuation)."""
    if len(run) < minimum or (HEXRUN.fullmatch(run) and len(run) in (40, 64)):
        return False
    return any(c.isdigit() for c in run) and any(c.isalpha() for c in run)


def _mask_generic(m: re.Match) -> str:
    return "[masked]" if _token_shaped(m.group(0)) else m.group(0)


def _mask_shapes(text: str) -> str:
    text = URL_CREDS.sub(r"\1[masked]@", text)
    text = SPECIFIC_SECRETS.sub("[masked]", text)
    return GENERIC_LONG_RUN.sub(_mask_generic, text)


# Where JSON can begin in text: an object or an array (a bracket followed by what the decoder needs to
# see first: for an object, a key and its colon, or the closing brace; for an array, a bracket, a brace
# or the closing bracket, or a first element that is a string, a number or a literal, and then a comma
# or the closing bracket), or a string with an escape in it (one without is as the patterns see it).
# Whatever the decoder reads passes this, and most of what only looks like JSON (a time or a name in
# brackets) does not, so it never reaches the decoder.
_STRING = r'"[^"\\]*(?:\\.[^"\\]*)*"'
_NUMBER = r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
_PLAIN = r'[^"\\\x00-\x1f]'
_ESCAPED = r'\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})'
_JSON_START = re.compile(
    r"\{(?=\s*(?:\}|" + _STRING + r"\s*:))"
    r"|\[(?=\s*(?:[\[{\]]|(?:" + _STRING + "|" + _NUMBER + r"|true|false|null|NaN|-?Infinity)\s*[,\]]))"
    r'|"(?=' + _PLAIN + "*(?:" + _ESCAPED + _PLAIN + r'*)+")', re.S)


def _int_or_digits(digits: str):
    """A JSON integer as Python reads it, or, too long for Python to convert, its digits as written."""
    try:
        return int(digits)
    except ValueError:
        return digits


_JSON = json.JSONDecoder(parse_int=_int_or_digits)
JSON_WINDOW = 4096


def _decode_at(text: str, start: int):
    """The JSON object, array or string that begins at `start` in `text`, and where it ends, or the
    decoder's error with its position in `text`. It is decoded from a window that begins at `start` and
    grows sixteenfold while the decoder reads to its end, so that what a document costs, and what the
    error costs that says one is not JSON (it counts the lines before it), is in proportion to what was
    read, not to where it is. Each of these ends at a closing character, so one that a window holds whole
    is what the whole text holds (a bare number could go on past a window)."""
    size = JSON_WINDOW
    while True:
        window = text[start:start + size]
        try:
            value, end = _JSON.raw_decode(window)
            return value, start + end
        except json.JSONDecodeError as exc:
            # A window that ends in a token or a string the decoder could not finish may have cut it.
            if start + size < len(text) and (exc.pos > len(window) - 16 or exc.msg.startswith("Unterminated string")):
                size *= 16
                continue
            exc.pos += start
            raise
# JSON is looked for in a text, and decoded, within these bounds. A document is decoded however long it
# is, and strings that hold JSON are followed to 100 levels (an object, an array or a string that holds
# JSON is a level). A bracket that looks like the start of JSON and is not is a miss: the search ends
# when the misses count more than JSON_MISSES, and one more for every JSON_MISSES_PER characters of the
# text, a miss counting one, and one more for every JSON_READ_PER characters from it to where the
# decoder failed (the end of the text, where the decoder does not say: nesting too deep for it). Real
# text has few misses, and short ones; text built to be slow to search is given up on once its misses
# have had the decoder read sixteen times its length and two million characters more, and the patterns
# alone read the rest of it.
JSON_MISSES = 1000
JSON_MISSES_PER = 128
JSON_READ_PER = 2048


def _mask_json_in(text: str, depth: int = 0) -> str:
    """`text` with the JSON in it masked as the values it holds. A secret is found at the level of
    escaping it was written at, not at the deeper one the JSON around it gives it: every object, array
    and string with an escape in it is decoded, whatever escapes it uses (none is looked for first: an
    escape that hides a secret from the patterns may be a slash, a tab, a letter written as a unicode
    escape, a quote), and every key and string in it masked on its own, a string that holds JSON in
    turn the same, and what was masked is written back (what held nothing is left as it was written).
    The bounds are those above."""
    if depth > 100:
        return text
    out, kept, pos, misses, still_open = [], 0, 0, 0, set()
    allowed = JSON_MISSES + len(text) // JSON_MISSES_PER
    while True:
        m = _JSON_START.search(text, pos)
        if m is None:
            break
        start = stop = m.start()
        # A bracket still open where a document around it was found not to be JSON fails there too,
        # so it is not decoded again.
        if start not in still_open:
            try:
                value, end = _decode_at(text, start)
            except (ValueError, RecursionError) as exc:
                stop = len(text)  # how far the decoder read, where it does not say
                if isinstance(exc, json.JSONDecodeError):
                    stop = exc.pos
                    still_open |= _open_brackets(text, start, stop)
            else:
                pos = end
                # The decoded value, its keys beside its values as the patterns read them, with the strings
                # in it masked: written back only if that is not just the value as it was.
                masked = _mask_shapes(json.dumps(_mask_parsed(value, depth + 1), ensure_ascii=False))
                if masked != json.dumps(value, ensure_ascii=False):
                    out += [text[kept:start], masked]
                    kept = end
                continue
        misses += 1 + (stop - start) // JSON_READ_PER
        if misses > allowed:
            break
        pos = start + 1
    return "".join(out) + text[kept:] if out else text


# What a scan for the brackets of JSON has to see: a quote, a backslash, a bracket.
_JSON_SPECIAL = re.compile(r'["\\\[\]{}]')


def _open_brackets(text: str, start: int, stop: int) -> set:
    """Where they are, the brackets of the JSON beginning at `start` that are still open at `stop`, up to
    which the decoder read it as JSON: decoded from any of them, it fails at `stop` too."""
    opened, in_string, escaped = [], False, -1
    for m in _JSON_SPECIAL.finditer(text, start, stop):
        at, c = m.start(), m.group()
        if at == escaped:
            continue
        if c == "\\":
            escaped = at + 1
        elif c == '"':
            in_string = not in_string
        elif not in_string:
            if c in "[{":
                opened.append(at)
            elif opened:
                opened.pop()
    return set(opened)


def _mask_parsed(value, depth: int = 0):
    """A parsed JSON value with every string in it masked (see _mask_json_in)."""
    if depth > 100:
        return value
    if isinstance(value, str):
        return _mask_shapes(_mask_json_in(value, depth))
    if isinstance(value, dict):
        return {_mask_parsed(k, depth + 1): _mask_parsed(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_parsed(v, depth + 1) for v in value]
    return value


def _masked_line(text: str) -> str:
    """The whole of a text, on one line and masked: the cut to a limit is made on this, never before
    it, so that a document the cut would split is already masked, a credential under a key written
    with an escape is found wherever it is, and nothing past the place the text would have been cut
    -- brought up to it when masking shortens what comes before -- is shown unread."""
    return mask(" ".join(text.split()))


def mask(text) -> str:
    """Replace obvious secret-shaped substrings; never a judgment about the surrounding text. JSON
    in the text, and a value that is not text, is masked as the values it holds before it is
    rendered (see _mask_json_in)."""
    if text is None:
        return ""
    if isinstance(text, str):
        return _mask_shapes(_mask_json_in(text))
    return _mask_shapes(json.dumps(_mask_parsed(text), default=str, ensure_ascii=False))


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
    its raw log with (mask_written adds that catch-all, as a pointer needs it)."""
    low = text.lower()
    if not any(marker in low for marker in _SECRET_MARKERS):
        return text
    return SPECIFIC_SECRETS.sub("[masked]", URL_CREDS.sub(r"\1[masked]@", text))


# The runs the catch-all would take for a token that are nevertheless pointers: those in the names of
# the files this run read and of the places it was given. A long id in a file or directory name is what
# a transcript, the index and the coverage lines need to lead back to a raw log, and it is on disk under
# that name already; anything else shaped like a token is masked.
POINTER_RUNS = set()


def note_pointer(path) -> None:
    """Let the runs in the names along `path` through the writer's catch-all (see _mask_pointer_run)."""
    for part in Path(path).parts:
        POINTER_RUNS.update(GENERIC_LONG_RUN.findall(part))


def _mask_pointer_run(m: re.Match) -> str:
    """The catch-all as a pointer needs it: a token-shaped run is masked, whole, unless it is a run of a
    name along a path this run read (see note_pointer). A word wrongly masked hides part of a pointer;
    one missed writes a secret."""
    run = m.group(0)
    return run if not _token_shaped(run) or run in POINTER_RUNS else "[masked]"


def mask_written(text: str) -> str:
    """What the writer applies to every line: mask_known's shapes, and the catch-all for long
    random-looking runs as a pointer needs it (see _mask_pointer_run), so that a path, a reference
    into a raw log or a path cell of the index is masked like any other value, whatever the code that
    composed it did, but keeps working as a pointer when it is made of pointer shapes alone."""
    return GENERIC_LONG_RUN.sub(_mask_pointer_run, mask_known(text))


def trim(text, limit: int, ref: str) -> str:
    """Mask, then cut to `limit` chars. The whole text is masked first, however long a command's
    output or an MCP result happens to be, and the cut is made on what is masked: masking costs time
    in proportion to the text, and what is shown has all been read (see _masked_line)."""
    if not isinstance(text, str):
        text = " ".join(mask(text).split())  # dict/list/etc.: mask() does its own json.dumps
    else:
        text = _masked_line(text)
    return text if len(text) <= limit else text[:limit].rstrip() + f"... [trimmed; full text at {ref}]"


def safe_label(value, limit: int = 200) -> str:
    """A short, masked, single-line description of a record's type, built from log content (a
    drifted log can put anything where a type name is expected), so it is masked and bounded
    like everything else this script writes."""
    text = _masked_line(str(value))
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
            f"error: invalid --since value {value!r}\n"
            "hint: use Nd (e.g. 7d) or an ISO date/time, e.g. 2026-01-01 or 2026-01-01T00:00:00Z"
        )
    # A naive value is assumed UTC; an already-offset value keeps its own offset instead of
    # being silently relabeled as UTC (which would shift the instant it names).
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_until(value):
    """--until: a date, YYYY-MM-DD, which takes in all of that day. Returns the instant the window
    ends, the midnight after it, which is itself out. Anything else (a time of day, Nd) is refused
    rather than read as something it is not."""
    if not value:
        return None
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError(value)
        return dt.datetime.combine(dt.date.fromisoformat(value), dt.time(), UTC) + dt.timedelta(days=1)
    except (ValueError, OverflowError):
        raise SystemExit(f"error: invalid --until value {value!r}\n"
                         "hint: use a date, YYYY-MM-DD; all of that day is included (a time of day is not accepted)")


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def short_hash(value: str, length: int = 12) -> str:
    return hashlib.sha1(str(value).encode("utf-8", "surrogateescape")).hexdigest()[:length]


# ---------------------------------------------------------------- one transcript entry

class Entry:
    """One transcript entry. A note has no raw position in `ref`; it carries `loc` instead, (unit, first,
    last) with unit "line" or "msg" (None for a whole-file note), so a run of notes can be collapsed into
    one line. A `solo` note is already an aggregate and is never merged with its neighbors. A line's
    `kind` is what its piece of the record is ("" for text, "thinking", "tool call", "tool result"), and
    `facts` the record's rare facts, filled in once the whole file is read."""
    __slots__ = ("ts", "kind", "text", "ref", "loc", "solo", "label", "facts", "record")

    def __init__(self, ts, kind, text, ref, loc=None, solo=False, label="", record=0):
        self.ts, self.kind, self.text, self.ref = ts, kind, text, ref
        self.loc, self.solo, self.label, self.record = loc, solo, label, record
        self.facts = ""


class Session:
    """One file of session records and what its transcript shows of it."""

    def __init__(self, path: Path, place: Path):
        self.path, self.place = path, place
        self.id = path.stem
        self.cwd = ""
        self.cwds = set()  # every working directory a record names, for the workspace facts
        self.out_name = ""  # assigned by assign_output_names(); the file this session writes to
        self.start = self.end = None
        self.entries = []
        self.records = 0
        self.user_lines = self.other_lines = self.tool_calls = 0
        self.shared = []  # (key, value) facts most of its records carry, named once in the header

    def touch(self, t):
        if t:
            self.start = t if not self.start or t < self.start else self.start
            self.end = t if not self.end or t > self.end else self.end
        return t

    def note(self, t, label, loc=None, solo=False, record=0):
        """Record something not rendered as a line of its own, named by `label` and located by `loc`:
        ("line", n), ("msg", i), a (unit, first, last) range, or None for the whole raw file."""
        self.touch(t)
        if loc is not None and len(loc) == 2:
            loc = (loc[0], loc[1], loc[1])
        text = mask(label) if solo else safe_label(label)
        self.entries.append(Entry(iso(t), "note", text, "", loc, solo, record=record))


# ---------------------------------------------------------------- reading any harness's records

# The fields whose values say what kind of record, or which side of an exchange, a record is.
LABEL_KEYS = ("type", "role", "subtype", "kind")
# The fields under which a record commonly nests the message or event it carries.
WRAPPER_KEYS = ("message", "payload", "item", "data", "msg", "event")
# The fields that hold a message's text when it has no "content" or "parts": the first that is a string
# (a "summary" of one word is a setting, not a summary).
TEXT_KEYS = ("text", "message", "prompt", "summary", "body")
# Field names, lower-cased with everything but letters and digits removed, that hold a time, a working
# directory, or a session id.
TIME_KEYS = {"timestamp", "time", "ts", "created", "createdat", "date", "datetime", "updated", "updatedat",
             "lastupdated", "started", "startedat", "starttime", "start"}
CWD_KEYS = {"cwd", "workdir", "workingdir", "workingdirectory", "projectpath", "projectroot", "projectdir"}
SESSION_ID_KEYS = {"sessionid"}
# The fields that hold what a command or a tool produced, and how it ended.
OUTPUT_KEYS = {"output", "result", "stdout", "stderr", "response"}
STATUS_KEYS = ("exitcode", "returncode", "exitstatus", "status")  # in the order a line prefers them
# The words in a label that name a person's side of the exchange, for the index's counts.
USER_WORDS = {"user", "human"}
# A thinking or reasoning line is cut here, or at --max-chars if that is smaller.
THINKING_LIMIT = 1500
# A label whose text repeats this many times, the same but for its digits, is a note, not a line each time.
REPEATS_TO_NOTE = 5
EARLIEST = dt.datetime(2000, 1, 1, tzinfo=UTC)
_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


@functools.lru_cache(maxsize=65536)
def norm(key) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _words(value) -> frozenset:
    """The lower-case words of a label or a type: split at case changes and at anything not a letter."""
    return _words_of(value if isinstance(value, str) else str(value))


@functools.lru_cache(maxsize=65536)
def _words_of(text: str) -> frozenset:
    return frozenset(re.findall(r"[a-z]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", text).lower()))


def plausible_time(value):
    """The time `value` names if it could be when a record was written (an ISO time, or seconds or
    milliseconds since the epoch, after the year 2000), else None: a duration or a count is not a time."""
    if isinstance(value, bool):
        return None
    t = stamp(value)
    return t if t and EARLIEST <= t and t.year < 2200 else None


def record_time(rec):
    """The first plausible time in one of a record's TIME_KEYS, at its top level, else in the objects
    under it (an object named by a time key, such as "time": {"created": ...}, included), two levels
    down at most."""
    level = [rec]
    for _ in range(3):
        deeper = []
        for obj in level:
            for key, value in obj.items():
                if isinstance(value, dict):
                    deeper.append(value)
                elif norm(key) in TIME_KEYS:
                    t = plausible_time(value)
                    if t:
                        return t
        level = deeper
    return None


def holders(rec) -> list:
    """The record and the objects down from it that hold its message: at each level the field its own
    "type" names when that is an object (a record of type "attachment" holding an "attachment"), else the
    first of WRAPPER_KEYS that is one; three levels down at most."""
    chain = [rec]
    for _ in range(3):
        cur, kind = chain[-1], chain[-1].get("type")
        nxt = cur.get(kind) if isinstance(kind, str) and isinstance(cur.get(kind), dict) else None
        if nxt is None:
            nxt = next((cur[k] for k in WRAPPER_KEYS if isinstance(cur.get(k), dict)), None)
        if nxt is None:
            break
        chain.append(nxt)
    return chain


def record_label(chain) -> str:
    """What a record says it is, in its own words (see holders): the values of its LABEL_KEYS down the
    chain, each once."""
    words = []
    for obj in chain:
        for key in LABEL_KEYS:
            value = obj.get(key)
            if (isinstance(value, str) and value and len(value) <= 60 and not any(c.isspace() for c in value)
                    and value not in words):
                words.append(value)
    return " > ".join(words)


def _id_shaped(value: str) -> bool:
    """An identifier rather than a value worth showing as a fact: a UUID, a long hex or digit run, or a
    run shaped like a token."""
    return bool(_UUID.search(value) or re.fullmatch(r"[0-9a-fA-F]{12,}|[0-9]{6,}", value) or _token_shaped(value, 20))


def _fact(value):
    if isinstance(value, bool):
        return "true" if value else None  # false is what a flag's absence says too
    return _word_fact(value) if isinstance(value, str) and 0 < len(value) <= 80 else None


_SPACE = re.compile(r"\s")


@functools.lru_cache(maxsize=65536)
def _word_fact(value: str):
    return None if _SPACE.search(value) or _id_shaped(value) else value


# The fields a line shows as its content, which are not facts besides.
CONTENT_KEYS = {"content", "parts", "text", "message", "prompt", "summary", "body", "name", "input", "arguments",
                "args", "parameters", "command", "cmd", "function"}


def record_facts(rec, chain) -> list:
    """(key, value) for each short value a record carries besides what its line shows: a flag that is set,
    or a word or a path without spaces that is not an identifier, at the top level of the record or of an
    object holding its message, or one level into a small object there (an "origin" holding a "kind")."""
    facts = []
    for holder in chain:
        for key, value in holder.items():
            if (key in LABEL_KEYS or norm(key) in TIME_KEYS or (holder is not rec and key in CONTENT_KEYS)
                    or any(value is held for held in chain[1:])):
                continue
            if isinstance(value, dict):
                if len(value) <= 8:
                    facts += [(f"{key}.{k}", f) for k, v in value.items()
                              if norm(k) not in TIME_KEYS and (f := _fact(v)) is not None]
            elif (f := _fact(value)) is not None:
                facts.append((key, f))
    return facts


def _text(value, depth: int = 0) -> str:
    """The text in a value: a string, or the texts of a list of strings and parts, or of an object's
    text fields."""
    if depth > 8:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(t for t in (_text(v, depth + 1) for v in value) if t)
    if isinstance(value, dict):
        for key in ("text", "content", "output", "result", "thinking", "summary", "message", "value"):
            if key in value:
                t = _text(value[key], depth + 1)
                if t:
                    return t
    return ""


def _call(obj: dict) -> str:
    """A tool call an object describes: a name with its input or arguments (a "function" object's
    included), or a command; "" if it describes none."""
    fn = obj.get("function") if isinstance(obj.get("function"), dict) else obj
    name = fn.get("name")
    for key in ("input", "arguments", "args", "parameters"):
        if isinstance(name, str) and name and key in fn:
            args = fn[key]
            return f"{name}({args if isinstance(args, str) else json.dumps(args, ensure_ascii=False, default=str)})"
    command = obj.get("command", obj.get("cmd"))
    if isinstance(command, list) and command and all(isinstance(c, str) for c in command):
        return " ".join(command)
    return command if isinstance(command, str) and command.strip() else ""


def _status(obj: dict) -> str:
    """How a command or a tool ended, as the object says: its exit code, else its status."""
    named = {norm(key): (key, value) for key, value in obj.items()
             if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value)}
    for wanted in STATUS_KEYS:
        if wanted in named:
            return f"({named[wanted][0]} {named[wanted][1]}) "
    return ""


def _result(obj: dict) -> str:
    """What a command or a tool produced, from the object's output fields (each named when there are
    several), with its exit status first where it has one; "" if it has none."""
    found = [(key, _text(value)) for key, value in obj.items()
             if norm(key) in OUTPUT_KEYS or norm(key).endswith("output")]
    found = [(key, text) for key, text in found if text.strip()]
    if not found:
        return ""
    body = found[0][1] if len(found) == 1 else " | ".join(f"{key}: {text}" for key, text in found)
    return _status(obj) + body


def _part(part) -> list:
    """(kind, text) for one part of a message's content, as the part says what it is."""
    if isinstance(part, str):
        return [("", part)] if part.strip() else []
    if not isinstance(part, dict):
        return []
    kind = part.get("type")
    words = _words(kind or "")
    if words & {"thinking", "reasoning", "thought"}:
        text = _text(part.get("thinking")) or _text(part.get("text")) or _text(part.get("summary")) or _text(part.get("content"))
        return [("thinking", text)] if text.strip() else []
    if "text" in words and isinstance(part.get("text"), str):
        return [("", part["text"])] if part["text"].strip() else []
    call = _call(part)
    if words & {"result", "output", "response"} or (not call and any(k in part for k in ("tool_use_id", "call_id", "tool_call_id"))):
        error = " (error)" if any(part.get(k) is True for k in ("is_error", "isError", "error")) else ""
        body = _text(part.get("content")) or _result(part) or _text(part.get("text"))
        return [("tool result" + error, _status(part) + body)]
    if call:
        return [("tool call", call)]
    text = _text(part.get("text"))
    if text.strip():
        return [("", text)]
    if words & {"image", "audio", "video", "file", "document"}:
        return [("", f"[{kind}]")]
    return []


def record_pieces(chain) -> list:
    """(kind, text) for each piece of a record a line shows: its content, part by part; else what it
    says as a tool call, a tool result, or reasoning, or its first TEXT_KEYS string; and any list of tool
    calls or of thoughts beside its message."""
    holder = chain[-1]
    pieces = []
    content = next((holder[k] for k in ("content", "parts") if isinstance(holder.get(k), (str, list))), None)
    if isinstance(content, str):
        if content.strip():
            pieces.append(("", content))
    elif isinstance(content, list):
        for part in content:
            pieces += _part(part)
    if not pieces:
        words = _words(holder.get("type") or "")
        call, result = _call(holder), _result(holder)
        if words & {"thinking", "reasoning", "thought"}:
            text = _text(holder.get("summary")) or _text(holder.get("text")) or _text(holder.get("thinking"))
            if text.strip():
                pieces.append(("thinking", text))
        if call:
            pieces.append(("tool call", call))
        if result:
            pieces.append(("tool result", result))
        if not pieces:
            text = next((holder[k] for k in TEXT_KEYS if isinstance(holder.get(k), str) and holder[k].strip()
                         and (k != "summary" or len(holder[k].split()) > 1)), "")
            if text:
                pieces.append(("", text))
    for obj in chain:
        for key in ("toolCalls", "tool_calls"):
            for call in obj.get(key) or [] if isinstance(obj.get(key), list) else []:
                if isinstance(call, dict) and _call(call):
                    pieces.append(("tool call", _call(call)))
                    if _result(call):
                        pieces.append(("tool result", _result(call)))
        thoughts = obj.get("thoughts")
        if isinstance(thoughts, list):
            for thought in thoughts:
                text = (" - ".join(v for v in thought.values() if isinstance(v, str) and v.strip())
                        if isinstance(thought, dict) else _text(thought))
                if text.strip():
                    pieces.append(("thinking", text))
    return pieces


def _records_list(doc):
    """The records of a JSON document: the longest list of objects in it, breadth-first to three levels
    down, of which at least half carry a label or a time; None if it has none."""
    candidates, level = [], [doc]
    for _ in range(4):
        deeper = []
        for value in level:
            if isinstance(value, list):
                if value and all(isinstance(v, dict) for v in value):
                    candidates.append(value)
            elif isinstance(value, dict):
                deeper += [v for v in value.values() if isinstance(v, (dict, list))]
        level = deeper
    best = None
    for items in candidates:
        marked = sum(1 for r in items if record_label(holders(r)) or record_time(r))
        if marked * 2 >= len(items) and (best is None or len(items) > len(best)):
            best = items
    return best


def _absolute(value) -> str:
    return value if isinstance(value, str) and (value.startswith("/") or re.match(r"[A-Za-z]:[\\/]", value)) else ""


def _session_facts(s: Session, obj, chain=()) -> None:
    """The session id and working directories a record (or a JSON document's top level) names."""
    for holder in (obj, *chain[1:]):
        for key, value in holder.items():
            k = norm(key)
            if k in SESSION_ID_KEYS and isinstance(value, (str, int)) and str(value) and s.id == s.path.stem:
                s.id = str(value)
            elif k in CWD_KEYS and _absolute(value):
                s.cwds.add(value)


def read_session(path: Path, place: Path, limit: int):
    """The session in a file of records, or (None, why) for a file that holds none."""
    s = Session(path, place)
    cwd_counts = {}
    facts_of = []  # each record's facts, by record number
    if record_kind(path) == ".json":
        try:
            with open_records(path) as fh:
                doc = json.loads(fh.read())
        except OSError as exc:
            return None, str(exc)
        except (ValueError, RecursionError) as exc:
            return None, f"not a JSON document ({exc.__class__.__name__})"
        records = _records_list(doc)
        if records is None:
            return None, "a JSON document with no list of records"
        if isinstance(doc, dict):
            _session_facts(s, doc)
            for key, value in doc.items():
                if norm(key) in TIME_KEYS:
                    s.touch(plausible_time(value))
        located = (((("msg", i), f"{path} record {i}"), r, None) for i, r in enumerate(records, 1))
    else:
        try:
            located = _lines(path)
            first = next(located, None)
        except OSError as exc:
            return None, str(exc)
        located = itertools.chain([first] if first is not None else [], located)
    for (loc, ref), rec, err in located:
        number = len(facts_of)
        if err is not None:
            s.note(None, unparseable(err), loc, record=number)
            facts_of.append([])
            continue
        if not isinstance(rec, dict):
            s.note(None, f"a record that is not an object ({type(rec).__name__})", loc, record=number)
            facts_of.append([])
            continue
        s.records += 1
        try:
            t = s.touch(record_time(rec))
            chain = holders(rec)
            label = record_label(chain) or "(no type or role)"
            _session_facts(s, rec, chain)
            for holder in chain:
                cwd = next((v for k, v in holder.items() if norm(k) in CWD_KEYS and _absolute(v)), "")
                if cwd:
                    cwd_counts[cwd] = cwd_counts.get(cwd, 0) + 1
            facts_of.append(record_facts(rec, chain))
            pieces = record_pieces(chain)
            for kind, text in pieces:
                bound = min(limit, THINKING_LIMIT) if kind == "thinking" else limit
                s.entries.append(Entry(iso(t), kind, trim(text, bound, ref), ref, loc, label=label, record=number))
            if not pieces:
                s.note(t, label, loc, record=number)
        except Exception as exc:  # a drifted or malformed record must not sink the whole run
            s.note(None, f"error reading record ({exc.__class__.__name__}: {exc})", loc, record=number)
            if len(facts_of) == number:
                facts_of.append([])
    if not s.records and not s.entries:
        return None, "no records"
    s.cwd = max(cwd_counts, key=cwd_counts.get) if cwd_counts else ""
    _finish(s, facts_of)
    return s, None


def _lines(path: Path):
    with open_records(path) as fh:
        for number, line in enumerate(fh, 1):
            if line.strip():
                rec, err = parse_json(line)
                yield (("line", number), f"{path}:{number}"), rec, err


def _finish(s: Session, facts_of: list) -> None:
    """Once a file is read: the facts most of its records share go to its header, each record's rare
    facts onto its lines, and a label whose every line repeats the same but for its digits (at least
    REPEATS_TO_NOTE times) becomes notes."""
    n = max(1, len(facts_of))
    counts = {}
    for facts in facts_of:
        for fact in set(facts):
            counts[fact] = counts.get(fact, 0) + 1
    best = {}
    for (key, value), count in counts.items():
        if count * 2 >= n and count > best.get(key, ("", 0))[1]:
            best[key] = (value, count)
    s.shared = sorted((key, value) for key, (value, _) in best.items())
    shared = set(s.shared)
    rare = max(1, n // 4)
    lines = {}
    for e in s.entries:
        if e.kind != "note":
            lines.setdefault(e.label, []).append((e.kind, re.sub(r"[0-9]+", "#", e.text.replace(e.ref, ""))))
    repeated = {label for label, seen in lines.items() if len(seen) >= REPEATS_TO_NOTE and len(set(seen)) == 1}
    for i, e in enumerate(s.entries):
        if e.kind != "note" and e.label in repeated:
            s.entries[i] = Entry(e.ts, "note", safe_label(e.label), "", (e.loc[0], e.loc[1], e.loc[1]), record=e.record)
            continue
        if e.kind == "note":
            continue
        facts = [(k, v) for k, v in facts_of[e.record] if counts[(k, v)] <= rare and (k, v) not in shared]
        e.facts = " {" + ", ".join(k if v == "true" else f"{k}={v}" for k, v in facts) + "}" if facts else ""
        if e.kind == "" and USER_WORDS & _words(e.label):
            s.user_lines += 1
        elif e.kind == "":
            s.other_lines += 1
        elif e.kind == "tool call":
            s.tool_calls += 1


# ---------------------------------------------------------------- which sessions are in the window

def in_window(path: Path, since, until) -> bool:
    """The file-modification-time rule: how a session whose records carry no times is placed in the
    window."""
    try:
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return False
    if since and mtime < since:
        return False
    if until and mtime >= until:
        return False
    return True


# How much of the end of a log is read to find the time of its last record. A record longer than
# that makes the read grow, fourfold at a time, until it holds one.
TAIL_BYTES = 64 * 1024


def _line_time(line: bytes):
    """The time a JSON-lines record carries (see record_time), or None for a line that is not a record
    (a cut-short one, say)."""
    rec, err = parse_json(line.decode("utf-8", errors="replace"))
    return record_time(rec) if err is None and isinstance(rec, dict) else None


def last_record_time(path: Path):
    """When the last record of a JSON-lines log was written, by the log's own clock, read from the end
    of the file; None if no record in it carries a time, or it cannot be read."""
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            window = TAIL_BYTES
            while True:
                start = max(0, size - window)
                fh.seek(start)
                lines = fh.read(size - start).split(b"\n")
                if start:
                    lines = lines[1:]  # the first line is probably cut short
                times = [t for t in map(_line_time, lines) if t]
                if times:
                    return max(times)
                if not start:
                    return None
                window *= 4
    except OSError:
        return None


def could_hold_window(path: Path, since) -> bool:
    """A cheap pre-filter that skips only a file that cannot hold a record in the window: one that
    neither its modification time nor its own last record says was written since --since. Either
    being recent means it is read. The modification time alone is no evidence that it was not (a log
    synced from another machine, or written under a wrong clock, can be stamped days before its last
    record), and the last record alone, read from the end of the file, is none either (the newest can
    sit ahead of older ones); a log in which no record carries a time is placed by its file's time, the
    rule that places such a session (see in_window). A JSON document has no last line to read, and is
    read whole; a compressed log has none to read cheaply, and is skipped when its file's time, which
    compressing it set, is older than --since. (Nothing can be said about --until: a log can hold only
    old records and be written today.)"""
    try:
        path.stat()
    except OSError:
        return False
    if not since or record_kind(path) == ".json" or in_window(path, since, None):
        return True
    if path.suffix in COMPRESSED_SUFFIXES:
        return False  # a compressed log has no end to read cheaply: its file's time, set when it was compressed, decides
    last = last_record_time(path)
    return last is not None and last >= since


def session_in_window(s: Session, since, until) -> bool:
    """A session is in the window by its own records: its latest record is at or after --since and its
    earliest is before `until`, the instant the window ends (the midnight after --until's day, see
    parse_until). Only a session whose records carry no times falls back to its file's modification
    time."""
    if s.start is None or s.end is None:
        return in_window(s.path, since, until)
    if since and s.end < since:
        return False
    if until and s.start >= until:
        return False
    return True


# ---------------------------------------------------------------- the places the records are kept

RECORD_SUFFIXES = (".jsonl", ".ndjson", ".json")
# A compressed record file is read through its decompressor (zstd through the standard library from
# Python 3.14, else through a zstd command on PATH).
COMPRESSED_SUFFIXES = (".gz", ".bz2", ".xz", ".zst")


def record_kind(path: Path) -> str:
    """The record suffix of a record file's name, under any compression suffix (".jsonl" for x.jsonl.zst),
    or "" for a file that is not one."""
    name = path.name[:-len(path.suffix)] if path.suffix in COMPRESSED_SUFFIXES else path.name
    return next((suffix for suffix in RECORD_SUFFIXES if name.endswith(suffix)), "")


def open_records(path: Path):
    """A text stream of a record file, decompressed as its name says; OSError when it cannot be."""
    suffix = path.suffix
    if suffix == ".gz":
        import gzip
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    if suffix == ".bz2":
        import bz2
        return bz2.open(path, "rt", encoding="utf-8", errors="replace")
    if suffix == ".xz":
        import lzma
        return lzma.open(path, "rt", encoding="utf-8", errors="replace")
    if suffix == ".zst":
        try:
            from compression import zstd
            return zstd.open(path, "rt", encoding="utf-8", errors="replace")
        except ImportError:
            pass
        if not shutil.which("zstd"):
            raise OSError("zstd-compressed, and neither Python's zstd module nor a zstd command is available")
        import io
        done = subprocess.run(["zstd", "-dcq", str(path)], capture_output=True, timeout=300)
        if done.returncode:
            raise OSError(f"zstd could not decompress it ({done.stderr.decode(errors='replace').strip()[:200]})")
        return io.StringIO(done.stdout.decode("utf-8", errors="replace"))
    return path.open(encoding="utf-8", errors="replace")


def record_files(place: Path):
    """(the record files a place holds, how many other files it holds): the place itself when it is a
    file, else every file under it with a record suffix (compressed or not), symbolic links to
    directories not followed."""
    if place.is_file():
        return [place], 0
    files, others = [], 0
    for directory, subdirectories, names in os.walk(place, onerror=lambda exc: None):
        subdirectories.sort()
        for name in sorted(names):
            if record_kind(Path(name)):
                files.append(Path(directory) / name)
            else:
                others += 1
    return files, others


def gather_places(places, since, until, limit: int):
    """(sessions, coverage): each place's sessions in the window, and one line per place saying what it
    held, including what it held that was not read or could not be."""
    sessions, coverage = [], []
    for place in places:
        note_pointer(place)
        if not place.exists():
            coverage.append(f"{rel_or_abs(place)}: not found")
            continue
        files, others = record_files(place)
        found, outside, unread = 0, 0, {}
        for path in files:
            note_pointer(path)
            if not could_hold_window(path, since):
                outside += 1
                continue
            try:
                s, why = read_session(path, place, limit)
            except Exception as exc:  # one file that cannot be read must not cost every other one its evidence
                s, why = None, f"failed to read ({exc.__class__.__name__}: {exc})"
            if s is None:
                unread.setdefault(why, []).append(path)
            elif session_in_window(s, since, until):
                sessions.append(s)
                found += 1
            else:
                outside += 1
        parts = [f"{len(files)} record file(s)", f"{found} session(s) in the window"]
        if outside:
            parts.append(f"{outside} outside it")
        for why, paths in sorted(unread.items()):
            parts.append(f"{len(paths)} not read, {safe_label(why, 300)} (e.g. {rel_or_abs(paths[0])})")
        if others:
            parts.append(f"{others} other file(s) not read")
        coverage.append(f"{rel_or_abs(place)}: " + "; ".join(parts))
    return sessions, coverage


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


# ---------------------------------------------------------------- workspace facts (scheduled jobs)

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
    is a property of this writer: every line is masked by shape (see mask_written) on its way to
    disk, so no line, header, table cell, path or reference reaches a file unmasked, however it was
    composed. The fields taken from a log or a configuration are also masked in full as they are
    composed."""
    content = "\n".join(mask_written(line) for line in content.split("\n"))
    # Valid JSON can decode to a lone surrogate ("\ud800"), which UTF-8 cannot encode: it is written
    # as the six characters \ud800 rather than raising and costing the run every later file.
    path.write_text(content, encoding="utf-8", errors="backslashreplace")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def assign_output_names(sessions) -> None:
    """Set each session's `out_name`, the file it writes to under sessions/: a short hash of the raw log's
    path. The index links to a file by its name and the writer masks every line it writes, so a name
    taken from a log -- an id can be a long, mixed run like a token -- would be written to the index masked
    and to disk as it was; a generated name is one masking cannot touch, and two raw logs never share it."""
    used = set()
    for s in sorted(sessions, key=lambda x: str(x.path)):
        base = f"s-{short_hash(str(s.path))}"
        name, n = base, 1
        while name in used:  # a collision of 48 bits: never an overwrite
            n += 1
            name = f"{base}-{n}"
        used.add(name)
        s.out_name = name


def write_index(out: Path, sessions, coverage, places):
    lines = ["# Session index", "", "Places:"]
    if not places:
        lines.append("- none given: name the places where the harnesses that did the work keep their session records")
    lines += [f"- {line}" for line in coverage]  # composed with each value from a log masked, its paths as pointers
    lines += ["", "| session | place | start | end | cwd | records | user-role text | other text | tool calls | size | readable | raw log |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in sorted(sessions, key=lambda x: (x.start or dt.datetime.min.replace(tzinfo=UTC), str(x.path))):
        try:
            size = human_size(s.path.stat().st_size)
        except OSError:
            size = "?"
        readable = f"sessions/{s.out_name}.md"
        cwd = safe_label(rel_or_abs(Path(s.cwd)), 1000) if s.cwd else ""
        lines.append(f"| {safe_label(s.id)} | {rel_or_abs(s.place)} | {iso(s.start)} | {iso(s.end)} | {cwd} | {s.records} | "
                     f"{s.user_lines} | {s.other_lines} | {s.tool_calls} | {size} | [{readable}]({readable}) | "
                     f"{rel_or_abs(s.path)} |")
    write_text_private(out / "index.md", "\n".join(lines) + "\n")


def format_loc(locs) -> str:
    """Where in the session's raw log (named once, in the transcript's header) a note, or a run of
    notes, comes from. `locs` holds each note's (unit, first, last), or None for the whole file;
    every unit that appears gets the range covering its notes (a run can hold both raw lines and
    record numbers), in the order the units first appear, and a whole-file note is kept too."""
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
        word = {"line": "line", "msg": "record"}.get(unit, unit)
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
    """One line for a run of notes: each label in it with how many there were (in the order they
    first appear), the first and last times, and where in the raw log it comes from (see
    format_loc)."""
    counts = {}
    for e in notes:
        counts[e.text] = counts.get(e.text, 0) + 1
    what = ", ".join(f"{label} x{n}" if n > 1 else label for label, n in counts.items())
    stamps = [e.ts for e in notes if e.ts]
    through = f" through {stamps[-1]}" if len(stamps) > 1 and stamps[-1] != stamps[0] else ""
    return f"[{stamps[0] if stamps else ''}] note: {what}{through}  ({format_loc(e.loc for e in notes)})"


def session_lines(s: Session):
    """(is_note, line) for each line of the transcript body. A line whose text is the same as the line
    before it (a harness that logs a message twice, under two record types) says so rather than repeat
    it, and still has its own place in the raw log."""
    before = None
    for e, notes in group_notes(s.entries):
        if notes is not None:
            before = None
            yield True, format_note_run(notes)
        elif e.kind == "note":
            before = None
            yield True, f"[{e.ts}] note: {e.text}  ({format_loc([e.loc])})"
        else:
            piece = f" - {e.kind}" if e.kind else ""
            text = e.text.replace(e.ref, "")
            shown = "(the same text as the line before)" if before == (e.kind, text) else e.text
            before = (e.kind, text)
            yield False, f"[{e.ts}] {safe_label(e.label)}{safe_label(e.facts, 1000)}{piece}: {shown}  ({e.ref})"


def write_session(out: Path, s: Session):
    shared = ", ".join(f"{k}={v}" for k, v in s.shared)
    lines = [f"# Session {safe_label(s.id)}", "",
             f"place: {rel_or_abs(s.place)}  ",
             f"raw log: {s.path}  ",
             f"cwd: {safe_label(s.cwd, 1000) if s.cwd else '(no record names one)'}  ",
             f"records: {s.records}  ",
             f"most records carry: {safe_label(shared, 4000) if shared else '(nothing in common)'}", ""]
    lines += [line for _, line in session_lines(s)]
    write_text_private(out / "sessions" / f"{s.out_name}.md", "\n".join(lines) + "\n")


def write_workspace(out: Path, sessions):
    lines = ["# Workspace facts", ""]
    if shutil.which("git") is None:
        lines.append("git was not found on PATH; branch, worktree, and stash facts are unavailable.")
        lines.append("")
    else:
        roots_seen = {}
        for cwd in sorted({c for s in sessions for c in s.cwds} | {os.getcwd()}):
            r = repo_root_for(cwd)
            if r:
                roots_seen.setdefault(str(r), r)
        if not roots_seen:
            lines.append("No session named a working directory that resolves to a git repository, and this one is not in one.")
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

    lines += ["## Scheduled or recurring jobs the operating system lists", ""]
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
    lines += ["", "A harness's own schedules (recurring tasks or automations it runs itself) are not listed here."]
    write_text_private(out / "workspace.md", "\n".join(lines) + "\n")


# ---------------------------------------------------------------- main

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
    ap.add_argument("places", nargs="*", metavar="PLACE",
                    help="a file of session records, or a directory searched for them (.jsonl, .ndjson, .json)")
    ap.add_argument("--since", default="7d",
                    help="Nd or an ISO date/time; sessions with a record at or after it (default: 7d)")
    ap.add_argument("--until", help="a date, YYYY-MM-DD; sessions that began before the end of that day "
                                    "(the midnight after it is out)")
    ap.add_argument("--out", default=None,
                    help="default: a new private (0700) temp directory, printed on completion")
    ap.add_argument("--max-chars", type=int, default=2000)
    ap.add_argument("--force", action="store_true",
                    help="write into an already-nonempty --out instead of refusing")
    args = ap.parse_args(argv)
    try:  # what is printed can hold text from a log (a lone surrogate); never fail on printing it
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass

    since = parse_when(args.since)
    until = parse_until(args.until)
    # Expand `~` here: a place quoted, or passed by a program rather than a shell, keeps it literally.
    places = [Path(p).expanduser() for p in args.places]
    out = prepare_out_dir(Path(args.out) if args.out else None, args.force)
    (out / "sessions").mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(out / "sessions", 0o700)
    except OSError:
        pass

    sessions, coverage = gather_places(places, since, until, args.max_chars)
    assign_output_names(sessions)
    write_index(out, sessions, coverage, places)
    for s in sessions:
        write_session(out, s)
    write_workspace(out, sessions)

    notes = sum(1 for s in sessions for e in s.entries if e.kind == "note")
    note_lines = sum(1 for s in sessions for e, run in group_notes(s.entries) if run is not None or e.kind == "note")
    print(f"wrote {out}")
    print(f"sessions: {len(sessions)} from {len(places)} place(s), {sum(s.records for s in sessions)} records")
    print(f"unrendered-but-noted records: {notes} (in {note_lines} transcript lines)")
    if not places:
        print("no places given: name the places where the harnesses that did the work keep their session records")
    for line in coverage:
        print(mask_written(line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
