"""Pass counts drawn from a fixed pass-rate model, and the arithmetic checks need on them.

Used by the scenarios that hand an agent repeated, noisy trial results and ask it to compare two
alternatives (`support-prompt-decision`, `review-rule-prereg`, `router-prompt-decision`). Each scenario's
`hidden/model.json` fixes its model; its `hidden/generate.py` writes the fixture's data files from that
model with fixed seeds, and a check can draw fresh data from the same model.

The model. A design is a grid of cells (scenario x setting, where a setting is a model or host), each run
`repeats` times per alternative. Cell c has a base log-odds of passing, `logit[c]`. One run of one
alternative over the whole design draws a run effect d ~ N(0, run_sd) and, for each setting h, a
setting-run effect g_h ~ N(0, setting_run_sd) (a provider having a bad night), and then each cell's pass
count is Binomial(repeats, sigmoid(logit[c] + d + g_h + shift[c])). `shift` is zero for an alternative that
is identical to the incumbent; a real difference is a nonzero shift on some cells. Identical alternatives
therefore differ only by the binomial draws and the two run-level effects.
"""
import csv
import io
import json
import math
import random
from pathlib import Path


def load_model(path) -> dict:
    model = json.loads(Path(path).read_text())
    model["cells"] = [(s, h) for s in model["scenarios"] for h in model["settings"]]
    return model


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def sample(model: dict, rng: random.Random, shift: dict | None = None) -> dict:
    """One run of one alternative: {(scenario, setting): passed}."""
    shift = shift or {}
    n = model["repeats"]
    d = rng.gauss(0.0, model["run_sd"])
    g = {h: rng.gauss(0.0, model["setting_run_sd"]) for h in model["settings"]}
    out = {}
    for s, h in model["cells"]:
        p = sigmoid(model["logit"][f"{s}|{h}"] + d + g[h] + shift.get((s, h), 0.0))
        out[(s, h)] = sum(rng.random() < p for _ in range(n))
    return out


def to_csv(fields: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def rows_for(model: dict, counts: dict, label_field: str, label: str, setting_field: str) -> list[dict]:
    return [{"scenario": s, setting_field: h, label_field: label, "repeats": model["repeats"],
             "passed": counts[(s, h)]} for s, h in model["cells"]]


def read_counts(text: str, label_field: str, setting_field: str) -> dict:
    """{label: {(scenario, setting): passed}} from a results CSV."""
    out: dict = {}
    for r in csv.DictReader(io.StringIO(text)):
        out.setdefault(r[label_field], {})[(r["scenario"], r[setting_field])] = int(r["passed"])
    return out


def total(counts: dict) -> int:
    return sum(counts.values())


def by_setting(counts: dict) -> dict:
    out: dict = {}
    for (s, h), v in counts.items():
        out[h] = out.get(h, 0) + v
    return out


def by_scenario(counts: dict) -> dict:
    out: dict = {}
    for (s, h), v in counts.items():
        out[s] = out.get(s, 0) + v
    return out


def compare(base: dict, other: dict) -> dict:
    """How `other` differs from `base`, cell by cell and in aggregate (other minus base)."""
    cells = sorted(base)
    drops = [base[c] - other[c] for c in cells]
    hb, ho = by_setting(base), by_setting(other)
    sb, so = by_scenario(base), by_scenario(other)
    return {
        "total_diff": total(other) - total(base),
        "cells_lower": sum(d > 0 for d in drops),
        "cells_higher": sum(d < 0 for d in drops),
        "max_cell_drop": max(drops),
        "setting_diff": {h: ho[h] - hb[h] for h in hb},
        "scenario_diff": {s: so[s] - sb[s] for s in sb},
    }
