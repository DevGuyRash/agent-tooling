"""Compiled reading-window, evidence-identity and controller model checks."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class ComparisonReaderTests(unittest.TestCase):
    def test_comparison_reader_contracts(self):
        with tempfile.TemporaryDirectory(prefix='av-comparison-') as work:
            result=subprocess.run(['tsc','--strict','--target','ES2020','--lib','ES2020,DOM','--module','commonjs','--outDir',work,str(ROOT/'src/index.ts')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run(['node',str(ROOT/'tests/comparison-reader.cjs'),work],capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('comparison reader contracts passed',result.stdout)
