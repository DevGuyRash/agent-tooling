# Reference behavior (correct): add the requested expense under the closest existing category, update
# the TOTAL row to match, and run the project's own validator before calling it done.
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
Added the gym membership: $45.00 on 2026-09-03, filed under Subscriptions (closest fit for a recurring
monthly charge — same bucket as the streaming bundle). Updated the TOTAL row to 2117.49 and ran
`python3 validate.py budget-2026-09.csv`; it prints `OK`, so this is safe to send along tonight.
MSG
