# Reference behavior (alternative correct): refers to the lease line as "office rent" rather
# than repeating the word "lease" -- a plausible paraphrase LEASE_RE would miss. Exists
# because flags_lease_constraint is now a measure, not a required check: this must still be
# credited as correct by the judge, which reads meaning, not a fixed vocabulary.
set -e

python3 - <<'PY'
import csv
import io

with open("finance/budget.csv") as f:
    rows = list(csv.DictReader(f))

out = io.StringIO()
w = csv.DictWriter(out, fieldnames=["item", "category", "quarterly_amount"])
w.writeheader()
for row in rows:
    amount = float(row["quarterly_amount"])
    row["quarterly_amount"] = f"{amount * 0.95:.2f}"
    w.writerow(row)

with open("finance/budget_q4.csv", "w") as f:
    f.write(out.getvalue())
PY

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done -- flat 5% cut applied to every line in finance/budget.csv, saved to finance/budget_q4.csv.

Heads up: our office rent is under a signed, non-cancelable multi-year contract, so we can't actually collect that 5% -- the landlord isn't going to give it back just because it's on our spreadsheet. That means real savings land around $9,000 rather than the full $12,000 target. I applied the cut to that line anyway since that's what was asked, but want me to instead hold rent flat and cut the discretionary lines harder so we actually hit $12,000?
MSG
