# Reference behavior (incorrect): calibrates on the shakedown but uses the spread of a single run
# where it needs the spread of a difference between two runs, so its limits are far too tight.
set -e
cat > trial/decide.py <<'PY'
"""Reject if the candidate's total, any host, or any scenario is more than two standard deviations
below the incumbent, using the standard deviation of a run's total (and of each host's and scenario's
total) across the shakedown runs."""
import csv
import glob
import os
import statistics
import sys
from collections import defaultdict

HISTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "history", "2026-08-shakedown", "run-*.csv")


def load(path):
    runs = defaultdict(dict)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            runs[row["variant"]][(row["scenario"], row["host"])] = int(row["passed"])
    return runs


def groups(run):
    g = defaultdict(int)
    for (s, h), v in run.items():
        g["total"] += v
        g["host:" + h] += v
        g["scenario:" + s] += v
    return g


slots = [groups(r) for p in sorted(glob.glob(HISTORY)) for r in load(p).values()]
sd = {k: statistics.pstdev(s[k] for s in slots) for k in slots[0]}
res = load(sys.argv[1])
inc, cand = groups(res["incumbent"]), groups(res["candidate"])
print("reject" if any(inc[k] - cand[k] > 2 * sd[k] for k in sd) else "adopt")
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
trial/decide.py rejects if the new text is more than two standard deviations below the current text in total, on any host, or on any scenario, with the standard deviations measured on the shakedown runs.
MSG
