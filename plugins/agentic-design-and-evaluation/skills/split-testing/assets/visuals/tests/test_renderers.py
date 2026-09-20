"""Renderer semantics and geometry, with only Python, Node and TypeScript installed."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RendererTests(unittest.TestCase):
    def test_renderer_contracts(self):
        node, tsc = shutil.which("node"), shutil.which("tsc")
        self.assertIsNotNone(node, "Node.js is required for renderer checks")
        self.assertIsNotNone(tsc, "TypeScript is required for renderer checks")
        with tempfile.TemporaryDirectory(prefix="agentic-renderers-") as temporary:
            compiled = subprocess.run(
                [tsc, "--strict", "--target", "ES2020", "--module", "commonjs", "--rootDir", str(ROOT), "--outDir", temporary, str(ROOT / "src/index.ts"), str(ROOT / "examples/demo.ts")],
                capture_output=True, text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            tested = subprocess.run([node, str(ROOT / "tests/renderers.cjs"), temporary], capture_output=True, text=True)
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            self.assertIn("renderer contracts passed", tested.stdout)


if __name__ == "__main__":
    unittest.main()
