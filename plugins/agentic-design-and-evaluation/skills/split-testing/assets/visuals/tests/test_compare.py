"""The quantitative comparison views, checked against the built bundle in node:vm."""
from __future__ import annotations

import unittest

from visual_harness import NodeCases


class CompareTest(NodeCases):
    """metric, scorecard, difference and hierarchy: drawing by metric kind, baselines, groups, notices and escaping."""

    script = "compare.cjs"
    minimum = 25

    def test_compare_views(self) -> None:
        self.run_script_cases()

    def test_known_compare_defects(self) -> None:
        self.check_known_defects()


if __name__ == "__main__":
    unittest.main()
