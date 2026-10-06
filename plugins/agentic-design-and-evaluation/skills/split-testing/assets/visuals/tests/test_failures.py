"""Why runs failed: failureCause() and the failures block, checked against the
built bundle in node:vm (failures.cjs reports each case as a subtest)."""
from __future__ import annotations

import unittest

from visual_harness import NodeCases


class FailuresTest(NodeCases):
    """Every failed run names its cause; failed runs group by cause; invalid runs are never failures."""

    script = "failures.cjs"
    minimum = 31

    def test_failure_causes_and_the_failures_view(self) -> None:
        self.run_script_cases()

    def test_known_failures_view_defects(self) -> None:
        self.check_known_defects()


if __name__ == "__main__":
    unittest.main()
