from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import unittest.mock
from pathlib import Path

from scripts import agent_plugins

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE = REPO_ROOT / "scripts" / "agent_plugins.py"
GIT = "/usr/bin/git" if Path("/usr/bin/git").is_file() else "git"

# A fake native client. Its whole state is one JSON file; every call is logged.
FAKE_CLI = r'''#!{python}
import json, os, sys
from pathlib import Path
client = {client!r}
state_path = Path(os.environ["FAKE_STATE"]) / f"{{client}}.json"
state = json.loads(state_path.read_text())
args = sys.argv[1:]
with open(Path(os.environ["FAKE_STATE"]) / "calls.jsonl", "a") as log:
    log.write(json.dumps([client, *args]) + "\n")
def save():
    state_path.write_text(json.dumps(state))
def fail_if(key):
    if key in state.get("fail", {{}}):
        sys.stderr.write(state["fail"][key] + "\n")
        sys.exit(1)
def entry(plugin, data):
    name, market = plugin.split("@")
    if client == "codex":
        return {{"pluginId": plugin, "name": name, "marketplaceName": market, "version": data["version"], "enabled": data["enabled"], "installed": True,
                **({{"installPath": data["root"]}} if data.get("root") else {{}})}}
    return {{"id": plugin, "version": data["version"], "scope": data.get("scope", "user"), "enabled": data["enabled"]}}
def latest(plugin):
    name, market = plugin.split("@")
    return state["catalog"][market][name]
if args[:3] == ["plugin", "marketplace", "list"]:
    if client == "codex":
        print(json.dumps({{"marketplaces": [{{"name": n, "marketplaceSource": {{"source": s}}}} for n, s in state["marketplaces"].items()]}}))
    else:
        print(json.dumps([{{"name": n, "repo": s}} for n, s in state["marketplaces"].items()]))
elif args[:3] == ["plugin", "marketplace", "add"]:
    source = args[3].split("@")[0] if client == "claude" else args[3]
    state["marketplaces"][state["register_as"][source]] = source
    save()
    print("{{}}" if "--json" in args else "added")
elif args[:3] in (["plugin", "marketplace", "upgrade"], ["plugin", "marketplace", "update"]):
    fail_if("refresh:" + args[3])
    print("{{}}" if "--json" in args else "updated")
elif args[:2] == ["plugin", "list"] and "--available" in args:
    markets = [args[args.index("--marketplace") + 1]] if "--marketplace" in args else list(state["catalog"])
    available = [{{"pluginId": f"{{n}}@{{m}}", "marketplaceName": m}} for m in markets if m in state["marketplaces"] for n in state["catalog"].get(m, {{}})]
    print(json.dumps({{"installed": [], "available": available}}))
elif args[:2] == ["plugin", "list"]:
    installed = [entry(p, d) for p, d in sorted(state["installed"].items())]
    print(json.dumps({{"installed": installed}} if client == "codex" else installed))
elif client == "codex" and args[:2] == ["plugin", "add"]:
    plugin = args[2] + "@" + args[args.index("--marketplace") + 1]
    fail_if("install:" + plugin)
    state["installed"][plugin] = {{"version": latest(plugin), "enabled": True}}
    save()
    print("{{}}")
elif client == "claude" and args[:2] == ["plugin", "install"]:
    fail_if("install:" + args[2])
    state["installed"][args[2]] = {{"version": latest(args[2]), "enabled": True, "scope": args[args.index("--scope") + 1]}}
    save()
elif client == "claude" and args[:2] == ["plugin", "update"]:
    fail_if("update:" + args[2])
    data = state["installed"][args[2]]
    data["version"] = latest(args[2])
    if state.get("update_enables"):
        data["enabled"] = True
    save()
else:
    sys.stderr.write("unexpected fake call: " + " ".join(args) + "\n")
    sys.exit(64)
'''


def manifest(**clients: dict) -> dict:
    return {
        "schema_version": 5,
        "resource": "agent-plugins",
        "policies": {"enabled_unmanaged_plugins": "preserve", "externally_managed_plugins": [],
                     "externally_managed_marketplaces": {"codex": ["bundled"]}, "project_plugin_agents": False},
        "marketplaces": [{"id": "tools", "provenance": {"kind": "owner", "evidence_url": "https://github.com/owner/tools"}, "clients": clients}],
    }


CODEX_SPEC = {"marketplace": "tools", "platforms": ["linux", "windows", "darwin"],
              "registration": {"mode": "source", "source": "https://github.com/owner/tools.git", "ref": "main"},
              "selection": {"mode": "include", "plugins": ["alpha", {"name": "mobile", "profiles": ["mobile_dev"]}]}}
CLAUDE_SPEC = {"marketplace": "tools", "platforms": ["linux", "windows", "darwin"], "scope": "user",
               "registration": {"mode": "source", "source": "owner/tools", "ref": "main"},
               "selection": {"mode": "include", "plugins": ["alpha"], "available_plugins": ["beta"]}}


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.home = root / "home"
        self.bin = root / "bin"
        self.state = root / "state"
        for path in (self.home, self.bin, self.state):
            path.mkdir()
        for client in ("codex", "claude"):
            script = self.bin / client
            script.write_text(FAKE_CLI.format(python=sys.executable, client=client))
            script.chmod(0o755)
            self.write_state(client, {"marketplaces": {}, "installed": {}, "register_as": {},
                                      "catalog": {"tools": {"alpha": "1.0.0", "beta": "1.0.0", "mobile": "1.0.0", "gamma": "1.0.0"}}})
        self.manifest = root / "manifest.json"

    def write_state(self, client: str, value: dict) -> None:
        (self.state / f"{client}.json").write_text(json.dumps(value))

    def read_state(self, client: str) -> dict:
        return json.loads((self.state / f"{client}.json").read_text())

    def update_state(self, client: str, **changes) -> None:
        self.write_state(client, {**self.read_state(client), **changes})

    def calls(self) -> list[list[str]]:
        path = self.state / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def run(self, *arguments: str, manifest_value: dict | None = None) -> subprocess.CompletedProcess[str]:
        self.manifest.write_text(json.dumps(manifest_value or manifest(codex=CODEX_SPEC, **{"claude-code": CLAUDE_SPEC})))
        (self.state / "calls.jsonl").unlink(missing_ok=True)
        environment = {"PATH": str(self.bin), "HOME": str(self.home), "XDG_STATE_HOME": str(self.root / "xdg-state"),
                       "XDG_CONFIG_HOME": str(self.root / "xdg-config"), "CODEX_HOME": str(self.home / ".codex"), "FAKE_STATE": str(self.state)}
        return subprocess.run([sys.executable, "-B", str(ENGINE), "--manifest", str(self.manifest), "--public-git-command", GIT,
                               "--home", str(self.home), *arguments], env=environment, capture_output=True, text=True, timeout=120, check=False)


class NativeClientTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.f = Fixture(Path(temporary.name))
        for client, source in (("codex", "https://github.com/owner/tools.git"), ("claude", "owner/tools")):
            self.f.update_state(client, register_as={source: "tools"})

    def report(self, result: subprocess.CompletedProcess[str]) -> dict:
        self.assertTrue(result.stdout, result.stderr)
        return json.loads(result.stdout)

    def test_setup_registers_installs_required_selections_and_verifies(self) -> None:
        result = self.f.run("--client", "codex", "--client", "claude-code", "--format", "json", "--profile", "mobile_dev")
        report = self.report(result)
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual(report["failures"], [])
        self.assertTrue(report["changed"])
        self.assertEqual(sorted(self.f.read_state("codex")["installed"]), ["alpha@tools", "mobile@tools"])
        # Available-only plugins are listed, never installed.
        self.assertEqual(sorted(self.f.read_state("claude")["installed"]), ["alpha@tools"])
        self.assertIn(["codex", "plugin", "marketplace", "add", "https://github.com/owner/tools.git", "--ref", "main", "--json"], self.f.calls())
        self.assertIn(["claude", "plugin", "marketplace", "add", "owner/tools@main", "--scope", "user"], self.f.calls())
        self.assertIn(["claude", "plugin", "install", "alpha@tools", "--scope", "user"], self.f.calls())
        verify = self.f.run("--client", "codex", "--client", "claude-code", "--verify-only", "--profile", "mobile_dev")
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)

    def test_profile_gated_selection_is_not_required_without_its_profile(self) -> None:
        result = self.f.run("--client", "codex", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(sorted(self.f.read_state("codex")["installed"]), ["alpha@tools"])

    def test_dry_run_reports_without_mutating(self) -> None:
        result = self.f.run("--client", "claude-code", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("claude-code would-add-marketplace tools", result.stdout)
        self.assertEqual(self.f.read_state("claude")["marketplaces"], {})
        self.assertFalse(any(call[1:3] in (["plugin", "install"], ["marketplace", "add"]) for call in self.f.calls()))

    def test_source_mismatch_fails_before_any_mutation(self) -> None:
        self.f.update_state("claude", marketplaces={"tools": "someone-else/tools"})
        result = self.f.run("--client", "claude-code", "--format", "json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("differs from the selection", self.report(result)["failures"][0])
        self.assertFalse(any(call[1:3] == ["plugin", "install"] for call in self.f.calls()))

    def test_native_failure_detail_is_reported(self) -> None:
        self.f.update_state("claude", fail={"install:alpha@tools": "Could not download x@1 from the npm registry: code EALLOWREMOTE"})
        result = self.f.run("--client", "claude-code", "--format", "json")
        self.assertEqual(result.returncode, 1)
        failure = self.report(result)["failures"][0]
        self.assertIn("install-plugin alpha@tools failed", failure)
        self.assertIn("EALLOWREMOTE", failure)

    def test_update_refreshes_and_updates_installed_plugins_without_installing_new_ones(self) -> None:
        self.f.update_state("claude", marketplaces={"tools": "owner/tools"},
                            installed={"alpha@tools": {"version": "0.9.0", "enabled": True}, "gamma@tools": {"version": "0.1.0", "enabled": False}},
                            catalog={"tools": {"alpha": "1.0.0", "gamma": "2.0.0", "beta": "1.0.0"}})
        result = self.f.run("--client", "claude-code", "--update", "--result-protocol")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        installed = self.f.read_state("claude")["installed"]
        self.assertEqual(sorted(installed), ["alpha@tools", "gamma@tools"])  # manual installations update too; nothing new
        self.assertEqual((installed["gamma@tools"]["version"], installed["gamma@tools"]["enabled"]), ("2.0.0", False))
        lines = result.stdout.splitlines()
        self.assertIn('UPDATE_ALL_ITEM {"subject":"claude-code / alpha@tools","action":"update-plugin","outcome":"passed","before":null,"after":null}', lines)
        self.assertEqual(lines[-1], 'UPDATE_ALL_RESULT {"outcome":"updated","detail":"3 native plugin update command(s) completed; 0 item(s) deferred; 0 failure(s)"}')

    def test_update_that_enables_a_disabled_plugin_is_a_failure(self) -> None:
        self.f.update_state("claude", marketplaces={"tools": "owner/tools"}, update_enables=True,
                            installed={"gamma@tools": {"version": "0.1.0", "enabled": False}})
        result = self.f.run("--client", "claude-code", "--update", "--format", "json")
        self.assertEqual(result.returncode, 1)
        report = self.report(result)
        self.assertIn("enabled a disabled plugin", report["failures"][0])
        self.assertTrue(report["changed"], "observed partial progress stays reported")

    def test_codex_update_refreshes_git_marketplaces_and_defers_disabled_local_plugins(self) -> None:
        self.f.update_state("codex", marketplaces={"tools": "https://github.com/owner/tools.git", "local": "/srv/local-market"},
                            installed={"alpha@tools": {"version": "1.0.0", "enabled": True}, "own@local": {"version": "1.0.0", "enabled": False},
                                       "app@bundled": {"version": "1.0.0", "enabled": True}})
        result = self.f.run("--client", "codex", "--update", "--format", "json")
        report = self.report(result)
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual([(a["operation"], a["resource"]) for a in report["actions"]], [("refresh-marketplace", "tools")])
        self.assertEqual(report["deferred"], ["own@local: disabled; the native local add command would enable it"])
        self.assertFalse(any("bundled" in " ".join(call) for call in self.f.calls()), "app-owned marketplaces stay untouched")

    def test_missing_client_is_deferred_only_when_requested(self) -> None:
        (self.f.bin / "claude").unlink()
        failed = self.f.run("--client", "claude-code", "--format", "json")
        self.assertEqual((failed.returncode, self.report(failed)["failures"]), (1, ["claude-code: missing client"]))
        deferred = self.f.run("--client", "claude-code", "--format", "json", "--defer-missing-client")
        self.assertEqual((deferred.returncode, self.report(deferred)["deferred"]), (0, ["claude-code: missing client"]))

    def test_codex_agents_of_selected_plugins_are_projected_and_retired(self) -> None:
        codex_home = self.f.home / ".codex"
        payload = codex_home / "plugins/cache/tools/alpha/1.0.0"
        (payload / ".codex-plugin").mkdir(parents=True)
        (payload / ".codex-plugin/plugin.json").write_text(json.dumps({"name": "alpha", "version": "1.0.0"}))
        (payload / ".codex/agents").mkdir(parents=True)
        (payload / ".codex/agents/reviewer.toml").write_text('name = "reviewer"\ndescription = "Review."\ndeveloper_instructions = "Review changes."\n')
        self.f.update_state("codex", marketplaces={"tools": "https://github.com/owner/tools.git"},
                            installed={"alpha@tools": {"version": "1.0.0", "enabled": True, "root": str(payload)}})
        value = manifest(codex=CODEX_SPEC)
        value["policies"]["project_plugin_agents"] = True
        result = self.f.run("--client", "codex", "--format", "json", manifest_value=value)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        agents = sorted((codex_home / "agents").glob("*.toml"))
        self.assertEqual(len(agents), 1)
        self.assertIn("reviewer", agents[0].read_text())
        self.assertEqual(json.loads((codex_home / agent_plugins.AGENT_INTENT).read_text())["owners"], ["alpha@tools"])
        # Disabling the plugin retires its projected agents and the intent.
        self.f.update_state("codex", installed={"alpha@tools": {"version": "1.0.0", "enabled": False, "root": str(payload)}})
        result = self.f.run("--client", "codex", "--format", "json", manifest_value=value)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(list((codex_home / "agents").glob("*.toml")), [])
        self.assertEqual(json.loads((codex_home / agent_plugins.AGENT_INTENT).read_text())["owners"], [])


def git(*arguments: str, cwd: Path) -> str:
    environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run([GIT, *arguments], cwd=cwd, env=environment, capture_output=True, text=True, check=True).stdout.strip()


class CursorTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.f = Fixture(Path(temporary.name))
        (self.f.bin / "cursor-agent").write_text("#!/bin/sh\nexit 0\n")
        (self.f.bin / "cursor-agent").chmod(0o755)
        self.market = self.f.root / "market"
        (self.market / ".cursor-plugin").mkdir(parents=True)
        (self.market / ".cursor-plugin/marketplace.json").write_text(json.dumps({"name": "tools", "plugins": [
            {"name": "alpha", "source": "plugins/alpha"}, {"name": "never", "source": "plugins/never", "minClientVersions": {"cursor": "never"}}]}))
        for name in ("alpha", "never"):
            (self.market / f"plugins/{name}/.cursor-plugin").mkdir(parents=True)
            (self.market / f"plugins/{name}/.cursor-plugin/plugin.json").write_text(json.dumps({"name": name, "version": "1.0.0"}))
        (self.market / "plugins/alpha/run.sh").write_text("#!/bin/sh\n")
        (self.market / "plugins/alpha/run.sh").chmod(0o755)
        git("init", "--quiet", "--initial-branch", "main", cwd=self.market)
        self.commit("initial")
        self.value = manifest(cursor={"marketplace": "tools", "platforms": ["linux", "darwin", "windows"],
                                      "registration": {"mode": "source", "source": str(self.market), "ref": "main"},
                                      "selection": {"mode": "all"}})
        self.value["marketplaces"][0]["provenance"]["evidence_url"] = "https://example.invalid/tools"
        self.value["marketplaces"][0]["provenance"]["kind"] = "platform-official"  # a local source has no provenance repository
        self.local = self.f.home / ".cursor/plugins/local"

    def commit(self, message: str) -> str:
        git("add", "-A", cwd=self.market)
        git("commit", "--quiet", "-m", message, cwd=self.market)
        return git("rev-parse", "HEAD", cwd=self.market)

    def run_cursor(self, *arguments: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        result = self.f.run("--client", "cursor", "--format", "json", *arguments, manifest_value=self.value)
        return result, json.loads(result.stdout)

    def ledger(self) -> dict:
        return json.loads((self.f.home / ".cursor/plugins" / agent_plugins.CURSOR_LEDGER).read_text())

    def test_setup_copies_compatible_plugins_with_receipts_and_update_follows_upstream(self) -> None:
        result, report = self.run_cursor()
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual(sorted(path.name for path in self.local.iterdir()), ["alpha"])
        receipt = self.ledger()["plugins"]["alpha"]
        self.assertEqual(receipt["commit"], git("rev-parse", "HEAD", cwd=self.market))
        self.assertEqual(receipt["digest"], agent_plugins.tree_digest(self.local / "alpha"))
        self.assertTrue(os.access(self.local / "alpha/run.sh", os.X_OK))
        # Upstream changes replace a clean copy.
        (self.market / "plugins/alpha/README.md").write_text("new\n")
        head = self.commit("readme")
        result, report = self.run_cursor("--update")
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual([(a["operation"], a["applied"]) for a in report["actions"]], [("update-plugin", True)])
        self.assertEqual((self.local / "alpha/README.md").read_text(), "new\n")
        self.assertEqual(self.ledger()["plugins"]["alpha"]["commit"], head)
        # Local edits block the next upstream change and are preserved.
        (self.local / "alpha/run.sh").write_text("#!/bin/sh\necho mine\n")
        (self.market / "plugins/alpha/README.md").write_text("newer\n")
        self.commit("readme again")
        result, report = self.run_cursor("--update")
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual(report["actions"], [])
        self.assertIn("alpha@tools: local edits since installation block the available update; they are preserved", report["deferred"])
        self.assertEqual((self.local / "alpha/run.sh").read_text(), "#!/bin/sh\necho mine\n")
        self.assertFalse(any(path.name.startswith(agent_plugins.CURSOR_STAGE) for path in (self.f.home / ".cursor/plugins").iterdir()))

    def test_unmanaged_directory_is_preserved(self) -> None:
        (self.local / "alpha").mkdir(parents=True)
        (self.local / "alpha/mine.txt").write_text("keep\n")
        result, report = self.run_cursor()
        self.assertEqual(result.returncode, 0, report)
        self.assertIn("alpha@tools: an unmanaged directory occupies plugins/local/alpha; it is preserved", report["deferred"])
        self.assertEqual(sorted(path.name for path in (self.local / "alpha").iterdir()), ["mine.txt"])


class UnitTests(unittest.TestCase):
    def test_tree_digest_follows_the_receipt_format(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "b").mkdir()
            (root / "b/x").write_text("hi")
            (root / "a.sh").write_text("run")
            (root / "a.sh").chmod(0o755)
            expected = hashlib.sha256(b"f\0a.sh\0x\0" + b"3\0run" + b"d\0b\0" + b"f\0b/x\0-\0" + b"2\0hi").hexdigest()
            self.assertEqual(agent_plugins.tree_digest(root), "sha256:" + expected)
            (root / "link").symlink_to("a.sh")
            with self.assertRaises(agent_plugins.PluginError):
                agent_plugins.tree_digest(root)

    def test_manifest_rejects_sources_outside_their_provenance_and_external_overlaps(self) -> None:
        value = manifest(codex=CODEX_SPEC)
        value["marketplaces"][0]["clients"]["codex"] = {**CODEX_SPEC, "registration": {"mode": "source", "source": "https://github.com/other/tools.git"}}
        with self.assertRaisesRegex(agent_plugins.PluginError, "provenance"):
            agent_plugins.parse_manifest(json.dumps(value).encode())
        value = manifest(codex=CODEX_SPEC)
        value["policies"]["externally_managed_plugins"] = ["alpha@tools"]
        with self.assertRaisesRegex(agent_plugins.PluginError, "external plugin"):
            agent_plugins.parse_manifest(json.dumps(value).encode())

    def test_npm_shim_rewrites_only_the_registry_tarball_of_the_resolved_package(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            real = Path(raw) / "real"
            real.mkdir()
            (real / "npm").write_text(textwrap.dedent(f"""\
                #!{sys.executable}
                import sys
                if sys.argv[1:] == ["config", "get", "registry"]:
                    print("https://registry.npmjs.org/")
                else:
                    print(" ".join(sys.argv[1:]))
                """))
            (real / "npm").chmod(0o755)
            with agent_plugins.claude_npm_environment({"PATH": str(real)}) as environment:
                # The shim directory leads PATH twice to prove it never resolves itself.
                shim_dir = environment["PATH"].split(os.pathsep)[0]
                environment = {**environment, "PATH": os.pathsep.join([shim_dir, environment["PATH"]])}

                def npm(*arguments: str) -> str:
                    return subprocess.run(["npm", *arguments], env=environment, capture_output=True, text=True, timeout=30, check=True).stdout.strip()

                self.assertEqual(npm("pack", "--ignore-scripts", "--", "https://registry.npmjs.org/rea-agents/-/rea-agents-6.10.1.tgz"),
                                 "pack --ignore-scripts -- rea-agents@6.10.1")
                self.assertEqual(npm("pack", "--", "https://registry.npmjs.org/@scope/tool/-/tool-1.2.3-beta.1.tgz"), "pack -- @scope/tool@1.2.3-beta.1")
                for untouched in ("https://example.com/rea-agents/-/rea-agents-6.10.1.tgz", "https://registry.npmjs.org/a/-/b-1.0.0.tgz"):
                    self.assertEqual(npm("pack", "--", untouched), f"pack -- {untouched}")
                self.assertEqual(npm("view", "--json", "--", "rea-agents@6.10.1"), "view --json -- rea-agents@6.10.1")


class FailureContainmentTests(unittest.TestCase):
    def test_interrupted_fallback_replacement_restores_the_previous_copy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / ".cursor"
            stage = home / "plugins" / (agent_plugins.CURSOR_STAGE + "x")
            (stage / ("alpha" + agent_plugins.DISPLACED)).mkdir(parents=True)
            (stage / ("alpha" + agent_plugins.DISPLACED) / "kept.txt").write_text("old\n")
            (home / "plugins/local").mkdir()
            agent_plugins.CursorClient(home, None, {}, lambda: None).clear_residue()
            self.assertEqual((home / "plugins/local/alpha/kept.txt").read_text(), "old\n")
            self.assertFalse(stage.exists())

    def test_failed_second_move_puts_the_previous_copy_back(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "target").mkdir()
            (root / "target/old").write_text("old")
            missing = root / "absent-staged"
            with unittest.mock.patch.object(agent_plugins, "_renameat2", return_value=False):
                with self.assertRaises(OSError):
                    agent_plugins.exchange(missing, root / "target", root / "displaced")
            self.assertEqual((root / "target/old").read_text(), "old")

    def test_exchange_swaps_both_trees(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for name in ("staged", "target"):
                (root / name).mkdir()
                (root / name / "who").write_text(name)
            displaced = agent_plugins.exchange(root / "staged", root / "target", root / "displaced")
            self.assertEqual((root / "target/who").read_text(), "staged")
            self.assertEqual((displaced / "who").read_text(), "target")

    def test_timeout_ends_the_whole_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pid_file = Path(raw) / "child"
            script = f"sleep 30 & echo $! > {pid_file}; wait"
            with self.assertRaisesRegex(agent_plugins.PluginError, "timed out"):
                agent_plugins.bounded_run(["/bin/sh", "-c", script], environment=dict(os.environ), cwd=None, timeout=1, stop=lambda: None)
            child = int(pid_file.read_text())
            for _ in range(50):
                try:
                    os.kill(child, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.1)
            else:
                self.fail("the grandchild survived the timeout")

    def test_cancellation_between_clients_keeps_what_already_ran(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fixture = Fixture(root)
            fixture.manifest.write_text(json.dumps(manifest(codex=CODEX_SPEC, **{"claude-code": CLAUDE_SPEC})))
            args = agent_plugins.parse_args(["--manifest", str(fixture.manifest), "--home", str(fixture.home), "--dry-run",
                                             "--client", "codex", "--client", "claude-code"])
            calls = []
            done = agent_plugins.Report(actions=[agent_plugins.Action("codex", "install-plugin", "alpha@tools", True)], changed=True)
            with unittest.mock.patch.object(agent_plugins, "run_native", side_effect=lambda *a: calls.append(a) or done), \
                    unittest.mock.patch.object(agent_plugins.shutil, "which", return_value="/bin/true"), \
                    unittest.mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(root / "state-home")}):
                report = agent_plugins.execute(args, lambda: bool(calls))
            self.assertEqual(len(calls), 1)
            self.assertEqual([a.resource for a in report.actions], ["alpha@tools"])
            self.assertTrue(report.changed)
            self.assertEqual(report.failures, ["plugin task cancelled"])

    def test_failure_text_keeps_the_cause_without_credentials(self) -> None:
        completed = subprocess.CompletedProcess([], 1, "", "fatal: https://user:ghp_abcdefghijklmnopqrstuvwxyz@github.com/x.git: code EALLOWREMOTE\n")
        detail = agent_plugins.failure_detail(completed)
        self.assertIn("EALLOWREMOTE", detail)
        self.assertNotIn("ghp_", detail)
        self.assertNotIn("user:", detail)

    def test_native_clients_keep_the_caller_environment_unless_a_public_git_is_selected(self) -> None:
        with unittest.mock.patch.dict(os.environ, {"GIT_DIR": "/x", "GH_TOKEN": "t", "SSH_AUTH_SOCK": "/agent"}):
            plain = agent_plugins.native_environment(None, Path("/home/u"))
            self.assertEqual((plain["GIT_DIR"], plain["GH_TOKEN"], plain["HOME"]), ("/x", "t", "/home/u"))
            routed = agent_plugins.native_environment(Path("/opt/git/bin/git"), Path("/home/u"))
            self.assertNotIn("GIT_DIR", routed)
            self.assertNotIn("GH_TOKEN", routed)
            self.assertEqual(routed["SSH_AUTH_SOCK"], "/agent")
            self.assertTrue(routed["PATH"].startswith("/opt/git/bin" + os.pathsep))
            self.assertEqual((routed["GIT_CONFIG_KEY_0"], routed["GIT_CONFIG_VALUE_0"]), ("credential.helper", ""))

if __name__ == "__main__":
    unittest.main()
