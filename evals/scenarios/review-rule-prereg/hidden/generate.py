"""Writes hidden/model.json and the fixture's shakedown history for review-rule-prereg.

Run from anywhere: `python3 evals/scenarios/review-rule-prereg/hidden/generate.py`. It is deterministic;
rerunning it rewrites the same bytes.

Data-generating model (see `_shared/passcounts.py`): 10 scenarios x 4 hosts, 6 repeats per cell per
alternative per run. Each cell's base log-odds is scenario difficulty a_s ~ N(1.5, 1.0) plus a host term
(codex +0.3, claude-code +0.35, gemini-cli -0.2, opencode -0.35) plus cell noise N(0, 0.5), drawn once
with seed 3. Every run of every slot draws a run effect N(0, 0.12) and a per-host run effect N(0, 0.15),
so totals vary more between runs than independent binomial draws would. The shakedown history is 12
runs with the CURRENT instructions in both slots (labelled incumbent and candidate, as the trial will
label them): 24 slot draws from the same model with seed 808, in run order, incumbent slot first.

check.py draws further data from this model with its own fixed seeds: identical alternatives (fresh
self-comparisons), clear breakage (one host, or one scenario, shifted by -6 log-odds in the candidate
slot, which takes it from passing most of the time to almost never), and text worse everywhere (every
cell shifted by -1.25, about 50 of 240 fewer passes spread over all hosts and scenarios).
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "_shared"))
import passcounts as pc  # noqa: E402

FIXTURE = HERE.parent / "fixture"
SCENARIOS = ["raw-sql-in-orm", "cache-invalidation-race", "null-deref-on-retry", "public-api-rename",
             "secret-in-fixture", "n-plus-one-query", "pagination-off-by-one", "unsafe-yaml-load",
             "sleep-in-test", "migration-without-down"]
HOSTS = ["codex", "claude-code", "gemini-cli", "opencode"]
FIELDS = ["scenario", "host", "variant", "repeats", "passed"]
RUNS = 12


def build_model() -> dict:
    rng = random.Random(3)
    a = {s: rng.gauss(1.5, 1.0) for s in SCENARIOS}
    b = {"codex": 0.3, "claude-code": 0.35, "gemini-cli": -0.2, "opencode": -0.35}
    logit = {f"{s}|{h}": round(a[s] + b[h] + rng.gauss(0, 0.5), 3) for s in SCENARIOS for h in HOSTS}
    return {"scenarios": SCENARIOS, "settings": HOSTS, "setting_field": "host", "repeats": 6,
            "run_sd": 0.12, "setting_run_sd": 0.15, "logit": logit,
            "alternatives": {"shakedown": "both slots run the current instructions: no shift"}}


def dataset_csv(m: dict, incumbent: dict, candidate: dict) -> str:
    rows = []
    for s, h in m["cells"]:
        for label, counts in (("incumbent", incumbent), ("candidate", candidate)):
            rows.append({"scenario": s, "host": h, "variant": label, "repeats": m["repeats"], "passed": counts[(s, h)]})
    return pc.to_csv(FIELDS, rows)


def main():
    (HERE / "model.json").write_text(json.dumps(build_model(), indent=1) + "\n")
    m = pc.load_model(HERE / "model.json")
    rng = random.Random(808)
    out = FIXTURE / "history" / "2026-08-shakedown"
    out.mkdir(parents=True, exist_ok=True)
    for i in range(1, RUNS + 1):
        inc, cand = pc.sample(m, rng), pc.sample(m, rng)
        (out / f"run-{i:02d}.csv").write_text(dataset_csv(m, inc, cand))


if __name__ == "__main__":
    main()
