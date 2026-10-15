import unittest

from stampcard.events import Malformed, parse_line

GOOD = '{"id": "e1", "card": "C-001", "kind": "purchase", "cents": 450, "ts": "2026-10-01T09:02:00"}'


class ParseLineTest(unittest.TestCase):
    def test_reads_a_valid_event(self):
        event = parse_line(GOOD)
        self.assertEqual((event.id, event.card, event.kind, event.cents), ("e1", "C-001", "purchase", 450))

    def test_rejects_lines_that_are_not_events(self):
        bad = [
            "not json",
            "[1, 2]",
            '{"id": "e1", "card": "C-001", "kind": "purchase", "cents": 450}',
            GOOD.replace("purchase", "gift"),
            GOOD.replace("450", "0"),
            GOOD.replace("450", '"450"'),
            GOOD.replace("450", "true"),
            GOOD.replace("450", "4.5"),
        ]
        for text in bad:
            with self.subTest(text=text):
                self.assertRaises(Malformed, parse_line, text)


if __name__ == "__main__":
    unittest.main()
