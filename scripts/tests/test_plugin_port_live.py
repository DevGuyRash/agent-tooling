from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
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


@unittest.skipUnless(os.environ.get("PLUGIN_PORT_LIVE") == "1", "set PLUGIN_PORT_LIVE=1 to run live plugin-port tests")
class PluginPortLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(prefix="plugin-port-live-")
        self.root = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def write_codex_plugin(self, root: Path) -> None:
        write(
            root / ".codex-plugin" / "plugin.json",
            json.dumps(
                {
                    "name": "live-codex",
                    "version": "1.0.0",
                    "description": "Live Codex fixture.",
                    "author": {"name": "Live Tests"},
                    "skills": "./skills/",
                    "interface": {
                        "displayName": "Live Codex",
                        "shortDescription": "Live Codex fixture.",
                        "longDescription": "Live Codex fixture for plugin-port acceptance.",
                        "developerName": "Live Tests",
                        "category": "Testing",
                        "capabilities": ["Read"],
                        "defaultPrompt": ["Use Live Codex."],
                    },
                },
                indent=2,
            )
            + "\n",
        )
        write(
            root / "skills" / "live-codex" / "SKILL.md",
            textwrap.dedent(
                """
                ---
                name: Live Codex
                description: Live Codex fixture skill.
                ---

                Confirm the live Codex fixture is visible.
                """
            ).lstrip(),
        )

    def write_claude_plugin(self, root: Path) -> None:
        write(
            root / ".claude-plugin" / "plugin.json",
            json.dumps(
                {
                    "name": "live-claude",
                    "version": "1.0.0",
                    "description": "Live Claude fixture.",
                    "author": {"name": "Live Tests"},
                },
                indent=2,
            )
            + "\n",
        )
        write(
            root / "commands" / "ping.md",
            textwrap.dedent(
                """
                ---
                description: Confirm the live Claude command is visible.
                ---

                Say that the live Claude command is visible.
                """
            ).lstrip(),
        )

    def test_claude_validator_accepts_converted_codex_plugin(self) -> None:
        if os.environ.get("PLUGIN_PORT_CLAUDE") != "1":
            self.skipTest("set PLUGIN_PORT_CLAUDE=1 to run Claude CLI checks")
        if shutil.which("claude") is None:
            self.skipTest("claude CLI is not installed")
        source = self.root / "live-codex"
        out = self.root / "live-claude-out"
        self.write_codex_plugin(source)

        plugin_port.convert_plugin(source, "claude", out, mode="strict", overwrite=False)
        proc = subprocess.run(
            ["claude", "plugin", "validate", "--strict", str(out)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )

        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

    def test_codex_temp_marketplace_accepts_converted_claude_plugin(self) -> None:
        if os.environ.get("PLUGIN_PORT_CODEX") != "1":
            self.skipTest("set PLUGIN_PORT_CODEX=1 to run Codex CLI checks")
        if shutil.which("codex") is None:
            self.skipTest("codex CLI is not installed")
        source = self.root / "live-claude"
        converted = self.root / "live-codex-out"
        marketplace = self.root / "marketplace"
        codex_home = self.root / "codex-home"
        self.write_claude_plugin(source)

        plugin_port.convert_plugin(source, "codex", converted, mode="strict", overwrite=False)
        shutil.copytree(converted, marketplace / "plugins" / "live-claude")
        write(
            marketplace / ".agents" / "plugins" / "marketplace.json",
            json.dumps(
                {
                    "name": "plugin-port-live",
                    "interface": {"displayName": "Plugin Port Live"},
                    "plugins": [
                        {
                            "name": "live-claude",
                            "source": {"source": "local", "path": "./plugins/live-claude"},
                            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                            "category": "Testing",
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
        )
        write(
            codex_home / "config.toml",
            "[marketplaces.plugin-port-live]\n"
            'source_type = "local"\n'
            f'source = "{marketplace.as_posix()}"\n',
        )
        env = {**os.environ, "CODEX_HOME": str(codex_home)}

        add = subprocess.run(
            ["codex", "plugin", "add", "live-claude@plugin-port-live"],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
        self.assertEqual(0, add.returncode, add.stdout + add.stderr)

        prompt = subprocess.run(
            ["codex", "debug", "prompt-input", "$live-claude:ping Confirm visibility without running tools."],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
        self.assertEqual(0, prompt.returncode, prompt.stdout + prompt.stderr)
        self.assertIn("plugin-port-live/live-claude/1.0.0/skills/ping/SKILL.md", prompt.stdout)


if __name__ == "__main__":
    unittest.main()
