"""Source-level interaction contracts using explicit DOM doubles, not a browser."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AtelierInteractionTests(unittest.TestCase):
    def test_presentation_interaction_contracts(self):
        node, tsc = shutil.which("node"), shutil.which("tsc")
        self.assertIsNotNone(node, "Node.js is required for interaction source checks")
        self.assertIsNotNone(tsc, "TypeScript is required for interaction source checks")
        with tempfile.TemporaryDirectory(prefix="av-interaction-contract-") as temporary:
            compiled = subprocess.run(
                [tsc, "--strict", "--target", "ES2020", "--lib", "ES2020,DOM", "--module", "commonjs", "--outDir", temporary, str(ROOT / "src/interaction.ts")],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            tested = subprocess.run(
                [node, str(ROOT / "tests/atelier_interactions.cjs"), temporary],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            self.assertIn("interaction source contracts passed", tested.stdout)


if __name__ == "__main__":
    unittest.main()
