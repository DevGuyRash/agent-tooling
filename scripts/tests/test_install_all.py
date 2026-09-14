from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts.install_all import (
    HostState,
    Identity,
    InstallError,
    InstalledArtifact,
    hash_tree,
    parse_args,
    plan_host,
    preserve_claude_registry,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_ALL = REPO_ROOT / "scripts" / "install-all"
CODEX_MARKETPLACE = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
CLAUDE_MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def write_fake_cli(path: Path, command_name: str) -> None:
    path.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json
            import os
            import subprocess
            import sys
            from pathlib import Path

            state_path = Path(__file__).with_name(".{command_name}.state.json")
            if state_path.exists():
                state = json.loads(state_path.read_text(encoding="utf-8"))
            else:
                configured = json.loads(os.environ.get("AGENT_TOOLING_FAKE_MARKETPLACES", "{{}}"))
                installed = json.loads(os.environ.get("AGENT_TOOLING_FAKE_INSTALLED", "{{}}"))
                state = {{"marketplaces": [item if isinstance(item, dict) else {{"name": item}} for item in configured.get({command_name!r}, [])], "installed": installed.get({command_name!r}, [])}}

            def save():
                state_path.write_text(json.dumps(state), encoding="utf-8")

            with open(os.environ["AGENT_TOOLING_FAKE_CLI_LOG"], "a", encoding="utf-8") as handle:
                handle.write(json.dumps({{"command": {command_name!r}, "args": sys.argv[1:]}}) + "\\n")
            if sys.argv[1:] == ["plugin", "marketplace", "list", "--json"]:
                payload = state["marketplaces"]
                if {command_name!r} == "codex":
                    payload = {{"marketplaces": payload}}
                print(json.dumps(payload))
            elif sys.argv[1:] == ["plugin", "list", "--json"]:
                payload = state["installed"]
                print(json.dumps({{"installed": payload}} if {command_name!r} == "codex" else payload))
            elif sys.argv[1:4] == ["plugin", "marketplace", "add"]:
                args = sys.argv[1:]
                source = args[-1] if {command_name!r} == "codex" else args[args.index("--scope") + 2]
                state["marketplaces"] = [{{"name": "agent-tooling", "source": source, "path": source}}]
                save()
            elif sys.argv[1:4] == ["plugin", "marketplace", "remove"]:
                state["marketplaces"] = []
                save()
            elif sys.argv[1:4] in (["plugin", "marketplace", "upgrade"], ["plugin", "marketplace", "update"]):
                if os.environ.get("AGENT_TOOLING_FAKE_CLIENT_RUNS_GIT") == "1":
                    subprocess.run(["git", "--version"], check=True, stdin=subprocess.DEVNULL)
            elif sys.argv[1:3] in (["plugin", "add"], ["plugin", "install"], ["plugin", "update"]):
                args = sys.argv[1:]
                selector = next(value for value in args[2:] if "@" in value)
                if selector == os.environ.get("AGENT_TOOLING_FAKE_FAIL_PLUGIN"):
                    raise SystemExit("injected plugin mutation failure")
                versions = json.loads(os.environ["AGENT_TOOLING_FAKE_VERSIONS"])
                scope = args[args.index("--scope") + 1] if "--scope" in args else "user"
                project_path = os.getcwd() if scope != "user" else None
                current = next((item for item in state["installed"] if item["pluginId"] == selector and item.get("scope", "user") == scope and item.get("projectPath") == project_path), None)
                if current is None:
                    record = {{"pluginId": selector, "version": versions[selector], "enabled": True, "scope": scope}}
                    if project_path: record["projectPath"] = project_path
                    state["installed"].append(record)
                else:
                    current["version"] = versions[selector]
                save()
            else:
                raise SystemExit("unexpected arguments: " + " ".join(sys.argv[1:]))
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_fake_git(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import os
            import shutil
            import sys
            import json
            from pathlib import Path

            with open(os.environ["AGENT_TOOLING_FAKE_GIT_LOG"], "a", encoding="utf-8") as handle:
                handle.write(json.dumps(sys.argv[1:]) + "\\n")
            if sys.argv[1:] == ["--version"]:
                print("git version fake")
            elif sys.argv[1] == "clone":
                shutil.copytree(Path(os.environ["AGENT_TOOLING_FAKE_GIT_SOURCE"]), Path(sys.argv[-1]))
            else:
                raise SystemExit("unsupported git arguments")
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_rejecting_git(path: Path) -> None:
    path.write_text(
        f"#!{sys.executable}\nraise SystemExit('caller Git must not be used')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_stateful_fake_cli(path: Path, command_name: str, state_path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json
            import os
            import sys
            from pathlib import Path

            state_path = Path({str(state_path)!r})
            state = json.loads(state_path.read_text(encoding="utf-8"))
            args = sys.argv[1:]
            with open(os.environ["AGENT_TOOLING_FAKE_CLI_LOG"], "a", encoding="utf-8") as handle:
                handle.write(json.dumps({{"command": {command_name!r}, "args": args}}) + "\\n")

            def save():
                state_path.write_text(json.dumps(state), encoding="utf-8")
                if {command_name!r} == "claude":
                    registry = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "plugins" / "installed_plugins.json"
                    registry.parent.mkdir(parents=True, exist_ok=True)
                    entries = {{}}
                    for item in state["installed"]:
                        entries.setdefault(item["pluginId"], []).append({{k:v for k,v in item.items() if k not in ("pluginId", "enabled")}})
                    registry.write_text(json.dumps({{"version": 2, "plugins": entries}}), encoding="utf-8")

            if args == ["plugin", "marketplace", "list", "--json"]:
                items = state["marketplaces"]
                print(json.dumps({{"marketplaces": items}} if {command_name!r} == "codex" else items))
            elif args == ["plugin", "list", "--json"]:
                installed = state["installed"]
                print(json.dumps({{"installed": installed}} if {command_name!r} == "codex" else installed))
            elif args[:3] == ["plugin", "marketplace", "add"]:
                source = next(value for value in args[3:] if not value.startswith("-") and value not in ("user", "project", "local", ".agents/plugins", ".claude-plugin", "plugins", "main"))
                state["marketplaces"] = [{{"name": "agent-tooling", "source": source, "path": source}}]
                save()
            elif args[:3] in (["plugin", "marketplace", "upgrade"], ["plugin", "marketplace", "update"]):
                pass
            elif args[:2] in (["plugin", "add"], ["plugin", "install"], ["plugin", "update"]):
                selector = next(value for value in args[2:] if "@" in value)
                version = os.environ["AGENT_TOOLING_FAKE_VERSION"]
                found = next((item for item in state["installed"] if item["pluginId"] == selector), None)
                if found is None:
                    state["installed"].append({{"pluginId": selector, "version": version, "enabled": True, "scope": "user"}})
                else:
                    found["version"] = version
                save()
            elif args[:3] == ["plugin", "marketplace", "remove"]:
                state["marketplaces"] = []
                save()
            else:
                raise SystemExit("unexpected arguments: " + " ".join(args))
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def load_calls(log_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def mutation_calls(calls: list[dict[str, object]]) -> list[dict[str, object]]:
    mutations = {
        ("plugin", "marketplace", "add"),
        ("plugin", "marketplace", "remove"),
        ("plugin", "marketplace", "upgrade"),
        ("plugin", "marketplace", "update"),
        ("plugin", "add"),
        ("plugin", "install"),
        ("plugin", "update"),
    }
    return [
        call
        for call in calls
        if any(tuple(call["args"][:length]) in mutations for length in (2, 3))
    ]


def marketplace_plugin_selectors(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [f'{entry["name"]}@{data["name"]}' for entry in data["plugins"]]


class InstallAllTests(unittest.TestCase):
    def test_artifact_digest_ignores_client_and_vcs_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-all-digest-") as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / "payload").write_text("stable", encoding="utf-8")
            (root / ".git" / "index").write_text("first", encoding="utf-8")
            (root / ".in_use").write_text("first", encoding="utf-8")
            first = hash_tree(root)
            (root / ".git" / "index").write_text("second", encoding="utf-8")
            (root / ".in_use").write_text("second", encoding="utf-8")
            self.assertEqual(first, hash_tree(root))

    def test_exact_candidate_adopts_a_stale_receipt_without_mutation(self) -> None:
        plugin_id = "goalspec@agent-tooling"
        plugin_root = REPO_ROOT / "plugins" / "goalspec"
        manifest = json.loads(
            (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        candidate = Identity(manifest["version"], hash_tree(plugin_root))
        args = parse_args(["--codex-only", "--source", str(REPO_ROOT)])
        args.resolved_source = str(REPO_ROOT.resolve())
        args.source_local = True
        plan = plan_host(
            "codex",
            HostState(
                "codex",
                str(REPO_ROOT),
                True,
                {plugin_id: InstalledArtifact(candidate.version, plugin_root)},
            ),
            {plugin_id: candidate},
            {
                "schema_version": 1,
                "marketplace": "agent-tooling",
                "hosts": {
                    "codex": {
                        "plugins": {
                            plugin_id: {
                                "version": candidate.version,
                                "digest": "0" * 64,
                            }
                        }
                    }
                },
            },
            args,
        )

        self.assertFalse(plan.mutates)

    def test_same_version_changed_content_updates_exactly_once(self) -> None:
        plugin_id = "example@agent-tooling"
        args = parse_args(["--codex-only", "--source", str(REPO_ROOT)])
        args.resolved_source = str(REPO_ROOT.resolve())
        args.source_local = True
        plan = plan_host(
            "codex",
            HostState(
                "codex",
                str(REPO_ROOT),
                True,
                {plugin_id: InstalledArtifact("1.0.0")},
            ),
            {plugin_id: Identity("1.0.0", "b" * 64)},
            {
                "schema_version": 1,
                "marketplace": "agent-tooling",
                "hosts": {
                    "codex": {
                        "plugins": {
                            plugin_id: {"version": "1.0.0", "digest": "a" * 64}
                        }
                    }
                },
            },
            args,
        )

        self.assertEqual((), plan.install)
        self.assertEqual((plugin_id,), plan.update)

    def test_downgrade_and_incomparable_versions_fail_before_mutation_unless_forced(self) -> None:
        plugin_id = "example@agent-tooling"
        state = HostState(
            "codex",
            str(REPO_ROOT),
            True,
            {plugin_id: InstalledArtifact("2.0.0")},
        )
        receipt = {
            "schema_version": 1,
            "marketplace": "agent-tooling",
            "hosts": {"codex": {"plugins": {plugin_id: {"version": "2.0.0", "digest": "a" * 64}}}},
        }
        args = parse_args(["--codex-only", "--source", str(REPO_ROOT)])
        args.resolved_source = str(REPO_ROOT.resolve())
        args.source_local = True

        with self.assertRaisesRegex(InstallError, "downgrade requires --force"):
            plan_host("codex", state, {plugin_id: Identity("1.0.0", "b" * 64)}, receipt, args)
        with self.assertRaisesRegex(InstallError, "incomparable plugin version"):
            plan_host("codex", state, {plugin_id: Identity("next", "b" * 64)}, receipt, args)

        args.force = True
        forced = plan_host(
            "codex",
            state,
            {plugin_id: Identity("1.0.0", "b" * 64)},
            receipt,
            args,
        )
        self.assertEqual((plugin_id,), forced.update)

    def test_artifact_digest_rejects_escaping_symlinks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-all-symlink-") as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            (root / "escape").symlink_to(Path(tmp).parent)
            with self.assertRaisesRegex(InstallError, "symlink escapes"):
                hash_tree(root)

    def _run_install_all_process(
        self,
        repo_root: Path,
        temp_root: Path,
        *args: str,
        fake_marketplaces: dict[str, list[str | dict[str, str]]] | None = None,
        fake_installed: dict[str, list[dict[str, object]]] | None = None,
        client_runs_git: bool = False,
        fail_plugin: str | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
        install_all = repo_root / "scripts" / "install-all"
        bin_dir = temp_root / "bin"
        bin_dir.mkdir()
        log_path = temp_root / "cli.jsonl"
        log_path.touch()
        git_log_path = temp_root / "git.jsonl"
        git_log_path.touch()
        write_fake_cli(bin_dir / "codex", "codex")
        write_fake_cli(bin_dir / "claude", "claude")
        write_rejecting_git(bin_dir / "git")
        public_bin_dir = temp_root / "public-bin"
        public_bin_dir.mkdir()
        public_git = public_bin_dir / "git"
        write_fake_git(public_git)
        versions: dict[str, str] = {}
        for host, manifest_name in (("codex", ".codex-plugin/plugin.json"), ("claude", ".claude-plugin/plugin.json")):
            catalog_path = repo_root / (".agents/plugins/marketplace.json" if host == "codex" else ".claude-plugin/marketplace.json")
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            for item in catalog["plugins"]:
                plugin_manifest = json.loads((repo_root / "plugins" / item["name"] / manifest_name).read_text(encoding="utf-8"))
                versions[f'{item["name"]}@{catalog["name"]}'] = plugin_manifest["version"]
        path_value = os.environ.get("PATH", os.defpath)
        env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{path_value}{os.pathsep}{os.defpath}",
            "AGENT_TOOLING_FAKE_CLI_LOG": str(log_path),
            "AGENT_TOOLING_FAKE_MARKETPLACES": json.dumps(fake_marketplaces or {}),
            "AGENT_TOOLING_FAKE_INSTALLED": json.dumps(fake_installed or {}),
            "AGENT_TOOLING_FAKE_CLIENT_RUNS_GIT": "1" if client_runs_git else "0",
            "AGENT_TOOLING_FAKE_FAIL_PLUGIN": fail_plugin or "",
            "AGENT_TOOLING_FAKE_VERSIONS": json.dumps(versions),
            "AGENT_TOOLING_FAKE_GIT_SOURCE": str(repo_root),
            "AGENT_TOOLING_FAKE_GIT_LOG": str(git_log_path),
            "AGENT_TOOLING_GIT_COMMAND": str(public_git),
            "XDG_STATE_HOME": str(temp_root / "state"),
            "CLAUDE_CONFIG_DIR": str(temp_root / "claude-profile"),
            "CODEX_HOME": str(temp_root / "codex-profile"),
        }
        proc = subprocess.run(
            [str(install_all), *args],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=120,
        )
        return proc, load_calls(log_path)

    def run_install_all_process(
        self,
        *args: str,
        fake_marketplaces: dict[str, list[str | dict[str, str]]] | None = None,
        fake_installed: dict[str, list[dict[str, object]]] | None = None,
        client_runs_git: bool = False,
        fail_plugin: str | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
        with tempfile.TemporaryDirectory(prefix="install-all-test-") as tmp:
            tmp_path = Path(tmp)
            return self._run_install_all_process(
                REPO_ROOT,
                tmp_path,
                *args,
                fake_marketplaces=fake_marketplaces,
                fake_installed=fake_installed,
                client_runs_git=client_runs_git,
                fail_plugin=fail_plugin,
            )

    def run_install_all_with_catalogs(
        self,
        codex_plugins: list[str],
        claude_plugins: list[str],
        *args: str,
    ) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
        with tempfile.TemporaryDirectory(prefix="install-all-catalog-test-") as tmp:
            tmp_path = Path(tmp)
            repo_root = tmp_path / "repo"
            (repo_root / "scripts").mkdir(parents=True)
            (repo_root / ".agents" / "plugins").mkdir(parents=True)
            (repo_root / ".claude-plugin").mkdir(parents=True)
            shutil.copy2(INSTALL_ALL, repo_root / "scripts" / "install-all")
            shutil.copy2(REPO_ROOT / "scripts" / "install_all.py", repo_root / "scripts" / "install_all.py")
            for name in sorted(set(codex_plugins) | set(claude_plugins)):
                for manifest_dir in (".codex-plugin", ".claude-plugin"):
                    manifest = repo_root / "plugins" / name / manifest_dir / "plugin.json"
                    manifest.parent.mkdir(parents=True, exist_ok=True)
                    manifest.write_text(json.dumps({"name": name, "version": "1.0.0"}), encoding="utf-8")
            (repo_root / ".agents" / "plugins" / "marketplace.json").write_text(
                json.dumps(
                    {
                        "name": "agent-tooling",
                        "plugins": [{"name": name, "source": {"source": "local", "path": f"./plugins/{name}"}} for name in codex_plugins],
                    }
                ),
                encoding="utf-8",
            )
            (repo_root / ".claude-plugin" / "marketplace.json").write_text(
                json.dumps(
                    {
                        "name": "agent-tooling",
                        "plugins": [{"name": name, "source": f"./plugins/{name}"} for name in claude_plugins],
                    }
                ),
                encoding="utf-8",
            )
            return self._run_install_all_process(repo_root, tmp_path, *args)

    def run_install_all(self, *args: str) -> list[dict[str, object]]:
        proc, calls = self.run_install_all_process(*args)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        return calls

    def test_installs_all_plugins_to_codex_and_claude_with_sparse_marketplaces(self) -> None:
        calls = self.run_install_all("--source", "DevGuyRash/agent-tooling", "--ref", "main", "--claude-scope", "local")

        mutations = mutation_calls(calls)
        codex_calls = [call["args"] for call in mutations if call["command"] == "codex"]
        claude_calls = [call["args"] for call in mutations if call["command"] == "claude"]

        self.assertEqual(
            ["plugin", "marketplace", "add", "--ref", "main", "--sparse", ".agents/plugins", "--sparse", "plugins", "DevGuyRash/agent-tooling"],
            codex_calls[0],
        )
        self.assertEqual(
            ["plugin", "marketplace", "add", "--scope", "local", "DevGuyRash/agent-tooling", "--sparse", ".claude-plugin", "plugins"],
            claude_calls[0],
        )

        codex_installs = codex_calls[1:]
        claude_installs = [args for args in claude_calls[1:] if args[:2] == ["plugin", "install"]]
        codex_plugins = [args[-1] for args in codex_installs]
        claude_plugins = [args[-1] for args in claude_installs]
        self.assertEqual(marketplace_plugin_selectors(CODEX_MARKETPLACE), codex_plugins)
        self.assertEqual(marketplace_plugin_selectors(CLAUDE_MARKETPLACE), claude_plugins)
        self.assertFalse(any(args[:2] == ["plugin", "update"] for args in claude_calls))

    def test_new_remote_plugin_refreshes_existing_marketplaces_before_install(self) -> None:
        proc, calls = self.run_install_all_process(
            "--include", "agentic-design-and-evaluation",
            fake_marketplaces={
                host: [{"name": "agent-tooling", "source": "DevGuyRash/agent-tooling"}]
                for host in ("codex", "claude")
            },
            fake_installed={"codex": [], "claude": []},
            client_runs_git=True,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual(
            [
                {"command": "codex", "args": ["plugin", "marketplace", "upgrade", "agent-tooling"]},
                {"command": "codex", "args": ["plugin", "add", "agentic-design-and-evaluation@agent-tooling"]},
                {"command": "claude", "args": ["plugin", "marketplace", "update", "agent-tooling"]},
                {"command": "claude", "args": ["plugin", "install", "--scope", "user", "agentic-design-and-evaluation@agent-tooling"]},
            ],
            mutation_calls(calls),
        )

    def test_client_marketplace_refresh_uses_the_exact_public_git(self) -> None:
        goalspec = json.loads(
            (REPO_ROOT / "plugins" / "goalspec" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        proc, calls = self.run_install_all_process(
            "--codex-only",
            "--include",
            "goalspec",
            "--force",
            fake_marketplaces={
                "codex": [
                    {
                        "name": "agent-tooling",
                        "source": "DevGuyRash/agent-tooling",
                    }
                ]
            },
            fake_installed={
                "codex": [
                    {
                        "pluginId": "goalspec@agent-tooling",
                        "version": goalspec["version"],
                        "enabled": True,
                    }
                ]
            },
            client_runs_git=True,
        )

        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn(
            {"command": "codex", "args": ["plugin", "marketplace", "upgrade", "agent-tooling"]},
            mutation_calls(calls),
        )

    def test_second_local_install_invokes_no_mutating_client_commands(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-all-idempotency-") as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            log_path = tmp_path / "cli.jsonl"
            log_path.touch()
            state_paths = {
                host: tmp_path / f"{host}.json" for host in ("codex", "claude")
            }
            for host, state_path in state_paths.items():
                state_path.write_text(json.dumps({"marketplaces": [], "installed": []}), encoding="utf-8")
                write_stateful_fake_cli(bin_dir / host, host, state_path)
            goalspec = json.loads(
                (REPO_ROOT / "plugins" / "goalspec" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            env = {
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', os.defpath)}{os.pathsep}{os.defpath}",
                "XDG_STATE_HOME": str(tmp_path / "state"),
                "CLAUDE_CONFIG_DIR": str(tmp_path / "claude-profile"),
                "CODEX_HOME": str(tmp_path / "codex-profile"),
                "AGENT_TOOLING_FAKE_CLI_LOG": str(log_path),
                "AGENT_TOOLING_FAKE_VERSION": goalspec["version"],
            }
            command = [str(INSTALL_ALL), "--source", str(REPO_ROOT), "--include", "goalspec"]

            first = subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            log_path.write_text("", encoding="utf-8")
            second = subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)
            self.assertEqual(0, second.returncode, second.stdout + second.stderr)

            mutating = {
                ("plugin", "marketplace", "add"),
                ("plugin", "marketplace", "upgrade"),
                ("plugin", "marketplace", "update"),
                ("plugin", "marketplace", "remove"),
                ("plugin", "add"),
                ("plugin", "install"),
                ("plugin", "update"),
            }
            second_calls = load_calls(log_path)
            self.assertFalse(
                any(tuple(call["args"][:length]) in mutating for call in second_calls for length in (2, 3))
            )

            log_path.write_text("", encoding="utf-8")
            forced = subprocess.run([*command, "--force"], cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)
            self.assertEqual(0, forced.returncode, forced.stdout + forced.stderr)
            forced_mutations = mutation_calls(load_calls(log_path))
            self.assertEqual(
                [
                    {"command": "codex", "args": ["plugin", "add", "goalspec@agent-tooling"]},
                    {"command": "claude", "args": ["plugin", "update", "--scope", "user", "goalspec@agent-tooling"]},
                ],
                forced_mutations,
            )

    def test_source_mismatch_fails_before_any_client_mutation(self) -> None:
        proc, calls = self.run_install_all_process(
            "--source",
            str(REPO_ROOT),
            "--include",
            "goalspec",
            fake_marketplaces={"codex": ["agent-tooling"], "claude": ["agent-tooling"]},
        )

        self.assertNotEqual(0, proc.returncode)
        self.assertIn("source mismatch", proc.stderr)
        self.assertEqual([], mutation_calls(calls))

    def test_failed_update_preserves_previous_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="install-all-failed-receipt-") as tmp:
            temp_root = Path(tmp)
            receipt = temp_root / "state" / "agent-tooling" / "install-all.json"
            receipt.parent.mkdir(parents=True)
            prior = {
                "schema_version": 1,
                "marketplace": "agent-tooling",
                "hosts": {
                    "codex": {
                        "source": str(REPO_ROOT),
                        "scope": "user",
                        "plugins": {
                            "goalspec@agent-tooling": {
                                "version": "0.0.1",
                                "digest": "a" * 64,
                            }
                        },
                    }
                },
            }
            receipt.write_text(json.dumps(prior, sort_keys=True) + "\n", encoding="utf-8")
            before = receipt.read_bytes()

            proc, calls = self._run_install_all_process(
                REPO_ROOT,
                temp_root,
                "--codex-only",
                "--source",
                str(REPO_ROOT),
                "--include",
                "goalspec",
                fake_marketplaces={
                    "codex": [
                        {
                            "name": "agent-tooling",
                            "source": str(REPO_ROOT),
                        }
                    ]
                },
                fake_installed={
                    "codex": [
                        {
                            "pluginId": "goalspec@agent-tooling",
                            "version": "0.0.1",
                            "enabled": True,
                        }
                    ]
                },
                fail_plugin="goalspec@agent-tooling",
            )

            self.assertNotEqual(0, proc.returncode)
            self.assertEqual(before, receipt.read_bytes())
            self.assertEqual(
                [
                    {
                        "command": "codex",
                        "args": ["plugin", "add", "goalspec@agent-tooling"],
                    }
                ],
                mutation_calls(calls),
            )

    def test_claude_github_marketplace_uses_repo_as_the_source_identity(self) -> None:
        proc, calls = self.run_install_all_process(
            "--claude-only",
            "--include",
            "goalspec",
            fake_marketplaces={
                "claude": [
                    {
                        "name": "agent-tooling",
                        "source": "github",
                        "repo": "DevGuyRash/agent-tooling",
                    }
                ]
            },
        )

        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertFalse(
            any(
                call["args"][:3] == ["plugin", "marketplace", "add"]
                for call in mutation_calls(calls)
            )
        )
        self.assertEqual(
            [
                {
                    "command": "claude",
                    "args": ["plugin", "marketplace", "update", "agent-tooling"],
                },
                {
                    "command": "claude",
                    "args": [
                        "plugin",
                        "install",
                        "--scope",
                        "user",
                        "goalspec@agent-tooling",
                    ],
                }
            ],
            mutation_calls(calls),
        )

    def test_local_source_omits_sparse_and_ref_flags(self) -> None:
        calls = self.run_install_all("--source", str(REPO_ROOT), "--codex-only")

        mutations = mutation_calls(calls)
        self.assertEqual(
            {"command": "codex", "args": ["plugin", "marketplace", "add", str(REPO_ROOT)]},
            mutations[0],
        )
        self.assertFalse(any(call["command"] == "claude" for call in calls))
        self.assertEqual(1 + len(marketplace_plugin_selectors(CODEX_MARKETPLACE)), len(mutations))

    def test_replace_marketplace_removes_existing_source_before_local_add(self) -> None:
        proc, calls = self.run_install_all_process(
            "--source",
            str(REPO_ROOT),
            "--include",
            "goalspec",
            "--replace-marketplace",
            fake_marketplaces={"codex": ["agent-tooling"], "claude": ["agent-tooling"]},
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

        self.assertEqual(
            [
                {"command": "codex", "args": ["plugin", "marketplace", "remove", "agent-tooling"]},
                {"command": "codex", "args": ["plugin", "marketplace", "add", str(REPO_ROOT)]},
                {"command": "codex", "args": ["plugin", "add", "goalspec@agent-tooling"]},
                {"command": "claude", "args": ["plugin", "marketplace", "remove", "--scope", "user", "agent-tooling"]},
                {"command": "claude", "args": ["plugin", "marketplace", "add", "--scope", "user", str(REPO_ROOT)]},
                {"command": "claude", "args": ["plugin", "install", "--scope", "user", "goalspec@agent-tooling"]},
            ],
            mutation_calls(calls),
        )

    def test_replace_marketplace_skips_removal_when_already_absent(self) -> None:
        proc, calls = self.run_install_all_process(
            "--source",
            str(REPO_ROOT),
            "--include",
            "goalspec",
            "--replace-marketplace",
        )

        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertFalse(
            any(call["args"][:3] == ["plugin", "marketplace", "remove"] for call in calls)
        )
        self.assertEqual([], [call for call in mutation_calls(calls) if call["args"][:3] == ["plugin", "marketplace", "remove"]])

    def test_rejects_invalid_claude_scope_before_cli_mutation(self) -> None:
        proc, calls = self.run_install_all_process("--claude-scope", "workspace")

        self.assertNotEqual(0, proc.returncode)
        self.assertIn("--claude-scope must be user, project, or local", proc.stderr)
        self.assertEqual([], calls)

    def test_claude_only_skips_codex(self) -> None:
        calls = self.run_install_all("--claude-only", "--include", "goalspec")

        self.assertFalse(any(call["command"] == "codex" for call in calls))
        self.assertEqual(
            [
                {
                    "command": "claude",
                    "args": ["plugin", "marketplace", "add", "--scope", "user", "DevGuyRash/agent-tooling", "--sparse", ".claude-plugin", "plugins"],
                },
                {
                    "command": "claude",
                    "args": ["plugin", "install", "--scope", "user", "goalspec@agent-tooling"],
                },
            ],
            mutation_calls(calls),
        )

    def test_exclude_accepts_csv_globs_and_removes_matching_plugins(self) -> None:
        calls = self.run_install_all("--exclude", "software-development")

        codex_installs = [call["args"][-1] for call in calls if call["command"] == "codex" and call["args"][:2] == ["plugin", "add"]]
        claude_installs = [call["args"][-1] for call in calls if call["command"] == "claude" and call["args"][:2] == ["plugin", "install"]]

        expected_codex = [
            selector
            for selector in marketplace_plugin_selectors(CODEX_MARKETPLACE)
            if selector != "software-development@agent-tooling"
        ]
        expected_claude = [
            selector
            for selector in marketplace_plugin_selectors(CLAUDE_MARKETPLACE)
            if selector != "software-development@agent-tooling"
        ]
        self.assertEqual(expected_codex, codex_installs)
        self.assertEqual(expected_claude, claude_installs)
        self.assertNotIn("software-development@agent-tooling", codex_installs)
        self.assertNotIn("software-development@agent-tooling", claude_installs)

    def test_include_and_exclude_are_repeatable_and_globbed(self) -> None:
        calls = self.run_install_all(
            "--include",
            "software-development",
            "--include",
            "goalspec",
            "--exclude",
            "software-development",
        )

        codex_installs = [call["args"][-1] for call in calls if call["command"] == "codex" and call["args"][:2] == ["plugin", "add"]]
        self.assertEqual(["goalspec@agent-tooling"], codex_installs)

    def test_unmatched_filter_fails_fast(self) -> None:
        proc, calls = self.run_install_all_process("--include", "missing-plugin")

        self.assertNotEqual(0, proc.returncode)
        self.assertIn("--include pattern(s) matched no Codex or Claude Code plugins: missing-plugin", proc.stderr)
        self.assertEqual([], calls)

    def test_synthetic_claude_only_plugin_skips_codex(self) -> None:
        proc, calls = self.run_install_all_with_catalogs(
            ["shared"],
            ["shared", "claude-only"],
            "--include",
            "claude-only",
        )

        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertFalse(any(call["command"] == "codex" for call in calls))
        self.assertEqual(
            [
                [
                    "plugin",
                    "marketplace",
                    "add",
                    "--scope",
                    "user",
                    "DevGuyRash/agent-tooling",
                    "--sparse",
                    ".claude-plugin",
                    "plugins",
                ],
                ["plugin", "install", "--scope", "user", "claude-only@agent-tooling"],
            ],
            [call["args"] for call in mutation_calls(calls)],
        )


class ClaudeRegistryPreservationTests(unittest.TestCase):
    def fixture(self, root):
        args = parse_args(["--claude-only"])
        args.resolved_source = "DevGuyRash/agent-tooling"
        args.source_local = False
        plan = plan_host("claude", HostState("claude", args.resolved_source, True, {}),
                         {"new@agent-tooling": Identity("1.0.0", "a" * 64)}, {}, args)
        old = {"scope": "user", "installPath": "/fixture/old", "version": "2.0.0",
               "gitCommitSha": "b" * 40, "installedAt": "original", "lastUpdated": "original"}
        other_scope = {**old, "scope": "project", "projectPath": "/fixture/project"}
        before = {"version": 2, "plugins": {"other@market": [old], "new@agent-tooling": [other_scope]}}
        path = root / "plugins/installed_plugins.json"
        path.parent.mkdir()
        path.write_text(json.dumps(before))
        path.chmod(0o640)
        return args, plan, path, before, {"CLAUDE_CONFIG_DIR": str(root)}

    def test_cli_overwrite_preserves_raw_unrelated_and_other_scope_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            args, plan, path, before, env = self.fixture(Path(tmp))
            new = {"scope": "user", "installPath": "/fixture/new", "version": "1.0.0"}
            with preserve_claude_registry(plan, args, env):
                path.write_text(json.dumps({"version": 2, "plugins": {"new@agent-tooling": [new]}}))
            after = json.loads(path.read_text())
            self.assertEqual(after['plugins']['other@market'], before['plugins']['other@market'])
            self.assertIn(before['plugins']['new@agent-tooling'][0], after['plugins']['new@agent-tooling'])
            self.assertIn(new, after['plugins']['new@agent-tooling'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual([p.name for p in path.parent.iterdir()], ['installed_plugins.json'])

    def test_failed_cli_still_preserves_missing_unrelated_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            args, plan, path, before, env = self.fixture(Path(tmp))
            with self.assertRaisesRegex(InstallError, 'native failure'):
                with preserve_claude_registry(plan, args, env):
                    path.write_text(json.dumps({"version": 2, "plugins": {}}))
                    raise InstallError('native failure')
            self.assertEqual(json.loads(path.read_text()), before)

    def test_conflicting_change_is_detected_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            args, plan, path, before, env = self.fixture(Path(tmp))
            changed = json.loads(json.dumps(before))
            changed['plugins']['other@market'][0]['version'] = '3.0.0'
            with self.assertRaisesRegex(InstallError, 'conflicts'):
                with preserve_claude_registry(plan, args, env):
                    path.write_text(json.dumps(changed))
            self.assertEqual(json.loads(path.read_text()), changed)

    def test_unreadable_after_state_restores_known_registry_and_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            args, plan, path, before, env = self.fixture(Path(tmp))
            with self.assertRaisesRegex(InstallError, 'restored the pre-operation registry'):
                with preserve_claude_registry(plan, args, env):
                    path.write_text('broken JSON')
            self.assertEqual(json.loads(path.read_text()), before)

    def test_unsupported_before_format_prevents_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            args, plan, path, before, env = self.fixture(Path(tmp))
            original = json.dumps({"version": 3, "plugins": {}})
            path.write_text(original)
            entered = False
            with self.assertRaisesRegex(InstallError, 'version-2 format'):
                with preserve_claude_registry(plan, args, env):
                    entered = True
            self.assertFalse(entered)
            self.assertEqual(path.read_text(), original)

    def test_missing_registry_with_observed_installations_blocks_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            args, plan, path, before, env = self.fixture(Path(tmp))
            path.unlink()
            plan = plan_host("claude", HostState("claude", args.resolved_source, True,
                             {"other@market": InstalledArtifact("2.0.0", scope="user")}),
                             plan.selected, {}, args)
            entered = False
            with self.assertRaisesRegex(InstallError, 'registry could not be located'):
                with preserve_claude_registry(plan, args, env):
                    entered = True
            self.assertFalse(entered)

    def test_dry_run_does_not_rewrite_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            args, plan, path, before, env = self.fixture(Path(tmp))
            args.dry_run = True
            original = path.read_bytes()
            with preserve_claude_registry(plan, args, env):
                pass
            self.assertEqual(path.read_bytes(), original)

if __name__ == "__main__":
    unittest.main()
