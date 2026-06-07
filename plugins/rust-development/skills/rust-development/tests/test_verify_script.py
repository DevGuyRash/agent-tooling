from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = ROOT / "scripts" / "verify.sh"
BANNED_FAMILY_ASSET = ROOT / "assets" / "banned_family.rs"


def run(cmd, *, cwd: Path, env=None, check=True):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def base_verify_env() -> dict[str, str]:
    env = os.environ.copy()
    env["VERIFY_RUN_FMT"] = "false"
    env["VERIFY_RUN_CLIPPY"] = "false"
    env["VERIFY_RUN_TESTS"] = "false"
    return env


class VerifyScriptParserAwareTests(unittest.TestCase):
    def create_workspace(self, temp_path: Path, *, source: str) -> Path:
        workspace = temp_path / "workspace"
        (workspace / "src").mkdir(parents=True, exist_ok=True)
        (workspace / "Cargo.toml").write_text(
            textwrap.dedent(
                """
                [package]
                name = "verify-script-repro"
                version = "0.1.0"
                edition = "2021"
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        (workspace / "src" / "lib.rs").write_text(source, encoding="utf-8")
        return workspace

    def make_fake_python(self, temp_path: Path, body: str) -> Path:
        fake_bin = temp_path / "bin"
        fake_bin.mkdir(parents=True, exist_ok=True)
        fake_python = fake_bin / "python3"
        fake_python.write_text(body, encoding="utf-8")
        fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
        return fake_bin

    def run_verify(self, workspace: Path, *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return run(
            ["bash", str(VERIFY_SCRIPT), "--dir", str(workspace)],
            cwd=ROOT,
            env=env,
            check=False,
        )

    def init_git_repo(self, workspace: Path) -> None:
        run(["git", "init", "-q"], cwd=workspace)

    def install_banned_family_harness(self, workspace: Path) -> None:
        tests_dir = workspace / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BANNED_FAMILY_ASSET, tests_dir / "banned_family.rs")

    def run_banned_family_harness(self, workspace: Path) -> subprocess.CompletedProcess[str]:
        return run(
            ["cargo", "test", "--test", "banned_family"],
            cwd=workspace,
            check=False,
        )

    def test_reports_real_parser_aware_violation_without_parser_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            workspace = self.create_workspace(
                temp_path,
                source=textwrap.dedent(
                    """
                    pub fn bad() {
                        todo!();
                    }
                    """
                ).lstrip(),
            )

            proc = self.run_verify(workspace, env=base_verify_env())

            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 1, output)
            self.assertIn("src/lib.rs:2:    todo!();", output)
            self.assertIn("✗ no todo!()", output)
            self.assertNotIn("parser-aware scan failed", output)

    def test_reports_hidden_checked_in_rust_violation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            workspace = self.create_workspace(
                temp_path,
                source="pub fn ok() {}\n",
            )
            hidden_dir = workspace / ".hidden" / "src"
            hidden_dir.mkdir(parents=True, exist_ok=True)
            (hidden_dir / "lib.rs").write_text(
                textwrap.dedent(
                    """
                    pub fn bad() {
                        todo!();
                    }
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            self.init_git_repo(workspace)

            proc = self.run_verify(workspace, env=base_verify_env())

            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 1, output)
            self.assertIn(".hidden/src/lib.rs:2:    todo!();", output)
            self.assertIn("✗ no todo!()", output)
            self.assertNotIn("parser-aware scan failed", output)

    def test_ignores_hidden_gitignored_generated_rust_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            workspace = self.create_workspace(
                temp_path,
                source="pub fn ok() {}\n",
            )
            generated_dir = workspace / ".generated"
            generated_dir.mkdir(parents=True, exist_ok=True)
            (generated_dir / "ghost.rs").write_text(
                textwrap.dedent(
                    """
                    pub fn ghost() {
                        todo!();
                    }
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            (workspace / ".gitignore").write_text(".generated/\n", encoding="utf-8")
            self.init_git_repo(workspace)

            proc = self.run_verify(workspace, env=base_verify_env())

            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, output)
            self.assertIn("✓ no todo!()", output)
            self.assertNotIn(".generated/ghost.rs", output)
            self.assertNotIn("parser-aware scan failed", output)

    def test_reports_parser_failure_cleanly_when_python_exits_one_without_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            workspace = self.create_workspace(
                temp_path,
                source="pub fn ok() {}\n",
            )
            fake_bin = self.make_fake_python(
                temp_path,
                "#!/usr/bin/env bash\nset -euo pipefail\nexit 1\n",
            )

            env = base_verify_env()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = self.run_verify(workspace, env=env)

            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 1, output)
            self.assertIn("parser-aware scan failed", output)
            self.assertNotIn("No such file or directory", output)

    def test_treats_python_exit_one_with_output_as_violation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            workspace = self.create_workspace(
                temp_path,
                source="pub fn ok() {}\n",
            )
            fake_bin = self.make_fake_python(
                temp_path,
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    printf '%s\\n' 'src/lib.rs:7:    shimmed_violation();'
                    exit 1
                    """
                ),
            )

            env = base_verify_env()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = self.run_verify(workspace, env=env)

            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 1, output)
            self.assertIn("src/lib.rs:7:    shimmed_violation();", output)
            self.assertIn("✗ no panic-inducing unwrap family", output)
            self.assertNotIn("parser-aware scan failed", output)

    def test_masks_trailing_test_attribute_after_multiline_non_test_attribute(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            workspace = self.create_workspace(
                temp_path,
                source=textwrap.dedent(
                    """
                    #[doc = concat(
                        "helper"
                    )] #[test]
                    fn helper() {
                        panic!("only in tests");
                    }

                    pub fn ok() {}
                    """
                ).lstrip(),
            )

            proc = self.run_verify(workspace, env=base_verify_env())

            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, output)
            self.assertIn("✓ no panic!()", output)
            self.assertNotIn('panic!("only in tests")', output)
            self.assertNotIn("parser-aware scan failed", output)

    def test_masks_trailing_cfg_test_attribute_after_multiline_non_test_attribute(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            workspace = self.create_workspace(
                temp_path,
                source=textwrap.dedent(
                    """
                    #[doc = concat(
                        "helper"
                    )] #[cfg(test)]
                    fn helper() {
                        panic!("only in tests");
                    }

                    pub fn ok() {}
                    """
                ).lstrip(),
            )

            proc = self.run_verify(workspace, env=base_verify_env())

            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, output)
            self.assertIn("✓ no panic!()", output)
            self.assertNotIn('panic!("only in tests")', output)
            self.assertNotIn("parser-aware scan failed", output)

    def test_banned_family_asset_masks_trailing_test_only_attributes_after_multiline_non_test_attribute(
        self,
    ):
        if shutil.which("cargo") is None:
            self.skipTest("cargo not installed")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            workspace = self.create_workspace(
                temp_path,
                source=textwrap.dedent(
                    """
                    #[doc = concat(
                        "helper"
                    )] #[test]
                    fn helper() {
                        panic!("only in tests");
                    }

                    #[doc = concat(
                        "helper"
                    )] #[cfg(test)]
                    fn helper_cfg() {
                        panic!("only in tests");
                    }

                    pub fn ok() {}
                    """
                ).lstrip(),
            )
            self.install_banned_family_harness(workspace)

            proc = self.run_banned_family_harness(workspace)

            output = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, output)
            self.assertIn("test result: ok.", output)
            self.assertNotIn("banned-family usage found", output)


if __name__ == "__main__":
    unittest.main()
