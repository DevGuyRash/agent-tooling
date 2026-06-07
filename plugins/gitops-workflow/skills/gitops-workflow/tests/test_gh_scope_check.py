from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = ROOT / "scripts" / "gh-scope-check.sh"


def run(cmd, *, cwd: Path, env=None, check=True):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def make_fake_gh(path: Path, mode: str, log_file: Path) -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "echo \"$*\" >> \"${FAKE_GH_LOG}\"\n"
        "mode=\"${FAKE_GH_MODE:-ok}\"\n"
        "if [[ \"$1\" != \"api\" ]]; then\n"
        "  echo \"unsupported command\" >&2\n"
        "  exit 1\n"
        "fi\n"
        "endpoint=\"${2:-}\"\n"
        "if [[ \"$mode\" == \"ok\" ]]; then\n"
        "  echo '{}'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$mode\" == \"ruleset_perm\" && \"$endpoint\" == *\"/rulesets\" ]]; then\n"
        "  echo 'Resource not accessible by integration' >&2\n"
        "  exit 1\n"
        "fi\n"
        "if [[ \"$mode\" == \"labels_network\" && \"$endpoint\" == *\"/labels?per_page=1&page=1\" ]]; then\n"
        "  echo 'Could not resolve host: api.github.com' >&2\n"
        "  exit 1\n"
        "fi\n"
        "echo '{}'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class GhScopeCheckTests(unittest.TestCase):
    def test_missing_repo_value_fails_with_exit_2(self):
        proc = run(
            ["bash", str(CHECK_SCRIPT), "--repo"],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("option '--repo' requires a value", proc.stderr)

    def test_missing_gh_binary_maps_to_exit_5(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            bash_path = subprocess.run(
                ["which", "bash"],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            (fake_bin / "bash").symlink_to(Path(bash_path))

            env = os.environ.copy()
            env["PATH"] = str(fake_bin)
            proc = run(
                ["bash", str(CHECK_SCRIPT), "--repo", "acme/widget"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            self.assertIn("missing required command: gh", proc.stderr)

    def test_all_probes_pass_returns_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "gh.log"
            fake_gh = fake_bin / "gh"
            make_fake_gh(fake_gh, mode="ok", log_file=log_file)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_GH_MODE"] = "ok"
            env["FAKE_GH_LOG"] = str(log_file)

            proc = run(
                ["bash", str(CHECK_SCRIPT), "--repo", "acme/widget"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            calls = log_file.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(calls), 3)
            self.assertIn("api repos/acme/widget", calls[0])
            self.assertIn("api repos/acme/widget/rulesets", calls[1])
            self.assertIn("api repos/acme/widget/labels?per_page=1&page=1", calls[2])

    def test_rulesets_probe_permission_error_returns_exit_5(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "gh.log"
            fake_gh = fake_bin / "gh"
            make_fake_gh(fake_gh, mode="ruleset_perm", log_file=log_file)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_GH_MODE"] = "ruleset_perm"
            env["FAKE_GH_LOG"] = str(log_file)

            proc = run(
                ["bash", str(CHECK_SCRIPT), "--repo", "acme/widget"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            self.assertIn("insufficient_token_permissions", proc.stderr)

    def test_labels_probe_network_error_returns_exit_5(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "gh.log"
            fake_gh = fake_bin / "gh"
            make_fake_gh(fake_gh, mode="labels_network", log_file=log_file)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_GH_MODE"] = "labels_network"
            env["FAKE_GH_LOG"] = str(log_file)

            proc = run(
                ["bash", str(CHECK_SCRIPT), "--repo", "acme/widget"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            self.assertIn("network_unavailable", proc.stderr)

    def test_json_output_is_machine_parseable_and_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "gh.log"
            fake_gh = fake_bin / "gh"
            make_fake_gh(fake_gh, mode="ok", log_file=log_file)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_GH_MODE"] = "ok"
            env["FAKE_GH_LOG"] = str(log_file)

            proc = run(
                ["bash", str(CHECK_SCRIPT), "--repo", "acme/widget", "--format", "json"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["repo"], "acme/widget")
            checks = payload["checks"]
            self.assertEqual([c["name"] for c in checks], ["repo_metadata", "rulesets_read", "labels_read"])


if __name__ == "__main__":
    unittest.main()
