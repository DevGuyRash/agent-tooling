"""Renderer behavior, checked against the built bundle in node:vm.

Each class runs one Node case script (escaping.cjs, outcomes.cjs,
composition.cjs) and reports each of its cases as a subtest.
"""
from __future__ import annotations

import unittest

from visual_harness import NodeCases


class EscapingTest(NodeCases):
    """Every text-bearing input renders as escaped, visible text."""

    script = "escaping.cjs"
    minimum = 9

    def test_supplied_text_never_becomes_markup(self) -> None:
        self.run_script_cases()

    def test_known_escaping_defects(self) -> None:
        self.check_known_defects()


class OutcomesTest(NodeCases):
    """Invalid runs are never failures; missing values render visibly."""

    script = "outcomes.cjs"
    minimum = 22

    def test_invalid_runs_and_missing_values(self) -> None:
        self.run_script_cases()

    def test_known_missing_value_defects(self) -> None:
        self.check_known_defects()


class CompositionTest(NodeCases):
    """Trial composition, the block registry, notices, check shading, the drawer and auto-mount."""

    script = "composition.cjs"
    minimum = 35

    def test_composition_registry_and_runtime(self) -> None:
        self.run_script_cases()


if __name__ == "__main__":
    unittest.main()
