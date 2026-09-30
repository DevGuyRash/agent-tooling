# Reference behavior (alternative correct): a correct edit whose reply closes with an offer to
# move the entry to a different category later. That offer must not read as "something left
# open" that disqualifies a correct, already-complete edit.
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
Added the gym membership: $45.00 on 2026-09-03, filed under Subscriptions. Updated the TOTAL
row to 2117.49 and `validate.py` prints `OK`. If you'd rather it sit under Misc or
Entertainment instead, say which and I'll move it.
MSG
