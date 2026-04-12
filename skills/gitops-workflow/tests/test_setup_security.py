from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = ROOT / "scripts" / "setup-security.sh"
MANAGED_MARKER = "gitops-workflow-managed-pre-commit:v1"


def run(cmd, *, cwd: Path, check=True):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
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
    p = Path(raw)
    if p.is_absolute():
        return p
    return repo / p


class SetupSecurityScriptTests(unittest.TestCase):
    def test_bootstrap_installs_hook_and_ci_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            proc = run(
                ["bash", str(SETUP_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("security bootstrap complete", proc.stdout)

            hook = hook_path(repo)
            self.assertTrue(hook.exists())
            self.assertIn(MANAGED_MARKER, hook.read_text(encoding="utf-8"))

            self.assertTrue((repo / ".github" / "gitleaks.toml").exists())
            self.assertTrue((repo / ".github" / "workflows" / "sensitive-scan.yml").exists())

    def test_bootstrap_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            (repo / ".github").mkdir(parents=True, exist_ok=True)
            (repo / ".github" / "gitleaks.toml").write_text("custom=true\n", encoding="utf-8")

            proc = run(
                ["bash", str(SETUP_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("rerun with --force to overwrite", proc.stderr)

    def test_bootstrap_force_overwrites_conflicting_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            (repo / ".github").mkdir(parents=True, exist_ok=True)
            (repo / ".github" / "gitleaks.toml").write_text("custom=true\n", encoding="utf-8")

            proc = run(
                ["bash", str(SETUP_SCRIPT), "--repo", str(repo), "--force"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            text = (repo / ".github" / "gitleaks.toml").read_text(encoding="utf-8")
            self.assertIn('title = "gitops-workflow gitleaks config"', text)

    def test_bootstrap_json_output_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            proc = run(
                ["bash", str(SETUP_SCRIPT), "--repo", str(repo), "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["repo"], str(repo))
            self.assertTrue(payload["hooks"])
            self.assertTrue(payload["ci"])


if __name__ == "__main__":
    unittest.main()
