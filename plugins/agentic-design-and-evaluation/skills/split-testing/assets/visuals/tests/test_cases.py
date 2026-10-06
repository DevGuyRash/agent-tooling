"""The cases view (case dossiers), checked against the built bundle in node:vm.

Runs tests/cases.cjs and reports each of its cases as a subtest.
"""
from __future__ import annotations

import unittest

from visual_harness import NodeCases


class CasesViewTest(NodeCases):
    """Dossiers in plan order, pass criteria, run marks, failure reasons, variants side by side, escaping."""

    script = "cases.cjs"
    minimum = 16

    def test_case_dossiers(self) -> None:
        self.run_script_cases()


if __name__ == "__main__":
    unittest.main()
