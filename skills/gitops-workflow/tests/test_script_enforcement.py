from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"


def run(cmd, *, cwd: Path, env=None, check=True):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


class ScriptSyntaxTests(unittest.TestCase):
    def test_shell_scripts_parse(self):
        targets = [
            SCRIPTS_DIR / "pr-workflow.sh",
            SCRIPTS_DIR / "governance-enforce.sh",
            SCRIPTS_DIR / "pr-unresolved-threads.sh",
        ]
        for target in targets:
            proc = run(["bash", "-n", str(target)], cwd=ROOT)
            self.assertEqual(proc.returncode, 0, f"bash -n failed for {target}\n{proc.stderr}")


class GovernanceWrapperBehaviorTests(unittest.TestCase):
    def test_governance_wrapper_runs_validate_plan_apply_audit_in_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "calls.log"

            fake_python3 = fake_bin / "python3"
            fake_python3.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "echo \"$*\" >> \"${FAKE_LOG}\"\n"
                "cmd=\"${2:-}\"\n"
                "if [[ \"$cmd\" == \"plan\" ]]; then\n"
                "  exit 3\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_python3.chmod(fake_python3.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_LOG"] = str(log_file)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "governance-enforce.sh")],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            calls = log_file.read_text(encoding="utf-8").strip().splitlines()
            self.assertGreaterEqual(len(calls), 4)
            self.assertIn(" validate ", f" {calls[0]} ")
            self.assertIn(" plan ", f" {calls[1]} ")
            self.assertIn(" apply ", f" {calls[2]} ")
            self.assertIn(" --write-codeowners", calls[2])
            self.assertIn(" audit ", f" {calls[3]} ")


class UnresolvedThreadsStrictModeTests(unittest.TestCase):
    def test_unresolved_threads_strict_mode_exits_three(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$1\" == \"api\" && \"$2\" == \"graphql\" ]]; then\n"
                "  echo '{\"author\":\"bot\",\"path\":\"a/b\",\"line\":1,\"url\":\"http://example\",\"body\":\"needs change\"}'\n"
                "  exit 0\n"
                "fi\n"
                "echo ''\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-unresolved-threads.sh"),
                    "7",
                    "--repo",
                    "acme/widget",
                    "--fail-on-unresolved",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
            self.assertIn("Unresolved inline review threads", proc.stdout)


if __name__ == "__main__":
    unittest.main()
