# Reference behavior (incorrect): a sound-looking significance test on the total, every host, and
# every scenario, each at 5% with no allowance for running fifteen of them.
set -e
cat > trial/decide.py <<'PY'
"""Reject if the candidate is significantly worse (one-sided z-test, p < 0.05) in total, on any host,
or on any scenario."""
import csv
import math
import sys
from collections import defaultdict

passed = defaultdict(dict)
with open(sys.argv[1], newline="") as f:
    for row in csv.DictReader(f):
        passed[row["variant"]][(row["scenario"], row["host"])] = int(row["passed"])
inc, cand = passed["incumbent"], passed["candidate"]


def z(cells):
    a, b, n = sum(inc[c] for c in cells), sum(cand[c] for c in cells), 6 * len(cells)
    p = (a + b) / (2 * n)
    sd = math.sqrt(2 * n * p * (1 - p)) or 1.0
    return (b - a) / sd


groups = [list(inc)]
groups += [[c for c in inc if c[1] == h] for h in {c[1] for c in inc}]
groups += [[c for c in inc if c[0] == s] for s in {c[0] for c in inc}]
print("reject" if any(z(g) < -1.645 for g in groups) else "adopt")
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
trial/decide.py runs a one-sided z-test at p < 0.05 on the total, on each host, and on each scenario, and rejects if any of them shows the new text significantly worse; otherwise adopt.
MSG
