"""The reader-first trial composition and the trial views it composes, checked
against the built bundle in node:vm (see compose.cjs)."""
from __future__ import annotations

import unittest

from visual_harness import NodeCases


class ComposeTest(NodeCases):
    """Section order and shape, case variants, the verdict's rule and counts,
    failure causes, checks by case, invalid reasons and escaping."""

    script = "compose.cjs"
    minimum = 30

    def test_composition_follows_the_trial(self) -> None:
        self.run_script_cases()


if __name__ == "__main__":
    unittest.main()
