"""Parse one access-log line written in logfmt by the edge proxies.

A line is a sequence of key=value pairs separated by spaces or tabs. A value is
either bare (everything up to the next space or tab) or double-quoted, where a
backslash makes the next character literal (so \\" is a quote and \\\\ a
backslash). Unknown keys are ignored; when a key repeats, the last value wins.
"""

import re
from dataclasses import dataclass

TS_RE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z")
DUR_RE = re.compile(r"([0-9]+)(?:\.([0-9]+))?(us|ms|s)")
METHOD_RE = re.compile(r"[A-Z]+")
STATUS_RE = re.compile(r"[0-9]{3}")
BYTES_RE = re.compile(r"[0-9]+")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

# Fraction digits a duration may carry in each unit: durations are kept as whole microseconds.
DUR_SCALE = {"us": 0, "ms": 3, "s": 6}

SEPARATORS = " \t"


class ParseError(ValueError):
    """A line that is not a valid request record."""


@dataclass(frozen=True)
class Request:
    ts: str
    method: str
    path: str
    status: int
    dur_us: int
    bytes: int


def split_pairs(line):
    """Return the key=value pairs of a logfmt line as a dict."""
    pairs = {}
    i, n = 0, len(line)
    while i < n:
        if line[i] in SEPARATORS:
            i += 1
            continue
        start = i
        while i < n and line[i] != "=" and line[i] not in SEPARATORS:
            i += 1
        if i >= n or line[i] != "=":
            raise ParseError(f"expected key=value at column {start + 1}")
        key = line[start:i]
        if not key:
            raise ParseError(f"empty key at column {start + 1}")
        i += 1  # the "="
        if i < n and line[i] == '"':
            i += 1
            chars = []
            while True:
                if i >= n:
                    raise ParseError(f"unterminated quote in {key}")
                c = line[i]
                if c == "\\":
                    if i + 1 >= n:
                        raise ParseError(f"unterminated quote in {key}")
                    chars.append(line[i + 1])
                    i += 2
                elif c == '"':
                    i += 1
                    break
                else:
                    chars.append(c)
                    i += 1
            if i < n and line[i] not in SEPARATORS:
                raise ParseError(f"text after closing quote in {key}")
            value = "".join(chars)
        else:
            vstart = i
            while i < n and line[i] not in SEPARATORS:
                i += 1
            value = line[vstart:i]
        pairs[key] = value
    return pairs


def valid_timestamp(ts):
    m = TS_RE.fullmatch(ts)
    if not m:
        return False
    _, month, day, hour, minute, second = (int(g) for g in m.groups())
    return 1 <= month <= 12 and 1 <= day <= 31 and hour <= 23 and minute <= 59 and second <= 59


def parse_duration(text):
    """Duration text such as 12ms, 1.5s or 350us, as whole microseconds."""
    m = DUR_RE.fullmatch(text)
    if not m:
        raise ParseError(f"bad duration {text!r}")
    whole, frac, unit = m.group(1), m.group(2) or "", m.group(3)
    scale = DUR_SCALE[unit]
    if len(frac) > scale:
        raise ParseError(f"bad duration {text!r}")
    return int(whole) * 10 ** scale + (int(frac.ljust(scale, "0")) if scale else 0)


def parse_line(line):
    """Parse one line into a Request; ParseError says why it is not one."""
    pairs = split_pairs(line)
    for key in ("ts", "method", "path", "status", "dur"):
        if key not in pairs:
            raise ParseError(f"missing {key}")
    ts = pairs["ts"]
    if not valid_timestamp(ts):
        raise ParseError(f"bad timestamp {ts!r}")
    method = pairs["method"]
    if not METHOD_RE.fullmatch(method):
        raise ParseError(f"bad method {method!r}")
    path = pairs["path"]
    if not path.startswith("/"):
        raise ParseError(f"bad path {path!r}")
    status = pairs["status"]
    if not STATUS_RE.fullmatch(status) or not 100 <= int(status) <= 599:
        raise ParseError(f"bad status {status!r}")
    size = pairs.get("bytes", "0")
    if not BYTES_RE.fullmatch(size):
        raise ParseError(f"bad bytes {size!r}")
    return Request(ts=ts, method=method, path=path, status=int(status),
                   dur_us=parse_duration(pairs["dur"]), bytes=int(size))


def normalize_path(path):
    """Drop the query string, collapse empty segments, and replace IDs with placeholders."""
    path = path.split("?", 1)[0]
    segments = []
    for seg in path.split("/"):
        if not seg:
            continue
        if seg.isascii() and seg.isdigit():
            segments.append(":id")
        elif UUID_RE.fullmatch(seg):
            segments.append(":uuid")
        else:
            segments.append(seg)
    return "/" + "/".join(segments)
