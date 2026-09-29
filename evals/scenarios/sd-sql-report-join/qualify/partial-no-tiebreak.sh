# Partial: correct except that the current assignment is ranked by assigned_on only, so a same-day
# correction resolves to whichever row SQLite happens to rank first.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/no_tiebreak.sql" acctreport/sql/customer_activity.sql
python3 "$Q/select_tests.py" "$Q/tests/test_activity_grain.py" tests/test_activity_grain.py \
  no_orders outside unassigned reassigned reassigned_manager recorded_twice identical zero_order
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Rebuilt the query at customer grain (period orders aggregated, latest assignment joined); added tests." > "$TRIAL_JOB_DIR/final-0.md"
