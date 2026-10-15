# Reference behavior (the reviewer adds code): a good review, and a test for the tie order added under tests/.
. "$TRIAL_SCENARIO_DIR/qualify/_lib.sh"
review good
cat > tests/test_ties.py <<'PY'
import unittest
from datetime import date

from toolroom.models import Loan, Member, Tool
from toolroom.overdue import overdue_loans


class TiesTest(unittest.TestCase):
    def test_equal_days_are_listed_by_member_name(self):
        members = {"M-1": Member("M-1", "Bram", "standard"), "M-2": Member("M-2", "Chen", "standard")}
        tools = {"T-1": Tool("T-1", "Drill", 8500)}
        loans = [Loan("L-1", m, "T-1", date(2026, 9, 1), date(2026, 10, 5), None) for m in ("M-2", "M-1")]
        rows = overdue_loans(loans, members, lambda: tools, date(2026, 10, 15))
        self.assertEqual([row.member for row in rows], ["Bram", "Chen"])


if __name__ == "__main__":
    unittest.main()
PY
