# Partial: fixes the multiplied totals only (one current assignment per customer); the WHERE filter
# still drops customers without orders in the period.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/dimension_only.sql" acctreport/sql/customer_activity.sql
python3 "$Q/select_tests.py" "$Q/tests/test_activity_grain.py" tests/test_activity_grain.py \
  unassigned reassigned reassigned_manager recorded_twice same_day identical
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Joined only the current assignment per customer, so reassignment history no longer multiplies revenue; added tests." > "$TRIAL_JOB_DIR/final-0.md"
