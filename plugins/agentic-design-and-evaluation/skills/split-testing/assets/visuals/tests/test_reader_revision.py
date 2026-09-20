"""Focused revision regressions. Native browser qualification is a separate command."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ReaderRevisionTests(unittest.TestCase):
    def test_reader_revision_contracts(self):
        self.assertIsNotNone(shutil.which('tsc'))
        self.assertIsNotNone(shutil.which('node'))
        with tempfile.TemporaryDirectory(prefix='av-reader-revision-') as output:
            build = subprocess.run(['tsc', '--strict', '--target', 'ES2020', '--lib', 'ES2020,DOM', '--module', 'commonjs', '--outDir', output, str(ROOT / 'src/index.ts')], capture_output=True, text=True, timeout=60)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run(['node', str(ROOT / 'tests/reader-revision.cjs'), output], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('reader revision contracts passed', result.stdout)

if __name__ == '__main__':
    unittest.main()
