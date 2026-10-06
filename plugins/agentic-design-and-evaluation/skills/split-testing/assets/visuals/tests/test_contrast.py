"""The contrast block and the Newcombe interval, checked against the built bundle in node:vm."""
from __future__ import annotations

import unittest

from visual_harness import NodeCases


class ContrastTest(NodeCases):
    """Differences in pass rate: published interval values, readings, invalid runs, trial forms and escaping."""

    script = "contrast.cjs"
    minimum = 20

    def test_contrast_block_and_interval(self) -> None:
        self.run_script_cases()

    def test_known_contrast_defects(self) -> None:
        self.check_known_defects()


if __name__ == "__main__":
    unittest.main()
