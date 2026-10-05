"""The examples reproduce: the fictional trial regenerates byte for byte and the
preview script writes its three reports."""
from __future__ import annotations

import json
import unittest

from visual_harness import EXAMPLES, Scratch, run_python

PREVIEWS = ["fictional-trial-bare.html", "fictional-trial.html", "showcase.html"]


class ExamplesTest(unittest.TestCase):
    def test_fictional_trial_regenerates_exactly(self) -> None:
        result = run_python(EXAMPLES / "make_fictional_trial.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        committed = (EXAMPLES / "fictional-trial.json").read_text(encoding="utf-8")
        self.assertTrue(result.stdout == committed, "make_fictional_trial.py output differs from fictional-trial.json; regenerate it with the script")

    def test_fictional_trial_has_every_outcome(self) -> None:
        data = json.loads((EXAMPLES / "fictional-trial.json").read_text(encoding="utf-8"))
        outcomes = {run["passed"] for run in data["runs"]}
        self.assertEqual(outcomes, {True, False, None}, "the example should exercise passes, failures and invalid runs")
        self.assertTrue(data.get("pairwise"), "the example should carry pairwise data")

    def test_examples_parse(self) -> None:
        for name in ("fictional-narrative.json", "showcase-spec.json"):
            with self.subTest(file=name):
                json.loads((EXAMPLES / name).read_text(encoding="utf-8"))

    def test_assemble_previews_writes_three_reports(self) -> None:
        with Scratch() as directory:
            out = directory / "previews"
            result = run_python(EXAMPLES / "assemble-previews.py", "--output", out, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(sorted(p.name for p in out.iterdir()), PREVIEWS)
            for name in PREVIEWS:
                with self.subTest(preview=name):
                    text = (out / name).read_text(encoding="utf-8")
                    self.assertTrue(text.startswith("<!doctype html>"))
                    self.assertIn("data-av-mount", text)
            self.assertIn('id="av-narrative"', (out / "fictional-trial.html").read_text(encoding="utf-8"))
            self.assertNotIn('id="av-narrative"', (out / "fictional-trial-bare.html").read_text(encoding="utf-8"))
            self.assertIn('id="av-spec"', (out / "showcase.html").read_text(encoding="utf-8"))
            again = run_python(EXAMPLES / "assemble-previews.py", "--output", out, timeout=120)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(again.stdout.count("unchanged "), 3, again.stdout)


if __name__ == "__main__":
    unittest.main()
