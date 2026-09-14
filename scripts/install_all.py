#!/usr/bin/env python3
"""Install selected agent-tooling plugins through an identity-aware plan."""

from __future__ import annotations

import argparse
import contextlib
import copy
import dataclasses
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterator, Mapping, Sequence


MARKETPLACE = "agent-tooling"
CANONICAL_SOURCE = "DevGuyRash/agent-tooling"
SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z.-]+)?$"
)


class InstallError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Identity:
    version: str
    digest: str


@dataclasses.dataclass(frozen=True)
class InstalledArtifact:
    version: str
    root: Path | None = None
    scope: str | None = None
    project_path: Path | None = None


@dataclasses.dataclass(frozen=True)
class HostState:
    command: str
    marketplace_source: str | None
    marketplace_present: bool
    installed: Mapping[str, InstalledArtifact]
    observed_installation_count: int = 0


@dataclasses.dataclass(frozen=True)
class HostPlan:
    host: str
    state: HostState
    selected: Mapping[str, Identity]
    add_marketplace: bool
    replace_marketplace: bool
    install: tuple[str, ...]
    update: tuple[str, ...]

    @property
    def mutates(self) -> bool:
        return self.add_marketplace or self.replace_marketplace or bool(self.install or self.update)


def log(message: str) -> None:
    print(f"install-all: {message}", file=sys.stderr)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=os.environ.get("AGENT_TOOLING_MARKETPLACE_SOURCE", CANONICAL_SOURCE))
    parser.add_argument("--ref", default=os.environ.get("AGENT_TOOLING_MARKETPLACE_REF", "main"))
    parser.add_argument(
        "--public-git-command",
        default=os.environ.get("AGENT_TOOLING_GIT_COMMAND"),
        help="Exact Git executable exposed to marketplace clients (default: /usr/bin/git or PATH).",
    )
    parser.add_argument("--claude-scope", default=os.environ.get("AGENT_TOOLING_CLAUDE_SCOPE", "user"))
    parser.add_argument("--codex-only", action="store_true")
    parser.add_argument("--claude-only", action="store_true")
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--no-codex", action="store_true")
    parser.add_argument("--no-claude", action="store_true")
    parser.add_argument("--no-sparse", action="store_true")
    parser.add_argument("--replace-marketplace", action="store_true")
    parser.add_argument("--force", action="store_true", help="Reinstall every selected plugin, including downgrades.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.codex_only and args.claude_only:
        parser.error("--codex-only and --claude-only are mutually exclusive")
    # Native project/local installs record process cwd as projectPath, even
    # when local settings are written at a containing Git root (observed probe).
    args.claude_project_path = Path.cwd().resolve() if args.claude_scope != "user" else None
    if args.claude_scope not in {"user", "project", "local"}:
        parser.error("--claude-scope must be user, project, or local")
    args.codex = not args.no_codex and not args.claude_only
    args.claude = not args.no_claude and not args.codex_only
    if not args.codex and not args.claude:
        parser.error("nothing to install: both Codex and Claude Code are disabled")
    return args


def run(
    argv: Sequence[str],
    *,
    dry_run: bool = False,
    environment: Mapping[str, str] | None = None,
) -> str:
    if dry_run:
        print("+ " + shlex.join(argv))
        return ""
    completed = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=600,
        env=environment,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise InstallError(f"command failed ({completed.returncode}): {shlex.join(argv)}" + (f": {detail}" if detail else ""))
    return completed.stdout


def run_json(argv: Sequence[str], *, environment: Mapping[str, str] | None = None) -> object:
    output = run(argv, environment=environment)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise InstallError(f"command returned malformed JSON: {shlex.join(argv)}: {exc}") from exc


def hash_tree(root: Path) -> str:
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise InstallError(f"plugin source is unavailable: {root}: {exc}") from exc
    if not resolved.is_dir():
        raise InstallError(f"plugin source is not a directory: {root}")
    digest = hashlib.sha256()
    for path in sorted(resolved.rglob("*"), key=lambda value: value.relative_to(resolved).as_posix()):
        relative_path = path.relative_to(resolved)
        if ".git" in relative_path.parts or path.name in {".codex-marketplace-install.json", ".in_use"}:
            continue
        relative = relative_path.as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            try:
                path.resolve(strict=True).relative_to(resolved)
            except (OSError, ValueError) as exc:
                raise InstallError(f"plugin symlink escapes its source root: {path} -> {target}") from exc
            digest.update(f"L\0{relative}\0{target}\0".encode())
        elif path.is_dir():
            digest.update(f"D\0{relative}\0".encode())
        elif path.is_file():
            digest.update(f"F\0{relative}\0{int(bool(path.stat().st_mode & 0o111))}\0".encode())
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
        else:
            raise InstallError(f"unsupported plugin source entry: {path}")
    return digest.hexdigest()


def source_path(root: Path, raw: object) -> Path:
    value: object = raw
    if isinstance(raw, dict) and raw.get("source") == "local":
        value = raw.get("path")
    if not isinstance(value, str) or not value:
        raise InstallError("plugin catalog entry lacks a local source path")
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise InstallError(f"plugin catalog source escapes marketplace root: {value}") from exc
    return candidate


def read_catalog(root: Path, host: str) -> dict[str, Identity]:
    catalog_path = root / (".agents/plugins/marketplace.json" if host == "codex" else ".claude-plugin/marketplace.json")
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"cannot read marketplace catalog {catalog_path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("name") != MARKETPLACE or not isinstance(payload.get("plugins"), list):
        raise InstallError(f"invalid {host} marketplace catalog: {catalog_path}")
    result: dict[str, Identity] = {}
    manifest_name = ".codex-plugin/plugin.json" if host == "codex" else ".claude-plugin/plugin.json"
    for item in payload["plugins"]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise InstallError(f"invalid plugin entry in {catalog_path}")
        plugin_root = source_path(root, item.get("source"))
        manifest_path = plugin_root / manifest_name
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InstallError(f"cannot read candidate manifest {manifest_path}: {exc}") from exc
        version = manifest.get("version") if isinstance(manifest, dict) else None
        if not isinstance(version, str) or not version:
            raise InstallError(f"candidate manifest has no version: {manifest_path}")
        plugin_id = f"{item['name']}@{MARKETPLACE}"
        if plugin_id in result:
            raise InstallError(f"duplicate plugin in marketplace: {plugin_id}")
        result[plugin_id] = Identity(version, hash_tree(plugin_root))
    return result


def patterns(values: Sequence[str]) -> list[str]:
    return [item.strip() for value in values for item in value.split(",") if item.strip()]


def select(catalogs: Mapping[str, Mapping[str, Identity]], args: argparse.Namespace) -> dict[str, dict[str, Identity]]:
    includes, excludes = patterns(args.include), patterns(args.exclude)
    enabled = {host: catalog for host, catalog in catalogs.items() if getattr(args, host)}
    all_names = [plugin_id.rsplit("@", 1)[0] for catalog in enabled.values() for plugin_id in catalog]
    for label, values in (("--include", includes), ("--exclude", excludes)):
        misses = [pattern for pattern in values if not any(fnmatch.fnmatchcase(name, pattern) for name in all_names)]
        if misses:
            hosts = " or ".join("Claude Code" if host == "claude" else "Codex" for host in enabled)
            raise InstallError(f"{label} pattern(s) matched no {hosts} plugins: {', '.join(misses)}")
    selected: dict[str, dict[str, Identity]] = {}
    for host, catalog in enabled.items():
        selected[host] = {
            plugin_id: identity
            for plugin_id, identity in catalog.items()
            if (not includes or any(fnmatch.fnmatchcase(plugin_id.rsplit("@", 1)[0], value) for value in includes))
            and not any(fnmatch.fnmatchcase(plugin_id.rsplit("@", 1)[0], value) for value in excludes)
        }
    if not any(selected.values()):
        raise InstallError("plugin filters selected no plugins for enabled hosts")
    return selected


def normalize_source(value: str | None) -> str | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if path.is_absolute() or value.startswith(("./", "../")):
        return str(path.resolve())
    normalized = value.removesuffix(".git").removeprefix("https://github.com/")
    return normalized.rstrip("/").lower()


def marketplace_source(item: Mapping[str, object]) -> str | None:
    nested = item.get("marketplaceSource")
    candidates = [
        nested.get("repo") if isinstance(nested, dict) else None,
        nested.get("url") if isinstance(nested, dict) else None,
        nested.get("path") if isinstance(nested, dict) else None,
        nested.get("source") if isinstance(nested, dict) else None,
        item.get("repo"), item.get("url"), item.get("path"), item.get("source"),
    ]
    return next((value for value in candidates if isinstance(value, str) and value), None)


def scoped_project_path(scope: str, value: object) -> Path | None:
    if scope == "user":
        return None
    if scope not in {"project", "local"} or not isinstance(value, str) or not Path(value).is_absolute():
        raise InstallError("Claude project/local installation has no unambiguous absolute projectPath")
    return Path(value).resolve()


def discover(host: str, command: str, environment: Mapping[str, str], *,
             claude_scope: str = "user", claude_project_path: Path | None = None) -> HostState:
    raw_marketplaces = run_json(
        [command, "plugin", "marketplace", "list", "--json"], environment=environment,
    )
    items = raw_marketplaces.get("marketplaces", []) if isinstance(raw_marketplaces, dict) else raw_marketplaces
    if not isinstance(items, list):
        raise InstallError(f"{host} marketplace list has invalid shape")
    matches = [item for item in items if isinstance(item, dict) and item.get("name") == MARKETPLACE]
    if len(matches) > 1:
        raise InstallError(f"{host} reports duplicate {MARKETPLACE} marketplaces")
    raw_plugins = run_json([command, "plugin", "list", "--json"], environment=environment)
    installed_items = raw_plugins.get("installed", []) if isinstance(raw_plugins, dict) else raw_plugins
    if not isinstance(installed_items, list):
        raise InstallError(f"{host} plugin list has invalid shape")
    installed: dict[str, InstalledArtifact] = {}
    for item in installed_items:
        if not isinstance(item, dict):
            continue
        plugin_id = item.get("pluginId") or item.get("id") or item.get("name")
        if not isinstance(plugin_id, str) or not plugin_id.endswith(f"@{MARKETPLACE}"):
            continue
        scope = item.get("scope") if host == "claude" else None
        project_path = None
        if host == "claude":
            if scope not in {"user", "project", "local"}:
                raise InstallError(f"Claude did not report a supported installation scope: {plugin_id}")
            project_path = scoped_project_path(scope, item.get("projectPath"))
            if scope != claude_scope or project_path != claude_project_path:
                continue
        version = item.get("version")
        if not isinstance(version, str) or not version:
            raise InstallError(f"installed plugin has no version: {plugin_id}")
        root_value = item.get("installPath") or item.get("cachePath")
        root = Path(root_value) if isinstance(root_value, str) and Path(root_value).is_absolute() else None
        if host == "codex" and root is None:
            # `source.path` in native list output names the marketplace checkout,
            # not the installed payload. The observed native cache layout is
            # profile/plugins/cache/marketplace/name/version.
            profile = Path(environment.get("CODEX_HOME") or Path.home() / ".codex")
            candidate = profile / "plugins" / "cache" / MARKETPLACE / plugin_id.split("@", 1)[0] / version
            root = candidate if candidate.is_dir() else None
        if plugin_id in installed:
            raise InstallError(f"ambiguous duplicate installed identity in the requested scope: {plugin_id}")
        installed[plugin_id] = InstalledArtifact(version, root, scope, project_path)
    match = matches[0] if matches else None
    return HostState(command, marketplace_source(match) if match else None, bool(match), installed, len(installed_items))


def semver_key(version: str) -> tuple[object, ...] | None:
    match = SEMVER.fullmatch(version)
    if match is None:
        return None
    prerelease = match.group(4)
    tail: tuple[tuple[int, object], ...] = ((2, ""),) if prerelease is None else tuple(
        (0, int(part)) if part.isdigit() else (1, part) for part in prerelease.split(".")
    )
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), tail


def receipt_path() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return root / "agent-tooling" / "install-all.json"


def read_receipt(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"schema_version": 1, "marketplace": MARKETPLACE, "hosts": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"cannot read installer receipt {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or payload.get("marketplace") != MARKETPLACE or not isinstance(payload.get("hosts"), dict):
        raise InstallError(f"invalid installer receipt: {path}")
    return payload


def receipt_identity(receipt: Mapping[str, object], host: str, plugin_id: str, *, scope: str | None = None, project_path: Path | None = None) -> Identity | None:
    hosts = receipt.get("hosts", {})
    host_data = hosts.get(host, {}) if isinstance(hosts, dict) else {}
    if host == "claude":
        if not isinstance(host_data, dict) or host_data.get("scope") != scope:
            return None
        if scope != "user":
            recorded = host_data.get("projectPath")
            if not isinstance(recorded, str) or not Path(recorded).is_absolute() or Path(recorded).resolve() != project_path:
                return None
    plugins = host_data.get("plugins", {}) if isinstance(host_data, dict) else {}
    value = plugins.get(plugin_id) if isinstance(plugins, dict) else None
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("version"), str) or not isinstance(value.get("digest"), str) or len(value["digest"]) != 64:
        raise InstallError(f"invalid installer receipt identity: {host} {plugin_id}")
    return Identity(value["version"], value["digest"])


def plan_host(host: str, state: HostState, selected: Mapping[str, Identity], receipt: Mapping[str, object], args: argparse.Namespace) -> HostPlan:
    replace = state.marketplace_present and args.replace_marketplace
    if state.marketplace_present and not replace and normalize_source(state.marketplace_source) != normalize_source(args.resolved_source):
        raise InstallError(
            f"{host} marketplace source mismatch: observed {state.marketplace_source!r}, expected {args.resolved_source!r}; use --replace-marketplace"
        )
    install: list[str] = []
    update: list[str] = []
    for plugin_id, candidate in selected.items():
        installed = state.installed.get(plugin_id)
        if host == "claude" and installed is not None and (installed.scope, installed.project_path) != (args.claude_scope, args.claude_project_path):
            installed = None
        if installed is None:
            install.append(plugin_id)
            continue
        current = installed.version
        previous = None if args.replace_marketplace else receipt_identity(receipt, host, plugin_id, scope=args.claude_scope, project_path=args.claude_project_path)
        observed_digest = hash_tree(installed.root) if installed.root is not None else None
        exact_candidate = current == candidate.version and observed_digest == candidate.digest
        if (
            previous is not None
            and observed_digest is not None
            and observed_digest != previous.digest
            and not exact_candidate
        ):
            raise InstallError(f"installed plugin content drifted after its receipt: {host} {plugin_id}")
        before_digest = observed_digest or (previous.digest if previous is not None else None)
        changed_digest = before_digest is not None and before_digest != candidate.digest
        if args.force or args.replace_marketplace or current != candidate.version or changed_digest:
            if current != candidate.version and not (args.force or args.replace_marketplace):
                before, after = semver_key(current), semver_key(candidate.version)
                if before is None or after is None:
                    raise InstallError(f"incomparable plugin version requires --force: {plugin_id} {current} -> {candidate.version}")
                if after < before:
                    raise InstallError(f"plugin downgrade requires --force: {plugin_id} {current} -> {candidate.version}")
            update.append(plugin_id)
    return HostPlan(host, state, selected, not state.marketplace_present, replace, tuple(install), tuple(update))


def mutation(command: str, host: str, operation: str, plugin_id: str | None, args: argparse.Namespace) -> list[str]:
    if operation == "remove-marketplace":
        return [command, "plugin", "marketplace", "remove", *(["--scope", args.claude_scope] if host == "claude" else []), MARKETPLACE]
    if operation == "add-marketplace":
        if host == "codex":
            sparse = [] if args.no_sparse or args.source_local else ["--ref", args.ref, "--sparse", ".agents/plugins", "--sparse", "plugins"]
            return [command, "plugin", "marketplace", "add", *sparse, args.source]
        sparse = [] if args.no_sparse or args.source_local else ["--sparse", ".claude-plugin", "plugins"]
        return [command, "plugin", "marketplace", "add", "--scope", args.claude_scope, args.source, *sparse]
    if operation == "refresh":
        return [command, "plugin", "marketplace", "upgrade" if host == "codex" else "update", MARKETPLACE]
    assert plugin_id is not None
    if host == "codex":
        return [command, "plugin", "add", plugin_id]
    if operation == "install":
        return [command, "plugin", "install", "--scope", args.claude_scope, plugin_id]
    return [command, "plugin", "update", "--scope", args.claude_scope, plugin_id]


def claude_registry_data(raw: bytes) -> dict:
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise InstallError("Claude plugin registry is unreadable; cannot preserve registrations") from exc
    if (not isinstance(data, dict) or data.get("version") != 2
            or not isinstance(data.get("plugins"), dict)
            or any(not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries)
                   for entries in data["plugins"].values())):
        raise InstallError("Claude registry preservation supports the observed version-2 format only")
    return data


def replace_registry(path: Path, expected: bytes | None, data: dict, mode: int) -> None:
    # The lifecycle lock coordinates this installer and syscfg. Detect an
    # intervening writer as well; never resolve a conflict by overwriting it.
    current = path.read_bytes() if path.exists() else None
    if current != expected:
        raise InstallError("Claude plugin registry changed during preservation; inspect before retrying")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".installed-plugins-preserve-", delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(handle.name, mode)
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if (path.read_bytes() if path.exists() else None) != expected:
            raise InstallError("Claude plugin registry changed during preservation; inspect before retrying")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def preserve_claude_registry(plan: HostPlan, args: argparse.Namespace,
                             environment: Mapping[str, str], *, transaction_mutates: bool | None = None) -> Iterator[None]:
    """Preserve raw non-selected registrations across native installation calls.

    This is a per-operation boundary, not a desired-state reconciler. Existing
    changed records are conflicts; only missing protected records are restored.
    """
    active = plan.mutates if transaction_mutates is None else transaction_mutates
    if plan.host != "claude" or args.dry_run or not active:
        yield
        return
    config = Path(environment.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
    path = config / "plugins" / "installed_plugins.json"
    if not path.exists():
        if plan.state.observed_installation_count or plan.state.installed:
            raise InstallError("Claude reports installed plugins but the native registry could not be located; no mutation attempted")
        yield
        return
    if path.is_symlink():
        raise InstallError("cannot preserve a symlinked Claude plugin registry; no mutation attempted")
    original = path.read_bytes()
    before = claude_registry_data(original)
    mode = stat.S_IMODE(path.stat().st_mode)
    mutable_ids = set(plan.install) | set(plan.update)
    target_project = getattr(args, "claude_project_path", None)
    # Validate potentially exempt scoped records before any host is mutated.
    for plugin_id, entries in before["plugins"].items():
        for entry in entries:
            if plugin_id in mutable_ids and entry.get("scope") == args.claude_scope:
                scoped_project_path(args.claude_scope, entry.get("projectPath"))
    try:
        yield
    finally:
        observed = path.read_bytes() if path.exists() else None
        try:
            after = claude_registry_data(observed or b"")
        except InstallError:
            replace_registry(path, observed, before, mode)
            raise InstallError("Claude registry became unreadable during the transaction; restored the pre-operation registry")
        repaired = copy.deepcopy(after)
        conflicts: list[str] = []
        restored = 0
        for key, value in before.items():
            if key == "plugins":
                continue
            if key not in repaired:
                repaired[key] = value
            elif repaired[key] != value:
                conflicts.append(key)
        for plugin_id, entries in before["plugins"].items():
            for entry in entries:
                if (plugin_id in mutable_ids and entry.get("scope") == args.claude_scope
                        and scoped_project_path(args.claude_scope, entry.get("projectPath")) == target_project):
                    continue
                current = repaired["plugins"].setdefault(plugin_id, [])
                matches = [e for e in current if (e.get("scope"), e.get("projectPath"))
                           == (entry.get("scope"), entry.get("projectPath"))]
                if not matches:
                    current.append(copy.deepcopy(entry))
                    restored += 1
                elif len(matches) != 1 or matches[0] != entry:
                    conflicts.append(plugin_id)
        if repaired != after:
            replace_registry(path, observed, repaired, mode)
        if restored:
            log(f"preserved {restored} missing non-selected Claude registration(s) after the installation transaction")
        if conflicts:
            raise InstallError("protected Claude registry data changed; preserved missing records but did not overwrite conflicts: " + ", ".join(sorted(set(conflicts))))


def apply(plan: HostPlan, args: argparse.Namespace, environment: Mapping[str, str]) -> None:
    command = plan.state.command
    if plan.replace_marketplace:
        run(
            mutation(command, plan.host, "remove-marketplace", None, args),
            dry_run=args.dry_run,
            environment=environment,
        )
    if plan.add_marketplace or plan.replace_marketplace:
        run(
            mutation(command, plan.host, "add-marketplace", None, args),
            dry_run=args.dry_run,
            environment=environment,
        )
    elif (plan.install or plan.update) and not args.source_local:
        run(
            mutation(command, plan.host, "refresh", None, args),
            dry_run=args.dry_run,
            environment=environment,
        )
    for plugin_id in plan.install:
        run(
            mutation(command, plan.host, "install", plugin_id, args),
            dry_run=args.dry_run,
            environment=environment,
        )
    for plugin_id in plan.update:
        run(
            mutation(command, plan.host, "update", plugin_id, args),
            dry_run=args.dry_run,
            environment=environment,
        )


def write_receipt(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def lifecycle_lock() -> Iterator[None]:
    syscfg_root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "syscfg" / "reconcilers"
    path = syscfg_root / "agent-plugins.json.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise InstallError(f"another agent-plugin lifecycle operation is running: {path}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def public_git_environment(command: Path) -> Iterator[dict[str, str]]:
    with tempfile.TemporaryDirectory(prefix="agent-tooling-public-git-") as raw:
        private_bin = Path(raw)
        if os.name == "nt":
            if '"' in str(command):
                raise InstallError(f"Git executable path cannot contain a quote: {command}")
            (private_bin / "git.cmd").write_text(
                f'@echo off\r\n"{command}" %*\r\n',
                encoding="utf-8",
            )
            (private_bin / "gh.cmd").write_text("@echo off\r\nexit /b 1\r\n", encoding="utf-8")
        else:
            (private_bin / "git").symlink_to(command)
            false_command = next(
                (candidate for candidate in (Path("/usr/bin/false"), Path("/bin/false")) if candidate.is_file()),
                None,
            )
            if false_command is None:
                raise InstallError("a system false executable is required to isolate Git authentication")
            (private_bin / "gh").symlink_to(false_command)

        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
            and key not in {"GH_TOKEN", "GITHUB_TOKEN", "SSH_ASKPASS", "SSH_AUTH_SOCK"}
        }
        environment["PATH"] = str(private_bin) + os.pathsep + os.environ.get("PATH", os.defpath)
        environment["GIT_CONFIG_GLOBAL"] = os.devnull
        environment["GIT_CONFIG_NOSYSTEM"] = "1"
        environment["GIT_TERMINAL_PROMPT"] = "0"
        if os.name != "nt":
            environment["GIT_ASKPASS"] = str(false_command)
            environment["GIT_SSH_COMMAND"] = str(false_command)
            environment["SSH_ASKPASS"] = str(false_command)
        yield environment


def resolve_public_git(raw_command: str | None) -> Path:
    command = raw_command
    if command is None:
        system_git = Path("/usr/bin/git")
        command = str(system_git) if system_git.is_file() else shutil.which("git")
    elif not Path(command).expanduser().is_absolute():
        command = shutil.which(command)
    if command is None:
        raise InstallError("Git is required to resolve and install marketplace sources")
    try:
        resolved = Path(command).expanduser().resolve(strict=True)
    except OSError as exc:
        raise InstallError(f"public Git executable is unavailable: {command}: {exc}") from exc
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise InstallError(f"public Git command is not an executable regular file: {resolved}")
    return resolved


@contextlib.contextmanager
def resolved_source(
    args: argparse.Namespace,
    public_git: Path,
    environment: Mapping[str, str],
) -> Iterator[Path]:
    source = Path(args.source).expanduser()
    if source.exists() or source.is_absolute() or args.source.startswith(("./", "../")):
        try:
            root = source.resolve(strict=True)
        except OSError as exc:
            raise InstallError(f"local marketplace source is unavailable: {args.source}: {exc}") from exc
        args.source_local = True
        args.resolved_source = str(root)
        yield root
        return
    with tempfile.TemporaryDirectory(prefix="agent-tooling-install-") as raw:
        root = Path(raw) / "source"
        remote = args.source if "://" in args.source or args.source.startswith("git@") else f"https://github.com/{args.source}.git"
        clone = [str(public_git), "clone", "--quiet", "--depth", "1", "--branch", args.ref, remote, str(root)]
        run(clone, environment=environment)
        args.source_local = False
        args.resolved_source = normalize_source(args.source)
        yield root


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        public_git = resolve_public_git(args.public_git_command)
        with public_git_environment(public_git) as environment, resolved_source(
            args,
            public_git,
            environment,
        ) as root:
            catalogs = {host: read_catalog(root, host) for host in ("codex", "claude")}
            selected = select(catalogs, args)
            receipt_file = receipt_path()
            lock = contextlib.nullcontext() if args.dry_run else lifecycle_lock()
            with lock:
                receipt = read_receipt(receipt_file)
                plans: list[HostPlan] = []
                for host, plugins in selected.items():
                    if not plugins:
                        continue
                    command_name = "claude" if host == "claude" else "codex"
                    command = shutil.which(command_name)
                    if command is None:
                        raise InstallError(f"missing required command: {command_name}")
                    state = discover(host, str(Path(command).resolve()), environment, claude_scope=args.claude_scope, claude_project_path=args.claude_project_path)
                    plans.append(plan_host(host, state, plugins, receipt, args))
                with contextlib.ExitStack() as protections:
                    for plan in plans:
                        protections.enter_context(preserve_claude_registry(plan, args, environment, transaction_mutates=any(p.mutates for p in plans)))
                    for plan in plans:
                        apply(plan, args, environment)
                if args.dry_run:
                    return 0
                next_hosts: dict[str, object] = dict(receipt.get("hosts", {}))
                for plan in plans:
                    observed = discover(plan.host, plan.state.command, environment, claude_scope=args.claude_scope, claude_project_path=args.claude_project_path)
                    if not observed.marketplace_present or normalize_source(observed.marketplace_source) != normalize_source(args.resolved_source):
                        raise InstallError(f"{plan.host} marketplace verification failed")
                    for plugin_id, identity in plan.selected.items():
                        installed = observed.installed.get(plugin_id)
                        if installed is None or installed.version != identity.version:
                            raise InstallError(f"{plan.host} plugin verification failed: {plugin_id} expected {identity.version}")
                        if installed.root is not None and hash_tree(installed.root) != identity.digest:
                            raise InstallError(f"{plan.host} plugin content verification failed: {plugin_id}")
                    next_hosts[plan.host] = {
                        "source": args.resolved_source,
                        "scope": args.claude_scope if plan.host == "claude" else "user",
                        "projectPath": str(args.claude_project_path) if plan.host == "claude" and args.claude_project_path is not None else None,
                        "plugins": {plugin_id: dataclasses.asdict(identity) for plugin_id, identity in sorted(plan.selected.items())},
                    }
                next_receipt = {"schema_version": 1, "marketplace": MARKETPLACE, "hosts": next_hosts}
                if receipt != next_receipt:
                    write_receipt(receipt_file, next_receipt)
                if any(plan.install or plan.update for plan in plans):
                    log("restart open Codex/Claude sessions because a plugin root was replaced")
                else:
                    log("all selected plugins are current")
        return 0
    except (InstallError, OSError) as exc:
        log(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
