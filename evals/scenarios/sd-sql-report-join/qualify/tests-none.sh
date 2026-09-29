# Correct report, no regression tests: passes the required checks; every tests_catch_* measure is false.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/good_window.sql" acctreport/sql/customer_activity.sql
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Fixed the query: period orders are aggregated per customer and only the current assignment is joined, both with LEFT JOINs. Existing tests pass." > "$TRIAL_JOB_DIR/final-0.md"
