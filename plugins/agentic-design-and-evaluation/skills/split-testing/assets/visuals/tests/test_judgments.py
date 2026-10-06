"""The judgment views (block types alternatives, preferences, decision-matrix and
observations) for a comparison of any alternatives, checked against the built
bundle in node:vm."""
from __future__ import annotations

import unittest

from visual_harness import NodeCases


class JudgmentsTest(NodeCases):
    """Nested alternatives with attribute and text diffs, win matrices and rankings, weighted decision matrices with visible arithmetic, observation tables with invalid ones counted, and escaping."""

    script = "judgments.cjs"
    minimum = 30

    def test_judgment_views(self) -> None:
        self.run_script_cases()

    def test_known_judgment_defects(self) -> None:
        self.check_known_defects()


if __name__ == "__main__":
    unittest.main()
