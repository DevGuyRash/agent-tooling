# Review round 1 counterexample `pytest_class` from ~/.cache/agent-trials/review-sd-sql-report-join/ce/pytest_class.sh, copied unchanged below;
# tests are a pytest class, run only by pytest; they must earn credit (pytest always runs).
# Counterexample (expected false negative): correct query; complete hazard tests written as a
# pytest test class (no unittest.TestCase, no `import pytest`), which `python3 -m pytest` runs.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/sql/good_window.sql" acctreport/sql/customer_activity.sql
cat > tests/test_activity_grain.py <<'EOF'
from acctreport import db, reports

START, END = "2026-08-01", "2026-09-01"


class TestActivityGrain:
    def report(self, customers, assignments=(), orders=()):
        conn = db.connect(":memory:")
        db.create_schema(conn)
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", customers)
        conn.executemany("INSERT INTO account_assignments VALUES (?, ?, ?, ?)", assignments)
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
        rows = reports.customer_activity(conn, START, END)
        conn.close()
        assert len(rows) == len(customers)
        return {r["customer_id"]: r for r in rows}

    def test_customer_without_orders_is_listed(self):
        rows = self.report([(1, "Quiet", "2026-08-18")], [(1, 1, "Luis Ortega", "2026-08-18")])
        assert (rows[1]["order_count"], rows[1]["revenue_cents"]) == (0, 0)

    def test_reassigned_customer_counts_orders_once(self):
        rows = self.report([(1, "Moved", "2025-01-01")],
                           [(1, 1, "Dana Whitfield", "2025-01-01"), (2, 1, "Luis Ortega", "2026-03-02")],
                           [(1, 1, "2026-08-04", 21240), (2, 1, "2026-08-11", 24510)])
        assert (rows[1]["order_count"], rows[1]["revenue_cents"]) == (2, 45750)

    def test_same_day_correction(self):
        rows = self.report([(1, "Fixed", "2025-08-11")],
                           [(1, 1, "Tom Becker", "2025-08-11"), (2, 1, "Priya Nair", "2026-06-09"),
                            (3, 1, "Grace Okafor", "2026-06-09")],
                           [(1, 1, "2026-08-12", 30400)])
        assert (rows[1]["account_manager"], rows[1]["order_count"], rows[1]["revenue_cents"]) == ("Grace Okafor", 1, 30400)

    def test_identical_orders_all_counted(self):
        rows = self.report([(1, "Standing", "2025-04-21")], [(1, 1, "Dana Whitfield", "2025-04-21")],
                           [(1, 1, "2026-08-17", 18450), (2, 1, "2026-08-17", 18450), (3, 1, "2026-08-24", 18450)])
        assert (rows[1]["order_count"], rows[1]["revenue_cents"]) == (3, 55350)
EOF
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q -p no:cacheprovider tests >/dev/null 2>&1
printf '%s\n' "Fixed the report query and added pytest grain tests." > "$TRIAL_JOB_DIR/final-0.md"
