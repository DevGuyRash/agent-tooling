# Correct fix, a fourth shape: the current assignment becomes a view in schema.sql and the report joins
# it; the regression test pins the whole August report over the dev snapshot.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cat "$Q/sql/current_assignments_view.sql" >> acctreport/schema.sql
cp "$Q/sql/good_view.sql" acctreport/sql/customer_activity.sql
cp "$Q/tests/test_dev_snapshot.py" tests/test_dev_snapshot.py
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Added a current_assignments view (latest assignment per customer, ties to the later entry) and joined it instead of the raw history; moved the period filter into the orders join. The new test pins the full August report on the dev snapshot." > "$TRIAL_JOB_DIR/final-0.md"
