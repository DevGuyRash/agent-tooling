from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pr-labels-list.sh"


def run(cmd, *, cwd: Path, env=None, check=True):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


class PrLabelsListTests(unittest.TestCase):
    def test_invalid_repo_slug_is_rejected(self):
        proc = run(
            [
                "bash",
                str(SCRIPT),
                "--repo",
                "../meta",
                "--format",
                "json",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("invalid --repo", proc.stderr)

    def test_valid_repo_slug_hits_expected_endpoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            calls_file = temp_path / "calls.txt"

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"api\" ]]; then\n"
                "  echo \"${2:-}\" >> \"${CALLS_FILE}\"\n"
                "  if [[ \"${2:-}\" == *\"page=1\" ]]; then\n"
                "    echo '[{\"name\":\"bug\",\"color\":\"f00\",\"description\":\"\"}]'\n"
                "  else\n"
                "    echo '[]'\n"
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["CALLS_FILE"] = str(calls_file)

            proc = run(
                [
                    "bash",
                    str(SCRIPT),
                    "--repo",
                    "acme/widget",
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            calls = calls_file.read_text(encoding="utf-8")
            self.assertIn("repos/acme/widget/labels?per_page=100&page=1", calls)


if __name__ == "__main__":
    unittest.main()
