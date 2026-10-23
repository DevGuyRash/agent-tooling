"""Input validation: the page's checker (src/validate.ts, run from the built
bundle by validate.cjs and engine.cjs) and report.py's checker find the same
problems in the same inputs, trial and comparison alike, and the page draws
them in a visible, escaped panel."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

from visual_harness import EXAMPLES, NODE, REPORT, TESTS, NodeCases, Scratch, run_node, run_python, story_for, told, write_hostile_fixtures


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
        # Runs naming no scenario (left out, null, empty, only spaces) are refused; the context trial, its narrative too.
        s([{"type": "text", "text": "x"}], None, trial={"runs": [{"arm": "a", "scenario": "c1"}, {"arm": "a"}, {"arm": "a", "scenario": None}, {"arm": "a", "scenario": ""}, {"arm": "a", "scenario": "   "}, "not a run"]}),
        n({}, "blank"),
        s([{"type": "ladder", "rows": [{"label": "x", "k": "\u00a03", "n": 4}], "threshold": "\ufeff0.5"}]),
        # The same trial borrowed beside a specification, and a filter on an empty or blank case.
        s([{"type": "ladder"}], "blank"),
        # Two names for one section's reading, the second empty: refused, naming both keys.
        n({"readings": {"setup": "Read.", "plan": ""}}), n({"readings": {"plan": "Read.", "setup": "Read too."}}),
        # The bad trial of the entry-path matrix: embedded, supplied beside, and a narrative's.
        s([], None, trial=BAD_TRIAL), s([], "bad"), n({}, "bad"),
        s([{"type": "text", "text": "x"}], None, arms=[{"id": "a"}, {"id": "a"}], meta=[{"label": "L"}], cases={"zz": "Z"}),
        {"kind": "spec", "input": {"title": "T", "sections": [{"id": "a", "title": "A", "blocks": []}, {"id": "a", "title": "B", "blocks": []}, {"id": "1", "title": "C", "blocks": []}, None, {"title": "D", "blocks": {}}]}, "trial": None},
        {"kind": "spec", "input": {"title": "T", "sections": [], "problems": [{"level": "error", "where": "narrative.x", "message": "m", "hint": "h"}, {"level": "fatal", "where": "w", "message": "m"}, {"where": 3}, None]}, "trial": None},
        {"kind": "spec", "input": {"sections": "none"}, "trial": None},
        # A block's own comparison: its alternatives and cases need the story's descriptions, and an empty part says nothing.
        {"kind": "spec", "input": {"title": "Lunch", "story": {"background": [], "intent": "i", "questions": ["", "q"], "covers": "c", "notCovered": [" "], "alternatives": {"pbj": "P"}}, "sections": [{"title": "T", "reading": "r", "blocks": [{"type": "metric", "metric": "taste", "data": {"alternatives": [{"id": "pbj"}, {"id": "ham"}], "cases": [{"id": "hungry"}], "metrics": [{"id": "taste", "kind": "numeric"}], "observations": [{"alternative": "pbj", "case": "hungry", "metric": "taste", "value": 8}]}}]}]}, "trial": None},
        {"kind": "spec", "input": ["not", "a", "spec"], "trial": None},
        {"kind": "narrative", "input": "not a narrative", "trial": trial},
    ]


# The entry-path matrix's bad inputs: each has problems of its own, which must be found alike however it enters.
BAD_TRIAL = {"runs": [{"job": "j1", "arm": "a", "scenario": "c1", "repeat": 1, "passed": True, "valid": True}, {"job": "j2", "arm": "a", "scenario": "", "repeat": 2, "passed": True, "valid": True}, {"job": "j3", "arm": "a", "scenario": 0, "repeat": 3, "passed": True, "valid": True}]}
BAD_COMPARISON = {"alternatives": [{"id": "x"}], "metrics": [{"id": "m", "kind": "weird"}], "observations": [{"alternative": "zz", "metric": "m", "value": 1, "case": 3}]}
BAD_COLLECTION = {"members": [{"id": "one", "trial": {"runs": [{"arm": "a", "scenario": "c1", "passed": True}]}}]}

# A comparison with a metric of every kind, the context for comparison probes.
BASE = {
    "alternatives": [{"id": "pb", "group": ["Savory", "Nutty"]}, {"id": "jelly", "group": "Sweet"}, {"id": "honey"}],
    "cases": [{"id": "lunch"}, {"id": "snack"}],
    "metrics": [
        {"id": "ate", "kind": "binary"}, {"id": "minutes", "kind": "numeric"}, {"id": "taste", "kind": "ordinal", "levels": ["meh", "good", "great"]},
        {"id": "bites", "kind": "count"}, {"id": "place", "kind": "rank"}, {"id": "pick", "kind": "preference"},
    ],
    "observations": [{"alternative": "pb", "metric": "ate", "value": True}, {"alternative": "jelly", "metric": "minutes", "value": 3}, {"alternative": "pb", "metric": "taste", "value": "great"}, {"alternative": "pb", "metric": "bites", "value": 3, "n": 9}],
    "rankings": [{"order": ["pb", "jelly"]}],
}
COMPARISONS = {"base": BASE, "bad": BAD_COMPARISON}


def comparison_corpus() -> list[dict]:
    """Field probes for a comparison, its narrative and the comparison blocks, then the cross-field rules."""
    corpus: list[dict] = [{"kind": "comparison", "input": v} for v in ("x", [], None, {})]
    for name, field in R.COMPARISON["fields"].items():
        for v in unique(probes(field)):
            corpus.append({"kind": "comparison", "input": {"alternatives": [], "metrics": [], name: v}})
            corpus.append({"kind": "comparison", "input": {**BASE, name: v}})
    for name, field in R.COMPARISON_NARRATIVE["fields"].items():
        for v in unique(probes(field)):
            corpus.append({"kind": "comparison", "input": BASE, "narrative": {name: v}})
    for kind in ("scorecard", "metric", "difference", "hierarchy", "alternatives", "preferences", "decision-matrix", "observations"):
        for name, field in R.BLOCKS[kind]["fields"].items():
            for v in unique(probes(field)):
                corpus.append({"kind": "spec", "input": {"title": "T", "sections": [{"title": "S", "blocks": [{"type": kind, name: v}]}]}, "comparison": "base"})
    # Numbers written as text, padded with a no-break space, an em space, a byte-order mark or a next-line: numeric to both checkers.
    corpus += [
        {"kind": "comparison", "input": {"alternatives": [{"id": "x"}], "metrics": [{"id": "m", "kind": "ordinal"}], "observations": [{"alternative": "x", "metric": "m", "value": v} for v in ("\u00a03", "4\u2003", "\ufeff5", "\u00856\u00a0")]}},
        {"kind": "comparison", "input": {"alternatives": [{"id": "x"}], "metrics": [{"id": "m", "kind": "ordinal"}], "aggregates": [{"alternative": "x", "metric": "m", "counts": {"\u00a03": 2, "4\ufeff": 1}}]}},
        {"kind": "comparison", "input": {"alternatives": [{"id": "x"}], "metrics": [{"id": "m", "kind": "numeric"}], "observations": [{"alternative": "x", "metric": "m", "value": "\u20033"}]}},
    ]
    o = lambda metric, value, **extra: {"alternative": "pb", "metric": metric, "value": value, **extra}  # noqa: E731
    written = [
        {**BASE, "alternatives": [*BASE["alternatives"], {"id": "pb"}], "metrics": [*BASE["metrics"], {"id": "ate", "kind": "numeric", "primary": True}, {"id": "x", "kind": "ordinal", "primary": True, "levels": ["a", "a"]}]},
        {**BASE, "observations": [o("ate", "yes"), o("ate", 2), o("ate", 1.0), o("minutes", "3"), o("minutes", "three"), o("taste", "superb"), o("taste", 2), o("taste", 7), o("bites", 4), o("bites", 9, n=4), o("bites", 1.5, n=4), o("place", 0), o("pick", True), o("ate", True, n=3), o("ate", None), o("ate", "x", valid=False), o("minutes", "")]},
        {**BASE, "metrics": [*BASE["metrics"], {"id": "loose", "kind": "ordinal"}, {"id": "nums", "kind": "ordinal"}, {"id": "empty", "kind": "numeric"}, {"id": "cap", "kind": "binary", "threshold": 1.5, "levels": ["x"]}], "observations": [o("loose", "fine"), o("nums", 3), o("nums", "4")], "aggregates": [{"alternative": "pb", "metric": "loose", "counts": {"ok": 1}}]},
        {**BASE, "aggregates": [{"alternative": "pb", "metric": "ate", "k": 5, "n": 3}, {"alternative": "pb", "metric": "minutes", "lo": 4, "hi": 2}, {"alternative": "pb", "metric": "taste", "counts": {"great": 2, "superb": 1}}, {"alternative": "pb", "metric": "taste"}, {"alternative": "pb", "metric": "bites", "k": 2}, {"alternative": "pb", "metric": "place", "sd": 1}, {"alternative": "pb", "metric": "pick", "k": 1, "n": 2}]},
        {**BASE, "preferences": [{"a": "pb", "b": "pb", "winner": "pb"}, {"a": "pb", "b": "jelly", "winner": "honey"}, {"a": "pb", "b": "jelly", "winner": 3}, {"a": "pb", "b": "jelly", "winner": None, "metric": "ate"}, {"a": "pb", "b": "jelly", "winner": "tie"}, {"a": 4, "b": "jelly", "winner": 4}], "rankings": [{"order": ["pb", "pb", "jelly"], "metric": "minutes"}, {"order": ["pb"]}, {"order": [1, 1]}]},
        {**BASE, "metrics": [*BASE["metrics"], {"id": "pick2", "kind": "preference"}], "preferences": [{"a": "pb", "b": "jelly", "winner": "pb"}], "identical": [["pb"], ["pb", "jelly"], ["pb", "pb"]], "baseline": "jely"},
        {**BASE, "metrics": [*BASE["metrics"], {"id": "pick2", "kind": "preference", "primary": True}], "preferences": [{"a": "pb", "b": "jelly", "winner": "pb"}], "cases": [], "observations": [o("ate", True, case="dinner")]},
        {**BASE, "observations": [o("ate", True, case="dinner"), {"alternative": "zz", "metric": "nope", "value": 1}], "kind": "x"},
        # A filter on an empty or blank case selects the evidence naming no case.
        {**BASE, "observations": [o("ate", True, case=""), o("ate", False, case="lunch")]},
        # Every form of an unnamed case, with cases declared and without.
        {**BASE, "cases": [{"id": "c1"}], "observations": [o("ate", True, case="c1"), o("ate", True, case=""), o("ate", True, case="   "), o("ate", True, case=None), o("ate", True)]},
        {**BASE, "observations": [o("ate", True, case=""), o("ate", True, case="   ")]},
    ]
    corpus += [{"kind": "comparison", "input": c} for c in written]
    narratives = [
        {"include": ["verdict", "metrics", "resuts", "nothing-like-it"], "exclude": ["groups"]},
        {"exclude": ["results"], "sections": [{"title": "A", "after": "results", "blocks": []}, {"title": "B", "id": "b", "after": "verdit", "blocks": []}, {"title": "C", "after": "b", "blocks": []}, {"title": "E", "after": "ledger", "blocks": []}]},
        {"include": ["verdict"], "append": {"verdict": [], "cases": [{"type": "text", "text": "x"}], "judgements": [], "runs": [], "zz top": []}},
        {"alternatives": [{"id": "pb"}, {"id": "pb"}, {"id": "pbb"}, {"label": "no id"}], "baseline": "honney", "identical": [["pb"], ["pb", "jelly"]]},
        {"alternatives": {"pb": {"label": "PB"}, "jely": {"label": "J"}}, "decision": {"verdict": "Adopt", "headline": " ", "rule": "mine"}},
        {"criteria": [{"label": "a"}, {"label": "b", "metric": "tast", "weight": -1}, {"label": "c", "scores": {"pb": 1, "zz": 2}, "weight": 2}, {"label": "d", "metric": None}, {"id": "e"}, {"id": "f", "better": "none"}], "cells": [{"criterion": "e", "alternative": "pb", "rating": 3}, {"criterion": "q", "alternative": "zz"}, {"alternative": "pb"}], "scale": {"min": 1, "max": "5", "levels": ["lo", 2]}},
        "not a narrative",
    ]
    corpus += [{"kind": "comparison", "input": BASE, "narrative": n} for n in narratives]
    # Cases the data name without declaring them, and every condition a composed section is drawn under.
    uv = {"alternatives": [{"id": "x"}, {"id": "y"}], "metrics": [{"id": "m", "kind": "numeric"}],
          "observations": [{"alternative": a, "case": c, "metric": "m", "value": v} for a, c, v in (("x", "u", 1), ("y", "u", 2), ("x", "v", 3), ("y", "v", 4))]}
    plain = {"story": {"background": "b", "intent": "i", "questions": ["q"], "rule": "r", "covers": "c", "notCovered": "n", "alternatives": {"x": "X.", "y": "Y."}}, "readings": {"compared": "c", "results": "r", "differences": "d", "observations": "o"}}
    picked = {"alternatives": [{"id": "x"}, {"id": "y"}, {"id": "z", "group": []}, {"id": "w", "group": [""]}], "metrics": [{"id": "pick", "kind": "preference"}, {"id": "odd", "kind": "unknown"}],
              "preferences": [{"a": "x", "b": "y", "winner": "x", "case": "u"}], "rankings": [{"order": "x", "case": "t"}, {"case": "s"}]}
    corpus += [
        {"kind": "comparison", "input": uv, "narrative": plain},
        {"kind": "comparison", "input": {**uv, "alternatives": [*uv["alternatives"], {"id": "z", "group": ""}]}, "narrative": {**plain, "identical": [["x", "y", "x"]]}},
        {"kind": "comparison", "input": {**uv, "alternatives": [*uv["alternatives"], {"id": "z"}], "identical": [["x", "zz"]]}, "narrative": plain},
        {"kind": "comparison", "input": picked, "narrative": plain},
        {"kind": "comparison", "input": {**picked, "rankings": [{"order": ["x", "y"], "case": "t"}]}, "narrative": {**plain, "criteria": ["x", {"label": "L"}]}},
        {"kind": "comparison", "input": uv, "narrative": {**plain, "sections": [{"title": "Own", "blocks": [{"type": "metric", "metric": "k", "data": {"alternatives": [{"id": "p"}], "metrics": [{"id": "k", "kind": "binary"}], "aggregates": [{"alternative": "p", "metric": "k", "k": 1, "n": 2, "case": "c9"}]}}]}],
                                                       "append": {"results": [{"type": "ladder", "rows": [{"arm": "hand", "case": "made", "k": 1, "n": 2}]}, {"type": "diagram", "source": "flowchart LR\n A --> B"}]}}},
        {"kind": "comparison", "input": uv, "narrative": {**plain, "story": {**plain["story"], "background": 0, "intent": None, "questions": [0, " "], "covers": False, "notCovered": {"x": 1}, "rule": 3}}},
    ]
    corpus += [
        {"kind": "spec", "input": {"title": "T", "sections": [], "comparison": BASE}, "comparison": None},
        {"kind": "spec", "input": {"title": "T", "sections": [], "comparison": {**BASE, "baseline": "zz"}}, "comparison": None},
        {"kind": "spec", "input": {"title": "T", "sections": [{"title": "S", "blocks": [{"type": "metric", "metric": "tast", "cases": ["lunch", "brunch"], "by": "segment"}, {"type": "hierarchy", "groups": ["Savory"]}]}], "comparison": {"rows": []}}, "comparison": "base"},
        {"kind": "spec", "input": {"title": "T", "sections": [{"title": "S", "blocks": [{"type": "difference", "baseline": "honey", "pairs": [["pb", "zz"]]}, {"type": "decision-matrix", "criteria": [{"metric": "ate"}]}]}]}, "comparison": None},
        {"kind": "spec", "input": {"title": "T", "sections": [{"title": "S", "blocks": [{"type": "metric", "metric": "own", "data": {"alternatives": [{"id": "x"}], "metrics": [{"id": "own", "kind": "numeric"}]}, "alternatives": ["x", "pb"]}, {"type": "scorecard", "data": {"rows": []}}, {"type": "difference", "pairs": "every", "identical": True, "threshold": None}]}]}, "comparison": None},
        {"kind": "spec", "input": {"title": "T", "sections": [{"title": "S", "blocks": [{"type": "metric", "metric": "own", "data": {"alternatives": [{"id": "x"}], "metrics": [{"id": "own", "kind": "numeric"}]}, "alternatives": ["x", "pb"]}]}]}, "comparison": "base"},
    ]
    # The bad comparison of the entry-path matrix, on every path a specification or a narrative gives it.
    view = lambda data: {"title": "T", "sections": [{"title": "S", "reading": "r", "blocks": [{"type": "metric", "metric": "m", "data": data}]}]}  # noqa: E731
    corpus += [
        {"kind": "spec", "input": {"title": "T", "sections": [], "comparison": BAD_COMPARISON}, "comparison": None},
        {"kind": "spec", "input": {"title": "T", "sections": []}, "comparison": "bad"},
        {"kind": "spec", "input": view(BAD_COMPARISON), "comparison": None},
        {"kind": "spec", "input": {**view(BAD_COMPARISON), "sections": [{"title": "S", "reading": "r", "blocks": [{"type": "scorecard", "data": {"rows": []}}, {"type": "decision-matrix", "data": "none"}]}]}, "comparison": None},
        {"kind": "comparison", "input": BAD_COMPARISON},
        {"kind": "comparison", "input": BASE, "narrative": {"readings": {"results": "Read.", "metrics": ""}}},
        {"kind": "comparison", "input": BASE, "narrative": {"readings": {"setup": "Read.", "alternatives": "Read too.", "compared": "And again."}}},
        {"kind": "comparison", "input": BASE, "narrative": {"sections": [{"title": "More", "blocks": [{"type": "metric", "metric": "m", "data": BAD_COMPARISON}]}], "append": {"results": [{"type": "scorecard", "data": BAD_COMPARISON}]}}},
    ]
    return corpus


class ComparisonAgreementTest(unittest.TestCase):
    """report.py and the page check comparisons, their narratives and the comparison blocks alike."""

    def test_every_comparison_field_and_rule_agrees(self) -> None:
        corpus = comparison_corpus()
        self.assertGreater(len(corpus), 1500)
        with Scratch() as directory:
            path = directory / "corpus.json"
            path.write_text(json.dumps({"comparisons": COMPARISONS, "entries": corpus}), encoding="utf-8")
            result = run_node(TESTS / "engine.cjs", "--corpus", path, "--out", directory / "page.json", timeout=300)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            page = json.loads((directory / "page.json").read_text(encoding="utf-8"))
        self.assertEqual(len(page), len(corpus))
        differ = []
        for entry, theirs in zip(corpus, page):
            if entry["kind"] == "comparison":
                ours = R.validate_comparison(entry["input"], entry["narrative"]) if "narrative" in entry else R.validate_comparison(entry["input"])
            else:
                ours = R.validate_spec(entry["input"], None, COMPARISONS[entry["comparison"]] if entry.get("comparison") else None)
            if ours != theirs:
                differ.append(f"input {json.dumps(entry)[:400]}\n  report.py: {json.dumps(ours)[:900]}\n  page:      {json.dumps(theirs)[:900]}")
        self.assertFalse(differ, f"{len(differ)} of {len(corpus)} inputs differ; the first:\n" + "\n".join(differ[:4]))
        written = [e for e in corpus if e["kind"] == "comparison" and e["input"] is not BASE and isinstance(e["input"], dict) and "zqxwv" not in json.dumps(e["input"])][-8:] + [e for e in corpus if e["kind"] == "comparison" and "narrative" in e][-7:]
        self.assertTrue(all(R.validate_comparison(e["input"], e.get("narrative", R.MISSING)) for e in written), "every written cross-field case finds a problem")
        self.assertEqual(R.validate_comparison(BASE), [], "the base comparison is clean")


# A small collection, the context for collection probes: two trial members and a comparison member.
TINY = {"runs": [{"job": "j1", "scenario": "c1", "arm": "a", "repeat": 1, "passed": True, "valid": True}]}
COLLECTION = {
    "story": story_for(),
    "readings": {s: "r" for s in ("glance", "reports", "shifts", "timeline", "matchups")},
    "themes": [{"id": "t1", "label": "T", "summary": "S"}],
    "members": [{"id": "m1", "theme": "t1", "trial": TINY, "narrative": told({}, TINY)}, {"id": "m2", "follows": "m1", "trial": TINY, "narrative": told({"title": "N"}, TINY)}, {"id": "m3", "comparison": BASE, "narrative": told({}, comparison=BASE)}],
}


UNTIMED = {s: "r" for s in ("glance", "reports", "shifts", "matchups")}
DATE_EDGES = (
    ("0099-01-01", "0099-01-02"), ("0001-01-01", "9999-12-31"), ("0000-01-01", "2026-01-01T10:00:60"),
    ("2026-01-01T23:30:00-08:00", "2026-01-02T00:15:00Z"), ("2026-01-01T10:00:30.123456+05:30", "2026-01-02 10:00Z"),
    ("2026-01-01Tgarbage", "2026-01-02 rubbish"), ("2026-01-01T24:00", "2026-01-01T10:60"), ("2026-01-01T10:00+24:00", "2026-01-01T10"),
    ("2026-01-01T10:00+0530", "2026-01-01T10:00z"), ("0001-01-01T00:30+01:00", "9999-12-31T23:30-01:00"),
    ("0001-01-01T00:30-01:00", "9999-12-31T23:30+01:00"), ("2026-01-01T10:00:30.", "2026-01-01T"), ("0099-01-02T09:00:00Z", "2024-02-28T20:00-08:00"),
)


def collection_corpus() -> list[dict]:
    """Field probes for a collection, its members and the collection blocks, then the cross-field rules."""
    corpus: list[dict] = [{"kind": "collection", "input": v} for v in ("x", [], None, {}, {"members": "x"})]
    for name, field in R.COLLECTION["fields"].items():
        for v in unique(probes(field)):
            corpus.append({"kind": "collection", "input": {**COLLECTION, name: v}})
    corpus.append({"kind": "collection", "input": {**COLLECTION, "members": [{"id": "m1", "trial": {**TINY, "runs": [*TINY["runs"], {**TINY["runs"][0], "scenario": " "}]}}, COLLECTION["members"][2]]}})
    for name, field in R.MEMBER["fields"].items():
        for v in unique(probes(field)):
            corpus.append({"kind": "collection", "input": {**COLLECTION, "members": [{"id": "m1", "trial": TINY, name: v}, COLLECTION["members"][2]]}})
    for kind in ("decisions", "reports", "shifts", "cost-gain", "timeline", "matchups", "report-compare"):
        for name, field in R.BLOCKS[kind]["fields"].items():
            for v in unique(probes(field)):
                block = {"type": kind, "a": "m1", "b": "m2", name: v} if kind == "report-compare" else {"type": kind, name: v}
                corpus.append({"kind": "spec", "input": {"title": "T", "sections": [{"title": "S", "blocks": [block]}]}, "collection": "base"})
    member = lambda **fields: {"id": "m9", "trial": TINY, **fields}  # noqa: E731
    written = [
        {"members": [member(), member(), member(id="m8", follows="m8"), member(id="m7", comparison=BASE), {"id": "m6"}, member(id="m5", trial={"runs": "x"}), {"id": "m4", "comparison": {"rows": []}}]},
        {"members": [member(date="2026-10-15"), member(id="m8", date="15 Oct"), member(id="m7", theme="nope", follows="m99")], "themes": [{"id": "t"}, {"id": "t"}, {"label": "no id"}], "pairs": [{"a": "m9", "b": "m9"}, {"a": "m9", "b": "m8x"}, {"a": "m9"}]},
        {"members": [member(date="2026-02-30"), member(id="m8", date="2026-13-01"), member(id="m7", date="2024-02-29"), {"id": "m6", "spec": {"title": "S", "sections": [{"title": "A", "blocks": [{"type": "verdit"}, {"type": "verdict", "headline": ""}]}]}, "narrative": {}},
                     {"id": "m5", "spec": {"sections": []}}, {"id": "m4", "spec": "x"}, {"id": "m3", "spec": {"title": "S", "sections": []}, "comparison": BASE, "trial": TINY}]},
        {"members": [member(narrative={"decision": {"verdict": "adpot", "headline": ""}, "arms": [{"id": "zz"}]}), {"id": "m8", "comparison": BASE, "narrative": {"baseline": "honney", "criteria": [{"label": "a"}]}}, {"id": "m7", "comparison": {**BASE, "baseline": "zz"}}, member(id="m6", narrative="not a narrative")]},
    ]
    # A specification member carrying a comparison draws the shifts section, which then needs its reading.
    written.append({**COLLECTION, "readings": {"glance": "g", "reports": "r"}, "members": [{"id": "m1", "spec": {"title": "S", "sections": [], "comparison": BASE}}, {"id": "m2", "spec": {"title": "S", "sections": [], "comparison": {**BASE, "metrics": []}}}]})
    corpus += [{"kind": "collection", "input": c} for c in written]
    s = lambda blocks, context="base": {"kind": "spec", "input": {"title": "T", "sections": [{"title": "S", "blocks": blocks}]}, "collection": context}  # noqa: E731
    corpus += [
        s([{"type": "report-compare", "a": "m1", "b": "m22"}, {"type": "reports", "members": ["m1", "mm1"], "themes": ["t2"], "layouts": ["cards", "grid"]}, {"type": "matchups", "pairs": [{"a": "m1", "b": "zz"}]}]),
        s([{"type": "decisions"}, {"type": "report-compare"}], None),
        {"kind": "spec", "input": {"title": "T", "sections": [{"title": "S", "blocks": [{"type": "timeline", "members": ["m1"]}]}], "collection": COLLECTION}, "collection": None},
        {"kind": "spec", "input": {"title": "T", "sections": [], "collection": {"members": [member(), member()]}}, "collection": None},
        # Member dates read by the one rule: padded with shared whitespace, or followed by a time, a date is used (and the
        # timeline's reading is required); anything else is unused and said to be.
        *[{"kind": "collection", "input": {**COLLECTION, "members": [{**COLLECTION["members"][0], "date": d1}, {**COLLECTION["members"][1], "date": d2}, COLLECTION["members"][2]]}}
          for d1, d2 in ((" 2026-01-01", "2026-01-02\u00a0"), ("\ufeff2026-01-01", "\t2026-01-02"), ("2026-01-01T09:30:00Z", "2026-01-02 10:00"), ("2026-02-30", "2026-01-02"), ("2026-01-011", "x 2026-01-02"))],
        # The rule's edges, as member dates and as a trial's run times, with no timeline reading so that the dates used show:
        # years below 100, offsets that move the day (past 0001 or 9999 too), and times that are not real times.
        *[{"kind": "collection", "input": {**COLLECTION, "readings": UNTIMED, "members": [{**COLLECTION["members"][0], "date": d1}, {**COLLECTION["members"][1], "date": d2}, COLLECTION["members"][2]]}}
          for d1, d2 in DATE_EDGES],
        *[{"kind": "collection", "input": {**COLLECTION, "readings": UNTIMED, "members": [{**COLLECTION["members"][0], "trial": {**TINY, "ran": {"first": d1}}}, {**COLLECTION["members"][1], "trial": {**TINY, "generated_at": d2}}, COLLECTION["members"][2]]}}
          for d1, d2 in DATE_EDGES],
        # The bad collection of the entry-path matrix, carried and supplied beside; and its trial and comparison as members.
        {"kind": "spec", "input": {"title": "T", "sections": [], "collection": BAD_COLLECTION}, "collection": None},
        {"kind": "spec", "input": {"title": "T", "sections": []}, "collection": "bad"},
        {"kind": "collection", "input": BAD_COLLECTION},
        {"kind": "collection", "input": {"members": [{"id": "t", "trial": BAD_TRIAL}, {"id": "c", "comparison": BAD_COMPARISON}, {"id": "s", "spec": {"title": "T", "sections": [], "trial": BAD_TRIAL, "comparison": BAD_COMPARISON}}]}},
    ]
    return corpus


class CollectionAgreementTest(unittest.TestCase):
    """report.py and the page check collections, their members' narratives and the collection blocks alike."""

    def test_every_collection_field_and_rule_agrees(self) -> None:
        corpus = collection_corpus()
        self.assertGreater(len(corpus), 400)
        with Scratch() as directory:
            path = directory / "corpus.json"
            path.write_text(json.dumps({"trials": {}, "collections": {"base": COLLECTION, "bad": BAD_COLLECTION}, "entries": corpus}), encoding="utf-8")
            result = run_node(TESTS / "validate.cjs", "--corpus", path, "--out", directory / "page.json", timeout=300)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            page = json.loads((directory / "page.json").read_text(encoding="utf-8"))
        self.assertEqual(len(page), len(corpus))
        differ = []
        for entry, theirs in zip(corpus, page):
            ours = R.validate_collection(entry["input"]) if entry["kind"] == "collection" else R.validate_spec(entry["input"], None, None, {"base": COLLECTION, "bad": BAD_COLLECTION}[entry["collection"]] if entry.get("collection") else None)
            if ours != theirs:
                differ.append(f"input {json.dumps(entry)[:400]}\n  report.py: {json.dumps(ours)[:900]}\n  page:      {json.dumps(theirs)[:900]}")
        self.assertFalse(differ, f"{len(differ)} of {len(corpus)} inputs differ; the first:\n" + "\n".join(differ[:4]))
        self.assertEqual(R.validate_collection(COLLECTION), [], "the base collection is clean")

    def test_each_cross_field_rule_names_its_one_defect(self) -> None:
        # The clean base collection, told in full, with one defect each: the problem the rule names, and nothing else.
        m1, m2, m3 = COLLECTION["members"]
        cases = {
            "a report that follows itself": ({**COLLECTION, "members": [m1, {**m2, "follows": "m2"}, m3]}, [("error", "collection.members[1].follows", "a report cannot follow itself")]),
            "a report that follows one not in the collection": ({**COLLECTION, "members": [m1, {**m2, "follows": "m99"}, m3]}, [("error", "collection.members[1].follows", '"m99" is not a report in this collection')]),
            "an id used twice": ({**COLLECTION, "members": [m1, m2, {**m3, "id": "m1"}]}, [("error", "collection.members[2].id", 'report id "m1" is already used by an earlier report')]),
            "an impossible date": ({**COLLECTION, "members": [{**m1, "date": "2026-02-30"}, m2, m3]}, [("warning", "collection.members[0].date", '"2026-02-30" is not a calendar day written YYYY-MM-DD, alone or with a time such as T09:30:00Z, so it is not used')]),
            "a theme the collection does not name": ({**COLLECTION, "members": [{**m1, "theme": "nope"}, m2, m3]}, [("warning", "collection.members[0].theme", '"nope" is not a theme in this collection')]),
            "a pair of one report with itself": ({**COLLECTION, "pairs": [{"a": "m1", "b": "m1"}]}, [("error", "collection.pairs[0]", "pairs a report with itself")]),
            "a member narrative's misspelled verdict": ({**COLLECTION, "members": [{**m1, "narrative": {**m1["narrative"], "decision": {"verdict": "adpot", "headline": "H."}}}, m2, m3]},
                                                       [("error", "collection.members[0].narrative.decision.verdict", '"adpot" is not one of the allowed values')]),
        }
        for name, (collection, expected) in cases.items():
            with self.subTest(case=name):
                self.assertEqual([(p["level"], p["where"], p["message"]) for p in R.validate_collection(collection)], expected)


class FromTrialAgreementTest(unittest.TestCase):
    """report.py --check --general checks a narrative against the comparison the page derives from a trial, so
    its conversion must be the page's: fromTrial and from_trial agree on trials of every kind of record."""

    def test_the_derived_comparison_agrees(self) -> None:
        if not NODE:
            self.skipTest("node is not on PATH")
        rich = {
            "name": "rich", "baseline": "a", "run_directory": "/home/someone/trials/rich",
            "plan": {"decision_rule": "Adopt b if it passes more.", "arms": {"a": {"executor": "codex", "model": "m", "codex_config": ["x=1"], "instructions_text": "Text.", "instructions_truncated": True}, "b": {"executor": "claude", "effort": 2.0}},
                     "scenarios": [{"name": "c1", "description": "First.", "required": ["ok"]}, {"name": "c2", "prompt": "p" * 450, "required": ["ok", "fast"]}]},
            "runs": [
                {"job": "c1__a__r1", "scenario": "c1", "arm": "a", "repeat": 1, "passed": True, "checks": {"ok": True, "fast": 2, "mixed": True, "note": "x"}, "usage": {"input_tokens": 10, "cache_read_input_tokens": 5, "output_tokens": 3, "cost_usd": 0.01}, "seconds": 4.5, "commands": 2, "judge": {"verdict": "pass", "reason": "Fine."}, "final_message_excerpt": "Done."},
                {"job": "c1__b__r1", "scenario": "c1", "arm": "b", "repeat": 1, "passed": False, "checks": {"ok": False, "fast": 3, "mixed": 1}, "usage": {"input_tokens": 12, "output_tokens": 4, "total_cost_usd": 0.02}, "seconds": 5, "judge": {"verdict": "fail"}},
                {"job": "c2__a__r1", "scenario": "c2", "arm": "a", "repeat": 1, "passed": None, "status": "timeout", "checks": {}},
                {"job": "c2__b__r1", "scenario": "c2", "arm": "b", "repeat": 1.5, "passed": True, "invalid_reason": None, "checks": {"ok": True}},
            ],
            "pairwise": {"a__b": {"arms": ["a", "b"], "judge": {"model": "j"}, "overall": {"a_wins": 1, "b_wins": 0, "tie": 0, "inconsistent": 0, "invalid": 0}, "scenarios": {"c1": {"a_wins": 1, "b_wins": 0, "tie": 1.0, "inconsistent": 1, "invalid": 0}}}},
        }
        with Scratch() as directory:
            hostile = write_hostile_fixtures(directory)["trial"]
            trials = {"rich": rich, "fictional": json.loads((EXAMPLES / "fictional-trial.json").read_text(encoding="utf-8")), "hostile": json.loads(hostile.read_text(encoding="utf-8"))}
            for name, trial in trials.items():
                with self.subTest(trial=name):
                    path = directory / f"{name}.json"
                    path.write_text(json.dumps(trial), encoding="utf-8")
                    script = "const H = require(process.argv[1]); const V = H.loadVisuals(); process.stdout.write(JSON.stringify(V.fromTrial(JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8')))));"
                    result = run_node("-e", script, TESTS / "harness.cjs", path)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(R.from_trial(json.loads(path.read_text(encoding="utf-8"))), json.loads(result.stdout))


def within(problems: list[dict], at: str) -> list[str]:
    """The problems found in an input entered at `at`, each placed within the input (as validate.cjs within)."""
    out = [f"{p['level']} {p['where'][len(at):].lstrip('.') or '(the input)'}: {p['message']}" for p in problems if p["where"] == at or p["where"].startswith(at + ".") or p["where"].startswith(at + "[")]
    return sorted(out)


class EntryPathMatrixTest(unittest.TestCase):
    """Each kind of data is checked by one function on every path it enters by: report.py's API and its command line
    find the same problems in the same bad input, wherever it enters, and the page's checker agrees (the corpora)."""

    def cli(self, *files: tuple[str, object]) -> list[dict]:
        with Scratch() as directory:
            args: list[object] = ["--check"]
            for flag, content in files:
                path = directory / f"{flag.strip('-')}.json"
                path.write_text(json.dumps(content), encoding="utf-8")
                args += [flag, path]
            result = run_python(REPORT, *args)
        found = []
        for line in result.stderr.splitlines():
            level, _, rest = line.partition(": ")
            if level in ("error", "warning"):
                where, _, message = rest.partition(": ")
                found.append({"level": level, "where": where, "message": message})
        return found

    def test_each_kind_is_checked_alike_on_every_path(self) -> None:
        bare = {"title": "T", "sections": []}
        view = {"title": "T", "sections": [{"title": "S", "reading": "r", "blocks": [{"type": "metric", "metric": "m", "data": BAD_COMPARISON}]}]}
        good_trial = json.loads((EXAMPLES / "fictional-trial.json").read_text(encoding="utf-8"))
        good_comparison = {"alternatives": [{"id": "x"}, {"id": "y"}], "metrics": [{"id": "m", "kind": "binary"}], "observations": [{"alternative": "x", "metric": "m", "value": True}]}
        bad_narrative = {"titel": "x", "decision": {"verdict": "adpot", "headline": "H."}}
        matrix = {
            "trial": [
                ("a specification's own", R.validate_spec({**bare, "trial": BAD_TRIAL}), "trial"),
                ("supplied beside a specification", R.validate_spec(bare, BAD_TRIAL), "trial"),
                ("a narrative's", R.validate_narrative({}, BAD_TRIAL), "trial"),
                ("a collection member's", R.validate_collection({"members": [{"id": "m", "trial": BAD_TRIAL}]}), "collection.members[0].trial"),
                ("a collection specification member's", R.validate_collection({"members": [{"id": "m", "spec": {**bare, "trial": BAD_TRIAL}}]}), "collection.members[0].spec.trial"),
                ("a member of a collection supplied beside", R.validate_spec(bare, None, None, {"members": [{"id": "m", "trial": BAD_TRIAL}]}), "collection.members[0].trial"),
                ("report.py --trial", self.cli(("--trial", BAD_TRIAL)), "trial"),
                ("report.py --spec --trial", self.cli(("--spec", bare), ("--trial", BAD_TRIAL)), "trial"),
            ],
            "comparison": [
                ("a specification's own", R.validate_spec({**bare, "comparison": BAD_COMPARISON}), "comparison"),
                ("supplied beside a specification", R.validate_spec(bare, None, BAD_COMPARISON), "comparison"),
                ("a view's own data", R.validate_spec(view), "sections[0].blocks[0] (metric).data"),
                ("checked alone", R.validate_comparison(BAD_COMPARISON), "comparison"),
                ("a collection member's", R.validate_collection({"members": [{"id": "m", "comparison": BAD_COMPARISON}]}), "collection.members[0].comparison"),
                ("a view a trial narrative adds", R.validate_narrative({"sections": [{"title": "More", "blocks": [{"type": "metric", "metric": "m", "data": BAD_COMPARISON}]}]}, good_trial), "narrative.sections[0].blocks[0] (metric).data"),
                ("report.py --data", self.cli(("--data", BAD_COMPARISON)), "comparison"),
                ("report.py --spec --data", self.cli(("--spec", bare), ("--data", BAD_COMPARISON)), "comparison"),
            ],
            "collection": [
                ("a specification's own", R.validate_spec({**bare, "collection": BAD_COLLECTION}), "collection"),
                ("supplied beside a specification", R.validate_spec(bare, None, None, BAD_COLLECTION), "collection"),
                ("checked alone", R.validate_collection(BAD_COLLECTION), "collection"),
                ("report.py --collection", self.cli(("--collection", BAD_COLLECTION)), "collection"),
                ("report.py --spec --collection", self.cli(("--spec", bare), ("--collection", BAD_COLLECTION)), "collection"),
            ],
            "trial narrative": [
                ("checked against its trial", R.validate_narrative(bad_narrative, good_trial), "narrative"),
                ("a collection member's", R.validate_collection({"members": [{"id": "m", "trial": good_trial, "narrative": bad_narrative}]}), "collection.members[0].narrative"),
                ("report.py --trial --narrative", self.cli(("--trial", good_trial), ("--narrative", bad_narrative)), "narrative"),
            ],
            "comparison narrative": [
                ("checked against its comparison", R.validate_comparison(good_comparison, bad_narrative), "narrative"),
                ("a collection member's", R.validate_collection({"members": [{"id": "m", "comparison": good_comparison, "narrative": bad_narrative}]}), "collection.members[0].narrative"),
                ("report.py --data --narrative", self.cli(("--data", good_comparison), ("--narrative", bad_narrative)), "narrative"),
            ],
        }
        for kind, paths in matrix.items():
            first_name, first_problems, first_at = paths[0]
            reference = within(first_problems, first_at)
            self.assertTrue(reference, f"{kind}: the bad input has problems")
            for name, problems, at in paths[1:]:
                with self.subTest(kind=kind, path=name):
                    self.assertEqual(within(problems, at), reference, f"{kind}: {name} against {first_name}")


# Every identifier field of each kind of data, and the malformed values each must be refused (or, where the field may be
# left out, accepted as left out). Each entry's path names the field; "*" marks its index in the base input.
# An identifier is text with something in it, starting with no "$" (a note) and with no space or tab at either end.
# Whitespace is one explicit set in both checkers: ASCII space and tab, and all Unicode whitespace (no-break and em
# spaces, the byte-order mark, next-line among them).
BAD_IDS = [None, False, 0, {}, [], "", "  ", "$x", " x", "x ", "\t", "\u00a0x", "x\u2003", "\ufeffx", "\u0085x", "\u00a0"]


def id_base_trial() -> dict:
    return {"plan": {"scenarios": [{"name": "c1"}]}, "runs": [{"job": "j1", "arm": "a", "scenario": "c1", "repeat": 1, "passed": True, "valid": True}, {"job": "j2", "arm": "b", "scenario": "c1", "repeat": 1, "passed": False, "valid": True}], "pairwise": {"a|b": {"arms": ["a", "b"], "overall": {"a_wins": 1, "b_wins": 0}, "scenarios": {"c1": {"a_wins": 1, "b_wins": 0}}}}}


def id_base_comparison() -> dict:
    return {"alternatives": [{"id": "x"}, {"id": "y"}], "cases": [{"id": "c1"}], "metrics": [{"id": "m", "kind": "binary"}, {"id": "p", "kind": "preference"}, {"id": "t", "kind": "numeric"}, {"id": "o", "kind": "ordinal", "levels": ["bad", "good"]}],
            "observations": [{"alternative": "x", "metric": "m", "case": "c1", "value": True}],
            "aggregates": [{"alternative": "y", "metric": "m", "case": "c1", "k": 1, "n": 2}, {"alternative": "y", "metric": "t", "case": "c1", "mean": 3, "sd": 1, "n": 4}, {"alternative": "y", "metric": "o", "case": "c1", "counts": {"good": 2}}],
            "preferences": [{"a": "x", "b": "y", "winner": "x", "case": "c1", "metric": "p"}], "rankings": [{"order": ["x", "y"], "case": "c1", "metric": "p"}]}


def id_base_collection() -> dict:
    tiny = {"runs": [{"job": "j1", "arm": "a", "scenario": "c1", "repeat": 1, "passed": True, "valid": True}]}
    small = {"alternatives": [{"id": "x"}], "metrics": [{"id": "m", "kind": "binary"}], "observations": [{"alternative": "x", "metric": "m", "value": True}]}
    return {"themes": [{"id": "t"}], "members": [{"id": "m1", "theme": "t", "trial": tiny}, {"id": "m2", "follows": "m1", "trial": tiny}, {"id": "m3", "comparison": small}, {"id": "m4", "spec": {"title": "S", "sections": []}}], "pairs": [{"a": "m1", "b": "m2"}]}


def id_one_arm_trial() -> dict:
    return {"runs": [{"job": "j1", "arm": "a", "scenario": "c1", "repeat": 1, "passed": True, "valid": True}, {"job": "j2", "arm": "a", "scenario": "c2", "repeat": 1, "passed": False, "valid": True}]}


ID_FIELDS = {
    "trial": (id_base_trial, [("runs", 1, "arm"), ("runs", 1, "scenario"), ("runs", 1, "job"), ("plan", "scenarios", 0, "name"), ("pairwise", "a|b", "arms", 1)]),
    "trial (one arm)": (id_one_arm_trial, [("runs", 1, "arm"), ("runs", 1, "scenario"), ("runs", 1, "job")]),
    "comparison": (id_base_comparison, [("alternatives", 0, "id"), ("cases", 0, "id"), ("metrics", 0, "id"), ("observations", 0, "alternative"), ("observations", 0, "metric"), ("observations", 0, "case"),
                                        ("aggregates", 0, "alternative"), ("aggregates", 0, "metric"), ("aggregates", 0, "case"), ("preferences", 0, "a"), ("preferences", 0, "b"), ("preferences", 0, "winner"),
                                        ("preferences", 0, "case"), ("preferences", 0, "metric"), ("rankings", 0, "order", 0), ("rankings", 0, "case"), ("rankings", 0, "metric")]),
    "collection": (id_base_collection, [("members", 0, "id"), ("themes", 0, "id"), ("members", 0, "theme"), ("members", 1, "follows"), ("pairs", 0, "a"), ("pairs", 0, "b")]),
}
# A field that may be left out may be null: a case left out is evidence naming no case (a blank one stands for it, with a
# warning), a winner left out a judgment never reached, a judgment's metric left out the overall question, and a job,
# theme or follow-up left out none. Every other malformed value is an error, at the field or at its record.
OPTIONAL = {"case", "winner", "metric", "job", "theme", "follows"}
# A member's theme that names no declared theme, a blank one among them, leaves the report among the other reports: a
# warning, as for any theme the collection does not declare.
ALLOWED = {(name, blank): ["warning"] for name in ("case", "theme") for blank in ("", "  ", "\t", "\u00a0")}


def with_value(base: dict, path: tuple, value) -> dict:
    data = json.loads(json.dumps(base))
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return data


def place(prefix: str, path: tuple) -> str:
    out = prefix
    for key in path:
        out = f"{out}[{key}]" if isinstance(key, int) else f"{out}.{key}" if R.PLAIN_KEY.fullmatch(key) else f"{out}[{json.dumps(key)}]"
    return out


def identifier_failures() -> tuple[list[str], int]:
    """Every identifier field and malformed value on each path, checked by both checkers: what fails, and how many were checked."""
    entries, expected = [], []
    for kind, (base, fields) in ID_FIELDS.items():
        for path in fields:
            for bad in BAD_IDS:
                data = with_value(base(), path, bad)
                family = kind.split(" ")[0]
                paths = {"trial": [("spec", {"title": "T", "sections": [{"title": "S", "reading": "r", "blocks": [{"type": "cases"}]}], "trial": data}, "trial"), ("narrative", {}, "trial"), ("collection", {"members": [{"id": "m", "trial": data}]}, "collection.members[0].trial")],
                         "comparison": [("comparison", data, "comparison"), ("spec", {"title": "T", "sections": [], "comparison": data}, "comparison"), ("collection", {"members": [{"id": "m", "comparison": data}]}, "collection.members[0].comparison")],
                         "collection": [("collection", data, "collection"), ("spec", {"title": "T", "sections": [], "collection": data}, "collection")]}[family]
                for which, input_, prefix in paths:
                    entries.append({"kind": which, "input": input_, **({"trial": data} if which == "narrative" else {})})
                    expected.append((kind, path, bad, which, prefix))
    with Scratch() as directory:
        path = directory / "ids.json"
        path.write_text(json.dumps(entries), encoding="utf-8")
        result = run_node(TESTS / "validate.cjs", "--ids", path, "--out", directory / "page.json", timeout=300)
        if result.returncode != 0:
            return [f"validate.cjs --ids failed: {result.stderr[-2000:]}"], len(entries)
        page = json.loads((directory / "page.json").read_text(encoding="utf-8"))
    failures = []
    for entry, theirs, (kind, field, bad, which, prefix) in zip(entries, page, expected):
        label = f"{kind} {'.'.join(map(str, field))} = {json.dumps(bad)} via {which}"
        try:
            ours = R.validate_spec(entry["input"]) if which == "spec" else R.validate_narrative({}, entry["trial"]) if which == "narrative" else R.validate_collection(entry["input"]) if which == "collection" else R.validate_comparison(entry["input"])
        except Exception as error:  # noqa: BLE001 - a crash is the finding
            failures.append(f"{label}: report.py raised {type(error).__name__}: {error}")
            continue
        if isinstance(theirs, dict) and "exception" in theirs:
            failures.append(f"{label}: the page's checker raised {theirs['exception'][:200]}")
            continue
        if ours != theirs:
            failures.append(f"{label}: the checkers differ\n  report.py: {json.dumps(ours)[:500]}\n  page:      {json.dumps(theirs)[:500]}")
            continue
        at, record = place(prefix, field), place(prefix, field[:-1])
        name = field[-1] if isinstance(field[-1], str) else "order"
        # A required field left out is named at its record ("missing required field").
        levels = sorted({p["level"] for p in ours if p["where"] == at or p["where"].startswith(at + ".") or p["where"].startswith(at + "[") or (p["where"] == record and f'"{name}"' in p["message"])})
        allowed = [] if bad is None and name in OPTIONAL and not (name == "metric" and field[0] in ("observations", "aggregates")) else ALLOWED.get((name, bad)) if isinstance(bad, str) else None
        want = allowed if allowed is not None else ["error"]
        if (want == [] and levels) or (want and want[0] not in levels):
            failures.append(f"{label}: expected {want or 'no problem'} at {at}, found {levels} in {json.dumps([p['where'] + ': ' + p['message'] for p in ours])[:400]}")
    return failures, len(entries)


# Every record type the views read and the fields they rely on: each removed in turn must be refused, at the field or
# at its record, alike in both checkers, and a page drawn from it says it has an error and invents nothing in its place.
REQUIRED_FIELDS = {
    "trial": (id_base_trial, [("runs",), ("runs", 1, "arm"), ("runs", 1, "scenario"), ("runs", 1, "passed"), ("plan", "scenarios", 0, "name"),
                              ("pairwise", "a|b", "arms"), ("pairwise", "a|b", "overall"), ("pairwise", "a|b", "scenarios")]),
    "comparison": (id_base_comparison, [("alternatives",), ("metrics",), ("alternatives", 0, "id"), ("cases", 0, "id"), ("metrics", 0, "id"), ("metrics", 0, "kind"),
                                        ("observations", 0, "alternative"), ("observations", 0, "metric"), ("aggregates", 0, "alternative"), ("aggregates", 0, "metric"),
                                        ("aggregates", 0, "k"), ("aggregates", 0, "n"), ("aggregates", 1, "mean"), ("aggregates", 2, "counts"),
                                        ("preferences", 0, "a"), ("preferences", 0, "b"), ("rankings", 0, "order")]),
    "collection": (id_base_collection, [("members",), ("members", 0, "id"), ("members", 0, "trial"), ("members", 2, "comparison"), ("members", 3, "spec"), ("themes", 0, "id"), ("pairs", 0, "a"), ("pairs", 0, "b")]),
}


def without(base: dict, path: tuple) -> dict:
    data = json.loads(json.dumps(base))
    node = data
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return data


def removal_failures() -> tuple[list[str], int]:
    """Each required field removed, on each path, in both checkers: what fails, and how many were checked."""
    entries, expected = [], []
    for kind, (base, fields) in REQUIRED_FIELDS.items():
        for path in fields:
            data = without(base(), path)
            spec = {"trial": {"title": "T", "sections": [{"title": "S", "reading": "r", "blocks": [{"type": "cases"}, {"type": "pairwise"}]}], "trial": data},
                    "comparison": {"title": "T", "sections": [{"title": "S", "reading": "r", "blocks": [{"type": "scorecard"}]}], "comparison": data},
                    "collection": {"title": "T", "sections": [{"title": "S", "reading": "r", "blocks": [{"type": "reports"}]}], "collection": data}}[kind]
            paths = {"trial": [("spec", spec, "trial"), ("narrative", {}, "trial"), ("collection", {"members": [{"id": "m", "trial": data}]}, "collection.members[0].trial")],
                     "comparison": [("comparison", data, "comparison"), ("spec", spec, "comparison"), ("collection", {"members": [{"id": "m", "comparison": data}]}, "collection.members[0].comparison")],
                     "collection": [("collection", data, "collection"), ("spec", spec, "collection")]}[kind]
            for which, input_, prefix in paths:
                entries.append({"kind": which, "input": input_, **({"trial": data} if which == "narrative" else {}), **({"render": True} if which == "spec" else {})})
                expected.append((kind, path, which, prefix))
    with Scratch() as directory:
        file = directory / "removed.json"
        file.write_text(json.dumps(entries), encoding="utf-8")
        result = run_node(TESTS / "validate.cjs", "--ids", file, "--out", directory / "page.json", timeout=300)
        if result.returncode != 0:
            return [f"validate.cjs --ids failed: {result.stderr[-2000:]}"], len(entries)
        page = json.loads((directory / "page.json").read_text(encoding="utf-8"))
    failures = []
    for entry, theirs, (kind, field, which, prefix) in zip(entries, page, expected):
        label = f"{kind} without {'.'.join(map(str, field))} via {which}"
        try:
            ours = R.validate_spec(entry["input"]) if which == "spec" else R.validate_narrative({}, entry["trial"]) if which == "narrative" else R.validate_collection(entry["input"]) if which == "collection" else R.validate_comparison(entry["input"])
        except Exception as error:  # noqa: BLE001 - a crash is the finding
            failures.append(f"{label}: report.py raised {type(error).__name__}: {error}")
            continue
        if isinstance(theirs, dict) and "exception" in theirs:
            failures.append(f"{label}: the page's checker raised {theirs['exception'][:200]}")
            continue
        drawn = theirs if isinstance(theirs, dict) else None
        problems = drawn["problems"] if drawn else theirs
        if ours != problems:
            failures.append(f"{label}: the checkers differ\n  report.py: {json.dumps(ours)[:500]}\n  page:      {json.dumps(problems)[:500]}")
            continue
        at, record, name = place(prefix, field), place(prefix, field[:-1]), field[-1]
        # At the field, or at its record: a missing required field is named there, and a record without the list that
        # makes it trial or comparison data is refused whole ("is not trial report data").
        found = [p for p in ours if p["level"] == "error" and (p["where"] == at or p["where"].startswith(at + ".") or p["where"].startswith(at + "[") or p["where"] == record)]
        if not found:
            failures.append(f"{label}: no error at {at} or its record, in {json.dumps([p['where'] + ': ' + p['message'] for p in ours])[:400]}")
        if drawn and not drawn["flagged"]:
            failures.append(f"{label}: the page drawn from it does not say it has an error")
        if drawn and kind == "trial" and field[0] == "pairwise" and drawn["duels"]:
            failures.append(f"{label}: the pairwise view draws a judgment whose {name} is missing")
    return failures, len(entries)


# Every keyed map a check reads, given a "$" entry carrying malformed content: a "$" key is a note, so each checker
# finds exactly what it finds without it, and both agree.
def note_cases() -> list[tuple[str, dict, dict]]:
    ghost = {"arms": ["ghost-a", "ghost-b"], "overall": {"a_wins": 1}, "scenarios": {"ghost-case": {"a_wins": 1}}}

    def trial_with(change) -> dict:
        t = id_base_trial()
        t["plan"]["arms"] = {"a": {"model": "m"}, "b": {"model": "m"}}
        for r in t["runs"]:
            r["checks"] = {"ok": r["passed"]}
        change(t)
        return t

    def comparison_with(change) -> dict:
        c = id_base_comparison()
        c["alternatives"][0]["attributes"] = {"Spread": "pb"}
        c["metrics"].append({"id": "taste", "kind": "ordinal", "levels": ["bad", "good"]})
        c["aggregates"].append({"alternative": "x", "metric": "taste", "case": "c1", "counts": {"good": 2}})
        change(c)
        return c

    def nothing(_):
        return None
    spec = lambda t: {"title": "T", "sections": [{"title": "S", "reading": "r", "blocks": [{"type": "pairwise"}, {"type": "checks"}]}], "trial": t}  # noqa: E731
    cspec = lambda c, scores: {"title": "T", "sections": [{"title": "S", "reading": "r", "blocks": [{"type": "decision-matrix", "criteria": [{"id": "cost", "scores": scores}]}]}], "comparison": c}  # noqa: E731
    out = []
    for name, change in [("pairwise judgments", lambda t: t["pairwise"].__setitem__("$p", ghost)),
                         ("a judgment's counts by case", lambda t: t["pairwise"]["a|b"]["scenarios"].__setitem__("$ghost", {"a_wins": "x"})),
                         ("a plan's arms", lambda t: t["plan"]["arms"].__setitem__("$ghost", {"model": {"odd": True}})),
                         ("a run's checks", lambda t: t["runs"][0]["checks"].__setitem__("$ghost", "not a check"))]:
        out += [(f"{name} via spec", spec(trial_with(change)), spec(trial_with(nothing))),
                (f"{name} via narrative", {"trial": trial_with(change)}, {"trial": trial_with(nothing)}),
                (f"{name} via collection", {"members": [{"id": "m", "trial": trial_with(change)}]}, {"members": [{"id": "m", "trial": trial_with(nothing)}]})]
    for name, change in [("a total's level counts", lambda c: c["aggregates"][-1]["counts"].__setitem__("$ghost", 99)),
                         ("an alternative's attributes", lambda c: c["alternatives"][0]["attributes"].__setitem__("$ghost", {"odd": True}))]:
        out += [(f"{name} via comparison", comparison_with(change), comparison_with(nothing)),
                (f"{name} via spec", cspec(comparison_with(change), {"x": 1}), cspec(comparison_with(nothing), {"x": 1}))]
    out += [("a criterion's scores via spec", cspec(comparison_with(nothing), {"x": 1, "$ghost": {"odd": True}}), cspec(comparison_with(nothing), {"x": 1})),
            ("a story's descriptions via spec", {**spec(trial_with(nothing)), "story": {**story_for(), "alternatives": {"$ghost": "Ghost."}, "cases": {"$ghost": "Ghost."}}}, {**spec(trial_with(nothing)), "story": {**story_for(), "alternatives": {}, "cases": {}}}),
            ("a collection's readings via collection", {**id_base_collection(), "readings": {"$ghost": {"odd": True}}}, {**id_base_collection(), "readings": {}})]
    return out


class NoteKeySweepTest(unittest.TestCase):
    """A "$" key is a note in every keyed map, for both checkers: each finds what it finds without it, both agree, neither raises."""

    def test_every_keyed_map_with_a_note(self) -> None:
        cases = note_cases()
        entries = []
        for _, noted, plain in cases:
            for given in (noted, plain):
                kind = "narrative" if "trial" in given and "title" not in given else "spec" if "title" in given else "collection" if "members" in given else "comparison"
                entries.append({"kind": kind, "input": {} if kind == "narrative" else given, **({"trial": given["trial"]} if kind == "narrative" else {})})
        with Scratch() as directory:
            file = directory / "notes.json"
            file.write_text(json.dumps(entries), encoding="utf-8")
            result = run_node(TESTS / "validate.cjs", "--ids", file, "--out", directory / "page.json", timeout=300)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            page = json.loads((directory / "page.json").read_text(encoding="utf-8"))
        for i, (name, _, _) in enumerate(cases):
            with self.subTest(map=name):
                noted, plain = entries[2 * i], entries[2 * i + 1]
                ours = [R.validate_spec(e["input"]) if e["kind"] == "spec" else R.validate_narrative({}, e["trial"]) if e["kind"] == "narrative" else R.validate_collection(e["input"]) if e["kind"] == "collection" else R.validate_comparison(e["input"]) for e in (noted, plain)]
                self.assertEqual(ours[0], page[2 * i], "the checkers agree, with the note")
                self.assertEqual(ours[1], page[2 * i + 1], "and without it")
                self.assertEqual(ours[0], ours[1], "the note changes nothing a check finds")


class RequiredFieldSweepTest(unittest.TestCase):
    """Every field the views rely on, removed from its record on each path: both checkers refuse it alike, neither raises,
    and the page drawn from it says so and invents nothing in its place."""

    def test_every_required_field_removed(self) -> None:
        failures, checked = removal_failures()
        self.assertFalse(failures, f"{len(failures)} of {checked} entries fail; the first:\n" + "\n".join(failures[:12]))


class IdentifierSweepTest(unittest.TestCase):
    """Every identifier field of a trial, a comparison and a collection, with every malformed value, on each path: both
    checkers find the same problems, raise nothing, and refuse the value at its place (or accept it where it may be left out)."""

    def test_every_identifier_field_and_malformed_value(self) -> None:
        failures, checked = identifier_failures()
        self.assertFalse(failures, f"{len(failures)} of {checked} entries fail; the first:\n" + "\n".join(failures[:12]))


# Every required text field, given each whitespace character alone, all of them together, or visible text: report.py's
# checker finds exactly what the page's checker finds (validate.cjs holds the page's checker and the drawn page to agree).
class BlankTextSweepTest(unittest.TestCase):
    def test_every_required_text_field_and_whitespace(self) -> None:
        trial = json.loads((EXAMPLES / "fictional-trial.json").read_text(encoding="utf-8"))
        narrative = json.loads((EXAMPLES / "fictional-narrative.json").read_text(encoding="utf-8"))
        sandwich = json.loads((EXAMPLES / "comparisons" / "sandwich.json").read_text(encoding="utf-8"))
        told = json.loads((EXAMPLES / "comparisons" / "sandwich-narrative.json").read_text(encoding="utf-8"))
        arm = next(iter(narrative["story"]["alternatives"]))
        values = [*R.WHITESPACE, R.WHITESPACE, "Visible."]
        story = lambda k, v: {**narrative, "story": {**narrative["story"], k: v}}  # noqa: E731
        fields = [
            ("a trial narrative's reading", lambda v: {"kind": "narrative", "input": {**narrative, "readings": {**narrative["readings"], "setup": v}}, "trial": trial}),
            ("a comparison narrative's reading", lambda v: {"kind": "comparison", "input": sandwich, "narrative": {**told, "readings": {**told["readings"], "results": v}}}),
            *[(f"the story's {k}", (lambda k: lambda v: {"kind": "narrative", "input": story(k, v), "trial": trial})(k)) for k in ("background", "intent", "rule", "covers", "notCovered")],
            ("the story's question", lambda v: {"kind": "narrative", "input": story("questions", [v]), "trial": trial}),
            ("an arm's description", lambda v: {"kind": "narrative", "input": story("alternatives", {**narrative["story"]["alternatives"], arm: v}), "trial": trial}),
            ("a text view's text", lambda v: {"kind": "spec", "input": {"title": "T", "sections": [{"title": "S", "reading": "r", "blocks": [{"type": "text", "text": v}]}]}}),
            ("a specification's title", lambda v: {"kind": "spec", "input": {"title": v, "sections": []}}),
            ("a collection's reading", lambda v: {"kind": "collection", "input": {**id_base_collection(), "readings": {"glance": v}}}),
        ]
        entries = [(name, repr(v), make(v)) for name, make in fields for v in values]
        with Scratch() as directory:
            file = directory / "blank.json"
            file.write_text(json.dumps([e for _, _, e in entries]), encoding="utf-8")
            result = run_node(TESTS / "validate.cjs", "--ids", file, "--out", directory / "page.json", timeout=300)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            page = json.loads((directory / "page.json").read_text(encoding="utf-8"))
        differ = []
        for (name, value, e), theirs in zip(entries, page):
            ours = (R.validate_narrative(e["input"], e["trial"]) if e["kind"] == "narrative" else R.validate_comparison(e["input"], e["narrative"]) if e["kind"] == "comparison"
                    else R.validate_spec(e["input"]) if e["kind"] == "spec" else R.validate_collection(e["input"]))
            if ours != theirs:
                differ.append(f"{name} = {value}:\n  report.py: {json.dumps(ours)[:400]}\n  page:      {json.dumps(theirs)[:400]}")
        self.assertFalse(differ, f"{len(differ)} of {len(entries)} differ; the first:\n" + "\n".join(differ[:6]))


class TrialEntryTest(unittest.TestCase):
    def test_report_check_refuses_a_borrowed_trial_run_naming_no_scenario(self) -> None:
        trial = {"runs": [{"job": "j1", "arm": "a", "scenario": "c1", "repeat": 1, "passed": True, "valid": True}, {"job": "j2", "arm": "a", "scenario": "", "repeat": 2, "passed": False, "valid": True}]}
        spec = {"title": "T", "story": story_for(), "sections": [{"title": "S", "reading": "r", "blocks": [{"type": "ladder"}]}]}
        with Scratch() as directory:
            (directory / "trial.json").write_text(json.dumps(trial), encoding="utf-8")
            (directory / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
            result = run_python(REPORT, "--check", "--spec", directory / "spec.json", "--trial", directory / "trial.json")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("trial.runs[1].scenario: a trial run must name its scenario", result.stdout + result.stderr)


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
        blank = json.loads(json.dumps(cls.trials["fictional"]))
        blank["runs"][0].pop("scenario", None)
        blank["runs"][1]["scenario"] = ""
        cls.trials["blank"] = blank
        cls.trials["bad"] = BAD_TRIAL

    def test_block_types_match_the_registry(self) -> None:
        self.compare([{"kind": "types"}], {})

    def test_every_field_table_and_rule_agrees(self) -> None:
        corpus = generated_corpus() + written_corpus()
        self.assertGreater(len(corpus), 2000)
        self.compare(corpus, self.trials)

    def test_story_obligations_and_drawn_sections_agree(self) -> None:
        """Every source a story's obligations come from, and every condition a composed section needs its reading under."""
        def run(job, scenario, arm, passed):
            return {"job": job, "scenario": scenario, "arm": arm, "repeat": 1, "passed": passed, "valid": passed is not None}
        variant = {"plan": {"arms": {"only": {}}, "scenarios": [{"name": "base", "prompt": "Do it.", "followups": [], "required": []}, {"name": "more", "prompt": "Do it.", "followups": ["Again."], "required": []},
                                                                {"name": "tied", "prompt": "Other.", "followups": [1.0]}, {"name": "tie2", "prompt": "Other.", "followups": [1]}]},
                   "runs": [run("j1", "base", "only", True), run("j2", "more", "only", False), run("j3", "tied", "only", True), run("j4", "tie2", "only", None)]}
        plain = {"background": "b", "intent": "i", "questions": ["q"], "rule": "r", "covers": "c", "notCovered": "n"}
        local = {"alternatives": [{"id": "x"}, {"id": "y"}], "metrics": [{"id": "m", "kind": "numeric"}],
                 "observations": [{"alternative": a, "case": c, "metric": "m", "value": v} for a, c, v in (("x", "u", 1), ("y", "u", 2), ("x", "v", 3))]}
        view = {"type": "metric", "data": local, "metric": "m", "read": {"says": "Y is higher."}}
        n = lambda value, context="variant": {"kind": "narrative", "input": value, "trial": context}  # noqa: E731
        sp = lambda value, context=None: {"kind": "spec", "input": value, "trial": context}  # noqa: E731
        corpus = [
            n({"story": plain, "readings": {"setup": "s", "cases": "c", "runs": "r"}}),
            n({"story": plain, "readings": {"setup": "s", "cases": "c", "runs": "r"}, "pairs": [["base", "more"]]}),
            n({"story": plain, "readings": {"setup": "s", "cases": "c", "runs": "r"}, "pairs": [["base", "base"], {"base": "base", "variant": "nope"}, ["more"]]}),
            n({"story": plain, "pairs": []}),
            n({"story": plain, "sections": [{"title": "Extra", "blocks": [view]}], "append": {"verdict": [view, {"type": "diagram", "source": "x"}]}}, "fictional"),
            n({"story": {**plain, "background": 0, "questions": [0, None, "q"], "covers": True, "notCovered": [3]}}, "fictional"),
            sp({"title": "Numeric", "story": {"background": 0, "intent": 0, "questions": [0], "covers": 0, "notCovered": 0, "rule": 0}, "sections": [{"title": "O", "reading": "R.", "blocks": [{"type": "intervals", "rows": [{"label": "L", "value": 3, "lo": 2, "hi": 4}]}]}]}),
            sp({"title": "Both", "trial": variant, "comparison": local, "story": plain, "sections": [{"title": "V", "reading": "R.", "blocks": [{"type": "metric", "metric": "m", "read": {"says": "S."}}]}]}),
            sp({"title": "Hand", "story": plain, "sections": [{"title": "Rates", "reading": "R.", "blocks": [
                {"type": "ladder", "rows": [{"arm": "x", "case": "c1", "k": 2, "n": 3}]}, {"type": "contrast", "rows": [{"arm": "y", "vs": "x2", "k1": 1, "n1": 2, "k2": 1, "n2": 2}]},
                {"type": "matrix", "columns": [{"id": "col-arm", "arm": True}, {"id": "col", "arm": False}], "rows": [{"id": "r", "label": "R"}]},
                {"type": "bars", "segments": [{"id": "s", "label": "S"}], "rows": [{"label": "B", "arm": "barred", "values": {"s": 1}}]},
                {"type": "excerpts", "items": [{"text": "t", "arm": "quoted"}]}, {"type": "trend", "stages": ["a"], "series": [{"label": "T", "arm": "trended", "points": [{"stage": "a", "value": 0.5}]}]}]}]}),
            sp({"title": "Flow", "story": plain, "sections": [{"title": "How", "blocks": [{"type": "diagram", "source": "flowchart LR\n A --> B"}]}, {"title": "Two", "blocks": [{"type": "diagram", "source": "x"}, {"type": "text", "text": "t"}]}]}),
            sp({"title": "Filters", "story": {**plain, "alternatives": {"only": "O."}}, "sections": [{"title": "F", "reading": "R.", "blocks": [{"type": "ladder", "arms": ["only"], "cases": ["base", "more"]}]}]}, "variant"),
            sp({"title": "Pointers", "story": {**plain, "background": "We compared docs/README.md with docs/guide.md; both are reproduced below. We found a typo in README.md.", "intent": "Read `docs/rule.md` first.",
                                                "covers": "see e.g. the table; see Node.js docs; see https://example.com/a.md", "notCovered": "As described in runs/slow/notes.txt."}, "sections": []}),
        ]
        # A decision matrix's own alternatives, listed, from its comparison, or named only by its cells; a trial's pairwise
        # arms and cases that no run names.
        matrix = {"type": "decision-matrix", "alternatives": [{"id": "x", "label": "Procedure X"}, "y", {"label": "no id"}], "criteria": [{"id": "quality", "scores": {"x": 5, "y": 3, "z": 1}}]}
        cells = {"type": "decision-matrix", "criteria": [{"id": "quality"}], "cells": [{"criterion": "quality", "alternative": "p"}, {"criterion": "quality", "alternative": "q"}, "x"]}
        ghost = {**variant, "pairwise": {"only__ghost": {"arms": ["only", "ghost", "third"], "overall": {"a_wins": 1}, "scenarios": {"base": {}, "nowhere": {}}}, "bad": "x"}}
        corpus += [
            sp({"title": "Pick", "story": plain, "sections": [{"title": "Choose", "reading": "X rates higher.", "blocks": [matrix, cells]}]}),
            sp({"title": "Pick", "story": plain, "comparison": local, "sections": [{"title": "Choose", "reading": "R.", "blocks": [{**cells, "read": {"says": "S."}}, {**matrix, "alternatives": [], "read": {"says": "S."}}]}]}),
            sp({"title": "Pick", "story": plain, "sections": [{"title": "Choose", "reading": "R.", "blocks": [{**cells, "data": local}]}]}),
            n({"story": plain, "readings": {"setup": "s", "cases": "c", "runs": "r", "arms": "a", "pairwise": "p"}, "sections": [{"title": "Choose", "reading": "R.", "blocks": [matrix]}]}, "ghost"),
            sp({"title": "Counts", "story": plain, "sections": [{"title": "C", "reading": "R.", "blocks": [{"type": "intervals", "independent": True, "rows": [{"label": "L", "k": 1, "n": 2, "cases": 2}], "read": {"shows": "", "how": "", "says": "S."}}]}]}),
        ]
        self.compare(corpus, {**self.trials, "variant": variant, "ghost": ghost})

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
