from __future__ import annotations

import importlib.util
import contextlib
import io
import json
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
                    "name": "goal-foundry",
                    "version": "1.0.0",
                    "description": "Compile bounded goals.",
                    "author": {"name": "Goal Foundry"},
                    "skills": "./skills/",
                    "mcpServers": "./.mcp.json",
                    "apps": "./.app.json",
                    "interface": {
                        "displayName": "Goal Foundry",
                        "shortDescription": "Compile bounded goals.",
                        "longDescription": "Compile bounded goals from raw intent.",
                        "developerName": "Goal Foundry",
                        "category": "Productivity",
                        "capabilities": ["Read", "Write"],
                        "defaultPrompt": ["Use Goal Foundry."],
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
        source = self.root / "goal-foundry"
        out = self.root / "out"
        self.write_codex_plugin(source)

        report = plugin_port.convert_plugin(source, "claude", out, mode="strict", overwrite=False)

        manifest = read_json(out / ".claude-plugin" / "plugin.json")
        self.assertEqual(manifest["name"], "goal-foundry")
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

    def test_codex_to_claude_quarantines_root_claude_md(self) -> None:
        source = self.root / "goal-foundry"
        out = self.root / "out"
        self.write_codex_plugin(source)
        write(source / "CLAUDE.md", "# Goal Foundry\n\nRoot context that Claude plugins do not load.\n")

        report = plugin_port.convert_plugin(source, "claude", out, mode="strict", overwrite=False)

        self.assertFalse((out / "CLAUDE.md").exists())
        self.assertTrue((out / ".plugin-portability" / "preserved" / "CLAUDE.md").exists())
        self.assertTrue(any(item["kind"] == "claude-root-context" for item in report.preserved_only))
        validation = plugin_port.validate_plugin(out, "claude", external=False)
        self.assertTrue(validation.validation_summary["internal"]["passed"])

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
        source = self.root / "goal-foundry"
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


if __name__ == "__main__":
    unittest.main()
