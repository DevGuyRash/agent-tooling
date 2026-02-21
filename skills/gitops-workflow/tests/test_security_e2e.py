from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import traceback
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT
SETUP_SCRIPT = SKILL_ROOT / "scripts" / "setup-security.sh"
SCAN_SCRIPT = SKILL_ROOT / "scripts" / "sensitive-scan.sh"
ARTIFACTS_DIR = ROOT / "tests" / "artifacts"
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


def stage_file(path: Path, name: str, content: str) -> None:
    file_path = path / name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    run(["git", "add", name], cwd=path)


def hook_path(repo: Path) -> Path:
    proc = run(["git", "rev-parse", "--git-path", "hooks/pre-commit"], cwd=repo)
    raw = proc.stdout.strip()
    p = Path(raw)
    if p.is_absolute():
        return p
    return repo / p


class SecurityScannerE2ETests(unittest.TestCase):
    def setUp(self):
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.log_path = ARTIFACTS_DIR / f"security-e2e-{stamp}.log"
        self.issues: list[str] = []

    def _clip(self, text: str, limit: int = 600) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _append_log(self, *, kind: str, scenario: str, step: str, payload: dict) -> None:
        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "scenario": scenario,
            "step": step,
            "payload": payload,
        }
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")

    def _record_issue(self, *, scenario: str, step: str, message: str, payload: dict | None = None) -> None:
        self.issues.append(f"{scenario}/{step}: {message}")
        self._append_log(
            kind="failure",
            scenario=scenario,
            step=step,
            payload={"message": message, **(payload or {})},
        )

    def _record_limitation(self, *, scenario: str, step: str, message: str, payload: dict | None = None) -> None:
        self._append_log(
            kind="limitation",
            scenario=scenario,
            step=step,
            payload={"message": message, **(payload or {})},
        )

    def _run_step(
        self,
        *,
        scenario: str,
        step: str,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        expected_codes: tuple[int, ...] = (0,),
    ) -> subprocess.CompletedProcess[str]:
        proc = run(cmd, cwd=cwd, env=env, check=False)
        if proc.returncode not in expected_codes:
            self._record_issue(
                scenario=scenario,
                step=step,
                message="unexpected exit code",
                payload={
                    "command": cmd,
                    "expected_codes": list(expected_codes),
                    "actual_code": proc.returncode,
                    "stdout": self._clip(proc.stdout),
                    "stderr": self._clip(proc.stderr),
                },
            )
        return proc

    def _fake_gitleaks(self, folder: Path, args_file: Path) -> Path:
        fake = folder / "gitleaks"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ \"${1:-}\" == \"version\" ]]; then\n"
            "  echo \"gitleaks version ${FAKE_GITLEAKS_VERSION:-8.1.2}\"\n"
            "  exit 0\n"
            "fi\n"
            "echo \"$*\" > \"${FAKE_ARGS}\"\n"
            "mode=\"${FAKE_MODE:-clean}\"\n"
            "if [[ \"$mode\" == \"findings\" ]]; then\n"
            "  has_redact='false'\n"
            "  for arg in \"$@\"; do\n"
            "    if [[ \"$arg\" == \"--redact\" ]]; then\n"
            "      has_redact='true'\n"
            "    fi\n"
            "  done\n"
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

    def _e2e_01_clean_bootstrap_and_scan_pass(self):
        scenario = "E2E-01"
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "notes.txt", "hello world\n")

            self._run_step(
                scenario=scenario,
                step="setup_security",
                cmd=["bash", str(SETUP_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
            )
            hook = hook_path(repo)
            if not hook.exists():
                self._record_issue(scenario=scenario, step="verify_hook", message="managed hook missing")
            elif MANAGED_MARKER not in hook.read_text(encoding="utf-8"):
                self._record_issue(scenario=scenario, step="verify_hook", message="managed marker missing")

            if not (repo / ".github" / "gitleaks.toml").exists():
                self._record_issue(scenario=scenario, step="verify_ci", message=".github/gitleaks.toml missing")
            if not (repo / ".github" / "workflows" / "sensitive-scan.yml").exists():
                self._record_issue(
                    scenario=scenario, step="verify_ci", message=".github/workflows/sensitive-scan.yml missing"
                )

            self._run_step(
                scenario=scenario,
                step="scan_staged",
                cmd=["bash", str(SCAN_SCRIPT), "--staged", "--redact", "--repo", str(repo)],
                cwd=ROOT,
            )

    def _e2e_02_idempotent_bootstrap(self):
        scenario = "E2E-02"
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            self._run_step(
                scenario=scenario,
                step="setup_first",
                cmd=["bash", str(SETUP_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
            )
            self._run_step(
                scenario=scenario,
                step="setup_second",
                cmd=["bash", str(SETUP_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
            )

    def _e2e_03_conflicting_hook_requires_force(self):
        scenario = "E2E-03"
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            hook = hook_path(repo)
            hook.parent.mkdir(parents=True, exist_ok=True)
            hook.write_text("#!/usr/bin/env bash\necho custom\n", encoding="utf-8")
            hook.chmod(0o755)

            no_force = self._run_step(
                scenario=scenario,
                step="setup_without_force",
                cmd=["bash", str(SETUP_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
                expected_codes=(2,),
            )
            if "not managed" not in no_force.stderr:
                self._record_issue(
                    scenario=scenario,
                    step="setup_without_force",
                    message="expected non-managed hook refusal message",
                    payload={"stderr": self._clip(no_force.stderr)},
                )

            self._run_step(
                scenario=scenario,
                step="setup_with_force",
                cmd=["bash", str(SETUP_SCRIPT), "--repo", str(repo), "--force"],
                cwd=ROOT,
            )

    def _e2e_04_conflicting_ci_requires_force(self):
        scenario = "E2E-04"
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            (repo / ".github").mkdir(parents=True, exist_ok=True)
            (repo / ".github" / "gitleaks.toml").write_text("custom=true\n", encoding="utf-8")

            no_force = self._run_step(
                scenario=scenario,
                step="setup_without_force",
                cmd=["bash", str(SETUP_SCRIPT), "--repo", str(repo)],
                cwd=ROOT,
                expected_codes=(2,),
            )
            if "rerun with --force to overwrite" not in no_force.stderr:
                self._record_issue(
                    scenario=scenario,
                    step="setup_without_force",
                    message="expected overwrite refusal message",
                    payload={"stderr": self._clip(no_force.stderr)},
                )

            self._run_step(
                scenario=scenario,
                step="setup_with_force",
                cmd=["bash", str(SETUP_SCRIPT), "--repo", str(repo), "--force"],
                cwd=ROOT,
            )
            cfg = (repo / ".github" / "gitleaks.toml").read_text(encoding="utf-8")
            if 'title = "gitops-workflow gitleaks config"' not in cfg:
                self._record_issue(
                    scenario=scenario,
                    step="verify_managed_config",
                    message="force setup did not restore managed gitleaks config",
                )

    def _e2e_05_staged_skip_no_changes_json(self):
        scenario = "E2E-05"
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            proc = self._run_step(
                scenario=scenario,
                step="scan_staged_json_skip",
                cmd=["bash", str(SCAN_SCRIPT), "--staged", "--format", "json", "--repo", str(repo)],
                cwd=ROOT,
            )
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                self._record_issue(
                    scenario=scenario,
                    step="scan_staged_json_skip",
                    message="stdout is not valid JSON",
                    payload={"stdout": self._clip(proc.stdout)},
                )
                return
            if payload.get("status") != "skipped" or payload.get("reason") != "no_staged_changes":
                self._record_issue(
                    scenario=scenario,
                    step="scan_staged_json_skip",
                    message="unexpected skip payload",
                    payload={"payload": payload},
                )

    def _e2e_06_staged_skip_deletions_only_json(self):
        scenario = "E2E-06"
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "obsolete.txt", "remove me\n")
            run(["git", "commit", "-m", "chore: add obsolete"], cwd=repo)
            run(["git", "rm", "obsolete.txt"], cwd=repo)

            proc = self._run_step(
                scenario=scenario,
                step="scan_staged_json_deletions_only",
                cmd=["bash", str(SCAN_SCRIPT), "--staged", "--format", "json", "--repo", str(repo)],
                cwd=ROOT,
            )
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                self._record_issue(
                    scenario=scenario,
                    step="scan_staged_json_deletions_only",
                    message="stdout is not valid JSON",
                    payload={"stdout": self._clip(proc.stdout)},
                )
                return
            if payload.get("status") != "skipped" or payload.get("reason") != "deletions_only":
                self._record_issue(
                    scenario=scenario,
                    step="scan_staged_json_deletions_only",
                    message="unexpected skip payload",
                    payload={"payload": payload},
                )

    def _e2e_07_findings_block_commit(self):
        scenario = "E2E-07"
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            bin_dir = Path(td) / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            bin_dir.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "secrets.env", "token=abc\n")
            args_file = Path(td) / "args.txt"
            fake = self._fake_gitleaks(bin_dir, args_file)

            env = os.environ.copy()
            env["GITLEAKS_BIN"] = str(fake)
            env["FAKE_ARGS"] = str(args_file)
            env["FAKE_MODE"] = "findings"

            proc = self._run_step(
                scenario=scenario,
                step="scan_findings",
                cmd=["bash", str(SCAN_SCRIPT), "--staged", "--repo", str(repo)],
                cwd=ROOT,
                env=env,
                expected_codes=(1,),
            )
            if "REDACTED" not in proc.stdout or "RAW-SECRET-123" in proc.stdout:
                self._record_issue(
                    scenario=scenario,
                    step="scan_findings",
                    message="findings output is not redacted as expected",
                    payload={"stdout": self._clip(proc.stdout)},
                )
            if "Commit blocked" not in proc.stderr:
                self._record_issue(
                    scenario=scenario,
                    step="scan_findings",
                    message="missing blocked message",
                    payload={"stderr": self._clip(proc.stderr)},
                )

    def _e2e_08_runtime_error_maps_to_setup_exit(self):
        scenario = "E2E-08"
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            bin_dir = Path(td) / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            bin_dir.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "notes.txt", "hello\n")
            args_file = Path(td) / "args.txt"
            fake = self._fake_gitleaks(bin_dir, args_file)

            env = os.environ.copy()
            env["GITLEAKS_BIN"] = str(fake)
            env["FAKE_ARGS"] = str(args_file)
            env["FAKE_MODE"] = "error"

            proc = self._run_step(
                scenario=scenario,
                step="scan_runtime_error",
                cmd=["bash", str(SCAN_SCRIPT), "--staged", "--repo", str(repo)],
                cwd=ROOT,
                env=env,
                expected_codes=(2,),
            )
            if "scanner/runtime error" not in proc.stderr:
                self._record_issue(
                    scenario=scenario,
                    step="scan_runtime_error",
                    message="missing runtime error message",
                    payload={"stderr": self._clip(proc.stderr)},
                )

    def _e2e_09_offline_fail_closed_no_download(self):
        scenario = "E2E-09"
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "notes.txt", "hello\n")

            env = os.environ.copy()
            env["GITLEAKS_BIN"] = str(Path(td) / "missing-gitleaks")

            proc = self._run_step(
                scenario=scenario,
                step="scan_no_download_missing_bin",
                cmd=["bash", str(SCAN_SCRIPT), "--staged", "--repo", str(repo), "--no-download"],
                cwd=ROOT,
                env=env,
                expected_codes=(2,),
            )
            if "not executable" not in proc.stderr:
                self._record_issue(
                    scenario=scenario,
                    step="scan_no_download_missing_bin",
                    message="missing actionable override-binary error",
                    payload={"stderr": self._clip(proc.stderr)},
                )

    def _e2e_10_pinned_update_and_path_fallback(self):
        scenario = "E2E-10"
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            fake_bin = Path(td) / "fake-bin"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "notes.txt", "hello\n")
            args_file = Path(td) / "args.txt"
            fake_gitleaks = self._fake_gitleaks(fake_bin, args_file)
            fake_gitleaks.chmod(fake_gitleaks.stat().st_mode | stat.S_IXUSR)

            fake_curl = fake_bin / "curl"
            fake_curl.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 1\n", encoding="utf-8")
            fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_ARGS"] = str(args_file)
            env["FAKE_MODE"] = "clean"
            env["FAKE_GITLEAKS_VERSION"] = "8.1.2"
            env["SENSITIVE_SCAN_GITLEAKS_VERSION"] = "v8.1.2"

            no_fallback = self._run_step(
                scenario=scenario,
                step="pinned_without_path_fallback",
                cmd=["bash", str(SCAN_SCRIPT), "--staged", "--repo", str(repo)],
                cwd=ROOT,
                env=env,
                expected_codes=(2,),
            )
            if "no fallback scanner is available" not in no_fallback.stderr:
                self._record_issue(
                    scenario=scenario,
                    step="pinned_without_path_fallback",
                    message="missing pinned no-fallback error",
                    payload={"stderr": self._clip(no_fallback.stderr)},
                )

            env["SENSITIVE_SCAN_ALLOW_PATH_BIN"] = "1"
            self._run_step(
                scenario=scenario,
                step="pinned_with_path_fallback",
                cmd=["bash", str(SCAN_SCRIPT), "--staged", "--repo", str(repo)],
                cwd=ROOT,
                env=env,
            )
            if not args_file.exists():
                self._record_issue(
                    scenario=scenario, step="pinned_with_path_fallback", message="fake scanner was not invoked"
                )

    def _e2e_11_all_mode_detect_path(self):
        scenario = "E2E-11"
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            bin_dir = Path(td) / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            bin_dir.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            stage_file(repo, "notes.txt", "hello\n")
            args_file = Path(td) / "args.txt"
            fake = self._fake_gitleaks(bin_dir, args_file)

            env = os.environ.copy()
            env["GITLEAKS_BIN"] = str(fake)
            env["FAKE_ARGS"] = str(args_file)
            env["FAKE_MODE"] = "clean"

            self._run_step(
                scenario=scenario,
                step="scan_all_mode",
                cmd=["bash", str(SCAN_SCRIPT), "--all", "--redact", "--repo", str(repo)],
                cwd=ROOT,
                env=env,
            )
            args = args_file.read_text(encoding="utf-8") if args_file.exists() else ""
            if "detect" not in args or "--no-git" not in args:
                self._record_issue(
                    scenario=scenario,
                    step="scan_all_mode",
                    message="all-mode did not use detect --no-git path",
                    payload={"args": args},
                )

    def _e2e_12_cleanup_limitation_logged(self):
        scenario = "E2E-12"
        managed_bin = SKILL_ROOT / ".bin" / "gitleaks"
        if managed_bin.exists():
            self._record_limitation(
                scenario=scenario,
                step="cleanup",
                message='Script bypass reason: uninstall path is not provided by skill scripts',
                payload={"managed_bin": str(managed_bin), "exists": True},
            )
        else:
            self._record_limitation(
                scenario=scenario,
                step="cleanup",
                message="No managed local scanner binary present; uninstall skipped",
                payload={"managed_bin": str(managed_bin), "exists": False},
            )

    def test_security_scanner_full_flow_matrix(self):
        scenarios = [
            self._e2e_01_clean_bootstrap_and_scan_pass,
            self._e2e_02_idempotent_bootstrap,
            self._e2e_03_conflicting_hook_requires_force,
            self._e2e_04_conflicting_ci_requires_force,
            self._e2e_05_staged_skip_no_changes_json,
            self._e2e_06_staged_skip_deletions_only_json,
            self._e2e_07_findings_block_commit,
            self._e2e_08_runtime_error_maps_to_setup_exit,
            self._e2e_09_offline_fail_closed_no_download,
            self._e2e_10_pinned_update_and_path_fallback,
            self._e2e_11_all_mode_detect_path,
            self._e2e_12_cleanup_limitation_logged,
        ]

        for fn in scenarios:
            try:
                fn()
            except Exception as exc:  # pragma: no cover - defensive to keep matrix going
                tb = traceback.format_exc()
                self._record_issue(
                    scenario=fn.__name__,
                    step="unhandled_exception",
                    message=f"scenario raised {type(exc).__name__}",
                    payload={"traceback": self._clip(tb, limit=3000)},
                )

        if self.issues:
            issue_summary = "\n".join(self.issues[:20])
            self.fail(
                f"{len(self.issues)} e2e issue(s) detected. "
                f"See artifact log: {self.log_path}\n{issue_summary}"
            )


if __name__ == "__main__":
    unittest.main()
