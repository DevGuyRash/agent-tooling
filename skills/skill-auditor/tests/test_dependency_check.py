from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dependency_check.sh"


def run_dependency_check(skill_dir: Path) -> str:
    return subprocess.check_output(["sh", str(SCRIPT), str(skill_dir)], text=True)


class DependencyCheckTests(unittest.TestCase):
    def test_skips_embedded_awk_tokens_but_keeps_following_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            (scripts_dir / "sample.sh").write_text(
                """#!/usr/bin/env sh
awk -v rel="$rel" \\
    '
    function block_value(x) {
        return x
    }
    { print $1 }
' "$1"
jq -r '.name' "$2"
""",
                encoding="utf-8",
            )

            output = run_dependency_check(skill_dir)

        self.assertIn("External commands used (non-POSIX candidates):", output)
        self.assertIn("- jq", output)
        self.assertNotIn("- function", output)
        self.assertNotIn("- block_value", output)

    def test_extracts_command_after_env_assignment_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            (scripts_dir / "sample.sh").write_text(
                """#!/usr/bin/env sh
FOO=1 jq -r '.name' "$1"
""",
                encoding="utf-8",
            )

            output = run_dependency_check(skill_dir)

        self.assertIn("External commands used (non-POSIX candidates):", output)
        self.assertIn("- jq", output)

    def test_extracts_command_after_env_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            (scripts_dir / "sample.sh").write_text(
                """#!/usr/bin/env sh
env FOO=1 jq -r '.name' "$1"
env -i BAR=2 python3 -V
""",
                encoding="utf-8",
            )

            output = run_dependency_check(skill_dir)

        self.assertIn("External commands used (non-POSIX candidates):", output)
        self.assertIn("- jq", output)
        self.assertIn("- python3", output)
        self.assertNotIn("- env", output)


if __name__ == "__main__":
    unittest.main()
