from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = ROOT / "scripts" / "install-hooks.sh"
MANAGED_MARKER = "gitops-workflow-managed-pre-commit:v1"


def run(cmd, *, cwd: Path, env=None, check=True):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def init_repo(path: Path) -> None:
    run(["git", "init"], cwd=path)
    run(["git", "config", "user.email", "dev@example.com"], cwd=path)
    run(["git", "config", "user.name", "Dev"], cwd=path)


def hook_path(repo: Path) -> Path:
    proc = run(["git", "rev-parse", "--git-path", "hooks/pre-commit"], cwd=repo)
    raw = proc.stdout.strip()
    path = Path(raw)
    if path.is_absolute():
        return path
    return repo / path


class HookInstallerTests(unittest.TestCase):
    def test_install_missing_repo_value_fails_cleanly(self):
        proc = run(
            ["bash", str(INSTALL_SCRIPT), "--repo"],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("option '--repo' requires a value", proc.stderr)

    def test_install_creates_managed_pre_commit_hook(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            proc = run(
                ["bash", str(INSTALL_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            path = hook_path(repo)
            self.assertTrue(path.exists())
            text = path.read_text(encoding="utf-8")
            self.assertIn(MANAGED_MARKER, text)
            self.assertIn("sensitive-scan.sh", text)
            self.assertTrue(os.access(path, os.X_OK))

    def test_install_escapes_skill_root_in_generated_hook(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            proc = run(
                ["bash", str(INSTALL_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            text = hook_path(repo).read_text(encoding="utf-8")
            expected_assignment = f"SKILL_ROOT={shlex.quote(str(ROOT))}"
            self.assertIn(expected_assignment, text)
            self.assertNotIn(f'SKILL_ROOT="{ROOT}"', text)

    def test_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            first = run(
                ["bash", str(INSTALL_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

            second = run(
                ["bash", str(INSTALL_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

    def test_install_refuses_non_managed_hook_without_force(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            path = hook_path(repo)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("#!/usr/bin/env bash\necho custom\n", encoding="utf-8")
            path.chmod(0o755)

            proc = run(
                ["bash", str(INSTALL_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("not managed", proc.stderr)

    def test_install_refuses_spoofed_marker_hook_without_force(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            path = hook_path(repo)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "#!/usr/bin/env bash\n"
                f"# {MANAGED_MARKER}\n"
                "echo spoofed\n",
                encoding="utf-8",
            )
            path.chmod(0o755)

            proc = run(
                ["bash", str(INSTALL_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("not managed", proc.stderr)

    def test_install_force_replaces_non_managed_hook(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            path = hook_path(repo)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("#!/usr/bin/env bash\necho custom\n", encoding="utf-8")
            path.chmod(0o755)

            proc = run(
                ["bash", str(INSTALL_SCRIPT), "--repo", str(repo), "--force"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            text = path.read_text(encoding="utf-8")
            self.assertIn(MANAGED_MARKER, text)
            self.assertIn("sensitive-scan.sh", text)

    def test_install_json_output_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            proc = run(
                ["bash", str(INSTALL_SCRIPT), "--repo", str(repo), "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "installed")
            self.assertEqual(payload["repo"], str(repo))
            self.assertTrue(payload["hook_path"])


if __name__ == "__main__":
    unittest.main()
