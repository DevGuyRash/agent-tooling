from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "scripts" / "receipt.py"


def run(cmd, cwd: Path) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True, text=True)
    return proc.stdout


class ReceiptScriptTests(unittest.TestCase):
    def test_receipt_uses_requested_branch_not_head(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            run(["git", "init"], repo)
            run(["git", "config", "user.name", "Test User"], repo)
            run(["git", "config", "user.email", "test@example.com"], repo)

            run(["git", "checkout", "-b", "main"], repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], repo)
            run(["git", "commit", "-m", "chore: base commit"], repo)

            run(["git", "checkout", "-b", "feat/branch-receipt"], repo)
            (repo / "README.md").write_text("base\nfeature\n", encoding="utf-8")
            run(["git", "add", "README.md"], repo)
            run(["git", "commit", "-m", "feat: feature commit"], repo)

            run(["git", "checkout", "main"], repo)
            (repo / "MAIN_ONLY.txt").write_text("main\n", encoding="utf-8")
            run(["git", "add", "MAIN_ONLY.txt"], repo)
            run(["git", "commit", "-m", "docs: main only commit"], repo)

            output = run(
                [
                    "python3",
                    str(RECEIPT),
                    "--branch",
                    "feat/branch-receipt",
                    "--base",
                    "main",
                ],
                repo,
            )

            self.assertIn("branch `feat/branch-receipt`", output)
            self.assertIn("feat: _feature commit_", output)
            self.assertNotIn("main only commit", output)


if __name__ == "__main__":
    unittest.main()
