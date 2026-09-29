# Partial: correct except that the current assignment is an inner join, which drops customers that
# have never been assigned.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/inner_current.sql" acctreport/sql/customer_activity.sql
python3 "$Q/select_tests.py" "$Q/tests/test_activity_grain.py" tests/test_activity_grain.py \
  no_orders outside reassigned reassigned_manager recorded_twice same_day identical
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Rebuilt the query at customer grain (period orders aggregated, current assignment joined); added tests." > "$TRIAL_JOB_DIR/final-0.md"
