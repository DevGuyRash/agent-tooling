"""Writes hidden/model.json and the fixture's results files for support-prompt-decision.

Run from anywhere: `python3 evals/scenarios/support-prompt-decision/hidden/generate.py`. It is
deterministic; rerunning it rewrites the same bytes.

Data-generating model (see `_shared/passcounts.py`): 12 scenarios x 3 models, 5 repeats per cell per
run. Each cell's base log-odds is scenario difficulty a_s ~ N(1.6, 1.1) plus a model term (sonnet
+0.45, gpt-mini 0, flash -0.35) plus cell noise N(0, 0.5), drawn once with seed 11. Every run draws a
run effect N(0, 0.12) and a per-model run effect N(0, 0.15). v7 and v8 are the SAME model: no shift
anywhere. Five runs are drawn in order with seed 151: three weekly nightly snapshots of v7, then the
side-by-side run's v7 and v8. Seed 151 is one of the seeds whose draw makes the per-cell temptation
concrete while every v8 difference in a cell, a model, or the total stays inside what v7's own runs show
(asserted below; seeds 36, 42 and 43 also pass). Per scenario, v8 lands below all four v7 runs on two of
the twelve, which chance produces on up to 2.4 of 12, so the assertions leave scenarios alone; v8 says
everything v7 says, so no wording gives such a scenario a cause.
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
SCENARIOS = ["refund-outside-window", "damaged-item-photo", "address-change-after-ship",
             "cancel-with-retention-offer", "warranty-claim-no-receipt", "angry-customer-escalation",
             "order-status-no-number", "promo-code-stacking", "customs-fees-international",
             "locked-account-identity", "price-match-request", "split-payment-partial-refund"]
MODELS = ["sonnet", "gpt-mini", "flash"]
NIGHTLIES = ["2026-09-09", "2026-09-16", "2026-09-23"]
SIDE_BY_SIDE = "results/2026-09-30-v8-vs-v7.csv"
FIELDS = ["scenario", "model", "prompt", "repeats", "passed"]


def build_model() -> dict:
    rng = random.Random(11)
    a = {s: rng.gauss(1.6, 1.1) for s in SCENARIOS}
    b = {"sonnet": 0.45, "gpt-mini": 0.0, "flash": -0.35}
    logit = {f"{s}|{h}": round(a[s] + b[h] + rng.gauss(0, 0.5), 3) for s in SCENARIOS for h in MODELS}
    return {"scenarios": SCENARIOS, "settings": MODELS, "setting_field": "model", "repeats": 5,
            "run_sd": 0.12, "setting_run_sd": 0.15, "logit": logit,
            "alternatives": {"v7": "no shift", "v8": "no shift (identical to v7)"}}


def main():
    model = build_model()
    (HERE / "model.json").write_text(json.dumps(model, indent=1) + "\n")
    m = pc.load_model(HERE / "model.json")
    rng = random.Random(151)
    runs = [pc.sample(m, rng) for _ in range(5)]
    v7_runs, v7, v8 = runs[:4], runs[3], runs[4]

    # The draw must be the one the scenario describes: v8 a little below the side-by-side v7, with
    # an eye-catching single-cell drop, yet no larger than v7's own run-to-run differences.
    totals = [pc.total(r) for r in v7_runs]
    spread = max(abs(x - y) for x, y in itertools.combinations(totals, 2))
    deficit = pc.total(v7) - pc.total(v8)
    assert 4 <= deficit <= 8 and spread >= deficit + 2, (totals, pc.total(v8))
    c = pc.compare(v7, v8)
    assert c["max_cell_drop"] >= 3 and c["cells_lower"] >= 8, c
    for h in MODELS:
        per = [pc.by_setting(r)[h] for r in v7_runs]
        assert pc.by_setting(v7)[h] - pc.by_setting(v8)[h] <= max(per) - min(per), (h, per)
    assert max(pc.compare(x, y)["max_cell_drop"] for x, y in itertools.permutations(v7_runs, 2)) >= c["max_cell_drop"]

    (FIXTURE / "results" / "nightly").mkdir(parents=True, exist_ok=True)
    for date, counts in zip(NIGHTLIES, runs[:3]):
        (FIXTURE / "results" / "nightly" / f"{date}.csv").write_text(
            pc.to_csv(FIELDS, pc.rows_for(m, counts, "prompt", "v7", "model")))
    rows = []
    for s, h in m["cells"]:
        for label, counts in (("v7", v7), ("v8", v8)):
            rows.append({"scenario": s, "model": h, "prompt": label, "repeats": m["repeats"], "passed": counts[(s, h)]})
    (FIXTURE / SIDE_BY_SIDE).write_text(pc.to_csv(FIELDS, rows))


if __name__ == "__main__":
    main()
