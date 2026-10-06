"""The comparison engine against the built bundle in node:vm (see engine.cjs):
every metric kind's summary and difference checked against a published worked
example, pooled groups at any depth, the reader-first composition, trial data
as a comparison, the comparison checker, and auto-mounting."""
from __future__ import annotations

import unittest

from visual_harness import NodeCases


class EngineTest(NodeCases):
    """Statistics, composition and checking for comparisons of any alternatives."""

    script = "engine.cjs"
    minimum = 16

    def test_engine(self) -> None:
        self.run_script_cases()


if __name__ == "__main__":
    unittest.main()
