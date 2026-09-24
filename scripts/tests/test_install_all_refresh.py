"""Exercise version-keyed client caches through the install-all entry point."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.install_all import hash_tree


REPO = Path(__file__).resolve().parents[2]
PLUGIN = "target@agent-tooling"

# Model the native consumer's consequential behavior: update ignores changed
# same-version bytes, install no-ops if registered, and uninstall keeps its cache.
FAKE_CLAUDE = r'''
import json, os, shutil, signal, sys
from pathlib import Path
root = Path(os.environ["INSTALL_FIXTURE"])
profile = Path(os.environ["CLAUDE_CONFIG_DIR"])
registry = profile / "plugins/installed_plugins.json"
marketplace = profile / "marketplace.json"
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as f:
    f.write(json.dumps(args) + "\n")
def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default
def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
state = read(registry, {"version": 2, "plugins": {}})
if args == ["plugin", "marketplace", "list", "--json"]:
    print(json.dumps(read(marketplace, [])))
elif args == ["plugin", "list", "--json"]:
    rows = [{"id": key, **entry} for key, entries in state["plugins"].items() for entry in entries]
    if os.environ.get("INSTALL_HIDE_ROOT") == "1":
        for row in rows:
            row.pop("installPath", None)
    print(json.dumps(rows))
elif args[:3] == ["plugin", "marketplace", "add"]:
    write(marketplace, [{"name": "agent-tooling", "source": str(root / "repo")}])
elif args[:3] == ["plugin", "marketplace", "remove"]:
    write(marketplace, [])
    state["plugins"] = {}
    write(registry, state)
elif args[:2] in (["plugin", "install"], ["plugin", "update"], ["plugin", "uninstall"]):
    scope = args[args.index("--scope") + 1]
    project = os.getcwd() if scope != "user" else None
    key = args[-1]
    entries = state["plugins"].get(key, [])
    current = next((e for e in entries if (e["scope"], e.get("projectPath")) == (scope, project)), None)
    settings_path = profile / "settings.json" if scope == "user" else (
        (Path.cwd() / ".claude/settings.json") if scope == "project" else root / "work/.claude/settings.local.json")
    settings = read(settings_path, {})
    enabled = settings.setdefault("enabledPlugins", {})
    if args[1] == "uninstall":
        if current is None:
            raise SystemExit("not installed at requested scope")
        state["plugins"][key] = [e for e in entries if e is not current]
        enabled.pop(key, None)
        if "--keep-data" not in args:
            shutil.rmtree(profile / "plugins/data/target-agent-tooling", ignore_errors=True)
        write(settings_path, settings)
        write(registry, state)
    else:
        source = root / "repo/plugins/target"
        version = read(source / ".claude-plugin/plugin.json", {})["version"]
        if current is not None and (args[1] == "install" or current["version"] == version):
            print("already installed / latest version")
            raise SystemExit(0)
        if os.environ.get("INSTALL_FAIL") == "1":
            raise SystemExit("injected install failure")
        cache = profile / "plugins/cache/agent-tooling/target" / version
        if cache.exists():
            shutil.rmtree(cache)
        shutil.copytree(source, cache)
        entry = {"scope": scope, "version": version, "installPath": str(cache)}
        if project:
            entry["projectPath"] = project
        state["plugins"][key] = [e for e in entries if e is not current] + [entry]
        enabled[key] = True
        write(settings_path, settings)
        write(registry, state)
        if os.environ.get("INSTALL_INTERRUPT") == "1":
            os.kill(os.getppid(), signal.SIGKILL)
else:
    raise SystemExit("unexpected arguments " + repr(args))
'''


class RefreshFixture:
    def __init__(self, root: Path, *, scope: str = "user", native: str | None = None):
        self.root, self.scope = root, scope
        self.source = root / "repo/plugins/target"
        self.profile = root / "profile"
        self.work = root / "work/nested"
        self.work.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(root / "work")], check=True)
        for host in ("codex", "claude"):
            folder = self.source / f".{host}-plugin"
            folder.mkdir(parents=True)
            (folder / "plugin.json").write_text(json.dumps({"name": "target", "version": "1.0.0", "description": "Installation fixture."}))
            catalog = root / "repo" / (".agents/plugins" if host == "codex" else ".claude-plugin")
            catalog.mkdir(parents=True)
            source = {"source": "local", "path": "./plugins/target"} if host == "codex" else "./plugins/target"
            (catalog / "marketplace.json").write_text(json.dumps({"name": "agent-tooling", "owner": {"name": "Fixture"}, "plugins": [{"name": "target", "source": source}]}))
        (self.source / "payload.txt").write_text("first\n")
        binary = root / "bin"
        binary.mkdir()
        if native:
            (binary / "claude").symlink_to(Path(native).resolve())
        else:
            cli = binary / "claude"
            cli.write_text(f"#!{sys.executable}\n" + FAKE_CLAUDE)
            cli.chmod(0o755)
        self.env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"],
                    "INSTALL_FIXTURE": str(root), "CLAUDE_CONFIG_DIR": str(self.profile),
                    "XDG_STATE_HOME": str(root / "state")}
        self.registry = self.profile / "plugins/installed_plugins.json"
        self.receipt = root / "state/agent-tooling/install-all.json"
        self.settings = self.profile / "settings.json" if scope == "user" else (
            self.work / ".claude/settings.json" if scope == "project" else root / "work/.claude/settings.local.json")
        self.data = self.profile / "plugins/data/target-agent-tooling/retained.txt"
        self.argv = [sys.executable, str(REPO / "scripts/install_all.py"), "--source", str(root / "repo"),
                     "--claude-only", "--claude-scope", scope]
        if native:
            observed = subprocess.run([str(binary / "claude"), "plugin", "list", "--json"],
                                      cwd=self.work, env=self.env, capture_output=True, text=True, timeout=60)
            if observed.returncode or json.loads(observed.stdout) != []:
                raise AssertionError("Native fixture profile is not empty; no mutation attempted")

    def run(self, *args: str, fail: bool = False, interrupt: bool = False,
            hide_root: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run([*self.argv, *args], cwd=self.work,
                              env={**self.env, "INSTALL_FAIL": "1" if fail else "0",
                                   "INSTALL_INTERRUPT": "1" if interrupt else "0",
                                   "INSTALL_HIDE_ROOT": "1" if hide_root else "0"},
                              capture_output=True, text=True, timeout=120)

    def cache(self) -> Path:
        entries = json.loads(self.registry.read_text())["plugins"][PLUGIN]
        project = str(self.work) if self.scope != "user" else None
        return Path(next(e["installPath"] for e in entries if (e["scope"], e.get("projectPath")) == (self.scope, project)))

    def activation(self, value: bool | None) -> None:
        data = json.loads(self.settings.read_text())
        if value is None:
            data["enabledPlugins"].pop(PLUGIN, None)
        else:
            data["enabledPlugins"][PLUGIN] = value
        self.settings.write_text(json.dumps(data))

    def mutations(self) -> list[str]:
        path = self.root / "calls.jsonl"
        calls = [json.loads(line) for line in path.read_text().splitlines()]
        return [args[1] for args in calls if args[:2] in (["plugin", "install"], ["plugin", "update"], ["plugin", "uninstall"])]

    def clear_calls(self) -> None:
        (self.root / "calls.jsonl").write_text("")


class ClaudeRefreshTests(unittest.TestCase):
    def success(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_same_version_changed_bytes_preserve_scopes_data_and_activation(self):
        for scope in ("user", "project", "local"):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as tmp:
                f = RefreshFixture(Path(tmp), scope=scope)
                self.success(f.run())
                f.activation(False)
                f.data.parent.mkdir(parents=True)
                f.data.write_text("reader notes")
                data = json.loads(f.registry.read_text())
                protected = {"scope": "project", "projectPath": str(f.root / "another-project"),
                             "version": "1.0.0", "installPath": str(f.cache()), "opaque": "retain"}
                data["plugins"][PLUGIN].append(protected)
                f.registry.write_text(json.dumps(data))
                (f.source / "payload.txt").unlink()
                (f.source / "replacement.txt").write_text("second\n")
                f.clear_calls()
                self.success(f.run())
                self.assertEqual(f.mutations(), ["uninstall", "install"])
                self.assertEqual(hash_tree(f.cache()), hash_tree(f.source))
                self.assertFalse((f.cache() / "payload.txt").exists())
                self.assertIn(protected, json.loads(f.registry.read_text())["plugins"][PLUGIN])
                self.assertEqual(f.data.read_text(), "reader notes")
                self.assertIs(json.loads(f.settings.read_text())["enabledPlugins"][PLUGIN], False)
                f.clear_calls()
                self.success(f.run())
                self.assertEqual(f.mutations(), [])

    def test_failed_install_preserves_receipt_data_and_disabled_choice_for_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = RefreshFixture(Path(tmp))
            self.success(f.run())
            receipt = f.receipt.read_bytes()
            f.activation(False)
            f.data.parent.mkdir(parents=True)
            f.data.write_text("keep me")
            (f.source / "payload.txt").write_text("second\n")
            failed = f.run(fail=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("rerun install-all", failed.stderr)
            self.assertEqual(f.receipt.read_bytes(), receipt)
            self.assertEqual(f.data.read_text(), "keep me")
            self.assertIs(json.loads(f.settings.read_text())["enabledPlugins"][PLUGIN], False)
            self.success(f.run())
            self.assertEqual(hash_tree(f.cache()), hash_tree(f.source))
            self.assertIs(json.loads(f.settings.read_text())["enabledPlugins"][PLUGIN], False)

    def test_force_reinstalls_and_preserves_absent_activation_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = RefreshFixture(Path(tmp))
            self.success(f.run())
            f.activation(None)
            f.clear_calls()
            self.success(f.run("--force"))
            self.assertEqual(f.mutations(), ["uninstall", "install"])
            self.assertNotIn(PLUGIN, json.loads(f.settings.read_text())["enabledPlugins"])

    def test_failed_reinstall_retry_preserves_inherited_activation(self):
        for scope in ("user", "project", "local"):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as tmp:
                f = RefreshFixture(Path(tmp), scope=scope)
                self.success(f.run())
                f.activation(None)
                if scope != "user":
                    (f.profile / "settings.json").write_text(json.dumps({"enabledPlugins": {PLUGIN: False}}))
                receipt = f.receipt.read_bytes()
                (f.source / "payload.txt").write_text("retry payload\n")
                failed = f.run(fail=True)
                self.assertNotEqual(failed.returncode, 0)
                self.assertEqual(f.receipt.read_bytes(), receipt)
                recovery = f.receipt.with_name("install-all-activation.json")
                self.assertIsNone(json.loads(recovery.read_text())["settings"][str(f.settings)][PLUGIN])
                self.success(f.run())
                self.assertEqual(hash_tree(f.cache()), hash_tree(f.source))
                self.assertNotIn(PLUGIN, json.loads(f.settings.read_text())["enabledPlugins"])
                self.assertFalse(recovery.exists())

    def test_interruption_recovers_activation_before_current_plugin_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = RefreshFixture(Path(tmp))
            self.success(f.run())
            f.activation(None)
            receipt = f.receipt.read_bytes()
            (f.source / "payload.txt").write_text("interrupted payload\n")
            interrupted = f.run(interrupt=True)
            self.assertNotEqual(interrupted.returncode, 0)
            self.assertEqual(f.receipt.read_bytes(), receipt)
            self.assertEqual(hash_tree(f.cache()), hash_tree(f.source))
            self.assertIs(json.loads(f.settings.read_text())["enabledPlugins"][PLUGIN], True)
            f.clear_calls()
            self.success(f.run())
            self.assertEqual(f.mutations(), [])
            self.assertEqual(hash_tree(f.cache()), hash_tree(f.source))
            self.assertNotIn(PLUGIN, json.loads(f.settings.read_text())["enabledPlugins"])
            self.assertFalse(f.receipt.with_name("install-all-activation.json").exists())

    def test_unverifiable_installed_path_cannot_write_a_success_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = RefreshFixture(Path(tmp))
            self.success(f.run())
            f.receipt.unlink()
            (f.source / "payload.txt").write_text("unverified content\n")
            result = f.run(hide_root=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("installed plugin path is unavailable", result.stderr)
            self.assertFalse(f.receipt.exists())

    def test_dry_run_preserves_old_payload_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = RefreshFixture(Path(tmp))
            self.success(f.run())
            before = (f.receipt.read_bytes(), hash_tree(f.cache()), f.settings.read_bytes())
            (f.source / "payload.txt").write_text("second\n")
            f.clear_calls()
            result = f.run("--dry-run")
            self.success(result)
            self.assertIn("--keep-data", result.stdout)
            self.assertEqual(f.mutations(), [])
            self.assertEqual(before, (f.receipt.read_bytes(), hash_tree(f.cache()), f.settings.read_bytes()))

    def test_version_upgrade_uses_native_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = RefreshFixture(Path(tmp))
            self.success(f.run())
            manifest = f.source / ".claude-plugin/plugin.json"
            data = json.loads(manifest.read_text())
            data["version"] = "1.0.1"
            manifest.write_text(json.dumps(data))
            f.clear_calls()
            self.success(f.run())
            self.assertEqual(f.mutations(), ["update"])
            self.assertEqual(hash_tree(f.cache()), hash_tree(f.source))

    def test_replacement_handles_registration_removed_with_marketplace(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = RefreshFixture(Path(tmp))
            self.success(f.run())
            (f.source / "payload.txt").write_text("replacement\n")
            f.clear_calls()
            self.success(f.run("--replace-marketplace"))
            self.assertEqual(f.mutations(), ["install"])
            self.assertEqual(hash_tree(f.cache()), hash_tree(f.source))

    def test_invalid_activation_prevents_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = RefreshFixture(Path(tmp))
            self.success(f.run())
            settings = json.loads(f.settings.read_text())
            settings["enabledPlugins"][PLUGIN] = None
            f.settings.write_text(json.dumps(settings))
            (f.source / "payload.txt").write_text("second\n")
            f.clear_calls()
            result = f.run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("activation values must be true or false", result.stderr)
            self.assertEqual(f.mutations(), [])


@unittest.skipUnless(os.environ.get("INSTALL_ALL_CLAUDE_BIN"), "set INSTALL_ALL_CLAUDE_BIN for an isolated native probe")
class NativeClaudeRefreshTests(unittest.TestCase):
    def test_changed_content_and_activation_survive_native_reinstall(self):
        for scope in ("user", "project", "local"):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory(prefix="install-native-") as tmp:
                f = RefreshFixture(Path(tmp), scope=scope, native=os.environ["INSTALL_ALL_CLAUDE_BIN"])
                first = f.run()
                self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
                f.activation(False)
                (f.source / "payload.txt").write_text("new native payload\n")
                changed = f.run()
                self.assertEqual(changed.returncode, 0, changed.stdout + changed.stderr)
                self.assertEqual(hash_tree(f.cache()), hash_tree(f.source))
                self.assertIs(json.loads(f.settings.read_text())["enabledPlugins"][PLUGIN], False)
                unchanged = f.run()
                self.assertEqual(unchanged.returncode, 0, unchanged.stdout + unchanged.stderr)
                self.assertIn("all selected plugins are current", unchanged.stderr)


if __name__ == "__main__":
    unittest.main()
