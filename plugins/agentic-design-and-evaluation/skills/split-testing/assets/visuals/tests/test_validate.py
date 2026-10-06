"""Input validation: the page's checker (src/validate.ts, run from the built
bundle by validate.cjs) and report.py's checker find the same problems in the
same inputs, and the page draws them in a visible, escaped panel."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

from visual_harness import EXAMPLES, REPORT, TESTS, NodeCases, Scratch, run_node, write_hostile_fixtures


def load_report_module():
    """report.py as a module, without leaving bytecode beside it."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("av_report_under_test", REPORT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


R = load_report_module()

# Values of every JSON type, plus near misses: wrong case, numbers in quotes,
# out-of-range counts and rates, empty text, and a k/n pair with k above n.
CANDIDATES = ["", "  ", "zz", "Adopt", "true", "12", "label-a-foto", "curent", 3, 2.5, -1, 0.5, 1e21, True, None, [], ["zz"], [1, 2, 3], {}, {"zz": 1}, {"k": 12, "n": 5}]


def probes(field, depth: int = 0) -> list:
    """Every candidate for a field, and for compound fields one candidate placed
    at each inner position, so nested field tables are compared too."""
    out = list(CANDIDATES)
    if depth > 4 or not isinstance(field, dict):
        return out
    if "list" in field:
        out += [[v] for v in probes(field["list"], depth + 1)]
    elif "record" in field:
        out += [{"label-a-foto": v} for v in probes(field["record"], depth + 1)] + [{"$note": 1}]
    elif "oneOf" in field:
        for alternative in field["oneOf"]:
            out += probes(alternative, depth + 1)
    elif "fields" in field:
        for name, sub in field["fields"].items():
            out += [{name: v} for v in probes(sub, depth + 1)]
        out += [{"zqxwv": 1}, {"titel": 1}, {"$note": 1}, {name: "x" for name in field.get("required", [])}]
    return out


def unique(values: list) -> list:
    seen, out = set(), []
    for v in values:
        key = json.dumps(v, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def generated_corpus() -> list[dict]:
    """Entries name their trial: None, or a key of the corpus's trials."""
    corpus: list[dict] = [{"kind": "types"}]
    for context in (None, "fictional"):
        for kind, schema in R.BLOCKS.items():
            blocks = [{"type": kind}, {"type": kind, "zqxwv": 1}]
            for name, field in schema["fields"].items():
                blocks += [{"type": kind, name: v} for v in unique(probes(field))]
            for block in blocks:
                corpus.append({"kind": "spec", "input": {"title": "T", "sections": [{"title": "S", "blocks": [block]}]}, "trial": context})
        for name, field in R.SPEC["fields"].items():
            for v in unique(probes(field)):
                corpus.append({"kind": "spec", "input": {"title": "T", "sections": [], name: v}, "trial": context})
        for name, field in R.NARRATIVE["fields"].items():
            for v in unique(probes(field)):
                corpus.append({"kind": "narrative", "input": {name: v}, "trial": context})
    return corpus


def written_corpus() -> list[dict]:
    """The cross-field rules, one input each."""
    trial = "fictional"
    n = lambda value, context=trial: {"kind": "narrative", "input": value, "trial": context}  # noqa: E731
    s = lambda blocks, context=None, **extra: {"kind": "spec", "input": {"title": "T", "sections": [{"title": "S", "blocks": blocks}], **extra}, "trial": context}  # noqa: E731
    return [
        n({"include": ["verdict", "plan", "pairwyse", "nothing-like-it"], "exclude": ["setup"]}),
        n({"exclude": ["arms"], "sections": [{"title": "A", "after": "arms", "blocks": []}, {"title": "B", "id": "b", "after": "verdit", "blocks": []}, {"title": "C", "after": "b", "blocks": []}, {"title": "D", "after": "A", "blocks": []}, {"title": "E", "after": "plan", "blocks": []}]}),
        n({"include": ["verdict"], "append": {"verdict": [], "cases": [{"type": "text", "text": "x"}], "pairwyse": [], "plan": [], "zz top": []}}),
        n({"identical": [["current"], ["current", "current-copy"], ["current-copy", "checklist", "checklist"], "zz", [3]]}),
        n({"identical": [["current", "checklist", "worked-example"], [3, "current-copy", "nope", "current"]]}),
        n({"pairs": [["label-a-photo"], ["label-a-photo", "label-a-photo"], {"base": "summarize-minutes", "variant": "summarize-minutes"}, ["label-a-photo", "explain-a-chart", "x"], {"base": "nope"}]}),
        n({"arms": [{"id": "current"}, {"id": "current"}, {"label": "no id"}, "current"]}),
        n({"arms": {"current": {"label": "C"}, "curent": {"label": "C"}, "checklist": "Checklist"}}),
        n({"decision": {"verdict": "none", "headline": "  ", "rule": "mine", "checks": [{"label": "", "observed": "x", "met": "yes"}]}}),
        n({"sections": [{"id": "9 bad id", "title": "T", "blocks": [{"type": "ledger"}, {"type": "verdit"}, {"type": "Ladder"}, {}]}]}),
        n({"title": "T"}, None),
        n({"baseline": "nope", "groups": [{"label": "G", "cases": ["nope", "label-a-photo"]}]}),
        n({"threshold": 15, "append": {"grid": [{"type": "text", "text": "x"}]}, "sections": [{"title": "A", "after": "grid", "blocks": []}]}),
        n({"threshold": {"value": -1.5, "label": "bar"}, "include": ["grid"], "append": {"grid": []}}),
        n({"threshold": 0.15, "exclude": ["grid"], "append": {"grid": []}}),
        s([{"type": "setup", "settings": {"a": {"model": "m"}}}, {"type": "setup"}, {"type": "checks", "required": "no"}]),
        s([{"type": "ladder", "rows": [{"arm": "a", "k": 3, "n": 4}], "baseline": "b"}]),
        s([{"type": "ladder", "rows": [{"arm": "current", "k": 3, "n": 4}], "baseline": "checklist"}], trial),
        s([{"type": "ladder", "baseline": "curent"}], trial),
        s([{"type": "ladder", "baseline": "nope", "case": "nope", "cases": ["label-a-photo", "zz"], "identical": [["current", "zz"]]}], trial),
        s([{"type": "table", "columns": ["a", "b"], "rows": [["1", "2", "3"], ["1"], "row", [{"value": 1, "status": "passed"}]]}]),
        s([{"type": "matrix", "columns": [{"id": "c1"}], "rows": [{"id": "r1", "label": "R"}], "cells": [{"row": "r1", "column": "c2"}, {"row": "r2", "column": "c1"}, {"row": "R1", "column": "C1"}]}]),
        s([{"type": "bars", "segments": [{"id": "s1", "label": "S"}], "rows": [{"label": "x", "values": {"s1": 1, "s2": 2, "S1": 3}}]}]),
        s([{"type": "trend", "stages": ["r1", "r2"], "series": [{"label": "x", "points": [{"stage": "r3", "value": 0.5}, {"stage": "R1", "k": 9, "n": 3}]}]}]),
        s([{"type": "intervals", "rows": [], "domain": [1, 0]}, {"type": "intervals", "rows": [], "domain": [0]}, {"type": "intervals", "rows": [], "domain": [0, 1]}]),
        s([{"type": "checks", "checks": ["reply_written", "reply_writen"]}, {"type": "pairwise", "pair": "zz"}, {"type": "cost", "measures": ["seconds", "tokens"]}], trial),
        s([{"type": "cost", "measures": ["output_token"]}]),
        s([{"type": "text", "text": "x"}], None, trial={"runs": "no"}),
        s([{"type": "tapestry"}], trial, trial={"runs": []}),
        s([{"type": "text", "text": "x"}], None, arms=[{"id": "a"}, {"id": "a"}], meta=[{"label": "L"}], cases={"zz": "Z"}),
        {"kind": "spec", "input": {"title": "T", "sections": [{"id": "a", "title": "A", "blocks": []}, {"id": "a", "title": "B", "blocks": []}, {"id": "1", "title": "C", "blocks": []}, None, {"title": "D", "blocks": {}}]}, "trial": None},
        {"kind": "spec", "input": {"title": "T", "sections": [], "problems": [{"level": "error", "where": "narrative.x", "message": "m", "hint": "h"}, {"level": "fatal", "where": "w", "message": "m"}, {"where": 3}, None]}, "trial": None},
        {"kind": "spec", "input": {"sections": "none"}, "trial": None},
        {"kind": "spec", "input": ["not", "a", "spec"], "trial": None},
        {"kind": "narrative", "input": "not a narrative", "trial": trial},
    ]


class ValidateCasesTest(NodeCases):
    """The page's checker and its panel, against the built bundle."""

    script = "validate.cjs"
    minimum = 18

    def test_validation_and_problem_panel(self) -> None:
        self.run_script_cases()


class CheckerAgreementTest(unittest.TestCase):
    """report.py --check and the page list the same problems for the same inputs."""

    def compare(self, corpus: list[dict], trials: dict) -> None:
        with Scratch() as directory:
            path = directory / "corpus.json"
            path.write_text(json.dumps({"trials": trials, "entries": corpus}), encoding="utf-8")
            result = run_node(TESTS / "validate.cjs", "--corpus", path, "--out", directory / "page.json", timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            page = json.loads((directory / "page.json").read_text(encoding="utf-8"))
        self.assertEqual(len(page), len(corpus))
        differ = []
        for entry, theirs in zip(corpus, page):
            trial = trials[entry["trial"]] if entry.get("trial") is not None else None
            if entry["kind"] == "types":
                ours = R.BLOCK_TYPES
            elif entry["kind"] == "spec":
                ours = R.validate_spec(entry["input"], trial)
            else:
                ours = R.validate_narrative(entry["input"], trial)
            if ours != theirs:
                differ.append(f"input {json.dumps(entry.get('input'))[:300]} (trial: {entry.get('trial') is not None})\n  report.py: {json.dumps(ours)[:800]}\n  page:      {json.dumps(theirs)[:800]}")
        self.assertFalse(differ, f"{len(differ)} of {len(corpus)} inputs differ; the first:\n" + "\n".join(differ[:5]))

    @classmethod
    def setUpClass(cls) -> None:
        cls.trials = {"fictional": json.loads((EXAMPLES / "fictional-trial.json").read_text(encoding="utf-8"))}

    def test_block_types_match_the_registry(self) -> None:
        self.compare([{"kind": "types"}], {})

    def test_every_field_table_and_rule_agrees(self) -> None:
        corpus = generated_corpus() + written_corpus()
        self.assertGreater(len(corpus), 2000)
        self.compare(corpus, self.trials)

    def test_examples_and_hostile_documents_agree(self) -> None:
        with Scratch() as directory:
            paths = write_hostile_fixtures(directory)
            hostile = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}
        narrative = json.loads((EXAMPLES / "fictional-narrative.json").read_text(encoding="utf-8"))
        showcase = json.loads((EXAMPLES / "showcase-spec.json").read_text(encoding="utf-8"))
        corpus = [
            {"kind": "narrative", "input": narrative, "trial": "fictional"},
            {"kind": "spec", "input": showcase, "trial": None},
            {"kind": "narrative", "input": hostile["narrative"], "trial": "hostile"},
            {"kind": "narrative", "input": hostile["narrative"], "trial": None},
            {"kind": "spec", "input": hostile["spec"], "trial": "hostile"},
            {"kind": "spec", "input": hostile["spec"], "trial": None},
        ]
        self.compare(corpus, {**self.trials, "hostile": hostile["trial"]})
        self.assertEqual(R.validate_narrative(narrative, self.trials["fictional"]), [], "the fictional narrative has problems")
        self.assertEqual(R.validate_spec(showcase), [], "the showcase specification has problems")


if __name__ == "__main__":
    unittest.main()
