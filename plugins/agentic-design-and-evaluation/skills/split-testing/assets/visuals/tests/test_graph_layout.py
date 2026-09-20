"""Actual graph layout and renderer contracts without browser rendering."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GraphLayoutTests(unittest.TestCase):
    def check_contracts(self, entry, geometry=False):
        with tempfile.TemporaryDirectory(prefix="av-graph-layout-") as temporary:
            compiled = subprocess.run(["tsc", "--strict", "--target", "ES2020", "--module", "commonjs", "--rootDir", str(ROOT / "src"), "--outDir", temporary, str(ROOT / "src" / entry)], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            tested = subprocess.run(["node", str(ROOT / "tests/graph-layout.cjs"), temporary, *(["geometry"] if geometry else [])], capture_output=True, text=True)
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)

    def test_graph_layout_geometry(self):
        self.check_contracts("graph-layout.ts", geometry=True)

    def test_graph_layout_and_renderer_contracts(self):
        self.check_contracts("qualitative.ts")


if __name__ == "__main__":
    unittest.main()
