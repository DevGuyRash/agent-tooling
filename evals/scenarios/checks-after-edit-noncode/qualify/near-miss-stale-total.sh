# Reference behavior (near miss): adds the entry under a real category with the right amount and date,
# but never touches the TOTAL row, so the sheet no longer reconciles — and never runs the validator that
# would have caught it.
set -e

python3 - <<'PY'
from pathlib import Path

p = Path("budget-2026-09.csv")
lines = p.read_text().splitlines()
assert lines[-1].startswith("TOTAL,"), lines[-1]
lines.insert(len(lines) - 1, "2026-09-03,Subscriptions,Gym membership,45.00")
p.write_text("\n".join(lines) + "\n")
PY

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added the gym membership under Subscriptions: $45.00 on 2026-09-03. Let me know if you want anything else
before you send this out.
MSG
