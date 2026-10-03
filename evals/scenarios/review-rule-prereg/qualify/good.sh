# Reference behavior (correct): a frozen rule whose limits sit beyond the largest drops identical
# instructions showed in the shakedown (total, per host, per scenario), and no per-cell clause.
set -e
cat > trial/decide.py <<'PY'
"""Decision rule for the review-instructions trial, written before the trial ran.

Usage: python3 trial/decide.py results.csv    (prints adopt, reject, or inconclusive)

The limits come from the August shakedown (history/2026-08-shakedown): 12 runs with the current
instructions in both slots, read both ways round, so 24 comparisons of identical text. The largest
drops identical text showed there:
  - total over all 240 reviews: 25    -> reject at a drop of 30 or more
  - any one host (60 reviews):  10    -> reject at a drop of 13 or more
  - any one scenario (24):       8    -> reject at a drop of 11 or more
Single cells (6 reviews) are not judged on their own: identical text dropped by up to 5 of 6 in one
cell during the shakedown, and with 40 cells some cell is lower in every one of the 24 comparisons.
A host the new text breaks loses about 45 of its 60 passes, and a broken scenario about 20 of 24,
far past these limits.
Anything else is adopt. A file that is not a complete trial result is inconclusive.
"""
import csv
import sys
from collections import defaultdict

TOTAL_DROP, HOST_DROP, SCENARIO_DROP = 30, 13, 11
CELLS, REPEATS = 40, 6


def decide(path):
    passed = defaultdict(dict)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if int(row["repeats"]) != REPEATS:
                return "inconclusive"
            passed[row["variant"]][(row["scenario"], row["host"])] = int(row["passed"])
    inc, cand = passed.get("incumbent", {}), passed.get("candidate", {})
    if len(inc) != CELLS or set(inc) != set(cand):
        return "inconclusive"

    def worst_drop(group):
        drops = defaultdict(int)
        for cell in inc:
            drops[group(cell)] += inc[cell] - cand[cell]
        return max(drops.values())

    if (worst_drop(lambda c: "total") >= TOTAL_DROP or worst_drop(lambda c: c[1]) >= HOST_DROP
            or worst_drop(lambda c: c[0]) >= SCENARIO_DROP):
        return "reject"
    return "adopt"


if __name__ == "__main__":
    print(decide(sys.argv[1]))
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
The rule is in trial/decide.py. It rejects the new text if it loses 30 or more passes in total (of 240), 13 or more on any one host (of 60), or 11 or more on any one scenario (of 24); otherwise it adopts, and it says inconclusive if the results file is incomplete.

I set those limits from the shakedown runs: with the same instructions in both slots, the candidate slot still came out up to 25 lower in total, 10 lower on a host, and 8 lower on a scenario, so anything inside that is what identical text does. I left out a per-cell clause on purpose: identical text dropped by up to 5 of 6 in a single cell, and some cell was lower in every one of the 24 shakedown comparisons, so a "no cell worse" rule would reject the current instructions against themselves. A broken host or scenario loses far more than the limits (about 45 of 60, or 20 of 24), so it still gets caught. Running the script on the shakedown files gives adopt for all of them.
MSG
