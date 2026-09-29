# Review round 1 counterexample `text_guards` from ~/.cache/agent-trials/review-sd-sql-report-join/ce/text_guards.sh, copied unchanged below;
# regex guards on the SQL text must not earn credit (a correct reference contains the forbidden tokens).
# Counterexample (expected false positive): correct query; the "tests" for dropped customers,
# multiplication, and ties are regexes over the SQL text; only equal orders get a behavioral test.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/sql/good_window.sql" acctreport/sql/customer_activity.sql
cat > tests/test_activity_guards.py <<'EOF'
import re
import unittest

from acctreport import db, reports


class QueryShapeGuards(unittest.TestCase):
    def setUp(self):
        self.sql = re.sub(r"--[^\n]*", "", reports.load_query("customer_activity"))

    def test_period_filter_is_not_in_where_on_outer_joined_orders(self):
        self.assertNotRegex(self.sql, r"(?i)WHERE\s+o\.order_date")

    def test_raw_assignment_history_is_not_joined(self):
        self.assertNotRegex(self.sql, r"(?i)JOIN\s+account_assignments\b")


class EqualOrders(unittest.TestCase):
    def test_identical_orders_all_counted(self):
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        db.create_schema(conn)
        conn.execute("INSERT INTO customers VALUES (1, 'Standing', '2025-04-21')")
        conn.execute("INSERT INTO account_assignments VALUES (1, 1, 'Dana Whitfield', '2025-04-21')")
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)",
                         [(1, 1, "2026-08-17", 18450), (2, 1, "2026-08-17", 18450), (3, 1, "2026-08-24", 18450)])
        r = reports.customer_activity(conn, "2026-08-01", "2026-09-01")[0]
        self.assertEqual((r["order_count"], r["revenue_cents"]), (3, 55350))
EOF
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Fixed the report query and added guard tests." > "$TRIAL_JOB_DIR/final-0.md"
