"""The "What was compared" view (block type setup) and the line diff behind it,
checked against the built bundle in node:vm."""
from __future__ import annotations

import unittest

from visual_harness import NodeCases


class SetupTest(NodeCases):
    """Shared and differing settings, identical material, lettered texts with diffs, truncation, artifacts, variants and escaping."""

    script = "setup.cjs"
    minimum = 22

    def test_setup_view_and_line_diff(self) -> None:
        self.run_script_cases()

    def test_known_setup_defects(self) -> None:
        self.check_known_defects()


if __name__ == "__main__":
    unittest.main()
