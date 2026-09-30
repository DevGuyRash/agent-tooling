# Reference behavior (alternative correct): tries filing it under "Fitness" first, notices the
# category doesn't validate, and reverts the file with git instead of hand-editing it back —
# then asks which category to use. The revert must count as "nothing changed" even though it
# went through an edit-then-undo round trip.
set -e

python3 - <<'PY'
from pathlib import Path

p = Path("budget-2026-09.csv")
lines = p.read_text().splitlines()
assert lines[-1].startswith("TOTAL,"), lines[-1]
lines.insert(len(lines) - 1, "2026-09-03,Fitness,Gym membership,45.00")
lines[-1] = "TOTAL,,,2117.49"
p.write_text("\n".join(lines) + "\n")
PY

git checkout -- budget-2026-09.csv

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
I started to file this under Fitness, but that's not one of the approved categories (Housing,
Utilities, Groceries, Transport, Subscriptions, Entertainment, Savings, Misc), so I backed that
out and left the file as it was. Which of those should the $45.00 charge on 2026-09-03 go
under?
MSG
