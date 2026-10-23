from __future__ import annotations

import importlib.util
import json
import os
import selectors
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
import uuid


SCRIPTS = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("plugin_port", SCRIPTS / "plugin_port.py")
assert SPEC is not None and SPEC.loader is not None
plugin_port = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = plugin_port
SPEC.loader.exec_module(plugin_port)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@unittest.skipUnless(os.environ.get("PLUGIN_PORT_LIVE") == "1", "set PLUGIN_PORT_LIVE=1 for native plugin-agent lifecycle tests")
class PluginAgentsLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="plugin-agents-live-")
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir(mode=0o700)
        self.cwd = self.root / "project"
        self.cwd.mkdir()
        self.profile_marker = "profile-probe-" + uuid.uuid4().hex
        self.checked: dict[str, str] = {}
        self.env = {
            "HOME": str(self.home),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "CODEX_HOME": str(self.home / ".codex"),
            "CLAUDE_CONFIG_DIR": str(self.home / ".claude"),
            "DISABLE_AUTOUPDATER": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }

    def tearDown(self) -> None:
        try:
            if "claude" in self.checked:
                self.assertIn(self.profile_marker, self.run_cli(self.checked["claude"], "plugin", "list", "--json").stdout)
            if "codex" in self.checked:
                config = tomllib.loads((Path(self.env["CODEX_HOME"]) / "config.toml").read_text())
                self.assertEqual(self.profile_marker, config["model"])
        finally:
            self.temporary.cleanup()

    def run_cli(self, binary: str, *args: str, success: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run([binary, *args], cwd=self.cwd, env=self.env, text=True, capture_output=True, timeout=90)
        if success:
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result

    def binary(self, host: str) -> str:
        if os.environ.get(f"PLUGIN_PORT_{host.upper()}") != "1":
            self.skipTest(f"set PLUGIN_PORT_{host.upper()}=1")
        candidate = os.environ.get(f"PLUGIN_PORT_{host.upper()}_BIN") or shutil.which(host)
        if not candidate:
            self.skipTest(f"{host} executable unavailable")
        if host == "codex":
            home = Path(self.env["CODEX_HOME"])
            write(home / "config.toml", f'model = "{self.profile_marker}"\n')
            self.codex_profile_probe(candidate, home)
        else:
            home = Path(self.env["CLAUDE_CONFIG_DIR"])
            plugin = home / "plugins/cache" / self.profile_marker
            identifier = self.profile_marker + "@isolated-profile"
            write(plugin / ".claude-plugin/plugin.json", json.dumps({"name": self.profile_marker, "version": "1.0.0"}))
            write(home / "settings.json", json.dumps({"enabledPlugins": {identifier: True}}))
            write(home / "plugins/installed_plugins.json", json.dumps({"version": 2, "plugins": {identifier: [{"scope": "user", "installPath": str(plugin), "version": "1.0.0", "installedAt": "2026-01-01T00:00:00Z", "lastUpdated": "2026-01-01T00:00:00Z"}]}}))
            probe = self.run_cli(candidate, "plugin", "list", "--json", success=False)
            if probe.returncode or identifier not in probe.stdout or str(plugin) not in probe.stdout:
                self.skipTest("Claude did not expose the disposable profile marker; no native mutation was attempted")
        self.checked[host] = candidate
        return candidate

    def codex_profile_probe(self, binary: str, home: Path) -> None:
        with tempfile.TemporaryFile(mode="w+") as errors:
            process = subprocess.Popen([binary, "app-server", "--stdio"], cwd=self.cwd, env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True)
            assert process.stdin is not None and process.stdout is not None
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)

            def request(identifier: int, method: str, params: dict[str, object]) -> dict[str, object]:
                process.stdin.write(json.dumps({"id": identifier, "method": method, "params": params}) + "\n")
                process.stdin.flush()
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline and selector.select(max(0, deadline - time.monotonic())):
                    line = process.stdout.readline()
                    if not line:
                        break
                    message = json.loads(line)
                    if message.get("id") == identifier:
                        return message.get("result", {})
                return {}

            try:
                initialized = request(1, "initialize", {"clientInfo": {"name": "agent-profile-probe", "version": "1"}, "capabilities": {"experimentalApi": True, "explicitGatewayOauth": True}})
                process.stdin.write('{"method":"initialized","params":{}}\n')
                process.stdin.flush()
                result = request(2, "config/read", {"cwd": str(self.cwd), "includeLayers": True})
                if initialized.get("codexHome") != str(home) or result.get("config", {}).get("model") != self.profile_marker:
                    self.skipTest("Codex did not expose the disposable profile marker; no native mutation was attempted")
            finally:
                selector.close()
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                process.stdin.close()
                process.stdout.close()

    def fixture(self, host: str, revision: str = "one") -> Path:
        source = self.root / f"source-{host}-{revision}"
        write(source / f".{host}-plugin/plugin.json", json.dumps({"name": "bogus-agents", "version": "1.0.0" if revision == "one" else "1.0.1", "description": "Inert cross-host agent fixture."}))
        write(source / "skills/probe/SKILL.md", "---\nname: probe\ndescription: Inert fixture discovery marker.\n---\nDo nothing.\n")
        if host == "claude":
            write(source / "agents/reviewer.md", f"---\nname: reviewer\ndescription: Inert reviewer {revision}.\n---\nReport fixture revision {revision}.\n")
        else:
            write(source / ".codex/agents/reviewer.toml", f'name="reviewer"\ndescription="Inert reviewer {revision}."\ndeveloper_instructions="Report fixture revision {revision}."\n')
        return source

    def marketplace(self, host: str, source: Path) -> Path:
        root = self.root / f"{host}-marketplace"
        output = root / "plugins/bogus-agents"
        plugin_port.convert_plugin(source, host, output, mode="strict", overwrite=True)
        entry: dict[str, object] = {"name": "bogus-agents", "source": "./plugins/bogus-agents"}
        if host == "codex":
            entry.update(source={"source": "local", "path": "./plugins/bogus-agents"}, policy={"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, category="Testing")
        manifest = {"name": "bogus-agent-tests", "owner": {"name": "Fixture Tests"}, "plugins": [entry]}
        manifest_path = ".agents/plugins/marketplace.json" if host == "codex" else ".claude-plugin/marketplace.json"
        write(root / manifest_path, json.dumps(manifest))
        return root

    def test_codex_to_claude_native_agent_lifecycle(self) -> None:
        claude = self.binary("claude")
        marketplace = self.marketplace("claude", self.fixture("codex"))
        self.run_cli(claude, "plugin", "validate", str(marketplace / "plugins/bogus-agents"))
        self.run_cli(claude, "plugin", "marketplace", "add", str(marketplace))
        identifier = "bogus-agents@bogus-agent-tests"
        self.run_cli(claude, "plugin", "install", identifier)
        details = self.run_cli(claude, "plugin", "details", identifier)
        self.assertIn("reviewer", details.stdout)
        installed = self.run_cli(claude, "plugin", "list", "--json")
        self.assertIn(identifier, installed.stdout)
        self.marketplace("claude", self.fixture("codex", "two"))
        self.run_cli(claude, "plugin", "marketplace", "update", "bogus-agent-tests")
        self.run_cli(claude, "plugin", "update", identifier)
        self.assertIn("1.0.1", self.run_cli(claude, "plugin", "list", "--json").stdout)
        self.assertIn("reviewer", self.run_cli(claude, "plugin", "details", identifier).stdout)
        self.run_cli(claude, "plugin", "uninstall", identifier)
        self.assertNotIn(identifier, self.run_cli(claude, "plugin", "list", "--json").stdout)
        self.run_cli(claude, "plugin", "marketplace", "remove", "bogus-agent-tests")

    def test_claude_to_codex_package_and_projection_lifecycle(self) -> None:
        codex = self.binary("codex")
        marketplace = self.marketplace("codex", self.fixture("claude"))
        codex_home = Path(self.env["CODEX_HOME"])
        codex_home.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.run_cli(codex, "plugin", "marketplace", "add", str(marketplace))
        identifier = "bogus-agents@bogus-agent-tests"
        self.run_cli(codex, "plugin", "add", identifier)
        self.assertIn(identifier, self.run_cli(codex, "plugin", "list", "--json").stdout)
        package = marketplace / "plugins/bogus-agents"
        command = [str(SCRIPTS / "plugin_port.py"), "install-agents", str(package), "--owner", identifier, "--codex-home", str(codex_home)]
        self.run_cli(sys.executable, *command)
        projected = list((codex_home / "agents").glob("*.toml"))
        self.assertEqual(1, len(projected))
        self.assertEqual("bogus-agents:reviewer", tomllib.loads(projected[0].read_text())["name"])
        self.marketplace("codex", self.fixture("claude", "two"))
        self.run_cli(codex, "plugin", "remove", identifier)
        self.run_cli(codex, "plugin", "add", identifier)
        self.run_cli(sys.executable, *command)
        self.assertIn("revision two", tomllib.loads(projected[0].read_text())["developer_instructions"])
        self.run_cli(sys.executable, str(SCRIPTS / "plugin_port.py"), "install-agents", "--remove", "--owner", identifier, "--codex-home", str(codex_home))
        self.assertEqual([], list((codex_home / "agents").glob("*.toml")))
        self.run_cli(codex, "plugin", "remove", identifier)
        self.assertNotIn(identifier, self.run_cli(codex, "plugin", "list", "--json").stdout)
        self.run_cli(codex, "plugin", "marketplace", "remove", "bogus-agent-tests")

    def test_malformed_agent_is_rejected_before_registration(self) -> None:
        source = self.fixture("claude")
        write(source / "agents/reviewer.md", "---\nname: reviewer\ntools: [Read\n---\nDo nothing.\n")
        output = self.root / "converted"
        with self.assertRaises(plugin_port.PluginPortError):
            plugin_port.convert_plugin(source, "codex", output, mode="best-effort", overwrite=False)
        self.assertFalse(output.exists())

    def test_restricted_agent_failure_preserves_installed_native_state(self) -> None:
        codex = self.binary("codex")
        source = self.fixture("claude")
        marketplace = self.marketplace("codex", source)
        identifier = "bogus-agents@bogus-agent-tests"
        home = Path(self.env["CODEX_HOME"])
        self.run_cli(codex, "plugin", "marketplace", "add", str(marketplace))
        self.run_cli(codex, "plugin", "add", identifier)
        package = marketplace / "plugins/bogus-agents"
        base = [str(SCRIPTS / "plugin_port.py"), "install-agents"]
        options = ["--owner", identifier, "--codex-home", str(home)]
        self.run_cli(sys.executable, *base, str(package), *options)
        before_plugins = json.loads(self.run_cli(codex, "plugin", "list", "--json").stdout)
        before_agents = {path.name: path.read_bytes() for path in (home / "agents").iterdir() if path.is_file()}
        write(source / "agents/reviewer.md", "---\nname: reviewer\ndescription: Restricted agent.\ntools: Read, Grep\n---\nDo not run commands.\n")
        failed = self.run_cli(sys.executable, *base, str(source), *options, success=False)
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("cannot preserve", failed.stderr)
        self.assertEqual(before_plugins, json.loads(self.run_cli(codex, "plugin", "list", "--json").stdout))
        self.assertEqual(before_agents, {path.name: path.read_bytes() for path in (home / "agents").iterdir() if path.is_file()})
        self.run_cli(sys.executable, *base, "--remove", *options)
        self.run_cli(codex, "plugin", "remove", identifier)
        self.run_cli(codex, "plugin", "marketplace", "remove", "bogus-agent-tests")


if __name__ == "__main__":
    unittest.main()
