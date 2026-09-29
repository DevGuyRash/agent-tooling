# Correct report whose added "tests" only inspect the SQL text: passes the required checks; the text
# tests reject correct rewrites, so tests_agree_with_reference and every tests_catch_* measure are false.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/good_window.sql" acctreport/sql/customer_activity.sql
cp "$Q/tests/test_query_text.py" tests/test_query_text.py
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Rebuilt the query at customer grain and added tests that guard against the DISTINCT patch and a WHERE filter on the outer-joined orders." > "$TRIAL_JOB_DIR/final-0.md"
