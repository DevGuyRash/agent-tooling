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

from visual_harness import EXAMPLES, NODE, REPORT, TESTS, NodeCases, Scratch, run_node, story_for, told, write_hostile_fixtures


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
        s([{"type": "text", "text": "x"}], None, arms=[{"id": "a"}, {"id": "a"}], meta=[{"label": "L"}], cases={"zz": "Z"}),
        {"kind": "spec", "input": {"title": "T", "sections": [{"id": "a", "title": "A", "blocks": []}, {"id": "a", "title": "B", "blocks": []}, {"id": "1", "title": "C", "blocks": []}, None, {"title": "D", "blocks": {}}]}, "trial": None},
        {"kind": "spec", "input": {"title": "T", "sections": [], "problems": [{"level": "error", "where": "narrative.x", "message": "m", "hint": "h"}, {"level": "fatal", "where": "w", "message": "m"}, {"where": 3}, None]}, "trial": None},
        {"kind": "spec", "input": {"sections": "none"}, "trial": None},
        # A block's own comparison: its alternatives and cases need the story's descriptions, and an empty part says nothing.
        {"kind": "spec", "input": {"title": "Lunch", "story": {"background": [], "intent": "i", "questions": ["", "q"], "covers": "c", "notCovered": [" "], "alternatives": {"pbj": "P"}}, "sections": [{"title": "T", "reading": "r", "blocks": [{"type": "metric", "metric": "taste", "data": {"alternatives": [{"id": "pbj"}, {"id": "ham"}], "cases": [{"id": "hungry"}], "metrics": [{"id": "taste", "kind": "numeric"}], "observations": [{"alternative": "pbj", "case": "hungry", "metric": "taste", "value": 8}]}}]}]}, "trial": None},
        {"kind": "spec", "input": ["not", "a", "spec"], "trial": None},
        {"kind": "narrative", "input": "not a narrative", "trial": trial},
    ]


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
    return corpus


class ComparisonAgreementTest(unittest.TestCase):
    """report.py and the page check comparisons, their narratives and the comparison blocks alike."""

    def test_every_comparison_field_and_rule_agrees(self) -> None:
        corpus = comparison_corpus()
        self.assertGreater(len(corpus), 1500)
        with Scratch() as directory:
            path = directory / "corpus.json"
            path.write_text(json.dumps({"comparisons": {"base": BASE}, "entries": corpus}), encoding="utf-8")
            result = run_node(TESTS / "engine.cjs", "--corpus", path, "--out", directory / "page.json", timeout=300)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            page = json.loads((directory / "page.json").read_text(encoding="utf-8"))
        self.assertEqual(len(page), len(corpus))
        differ = []
        for entry, theirs in zip(corpus, page):
            if entry["kind"] == "comparison":
                ours = R.validate_comparison(entry["input"], entry["narrative"]) if "narrative" in entry else R.validate_comparison(entry["input"])
            else:
                ours = R.validate_spec(entry["input"], None, BASE if entry.get("comparison") else None)
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
    ]
    return corpus


class CollectionAgreementTest(unittest.TestCase):
    """report.py and the page check collections, their members' narratives and the collection blocks alike."""

    def test_every_collection_field_and_rule_agrees(self) -> None:
        corpus = collection_corpus()
        self.assertGreater(len(corpus), 400)
        with Scratch() as directory:
            path = directory / "corpus.json"
            path.write_text(json.dumps({"trials": {}, "collections": {"base": COLLECTION}, "entries": corpus}), encoding="utf-8")
            result = run_node(TESTS / "validate.cjs", "--corpus", path, "--out", directory / "page.json", timeout=300)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            page = json.loads((directory / "page.json").read_text(encoding="utf-8"))
        self.assertEqual(len(page), len(corpus))
        differ = []
        for entry, theirs in zip(corpus, page):
            ours = R.validate_collection(entry["input"]) if entry["kind"] == "collection" else R.validate_spec(entry["input"], None, None, COLLECTION if entry.get("collection") else None)
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
            "an impossible date": ({**COLLECTION, "members": [{**m1, "date": "2026-02-30"}, m2, m3]}, [("warning", "collection.members[0].date", '"2026-02-30" is not a calendar date written YYYY-MM-DD, so it is not used')]),
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
