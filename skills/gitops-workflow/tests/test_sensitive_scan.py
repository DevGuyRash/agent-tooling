from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_SCRIPT = ROOT / "scripts" / "sensitive-scan.sh"
GITLEAKS_CONFIG = ROOT / "assets" / "config" / "gitleaks.toml"


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


def stage_file(path: Path, name: str, content: str) -> None:
    file_path = path / name
    file_path.write_text(content, encoding="utf-8")
    run(["git", "add", name], cwd=path)


class SensitiveScanScriptTests(unittest.TestCase):
    def test_gitleaks_config_avoids_lookaround_patterns(self):
        cfg = GITLEAKS_CONFIG.read_text(encoding="utf-8")
        unsupported = ["(?=", "(?!", "(?<=", "(?<!"]
        for token in unsupported:
            self.assertNotIn(token, cfg, f"gitleaks config uses RE2-unsupported token: {token}")

    def test_gitleaks_config_ignores_build_artifacts(self):
        cfg = GITLEAKS_CONFIG.read_text(encoding="utf-8")
        self.assertIn("'''(^|/)\\.git/'''", cfg)
        self.assertIn("'''(^|/)target/'''", cfg)
        self.assertIn("'''(^|/)__pycache__/'''", cfg)

    def _write_fake_gitleaks(self, folder: Path) -> Path:
        fake = folder / "gitleaks"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ \"${1:-}\" == \"version\" ]]; then\n"
            "  echo 'gitleaks version 8.1.2'\n"
            "  exit 0\n"
            "fi\n"
            "echo \"$*\" > \"${FAKE_ARGS}\"\n"
            "has_redact=\"false\"\n"
            "for arg in \"$@\"; do\n"
            "  if [[ \"$arg\" == \"--redact\" ]]; then\n"
            "    has_redact=\"true\"\n"
            "  fi\n"
            "done\n"
            "mode=\"${FAKE_MODE:-clean}\"\n"
            "if [[ \"$mode\" == \"findings\" ]]; then\n"
            "  if [[ \"$has_redact\" == \"true\" ]]; then\n"
            "    echo 'finding value=REDACTED'\n"
            "  else\n"
            "    echo 'finding value=RAW-SECRET-123'\n"
            "  fi\n"
            "  exit 1\n"
            "fi\n"
            "if [[ \"$mode\" == \"error\" ]]; then\n"
            "  exit 7\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return fake

    def test_staged_scan_passes_and_uses_expected_flags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "notes.txt", "hello world\n")

            fake_dir = Path(temp_dir) / "bin"
            fake_dir.mkdir(parents=True, exist_ok=True)
            fake_gitleaks = self._write_fake_gitleaks(fake_dir)
            args_file = Path(temp_dir) / "args.txt"

            env = os.environ.copy()
            env["GITLEAKS_BIN"] = str(fake_gitleaks)
            env["FAKE_ARGS"] = str(args_file)
            env["FAKE_MODE"] = "clean"

            proc = run(
                ["bash", str(SCAN_SCRIPT), "--staged", "--repo", str(repo)],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            args = args_file.read_text(encoding="utf-8")
            self.assertIn("protect", args)
            self.assertIn("--staged", args)
            self.assertIn("--redact", args)

    def test_json_success_keeps_stdout_machine_parseable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "notes.txt", "hello world\n")

            fake_dir = Path(temp_dir) / "bin"
            fake_dir.mkdir(parents=True, exist_ok=True)
            fake_gitleaks = self._write_fake_gitleaks(fake_dir)
            args_file = Path(temp_dir) / "args.txt"

            env = os.environ.copy()
            env["GITLEAKS_BIN"] = str(fake_gitleaks)
            env["FAKE_ARGS"] = str(args_file)
            env["FAKE_MODE"] = "clean"

            proc = run(
                ["bash", str(SCAN_SCRIPT), "--staged", "--format", "json", "--repo", str(repo)],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertNotIn("Sensitive-data scan passed", proc.stdout)
            self.assertIn("Sensitive-data scan passed", proc.stderr)

    def test_staged_scan_blocks_on_findings_with_redacted_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "secrets.env", "mode=findings\n")

            fake_dir = Path(temp_dir) / "bin"
            fake_dir.mkdir(parents=True, exist_ok=True)
            fake_gitleaks = self._write_fake_gitleaks(fake_dir)
            args_file = Path(temp_dir) / "args.txt"

            env = os.environ.copy()
            env["GITLEAKS_BIN"] = str(fake_gitleaks)
            env["FAKE_ARGS"] = str(args_file)
            env["FAKE_MODE"] = "findings"

            proc = run(
                ["bash", str(SCAN_SCRIPT), "--staged", "--repo", str(repo)],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("REDACTED", proc.stdout)
            self.assertNotIn("RAW-SECRET-123", proc.stdout)
            self.assertIn("Commit blocked", proc.stderr)

    def test_no_download_fails_closed_when_override_binary_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "notes.txt", "hello world\n")

            env = os.environ.copy()
            env["GITLEAKS_BIN"] = str(Path(temp_dir) / "missing-gitleaks")

            proc = run(
                ["bash", str(SCAN_SCRIPT), "--staged", "--repo", str(repo), "--no-download"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("not executable", proc.stderr)

    def test_pinned_update_failure_allows_opt_in_path_binary_only_when_version_matches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "notes.txt", "hello world\n")

            fake_bin = Path(temp_dir) / "fake-bin"
            fake_bin.mkdir(parents=True, exist_ok=True)

            fake_gitleaks = self._write_fake_gitleaks(fake_bin)
            args_file = Path(temp_dir) / "args.txt"

            fake_curl = fake_bin / "curl"
            fake_curl.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_ARGS"] = str(args_file)
            env["FAKE_MODE"] = "clean"
            env["SENSITIVE_SCAN_GITLEAKS_VERSION"] = "v8.1.2"

            proc = run(
                ["bash", str(SCAN_SCRIPT), "--staged", "--repo", str(repo)],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("no fallback scanner is available", proc.stderr)

            env["SENSITIVE_SCAN_ALLOW_PATH_BIN"] = "1"
            proc_allow_path = run(
                ["bash", str(SCAN_SCRIPT), "--staged", "--repo", str(repo)],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc_allow_path.returncode, 0, proc_allow_path.stdout + proc_allow_path.stderr)
            args = args_file.read_text(encoding="utf-8")
            self.assertIn("--staged", args)

    def test_missing_repo_value_fails_with_actionable_error(self):
        proc = run(
            ["bash", str(SCAN_SCRIPT), "--repo"],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("option '--repo' requires a value", proc.stderr)

    def test_missing_format_value_fails_with_actionable_error(self):
        proc = run(
            ["bash", str(SCAN_SCRIPT), "--format"],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("option '--format' requires a value", proc.stderr)

    def test_non_findings_scanner_error_maps_to_setup_exit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "notes.txt", "hello world\n")

            fake_dir = Path(temp_dir) / "bin"
            fake_dir.mkdir(parents=True, exist_ok=True)
            fake_gitleaks = self._write_fake_gitleaks(fake_dir)
            args_file = Path(temp_dir) / "args.txt"

            env = os.environ.copy()
            env["GITLEAKS_BIN"] = str(fake_gitleaks)
            env["FAKE_ARGS"] = str(args_file)
            env["FAKE_MODE"] = "error"

            proc = run(
                ["bash", str(SCAN_SCRIPT), "--staged", "--repo", str(repo)],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("scanner/runtime error", proc.stderr)


if __name__ == "__main__":
    unittest.main()
