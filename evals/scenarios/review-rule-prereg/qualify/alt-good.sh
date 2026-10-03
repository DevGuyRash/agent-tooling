# Reference behavior (alternative correct): computes its limits when it runs, from every pairing of
# the shakedown slots, and explains the numbers before printing the decision on the last line.
set -e
cat > trial/decide.py <<'PY'
"""Trial decision rule, fixed before the trial: python3 trial/decide.py results.csv

Reject when the candidate's drop against the incumbent, in total, on any one host, or on any one
scenario, is larger than any drop seen between two runs of the SAME instructions in the August
shakedown (every pairing of its 24 slot runs). Otherwise adopt. Malformed input: inconclusive.
"""
import csv
import glob
import itertools
import os
import sys
from collections import defaultdict

HISTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "history", "2026-08-shakedown", "run-*.csv")


def load(path):
    runs = defaultdict(dict)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            runs[row["variant"]][(row["scenario"], row["host"])] = int(row["passed"])
    return runs


def drops(a, b):
    """How much b falls short of a: (total, worst host, worst scenario)."""
    host, scen = defaultdict(int), defaultdict(int)
    for cell, v in a.items():
        host[cell[1]] += v - b[cell]
        scen[cell[0]] += v - b[cell]
    return sum(a[c] - b[c] for c in a), max(host.values()), max(scen.values())


def limits():
    slots = [r for path in sorted(glob.glob(HISTORY)) for r in load(path).values()]
    seen = [drops(a, b) for a, b in itertools.permutations(slots, 2)]
    return tuple(max(s[i] for s in seen) for i in range(3))


def main(path):
    runs = load(path)
    inc, cand = runs.get("incumbent"), runs.get("candidate")
    if not inc or not cand or set(inc) != set(cand) or len(inc) != 40:
        return "inconclusive"
    lim, got = limits(), drops(inc, cand)
    print(f"candidate drop: total {got[0]}, worst host {got[1]}, worst scenario {got[2]}; "
          f"largest between identical runs: {lim[0]}, {lim[1]}, {lim[2]}")
    return "reject" if any(g > l for g, l in zip(got, lim)) else "adopt"


if __name__ == "__main__":
    print(main(sys.argv[1]))
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done: trial/decide.py. It works out, from the shakedown runs, the largest drop two runs of the same instructions ever showed (every pairing of the 24 slot runs: in total, on one host, on one scenario) and rejects the new text only if it falls further behind than that on any of the three. Otherwise it adopts. It doesn't judge single scenario-host cells, because identical text already swings by up to 5 of 6 in a cell; a broken host or scenario shows up as a much larger drop at the host or scenario level.
MSG
