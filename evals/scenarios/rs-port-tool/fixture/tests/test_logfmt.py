import unittest

from reqstat.logfmt import ParseError, normalize_path, parse_duration, parse_line, split_pairs


class SplitPairsTest(unittest.TestCase):
    def test_bare_and_quoted_values(self):
        self.assertEqual(split_pairs('a=1 b="two words" c='), {"a": "1", "b": "two words", "c": ""})

    def test_escapes_inside_quotes(self):
        self.assertEqual(split_pairs(r'msg="say \"hi\" \\ bye"'), {"msg": 'say "hi" \\ bye'})

    def test_tabs_separate_pairs_and_last_value_wins(self):
        self.assertEqual(split_pairs("a=1\tb=2  a=3"), {"a": "3", "b": "2"})

    def test_rejects_bare_word(self):
        with self.assertRaises(ParseError):
            split_pairs("a=1 oops b=2")

    def test_rejects_unterminated_quote(self):
        with self.assertRaises(ParseError):
            split_pairs('a="never closed')

    def test_rejects_text_after_quote(self):
        with self.assertRaises(ParseError):
            split_pairs('a="x"y b=2')


class DurationTest(unittest.TestCase):
    def test_units(self):
        self.assertEqual(parse_duration("350us"), 350)
        self.assertEqual(parse_duration("12.5ms"), 12500)
        self.assertEqual(parse_duration("1.2s"), 1200000)
        self.assertEqual(parse_duration("0.000001s"), 1)

    def test_rejects_sub_microsecond_precision(self):
        for text in ("1.5us", "1.0001ms", "1.0000001s", "12", "ms", "-3ms", "1e3ms"):
            with self.subTest(text=text), self.assertRaises(ParseError):
                parse_duration(text)


class ParseLineTest(unittest.TestCase):
    def test_full_record(self):
        req = parse_line("ts=2026-09-14T08:00:01Z method=GET path=/a status=200 dur=1ms bytes=10 extra=x")
        self.assertEqual((req.ts, req.method, req.path, req.status, req.dur_us, req.bytes),
                         ("2026-09-14T08:00:01Z", "GET", "/a", 200, 1000, 10))

    def test_bytes_default_to_zero(self):
        self.assertEqual(parse_line("ts=2026-09-14T08:00:01Z method=GET path=/a status=200 dur=1ms").bytes, 0)

    def test_invalid_fields(self):
        base = {"ts": "2026-09-14T08:00:01Z", "method": "GET", "path": "/a", "status": "200", "dur": "1ms"}
        bad = {"ts": ["2026-13-01T00:00:00Z", "2026-09-14 08:00:01", "2026-09-14T24:00:00Z"],
               "method": ["get", "G3T"], "path": ["a/b"], "status": ["99", "600", "2000", "abc"],
               "dur": ["fast"], "bytes": ["-1", "1.5"]}
        for key, values in bad.items():
            for value in values:
                line = " ".join(f"{k}={v}" for k, v in dict(base, **{key: value}).items())
                with self.subTest(line=line), self.assertRaises(ParseError):
                    parse_line(line)

    def test_missing_field(self):
        with self.assertRaises(ParseError):
            parse_line("ts=2026-09-14T08:00:01Z method=GET path=/a dur=1ms")


class NormalizePathTest(unittest.TestCase):
    def test_placeholders(self):
        self.assertEqual(normalize_path("/api/users/42/orders"), "/api/users/:id/orders")
        self.assertEqual(normalize_path("/o/9f1c2e4a-55b0-4c7e-a1d2-3e4f5a6b7c8d"), "/o/:uuid")
        self.assertEqual(normalize_path("/v2/items"), "/v2/items")

    def test_query_and_slashes(self):
        self.assertEqual(normalize_path("//a//b/?x=1/2"), "/a/b")
        self.assertEqual(normalize_path("/?q"), "/")
