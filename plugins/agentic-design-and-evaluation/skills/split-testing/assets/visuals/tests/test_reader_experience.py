"""Current reader contracts in real compiled source and explicit DOM models."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
class ReaderExperienceTests(unittest.TestCase):
    def test_reader_experience_contracts(self):
        with tempfile.TemporaryDirectory(prefix='av-reader-experience-') as output:
            result=subprocess.run(['tsc','--strict','--target','ES2020','--lib','ES2020,DOM','--module','commonjs','--outDir',output,str(ROOT/'src/index.ts')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run(['node',str(ROOT/'tests/reader-experience.cjs'),output],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('reader experience contracts passed',result.stdout)
