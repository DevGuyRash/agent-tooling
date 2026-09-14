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
import uuid
from unittest import mock
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
                name: live-codex
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
        """Require positive model-visible evidence before any install mutation.

        A silent wrapper can return success while resetting CODEX_HOME. A unique
        skill marker and the intended profile path must appear in developer
        prompt input from an unrelated cwd. This verifies profile selection,
        not complete filesystem or ambient-context isolation; no model runs.
        """
        candidates: list[str] = []
        override = os.environ.get("PLUGIN_PORT_CODEX_BIN")
        if override:
            candidates.append(override)
        else:
            which = shutil.which("codex")
            if which:
                candidates.append(which)
            candidates.extend(p for p in ("/usr/bin/codex", "/usr/local/bin/codex") if Path(p).exists())
        env = {**os.environ, "CODEX_HOME": str(codex_home)}
        marker = "port-profile-" + uuid.uuid4().hex
        marker_dir = codex_home / "skills" / marker
        marker_dir.mkdir(parents=True, exist_ok=False)
        write(marker_dir / "SKILL.md", f"---\nname: {marker}\ndescription: Unique inert profile marker {marker}.\n---\n\n# Profile Marker\n")
        try:
            with tempfile.TemporaryDirectory(prefix="plugin-port-profile-cwd-") as working:
                for candidate in dict.fromkeys(candidates):
                    try:
                        probe = subprocess.run(
                            [candidate, "debug", "prompt-input", "Describe the available skill catalog without running tools."],
                            cwd=working, env=env, capture_output=True, text=True,
                            encoding="utf-8", check=False, timeout=45,
                        )
                        if probe.returncode != 0:
                            continue
                        messages = json.loads(probe.stdout)
                        developer_text = "\n".join(
                            part.get("text", "")
                            for message in messages if message.get("role") == "developer"
                            for part in message.get("content", [])
                            if part.get("type") == "input_text"
                        )
                    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, AttributeError):
                        continue
                    if marker in developer_text and str(codex_home / "skills") in developer_text:
                        return candidate
        finally:
            shutil.rmtree(marker_dir)
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
        if not os.environ.get("PLUGIN_PORT_CODEX_BIN") and shutil.which("codex") is None:
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
                "no codex executable positively exposed the isolated profile marker; "
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
        messages = json.loads(prompt.stdout)
        developer_text = "\n".join(
            part["text"]
            for message in messages
            if message.get("role") == "developer"
            for part in message.get("content", [])
            if part.get("type") == "input_text" and isinstance(part.get("text"), str)
        )
        expected_skill_root = (
            codex_home
            / "plugins"
            / "cache"
            / "plugin-port-live"
            / "live-claude"
            / "1.0.0"
            / "skills"
        )
        root_line = next(
            (
                line
                for line in developer_text.splitlines()
                if f"`{expected_skill_root}`" in line
            ),
            None,
        )
        self.assertIsNotNone(root_line, developer_text)
        assert root_line is not None
        skill_root_alias = root_line.split("`")[1]
        self.assertIn(
            f"- live-claude:ping: Confirm the live Claude command is visible. "
            f"(file: {skill_root_alias}/ping/SKILL.md)",
            developer_text,
        )



class ProfileSelectionTests(unittest.TestCase):
    """The safety precondition runs in ordinary tests, without native CLIs."""

    def probe_with(self, response):
        helper = PluginPortLiveTests()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "profile"
            with mock.patch.dict(os.environ, {"PLUGIN_PORT_CODEX_BIN": "/fake/codex"}):
                with mock.patch.object(subprocess, "run", side_effect=response) as run:
                    selected = helper._codex_binary_honoring_home(home)
            self.assertEqual(list((home / "skills").iterdir()), [])
            self.assertTrue(all(call.args[0][1:3] == ["debug", "prompt-input"] for call in run.call_args_list))
            return selected

    def test_silent_home_reset_is_rejected_despite_success(self):
        def silent(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, json.dumps([{
                "role": "developer", "content": [{"type": "input_text", "text": "Real home skills"}]
            }]), "")
        self.assertIsNone(self.probe_with(silent))

    def test_marker_in_user_echo_does_not_establish_profile(self):
        def echoed(argv, **kwargs):
            profile = Path(kwargs["env"]["CODEX_HOME"])
            marker = next((profile / "skills").iterdir()).name
            return subprocess.CompletedProcess(argv, 0, json.dumps([{
                "role": "user", "content": [{"type": "input_text", "text": f"{marker} {profile / 'skills'}"}]
            }]), "")
        self.assertIsNone(self.probe_with(echoed))

    def test_positive_marker_and_profile_are_accepted(self):
        def rendered(argv, **kwargs):
            profile = Path(kwargs["env"]["CODEX_HOME"])
            marker = next((profile / "skills").iterdir()).name
            self.assertNotEqual(Path(kwargs["cwd"]), profile)
            return subprocess.CompletedProcess(argv, 0, json.dumps([{
                "role": "developer", "content": [{"type": "input_text", "text": f"{marker} {profile / 'skills'}"}]
            }]), "")
        self.assertEqual(self.probe_with(rendered), "/fake/codex")

    def test_unusable_renderer_is_rejected_and_marker_cleaned(self):
        def failed(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 45)
        self.assertIsNone(self.probe_with(failed))

if __name__ == "__main__":
    unittest.main()
