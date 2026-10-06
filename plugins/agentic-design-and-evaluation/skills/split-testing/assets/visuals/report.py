#!/usr/bin/env python3
"""Write one self-contained HTML report from trial data, a comparison of any alternatives, a report specification, or a mix.

  report.py --trial REPORT.json [--narrative NARRATIVE.json] --output report.html
  report.py --data COMPARISON.json [--csv TABLE.csv] [--narrative NARRATIVE.json] --output report.html
  report.py --csv TABLE.csv [--narrative NARRATIVE.json] --output report.html
  report.py --spec SPEC.json [--trial REPORT.json] [--data COMPARISON.json] --output report.html
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
report specification instead (see catalog.md). The library renders the report
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

FRAME = {"title": "text", "description": "prose", "note": "text", "id": "text"}
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

BLOCKS = {
    "verdict": {"fields": {**FRAME, **VERDICT, "rule": "prose"}, "required": ["headline"]},
    "figures": {"fields": {**FRAME, "items": {"list": {"fields": {"value": {"oneOf": ["text", "null"]}, "label": "text", "note": "text", "tone": {"enum": ["neutral", "pass", "fail", "warn", "invalid"], "warn": True}}, "required": ["label"]}}}, "required": ["items"]},
    "ladder": {
        "trial": "without-rows",
        "fields": {
            **FRAME, "rows": {"list": {"fields": {"arm": "arm-ref", "case": "case-ref", "k": "count", "n": "count", "invalid": "count", "note": "text"}, "required": ["k", "n"], "kn": [["k", "n"]]}},
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
    "cases": {"trial": "always", "fields": {**FRAME, "cases": {"list": "case"}, "arms": {"list": "arm"}, "groups": {"list": GROUP}, "pairs": {"oneOf": [AUTO_OFF, PAIR_SPECS]}, "index": "boolean"}},
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
}
BLOCK_TYPES = sorted(BLOCKS)

SECTION = {"id": "section-id", "title": "text", "label": "text", "lead": "prose", "blocks": {"list": "block"}}
SPEC = {
    "fields": {
        "title": "string", "kicker": "text", "summary": "prose",
        "meta": {"list": {"fields": {"label": "text", "value": "text"}, "required": ["label", "value"]}},
        "arms": {"list": {"fields": {"id": "arm-ref", "label": "text", "note": "text"}, "required": ["id"]}},
        "sections": {"list": {"fields": SECTION, "required": ["title", "blocks"]}},
        "footer": "text", "trial": "any", "cases": {"record": "text", "keys": "case-ref"}, "problems": "any", "comparison": "any",
    },
    "required": ["title", "sections"],
}
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
        "footer": "text",
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
        "footer": "text",
    },
}


def comparison_key(ident: str) -> str:
    return COMPARISON_ALIASES.get(ident, ident)

DESCRIPTIONS = {
    "text": "text", "string": "text", "prose": "text or a list of paragraphs", "number": "a number", "count": "a whole number of 0 or more",
    "rate": "a number from 0 to 1", "boolean": "true or false", "null": "null", "any": "any value", "block": "a block object",
    "arm": "an arm id", "arm-ref": "an arm id", "arm-label": "an arm id", "case": "a case id", "case-ref": "a case id", "check": "a check name", "pair": "a pairwise key",
    "measure": "a measure id", "section-id": "a section id", "alternative": "an alternative id", "alternative-ref": "an alternative id", "metric": "a metric id", "comparison-case": "a case id",
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
}
FROM_COMPARISON = ("alternatives", "metrics", "ccases")
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


def known_from(trial, comparison=None) -> dict:
    known = {"trial": False, "arms": [], "cases": [], "checks": [], "pairs": [], "settings": {}, "comparison": False, "alternatives": [], "metrics": [], "ccases": []}
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
        of_comparison = source in FROM_COMPARISON
        if source and not ((self.known["comparison"] and (source != "ccases" or self.known["ccases"])) if of_comparison else self.known["trial"]):
            return
        options = self.known[source] if source else MEASURES
        if value in options:
            return
        s = suggest(value, options)
        hint = f'did you mean "{s}"?' if s else f"{many}: {list_of(options)}" if options else f"this {'comparison' if of_comparison else 'trial'} has no {re.sub(r' in this (trial|comparison)$', '', many)}"
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


def ordered(problems: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for p in problems:
        key = (p["level"], p["where"], p["message"])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return [p for p in unique if p["level"] == "error"] + [p for p in unique if p["level"] != "error"]


def validate_spec(spec, trial=None, comparison=None) -> list[dict]:
    """Problems in a report specification, as src/validate.ts validateSpec finds them."""
    if not isinstance(spec, dict):
        return [{"level": "error", "where": "spec", "message": f'expected an object with "title" and "sections", found {found(spec)}', "hint": 'a specification is {"title": "…", "sections": [ … ]}'}]
    if isinstance(spec.get("problems"), list):
        carried = []
        for p in spec["problems"]:
            if isinstance(p, dict) and isinstance(p.get("where"), str) and isinstance(p.get("message"), str):
                item = {"level": "error" if p.get("level") == "error" else "warning", "where": p["where"], "message": p["message"]}
                if isinstance(p.get("hint"), str) and p["hint"]:
                    item["hint"] = p["hint"]
                carried.append(item)
        return ordered(carried)
    # As in the browser: a specification without trial data of its own borrows the trial supplied beside it.
    own = spec.get("comparison")
    c = Checker(known_from(spec.get("trial") or trial, own if own not in (None, False, 0, "") else comparison), "spec")

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

    c.shape(spec, SPEC, "", {"trial": check_trial, "comparison": check_comparison, "sections": check_sections})
    return ordered(c.problems)


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
        c.problems.extend(comparison_narrative(narrative, c.known))
    return ordered(c.problems)


def comparison_narrative(narrative, known: dict) -> list[dict]:
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
            if bool(args.trial) == compared or args.narrative or args.spec or args.check or args.output or args.general:
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
        if not args.trial and not args.spec and not compared:
            raise assemble.PackagingError("supply --trial, --data, --csv or --spec")
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
        if compared:
            comparison = load_comparison(args.data, strict=args.check) if args.data else None
            if args.csv:
                comparison = comparison_from_csv(args.csv, comparison)
            elif args.data:
                data.append(f"av-comparison={args.data}")
            if not args.spec:
                problems = validate_comparison(comparison)
            title = title or next((comparison[k] for k in ("title", "question") if isinstance(comparison.get(k), str) and comparison[k].strip()), None)
        if args.narrative:
            narrative = load(args.narrative, "--narrative", strict=args.check)
            # With --general the narrative names the comparison the page derives from the trial
            # (fromTrial); the page checks it against that comparison and lists problems at its top.
            problems = validate_comparison(comparison, narrative) if compared else validate_narrative(narrative, trial) if not args.general else [] if isinstance(narrative, dict) else [
                {"level": "error", "where": "narrative", "message": "expected a JSON object", "hint": "a comparison narrative is an object such as {\"title\": …, \"decision\": …}; see catalog.md"}]
            diagrams |= uses_diagrams(narrative)
            data.append(f"av-narrative={args.narrative}")
            title = args.title or (narrative.get("title") or narrative.get("question") if isinstance(narrative, dict) else None) or title
        if args.spec:
            spec = load(args.spec, "--spec", strict=args.check)
            if not isinstance(spec, dict) or not isinstance(spec.get("sections"), list) or not isinstance(spec.get("title"), str):
                raise assemble.PackagingError(f"{args.spec} needs a string \"title\" and a \"sections\" list")
            # As in the browser, a specification without a comparison of its own borrows the one beside it.
            borrowed = comparison is not None and spec.get("comparison") in (None, False, 0, "")
            problems = validate_spec({**spec, "comparison": comparison} if borrowed else spec, trial)
            diagrams |= uses_diagrams(spec)
            data.append(f"av-spec={args.spec}")
            title = args.title or spec["title"]
        if args.check:
            print_problems(problems)
            inputs = ", ".join(str(p) for p in (args.trial, args.data, args.csv, args.narrative, args.spec) if p)
            print(f"checked {inputs}: {counted(problems) if problems else 'no problems'}")
            return 1 if any(p["level"] == "error" for p in problems) else 0
        with tempfile.TemporaryDirectory(prefix="av-report-") as scratch:
            body = Path(scratch) / "body.html"
            body.write_text(BODY, encoding="utf-8")
            if args.csv:
                merged = Path(scratch) / "comparison.json"
                merged.write_text(json.dumps(comparison, ensure_ascii=False), encoding="utf-8")
                data.append(f"av-comparison={merged}")
            if args.general:
                marker = Path(scratch) / "general.json"
                marker.write_text("true", encoding="utf-8")
                data.append(f"av-general={marker}")
            namespace = argparse.Namespace(
                body=body, output=args.output, title=title or ("Comparison" if compared else "Trial report"), lang="en",
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
