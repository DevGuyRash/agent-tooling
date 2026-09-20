"""Second-pass contracts; native rendering is separately exercised by native_polish.py."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
class ProductionPolishTests(unittest.TestCase):
    def test_production_polish_models(self):
        with tempfile.TemporaryDirectory(prefix='av-polish-') as output:
            result = subprocess.run(['tsc','--strict','--target','ES2020','--lib','ES2020,DOM','--module','commonjs','--outDir',output,str(ROOT/'src/index.ts')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result = subprocess.run(['node',str(ROOT/'tests/production-polish.cjs'),output],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('production polish contracts passed',result.stdout)
    def test_generated_css_delimiter_guard(self):
        script = r'''import {validateCssBlocks} from './build-theme.mjs';
        import assert from 'node:assert/strict';
        for(const css of ['@media print { .x { color: red; } }', '.x { content: "}"; /* [ { */ background: url("data:a(b)"); }', '[data-x="}"] { --value: calc(1px + (2px)); }']) validateCssBlocks(css);
        for(const css of ['@media print { .x { color: red; }', '.x { content: "unfinished; }', '.x { color: rgb(0,0,0]; }', '.x { /* unfinished']) assert.throws(()=>validateCssBlocks(css));
        console.log('CSS delimiter guard passed');'''
        result = subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
