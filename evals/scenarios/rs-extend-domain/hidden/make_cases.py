"""Regenerate hidden/cases.json: routing files, history exports, and `pagerlog replay` command lines, with the
expected exit status and standard output from hidden/reference.py (which follows fixture/docs/replay.md,
routing.md, and history.md), and command lines of pagerlog's existing commands (check, receivers, top) with
what the fixture's own pagerlog gives.

    python3 hidden/make_cases.py                         # write cases.json
    python3 hidden/make_cases.py --cross-check PAGERLOG  # also run a built pagerlog on every case, report differences
    python3 hidden/make_cases.py --helper-parity         # check the fixture's routes.py against the reference
    python3 hidden/make_cases.py --fixture DIR           # rewrite the fixture's routing files and history export in DIR

The fixture's pagerlog is built here with the host's cargo, offline, from a copy of the fixture. A case's
arguments and expected standard output name its files as {dir}/NAME; the check replaces {dir} with the
directory holding that case's files, the same absolute path in both roots it runs in. Every replay case is
behavior the spec states, so all are required except the few marked as measures; the existing-command cases
guard what pagerlog already did and count toward existing_tests_pass.
"""
import base64
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import catalog  # noqa: E402

FIX = catalog.FIXTURE_ROUTING
ROUTES = "{dir}/routing/main.routes"
HIST = "{dir}/history.tsv"


def edit(files, path, old, new, count=1):
    """A copy of files with old replaced by new in files[path] (old must be there)."""
    if old not in files[path]:
        raise SystemExit(f"edit: {old!r} is not in {path}")
    return dict(files, **{path: files[path].replace(old, new, count)})


def hist(rows):
    """A history export from (time, alert, receivers, labels) rows, written as given."""
    return "time\talert\treceivers\tlabels\n" + "".join(f"{t}\t{a}\t{r}\t{l}\n" for t, a, r, l in rows)


def blocks(*names):
    return "".join(f"receiver {n} {{\n}}\n" for n in names)


# ---------------------------------------------------------------- routing sets

PROPOSED = {
    "routing/shared/receivers.routes": catalog.RECEIVERS + "\nreceiver payments-sre {\n  page payments-sre\n}\n",
    "routing/main.routes": """\
# Proposed for Q4: teams in one file, eu nodes to the weekend rota out of hours.
include "shared/receivers.routes"
include "shared/receivers.routes"

route {
\treceiver platform-oncall

  route {
    match alertname = NodeDown
    match zone ~ eu-*
    during fri-mon 18:00-24:00
    during sat,sun 00:00-09:00
    receiver platform-weekend
    continue
  }
  route {
    match service ~ db-*
    receiver dba-oncall
    continue
  }
  include "teams/all.routes"
  route {
    match severity = info
    receiver platform-tickets
  }
}
""",
    "routing/teams/all.routes": """\
route {
  match team = payments
  receiver payments-oncall
  include "payments.routes"
}
route {
  match team = storage
  receiver storage-oncall
  include "storage/blob.routes"
}
route {
  match team = search
  match severity = critical
  receiver search-oncall
}
""",
    "routing/teams/payments.routes": """\
route {
  match env !~ prod*
  receiver payments-tickets
}
route {
  match alertname ~ *Latency
  during mon-fri 08:00-18:00
  receiver payments-sre
  continue
}
route {
  match alertname ~ *Latency
  receiver payments-tickets
}
route {
  match queue = payouts
  receiver payments-sre
}
""",
    "routing/teams/storage/blob.routes": """\
include "../../shared/receivers.routes"
route {
  match service ~ blob-*
  match severity != critical
  receiver storage-tickets
}
""",
}

CONTINUE = {"routing/main.routes": blocks("a", "b", "c") + """\
route {
  receiver a
  route {
    match x = 1
    receiver b
    continue
  }
  route {
    match y = 1
    continue
  }
  route {
    match z = 1
    receiver b
    continue
  }
  route {
    match w = 1
    receiver c
  }
  route {
    match v = 1
    receiver b
  }
}
"""}
CONTINUE_HISTORY = hist([
    ("2026-08-03T10:00:00Z", "One", "a", "x=1"),
    ("2026-08-03T10:01:00Z", "Two", "a", "x=1,y=1"),
    ("2026-08-03T10:02:00Z", "Two", "b,a", "y=1,z=1"),
    ("2026-08-03T10:03:00Z", "One", "a", "x=1,z=1"),
    ("2026-08-03T10:04:00Z", "Three", "a", "v=1,w=1,x=1"),
    ("2026-08-03T10:05:00Z", "Three", "c", "v=1"),
    ("2026-08-03T10:06:00Z", "Four", "a", "-"),
    ("2026-08-03T10:07:00Z", "Four", "a", "w=1,y=1"),
    ("2026-08-03T10:08:00Z", "One", "b", "x=1"),
    ("2026-08-03T10:09:00Z", "Two", "a", "x=1,y=1"),
])

SPLICE = {
    "routing/receivers.routes": blocks("a", "b", "c", "d", "e", "f", "g", "h"),
    "routing/main.routes": """\
include "receivers.routes"
route {
  receiver a
  route {
    match k = 1
    receiver b
  }
  include "middle.routes"
  route {
    match k = 2
    receiver c
  }
  route {
    match team = x
    receiver d
    include "teams.routes"
  }
  route {
    match team = y
    receiver e
    include "teams.routes"
  }
}
""",
    "routing/middle.routes": """\
include "receivers.routes"
route {
  match k = 2
  receiver f
}
route {
  match k = 1
  receiver g
}
route {
  match j = 1
  continue
}
""",
    "routing/teams.routes": """\
route {
  match sev = low
  receiver h
}
route {
  match sev = high
}
""",
}
SPLICE_HISTORY = hist([
    ("2026-08-04T01:00:00Z", "K", "a", "k=1"),
    ("2026-08-04T01:01:00Z", "K", "a", "k=2"),
    ("2026-08-04T01:02:00Z", "J", "a", "j=1"),
    ("2026-08-04T01:03:00Z", "J", "a", "j=1,team=x"),
    ("2026-08-04T01:04:00Z", "J", "a", "j=1,k=2"),
    ("2026-08-04T01:05:00Z", "T", "a", "sev=low,team=x"),
    ("2026-08-04T01:06:00Z", "T", "a", "sev=high,team=x"),
    ("2026-08-04T01:07:00Z", "T", "a", "team=x"),
    ("2026-08-04T01:08:00Z", "T", "a", "sev=low,team=y"),
    ("2026-08-04T01:09:00Z", "T", "a", "sev=high,team=y"),
    ("2026-08-04T01:10:00Z", "N", "a", "-"),
])

INHERIT = {
    "routing/main.routes": blocks("top", "mid", "leaf") + """\
route {
  receiver top
  route {
    match a = 1
    route {
      match b = 1
      receiver mid
      route {
        match c = 1
        route {
          match d = 1
        }
        include "deep/leaf.routes"
      }
    }
    route {
      match b = 2
    }
  }
}
""",
    "routing/deep/leaf.routes": """\
route {
  match e = 1
  receiver leaf
}
route {
  match e = 2
}
""",
}
INHERIT_HISTORY = hist([
    ("2026-08-05T09:00:00Z", "A", "top", "a=1"),
    ("2026-08-05T09:01:00Z", "A", "top", "a=1,b=1"),
    ("2026-08-05T09:02:00Z", "A", "top", "a=1,b=1,c=1"),
    ("2026-08-05T09:03:00Z", "A", "top", "a=1,b=1,c=1,d=1"),
    ("2026-08-05T09:04:00Z", "A", "top", "a=1,b=1,c=1,e=1"),
    ("2026-08-05T09:05:00Z", "A", "top", "a=1,b=1,c=1,e=2"),
    ("2026-08-05T09:06:00Z", "A", "top", "a=1,b=2"),
    ("2026-08-05T09:07:00Z", "A", "top", "b=1"),
])

WINDOWS = {"routing/main.routes": blocks("lunch", "office", "night", "weekend", "day") + """\
route {
  receiver day
  route {
    during wed 12:30-12:31
    receiver lunch
  }
  route {
    during mon-fri 09:00-17:00
    receiver office
  }
  route {
    during fri-mon 22:00-24:00
    during fri-mon 00:00-06:00
    receiver night
  }
  route {
    during sat,sun 00:00-24:00
    receiver weekend
  }
}
"""}
WINDOW_TIMES = [
    "2026-09-30T12:30:00Z", "2026-09-30T12:30:59Z", "2026-09-30T12:31:00Z", "2026-09-30T12:29:59Z",
    "2026-09-28T09:00:00Z", "2026-09-28T08:59:59Z", "2026-09-28T05:59:59Z", "2026-09-28T06:00:00Z",
    "2026-09-28T16:59:59Z", "2026-09-28T17:00:00Z", "2026-10-02T22:00:00Z", "2026-10-02T21:59:59Z",
    "2026-10-03T03:00:00Z", "2026-10-03T12:00:00Z", "2026-10-04T23:59:59Z", "2026-09-29T23:00:00Z",
    "2026-09-29T02:00:00Z", "2028-02-29T10:00:00Z", "2100-03-01T23:30:00Z", "1999-12-31T23:59:59Z",
    "2027-01-02T10:00:00Z", "2024-02-29T12:30:30Z", "2026-12-31T23:00:00Z", "2027-01-01T05:00:00Z",
]
WINDOWS_HISTORY = hist([(t, "Tick", "day", f"n={i}") for i, t in enumerate(WINDOW_TIMES)])

PATTERNS = {"routing/main.routes": blocks("other", "literal", "question", "prefix", "suffix", "infix", "multi",
                                           "exact", "brackets", "nonprod") + """\
route {
  receiver other
  route {
    match svc ~ svc.v*
    receiver literal
  }
  route {
    match svc ~ api?
    receiver question
  }
  route {
    match svc ~ db-*
    receiver prefix
  }
  route {
    match svc ~ *-eu
    receiver suffix
  }
  route {
    match svc ~ *cache*
    receiver infix
  }
  route {
    match svc ~ a*b*c
    receiver multi
  }
  route {
    match svc ~ checkout
    receiver exact
  }
  route {
    match svc ~ [x]+
    receiver brackets
  }
  route {
    match env !~ prod*
    match svc ~ *
    receiver nonprod
  }
}
"""}
PATTERN_SERVICES = ["svc.v2", "svcXv2", "api?", "api1", "db-", "mydb-1", "blob-eu", "eu", "memcache-1", "cache",
                    "abc", "aXbYbc", "acb", "checkout", "checkout-eu", "[x]+", "x", "[x]"]
PATTERNS_HISTORY = hist([("2026-08-06T12:00:%02dZ" % i, "Probe", "other", f"env=prod,svc={s}")
                         for i, s in enumerate(PATTERN_SERVICES)] + [
    ("2026-08-06T12:01:00Z", "Probe", "other", "env=staging,svc=foo"),
    ("2026-08-06T12:01:01Z", "Probe", "other", "svc=foo"),
    ("2026-08-06T12:01:02Z", "Probe", "other", "env=production,svc=foo"),
    ("2026-08-06T12:01:03Z", "Probe", "other", "env=staging"),
])

MISSING = {"routing/main.routes": blocks("root", "never", "eu", "not-us", "gold") + """\
route {
  receiver root
  route {
    match region !~ *
    receiver never
  }
  route {
    match region = eu
    receiver eu
  }
  route {
    match region != us
    match tier ~ *
    receiver not-us
    continue
  }
  route {
    match tier ~ gold*
    receiver gold
  }
}
"""}
MISSING_HISTORY = hist([
    ("2026-08-07T08:00:00Z", "Ping", "root", "-"),
    ("2026-08-07T08:00:01Z", "Ping", "root", "region=eu"),
    ("2026-08-07T08:00:02Z", "Ping", "root", "region=us"),
    ("2026-08-07T08:00:03Z", "Ping", "root", "region=us,tier=gold"),
    ("2026-08-07T08:00:04Z", "Ping", "root", "tier=gold-plus"),
    ("2026-08-07T08:00:05Z", "Ping", "root", "region=apac"),
    ("2026-08-07T08:00:06Z", "Ping", "root", "zone=a"),
])

QUIRKS = {"routing/main.routes": (
    "#\trouting with Windows line endings, tabs, and receivers defined after use\r\n"
    "   # an indented comment\r\n"
    "\r\n"
    "route\t{\r\n"
    "\treceiver   ops\r\n"
    "\t\troute {\r\n"
    "\t\t\tmatch\talertname\t=\tHeartbeat\r\n"
    "\t\t\treceiver quiet\r\n"
    "\t\t}\r\n"
    "  route {   \r\n"
    "    match   team  =   web   \r\n"
    "    receiver web-oncall\r\n"
    "  }\r\n"
    "}\r\n"
    "   \r\n"
    "receiver ops {\r\n"
    "  chat #ops-room\r\n"
    "  page ops-primary\r\n"
    "}\r\n"
    "receiver quiet {\r\n"
    "}\r\n"
    "receiver web-oncall {\r\n"
    "  chat #web\r\n"
    "}\r\n")}
QUIRKS_HISTORY = hist([
    ("2026-08-08T00:00:00Z", "Heartbeat", "ops", "team=web"),
    ("2026-08-08T00:05:00Z", "Heartbeat", "quiet", "-"),
    ("2026-08-08T00:10:00Z", "SlowPage", "ops", "team=web"),
    ("2026-08-08T00:15:00Z", "SlowPage", "web-oncall", "team=web"),
    ("2026-08-08T00:20:00Z", "Down", "ops", "team=core"),
]).replace("\n", "\r\n")

FLAT = {"routing/main.routes": "receiver everyone {\n  page everyone\n}\nroute {\n  receiver everyone\n}\n"}
FLAT_HISTORY = hist([("2026-07-%02dT0%d:00:00Z" % (d, d % 10), n, "everyone", "-")
                     for d, n in zip(range(10, 16), ["A", "B", "C", "A", "B", "A"])])

ORDERING = {"routing/main.routes": blocks("d", "db-oncall", "dba-oncall", "db2-oncall", "zz") + """\
route {
  receiver zz
  route {
    match alertname ~ A*
    receiver dba-oncall
    continue
  }
  route {
    match alertname ~ *B
    receiver db-oncall
  }
  route {
    match alertname = C
    receiver db2-oncall
  }
}
"""}
ORDERING_HISTORY = hist([
    ("2026-09-01T00:00:00Z", "AB", "d", "-"),
    ("2026-09-01T00:01:00Z", "AB", "zz", "-"),
    ("2026-09-01T00:02:00Z", "A1", "d", "-"),
    ("2026-09-01T00:03:00Z", "A1", "d", "-"),
    ("2026-09-01T00:04:00Z", "CB", "d", "-"),
    ("2026-09-01T00:05:00Z", "CB", "d", "-"),
    ("2026-09-01T00:06:00Z", "C", "zz,d", "-"),
    ("2026-09-01T00:07:00Z", "C", "d,zz", "-"),
    ("2026-09-01T00:08:00Z", "X", "db-oncall", "-"),
    ("2026-09-01T00:09:00Z", "X", "zz", "-"),
    ("2026-09-01T00:10:00Z", "B", "dba-oncall,d", "-"),
    ("2026-09-01T00:11:00Z", "AB", "db-oncall", "-"),
    ("2026-09-01T00:12:00Z", "A2", "zz", "-"),
    ("2026-09-01T00:13:00Z", "A2", "dba-oncall", "-"),
] + [("2026-09-02T00:%02d:00Z" % i, "X", "d", "-") for i in range(10)])

MAIN_HISTORY = catalog.generate(seed=31, count=200)
BIG_HISTORY = catalog.generate(seed=47, count=300, start=(2026, 4, 1), days=91)
PROPOSED_HISTORY = catalog.generate(seed=59, count=160, start=(2026, 9, 1), days=30)
SMALL_HISTORY = catalog.generate(seed=71, count=20)
CRLF_HISTORY = catalog.generate(seed=83, count=40).replace("\n", "\r\n")


def files(routing, history=SMALL_HISTORY):
    return dict(routing, **{"history.tsv": history})


def case(name, args, routing_files, required=True, stderr_has=None, kind="replay"):
    return {"name": name, "kind": kind, "required": required, "args": args, "files": routing_files,
            "stderr_has": stderr_has}


def replay(name, routing, history=SMALL_HISTORY, **kw):
    return case(name, ["replay", "--routes", ROUTES, HIST], files(routing, history), **kw)


def broken(name, routing, fragment, history=SMALL_HISTORY, **kw):
    return replay(name, routing, history, stderr_has=["pagerlog: ", fragment], **kw)


def existing(name, args, history, stderr_has=None):
    return case(name, args, {"history.tsv": history}, stderr_has=stderr_has, kind="existing")


P, M, S = "routing/teams/payments.routes", "routing/main.routes", "routing/teams/storage.routes"
R = "routing/receivers.routes"
BAD_TIME = SMALL_HISTORY.replace("T", " ", 1)  # line 2: a space for the T
CASES = [
    # The fixture's own routing, on generated quarters.
    replay("main_q3", FIX, MAIN_HISTORY),
    replay("main_q2_big", FIX, BIG_HISTORY),
    replay("main_crlf_history", FIX, CRLF_HISTORY),
    case("main_routes_after_history", ["replay", HIST, "--routes", ROUTES], files(FIX, MAIN_HISTORY)),
    replay("proposed_september", PROPOSED, PROPOSED_HISTORY),
    replay("proposed_q3", PROPOSED, MAIN_HISTORY),
    # One rule at a time.
    replay("continue_and_once", CONTINUE, CONTINUE_HISTORY),
    replay("include_splice_and_once", SPLICE, SPLICE_HISTORY),
    replay("inherit_deep", INHERIT, INHERIT_HISTORY),
    replay("windows", WINDOWS, WINDOWS_HISTORY),
    replay("patterns", PATTERNS, PATTERNS_HISTORY),
    replay("missing_labels", MISSING, MISSING_HISTORY),
    replay("crlf_tabs_forward_receivers", QUIRKS, QUIRKS_HISTORY),
    replay("nothing_changed", FLAT, FLAT_HISTORY),
    replay("ordering", ORDERING, ORDERING_HISTORY),
    # Routing errors, one at a time, in the fixture's files.
    broken("error_unknown_receiver_included", edit(FIX, P, "receiver payments-tickets\n}\n\n# Anything",
                                                   "receiver payments-ticket\n}\n\n# Anything"),
           'routing/teams/payments.routes:18: unknown receiver "payments-ticket"'),
    broken("error_duplicate_receiver", edit(FIX, M, 'include "receivers.routes"\n',
                                            'include "receivers.routes"\n\nreceiver dba-oncall {\n  page dba-secondary\n}\n'),
           'routing/main.routes:6: receiver "dba-oncall" is already defined at '),
    broken("error_duplicate_receiver_where", edit(FIX, M, 'include "receivers.routes"\n',
                                                  'include "receivers.routes"\n\nreceiver dba-oncall {\n  page dba-secondary\n}\n'),
           "routing/receivers.routes:36"),
    broken("error_include_cycle", edit(FIX, S, "# Storage team routing: everything under team=storage.\n",
                                       '# Storage team routing.\ninclude "../main.routes"\n'),
           'routing/teams/storage.routes:2: include cycle at "../main.routes"'),
    broken("error_include_missing", edit(FIX, M, 'include "teams/storage.routes"', 'include "teams/stor.routes"'),
           'routing/main.routes:32: cannot read "teams/stor.routes"'),
    broken("error_routes_at_top", edit(FIX, M, 'include "receivers.routes"\n',
                                       'include "receivers.routes"\ninclude "teams/payments.routes"\n'),
           'routing/main.routes:5: "teams/payments.routes" has routes; include it inside a route'),
    broken("error_root_no_receiver", edit(FIX, M, "  receiver platform-oncall\n\n  # Load", "\n\n  # Load"),
           "routing/main.routes:6: the root route has no receiver"),
    broken("error_root_match", edit(FIX, M, "  receiver platform-oncall\n", "  receiver platform-oncall\n  match env = prod\n"),
           'routing/main.routes:8: the root route cannot have "match"'),
    broken("error_block_not_closed", edit(FIX, S, "  receiver storage-tickets\n}\n", "  receiver storage-tickets\n"),
           "routing/teams/storage.routes:9: block is not closed"),
    broken("error_bad_window", edit(FIX, P, "during mon-fri 08:00-18:00", "during mon-fri 18:00-08:00"),
           'routing/teams/payments.routes:13: bad time window "18:00-08:00"'),
    broken("error_bad_days", edit(FIX, M, "during sat,sun 00:00-24:00", "during weekend 00:00-24:00"),
           'routing/main.routes:48: bad days "weekend"'),
    broken("error_bad_operator", edit(FIX, M, "match team = search", "match team =~ search"),
           'routing/main.routes:36: bad operator "=~"'),
    broken("error_bad_label", edit(FIX, P, "match env !~ prod*", "match Env !~ prod*"),
           'routing/teams/payments.routes:23: bad label "Env"'),
    broken("error_unexpected_word", edit(FIX, S, "  match severity = warning\n  receiver",
                                         "  matches severity = warning\n  receiver"),
           'routing/teams/storage.routes:11: unexpected "matches"'),
    broken("error_unexpected_brace", edit(FIX, R, "receiver blackhole {\n}\n", "receiver blackhole {\n}\n}\n"),
           'routing/receivers.routes:49: unexpected "}"'),
    broken("error_match_form", edit(FIX, M, "match severity = info", "match severity info"),
           "routing/main.routes:41: expected: match LABEL OP VALUE"),
    broken("error_include_form", edit(FIX, M, 'include "teams/payments.routes"', "include teams/payments.routes"),
           'routing/main.routes:26: expected: include "PATH"'),
    broken("error_receiver_twice", edit(FIX, S, "  match service ~ blob-*\n  match severity = warning\n  during",
                                        "  match service ~ blob-*\n  receiver storage-tickets\n  receiver storage-oncall\n  during"),
           'routing/teams/storage.routes:7: "receiver" given twice in one route'),
    broken("error_second_root", dict(FIX, **{M: FIX[M] + "\nroute {\n  receiver blackhole\n}\n"}),
           "routing/main.routes:53: second root route"),
    broken("error_no_root", dict(FIX, **{M: 'include "receivers.routes"\n'}), "routing/main.routes: no root route"),
    broken("error_bad_receiver_name", edit(FIX, R, "receiver search-oncall {", "receiver Search {"),
           'routing/receivers.routes:41: bad receiver name "Search"'),
    case("error_routes_missing", ["replay", "--routes", "{dir}/routing/none.routes", HIST], files(FIX),
         stderr_has=["pagerlog: ", "routing/none.routes: cannot read"]),
    # Histories that cannot be replayed; the routing file is read first.
    replay("history_bad_time", FIX, BAD_TIME, stderr_has=["pagerlog: ", "history.tsv: line 2: bad time"]),
    replay("history_wrong_fields", FIX, SMALL_HISTORY.replace("\tDiskFull\t", "\tDiskFull\t\t", 1),
           stderr_has=["pagerlog: ", "history.tsv: line ", ": expected 4 fields, found 5"]),
    replay("history_no_alerts", FIX, "time\talert\treceivers\tlabels\n", stderr_has=["pagerlog: ", "history.tsv: no alerts"]),
    replay("history_bad_header", FIX, "when\talert\treceivers\tlabels\n" + SMALL_HISTORY.split("\n", 1)[1],
           stderr_has=["pagerlog: ", "history.tsv: line 1: bad header"]),
    case("history_missing", ["replay", "--routes", ROUTES, "{dir}/nothing.tsv"], files(FIX), stderr_has=["pagerlog: ", "nothing.tsv"]),
    broken("both_bad_routing_first", edit(FIX, M, "match team = search", "match team =~ search"),
           'routing/main.routes:36: bad operator "=~"', history="time\talert\n"),
    # Usage errors.
    case("usage_no_routes", ["replay", HIST], files(FIX), stderr_has="pagerlog: "),
    case("usage_routes_twice", ["replay", "--routes", ROUTES, "--routes", ROUTES, HIST], files(FIX), stderr_has="pagerlog: "),
    case("usage_routes_without_value", ["replay", HIST, "--routes"], files(FIX), stderr_has="pagerlog: "),
    case("usage_unknown_option", ["replay", "--routes", ROUTES, "--verbose", HIST], files(FIX), stderr_has="pagerlog: "),
    case("usage_no_history", ["replay", "--routes", ROUTES], files(FIX), stderr_has="pagerlog: "),
    case("usage_two_histories", ["replay", "--routes", ROUTES, HIST, HIST], files(FIX), stderr_has="pagerlog: "),
    # Measures: forms the spec does not settle.
    case("m_routes_equals", ["replay", f"--routes={ROUTES}", HIST], files(FIX, MAIN_HISTORY), required=False),
    replay("m_routing_bom", dict(FIX, **{M: "﻿" + FIX[M]}), MAIN_HISTORY, required=False),
    case("m_history_dash", ["replay", "--routes", ROUTES, "-"], files(FIX), required=False),
    # pagerlog's existing commands, as the fixture's pagerlog answers them.
    existing("existing_check", ["check", HIST], MAIN_HISTORY),
    existing("existing_check_crlf", ["check", HIST], CRLF_HISTORY),
    existing("existing_check_empty", ["check", HIST], "time\talert\treceivers\tlabels\n"),
    existing("existing_check_invalid", ["check", HIST], BAD_TIME, stderr_has=["pagerlog: ", "line 2: bad time"]),
    existing("existing_receivers", ["receivers", HIST], BIG_HISTORY),
    existing("existing_receivers_by_name", ["receivers", "--sort", "name", HIST], MAIN_HISTORY),
    existing("existing_receivers_bad_sort", ["receivers", HIST, "--sort", "night"], MAIN_HISTORY, stderr_has="pagerlog: "),
    existing("existing_top", ["top", HIST], BIG_HISTORY),
    existing("existing_top_limit", [  "top", HIST, "--limit", "3"], MAIN_HISTORY),
    existing("existing_top_bad_limit", ["top", "--limit", "0", HIST], MAIN_HISTORY, stderr_has="pagerlog: "),
    existing("existing_missing_file", ["check", "{dir}/nothing.tsv"], MAIN_HISTORY, stderr_has=["pagerlog: ", "nothing.tsv: "]),
    existing("existing_unknown_command", ["purge", HIST], MAIN_HISTORY, stderr_has="pagerlog: "),
]


def run(argv, case_files, cwd_files=True):
    """(exit status, standard output with the files' directory written as {dir}, standard error)."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in case_files.items():
            path = Path(tmp) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
        args = [a.replace("{dir}", tmp) for a in argv]
        r = subprocess.run(args, cwd=tmp, capture_output=True, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    return r.returncode, r.stdout.replace(tmp.encode(), b"{dir}"), r.stderr.decode("utf-8", "replace").replace(tmp, "{dir}")


def build_fixture_pagerlog(work):
    """The fixture's own pagerlog, built offline with the host's cargo from a copy of the fixture under work."""
    src = Path(work) / "fixture"
    shutil.copytree(HERE.parent / "fixture", src, ignore=shutil.ignore_patterns("target"))
    for manifest in src.rglob("Cargo.toml.in"):
        manifest.rename(manifest.with_suffix(""))
    cargo = shutil.which("cargo") or sys.exit("cargo is needed to build the fixture's pagerlog")
    subprocess.run([cargo, "build", "--release", "--offline", "--quiet", "-p", "pagerlog"], cwd=src, check=True,
                   env=dict(os.environ, CARGO_TARGET_DIR=str(Path(work) / "target")))
    return str(Path(work) / "target" / "release" / "pagerlog")


def expected(c, fixture_pagerlog):
    if c["kind"] == "existing":
        return run([fixture_pagerlog, *c["args"]], c["files"])
    return run([sys.executable, str(HERE / "reference.py"), *c["args"]], c["files"])


def wanted_list(wanted):
    return [wanted] if isinstance(wanted, str) else wanted or []


def error_sets(seed=97, count=40):
    """Seeded routing sets, each with several errors, for --helper-parity: routes nested in the main file and
    in team files included from routes at different depths (some included twice), receiver lines before,
    between, and after child routes, two or more routes naming receivers no file defines, and in some sets a
    further error (a team file's block left open, a receiver defined twice, a root route without a receiver)
    that decides which error is reported first."""
    rng = random.Random(seed)
    out = []
    while len(out) < count:
        unknown = []  # unknown receiver lines, by file

        def receiver_line(path, required=False):
            if not required and rng.random() < 0.3:
                return None
            if rng.random() < 0.4:
                name = f"nope-{rng.randrange(100)}"
                unknown.append(path)
            else:
                name = f"r{rng.randrange(4)}"
            return f"receiver {name}"

        def route(path, depth, includes, root=False):
            """The lines of one route block at this depth, with child routes and include lines."""
            items = []
            if depth < 3:
                items += [route(path, depth + 1, includes) for _ in range(rng.randrange(3))]
            if includes and rng.random() < 0.5:
                items.insert(rng.randrange(len(items) + 1), [f'include "{includes.pop()}"'])
            body = [] if root else [f"match k{rng.randrange(3)} = v{rng.randrange(3)}"]
            line = receiver_line(path, required=root)
            if line:
                items.insert(rng.randrange(len(items) + 1), [line])
            lines = ["route {"] + ["  " + l for l in body]
            for item in items:
                lines += ["  " + l for l in item]
            return lines + ["}"]

        teams = [f"teams/t{j}.routes" for j in range(rng.randrange(1, 4))]
        files, included = {}, []
        for j, team in enumerate(teams):
            lines = ['include "../receivers.routes"'] if rng.random() < 0.5 else []
            for _ in range(rng.randrange(1, 3)):
                lines += route(f"routing/{team}", 1, [])
            files[f"routing/{team}"] = lines
        wanted = [t[len("teams/"):] for t in teams] + ([teams[0][len("teams/"):]] if rng.random() < 0.3 else [])
        rng.shuffle(wanted)
        pending = [f"teams/{w}" for w in wanted]
        main = ['include "receivers.routes"', ""] + route("routing/main.routes", 0, pending, root=True)
        included = set(wanted) - {p[len("teams/"):] for p in pending}
        if rng.random() < 0.3:
            main += ["", "receiver late {", "}"]
        kind = rng.random()
        if kind < 0.15 and files:
            team = rng.choice(sorted(files))
            files[team] = files[team] + ["receiver r1 {", "}"]
        elif kind < 0.3 and files:
            team = rng.choice(sorted(files))
            files[team] = files[team][:-1]
        elif kind < 0.4:
            main = [l for l in main if not (l.startswith("  receiver ") and not l.startswith("    "))]
        live = {"routing/main.routes"} | {f"routing/teams/{w}" for w in included}
        if sum(1 for path in unknown if path in live) < 2:
            continue
        files = {path: "\n".join(lines) + "\n" for path, lines in files.items()}
        files["routing/main.routes"] = "\n".join(main) + "\n"
        files["routing/receivers.routes"] = blocks("r0", "r1", "r2", "r3")
        out.append(files)
    return out


def routes_argument(args):
    """The routing file a case's command line names, or None."""
    for i, a in enumerate(args):
        if a == "--routes" and i + 1 < len(args):
            return args[i + 1]
        if a.startswith("--routes="):
            return a[len("--routes="):]
    return None


def helper_parity():
    """The fixture's tools/routes.py against the reference. docs/routing.md says the script reads routing files
    by the same rules, and the README sends on-call to it, so a bridge to the script, or a port of it, must fail
    only for what it is, never because the script and the documentation disagree. Every alert of every
    successful replay case goes to the same receivers by both; every replay case's routing file, and every
    routing set from error_sets, is either valid for both or reported by both with the same error (what
    `routes.py check` prints, and what replay prints after `pagerlog: `)."""
    sys.path.insert(0, str(HERE.parent / "fixture" / "tools"))
    import reference
    import routes
    from datetime import datetime, timezone

    def outcome(path):
        """(the reference's error or None, the script's error or None) for the routing file at path."""
        try:
            reference.load_routing(path)
            ours = None
        except reference.Fail as e:
            ours = str(e)
        try:
            routes.load(path)
            theirs = None
        except routes.RoutingError as e:
            theirs = str(e)
        return ours, theirs

    alerts, errors, sets = 0, 0, 0
    work = [(c["name"], c["files"], routes_argument(c["args"]), c) for c in CASES if c["kind"] == "replay"]
    work += [(f"error_set_{i}", s, ROUTES, None) for i, s in enumerate(error_sets())]
    for name, case_files, routes_arg, c in work:
        if routes_arg is None:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            for rel, text in case_files.items():
                p = Path(tmp) / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(text.encode("utf-8"))
            main = routes_arg.replace("{dir}", tmp)
            ours, theirs = outcome(main)
            if ours != theirs:
                raise SystemExit(f"{name}: the reference says {ours!r}, routes.py says {theirs!r}")
            sets += 1
            errors += ours is not None
            if c is None or ours is not None or c["stderr_has"] or not c["required"]:
                continue
            ref, scr = reference.load_routing(main), routes.load(main)
            for a in reference.read_history(os.path.join(tmp, "history.tsv")):
                labels = dict(a["labels"], alertname=a["name"])
                when = datetime(*a["time"], tzinfo=timezone.utc)
                if reference.destinations(ref, labels, a["time"]) != routes.receivers_for(scr, labels, when):
                    raise SystemExit(f"{name}: routes.py and the reference disagree on {a}")
                alerts += 1
    print(f"routes.py and the reference agree on {alerts} alerts and on reading {sets} routing sets "
          f"({errors} of them with the same error)")


def fixture_consistency():
    """The fixture's routing files and history are what write_fixture writes, setup.sh's third-quarter
    main.routes is the routing that decided the history's receivers, and the example in docs/replay.md is what
    the reference prints for them."""
    fixture = HERE.parent / "fixture"
    for rel, text in FIX.items():
        if (fixture / rel).read_text(encoding="utf-8") != text:
            raise SystemExit(f"fixture/{rel} differs from catalog.py; run --fixture fixture")
    if (fixture / "history" / "2026-q3.tsv").read_text(encoding="utf-8") != catalog.generate(seed=2026, count=240):
        raise SystemExit("fixture/history/2026-q3.tsv differs from its generator; run --fixture fixture")
    if catalog.Q3_ROUTING["main.routes"] not in (HERE.parent / "setup.sh").read_text(encoding="utf-8"):
        raise SystemExit("setup.sh's third-quarter main.routes differs from catalog.Q3_ROUTING")
    r = subprocess.run([sys.executable, str(HERE / "reference.py"), "replay", "--routes", "routing/main.routes",
                        "history/2026-q3.tsv"], cwd=fixture, capture_output=True, text=True, check=True)
    spec = (fixture / "docs" / "replay.md").read_text(encoding="utf-8")
    if f"history/2026-q3.tsv` prints:\n\n```\n{r.stdout}```\n" not in spec:
        raise SystemExit("the example in docs/replay.md differs from what the reference prints")


def main(argv):
    if argv[:1] == ["--fixture"]:
        write_fixture(Path(argv[1]))
        return 0
    if argv[:1] == ["--helper-parity"]:
        helper_parity()
        return 0
    fixture_consistency()
    cross = argv[1] if argv[:1] == ["--cross-check"] else None
    out, problems = [], []
    names = [c["name"] for c in CASES]
    if len(set(names)) != len(names):
        raise SystemExit("case names repeat")
    with tempfile.TemporaryDirectory() as work:
        fixture_pagerlog = build_fixture_pagerlog(work)
        for c in CASES:
            rc, stdout, stderr = expected(c, fixture_pagerlog)
            if rc != 0 and stdout:
                raise SystemExit(f"{c['name']}: the expected result has output on error")
            if c["required"] and c["kind"] == "replay" and (rc != 0) != bool(c["stderr_has"]):
                raise SystemExit(f"{c['name']}: expected exit {rc}, stderr {stderr!r}")
            wanted = c["stderr_has"] if rc != 0 else None
            for w in wanted_list(wanted):
                if w not in stderr:
                    raise SystemExit(f"{c['name']}: the expected stderr lacks {w!r}: {stderr!r}")
            if cross:
                got = run([cross, *c["args"]], c["files"])
                if got[0] != rc or got[1] != stdout or any(w not in got[2] for w in wanted_list(wanted)):
                    problems.append(f"{c['name']}: pagerlog gave {got[0]} {got[1][:80]!r} {got[2][:160]!r}, "
                                    f"expected {rc} {stdout[:80]!r} {stderr[:160]!r}")
            out.append({"name": c["name"], "kind": c["kind"], "required": c["required"], "args": c["args"],
                        "files_b64": {k: base64.b64encode(v.encode("utf-8")).decode() for k, v in c["files"].items()},
                        "rc": rc, "stdout_b64": base64.b64encode(stdout).decode(), "stderr_has": wanted})
    (HERE / "cases.json").write_text(json.dumps({"program": "pagerlog", "cases": out}, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(out)} cases written to {HERE / 'cases.json'}")
    for p in problems:
        print(p)
    return 1 if problems else 0


def write_fixture(directory):
    catalog.write_files(directory, FIX)
    history = Path(directory) / "history" / "2026-q3.tsv"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(catalog.generate(seed=2026, count=240), encoding="utf-8")
    print(f"routing files and {history} written")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
