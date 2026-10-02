"""Tests for routes.py: python3 -m unittest discover -s tools"""
import contextlib
import io
import os
import tempfile
import unittest
from datetime import datetime, timezone

import routes

RECEIVERS = """\
receiver platform-oncall {
  page platform-primary
  chat #platform
}
receiver payments-oncall {
  page payments-primary
}
receiver payments-tickets {
  ticket PAY
}
receiver dba-oncall {
  page dba-primary
}
receiver drop {
}
"""

MAIN = """\
# Test routing
include "receivers.routes"

route {
  receiver platform-oncall
  route {
    match service ~ db-*
    receiver dba-oncall
    continue
  }
  route {
    match team = payments
    receiver payments-oncall
    include "teams/payments.routes"
  }
  route {
    match env != prod
    receiver drop
  }
}
"""

PAYMENTS = """\
include "../receivers.routes"

route {
  match severity = info
  receiver payments-tickets
}
route {
  match alertname ~ *Latency
  during mon-fri 09:00-17:00
  continue
}
route {
  match alertname ~ *Latency
  receiver payments-tickets
}
"""

MONDAY_NOON = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
SATURDAY = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


class Files:
    """A directory of routing files for one test."""

    def __init__(self, files):
        self.tmp = tempfile.TemporaryDirectory()
        for name, text in files.items():
            path = os.path.join(self.tmp.name, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def close(self):
        self.tmp.cleanup()


class RoutingTest(unittest.TestCase):
    def files(self, files):
        f = Files(files)
        self.addCleanup(f.close)
        return f

    def standard(self):
        return self.files({"main.routes": MAIN, "receivers.routes": RECEIVERS, "teams/payments.routes": PAYMENTS})

    def routing(self):
        return routes.load(self.standard().path("main.routes"))

    def error(self, files, main="main.routes"):
        f = self.files(files)
        with self.assertRaises(routes.RoutingError) as ctx:
            routes.load(f.path(main))
        return str(ctx.exception).replace(f.tmp.name + os.sep, "")

    def go(self, labels, when=MONDAY_NOON):
        return routes.receivers_for(self.routing(), labels, when)


class LoadTest(RoutingTest):
    def test_counts(self):
        r = self.routing()
        self.assertEqual(len(r.receivers), 5)
        self.assertEqual(len(r.routes), 7)

    def test_included_routes_join_the_route_that_includes_them(self):
        r = self.routing()
        payments = r.root.children[1]
        self.assertEqual([c.where.rsplit(":", 1)[1] for c in payments.children], ["3", "7", "12"])
        self.assertTrue(all(c.parent is payments for c in payments.children))

    def test_a_file_already_read_is_skipped(self):
        # receivers.routes is included twice; reading it twice would define every receiver twice.
        self.assertIn("dba-oncall", self.routing().receivers)

    def test_crlf_and_tabs(self):
        f = self.files({"main.routes": "receiver a {\r\n}\r\nroute\t{\r\n\treceiver\t a\r\n}\r\n"})
        self.assertEqual(routes.load(f.path("main.routes")).root.receiver, "a")

    def test_hash_inside_a_line_is_text(self):
        f = self.files({"main.routes": "receiver a {\n  chat #ops\n}\nroute {\n  receiver a\n}\n"})
        self.assertEqual(routes.load(f.path("main.routes")).receivers["a"].targets, [("chat", "#ops")])

    def test_days(self):
        self.assertEqual(routes.parse_days("mon-fri"), {0, 1, 2, 3, 4})
        self.assertEqual(routes.parse_days("fri-mon"), {4, 5, 6, 0})
        self.assertEqual(routes.parse_days("mon-thu,sat"), {0, 1, 2, 3, 5})
        self.assertEqual(routes.parse_days("sun"), {6})
        for bad in ("", "mon,", "Mon", "mon-tue-wed", "weekend"):
            self.assertIsNone(routes.parse_days(bad), bad)

    def test_windows(self):
        self.assertEqual(routes.parse_window("09:00-17:30"), (540, 1050))
        self.assertEqual(routes.parse_window("00:00-24:00"), (0, 1440))
        for bad in ("17:00-09:00", "09:00-09:00", "9:00-17:00", "09:00-24:30", "24:00-24:00", "09:60-10:00"):
            self.assertIsNone(routes.parse_window(bad), bad)


class ErrorTest(RoutingTest):
    def test_unknown_receiver_names_the_included_file(self):
        files = {"main.routes": MAIN, "receivers.routes": RECEIVERS,
                 "teams/payments.routes": PAYMENTS.replace("receiver payments-tickets", "receiver payments-ticket", 1)}
        self.assertEqual(self.error(files), 'teams/payments.routes:5: unknown receiver "payments-ticket"')

    def test_unknown_receivers_in_the_order_read(self):
        files = {"main.routes": "receiver x {\n}\nroute {\n  route {\n    match a = b\n    receiver nope-child\n  }\n"
                                "  receiver nope-root\n}\n"}
        self.assertEqual(self.error(files), 'main.routes:6: unknown receiver "nope-child"')

    def test_duplicate_receiver(self):
        files = {"main.routes": 'include "a.routes"\nreceiver x {\n}\nroute {\n  receiver x\n}\n',
                 "a.routes": "\nreceiver x {\n}\n"}
        self.assertEqual(self.error(files), 'main.routes:2: receiver "x" is already defined at a.routes:2')

    def test_include_cycle(self):
        files = {"main.routes": 'include "a.routes"\nroute {\n  receiver x\n}\n', "a.routes": 'include "main.routes"\n'}
        self.assertEqual(self.error(files), 'a.routes:1: include cycle at "main.routes"')

    def test_include_missing(self):
        files = {"main.routes": 'route {\n  receiver x\n  include "teams/none.routes"\n}\n'}
        self.assertEqual(self.error(files), 'main.routes:3: cannot read "teams/none.routes"')

    def test_routes_included_outside_a_route(self):
        files = {"main.routes": 'include "t.routes"\nroute {\n  receiver x\n}\n', "t.routes": "route {\n}\n"}
        self.assertEqual(self.error(files), 'main.routes:1: "t.routes" has routes; include it inside a route')

    def test_root_route(self):
        self.assertEqual(self.error({"main.routes": "receiver x {\n}\n"}), "main.routes: no root route")
        self.assertEqual(self.error({"main.routes": "route {\n}\n"}), "main.routes:1: the root route has no receiver")
        self.assertEqual(self.error({"main.routes": "route {\n  receiver x\n  continue\n}\n"}),
                         'main.routes:3: the root route cannot have "continue"')
        self.assertEqual(self.error({"main.routes": "receiver x {\n}\nroute {\n  receiver x\n}\nroute {\n}\n"}),
                         "main.routes:6: second root route")

    def test_block_not_closed(self):
        files = {"main.routes": "receiver x {\n}\nroute {\n  receiver x\n  route {\n    match a = b\n}\n"}
        self.assertEqual(self.error(files), "main.routes:3: block is not closed")

    def test_line_errors(self):
        cases = [
            ("  matches team = a", 'unexpected "matches"'),
            ("  match team == a", 'bad operator "=="'),
            ("  match Team = a", 'bad label "Team"'),
            ("  match team =", "expected: match LABEL OP VALUE"),
            ("  during weekdays 09:00-17:00", 'bad days "weekdays"'),
            ("  during mon-fri 17:00-09:00", 'bad time window "17:00-09:00"'),
            ("  during mon-fri", "expected: during DAYS FROM-TO"),
            ("  receiver y\n    receiver y", '"receiver" given twice in one route', 9),
            ("  route payments {", "expected: route {"),
            ("  include teams.routes", 'expected: include "PATH"'),
        ]
        for line, message, *at in cases:
            text = f"receiver x {{\n}}\nreceiver y {{\n}}\nroute {{\n  receiver x\n  route {{\n{line}\n  }}\n}}\n"
            self.assertEqual(self.error({"main.routes": text}), f"main.routes:{at[0] if at else 8}: {message}", line)

    def test_receiver_errors(self):
        self.assertEqual(self.error({"main.routes": "receiver Ops {\n}\n"}), 'main.routes:1: bad receiver name "Ops"')
        self.assertEqual(self.error({"main.routes": "receiver ops {\n  page\n}\n"}), "main.routes:2: expected: page SCHEDULE")
        self.assertEqual(self.error({"main.routes": "receiver ops {\n  match a = b\n}\n"}), 'main.routes:2: unexpected "match"')
        self.assertEqual(self.error({"main.routes": "}\n"}), 'main.routes:1: unexpected "}"')

    def test_unreadable_main_file(self):
        f = self.files({})
        with self.assertRaises(routes.RoutingError) as ctx:
            routes.load(f.path("none.routes"))
        self.assertTrue(str(ctx.exception).endswith("none.routes: cannot read"))


class RouteTest(RoutingTest):
    def test_root_receiver_when_nothing_matches(self):
        self.assertEqual(self.go({"alertname": "Down", "env": "prod"}), ["platform-oncall"])

    def test_missing_label_counts_as_empty(self):
        # env != prod holds when there is no env label at all.
        self.assertEqual(self.go({"alertname": "Down"}), ["drop"])

    def test_continue(self):
        self.assertEqual(self.go({"service": "db-orders", "team": "payments", "env": "prod"}),
                         ["dba-oncall", "payments-oncall"])

    def test_first_match_wins_without_continue(self):
        self.assertEqual(self.go({"team": "payments", "env": "dev"}), ["payments-oncall"])

    def test_included_route_inherits_the_including_route(self):
        # The Latency route in office hours has no receiver of its own: it uses payments-oncall's.
        self.assertEqual(self.go({"team": "payments", "alertname": "ApiLatency", "env": "prod"}),
                         ["payments-oncall", "payments-tickets"])

    def test_windows(self):
        self.assertEqual(self.go({"team": "payments", "alertname": "ApiLatency", "env": "prod"}, SATURDAY),
                         ["payments-tickets"])
        five = datetime(2026, 9, 28, 17, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(self.go({"team": "payments", "alertname": "ApiLatency", "env": "prod"}, five),
                         ["payments-tickets"])

    def test_patterns(self):
        self.assertTrue(routes.pattern_matches("db-*", "db-"))
        self.assertTrue(routes.pattern_matches("*Latency", "Latency"))
        self.assertTrue(routes.pattern_matches("a*b*c", "aXbYbc"))
        self.assertFalse(routes.pattern_matches("db-*", "mydb-1"))
        self.assertFalse(routes.pattern_matches("a.c", "abc"))
        self.assertTrue(routes.pattern_matches("*", ""))

    def test_receivers_listed_once(self):
        f = self.files({"main.routes": "receiver a {\n}\nreceiver b {\n}\nroute {\n  receiver a\n"
                                       "  route {\n    match x = 1\n    continue\n  }\n"
                                       "  route {\n    match y = 1\n    receiver b\n    continue\n  }\n"
                                       "  route {\n    match z = 1\n  }\n}\n"})
        r = routes.load(f.path("main.routes"))
        self.assertEqual(routes.receivers_for(r, {"x": "1", "y": "1", "z": "1"}, MONDAY_NOON), ["a", "b"])


class CommandTest(RoutingTest):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = routes.main(argv)
        return status, out.getvalue(), err.getvalue()

    def test_check(self):
        path = self.standard().path("main.routes")
        self.assertEqual(self.run_main(["check", path]), (0, f"{path}: ok, 5 receivers, 7 routes\n", ""))

    def test_test(self):
        path = self.standard().path("main.routes")
        status, out, _ = self.run_main(["test", path, "--at", "2026-09-28T12:00:00Z", "team=payments",
                                        "alertname=ApiLatency", "env=prod"])
        self.assertEqual((status, out), (0, "payments-oncall\npayments-tickets\n"))

    def test_usage(self):
        self.assertEqual(self.run_main(["test", "x.routes", "team"])[0], 2)
        self.assertEqual(self.run_main(["test", "x.routes", "--at", "noon"])[0], 2)
        self.assertEqual(self.run_main(["lint", "x.routes"])[0], 2)


if __name__ == "__main__":
    unittest.main()
