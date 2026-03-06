from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "output_size_check.sh"


def run_output_size_check(skill_dir: Path, *extra: str) -> str:
    return subprocess.check_output(["sh", str(SCRIPT), str(skill_dir), *extra], text=True)


class OutputSizeCheckTests(unittest.TestCase):
    def test_recognizes_format_json_as_filtering_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "skill"
            skill_dir.mkdir()

            cli = root / "fake-cli"
            cli.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env sh
                    if [ "${1-}" = "--help" ]; then
                        echo "Usage: fake-cli [--format json]"
                        exit 0
                    fi
                    exit 0
                    """
                ),
                encoding="utf-8",
            )
            cli.chmod(0o755)

            output = run_output_size_check(skill_dir, "--cli", str(cli))

        self.assertIn("✓ Filtering flags available", output)
        self.assertNotIn("No filtering flags detected", output)


if __name__ == "__main__":
    unittest.main()
