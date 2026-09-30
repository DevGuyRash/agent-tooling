# Reference behavior (alternative correct): inserts the new row in date order next to the
# existing 2026-09-03 entry instead of appending it just before TOTAL. Row order must not
# matter to the outcome — only the row's own fields and the reconciling total do.
set -e

python3 - <<'PY'
from pathlib import Path

p = Path("budget-2026-09.csv")
lines = p.read_text().splitlines()
assert lines[-1].startswith("TOTAL,"), lines[-1]
idx = next(i for i, l in enumerate(lines) if l.startswith("2026-09-03,"))
lines.insert(idx + 1, "2026-09-03,Subscriptions,Gym membership,45.00")
lines[-1] = "TOTAL,,,2117.49"
p.write_text("\n".join(lines) + "\n")
PY

python3 validate.py budget-2026-09.csv

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added the gym membership under Subscriptions: $45.00 on 2026-09-03, placed next to the other
2026-09-03 entry to keep the sheet in date order. Updated the TOTAL row to 2117.49 and ran
`python3 validate.py budget-2026-09.csv` — it prints `OK`.
MSG
