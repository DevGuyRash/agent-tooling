from __future__ import annotations

import importlib.util
import os
import platform
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "package_skills.py"
SPEC = importlib.util.spec_from_file_location("package_skills", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
package_skills = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_skills)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class PackageSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(prefix="package-skills-test-")
        self.repo = Path(self.tmpdir.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.original_repo_root = package_skills.REPO_ROOT
        self.original_config_path = package_skills.CONFIG_PATH
        package_skills.REPO_ROOT = self.repo
        package_skills.CONFIG_PATH = self.repo / "packaging" / "skills.toml"
        self.addCleanup(self.restore_module_paths)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def restore_module_paths(self) -> None:
        package_skills.REPO_ROOT = self.original_repo_root
        package_skills.CONFIG_PATH = self.original_config_path

    def write_config(self) -> None:
        write(
            package_skills.CONFIG_PATH,
            textwrap.dedent(
                """
                [skills.tool]
                package = "tool"
                binary = "tool"
                skill_dir = "skills/tool"
                launcher = "scripts/tool"
                required_platforms = ["linux-x86_64"]
                ci_platforms = ["linux-x86_64"]
                """
            ).strip()
            + "\n",
        )

    def write_multi_config(self) -> None:
        write(
            package_skills.CONFIG_PATH,
            textwrap.dedent(
                """
                [skills.tool]
                package = "tool"
                binary = "tool"
                skill_dir = "skills/tool"
                launcher = "scripts/tool"
                required_platforms = ["linux-x86_64"]
                ci_platforms = ["linux-x86_64"]

                [skills.helper]
                package = "helper"
                binary = "helper"
                skill_dir = "skills/helper"
                launcher = "scripts/helper"
                required_platforms = ["linux-x86_64"]
                ci_platforms = ["linux-x86_64"]
                """
            ).strip()
            + "\n",
        )

    def test_selected_platforms_prefers_manifest_order(self) -> None:
        self.write_config()
        config = package_skills.load_config()
        self.assertEqual(package_skills.selected_platforms(config, "required"), ["linux-x86_64"])
        self.assertEqual(package_skills.selected_platforms(config, "ci"), ["linux-x86_64"])
        self.assertEqual(package_skills.selected_platforms(config, "all"), ["linux-x86_64"])

    def test_host_platform_id_rejects_non_linux_hosts(self) -> None:
        original_sys_platform = sys.platform
        original_machine = platform.machine
        original_module_sys_platform = package_skills.sys.platform
        original_module_platform_machine = package_skills.platform.machine

        sys.platform = "darwin"
        package_skills.sys.platform = "darwin"
        platform.machine = lambda: "x86_64"
        package_skills.platform.machine = lambda: "x86_64"
        self.addCleanup(setattr, sys, "platform", original_sys_platform)
        self.addCleanup(setattr, package_skills.sys, "platform", original_module_sys_platform)
        self.addCleanup(setattr, platform, "machine", original_machine)
        self.addCleanup(setattr, package_skills.platform, "machine", original_module_platform_machine)

        with self.assertRaises(SystemExit) as ctx:
            package_skills.host_platform_id()
        self.assertIn("only Linux packaging is supported", str(ctx.exception))

    def test_verify_complete_accepts_tracked_required_payloads(self) -> None:
        self.write_config()
        payload = self.repo / "skills" / "tool" / "dist" / "linux-x86_64" / "tool"
        write(payload, "linux binary\n")
        payload.chmod(0o755)
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)

        package_skills.verify_complete("required")

    def test_compare_and_sync_artifacts_use_downloaded_artifact_tree(self) -> None:
        self.write_config()
        repo_payload = self.repo / "skills" / "tool" / "dist" / "linux-x86_64" / "tool"
        write(repo_payload, "old payload\n")
        repo_payload.chmod(0o755)
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)

        artifact_root = self.repo / "artifact-downloads"
        artifact_payload = artifact_root / "skill-dist-linux-x86_64" / "skills" / "tool" / "dist" / "linux-x86_64" / "tool"
        write(artifact_payload, "new payload\n")

        with self.assertRaises(SystemExit):
            package_skills.compare_artifacts(artifact_root, "required")

        package_skills.sync_artifacts(artifact_root, "required")
        self.assertEqual(repo_payload.read_text(encoding="utf-8"), "new payload\n")
        package_skills.compare_artifacts(artifact_root, "required")

    def test_stage_host_can_target_specific_skills(self) -> None:
        self.write_multi_config()
        target_release = self.repo / "target" / "release"
        write(target_release / "tool", "tool payload\n")
        write(target_release / "helper", "helper payload\n")

        original_run = package_skills.run
        original_host_platform_id = package_skills.host_platform_id
        commands: list[tuple[list[str], dict[str, str] | None]] = []

        def fake_run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
            commands.append((cmd, env))

        package_skills.run = fake_run
        package_skills.host_platform_id = lambda: "linux-x86_64"
        self.addCleanup(setattr, package_skills, "run", original_run)
        self.addCleanup(setattr, package_skills, "host_platform_id", original_host_platform_id)

        package_skills.stage_host(["tool"])

        self.assertEqual(
            commands,
            [(["cargo", "build", "--workspace", "--release", "--locked", "-p", "tool"], package_skills.build_env())],
        )
        self.assertTrue((self.repo / "skills" / "tool" / "dist" / "linux-x86_64" / "tool").exists())
        self.assertFalse((self.repo / "skills" / "helper" / "dist" / "linux-x86_64" / "helper").exists())

    def test_selected_skill_entries_rejects_unknown_skill(self) -> None:
        self.write_config()
        config = package_skills.load_config()
        with self.assertRaises(SystemExit) as ctx:
            package_skills.selected_skill_entries(config, ["missing"])
        self.assertIn("unknown packaged skill(s): missing", str(ctx.exception))

    def test_compare_artifacts_flags_stale_repo_payloads_and_sync_removes_them(self) -> None:
        self.write_config()
        repo_payload = self.repo / "skills" / "tool" / "dist" / "linux-x86_64" / "tool"
        stale_payload = self.repo / "skills" / "helper" / "dist" / "linux-x86_64" / "helper"
        write(repo_payload, "current payload\n")
        write(stale_payload, "stale payload\n")
        repo_payload.chmod(0o755)
        stale_payload.chmod(0o755)

        artifact_root = self.repo / "artifact-downloads"
        artifact_payload = artifact_root / "skill-dist-linux-x86_64" / "skills" / "tool" / "dist" / "linux-x86_64" / "tool"
        write(artifact_payload, "current payload\n")

        with self.assertRaises(SystemExit) as ctx:
            package_skills.compare_artifacts(artifact_root, "required")
        self.assertIn("artifact payloads do not match", str(ctx.exception))

        package_skills.sync_artifacts(artifact_root, "required")
        self.assertTrue(repo_payload.exists())
        self.assertFalse(stale_payload.exists())
        package_skills.compare_artifacts(artifact_root, "required")

    def test_build_env_adds_reproducible_remap_flags(self) -> None:
        original_env = os.environ.copy()
        original_repo_root = package_skills.REPO_ROOT
        package_skills.REPO_ROOT = Path("/workspace/repo")
        os.environ["CARGO_HOME"] = "/custom/cargo"
        os.environ["RUSTUP_HOME"] = "/custom/rustup"
        os.environ["RUSTFLAGS"] = "-C target-cpu=native"
        self.addCleanup(setattr, package_skills, "REPO_ROOT", original_repo_root)
        self.addCleanup(os.environ.clear)
        self.addCleanup(os.environ.update, original_env)

        env = package_skills.build_env()

        self.assertIn("--remap-path-prefix=/workspace/repo=/workspace", env["RUSTFLAGS"])
        self.assertIn("--remap-path-prefix=/custom/cargo=/cargo-home", env["RUSTFLAGS"])
        self.assertIn("--remap-path-prefix=/custom/rustup=/rustup-home", env["RUSTFLAGS"])
        self.assertTrue(env["RUSTFLAGS"].endswith("-C target-cpu=native"))


if __name__ == "__main__":
    unittest.main()
