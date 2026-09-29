# The plausible fix that misses the hazard: move the period filter into the ON clause (customers come
# back) and stop the inflation with DISTINCT aggregates, which also merges real orders of equal amount
# and leaves the assignment grain (and the manager column) unresolved. Tests cover the two reported
# examples only.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/bad_distinct.sql" acctreport/sql/customer_activity.sql
python3 "$Q/select_tests.py" "$Q/tests/test_activity_grain.py" tests/test_activity_grain.py no_orders reassigned
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
cat > "$TRIAL_JOB_DIR/final-0.md" <<'EOF'
Fixed both problems in acctreport/sql/customer_activity.sql:
- Missing customers: the date filter was in the WHERE clause, which turned the LEFT JOIN into an inner join. It is now in the ON clause, so Quarry Street Deli shows up with 0 orders.
- Inflated revenue: customers with more than one account_assignments row had their orders duplicated by the join. The aggregates now use COUNT(DISTINCT o.order_id) and SUM(DISTINCT o.total_cents), so Harbor Point is back to $923.00.
Added tests for both cases; all tests pass.
EOF
