"""Command routing and notification/reading-pane behavior with explicit models."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class CanvasControlTests(unittest.TestCase):
    def test_shared_control_contracts(self):
        self.assertIsNotNone(shutil.which('node'))
        self.assertIsNotNone(shutil.which('tsc'))
        with tempfile.TemporaryDirectory(prefix='av-canvas-controls-') as output:
            build=subprocess.run(['tsc','--strict','--target','ES2020','--lib','ES2020,DOM','--module','commonjs','--outDir',output,str(ROOT/'src/index.ts')],text=True,capture_output=True,timeout=60)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            checked=subprocess.run(['node',str(ROOT/'tests/canvas-controls.cjs'),output],text=True,capture_output=True,timeout=60)
            self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            self.assertIn('canvas control contracts passed',checked.stdout)
if __name__=='__main__':unittest.main()
