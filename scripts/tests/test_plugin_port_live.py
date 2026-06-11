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

    def _codex_binary_honoring_home(self, codex_home: Path) -> str | None:
        """A codex executable that respects CODEX_HOME=<temp dir>.

        Wrapper launchers may pin CODEX_HOME to the user's real home (observed
        live: temp-home isolation silently broken, with installs landing in the
        real cache). Such wrappers advertise the resolved home in a banner
        line, so reject any candidate that reports a different CODEX_HOME than
        the one we set.
        """
        candidates: list[str] = []
        if os.environ.get("PLUGIN_PORT_CODEX_BIN"):
            candidates.append(os.environ["PLUGIN_PORT_CODEX_BIN"])
        which = shutil.which("codex")
        if which:
            candidates.append(which)
        candidates.extend(p for p in ("/usr/bin/codex", "/usr/local/bin/codex") if Path(p).exists())
        env = {**os.environ, "CODEX_HOME": str(codex_home)}
        for cand in dict.fromkeys(candidates):
            try:
                probe = subprocess.run(
                    [cand, "plugin", "marketplace", "list"],
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                    timeout=60,
                )
            except OSError:
                continue
            out = probe.stdout + probe.stderr
            if "CODEX_HOME=" in out and f"CODEX_HOME={codex_home}" not in out:
                continue
            if probe.returncode == 0:
                return cand
        return None

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
        codex_home.mkdir(parents=True, exist_ok=True)
        codex = self._codex_binary_honoring_home(codex_home)
        if codex is None:
            self.skipTest(
                "no codex executable honors CODEX_HOME (wrapper pins the real home); "
                "set PLUGIN_PORT_CODEX_BIN to a vanilla binary")
        env = {**os.environ, "CODEX_HOME": str(codex_home)}

        # Register through the explicit add flow (the production path used by
        # scripts/install-all), not a hand-written config declaration.
        add_market = subprocess.run(
            [codex, "plugin", "marketplace", "add", str(marketplace)],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
        self.assertEqual(0, add_market.returncode, add_market.stdout + add_market.stderr)

        add = subprocess.run(
            [codex, "plugin", "add", "live-claude@plugin-port-live"],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
        self.assertEqual(0, add.returncode, add.stdout + add.stderr)

        prompt = subprocess.run(
            [codex, "debug", "prompt-input", "$live-claude:ping Confirm visibility without running tools."],
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
