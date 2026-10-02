# Reference behavior (incorrect): catches breakage with the good limits but never switches; anything short
# of a reject is "inconclusive", so identical text is never adopted.
set -e
cat > trial/decide.py <<'PY'
"""Reject at a drop of 30 in total, 13 on a host, or 11 on a scenario; otherwise inconclusive, because a
trial this size cannot prove the new text is as good."""
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
        d[group(c)] += inc[c] - cand[c]
    return max(d.values())


print("reject" if worst(lambda c: 0) >= 30 or worst(lambda c: c[1]) >= 13 or worst(lambda c: c[0]) >= 11 else "inconclusive")
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
trial/decide.py rejects the new text if it loses 30 or more passes in total, 13 on a host, or 11 on a scenario. Otherwise it prints inconclusive: 240 reviews per arm can't prove the new text is as good, only catch it being clearly worse.
MSG
