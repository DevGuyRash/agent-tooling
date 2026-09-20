"""Pure reader records, validated without a browser or DOM library."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReaderStateTests(unittest.TestCase):
    def test_reader_state_contracts(self):
        node, tsc = shutil.which("node"), shutil.which("tsc")
        self.assertIsNotNone(node, "Node.js is required for reader-state checks")
        self.assertIsNotNone(tsc, "TypeScript is required for reader-state checks")
        with tempfile.TemporaryDirectory(prefix="av-reader-state-") as temporary:
            compiled = subprocess.run(
                [tsc, "--strict", "--target", "ES2020", "--lib", "ES2020", "--module", "commonjs", "--outDir", temporary, str(ROOT / "src/reader-state.ts")],
                capture_output=True, text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            tested = subprocess.run(
                [node, str(ROOT / "tests/reader-state.cjs"), temporary],
                capture_output=True, text=True,
            )
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            self.assertIn("reader-state contracts passed", tested.stdout)


if __name__ == "__main__":
    unittest.main()
