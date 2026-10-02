"""Reference `pagerlog replay`, written from fixture/docs/replay.md, routing.md, and history.md alone.

    python3 hidden/reference.py replay --routes FILE HISTORY

Prints what the spec says pagerlog prints, with the same exit status; standard error carries the spec's
messages. It shares no code with the fixture's tools/routes.py, so the two can check each other.
"""
import os
import re
import sys

USAGE = "usage: pagerlog replay --routes FILE HISTORY"
HEADER = "time\talert\treceivers\tlabels"
WEEK = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class Fail(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def bad(where, message):
    return Fail(1, f"{where}: {message}")


# ---------------------------------------------------------------- history exports

def civil_days(y, m, d):
    """Days since 1970-01-01 of a proleptic Gregorian date."""
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    return era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468


def month_length(y, m):
    if m == 2:
        return 29 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 28
    return 30 if m in (4, 6, 9, 11) else 31


def parse_time(text):
    m = re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z", text)
    if not m:
        return None
    y, mo, d, h, mi, s = map(int, m.groups())
    if not (1 <= mo <= 12 and 1 <= d <= month_length(y, mo) and h < 24 and mi < 60 and s < 60):
        return None
    return (y, mo, d, h, mi, s)


def read_history(path):
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise Fail(1, f"{path}: {getattr(e, 'strerror', None) or e}")
    lines = [l[:-1] if l.endswith("\r") else l for l in text.split("\n")]
    if lines[0] != HEADER:
        raise bad(path, "line 1: bad header")
    alerts = []
    for n, line in enumerate(lines[1:], 2):
        if line == "":
            continue
        f = line.split("\t")
        if len(f) != 4:
            raise bad(path, f"line {n}: expected 4 fields, found {len(f)}")
        when = parse_time(f[0])
        if when is None:
            raise bad(path, f'line {n}: bad time "{f[0]}"')
        if not re.fullmatch(r"[A-Za-z0-9_]+", f[1]):
            raise bad(path, f'line {n}: bad alert name "{f[1]}"')
        receivers = f[2].split(",")
        if len(set(receivers)) != len(receivers) or not all(re.fullmatch(r"[a-z0-9][a-z0-9-]*", r) for r in receivers):
            raise bad(path, f'line {n}: bad receivers "{f[2]}"')
        labels = {}
        if f[3] != "-":
            for item in f[3].split(","):
                name, eq, value = item.partition("=")
                if not eq or not re.fullmatch(r"[a-z_][a-z0-9_]*", name) or not value or " " in value:
                    raise bad(path, f'line {n}: bad label "{item}"')
                if name == "alertname":
                    raise bad(path, f'line {n}: label "alertname" is reserved')
                if name in labels:
                    raise bad(path, f'line {n}: label "{name}" given twice')
                labels[name] = value
        alerts.append({"time": when, "name": f[1], "receivers": receivers, "labels": labels})
    return alerts


# ---------------------------------------------------------------- routing files

class Node:
    def __init__(self, at, parent):
        self.at, self.parent = at, parent
        self.receiver = None
        self.conditions = []  # ("match", label, op, value) or ("during", days, lo, hi)
        self.go_on = False
        self.kids = []


class Routing:
    def __init__(self):
        self.defined = {}  # receiver name -> FILE:LINE
        self.root = None
        self.uses = []  # (name, FILE:LINE) of every route's receiver line, in reading order
        self.open_files = []
        self.seen = set()


def days_of(word):
    out = set()
    for piece in word.split(","):
        bounds = piece.split("-")
        if not 1 <= len(bounds) <= 2 or not all(b in WEEK for b in bounds):
            return None
        a, b = WEEK.index(bounds[0]), WEEK.index(bounds[-1])
        span = (b - a) % 7
        out.update((a + k) % 7 for k in range(span + 1))
    return out


def window_of(word):
    m = re.fullmatch(r"([0-9]{2}):([0-9]{2})-([0-9]{2}):([0-9]{2})", word)
    if not m:
        return None
    fh, fm, th, tm = map(int, m.groups())
    if fm >= 60 or tm >= 60 or fh >= 24 or th > 24 or (th == 24 and tm > 0):
        return None
    lo, hi = fh * 60 + fm, th * 60 + tm
    return (lo, hi) if lo < hi else None


def statements(path, text):
    """[(FILE:LINE, line, words)] for the lines that are statements."""
    out = []
    for n, raw in enumerate(text.split("\n"), 1):
        if raw.endswith("\r"):
            raw = raw[:-1]
        line = raw.strip(" \t")
        if line and line[0] != "#":
            out.append((f"{path}:{n}", line, re.split(r"[ \t]+", line)))
    return out


def read_routing_file(r, path, host, is_main, via):
    """host: the route this file's top-level routes join, or None; via: (FILE:LINE, PATH) of its include."""
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise bad(via[0], f'cannot read "{via[1]}"') if via else bad(path, "cannot read")
    real = os.path.realpath(path)
    r.open_files.append(real)
    stmts = statements(path, text)
    pos = 0
    while pos < len(stmts):
        at, line, w = stmts[pos]
        pos += 1
        if w[0] == "include":
            include(r, path, at, line, None)
        elif w[0] == "receiver":
            pos = receiver_block(r, path, stmts, pos, at, w)
        elif w[0] == "route":
            if w != ["route", "{"]:
                raise bad(at, "expected: route {")
            if is_main:
                if r.root is not None:
                    raise bad(at, "second root route")
                node = r.root = Node(at, None)
            elif host is None:
                raise bad(via[0], f'"{via[1]}" has routes; include it inside a route')
            else:
                node = Node(at, host)
                host.kids.append(node)
            pos = route_block(r, path, stmts, pos, node)
        else:
            raise bad(at, f'unexpected "{w[0]}"')
    r.open_files.pop()
    r.seen.add(real)


def include(r, path, at, line, host):
    m = re.fullmatch(r'include[ \t]+"([^"]+)"', line)
    if not m:
        raise bad(at, 'expected: include "PATH"')
    written = m.group(1)
    target = os.path.join(os.path.dirname(path), written)
    real = os.path.realpath(target)
    if real in r.open_files:
        raise bad(at, f'include cycle at "{written}"')
    if real not in r.seen:
        read_routing_file(r, target, host, False, (at, written))


def closing(stmts, pos, opened_at):
    if pos >= len(stmts):
        raise bad(opened_at, "block is not closed")


def receiver_block(r, path, stmts, pos, at, w):
    if len(w) != 3 or w[2] != "{":
        raise bad(at, "expected: receiver NAME {")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", w[1]):
        raise bad(at, f'bad receiver name "{w[1]}"')
    if w[1] in r.defined:
        raise bad(at, f'receiver "{w[1]}" is already defined at {r.defined[w[1]]}')
    r.defined[w[1]] = at
    forms = {"page": "page SCHEDULE", "chat": "chat CHANNEL", "ticket": "ticket QUEUE"}
    while True:
        closing(stmts, pos, at)
        here, _, words = stmts[pos]
        pos += 1
        if words[0] == "}":
            if len(words) > 1:
                raise bad(here, "expected: }")
            return pos
        if words[0] not in forms:
            raise bad(here, f'unexpected "{words[0]}"')
        if len(words) != 2:
            raise bad(here, f"expected: {forms[words[0]]}")


def route_block(r, path, stmts, pos, node):
    root = node.parent is None
    while True:
        closing(stmts, pos, node.at)
        here, line, words = stmts[pos]
        pos += 1
        key = words[0]
        if key == "}":
            if len(words) > 1:
                raise bad(here, "expected: }")
            if root and node.receiver is None:
                raise bad(node.at, "the root route has no receiver")
            return pos
        if key not in ("receiver", "match", "during", "continue", "route", "include"):
            raise bad(here, f'unexpected "{key}"')
        if root and key in ("match", "during", "continue"):
            raise bad(here, f'the root route cannot have "{key}"')
        if key == "route":
            if words != ["route", "{"]:
                raise bad(here, "expected: route {")
            kid = Node(here, node)
            node.kids.append(kid)
            pos = route_block(r, path, stmts, pos, kid)
        elif key == "include":
            include(r, path, here, line, node)
        elif key == "receiver":
            if len(words) != 2:
                raise bad(here, "expected: receiver NAME")
            if node.receiver is not None:
                raise bad(here, '"receiver" given twice in one route')
            node.receiver = words[1]
            r.uses.append((words[1], here))
        elif key == "continue":
            if len(words) != 1:
                raise bad(here, "expected: continue")
            if node.go_on:
                raise bad(here, '"continue" given twice in one route')
            node.go_on = True
        elif key == "match":
            if len(words) != 4:
                raise bad(here, "expected: match LABEL OP VALUE")
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", words[1]):
                raise bad(here, f'bad label "{words[1]}"')
            if words[2] not in ("=", "!=", "~", "!~"):
                raise bad(here, f'bad operator "{words[2]}"')
            node.conditions.append(("match", words[1], words[2], words[3]))
        else:
            if len(words) != 3:
                raise bad(here, "expected: during DAYS FROM-TO")
            days = days_of(words[1])
            if days is None:
                raise bad(here, f'bad days "{words[1]}"')
            span = window_of(words[2])
            if span is None:
                raise bad(here, f'bad time window "{words[2]}"')
            node.conditions.append(("during", days, span[0], span[1]))


def load_routing(path):
    r = Routing()
    read_routing_file(r, path, None, True, None)
    if r.root is None:
        raise bad(path, "no root route")
    for name, at in r.uses:
        if name not in r.defined:
            raise bad(at, f'unknown receiver "{name}"')
    return r


def glob(pattern, value):
    pieces = pattern.split("*")
    if len(pieces) == 1:
        return value == pattern
    if not value.startswith(pieces[0]) or len(value) < len(pieces[0]) + len(pieces[-1]) or not value.endswith(pieces[-1]):
        return False
    pos, end = len(pieces[0]), len(value) - len(pieces[-1])
    for mid in pieces[1:-1]:
        found = value.find(mid, pos, end)
        if found < 0:
            return False
        pos = found + len(mid)
    return True


def holds(node, labels, weekday, minute):
    windows = [c for c in node.conditions if c[0] == "during"]
    for c in node.conditions:
        if c[0] == "match":
            _, label, op, value = c
            have = labels.get(label, "")
            result = {"=": have == value, "!=": have != value, "~": glob(value, have), "!~": not glob(value, have)}[op]
            if not result:
                return False
    return not windows or any(weekday in d and lo <= minute < hi for _, d, lo, hi in windows)


def destinations(routing, labels, when):
    y, mo, d, h, mi, _ = when
    weekday = (civil_days(y, mo, d) + 3) % 7
    minute = h * 60 + mi
    found = []

    def visit(node, inherited):
        mine = node.receiver if node.receiver is not None else inherited
        any_kid = False
        for kid in node.kids:
            if not holds(kid, labels, weekday, minute):
                continue
            any_kid = True
            visit(kid, mine)
            if not kid.go_on:
                break
        if not any_kid and mine not in found:
            found.append(mine)

    visit(routing.root, None)
    return found


# ---------------------------------------------------------------- the report

def layout(columns, rows):
    """columns: [(header, "l" or "r")]."""
    table = [[h for h, _ in columns]] + rows
    widths = [max(len(row[i]) for row in table) for i in range(len(columns))]
    lines = []
    for row in table:
        cells = [cell.ljust(widths[i]) if columns[i][1] == "l" else cell.rjust(widths[i]) for i, cell in enumerate(row)]
        lines.append("  ".join(cells).rstrip(" "))
    return "\n".join(lines) + "\n"


def replay(routes_path, history_path):
    routing = load_routing(routes_path)
    alerts = read_history(history_path)
    if not alerts:
        raise Fail(1, f"{history_path}: no alerts")
    before, after, groups = {}, {}, {}
    for a in alerts:
        labels = dict(a["labels"], alertname=a["name"])
        now = destinations(routing, labels, a["time"])
        for name in a["receivers"]:
            before[name] = before.get(name, 0) + 1
        for name in now:
            after[name] = after.get(name, 0) + 1
        if set(now) != set(a["receivers"]):
            key = (a["name"], ", ".join(sorted(a["receivers"])), ", ".join(sorted(now)))
            groups[key] = groups.get(key, 0) + 1
    times = sorted(a["time"] for a in alerts)
    day = lambda t: f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"  # noqa: E731
    out = f"Replay of {len(alerts)} alerts ({day(times[0])} to {day(times[-1])}) through {routes_path}\n\n"
    rows = []
    for name in sorted(set(before) | set(after)):
        b, n = before.get(name, 0), after.get(name, 0)
        rows.append([name, str(b), str(n), f"{n - b:+d}" if n != b else "0"])
    out += layout([("Receiver", "l"), ("Before", "r"), ("After", "r"), ("Change", "r")], rows)
    changed = sum(groups.values())
    out += f"\nChanged: {changed} of {len(alerts)} alerts\n"
    if changed:
        order = sorted(groups.items(), key=lambda kv: (-kv[1], kv[0]))
        out += "\n" + layout([("Alerts", "r"), ("Alert", "l"), ("Before", "l"), ("After", "l")],
                             [[str(c), k[0], k[1], k[2]] for k, c in order])
    return out


def command_line(argv):
    if not argv or argv[0] != "replay":
        raise Fail(2, f'unknown command "{argv[0] if argv else ""}"')
    routes, plain, rest = None, [], list(argv[1:])
    while rest:
        a = rest.pop(0)
        if a == "--routes":
            if not rest:
                raise Fail(2, "--routes needs a value")
            if routes is not None:
                raise Fail(2, "--routes given twice")
            routes = rest.pop(0)
        elif a.startswith("-") and len(a) > 1:
            raise Fail(2, f'unknown option "{a}"')
        else:
            plain.append(a)
    if routes is None:
        raise Fail(2, "replay needs --routes FILE")
    if len(plain) != 1:
        raise Fail(2, "replay takes one HISTORY file")
    return routes, plain[0]


def main(argv):
    try:
        routes, history = command_line(argv)
        sys.stdout.write(replay(routes, history))
        return 0
    except Fail as f:
        sys.stderr.write(f"pagerlog: {f}\n" + (USAGE + "\n" if f.status == 2 else ""))
        return f.status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
