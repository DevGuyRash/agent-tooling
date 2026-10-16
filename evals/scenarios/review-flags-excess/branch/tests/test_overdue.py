import unittest
from datetime import date

from toolroom.cache import ToolCache
from toolroom.models import Loan, Member, Tool
from toolroom.overdue import overdue_loans

TODAY = date(2026, 10, 15)
MEMBERS = {
    "M-1": Member("M-1", "Bram Okafor", "standard"),
    "M-2": Member("M-2", "Chen Wei", "supporter"),
    "M-3": Member("M-3", "Dara Lindqvist", "standard"),
}
TOOLS = {"T-1": Tool("T-1", "Cordless drill", 8500), "T-2": Tool("T-2", "Tile cutter", 1200)}


def loan(loan_id, member, tool, due, returned=None):
    return Loan(loan_id, member, tool, date(2026, 9, 1), due, returned)


def rows(loans):
    return overdue_loans(loans, MEMBERS, lambda: TOOLS, TODAY)


class OverdueLoansTest(unittest.TestCase):
    def test_most_days_overdue_first(self):
        loans = [
            loan("L-1", "M-1", "T-1", date(2026, 10, 12)),
            loan("L-2", "M-2", "T-2", date(2026, 10, 5)),
            loan("L-3", "M-3", "T-1", date(2026, 10, 9)),
        ]
        self.assertEqual([row.loan for row in rows(loans)], ["L-2", "L-3", "L-1"])

    def test_a_loan_due_today_or_back_is_not_overdue(self):
        loans = [
            loan("L-1", "M-1", "T-1", TODAY),
            loan("L-2", "M-2", "T-2", date(2026, 10, 1), returned=date(2026, 10, 14)),
            loan("L-3", "M-3", "T-1", date(2026, 10, 14)),
        ]
        self.assertEqual([row.loan for row in rows(loans)], ["L-3"])

    def test_a_row_has_the_names_the_days_and_the_fine(self):
        (row,) = rows([loan("L-1", "M-2", "T-2", date(2026, 10, 5))])
        self.assertEqual(tuple(row), ("L-1", "M-2", "Chen Wei", "Tile cutter", 10, 375))


class ToolCacheTest(unittest.TestCase):
    def test_tools_are_loaded_again_after_the_ttl(self):
        loads, now = [], [0.0]
        cache = ToolCache(lambda: loads.append(1) or TOOLS, ttl=10, clock=lambda: now[0])
        cache.get("T-1")
        cache.get("T-2")
        self.assertEqual((len(loads), cache.hits, cache.misses), (1, 1, 1))
        now[0] = 10.0
        cache.get("T-1")
        self.assertEqual(len(loads), 2)


if __name__ == "__main__":
    unittest.main()
