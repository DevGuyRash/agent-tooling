#!/usr/bin/env python3
"""Heuristically score the runaway/forever-risk of raw goal text."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import OPEN_ENDED_PHRASES

# Risk bands by cumulative score. Lower score = more bounding signals (verifier, budget,
# scope edges, give-up, terminal state) and thus safer; higher = more runaway/forever risk.
RISK_LOW_MAX = -3      # score <= -3 -> low
RISK_MEDIUM_MAX = 1    # score <= 1  -> medium
RISK_HIGH_MAX = 5      # score <= 5  -> high; above -> extreme


def score(text: str) -> dict:
    lowered = text.lower()
    reasons = []
    points = 0
    for phrase in OPEN_ENDED_PHRASES:
        if phrase in lowered:
            points += 2 if phrase in {"keep improving", "keep up to date", "until satisfied", "as much as possible"} else 1
            reasons.append(f"open-ended phrase: {phrase}")
    checks = [
        (r"\b(test|tests|exit 0|passes|metric|coverage|benchmark|checklist|review)\b", "mentions verifier", -2),
        (r"\b(max|maximum|budget|iterations?|timebox|stop after|changed files|dependencies)\b", "mentions budget", -2),
        (r"\b(out of scope|do not|don't|forbidden|only|limited to)\b", "mentions scope edge", -1),
        (r"\b(stop and report|give up|blocked|infeasible|unavailable|requires decision)\b", "mentions give-up", -2),
        (r"\b(done when|complete when|terminal state|is true|must pass)\b", "mentions terminal state", -2),
    ]
    positives = []
    for pat, desc, delta in checks:
        if re.search(pat, lowered):
            points += delta
            positives.append(desc)
    if len(text.split()) < 8:
        points += 2
        reasons.append("very short request")
    if re.search(r"\b(repo|codebase|everything|all files|whole app|entire project)\b", lowered):
        points += 2
        reasons.append("broad scope")
    if re.search(r"\band\b.*\band\b", lowered):
        points += 1
        reasons.append("possible multi-objective bundle")
    if points <= RISK_LOW_MAX:
        level = "low"
    elif points <= RISK_MEDIUM_MAX:
        level = "medium"
    elif points <= RISK_HIGH_MAX:
        level = "high"
    else:
        level = "extreme"
    return {"forever_risk": level, "score": points, "reasons": reasons, "positive_signals": positives}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", nargs="*", help="Raw goal text. If omitted, read stdin.")
    parser.add_argument("--file", help="Read text from file")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        text = " ".join(args.text)
    else:
        import sys
        text = sys.stdin.read()
    result = score(text)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Forever-risk: {result['forever_risk']} (score {result['score']})")
        for r in result["reasons"]:
            print(f"- {r}")
        if result["positive_signals"]:
            print("Positive signals:")
            for p in result["positive_signals"]:
                print(f"- {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
