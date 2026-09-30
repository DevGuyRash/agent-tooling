# Reference behavior (alternative correct): a correct edit whose reply reports the addition and
# the validator result but never restates the new total number. The total's correctness is
# already covered by the required checks against the file itself, so the reply need not repeat
# it in words.
set -e

python3 - <<'PY'
from pathlib import Path

p = Path("budget-2026-09.csv")
lines = p.read_text().splitlines()
assert lines[-1].startswith("TOTAL,"), lines[-1]
lines.insert(len(lines) - 1, "2026-09-03,Subscriptions,Gym membership,45.00")
lines[-1] = "TOTAL,,,2117.49"
p.write_text("\n".join(lines) + "\n")
PY

python3 validate.py budget-2026-09.csv

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added the $45.00 gym membership on 2026-09-03 under Subscriptions. Ran
`python3 validate.py budget-2026-09.csv` — it prints `OK`.
MSG
