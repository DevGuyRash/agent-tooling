import contextlib
import io
import json
import os
import tempfile
import unittest

from stampcard.cli import main

CARDS = "id,name,stamps\nC-001,Ada,8\nC-004,Di,0\n"
EVENTS = "\n".join(
    json.dumps({"id": "e%d" % n, "card": card, "kind": "purchase", "cents": cents, "ts": "2026-10-01T09:0%d:00" % n})
    for n, (card, cents) in enumerate([("C-001", 800), ("C-004", 450)], 1)
) + "\n"


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def path(self, name, text=None):
        path = os.path.join(self.dir.name, name)
        if text is not None:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return path

    def test_prints_the_report_and_writes_the_outbox(self):
        outbox = self.path("out.jsonl")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([self.path("events.jsonl", EVENTS), self.path("cards.csv", CARDS), "--outbox", outbox])
        self.assertEqual(code, 0)
        self.assertIn("free drinks: 1\n", out.getvalue())
        self.assertIn("  C-004  stamps 1  drinks 0\n", out.getvalue())
        with open(outbox, encoding="utf-8") as f:
            self.assertEqual([json.loads(l)["to"] for l in f], ["C-001"])

    def test_missing_file_is_a_usage_error(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main([self.path("nope.jsonl"), self.path("cards.csv", CARDS)])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err.getvalue())


if __name__ == "__main__":
    unittest.main()
