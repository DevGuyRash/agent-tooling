"""Shared text preservation and geometry with an explicit metric adapter double."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TextLayoutTests(unittest.TestCase):
    def test_text_layout_contracts(self):
        with tempfile.TemporaryDirectory(prefix="av-text-layout-") as temporary:
            compiled = subprocess.run(["tsc", "--strict", "--target", "ES2020", "--module", "commonjs", "--outDir", temporary, str(ROOT / "src/text-layout.ts")], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            tested = subprocess.run(["node", str(ROOT / "tests/text-layout.cjs"), temporary], capture_output=True, text=True)
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)


if __name__ == "__main__":
    unittest.main()
