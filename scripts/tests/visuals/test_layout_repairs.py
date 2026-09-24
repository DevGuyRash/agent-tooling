"""Numerical geometry and lifecycle contracts; no browser or SVG rendering."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
VISUALS = ROOT / "plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals"


class LayoutRepairTests(unittest.TestCase):
    def test_architecture_and_elk_geometry(self):
        with tempfile.TemporaryDirectory(prefix="mermaid-layout-contract-") as output:
            build = subprocess.run(
                ["tsc", "--strict", "--target", "ES2020", "--lib", "ES2020,DOM", "--module", "commonjs",
                 "--outDir", output, str(VISUALS / "src/index.ts")],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            for filename in ["architecture_geometry.cjs", "architecture_group_routes.cjs", "elk_geometry.cjs"]:
                with self.subTest(contract=filename):
                    result = subprocess.run(
                        ["node", str(Path(__file__).with_name(filename)), output],
                        cwd=output, capture_output=True, text=True, timeout=45,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("geometry passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
