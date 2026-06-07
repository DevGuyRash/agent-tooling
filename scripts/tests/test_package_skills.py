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
                skill_dir = "plugins/tool/skills/tool"
                launcher = "scripts/tool"
                required_platforms = ["linux-x86_64"]
                ci_platforms = ["linux-x86_64"]
                """
            ).strip()
            + "\n",
        )

    def write_workspace(self) -> None:
        write(
            self.repo / "Cargo.toml",
            textwrap.dedent(
                """
                [workspace]
                members = ["crates/tool", "crates/helper"]
                resolver = "2"
                """
            ).strip()
            + "\n",
        )
        write(
            self.repo / "Cargo.lock",
            "# test lockfile\n",
        )
        write(
            self.repo / "rust-toolchain.toml",
            textwrap.dedent(
                """
                [toolchain]
                channel = "stable"
                """
            ).strip()
            + "\n",
        )
        write(
            self.repo / "crates" / "tool" / "Cargo.toml",
            textwrap.dedent(
                """
                [package]
                name = "tool"
                version = "0.1.0"
                edition = "2021"

                [dependencies]
                helper = { path = "../helper" }
                """
            ).strip()
            + "\n",
        )
        write(self.repo / "crates" / "tool" / "src" / "main.rs", "fn main() {}\n")
        write(
            self.repo / "crates" / "helper" / "Cargo.toml",
            textwrap.dedent(
                """
                [package]
                name = "helper"
                version = "0.1.0"
                edition = "2021"
                """
            ).strip()
            + "\n",
        )
        write(self.repo / "crates" / "helper" / "src" / "lib.rs", "pub fn helper() {}\n")
        write(self.repo / "plugins" / "tool" / "skills" / "tool" / "scripts" / "tool", "#!/bin/sh\n")
        write(self.repo / "plugins" / "tool" / "skills" / "tool" / "tests" / "smoke.sh", "#!/bin/sh\n")

    def write_multi_config(self) -> None:
        write(
            package_skills.CONFIG_PATH,
            textwrap.dedent(
                """
                [skills.tool]
                package = "tool"
                binary = "tool"
                skill_dir = "plugins/tool/skills/tool"
                launcher = "scripts/tool"
                required_platforms = ["linux-x86_64"]
                ci_platforms = ["linux-x86_64"]

                [skills.helper]
                package = "helper"
                binary = "helper"
                skill_dir = "plugins/helper/skills/helper"
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
        payload = self.repo / "plugins" / "tool" / "skills" / "tool" / "dist" / "linux-x86_64" / "tool"
        write(payload, "linux binary\n")
        payload.chmod(0o755)
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)

        package_skills.verify_complete("required")

    def test_compare_and_sync_artifacts_use_downloaded_artifact_tree(self) -> None:
        self.write_config()
        repo_payload = self.repo / "plugins" / "tool" / "skills" / "tool" / "dist" / "linux-x86_64" / "tool"
        write(repo_payload, "old payload\n")
        repo_payload.chmod(0o755)
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)

        artifact_root = self.repo / "artifact-downloads"
        artifact_payload = artifact_root / "skill-dist-linux-x86_64" / "plugins" / "tool" / "skills" / "tool" / "dist" / "linux-x86_64" / "tool"
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

        original_stage_host_native = package_skills.stage_host_native
        original_use_container_build = package_skills.use_container_build
        original_host_platform_id = package_skills.host_platform_id
        calls: list[tuple[list[tuple[str, dict[str, object]]], str]] = []

        def fake_stage_host_native(selected: list[tuple[str, dict[str, object]]], platform_id: str) -> None:
            calls.append((selected, platform_id))
            for _, skill in selected:
                target_name = str(skill["binary"])
                dst = self.repo / str(skill["skill_dir"]) / "dist" / platform_id / target_name
                write(dst, f"{target_name} payload\n")
                dst.chmod(0o755)

        package_skills.stage_host_native = fake_stage_host_native
        package_skills.use_container_build = lambda platform_id: False
        package_skills.host_platform_id = lambda: "linux-x86_64"
        self.addCleanup(setattr, package_skills, "stage_host_native", original_stage_host_native)
        self.addCleanup(setattr, package_skills, "use_container_build", original_use_container_build)
        self.addCleanup(setattr, package_skills, "host_platform_id", original_host_platform_id)

        package_skills.stage_host(["tool"])

        self.assertEqual(
            calls,
            [([("tool", package_skills.load_config()["tool"])], "linux-x86_64")],
        )
        self.assertTrue((self.repo / "plugins" / "tool" / "skills" / "tool" / "dist" / "linux-x86_64" / "tool").exists())
        self.assertFalse((self.repo / "plugins" / "helper" / "skills" / "helper" / "dist" / "linux-x86_64" / "helper").exists())

    def test_selected_skill_entries_rejects_unknown_skill(self) -> None:
        self.write_config()
        config = package_skills.load_config()
        with self.assertRaises(SystemExit) as ctx:
            package_skills.selected_skill_entries(config, ["missing"])
        self.assertIn("unknown packaged skill(s): missing", str(ctx.exception))

    def test_compare_artifacts_flags_stale_repo_payloads_and_sync_removes_them(self) -> None:
        self.write_config()
        repo_payload = self.repo / "plugins" / "tool" / "skills" / "tool" / "dist" / "linux-x86_64" / "tool"
        stale_payload = self.repo / "plugins" / "helper" / "skills" / "helper" / "dist" / "linux-x86_64" / "helper"
        write(repo_payload, "current payload\n")
        write(stale_payload, "stale payload\n")
        repo_payload.chmod(0o755)
        stale_payload.chmod(0o755)

        artifact_root = self.repo / "artifact-downloads"
        artifact_payload = artifact_root / "skill-dist-linux-x86_64" / "plugins" / "tool" / "skills" / "tool" / "dist" / "linux-x86_64" / "tool"
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

    def test_container_rustflags_use_fixed_container_prefixes(self) -> None:
        original_env = os.environ.copy()
        os.environ["RUSTFLAGS"] = "-C target-cpu=native"
        self.addCleanup(os.environ.clear)
        self.addCleanup(os.environ.update, original_env)

        flags = package_skills.container_rustflags()

        self.assertIn("--remap-path-prefix=/work=/workspace", flags)
        self.assertIn("--remap-path-prefix=/usr/local/cargo=/cargo-home", flags)
        self.assertIn("--remap-path-prefix=/usr/local/rustup=/rustup-home", flags)
        self.assertTrue(flags.endswith("-C target-cpu=native"))

    def test_use_container_build_prefers_docker_for_linux_x86_64_in_auto_mode(self) -> None:
        original_env = os.environ.copy()
        original_docker_available = package_skills.docker_available
        os.environ.pop("AGENT_TOOLING_DIST_BUILD_MODE", None)
        os.environ.pop("AGENT_SKILLS_DIST_BUILD_MODE", None)
        package_skills.docker_available = lambda: True
        self.addCleanup(os.environ.clear)
        self.addCleanup(os.environ.update, original_env)
        self.addCleanup(setattr, package_skills, "docker_available", original_docker_available)

        self.assertTrue(package_skills.use_container_build("linux-x86_64"))
        self.assertFalse(package_skills.use_container_build("linux-aarch64"))

    def test_dist_build_mode_accepts_deprecated_agent_skills_alias(self) -> None:
        original_env = os.environ.copy()
        os.environ.pop("AGENT_TOOLING_DIST_BUILD_MODE", None)
        os.environ["AGENT_SKILLS_DIST_BUILD_MODE"] = "host"
        self.addCleanup(os.environ.clear)
        self.addCleanup(os.environ.update, original_env)

        self.assertEqual(package_skills.dist_build_mode(), "host")

    def test_use_container_build_requires_docker_in_container_mode(self) -> None:
        original_env = os.environ.copy()
        original_docker_available = package_skills.docker_available
        os.environ["AGENT_TOOLING_DIST_BUILD_MODE"] = "container"
        os.environ.pop("AGENT_SKILLS_DIST_BUILD_MODE", None)
        package_skills.docker_available = lambda: False
        self.addCleanup(os.environ.clear)
        self.addCleanup(os.environ.update, original_env)
        self.addCleanup(setattr, package_skills, "docker_available", original_docker_available)

        with self.assertRaises(SystemExit) as ctx:
            package_skills.use_container_build("linux-x86_64")
        self.assertIn("docker is required", str(ctx.exception))

    def test_watched_repo_paths_include_crates_launchers_and_dist(self) -> None:
        self.write_config()
        self.write_workspace()

        watched = package_skills.watched_repo_paths(package_skills.load_config(), ["tool"])

        self.assertIn("packaging/skills.toml", watched)
        self.assertIn("scripts/package_skills.py", watched)
        self.assertIn("Cargo.toml", watched)
        self.assertIn("Cargo.lock", watched)
        self.assertIn("rust-toolchain.toml", watched)
        self.assertIn("crates/tool", watched)
        self.assertIn("crates/helper", watched)
        self.assertIn("plugins/tool/skills/tool/scripts/tool", watched)
        self.assertIn("plugins/tool/skills/tool/dist", watched)

    def test_matches_changed_files_respects_watch_prefixes_and_optional_tests(self) -> None:
        self.write_config()
        self.write_workspace()
        config = package_skills.load_config()

        self.assertTrue(
            package_skills.matches_changed_files(
                ["crates/helper/src/lib.rs"],
                config,
                ["tool"],
            )
        )
        self.assertTrue(
            package_skills.matches_changed_files(
                ["plugins/tool/skills/tool/dist/linux-x86_64/tool"],
                config,
                ["tool"],
            )
        )
        self.assertFalse(
            package_skills.matches_changed_files(
                ["plugins/tool/skills/tool/tests/smoke.sh"],
                config,
                ["tool"],
            )
        )
        self.assertTrue(
            package_skills.matches_changed_files(
                ["./plugins/tool/skills/tool/tests/smoke.sh"],
                config,
                ["tool"],
                include_tests=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
