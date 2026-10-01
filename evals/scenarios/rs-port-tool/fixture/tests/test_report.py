import unittest

from reqstat.logfmt import Request
from reqstat.report import Summary, human_bytes, ms, percentile, ratio_tenths, render_csv, select


def req(path="/a", status=200, dur_us=1000, size=0, ts="2026-09-14T08:00:00Z", method="GET"):
    return Request(ts=ts, method=method, path=path, status=status, dur_us=dur_us, bytes=size)


class ArithmeticTest(unittest.TestCase):
    def test_nearest_rank_percentile(self):
        values = list(range(1, 21))
        self.assertEqual(percentile(values, 50), 10)
        self.assertEqual(percentile(values, 95), 19)
        self.assertEqual(percentile(values, 99), 20)
        self.assertEqual(percentile([7], 50), 7)

    def test_rounding_is_half_up(self):
        self.assertEqual(ms(84250), "84.3")
        self.assertEqual(ms(84249), "84.2")
        self.assertEqual(ms(49), "0.0")
        self.assertEqual(ratio_tenths(1, 3), 333)
        self.assertEqual(ratio_tenths(1, 8), 125)
        self.assertEqual(ratio_tenths(1, 16), 63)

    def test_human_bytes(self):
        self.assertEqual(human_bytes(1023), "1023 B")
        self.assertEqual(human_bytes(1024), "1.0 KiB")
        self.assertEqual(human_bytes(1048575), "1.0 MiB")
        self.assertEqual(human_bytes(5 * 1024 ** 3 + 1), "5.0 GiB")


class SelectTest(unittest.TestCase):
    def summary(self, by="route"):
        s = Summary()
        for r in [req("/b"), req("/b", status=500, dur_us=9000), req("/a", dur_us=500), req("/c"), req("/c")]:
            s.add(r, by)
        return s

    def test_sorting_and_limits(self):
        s = self.summary()
        self.assertEqual([r.name for r in select(s)], ["GET /b", "GET /c", "GET /a"])
        self.assertEqual([r.name for r in select(s, order="p95")], ["GET /b", "GET /c", "GET /a"])
        self.assertEqual([r.name for r in select(s, order="name")], ["GET /a", "GET /b", "GET /c"])
        self.assertEqual([r.name for r in select(s, order="errors", top=2)], ["GET /b", "GET /a"])
        self.assertEqual([r.name for r in select(s, min_count=2)], ["GET /b", "GET /c"])

    def test_csv_quotes_names_that_need_it(self):
        s = Summary()
        s.add(req("/tags/a,b"), "path")
        self.assertEqual(render_csv(select(s), "path").splitlines()[1], '"/tags/a,b",1,0,0.0,1.0,1.0,1.0,1.0,0')
