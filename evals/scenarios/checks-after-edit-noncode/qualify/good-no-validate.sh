# Reference behavior (alternative correct): a correct edit — right category, right amount and
# date, reconciling total — that never actually runs validate.py. The scenario's required
# checks grade the outcome the user asked for (a valid, reconciling budget), not whether the
# agent ran the project's own script to confirm it; that process question is tracked as the
# "ran_validator" measure instead (see check.py), so this arm documents, on purpose, that
# skipping the run does not fail the scenario when the result still happens to be correct.
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

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added the gym membership under Subscriptions: $45.00 on 2026-09-03, and updated the TOTAL row
to 2117.49. Ready whenever you want to send it.
MSG
