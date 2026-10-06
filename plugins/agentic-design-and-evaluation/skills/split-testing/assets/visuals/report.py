#!/usr/bin/env python3
"""Write one self-contained HTML report from trial data, a report specification, or both.

  report.py --trial REPORT.json [--narrative NARRATIVE.json] --output report.html
  report.py --spec SPEC.json [--trial REPORT.json] --output report.html
  report.py --check --trial REPORT.json [--narrative NARRATIVE.json]
  report.py --check --spec SPEC.json [--trial REPORT.json]
  report.py --skeleton [NARRATIVE.json] --trial REPORT.json

REPORT.json is what `trial.py report RUN_DIR` writes. NARRATIVE.json adds the
decision, labels and extra sections to the default trial composition; SPEC.json
is a complete report specification instead (see catalog.md). The library renders
the report in the reader's browser from the embedded data, so this needs only
Python: no Node.js, no network, no build step.

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
reference, and an empty decision to fill in. Keys starting with $ are notes
the report ignores.
"""
from __future__ import annotations

import argparse
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
}
BLOCK_TYPES = sorted(BLOCKS)

SECTION = {"id": "section-id", "title": "text", "label": "text", "lead": "prose", "blocks": {"list": "block"}}
SPEC = {
    "fields": {
        "title": "string", "kicker": "text", "summary": "prose",
        "meta": {"list": {"fields": {"label": "text", "value": "text"}, "required": ["label", "value"]}},
        "arms": {"list": {"fields": {"id": "arm-ref", "label": "text", "note": "text"}, "required": ["id"]}},
        "sections": {"list": {"fields": SECTION, "required": ["title", "blocks"]}},
        "footer": "text", "trial": "any", "cases": {"record": "text", "keys": "case-ref"}, "problems": "any",
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

DESCRIPTIONS = {
    "text": "text", "string": "text", "prose": "text or a list of paragraphs", "number": "a number", "count": "a whole number of 0 or more",
    "rate": "a number from 0 to 1", "boolean": "true or false", "null": "null", "any": "any value", "block": "a block object",
    "arm": "an arm id", "arm-ref": "an arm id", "arm-label": "an arm id", "case": "a case id", "case-ref": "a case id", "check": "a check name", "pair": "a pairwise key",
    "measure": "a measure id", "section-id": "a section id",
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
}
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


def known_from(trial) -> dict:
    known = {"trial": False, "arms": [], "cases": [], "checks": [], "pairs": [], "settings": {}}
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
        if not spec or (spec[0] and not self.known["trial"]):
            return
        source, noun, many, level, tail = spec
        options = self.known[source] if source else MEASURES
        if value in options:
            return
        s = suggest(value, options)
        hint = f'did you mean "{s}"?' if s else f"{many}: {list_of(options)}" if options else f"this trial has no {re.sub(r' in this trial$', '', many)}"
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
        needs = schema.get("trial")
        own = needs[len("without-"):] if needs and needs.startswith("without-") else None
        if not self.known["trial"] and (needs == "always" or (own is not None and v.get(own) is None)):
            self.add("error", at, f"the {kind} block needs trial data{f' or its own {chr(34)}{own}{chr(34)}' if own is not None else ''}", "pass --trial to report.py, or set the specification's \"trial\" field")
        self.shape(v, schema, at, skip=("type",))
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


def validate_spec(spec, trial=None) -> list[dict]:
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
    c = Checker(known_from(spec.get("trial") or trial), "spec")

    def check_trial(value, where: str) -> None:
        if not isinstance(value, dict) or not isinstance(value.get("runs"), list):
            c.add("error", where, "is not trial report data", "write it with trial.py report RUN_DIR --out FILE")

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

    c.shape(spec, SPEC, "", {"trial": check_trial, "sections": check_sections})
    return ordered(c.problems)


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


# --------------------------------------------------------------------------- command


def main() -> int:
    summary, _, usage = (__doc__ or "").partition("\n\n")
    parser = argparse.ArgumentParser(description=summary, formatter_class=argparse.RawDescriptionHelpFormatter, epilog=usage)
    parser.add_argument("--trial", type=Path, help="JSON from `trial.py report RUN_DIR`")
    parser.add_argument("--narrative", type=Path, help="decision, labels and extra sections for the trial composition")
    parser.add_argument("--spec", type=Path, help="a complete report specification (replaces the trial composition)")
    parser.add_argument("--output", type=Path, help="standalone HTML file to write (required unless --check or --skeleton)")
    parser.add_argument("--title", help="document title (default: the report's own title)")
    parser.add_argument("--replace", action="store_true", help="replace a differing existing output")
    parser.add_argument("--check", action="store_true", help="check the inputs and print every problem; write nothing; exit 1 on an error")
    parser.add_argument("--skeleton", nargs="?", const="-", metavar="FILE", help="print a starter narrative for --trial, or write it to FILE")
    args = parser.parse_args()
    try:
        if args.skeleton is not None:
            if not args.trial or args.narrative or args.spec or args.check or args.output:
                raise assemble.PackagingError("--skeleton takes only --trial (and --replace when writing a file)")
            trial = load(args.trial, "--trial", strict=True)
            if not isinstance(trial, dict) or not isinstance(trial.get("runs"), list):
                raise assemble.PackagingError(f"{args.trial} is not trial report data; write it with `trial.py report RUN_DIR --out FILE`")
            done = write_skeleton(skeleton(trial, args.trial.name), args.skeleton, args.replace)
            if done:
                print(done)
            return 0
        if args.narrative and not args.trial:
            raise assemble.PackagingError("--narrative needs --trial")
        if not args.trial and not args.spec:
            raise assemble.PackagingError("supply --trial, --spec, or both")
        if args.narrative and args.spec:
            raise assemble.PackagingError("--narrative shapes the trial composition; a --spec replaces it, so pass one or the other")
        if not args.output and not args.check:
            raise assemble.PackagingError("--output is required to write a report (or use --check to only check the inputs)")
        data, title, problems, trial = [], args.title, [], None
        diagrams = False
        if args.trial:
            trial = load(args.trial, "--trial", strict=args.check)
            if not isinstance(trial, dict) or not isinstance(trial.get("runs"), list):
                raise assemble.PackagingError(f"{args.trial} is not trial report data; write it with `trial.py report RUN_DIR --out FILE`")
            data.append(f"av-trial={args.trial}")
            title = title or trial.get("name")
        if args.narrative:
            narrative = load(args.narrative, "--narrative", strict=args.check)
            problems = validate_narrative(narrative, trial)
            diagrams |= uses_diagrams(narrative)
            data.append(f"av-narrative={args.narrative}")
            title = args.title or (narrative.get("title") or narrative.get("question") if isinstance(narrative, dict) else None) or title
        if args.spec:
            spec = load(args.spec, "--spec", strict=args.check)
            if not isinstance(spec, dict) or not isinstance(spec.get("sections"), list) or not isinstance(spec.get("title"), str):
                raise assemble.PackagingError(f"{args.spec} needs a string \"title\" and a \"sections\" list")
            problems = validate_spec(spec, trial)
            diagrams |= uses_diagrams(spec)
            data.append(f"av-spec={args.spec}")
            title = args.title or spec["title"]
        if args.check:
            print_problems(problems)
            inputs = ", ".join(str(p) for p in (args.trial, args.narrative, args.spec) if p)
            print(f"checked {inputs}: {counted(problems) if problems else 'no problems'}")
            return 1 if any(p["level"] == "error" for p in problems) else 0
        with tempfile.TemporaryDirectory(prefix="av-report-") as scratch:
            body = Path(scratch) / "body.html"
            body.write_text(BODY, encoding="utf-8")
            namespace = argparse.Namespace(
                body=body, output=args.output, title=title or "Trial report", lang="en",
                style=[HERE / "styles/agentic-visuals.css"], script=[HERE / "dist/agentic-visuals.js"],
                data=data, asset=[], feature=["mermaid"] if diagrams else [], replace=args.replace,
            )
            content = assemble.assemble(namespace)
            action = assemble.write_output(args.output, content, args.replace)
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
