from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "plugin_port.py"
SPEC = importlib.util.spec_from_file_location("plugin_port", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
plugin_port = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = plugin_port
SPEC.loader.exec_module(plugin_port)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


class PluginPortTests(unittest.TestCase):
    def test_private_operational_state_is_outside_converted_payload(self) -> None:
        source = self.root / 'source'
        self.write_codex_plugin(source)
        write(source / '.local/context/private.md', 'retained private evidence')
        write(source / '.local-test/reports/private.json', '{"private":true}')
        (source / '.local/browser-socket').symlink_to('/missing-private-runtime-socket')
        output = self.root / 'converted'
        plugin_port.convert_plugin(source, 'claude', output, mode='strict', overwrite=False)
        self.assertFalse((output / '.local').exists())
        self.assertFalse((output / '.local-test').exists())
        self.assertTrue((output / 'skills/authoring-goals/SKILL.md').is_file())

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(prefix="plugin-port-test-")
        self.root = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def write_codex_plugin(self, root: Path) -> None:
        write(
            root / ".codex-plugin" / "plugin.json",
            json.dumps(
                {
                    "name": "goalspec",
                    "version": "1.0.0",
                    "description": "Compile bounded goals.",
                    "author": {"name": "GoalSpec"},
                    "skills": "./skills/",
                    "mcpServers": "./.mcp.json",
                    "apps": "./.app.json",
                    "interface": {
                        "displayName": "GoalSpec",
                        "shortDescription": "Compile bounded goals.",
                        "longDescription": "Compile bounded goals from raw intent.",
                        "developerName": "GoalSpec",
                        "category": "Productivity",
                        "capabilities": ["Read", "Write"],
                        "defaultPrompt": ["Use GoalSpec."],
                    },
                },
                indent=2,
            )
            + "\n",
        )
        write(
            root / "skills" / "authoring-goals" / "SKILL.md",
            textwrap.dedent(
                """
                ---
                name: Authoring Goals
                description: Compile raw intent into goal contracts.
                ---

                Build a bounded goal contract.
                """
            ).lstrip(),
        )
        write(
            root / "skills" / "authoring-goals" / "agents" / "openai.yaml",
            textwrap.dedent(
                """
                interface:
                  display_name: Authoring Goals
                  short_description: Compile goals.
                policy:
                  allow_implicit_invocation: false
                """
            ).lstrip(),
        )
        write(
            root / "hooks" / "hooks.json",
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 \"$PLUGIN_ROOT/hooks/prompt.py\"",
                                        "timeout": 10,
                                    }
                                ]
                            }
                        ]
                    }
                },
                indent=2,
            )
            + "\n",
        )
        write(
            root / ".mcp.json",
            json.dumps(
                {
                    "mcpServers": {
                        "goal-tools": {
                            "cwd": ".",
                            "command": "node",
                            "args": ["./server.mjs", "$PLUGIN_ROOT/extra.mjs"],
                        }
                    }
                },
                indent=2,
            )
            + "\n",
        )
        write(root / ".app.json", json.dumps({"apps": {"demo": {"id": "asdk_app_test"}}}) + "\n")
        write(
            root / "commands" / "implement.md",
            textwrap.dedent(
                """
                # /implement

                Implement the selected design in code.
                """
            ).lstrip(),
        )
        write(
            root / "agents" / "reviewer.md",
            textwrap.dedent(
                """
                You are a reviewer agent.

                Review the converted plugin output.
                """
            ).lstrip(),
        )

    def write_claude_plugin(self, root: Path) -> None:
        write(
            root / ".claude-plugin" / "plugin.json",
            json.dumps(
                {
                    "name": "kitchen-sink",
                    "displayName": "Kitchen Sink",
                    "version": "1.2.3",
                    "description": "Claude plugin with several component types.",
                    "author": {"name": "Claude Team"},
                    "hooks": "./hooks/hooks.json",
                    "mcpServers": "./.mcp.json",
                    "outputStyles": "./output-styles/",
                    "lspServers": "./.lsp.json",
                    "experimental": {"themes": "./themes/", "monitors": "./monitors/monitors.json"},
                },
                indent=2,
            )
            + "\n",
        )
        write(
            root / "skills" / "review" / "SKILL.md",
            textwrap.dedent(
                """
                ---
                description: Review code manually.
                disable-model-invocation: true
                ---

                Review the selected code.
                """
            ).lstrip(),
        )
        write(
            root / "commands" / "deploy.md",
            textwrap.dedent(
                """
                ---
                description: Deploy the app.
                ---

                Run the deployment checklist.
                """
            ).lstrip(),
        )
        write(
            root / "agents" / "reviewer.md",
            textwrap.dedent(
                """
                ---
                description: Review pull requests.
                ---

                Review the change set thoroughly.
                """
            ).lstrip(),
        )
        write(
            root / "hooks" / "hooks.json",
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "${CLAUDE_PLUGIN_ROOT}/scripts/check.sh",
                                    }
                                ],
                            }
                        ],
                        "Notification": [
                            {
                                "hooks": [
                                    {
                                        "type": "http",
                                        "url": "https://example.com/hook",
                                    }
                                ]
                            }
                        ],
                    }
                },
                indent=2,
            )
            + "\n",
        )
        write(
            root / ".mcp.json",
            json.dumps(
                {
                    "mcpServers": {
                        "tools": {
                            "command": "${CLAUDE_PLUGIN_ROOT}/server",
                        }
                    }
                }
            )
            + "\n",
        )
        write(root / ".lsp.json", json.dumps({"python": {"command": "pyright", "extensionToLanguage": {".py": "python"}}}) + "\n")
        write(root / "output-styles" / "terse.md", "---\nname: Terse\n---\nBe terse.\n")
        write(root / "themes" / "dark.json", json.dumps({"name": "Dark", "base": "dark"}) + "\n")
        write(root / "monitors" / "monitors.json", "[]\n")

    def test_codex_plugin_converts_to_claude_with_env_and_skill_policy(self) -> None:
        source = self.root / "goalspec"
        out = self.root / "out"
        self.write_codex_plugin(source)

        report = plugin_port.convert_plugin(source, "claude", out, mode="strict", overwrite=False)

        manifest = read_json(out / ".claude-plugin" / "plugin.json")
        self.assertEqual(manifest["name"], "goalspec")
        self.assertNotIn("hooks", manifest)
        hooks = read_json(out / "hooks" / "hooks.json")
        command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", command)
        mcp = read_json(out / ".mcp.json")
        self.assertEqual("${CLAUDE_PLUGIN_ROOT}", mcp["mcpServers"]["goal-tools"]["cwd"])
        self.assertEqual("${CLAUDE_PLUGIN_ROOT}/server.mjs", mcp["mcpServers"]["goal-tools"]["args"][0])
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", mcp["mcpServers"]["goal-tools"]["args"][0])
        converted_command = (out / "commands" / "implement.md").read_text(encoding="utf-8")
        self.assertTrue(converted_command.startswith("---\n"))
        self.assertIn("description:", converted_command)
        converted_agent = (out / "agents" / "reviewer.md").read_text(encoding="utf-8")
        self.assertTrue(converted_agent.startswith("---\n"))
        self.assertIn("description:", converted_agent)
        skill_text = (out / "skills" / "authoring-goals" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("disable-model-invocation: true", skill_text)
        self.assertTrue((out / ".app.json").exists())
        self.assertTrue(any(item["kind"] == "codex-apps" for item in report.preserved_only))
        self.assertEqual(report.schema_version, plugin_port.REPORT_SCHEMA_VERSION)
        self.assertEqual(report.status, "success")
        self.assertEqual(report.support_level, "supported-with-preserved-surfaces")
        self.assertTrue(any(item["kind"] == "apps" for item in report.executable_surfaces))

    def test_conversion_thaws_read_only_files_only_in_staging_output(self) -> None:
        source = self.root / "goalspec"
        out = self.root / "out"
        self.write_codex_plugin(source)
        skill = source / "skills" / "authoring-goals" / "SKILL.md"
        skill.chmod(0o444)

        plugin_port.convert_plugin(source, "claude", out, mode="strict", overwrite=False)

        self.assertEqual(0o444, stat.S_IMODE(skill.stat().st_mode))
        converted = out / "skills" / "authoring-goals" / "SKILL.md"
        self.assertTrue(stat.S_IMODE(converted.stat().st_mode) & stat.S_IWUSR)
        self.assertIn("disable-model-invocation: true", converted.read_text(encoding="utf-8"))

    def test_mcp_runtime_path_escape_is_rejected(self) -> None:
        source = self.root / "goalspec"
        self.write_codex_plugin(source)
        mcp = read_json(source / ".mcp.json")
        mcp["mcpServers"]["goal-tools"]["args"] = ["../outside.mjs"]
        write(source / ".mcp.json", json.dumps(mcp, indent=2) + "\n")

        with self.assertRaisesRegex(plugin_port.PluginPortError, "path escapes the plugin root"):
            plugin_port.convert_plugin(
                source,
                "claude",
                self.root / "out",
                mode="strict",
                overwrite=False,
            )

    def test_codex_external_validator_respects_codex_home(self) -> None:
        codex_home = self.root / "codex-home"
        validator = (
            codex_home / "skills" / ".system" / "plugin-creator" / "scripts" / "validate_plugin.py"
        )
        write(validator, "raise SystemExit(0)\n")

        previous = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(codex_home)
        try:
            result = plugin_port.run_external_validator(self.root, "codex")
        finally:
            if previous is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(str(validator), result["command"][1])

    def test_roundtrip_defaults_to_strict_and_validates_second_hop(self) -> None:
        source = self.root / "goalspec"
        self.write_codex_plugin(source)
        args = plugin_port.build_parser().parse_args(
            ["roundtrip", str(source), "--to", "claude", "--tmp", str(self.root / "rt")]
        )
        self.assertEqual("strict", args.mode)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = plugin_port.main(
                [
                    "roundtrip",
                    str(source),
                    "--to",
                    "claude",
                    "--tmp",
                    str(self.root / "rt"),
                    "--summary",
                    "json",
                ]
            )
        self.assertEqual(0, code)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["second_validation"]["validation_summary"]["internal"]["passed"])

    def test_codex_to_claude_quarantines_root_claude_md(self) -> None:
        source = self.root / "goalspec"
        out = self.root / "out"
        self.write_codex_plugin(source)
        write(source / "CLAUDE.md", "# GoalSpec\n\nRoot context that Claude plugins do not load.\n")

        report = plugin_port.convert_plugin(source, "claude", out, mode="strict", overwrite=False)

        self.assertFalse((out / "CLAUDE.md").exists())
        self.assertTrue((out / ".plugin-portability" / "preserved" / "CLAUDE.md").exists())
        self.assertTrue(any(item["kind"] == "claude-root-context" for item in report.preserved_only))
        validation = plugin_port.validate_plugin(out, "claude", external=False)
        self.assertTrue(validation.validation_summary["internal"]["passed"])

    def test_conversion_excludes_only_generated_junk_from_output_and_inventory(self) -> None:
        source = self.root / "goalspec"
        out = self.root / "out"
        self.write_codex_plugin(source)
        excluded_files = {
            Path(".DS_Store"),
            Path("assets/Thumbs.db"),
            Path("scripts/cache.pyc"),
            Path("scripts/cache.pyo"),
            Path("scripts/cache.pyd"),
            Path("lib/__pycache__/keep.py"),
        }
        ordinary = {
            Path("assets/thumbs.db"),
            Path("cache-target/keep.py"),
            Path("scripts/cache.pyc.txt"),
            Path("scripts/ordinary.pyc/keep.txt"),
            Path("scripts/worker.py"),
        }
        for relative in excluded_files | ordinary:
            write(source / relative, f"fixture for {relative.as_posix()}\n")
        linked_cache = source / "scripts" / "__pycache__"
        linked_cache.symlink_to(Path("../cache-target"), target_is_directory=True)
        excluded = excluded_files | {Path("scripts/__pycache__")}

        source_inventory = set(plugin_port.rel_files(source))
        self.assertTrue({path.as_posix() for path in ordinary} <= source_inventory)
        self.assertTrue({path.as_posix() for path in excluded}.isdisjoint(source_inventory))

        report = plugin_port.convert_plugin(source, "claude", out, mode="strict", overwrite=False)

        for relative in excluded:
            self.assertFalse((out / relative).exists())
        self.assertFalse((out / "scripts" / "__pycache__").exists())
        for relative in ordinary:
            self.assertTrue((out / relative).is_file())
        copied = set(report.files_copied)
        self.assertTrue({path.as_posix() for path in ordinary} <= copied)
        self.assertTrue({path.as_posix() for path in excluded}.isdisjoint(copied))

    def test_conversion_preserves_safe_in_tree_symlinks(self) -> None:
        source = self.root / "goalspec"
        out = self.root / "out"
        self.write_codex_plugin(source)
        write(source / "assets" / "payload.txt", "payload\n")
        (source / "assets" / "payload-link.txt").symlink_to(Path("payload.txt"))
        (source / "asset-link").symlink_to(Path("assets"), target_is_directory=True)

        report = plugin_port.convert_plugin(source, "claude", out, mode="strict", overwrite=False)

        copied_link = out / "assets" / "payload-link.txt"
        self.assertTrue(copied_link.is_symlink())
        self.assertEqual(Path("payload.txt"), copied_link.readlink())
        self.assertEqual("payload\n", copied_link.read_text(encoding="utf-8"))
        copied_directory_link = out / "asset-link"
        self.assertTrue(copied_directory_link.is_symlink())
        self.assertEqual(Path("assets"), copied_directory_link.readlink())
        self.assertEqual("payload\n", (copied_directory_link / "payload.txt").read_text(encoding="utf-8"))
        self.assertIn("asset-link", report.files_copied)
        self.assertIn("assets/payload-link.txt", report.files_copied)

    def test_conversion_rejects_outbound_file_symlink_before_copy(self) -> None:
        source = self.root / "goalspec"
        out = self.root / "out"
        self.write_codex_plugin(source)
        outside = self.root / "outside.txt"
        write(outside, "secret\n")
        (source / "assets").mkdir()
        (source / "assets" / "leak.txt").symlink_to(outside)

        with self.assertRaisesRegex(plugin_port.PluginPortError, "resolves outside the plugin root"):
            plugin_port.convert_plugin(source, "claude", out, mode="strict", overwrite=False)

        self.assertFalse(out.exists())

    def test_conversion_rejects_outbound_directory_and_pycache_symlinks(self) -> None:
        for link_name in ("vendor", "__pycache__"):
            with self.subTest(link_name=link_name):
                case_root = self.root / link_name
                source = case_root / "goalspec"
                out = case_root / "out"
                outside = case_root / "outside"
                self.write_codex_plugin(source)
                write(outside / "secret.txt", "secret\n")
                scripts = source / "scripts"
                scripts.mkdir()
                (scripts / link_name).symlink_to(outside, target_is_directory=True)

                with self.assertRaisesRegex(plugin_port.PluginPortError, "resolves outside the plugin root"):
                    plugin_port.convert_plugin(source, "claude", out, mode="strict", overwrite=False)

                self.assertFalse(out.exists())

    def test_conversion_rejects_broken_and_looping_symlinks_clearly(self) -> None:
        for case_name, expected in (("broken", "is broken"), ("loop", "symlink loop")):
            with self.subTest(case_name=case_name):
                case_root = self.root / case_name
                source = case_root / "goalspec"
                self.write_codex_plugin(source)
                if case_name == "broken":
                    (source / "broken-link").symlink_to(Path("missing-target"))
                else:
                    (source / "loop-a").symlink_to(Path("loop-b"))
                    (source / "loop-b").symlink_to(Path("loop-a"))

                with self.assertRaisesRegex(plugin_port.PluginPortError, expected):
                    plugin_port.convert_plugin(
                        source,
                        "claude",
                        case_root / "out",
                        mode="strict",
                        overwrite=False,
                    )

    def test_validation_rejects_outbound_symlink_with_validation_exit_code(self) -> None:
        source = self.root / "goalspec"
        self.write_codex_plugin(source)
        outside = self.root / "outside.txt"
        write(outside, "secret\n")
        (source / "leak.txt").symlink_to(outside)

        with self.assertRaisesRegex(plugin_port.PluginPortError, "resolves outside the plugin root") as caught:
            plugin_port.validate_plugin(source, "codex", external=False)

        self.assertEqual(plugin_port.EXIT_VALIDATION_FAILED, caught.exception.exit_code)

    def test_report_includes_only_real_skill_script_directories_as_active(self) -> None:
        source = self.root / "goalspec"
        out = self.root / "out"
        self.write_codex_plugin(source)
        write(source / "skills" / "authoring-goals" / "scripts" / "run.sh", "#!/bin/sh\n")
        write(
            source / "skills" / "z-last" / "SKILL.md",
            "---\nname: z-last\ndescription: Last skill.\n---\n\nRun the last skill.\n",
        )
        write(source / "skills" / "z-last" / "scripts" / "run.py", "print('run')\n")
        write(source / "skills" / "authoring-goals" / "evals" / "scripts" / "fixture.py", "pass\n")
        write(source / "skills" / "not-a-skill" / "scripts" / "fixture.py", "pass\n")
        write(source / "evals" / "scripts" / "fixture.py", "pass\n")

        report = plugin_port.convert_plugin(source, "claude", out, mode="strict", overwrite=False)

        skill_scripts = [
            item
            for item in report.executable_surfaces
            if item["path"].startswith("skills/") and item["path"].endswith("/scripts")
        ]
        self.assertEqual(
            ["skills/authoring-goals/scripts", "skills/z-last/scripts"],
            [item["path"] for item in skill_scripts],
        )
        self.assertTrue(all(item["kind"] == "scripts" for item in skill_scripts))
        self.assertTrue(all(item["active_in_target"] for item in skill_scripts))

    def test_report_includes_only_executable_skill_dist_payloads(self) -> None:
        source = self.root / "goalspec"
        out = self.root / "out"
        self.write_codex_plugin(source)
        binary = source / "skills" / "authoring-goals" / "dist" / "linux-x86_64" / "goal-tool"
        write(binary, "packaged executable\n")
        binary.chmod(0o755)
        write(
            source / "skills" / "authoring-goals" / "dist" / "linux-x86_64" / "README.txt",
            "packaged data\n",
        )
        unrelated = source / "skills" / "not-a-skill" / "dist" / "linux-x86_64" / "fixture"
        write(unrelated, "not a skill payload\n")
        unrelated.chmod(0o755)

        report = plugin_port.convert_plugin(source, "claude", out, mode="strict", overwrite=False)

        dist_surfaces = [
            item
            for item in report.executable_surfaces
            if "/dist/" in item["path"]
        ]
        self.assertEqual(
            ["skills/authoring-goals/dist/linux-x86_64/goal-tool"],
            [item["path"] for item in dist_surfaces],
        )
        self.assertTrue(all(item["kind"] == "binary" for item in dist_surfaces))
        self.assertTrue(all(item["active_in_target"] for item in dist_surfaces))

    def test_claude_plugin_best_effort_converts_to_codex_and_reports_unsupported(self) -> None:
        source = self.root / "kitchen"
        out = self.root / "codex-out"
        self.write_claude_plugin(source)

        report = plugin_port.convert_plugin(source, "codex", out, mode="best-effort", overwrite=False)

        manifest = read_json(out / ".codex-plugin" / "plugin.json")
        self.assertEqual(manifest["name"], "kitchen-sink")
        self.assertEqual(manifest["skills"], "./skills/")
        converted_command = out / "skills" / "deploy" / "SKILL.md"
        self.assertTrue(converted_command.exists())
        self.assertIn("Deploy the app.", converted_command.read_text(encoding="utf-8"))
        skill_text = (out / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: review", skill_text)
        self.assertNotIn("disable-model-invocation", skill_text)
        self.assertTrue((out / "skills" / "review" / "agents" / "openai.yaml").exists())
        hooks = read_json(out / "hooks" / "hooks.json")
        self.assertIn("PreToolUse", hooks["hooks"])
        self.assertNotIn("Notification", hooks["hooks"])
        self.assertTrue(any(item["kind"] == "hook-event" for item in report.unsupported))
        self.assertTrue(any(item["kind"] == "claude-lsp" for item in report.preserved_only))
        self.assertTrue(any(item["kind"] == "claude-agents" for item in report.preserved_only))
        self.assertEqual(report.support_level, "best-effort-lossy")

    def test_claude_lowercase_skill_entrypoint_converts_to_codex_skill_md(self) -> None:
        source = self.root / "lowercase-skill"
        out = self.root / "codex-out"
        write(
            source / ".claude-plugin" / "plugin.json",
            json.dumps(
                {
                    "name": "lowercase-skill",
                    "version": "1.0.0",
                    "description": "Claude plugin with lowercase skill entrypoint.",
                },
                indent=2,
            )
            + "\n",
        )
        write(
            source / "skills" / "git-commit" / "skill.md",
            textwrap.dedent(
                """
                ---
                description: Commit changes with project conventions.
                ---

                Create a commit after checking repository state.
                """
            ).lstrip(),
        )

        payload = json.loads(plugin_port.inspect_path(source, fmt="json", explicit_host="claude"))
        self.assertIn("skills/git-commit/skill.md", payload["components"]["skills"])

        report = plugin_port.convert_plugin(source, "codex", out, mode="strict", overwrite=False)

        self.assertFalse((out / "skills" / "git-commit" / "skill.md").exists())
        converted = out / "skills" / "git-commit" / "SKILL.md"
        self.assertTrue(converted.exists())
        self.assertIn("name: git-commit", converted.read_text(encoding="utf-8"))
        self.assertTrue(
            any(
                item["source"] == "skills/git-commit/skill.md"
                and item["target"] == "skills/git-commit/SKILL.md"
                for item in report.mappings
            )
        )
        validation = plugin_port.validate_plugin(out, "codex", external=False)
        self.assertTrue(validation.validation_summary["internal"]["passed"])

    def test_invalid_skill_frontmatter_best_effort_converts_with_generated_metadata(self) -> None:
        source = self.root / "invalid-skill"
        out = self.root / "codex-out"
        write(
            source / ".claude-plugin" / "plugin.json",
            json.dumps(
                {
                    "name": "invalid-skill",
                    "version": "1.0.0",
                    "description": "Plugin with malformed skill metadata.",
                },
                indent=2,
            )
            + "\n",
        )
        write(
            source / "skills" / "monitor" / "SKILL.md",
            textwrap.dedent(
                """
                ---
                name: monitor
                description: Use this skill when: monitoring systems.
                ---

                # Monitor

                Analyze system telemetry.
                """
            ).lstrip(),
        )

        report = plugin_port.convert_plugin(source, "codex", out, mode="best-effort", overwrite=False)

        converted = out / "skills" / "monitor" / "SKILL.md"
        converted_text = converted.read_text(encoding="utf-8")
        self.assertIn("name: monitor", converted_text)
        self.assertIn("description: Monitor", converted_text)
        self.assertIn("Analyze system telemetry.", converted_text)
        self.assertTrue(any(item["kind"] == "skill-frontmatter" for item in report.unsupported))
        self.assertEqual(report.support_level, "best-effort-lossy")
        validation = plugin_port.validate_plugin(out, "codex", external=False)
        self.assertTrue(validation.validation_summary["internal"]["passed"])

        with self.assertRaises(plugin_port.PluginPortError):
            plugin_port.convert_plugin(source, "codex", self.root / "strict-out", mode="strict", overwrite=False)

    def test_claude_plugin_strict_rejects_codex_unsupported_hooks(self) -> None:
        source = self.root / "kitchen"
        out = self.root / "codex-out"
        self.write_claude_plugin(source)

        with self.assertRaises(plugin_port.PluginPortError):
            plugin_port.convert_plugin(source, "codex", out, mode="strict", overwrite=False)

    def test_claude_command_invalid_frontmatter_best_effort_converts_body(self) -> None:
        source = self.root / "relaxed-command"
        out = self.root / "codex-out"
        write(
            source / ".claude-plugin" / "plugin.json",
            json.dumps(
                {
                    "name": "relaxed-command",
                    "version": "1.0.0",
                    "description": "Claude command with relaxed metadata.",
                },
                indent=2,
            )
            + "\n",
        )
        write(
            source / "commands" / "add-agent.md",
            textwrap.dedent(
                """
                ---
                description: Add a new sub-agent to the current plugin
                argument-hint: [agent-name] ["description"]
                ---

                # Add Agent

                Create a new sub-agent file.
                """
            ).lstrip(),
        )

        report = plugin_port.convert_plugin(source, "codex", out, mode="best-effort", overwrite=False)

        converted = out / "skills" / "add-agent" / "SKILL.md"
        self.assertTrue(converted.exists())
        converted_text = converted.read_text(encoding="utf-8")
        self.assertIn("Create a new sub-agent file.", converted_text)
        self.assertIn("description: Add Agent", converted_text)
        self.assertTrue(any(item["kind"] == "command-frontmatter" for item in report.unsupported))
        self.assertEqual(report.support_level, "best-effort-lossy")
        validation = plugin_port.validate_plugin(out, "codex", external=False)
        self.assertTrue(validation.validation_summary["internal"]["passed"])

        with self.assertRaises(plugin_port.PluginPortError):
            plugin_port.convert_plugin(source, "codex", self.root / "strict-out", mode="strict", overwrite=False)

    def test_claude_marketplace_converts_local_plugins_to_codex_marketplace(self) -> None:
        marketplace = self.root / "market"
        plugin = marketplace / "plugins" / "kitchen"
        self.write_claude_plugin(plugin)
        write(
            marketplace / ".claude-plugin" / "marketplace.json",
            json.dumps(
                {
                    "name": "team-tools",
                    "owner": {"name": "Team"},
                    "plugins": [
                        {
                            "name": "legacy-kitchen-alias",
                            "source": "./plugins/kitchen",
                            "description": "Kitchen plugin",
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
        )
        out = self.root / "codex-market"

        report = plugin_port.convert_marketplace(marketplace, "codex", out, mode="best-effort", overwrite=False)

        manifest = read_json(out / ".agents" / "plugins" / "marketplace.json")
        self.assertEqual(manifest["name"], "team-tools")
        self.assertEqual(manifest["plugins"][0]["source"]["path"], "./plugins/kitchen-sink")
        self.assertEqual(manifest["plugins"][0]["name"], "kitchen-sink")
        self.assertEqual(manifest["plugins"][0]["policy"]["installation"], "AVAILABLE")
        self.assertTrue((out / "plugins" / "kitchen-sink" / ".codex-plugin" / "plugin.json").exists())
        self.assertTrue(report.mappings)

    def test_inspect_reports_manifestless_claude_plugin(self) -> None:
        source = self.root / "manifestless"
        write(source / "skills" / "audit" / "SKILL.md", "---\ndescription: Audit things.\n---\nAudit.\n")

        payload = json.loads(plugin_port.inspect_path(source, fmt="json", explicit_host="claude"))

        self.assertEqual(payload["kind"], "plugin")
        self.assertEqual(payload["host"], "claude")
        self.assertIn("skills", payload["components"])

    def test_codex_validation_reports_invalid_skill_frontmatter_without_traceback(self) -> None:
        source = self.root / "bad-frontmatter"
        self.write_codex_plugin(source)
        write(
            source / "skills" / "authoring-goals" / "SKILL.md",
            "---\nname: authoring-goals\ndescription: broken: yaml\n---\nBody.\n",
        )

        with self.assertRaisesRegex(plugin_port.PluginPortError, "frontmatter must be valid YAML"):
            plugin_port.validate_plugin(source, "codex", external=False)

    def test_codex_validation_rejects_unsupported_manifest_fields(self) -> None:
        source = self.root / "bad-manifest"
        self.write_codex_plugin(source)
        manifest = read_json(source / ".codex-plugin" / "plugin.json")
        manifest["hooks"] = "./hooks/hooks.json"
        write(source / ".codex-plugin" / "plugin.json", json.dumps(manifest, indent=2) + "\n")

        with self.assertRaisesRegex(plugin_port.PluginPortError, "field `hooks` is not accepted"):
            plugin_port.validate_plugin(source, "codex", external=False)

    def test_codex_validation_summary_and_external_missing_warning(self) -> None:
        source = self.root / "valid"
        self.write_codex_plugin(source)

        original = plugin_port.run_external_validator
        try:
            plugin_port.run_external_validator = lambda path, host: None  # type: ignore[assignment]
            report = plugin_port.validate_plugin(source, "codex", external=True)
        finally:
            plugin_port.run_external_validator = original  # type: ignore[assignment]

        self.assertTrue(report.validation_summary["internal"]["passed"])
        self.assertFalse(report.validation_summary["external"]["available"])
        self.assertTrue(any("validator unavailable" in warning for warning in report.warnings))

    def test_validate_requires_external_validator_when_requested(self) -> None:
        source = self.root / "valid"
        self.write_codex_plugin(source)

        original = plugin_port.run_external_validator
        try:
            plugin_port.run_external_validator = lambda path, host: None  # type: ignore[assignment]
            with self.assertRaisesRegex(plugin_port.PluginPortError, "validator is required"):
                plugin_port.validate_plugin(source, "codex", external=True, require_external=True)
        finally:
            plugin_port.run_external_validator = original  # type: ignore[assignment]

    def test_validate_command_uses_distinct_exit_codes(self) -> None:
        source = self.root / "bad-manifest"
        self.write_codex_plugin(source)
        manifest = read_json(source / ".codex-plugin" / "plugin.json")
        manifest["version"] = "not-semver"
        write(source / ".codex-plugin" / "plugin.json", json.dumps(manifest, indent=2) + "\n")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = plugin_port.main(["validate", str(source), "--host", "codex", "--no-external"])

        self.assertEqual(plugin_port.EXIT_VALIDATION_FAILED, code)
        self.assertIn("strict semver", stderr.getvalue())

    def test_marketplace_strict_rejects_path_escape(self) -> None:
        marketplace = self.root / "market"
        write(
            marketplace / ".claude-plugin" / "marketplace.json",
            json.dumps(
                {
                    "name": "team-tools",
                    "owner": {"name": "Team"},
                    "plugins": [{"name": "escape", "source": {"source": "local", "path": "../escape"}}],
                },
                indent=2,
            )
            + "\n",
        )

        with self.assertRaisesRegex(plugin_port.PluginPortError, "escapes root"):
            plugin_port.convert_marketplace(marketplace, "codex", self.root / "out", mode="strict", overwrite=False)

    def test_summary_output_is_concise_json(self) -> None:
        source = self.root / "goalspec"
        out = self.root / "out"
        self.write_codex_plugin(source)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = plugin_port.main(
                [
                    "convert",
                    str(source),
                    "--to",
                    "claude",
                    "--out",
                    str(out),
                    "--summary",
                    "json",
                ]
            )

        self.assertEqual(0, code)
        payload = json.loads(stdout.getvalue())
        self.assertEqual("success", payload["status"])
        self.assertIn("executable_surfaces_count", payload)




class DualHostRootPreservationTest(unittest.TestCase):
    def test_dual_host_fallback_survives_both_directions(self) -> None:
        from plugin_port import DUAL_HOST_ROOT, recursive_replace

        command = 'python3 "%s/hooks/scripts/scope_guard.py"' % DUAL_HOST_ROOT
        for replacements in (
            {"${CLAUDE_PLUGIN_ROOT}": "${PLUGIN_ROOT}", "$CLAUDE_PLUGIN_ROOT": "$PLUGIN_ROOT"},
            {"${PLUGIN_ROOT}": "${CLAUDE_PLUGIN_ROOT}", "$PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}"},
        ):
            self.assertEqual(command, recursive_replace(command, replacements))
        # Plain single-host references still rewrite.
        self.assertEqual(
            "${PLUGIN_ROOT}/x",
            recursive_replace("${CLAUDE_PLUGIN_ROOT}/x", {"${CLAUDE_PLUGIN_ROOT}": "${PLUGIN_ROOT}"}),
        )

if __name__ == "__main__":
    unittest.main()
