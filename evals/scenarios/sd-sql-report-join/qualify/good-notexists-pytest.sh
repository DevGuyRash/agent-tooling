# Correct fix, a third shape: NOT EXISTS picks the current assignment, orders pre-aggregated; tests
# written pytest-style (pytest is installed on the host, though the project documents unittest).
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/good_notexists.sql" acctreport/sql/customer_activity.sql
cp "$Q/tests/test_activity_edges_pytest.py" tests/test_activity_edges.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q -p no:cacheprovider tests >/dev/null 2>&1
cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed the report query: customers without orders in the period are kept (the period filter no longer sits in WHERE after the outer join), and each customer joins exactly one assignment, the current one, so reassignment history and duplicate sync rows no longer multiply revenue. Added pytest tests for missing customers, unassigned customers, reassigned, duplicated and same-day assignments, and equal orders.
EOF
