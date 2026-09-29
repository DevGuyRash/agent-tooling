# Correct fix that also moves the query to a new file (and points reports.py at it), so the check must
# find the file the report actually reads before swapping in defective versions.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
git mv acctreport/sql/customer_activity.sql acctreport/sql/customer_activity_by_customer.sql
cp "$Q/sql/good_window.sql" acctreport/sql/customer_activity_by_customer.sql
python3 - <<'PY'
p = "acctreport/reports.py"
s = open(p).read().replace('load_query("customer_activity")', 'load_query("customer_activity_by_customer")')
open(p, "w").write(s)
PY
cp "$Q/tests/test_activity_grain.py" tests/test_activity_grain.py
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Rewrote the report at customer grain in acctreport/sql/customer_activity_by_customer.sql (period orders aggregated, current assignment joined, both LEFT JOINs) and added grain tests." > "$TRIAL_JOB_DIR/final-0.md"
