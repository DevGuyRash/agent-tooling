# Reference behavior (alternative correct): the good limits, plus a git check that the instructions and the
# rule are the committed versions, and a decision printed inside a sentence that also names "reject".
set -e
cat > trial/decide.py <<'PY'
"""Decision rule for the review-instructions trial, fixed before the trial ran.

Usage: python3 trial/decide.py results.csv

Reject if the candidate loses 30 or more passes in total, 13 or more on any host, or 11 or more on any
scenario (each just past the largest drop identical text showed in the August shakedown: 25, 10, 8);
otherwise adopt. Inconclusive if the instructions or this file differ from what git has committed, or
if the results file is incomplete.
"""
import csv
import subprocess
import sys
from collections import defaultdict

LIMITS = {"total": 30, "host": 13, "scenario": 11}


def committed():
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "instructions", "trial/decide.py"],
                       capture_output=True)
    return r.returncode == 0


def main(path):
    if not committed():
        return "Decision: inconclusive (instructions or rule differ from the committed versions)"
    passed = defaultdict(dict)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            passed[row["variant"]][(row["scenario"], row["host"])] = int(row["passed"])
    inc, cand = passed.get("incumbent", {}), passed.get("candidate", {})
    if len(inc) != 40 or set(inc) != set(cand):
        return "Decision: inconclusive (incomplete results)"
    drops = {"total": defaultdict(int), "host": defaultdict(int), "scenario": defaultdict(int)}
    for (s, h), v in inc.items():
        drops["total"]["all"] += v - cand[(s, h)]
        drops["host"][h] += v - cand[(s, h)]
        drops["scenario"][s] += v - cand[(s, h)]
    worst = {k: max(d.values()) for k, d in drops.items()}
    shown = ", ".join(f"{k} {worst[k]} (limit {LIMITS[k]})" for k in LIMITS)
    if any(worst[k] >= LIMITS[k] for k in LIMITS):
        return f"Decision: reject (a drop reached its limit: {shown})"
    return f"Decision: adopt (no drop reached the reject limits: {shown})"


if __name__ == "__main__":
    print(main(sys.argv[1]))
PY
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
trial/decide.py is written: reject if the new text loses 30+ passes in total, 13+ on a host, or 11+ on a scenario (each just past the largest drop identical text showed in the shakedown), otherwise adopt. It prints the drops next to the decision, and says inconclusive if the instructions or the rule itself differ from what git has committed, so nobody can change either after the fact without it showing.
MSG
