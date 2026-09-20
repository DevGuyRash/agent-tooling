"""Figure/review contracts using source execution and explicit DOM/storage doubles."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class FigureReviewTests(unittest.TestCase):
    def test_figure_review_contracts(self):
        node, tsc = shutil.which('node'), shutil.which('tsc')
        self.assertIsNotNone(node)
        self.assertIsNotNone(tsc)
        with tempfile.TemporaryDirectory(prefix='av-figure-review-') as work:
            build = subprocess.run([tsc, '--strict', '--target', 'ES2020', '--lib', 'ES2020,DOM', '--module', 'commonjs', '--outDir', work, str(ROOT / 'src/index.ts')], capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            for script in ['figure-review.cjs', 'figure-viewer.cjs', 'mermaid-contract.cjs']:
                with self.subTest(script=script):
                    result = subprocess.run([node, str(ROOT/'tests'/script), work], capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('contracts passed', result.stdout)

if __name__ == '__main__':
    unittest.main()
