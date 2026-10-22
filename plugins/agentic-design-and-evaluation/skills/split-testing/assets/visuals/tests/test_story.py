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


    def test_check_runs_every_check_on_a_specification_that_claims_none(self) -> None:
        spec = {"title": "Claimed", "problems": [], "sections": [{"title": "Results", "blocks": [{"type": "intervals", "rows": [{"label": "A", "value": 3, "lo": 2, "hi": 4}]}]}]}
        with Scratch() as directory:
            path = directory / "s.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            result = run_python(REPORT, "--check", "--spec", path)
        self.assertEqual(result.returncode, 1)
        self.assertEqual([line for line in result.stderr.splitlines() if not line.startswith("hint: ")], [
            'error: spec: missing "story", which tells a reader new to this work what it is about',
            "error: sections[0]: says nothing about what its views show for this data",
        ])

    def test_check_general_reads_the_comparison_the_page_derives(self) -> None:
        # Two arms on one case, no narrative: the derived comparison shows what was compared, the results, the
        # difference between the two arms and every observation, and nothing tells their story.
        runs = [{"job": f"c__{arm}__r{i}", "scenario": "c", "arm": arm, "repeat": i, "passed": mark == "P"} for arm, marks in (("a", "PPF"), ("b", "PFF")) for i, mark in enumerate(marks, 1)]
        trial = {"name": "t", "plan": {"arms": {"a": {}, "b": {}}, "scenarios": [{"name": "c", "prompt": "Do it."}]}, "runs": runs}
        expected = [
            'error: narrative: missing "story", which tells a reader new to this work what it is about',
            'error: narrative.readings: no reading for the "compared" section',
            'error: narrative.readings: no reading for the "results" section',
            'error: narrative.readings: no reading for the "differences" section',
            'error: narrative.readings: no reading for the "observations" section',
        ]
        with Scratch() as directory:
            path, empty = directory / "t.json", directory / "n.json"
            path.write_text(json.dumps(trial), encoding="utf-8")
            empty.write_text("{}", encoding="utf-8")
            for extra in ([], ["--narrative", empty]):
                with self.subTest(narrative=bool(extra)):
                    result = run_python(REPORT, "--check", "--trial", path, "--general", *extra)
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertEqual([line for line in result.stderr.splitlines() if not line.startswith("hint: ")], expected)


    def test_check_refuses_a_plan_rule_that_only_points_at_a_file_until_the_narrative_states_it(self) -> None:
        runs = [{"job": f"c__{arm}__r1", "scenario": "c", "arm": arm, "repeat": 1, "passed": arm == "a"} for arm in ("a", "b")]
        trial = {"name": "t", "plan": {"decision_rule": "Fixed before results: see ../README.md (Decision rule)", "arms": {"a": {}, "b": {}}, "scenarios": [{"name": "c"}]}, "runs": runs}
        story = {"background": "b", "intent": "i", "questions": ["q"], "covers": "c", "notCovered": "n", "alternatives": {"a": "A.", "b": "B."}, "cases": {"c": "C."}}
        readings = {"setup": "s", "arms": "a", "cases": "c", "failures": "f", "runs": "r"}
        with Scratch() as directory:
            path = directory / "t.json"
            path.write_text(json.dumps(trial), encoding="utf-8")
            for rule, expected in ((None, [
                    'error: narrative.story: missing "rule": how the decision was to be made, in plain words',
                    'error: narrative.story.rule: the plan\'s decision rule points the reader at "../README.md", which this report does not include, so the narrative states the rule']),
                    ("Adopt a if it passes more often than b.", [])):
                with self.subTest(rule=rule):
                    narrative = directory / "n.json"
                    narrative.write_text(json.dumps({"story": {**story, **({"rule": rule} if rule else {})}, "readings": readings}), encoding="utf-8")
                    result = run_python(REPORT, "--check", "--trial", path, "--narrative", narrative)
                    self.assertEqual([line for line in result.stderr.splitlines() if not line.startswith("hint: ")], expected)
                    self.assertEqual(result.returncode, 1 if expected else 0)


if __name__ == "__main__":
    unittest.main()
