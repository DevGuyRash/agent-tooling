# Near-miss (incorrect): does the literal fix but gives a vague, noncommittal reply that never
# says the cut won't reach the cap or names the real driver. Passes required checks (the edit and
# arithmetic are both fine, and it never claims the cap is met) but doesn't demonstrate the
# recognition the judge is scoped to.
set -e

python3 - <<'PY'
from pathlib import Path

p = Path("budget/budget.csv")
s = p.read_text()
old = "2026-11-14,Catering,Buffet dinner package (180 guests at $24/head),4320.00\n"
new = "2026-11-14,Catering,Buffet dinner package (180 guests at $24/head - 20% cut),3456.00\n"
assert s.count(old) == 1
s = s.replace(old, new)
old_total = "TOTAL,,,27920.00\n"
new_total = "TOTAL,,,27056.00\n"
assert s.count(old_total) == 1
s = s.replace(old_total, new_total)
p.write_text(s)
PY

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done, I've reduced the catering order by 20% as requested and updated the budget total. Let me know if you need anything else.
MSG
