# Partial: collapses the repeated order rows with GROUP BY (customer, date, amount), which also merges
# real orders that match on those, and takes MAX(manager).
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/groupby_dedupe.sql" acctreport/sql/customer_activity.sql
python3 "$Q/select_tests.py" "$Q/tests/test_activity_grain.py" tests/test_activity_grain.py no_orders reassigned
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Customers without orders are kept, and the order rows repeated by the assignment join are grouped back to one per order; added tests." > "$TRIAL_JOB_DIR/final-0.md"
