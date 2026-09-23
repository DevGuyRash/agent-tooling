#!/usr/bin/env python3
"""Focused contracts for Mermaid full-drawing bounds."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VISUALS = ROOT / "plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals"


class MermaidBoundsTests(unittest.TestCase):
    def test_clip_aware_text_protection(self) -> None:
        node = shutil.which("node")
        tsc = shutil.which("tsc")
        self.assertIsNotNone(node, "Node.js is required for Mermaid bounds contracts")
        self.assertIsNotNone(tsc, "TypeScript is required for Mermaid bounds contracts")
        with tempfile.TemporaryDirectory(prefix="mermaid-bounds-") as output:
            build = subprocess.run(
                [
                    tsc,
                    "--strict",
                    "--target",
                    "ES2020",
                    "--lib",
                    "ES2020,DOM",
                    "--module",
                    "commonjs",
                    "--outDir",
                    output,
                    str(VISUALS / "src/mermaid.ts"),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            check = subprocess.run(
                [node, str(HERE / "mermaid_bounds_contract.cjs"), output],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertIn("Mermaid bounds contract passed", check.stdout)


if __name__ == "__main__":
    unittest.main()
