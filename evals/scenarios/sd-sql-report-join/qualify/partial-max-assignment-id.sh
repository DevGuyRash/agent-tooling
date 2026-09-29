# Partial: correct except that the current assignment is the latest entry (highest assignment_id)
# instead of the latest assigned_on, which differs when an older assignment was recorded late.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/max_assignment_id.sql" acctreport/sql/customer_activity.sql
python3 "$Q/select_tests.py" "$Q/tests/test_activity_grain.py" tests/test_activity_grain.py \
  no_orders outside unassigned reassigned reassigned_manager recorded_twice same_day identical zero_order
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Rebuilt the query at customer grain (period orders aggregated, latest assignment entry joined); added tests." > "$TRIAL_JOB_DIR/final-0.md"
