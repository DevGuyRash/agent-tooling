"""The examples reproduce: the fictional trial regenerates byte for byte, the
comparison examples follow the comparison model and show the shapes they claim,
and the preview script writes every report."""
from __future__ import annotations

import csv
import hashlib
import json
import unittest

from visual_harness import EXAMPLES, REPORT, Scratch, run_python

COMPARISONS = EXAMPLES / "comparisons"
PREVIEWS = sorted([
    "fictional-trial-bare.html", "fictional-trial.html", "showcase.html",
    "comparison-sandwich.html", "comparison-research-directions.html", "comparison-ad-campaign.html",
    "comparison-game-design.html", "comparison-commute.html",
])
COMPARISON_NAMES = ["sandwich", "research-directions", "ad-campaign", "game-design"]
KINDS = {"binary", "numeric", "ordinal", "count", "rank", "preference"}


def load(name: str) -> dict:
    return json.loads((COMPARISONS / name).read_text(encoding="utf-8"))


def check_model(test: unittest.TestCase, data: dict) -> None:
    """Every reference in a comparison points at something it defines, and every value fits its metric's kind."""
    alts = [a["id"] for a in data["alternatives"]]
    cases = [c["id"] for c in data.get("cases", [])]
    metrics = {m["id"]: m for m in data["metrics"]}
    for ids in (alts, cases, list(metrics)):
        test.assertEqual(len(ids), len(set(ids)), "ids repeat")
    test.assertTrue(all(m["kind"] in KINDS for m in metrics.values()))
    test.assertLessEqual(sum(1 for m in metrics.values() if m.get("primary")), 1)
    for m in metrics.values():
        if m["kind"] == "ordinal":
            test.assertTrue(m.get("levels"), f"ordinal metric {m['id']} needs levels")
    if data.get("baseline"):
        test.assertIn(data["baseline"], alts)
    for group in data.get("identical", []):
        test.assertTrue(set(group) <= set(alts) and len(group) > 1)
    for row in [*data.get("observations", []), *data.get("aggregates", [])]:
        test.assertIn(row["alternative"], alts)
        test.assertIn(row["metric"], metrics)
        if "case" in row:
            test.assertIn(row["case"], cases)
    for row in data.get("observations", []):
        kind, value = metrics[row["metric"]]["kind"], row["value"]
        if row.get("valid") is False:
            test.assertIsNone(value)
            test.assertTrue(row.get("invalid_reason"), "an invalid observation says why")
        elif kind == "binary":
            test.assertIsInstance(value, bool)
        elif kind == "numeric":
            test.assertTrue(isinstance(value, (int, float)) and not isinstance(value, bool))
        elif kind == "ordinal":
            test.assertIn(value, metrics[row["metric"]]["levels"])
    for row in data.get("aggregates", []):
        kind = metrics[row["metric"]]["kind"]
        if kind in ("binary", "count"):
            test.assertTrue(0 <= row["k"] <= row["n"])
        elif kind == "numeric":
            test.assertTrue({"mean", "sd", "n"} <= set(row))
    for row in data.get("preferences", []):
        test.assertTrue({row["a"], row["b"]} <= set(alts))
        test.assertTrue(row["winner"] is None or row["winner"] == "tie" or row["winner"] in (row["a"], row["b"]))
        test.assertEqual(metrics[row["metric"]]["kind"], "preference")
    for row in data.get("rankings", []):
        test.assertEqual(sorted(row["order"]), sorted(alts))
        test.assertEqual(metrics[row["metric"]]["kind"], "rank")


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

    def test_fictional_trial_shows_what_was_compared(self) -> None:
        """The arms carry the instruction texts their digests name, the two copies of the
        current guidance share one text, and each case says what it is and what passes."""
        data = json.loads((EXAMPLES / "fictional-trial.json").read_text(encoding="utf-8"))
        arms = data["plan"]["arms"]
        for name, arm in arms.items():
            with self.subTest(arm=name):
                self.assertIsInstance(arm.get("instructions_text"), str)
                self.assertEqual(arm["instructions_sha256"], hashlib.sha256(arm["instructions_text"].encode("utf-8")).hexdigest())
                self.assertIs(arm.get("instructions_truncated"), False)
        self.assertEqual(arms["current"]["instructions_text"], arms["current-copy"]["instructions_text"])
        self.assertEqual(len({arm["instructions_sha256"] for arm in arms.values()}), 3)
        for scenario in data["plan"]["scenarios"]:
            with self.subTest(case=scenario["name"]):
                self.assertTrue(scenario.get("description"))
                self.assertTrue(scenario["judge"].get("question"))
                self.assertTrue(scenario["judge"].get("pass_when"))

    def test_examples_parse(self) -> None:
        for name in ("fictional-narrative.json", "showcase-spec.json"):
            with self.subTest(file=name):
                json.loads((EXAMPLES / name).read_text(encoding="utf-8"))

    def test_comparison_examples_follow_the_model(self) -> None:
        self.assertEqual(sorted(p.name for p in COMPARISONS.iterdir() if p.suffix == ".json" and not p.stem.endswith("-narrative")), sorted(f"{n}.json" for n in COMPARISON_NAMES))
        for name in COMPARISON_NAMES:
            with self.subTest(example=name):
                data = load(f"{name}.json")
                check_model(self, data)
                self.assertTrue(data.get("decision_rule"), "the rule fixed before results is quoted")
                narrative = load(f"{name}-narrative.json")
                self.assertTrue(narrative["decision"]["headline"])

    def test_sandwich_is_small_and_shows_what_is_missing(self) -> None:
        data = load("sandwich.json")
        self.assertEqual(len(data["alternatives"]), 2)
        self.assertLess(len(data["observations"]), 20)
        self.assertTrue(any(o.get("valid") is False for o in data["observations"]), "an observation with no valid value")
        self.assertTrue(any(p["winner"] is None for p in data["preferences"]), "a head-to-head left undecided")
        self.assertEqual({m["better"] for m in data["metrics"] if m["kind"] == "ordinal"}, {"higher", "lower"})

    def test_research_directions_nest_alternatives_and_carry_a_noise_reference(self) -> None:
        data = load("research-directions.json")
        paths = [a["group"] for a in data["alternatives"] if a.get("group")]
        self.assertEqual({path[0] for path in paths}, {"Mine records", "Ask people", "Simulate"})
        self.assertTrue(any(len(path) == 2 for path in paths), "one direction has sub-groups")
        self.assertEqual(data["identical"], [["a1", "a1r"]])
        self.assertEqual({m["kind"] for m in data["metrics"]}, {"binary", "numeric", "ordinal"})
        self.assertGreaterEqual(len(data["cases"]), 5)
        runs = {(o["alternative"], o["case"]) for o in data["observations"]}
        self.assertLess(len(runs), len(data["alternatives"]) * len(data["cases"]), "a cell that was not run stays missing")
        self.assertEqual(data["alternatives"][0]["content"], data["alternatives"][1]["content"], "identical copies carry identical text")

    def test_ad_campaign_has_totals_only(self) -> None:
        data = load("ad-campaign.json")
        self.assertFalse(data.get("observations"))
        self.assertEqual({m["kind"] for m in data["metrics"]}, {"count", "numeric"})
        self.assertTrue(data.get("baseline") and any("threshold" in m for m in data["metrics"]))
        self.assertTrue(any("lo" in a for a in data["aggregates"]), "an interval the source reported")
        cells = {(a["alternative"], a["case"]) for a in data["aggregates"]}
        self.assertLess(len(cells), len(data["alternatives"]) * len(data["cases"]), "a cell that was not shown stays missing")

    def test_game_design_mixes_ratings_choices_rankings_and_words(self) -> None:
        data = load("game-design.json")
        self.assertEqual({m["kind"] for m in data["metrics"]}, {"ordinal", "numeric", "preference", "rank"})
        self.assertTrue(data["preferences"] and data["rankings"])
        self.assertTrue(any(o.get("excerpt") for o in data["observations"]), "qualitative excerpts")
        self.assertTrue(any(o.get("valid") is False for o in data["observations"]))

    def test_commute_csv_is_long_and_readable(self) -> None:
        with (COMPARISONS / "commute.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreater(len(rows), 60)
        self.assertEqual(list(rows[0]), ["alternative", "metric", "value", "case", "group", "unit", "n", "valid", "note", "source", "invalid_reason"])
        for row in rows:
            self.assertTrue(row["alternative"] and row["metric"])
            self.assertTrue(row["value"] != "" or row["valid"] == "false", "an empty value is marked invalid")
        self.assertTrue(any(row["n"] for row in rows), "a count carries its trials")

    def test_report_check_accepts_every_comparison_example(self) -> None:
        inputs = [["--data", COMPARISONS / f"{n}.json", "--narrative", COMPARISONS / f"{n}-narrative.json"] for n in COMPARISON_NAMES] + [["--csv", COMPARISONS / "commute.csv"]]
        for args in inputs:
            with self.subTest(example=args[1].name):
                result = run_python(REPORT, "--check", *args)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("error:", result.stdout + result.stderr)

    def test_assemble_previews_writes_every_report(self) -> None:
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
            self.assertEqual(again.stdout.count("unchanged "), len(PREVIEWS), again.stdout)


if __name__ == "__main__":
    unittest.main()
