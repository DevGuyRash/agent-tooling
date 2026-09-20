"""Notebook controller contracts using bounded DOM doubles, not a browser."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NotebookTests(unittest.TestCase):
    def test_notebook_contracts(self):
        node, tsc = shutil.which("node"), shutil.which("tsc")
        self.assertIsNotNone(node, "Node.js is required for notebook source checks")
        self.assertIsNotNone(tsc, "TypeScript is required for notebook source checks")
        with tempfile.TemporaryDirectory(prefix="av-notebook-contract-") as temporary:
            compiled = subprocess.run(
                [tsc, "--strict", "--target", "ES2020", "--lib", "ES2020,DOM", "--module", "commonjs", "--outDir", temporary, str(ROOT / "src/index.ts")],
                capture_output=True, text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            tested = subprocess.run([node, str(ROOT / "tests/notebook.cjs"), temporary], capture_output=True, text=True)
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            self.assertIn("notebook contracts passed", tested.stdout)


if __name__ == "__main__":
    unittest.main()
