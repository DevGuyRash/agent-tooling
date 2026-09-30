import unittest

import pipeline

SAMPLE = [
    {"id": "x", "v": 1},
    {"id": "y", "v": 2},
    {"id": "x", "v": 3},
]


class PipelineTest(unittest.TestCase):
    def test_process_dedupes(self):
        self.assertEqual([r["id"] for r in pipeline.process(SAMPLE)], ["x", "y"])

    def test_summarize_counts(self):
        summary = pipeline.summarize(SAMPLE)
        self.assertEqual(summary, {"total": 3, "unique": 2})


if __name__ == "__main__":
    unittest.main()
