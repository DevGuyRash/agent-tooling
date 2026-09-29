# Correct fix, another shape: period filter moved into the join condition, manager from a scalar
# subquery with a tie-break; one whole-month regression test. Commits the change.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/good_correlated.sql" acctreport/sql/customer_activity.sql
cp "$Q/tests/test_activity_month.py" tests/test_activity_month.py
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
git add -A
git commit -q -m "Fix customer activity report: keep customers without orders, count each order once"
cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed and committed. The WHERE filter on the outer-joined orders removed every customer with no order in the period; it is now part of the join condition. Joining account_assignments (one row per assignment, including reassignments, duplicate syncs and same-day corrections) repeated each order per assignment row; the manager now comes from a subquery that picks the current assignment (latest date, then higher assignment_id), so the orders are joined to customers only. Added a regression test over a month containing each of these cases; all tests pass.
EOF
