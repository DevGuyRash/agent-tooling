from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "idempotency_check.sh"


def run_idempotency_check(skill_dir: Path, *extra: str) -> str:
    return subprocess.check_output(["sh", str(SCRIPT), str(skill_dir), *extra], text=True)


class IdempotencyCheckTests(unittest.TestCase):
    def test_default_run_is_bounded_and_skips_recursive_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir()

            for name in ("alpha_check.sh", "beta_check.sh", "staleness_check.sh", "idempotency_check.sh"):
                script = scripts_dir / name
                script.write_text(
                    textwrap.dedent(
                        """\
                        #!/usr/bin/env sh
                        echo "Usage: demo <skill-directory>"
                        exit 0
                        """
                    ),
                    encoding="utf-8",
                )
                script.chmod(0o755)

            output = run_idempotency_check(skill_dir, "--max-scripts", "1")

        self.assertIn("Scripts checked for idempotency: 1", output)
        self.assertIn("Scripts skipped:", output)
        self.assertIn("bounded default excludes recursive/heavy checks", output)


if __name__ == "__main__":
    unittest.main()
