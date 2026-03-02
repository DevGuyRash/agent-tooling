from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "error_quality_check.sh"


def run_error_quality_check(skill_dir: Path, *extra: str) -> str:
    return subprocess.check_output(["sh", str(SCRIPT), str(skill_dir), *extra], text=True)


class ErrorQualityCheckTests(unittest.TestCase):
    def test_cli_violations_are_counted_in_summary_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "skill"
            skill_dir.mkdir(parents=True)

            cli = root / "fake-cli"
            cli.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env sh
                    echo "line1"
                    echo "line2"
                    echo "line3"
                    echo "line4"
                    echo "line5"
                    exit 2
                    """
                ),
                encoding="utf-8",
            )
            cli.chmod(0o755)

            output = run_error_quality_check(skill_dir, "--cli", str(cli))

        self.assertIn("Script error issues: 0", output)
        self.assertIn("CLI error issues: 4", output)
        self.assertIn("Issues found: 4", output)

    def test_total_issues_combines_script_and_cli_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "skill"
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)

            local_script = scripts_dir / "run.sh"
            local_script.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env sh
                    echo "error: bad input"
                    echo "detail one"
                    echo "detail two"
                    echo "detail three"
                    exit 1
                    """
                ),
                encoding="utf-8",
            )
            local_script.chmod(0o755)

            cli = root / "fake-cli"
            cli.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env sh
                    echo "panic happened"
                    exit 2
                    """
                ),
                encoding="utf-8",
            )
            cli.chmod(0o755)

            output = run_error_quality_check(skill_dir, "--cli", str(cli))

        self.assertIn("Script error issues: 1", output)
        self.assertIn("CLI error issues: 4", output)
        self.assertIn("Issues found: 5", output)

    def test_no_cli_keeps_cli_count_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            output = run_error_quality_check(skill_dir)

        self.assertIn("CLI error issues: 0", output)
        self.assertIn("Issues found: 0", output)


if __name__ == "__main__":
    unittest.main()
