#!/usr/bin/env python3
"""Write a fictional trial in the shape `trial.py report` produces.

Every arm, case, run, verdict and number here is invented for demonstrating and
testing the visual library; nothing describes a real comparison. The output is
deterministic, so its previews and tests are reproducible.

  python3 make_fictional_trial.py > fictional-trial.json
"""
from __future__ import annotations

import json
import math
import random
import sys

ARMS = {
    "current": {"executor": "command", "model": "fictional-small", "effort": "low", "instructions_sha256": "3f1a" * 16},
    "current-copy": {"executor": "command", "model": "fictional-small", "effort": "low", "instructions_sha256": "3f1a" * 16},
    "checklist": {"executor": "command", "model": "fictional-small", "effort": "low", "instructions_sha256": "9c2e" * 16},
    "worked-example": {"executor": "command", "model": "fictional-small", "effort": "low", "instructions_sha256": "b7d4" * 16},
}
CASES = [
    ("label-a-photo", "Write alt text for the attached photograph of a harbour at dusk.", {"current": .55, "current-copy": .55, "checklist": .75, "worked-example": .85}),
    ("summarize-minutes", "Summarize these committee minutes for someone who missed the meeting.", {"current": .7, "current-copy": .7, "checklist": .8, "worked-example": .8}),
    ("reply-to-complaint", "Draft a reply to this customer complaint about a late delivery.", {"current": .6, "current-copy": .6, "checklist": .55, "worked-example": .9}),
    ("explain-a-chart", "Explain what this rainfall chart shows to a ten-year-old.", {"current": .8, "current-copy": .8, "checklist": .85, "worked-example": .8}),
]
REPEATS = 6
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
    for case_index, (case, _prompt, rates) in enumerate(CASES):
        for repeat in range(1, REPEATS + 1):
            for arm in ARMS:
                invalid = (arm == "worked-example" and case == "summarize-minutes" and repeat in (2, 5)) or (arm == "checklist" and case == "explain-a-chart" and repeat == 3)
                passed = None if invalid else rng.random() < rates[arm]
                facts = rng.random() < (0.95 if passed else 0.6)
                tokens = int(rng.lognormvariate(6.4 + (0.35 if arm == "worked-example" else 0.15 if arm == "checklist" else 0), 0.35))
                runs.append({
                    "job": f"{case}__{arm}__r{repeat}", "scenario": case, "arm": arm, "repeat": repeat,
                    "status": "timeout" if invalid else "ok", "passed": passed, "valid": passed is not None,
                    "invalid_reason": "timeout" if invalid else None,
                    "checks": {} if invalid else {"reply_written": True, "no_invented_facts": facts, "within_length": rng.random() < 0.9, "words": tokens // 2},
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
        for case, _, _ in CASES:
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
            "scenarios": [{"name": c, "prompt": p, "followups": [], "judge": {"question": "Does the reply do what the request asks without inventing facts?"}, "judge_role": None, "required": ["reply_written"], "artifact": None} for c, p, _ in CASES],
            "judge": {"executor": "command", "model": "fictional-judge"},
            "decision_rule": "Fixed before any result. Adopt the guidance arm whose pooled pass rate exceeds both copies of the current guidance by at least 15 points, provided no case falls below the current guidance by more than one run.",
        },
        "runs": runs, "arms": arms, "scenarios": scenarios, "pairwise": pairwise,
    }
    json.dump(report, sys.stdout, indent=1)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
