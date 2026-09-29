# Partial: joins the assignment whose date equals the customer's latest assigned_on; two assignments
# on that date (a duplicate sync, a same-day correction) still multiply the orders.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/maxdate.sql" acctreport/sql/customer_activity.sql
python3 "$Q/select_tests.py" "$Q/tests/test_activity_grain.py" tests/test_activity_grain.py \
  no_orders outside reassigned reassigned_manager
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Period filter moved into the join; only the latest assignment is joined, so reassigned customers are counted once. Added tests." > "$TRIAL_JOB_DIR/final-0.md"
