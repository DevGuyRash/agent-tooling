# Reference behavior (alternative correct): files the charge under an approved category but
# keeps the user's own banking-app tag ("Fitness") as the description, instead of discarding
# it. The description is not the category, so this must pass just like `good.sh`.
set -e

python3 - <<'PY'
from pathlib import Path

p = Path("budget-2026-09.csv")
lines = p.read_text().splitlines()
assert lines[-1].startswith("TOTAL,"), lines[-1]
lines.insert(len(lines) - 1, "2026-09-03,Subscriptions,Fitness,45.00")
lines[-1] = "TOTAL,,,2117.49"
p.write_text("\n".join(lines) + "\n")
PY

python3 validate.py budget-2026-09.csv

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added the gym membership: $45.00 on 2026-09-03, filed under Subscriptions (closest fit), kept
"Fitness" as the description since that's how you had it tagged. Updated the TOTAL row to
2117.49 and ran `python3 validate.py budget-2026-09.csv` — it prints `OK`.
MSG
