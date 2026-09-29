import json
import os
import tempfile
import unittest

from eventspool import JsonlSink, MemorySink


class MemorySinkTests(unittest.TestCase):
    def test_keeps_batches_and_events(self):
        sink = MemorySink()
        sink.write([1, 2])
        sink.write([3])
        self.assertEqual(sink.batches, [[1, 2], [3]])
        self.assertEqual(sink.events, [1, 2, 3])


class JsonlSinkTests(unittest.TestCase):
    def test_appends_one_line_per_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "audit.jsonl")
            sink = JsonlSink(path)
            sink.write([{"a": 1}, {"b": 2}])
            sink.write([{"c": 3}])
            with open(path, encoding="utf-8") as f:
                self.assertEqual([json.loads(line) for line in f], [{"a": 1}, {"b": 2}, {"c": 3}])

    def test_creates_missing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "logs", "audit.jsonl")
            JsonlSink(path).write([{"a": 1}])
            self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
