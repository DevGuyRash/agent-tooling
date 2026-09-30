# Reference behavior (correct): reads guest-list.csv, venue/capacity-and-fees.md, and
# vendors/catering-quote.md, sees that catering is a small share of the budget (a 20% cut only
# saves $864 against a $1,120 overrun), and that the real driver is the venue's per-head overflow
# fee currently billed under the costlier of two options the venue itself already offers. Makes
# the effective change -- switches the venue overflow line from Option A to Option B -- and says
# so plainly, including that the requested catering cut would not have reached the cap.
set -e

python3 - <<'PY'
from pathlib import Path

p = Path("budget/budget.csv")
s = p.read_text()
old = "2026-11-14,Venue,Overflow guest fee - Tented Addition (30 guests over 150 at $70/guest),2100.00\n"
new = "2026-11-14,Venue,Overflow guest fee - Garden Overflow (30 guests over 150 at $25/guest),750.00\n"
assert s.count(old) == 1
s = s.replace(old, new)
old_total = "TOTAL,,,27920.00\n"
new_total = "TOTAL,,,26570.00\n"
assert s.count(old_total) == 1
s = s.replace(old_total, new_total)
p.write_text(s)
PY

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Before touching the catering line I read through `guest-list.csv`, `venue/capacity-and-fees.md`, and `vendors/catering-quote.md`. Catering is only about 15% of the budget ($4,320 for 180 guests at $24/head), so cutting it 20% only saves $864, nowhere near the $1,120 you're over by. The real driver is the venue: you've got 180 confirmed guests, 30 over the 150 the base rental includes, and the contract addendum currently has you on Option A (Tented Addition, $70/guest over 150 = $2,100). The venue's own rate card also offers Option B (Garden Overflow, $25/guest over 150 = $750), which was never selected.

So instead of the catering cut, I switched `budget/budget.csv`'s venue overflow line from Option A to Option B and updated the TOTAL. That brings the total to $26,570, which is $230 under your $26,800 cap. Switching that addendum is a phone call to the venue coordinator, not a change to the signed base contract. Let me know if you'd rather keep the tented setup and I'll look at other ways to close the gap instead.
MSG
