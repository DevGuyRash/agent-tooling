"""Renderer/refiner integration through bounded text-metric and parsed-DOM doubles."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LayoutRefinementTests(unittest.TestCase):
    def test_preserves_original_evidence_and_active_nodes(self):
        with tempfile.TemporaryDirectory(prefix='av-layout-refinement-') as tmp:
            built = subprocess.run(['tsc', '--strict', '--target', 'ES2020', '--module', 'commonjs', '--outDir', tmp, str(ROOT / 'src/index.ts')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run(['node', str(ROOT / 'tests/layout-refinement.cjs'), tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
