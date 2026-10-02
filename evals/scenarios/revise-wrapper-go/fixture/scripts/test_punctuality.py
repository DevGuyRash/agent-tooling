import unittest

import punctuality


def sail(route, *delays):
    return [{"route": route, "delay": d} for d in delays]


class Figures(unittest.TestCase):
    def test_one_route(self):
        [r] = punctuality.figures(sail("Inchmara–Dunvoan", 4, None, -2, 12, 0, 5))
        self.assertEqual(r, {"route": "Inchmara–Dunvoan", "sailings": 6, "cancelled": 1, "on_time": 4,
                             "median": 4, "worst": 12, "bands": [(-5, 1), (0, 2), (5, 1), (10, 1)]})

    def test_even_median_is_halfway(self):
        [r] = punctuality.figures(sail("Saltness–Inchmara", 1, 4, 2, 9))
        self.assertEqual(r["median"], 3.0)
        [r] = punctuality.figures(sail("Saltness–Inchmara", 1, 4))
        self.assertEqual(r["median"], 2.5)

    def test_nothing_ran(self):
        [r] = punctuality.figures(sail("Kilbride–Eilean Rùm", None, None))
        self.assertEqual((r["median"], r["worst"], r["bands"], r["on_time"]), (None, None, [], 0))

    def test_least_punctual_first_ties_keep_order(self):
        sailings = (sail("A–B", 0, 0) + sail("C–D", 9, 0) + sail("E–F", None) + sail("G–H", 1, 2)
                    + sail("I–J", 20, 1, 1, 30))
        order = [r["route"] for r in punctuality.figures(sailings)]
        self.assertEqual(order, ["E–F", "C–D", "I–J", "A–B", "G–H"])


if __name__ == "__main__":
    unittest.main()
