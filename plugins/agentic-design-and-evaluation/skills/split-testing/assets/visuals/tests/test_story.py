"""Every report tells its whole story: the checkers refuse a trial, comparison,
specification or collection missing what a reader new to the work needs, and
the page opens with the story and reads each view (story.cjs). report.py
--check refuses the same input, as the page lists it."""
from __future__ import annotations

import json
import unittest

from visual_harness import EXAMPLES, REPORT, NodeCases, Scratch, run_python


class StoryCasesTest(NodeCases):
    """The story's checks and how the page draws it, against the built bundle."""

    script = "story.cjs"
    minimum = 8

    def test_every_report_tells_its_whole_story(self) -> None:
        self.run_script_cases()


class StoryCheckTest(unittest.TestCase):
    def test_check_refuses_a_report_that_tells_half_a_story(self) -> None:
        narrative = json.loads((EXAMPLES / "comparisons/sandwich-narrative.json").read_text(encoding="utf-8"))
        narrative["story"]["rule"] = "Fixed before results: see ../README.md (Decision rule)"
        del narrative["story"]["notCovered"], narrative["story"]["alternatives"]["jelly"], narrative["readings"]["results"]
        with Scratch() as directory:
            path = directory / "n.json"
            path.write_text(json.dumps(narrative), encoding="utf-8")
            result = run_python(REPORT, "--check", "--data", EXAMPLES / "comparisons/sandwich.json", "--narrative", path)
        self.assertEqual(result.returncode, 1)
        self.assertEqual([line for line in result.stderr.splitlines() if not line.startswith("hint: ")], [
            'error: narrative.story: missing required field "notCovered"',
            'error: narrative.story.alternatives: does not describe alternative "jelly"',
            'error: narrative.story.rule: points the reader at "../README.md", which this report does not include',
            'error: narrative.readings: no reading for the "results" section',
        ])


if __name__ == "__main__":
    unittest.main()
