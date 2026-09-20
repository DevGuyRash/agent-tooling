"""View modes, panning, resize and axis synchronization with bounded DOM doubles."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PlotNavigationTests(unittest.TestCase):
    def test_zoom_pan_and_inspection_boundaries(self):
        node, tsc = shutil.which('node'), shutil.which('tsc')
        self.assertIsNotNone(node, 'Node.js is required for viewport checks; nothing is installed automatically')
        self.assertIsNotNone(tsc, 'TypeScript is required for viewport checks; nothing is installed automatically')
        with tempfile.TemporaryDirectory(prefix='av-plot-navigation-') as tmp:
            compiled = subprocess.run([tsc, '--strict', '--target', 'ES2020', '--module', 'commonjs', '--outDir', tmp, str(ROOT / 'src/plot-navigation.ts')], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            tested = subprocess.run([node, str(ROOT / 'tests/plot-navigation.cjs'), tmp], capture_output=True, text=True, timeout=30)
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            self.assertIn('plot navigation source contracts passed', tested.stdout)
