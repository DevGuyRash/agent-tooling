"""Actual renderer and shared reader integration with bounded geometry models."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReaderFitTests(unittest.TestCase):
    def test_auto_fit_controls_and_evidence_survive_reader_actions(self):
        with tempfile.TemporaryDirectory(prefix="av-reader-fit-") as tmp:
            build = subprocess.run(["tsc", "--strict", "--target", "ES2020", "--module", "commonjs", "--outDir", tmp, str(ROOT / "src/index.ts")], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run(["node", str(ROOT / "tests/reader-fit.cjs"), tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
