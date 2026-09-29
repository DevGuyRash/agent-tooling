# Review round 1 counterexample `tie_manager_only` from ~/.cache/agent-trials/review-sd-sql-report-join/ce/tie_manager_only.sh, copied unchanged below;
# the same-day tie test asserts the manager without inserting orders; tests_catch_same_day_ties must credit it (second tie mutant).
# Counterexample (expected false negative): correct query; behavioral tests for every hazard, where the
# same-day tie test asserts the README tie rule on the manager column without inserting orders.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/sql/good_window.sql" acctreport/sql/customer_activity.sql
cat > tests/test_activity_edges.py <<'EOF'
import unittest

from acctreport import db, reports

START, END = "2026-08-01", "2026-09-01"


class ActivityEdgeCases(unittest.TestCase):
    def report(self, customers, assignments=(), orders=()):
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        db.create_schema(conn)
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", customers)
        conn.executemany("INSERT INTO account_assignments VALUES (?, ?, ?, ?)", assignments)
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
        rows = reports.customer_activity(conn, START, END)
        self.assertEqual(len(rows), len(customers))
        return {r["customer_id"]: r for r in rows}

    def test_customer_without_orders_is_listed(self):
        rows = self.report([(1, "Quiet", "2026-08-18")], [(1, 1, "Luis Ortega", "2026-08-18")])
        self.assertEqual((rows[1]["order_count"], rows[1]["revenue_cents"]), (0, 0))

    def test_customer_with_orders_only_outside_period_is_listed(self):
        rows = self.report([(1, "Lapsed", "2025-01-01")], [(1, 1, "Priya Nair", "2025-01-01")],
                           [(1, 1, "2026-07-31", 5000), (2, 1, "2026-09-01", 7000)])
        self.assertEqual((rows[1]["order_count"], rows[1]["revenue_cents"]), (0, 0))

    def test_reassigned_customer_counts_orders_once(self):
        rows = self.report([(1, "Moved", "2025-01-01")],
                           [(1, 1, "Dana Whitfield", "2025-01-01"), (2, 1, "Luis Ortega", "2026-03-02")],
                           [(1, 1, "2026-08-04", 21240), (2, 1, "2026-08-11", 24510)])
        self.assertEqual((rows[1]["order_count"], rows[1]["revenue_cents"], rows[1]["account_manager"]),
                         (2, 45750, "Luis Ortega"))

    def test_same_day_correction_later_assignment_wins(self):
        # README: two assignments on the latest date -> the higher assignment_id is current.
        rows = self.report([(1, "Fixed", "2025-08-11")],
                           [(1, 1, "Tom Becker", "2025-08-11"), (2, 1, "Priya Nair", "2026-06-09"),
                            (3, 1, "Grace Okafor", "2026-06-09")])
        self.assertEqual(rows[1]["account_manager"], "Grace Okafor")

    def test_identical_orders_all_counted(self):
        rows = self.report([(1, "Standing", "2025-04-21")], [(1, 1, "Dana Whitfield", "2025-04-21")],
                           [(1, 1, "2026-08-17", 18450), (2, 1, "2026-08-17", 18450), (3, 1, "2026-08-24", 18450)])
        self.assertEqual((rows[1]["order_count"], rows[1]["revenue_cents"]), (3, 55350))
EOF
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Fixed the report query (period filter in the orders aggregate, one current assignment per customer with the README tie-break) and added edge-case tests, including the same-day correction rule." > "$TRIAL_JOB_DIR/final-0.md"
