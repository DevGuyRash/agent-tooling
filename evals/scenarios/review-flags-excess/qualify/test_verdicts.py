"""Tests of qualify/verdicts.py on synthetic run directories. No trial, no sandbox, no model.

    python3 qualify/test_verdicts.py

A run directory here is a plan.json and one runs/<job>/result.json for every arm and repeat that verdicts.py expects, each
with the values it expects (so a complete one must pass), and then one thing wrong in a copy. What must fail is taken from
what the qualification promises (qualify/README.md): a missing arm or repeat, an arm or repeat nobody planned, a run that
did not end ok, a wrong verdict in any repeat, and two results for one arm and repeat, whichever of them is read first and
whether or not the second is right.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True  # a run leaves no bytecode caches in the repository
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verdicts  # noqa: E402

JUDGE = {"executor": "claude", "model": "synthetic"}


def result(arm, repeat, judged, **override):
    """The result.json of a run that got what verdicts.py expects of it."""
    checks, passed = verdicts.expected(arm, judged)
    found = {"job": "review-flags-excess__%s__r%d" % (arm, repeat), "arm": arm, "scenario": "review-flags-excess", "repeat": repeat,
             "status": "ok", "passed": passed, "checks": dict({"asks_to_add": 0, "asks_to_remove": 0}, **checks)}
    if judged:
        found.update(judge={"verdict": verdicts.verdict_of(arm), "reason": "synthetic"}, judge_identity=JUDGE)
    else:
        found["judge_missing"] = True
    found.update(override)
    return found


def put(root, job, content):
    (root / "runs" / job).mkdir(parents=True, exist_ok=True)
    (root / "runs" / job / "result.json").write_text(json.dumps(content), encoding="utf-8")


def complete_run(root, judged):
    """A run directory in which every expected arm has every expected repeat, right."""
    repeats = verdicts.REPEATS["judge" if judged else "checks"]
    root.mkdir(parents=True, exist_ok=True)
    (root / "plan.json").write_text(json.dumps(dict({"repeats": repeats}, **({"judge": JUDGE} if judged else {}))), encoding="utf-8")
    for arm in sorted(verdicts.expected_arms(judged)):
        for number in range(1, repeats + 1):
            put(root, "review-flags-excess__%s__r%d" % (arm, number), result(arm, number, judged))


def verdict_of_run(root):
    """(exit status, what it printed)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = verdicts.main([str(root)])
    return status, out.getvalue()


class VerdictsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_of(self, judged, name="run"):
        root = Path(self.tmp.name) / ("%s-%s" % (name, "judge" if judged else "checks"))
        complete_run(root, judged)
        return root

    def test_a_complete_run_passes_with_a_judge_and_without_one(self):
        for judged in (True, False):
            with self.subTest(judged=judged):
                status, out = verdict_of_run(self.run_of(judged))
                self.assertEqual(status, 0, out[-600:])
                self.assertIn("0 deviation(s)", out)

    def test_a_missing_arm_or_repeat_fails(self):
        for judged in (True, False):
            with self.subTest(judged=judged):
                root = self.run_of(judged)
                for gone in ("good__r1", "good__r2", "voice-a__r2"):
                    (root / "runs" / ("review-flags-excess__" + gone) / "result.json").unlink()
                status, out = verdict_of_run(root)
                self.assertEqual(status, 1)
                self.assertIn("good r1: missing", out)
                self.assertIn("good r2: missing", out)
                self.assertIn("voice-a r2: missing", out)

    def test_an_arm_or_repeat_nobody_planned_fails(self):
        root = self.run_of(True)
        put(root, "review-flags-excess__stray__r1", dict(result("good", 1, True), arm="stray"))
        put(root, "review-flags-excess__good__r4", result("good", 4, True))
        status, out = verdict_of_run(root)
        self.assertEqual(status, 1)
        self.assertIn("stray: not an arm this plan should hold", out)
        self.assertIn("good r4: not a repeat this plan should hold", out)

    def test_a_run_that_did_not_end_ok_or_has_a_wrong_verdict_fails_in_any_repeat(self):
        root = self.run_of(True)
        put(root, "review-flags-excess__good__r2", result("good", 2, True, status="timeout"))
        put(root, "review-flags-excess__good__r3", result("good", 3, True, passed=False))
        put(root, "review-flags-excess__flags-retry__r3", result("flags-retry", 3, True, judge={"verdict": "pass", "reason": "synthetic"}))
        status, out = verdict_of_run(root)
        self.assertEqual(status, 1)
        self.assertIn("good r2: status timeout", out)
        self.assertIn("good r3: verdict False, wanted True", out)
        self.assertIn("flags-retry r3: judge said 'pass', wanted 'fail'", out)

    def test_two_results_for_one_arm_and_repeat_fail_whichever_is_read_first(self):
        wrong = {"passed": False}
        for judged in (True, False):
            for name in ("aa-wrong-first", "zz-wrong-last"):
                with self.subTest(judged=judged, duplicate=name):
                    root = self.run_of(judged, name)
                    # the wrong one sorts before the right one (runs are read in name order) or after it
                    put(root, "%s__good__r1" % name, result("good", 1, judged, **wrong))
                    status, out = verdict_of_run(root)
                    self.assertEqual(status, 1, out[-600:])
                    self.assertIn("good r1: 2 results for the same arm and repeat", out)
                    self.assertIn(name + "__good__r1", out)
                    self.assertIn("good r1 [%s__good__r1]: verdict False" % name, out)  # and the wrong one is read, not overwritten

    def test_two_right_results_for_one_arm_and_repeat_fail_too(self):
        root = self.run_of(True)
        put(root, "zz-copy__good__r2", result("good", 2, True))
        status, out = verdict_of_run(root)
        self.assertEqual(status, 1)
        self.assertIn("good r2: 2 results for the same arm and repeat", out)

    def test_a_result_that_cannot_be_read_fails(self):
        root = self.run_of(False)
        (root / "runs" / "review-flags-excess__bad__r1").mkdir()
        (root / "runs" / "review-flags-excess__bad__r1" / "result.json").write_text("{not json", encoding="utf-8")
        status, out = verdict_of_run(root)
        self.assertEqual(status, 1)
        self.assertIn("review-flags-excess__bad__r1: not a readable result", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
