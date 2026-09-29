"""Guards on the report query's text."""
import unittest

from acctreport import reports


class QueryTextTest(unittest.TestCase):
    def setUp(self):
        self.sql = reports.load_query("customer_activity")

    def test_no_distinct_patch(self):
        self.assertNotIn("DISTINCT", self.sql.upper())

    def test_period_filter_not_in_where_after_outer_join(self):
        self.assertNotIn("WHERE O.ORDER_DATE", self.sql.upper())

    def test_current_assignment_ranked_with_tie_break(self):
        self.assertIn("ROW_NUMBER()", self.sql)
        self.assertIn("assignment_id DESC", self.sql)


if __name__ == "__main__":
    unittest.main()
