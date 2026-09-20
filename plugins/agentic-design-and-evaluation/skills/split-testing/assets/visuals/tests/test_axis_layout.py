"""Exercise emitted axis text using an independently supplied width model."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AxisLayoutTests(unittest.TestCase):
    def test_full_scale_labels_fit_measured_bounds(self):
        with tempfile.TemporaryDirectory(prefix='av-axis-layout-') as tmp:
            built = subprocess.run(['tsc', '--strict', '--target', 'ES2020', '--module', 'commonjs', '--outDir', tmp, str(ROOT / 'src/index.ts')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run(['node', str(ROOT / 'tests/axis-layout.cjs'), tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
