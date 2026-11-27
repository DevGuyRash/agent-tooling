#!/usr/bin/env python3
"""Reconcile agent plugins for Codex, Claude Code and Cursor from a declarative manifest.

Setup installs missing selections through the native clients and never uninstalls
existing plugins. Update mode updates installed eligible plugins, including manual
installations, without installing new catalog members. Disabled choices are
preserved; updates that would enable them are deferred. Client consent is never
pre-answered.

Cursor has no plugin install command: the selected plugins are fetched with Git and
copied into <cursor home>/plugins/local/<name>/ with receipts; Cursor loads new
copies after a window reload.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterable, Iterator, Mapping, Sequence

if __package__:
    from . import agent_install, install_all, plugin_port
else:
    import agent_install
    import install_all
    import plugin_port


CLIENTS = ("codex", "claude-code", "cursor")
NATIVE_COMMAND = {"codex": "codex", "claude-code": "claude"}
SCOPES = ("user", "project", "local")
PROVENANCE = ("owner", "vendor-official", "platform-official")
READ_TIMEOUT = 30
OUTPUT_LIMIT = 8 * 1024 * 1024
METADATA_LIMIT = 1024 * 1024
AGENT_INTENT = ".agent-plugins-projections.json"
CURSOR_LEDGER = ".agent-plugins-local.json"
CURSOR_STAGE = ".agent-plugins-stage-"
CURSOR_LEDGER_STAGE = ".agent-plugins-ledger-"
CURSOR_KEPT = ".agent-plugins-kept-"
DISPLACED = ".previous"
CURSOR_MAX_ENTRIES = 16_384
CURSOR_MAX_BYTES = 256 * 1024 * 1024
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
COMMIT = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
EXTERNAL_UPGRADE = "native marketplace upgrade would also affect an external plugin"
# Refreshing a marketplace or updating an installed plugin converges to the same
# state when repeated, so a network-shaped failure is retried after a pause.
RETRYABLE_OPERATIONS = frozenset({"refresh-marketplace", "update-plugin"})
RETRY_DELAYS = (5, 20)
TRANSIENT_FAILURE = re.compile(
    r"timed out|could not resolve host|failed to connect|connection (?:reset|refused|timed out|closed)"
    r"|early eof|rpc failed|unexpected disconnect|temporary failure|network is unreachable"
    r"|\b(?:tls|ssl)\b|\bhttp(?:/[\d.]+)? 5\d\d\b|\b50[234]\b",
    re.IGNORECASE,
)


class PluginError(RuntimeError):
    pass


class Cancelled(PluginError):
    pass


# --------------------------------------------------------------------------- manifest


@dataclasses.dataclass(frozen=True)
class PluginRef:
    name: str
    profiles: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Registration:
    mode: str  # "source" or "existing"
    source: str | None = None
    ref: str | None = None
    sparse_paths: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Selection:
    mode: str  # "all" or "include"
    required: tuple[PluginRef, ...] = ()
    available: tuple[PluginRef, ...] = ()


@dataclasses.dataclass(frozen=True)
class ClientSpec:
    marketplace_id: str
    marketplace: str
    platforms: tuple[str, ...]
    scope: str
    registration: Registration
    selection: Selection


@dataclasses.dataclass
class Manifest:
    specs: dict[str, list[ClientSpec]]
    external_plugins: frozenset[str]
    external_marketplaces: dict[str, frozenset[str]]
    project_agents: bool
    agent_models: dict[str, dict[str, str]]

    def client_specs(self, client: str, platform: str) -> list[ClientSpec]:
        return [spec for spec in self.specs.get(client, []) if platform in spec.platforms]

    def external_marketplace(self, client: str, marketplace: str) -> bool:
        return marketplace in self.external_marketplaces.get(client, frozenset())

    def external_plugin(self, client: str, plugin: str) -> bool:
        parts = qualified(plugin)
        return plugin in self.external_plugins or (parts is not None and self.external_marketplace(client, parts[1]))


def qualified(plugin: str) -> tuple[str, str] | None:
    name, separator, marketplace = plugin.partition("@")
    if not separator or not name or not marketplace or "@" in marketplace:
        return None
    return name, marketplace


def identifier(value: object) -> bool:
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def normalize_source(source: str) -> str:
    value = source.strip().removesuffix(".git").removesuffix("/")
    for prefix in ("https://github.com/", "http://github.com/"):
        value = value.removeprefix(prefix)
    return value.lower()


def _fields(value: object, required: Sequence[str], optional: Sequence[str] = ()) -> dict:
    if not isinstance(value, dict) or any(key not in value for key in required) or any(
        key not in required and key not in optional for key in value
    ):
        raise PluginError("invalid plugin manifest field set")
    return value


def _string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PluginError("plugin manifest string must be nonempty")
    return value.strip()


def _strings(value: object, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise PluginError("plugin manifest string list is invalid")
    result = [_string(item) for item in value]
    if len(set(result)) != len(result):
        raise PluginError("plugin manifest string list has duplicates")
    return result


def _refs(value: object) -> tuple[PluginRef, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise PluginError("plugin selection must be an array")
    result: list[PluginRef] = []
    for item in value:
        if isinstance(item, str):
            ref = PluginRef(_string(item))
        else:
            data = _fields(item, ("name", "profiles"))
            ref = PluginRef(_string(data["name"]), tuple(_strings(data["profiles"], allow_empty=False)))
        if "@" in ref.name or any(existing.name == ref.name for existing in result):
            raise PluginError("plugin selection needs unique bare names")
        result.append(ref)
    return tuple(result)


def _registration(value: object) -> Registration:
    mode = _string(value.get("mode") if isinstance(value, dict) else None)
    if mode == "existing":
        _fields(value, ("mode",))
        return Registration("existing")
    if mode != "source":
        raise PluginError("unsupported plugin registration mode")
    data = _fields(value, ("mode", "source"), ("ref", "sparse_paths"))
    ref = None if data.get("ref") is None else _string(data["ref"])
    sparse = tuple(_strings(data.get("sparse_paths", []), allow_empty=True))
    for path in sparse:
        if path.startswith(("/", "\\")) or path[1:2] == ":" or ".." in re.split(r"[/\\]", path):
            raise PluginError("plugin sparse paths must remain repository relative")
    return Registration("source", _string(data["source"]), ref, sparse)


def _selection(value: object) -> Selection:
    mode = _string(value.get("mode") if isinstance(value, dict) else None)
    if mode == "all":
        _fields(value, ("mode",))
        return Selection("all")
    if mode != "include":
        raise PluginError("unsupported plugin selection mode")
    data = _fields(value, ("mode",), ("plugins", "available_plugins"))
    required, available = _refs(data.get("plugins")), _refs(data.get("available_plugins"))
    if not required and not available:
        raise PluginError("plugin include selection is empty")
    if {item.name for item in required} & {item.name for item in available}:
        raise PluginError("required and available plugin selections overlap")
    return Selection("include", required, available)


def parse_manifest(raw: bytes) -> Manifest:
    if len(raw) > METADATA_LIMIT:
        raise PluginError("plugin selection manifest is too large")
    try:
        root = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise PluginError("plugin selection manifest is not valid JSON") from exc
    root = _fields(root, ("schema_version", "resource", "policies", "marketplaces"))
    if root["schema_version"] != 5 or root["resource"] != "agent-plugins":
        raise PluginError("unsupported plugin manifest schema or resource")
    policy = _fields(
        root["policies"],
        ("enabled_unmanaged_plugins", "externally_managed_plugins", "externally_managed_marketplaces"),
        ("project_plugin_agents", "project_agent_models"),
    )
    if policy["enabled_unmanaged_plugins"] not in {"preserve", "error"}:
        raise PluginError("unsupported unmanaged plugin policy")
    project_agents = policy.get("project_plugin_agents", False)
    if not isinstance(project_agents, bool):
        raise PluginError("plugin agent projection policy must be boolean")
    model = re.compile(r"[A-Za-z0-9._-]{1,128}")
    agent_models: dict[str, dict[str, str]] = {}
    models = policy.get("project_agent_models", {})
    if not isinstance(models, dict):
        raise PluginError("agent model mappings must be keyed by plugin")
    for owner, values in models.items():
        if qualified(owner) is None or not isinstance(values, dict):
            raise PluginError("agent model mapping requires an exact plugin identifier and an object")
        for source, target in values.items():
            if not model.fullmatch(source) or not isinstance(target, str) or not model.fullmatch(target):
                raise PluginError("invalid projected agent model mapping")
        agent_models[owner] = dict(values)
    external_plugins = frozenset(_strings(policy["externally_managed_plugins"], allow_empty=True))
    if any(qualified(plugin) is None for plugin in external_plugins):
        raise PluginError("external plugin must be an exact qualified identifier")
    by_client = policy["externally_managed_marketplaces"]
    if not isinstance(by_client, dict) or any(client not in CLIENTS for client in by_client):
        raise PluginError("external plugin marketplaces must be client scoped")
    external_marketplaces = {client: frozenset(_strings(values, allow_empty=False)) for client, values in by_client.items()}
    if any(not identifier(name) for names in external_marketplaces.values() for name in names):
        raise PluginError("external marketplace must be an exact identifier")
    marketplaces = root["marketplaces"]
    if not isinstance(marketplaces, list) or not marketplaces:
        raise PluginError("plugin marketplaces must be a nonempty array")
    specs: dict[str, list[ClientSpec]] = {client: [] for client in CLIENTS}
    ids: set[str] = set()
    for item in marketplaces:
        item = _fields(item, ("id", "provenance", "clients"))
        marketplace_id = _string(item["id"])
        if marketplace_id in ids:
            raise PluginError("duplicate plugin marketplace identifier")
        ids.add(marketplace_id)
        provenance = _fields(item["provenance"], ("kind", "evidence_url"))
        kind, evidence = _string(provenance["kind"]), _string(provenance["evidence_url"])
        if kind not in PROVENANCE:
            raise PluginError("unsupported plugin provenance kind")
        if not evidence.startswith("https://"):
            raise PluginError("plugin provenance requires HTTPS")
        clients = item["clients"]
        if not isinstance(clients, dict) or not clients:
            raise PluginError("plugin marketplace clients must be a nonempty object")
        for client, data in clients.items():
            if client not in CLIENTS:
                raise PluginError(f"unsupported plugin client: {client}")
            data = _fields(data, ("marketplace", "platforms", "registration", "selection"), ("scope",) if client == "claude-code" else ())
            marketplace = _string(data["marketplace"])
            if not identifier(marketplace):
                raise PluginError("plugin marketplace name must be an exact identifier")
            if marketplace in external_marketplaces.get(client, frozenset()):
                raise PluginError("external plugin marketplace overlaps declared authority")
            if any(spec.marketplace == marketplace for spec in specs[client]):
                raise PluginError("duplicate client plugin marketplace")
            platforms = tuple(_strings(data["platforms"], allow_empty=False))
            if any(platform not in {"linux", "windows", "darwin"} for platform in platforms):
                raise PluginError("unsupported plugin platform")
            scope = data.get("scope", "user")
            if scope not in SCOPES:
                raise PluginError("unsupported plugin installation scope")
            registration = _registration(data["registration"])
            if client == "cursor" and registration.mode != "source":
                raise PluginError("cursor plugin marketplaces require a source registration")
            if registration.mode == "source" and kind != "platform-official" and normalize_source(registration.source or "") != normalize_source(evidence):
                raise PluginError("plugin source differs from provenance repository")
            specs[client].append(ClientSpec(marketplace_id, marketplace, platforms, scope, registration, _selection(data["selection"])))
    for plugin in external_plugins:
        name, marketplace = qualified(plugin) or ("", "")
        for spec in (spec for values in specs.values() for spec in values if spec.marketplace == marketplace):
            if spec.registration.mode == "source":
                raise PluginError("external plugin overlaps source-managed marketplace")
            if spec.selection.mode == "all":
                raise PluginError("external plugin overlaps all-plugin selection")
            if any(item.name == name for item in spec.selection.required):
                raise PluginError("external plugin is also required")
    return Manifest(specs, external_plugins, external_marketplaces, project_agents, agent_models)


def active_refs(refs: Iterable[PluginRef], profiles: frozenset[str]) -> list[str]:
    return [item.name for item in refs if not item.profiles or any(profile in profiles for profile in item.profiles)]


# --------------------------------------------------------------------------- report


@dataclasses.dataclass
class Action:
    client: str
    operation: str
    resource: str
    applied: bool = False


@dataclasses.dataclass
class Report:
    actions: list[Action] = dataclasses.field(default_factory=list)
    deferred: list[str] = dataclasses.field(default_factory=list)
    failures: list[str] = dataclasses.field(default_factory=list)
    changed: bool = False
    verified: bool = True

    def succeeded(self) -> bool:
        return not self.failures

    def append(self, other: "Report") -> None:
        self.actions += other.actions
        self.deferred += other.deferred
        self.failures += other.failures
        self.changed |= other.changed
        self.verified &= other.verified

    def outcome(self, dry_run: bool) -> str:
        if self.failures:
            return "failed"
        if self.deferred:
            return "deferred"
        if self.changed or (not dry_run and any(a.applied and a.operation in {"update-plugin", "refresh-marketplace"} for a in self.actions)):
            return "updated"
        return "no_op"

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Options:
    client: str
    platform: str
    profiles: frozenset[str]
    update: bool
    dry_run: bool
    verify_only: bool
    timeout: int


# --------------------------------------------------------------------------- native clients


@dataclasses.dataclass(frozen=True)
class Installed:
    marketplace: str
    enabled: bool
    version: str | None
    root: Path | None
    scope: str | None


@dataclasses.dataclass(frozen=True)
class Marketplace:
    source: str | None


@dataclasses.dataclass(frozen=True)
class Task:
    operation: str
    resource: str
    arguments: tuple[str, ...]


def _text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PluginError("plugin inventory text field has invalid type")
    return value or None


def _path(value: object) -> Path | None:
    text = _text(value)
    return Path(text) if text is not None and Path(text).is_absolute() else None


def _identity(item: object) -> tuple[str, str]:
    if not isinstance(item, dict):
        raise PluginError("plugin inventory entry must be an object")
    plugin = next((text for key in ("pluginId", "id", "name") if (text := _text(item.get(key)))), None)
    if plugin is None:
        raise PluginError("plugin inventory identity is missing")
    marketplace = next((text for key in ("marketplaceName", "marketplace") if (text := _text(item.get(key)))), None)
    if "@" in plugin:
        parts = qualified(plugin)
        if parts is None or (marketplace is not None and marketplace != parts[1]):
            raise PluginError("plugin inventory identity is malformed")
        return plugin, parts[1]
    if marketplace is None or "@" in marketplace:
        raise PluginError("bare plugin inventory identity requires a marketplace")
    return f"{plugin}@{marketplace}", marketplace


def decode_installed(manifest: Manifest, client: str, payload: object) -> dict[str, Installed]:
    items = payload if client == "claude-code" and isinstance(payload, list) else payload.get("installed") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise PluginError("invalid installed plugin inventory envelope")
    result: dict[str, Installed] = {}
    for item in items:
        plugin, marketplace = _identity(item)
        if manifest.external_plugin(client, plugin):
            continue
        enabled = item.get("enabled", item.get("installed", True))
        if not isinstance(enabled, bool):
            raise PluginError("plugin enabled state must be boolean")
        scope = None
        if client == "claude-code":
            scope = _text(item.get("scope"))
            if scope is not None and scope not in SCOPES:
                raise PluginError("unsupported observed plugin scope")
        root = _path(item.get("installPath")) or (_path(item.get("cachePath")) if client == "codex" else None)
        if plugin in result:
            raise PluginError(f"duplicate installed plugin identity: {plugin}")
        result[plugin] = Installed(marketplace, enabled, _text(item.get("version")), root, scope)
    return result


def decode_marketplaces(manifest: Manifest, client: str, payload: object) -> dict[str, Marketplace]:
    items = payload if isinstance(payload, list) else payload.get("marketplaces") if client == "codex" and isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise PluginError("invalid marketplace inventory envelope")
    result: dict[str, Marketplace] = {}
    for item in items:
        if not isinstance(item, dict) or not (name := _text(item.get("name"))):
            raise PluginError("marketplace inventory entry is invalid")
        if manifest.external_marketplace(client, name):
            continue
        if client == "codex":
            nested = item.get("marketplaceSource")
            if nested is not None and not isinstance(nested, dict):
                raise PluginError("marketplace source observation must be an object")
            source = _text(nested.get("source")) if isinstance(nested, dict) else _text(item.get("source"))
        else:
            source = next((text for key in ("repo", "url", "path") if (text := _text(item.get(key)))), None)
        if name in result:
            raise PluginError(f"duplicate marketplace inventory identity: {name}")
        result[name] = Marketplace(source)
    return result


def decode_catalogs(selected: set[str], payload: object) -> dict[str, list[str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("installed"), list) or not isinstance(payload.get("available"), list):
        raise PluginError("plugin catalog must report installed and available arrays")
    result: dict[str, set[str]] = {}
    for item in [*payload["installed"], *payload["available"]]:
        plugin, marketplace = _identity(item)
        if marketplace in selected:
            result.setdefault(marketplace, set()).add(plugin)
    return {marketplace: sorted(plugins) for marketplace, plugins in result.items()}


def operand(value: str) -> str:
    if not value or len(value) > 4096 or value.startswith("-") or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise PluginError("plugin command operand is not admitted")
    return value


CREDENTIALS = (
    (re.compile(r"(?<=://)[^/\s@]+@"), "***@"),
    (re.compile(r"\b(?:gh[pousr]_|github_pat_|npm_|glpat-|xox[abpr]-)[A-Za-z0-9_-]{12,}"), "***"),
    (re.compile(r"(?i)\b(authorization|bearer|token|password)([=: ]+)\S+"), r"\1\2***"),
)


def redact(text: str) -> str:
    for pattern, replacement in CREDENTIALS:
        text = pattern.sub(replacement, text)
    return text


def failure_detail(completed: subprocess.CompletedProcess) -> str:
    """The native client's own error text, the actionable part of a failure, without credentials."""
    text = (completed.stderr or "").strip() or (completed.stdout or "").strip()
    text = " ".join("".join(c if c.isprintable() else " " for c in text).split())
    return redact(text)[-600:]


def _kill_group(process: subprocess.Popen) -> None:
    with contextlib.suppress(OSError):
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired, OSError, ValueError):
        process.communicate(timeout=5)


def bounded_run(argv: Sequence[str], *, environment: Mapping[str, str], cwd: Path | None, timeout: int,
                stop: Callable[[], None]) -> subprocess.CompletedProcess:
    """Run one command in its own process group; a timeout or cancellation ends the whole group."""
    options: dict = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    try:
        process = subprocess.Popen(list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   encoding="utf-8", errors="replace", env=dict(environment), cwd=cwd, **options)
    except OSError as exc:
        raise PluginError(f"cannot run {Path(argv[0]).name}: {exc}") from exc
    deadline = time.monotonic() + timeout
    while True:
        try:
            stdout, stderr = process.communicate(timeout=0.25)
            return subprocess.CompletedProcess(list(argv), process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            pass
        try:
            stop()
        except Cancelled:
            _kill_group(process)
            raise
        if time.monotonic() > deadline:
            _kill_group(process)
            raise PluginError(f"`{' '.join(Path(argv[0]).name if i == 0 else a for i, a in enumerate(argv[:4]))}` timed out after {timeout}s")


class NativeClient:
    """One native CLI with an explicit environment; output is bounded and never trusted."""

    def __init__(self, client: str, executable: Path, environment: Mapping[str, str], cwd: Path, stop: Callable[[], None]):
        self.client, self.executable, self.environment, self.cwd, self.stop = client, executable, environment, cwd, stop

    def capture(self, arguments: Sequence[str], timeout: int) -> str:
        self.stop()
        completed = bounded_run([str(self.executable), *arguments], environment=self.environment, cwd=self.cwd, timeout=timeout, stop=self.stop)
        self.stop()
        if completed.returncode:
            detail = failure_detail(completed)
            raise PluginError(f"exit {completed.returncode}" + (f": {detail}" if detail else ""))
        if len(completed.stdout) > OUTPUT_LIMIT:
            raise PluginError("native client output exceeds its bound")
        return completed.stdout

    def capture_json(self, arguments: Sequence[str], timeout: int = READ_TIMEOUT) -> object:
        try:
            return json.loads(self.capture(arguments, timeout))
        except ValueError as exc:
            raise PluginError(f"`{' '.join(arguments)}` returned malformed JSON") from exc

    def execute(self, task: Task, timeout: int) -> None:
        output = self.capture(task.arguments, timeout)
        if "--json" in task.arguments:
            try:
                result = json.loads(output)
            except ValueError as exc:
                raise PluginError("native plugin command returned malformed JSON") from exc
            if not isinstance(result, dict):
                raise PluginError("native plugin command result must be an object")
            if result.get("errors") not in (None, []):
                raise PluginError(f"native plugin command reported errors: {redact(json.dumps(result['errors']))[:400]}")

    def installed(self, manifest: Manifest) -> dict[str, Installed]:
        arguments = ["plugin", "list", "--json"] + (["--disable", "remote_plugin"] if self.client == "codex" else [])
        return decode_installed(manifest, self.client, self.capture_json(arguments))

    def marketplaces(self, manifest: Manifest) -> dict[str, Marketplace]:
        return decode_marketplaces(manifest, self.client, self.capture_json(["plugin", "marketplace", "list", "--json"]))

    def catalogs(self, manifest: Manifest, platform: str) -> dict[str, list[str]]:
        selected = [spec.marketplace for spec in manifest.client_specs(self.client, platform)]
        if not selected:
            return {}
        if self.client == "claude-code":
            return decode_catalogs(set(selected), self.capture_json(["plugin", "list", "--available", "--json"]))
        result = {}
        for marketplace in selected:
            catalogs = decode_catalogs({marketplace}, self.capture_json(["plugin", "list", "--marketplace", operand(marketplace), "--available", "--json"]))
            result[marketplace] = catalogs.get(marketplace, [])
        return result


def registration_tasks(manifest: Manifest, client: str, platform: str, observed: Mapping[str, Marketplace]) -> list[Task]:
    tasks = []
    for spec in manifest.client_specs(client, platform):
        registration = spec.registration
        if spec.marketplace in observed:
            current = observed[spec.marketplace].source
            if registration.mode == "source" and (current is None or normalize_source(current) != normalize_source(registration.source or "")):
                raise PluginError(f"{spec.marketplace}: registered marketplace source {current!r} differs from the selection {registration.source!r}")
            continue
        if registration.mode != "source":
            raise PluginError(f"{spec.marketplace}: required existing marketplace is unavailable")
        source = operand(registration.source or "")
        for value in (registration.ref, *registration.sparse_paths):
            if value is not None:
                operand(value)
        if client == "codex":
            arguments = ["plugin", "marketplace", "add", source]
            if registration.ref:
                arguments += ["--ref", registration.ref]
            for path in registration.sparse_paths:
                arguments += ["--sparse", path]
            arguments.append("--json")
        else:
            arguments = ["plugin", "marketplace", "add", f"{source}@{registration.ref}" if registration.ref else source, "--scope", spec.scope]
            if registration.sparse_paths:
                arguments += ["--sparse", *registration.sparse_paths]
        tasks.append(Task("add-marketplace", spec.marketplace, tuple(arguments)))
    return tasks


def refresh_task(client: str, marketplace: str) -> Task:
    arguments = ["plugin", "marketplace", "upgrade" if client == "codex" else "update", operand(marketplace)]
    return Task("refresh-marketplace", marketplace, tuple(arguments + (["--json"] if client == "codex" else [])))


def plugin_task(client: str, plugin: str, scope: str, update: bool) -> Task:
    parts = qualified(plugin)
    if parts is None:
        raise PluginError("invalid plugin command identity")
    name, marketplace = operand(parts[0]), operand(parts[1])
    if client == "codex":
        arguments = ("plugin", "add", name, "--marketplace", marketplace, "--json")
    else:
        arguments = ("plugin", "update" if update else "install", plugin, "--scope", scope)
    return Task("update-plugin" if update else "install-plugin", plugin, arguments)


def bulk_refresh_affects_external(manifest: Manifest, client: str, marketplace: str) -> bool:
    # Codex upgrades every plugin of a marketplace; Claude refreshes the catalog only.
    return client == "codex" and any((qualified(plugin) or ("", ""))[1] == marketplace for plugin in manifest.external_plugins)


def resolve_selection(manifest: Manifest, client: str, platform: str, profiles: frozenset[str], catalogs: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    desired: dict[str, list[str]] = {}
    for spec in manifest.client_specs(client, platform):
        catalog: dict[str, str] = {}
        for plugin in catalogs.get(spec.marketplace, []):
            parts = qualified(plugin)
            if parts is not None and parts[1] != spec.marketplace:
                continue
            name = parts[0] if parts else plugin
            catalog[name] = f"{name}@{spec.marketplace}"
        if spec.selection.mode == "all":
            if not catalog:
                raise PluginError(f"{spec.marketplace}: selected marketplace has no available plugins")
            selected = sorted(catalog.values())
        else:
            for name in active_refs(spec.selection.available, profiles):
                if name not in catalog:
                    raise PluginError(f"{name}@{spec.marketplace}: selected available-only plugin is absent from its catalog")
            missing = [name for name in active_refs(spec.selection.required, profiles) if name not in catalog]
            if missing:
                raise PluginError(f"{', '.join(f'{name}@{spec.marketplace}' for name in missing)}: required plugin is absent from its catalog")
            selected = [catalog[name] for name in active_refs(spec.selection.required, profiles)]
        if any(manifest.external_plugin(client, plugin) for plugin in selected):
            raise PluginError("external plugin cannot become desired state")
        desired[spec.marketplace] = selected
    return desired


def setup_tasks(manifest: Manifest, client: str, platform: str, profiles: frozenset[str], installed: Mapping[str, Installed], catalogs: Mapping[str, Sequence[str]]) -> list[Task]:
    available = {key: list(values) for key, values in catalogs.items()}
    for spec in manifest.client_specs(client, platform):
        if spec.selection.mode == "include":
            for name in active_refs(spec.selection.required, profiles):
                plugin = f"{name}@{spec.marketplace}"
                if plugin in installed:  # an installed selection needs no catalog listing, even when delisted
                    available.setdefault(spec.marketplace, []).append(plugin)
    desired = resolve_selection(manifest, client, platform, profiles, available)
    return [plugin_task(client, plugin, spec.scope, False)
            for spec in manifest.client_specs(client, platform)
            for plugin in desired.get(spec.marketplace, []) if plugin not in installed]


def setup_refreshes(manifest: Manifest, client: str, platform: str, observed: Mapping[str, Marketplace], profiles: frozenset[str],
                    installed: Mapping[str, Installed], catalogs: Mapping[str, Sequence[str]]) -> tuple[list[Task], list[str]]:
    tasks, deferred = [], []
    for spec in manifest.client_specs(client, platform):
        listed = set(catalogs.get(spec.marketplace, []))
        def contains(name: str) -> bool:
            return name in listed or f"{name}@{spec.marketplace}" in listed
        if spec.selection.mode == "all":
            needed = True
        else:
            needed = any(f"{name}@{spec.marketplace}" not in installed and not contains(name) for name in active_refs(spec.selection.required, profiles)) \
                or any(not contains(name) for name in active_refs(spec.selection.available, profiles))
        source = observed.get(spec.marketplace)
        if not needed or source is None or (source.source is not None and Path(source.source).is_absolute()):
            continue
        if bulk_refresh_affects_external(manifest, client, spec.marketplace):
            deferred.append(f"{spec.marketplace}: {EXTERNAL_UPGRADE}")
            continue
        tasks.append(refresh_task(client, spec.marketplace))
    return tasks, deferred


def update_tasks(manifest: Manifest, client: str, installed: Mapping[str, Installed], observed: Mapping[str, Marketplace]) -> tuple[list[Task], list[str]]:
    deferred: list[str] = []
    marketplaces: set[str] = set()
    plugins: list[Task] = []
    for plugin, entry in sorted(installed.items()):
        if manifest.external_plugin(client, plugin):
            continue
        parts = qualified(plugin)
        if parts is None or parts[1] != entry.marketplace:
            raise PluginError(f"installed plugin marketplace disagrees with its identity: {plugin}")
        if client == "claude-code":
            if entry.marketplace not in observed:
                # App-provided plugins such as Claude Code's `builtin` set come
                # from a marketplace the native inventory does not list, so the
                # CLI can neither refresh nor update them; the app owns them.
                continue
            if entry.scope not in (None, "user"):
                deferred.append(f"{plugin}: outside user scope")
                continue
            marketplaces.add(entry.marketplace)
        else:
            source = observed.get(entry.marketplace)
            if source is None or source.source is None:
                deferred.append(f"{plugin}: marketplace source is unavailable")
                continue
            if not Path(source.source).is_absolute():
                if bulk_refresh_affects_external(manifest, client, entry.marketplace):
                    deferred.append(f"{plugin}: {EXTERNAL_UPGRADE}")
                else:
                    marketplaces.add(entry.marketplace)
                continue
            if not entry.enabled:
                deferred.append(f"{plugin}: disabled; the native local add command would enable it")
                continue
        plugins.append(plugin_task(client, plugin, entry.scope or "user", True))
    return [refresh_task(client, marketplace) for marketplace in sorted(marketplaces)] + plugins, deferred


def verify_inventory(before: Mapping[str, Installed], after: Mapping[str, Installed], update: bool, report: Report) -> None:
    added = any(plugin not in before for plugin in after)
    # Confirmed partial progress stays reported even when a native command broke a rule.
    report.changed |= added or any(
        plugin not in after or (entry.enabled, entry.version) != (after[plugin].enabled, after[plugin].version)
        for plugin, entry in before.items()
    )
    for plugin, entry in before.items():
        current = after.get(plugin)
        if current is None:
            raise PluginError(f"native command removed an existing plugin: {plugin}")
        if entry.enabled != current.enabled:
            raise PluginError(f"native command {'disabled an enabled' if entry.enabled else 'enabled a disabled'} plugin: {plugin}")
    if update and added:
        raise PluginError("native update command installed a previously absent plugin")


def apply_task(native: NativeClient, options: Options, task: Task, report: Report, admission: Callable[[], None]) -> None:
    action = Action(options.client, task.operation, task.resource)
    report.actions.append(action)
    if options.dry_run:
        return
    admission()
    delays = RETRY_DELAYS if task.operation in RETRYABLE_OPERATIONS else ()
    for attempt in range(len(delays) + 1):
        try:
            native.execute(task, options.timeout)
            break
        except Cancelled:
            raise
        except PluginError as exc:
            if attempt == len(delays) or not TRANSIENT_FAILURE.search(str(exc)):
                raise PluginError(f"{task.operation} {task.resource} failed: {exc}") from exc
            print(f"{options.client} {task.operation} {task.resource}: transient failure, retrying "
                  f"(attempt {attempt + 2} of {len(delays) + 1})", file=sys.stderr)
            pause(delays[attempt], native.stop)
    action.applied = True


def pause(seconds: float, stop: Callable[[], None]) -> None:
    """Wait between retries; cancellation raises from `stop` immediately."""
    deadline = time.monotonic() + seconds
    while True:
        stop()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.25, remaining))


def run_native(manifest: Manifest, native: NativeClient, options: Options, admission: Callable[[], None]) -> Report:
    report = Report()
    try:
        _run_native(manifest, native, options, report, admission)
    except PluginError as exc:
        report.failures.append(f"{options.client}: {exc}")
    report.verified = report.succeeded() and not report.deferred and not options.dry_run
    return report


def _run_native(manifest: Manifest, native: NativeClient, options: Options, report: Report, admission: Callable[[], None]) -> None:
    client, platform, profiles = options.client, options.platform, options.profiles
    before = native.installed(manifest)
    if options.update:
        observed = native.marketplaces(manifest) if before else {}
        tasks, deferred = update_tasks(manifest, client, before, observed)
        report.deferred += deferred
    else:
        observed = native.marketplaces(manifest)
        registration = registration_tasks(manifest, client, platform, observed)
        if options.verify_only and registration:
            raise PluginError("selected marketplace is missing")
        for task in registration:
            apply_task(native, options, task, report, admission)
        if registration:
            if options.dry_run:
                report.deferred.append("plugin discovery requires the planned marketplace registration")
                return
            if registration_tasks(manifest, client, platform, native.marketplaces(manifest)):
                raise PluginError("client did not register the selected marketplace")
            report.changed = True
        catalogs = native.catalogs(manifest, platform)
        if not options.verify_only:
            refreshes, deferred = setup_refreshes(manifest, client, platform, observed, profiles, native.installed(manifest), catalogs)
            report.deferred += deferred
            if deferred:
                report.deferred.append("setup for this client remains incomplete until required marketplace discovery is available")
                return
            for task in refreshes:
                apply_task(native, options, task, report, admission)
            if refreshes:
                if options.dry_run:
                    report.deferred.append("plugin discovery requires the planned marketplace refresh")
                    return
                catalogs = native.catalogs(manifest, platform)
        tasks = setup_tasks(manifest, client, platform, profiles, native.installed(manifest), catalogs)
    if options.verify_only and tasks:
        raise PluginError("selected plugin is missing")
    for task in tasks:
        if not options.dry_run and task.operation in {"install-plugin", "update-plugin"}:
            current = native.installed(manifest)
            if task.operation == "install-plugin" and task.resource in current:
                continue
            if task.operation == "update-plugin" and not (task.resource in current and (client == "claude-code" or current[task.resource].enabled)):
                report.deferred.append(f"{task.resource}: no longer eligible for this native update command")
                continue
        apply_task(native, options, task, report, admission)
    if options.dry_run:
        return
    after = native.installed(manifest)
    verify_inventory(before, after, options.update, report)
    if not options.update and setup_tasks(manifest, client, platform, profiles, after, native.catalogs(manifest, platform)):
        raise PluginError("client did not install the selected plugins")


# --------------------------------------------------------------------------- Claude npm acquisition

NPM_SHIM = r'''"""Hand Claude Code's registry tarball fetch to npm as the equivalent registry spec."""
import os, re, shutil, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if p and os.path.abspath(p) != here)
os.environ["PATH"] = path
real = shutil.which("npm", path=path)
if real is None:
    sys.exit("npm is unavailable")
args = sys.argv[1:]
if "pack" in args and "--" in args and args.index("--") == len(args) - 2 and args[-1].startswith("https://"):
    registry = subprocess.run([real, "config", "get", "registry"], capture_output=True, text=True).stdout.strip().rstrip("/") + "/"
    name = r"(?:@[a-z0-9][a-z0-9._~-]*/)?([a-z0-9][a-z0-9._~-]*)"
    match = re.fullmatch(re.escape(registry) + "(" + name + r")/-/([a-z0-9][a-z0-9._~-]*)-([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.+-]*)?)\.tgz", args[-1])
    if match and match.group(2) == match.group(3):
        args[-1] = match.group(1) + "@" + match.group(4)
os.execv(real, ["npm", *args])
'''


@contextlib.contextmanager
def claude_npm_environment(environment: Mapping[str, str]) -> Iterator[dict[str, str]]:
    """Let Claude acquire npm-hosted plugins while npm's remote-URL policy stays closed.

    Claude Code resolves an npm plugin's dist.tarball and then runs `npm pack -- <URL>`;
    npm 12 refuses every URL under its default `allow-remote=none`, including the
    registry's own tarball. The shim rewrites exactly that registry tarball URL back to
    the `name@version` it was resolved from, which npm fetches from the same registry;
    every other npm invocation passes through unchanged.
    """
    real = shutil.which("npm", path=environment.get("PATH"))
    if os.name == "nt" or real is None:
        yield dict(environment)
        return
    with tempfile.TemporaryDirectory(prefix="agent-plugins-npm-") as raw:
        program = Path(raw) / "npm.py"
        program.write_text(NPM_SHIM, encoding="utf-8")
        shim = Path(raw) / "npm"
        quote = lambda value: "'" + str(value).replace("'", "'\\''") + "'"
        shim.write_text(f"#!/bin/sh\nexec {quote(sys.executable)} -I {quote(program)} \"$@\"\n", encoding="utf-8")
        shim.chmod(0o700)
        result = dict(environment)
        result["PATH"] = raw + os.pathsep + environment.get("PATH", os.defpath)
        yield result


# --------------------------------------------------------------------------- Codex agents


def _read_optional(path: Path) -> bytes | None:
    if path.is_symlink():
        raise PluginError(f"{path} must not be a link")
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    if len(data) > METADATA_LIMIT:
        raise PluginError(f"{path} exceeds its size bound")
    return data


def _save_guarded(path: Path, data: object, original: bytes | None) -> bytes:
    if _read_optional(path) != original:
        raise PluginError(f"{path} changed during reconciliation")
    encoded = (json.dumps(data, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return encoded


def codex_payload_root(codex_home: Path, owner: str, entry: Installed) -> Path:
    name, marketplace = qualified(owner) or ("", "")
    if not identifier(name) or not identifier(marketplace):
        raise PluginError(f"invalid agent projection owner: {owner}")
    if entry.version is not None and not re.fullmatch(r"[A-Za-z0-9._+-]{1,256}", entry.version) or entry.version in {".", ".."}:
        raise PluginError(f"{owner}: installed plugin has an invalid payload version")
    base = codex_home / "plugins" / "cache" / marketplace / name
    if entry.root is not None:
        root = entry.root
    elif entry.version is not None:
        root = base / entry.version
    else:
        raise PluginError(f"{owner}: installed plugin has no usable payload version")
    if root == base or base not in root.parents or not root.is_dir() or root.is_symlink():
        raise PluginError(f"{owner}: installed plugin payload is outside its native cache owner")
    for relative in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json", "plugin.json"):
        candidate = root / relative
        if candidate.is_file():
            try:
                metadata = json.loads(candidate.read_bytes())
            except ValueError as exc:
                raise PluginError(f"{owner}: installed plugin manifest is unreadable") from exc
            if not isinstance(metadata, dict) or metadata.get("name") != name:
                raise PluginError(f"{owner}: installed plugin payload identity differs from native inventory")
            if entry.version is not None and metadata.get("version") != entry.version:
                raise PluginError(f"{owner}: installed plugin payload version differs from native inventory")
            return root
    raise PluginError(f"{owner}: installed plugin payload lacks a plugin manifest")


def run_agents(manifest: Manifest, native: NativeClient, options: Options, codex_home: Path, admission: Callable[[], None]) -> Report:
    """Project the custom agents of selected, enabled Codex plugins into Codex discovery."""
    report = Report()
    try:
        _run_agents(manifest, native, options, codex_home, admission, report)
    except (PluginError, agent_install.AgentInstallError, plugin_port.PluginPortError, OSError) as exc:
        report.failures.append(f"codex agents: {exc}")
    report.verified = report.succeeded() and not options.dry_run
    return report


def _run_agents(manifest: Manifest, native: NativeClient, options: Options, codex_home: Path, admission: Callable[[], None], report: Report) -> None:
    ledger = codex_home / AGENT_INTENT
    original = _read_optional(ledger)
    try:
        intent = json.loads(original) if original is not None else {"schema_version": 1, "owners": []}
    except ValueError as exc:
        raise PluginError("invalid agent projection intent") from exc
    if not isinstance(intent, dict) or set(intent) != {"schema_version", "owners"} or intent["schema_version"] != 1 \
            or not isinstance(intent["owners"], list) or any(not isinstance(owner, str) or qualified(owner) is None for owner in intent["owners"]):
        raise PluginError("invalid agent projection intent")
    owners_intent = set(intent["owners"])
    if not manifest.project_agents and not owners_intent:
        return
    installed = native.installed(manifest)
    desired: dict[str, Path] = {}
    if manifest.project_agents:
        for spec in manifest.client_specs("codex", options.platform):
            required = set(active_refs(spec.selection.required, options.profiles))
            for owner, entry in installed.items():
                name, marketplace = qualified(owner) or ("", "")
                if marketplace == spec.marketplace and entry.enabled and (spec.selection.mode == "all" or name in required):
                    desired[owner] = codex_payload_root(codex_home, owner, entry)

    def plan(owner: str) -> agent_install.AgentPlan:
        documents: dict[str, str] = {}
        if owner in desired:
            package = plugin_port.detect_plugin(desired[owner])
            models = dict(manifest.agent_models.get(owner, {}))
            for document in plugin_port.agent_documents(package.root, "codex", models, namespace=owner.split("@", 1)[0], source_host=package.host):
                documents[agent_install.document_filename(document.path)] = document.content
        return agent_install.plan(codex_home, owner, documents)

    def count(planned: agent_install.AgentPlan) -> int:
        return len(planned.changes) - (agent_install.RECEIPT in planned.changes)

    def save() -> None:
        nonlocal original
        original = _save_guarded(ledger, {"schema_version": 1, "owners": sorted(owners_intent)}, original)

    for owner in sorted(owners_intent | set(desired)):
        present = owner in desired
        operation = "project-plugin-agents" if present else "remove-plugin-agents"
        planned = plan(owner)
        if options.verify_only:
            if count(planned) or not present:
                raise PluginError("selected plugin agents require reconciliation")
            continue
        if options.dry_run:
            if count(planned):
                report.actions.append(Action("codex", operation, owner))
            continue
        if present and owner not in owners_intent:
            admission()
            owners_intent.add(owner)
            save()
            report.changed = True
        action = Action("codex", operation, owner)
        report.actions.append(action)
        if planned.changes:
            admission()
            agent_install.apply(planned)
            report.changed = True
        if count(plan(owner)):
            raise PluginError(f"{owner}: agent projection did not converge; intent retained")
        action.applied = True
        if not present:
            admission()
            owners_intent.discard(owner)
            save()
            report.changed = True


# --------------------------------------------------------------------------- Cursor local folders


@dataclasses.dataclass(frozen=True)
class Origin:
    marketplace: str
    source: str
    ref: str | None
    sparse_paths: tuple[str, ...]

    def records(self, receipt: Mapping[str, object]) -> bool:
        # Sparse paths only narrow the checkout; they never change a plugin's bytes.
        return normalize_source(str(receipt["source"])) == normalize_source(self.source) and receipt.get("ref") == self.ref


@dataclasses.dataclass
class Checkout:
    root: Path
    sparse: bool
    commit: str
    catalog: dict[str, tuple[str | None, bool]]  # name -> (relative source, incompatible)


def _relative(path: object) -> str:
    if not isinstance(path, str) or not path or "\\" in path or len(path) > 4096:
        raise PluginError("plugin source must name a repository directory")
    parts = [part for part in path.split("/") if part not in ("", ".")]
    if not parts or path.startswith("/") or ".." in parts:
        raise PluginError("plugin source must stay inside its repository")
    return "/".join(parts)


def tree_entries(root: Path) -> list[tuple[str, Path, os.stat_result | None]]:
    """Every entry below root sorted by its /-joined UTF-8 path; links and special files are refused."""
    entries: list[tuple[str, Path, os.stat_result | None]] = []
    pending = [(root, "")]
    total = 0
    while pending:
        directory, prefix = pending.pop()
        with os.scandir(directory) as listing:
            items = list(listing)
        for item in items:
            relative = f"{prefix}/{item.name}" if prefix else item.name
            try:
                relative.encode("utf-8")
            except UnicodeError as exc:
                raise PluginError("plugin payload names must be UTF-8") from exc
            metadata = item.stat(follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise PluginError("plugin payload contains a symbolic link")
            if stat.S_ISDIR(metadata.st_mode):
                pending.append((Path(item.path), relative))
                entries.append((relative, Path(item.path), None))
            elif stat.S_ISREG(metadata.st_mode):
                total += metadata.st_size
                entries.append((relative, Path(item.path), metadata))
            else:
                raise PluginError("plugin payload contains a special file")
            if len(entries) > CURSOR_MAX_ENTRIES or total > CURSOR_MAX_BYTES:
                raise PluginError("plugin payload exceeds its size bound")
    return sorted(entries, key=lambda entry: entry[0].encode("utf-8"))


def tree_digest(root: Path) -> str:
    """SHA-256 over sorted entries: d\\0<path>\\0 per directory, f\\0<path>\\0<x|->\\0<length>\\0<bytes> per file."""
    digest = hashlib.sha256()
    for relative, path, metadata in tree_entries(root):
        if metadata is None:
            digest.update(b"d\0" + relative.encode() + b"\0")
            continue
        executable = os.name != "nt" and bool(metadata.st_mode & 0o111)
        digest.update(b"f\0" + relative.encode() + (b"\0x\0" if executable else b"\0-\0") + str(metadata.st_size).encode() + b"\0")
        read = 0
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                read += len(chunk)
                digest.update(chunk)
        if read != metadata.st_size:
            raise PluginError("plugin payload changed during observation")
    return "sha256:" + digest.hexdigest()


def copy_tree(source: Path, destination: Path) -> None:
    entries = tree_entries(source)
    destination.mkdir(mode=0o755)
    for relative, path, metadata in entries:
        target = destination / relative
        if metadata is None:
            target.mkdir(mode=0o755)
        else:
            shutil.copyfile(path, target)
            target.chmod(0o755 if metadata.st_mode & 0o111 else 0o644)


def _renameat2(source: Path, target: Path, flag: int) -> bool:
    """Linux renameat2(2); False when the platform or filesystem lacks it, so the caller falls back."""
    if not sys.platform.startswith("linux"):
        return False
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, "renameat2", None)
    if function is None:
        return False
    at_fdcwd = -100
    if function(at_fdcwd, os.fsencode(source), at_fdcwd, os.fsencode(target), flag) == 0:
        return True
    error = ctypes.get_errno()
    if error in (22, 38, 95):  # EINVAL, ENOSYS, EOPNOTSUPP: unsupported here
        return False
    raise OSError(error, os.strerror(error), str(target))


def rename_noreplace(source: Path, target: Path) -> None:
    if _renameat2(source, target, 1):  # RENAME_NOREPLACE
        return
    if target.exists() or target.is_symlink():
        raise FileExistsError(17, "an entry appeared at the target", str(target))
    os.rename(source, target)


def exchange(staged: Path, target: Path, displaced: Path) -> Path:
    """Swap staged into target; return where the previous target now is.

    Linux exchanges atomically. Elsewhere the previous copy moves aside first and is put
    back if the second move fails; an interruption between the two moves is repaired by
    the next run, which restores the displaced copy before clearing staging.
    """
    if _renameat2(staged, target, 2):  # RENAME_EXCHANGE
        return staged
    os.rename(target, displaced)
    try:
        os.rename(staged, target)
    except OSError:
        os.rename(displaced, target)
        raise
    return displaced


class CursorClient:
    def __init__(self, home: Path, git: Path | None, environment: Mapping[str, str], stop: Callable[[], None]):
        self.home, self.git_command, self.environment, self.stop = home, git, environment, stop
        self.plugins = home / "plugins"
        self.local_root = self.plugins / "local"
        self.ledger_path = self.plugins / CURSOR_LEDGER

    def read_ledger(self) -> tuple[dict, bytes | None]:
        for directory in (self.plugins, self.local_root):
            if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
                raise PluginError("Cursor plugin directories must be real directories")
        raw = _read_optional(self.ledger_path)
        if raw is None:
            return {"schema_version": 1, "plugins": {}, "pending": {}}, None
        try:
            ledger = json.loads(raw)
        except ValueError as exc:
            raise PluginError("unsupported Cursor plugin receipt ledger") from exc
        if not isinstance(ledger, dict) or ledger.get("schema_version") != 1 or set(ledger) - {"schema_version", "plugins", "pending"} \
                or not isinstance(ledger.get("plugins"), dict) or not isinstance(ledger.setdefault("pending", {}), dict):
            raise PluginError("unsupported Cursor plugin receipt ledger")
        fields = {"plugin", "marketplace_id", "source", "ref", "sparse_paths", "commit", "path", "version", "digest"}
        for name, receipt in [*ledger["plugins"].items(), *ledger["pending"].items()]:
            parts = qualified(receipt.get("plugin", "")) if isinstance(receipt, dict) else None
            if not isinstance(receipt, dict) or set(receipt) != fields or parts is None or parts[0] != name \
                    or not identifier(name) or not identifier(parts[1]) or not COMMIT.fullmatch(str(receipt["commit"])) \
                    or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(receipt["digest"])) \
                    or not isinstance(receipt["source"], str) or not isinstance(receipt["marketplace_id"], str) \
                    or not (receipt["ref"] is None or isinstance(receipt["ref"], str)) \
                    or not (receipt["version"] is None or isinstance(receipt["version"], str)) \
                    or not isinstance(receipt["sparse_paths"], list) or any(not isinstance(item, str) for item in receipt["sparse_paths"]):
                raise PluginError("invalid Cursor plugin receipt")
            _relative(receipt["path"])
        return ledger, raw

    def save(self, ledger: dict, original: bytes | None) -> bytes:
        if _read_optional(self.ledger_path) != original:
            raise PluginError("Cursor plugin receipts changed during reconciliation")
        stored = {"schema_version": 1, "plugins": ledger["plugins"]}
        if ledger["pending"]:
            stored["pending"] = ledger["pending"]
        encoded = (json.dumps(stored, indent=2) + "\n").encode()
        with tempfile.NamedTemporaryFile("wb", dir=self.plugins, prefix=CURSOR_LEDGER_STAGE, delete=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        try:
            os.replace(temporary, self.ledger_path)
        finally:
            temporary.unlink(missing_ok=True)
        return encoded

    def clear_residue(self) -> None:
        if not self.plugins.is_dir():
            return
        for entry in self.plugins.iterdir():
            if entry.name.startswith(CURSOR_STAGE) and entry.is_dir() and not entry.is_symlink():
                # An interrupted fallback replacement leaves the previous copy here; put it back first.
                for displaced in entry.glob("*" + DISPLACED):
                    target = self.local_root / displaced.name.removesuffix(DISPLACED)
                    if displaced.is_dir() and not displaced.is_symlink() and not target.exists() and not target.is_symlink():
                        os.rename(displaced, target)
                shutil.rmtree(entry)
            elif entry.name.startswith(CURSOR_LEDGER_STAGE) and entry.is_file() and not entry.is_symlink():
                entry.unlink()

    def ensure_directories(self) -> None:
        if not self.home.is_dir():
            self.home.mkdir()
        for directory in (self.plugins, self.local_root):
            if directory.is_symlink():
                raise PluginError("Cursor plugin directories must be real directories")
            directory.mkdir(exist_ok=True)

    def local(self, ledger: dict, name: str, marketplace: str) -> tuple[str, dict | None, bool]:
        """Classify plugins/local/<name>: absent, managed (with its receipt and cleanliness) or occupied."""
        target = self.local_root / name
        if not target.exists() and not target.is_symlink():
            return "absent", None, True
        if target.is_symlink() or not target.is_dir():
            return "occupied:an entry that is not a real directory", None, False
        receipt = ledger["plugins"].get(name)
        if receipt is None:
            return "occupied:an unmanaged directory", None, False
        if receipt["plugin"] != f"{name}@{marketplace}":
            return "occupied:another marketplace's managed plugin", None, False
        try:
            clean = tree_digest(target) == receipt["digest"]
        except (PluginError, OSError, UnicodeError):
            clean = False  # anything unreadable counts as a local edit and is never overwritten
        return "managed", receipt, clean

    def git(self, step: str, arguments: Sequence[str], timeout: int) -> str:
        if self.git_command is None:
            raise PluginError("Git is required to fetch Cursor marketplaces")
        self.stop()
        try:
            completed = bounded_run([str(self.git_command), *arguments], environment=self.environment, cwd=None, timeout=timeout, stop=self.stop)
        except Cancelled:
            raise
        except PluginError as exc:
            raise PluginError(f"Git {step}: {exc}") from exc
        if completed.returncode:
            detail = failure_detail(completed)
            raise PluginError(f"Git {step} failed" + (f": {detail}" if detail else ""))
        return completed.stdout

    def fetch(self, origin: Origin, timeout: int, scratch: Path) -> Checkout:
        for value in (origin.source, origin.ref, *origin.sparse_paths):
            if value is not None:
                operand(value)
        root = Path(tempfile.mkdtemp(prefix="cursor-marketplace-", dir=scratch)) / "checkout"
        self.git("init", ["init", "--quiet", "--template=", str(root)], READ_TIMEOUT)
        self.git("fetch", ["-C", str(root), "fetch", "--quiet", "--depth", "1", "--no-tags", "--", origin.source, origin.ref or "HEAD"], timeout)
        commit = self.git("rev-parse", ["-C", str(root), "rev-parse", "--verify", "--end-of-options", "FETCH_HEAD^{commit}"], READ_TIMEOUT).strip()
        if not COMMIT.fullmatch(commit):
            raise PluginError("Git returned an invalid commit")
        sparse = bool(origin.sparse_paths)
        if sparse:
            # Cone mode keeps top-level files and named directories; plugin directories follow on demand.
            paths = [path for path in origin.sparse_paths if path.rstrip("/") != ".cursor-plugin"]
            self.git("sparse-checkout", ["-C", str(root), "sparse-checkout", "set", ".cursor-plugin", *paths], READ_TIMEOUT)
        self.git("checkout", ["-C", str(root), "-c", "advice.detachedHead=false", "checkout", "--quiet", "--detach", commit], timeout)
        return Checkout(root, sparse, commit, self.catalog(root, origin.marketplace))

    @staticmethod
    def catalog(root: Path, marketplace: str) -> dict[str, tuple[str | None, bool]]:
        path = root / ".cursor-plugin" / "marketplace.json"
        if not path.is_file() or path.is_symlink():
            raise PluginError("fetched source has no .cursor-plugin/marketplace.json")
        try:
            value = json.loads(path.read_bytes())
        except ValueError as exc:
            raise PluginError("fetched Cursor marketplace is not valid JSON") from exc
        if not isinstance(value, dict) or value.get("name") != marketplace:
            raise PluginError("fetched Cursor marketplace name differs from the selection")
        if not isinstance(value.get("plugins"), list):
            raise PluginError("Cursor marketplace plugins must be an array")
        catalog: dict[str, tuple[str | None, bool]] = {}
        for item in value["plugins"]:
            name = item.get("name") if isinstance(item, dict) else None
            if not identifier(name) or len(name) > 256:
                raise PluginError("Cursor marketplace lists an invalid plugin name")
            if name in catalog:
                raise PluginError("Cursor marketplace lists a plugin twice")
            try:
                source = _relative(item.get("source")) if isinstance(item.get("source"), str) else None
            except PluginError:
                source = None
            versions = item.get("minClientVersions")
            # Minimum versions are not compared: which Cursor build will load the copy is unknown.
            catalog[name] = (source, isinstance(versions, dict) and versions.get("cursor") == "never")
        return catalog

    def published(self, checkout: Checkout, path: str) -> Path:
        path = _relative(path)
        if checkout.sparse and not (checkout.root / path).exists():
            self.git("sparse-checkout", ["-C", str(checkout.root), "sparse-checkout", "add", path], READ_TIMEOUT)
        current = checkout.root
        for part in path.split("/"):
            current = current / part
            if current.is_symlink() or not current.is_dir():
                raise PluginError("plugin source is absent from the fetched marketplace or is not a real directory")
        return current


class CursorRun:
    def __init__(self, manifest: Manifest, cursor: CursorClient, options: Options, report: Report, admission: Callable[[], None], scratch: Path):
        self.manifest, self.cursor, self.options, self.report, self.admission, self.scratch = manifest, cursor, options, report, admission, scratch
        self.ledger, self.original = cursor.read_ledger()
        self.observed: dict[str, tuple[str, dict | None, bool]] = {}
        self.blocked: set[str] = set()

    @property
    def mutating(self) -> bool:
        return not self.options.dry_run and not self.options.verify_only

    def run(self) -> None:
        if self.mutating:
            self.cursor.clear_residue()  # the coordination lock is held, so any staging here is stale
        self.settle_journal()
        if self.options.update:
            self.update()
        else:
            self.setup()
        for plugin, (kind, _, clean) in sorted(self.observed.items()):
            if kind == "managed" and not clean:
                self.report.deferred.append(
                    f"{plugin}: local edits since installation block the available update; they are preserved" if plugin in self.blocked
                    else f"{plugin}: local edits since installation are preserved and will not be overwritten")

    def settle_journal(self) -> None:
        if not self.ledger["pending"]:
            return
        if self.options.verify_only:
            raise PluginError("an interrupted Cursor plugin change needs a setup or update run to settle")
        recovered = []
        for name, receipt in list(self.ledger["pending"].items()):
            del self.ledger["pending"][name]
            target = self.cursor.local_root / name
            with contextlib.suppress(PluginError, OSError, UnicodeError):
                if target.is_dir() and not target.is_symlink() and tree_digest(target) == receipt["digest"]:
                    self.ledger["plugins"][name] = receipt
                    recovered.append(receipt["plugin"])
        for plugin in recovered:
            self.report.actions.append(Action("cursor", "recover-plugin", plugin))
        if self.mutating:
            self.admission()
            self.original = self.cursor.save(self.ledger, self.original)
            for action in self.report.actions:
                action.applied |= action.operation == "recover-plugin"
            self.report.changed |= bool(recovered)

    def observe(self, name: str, marketplace: str) -> tuple[str, dict | None, bool]:
        plugin = f"{name}@{marketplace}"
        if plugin not in self.observed:
            local = self.cursor.local(self.ledger, name, marketplace)
            if local[0].startswith("occupied:"):
                self.report.deferred.append(f"{plugin}: {local[0].split(':', 1)[1]} occupies plugins/local/{name}; it is preserved")
            self.observed[plugin] = local
        return self.observed[plugin]

    def desired(self, name: str, marketplace: str) -> str:
        if not identifier(name):
            raise PluginError("cursor plugin name is not a safe directory name")
        plugin = f"{name}@{marketplace}"
        if self.manifest.external_plugin("cursor", plugin):
            raise PluginError(f"{plugin}: external plugin cannot become desired state")
        return plugin

    def setup(self) -> None:
        for spec in self.manifest.client_specs("cursor", self.options.platform):
            try:
                self.setup_marketplace(spec)
            except PluginError as exc:
                if self.options.verify_only or isinstance(exc, Cancelled):
                    raise
                self.report.failures.append(f"cursor: {spec.marketplace}: {exc}")

    def setup_marketplace(self, spec: ClientSpec) -> None:
        origin = Origin(spec.marketplace, spec.registration.source or "", spec.registration.ref, spec.registration.sparse_paths)
        if spec.selection.mode == "all":
            if self.options.verify_only:
                self.report.deferred.append(f"{spec.marketplace}: verifying an all-plugin selection requires marketplace discovery")
                return
        else:
            missing, stale = [], []
            for name in active_refs(spec.selection.required, self.options.profiles):
                plugin = self.desired(name, spec.marketplace)
                kind, receipt, _ = self.observe(name, spec.marketplace)
                if kind == "absent":
                    missing.append(plugin)
                elif kind == "managed" and not origin.records(receipt):
                    stale.append(plugin)
            discover = bool(active_refs(spec.selection.available, self.options.profiles))
            if self.options.verify_only:
                if missing:
                    raise PluginError(f"{', '.join(missing)}: selected plugin is missing")
                if stale:
                    raise PluginError(f"{', '.join(stale)}: the installed copy does not record the selected source and ref")
                if discover:
                    self.report.deferred.append(f"{spec.marketplace}: validating available-only plugins requires marketplace discovery")
                return
            if not (missing or stale or discover):
                return
        checkout = self.cursor.fetch(origin, self.options.timeout, self.scratch)
        if spec.selection.mode == "all":
            names = [name for name, (_, incompatible) in checkout.catalog.items() if not incompatible]
            if not names:
                raise PluginError("selected marketplace has no available plugins")
        else:
            for name in active_refs(spec.selection.available, self.options.profiles):
                plugin = self.desired(name, spec.marketplace)
                if name not in checkout.catalog:
                    raise PluginError(f"{plugin}: selected available-only plugin is absent from its marketplace")
                if checkout.catalog[name][1]:
                    self.report.deferred.append(f"{plugin}: its marketplace marks it incompatible with Cursor; it is not installed")
            names = active_refs(spec.selection.required, self.options.profiles)
        for name in names:
            plugin = self.desired(name, spec.marketplace)
            kind, receipt, clean = self.observe(name, spec.marketplace)
            if kind.startswith("occupied:") or (kind == "managed" and origin.records(receipt)):
                continue
            path = self.publication(checkout, name, plugin, installed=receipt is not None)
            if path is None:
                continue
            change = ("install", None) if receipt is None else self.converge(checkout, path, receipt, clean, plugin)
            if change is not None:
                self.apply(checkout, name, spec.marketplace_id, origin, path, change)

    def publication(self, checkout: Checkout, name: str, plugin: str, *, installed: bool) -> str | None:
        if name not in checkout.catalog:
            if installed:
                self.report.deferred.append(f"{plugin}: no longer published by its marketplace; the installed copy is preserved")
            else:
                self.report.failures.append(f"cursor: {plugin}: required plugin is absent from its marketplace")
            return None
        source, incompatible = checkout.catalog[name]
        if incompatible:
            self.report.deferred.append(f"{plugin}: its marketplace marks it incompatible with Cursor; "
                                        + ("the installed copy is preserved" if installed else "it is not installed"))
            return None
        if source is None:
            self.report.failures.append(f"cursor: {plugin}: unsupported marketplace source form")
            return None
        return source

    def converge(self, checkout: Checkout, path: str, receipt: dict, clean: bool, plugin: str) -> tuple[str, dict | None] | None:
        try:
            candidate = tree_digest(self.cursor.published(checkout, path))
        except PluginError as exc:
            self.report.failures.append(f"cursor: {plugin}: {exc}")
            return None
        if candidate == receipt["digest"]:
            return "record", receipt
        if not clean:
            self.blocked.add(plugin)
            return None
        return "replace", receipt

    def update(self) -> None:
        declared: dict[str, tuple[Origin, str]] = {}
        for spec in self.manifest.client_specs("cursor", self.options.platform):
            declared[spec.marketplace] = (Origin(spec.marketplace, spec.registration.source or "", spec.registration.ref, spec.registration.sparse_paths), spec.marketplace_id)
        groups: dict[Origin, list[tuple[str, dict, bool, str]]] = {}
        for name, receipt in sorted(self.ledger["plugins"].items()):
            if self.manifest.external_plugin("cursor", receipt["plugin"]):
                continue
            marketplace = receipt["plugin"].split("@", 1)[1]
            try:
                kind, current, clean = self.observe(name, marketplace)
            except (PluginError, OSError) as exc:
                self.report.failures.append(f"cursor: {receipt['plugin']}: {exc}")
                continue
            if kind != "managed":
                continue
            origin, marketplace_id = declared.get(marketplace) or (
                Origin(marketplace, current["source"], current["ref"], tuple(current["sparse_paths"])), current["marketplace_id"])
            groups.setdefault(origin, []).append((name, current, clean, marketplace_id))
        for origin, members in groups.items():
            try:
                checkout = self.cursor.fetch(origin, self.options.timeout, self.scratch)
            except PluginError as exc:
                if isinstance(exc, Cancelled):
                    raise
                self.report.failures.append(f"cursor: {origin.marketplace}: {exc}")
                continue
            for name, receipt, clean, marketplace_id in members:
                plugin = receipt["plugin"]
                recorded = origin.records(receipt)
                if recorded and checkout.commit == receipt["commit"]:
                    continue
                path = self.publication(checkout, name, plugin, installed=True)
                if path is None:
                    continue
                change = self.converge(checkout, path, receipt, clean, plugin)
                if change is None or (change[0] == "record" and recorded):
                    continue  # same origin and bytes at a newer commit: nothing to do
                self.apply(checkout, name, marketplace_id, origin, path, change)

    def apply(self, checkout: Checkout, name: str, marketplace_id: str, origin: Origin, path: str, change: tuple[str, dict | None]) -> None:
        plugin = f"{name}@{origin.marketplace}"
        kind, previous = change
        operation = {"install": "install-plugin", "replace": "update-plugin", "record": "record-plugin"}[kind]
        action = Action("cursor", operation, plugin)
        self.report.actions.append(action)
        if self.options.dry_run:
            return
        try:
            if kind == "record":
                self.admission()
                assert previous is not None
                self.ledger["plugins"][name] = {**previous, "marketplace_id": marketplace_id, "source": origin.source, "ref": origin.ref,
                                                "sparse_paths": list(origin.sparse_paths), "commit": checkout.commit, "path": path}
                self.original = self.cursor.save(self.ledger, self.original)
                preserved = None
            else:
                preserved = self.install(checkout, name, marketplace_id, origin, path, previous)
        except Cancelled:
            raise
        except (PluginError, OSError) as exc:
            self.report.failures.append(f"cursor: {operation} {plugin} failed: {exc}")
            return
        if preserved is not None:
            self.report.actions.pop()
            self.report.deferred.append(f"{plugin}: {preserved}")
            return
        action.applied = True
        self.report.changed = True
        current = self.cursor.local(self.ledger, name, origin.marketplace)
        if current[0] != "managed" or current[1]["commit"] != checkout.commit or not (current[2] or kind == "record"):
            self.report.failures.append(f"cursor: {operation} {plugin} did not verify")
        elif current[2]:
            self.observed.pop(plugin, None)

    def install(self, checkout: Checkout, name: str, marketplace_id: str, origin: Origin, path: str, replacing: dict | None) -> str | None:
        """Stage a verified copy, journal its receipt, move it into place, then record it. Returns a preservation reason."""
        source = self.cursor.published(checkout, path)
        expected = tree_digest(source)
        self.cursor.ensure_directories()
        stage = Path(tempfile.mkdtemp(prefix=CURSOR_STAGE, dir=self.cursor.plugins))
        keep_stage = False
        try:
            staged = stage / name
            copy_tree(source, staged)
            if tree_digest(staged) != expected:
                raise PluginError("staged plugin copy differs from the fetched source")
            try:
                metadata = json.loads((staged / ".cursor-plugin" / "plugin.json").read_bytes())
            except (OSError, ValueError) as exc:
                raise PluginError("plugin lacks a readable .cursor-plugin/plugin.json") from exc
            if not isinstance(metadata, dict) or metadata.get("name") != name:
                raise PluginError("plugin manifest name differs from its marketplace entry")
            version = metadata.get("version")
            if version is not None and (not isinstance(version, str) or len(version) > 256):
                raise PluginError("plugin manifest version is invalid")
            receipt = {"plugin": f"{name}@{origin.marketplace}", "marketplace_id": marketplace_id, "source": origin.source, "ref": origin.ref,
                       "sparse_paths": list(origin.sparse_paths), "commit": checkout.commit, "path": path, "version": version, "digest": expected}
            target = self.cursor.local_root / name
            self.admission()
            if replacing is None and (target.exists() or target.is_symlink()):
                return "an entry appeared at the target during installation; it is preserved"
            if replacing is not None and self._digest_or_none(target) != replacing["digest"]:
                return "local edits appeared before the update; they are preserved"
            self.ledger["pending"][name] = receipt
            try:
                self.original = self.cursor.save(self.ledger, self.original)
            except PluginError:
                del self.ledger["pending"][name]
                raise
            try:
                if replacing is None:
                    rename_noreplace(staged, target)
                else:
                    displaced = exchange(staged, target, stage / f"{name}{DISPLACED}")
                    if self._digest_or_none(displaced) != replacing["digest"]:
                        # The replaced copy changed after the check: put it back and keep the new copy staged.
                        try:
                            exchange(displaced, target, stage / f"{name}.incoming")
                        except OSError as exc:
                            keep_stage = True
                            kept = stage.with_name(f"{CURSOR_KEPT}{name}-{stage.name.removeprefix(CURSOR_STAGE)}")
                            with contextlib.suppress(OSError):
                                os.rename(stage, kept)
                                stage = kept
                            raise PluginError(f"local edits appeared during the update and could not be swapped back ({exc}); the edited copy is kept at {stage}") from exc
                        del self.ledger["pending"][name]
                        with contextlib.suppress(PluginError):
                            self.original = self.cursor.save(self.ledger, self.original)
                        return "local edits appeared during the update; they are preserved"
            except OSError as exc:
                del self.ledger["pending"][name]
                with contextlib.suppress(PluginError):
                    self.original = self.cursor.save(self.ledger, self.original)
                raise PluginError(f"cannot move the staged copy into place: {exc}") from exc
            self.ledger["plugins"][name] = receipt
            del self.ledger["pending"][name]
            try:
                self.original = self.cursor.save(self.ledger, self.original)
            except PluginError as exc:
                raise PluginError(f"{exc}; the journaled receipt settles on the next run") from exc
            return None
        finally:
            if not keep_stage:
                shutil.rmtree(stage, ignore_errors=True)

    @staticmethod
    def _digest_or_none(path: Path) -> str | None:
        try:
            return tree_digest(path) if path.is_dir() and not path.is_symlink() else None
        except (PluginError, OSError, UnicodeError):
            return None


def run_cursor(manifest: Manifest, cursor: CursorClient, options: Options, admission: Callable[[], None]) -> Report:
    report = Report()
    try:
        if not cursor.home.is_absolute():
            raise PluginError("the Cursor home must be absolute")
        with tempfile.TemporaryDirectory(prefix="agent-plugins-cursor-") as scratch:
            CursorRun(manifest, cursor, options, report, admission, Path(scratch)).run()
    except Cancelled:
        report.failures.append("plugin task cancelled")
    except (PluginError, OSError) as exc:
        report.failures.append(f"cursor: {exc}")
    report.verified = report.succeeded() and not report.deferred and not options.dry_run
    return report


# --------------------------------------------------------------------------- command line


def platform_name() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    raise PluginError("unsupported plugin platform")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent-plugins", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=Path, help="Plugin selection manifest (schema_version 5).")
    parser.add_argument("--client", action="append", choices=CLIENTS, default=[], help="Client to reconcile; repeatable (default: all).")
    parser.add_argument("--profile", action="append", default=[], help="Active profile for profile-gated selections; repeatable.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--update", action="store_true", help="Update installed eligible plugins instead of installing selections.")
    modes.add_argument("--verify-only", action="store_true", help="Fail unless the selections are installed; never mutate.")
    parser.add_argument("--dry-run", action="store_true", help="Discover and report the operations without applying them.")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    parser.add_argument("--result-protocol", action="store_true", help="Emit UPDATE_ALL_ITEM and UPDATE_ALL_RESULT records (update mode only).")
    parser.add_argument("--defer-missing-client", action="store_true", help="Report an absent client as deferred instead of failed.")
    parser.add_argument("--timeout-seconds", type=int, default=600, help="Bound for each native mutation (reads are bounded to 30s).")
    parser.add_argument("--public-git-command", help="Exact Git executable exposed to clients (default: /usr/bin/git or PATH).")
    parser.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.verify_only and args.dry_run:
        parser.error("--verify-only and --dry-run are mutually exclusive")
    if args.result_protocol and (not args.update or args.format == "json"):
        parser.error("--result-protocol requires --update and human output")
    if not 1 <= args.timeout_seconds <= 86400:
        parser.error("--timeout-seconds must be between 1 and 86400")
    args.client = [client for client in CLIENTS if client in args.client] or list(CLIENTS)
    args.manifest = args.manifest.expanduser().absolute()
    return args


@contextlib.contextmanager
def coordination_lock(home: Path) -> Iterator[None]:
    """The lock install-all also takes, so the two never mutate plugin state at once."""
    path = install_all.lifecycle_lock_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise PluginError("plugin coordination path is not a regular file")
    with path.open("a+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise PluginError(f"another agent-plugin operation is running: {path}") from exc
        yield


def cursor_present(home: Path, environment: Mapping[str, str]) -> bool:
    # A ~/.cursor directory proves nothing: configuration tools create it for rules and skills.
    config = Path(environment.get("XDG_CONFIG_HOME") or home / ".config")
    return shutil.which("cursor-agent", path=environment.get("PATH")) is not None or (sys.platform.startswith("linux") and (config / "Cursor").is_dir())


def emit(report: Report, args: argparse.Namespace) -> None:
    out = sys.stdout
    if args.format == "json":
        out.write(json.dumps(report.as_dict()) + "\n")
        return
    for action in report.actions:
        prefix = "would-" if args.dry_run else "" if action.applied else "failed-"
        out.write(f"{action.client} {prefix}{action.operation} {action.resource}\n")
    for item in report.deferred:
        out.write(f"deferred {item}\n")
    for item in report.failures:
        out.write(f"failed {item}\n")
    if not (report.actions or report.deferred or report.failures):
        out.write("agent-plugins up-to-date\n")
    if not args.result_protocol:
        return
    if not args.dry_run:
        for action in report.actions:
            item = {"subject": f"{action.client} / {action.resource}", "action": action.operation,
                    "outcome": "passed" if action.applied else "failed", "before": None, "after": None}
            out.write("UPDATE_ALL_ITEM " + json.dumps(item, separators=(",", ":")) + "\n")

    def completed(cursor: bool) -> int:
        return sum(1 for a in report.actions if a.applied and (a.client == "cursor") == cursor and a.operation in {"update-plugin", "refresh-marketplace"})

    if "cursor" not in args.client:
        updates = f"{completed(False)} native plugin update command(s) completed"
    elif len(args.client) == 1:
        updates = f"{completed(True)} Cursor plugin copy update(s) completed"
    else:
        updates = f"{completed(False)} native plugin update command(s) and {completed(True)} Cursor plugin copy update(s) completed"
    detail = f"{updates}; {len(report.deferred)} item(s) deferred; {len(report.failures)} failure(s)"
    reason = (report.failures or report.deferred or [None])[0]
    if reason:
        detail += ": " + "".join(c for c in reason if c.isprintable())[:320]
    out.write("UPDATE_ALL_RESULT " + json.dumps({"outcome": report.outcome(args.dry_run), "detail": detail}, separators=(",", ":")) + "\n")


def native_environment(public_git: Path | None, home: Path) -> dict[str, str]:
    """The native clients' environment: the caller's, with the selected public Git routed first.

    With a public Git, inherited Git settings, tokens and credential helpers are dropped so
    marketplace fetches cannot use private credentials; SSH and the clients' own sign-in remain.
    """
    environment = {**os.environ, "HOME": str(home)}
    if public_git is None:
        return environment
    environment = {key: value for key, value in environment.items() if not key.upper().startswith("GIT_")
                   and key.upper() not in {"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"}}
    environment["PATH"] = str(public_git.parent) + os.pathsep + environment.get("PATH", os.defpath)
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
                       GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="credential.helper", GIT_CONFIG_VALUE_0="")
    return environment


def execute(args: argparse.Namespace, stopped: Callable[[], bool]) -> Report:
    def stop() -> None:
        if stopped():
            raise Cancelled("plugin task cancelled")

    home = args.home
    try:
        manifest = parse_manifest(args.manifest.read_bytes())
    except OSError as exc:
        raise PluginError(f"plugin selection manifest is unavailable: {exc}") from exc
    platform = platform_name()
    profiles = frozenset(args.profile)
    public_git = install_all.resolve_public_git(args.public_git_command) if args.public_git_command else None
    report = Report()
    lock = contextlib.nullcontext() if args.dry_run or args.verify_only else coordination_lock(home)
    with lock:
        def admission() -> None:
            stop()

        for client in args.client:
            if stopped():
                report.failures.append("plugin task cancelled")  # what already ran stays reported
                report.verified = False
                break
            options = Options(client, platform, profiles, args.update, args.dry_run, args.verify_only, args.timeout_seconds)
            if client == "cursor":
                if not cursor_present(home, os.environ):
                    (report.deferred if args.defer_missing_client else report.failures).append("cursor: missing client")
                    report.verified = False
                    continue
                found = public_git or (Path(git) if (git := shutil.which("git")) else None)
                if found is None:
                    report.failures.append("cursor: Git is required to fetch Cursor marketplaces; pass --public-git-command")
                    report.verified = False
                    continue
                # Cursor fetches are ours: no user Git configuration, credentials, SSH agent or prompts.
                with install_all.public_git_environment(found.resolve()) as isolated:
                    cursor = CursorClient(home / ".cursor", found, {**isolated, "HOME": str(home)}, stop)
                    report.append(run_cursor(manifest, cursor, options, admission))
                continue
            command = shutil.which(NATIVE_COMMAND[client], path=os.environ.get("PATH"))
            if command is None:
                (report.deferred if args.defer_missing_client else report.failures).append(f"{client}: missing client")
                report.verified = False
                continue
            base = native_environment(public_git, home)
            with (claude_npm_environment(base) if client == "claude-code" else contextlib.nullcontext(base)) as environment:
                native = NativeClient(client, Path(command), environment, home, stop)
                result = run_native(manifest, native, options, admission)
                report.append(result)
                if client == "codex" and result.succeeded():
                    if os.name == "nt":
                        if manifest.project_agents:
                            report.deferred.append("Codex agent projection requires a POSIX host")
                            report.verified = False
                        continue
                    codex_home = Path(os.environ.get("CODEX_HOME") or home / ".codex")
                    report.append(run_agents(manifest, native, options, codex_home, admission))
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    cancelled = False

    def handler(signum: int, frame: object) -> None:
        nonlocal cancelled
        cancelled = True

    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), handler)
    try:
        report = execute(args, lambda: cancelled)
    except (PluginError, install_all.InstallError, OSError) as exc:
        report = Report(failures=[str(exc)], verified=False)
    emit(report, args)
    return 0 if report.succeeded() else 1


if __name__ == "__main__":
    raise SystemExit(main())
