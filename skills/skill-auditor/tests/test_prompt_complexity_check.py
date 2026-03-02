from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prompt_complexity_check.sh"


class PromptComplexityCheckTests(unittest.TestCase):
    def test_empty_directory_reports_zero_density_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                ["sh", str(SCRIPT), tmp],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Total paragraphs: 0", result.stdout)
        self.assertIn("Conditional density: 0.0/para", result.stdout)


if __name__ == "__main__":
    unittest.main()
