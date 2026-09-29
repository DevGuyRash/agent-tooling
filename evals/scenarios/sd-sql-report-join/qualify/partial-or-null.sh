# Partial: keeps the WHERE filter but adds OR o.order_id IS NULL, which brings back customers with no
# orders at all and still drops customers whose orders all fall outside the period.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/or_null.sql" acctreport/sql/customer_activity.sql
python3 "$Q/select_tests.py" "$Q/tests/test_activity_grain.py" tests/test_activity_grain.py \
  no_orders unassigned reassigned reassigned_manager recorded_twice same_day identical zero_order
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Customers without orders are kept (OR o.order_id IS NULL) and each customer joins only the current assignment; added tests." > "$TRIAL_JOB_DIR/final-0.md"
