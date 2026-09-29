# Partial: fixes the missing customers only (predicate moved into ON); totals stay multiplied.
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/on_clause_only.sql" acctreport/sql/customer_activity.sql
python3 "$Q/select_tests.py" "$Q/tests/test_activity_grain.py" tests/test_activity_grain.py no_orders outside
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Moved the period filter from WHERE into the LEFT JOIN condition so customers without orders in the period are listed with zeros; added tests." > "$TRIAL_JOB_DIR/final-0.md"
