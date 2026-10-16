import unittest

from toolroom.fines import ROUNDING_MODES, fine_for
from toolroom.models import Member, Tool
from toolroom.rules import FineRule, get_rule, register

DRILL = Tool("T-1", "Cordless drill", 8500)
STANDARD = Member("M-1", "Bram Okafor", "standard")
SUPPORTER = Member("M-2", "Chen Wei", "supporter")


class FineForTest(unittest.TestCase):
    def test_fifty_cents_a_day(self):
        self.assertEqual(fine_for(3, DRILL, STANDARD), 150)

    def test_never_more_than_the_replacement_value(self):
        self.assertEqual(fine_for(400, DRILL, STANDARD), 8500)

    def test_a_supporter_pays_three_quarters(self):
        self.assertEqual(fine_for(4, DRILL, SUPPORTER), 150)

    def test_the_cap_comes_before_the_discount(self):
        self.assertEqual(fine_for(400, DRILL, SUPPORTER), 6375)

    def test_a_half_cent_rounds_up(self):
        self.assertEqual(fine_for(1, DRILL, SUPPORTER), 38)

    def test_the_rounding_modes(self):
        fines = {mode: fine_for(3, DRILL, SUPPORTER, mode) for mode in ROUNDING_MODES}
        self.assertEqual(fines, {"nearest": 113, "up": 113, "down": 112, "even": 112})


class RulesTest(unittest.TestCase):
    def test_per_day_is_registered(self):
        self.assertEqual(get_rule("per-day").cents(2), 100)

    def test_an_unknown_rule_is_an_error(self):
        self.assertRaises(KeyError, get_rule, "flat")

    def test_a_name_is_registered_once(self):
        other = type("Other", (FineRule,), {"cents": lambda self, days: 0})
        self.assertRaises(ValueError, register("per-day"), other)


if __name__ == "__main__":
    unittest.main()
