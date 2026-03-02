from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pr-update-body.sh"


def run(cmd, *, cwd: Path, env=None, check=True):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


class PrUpdateBodyTests(unittest.TestCase):
    def test_updates_body_from_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo = temp_path / "repo"
            fake_bin = temp_path / "bin"
            args_file = temp_path / "gh-args.txt"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)

            body_file = repo / "body.md"
            body_file.write_text("# Updated Body\n", encoding="utf-8")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "echo \"$*\" > \"${GH_ARGS_FILE}\"\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["GH_ARGS_FILE"] = str(args_file)

            proc = run(
                ["bash", str(SCRIPT), "20", "--repo", "acme/widget", "--body-file", str(body_file)],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            args = args_file.read_text(encoding="utf-8")
            self.assertIn("pr edit 20 --body-file", args)
            self.assertIn("--repo acme/widget", args)

    def test_dry_run_does_not_call_gh(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo = temp_path / "repo"
            fake_bin = temp_path / "bin"
            called_file = temp_path / "called.txt"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)

            body_file = repo / "body.md"
            body_file.write_text("body\n", encoding="utf-8")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "echo called > \"${CALLED_FILE}\"\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["CALLED_FILE"] = str(called_file)

            proc = run(
                ["bash", str(SCRIPT), "20", "--body-file", str(body_file), "--dry-run"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("DRY-RUN: gh pr edit 20 --body-file", proc.stdout)
            self.assertFalse(called_file.exists())

    def test_invalid_repo_slug_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            body_file = repo / "body.md"
            body_file.write_text("body\n", encoding="utf-8")

            proc = run(
                ["bash", str(SCRIPT), "20", "--repo", "../meta", "--body-file", str(body_file)],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("invalid --repo", proc.stderr)


if __name__ == "__main__":
    unittest.main()
