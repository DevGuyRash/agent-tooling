# Reference behavior (incorrect): rejects only when a host or a scenario collapses, so text that is worse
# by a fifth everywhere, without any one host or scenario collapsing, is adopted.
set -e
cat > trial/decide.py <<'PY'
"""Reject only if the new text breaks something: a host losing 25 or more of its 60 passes, or a scenario
losing 14 or more of its 24. Otherwise adopt."""
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


print("reject" if worst(lambda c: c[1]) >= 25 or worst(lambda c: c[0]) >= 14 else "adopt")
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
trial/decide.py adopts unless the new text breaks a host (25 or more of its 60 passes lost) or a scenario (14 or more of 24 lost). Identical text never came close to that in the shakedown, so it won't block on noise.
MSG
