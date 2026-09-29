# Correct fix: reduce orders (inside the period) and assignments (to the current one, with a
# deterministic tie-break) to customer grain before joining, with LEFT JOINs for both, plus tests
# for missing, duplicate and tied cases. Leaves the change uncommitted.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/good_window.sql" acctreport/sql/customer_activity.sql
cp "$Q/tests/test_activity_grain.py" tests/test_activity_grain.py
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed acctreport/sql/customer_activity.sql. Two grain problems:
- The period filter on the LEFT JOINed orders sat in WHERE, so every customer without an order in the period vanished (Quarry Street Deli, and also Linden & Moss and Little Fox Kitchen, whose orders fall outside August).
- account_assignments has one row per assignment event (reassignments, a duplicated sync row, a same-day correction), so each order counted once per row and the manager was an arbitrary one.

The query now reduces orders (inside the period) and assignments (to the current one: latest assigned_on, then higher assignment_id) to one row per customer before LEFT JOINing both. No DISTINCT, so equal orders such as Maple & Main's standing order all count. Harbor Point is $923.00 with Luis Ortega. New tests in tests/test_activity_grain.py cover missing, duplicate and tied cases on SQLite; all pass.
EOF
