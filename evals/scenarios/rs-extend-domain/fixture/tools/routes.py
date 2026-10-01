#!/usr/bin/env python3
"""Check routing files and see where an alert would go, before a routing change is deployed.

The paging service sends every alert through routing/main.routes and the files it includes. This script
reads routing files by the same rules (docs/routing.md):

    python3 tools/routes.py check routing/main.routes
    python3 tools/routes.py test routing/main.routes alertname=DiskFull service=db-orders severity=critical
    python3 tools/routes.py test routing/main.routes --at 2026-10-03T02:15:00Z alertname=QueueDepth team=payments
    python3 tools/routes.py tree routing/main.routes

check prints how many receivers and routes the files define, or the first error. test prints the receivers
an alert with those labels would go to, one per line, in order; the alert fires at --at (UTC), or now.
tree prints every route with what it matches and the receiver it sends to.

Errors go to standard error as FILE:LINE: MESSAGE (the messages are listed in docs/routing.md) with exit
status 1; usage errors exit with status 2.
"""
import os
import re
import sys
from datetime import datetime, timezone

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
RECEIVER_NAME = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
LABEL_NAME = re.compile(r"[a-z_][a-z0-9_]*\Z")
OPERATORS = ("=", "!=", "~", "!~")
TARGETS = {"page": "page SCHEDULE", "chat": "chat CHANNEL", "ticket": "ticket QUEUE"}
INCLUDE = re.compile(r'include[ \t]+"([^"]+)"\Z')
WORDS = re.compile(r"[ \t]+")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# What may start a line, by where it stands.
ALLOWED = {
    "file": {"include", "receiver", "route"},
    "receiver": {"page", "chat", "ticket", "}"},
    "route": {"receiver", "match", "during", "continue", "route", "include", "}"},
}


class RoutingError(Exception):
    """The first problem in a set of routing files; str() is the message as reported."""

    def __init__(self, where, message):
        super().__init__(f"{where}: {message}")


class Receiver:
    def __init__(self, name, where):
        self.name = name
        self.where = where  # FILE:LINE of its block
        self.targets = []  # (kind, value)


class Route:
    def __init__(self, where, parent=None):
        self.where = where  # FILE:LINE of its `route {` line
        self.parent = parent
        self.receiver = None  # the name it names, or None to use the parent's
        self.matchers = []  # (label, operator, value)
        self.windows = []  # (set of weekdays, 0 = Monday; first minute; minute after the last)
        self.cont = False
        self.children = []

    def is_root(self):
        return self.parent is None


class Routing:
    """Everything a main file and its includes define."""

    def __init__(self):
        self.root = None
        self.receivers = {}  # name -> Receiver
        self.routes = []  # every route, in the order their blocks were read
        self.receiver_lines = []  # (name, FILE:LINE) of every route's receiver line, in the order read


def parse_days(text):
    """The weekdays a DAYS word names (0 = Monday), or None when it is not valid."""
    days = set()
    for part in text.split(","):
        ends = part.split("-")
        if len(ends) > 2 or any(e not in DAYS for e in ends):
            return None
        first, last = DAYS.index(ends[0]), DAYS.index(ends[-1])
        day = first
        while True:
            days.add(day)
            if day == last:
                break
            day = (day + 1) % 7
    return days


def parse_window(text):
    """(first minute, minute after the last) for FROM-TO, or None when it is not valid."""
    m = re.fullmatch(r"([0-9]{2}):([0-9]{2})-([0-9]{2}):([0-9]{2})", text)
    if not m:
        return None
    h1, m1, h2, m2 = (int(g) for g in m.groups())
    if h1 > 23 or m1 > 59 or m2 > 59 or h2 > 24 or (h2 == 24 and m2 != 0):
        return None
    start, end = h1 * 60 + m1, h2 * 60 + m2
    if start >= end:
        return None
    return start, end


class Loader:
    def __init__(self):
        self.routing = Routing()
        self.reading = []  # real paths of the files being read, outermost first
        self.done = set()  # real paths of the files read

    def load(self, path):
        try:
            text = read_text(path)
        except (OSError, UnicodeDecodeError):
            raise RoutingError(path, "cannot read")
        self.read_file(path, text, host=None, main=True)
        if self.routing.root is None:
            raise RoutingError(path, "no root route")
        for name, where in self.routing.receiver_lines:
            if name not in self.routing.receivers:
                raise RoutingError(where, f'unknown receiver "{name}"')
        return self.routing

    def read_file(self, path, text, host, main=False, included_at=None):
        """Read one file. host is the route its top-level route blocks join (None outside any route);
        included_at is (FILE:LINE, PATH as written) of the include line that brought it in."""
        real = os.path.realpath(path)
        self.reading.append(real)
        stack = []  # open blocks: (kind, Receiver or Route, FILE:LINE)
        for number, raw in enumerate(text.split("\n"), 1):
            line = raw[:-1] if raw.endswith("\r") else raw
            line = line.strip(" \t")
            if not line or line.startswith("#"):
                continue
            where = f"{path}:{number}"
            words = WORDS.split(line)
            kind = stack[-1][0] if stack else "file"
            block = stack[-1][1] if stack else None
            first = words[0]
            if first not in ALLOWED[kind]:
                raise RoutingError(where, f'unexpected "{first}"')
            if first == "}":
                if len(words) != 1:
                    raise RoutingError(where, "expected: }")
                closed = stack.pop()
                if closed[0] == "route" and closed[1].is_root() and closed[1].receiver is None:
                    raise RoutingError(closed[2], "the root route has no receiver")
            elif first == "include":
                m = INCLUDE.fullmatch(line)
                if not m:
                    raise RoutingError(where, 'expected: include "PATH"')
                self.include(path, where, m.group(1), block if kind == "route" else None)
            elif kind == "file" and first == "receiver":
                if len(words) != 3 or words[2] != "{":
                    raise RoutingError(where, "expected: receiver NAME {")
                name = words[1]
                if not RECEIVER_NAME.match(name):
                    raise RoutingError(where, f'bad receiver name "{name}"')
                if name in self.routing.receivers:
                    raise RoutingError(where, f'receiver "{name}" is already defined at {self.routing.receivers[name].where}')
                receiver = Receiver(name, where)
                self.routing.receivers[name] = receiver
                stack.append(("receiver", receiver, where))
            elif first == "route":
                if words != ["route", "{"]:
                    raise RoutingError(where, "expected: route {")
                if kind == "route":
                    route = Route(where, parent=block)
                    block.children.append(route)
                elif main:
                    if self.routing.root is not None:
                        raise RoutingError(where, "second root route")
                    route = Route(where)
                    self.routing.root = route
                elif host is None:
                    raise RoutingError(included_at[0], f'"{included_at[1]}" has routes; include it inside a route')
                else:
                    route = Route(where, parent=host)
                    host.children.append(route)
                self.routing.routes.append(route)
                stack.append(("route", route, where))
            elif kind == "receiver":
                if len(words) != 2:
                    raise RoutingError(where, f"expected: {TARGETS[first]}")
                block.targets.append((first, words[1]))
            else:
                self.route_line(block, where, words)
        if stack:
            raise RoutingError(stack[-1][2], "block is not closed")
        self.reading.pop()
        self.done.add(real)

    def route_line(self, route, where, words):
        first = words[0]
        if route.is_root() and first in ("match", "during", "continue"):
            raise RoutingError(where, f'the root route cannot have "{first}"')
        if first == "receiver":
            if len(words) != 2:
                raise RoutingError(where, "expected: receiver NAME")
            if route.receiver is not None:
                raise RoutingError(where, '"receiver" given twice in one route')
            route.receiver = words[1]
            self.routing.receiver_lines.append((words[1], where))
        elif first == "match":
            if len(words) != 4:
                raise RoutingError(where, "expected: match LABEL OP VALUE")
            _, label, op, value = words
            if not LABEL_NAME.match(label):
                raise RoutingError(where, f'bad label "{label}"')
            if op not in OPERATORS:
                raise RoutingError(where, f'bad operator "{op}"')
            route.matchers.append((label, op, value))
        elif first == "during":
            if len(words) != 3:
                raise RoutingError(where, "expected: during DAYS FROM-TO")
            days = parse_days(words[1])
            if days is None:
                raise RoutingError(where, f'bad days "{words[1]}"')
            window = parse_window(words[2])
            if window is None:
                raise RoutingError(where, f'bad time window "{words[2]}"')
            route.windows.append((days, window[0], window[1]))
        elif first == "continue":
            if len(words) != 1:
                raise RoutingError(where, "expected: continue")
            if route.cont:
                raise RoutingError(where, '"continue" given twice in one route')
            route.cont = True

    def include(self, path, where, written, host):
        target = os.path.join(os.path.dirname(path), written)
        real = os.path.realpath(target)
        if real in self.reading:
            raise RoutingError(where, f'include cycle at "{written}"')
        if real in self.done:
            return
        try:
            text = read_text(target)
        except (OSError, UnicodeDecodeError):
            raise RoutingError(where, f'cannot read "{written}"')
        self.read_file(target, text, host, included_at=(where, written))


def read_text(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8")


def load(path):
    """The routing defined by the main file at path and its includes; raises RoutingError."""
    return Loader().load(path)


# ---------------------------------------------------------------- where an alert goes

def pattern_matches(pattern, value):
    return re.fullmatch(".*".join(re.escape(p) for p in pattern.split("*")), value, re.S) is not None


def route_matches(route, labels, when):
    for label, op, value in route.matchers:
        actual = labels.get(label, "")
        if op == "=":
            ok = actual == value
        elif op == "!=":
            ok = actual != value
        elif op == "~":
            ok = pattern_matches(value, actual)
        else:
            ok = not pattern_matches(value, actual)
        if not ok:
            return False
    if not route.windows:
        return True
    day, minute = when.weekday(), when.hour * 60 + when.minute
    return any(day in days and start <= minute < end for days, start, end in route.windows)


def receivers_for(routing, labels, when):
    """The receivers an alert with these labels (a dict), firing at when (a datetime in UTC), goes to."""
    out = []

    def take(route, inherited):
        receiver = route.receiver or inherited
        taken = False
        for child in route.children:
            if route_matches(child, labels, when):
                take(child, receiver)
                taken = True
                if not child.cont:
                    break
        if not taken and receiver not in out:
            out.append(receiver)

    take(routing.root, None)
    return out


# ---------------------------------------------------------------- command line

def describe(route):
    parts = [f"{label} {op} {value}" for label, op, value in route.matchers]
    for days, start, end in route.windows:
        names = ",".join(DAYS[d] for d in sorted(days))
        parts.append(f"{names} {start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}")
    return ", ".join(parts) or "every alert"


def tree_lines(route, inherited, depth=0):
    receiver = route.receiver or inherited
    flag = ", continue" if route.cont else ""
    lines = [f"{'  ' * depth}{describe(route)} -> {receiver}{flag}  ({route.where})"]
    for child in route.children:
        lines += tree_lines(child, receiver, depth + 1)
    return lines


def usage(message):
    print(f"routes.py: {message}", file=sys.stderr)
    print("usage: routes.py check FILE | test FILE [--at TIME] LABEL=VALUE... | tree FILE", file=sys.stderr)
    return 2


def main(argv):
    if len(argv) < 2 or argv[0] not in ("check", "test", "tree"):
        return usage("expected a command and a FILE")
    command, path, rest = argv[0], argv[1], argv[2:]
    when = datetime.now(timezone.utc)
    labels = {}
    if command != "test" and rest:
        return usage(f"{command} takes one FILE")
    while rest:
        arg = rest.pop(0)
        if arg == "--at":
            if not rest:
                return usage("--at needs a time")
            try:
                when = datetime.strptime(rest.pop(0), TIME_FORMAT).replace(tzinfo=timezone.utc)
            except ValueError:
                return usage("--at takes a time such as 2026-10-03T02:15:00Z")
        elif "=" in arg and LABEL_NAME.match(arg.split("=", 1)[0]):
            name, value = arg.split("=", 1)
            labels[name] = value
        else:
            return usage(f'expected LABEL=VALUE, not "{arg}"')
    try:
        routing = load(path)
    except RoutingError as e:
        print(e, file=sys.stderr)
        return 1
    if command == "check":
        print(f"{path}: ok, {len(routing.receivers)} receivers, {len(routing.routes)} routes")
    elif command == "test":
        for receiver in receivers_for(routing, labels, when):
            print(receiver)
    else:
        print("\n".join(tree_lines(routing.root, None)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
