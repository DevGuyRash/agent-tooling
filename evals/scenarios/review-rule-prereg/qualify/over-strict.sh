# Reference behavior (incorrect, the failure under test): "no worse anywhere" as a per-cell clause.
set -e
cat > trial/decide.py <<'PY'
"""Decision rule: the candidate must be no worse than the incumbent on any scenario on any host."""
import csv
import sys
from collections import defaultdict

passed = defaultdict(dict)
with open(sys.argv[1], newline="") as f:
    for row in csv.DictReader(f):
        passed[row["variant"]][(row["scenario"], row["host"])] = int(row["passed"])
inc, cand = passed["incumbent"], passed["candidate"]
worse = [c for c in inc if cand[c] < inc[c]]
print("reject" if worse else "adopt")
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
trial/decide.py rejects the new text if it scores lower than the current text on any scenario on any host, so it catches a broken host or scenario; otherwise it adopts.
MSG
