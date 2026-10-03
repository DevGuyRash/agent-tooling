"""Writes hidden/model.json and the fixture's results files for router-prompt-decision.

Run from anywhere: `python3 evals/scenarios/router-prompt-decision/hidden/generate.py`. It is
deterministic; rerunning it rewrites the same bytes.

Data-generating model (see `_shared/passcounts.py`): 12 scenarios x 4 models, 5 repeats per cell per
run. Each cell's base log-odds is scenario difficulty a_s ~ N(1.7, 1.0) plus a model term (sonnet +0.4,
gpt-mini +0.05, flash +0.15, llama-70b -0.3) plus cell noise N(0, 0.5), drawn once with seed 5. Every run
draws a run effect N(0, 0.12) and a per-model run effect N(0, 0.15). v4 has no shift. v5 is the same model
except that every flash cell is shifted by -1.5 log-odds (flash's pass rate falls from about 0.75 to
about 0.45); the other three models are unchanged. Five runs are drawn in order with seed 68: three weekly
nightly snapshots of v4, then the side-by-side run's v4 and v5. Seed 68 is the first seed whose draw
keeps every single flash cell's drop within the cell-to-cell swings v4 shows against itself while flash's
total falls below every v4 run by at least twice the largest per-model difference between two v4 runs
(asserted below). In this draw v4's four flash results happen to sit within one pass of each other (44,
45, 45, 45; under the model the median range over four runs is 7, and a range this tight occurs about 1%
of the time), so flash's drop looks larger against flash's own runs than against the all-model yardstick
the judge uses (at most 8 between two runs on any model).
"""
import itertools
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "_shared"))
import passcounts as pc  # noqa: E402

FIXTURE = HERE.parent / "fixture"
SCENARIOS = ["password-reset-loop", "vpn-drops-on-wifi", "new-hire-laptop-request", "printer-queue-stuck",
             "shared-mailbox-access", "mfa-phone-replaced", "software-license-renewal", "phishing-report",
             "badge-access-after-hours", "onboarding-account-batch", "data-restore-request",
             "conference-room-display"]
MODELS = ["sonnet", "gpt-mini", "flash", "llama-70b"]
DEGRADED = "flash"
SHIFT = -1.5
NIGHTLIES = ["2026-09-09", "2026-09-16", "2026-09-23"]
SIDE_BY_SIDE = "results/2026-09-30-v5-vs-v4.csv"
FIELDS = ["scenario", "model", "prompt", "repeats", "passed"]


def build_model() -> dict:
    rng = random.Random(5)
    a = {s: rng.gauss(1.7, 1.0) for s in SCENARIOS}
    b = {"sonnet": 0.4, "gpt-mini": 0.05, "flash": 0.15, "llama-70b": -0.3}
    logit = {f"{s}|{h}": round(a[s] + b[h] + rng.gauss(0, 0.5), 3) for s in SCENARIOS for h in MODELS}
    return {"scenarios": SCENARIOS, "settings": MODELS, "setting_field": "model", "repeats": 5,
            "run_sd": 0.12, "setting_run_sd": 0.15, "logit": logit,
            "alternatives": {"v4": "no shift", "v5": f"shift {SHIFT} on every {DEGRADED} cell, none elsewhere"}}


def main():
    model = build_model()
    (HERE / "model.json").write_text(json.dumps(model, indent=1) + "\n")
    m = pc.load_model(HERE / "model.json")
    rng = random.Random(68)
    v4_runs = [pc.sample(m, rng) for _ in range(4)]
    v5 = pc.sample(m, rng, {(s, DEGRADED): SHIFT for s in SCENARIOS})
    v4 = v4_runs[3]

    # The draw must be the one the scenario describes: flash far below every v4 run in total, each
    # flash cell's drop no larger than v4's own cell swings, the other models inside v4's spread.
    flash = [pc.by_setting(r)[DEGRADED] for r in v4_runs]
    model_spread = max(max(pc.by_setting(r)[h] for r in v4_runs) - min(pc.by_setting(r)[h] for r in v4_runs)
                       for h in MODELS)
    assert min(flash) - pc.by_setting(v5)[DEGRADED] >= max(15, 2 * model_spread), (flash, model_spread)
    v4_cell_swing = max(pc.compare(x, y)["max_cell_drop"] for x, y in itertools.permutations(v4_runs, 2))
    assert max(v4[(s, DEGRADED)] - v5[(s, DEGRADED)] for s in SCENARIOS) <= min(v4_cell_swing, 3)
    for h in MODELS:
        if h != DEGRADED:
            per = [pc.by_setting(r)[h] for r in v4_runs]
            assert min(per) - 1 <= pc.by_setting(v5)[h] <= max(per) + 1, (h, per)
    totals = [pc.total(r) for r in v4_runs]
    assert min(totals) - pc.total(v5) >= max(totals) - min(totals), (totals, pc.total(v5))

    (FIXTURE / "results" / "nightly").mkdir(parents=True, exist_ok=True)
    for date, counts in zip(NIGHTLIES, v4_runs[:3]):
        (FIXTURE / "results" / "nightly" / f"{date}.csv").write_text(
            pc.to_csv(FIELDS, pc.rows_for(m, counts, "prompt", "v4", "model")))
    rows = []
    for s, h in m["cells"]:
        for label, counts in (("v4", v4), ("v5", v5)):
            rows.append({"scenario": s, "model": h, "prompt": label, "repeats": m["repeats"], "passed": counts[(s, h)]})
    (FIXTURE / SIDE_BY_SIDE).write_text(pc.to_csv(FIELDS, rows))


if __name__ == "__main__":
    main()
