# Reference behavior (incorrect): the good rule's limits with the difference taken the wrong way
# round, so it rejects improvements and adopts breakage.
set -e
cat > trial/decide.py <<'PY'
"""Reject at a drop of 30 in total, 13 on a host, or 11 on a scenario (beyond the shakedown's worst)."""
import csv
import sys
from collections import defaultdict

passed = defaultdict(dict)
with open(sys.argv[1], newline="") as f:
    for row in csv.DictReader(f):
        passed[row["variant"]][(row["scenario"], row["host"])] = int(row["passed"])
inc, cand = passed["incumbent"], passed["candidate"]


def worst(group):
    d = defaultdict(int)
    for c in inc:
        d[group(c)] += cand[c] - inc[c]
    return max(d.values())


bad = worst(lambda c: 0) >= 30 or worst(lambda c: c[1]) >= 13 or worst(lambda c: c[0]) >= 11
print("reject" if bad else "adopt")
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
trial/decide.py rejects if the new text drops 30 or more passes in total, 13 on a host, or 11 on a scenario, which is beyond anything identical text did in the shakedown.
MSG
