# Reference behavior (near miss): a valid category and an internally consistent total, but the amount
# itself is wrong (transposed digits) — the validator still prints OK, because it can't know what the
# user actually asked for, only that the sheet is self-consistent.
set -e

python3 - <<'PY'
from pathlib import Path

p = Path("budget-2026-09.csv")
lines = p.read_text().splitlines()
assert lines[-1].startswith("TOTAL,"), lines[-1]
lines.insert(len(lines) - 1, "2026-09-03,Subscriptions,Gym membership,54.00")
lines[-1] = "TOTAL,,,2126.49"
p.write_text("\n".join(lines) + "\n")
PY

python3 validate.py budget-2026-09.csv

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added the gym membership under Subscriptions: $54.00 on 2026-09-03, and updated the total to 2126.49. Ran
`python3 validate.py budget-2026-09.csv` — it prints `OK`.
MSG
