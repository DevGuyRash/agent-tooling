#!/usr/bin/env python3
"""Write a fictional trial in the shape `trial.py report` produces.

Every arm, case, run, verdict and number here is invented for demonstrating and
testing the visual library; nothing describes a real comparison. The output is
deterministic, so its previews and tests are reproducible.

  python3 make_fictional_trial.py > fictional-trial.json
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import sys

# The guidance each arm received. The two copies of the current guidance are the
# same text, so the distance between their results is chance alone.
CURRENT = """# Reply guidance

Write a short reply that answers the request.
Keep it under 120 words.
Use plain language and a friendly tone.
Do not add facts the request does not give you.
"""
CHECKLIST = """# Reply guidance

Write a short reply that answers the request.
Keep it under 120 words.
Use plain language and a friendly tone.

Before you send it, check each point:
- Every fact in the reply appears in the request or its attachment.
- The reply answers the question that was asked, not a nearby one.
- Names, dates and numbers match the source exactly.
- Nothing is promised that the request does not allow.
"""
WORKED_EXAMPLE = """# Reply guidance

Write a short reply that answers the request.
Keep it under 120 words.
Use plain language and a warm tone.
Do not add facts the request does not give you.

Example request: "Summarize the notice about Tuesday's water outage."
Example reply: "Water will be off on Tuesday from 9 to 11 in the morning while the main is repaired. Fill a jug beforehand; nothing is needed afterwards."
The example uses only the times and the reason the notice gives.
"""


def arm(text: str) -> dict:
    """An arm's plan entry as `trial.py report` writes it: settings, the digest of its instructions and their text."""
    return {"executor": "command", "model": "fictional-small", "effort": "low",
            "instructions_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "instructions_text": text, "instructions_truncated": False}


ARMS = {"current": arm(CURRENT), "current-copy": arm(CURRENT), "checklist": arm(CHECKLIST), "worked-example": arm(WORKED_EXAMPLE)}
# (name, prompt, pass rates by arm, description, what the judge counts as a pass)
CASES = [
    ("label-a-photo", "Write alt text for the attached photograph of a harbour at dusk.", {"current": .55, "current-copy": .55, "checklist": .75, "worked-example": .85},
     "Alt text for one photograph: a harbour at dusk with moored boats and no visible names or signs, so any named boat, person or place is invented.",
     "the alt text names the harbour, the dusk light and the mood in under 40 words, and names no boat, person or place the photograph does not show"),
    ("summarize-minutes", "Summarize these committee minutes for someone who missed the meeting.", {"current": .7, "current-copy": .7, "checklist": .8, "worked-example": .8},
     "Minutes of a committee meeting with four agenda items; item 4 records a budget decision and who owns its follow-up.",
     "the summary covers all four items, includes the budget decision from item 4 and names who owns each follow-up"),
    ("reply-to-complaint", "Draft a reply to this customer complaint about a late delivery.", {"current": .6, "current-copy": .6, "checklist": .55, "worked-example": .9},
     "A customer's complaint about a delivery that arrived a week late. The policy attached allows a voucher, not a refund.",
     "the reply apologizes once, states the new delivery date and offers only the remedy the policy allows"),
    ("explain-a-chart", "Explain what this rainfall chart shows to a ten-year-old.", {"current": .8, "current-copy": .8, "checklist": .85, "worked-example": .8},
     "A bar chart of monthly rainfall for one town over a year, wettest in November.",
     "the explanation reads the bars as rainfall, names the wettest month and uses no word a ten-year-old would not know"),
]
JUDGE_QUESTION = "Does the reply do what the request asks without inventing facts?"
REPEATS = 6
# Each case's word limit and the range its replies' lengths fall in: alt text is
# held to 40 words by its pass criterion, every other reply to the guidance's 120.
WORDS = {"label-a-photo": (40, 22, 44), "summarize-minutes": (120, 60, 132), "reply-to-complaint": (120, 55, 128), "explain-a-chart": (120, 50, 130)}
REASONS_PASS = ["Names the scene, the light and the mood without inventing detail.", "Covers every decision and who owns each follow-up.", "Apologizes once, states the new date and offers a remedy.", "Uses one comparison a child would know and no jargon."]
REASONS_FAIL = ["Invents a boat name the photograph does not show.", "Omits the budget decision recorded in item 4.", "Promises a refund the policy does not allow.", "Reads the axis as temperature instead of rainfall."]


def wilson(k: int, n: int) -> list | None:
    if n == 0:
        return [0.0, 1.0]
    z, p = 1.96, k / n
    centre, spread, denom = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)), 1 + z * z / n
    return [max(0.0, (centre - spread) / denom), min(1.0, (centre + spread) / denom)]


def main() -> None:
    rng = random.Random(20261005)
    runs = []
    for case_index, (case, _prompt, rates, _description, _pass_when) in enumerate(CASES):
        for repeat in range(1, REPEATS + 1):
            for arm in ARMS:
                invalid = (arm == "worked-example" and case == "summarize-minutes" and repeat in (2, 5)) or (arm == "checklist" and case == "explain-a-chart" and repeat == 3)
                passed = None if invalid else rng.random() < rates[arm]
                facts = rng.random() < (0.95 if passed else 0.6)
                tokens = int(rng.lognormvariate(5.3 + (0.35 if arm == "worked-example" else 0.15 if arm == "checklist" else 0), 0.35))
                limit, shortest, longest = WORDS[case]
                words = None if invalid else shortest + round(rng.random() * (longest - shortest))
                runs.append({
                    "job": f"{case}__{arm}__r{repeat}", "scenario": case, "arm": arm, "repeat": repeat,
                    "status": "timeout" if invalid else "ok", "passed": passed, "valid": passed is not None,
                    "invalid_reason": "timeout" if invalid else None,
                    "checks": {} if invalid else {"reply_written": True, "no_invented_facts": facts, "within_length": words <= limit, "words": words},
                    "judge": None if invalid else {"verdict": "pass" if passed else "fail", "reason": REASONS_PASS[case_index] if passed else REASONS_FAIL[case_index]},
                    "usage": {} if invalid else {"input_tokens": 1800 + rng.randint(0, 400), "output_tokens": tokens},
                    "commands": None, "seconds": 300.0 if invalid else round(rng.uniform(6, 22) * (1.3 if arm == "worked-example" else 1), 1),
                    "setup_seconds": 0.4, "checks_seconds": 0.2, "judge_seconds": None if invalid else round(rng.uniform(3, 7), 1),
                    "confined": True, "artifact_missing": False,
                    "final_message_excerpt": "" if invalid else f"(fictional output for {case}, {arm}, repeat {repeat})",
                })
    arms, scenarios = {}, {}
    for arm in ARMS:
        rs = [r for r in runs if r["arm"] == arm]
        ok = [r for r in rs if r["passed"] is not None]
        k = sum(1 for r in ok if r["passed"])
        arms[arm] = {"passed": k, "valid": len(ok), "runs": len(rs), "interval": wilson(k, len(ok))}
        for case, *_ in CASES:
            cs = [r for r in rs if r["scenario"] == case]
            cok = [r for r in cs if r["passed"] is not None]
            ck = sum(1 for r in cok if r["passed"])
            scenarios[f"{case}|{arm}"] = {"scenario": case, "arm": arm, "passed": ck, "valid": len(cok), "runs": len(cs),
                                         "invalid": sorted({r["invalid_reason"] for r in cs if r["passed"] is None}), "interval": wilson(ck, len(cok))}

    def pair_stats(a_wins: int, b_wins: int, tie: int, inconsistent: int) -> dict:
        decisive = a_wins + b_wins
        return {"a_wins": a_wins, "b_wins": b_wins, "tie": tie, "inconsistent": inconsistent, "invalid": 0,
                "pairs": decisive + tie + inconsistent, "decisive": decisive,
                "a_win_rate": a_wins / decisive if decisive else None, "a_win_rate_interval": wilson(a_wins, decisive) if decisive else None}
    per_case = {"label-a-photo": (4, 1, 1, 0), "summarize-minutes": (2, 1, 1, 0), "reply-to-complaint": (5, 0, 0, 1), "explain-a-chart": (1, 2, 2, 1)}
    overall = tuple(sum(v[i] for v in per_case.values()) for i in range(4))
    pairwise = {"worked-example__current": {"arms": ["worked-example", "current"], "judge": {"executor": "command", "model": "fictional-judge"},
                                            "overall": pair_stats(*overall), "scenarios": {c: pair_stats(*v) for c, v in per_case.items()}}}
    report = {
        "name": "fictional-reply-guidance", "run_directory": "trials/fictional-reply-guidance",
        "plan": {
            "arms": ARMS,
            "scenarios": [{"name": c, "prompt": p, "followups": [], "judge": {"question": JUDGE_QUESTION, "pass_when": pass_when}, "judge_role": None,
                           "required": ["reply_written"], "artifact": None, "description": description} for c, p, _, description, pass_when in CASES],
            "judge": {"executor": "command", "model": "fictional-judge"},
            "decision_rule": "Fixed before any result. Adopt the guidance arm whose pooled pass rate exceeds both copies of the current guidance by at least 15 points, provided no case falls below the current guidance by more than one run.",
        },
        "runs": runs, "arms": arms, "scenarios": scenarios, "pairwise": pairwise,
    }
    json.dump(report, sys.stdout, indent=1)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
