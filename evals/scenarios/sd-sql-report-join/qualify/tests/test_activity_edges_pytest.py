"""Edge cases of the customer activity report, pytest style."""
import pytest

from acctreport import db, reports


@pytest.fixture
def activity():
    conns = []

    def run(customers, assignments=(), orders=()):
        conn = db.connect(":memory:")
        conns.append(conn)
        db.create_schema(conn)
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", customers)
        conn.executemany("INSERT INTO account_assignments VALUES (?, ?, ?, ?)", assignments)
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
        rows = reports.customer_activity(conn, "2026-08-01", "2026-09-01")
        assert sorted(r["customer_id"] for r in rows) == sorted(c[0] for c in customers)
        return {r["customer_id"]: r for r in rows}

    yield run
    for conn in conns:
        conn.close()


def test_customers_without_orders_in_the_period_get_zero_rows(activity):
    rows = activity([(1, "Never Co", "2026-08-18"), (2, "Lapsed Co", "2025-01-01")],
                    [(1, 1, "Luis Ortega", "2026-08-18"), (2, 2, "Priya Nair", "2025-01-01")],
                    [(1, 2, "2026-07-31", 5000), (2, 2, "2026-09-01", 6000)])
    for cid in (1, 2):
        assert (rows[cid]["order_count"], rows[cid]["revenue_cents"], rows[cid]["last_order_date"]) == (0, 0, None)


def test_unassigned_customer_is_listed(activity):
    rows = activity([(1, "New Co", "2026-07-27")], [], [(1, 1, "2026-08-05", 9875)])
    assert rows[1]["account_manager"] is None and rows[1]["revenue_cents"] == 9875


@pytest.mark.parametrize("assignments, manager", [
    ([(1, 1, "Dana Whitfield", "2025-01-01"), (2, 1, "Luis Ortega", "2026-03-02")], "Luis Ortega"),
    ([(1, 1, "Priya Nair", "2025-09-15"), (2, 1, "Priya Nair", "2025-09-15")], "Priya Nair"),
    ([(1, 1, "Tom Becker", "2025-08-11"), (2, 1, "Priya Nair", "2026-06-09"),
      (3, 1, "Grace Okafor", "2026-06-09")], "Grace Okafor"),
])
def test_one_current_assignment_per_customer(activity, assignments, manager):
    rows = activity([(1, "Some Co", "2025-01-01")], assignments,
                    [(1, 1, "2026-08-04", 21240), (2, 1, "2026-08-11", 24510)])
    assert (rows[1]["account_manager"], rows[1]["order_count"], rows[1]["revenue_cents"]) == (manager, 2, 45750)


def test_equal_orders_each_count(activity):
    rows = activity([(1, "Standing Co", "2025-04-21")], [(1, 1, "Dana Whitfield", "2025-04-21")],
                    [(1, 1, "2026-08-17", 18450), (2, 1, "2026-08-17", 18450), (3, 1, "2026-08-24", 18450)])
    assert (rows[1]["order_count"], rows[1]["revenue_cents"]) == (3, 55350)
