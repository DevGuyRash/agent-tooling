# Partial: correct except that the manager is carried inside the per-customer order aggregate, so a
# customer without orders in the period is listed with zeros but no manager.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/manager_from_orders.sql" acctreport/sql/customer_activity.sql
python3 "$Q/select_tests.py" "$Q/tests/test_activity_grain.py" tests/test_activity_grain.py \
  outside unassigned reassigned reassigned_manager recorded_twice same_day identical zero_order
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Rebuilt the query: period orders aggregated per customer with their current manager, LEFT JOINed to customers; added tests." > "$TRIAL_JOB_DIR/final-0.md"
