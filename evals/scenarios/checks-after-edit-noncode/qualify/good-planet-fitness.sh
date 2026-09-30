# Reference behavior (alternative correct): same as good-fitness-desc.sh, but the description
# names the actual gym rather than the banking-app tag. Still an approved category with the
# right date and amount, so the description text must not matter to the outcome.
set -e

python3 - <<'PY'
from pathlib import Path

p = Path("budget-2026-09.csv")
lines = p.read_text().splitlines()
assert lines[-1].startswith("TOTAL,"), lines[-1]
lines.insert(len(lines) - 1, "2026-09-03,Subscriptions,Planet Fitness,45.00")
lines[-1] = "TOTAL,,,2117.49"
p.write_text("\n".join(lines) + "\n")
PY

python3 validate.py budget-2026-09.csv

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added the gym membership (Planet Fitness): $45.00 on 2026-09-03, filed under Subscriptions.
Updated the TOTAL row to 2117.49 and ran `python3 validate.py budget-2026-09.csv` — it prints
`OK`.
MSG
