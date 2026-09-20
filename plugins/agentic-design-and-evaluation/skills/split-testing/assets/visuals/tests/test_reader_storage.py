"""Transactional ownership/concurrency contracts with bounded doubles, not a browser."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReaderStorageTests(unittest.TestCase):
    def test_transactional_reader_storage(self):
        node, tsc = shutil.which("node"), shutil.which("tsc")
        self.assertIsNotNone(node)
        self.assertIsNotNone(tsc)
        with tempfile.TemporaryDirectory(prefix="av-reader-storage-") as temporary:
            compiled = subprocess.run([tsc, "--strict", "--target", "ES2020", "--lib", "ES2020,DOM", "--module", "commonjs", "--outDir", temporary, str(ROOT / "src/reader-storage.ts"), str(ROOT / "src/reader-state.ts")], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            tested = subprocess.run([node, str(ROOT / "tests/reader-storage.cjs"), temporary], capture_output=True, text=True)
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            self.assertIn("reader-storage contracts passed", tested.stdout)


if __name__ == "__main__":
    unittest.main()
