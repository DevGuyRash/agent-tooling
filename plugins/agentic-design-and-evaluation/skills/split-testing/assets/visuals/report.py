#!/usr/bin/env python3
"""Write one self-contained HTML report from trial data, a comparison of any alternatives, a report specification, or a mix.

  report.py --trial REPORT.json [--narrative NARRATIVE.json] --output report.html
  report.py --data COMPARISON.json [--csv TABLE.csv] [--narrative NARRATIVE.json] --output report.html
  report.py --csv TABLE.csv [--narrative NARRATIVE.json] --output report.html
  report.py --spec SPEC.json [--trial REPORT.json] [--data COMPARISON.json] --output report.html
  report.py --collection COLLECTION.json [--spec SPEC.json] --output collection.html
  report.py --check (any of the inputs above)
  report.py --skeleton [NARRATIVE.json] (--trial REPORT.json | --data COMPARISON.json | --csv TABLE.csv)

REPORT.json is what `trial.py report RUN_DIR` writes. COMPARISON.json compares
any alternatives (a prompt, a sandwich, an ad, a game mechanic, a research
direction) on any metrics; TABLE.csv is a long table with one observation per
row (columns alternative, metric, value and optional case, group, unit, n,
valid, note, source, invalid_reason, excerpt), merged into COMPARISON.json when
both are given, with metric kinds inferred where COMPARISON.json does not
define them and ambiguous input refused. NARRATIVE.json adds the decision,
labels and extra sections to the default composition; SPEC.json is a complete
report specification instead (see catalog.md). COLLECTION.json names many
reports, each a member with its trial or comparison file and its narrative
file (paths relative to COLLECTION.json), with themes and pairs worth
comparing; the page shows them all at a glance with one copy of the library,
opens any of them in full, and sets any two side by side. The library renders the report
in the reader's browser from the embedded data, so this needs only Python: no
Node.js, no network, no build step.

--check reads the same inputs the way the page will and prints each problem as
an error: or warning: line followed by a hint: line, writes nothing, and exits 1
when there is an error. Errors are input that would break a view or make it
misread (a misspelled verdict, arm or case, a block type the library does not
have, more passes than valid runs, arms called identical whose recorded
settings differ); warnings are input the report does not use as written.
A normal run writes the report either way; the page lists the same problems at
its top.

--skeleton prints a starter narrative for --trial, or writes it to the file
named: every arm and case id spelled as the trial records it, arms whose
recorded settings all match grouped as identical, the plan's decision rule for
reference, and an empty decision to fill in. With --data or --csv it starts a
comparison narrative instead: every alternative and metric id as recorded, the
comparison's decision rule, and empty criteria for a decision matrix. Keys
starting with $ are notes the report ignores.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import math
from pathlib import Path
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import assemble  # noqa: E402  (the sibling offline packager)

BODY = (
    '<div class="av-mount" data-av-mount aria-busy="true">'
    '<noscript><p style="font:16px/1.5 system-ui;max-width:40rem;margin:4rem auto;padding:0 1rem">'
    "This report draws its views from embedded data with JavaScript. Enable JavaScript "
    "for this file, or read the JSON blocks inside it directly.</p></noscript></div>\n"
)


def uses_diagrams(value) -> bool:
    if isinstance(value, dict):
        return value.get("type") == "diagram" or any(uses_diagrams(v) for v in value.values())
    if isinstance(value, list):
        return any(uses_diagrams(v) for v in value)
    return False


def load(path: Path, label: str, strict: bool = False):
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise assemble.PackagingError(f"{label} file not found: {path}") from None
    if strict:
        # The same JSON checks the packager applies before embedding: no duplicate keys, no NaN.
        assemble.json_content(text, f"{label} {path}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise assemble.PackagingError(f"{label} is not valid JSON: {path}: {error.msg} at line {error.lineno}") from None


# --------------------------------------------------------------------------- validation
#
# The same rules as src/validate.ts, so an agent learns about a misspelled field,
# arm or case without opening a browser. tests/test_validate.py runs both
# implementations over the same inputs and requires identical problems.

READ = {"fields": {"shows": "prose", "how": "prose", "says": "prose"}}
FRAME = {"title": "text", "description": "prose", "note": "text", "id": "text", "read": READ}
NUMBER_OR_NULL = {"oneOf": ["number", "null"]}
TONES = ["neutral", "pass", "fail", "invalid", "warn", "accent"]
TONE = {"enum": TONES, "warn": True}
GROUP = {"fields": {"label": "text", "cases": {"list": "case"}, "note": "text"}, "required": ["label", "cases"]}
CELL_VALUE = {"oneOf": ["text", "boolean", "null"]}
CASE_PAIR = {"fields": {"base": "case", "variant": "case", "label": "text", "note": "text"}, "required": ["base", "variant"]}
PAIR_LIST = {"list": {"oneOf": [{"list": "case"}, {"fields": {"base": "case", "variant": "case"}, "required": ["base", "variant"]}]}}
PAIR_SPECS = {"list": {"oneOf": [{"list": "case"}, {"fields": {"base": "case", "variant": "case", "variants": {"oneOf": [{"list": "case"}, {"record": "text", "keys": "case"}]}, "label": "text", "baseLabel": "text", "suffix": "text"}}]}}
AUTO_OFF = {"enum": ["auto", "off"], "warn": True}
CONTRAST_SIDE = {"fields": {"label": "text", "arms": {"list": "arm"}, "arm": "arm", "cases": {"list": "case"}, "case": "case"}}
CELL = {"oneOf": ["text", "boolean", "null", {"fields": {"value": CELL_VALUE, "status": {"enum": TONES}, "note": "text", "mono": "boolean"}}]}
VERDICT = {
    "verdict": {"enum": ["adopt", "reject", "inconclusive", "mixed", "none"], "fold": True},
    "label": "text", "headline": "text", "detail": "prose",
    "checks": {"list": {"fields": {"label": "text", "observed": "text", "threshold": "text", "met": {"oneOf": ["boolean", "null"]}, "group": "text"}, "required": ["label", "observed"]}},
    "conditions": {"list": "text"}, "limits": {"list": "text"}, "changes": {"list": "text"},
    "mentions": {"list": "text"}, "pairs": {"list": CASE_PAIR}, "alert": {"fields": {"text": "text", "href": "text", "link": "text"}, "required": ["text"]},
}

# Fields each built-in block reads; the keys are the library's block types.
ALTERNATIVES = {"list": "alternative"}
# What every comparison view reads: its own data or the report's, a metric, and what to narrow to
# (alternatives, cases, and group-path prefixes for alternatives and cases, outermost first).
COMPARE = {**FRAME, "data": "any", "metric": "metric", "alternatives": ALTERNATIVES, "cases": {"list": "comparison-case"}, "groups": {"list": "text"}, "caseGroups": {"list": "text"}, "baseline": "alternative"}
THRESHOLD = {"oneOf": ["number", "null", {"fields": {"value": "number", "label": "text"}, "required": ["value"]}]}
CENTER = {"enum": ["mean", "median"], "warn": True}
CRITERION_FIELDS = {"id": "text", "label": "text", "weight": "number", "better": {"enum": ["higher", "lower", "none"]}, "description": "text", "note": "text", "metric": "metric", "scores": {"record": {"oneOf": ["text", "boolean", "null"]}, "keys": "alternative-ref"}}
DECISION_CELL = {"fields": {"criterion": "text", "alternative": "alternative-ref", "rating": {"oneOf": ["text", "null"]}, "text": "text", "evidence": "prose"}, "required": ["criterion", "alternative"]}
DECISION_SCALE = {"fields": {"min": "number", "max": "number", "levels": {"list": "text"}, "labels": {"record": "text"}, "note": "text"}}

# Collection views: a subset of members by id or by theme, and pairs of members.
SUBSET = {**FRAME, "members": {"list": "member"}, "themes": {"list": "theme"}}
PAIR = {"fields": {"a": "member", "b": "member", "title": "text", "note": "text"}, "required": ["a", "b"]}
BLOCKS = {
    "verdict": {"fields": {**FRAME, **VERDICT, "rule": "prose"}, "required": ["headline"]},
    "figures": {"fields": {**FRAME, "items": {"list": {"fields": {"value": {"oneOf": ["text", "null"]}, "label": "text", "note": "text", "tone": {"enum": ["neutral", "pass", "fail", "warn", "invalid"], "warn": True}}, "required": ["label"]}}}, "required": ["items"]},
    "ladder": {
        "trial": "without-rows",
        "fields": {
            **FRAME, "rows": {"list": {"fields": {"arm": "arm-ref", "case": "case-ref", "k": "count", "n": "count", "invalid": "count", "note": "text", "cases": "count"}, "required": ["k", "n"], "kn": [["k", "n"]]}},
            "by": {"enum": ["arm", "case"]}, "case": "case", "cases": {"list": "case"}, "arms": {"list": "arm"}, "identical": {"list": {"list": "arm"}}, "baseline": "text",
            "sort": {"enum": ["identity", "rate"], "warn": True}, "references": {"list": {"fields": {"value": "rate", "label": "text"}, "required": ["value", "label"]}}, "pairs": {"list": CASE_PAIR},
        },
    },
    "tapestry": {"trial": "always", "fields": {**FRAME, "arms": {"list": "arm"}, "cases": {"list": "case"}, "transpose": "boolean", "groups": {"list": GROUP}, "pairs": {"list": CASE_PAIR}}},
    "checks": {"trial": "always", "fields": {**FRAME, "arms": {"list": "arm"}, "checks": {"list": "check"}, "cases": {"list": "case"}, "by": {"enum": ["case", "check"], "warn": True}, "pairs": {"list": CASE_PAIR}, "required": "boolean"}},
    "pairwise": {"trial": "always", "fields": {**FRAME, "pair": "pair"}},
    "cost": {"trial": "always", "fields": {**FRAME, "measures": {"list": "measure"}, "arms": {"list": "arm"}}},
    "invalid": {"trial": "always", "fields": {**FRAME}},
    "ledger": {"trial": "always", "fields": {**FRAME}},
    "plan": {"trial": "always", "fields": {**FRAME}},
    "setup": {
        "trial": "without-settings",
        "fields": {**FRAME, "arms": {"list": "arm"}, "baseline": "arm", "identical": {"list": {"list": "arm"}}, "hide": {"list": "text"}, "settings": {"record": "any", "keys": "arm-ref"}, "judge": "any", "pairs": {"oneOf": [AUTO_OFF, PAIR_LIST]}},
    },
    "cases": {"trial": "always", "fields": {**FRAME, "cases": {"list": "case"}, "arms": {"list": "arm"}, "groups": {"list": GROUP}, "pairs": {"oneOf": [AUTO_OFF, PAIR_SPECS]}, "index": "boolean", "descriptions": {"record": "prose", "keys": "case-ref"}}},
    "failures": {"trial": "always", "fields": {**FRAME, "cases": {"list": "case"}, "arms": {"list": "arm"}, "by": {"enum": ["cause", "case"], "warn": True}, "reasons": "count"}},
    "contrast": {
        "trial": "without-rows",
        "fields": {
            **FRAME,
            "rows": {"list": {"fields": {"label": "text", "arm": "arm-ref", "vs": "arm-ref", "note": "text", "k1": "count", "n1": "count", "k2": "count", "n2": "count", "invalid1": "count", "invalid2": "count", "identical": "boolean"}, "required": ["k1", "n1", "k2", "n2"], "kn": [["k1", "n1"], ["k2", "n2"]]}},
            "baseline": {"oneOf": ["arm", {"list": "arm"}]}, "arms": {"list": "arm"}, "cases": {"list": "case"}, "a": CONTRAST_SIDE, "b": CONTRAST_SIDE,
            "pair": {"oneOf": ["text", {"fields": {"suffix": "text"}, "required": ["suffix"]}]}, "by": {"enum": ["arm", "case", "none"], "warn": True}, "identical": {"list": {"list": "arm"}},
            "threshold": {"oneOf": ["number", {"fields": {"value": "number", "label": "text"}, "required": ["value"]}]}, "sort": {"enum": ["identity", "difference"], "warn": True}, "method": "boolean",
        },
    },
    "text": {"fields": {**FRAME, "text": "prose"}, "required": ["text"]},
    "callout": {"fields": {"title": "text", "id": "text", "tone": {"enum": [*TONES, "note", "limit"], "warn": True}, "label": "text", "text": "prose"}, "required": ["text"]},
    "list": {"fields": {**FRAME, "items": {"list": {"oneOf": ["text", {"fields": {"text": "text", "tone": TONE, "detail": "text"}, "required": ["text"]}]}}, "ordered": "boolean"}, "required": ["items"]},
    "facts": {"fields": {**FRAME, "items": {"list": {"fields": {"label": "text", "value": CELL_VALUE, "mono": "boolean"}, "required": ["label"]}}}, "required": ["items"]},
    "table": {"fields": {**FRAME, "columns": {"list": "text"}, "rows": {"list": {"list": CELL}}, "numeric": {"list": "count"}, "rowHeader": "boolean"}, "required": ["columns", "rows"]},
    "matrix": {
        "fields": {
            **FRAME, "columns": {"list": {"fields": {"id": "text", "label": "text", "arm": "boolean"}, "required": ["id"]}},
            "rows": {"list": {"fields": {"id": "text", "label": "text", "detail": "text"}, "required": ["id", "label"]}},
            "cells": {"list": {"fields": {"row": "text", "column": "text", "status": {"enum": [*TONES, "missing"]}, "text": "text", "note": "text"}, "required": ["row", "column"]}},
        },
        "required": ["columns", "rows", "cells"],
    },
    "intervals": {
        "fields": {
            **FRAME, "rows": {"list": {"fields": {"label": "text", "arm": "arm-ref", "k": "count", "n": "count", "value": NUMBER_OR_NULL, "lo": NUMBER_OR_NULL, "hi": NUMBER_OR_NULL, "note": "text"}, "kn": [["k", "n"]]}},
            "domain": {"list": "number"}, "unit": "text", "percent": "boolean", "reference": {"fields": {"value": "number", "label": "text"}, "required": ["value", "label"]},
        },
        "required": ["rows"],
    },
    "bars": {
        "fields": {
            **FRAME, "segments": {"list": {"fields": {"id": "text", "label": "text", "tone": TONE}, "required": ["id", "label"]}},
            "rows": {"list": {"fields": {"label": "text", "arm": "arm-ref", "values": {"record": NUMBER_OR_NULL}, "note": "text"}, "required": ["values"]}},
        },
        "required": ["segments", "rows"],
    },
    "trend": {
        "fields": {
            **FRAME, "stages": {"list": "text"},
            "series": {"list": {"fields": {"label": "text", "arm": "arm-ref", "points": {"list": {"fields": {"stage": "text", "k": "count", "n": "count", "value": NUMBER_OR_NULL, "lo": NUMBER_OR_NULL, "hi": NUMBER_OR_NULL}, "required": ["stage"], "kn": [["k", "n"]]}}}, "required": ["label", "points"]}},
            "percent": "boolean", "unit": "text",
        },
        "required": ["stages", "series"],
    },
    "excerpts": {"fields": {**FRAME, "items": {"list": {"fields": {"text": "text", "source": "text", "arm": "arm-ref", "outcome": {"enum": ["pass", "fail", "invalid"]}, "note": "text"}, "required": ["text"]}}}, "required": ["items"]},
    "diagram": {"fields": {**FRAME, "source": "text", "caption": "text", "config": "any"}, "required": ["source"]},
    "scorecard": {"comparison": "without-data", "fields": {**COMPARE, "metrics": {"list": "metric"}, "orient": {"enum": ["columns", "rows"], "warn": True}, "center": CENTER}},
    "metric": {"comparison": "without-data", "fields": {**COMPARE, "by": {"enum": ["alternative", "case", "group"], "warn": True}, "depth": "count", "sort": {"enum": ["identity", "value"], "warn": True}, "threshold": THRESHOLD, "center": CENTER, "method": "boolean"}},
    "difference": {
        "comparison": "without-data",
        "fields": {**COMPARE, "metrics": {"list": "metric"}, "pairs": {"oneOf": [{"enum": ["baseline", "all"], "warn": True}, {"list": ALTERNATIVES}]}, "threshold": THRESHOLD, "identical": {"oneOf": [{"list": ALTERNATIVES}, "boolean"]}, "sort": {"enum": ["identity", "difference"], "warn": True}, "center": CENTER, "method": "boolean"},
    },
    "hierarchy": {"comparison": "without-data", "fields": {**COMPARE, "depth": "count", "between": "boolean", "center": CENTER, "method": "boolean"}},
    "alternatives": {"comparison": "without-data", "fields": {**FRAME, "data": "any", "alternatives": ALTERNATIVES, "baseline": "alternative", "hide": {"list": "text"}, "identical": {"list": {"list": "alternative-ref"}}}},
    "preferences": {"comparison": "without-data", "fields": {**FRAME, "data": "any", "metric": "metric", "alternatives": ALTERNATIVES, "cases": {"list": "comparison-case"}, "groups": {"list": "text"}}},
    "decision-matrix": {
        "fields": {**FRAME, "data": "any", "criteria": {"list": {"fields": CRITERION_FIELDS, "required": ["id"]}}, "cells": {"list": DECISION_CELL}, "alternatives": {"list": {"oneOf": ["alternative-ref", {"fields": {"id": "alternative-ref", "label": "text"}, "required": ["id"]}]}}, "scale": DECISION_SCALE},
        "required": ["criteria"],
    },
    "observations": {"comparison": "without-data", "fields": {**FRAME, "data": "any", "alternatives": ALTERNATIVES, "cases": {"list": "comparison-case"}, "metrics": {"list": "metric"}, "metric": "metric", "groups": {"list": "text"}}},
    "decisions": {"collection": "always", "fields": SUBSET},
    "reports": {"collection": "always", "fields": {**SUBSET, "layouts": {"list": {"enum": ["cards", "list", "table", "matrix"], "warn": True}}}},
    "shifts": {"collection": "always", "fields": SUBSET},
    "cost-gain": {"collection": "always", "fields": SUBSET},
    "timeline": {"collection": "always", "fields": SUBSET},
    "matchups": {"collection": "always", "fields": {**SUBSET, "pairs": {"list": PAIR}}},
    "report-compare": {"collection": "always", "fields": {**FRAME, "a": "member", "b": "member"}, "required": ["a", "b"]},
}
BLOCK_TYPES = sorted(BLOCKS)

SECTION = {"id": "section-id", "title": "text", "label": "text", "lead": "prose", "reading": "prose", "blocks": {"list": "block"}}
SPEC = {
    "fields": {
        "title": "string", "kicker": "text", "summary": "prose",
        "meta": {"list": {"fields": {"label": "text", "value": "text"}, "required": ["label", "value"]}},
        "arms": {"list": {"fields": {"id": "arm-ref", "label": "text", "note": "text"}, "required": ["id"]}},
        "sections": {"list": {"fields": SECTION, "required": ["title", "blocks"]}},
        "footer": "text", "trial": "any", "cases": {"record": "text", "keys": "case-ref"}, "problems": "any", "comparison": "any", "collection": "any", "story": "any",
    },
    "required": ["title", "sections"],
}
# A collection of reports (collection.ts).
MEMBER = {"fields": {"id": "member-id", "theme": "theme", "title": "text", "label": "text", "note": "text", "date": "text", "follows": "member", "models": {"list": "text"}, "trial": "any", "comparison": "any", "spec": "any", "narrative": "any"}, "required": ["id"]}
COLLECTION = {
    "fields": {"title": "text", "kicker": "text", "summary": "prose", "footer": "text", "story": "any", "readings": {"record": "prose"}, "themes": {"list": {"fields": {"id": "text", "label": "text", "summary": "prose"}, "required": ["id"]}}, "members": {"list": MEMBER}, "pairs": {"list": PAIR}},
    "required": ["members"],
}
MEMBER_ID = re.compile(r"[A-Za-z][\w.-]*", re.ASCII)
# Section ids of the trial composition (compose.ts SECTION_IDS), and earlier ids
# it still accepts, for include, exclude, after and append.
DEFAULT_SECTIONS = ["verdict", "setup", "arms", "cases", "grid", "failures", "checks", "pairwise", "cost", "invalid", "runs"]
# Sections composed only when include names them.
OPT_IN_SECTIONS = ["grid"]
SECTION_ALIASES = {"plan": "setup"}
SECTION_NAMES = [*DEFAULT_SECTIONS, *SECTION_ALIASES]


def section_key(ident: str) -> str:
    return SECTION_ALIASES.get(ident, ident)


NARRATIVE = {
    "fields": {
        "title": "text", "question": "text", "summary": "prose", "kicker": "text",
        "decision": {"fields": {**FRAME, **VERDICT, "rule": "any"}, "required": ["headline"], "empty": {"headline": 'write the decision in one sentence, or delete "decision" to report the results without one'}},
        "arms": {"oneOf": [{"list": {"fields": {"id": "arm-label", "label": "text", "note": "text"}, "required": ["id"]}}, {"record": {"fields": {"label": "text", "note": "text"}}, "keys": "arm-label"}]},
        "cases": {"record": "text", "keys": "case-ref"},
        "identical": {"list": {"list": "arm"}},
        "groups": {"list": GROUP},
        "pairs": {"list": {"oneOf": [{"list": "case"}, {"fields": {"base": "case", "variant": "case", "label": "text"}, "required": ["base", "variant"]}]}},
        "baseline": "arm",
        "threshold": {"oneOf": ["number", {"fields": {"value": "number", "label": "text"}, "required": ["value"]}]},
        "include": {"list": "text"}, "exclude": {"list": "text"},
        "sections": {"list": {"fields": {**SECTION, "after": "text"}, "required": ["title", "blocks"]}},
        "append": {"record": {"list": "block"}},
        "footer": "text", "story": "any", "readings": {"record": "prose"},
    },
}
MEASURES = ["output_tokens", "input_tokens", "seconds", "commands", "total_cost_usd"]

# A comparison of any alternatives (src/comparison-model.ts), as validate_comparison reads it.
METRIC_KINDS = ["binary", "numeric", "ordinal", "count", "rank", "preference"]
GROUP_PATH = {"oneOf": ["text", {"list": "text"}]}
COMPARISON = {
    "fields": {
        "title": "text", "question": "text", "summary": "prose",
        "alternatives": {"list": {"fields": {"id": "string", "label": "text", "description": "text", "group": GROUP_PATH, "attributes": {"record": {"oneOf": ["text", "boolean", "null"]}}, "content": "text", "note": "text"}, "required": ["id"]}},
        "cases": {"list": {"fields": {"id": "string", "label": "text", "description": "text", "group": GROUP_PATH}, "required": ["id"]}},
        "metrics": {"list": {"fields": {"id": "string", "label": "text", "kind": {"enum": METRIC_KINDS}, "better": {"enum": ["higher", "lower", "none"]}, "unit": "text", "levels": {"list": "text"}, "primary": "boolean", "description": "text", "threshold": "number"}, "required": ["id", "kind"]}},
        "observations": {"list": {"fields": {"alternative": "alternative", "metric": "metric", "case": "comparison-case", "value": {"oneOf": ["boolean", "text", "null"]}, "n": "count", "unit": "text", "valid": "boolean", "invalid_reason": "text", "note": "text", "excerpt": "text", "source": "text", "id": "text"}, "required": ["alternative", "metric"]}},
        "aggregates": {"list": {"fields": {"alternative": "alternative", "metric": "metric", "case": "comparison-case", "k": "count", "n": "count", "mean": "number", "sd": "number", "median": "number", "lo": "number", "hi": "number", "counts": {"record": "count"}, "source": "text", "note": "text"}, "required": ["alternative", "metric"]}},
        "preferences": {"list": {"fields": {"a": "alternative", "b": "alternative", "winner": {"oneOf": ["text", "null"]}, "case": "comparison-case", "metric": "metric", "judge": "text", "note": "text"}, "required": ["a", "b"]}},
        "rankings": {"list": {"fields": {"order": ALTERNATIVES, "case": "comparison-case", "metric": "metric", "judge": "text"}, "required": ["order"]}},
        "baseline": "alternative",
        "identical": {"list": ALTERNATIVES},
        "decision_rule": "prose",
        "sources": {"list": {"fields": {"label": "text", "href": "text", "note": "text"}, "required": ["label"]}},
    },
    "required": ["alternatives", "metrics"],
}
# Section ids of the comparison composition (comparison-compose.ts), and other names it accepts.
COMPARISON_SECTIONS = ["verdict", "compared", "results", "differences", "groups", "cases", "judgments", "decision", "observations", "sources"]
COMPARISON_ALIASES = {"setup": "compared", "alternatives": "compared", "metrics": "results", "hierarchy": "groups", "preferences": "judgments", "pairwise": "judgments", "matrix": "decision", "ledger": "observations", "runs": "observations"}
COMPARISON_NAMES = [*COMPARISON_SECTIONS, *COMPARISON_ALIASES]
COMPARISON_NARRATIVE = {
    "fields": {
        "title": "text", "question": "text", "summary": "prose", "kicker": "text",
        "decision": NARRATIVE["fields"]["decision"],
        "alternatives": {"oneOf": [{"list": {"fields": {"id": "alternative-ref", "label": "text", "note": "text"}, "required": ["id"]}}, {"record": {"fields": {"label": "text", "note": "text"}}, "keys": "alternative-ref"}]},
        "baseline": "alternative",
        "identical": {"list": ALTERNATIVES},
        "criteria": {"list": {"fields": CRITERION_FIELDS}},
        "cells": {"list": DECISION_CELL},
        "scale": DECISION_SCALE,
        "include": {"list": "text"}, "exclude": {"list": "text"},
        "sections": {"list": {"fields": {**SECTION, "after": "text"}, "required": ["title", "blocks"]}},
        "append": {"record": {"list": "block"}},
        "footer": "text", "story": "any", "readings": {"record": "prose"},
    },
}


def comparison_key(ident: str) -> str:
    return COMPARISON_ALIASES.get(ident, ident)

DESCRIPTIONS = {
    "text": "text", "string": "text", "prose": "text or a list of paragraphs", "number": "a number", "count": "a whole number of 0 or more",
    "rate": "a number from 0 to 1", "boolean": "true or false", "null": "null", "any": "any value", "block": "a block object",
    "arm": "an arm id", "arm-ref": "an arm id", "arm-label": "an arm id", "case": "a case id", "case-ref": "a case id", "check": "a check name", "pair": "a pairwise key",
    "measure": "a measure id", "section-id": "a section id", "alternative": "an alternative id", "alternative-ref": "an alternative id", "metric": "a metric id", "comparison-case": "a case id",
    "member": "a report id", "member-id": "a report id", "theme": "a theme id",
}
IDS = {
    "arm": ("arms", "an arm in this trial", "arms in this trial", "error", ""),
    "arm-ref": ("arms", "an arm in this trial", "arms in this trial", "warning", "; it gets an identity color of its own"),
    "arm-label": ("arms", "an arm in this trial", "arms in this trial", "warning", ", so this entry is not used"),
    "case": ("cases", "a case in this trial", "cases in this trial", "error", ""),
    "case-ref": ("cases", "a case in this trial", "cases in this trial", "warning", ", so this label is not used"),
    "check": ("checks", "a recorded pass/fail check in this trial", "checks in this trial", "error", ""),
    "pair": ("pairs", "a pairwise comparison in this trial", "pairwise comparisons in this trial", "error", ""),
    "measure": (None, "a cost measure", "measures", "error", ""),
    "alternative": ("alternatives", "an alternative in this comparison", "alternatives in this comparison", "error", ""),
    "alternative-ref": ("alternatives", "an alternative in this comparison", "alternatives in this comparison", "warning", ", so this entry is not used"),
    "metric": ("metrics", "a metric in this comparison", "metrics in this comparison", "error", ""),
    "comparison-case": ("ccases", "a case defined in this comparison", "cases in this comparison", "warning", "; it is shown by its id"),
    "member": ("members", "a report in this collection", "reports in this collection", "error", ""),
    "theme": ("themes", "a theme in this collection", "themes in this collection", "warning", ""),
}
FROM_COMPARISON = ("alternatives", "metrics", "ccases")
FROM_COLLECTION = ("members", "themes")
SECTION_ID = re.compile(r"[A-Za-z][\w:.-]*", re.ASCII)
PLAIN_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
NUMERIC_TEXT = re.compile(r"\s*-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*", re.ASCII)


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def is_text(v) -> bool:
    return isinstance(v, str) or is_number(v)


def is_whole(v) -> bool:
    return is_number(v) and float(v).is_integer()


def keys_of(v: dict) -> list[str]:
    return sorted(k for k in v if not k.startswith("$"))


def clip(value: str, limit: int = 60) -> str:
    return value[: limit - 1] + "…" if len(value) > limit else value


def number_text(v) -> str:
    """A number as JavaScript's String() writes it, for messages both checkers share."""
    if isinstance(v, int) or (float(v).is_integer() and abs(v) < 1e21):
        return str(int(v))
    return repr(float(v))


def found(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, list):
        return "a list"
    if isinstance(v, dict):
        return "an object"
    if isinstance(v, str):
        return f'text "{clip(v)}"'
    if isinstance(v, bool):
        return "true" if v else "false"
    if is_number(v):
        return f"the number {number_text(v)}"
    return "a value JSON cannot hold"


def list_of(items: list[str], limit: int = 12) -> str:
    shown = ", ".join(clip(x, 40) for x in items[:limit])
    return f"{shown}, and {len(items) - limit} more" if len(items) > limit else shown


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def distance(a: str, b: str) -> int:
    """Edit distance with adjacent transpositions (optimal string alignment)."""
    rows = [[i] + [0 if i else j for j in range(1, len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            rows[i][j] = min(rows[i - 1][j] + 1, rows[i][j - 1] + 1, rows[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                rows[i][j] = min(rows[i][j], rows[i - 2][j - 2] + 1)
    return rows[len(a)][len(b)]


def suggest(value: str, options: list[str]) -> str | None:
    """The option a misspelling most likely meant: a case-insensitive match, else
    the closest within one edit per three characters (at most two)."""
    lower = value.lower()
    for option in options:
        if option.lower() == lower:
            return option
    best, best_distance = None, math.inf
    for option in options:
        d, limit = distance(lower, option.lower()), min(2, max(1, len(option) // 3))
        if d <= limit and d < best_distance:
            best, best_distance = option, d
    return best


def describe(f) -> str:
    if isinstance(f, str):
        return DESCRIPTIONS.get(f, f)
    if "enum" in f:
        return "one of " + ", ".join(f["enum"])
    if "list" in f:
        return "a list"
    if "oneOf" in f:
        return " or ".join(dict.fromkeys(describe(a) for a in f["oneOf"]))
    return "an object"


def fits(v, f) -> bool:
    if isinstance(f, str):
        if f == "any":
            return True
        if f == "null":
            return v is None
        if f == "boolean":
            return isinstance(v, bool)
        if f in ("number", "count", "rate"):
            return is_number(v)
        if f == "text":
            return is_text(v)
        if f == "prose":
            return is_text(v) or isinstance(v, list)
        if f == "block":
            return isinstance(v, dict)
        return isinstance(v, str)
    if "enum" in f:
        return isinstance(v, str)
    if "list" in f:
        return isinstance(v, list)
    if "oneOf" in f:
        return any(fits(v, a) for a in f["oneOf"])
    return isinstance(v, dict)


def type_hint(v, f) -> str:
    if f in ("number", "count", "rate") and isinstance(v, str) and NUMERIC_TEXT.fullmatch(v):
        return "write the number without quotes"
    if f == "boolean" and v in ("true", "false"):
        return "write true or false without quotes"
    if isinstance(f, dict) and "list" in f and not isinstance(v, list):
        return "write a list in square brackets, even for one item"
    if f == "count" and is_number(v):
        return "counts are whole numbers of 0 or more"
    if f == "rate" and is_number(v):
        return "rates are fractions: write 0.75 for 75%"
    return f"write {describe(f)}"


def canon(v) -> str:
    """A value as canonical text (keys sorted), as src/validate.ts canon() writes it."""
    if isinstance(v, list):
        return "[" + ",".join(canon(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(f"{json.dumps(k, ensure_ascii=False)}:{canon(v[k])}" for k in sorted(v)) + "}"
    if isinstance(v, bool) or v is None:
        return json.dumps(v)
    if is_number(v):
        return number_text(v)
    return json.dumps(v, ensure_ascii=False)


def is_comparison(v) -> bool:
    return isinstance(v, dict) and isinstance(v.get("alternatives"), list)


def is_collection(v) -> bool:
    return isinstance(v, dict) and isinstance(v.get("members"), list)


def is_calendar_date(v: str) -> bool:
    """A real calendar day written YYYY-MM-DD: 2026-02-30 and 2026-99-99 are not."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v, re.ASCII):
        return False
    try:
        datetime.date.fromisoformat(v)
    except ValueError:
        return False
    return True


def known_from(trial, comparison=None, collection=None) -> dict:
    known = {"trial": False, "arms": [], "cases": [], "checks": [], "pairs": [], "settings": {}, "comparison": False, "alternatives": [], "metrics": [], "ccases": [], "collection": False, "members": [], "themes": [], "ran_arms": [], "ran_cases": []}
    if is_collection(collection):
        known["collection"] = True
        for name in ("members", "themes"):
            for x in collection.get(name) if isinstance(collection.get(name), list) else []:
                if isinstance(x, dict) and isinstance(x.get("id"), str) and x["id"] not in known[name]:
                    known[name].append(x["id"])
    if is_comparison(comparison):
        known["comparison"] = True
        for name, key in (("alternatives", "alternatives"), ("metrics", "metrics"), ("ccases", "cases")):
            for x in comparison.get(key) if isinstance(comparison.get(key), list) else []:
                if isinstance(x, dict) and isinstance(x.get("id"), str) and x["id"] not in known[name]:
                    known[name].append(x["id"])
    if not isinstance(trial, dict) or not isinstance(trial.get("runs"), list):
        return known
    known["trial"] = True

    def add(name: str, v) -> None:
        if isinstance(v, str) and v not in known[name]:
            known[name].append(v)

    plan = trial.get("plan") if isinstance(trial.get("plan"), dict) else {}
    if isinstance(plan.get("arms"), dict):
        for arm, entry in plan["arms"].items():
            add("arms", arm)
            if isinstance(entry, dict):
                known["settings"][arm] = entry
    if isinstance(plan.get("scenarios"), list):
        for scenario in plan["scenarios"]:
            if isinstance(scenario, dict):
                add("cases", scenario.get("name"))
    for run in trial["runs"]:
        if not isinstance(run, dict):
            continue
        add("arms", run.get("arm"))
        add("cases", run.get("scenario"))
        add("ran_arms", run.get("arm"))
        add("ran_cases", run.get("scenario"))
        if isinstance(run.get("passed"), bool) and isinstance(run.get("checks"), dict):
            for key, value in run["checks"].items():
                if isinstance(value, bool):
                    add("checks", key)
    if isinstance(trial.get("pairwise"), dict):
        for key in trial["pairwise"]:
            add("pairs", key)
    return known


class Checker:
    def __init__(self, known: dict, root: str):
        self.known, self.root, self.types, self.problems = known, root, BLOCK_TYPES, []

    def add(self, level: str, where: str, message: str, hint: str | None = None) -> None:
        problem = {"level": level, "where": where or self.root, "message": message}
        if hint:
            problem["hint"] = hint
        self.problems.append(problem)

    @staticmethod
    def join(where: str, key) -> str:
        if isinstance(key, int):
            return f"{where}[{key}]"
        if not PLAIN_KEY.fullmatch(key):
            return f"{where}[{json.dumps(key, ensure_ascii=False)}]"
        return f"{where}.{key}" if where else key

    def type(self, v, f, where: str) -> None:
        self.add("error", where, f"expected {describe(f)}, found {found(v)}", type_hint(v, f))

    def check(self, v, f, where: str) -> None:
        if isinstance(f, str):
            return self.scalar(v, f, where)
        if "enum" in f:
            return self.choice(v, f, where)
        if "list" in f:
            if not isinstance(v, list):
                return self.type(v, f, where)
            for i, x in enumerate(v):
                self.check(x, f["list"], self.join(where, i))
            return None
        if "record" in f:
            if not isinstance(v, dict):
                return self.type(v, f, where)
            for k in keys_of(v):
                at = self.join(where, k)
                if f.get("keys"):
                    self.id(k, f["keys"], at)
                if v[k] is not None:
                    self.check(v[k], f["record"], at)
            return None
        if "oneOf" in f:
            alternative = next((a for a in f["oneOf"] if fits(v, a)), None)
            return self.type(v, f, where) if alternative is None else self.check(v, alternative, where)
        return self.shape(v, f, where)

    def scalar(self, v, kind: str, where: str) -> None:
        if kind == "any":
            return None
        if kind == "block":
            return self.block(v, where)
        if not fits(v, kind):
            return self.type(v, kind, where)
        if kind == "count" and (not is_whole(v) or v < 0):
            return self.type(v, kind, where)
        if kind == "rate" and (v < 0 or v > 1):
            return self.type(v, kind, where)
        if kind == "prose" and isinstance(v, list):
            for i, x in enumerate(v):
                if not is_text(x):
                    self.type(x, "text", self.join(where, i))
        if kind == "member-id" and not MEMBER_ID.fullmatch(v):
            self.add("error", where, f'"{clip(v)}" cannot be a report id, since links name reports by id', "start with a letter and use only letters, digits, _ . or -")
        if kind == "section-id" and not SECTION_ID.fullmatch(v):
            self.add("warning", where, f'"{clip(v)}" cannot be used as a section id, so the section gets a generated one', "start with a letter and use only letters, digits, _ : . or -")
        if kind in IDS:
            self.id(v, kind, where)
        return None

    def choice(self, v, f: dict, where: str) -> None:
        if isinstance(v, str) and (v in f["enum"] or (f.get("fold") and v.lower() in f["enum"])):
            return None
        if not isinstance(v, str):
            return self.type(v, f, where)
        s = suggest(v, f["enum"])
        lead = f'did you mean "{s}"? Allowed' if s else "allowed"
        self.add("warning" if f.get("warn") else "error", where, f'"{clip(v)}" is not one of the allowed values', f'{lead} values: {", ".join(f["enum"])}')
        return None

    def id(self, value: str, kind: str, where: str) -> None:
        spec = IDS.get(kind)
        if not spec:
            return
        source, noun, many, level, tail = spec
        of_comparison, of_collection = source in FROM_COMPARISON, source in FROM_COLLECTION
        if source and not (self.known["collection"] if of_collection else (self.known["comparison"] and (source != "ccases" or self.known["ccases"])) if of_comparison else self.known["trial"]):
            return
        options = self.known[source] if source else MEASURES
        if value in options:
            return
        s = suggest(value, options)
        hint = f'did you mean "{s}"?' if s else f"{many}: {list_of(options)}" if options else f"this {'collection' if of_collection else 'comparison' if of_comparison else 'trial'} has no {re.sub(r' in this (trial|comparison|collection)$', '', many)}"
        self.add(level, where, f'"{clip(value)}" is not {noun}{tail}', hint)

    def shape(self, v, f: dict, where: str, hooks: dict | None = None, skip: tuple = ()) -> None:
        if not isinstance(v, dict):
            return self.type(v, f, where)
        hooks = hooks or {}
        required = f.get("required", [])
        for name in required:
            x = v.get(name)
            if x is None:
                self.add("error", where, f'missing required field "{name}"', f"required here: {', '.join(required)}")
            elif isinstance(x, str) and not x.strip() and f["fields"].get(name) in ("text", "string", "prose"):
                self.add("error", self.join(where, name), f'"{name}" is empty', f.get("empty", {}).get(name) or "write the text the report should show, or remove the entry")
        for name, field in f["fields"].items():
            x = v.get(name)
            if x is None:
                continue
            at = self.join(where, name)
            self.check(x, field, at)
            if name in hooks:
                hooks[name](x, at)
        names = [n for n in f["fields"] if n not in skip]
        for k in keys_of(v):
            if k in f["fields"] or k in skip:
                continue
            s = suggest(k, names)
            self.add("warning", self.join(where, k), f'unknown field "{clip(k)}" is not used', f'did you mean "{s}"?' if s else f"fields here: {list_of(names, 30)}")
        for k, n in f.get("kn", []):
            passed, valid = v.get(k), v.get(n)
            if is_number(passed) and is_number(valid) and passed > valid:
                self.add("error", where, f"{k} ({number_text(passed)}) is larger than {n} ({number_text(valid)})", f"{k} counts passed runs and {n} counts valid runs, so {k} cannot be larger than {n}")
        return None

    def block(self, v, where: str) -> None:
        if not isinstance(v, dict):
            return self.add("error", where, f"expected a block object, found {found(v)}", 'a block is an object with a "type", such as {"type": "text", "text": "…"}')
        kind = v.get("type")
        if not isinstance(kind, str) or not kind:
            return self.add("error", where, 'the block has no "type"', f"block types: {list_of(self.types, 40)}")
        if kind not in self.types:
            s = suggest(kind, self.types)
            return self.add("error", where, f'unknown block type "{clip(kind)}"', f'did you mean "{s}"?' if s else f"block types: {list_of(self.types, 40)}")
        schema = BLOCKS.get(kind)
        if not schema:
            return None
        at = f"{where} ({kind})"
        # A block that carries its own comparison is checked against it.
        if is_comparison(v.get("data")):
            own = known_from(None, v["data"])
            inner = Checker({**self.known, "comparison": True, "alternatives": own["alternatives"], "metrics": own["metrics"], "ccases": own["ccases"]}, self.root)
            inner.block_body(kind, schema, v, at)
            self.problems.extend(inner.problems)
            return None
        return self.block_body(kind, schema, v, at)

    def block_body(self, kind: str, schema: dict, v: dict, at: str) -> None:
        needs = schema.get("trial")
        own = needs[len("without-"):] if needs and needs.startswith("without-") else None
        if not self.known["trial"] and (needs == "always" or (own is not None and v.get(own) is None)):
            self.add("error", at, f"the {kind} block needs trial data{f' or its own {chr(34)}{own}{chr(34)}' if own is not None else ''}", "pass --trial to report.py, or set the specification's \"trial\" field")
        if schema.get("collection") and not self.known["collection"]:
            self.add("error", at, f"the {kind} block needs a collection", "pass --collection to report.py, or set the specification's \"collection\" field")
        if schema.get("comparison") and not self.known["comparison"] and v.get("data") is None:
            self.add("error", at, f'the {kind} block needs comparison data or its own "data"', "pass --data or --csv to report.py, or set the specification's \"comparison\" field")

        def data(value, where: str) -> None:
            if not is_comparison(value):
                self.add("error", where, "is not comparison data", 'a comparison is {"alternatives": [ … ], "metrics": [ … ]}; see catalog.md')

        self.shape(v, schema, at, {"data": data}, skip=("type",))
        self.block_rules(kind, v, at)
        return None

    def block_rules(self, kind: str, v: dict, at: str) -> None:
        """Cross-field rules a field table cannot state."""
        def strings(items, key: str) -> list[str]:
            return [x[key] for x in items if isinstance(x, dict) and isinstance(x.get(key), str)] if isinstance(items, list) else []

        def refer(value, options: list[str], where: str, noun: str, tail: str) -> None:
            if not isinstance(value, str) or value in options:
                return
            s = suggest(value, options)
            self.add("warning", where, f'"{clip(value)}" is not {noun}, so {tail}', f'did you mean "{s}"?' if s else f"ids here: {list_of(options)}" if options else "this block defines none")

        if kind == "ladder" and isinstance(v.get("rows"), list):
            key = "case" if v.get("by") == "case" else "arm"
            for i, row in enumerate(v["rows"]):
                if isinstance(row, dict) and row.get(key) is None:
                    self.add("error", f"{at}.rows[{i}]", f'missing required field "{key}"', f"rows by {key} name the {key} each count belongs to")
        if kind == "ladder" and isinstance(v.get("baseline"), str) and v.get("by") != "case":
            rows = strings(v["rows"], "arm") if isinstance(v.get("rows"), list) else None
            options = rows if rows is not None else (self.known["arms"] if self.known["trial"] else None)
            if options is not None and v["baseline"] not in options:
                s = suggest(v["baseline"], options)
                noun = "an arm in this block's rows" if rows is not None else "an arm in this trial"
                many = "arms in the rows" if rows is not None else "arms in this trial"
                self.add("error", f"{at}.baseline", f'"{clip(v["baseline"])}" is not {noun}', f'did you mean "{s}"?' if s else f"{many}: {list_of(options)}")
        if kind == "table" and isinstance(v.get("columns"), list) and isinstance(v.get("rows"), list):
            for i, row in enumerate(v["rows"]):
                if isinstance(row, list) and len(row) > len(v["columns"]):
                    self.add("warning", f"{at}.rows[{i}]", f"{plural(len(row), 'cell')} for {plural(len(v['columns']), 'column')}; the extra cells are not shown", "add a column or remove the extra cells")
        if kind == "matrix" and isinstance(v.get("cells"), list):
            rows, columns = strings(v.get("rows"), "id"), strings(v.get("columns"), "id")
            for i, cell in enumerate(v["cells"]):
                if isinstance(cell, dict):
                    refer(cell.get("row"), rows, f"{at}.cells[{i}].row", "a row id of this matrix", "the cell is not shown")
                    refer(cell.get("column"), columns, f"{at}.cells[{i}].column", "a column id of this matrix", "the cell is not shown")
        if kind == "bars" and isinstance(v.get("rows"), list):
            segments = strings(v.get("segments"), "id")
            for i, row in enumerate(v["rows"]):
                if isinstance(row, dict) and isinstance(row.get("values"), dict):
                    for k in keys_of(row["values"]):
                        refer(k, segments, self.join(f"{at}.rows[{i}].values", k), "a segment id", "this value is not drawn")
        if kind == "trend" and isinstance(v.get("series"), list):
            stages = [s for s in v["stages"] if isinstance(s, str)] if isinstance(v.get("stages"), list) else []
            for i, series in enumerate(v["series"]):
                if isinstance(series, dict) and isinstance(series.get("points"), list):
                    for j, point in enumerate(series["points"]):
                        if isinstance(point, dict):
                            refer(point.get("stage"), stages, f"{at}.series[{i}].points[{j}].stage", "one of the stages", "this point is not drawn")
        domain = v.get("domain")
        if kind == "intervals" and isinstance(domain, list) and not (len(domain) == 2 and is_number(domain[0]) and is_number(domain[1]) and domain[0] < domain[1]):
            self.add("error", f"{at}.domain", "the domain is not two increasing numbers", "write [low, high], such as [0, 1]")


# --------------------------------------------------------------------------- the story a newcomer needs
#
# What a reader who has never heard of the work needs before the results, as src/validate.ts checks it.

STORY = {
    "fields": {
        "background": "prose", "intent": "prose", "questions": {"list": "text"}, "rule": "prose", "covers": "prose", "notCovered": "prose",
        "alternatives": {"record": "prose"}, "cases": {"record": "prose"},
        "glossary": {"list": {"fields": {"term": "text", "meaning": "prose"}, "required": ["term", "meaning"]}},
    },
    "required": ["background", "intent", "questions", "covers", "notCovered"],
}
STORY_HINT = 'add "story": background, intent, questions, rule, covers and notCovered, with every alternative and case described in plain words; see catalog.md#the-story'
# A sentence that sends the reader to a file for what the report should say itself: a referral phrase followed by a
# path or a document's file name; naming a file as the subject is not one (as src/validate.ts FILE_REF).
FILE_REF = re.compile(r"""(?:\b(?:see(?:\s+also)?|refer(?:red)?\s+to|per|according\s+to|consult|as\s+(?:[a-z]+\s+)?in|(?:described|listed|documented|defined|explained|given|written|set\s+out|spelled\s+out|recorded|kept|stated|specified|detailed|available|covered)\s+in|details?\s+(?:are\s+|is\s+)?in)|(?:^|[.!?;:]\s+|\(\s*)(?:read|open|check))\s+(?:the\s+)?[`"'“‘]?((?:\.{1,2}/|~/|/)?(?:[\w.-]+/)+[\w.-]*\w\.[A-Za-z][A-Za-z0-9]{0,4}|(?:\.{1,2}/|~/|/)[\w.-]*\w\.[A-Za-z][A-Za-z0-9]{0,4}|[\w-][\w.-]*\.(?:md|markdown|txt|rst|adoc|pdf|docx?|html?|json|jsonl|ya?ml|toml|csv|tsv|ipynb|xlsx?|log))(?![\w/])""", re.ASCII | re.IGNORECASE)


def file_pointer(text: str):
    m = FILE_REF.search(text)
    return m.group(1) if m else None
PROSE_BLOCKS = ("text", "callout", "list", "facts", "verdict")
COLLECTION_SECTIONS = ["glance", "reports", "shifts", "cost-gain", "timeline", "matchups"]


def said(v) -> bool:
    return (isinstance(v, str) and v.strip() != "") or (isinstance(v, list) and any(isinstance(x, str) and x.strip() != "" for x in v))


def texts_of(v) -> list[str]:
    return [v] if isinstance(v, str) else [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def file_refs(c, value, where: str) -> None:
    for t in texts_of(value):
        m = file_pointer(t)
        if m:
            c.add("error", where, f'points the reader at "{clip(m)}", which this report does not include', "say here, in plain words, what the reader needs from it")
            return


def pointed_rule(c, narrative: dict, recorded, whose: str) -> None:
    """A recorded decision rule that only points at a file: the narrative states the rule, and the verdict shows that."""
    file = file_pointer(recorded) if isinstance(recorded, str) else None
    if not file or not isinstance(narrative.get("story"), dict) or said(narrative["story"].get("rule")):
        return
    c.add("error", "narrative.story.rule", f'{whose} decision rule points the reader at "{clip(file)}", which this report does not include, so the narrative states the rule', "write the rule in story.rule, in plain words; the verdict shows it in place of the recorded pointer")


ARM_FIELDS, CASE_FIELDS = ("arm", "arm-ref"), ("case", "case-ref")


def named_ids(value, field, out: dict) -> None:
    """The ids a value names where its field holds an arm or a case, and an object flagged as an arm (a matrix column
    with arm: true) by its id, as src/validate.ts namedIds finds them."""
    if field is None or value is None:
        return

    def take(names: list, v) -> None:
        if isinstance(v, str) and v and v not in names:
            names.append(v)

    if isinstance(field, str):
        if field in ARM_FIELDS:
            take(out["arms"], value)
        elif field in CASE_FIELDS:
            take(out["cases"], value)
        return
    if "list" in field:
        for v in value if isinstance(value, list) else []:
            named_ids(v, field["list"], out)
        return
    if "record" in field:
        if not isinstance(value, dict):
            return
        for k in keys_of(value):
            if field.get("keys") in ARM_FIELDS:
                take(out["arms"], k)
            elif field.get("keys") in CASE_FIELDS:
                take(out["cases"], k)
            named_ids(value[k], field["record"], out)
        return
    if "oneOf" in field:
        for f in field["oneOf"]:
            named_ids(value, f, out)
        return
    if "fields" in field:
        if not isinstance(value, dict):
            return
        if field["fields"].get("arm") == "boolean" and value.get("arm") is True:
            take(out["arms"], value.get("id"))
        for k, f in field["fields"].items():
            named_ids(value.get(k), f, out)


def comparison_cases(data: dict) -> list:
    """A comparison's cases as the composition finds them: those it declares, then every case its data name."""
    out: list = []
    for x in data.get("cases") if isinstance(data.get("cases"), list) else []:
        if isinstance(x, dict) and isinstance(x.get("id"), str) and x["id"] not in out:
            out.append(x["id"])
    for key in ("observations", "aggregates", "preferences", "rankings"):
        for x in data.get(key) if isinstance(data.get(key), list) else []:
            if isinstance(x, dict) and isinstance(x.get("case"), str) and x["case"] not in out:
                out.append(x["case"])
    return out


def story_obligations(known: dict, trial, comparison, blocks: list, own: dict, rule: bool) -> dict:
    """Every alternative and case a report draws, from every source of data it uses, as src/validate.ts
    storyObligations finds them: the one place a story's descriptions are required from."""
    alternatives: dict = {}
    cases: list = []
    found = False

    def alt(ident, noun: str) -> None:
        if isinstance(ident, str) and ident and ident not in alternatives:
            alternatives[ident] = noun

    def kase(ident) -> None:
        if isinstance(ident, str) and ident and ident not in cases:
            cases.append(ident)

    def from_comparison(data: dict) -> None:
        nonlocal found
        found = True
        for a in data["alternatives"]:
            if isinstance(a, dict):
                alt(a.get("id"), "alternative")
        for x in comparison_cases(data):
            kase(x)

    if known["trial"]:
        found = True
        for a in known["ran_arms"]:
            alt(a, "arm")
        for x in known["ran_cases"]:
            kase(x)
    if is_comparison(comparison):
        from_comparison(comparison)
    for a in own.get("arms") if isinstance(own.get("arms"), list) else []:
        if isinstance(a, dict):
            found = True
            alt(a.get("id"), "alternative")
    for k in keys_of(own["cases"]) if isinstance(own.get("cases"), dict) else []:
        found = True
        kase(k)
    for b in blocks:
        if not isinstance(b, dict) or not isinstance(b.get("type"), str):
            continue
        if is_comparison(b.get("data")):
            from_comparison(b["data"])
        named = {"arms": [], "cases": []}
        if b["type"] in BLOCKS:
            named_ids(b, BLOCKS[b["type"]], named)
        if named["arms"] or named["cases"]:
            found = True
        for a in named["arms"]:
            alt(a, "arm" if isinstance(trial, dict) and a in known["ran_arms"] else "alternative")
        for x in named["cases"]:
            kase(x)
    if not found:
        return {"rule": rule, "alternatives": None, "cases": None}
    return {"rule": rule, "alternatives": alternatives, "cases": cases if known["trial"] or cases else None}


def blocks_of(owner: dict) -> list:
    """Every block of a specification's or a narrative's own sections, and of its appended blocks."""
    out: list = []
    for sec in owner.get("sections") if isinstance(owner.get("sections"), list) else []:
        if isinstance(sec, dict) and isinstance(sec.get("blocks"), list):
            out.extend(sec["blocks"])
    if isinstance(owner.get("append"), dict):
        for k in keys_of(owner["append"]):
            if isinstance(owner["append"][k], list):
                out.extend(owner["append"][k])
    return out


def story_checks(c, owner: dict, at: str, needs: dict) -> None:
    story, where = owner.get("story"), c.join(at, "story")
    if story is None:
        c.add("error", at, 'missing "story", which tells a reader new to this work what it is about', STORY_HINT)
        return
    c.shape(story, STORY, where)
    if not isinstance(story, dict):
        return
    if needs["rule"] and not said(story.get("rule")):
        c.add("error", where, 'missing "rule": how the decision was to be made, in plain words', "say what result would decide it, so the reader can hold the views below against it")
    if isinstance(story.get("questions"), list) and not story["questions"]:
        c.add("error", c.join(where, "questions"), "lists no question", "write each question or theory the work set out to test, in plain words")
    # A part given but saying nothing (empty, blank, or not words at all, such as a number) tells the reader as little
    # as one left out. A rule the report does not require is checked the same way when given.
    for k in ("background", "intent", "questions", "covers", "notCovered", *(() if needs["rule"] else ("rule",))):
        if k not in story:
            continue
        v = story[k]
        if k == "questions":
            for i, q in enumerate(v if isinstance(v, list) else []):
                if not isinstance(q, str) or not q.strip():
                    c.add("error", c.join(c.join(where, k), i), "is blank", "write the question in plain words, or remove it")
        elif not said(v):
            c.add("error", c.join(where, k), "says nothing", "write it in plain words for a reader new to this work")

    def described(key: str, needed) -> None:
        if needed is None:
            return
        ids = list(needed)
        given = story[key] if isinstance(story.get(key), dict) else {}
        for ident, noun in needed.items():
            if not said(given.get(ident)):
                c.add("error", c.join(where, key), f'does not describe {noun} "{clip(ident)}"', "say in plain words what each one is and how it differs from the others" if key == "alternatives" else "say in plain words why each case exists and what it checks for")
        article = "a case" if key == "cases" else "an arm" if ids and all(n == "arm" for n in needed.values()) else "an alternative"
        for k in keys_of(given):
            if k not in ids:
                s = suggest(k, ids)
                c.add("warning", c.join(c.join(where, key), k), f'"{clip(k)}" is not {article} in this report, so this description is not used', f'did you mean "{s}"?' if s else f"ids here: {list_of(ids)}" if ids else "this report has none")

    described("alternatives", needs["alternatives"])
    described("cases", None if needs["cases"] is None else {ident: "case" for ident in needs["cases"]})
    for k in ("background", "intent", "questions", "rule", "covers", "notCovered"):
        file_refs(c, story.get(k), c.join(where, k))
    for key in ("alternatives", "cases"):
        if isinstance(story.get(key), dict):
            for k in keys_of(story[key]):
                file_refs(c, story[key][k], c.join(c.join(where, key), k))
    if isinstance(story.get("glossary"), list):
        for i, g in enumerate(story["glossary"]):
            if isinstance(g, dict):
                file_refs(c, g.get("meaning"), c.join(c.join(c.join(where, "glossary"), i), "meaning"))


def readings_checks(c, owner: dict, at: str, required: list[str], names: list[str], key) -> None:
    where = c.join(at, "readings")
    given = owner["readings"] if isinstance(owner.get("readings"), dict) else {}
    covered = [key(k) for k in keys_of(given) if said(given[k])]
    for ident in required:
        if ident not in covered:
            c.add("error", where, f'no reading for the "{ident}" section', f"add readings.{ident}: what a newcomer should take from that section's views for this data, in plain words, with the numbers that matter")
    for k in keys_of(given):
        if k not in names:
            s = suggest(k, names)
            c.add("warning", c.join(where, k), f'"{clip(k)}" is not a section of this report, so this reading is not used', f'did you mean "{s}"?' if s else f"sections: {list_of(names, 20)}")
        file_refs(c, given[k], c.join(where, k))


def trial_sections_shown(trial, narrative: dict, kept: list[str]) -> list[str]:
    shown = ["setup", "cases", "runs"]
    if isinstance(trial, dict) and isinstance(trial.get("runs"), list):
        runs = [r for r in trial["runs"] if isinstance(r, dict)]
        valid = [r for r in runs if r.get("passed") is True or r.get("passed") is False]
        # The arms section holds the arm views, or with one arm the variants against their base cases.
        if valid and (len({r["arm"] for r in runs if isinstance(r.get("arm"), str)}) > 1 or variant_pairs(trial, runs, narrative)):
            shown.append("arms")
        if any(r.get("passed") is False for r in valid):
            shown.append("failures")
        if isinstance(trial.get("pairwise"), dict) and trial["pairwise"]:
            shown.append("pairwise")

        def positive(v) -> bool:
            return is_number(v) and v > 0

        if any(positive(r.get("seconds")) or positive(r.get("commands")) or (isinstance(r.get("usage"), dict) and any(positive(r["usage"].get(k)) for k in ("output_tokens", "input_tokens", "cost_usd", "total_cost_usd"))) for r in valid):
            shown.append("cost")
        if any(r.get("passed") is not True and r.get("passed") is not False for r in runs):
            shown.append("invalid")
        if valid:
            shown.append("grid")
        if valid and checks_shown(trial, runs):
            shown.append("checks")
    return [s for s in DEFAULT_SECTIONS if s in shown and s in kept]


def variant_pairs(trial: dict, runs: list[dict], narrative: dict) -> bool:
    """Whether the composition pairs any case with a variant of it: the narrative's own pairs where it lists them, else
    those the plan's scenarios form (as src/validate.ts variantPairs decides it)."""
    ran = {r.get("scenario") for r in runs if isinstance(r.get("scenario"), str)}
    if isinstance(narrative.get("pairs"), list):
        for p in narrative["pairs"]:
            base, variant = (p[0] if len(p) > 0 else None, p[1] if len(p) > 1 else None) if isinstance(p, list) else (p.get("base"), p.get("variant")) if isinstance(p, dict) else (None, None)
            if isinstance(base, str) and isinstance(variant, str) and base != variant and base in ran and variant in ran:
                return True
        return False
    plan = trial.get("plan") if isinstance(trial.get("plan"), dict) else {}
    scenarios = [x for x in plan.get("scenarios") if isinstance(x, dict)] if isinstance(plan.get("scenarios"), list) else []
    return bool(case_pairs(scenarios, runs))


def case_pairs(scenarios: list[dict], runs: list[dict]) -> list[tuple]:
    """Case variants found in the plan by content, as src/trial-model.ts casePairs finds them: scenarios that ran and share
    prompt, judge, judge role, required checks and artifact, where the variant repeats its base's follow-up turns and adds
    more. The closest base wins; a tie means no single base."""
    ran = {r.get("scenario") for r in runs}
    ran_scenarios = [x for x in scenarios if isinstance(x.get("name"), str) and x["name"] in ran and isinstance(x.get("prompt"), str) and x["prompt"]]

    def turns(x: dict) -> list:
        return [js_text(t) for t in x["followups"]] if isinstance(x.get("followups"), list) else []

    def same(a, b) -> bool:
        return js_json(a) == js_json(b)

    pairs, used = [], set()
    for variant in ran_scenarios:
        if variant["name"] in used:
            continue
        vt = turns(variant)
        bases = [b for b in ran_scenarios if b is not variant and b["name"] not in used and b["prompt"] == variant["prompt"]
                 and all(same(b.get(k), variant.get(k)) for k in ("judge", "judge_role", "required", "artifact"))
                 and len(turns(b)) < len(vt) and turns(b) == vt[:len(turns(b))]]
        most = max([-1, *(len(turns(b)) for b in bases)])
        closest = [b for b in bases if len(turns(b)) == most]
        if len(closest) != 1:
            continue
        pairs.append((closest[0]["name"], variant["name"]))
        used.add(variant["name"])
    return pairs


def checks_shown(trial: dict, runs: list[dict]) -> bool:
    """Whether the composition draws its checks section, as src/validate.ts checksShown decides it."""
    arms = {canon(r.get("arm")) for r in runs}
    recorded = [r for r in runs if r.get("passed", MISSING) is not None]
    checks_of = lambda r: r["checks"] if isinstance(r.get("checks"), dict) else {}
    if len(arms) > 1:
        names: dict[str, bool] = {}
        for r in recorded:
            for k, v in checks_of(r).items():
                names[k] = names.get(k, True) if isinstance(v, bool) else False
        return any(names.values()) or any(isinstance(r.get("judge"), dict) and r["judge"].get("verdict") in ("pass", "fail") for r in runs)
    plan = trial.get("plan") if isinstance(trial.get("plan"), dict) else {}
    scenarios = [x for x in plan.get("scenarios") or [] if isinstance(x, dict)] if isinstance(plan.get("scenarios"), list) else []
    seen = []
    for r in runs:
        if canon(r.get("scenario")) not in [canon(x) for x in seen]:
            seen.append(r.get("scenario"))
    for cs in seen:
        sc = next((x for x in scenarios if js_same(x.get("name"), cs)), None)
        required = [x for x in sc["required"] if isinstance(x, str)] if sc and isinstance(sc.get("required"), list) else []
        kinds: dict[str, str] = {}
        for r in recorded:
            if not js_same(r.get("scenario"), cs):
                continue
            for k, v in checks_of(r).items():
                if k in required:
                    continue
                t = "boolean" if isinstance(v, bool) else "number" if is_number(v) else "other"
                kinds[k] = t if k not in kinds or kinds[k] == t else "other"
        if any(t != "other" for t in kinds.values()):
            return True
    return False


def comparison_sections_shown(data: dict, narrative: dict, kept: list[str]) -> list[str]:
    """The sections the comparison composition draws, under its own conditions (src/comparison-compose.ts)."""
    def objects(v):
        return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []

    ids: list = []
    for a in objects(data.get("alternatives")):
        if isinstance(a.get("id"), str) and a["id"] not in ids:
            ids.append(a["id"])
    metrics = [m for m in objects(data.get("metrics")) if isinstance(m.get("id"), str) and m.get("kind") in METRIC_KINDS]
    baseline = any(isinstance(b, str) and b in ids for b in (narrative.get("baseline"), data.get("baseline")))
    groups = narrative["identical"] if isinstance(narrative.get("identical"), list) else data["identical"] if isinstance(data.get("identical"), list) else []
    identical = any(len({a for a in (g if isinstance(g, list) else []) if isinstance(a, str) and a in ids}) > 1 for g in groups)
    shown = []
    if ids:
        shown.append("compared")
    if metrics:
        shown.append("results")
    if metrics and len(ids) > 1 and (baseline or identical or len(ids) == 2):
        shown.append("differences")
    if any(isinstance(a.get("id"), str) and (len(a["group"]) > 0 if isinstance(a.get("group"), list) else isinstance(a.get("group"), str) and a["group"] != "") for a in objects(data.get("alternatives"))):
        shown.append("groups")
    if len(comparison_cases(data)) > 1 and metrics:
        shown.append("cases")
    if objects(data.get("preferences")) or any(isinstance(r.get("order"), list) for r in objects(data.get("rankings"))):
        shown.append("judgments")
    if objects(narrative.get("criteria")):
        shown.append("decision")
    if objects(data.get("observations")) or objects(data.get("aggregates")):
        shown.append("observations")
    return [x for x in COMPARISON_SECTIONS if x in shown and x in kept]


def collection_sections_shown(collection: dict) -> list[str]:
    members = [m for m in collection.get("members") if isinstance(m, dict)] if isinstance(collection.get("members"), list) else []
    shown = ["glance", "reports"]
    if any(isinstance(m.get("trial"), dict) or (isinstance(m.get("spec"), dict) and isinstance(m["spec"].get("trial"), dict)) or (isinstance(m.get("comparison"), dict) and isinstance(m["comparison"].get("metrics"), list) and m["comparison"]["metrics"]) for m in members):
        shown.append("shifts")
    if any(isinstance(m.get("trial"), dict) or isinstance(m.get("spec"), dict) for m in members) and any(cost_shown(m) for m in members):
        shown.append("cost-gain")
    if len([m for m in members if dated(m)]) > 1 or any(isinstance(m.get("follows"), str) for m in members):
        shown.append("timeline")
    if (isinstance(collection.get("pairs"), list) and collection["pairs"]) or any(isinstance(m.get("follows"), str) for m in members):
        shown.append("matchups")
    return [s for s in COLLECTION_SECTIONS if s in shown]


def member_trial(m: dict):
    if isinstance(m.get("spec"), dict):
        t = m["spec"].get("trial")
        return t if isinstance(t, dict) and isinstance(t.get("runs"), list) else None
    t = m.get("trial")
    return t if isinstance(t, dict) and isinstance(t.get("runs"), list) else None


def trimmed(v) -> str:
    return v.strip() if isinstance(v, str) else number_text(v) if is_number(v) else ""


DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def dated(m: dict) -> bool:
    """A member the timeline places by day: its own date, or the day its trial's runs began."""
    if isinstance(m.get("date"), str) and DAY.match(m["date"]) and is_calendar_date(m["date"][:10]):
        return True
    t = member_trial(m)
    if not t:
        return False
    ran = t["ran"] if isinstance(t.get("ran"), dict) else {}
    first = trimmed(ran.get("first")) or trimmed(t.get("generated_at"))
    return bool(DAY.match(first)) and is_calendar_date(first[:10])


def cost_shown(m: dict) -> bool:
    """Whether a member draws a point on the cost-against-gain view, as src/validate.ts costShown decides it."""
    t = member_trial(m)
    if not t:
        return False
    runs = [r for r in t["runs"] if isinstance(r, dict)]
    ran = []
    for r in runs:
        if isinstance(r.get("arm"), str) and r["arm"] not in ran:
            ran.append(r["arm"])
    narrative = m["narrative"] if not isinstance(m.get("spec"), dict) and isinstance(m.get("narrative"), dict) else {}
    wanted = trimmed(t.get("baseline")) if isinstance(m.get("spec"), dict) else trimmed(narrative.get("baseline")) or trimmed(t.get("baseline"))
    if wanted not in ran or t.get("baseline") != wanted:
        return False
    arms = t["plan"]["arms"] if isinstance(t.get("plan"), dict) and isinstance(t["plan"].get("arms"), dict) else {}
    lane = lambda ident: arms[ident]["model"] if isinstance(arms.get(ident), dict) and isinstance(arms[ident].get("model"), str) else ""
    valid = lambda ident: any(r.get("arm") == ident and (r.get("passed") is True or r.get("passed") is False) for r in runs)
    pct = t["pct_vs_baseline"] if isinstance(t.get("pct_vs_baseline"), dict) else {}

    def change(ident) -> bool:
        e = pct[ident] if isinstance(pct.get(ident), dict) else {}
        cost = e.get("cost_usd")
        v = cost["median"] if isinstance(cost, dict) and cost.get("median") is not None else e["total_cost_usd"].get("median") if isinstance(e.get("total_cost_usd"), dict) else None
        return is_number(v)

    return valid(wanted) and any(ident != wanted and lane(ident) == lane(wanted) and valid(ident) and change(ident) for ident in ran)


def section_readings(c, sections, at0: str) -> None:
    if not isinstance(sections, list):
        return
    for i, s in enumerate(sections):
        if not isinstance(s, dict) or not isinstance(s.get("blocks"), list):
            continue
        at = f"{c.join(at0, 'sections')}[{i}]"
        file_refs(c, s.get("reading"), f"{at}.reading")
        for j, b in enumerate(s["blocks"]):
            if not isinstance(b, dict):
                continue
            if isinstance(b.get("read"), dict):
                for k in ("shows", "how", "says"):
                    file_refs(c, b["read"].get(k), f"{at}.blocks[{j}].read.{k}")
            if b.get("type") == "verdict":
                for k in ("headline", "detail", "rule", "conditions", "limits", "changes"):
                    file_refs(c, b.get(k), f"{at}.blocks[{j}].{k}")
        views = [(b, j) for j, b in enumerate(s["blocks"]) if isinstance(b, dict) and isinstance(b.get("type"), str) and b["type"] not in PROSE_BLOCKS]
        says = lambda b: isinstance(b.get("read"), dict) and said(b["read"].get("says"))
        if len(views) == 1:
            if not said(s.get("reading")) and not says(views[0][0]):
                c.add("error", at, "says nothing about what its views show for this data", 'add "reading" to the section, or "read": {"says": …} to the view: what a newcomer should take from it, with the numbers that matter')
            continue
        # With several views, a reading belongs to its view: one paragraph for the section cannot stand for views it does not describe.
        for b, j in views:
            if not says(b):
                c.add("error", f"{at}.blocks[{j}]", "says nothing about what this view shows for this data", 'in a section of several views, give each one its own "read": {"says": …}: what a newcomer should take from it, with the numbers that matter')


def append_readings(c, append, at: str) -> None:
    """Views a narrative appends to the composed sections: each says what it shows."""
    if not isinstance(append, dict):
        return
    for k in keys_of(append):
        blocks = append[k]
        if not isinstance(blocks, list):
            continue
        for j, b in enumerate(blocks):
            if not isinstance(b, dict) or not isinstance(b.get("type"), str):
                continue
            where = f"{c.join(c.join(at, 'append'), k)}[{j}]"
            if isinstance(b.get("read"), dict):
                for f in ("shows", "how", "says"):
                    file_refs(c, b["read"].get(f), f"{where}.read.{f}")
            if b["type"] not in PROSE_BLOCKS and not (isinstance(b.get("read"), dict) and said(b["read"].get("says"))):
                c.add("error", where, "says nothing about what this view shows for this data", 'add "read": {"says": …}: what a newcomer should take from it, with the numbers that matter')


def has_verdict(spec: dict) -> bool:
    return isinstance(spec.get("sections"), list) and any(isinstance(s, dict) and isinstance(s.get("blocks"), list) and any(isinstance(b, dict) and b.get("type") == "verdict" for b in s["blocks"]) for s in spec["sections"])


def ordered(problems: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for p in problems:
        key = (p["level"], p["where"], p["message"])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return [p for p in unique if p["level"] == "error"] + [p for p in unique if p["level"] != "error"]


def validate_spec(spec, trial=None, comparison=None, collection=None) -> list[dict]:
    """Problems in a report specification, as src/validate.ts validateSpec finds them."""
    if not isinstance(spec, dict):
        return [{"level": "error", "where": "spec", "message": f'expected an object with "title" and "sections", found {found(spec)}', "hint": 'a specification is {"title": "…", "sections": [ … ]}'}]
    # A specification read from a file is checked as written: a "problems" field of its own proves nothing.
    # As in the browser: a specification without trial data of its own borrows the trial supplied beside it.
    own, gathered = spec.get("comparison"), spec.get("collection")
    trial, comparison = spec.get("trial") or trial, own if own not in (None, False, 0, "") else comparison
    c = Checker(known_from(trial, comparison, gathered if gathered not in (None, False, 0, "") else collection), "spec")

    def check_trial(value, where: str) -> None:
        if not isinstance(value, dict) or not isinstance(value.get("runs"), list):
            c.add("error", where, "is not trial report data", "write it with trial.py report RUN_DIR --out FILE")

    def check_comparison(value, where: str) -> None:
        if not is_comparison(value):
            c.add("error", where, "is not comparison data", 'a comparison is {"alternatives": [ … ], "metrics": [ … ]}; see catalog.md')
        else:
            c.problems.extend(validate_comparison(value))

    def check_sections(value, where: str) -> None:
        if not isinstance(value, list):
            return
        ids: list[str] = []
        for i, s in enumerate(value):
            if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not SECTION_ID.fullmatch(s["id"]):
                continue
            if s["id"] in ids:
                c.add("warning", f"sections[{i}].id", f'section id "{clip(s["id"])}" is already used by an earlier section', "give each section its own id, so links reach the section meant")
            ids.append(s["id"])

    def check_collection(value, where: str) -> None:
        c.problems.extend(validate_collection(value))

    c.shape(spec, SPEC, "", {"trial": check_trial, "comparison": check_comparison, "collection": check_collection, "sections": check_sections})
    story_checks(c, spec, "", story_obligations(c.known, trial, comparison, blocks_of(spec), spec, has_verdict(spec)))
    section_readings(c, spec.get("sections"), "")
    return ordered(c.problems)


def validate_collection(collection) -> list[dict]:
    """Problems in a collection of reports, as src/validate.ts validateCollection finds them."""
    if not is_collection(collection):
        return [{"level": "error", "where": "collection", "message": f'expected an object with a "members" list, found {found(collection)}', "hint": 'a collection is {"members": [{"id": "…", "trial": { … }, "narrative": { … }}, …]}; see catalog.md'}]
    c = Checker(known_from(None, None, collection), "collection")
    c.shape(collection, COLLECTION, "collection")
    themes: list[str] = []
    for i, t in enumerate(collection.get("themes") if isinstance(collection.get("themes"), list) else []):
        if not isinstance(t, dict) or not isinstance(t.get("id"), str):
            continue
        if t["id"] in themes:
            c.add("warning", f"collection.themes[{i}].id", f'theme id "{clip(t["id"])}" is already used by an earlier theme', "give each theme its own id; reports join the first")
        themes.append(t["id"])
        if not said(t.get("summary")):
            c.add("error", f"collection.themes[{i}]", f'theme "{clip(t["id"])}" has no summary', "say what its reports set out to decide and how they relate to one another")
        else:
            file_refs(c, t["summary"], f"collection.themes[{i}].summary")
    story_checks(c, collection, "collection", {"rule": False, "alternatives": None, "cases": None})
    readings_checks(c, collection, "collection", collection_sections_shown(collection), COLLECTION_SECTIONS, lambda x: x)
    ids: list[str] = []
    for i, m in enumerate(collection["members"]):
        if not isinstance(m, dict):
            continue
        at = f"collection.members[{i}]"
        if isinstance(m.get("id"), str):
            if m["id"] in ids:
                c.add("error", f"{at}.id", f'report id "{clip(m["id"])}" is already used by an earlier report', "give each report its own id; links and pairs name reports by id")
            ids.append(m["id"])
            if m.get("follows") == m["id"]:
                c.add("error", f"{at}.follows", "a report cannot follow itself", "name the earlier report this one follows up, or remove the field")
        has_trial, has_comparison, has_spec = m.get("trial") is not None, m.get("comparison") is not None, m.get("spec") is not None
        sources = sum((has_trial, has_comparison, has_spec))
        if sources > 1:
            c.add("error", at, 'has more than one of "trial", "comparison" and "spec"', "a report draws one trial, one comparison or one specification; make them separate reports")
        elif not sources:
            c.add("error", at, 'missing "trial", "comparison" or "spec"', "give the report its trial data (trial.py report), its comparison data, or a specification of its own")
        if isinstance(m.get("date"), str) and not is_calendar_date(m["date"]):
            c.add("warning", f"{at}.date", f'"{clip(m["date"])}" is not a calendar date written YYYY-MM-DD, so it is not used', "write the day the runs began, such as 2026-10-15")
        narrated = m.get("narrative") is not None
        found_problems: list[dict] = []
        if has_spec and sources == 1:
            spec = m["spec"]
            if not isinstance(spec, dict) or not isinstance(spec.get("title"), str) or not isinstance(spec.get("sections"), list):
                c.add("error", f"{at}.spec", "is not a report specification", 'a specification is {"title": "…", "sections": [ … ]}; see catalog.md')
            else:
                for problem in validate_spec(spec):
                    c.problems.append({**problem, "where": f"{at}.spec" if problem["where"] == "spec" else f"{at}.spec.{problem['where']}"})
            if narrated:
                c.add("warning", f"{at}.narrative", "a specification replaces the composition a narrative shapes, so this narrative is not used", "put the decision and labels in the specification itself, or remove the narrative")
        if has_trial and sources == 1:
            if not isinstance(m["trial"], dict) or not isinstance(m["trial"].get("runs"), list):
                c.add("error", f"{at}.trial", "is not trial report data", "write it with trial.py report RUN_DIR --out FILE")
            else:
                # Without a narrative the member's report is composed from none, and checked as such.
                found_problems = validate_narrative(m["narrative"] if narrated else {}, m["trial"])
        if has_comparison and sources == 1:
            if not is_comparison(m["comparison"]):
                c.add("error", f"{at}.comparison", "is not comparison data", 'a comparison is {"alternatives": [ … ], "metrics": [ … ]}; see catalog.md')
            else:
                found_problems = validate_comparison(m["comparison"], m["narrative"] if narrated else {})
        for problem in found_problems:
            c.problems.append({**problem, "where": f"{at}.{problem['where']}"})
    for i, pair in enumerate(collection.get("pairs") if isinstance(collection.get("pairs"), list) else []):
        if isinstance(pair, dict) and isinstance(pair.get("a"), str) and pair.get("a") == pair.get("b"):
            c.add("error", f"collection.pairs[{i}]", "pairs a report with itself", "name two different reports")
    return ordered(c.problems)


MEMBER_FILES = ("trial", "comparison", "spec", "narrative")


def member_file(base: Path, name: str, label: str) -> Path:
    """A member's file, named relative to the collection's directory and kept inside it (symlinks resolved), since
    its whole content is embedded in the page."""
    if Path(name).is_absolute():
        raise InputError(f"{label}: {name} is an absolute path", "name the file relative to the collection file, inside its directory")
    root = base.resolve()
    target = (root / name).resolve()
    if target != root and root not in target.parents:
        raise InputError(f"{label}: {name} is outside the collection's directory", "keep every member's files beside the collection file or in folders under it; the page embeds them whole")
    return target


def load_collection(path: Path, strict: bool) -> dict:
    """A collection with each member's files read in: a member's "trial", "comparison", "spec" or "narrative" given
    as a string is a JSON file named relative to the collection file and inside its directory."""
    collection = load(path, "--collection", strict=strict)
    if not isinstance(collection, dict) or not isinstance(collection.get("members"), list):
        raise assemble.PackagingError(f"{path} needs a \"members\" list; see catalog.md")
    members = []
    for i, member in enumerate(collection["members"]):
        if isinstance(member, dict):
            member = dict(member)
            for key in MEMBER_FILES:
                if isinstance(member.get(key), str):
                    label = f"collection.members[{i}].{key}"
                    member[key] = load(member_file(path.parent, member[key], label), label, strict=strict)
        members.append(member)
    return {**collection, "members": members}


def level_of(levels: list[str], value) -> int:
    """The level an ordinal value names: its name, or a 0-based index into the metric's levels."""
    name = value if isinstance(value, str) else number_text(value) if is_number(value) else None
    if name is not None and name in levels:
        return levels.index(name)
    return int(value) if is_whole(value) and 0 <= value < len(levels) else -1


MISSING = object()


def js_same(x, y) -> bool:
    """JavaScript's === for JSON values: numbers by value, text and booleans exactly, objects never."""
    if isinstance(x, bool) or isinstance(y, bool):
        return x is y
    if is_number(x) and is_number(y):
        return x == y
    if isinstance(x, str) and isinstance(y, str):
        return x == y
    return x is None and y is None


def validate_comparison(data, narrative=MISSING) -> list[dict]:
    """Problems in a comparison, and in a narrative for its composition, as src/validate.ts validateComparison finds them."""
    if not isinstance(data, dict):
        return [{"level": "error", "where": "comparison", "message": f'expected an object with "alternatives" and "metrics", found {found(data)}', "hint": 'a comparison is {"alternatives": [ … ], "metrics": [ … ]}; see catalog.md'}]
    c = Checker(known_from(None, data if is_comparison(data) else {"alternatives": []}), "comparison")
    c.shape(data, COMPARISON, "comparison")

    def items(key: str) -> list:
        return data[key] if isinstance(data.get(key), list) else []

    for key in ("alternatives", "cases", "metrics"):
        seen: list[str] = []
        for i, x in enumerate(items(key)):
            if not isinstance(x, dict) or not isinstance(x.get("id"), str):
                continue
            if x["id"] in seen:
                c.add("error", f"comparison.{key}[{i}].id", f'id "{clip(x["id"])}" is already used by an earlier entry', "give each entry its own id; the views read the first")
            seen.append(x["id"])
    metrics: dict = {}
    for m in items("metrics"):
        if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"] not in metrics:
            metrics[m["id"]] = m

    def levels(m: dict) -> list[str]:
        return [x if isinstance(x, str) else number_text(x) for x in m["levels"] if is_text(x)] if isinstance(m.get("levels"), list) else []

    primaries = sum(1 for m in items("metrics") if isinstance(m, dict) and m.get("primary") is True)
    if primaries > 1:
        c.add("warning", "comparison.metrics", f"{primaries} metrics are marked primary", "mark one; the views read the first as primary")

    def owner(kind):
        of = [m for m in metrics.values() if m.get("kind") == kind]
        if len(of) == 1:
            return of[0]["id"]
        return next((m["id"] for m in of if m.get("primary") is True), None)

    def unnamed(x) -> bool:
        return isinstance(x, dict) and not (isinstance(x.get("metric"), str) and x["metric"])

    numeric = lambda v: bool(NUMERIC_TEXT.fullmatch(v))  # noqa: E731
    for i, m in enumerate(items("metrics")):
        if not isinstance(m, dict) or not isinstance(m.get("id"), str):
            continue
        at, ident, kind = f"comparison.metrics[{i}]", m["id"], m.get("kind")
        if isinstance(m.get("levels"), list) and kind != "ordinal":
            c.add("warning", f"{at}.levels", "levels are read only for ordinal metrics", 'remove them, or set "kind": "ordinal"')
        if len(set(levels(m))) < len(levels(m)):
            c.add("error", f"{at}.levels", "a level is listed more than once, so the order is ambiguous", "list each level once, lowest first")
        if kind in ("binary", "count") and is_number(m.get("threshold")) and (m["threshold"] < 0 or m["threshold"] > 1):
            c.add("error", f"{at}.threshold", f"the threshold {number_text(m['threshold'])} is outside 0 to 1", "write a rate as a share: 0.15 for 15%")
        if kind == "ordinal" and not levels(m) and (
            any(isinstance(o, dict) and o.get("metric") == ident and o.get("valid") is not False and isinstance(o.get("value"), str) and o["value"] != "" and not numeric(o["value"]) for o in items("observations"))
            or any(isinstance(a, dict) and a.get("metric") == ident and isinstance(a.get("counts"), dict) and any(not numeric(k) for k in keys_of(a["counts"])) for a in items("aggregates"))
        ):
            c.add("error", at, f'ordinal metric "{clip(ident)}" names no levels, so its text values have no order', '"levels" lists them lowest first, such as ["poor", "fair", "good"]')
        judged = kind in ("preference", "rank")
        judgments = [*(items("preferences") if kind == "preference" else []), *items("rankings")]
        has_data = (
            any(isinstance(o, dict) and o.get("metric") == ident for o in items("observations"))
            or any(isinstance(a, dict) and a.get("metric") == ident for a in items("aggregates"))
            or (judged and any(isinstance(j, dict) and (j.get("metric") == ident or (unnamed(j) and owner(kind) == ident)) for j in judgments))
        )
        if not has_data and kind in METRIC_KINDS:
            what = "observations, aggregates or judgments" if judged else "observations or aggregates"
            c.add("warning", at, f'metric "{clip(ident)}" has no {what}, so its views show nothing', "add its data, or remove the metric")

    unread = 'mark an observation without a result "valid": false'
    for i, o in enumerate(items("observations")):
        if not isinstance(o, dict):
            continue
        at = f"comparison.observations[{i}]"
        m = metrics.get(o["metric"]) if isinstance(o.get("metric"), str) else None
        if m is None:
            continue
        kind, v, name = m.get("kind"), o.get("value"), clip(m["id"])
        if o.get("n") is not None and kind != "count":
            c.add("warning", f"{at}.n", '"n" is read only for count metrics', "remove it, or make the metric a count")
        if kind == "preference":
            c.add("warning", at, 'preference metrics read "preferences" and "rankings", so this observation is counted invalid', "record head-to-head judgments in preferences, or use a rank or numeric metric")
            continue
        if o.get("valid") is False or v is None or v == "":
            continue

        def wrong(what: str, hint: str) -> None:
            c.add("error", f"{at}.value", f'expected {what} for {kind} metric "{name}", found {found(v)}', hint)

        if kind == "binary" and not (isinstance(v, bool) or (is_number(v) and v in (0, 1))):
            wrong("true or false", f"write true or false (or 1 and 0); {unread}")
        if kind == "numeric" and not is_number(v):
            wrong("a number", "write the number without quotes" if isinstance(v, str) and numeric(v) else f"write a number; {unread}")
        if kind == "rank" and not (is_number(v) and v >= 1):
            wrong("a position of 1 or more", "1 is first place")
        if kind == "count":
            if not (is_whole(v) and v >= 0):
                wrong("a whole number of successes", 'write the successes as a number, with "n" for the trials')
            elif not is_number(o.get("n")):
                c.add("error", at, 'a count needs "n", the trials behind it', 'add "n", such as {"value": 12, "n": 400}')
            elif v > o["n"]:
                c.add("error", f"{at}.value", f"{number_text(v)} successes is more than n ({number_text(o['n'])}) trials", "successes cannot exceed trials")
        if kind == "ordinal" and levels(m) and level_of(levels(m), v) < 0:
            c.add("error", f"{at}.value", f'{found(v)} is not a level of ordinal metric "{name}"', f"levels: {list_of(levels(m))}")

    for i, a in enumerate(items("aggregates")):
        if not isinstance(a, dict):
            continue
        at = f"comparison.aggregates[{i}]"
        m = metrics.get(a["metric"]) if isinstance(a.get("metric"), str) else None
        if is_number(a.get("k")) and is_number(a.get("n")) and a["k"] > a["n"]:
            c.add("error", at, f"k ({number_text(a['k'])}) is larger than n ({number_text(a['n'])})", "k counts successes (or wins) out of n trials (or decisive judgments)")
        if is_number(a.get("lo")) and is_number(a.get("hi")) and a["lo"] > a["hi"]:
            c.add("error", at, f"lo ({number_text(a['lo'])}) is above hi ({number_text(a['hi'])})", "write the interval with lo at or below hi")
        if m is None:
            continue
        kind = m.get("kind")
        if kind in ("binary", "count", "preference") and not (is_number(a.get("k")) and is_number(a.get("n"))):
            c.add("error", at, f'a {kind} aggregate needs "k" and "n"', "k successes (or wins) out of n trials (or decisive judgments)")
        if kind in ("numeric", "rank") and not is_number(a.get("mean")):
            c.add("error", at, f'a {kind} aggregate needs "mean"', 'add "mean", with "sd" and "n" for an interval')
        if kind == "ordinal" and not isinstance(a.get("counts"), dict):
            c.add("error", at, 'an ordinal aggregate needs "counts"', 'counts per level, such as {"good": 12, "fair": 5}')
        if kind == "ordinal" and isinstance(a.get("counts"), dict) and levels(m):
            for k in keys_of(a["counts"]):
                if k not in levels(m):
                    c.add("error", c.join(f"{at}.counts", k), f'"{clip(k)}" is not a level of ordinal metric "{clip(m["id"])}"', f"levels: {list_of(levels(m))}")

    def judged_by(j: dict, where: str) -> None:
        m = metrics.get(j["metric"]) if isinstance(j.get("metric"), str) else None
        if m is not None and isinstance(m.get("kind"), str) and m["kind"] not in ("preference", "rank"):
            c.add("warning", where, f'metric "{clip(m["id"])}" is a {m["kind"]} metric, so this judgment does not count toward it', "name a preference or rank metric, or leave metric out for the overall preference")

    for i, pref in enumerate(items("preferences")):
        if not isinstance(pref, dict):
            continue
        at, a, b, winner = f"comparison.preferences[{i}]", pref.get("a"), pref.get("b"), pref.get("winner", MISSING)
        if isinstance(a, str) and a == b:
            c.add("error", at, f'"{clip(a)}" is judged against itself', "name two different alternatives")
        elif winner is not MISSING and winner is not None and winner != "tie" and not js_same(winner, a) and not js_same(winner, b):
            named = lambda x, fallback: f'"{clip(x)}"' if isinstance(x, str) else fallback  # noqa: E731
            c.add("error", f"{at}.winner", f"{found(winner)} names neither alternative of this judgment", f'write {named(a, "a")}, {named(b, "b")}, "tie", or null when no judgment was reached')
        judged_by(pref, f"{at}.metric")
    for i, r in enumerate(items("rankings")):
        if not isinstance(r, dict) or not isinstance(r.get("order"), list):
            continue
        at, seen = f"comparison.rankings[{i}]", []
        for j, ident in enumerate(r["order"]):
            if not isinstance(ident, str):
                continue
            if ident in seen:
                c.add("error", f"{at}.order[{j}]", f'"{clip(ident)}" is placed twice in one ranking', "list each alternative once, first place first")
            seen.append(ident)
        if len(r["order"]) < 2:
            c.add("warning", f"{at}.order", "a ranking of fewer than two alternatives compares nothing", "list at least two alternatives, first place first")
        judged_by(r, f"{at}.metric")
    for i, group in enumerate(items("identical")):
        if isinstance(group, list) and len({x for x in group if isinstance(x, str)}) < 2:
            c.add("warning", f"comparison.identical[{i}]", "an identical group needs at least two different alternatives; this one shows no spread", "list every alternative that received the same material in one group")
    prefs = [m for m in metrics.values() if m.get("kind") == "preference"]
    loose = sum(1 for x in items("preferences") if unnamed(x))
    if loose and len(prefs) > 1 and not any(m.get("primary") is True for m in prefs):
        c.add("warning", "comparison.preferences", f"{plural(loose, 'judgment')} name no metric, and {len(prefs)} preference metrics could own them", 'name the metric on each judgment, or mark one preference metric "primary"; until then they count only toward the overall preference')
    if narrative is not MISSING:
        c.problems.extend(comparison_narrative(narrative, c.known, data))
    return ordered(c.problems)


def comparison_narrative(narrative, known: dict, data: dict) -> list[dict]:
    """Problems in a narrative for the comparison composition."""
    if not isinstance(narrative, dict):
        return [{"level": "error", "where": "narrative", "message": f"expected an object, found {found(narrative)}", "hint": 'a narrative is an object such as {"title": "…", "decision": { … }}'}]
    c = Checker(known, "narrative")

    def strings(v):
        return [x for x in v if isinstance(x, str)] if isinstance(v, list) else None

    include = strings(narrative.get("include"))
    include = [comparison_key(x) for x in include] if include is not None else None
    exclude = [comparison_key(x) for x in strings(narrative.get("exclude")) or []]
    kept = [s for s in COMPARISON_SECTIONS if (include is None or s in include) and s not in exclude]

    def section_ids(value, where: str) -> None:
        for i, ident in enumerate(value if isinstance(value, list) else []):
            if not isinstance(ident, str) or ident in COMPARISON_NAMES:
                continue
            s = suggest(ident, COMPARISON_SECTIONS)
            c.add("error", c.join(where, i), f'"{clip(ident)}" is not a section of the comparison report', f'did you mean "{s}"?' if s else f"sections: {', '.join(COMPARISON_SECTIONS)}")

    def decision(value, where: str) -> None:
        if isinstance(value, dict) and "rule" in value:
            c.add("warning", c.join(where, "rule"), "the decision rule comes from the comparison's decision_rule, so this value is not shown", "remove it; the verdict quotes the comparison's rule word for word")

    def alternatives(value, where: str) -> None:
        if not isinstance(value, list):
            return
        seen: list[str] = []
        for i, a in enumerate(value):
            if not isinstance(a, dict) or not isinstance(a.get("id"), str):
                continue
            if a["id"] in seen:
                c.add("warning", c.join(c.join(where, i), "id"), f'alternative "{clip(a["id"])}" is listed more than once; the first entry is used', "keep one entry per alternative")
            seen.append(a["id"])

    def identical(value, where: str) -> None:
        for i, group in enumerate(value if isinstance(value, list) else []):
            if isinstance(group, list) and len({x for x in group if isinstance(x, str)}) < 2:
                c.add("warning", c.join(where, i), "an identical group needs at least two different alternatives; this one shows no spread", "list every alternative that received the same material in one group")

    def criteria(value, where: str) -> None:
        if not isinstance(value, list):
            return
        rows = [r for r in value if isinstance(r, dict) and r.get("better", MISSING) != "none"]
        weighted = sum(1 for r in rows if is_number(r.get("weight")))
        rated = [x.get("criterion", MISSING) for x in narrative.get("cells") if isinstance(x, dict)] if isinstance(narrative.get("cells"), list) else []
        for i, r in enumerate(value):
            if not isinstance(r, dict):
                continue
            if "metric" not in r and "scores" not in r and not ("id" in r and any(js_same(r["id"], x) for x in rated)):
                c.add("error", c.join(where, i), 'a criterion needs "metric", "scores" or cells that rate it', "name the metric that measures it, give each alternative a score, or rate it in cells by its id")
            if is_number(r.get("weight")) and r["weight"] < 0:
                c.add("error", c.join(c.join(where, i), "weight"), "a weight cannot be negative", "write how much the criterion counts, 0 or more")
        if weighted and weighted < len(rows):
            c.add("warning", where, f"{weighted} of {len(rows)} criteria carry a weight, so the weighted total leaves out the other {len(rows) - weighted}", "weight every criterion that should count toward the total")

    def sections(value, where: str) -> None:
        if not isinstance(value, list):
            return
        before = list(kept)
        for i, s in enumerate(value):
            if not isinstance(s, dict):
                continue
            after = s.get("after")
            if isinstance(after, str) and comparison_key(after) not in before:
                at = c.join(c.join(where, i), "after")
                if after in COMPARISON_NAMES:
                    c.add("warning", at, f'section "{after}" is left out by include or exclude, so this section goes at the end', "keep that section, or name another one to follow")
                else:
                    options = list(dict.fromkeys([*COMPARISON_SECTIONS, *before]))
                    hint = suggest(after, options)
                    c.add("error", at, f'no section "{clip(after)}" comes before this one, so this section goes at the end', f'did you mean "{hint}"?' if hint else f"sections: {list_of(options)}")
            key = s["id"] if isinstance(s.get("id"), str) and s["id"] else s.get("title")
            if isinstance(key, str):
                before.append(key)

    def append(value, where: str) -> None:
        if not isinstance(value, dict):
            return
        for k in keys_of(value):
            at = c.join(where, k)
            if k not in COMPARISON_NAMES:
                s = suggest(k, COMPARISON_SECTIONS)
                c.add("error", at, f'"{clip(k)}" is not a section of the comparison report, so these blocks do not appear', f'did you mean "{s}"?' if s else f"sections: {', '.join(COMPARISON_SECTIONS)}")
            elif comparison_key(k) not in kept:
                c.add("warning", at, f'section "{k}" is left out by include or exclude, so these blocks do not appear', "keep that section, or append the blocks to another one")

    c.shape(narrative, COMPARISON_NARRATIVE, "narrative", {
        "decision": decision, "alternatives": alternatives, "identical": identical, "criteria": criteria, "include": section_ids, "exclude": section_ids, "sections": sections, "append": append,
    })
    story_checks(c, narrative, "narrative", story_obligations(known, None, data, blocks_of(narrative), {}, True))
    pointed_rule(c, narrative, data.get("decision_rule"), "the comparison's")
    readings_checks(c, narrative, "narrative", comparison_sections_shown(data, narrative, kept), COMPARISON_NAMES, comparison_key)
    section_readings(c, narrative.get("sections"), "narrative")
    append_readings(c, narrative.get("append"), "narrative")
    if isinstance(narrative.get("decision"), dict):
        for k in ("headline", "detail", "conditions", "limits", "changes"):
            file_refs(c, narrative["decision"].get(k), f"narrative.decision.{k}")
    return c.problems


def validate_narrative(narrative, trial=None) -> list[dict]:
    """Problems in a narrative, as src/validate.ts validateNarrative finds them."""
    c = Checker(known_from(trial), "narrative")
    if not isinstance(narrative, dict):
        return [{"level": "error", "where": "narrative", "message": f"expected an object, found {found(narrative)}", "hint": 'a narrative is an object such as {"title": "…", "decision": { … }}'}]

    def strings(v):
        return [x for x in v if isinstance(x, str)] if isinstance(v, list) else None

    include = strings(narrative.get("include"))
    include = [section_key(x) for x in include] if include is not None else None
    exclude = [section_key(x) for x in strings(narrative.get("exclude")) or []]
    kept = [s for s in DEFAULT_SECTIONS if (s in include if include is not None else s not in OPT_IN_SECTIONS) and s not in exclude]

    def left_out(ident: str) -> str:
        return "is drawn only when include names it" if section_key(ident) in OPT_IN_SECTIONS and section_key(ident) not in exclude else "is left out by include or exclude"

    def section_ids(value, where: str) -> None:
        for i, ident in enumerate(value if isinstance(value, list) else []):
            if not isinstance(ident, str) or ident in SECTION_NAMES:
                continue
            s = suggest(ident, DEFAULT_SECTIONS)
            c.add("error", c.join(where, i), f'"{clip(ident)}" is not a section of the trial report', f'did you mean "{s}"?' if s else f"sections: {', '.join(DEFAULT_SECTIONS)}")

    def decision(value, where: str) -> None:
        if isinstance(value, dict) and "rule" in value:
            c.add("warning", c.join(where, "rule"), "the decision rule comes from the trial's plan, so this value is not shown", "remove it; the verdict quotes the plan's rule word for word")

    def arms(value, where: str) -> None:
        if not isinstance(value, list):
            return
        seen: list[str] = []
        for i, arm in enumerate(value):
            if not isinstance(arm, dict) or not isinstance(arm.get("id"), str):
                continue
            if arm["id"] in seen:
                c.add("warning", c.join(c.join(where, i), "id"), f'arm "{clip(arm["id"])}" is listed more than once; the first entry is used', "keep one entry per arm")
            seen.append(arm["id"])

    def identical(value, where: str) -> None:
        if not isinstance(value, list):
            return
        placed: list[str] = []
        for i, group in enumerate(value):
            members = strings(group)
            if members is None:
                continue
            if len(set(members)) < 2:
                c.add("warning", c.join(where, i), "an identical group needs at least two different arms; this one shows no spread", "list every arm that received the same material in one group")
            for arm in members:
                if arm in placed:
                    c.add("warning", c.join(where, i), f'arm "{clip(arm)}" is already in an earlier identical group', "each arm belongs to at most one group")
            placed.extend(dict.fromkeys(members))
            # Copies differ only by chance; arms whose recorded settings differ do not.
            settings = c.known["settings"]
            first = next((a for a in members if a in settings), None)
            if first is None:
                continue
            base = settings[first]
            for j, arm in enumerate(group):
                other = settings.get(arm) if isinstance(arm, str) else None
                if arm == first or other is None:
                    continue
                differ = sorted(k for k in {*base, *other} if k not in MATERIAL_TEXT and (canon(base[k]) if k in base else "") != (canon(other[k]) if k in other else ""))
                if differ:
                    c.add("error", c.join(c.join(where, i), j), f'"{clip(arm)}" differs from "{clip(first)}" in {list_of(differ)}, so the gap between them is not chance alone', "identical is for copies whose every recorded setting matches; leave these arms out of it")

    def sections(value, where: str) -> None:
        if not isinstance(value, list):
            return
        before = list(kept)
        for i, s in enumerate(value):
            if not isinstance(s, dict):
                continue
            after = s.get("after")
            if isinstance(after, str) and section_key(after) not in before:
                at = c.join(c.join(where, i), "after")
                if after in SECTION_NAMES:
                    c.add("warning", at, f'section "{after}" {left_out(after)}, so this section goes at the end', "keep that section, or name another one to follow")
                else:
                    options = list(dict.fromkeys([*DEFAULT_SECTIONS, *before]))
                    hint = suggest(after, options)
                    c.add("error", at, f'no section "{clip(after)}" comes before this one, so this section goes at the end', f'did you mean "{hint}"?' if hint else f"sections: {list_of(options)}")
            key = s["id"] if isinstance(s.get("id"), str) and s["id"] else s.get("title")
            if isinstance(key, str):
                before.append(key)

    def append(value, where: str) -> None:
        if not isinstance(value, dict):
            return
        for k in keys_of(value):
            at = c.join(where, k)
            if k not in SECTION_NAMES:
                s = suggest(k, DEFAULT_SECTIONS)
                c.add("error", at, f'"{clip(k)}" is not a section of the trial report, so these blocks do not appear', f'did you mean "{s}"?' if s else f"sections: {', '.join(DEFAULT_SECTIONS)}")
            elif section_key(k) not in kept:
                c.add("warning", at, f'section "{k}" {left_out(k)}, so these blocks do not appear', "keep that section, or append the blocks to another one")

    def pairs(value, where: str) -> None:
        if not isinstance(value, list):
            return
        for i, pair in enumerate(value):
            at = c.join(where, i)
            if isinstance(pair, list) and len(pair) != 2:
                c.add("error", at, f"a pair names a base case and its variant, found {plural(len(pair), 'item')}", 'write ["base-case", "variant-case"], or {"base": "…", "variant": "…"}')
            base, variant = (pair + [None, None])[:2] if isinstance(pair, list) else (pair.get("base"), pair.get("variant")) if isinstance(pair, dict) else (None, None)
            if isinstance(base, str) and base == variant:
                c.add("warning", at, f'"{clip(base)}" cannot be a variant of itself, so this pair is not used', "name two different cases")

    def threshold(value, where: str) -> None:
        v = value if is_number(value) else value.get("value") if isinstance(value, dict) and is_number(value.get("value")) else None
        if v is not None and abs(v) > 1:
            c.add("error", where if is_number(value) else c.join(where, "value"), f"the threshold {number_text(v)} is outside −1 to 1, so it is not drawn", "write the difference as a share: 0.15 for +15 points")

    c.shape(narrative, NARRATIVE, "narrative", {
        "decision": decision, "arms": arms, "identical": identical, "pairs": pairs, "threshold": threshold, "include": section_ids, "exclude": section_ids, "sections": sections, "append": append,
    })
    story_checks(c, narrative, "narrative", story_obligations(c.known, trial, None, blocks_of(narrative), {}, True))
    pointed_rule(c, narrative, trial["plan"].get("decision_rule") if isinstance(trial, dict) and isinstance(trial.get("plan"), dict) else None, "the plan's")
    readings_checks(c, narrative, "narrative", trial_sections_shown(trial, narrative, kept), SECTION_NAMES, section_key)
    section_readings(c, narrative.get("sections"), "narrative")
    append_readings(c, narrative.get("append"), "narrative")
    if isinstance(narrative.get("decision"), dict):
        for k in ("headline", "detail", "conditions", "limits", "changes"):
            file_refs(c, narrative["decision"].get(k), f"narrative.decision.{k}")
    return ordered(c.problems)


def print_problems(problems: list[dict]) -> None:
    for p in problems:
        print(f"{p['level']}: {p['where']}: {p['message']}", file=sys.stderr)
        print(f"hint: {p.get('hint') or 'correct the named input'}", file=sys.stderr)


def counted(problems: list[dict]) -> str:
    errors = sum(p["level"] == "error" for p in problems)
    parts = [plural(errors, "error") if errors else "", plural(len(problems) - errors, "warning") if len(problems) > errors else ""]
    return " and ".join(x for x in parts if x)


# --------------------------------------------------------------------------- skeleton

# Plan fields that carry an arm's material rather than a setting; their digests are compared instead.
MATERIAL_TEXT = {"instructions_text", "instructions_truncated", "artifact_text", "artifact_truncated"}


def skeleton(trial: dict, trial_label: str) -> dict:
    """A starter narrative with every id spelled as the trial records it."""
    plan = trial.get("plan") if isinstance(trial.get("plan"), dict) else {}
    runs = [r for r in trial["runs"] if isinstance(r, dict)]
    ran_arms = list(dict.fromkeys(r["arm"] for r in runs if isinstance(r.get("arm"), str)))
    ran_cases = list(dict.fromkeys(r["scenario"] for r in runs if isinstance(r.get("scenario"), str)))
    planned = plan.get("arms") if isinstance(plan.get("arms"), dict) else {}
    arms = [a for a in planned if a in ran_arms] + [a for a in ran_arms if a not in planned]
    scenarios = [s["name"] for s in plan.get("scenarios") or [] if isinstance(s, dict) and isinstance(s.get("name"), str)]
    cases = [c for c in dict.fromkeys(scenarios) if c in ran_cases] + [c for c in ran_cases if c not in scenarios]
    settings = {a: {k: v for k, v in planned[a].items() if k not in MATERIAL_TEXT} for a in arms if isinstance(planned.get(a), dict) and planned[a]}

    by_identity: dict[str, list[str]] = {}
    for arm in arms:
        if settings.get(arm):
            by_identity.setdefault(canon(settings[arm]), []).append(arm)
    identical = [group for group in by_identity.values() if len(group) > 1]

    by_digest: dict[str, list[str]] = {}
    for arm in arms:
        digest = settings.get(arm, {}).get("instructions_sha256")
        if isinstance(digest, str) and digest:
            by_digest.setdefault(digest, []).append(arm)
    same = []
    for digest, members in by_digest.items():
        if len(members) < 2 or any(set(members) <= set(group) for group in identical):
            continue
        fields = sorted({k for arm in members for k in {*settings[arm], *settings[members[0]]} if settings[arm].get(k) != settings[members[0]].get(k)})
        same.append({"arms": members, "instructions_sha256": digest[:12], "differ_in": fields})

    name = trial.get("name") if isinstance(trial.get("name"), str) and trial.get("name") else "this trial"
    out: dict = {
        "$about": (
            f"Starter narrative for {name}, from report.py --skeleton. Every arm and case id is spelled as the trial records it. "
            "Write the title and question in the reader's words, give arms and cases readable labels, and write the decision you reached "
            "by applying the plan's rule, or delete \"decision\" to report the results without one. Keys that start with $ are notes for you; "
            "the report ignores them. Optional fields (summary, groups, pairs, sections, append, include, exclude) are described in catalog.md. "
            f"Check the result with: report.py --check --trial {trial_label} --narrative THIS_FILE"
        ),
    }
    rule = plan.get("decision_rule")
    if isinstance(rule, str) and rule.strip():
        out["$rule"] = rule
    out["title"] = ""
    out["question"] = ""
    out["decision"] = {
        "$verdicts": "adopt, reject, inconclusive, mixed or none",
        "$check": {"label": "what the rule asks", "observed": "what the runs show", "threshold": "the rule's bar", "met": True},
        "verdict": "none", "headline": "", "detail": "", "checks": [], "conditions": [], "limits": [], "changes": [],
    }
    out["arms"] = [{"id": arm, "label": arm} for arm in arms]
    out["cases"] = {case: case for case in cases}
    if identical:
        out["identical"] = identical
    if same:
        out["$same_instructions"] = {
            "note": "These arms received the same instructions but differ in other recorded settings, so their difference is not chance alone; they are not listed under identical.",
            "groups": same,
        }
    baseline = trial.get("baseline")
    if isinstance(baseline, str) and baseline in arms:
        out["baseline"] = baseline
    out["$story"] = "Write for a reader who has never heard of this work: what it is about, what the decider wanted, what was tested, each alternative and case in plain words, and what the report covers and does not. Then say, for each section, what its views show for this data. See catalog.md#the-story."
    ran = known_from(trial)
    out["story"] = {"background": "", "intent": "", "questions": [], "rule": "", "covers": "", "notCovered": "", "alternatives": {a: "" for a in ran["ran_arms"]}, "cases": {c: "" for c in ran["ran_cases"]}}
    out["readings"] = {section: "" for section in trial_sections_shown(trial, {}, [x for x in DEFAULT_SECTIONS if x not in OPT_IN_SECTIONS])}
    return out


def write_skeleton(narrative: dict, target: str, replace: bool) -> str:
    text = json.dumps(narrative, indent=2, ensure_ascii=False) + "\n"
    if target == "-":
        sys.stdout.write(text)
        return ""
    path = Path(target)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise assemble.PackagingError(f"--skeleton output is not a regular file: {path}")
    if path.exists():
        if path.read_text(encoding="utf-8") == text:
            return f"unchanged {path}"
        if not replace:
            raise assemble.PackagingError(f"--skeleton output exists and differs: {path}; use --replace or choose another file")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".av-skeleton-", dir=path.parent) as scratch:
        temporary = Path(scratch) / "narrative.json"
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(path)
    return f"wrote {path}"


# --------------------------------------------------------------------------- comparison inputs


class InputError(ValueError):
    """Input the command refuses, with the fix in its hint."""

    def __init__(self, message: str, hint: str):
        super().__init__(message)
        self.hint = hint


CSV_COLUMNS = ["alternative", "metric", "value", "case", "group", "unit", "n", "valid", "note", "source", "invalid_reason", "excerpt"]
CSV_REQUIRED = ["alternative", "metric", "value"]
TRUE_WORDS = {"true", "yes", "pass", "passed"}
FALSE_WORDS = {"false", "no", "fail", "failed"}


def load_comparison(path: Path, strict: bool) -> dict:
    data = load(path, "--data", strict=strict)
    if not is_comparison(data):
        raise InputError(f"{path} is not comparison data", 'a comparison is {"alternatives": [ … ], "metrics": [ … ]}; see catalog.md')
    return data


def csv_number(text: str):
    if not NUMERIC_TEXT.fullmatch(text):
        return None
    value = float(text)
    return int(value) if value.is_integer() and abs(value) < 2 ** 53 else value


def csv_flag(text: str):
    word = text.strip().lower()
    return True if word in TRUE_WORDS or word == "1" else False if word in FALSE_WORDS or word == "0" else None


FROM_TRIAL_MATERIAL = {"instructions_text", "instructions_truncated", "artifact_text", "artifact_truncated"}
FROM_TRIAL_UNITS = {"tokens": "tokens", "seconds": "seconds", "usd": "USD", "count": ""}


def js_json(v) -> str:
    """JSON.stringify's compact text for a JSON value (a whole number written 1.0 is 1 there)."""
    def js(x):
        if isinstance(x, float) and x.is_integer() and abs(x) < 1e21:
            return int(x)
        if isinstance(x, list):
            return [js(y) for y in x]
        if isinstance(x, dict):
            return {k: js(y) for k, y in x.items()}
        return x
    return json.dumps(js(v), ensure_ascii=False, separators=(",", ":"))


def js_listed(names: list[str]) -> str:
    return "".join(names) if len(names) <= 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def trial_axes(trial: dict) -> tuple[list, list]:
    """The arms and cases that ran, in plan order then run order, as src/trial-model.ts trialAxes orders them."""
    plan = trial.get("plan") if isinstance(trial.get("plan"), dict) else {}
    runs = [r for r in trial.get("runs") or [] if isinstance(r, dict)]
    arms, cases = [], []
    for a in (plan.get("arms") if isinstance(plan.get("arms"), dict) else {}):
        arms.append(a)
    for sc in plan.get("scenarios") or []:
        if isinstance(sc, dict) and sc.get("name") and sc["name"] not in cases:
            cases.append(sc["name"])
    for r in runs:
        if r.get("arm") not in arms:
            arms.append(r.get("arm"))
        if r.get("scenario") not in cases:
            cases.append(r.get("scenario"))
    ran, ran_cases = {r.get("arm") for r in runs}, {r.get("scenario") for r in runs}
    return [a for a in arms if a in ran], [c for c in cases if c in ran_cases]


def usage_value(run: dict, field: str):
    usage = run.get("usage") if isinstance(run.get("usage"), dict) else {}
    v = usage.get(field)
    return v if is_number(v) else None


def cost_measures(trial: dict) -> list[dict]:
    """The numeric measures a trial's valid runs recorded, as src/trial-model.ts costMeasures finds them."""
    runs = [r for r in trial.get("runs") or [] if isinstance(r, dict) and r.get("passed") is not None]

    def input_tokens(r):
        base = usage_value(r, "input_tokens")
        return None if base is None else base + (usage_value(r, "cache_read_input_tokens") or 0) + (usage_value(r, "cache_creation_input_tokens") or 0)

    separate = any(usage_value(r, "cache_read_input_tokens") is not None or usage_value(r, "cache_creation_input_tokens") is not None for r in runs)
    every = [
        {"id": "output_tokens", "label": "Output tokens", "unit": "tokens", "get": lambda r: usage_value(r, "output_tokens")},
        {"id": "input_tokens", "label": "Input tokens", "unit": "tokens", "get": input_tokens, **({"note": "including cache reads and writes, which this executor reports apart from input_tokens"} if separate else {})},
        {"id": "seconds", "label": "Executor time", "unit": "seconds", "get": lambda r: r.get("seconds") if is_number(r.get("seconds")) else None},
        {"id": "commands", "label": "Commands run", "unit": "count", "get": lambda r: r.get("commands") if is_number(r.get("commands")) else None},
        {"id": "total_cost_usd", "label": "Cost", "unit": "usd", "get": lambda r: usage_value(r, "cost_usd") if usage_value(r, "cost_usd") is not None else usage_value(r, "total_cost_usd")},
    ]
    return [m for m in every if any(is_number(m["get"](r)) and m["get"](r) > 0 for r in runs)]


def from_trial(trial: dict) -> dict:
    """Trial report data as the comparison the page derives for --general: as src/comparison-compose.ts fromTrial does it."""
    arms_axis, cases_axis = trial_axes(trial)
    plan = trial.get("plan") if isinstance(trial.get("plan"), dict) else {}
    planned = plan.get("arms") if isinstance(plan.get("arms"), dict) else {}
    runs = [r for r in trial.get("runs") or [] if isinstance(r, dict) and isinstance(r.get("arm"), str) and isinstance(r.get("scenario"), str)]
    valid = [r for r in runs if r.get("passed") is True or r.get("passed") is False]

    def scalar(v):
        return v if v is None or isinstance(v, (str, bool)) or is_number(v) else js_json(v)

    alternatives = []
    for ident in arms_axis:
        entry = planned.get(ident) if isinstance(planned.get(ident), dict) else {}
        attributes = {k: scalar(v) for k, v in entry.items() if k not in FROM_TRIAL_MATERIAL}
        text = entry.get("instructions_text") if isinstance(entry.get("instructions_text"), str) else None
        alternatives.append({"id": ident, **({"attributes": attributes} if attributes else {}), **({"content": text} if text else {}),
                             **({"note": "instructions shortened to the report's text bound"} if entry.get("instructions_truncated") is True else {})})
    scenarios = [x for x in plan.get("scenarios") or [] if isinstance(x, dict)]
    cases = []
    for ident in cases_axis:
        sc = next((x for x in scenarios if x.get("name") == ident), None) or {}
        desc, prompt = sc.get("description"), sc.get("prompt")
        text = desc if isinstance(desc, str) and desc else (prompt[:399] + "…" if len(prompt) > 400 else prompt) if isinstance(prompt, str) and prompt else None
        cases.append({"id": ident, **({"description": text} if text else {})})
    required: dict[str, list[str]] = {}
    for sc in scenarios:
        for c in [x for x in sc.get("required") or [] if isinstance(x, str)] if isinstance(sc.get("required"), list) else []:
            required.setdefault(c, []).append(str(sc.get("name")) if sc.get("name") is not None else "undefined")
    metrics = [{"id": "passed", "label": "Passed", "kind": "binary", "better": "higher", "primary": True,
                "description": "A run passes when every required check holds and the judge, when there is one, says pass. Invalid runs have no result and are counted apart."}]
    observations = []

    def at(r):
        return {"alternative": r["arm"], "case": r["scenario"], **({"unit": r["repeat"]} if is_number(r.get("repeat")) else {}),
                **({"id": r["job"], "source": r["job"]} if isinstance(r.get("job"), str) else {})}

    for r in runs:
        ok = r.get("passed") is True or r.get("passed") is False
        judge = r.get("judge") if isinstance(r.get("judge"), dict) else {}
        observations.append({**at(r), "metric": "passed", "value": r["passed"] if ok else None,
                             **({} if ok else {"valid": False, "invalid_reason": str(r.get("invalid_reason") or r.get("status") or "invalid")}),
                             **({"note": judge["reason"]} if isinstance(judge.get("reason"), str) and judge["reason"] else {}),
                             **({"excerpt": r["final_message_excerpt"]} if isinstance(r.get("final_message_excerpt"), str) and r["final_message_excerpt"] else {})})
    for m in cost_measures(trial):
        unit = FROM_TRIAL_UNITS[m["unit"]]
        metrics.append({"id": m["id"], "label": m["label"], "kind": "numeric", "better": "lower", **({"unit": unit} if unit else {}), **({"description": m["note"]} if m.get("note") else {})})
        for r in valid:
            v = m["get"](r)
            if is_number(v):
                observations.append({**at(r), "metric": m["id"], "value": v})
    kinds: dict[str, set] = {}
    for r in valid:
        for k, v in (r.get("checks") if isinstance(r.get("checks"), dict) else {}).items():
            kinds.setdefault(k, set()).add("boolean" if isinstance(v, bool) else "number" if is_number(v) else "other")
    for name in sorted(kinds):
        types = kinds[name]
        if len(types) != 1 or "other" in types:
            continue
        boolean, ident, req = "boolean" in types, f"check:{name}", required.get(name)
        metrics.append({"id": ident, "label": name, "kind": "binary" if boolean else "numeric", "better": "higher" if boolean and req else "none",
                        "description": f"A required check in {js_listed(req)}; elsewhere a recorded measure." if req else "A recorded check value; no case requires it."})
        for r in valid:
            v = (r.get("checks") if isinstance(r.get("checks"), dict) else {}).get(name)
            if (isinstance(v, bool) if boolean else is_number(v)):
                observations.append({**at(r), "metric": ident, "value": v})
    verdict = lambda r: (r.get("judge") or {}).get("verdict") if isinstance(r.get("judge"), dict) else None
    if any(verdict(r) in ("pass", "fail") for r in runs):
        metrics.append({"id": "judge", "label": "Judge says pass", "kind": "binary", "better": "higher"})
        for r in runs:
            if verdict(r) in ("pass", "fail"):
                observations.append({**at(r), "metric": "judge", "value": verdict(r) == "pass"})
    preferences = []
    pairwise = trial.get("pairwise") if isinstance(trial.get("pairwise"), dict) else {}
    pairs = [(k, v) for k, v in pairwise.items() if isinstance(v, dict) and isinstance(v.get("arms"), list) and len(v["arms"]) == 2]
    for key, summary in pairs:
        a, b = (js_text(x) for x in summary["arms"])
        ident = "pairwise" if len(pairs) == 1 else f"pairwise:{key}"
        judge = summary["judge"]["model"] if isinstance(summary.get("judge"), dict) and isinstance(summary["judge"].get("model"), str) else None
        metrics.append({"id": ident, "label": "Pairwise preference" if len(pairs) == 1 else f"Pairwise: {a} vs {b}", "kind": "preference", "better": "higher",
                        "description": "A judge saw matched runs side by side in both orders; only pairs decided the same way in both orders count as decided."})
        scen = list(summary["scenarios"].items()) if isinstance(summary.get("scenarios"), dict) and summary["scenarios"] else [(None, summary.get("overall"))]
        count = lambda v: int(v) if is_number(v) and float(v).is_integer() and v > 0 else 0
        for scenario, st in scen:
            if not isinstance(st, dict):
                continue
            def push(n, winner, note=None):
                for _ in range(n):
                    preferences.append({"a": a, "b": b, "winner": winner, "metric": ident, **({"case": scenario} if scenario else {}), **({"judge": judge} if judge else {}), **({"note": note} if note else {})})
            push(count(st.get("a_wins")), a); push(count(st.get("b_wins")), b); push(count(st.get("tie")), "tie")
            push(count(st.get("inconsistent")), None, "decided differently in the two orders"); push(count(st.get("invalid")), None, "no valid judgment")
    name = trial.get("name") if isinstance(trial.get("name"), str) and trial.get("name") else None
    rule = plan.get("decision_rule")
    directory = trial.get("run_directory")
    return {
        **({"title": name} if name else {}),
        "alternatives": alternatives, "cases": cases, "metrics": metrics, "observations": observations, **({"preferences": preferences} if preferences else {}),
        **({"baseline": trial["baseline"]} if isinstance(trial.get("baseline"), str) and trial["baseline"] in arms_axis else {}),
        **({"decision_rule": rule} if isinstance(rule, str) and rule.strip() else {}),
        **({"sources": [{"label": "trial.py report", "note": f"run directory {re.sub(r'^/(?:home|Users)/[^/]+(?=/|$)', '~', directory)}"}]} if isinstance(directory, str) and directory else {}),
    }


def js_text(v) -> str:
    """String(v) for a JSON value, as JavaScript writes it."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if is_number(v):
        return number_text(v)
    if isinstance(v, (list, dict)):
        return ",".join(js_text(x) for x in v) if isinstance(v, list) else "[object Object]"
    return str(v)


def comparison_from_csv(path: Path, base: dict | None = None) -> dict:
    """A long table, one observation per row, as a comparison (merged into base when given)."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise assemble.PackagingError(f"--csv file not found: {path}") from None
    rows = list(csv.reader(io.StringIO(text, newline="")))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        raise InputError(f"{path} is empty", f"the first row names the columns: {', '.join(CSV_REQUIRED)}, then any of {', '.join(CSV_COLUMNS[3:])}")
    header = [h.strip().lower() for h in rows[0]]
    for i, name in enumerate(header):
        if name not in CSV_COLUMNS:
            s = suggest(name, CSV_COLUMNS)
            raise InputError(f'{path}: column {i + 1} "{clip(rows[0][i])}" is not a column this table can hold', f'did you mean "{s}"?' if s else f"columns: {', '.join(CSV_COLUMNS)}")
        if name in header[:i]:
            raise InputError(f'{path}: column "{name}" appears twice, so its values are ambiguous', "keep one column per name")
    missing = [c for c in CSV_REQUIRED if c not in header]
    if missing:
        raise InputError(f"{path}: no {', '.join(missing)} column", f"the first row names the columns: {', '.join(CSV_REQUIRED)}, then any of {', '.join(CSV_COLUMNS[3:])}")
    out = json.loads(json.dumps(base)) if base else {"alternatives": [], "metrics": []}
    out.setdefault("alternatives", [])
    out.setdefault("metrics", [])
    alternatives = {a["id"]: a for a in out["alternatives"] if isinstance(a, dict) and isinstance(a.get("id"), str)}
    defined = {m["id"]: m for m in out["metrics"] if isinstance(m, dict) and isinstance(m.get("id"), str)}
    cases = {c["id"] for c in out.get("cases") or [] if isinstance(c, dict) and isinstance(c.get("id"), str)}
    group_row: dict[str, int] = {}
    records = []
    for line, raw in enumerate(rows[1:], start=2):
        if len(raw) != len(header):
            raise InputError(f"{path}: row {line} has {plural(len(raw), 'cell')} for {plural(len(header), 'column')}", "give every row one cell per column; quote cells that contain commas")
        row = {name: cell.strip() for name, cell in zip(header, raw)}
        for name in ("alternative", "metric"):
            if not row[name]:
                raise InputError(f"{path}: row {line} has no {name}", f"every row names its {name}")
        valid = True
        if row.get("valid"):
            valid = csv_flag(row["valid"])
            if valid is None:
                raise InputError(f'{path}: row {line}: valid "{clip(row["valid"])}" is not true or false', "write true or false (or yes and no), or leave it empty for a valid row")
        n = None
        if row.get("n"):
            n = csv_number(row["n"])
            if not isinstance(n, int) or n < 0:
                raise InputError(f'{path}: row {line}: n "{clip(row["n"])}" is not a whole number of trials', "n is the trials behind a count, such as 400")
        alt = row["alternative"]
        group = [part.strip() for part in row.get("group", "").split(">") if part.strip()]
        if alt not in alternatives:
            alternatives[alt] = {"id": alt}
            out["alternatives"].append(alternatives[alt])
        if group:
            had = alternatives[alt].get("group")
            had = [had] if isinstance(had, str) else had
            if had and had != group:
                where = f"row {group_row[alt]}" if alt in group_row else "--data"
                raise InputError(f'{path}: row {line} puts "{clip(alt)}" in group "{" > ".join(group)}", but {where} puts it in "{" > ".join(map(str, had))}"', "give each alternative one group path, outermost first, separated by >")
            alternatives[alt]["group"] = group
            group_row.setdefault(alt, line)
        if row.get("case") and row["case"] not in cases:
            cases.add(row["case"])
            out.setdefault("cases", []).append({"id": row["case"]})
        records.append((line, row, valid, n))

    # Kinds: from --data where it defines the metric, else inferred from every row's value, refusing what could be read two ways.
    kinds = {mid: m.get("kind") for mid, m in defined.items()}
    for metric in dict.fromkeys(r[1]["metric"] for r in records):
        if metric in kinds:
            continue
        mine = [r for r in records if r[1]["metric"] == metric and r[1]["value"] and r[2] is not False]
        values = [r[1]["value"] for r in mine]
        define = f'define "{clip(metric)}" in --data metrics with its "kind"'
        if any(r[3] is not None for r in records if r[1]["metric"] == metric):
            without = next((r[0] for r in mine if r[3] is None), None)
            if without is not None:
                raise InputError(f'{path}: metric "{clip(metric)}" has n on some rows but not row {without}', "a count needs n, the trials behind it, on every row")
            kind = "count"
        elif not values:
            raise InputError(f'{path}: metric "{clip(metric)}" has no values, so its kind cannot be inferred', define)
        else:
            words = [v.lower() in TRUE_WORDS | FALSE_WORDS for v in values]
            numbers = [csv_number(v) for v in values]
            if all(words):
                kind = "binary"
            elif all(x is not None for x in numbers):
                if all(x in (0, 1) for x in numbers):
                    raise InputError(f'{path}: metric "{clip(metric)}" holds only 0 and 1, which could be a yes/no outcome or a number', f'write true and false for a yes/no outcome, or {define}: "binary" or "numeric"')
                kind = "numeric"
            elif any(words) and all(w or x is not None for w, x in zip(words, numbers)):
                raise InputError(f'{path}: metric "{clip(metric)}" mixes numbers and true/false values, so its kind is ambiguous', f"make its values one type, or {define}")
            else:
                text = list(dict.fromkeys(v for v, x in zip(values, numbers) if x is None))
                raise InputError(f'{path}: metric "{clip(metric)}" has text values ({list_of(text, 4)}), whose order is unknown', f'{define} "ordinal" and "levels" lowest first, such as ["poor", "fair", "good"]')
        kinds[metric] = kind
        defined[metric] = {"id": metric, "kind": kind}
        out["metrics"].append(defined[metric])

    observations = out.setdefault("observations", [])
    for line, row, valid, n in records:
        metric, kind, text = row["metric"], kinds.get(row["metric"]), row["value"]
        o: dict = {"alternative": row["alternative"], "metric": metric}
        if row.get("case"):
            o["case"] = row["case"]
        value = None
        if text:
            levels = defined[metric].get("levels") if isinstance(defined[metric].get("levels"), list) else None
            if kind == "binary":
                value = csv_flag(text)
                problem = None if value is not None else ("true or false", "write true or false (yes and no, pass and fail, 1 and 0)")
            elif kind == "numeric":
                value = csv_number(text)
                problem = None if value is not None else ("a number", "write the number alone, without units or thousands separators")
            elif kind == "count":
                value = csv_number(text)
                problem = None if isinstance(value, int) and value >= 0 and n is not None and value <= n else ("a whole number of successes no larger than n", "write the successes, with the trials in the n column")
            elif kind == "rank":
                value = csv_number(text)
                problem = None if value is not None and value >= 1 else ("a position of 1 or more", "1 is first place")
            elif kind == "ordinal":
                value = text if levels and text in [str(x) for x in levels] else csv_number(text) if not levels else None
                problem = None if value is not None else ("one of the levels", f"levels: {list_of([str(x) for x in levels])}" if levels else 'define its "levels" lowest first in --data')
            else:
                problem = ("a value this metric reads", "preference metrics read head-to-head judgments: put them in --data preferences" if kind == "preference" else 'give the metric a known "kind" in --data')
            if problem and valid is not False:
                raise InputError(f'{path}: row {line}: value "{clip(text)}" is not {problem[0]} for {kind} metric "{clip(metric)}"', problem[1])
            if problem:
                value = None
        o["value"] = value
        if n is not None:
            o["n"] = n
        if valid is False or value is None:
            o["valid"] = False
            o["invalid_reason"] = row.get("invalid_reason") or ("marked invalid" if valid is False else "empty value")
        for name in ("unit", "note", "source", "excerpt"):
            if row.get(name):
                o[name] = row[name]
        o["source"] = o.get("source") or f"{path.name} row {line}"
        observations.append(o)
    return out


def comparison_skeleton(data: dict, check: str) -> dict:
    """A starter narrative for the comparison composition, every id spelled as the comparison records it."""
    alternatives = [a for a in data.get("alternatives") or [] if isinstance(a, dict) and isinstance(a.get("id"), str)]
    metrics = [m for m in data.get("metrics") or [] if isinstance(m, dict) and isinstance(m.get("id"), str)]
    name = data.get("title") if isinstance(data.get("title"), str) and data.get("title") else "this comparison"
    out: dict = {
        "$about": (
            f"Starter narrative for {name}, from report.py --skeleton. Every alternative and metric id is spelled as the comparison records it. "
            "Write the title and question in the reader's words, give alternatives readable labels, and write the decision you reached by applying "
            "the comparison's decision rule, or delete \"decision\" to report the results without one. criteria fills the decision matrix: each criterion "
            "names a metric or gives each alternative a score (cells can add a rating, text and evidence per alternative), and a weighted total appears only "
            "when you give weights; it sums the weighted criteria and names any left out. Keys that start "
            f"with $ are notes for you; the report ignores them. Sections for include, exclude, after and append: {', '.join(COMPARISON_SECTIONS)} (see catalog.md). "
            f"Check the result with: {check} --narrative THIS_FILE"
        ),
    }
    rule = data.get("decision_rule")
    if isinstance(rule, str) and rule.strip():
        out["$rule"] = rule
    out["$metrics"] = {m["id"]: m.get("kind") for m in metrics}
    out["title"] = ""
    out["question"] = data.get("question") if isinstance(data.get("question"), str) else ""
    out["decision"] = {
        "$verdicts": "adopt, reject, inconclusive, mixed or none",
        "$check": {"label": "what the rule asks", "observed": "what the data show", "threshold": "the rule's bar", "met": True},
        "verdict": "none", "headline": "", "detail": "", "checks": [], "conditions": [], "limits": [], "changes": [],
    }
    out["alternatives"] = [{"id": a["id"], "label": a.get("label") if isinstance(a.get("label"), str) and a.get("label") else a["id"]} for a in alternatives]
    out["$criterion"] = {"label": "what matters", "metric": metrics[0]["id"] if metrics else "", "weight": 1, "$or": {"scores": {a["id"]: None for a in alternatives}}}
    out["criteria"] = []
    out["$story"] = "Write for a reader who has never heard of this work: what it is about, what the decider wanted, what was tested, each alternative and case in plain words, and what the report covers and does not. Then say, for each section, what its views show for this data. See catalog.md#the-story."
    cases = [x["id"] for x in data.get("cases") if isinstance(x, dict) and isinstance(x.get("id"), str)] if isinstance(data.get("cases"), list) else []
    out["story"] = {"background": "", "intent": "", "questions": [], "rule": "", "covers": "", "notCovered": "", "alternatives": {a["id"]: "" for a in alternatives}, **({"cases": {c: "" for c in cases}} if cases else {})}
    out["readings"] = {section: "" for section in comparison_sections_shown(data, out, COMPARISON_SECTIONS)}
    return out


# --------------------------------------------------------------------------- command


def main() -> int:
    summary, _, usage = (__doc__ or "").partition("\n\n")
    parser = argparse.ArgumentParser(description=summary, formatter_class=argparse.RawDescriptionHelpFormatter, epilog=usage)
    parser.add_argument("--trial", type=Path, help="JSON from `trial.py report RUN_DIR`")
    parser.add_argument("--data", type=Path, help="a comparison of any alternatives (see catalog.md)")
    parser.add_argument("--csv", type=Path, help="a long table, one observation per row, read as a comparison (merged into --data when both are given)")
    parser.add_argument("--narrative", type=Path, help="decision, labels and extra sections for the trial or comparison composition")
    parser.add_argument("--spec", type=Path, help="a complete report specification (replaces the composition)")
    parser.add_argument("--collection", type=Path, help="many reports in one page: members with their trial or comparison and narrative files, themes and pairs (see catalog.md)")
    parser.add_argument("--general", action="store_true", help="with --trial: draw the trial through the comparison views of any alternatives instead of the trial composition; a --narrative is then a comparison narrative")
    parser.add_argument("--output", type=Path, help="standalone HTML file to write (required unless --check or --skeleton)")
    parser.add_argument("--title", help="document title (default: the report's own title)")
    parser.add_argument("--replace", action="store_true", help="replace a differing existing output")
    parser.add_argument("--check", action="store_true", help="check the inputs and print every problem; write nothing; exit 1 on an error")
    parser.add_argument("--skeleton", nargs="?", const="-", metavar="FILE", help="print a starter narrative for --trial, --data or --csv, or write it to FILE")
    args = parser.parse_args()
    compared = bool(args.data or args.csv)
    try:
        if args.skeleton is not None:
            if bool(args.trial) == compared or args.narrative or args.spec or args.check or args.output or args.general or args.collection:
                raise assemble.PackagingError("--skeleton takes only --trial, or --data and --csv (and --replace when writing a file)")
            if compared:
                data = load_comparison(args.data, strict=True) if args.data else None
                data = comparison_from_csv(args.csv, data) if args.csv else data
                check = "report.py --check" + (f" --data {args.data.name}" if args.data else "") + (f" --csv {args.csv.name}" if args.csv else "")
                done = write_skeleton(comparison_skeleton(data, check), args.skeleton, args.replace)
            else:
                trial = load(args.trial, "--trial", strict=True)
                if not isinstance(trial, dict) or not isinstance(trial.get("runs"), list):
                    raise assemble.PackagingError(f"{args.trial} is not trial report data; write it with `trial.py report RUN_DIR --out FILE`")
                done = write_skeleton(skeleton(trial, args.trial.name), args.skeleton, args.replace)
            if done:
                print(done)
            return 0
        if args.general and (not args.trial or compared or args.spec):
            raise assemble.PackagingError("--general draws a --trial through the comparison views; pass it with --trial (and optionally --narrative) only")
        if args.narrative and not (args.trial or compared):
            raise assemble.PackagingError("--narrative needs --trial, --data or --csv")
        if args.collection and (args.trial or compared or args.narrative or args.general):
            raise assemble.PackagingError("--collection names each report's own files; pass it alone, or with a --spec that uses it")
        if not args.trial and not args.spec and not compared and not args.collection:
            raise assemble.PackagingError("supply --trial, --data, --csv, --spec or --collection")
        if args.narrative and args.spec:
            raise assemble.PackagingError("--narrative shapes the composition; a --spec replaces it, so pass one or the other")
        if args.trial and compared and not args.spec:
            raise assemble.PackagingError("--trial and --data/--csv each make a report of their own; pass one, or a --spec that uses both")
        if not args.output and not args.check:
            raise assemble.PackagingError("--output is required to write a report (or use --check to only check the inputs)")
        data, title, problems, trial, comparison = [], args.title, [], None, None
        diagrams = False
        if args.trial:
            trial = load(args.trial, "--trial", strict=args.check)
            if not isinstance(trial, dict) or not isinstance(trial.get("runs"), list):
                raise assemble.PackagingError(f"{args.trial} is not trial report data; write it with `trial.py report RUN_DIR --out FILE`")
            data.append(f"av-trial={args.trial}")
            title = title or trial.get("name")
            if not args.spec and not args.narrative:
                # As the page does: the composition checks the narrative it was given, here none; with --general,
                # against the comparison the page derives from the trial.
                problems = validate_comparison(from_trial(trial), {}) if args.general else validate_narrative({}, trial)
        if compared:
            comparison = load_comparison(args.data, strict=args.check) if args.data else None
            if args.csv:
                comparison = comparison_from_csv(args.csv, comparison)
            elif args.data:
                data.append(f"av-comparison={args.data}")
            if not args.spec:
                problems = validate_comparison(comparison, {})
            title = title or next((comparison[k] for k in ("title", "question") if isinstance(comparison.get(k), str) and comparison[k].strip()), None)
        if args.narrative:
            narrative = load(args.narrative, "--narrative", strict=args.check)
            # With --general the narrative names the comparison the page derives from the trial
            # (fromTrial); the page checks it against that comparison and lists problems at its top.
            problems = validate_comparison(comparison, narrative) if compared else validate_comparison(from_trial(trial), narrative) if args.general else validate_narrative(narrative, trial)
            diagrams |= uses_diagrams(narrative)
            data.append(f"av-narrative={args.narrative}")
            title = args.title or (narrative.get("title") or narrative.get("question") if isinstance(narrative, dict) else None) or title
        collection = None
        if args.collection:
            collection = load_collection(args.collection, strict=args.check)
            diagrams |= uses_diagrams(collection)
            if not args.spec:
                problems = validate_collection(collection)
            title = title or (collection.get("title") if isinstance(collection.get("title"), str) and collection["title"].strip() else None)
        if args.spec:
            spec = load(args.spec, "--spec", strict=args.check)
            if not isinstance(spec, dict) or not isinstance(spec.get("sections"), list) or not isinstance(spec.get("title"), str):
                raise assemble.PackagingError(f"{args.spec} needs a string \"title\" and a \"sections\" list")
            # As in the browser, a specification without a comparison of its own borrows the one beside it.
            borrowed = comparison is not None and spec.get("comparison") in (None, False, 0, "")
            effective = {**spec, "comparison": comparison} if borrowed else spec
            if collection is not None and spec.get("collection") in (None, False, 0, ""):
                effective = {**effective, "collection": collection}
            problems = validate_spec(effective, trial, None, collection)
            diagrams |= uses_diagrams(spec)
            data.append(f"av-spec={args.spec}")
            title = args.title or spec["title"]
        if args.check:
            print_problems(problems)
            inputs = ", ".join(str(p) for p in (args.trial, args.data, args.csv, args.narrative, args.spec, args.collection) if p)
            print(f"checked {inputs}: {counted(problems) if problems else 'no problems'}")
            return 1 if any(p["level"] == "error" for p in problems) else 0
        with tempfile.TemporaryDirectory(prefix="av-report-") as scratch:
            body = Path(scratch) / "body.html"
            body.write_text(BODY, encoding="utf-8")
            if args.csv:
                merged = Path(scratch) / "comparison.json"
                merged.write_text(json.dumps(comparison, ensure_ascii=False), encoding="utf-8")
                data.append(f"av-comparison={merged}")
            if collection is not None:
                gathered = Path(scratch) / "collection.json"
                gathered.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
                data.append(f"av-collection={gathered}")
            if args.general:
                marker = Path(scratch) / "general.json"
                marker.write_text("true", encoding="utf-8")
                data.append(f"av-general={marker}")
            namespace = argparse.Namespace(
                body=body, output=args.output, title=title or ("Comparison" if compared else "Report collection" if collection is not None else "Trial report"), lang="en",
                style=[HERE / "styles/agentic-visuals.css"], script=[HERE / "dist/agentic-visuals.js"],
                data=data, asset=[], feature=["mermaid"] if diagrams else [], replace=args.replace,
            )
            content = assemble.assemble(namespace)
            action = assemble.write_output(args.output, content, args.replace)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        print(f"hint: {error.hint}", file=sys.stderr)
        return 1
    except (assemble.PackagingError, OSError, UnicodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("hint: correct the named input or output and rerun; nothing is downloaded", file=sys.stderr)
        return 1
    print(f"{action} {args.output} ({args.output.stat().st_size} bytes)")
    if problems:
        print(f"warning: the inputs have {counted(problems)}; the report lists them at its top", file=sys.stderr)
        print("hint: run the same command with --check to see each one with its fix", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
