"""Authored story/comparison composition, checked directly from TypeScript source."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StoryTests(unittest.TestCase):
    def test_story_contracts(self):
        node, tsc = shutil.which("node"), shutil.which("tsc")
        self.assertIsNotNone(node, "Node.js is required for story checks")
        self.assertIsNotNone(tsc, "TypeScript is required for story checks")
        with tempfile.TemporaryDirectory(prefix="av-story-") as temporary:
            compiled = subprocess.run(
                [tsc, "--strict", "--target", "ES2020", "--module", "commonjs", "--rootDir", str(ROOT), "--outDir", temporary, str(ROOT / "src/story.ts")],
                capture_output=True, text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            tested = subprocess.run(
                [node, str(ROOT / "tests/story.cjs"), temporary],
                capture_output=True, text=True,
            )
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            self.assertIn("story contracts passed", tested.stdout)


if __name__ == "__main__":
    unittest.main()
