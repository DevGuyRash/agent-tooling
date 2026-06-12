#!/usr/bin/env python3
"""Convert Codex and Claude Code plugin packages and marketplaces.

The converter is intentionally conservative: it copies the entire source tree
first, rewrites only the active target-host surfaces, and records any semantic
loss or preserved-only component in .plugin-portability/report.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

try:
    import yaml
except Exception:  # pragma: no cover - exercised only on minimal hosts
    yaml = None  # type: ignore[assignment]


CODEX_MANIFEST = Path(".codex-plugin/plugin.json")
CLAUDE_MANIFEST = Path(".claude-plugin/plugin.json")
CODEX_MARKETPLACE = Path(".agents/plugins/marketplace.json")
CLAUDE_MARKETPLACE = Path(".claude-plugin/marketplace.json")
PORTABILITY_DIR = Path(".plugin-portability")
REPORT_NAME = "report.json"
REPORT_SCHEMA_VERSION = "1.0"
SKILL_ENTRYPOINT_NAMES = ("SKILL.md", "skill.md")

EXIT_USER_ERROR = 2
EXIT_VALIDATION_FAILED = 3
EXIT_EXTERNAL_TOOL_UNAVAILABLE = 4

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\."
    r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
HEX_COLOR_RE = re.compile(r"^#[0-9A-F]{6}$", re.IGNORECASE)

CODEX_ALLOWED_MANIFEST_KEYS = {
    "id",
    "name",
    "version",
    "description",
    "skills",
    "apps",
    "mcpServers",
    "interface",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
}

CODEX_ALLOWED_INTERFACE_KEYS = {
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "capabilities",
    "websiteURL",
    "privacyPolicyURL",
    "termsOfServiceURL",
    "brandColor",
    "composerIcon",
    "logo",
    "screenshots",
    "defaultPrompt",
    "default_prompt",
}

CODEX_EVENTS = {
    "SessionStart",
    "SubagentStart",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "UserPromptSubmit",
    "SubagentStop",
    "Stop",
}

CLAUDE_DEFAULT_COMPONENTS = {
    "skills": Path("skills"),
    "commands": Path("commands"),
    "agents": Path("agents"),
    "hooks": Path("hooks/hooks.json"),
    "mcpServers": Path(".mcp.json"),
    "lspServers": Path(".lsp.json"),
    "outputStyles": Path("output-styles"),
    "themes": Path("themes"),
    "monitors": Path("monitors/monitors.json"),
    "bin": Path("bin"),
    "settings": Path("settings.json"),
}


class PluginPortError(RuntimeError):
    """Expected, user-facing converter failure."""

    def __init__(self, message: str, *, exit_code: int = EXIT_USER_ERROR) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class Report:
    source: str
    target: str
    source_root: str
    output_root: str
    mode: str
    schema_version: str = REPORT_SCHEMA_VERSION
    status: str = "success"
    support_level: str = "supported"
    warnings: list[str] = field(default_factory=list)
    unsupported: list[dict[str, Any]] = field(default_factory=list)
    preserved_only: list[dict[str, Any]] = field(default_factory=list)
    mappings: list[dict[str, Any]] = field(default_factory=list)
    files_copied: list[str] = field(default_factory=list)
    validations: list[dict[str, Any]] = field(default_factory=list)
    validation_summary: dict[str, Any] = field(default_factory=dict)
    executable_surfaces: list[dict[str, Any]] = field(default_factory=list)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def add_unsupported(self, kind: str, path: str, reason: str, *, active: bool = False) -> None:
        item = {"kind": kind, "path": path, "reason": reason, "active_in_target": active}
        if item not in self.unsupported:
            self.unsupported.append(item)

    def add_preserved(self, kind: str, path: str, reason: str) -> None:
        item = {"kind": kind, "path": path, "reason": reason}
        if item not in self.preserved_only:
            self.preserved_only.append(item)

    def add_mapping(self, source: str, target: str, reason: str) -> None:
        self.mappings.append({"source": source, "target": target, "reason": reason})

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "target": self.target,
            "source_root": self.source_root,
            "output_root": self.output_root,
            "mode": self.mode,
            "status": self.status,
            "support_level": self.support_level,
            "warnings": self.warnings,
            "unsupported": self.unsupported,
            "preserved_only": self.preserved_only,
            "mappings": self.mappings,
            "files_copied": self.files_copied,
            "validations": self.validations,
            "validation_summary": self.validation_summary,
            "executable_surfaces": self.executable_surfaces,
        }

    def summary_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "target": self.target,
            "source_root": self.source_root,
            "output_root": self.output_root,
            "mode": self.mode,
            "status": self.status,
            "support_level": self.support_level,
            "warnings_count": len(self.warnings),
            "unsupported_count": len(self.unsupported),
            "preserved_only_count": len(self.preserved_only),
            "executable_surfaces_count": len(self.executable_surfaces),
            "validation_summary": self.validation_summary,
        }


@dataclass
class PluginPackage:
    root: Path
    host: str
    name: str
    codex_manifest: dict[str, Any] | None
    claude_manifest: dict[str, Any] | None
    components: dict[str, list[str]]
    files: list[str]


def die(message: str, *, exit_code: int = EXIT_USER_ERROR) -> None:
    raise PluginPortError(message, exit_code=exit_code)


def load_json(path: Path, *, exit_code: int = EXIT_USER_ERROR) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"{path}: invalid JSON: {exc}", exit_code=exit_code)
    if not isinstance(data, dict):
        die(f"{path}: expected a JSON object", exit_code=exit_code)
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def slugify(value: str, *, fallback: str = "plugin") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = fallback
    return slug[:64].strip("-") or fallback


def display_name(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def first_text_paragraph(markdown: str) -> str:
    for block in re.split(r"\n\s*\n", markdown.strip()):
        text = " ".join(line.strip("#*` -") for line in block.splitlines()).strip()
        if text:
            return text
    return ""


def safe_description(value: str, fallback: str) -> str:
    value = " ".join(str(value or "").split())
    if not value:
        value = fallback
    return value[:1024]


def ensure_yaml() -> None:
    if yaml is None:
        die("PyYAML is required for plugin YAML/frontmatter conversion")


def load_yaml_text(text: str, *, path: Path) -> dict[str, Any]:
    ensure_yaml()
    if not text.strip():
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        die(f"{path}: YAML frontmatter failed to parse: {exc}")
    if data is None:
        return {}
    if not isinstance(data, dict):
        die(f"{path}: YAML frontmatter must be a mapping")
    return dict(data)


def dump_yaml_data(data: dict[str, Any]) -> str:
    ensure_yaml()
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=False).strip()


def split_frontmatter(path: Path) -> tuple[dict[str, Any], str, bool, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text, False, ""
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text, False, ""
    raw = text[4:end]
    after = text[end + len("\n---") :]
    if after.startswith("\n"):
        after = after[1:]
    return load_yaml_text(raw, path=path), after, True, raw


def split_frontmatter_unparsed(path: Path) -> tuple[str, str, bool]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return "", text, False
    end = text.find("\n---", 4)
    if end == -1:
        return "", text, False
    raw = text[4:end]
    after = text[end + len("\n---") :]
    if after.startswith("\n"):
        after = after[1:]
    return raw, after, True


def split_component_frontmatter(
    path: Path,
    root: Path,
    report: Report,
    *,
    kind: str,
    mode: str,
) -> tuple[dict[str, Any], str, bool, str]:
    try:
        return split_frontmatter(path)
    except PluginPortError as exc:
        if mode == "strict":
            raise
        raw_frontmatter, body, had_frontmatter = split_frontmatter_unparsed(path)
        rel = path.relative_to(root).as_posix()
        report.warn(f"{rel}: invalid Claude {kind} frontmatter ignored during best-effort conversion")
        report.add_unsupported(
            f"{kind}-frontmatter",
            rel,
            f"Frontmatter could not be parsed and was replaced with generated metadata: {exc}",
            active=True,
        )
        return {}, body, had_frontmatter, raw_frontmatter


def write_frontmatter(path: Path, data: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{dump_yaml_data(data)}\n---\n\n{body.lstrip()}", encoding="utf-8")


# A command already written against the dual-host fallback is correct on BOTH
# hosts; rewriting either variable inside it degrades portability (observed:
# claude->codex turned it into the degenerate ${PLUGIN_ROOT:-${PLUGIN_ROOT}}).
DUAL_HOST_ROOT = "${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}"
_DUAL_HOST_SENTINEL = "\x00plugin-port-dual-root\x00"


def recursive_replace(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        result = value.replace(DUAL_HOST_ROOT, _DUAL_HOST_SENTINEL)
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result.replace(_DUAL_HOST_SENTINEL, DUAL_HOST_ROOT)
    if isinstance(value, list):
        return [recursive_replace(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: recursive_replace(item, replacements) for key, item in value.items()}
    return value


def is_relative_file_ref(value: str) -> bool:
    return value.startswith("./") or value.startswith("../")


def claude_plugin_root_ref(value: str) -> str:
    if value.startswith("./"):
        return "${CLAUDE_PLUGIN_ROOT}/" + value[2:]
    if value.startswith("../"):
        return "${CLAUDE_PLUGIN_ROOT}/" + value
    return value


def normalize_claude_mcp_servers(servers: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for name, server in servers.items():
        if not isinstance(server, dict):
            normalized[name] = server
            continue
        server_out = dict(server)
        cwd = server_out.get("cwd")
        if isinstance(cwd, str) and cwd.strip() in ("", ".", "./"):
            server_out["cwd"] = "${CLAUDE_PLUGIN_ROOT}"
        command = server_out.get("command")
        if isinstance(command, str) and is_relative_file_ref(command):
            server_out["command"] = claude_plugin_root_ref(command)
        args = server_out.get("args")
        if isinstance(args, list):
            server_out["args"] = [
                claude_plugin_root_ref(arg) if isinstance(arg, str) and is_relative_file_ref(arg) else arg
                for arg in args
            ]
        normalized[name] = server_out
    return normalized


def normalize_mcp_config(data: dict[str, Any], *, target: str) -> dict[str, Any]:
    if "mcpServers" in data and isinstance(data["mcpServers"], dict):
        servers = data["mcpServers"]
    elif "mcp_servers" in data and isinstance(data["mcp_servers"], dict):
        servers = data["mcp_servers"]
    else:
        ignored = {"metadata", "$schema"}
        servers = {key: value for key, value in data.items() if key not in ignored}
    replacements = (
        {
            "${CLAUDE_PLUGIN_ROOT}": "${PLUGIN_ROOT}",
            "$CLAUDE_PLUGIN_ROOT": "$PLUGIN_ROOT",
            "${CLAUDE_PLUGIN_DATA}": "${PLUGIN_DATA}",
            "$CLAUDE_PLUGIN_DATA": "$PLUGIN_DATA",
        }
        if target == "codex"
        else {
            "${PLUGIN_ROOT}": "${CLAUDE_PLUGIN_ROOT}",
            "$PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}",
            "${PLUGIN_DATA}": "${CLAUDE_PLUGIN_DATA}",
            "$PLUGIN_DATA": "${CLAUDE_PLUGIN_DATA}",
        }
    )
    normalized = recursive_replace(servers, replacements)
    if target == "claude":
        normalized = normalize_claude_mcp_servers(normalized)
    return {"mcpServers": normalized}


def rel_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() or path.is_symlink():
            files.append(path.relative_to(root).as_posix())
    return files


def report_support_level(report: Report) -> str:
    if report.unsupported:
        return "best-effort-lossy" if report.mode == "best-effort" else "unsupported"
    if report.preserved_only:
        return "supported-with-preserved-surfaces"
    return "supported"


def add_surface(surfaces: list[dict[str, Any]], kind: str, path: Path, root: Path, reason: str, *, active: bool) -> None:
    if not path.exists():
        return
    item = {
        "kind": kind,
        "path": path.relative_to(root).as_posix(),
        "active_in_target": active,
        "reason": reason,
    }
    if item not in surfaces:
        surfaces.append(item)


def collect_executable_surfaces(root: Path, target: str) -> list[dict[str, Any]]:
    surfaces: list[dict[str, Any]] = []
    add_surface(
        surfaces,
        "hooks",
        root / "hooks" / "hooks.json",
        root,
        "Hook command handlers may execute during plugin runtime",
        active=True,
    )
    add_surface(
        surfaces,
        "hooks",
        root / "hooks.json",
        root,
        "Hook command handlers may execute during plugin runtime",
        active=True,
    )
    add_surface(
        surfaces,
        "mcp",
        root / ".mcp.json",
        root,
        "MCP server definitions may launch local or remote processes",
        active=True,
    )
    add_surface(
        surfaces,
        "apps",
        root / ".app.json",
        root,
        "Codex app connector mappings may require install-time or use-time auth",
        active=target == "codex",
    )
    add_surface(
        surfaces,
        "bin",
        root / "bin",
        root,
        "Plugin bin files may be invoked by plugin commands or runtime helpers",
        active=target == "claude",
    )
    add_surface(
        surfaces,
        "scripts",
        root / "scripts",
        root,
        "Copied scripts may be invoked by hooks, commands, or MCP servers",
        active=True,
    )
    add_surface(
        surfaces,
        "settings",
        root / "settings.json",
        root,
        "Claude settings may affect plugin runtime behavior",
        active=target == "claude",
    )
    for rel in (
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "uv.lock",
    ):
        add_surface(
            surfaces,
            "dependency-manifest",
            root / rel,
            root,
            "Dependency manifest may influence runtime installation or execution",
            active=False,
        )
    return surfaces


def finalize_report(report: Report, root: Path) -> Report:
    target_host = report.target.removesuffix("-marketplace").removesuffix("-validation")
    report.executable_surfaces = collect_executable_surfaces(root, target_host)
    report.support_level = report_support_level(report)
    report.files_copied = rel_files(root)
    return report


def skill_entrypoint_path(skill_dir: Path) -> Path | None:
    for filename in SKILL_ENTRYPOINT_NAMES:
        path = skill_dir / filename
        if path.is_file():
            return path
    return None


def skill_entrypoint_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    root_skill = skill_entrypoint_path(root)
    if root_skill is not None:
        paths.append(root_skill)
    skills_dir = root / "skills"
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir(), key=lambda path: path.name):
            if not skill_dir.is_dir():
                continue
            skill = skill_entrypoint_path(skill_dir)
            if skill is not None:
                paths.append(skill)
    return paths


def component_inventory(root: Path) -> dict[str, list[str]]:
    components: dict[str, list[str]] = {
        "skills": [],
        "commands": [],
        "agents": [],
        "hooks": [],
        "mcpServers": [],
        "apps": [],
        "lspServers": [],
        "outputStyles": [],
        "themes": [],
        "monitors": [],
        "bin": [],
        "settings": [],
        "assets": [],
    }
    for skill in skill_entrypoint_paths(root):
        components["skills"].append(skill.relative_to(root).as_posix())
    commands_dir = root / "commands"
    if commands_dir.exists():
        for command in sorted(commands_dir.rglob("*.md")):
            components["commands"].append(command.relative_to(root).as_posix())
    agents_dir = root / "agents"
    if agents_dir.exists():
        for agent in sorted(agents_dir.rglob("*.md")):
            components["agents"].append(agent.relative_to(root).as_posix())
    for hook in (root / "hooks").glob("*.json") if (root / "hooks").exists() else []:
        components["hooks"].append(hook.relative_to(root).as_posix())
    if (root / "hooks.json").exists():
        components["hooks"].append("hooks.json")
    if (root / ".mcp.json").exists():
        components["mcpServers"].append(".mcp.json")
    if (root / ".app.json").exists():
        components["apps"].append(".app.json")
    if (root / ".lsp.json").exists():
        components["lspServers"].append(".lsp.json")
    output_styles = root / "output-styles"
    if output_styles.exists():
        components["outputStyles"].extend(
            path.relative_to(root).as_posix() for path in sorted(output_styles.rglob("*.md"))
        )
    themes = root / "themes"
    if themes.exists():
        components["themes"].extend(
            path.relative_to(root).as_posix() for path in sorted(themes.rglob("*.json"))
        )
    monitors = root / "monitors"
    if monitors.exists():
        components["monitors"].extend(
            path.relative_to(root).as_posix() for path in sorted(monitors.rglob("*.json"))
        )
    bin_dir = root / "bin"
    if bin_dir.exists():
        components["bin"].extend(
            path.relative_to(root).as_posix() for path in sorted(bin_dir.rglob("*")) if path.is_file()
        )
    if (root / "settings.json").exists():
        components["settings"].append("settings.json")
    assets = root / "assets"
    if assets.exists():
        components["assets"].extend(
            path.relative_to(root).as_posix() for path in sorted(assets.rglob("*")) if path.is_file()
        )
    return {key: values for key, values in components.items() if values}


def detect_plugin(root: Path, *, explicit_host: str | None = None) -> PluginPackage:
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        die(f"{root}: plugin path must be an existing directory")
    codex_manifest = load_json(root / CODEX_MANIFEST) if (root / CODEX_MANIFEST).exists() else None
    claude_manifest = load_json(root / CLAUDE_MANIFEST) if (root / CLAUDE_MANIFEST).exists() else None
    components = component_inventory(root)

    if explicit_host:
        host = explicit_host
    elif codex_manifest and not claude_manifest:
        host = "codex"
    elif claude_manifest and not codex_manifest:
        host = "claude"
    elif codex_manifest and claude_manifest:
        host = "dual"
    elif any((root / rel).exists() for rel in CLAUDE_DEFAULT_COMPONENTS.values()):
        host = "claude"
    else:
        die(f"{root}: no Codex or Claude plugin manifest/components found")

    manifest = codex_manifest or claude_manifest or {}
    name = slugify(str(manifest.get("name") or root.name))
    return PluginPackage(
        root=root,
        host=host,
        name=name,
        codex_manifest=codex_manifest,
        claude_manifest=claude_manifest,
        components=components,
        files=rel_files(root),
    )


def target_manifest_name(pkg: PluginPackage, target: str) -> str:
    if target == "codex":
        source = pkg.codex_manifest or {}
        claude = pkg.claude_manifest or {}
        return slugify(str(source.get("name") or claude.get("name") or pkg.name))
    source = pkg.claude_manifest or {}
    codex = pkg.codex_manifest or {}
    return slugify(str(source.get("name") or codex.get("name") or pkg.name))


def prepare_output(source: Path, output: Path, *, overwrite: bool) -> None:
    source = source.resolve()
    output = output.resolve()
    if output == source or source in output.parents:
        die("output path must not be the source path or inside the source tree")
    if output.exists():
        if not overwrite:
            die(f"{output}: output already exists; pass --overwrite to replace it")
        if output.is_dir():
            shutil.rmtree(output)
        else:
            output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, output, symlinks=True)


def read_skill_description(
    path: Path,
    root: Path,
    report: Report,
    *,
    mode: str,
) -> tuple[dict[str, Any], str, str, str]:
    try:
        frontmatter, body, _, raw_frontmatter = split_frontmatter(path)
    except PluginPortError as exc:
        if mode == "strict":
            raise
        raw_frontmatter, body, _ = split_frontmatter_unparsed(path)
        rel = path.relative_to(root).as_posix()
        report.warn(f"{rel}: invalid skill frontmatter ignored during best-effort conversion")
        report.add_unsupported(
            "skill-frontmatter",
            rel,
            f"Frontmatter could not be parsed and was replaced with generated metadata: {exc}",
            active=True,
        )
        frontmatter = {}
    fallback = first_text_paragraph(body) or f"Skill converted from {path.parent.name}."
    description = safe_description(str(frontmatter.get("description", "")), fallback)
    return frontmatter, body, description, raw_frontmatter


def merge_openai_yaml_policy(skill_dir: Path, *, allow_implicit: bool, name: str, description: str) -> None:
    path = skill_dir / "agents/openai.yaml"
    data: dict[str, Any] = {}
    if path.exists():
        data = load_yaml_text(path.read_text(encoding="utf-8"), path=path)
    data.setdefault("interface", {})
    data["interface"].setdefault("display_name", display_name(name))
    data["interface"].setdefault("short_description", description[:160])
    data.setdefault("policy", {})
    data["policy"]["allow_implicit_invocation"] = allow_implicit
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml_data(data) + "\n", encoding="utf-8")


def normalize_skill_entrypoint_filenames(root: Path, report: Report) -> None:
    candidates = [root]
    skills_dir = root / "skills"
    if skills_dir.exists():
        candidates.extend(path for path in sorted(skills_dir.iterdir(), key=lambda item: item.name) if path.is_dir())
    for skill_dir in candidates:
        lower = skill_dir / "skill.md"
        target = skill_dir / "SKILL.md"
        if not lower.is_file() or target.exists():
            continue
        lower.rename(target)
        report.add_mapping(
            lower.relative_to(root).as_posix(),
            target.relative_to(root).as_posix(),
            "Lowercase Claude skill entrypoint normalized to Codex SKILL.md",
        )


def normalize_codex_skills(root: Path, report: Report, *, mode: str) -> None:
    normalize_skill_entrypoint_filenames(root, report)
    skill_paths: list[Path] = []
    if (root / "SKILL.md").exists():
        root_skill_name = slugify(root.name)
        target = root / "skills" / root_skill_name / "SKILL.md"
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / "SKILL.md", target)
            report.add_mapping("SKILL.md", target.relative_to(root).as_posix(), "Codex plugins use skills/<name>/SKILL.md")
        skill_paths.append(target)
    skill_paths.extend(sorted((root / "skills").glob("*/SKILL.md")) if (root / "skills").exists() else [])

    for path in skill_paths:
        frontmatter, body, description, raw_frontmatter = read_skill_description(
            path,
            root,
            report,
            mode=mode,
        )
        skill_slug = slugify(path.parent.name)
        disable_model = bool(
            frontmatter.pop("disable-model-invocation", False)
            or frontmatter.pop("disable_model_invocation", False)
        )
        if "name" not in frontmatter or not str(frontmatter.get("name", "")).strip():
            frontmatter["name"] = skill_slug
        frontmatter["description"] = description
        if raw_frontmatter:
            report.add_mapping(
                path.relative_to(root).as_posix(),
                f"{PORTABILITY_DIR.as_posix()}/{REPORT_NAME}",
                "Original skill frontmatter recorded in report before Codex normalization",
            )
        write_frontmatter(path, frontmatter, body)
        if disable_model:
            merge_openai_yaml_policy(
                path.parent,
                allow_implicit=False,
                name=skill_slug,
                description=description,
            )
            report.add_mapping(
                path.relative_to(root).as_posix(),
                (path.parent / "agents/openai.yaml").relative_to(root).as_posix(),
                "Claude disable-model-invocation mapped to Codex allow_implicit_invocation=false",
            )


def normalize_claude_skills(root: Path, report: Report, *, mode: str) -> None:
    for path in sorted((root / "skills").glob("*/SKILL.md")) if (root / "skills").exists() else []:
        frontmatter, body, description, _ = read_skill_description(
            path,
            root,
            report,
            mode=mode,
        )
        openai_yaml = path.parent / "agents/openai.yaml"
        if openai_yaml.exists():
            data = load_yaml_text(openai_yaml.read_text(encoding="utf-8"), path=openai_yaml)
            policy = data.get("policy") if isinstance(data.get("policy"), dict) else {}
            if policy.get("allow_implicit_invocation") is False:
                frontmatter["disable-model-invocation"] = True
                report.add_mapping(
                    openai_yaml.relative_to(root).as_posix(),
                    path.relative_to(root).as_posix(),
                    "Codex allow_implicit_invocation=false mapped to Claude disable-model-invocation",
                )
        frontmatter.setdefault("description", description)
        write_frontmatter(path, frontmatter, body)


def normalize_claude_markdown_components(root: Path, report: Report, *, mode: str) -> None:
    for dirname, kind in (("commands", "command"), ("agents", "agent")):
        directory = root / dirname
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.md")):
            frontmatter, body, had_frontmatter, _ = split_component_frontmatter(
                path,
                root,
                report,
                kind=kind,
                mode=mode,
            )
            fallback = first_text_paragraph(body) or f"{display_name(slugify(path.stem))} {kind}."
            description = safe_description(str(frontmatter.get("description", "")), fallback)
            if frontmatter.get("description") == description and had_frontmatter:
                continue
            frontmatter["description"] = description
            write_frontmatter(path, frontmatter, body)
            report.add_mapping(
                path.relative_to(root).as_posix(),
                path.relative_to(root).as_posix(),
                f"Claude {kind} frontmatter normalized",
            )


def convert_commands_to_codex_skills(root: Path, report: Report, *, mode: str) -> None:
    commands_dir = root / "commands"
    if not commands_dir.exists():
        return
    for command in sorted(commands_dir.rglob("*.md")):
        frontmatter, body, _, _ = split_component_frontmatter(
            command,
            root,
            report,
            kind="command",
            mode=mode,
        )
        slug = slugify(command.stem)
        target = root / "skills" / slug / "SKILL.md"
        if target.exists():
            report.warn(f"Command {command.relative_to(root)} not converted because skill {slug} already exists")
            continue
        description = safe_description(
            str(frontmatter.get("description", "")),
            first_text_paragraph(body) or f"Command converted from /{slug}.",
        )
        write_frontmatter(
            target,
            {"name": slug, "description": description},
            body or f"Run the behavior previously exposed by /{slug}.\n",
        )
        report.add_mapping(
            command.relative_to(root).as_posix(),
            target.relative_to(root).as_posix(),
            "Claude flat command converted to Codex skill",
        )


def load_hooks_from_plugin(root: Path, manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    default = root / "hooks/hooks.json"
    if default.exists():
        return load_json(default)
    root_hooks = root / "hooks.json"
    if root_hooks.exists():
        return load_json(root_hooks)
    if manifest and "hooks" in manifest:
        hooks = manifest["hooks"]
        if isinstance(hooks, dict):
            return {"hooks": hooks} if "hooks" not in hooks else hooks
        if isinstance(hooks, str):
            path = root / hooks.removeprefix("./")
            if path.exists():
                return load_json(path)
    return None


def quote_command_with_args(command: str, args: list[Any]) -> str:
    return " ".join([shlex.quote(str(command)), *(shlex.quote(str(arg)) for arg in args)])


def convert_hooks_to_codex(data: dict[str, Any], report: Report, *, mode: str) -> dict[str, Any]:
    hooks = data.get("hooks", data)
    if not isinstance(hooks, dict):
        die("hooks config must contain a hooks object")
    converted: dict[str, list[dict[str, Any]]] = {}
    for event, groups in hooks.items():
        if event not in CODEX_EVENTS:
            reason = f"Codex does not support Claude hook event {event}"
            if mode == "strict":
                die(reason)
            report.add_unsupported("hook-event", f"hooks.{event}", reason)
            continue
        if not isinstance(groups, list):
            report.add_unsupported("hook-event", f"hooks.{event}", "hook event value is not a list")
            continue
        converted_groups: list[dict[str, Any]] = []
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict):
                report.add_unsupported("hook-group", f"hooks.{event}[{group_index}]", "hook group is not an object")
                continue
            out_group: dict[str, Any] = {}
            if "matcher" in group:
                out_group["matcher"] = group["matcher"]
            out_handlers: list[dict[str, Any]] = []
            handlers = group.get("hooks", [])
            if not isinstance(handlers, list):
                report.add_unsupported("hook-group", f"hooks.{event}[{group_index}].hooks", "handlers are not a list")
                continue
            for handler_index, handler in enumerate(handlers):
                ref = f"hooks.{event}[{group_index}].hooks[{handler_index}]"
                if not isinstance(handler, dict):
                    report.add_unsupported("hook-handler", ref, "handler is not an object")
                    continue
                if handler.get("type", "command") != "command":
                    reason = f"Codex only runs command hook handlers; got {handler.get('type')}"
                    if mode == "strict":
                        die(reason)
                    report.add_unsupported("hook-handler", ref, reason)
                    continue
                if handler.get("async") is True:
                    reason = "Codex parses but skips async command hooks"
                    if mode == "strict":
                        die(reason)
                    report.add_unsupported("hook-handler", ref, reason)
                    continue
                if "if" in handler:
                    reason = "Codex hooks do not support Claude handler-level if filters"
                    if mode == "strict":
                        die(reason)
                    report.add_unsupported("hook-handler", ref, reason)
                    continue
                out_handler: dict[str, Any] = {"type": "command"}
                if "command" not in handler:
                    report.add_unsupported("hook-handler", ref, "command hook missing command")
                    continue
                command = str(handler["command"])
                if "args" in handler:
                    args = handler["args"]
                    if not isinstance(args, list):
                        reason = "Codex cannot represent non-list Claude args"
                        if mode == "strict":
                            die(reason)
                        report.add_unsupported("hook-handler", ref, reason)
                        continue
                    command = quote_command_with_args(command, args)
                    report.warn(f"{ref}: Claude exec-form args were shell-quoted for Codex")
                command = recursive_replace(
                    command,
                    {
                        "${CLAUDE_PLUGIN_ROOT}": "${PLUGIN_ROOT}",
                        "$CLAUDE_PLUGIN_ROOT": "$PLUGIN_ROOT",
                        "${CLAUDE_PLUGIN_DATA}": "${PLUGIN_DATA}",
                        "$CLAUDE_PLUGIN_DATA": "$PLUGIN_DATA",
                    },
                )
                out_handler["command"] = command
                for key in ("timeout", "statusMessage", "commandWindows", "command_windows"):
                    if key in handler:
                        out_handler[key] = handler[key]
                out_handlers.append(out_handler)
            if out_handlers:
                out_group["hooks"] = out_handlers
                converted_groups.append(out_group)
        if converted_groups:
            converted[event] = converted_groups
    return {"hooks": converted}


def convert_hooks_to_claude(data: dict[str, Any], report: Report) -> dict[str, Any]:
    hooks = data.get("hooks", data)
    if not isinstance(hooks, dict):
        die("hooks config must contain a hooks object")
    converted = recursive_replace(
        {"hooks": hooks},
        {
            "${PLUGIN_ROOT}": "${CLAUDE_PLUGIN_ROOT}",
            "$PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}",
            "${PLUGIN_DATA}": "${CLAUDE_PLUGIN_DATA}",
            "$PLUGIN_DATA": "${CLAUDE_PLUGIN_DATA}",
        },
    )
    report.add_mapping("hooks", "hooks/hooks.json", "Hook placeholders normalized for Claude plugin runtime")
    return converted


def write_hooks(root: Path, data: dict[str, Any]) -> None:
    write_json(root / "hooks/hooks.json", data)
    if (root / "hooks.json").exists():
        (root / "hooks.json").unlink()


def quarantine_root_claude_context(root: Path, report: Report) -> None:
    context = root / "CLAUDE.md"
    if not context.exists():
        return
    target = root / PORTABILITY_DIR / "preserved" / "CLAUDE.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(context), str(target))
    report.add_mapping(
        "CLAUDE.md",
        target.relative_to(root).as_posix(),
        "Root CLAUDE.md moved because Claude plugin validation rejects plugin-root context files",
    )
    report.add_preserved(
        "claude-root-context",
        "CLAUDE.md",
        "Claude plugins do not load root CLAUDE.md; original file preserved under .plugin-portability/preserved/",
    )


def author_object(value: Any, fallback: str) -> dict[str, Any]:
    if isinstance(value, dict):
        name = value.get("name") or fallback
        result = {"name": str(name)}
        for key in ("email", "url"):
            if value.get(key):
                result[key] = str(value[key])
        return result
    if isinstance(value, str) and value.strip():
        return {"name": value.strip()}
    return {"name": fallback}


def build_codex_manifest(pkg: PluginPackage, root: Path) -> dict[str, Any]:
    source = dict(pkg.codex_manifest or {})
    claude = pkg.claude_manifest or {}
    name = slugify(str(source.get("name") or claude.get("name") or pkg.name))
    description = safe_description(
        str(source.get("description") or claude.get("description") or ""),
        f"{display_name(name)} converted plugin.",
    )
    interface = source.get("interface") if isinstance(source.get("interface"), dict) else {}
    display = str(interface.get("displayName") or claude.get("displayName") or display_name(name))
    manifest: dict[str, Any] = {
        "name": name,
        "version": str(source.get("version") or claude.get("version") or "1.0.0"),
        "description": description,
        "author": author_object(source.get("author") or claude.get("author"), display),
    }
    for key in ("homepage", "repository", "license", "keywords"):
        value = source.get(key, claude.get(key))
        if value:
            manifest[key] = value
    if (root / "skills").exists():
        manifest["skills"] = "./skills/"
    if (root / ".mcp.json").exists():
        manifest["mcpServers"] = "./.mcp.json"
    if (root / ".app.json").exists():
        manifest["apps"] = "./.app.json"
    manifest["interface"] = {
        "displayName": display,
        "shortDescription": str(interface.get("shortDescription") or description[:120]),
        "longDescription": str(interface.get("longDescription") or description),
        "developerName": str(interface.get("developerName") or display),
        "category": str(interface.get("category") or claude.get("category") or "Productivity"),
        "capabilities": interface.get("capabilities") or ["Read", "Write"],
        "defaultPrompt": interface.get("defaultPrompt")
        or interface.get("default_prompt")
        or [f"Use {display} when its plugin capabilities are relevant."],
    }
    return manifest


def build_claude_manifest(pkg: PluginPackage, root: Path) -> dict[str, Any]:
    source = dict(pkg.claude_manifest or {})
    codex = pkg.codex_manifest or {}
    codex_interface = codex.get("interface") if isinstance(codex.get("interface"), dict) else {}
    name = slugify(str(source.get("name") or codex.get("name") or pkg.name))
    manifest: dict[str, Any] = {"name": name}
    display = source.get("displayName") or codex_interface.get("displayName")
    if display:
        manifest["displayName"] = display
    for key in ("version", "description", "author", "homepage", "repository", "license", "keywords"):
        value = source.get(key, codex.get(key))
        if value:
            manifest[key] = value
    for key in ("skills", "commands", "agents"):
        if key in source:
            manifest[key] = source[key]
    if "hooks" in source:
        manifest["hooks"] = source["hooks"]
    if (root / ".mcp.json").exists():
        manifest["mcpServers"] = "./.mcp.json"
    if (root / ".lsp.json").exists():
        manifest["lspServers"] = "./.lsp.json"
    if (root / "output-styles").exists():
        manifest["outputStyles"] = "./output-styles/"
    experimental: dict[str, Any] = {}
    if (root / "themes").exists():
        experimental["themes"] = "./themes/"
    if (root / "monitors").exists():
        experimental["monitors"] = "./monitors/monitors.json"
    if experimental:
        manifest["experimental"] = experimental
    for key in ("dependencies", "userConfig", "channels", "defaultEnabled"):
        if key in source:
            manifest[key] = source[key]
    return manifest


def mark_preserved_host_specific(root: Path, target: str, report: Report) -> None:
    if target == "codex":
        for kind, rels in {
            "claude-lsp": [".lsp.json"],
            "claude-agents": ["agents"],
            "claude-output-style": ["output-styles"],
            "claude-theme": ["themes"],
            "claude-monitor": ["monitors"],
            "claude-bin": ["bin"],
            "claude-settings": ["settings.json"],
        }.items():
            for rel in rels:
                if (root / rel).exists():
                    report.add_preserved(kind, rel, "Claude-specific component preserved but not active in Codex")
    else:
        if (root / ".app.json").exists():
            report.add_preserved("codex-apps", ".app.json", "Codex app/connector mappings have no Claude plugin equivalent")
        if (root / ".codex-plugin/plugin.json").exists():
            report.add_preserved("codex-manifest", ".codex-plugin/plugin.json", "Codex manifest preserved for round-trip metadata")


def convert_plugin(source: Path, target: str, output: Path, *, mode: str, overwrite: bool, explicit_host: str | None = None) -> Report:
    pkg = detect_plugin(source, explicit_host=explicit_host)
    prepare_output(pkg.root, output, overwrite=overwrite)
    out_root = output.resolve()
    report = Report(
        source=pkg.host,
        target=target,
        source_root=str(pkg.root),
        output_root=str(out_root),
        mode=mode,
        files_copied=rel_files(out_root),
    )

    if target == "codex":
        convert_commands_to_codex_skills(out_root, report, mode=mode)
        normalize_codex_skills(out_root, report, mode=mode)
        hooks = load_hooks_from_plugin(out_root, pkg.claude_manifest or pkg.codex_manifest)
        if hooks:
            write_hooks(out_root, convert_hooks_to_codex(hooks, report, mode=mode))
        if (out_root / ".mcp.json").exists():
            write_json(out_root / ".mcp.json", normalize_mcp_config(load_json(out_root / ".mcp.json"), target="codex"))
        write_json(out_root / CODEX_MANIFEST, build_codex_manifest(pkg, out_root))
    elif target == "claude":
        quarantine_root_claude_context(out_root, report)
        normalize_claude_skills(out_root, report, mode=mode)
        normalize_claude_markdown_components(out_root, report, mode=mode)
        hooks = load_hooks_from_plugin(out_root, pkg.codex_manifest or pkg.claude_manifest)
        if hooks:
            write_hooks(out_root, convert_hooks_to_claude(hooks, report))
        if (out_root / ".mcp.json").exists():
            write_json(out_root / ".mcp.json", normalize_mcp_config(load_json(out_root / ".mcp.json"), target="claude"))
        write_json(out_root / CLAUDE_MANIFEST, build_claude_manifest(pkg, out_root))
    else:
        die(f"unsupported target host: {target}")

    mark_preserved_host_specific(out_root, target, report)
    finalize_report(report, out_root)
    write_json(out_root / PORTABILITY_DIR / REPORT_NAME, report.as_dict())
    return report


def marketplace_manifest_path(root_or_file: Path, host: str | None = None) -> tuple[str, Path, Path]:
    path = root_or_file.resolve()
    if path.is_file():
        if path.name != "marketplace.json":
            die(f"{path}: expected a marketplace.json file")
        if path.parent.name == "plugins" and path.parent.parent.name == ".agents":
            return "codex", path.parent.parent.parent, path
        if path.parent.name == ".claude-plugin":
            return "claude", path.parent.parent, path
        die(f"{path}: cannot infer marketplace host; pass a marketplace root instead")
    if host == "codex":
        manifest = path / CODEX_MARKETPLACE
        if manifest.exists():
            return "codex", path, manifest
        die(f"{path}: no Codex marketplace manifest found")
    if host == "claude":
        manifest = path / CLAUDE_MARKETPLACE
        if manifest.exists():
            return "claude", path, manifest
        die(f"{path}: no Claude marketplace manifest found")
    if (path / CODEX_MARKETPLACE).exists():
        return "codex", path, path / CODEX_MARKETPLACE
    if (path / CLAUDE_MARKETPLACE).exists():
        return "claude", path, path / CLAUDE_MARKETPLACE
    die(f"{path}: no Codex or Claude marketplace manifest found")


def local_plugin_source(entry: dict[str, Any], source_host: str, marketplace_root: Path) -> Path | None:
    source = entry.get("source")
    rel: str | None = None
    if isinstance(source, str) and source.startswith("./"):
        rel = source
    elif isinstance(source, dict):
        if source_host == "codex" and source.get("source") == "local" and isinstance(source.get("path"), str):
            rel = str(source["path"])
        elif source_host == "claude" and source.get("source") in {"path", "local"} and isinstance(source.get("path"), str):
            rel = str(source["path"])
    if not rel:
        return None
    candidate = (marketplace_root / rel.removeprefix("./")).resolve()
    try:
        candidate.relative_to(marketplace_root.resolve())
    except ValueError:
        die(f"marketplace source escapes root: {rel}")
    return candidate if candidate.exists() else None


def convert_marketplace(source: Path, target: str, output: Path, *, mode: str, overwrite: bool, explicit_host: str | None = None) -> Report:
    source_host, marketplace_root, manifest_path = marketplace_manifest_path(source, explicit_host)
    data = load_json(manifest_path)
    if output.exists():
        if not overwrite:
            die(f"{output}: output already exists; pass --overwrite to replace it")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    name = slugify(str(data.get("name") or marketplace_root.name), fallback="marketplace")
    report = Report(
        source=source_host,
        target=f"{target}-marketplace",
        source_root=str(marketplace_root),
        output_root=str(output.resolve()),
        mode=mode,
    )
    target_entries: list[dict[str, Any]] = []
    plugins = data.get("plugins", [])
    if not isinstance(plugins, list):
        die(f"{manifest_path}: plugins must be a list")
    for entry in plugins:
        if not isinstance(entry, dict):
            continue
        plugin_source = local_plugin_source(entry, source_host, marketplace_root)
        plugin_name_for_error = slugify(str(entry.get("name") or "plugin"))
        if plugin_source is None:
            reason = f"unsupported or non-local marketplace source for {plugin_name_for_error}"
            if mode == "strict":
                die(reason)
            report.add_unsupported("marketplace-source", plugin_name_for_error, reason)
            continue
        child_pkg = detect_plugin(plugin_source, explicit_host=source_host)
        plugin_name = target_manifest_name(child_pkg, target)
        if any(item.get("name") == plugin_name for item in target_entries):
            reason = f"duplicate target marketplace plugin name: {plugin_name}"
            if mode == "strict":
                die(reason)
            report.add_unsupported("marketplace-duplicate", plugin_name, reason)
            continue
        out_plugin = output / "plugins" / plugin_name
        child = convert_plugin(
            plugin_source,
            target,
            out_plugin,
            mode=mode,
            overwrite=True,
            explicit_host=source_host,
        )
        report.mappings.append(
            {
                "source": str(plugin_source),
                "target": out_plugin.relative_to(output).as_posix(),
                "reason": "Local marketplace plugin converted",
            }
        )
        report.unsupported.extend(child.unsupported)
        report.preserved_only.extend(child.preserved_only)
        description = str(entry.get("description") or "")
        if target == "codex":
            target_entries.append(
                {
                    "name": plugin_name,
                    "source": {"source": "local", "path": f"./plugins/{plugin_name}"},
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": str(entry.get("category") or "Productivity"),
                }
            )
        else:
            target_entry: dict[str, Any] = {
                "name": plugin_name,
                "source": f"./plugins/{plugin_name}",
            }
            if description:
                target_entry["description"] = description
            if entry.get("version"):
                target_entry["version"] = entry["version"]
            target_entries.append(target_entry)

    if target == "codex":
        manifest = {
            "name": name,
            "interface": {"displayName": display_name(name)},
            "plugins": target_entries,
        }
        write_json(output / CODEX_MARKETPLACE, manifest)
    else:
        owner = data.get("owner") if isinstance(data.get("owner"), dict) else {}
        manifest = {
            "name": name,
            "owner": {"name": str(owner.get("name") or data.get("name") or display_name(name))},
            "plugins": target_entries,
        }
        if data.get("description"):
            manifest["description"] = data["description"]
        write_json(output / CLAUDE_MARKETPLACE, manifest)
    report.files_copied = rel_files(output)
    finalize_report(report, output.resolve())
    write_json(output / PORTABILITY_DIR / REPORT_NAME, report.as_dict())
    return report


def inspect_path(path: Path, *, fmt: str, explicit_host: str | None = None) -> str:
    try:
        host, root, manifest_path = marketplace_manifest_path(path, explicit_host)
    except PluginPortError:
        pkg = detect_plugin(path, explicit_host=explicit_host)
        payload = {
            "kind": "plugin",
            "host": pkg.host,
            "name": pkg.name,
            "root": str(pkg.root),
            "components": pkg.components,
            "files": pkg.files,
        }
    else:
        data = load_json(manifest_path)
        payload = {
            "kind": "marketplace",
            "host": host,
            "name": data.get("name"),
            "root": str(root),
            "manifest": str(manifest_path),
            "plugins": data.get("plugins", []),
        }
    if fmt == "json":
        return json.dumps(payload, indent=2, sort_keys=False)
    lines = [f"# {payload['kind'].capitalize()} inventory", "", f"- Host: {payload['host']}", f"- Root: {payload['root']}"]
    if payload.get("name"):
        lines.append(f"- Name: {payload['name']}")
    if payload["kind"] == "plugin":
        lines.append("")
        lines.append("## Components")
        for kind, values in payload["components"].items():
            lines.append(f"- {kind}: {len(values)}")
            for value in values[:8]:
                lines.append(f"  - {value}")
            if len(values) > 8:
                lines.append(f"  - ... {len(values) - 8} more")
    else:
        lines.append(f"- Plugins: {len(payload.get('plugins') or [])}")
    return "\n".join(lines)


def validation_die(errors: list[str]) -> None:
    die("; ".join(errors), exit_code=EXIT_VALIDATION_FAILED)


def reject_unknown_fields(payload: dict[str, Any], allowed_keys: set[str], prefix: str, errors: list[str]) -> None:
    for key in sorted(set(payload) - allowed_keys):
        errors.append(f"plugin.json field `{prefix}.{key}` is not accepted by plugin validation")


def require_object(payload: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any] | None:
    value = payload.get(key)
    if not isinstance(value, dict):
        errors.append(f"plugin.json field `{key}` must be an object")
        return None
    return value


def require_non_empty_string(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> str | None:
    value = payload.get(key)
    field = f"{prefix}.{key}" if prefix is not None else key
    if not isinstance(value, str) or not value.strip():
        errors.append(f"plugin.json field `{field}` must be a non-empty string")
        return None
    return value


def validate_optional_non_empty_string(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> None:
    value = payload.get(key)
    if value is None:
        return
    field = f"{prefix}.{key}" if prefix is not None else key
    if not isinstance(value, str) or not value.strip():
        errors.append(f"plugin.json field `{field}` must be a non-empty string")


def validate_optional_https_url(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str,
) -> None:
    value = payload.get(key)
    if value is None:
        return
    parsed = urlparse(value) if isinstance(value, str) else None
    if parsed is None or parsed.scheme != "https" or not parsed.netloc:
        errors.append(f"plugin.json field `{prefix}.{key}` must be an absolute `https://` URL")


def normalize_contract_path(raw_path: str) -> str | None:
    path = Path(raw_path)
    if path.is_absolute():
        return None
    normalized = path.as_posix().rstrip("/")
    return normalized or None


def validate_optional_contract_path(
    payload: dict[str, Any],
    key: str,
    expected: str,
    errors: list[str],
) -> None:
    value = payload.get(key)
    if value is None:
        return
    normalized = normalize_contract_path(value) if isinstance(value, str) else None
    if normalized != expected:
        errors.append(f"plugin.json field `{key}` must resolve to `{expected}`")


def load_companion_json_object(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"{label} is required when its plugin.json field is present")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors.append(f"{label} must contain valid JSON")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{label} must contain a JSON object")
        return None
    return payload


def reject_companion_unknown_fields(payload: dict[str, Any], allowed_keys: set[str], prefix: str, errors: list[str]) -> None:
    for key in sorted(set(payload) - allowed_keys):
        errors.append(f"{prefix} field `{key}` is not accepted by plugin validation")


def validate_app_manifest(path: Path, errors: list[str]) -> None:
    payload = load_companion_json_object(path, "`.app.json`", errors)
    if payload is None:
        return
    reject_companion_unknown_fields(payload, {"apps"}, "`.app.json`", errors)
    apps = payload.get("apps")
    if not isinstance(apps, dict):
        errors.append("`.app.json` field `apps` must be an object")
        return
    for key, value in apps.items():
        if not isinstance(value, dict):
            errors.append(f"`.app.json` app `{key}` must be an object")
            continue
        reject_companion_unknown_fields(value, {"id"}, f"`.app.json` app `{key}`", errors)
        app_id = value.get("id")
        if not isinstance(app_id, str) or not app_id.strip():
            errors.append(f"`.app.json` app `{key}` field `id` must be a non-empty string")


def validate_mcp_manifest(path: Path, errors: list[str]) -> None:
    payload = load_companion_json_object(path, "`.mcp.json`", errors)
    if payload is None:
        return
    reject_companion_unknown_fields(payload, {"mcpServers"}, "`.mcp.json`", errors)
    servers = payload.get("mcpServers")
    if not isinstance(servers, dict):
        errors.append("`.mcp.json` field `mcpServers` must be an object")
        return
    for key, value in servers.items():
        if not isinstance(key, str) or not key.strip():
            errors.append("`.mcp.json` server names must be non-empty strings")
        if not isinstance(value, dict):
            errors.append(f"`.mcp.json` server `{key}` must be an object")


def validate_asset_path(
    base_dir: Path,
    allowed_root: Path,
    raw_path: Any,
    field: str,
    errors: list[str],
) -> None:
    label = field if field.startswith("skill `") else f"plugin.json field `{field}`"
    if not isinstance(raw_path, str) or not raw_path.strip():
        errors.append(f"{label} must be a non-empty relative path")
        return
    candidate = PurePosixPath(raw_path.replace("\\", "/"))
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        errors.append(f"{label} must stay inside the plugin archive")
        return
    resolved_path = (base_dir / candidate.as_posix()).resolve()
    try:
        resolved_path.relative_to(allowed_root.resolve())
    except ValueError:
        errors.append(f"{label} must stay inside the plugin archive")
        return
    if not resolved_path.is_file():
        errors.append(f"{label} points to a missing file")


def validate_optional_asset_path(
    base_dir: Path,
    allowed_root: Path,
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str = "interface",
) -> None:
    raw_path = payload.get(key)
    if raw_path is None:
        return
    validate_asset_path(base_dir, allowed_root, raw_path, f"{prefix}.{key}", errors)


def validate_skill_agent_manifest(plugin_root: Path, skill_root: Path, agent_yaml_path: Path, errors: list[str]) -> None:
    try:
        payload = yaml.safe_load(agent_yaml_path.read_text(encoding="utf-8")) if yaml is not None else None
    except OSError:
        errors.append(f"unable to read skill `{skill_root.name}` agent YAML")
        return
    except yaml.YAMLError:
        errors.append(f"skill `{skill_root.name}` agent YAML must be valid YAML")
        return
    if not isinstance(payload, dict):
        errors.append(f"skill `{skill_root.name}` agent YAML must be an object")
        return
    allowed_top = {"interface", "policy", "dependencies"}
    for key in sorted(set(payload) - allowed_top):
        errors.append(f"skill `{skill_root.name}` agent field `{key}` is not accepted by plugin validation")
    interface = payload.get("interface")
    if not isinstance(interface, dict):
        errors.append(f"skill `{skill_root.name}` agent field `interface` must be an object")
        return
    allowed_interface = {"display_name", "short_description", "icon_small", "icon_large", "brand_color", "default_prompt"}
    for key in sorted(set(interface) - allowed_interface):
        errors.append(f"skill `{skill_root.name}` agent field `interface.{key}` is not accepted by plugin validation")
    for field_name in ("display_name", "short_description"):
        value = interface.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"skill `{skill_root.name}` agent field `interface.{field_name}` must be non-empty")
    for field_name in ("icon_small", "icon_large"):
        validate_optional_asset_path(
            skill_root,
            plugin_root,
            interface,
            field_name,
            errors,
            prefix=f"skill `{skill_root.name}` agent field `interface",
        )
    brand_color = interface.get("brand_color")
    if brand_color is not None and (not isinstance(brand_color, str) or HEX_COLOR_RE.fullmatch(brand_color) is None):
        errors.append(f"skill `{skill_root.name}` agent field `interface.brand_color` must use `#RRGGBB`")
    default_prompt = interface.get("default_prompt")
    if default_prompt is not None and (not isinstance(default_prompt, str) or not default_prompt.strip()):
        errors.append(f"skill `{skill_root.name}` agent field `interface.default_prompt` must be non-empty")
    policy = payload.get("policy")
    if policy is not None:
        if not isinstance(policy, dict):
            errors.append(f"skill `{skill_root.name}` agent field `policy` must be an object")
        else:
            for key in sorted(set(policy) - {"allow_implicit_invocation"}):
                errors.append(f"skill `{skill_root.name}` agent field `policy.{key}` is not accepted by plugin validation")
            allow_implicit = policy.get("allow_implicit_invocation")
            if allow_implicit is not None and not isinstance(allow_implicit, bool):
                errors.append(f"skill `{skill_root.name}` agent field `policy.allow_implicit_invocation` must be a boolean")
    dependencies = payload.get("dependencies")
    if dependencies is not None:
        if not isinstance(dependencies, dict):
            errors.append(f"skill `{skill_root.name}` agent field `dependencies` must be an object")
        else:
            for key in sorted(set(dependencies) - {"tools"}):
                errors.append(f"skill `{skill_root.name}` agent field `dependencies.{key}` is not accepted by plugin validation")


def validate_skill_manifest(plugin_root: Path, skill_root: Path, errors: list[str]) -> None:
    skill_md_path = skill_root / "SKILL.md"
    if not skill_md_path.is_file():
        errors.append(f"skill `{skill_root.name}` is missing `SKILL.md`")
        return
    try:
        contents = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        errors.append(f"unable to read skill `{skill_root.name}`")
        return
    if not contents.startswith("---\n"):
        errors.append(f"skill `{skill_root.name}` must start with YAML frontmatter")
        return
    frontmatter_end = contents.find("\n---", 4)
    if frontmatter_end == -1:
        errors.append(f"skill `{skill_root.name}` frontmatter is not closed")
        return
    try:
        frontmatter = yaml.safe_load(contents[4:frontmatter_end]) if yaml is not None else None
    except yaml.YAMLError:
        errors.append(f"skill `{skill_root.name}` frontmatter must be valid YAML")
        return
    if not isinstance(frontmatter, dict):
        errors.append(f"skill `{skill_root.name}` frontmatter must be an object")
        return
    skill_name = frontmatter.get("name")
    if not isinstance(skill_name, str) or not skill_name.strip():
        errors.append(f"skill `{skill_root.name}` frontmatter field `name` must be non-empty")
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"skill `{skill_root.name}` frontmatter field `description` must be non-empty")
    disable_model_invocation = frontmatter.get("disable-model-invocation")
    if disable_model_invocation is None:
        disable_model_invocation = frontmatter.get("disable_model_invocation")
    if disable_model_invocation not in (None, False):
        errors.append(f"skill `{skill_root.name}` frontmatter field `disable-model-invocation` must be false")
    agent_yaml_path = skill_root / "agents" / "openai.yaml"
    if agent_yaml_path.is_file():
        validate_skill_agent_manifest(plugin_root, skill_root, agent_yaml_path, errors)


def validate_skill_manifests(plugin_root: Path, errors: list[str]) -> None:
    skills_root = plugin_root / "skills"
    if not skills_root.is_dir():
        return
    for skill_root in sorted(skills_root.iterdir(), key=lambda path: path.name):
        if skill_root.name.startswith(".") or not skill_root.is_dir():
            continue
        validate_skill_manifest(plugin_root, skill_root, errors)


def validate_codex_manifest_shape(plugin_root: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in sorted(set(manifest) - CODEX_ALLOWED_MANIFEST_KEYS):
        errors.append(f"plugin.json field `{key}` is not accepted by plugin validation")
    validate_optional_non_empty_string(manifest, "id", errors)
    require_non_empty_string(manifest, "name", errors)
    version = require_non_empty_string(manifest, "version", errors)
    if version is not None and SEMVER_RE.fullmatch(version) is None:
        errors.append("plugin.json field `version` must be strict semver")
    require_non_empty_string(manifest, "description", errors)
    author = require_object(manifest, "author", errors)
    if author is not None:
        reject_unknown_fields(author, {"name", "email", "url"}, "author", errors)
        require_non_empty_string(author, "name", errors, prefix="author")
        validate_optional_non_empty_string(author, "email", errors, prefix="author")
        validate_optional_https_url(author, "url", errors, prefix="author")
    validate_optional_contract_path(manifest, "skills", "skills", errors)
    validate_optional_contract_path(manifest, "apps", ".app.json", errors)
    validate_optional_contract_path(manifest, "mcpServers", ".mcp.json", errors)
    if manifest.get("apps") is not None:
        validate_app_manifest(plugin_root / ".app.json", errors)
    if manifest.get("mcpServers") is not None:
        validate_mcp_manifest(plugin_root / ".mcp.json", errors)
    validate_skill_manifests(plugin_root, errors)
    interface = require_object(manifest, "interface", errors)
    if interface is None:
        return errors
    reject_unknown_fields(interface, CODEX_ALLOWED_INTERFACE_KEYS, "interface", errors)
    for field_name in ("displayName", "shortDescription", "longDescription", "developerName", "category"):
        require_non_empty_string(interface, field_name, errors, prefix="interface")
    if "defaultPrompt" not in interface and "default_prompt" not in interface:
        errors.append("plugin.json field `interface.defaultPrompt` or `interface.default_prompt` is required")
    capabilities = interface.get("capabilities")
    if not isinstance(capabilities, list) or not all(isinstance(value, str) and value.strip() for value in capabilities):
        errors.append("plugin.json field `interface.capabilities` must be an array of strings")
    for field_name in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
        validate_optional_https_url(interface, field_name, errors, prefix="interface")
    brand_color = interface.get("brandColor")
    if brand_color is not None and (not isinstance(brand_color, str) or HEX_COLOR_RE.fullmatch(brand_color) is None):
        errors.append("plugin.json field `interface.brandColor` must use `#RRGGBB`")
    for field_name in ("composerIcon", "logo"):
        validate_optional_asset_path(plugin_root, plugin_root, interface, field_name, errors)
    screenshots = interface.get("screenshots", [])
    if not isinstance(screenshots, list):
        errors.append("plugin.json field `interface.screenshots` must be an array")
    else:
        for index, raw_path in enumerate(screenshots):
            validate_asset_path(plugin_root, plugin_root, raw_path, f"interface.screenshots[{index}]", errors)
    return errors


def internal_validate(path: Path, host: str) -> list[str]:
    warnings: list[str] = []
    if host == "codex":
        manifest = path / CODEX_MANIFEST
        if not manifest.exists():
            die(f"{path}: missing {CODEX_MANIFEST}", exit_code=EXIT_VALIDATION_FAILED)
        data = load_json(manifest, exit_code=EXIT_VALIDATION_FAILED)
        errors = validate_codex_manifest_shape(path, data)
        if errors:
            validation_die(errors)
        hooks = load_hooks_from_plugin(path, data)
        if hooks:
            temp_report = Report("codex", "codex", str(path), str(path), "strict")
            try:
                convert_hooks_to_codex(hooks, temp_report, mode="strict")
            except PluginPortError as exc:
                die(str(exc), exit_code=EXIT_VALIDATION_FAILED)
    else:
        if not (path / CLAUDE_MANIFEST).exists():
            die(f"{path}: missing {CLAUDE_MANIFEST}", exit_code=EXIT_VALIDATION_FAILED)
    return warnings


def run_external_validator(path: Path, host: str) -> dict[str, Any] | None:
    if host == "codex":
        validator = Path.home() / ".codex/skills/.system/plugin-creator/scripts/validate_plugin.py"
        if not validator.exists():
            return None
        cmd = ["python3", str(validator), str(path)]
    else:
        if shutil.which("claude") is None:
            return None
        cmd = ["claude", "plugin", "validate", "--strict", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def validate_plugin(path: Path, host: str, *, external: bool = True, require_external: bool = False) -> Report:
    path = path.resolve()
    report = Report(host, f"{host}-validation", str(path), str(path), "strict")
    report.validation_summary = {
        "internal": {"available": True, "passed": False},
        "external": {"requested": external, "required": require_external, "available": False, "passed": None},
    }
    warnings = internal_validate(path, host)
    report.validation_summary["internal"]["passed"] = True
    for warning in warnings:
        report.warn(warning)
    if external:
        result = run_external_validator(path, host)
        if result is not None:
            report.validation_summary["external"]["available"] = True
            report.validation_summary["external"]["passed"] = result["returncode"] == 0
            report.validations.append(result)
            if result["returncode"] != 0:
                detail = (result.get("stderr") or result.get("stdout") or "").strip()
                suffix = f": {detail}" if detail else ""
                die(f"external {host} validator failed for {path}{suffix}", exit_code=EXIT_VALIDATION_FAILED)
        elif require_external:
            die(f"external {host} validator is required but unavailable", exit_code=EXIT_EXTERNAL_TOOL_UNAVAILABLE)
        else:
            report.warn(f"external {host} validator unavailable; internal validation only")
            report.validation_summary["external"]["passed"] = None
    finalize_report(report, path)
    return report


def report_summary_md(report: Report) -> str:
    lines = [
        f"# Plugin Port Summary",
        "",
        f"- Source: {report.source}",
        f"- Target: {report.target}",
        f"- Mode: {report.mode}",
        f"- Status: {report.status}",
        f"- Support: {report.support_level}",
        f"- Output: {report.output_root}",
        f"- Warnings: {len(report.warnings)}",
        f"- Unsupported: {len(report.unsupported)}",
        f"- Preserved only: {len(report.preserved_only)}",
        f"- Executable/runtime surfaces: {len(report.executable_surfaces)}",
    ]
    external = report.validation_summary.get("external") if isinstance(report.validation_summary, dict) else None
    if isinstance(external, dict) and external:
        lines.append(
            f"- External validator: requested={external.get('requested')} "
            f"available={external.get('available')} passed={external.get('passed')}"
        )
    return "\n".join(lines)


def print_report(report: Report, summary: str) -> None:
    if summary == "full":
        print(json.dumps(report.as_dict(), indent=2, sort_keys=False))
    elif summary == "json":
        print(json.dumps(report.summary_dict(), indent=2, sort_keys=False))
    elif summary == "md":
        print(report_summary_md(report))
    else:
        die(f"unsupported summary format: {summary}")


def cmd_inspect(args: argparse.Namespace) -> int:
    print(inspect_path(Path(args.path), fmt=args.format, explicit_host=args.from_host))
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    report = convert_plugin(
        Path(args.path),
        args.to,
        Path(args.out),
        mode=args.mode,
        overwrite=args.overwrite,
        explicit_host=args.from_host,
    )
    print_report(report, args.summary)
    return 0


def cmd_convert_marketplace(args: argparse.Namespace) -> int:
    report = convert_marketplace(
        Path(args.path),
        args.to,
        Path(args.out),
        mode=args.mode,
        overwrite=args.overwrite,
        explicit_host=args.from_host,
    )
    print_report(report, args.summary)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    if args.no_external and args.require_external_validator:
        die("--require-external-validator cannot be used with --no-external")
    report = validate_plugin(
        Path(args.path),
        args.host,
        external=not args.no_external,
        require_external=args.require_external_validator,
    )
    print_report(report, args.summary)
    return 0


def cmd_roundtrip(args: argparse.Namespace) -> int:
    source = Path(args.path).resolve()
    pkg = detect_plugin(source, explicit_host=args.from_host)
    first = Path(args.tmp).resolve() / f"{pkg.name}-{args.to}"
    back_host = "claude" if args.to == "codex" else "codex"
    second = Path(args.tmp).resolve() / f"{pkg.name}-{back_host}"
    first_report = convert_plugin(source, args.to, first, mode=args.mode, overwrite=True, explicit_host=args.from_host)
    second_report = convert_plugin(first, back_host, second, mode=args.mode, overwrite=True, explicit_host=args.to)
    payload = {
        "first": first_report.as_dict(),
        "second": second_report.as_dict(),
        "roundtrip_root": str(second),
    }
    if args.summary == "full":
        print(json.dumps(payload, indent=2, sort_keys=False))
    elif args.summary == "json":
        print(
            json.dumps(
                {
                    "first": first_report.summary_dict(),
                    "second": second_report.summary_dict(),
                    "roundtrip_root": str(second),
                },
                indent=2,
                sort_keys=False,
            )
        )
    elif args.summary == "md":
        print("# Plugin Port Roundtrip Summary\n")
        print(report_summary_md(first_report))
        print("\n---\n")
        print(report_summary_md(second_report))
    else:
        die(f"unsupported summary format: {args.summary}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Inspect a plugin or marketplace")
    inspect_p.add_argument("path")
    inspect_p.add_argument("--format", choices=("json", "md"), default="md")
    inspect_p.add_argument("--from", dest="from_host", choices=("codex", "claude"))
    inspect_p.set_defaults(func=cmd_inspect)

    convert_p = sub.add_parser("convert", help="Convert a plugin package")
    convert_p.add_argument("path")
    convert_p.add_argument("--to", choices=("codex", "claude"), required=True)
    convert_p.add_argument("--out", required=True)
    convert_p.add_argument("--mode", choices=("strict", "best-effort"), default="strict")
    convert_p.add_argument("--from", dest="from_host", choices=("codex", "claude"))
    convert_p.add_argument("--overwrite", action="store_true")
    convert_p.add_argument("--summary", choices=("full", "json", "md"), default="full")
    convert_p.set_defaults(func=cmd_convert)

    market_p = sub.add_parser("convert-marketplace", help="Convert a plugin marketplace")
    market_p.add_argument("path")
    market_p.add_argument("--to", choices=("codex", "claude"), required=True)
    market_p.add_argument("--out", required=True)
    market_p.add_argument("--mode", choices=("strict", "best-effort"), default="strict")
    market_p.add_argument("--from", dest="from_host", choices=("codex", "claude"))
    market_p.add_argument("--overwrite", action="store_true")
    market_p.add_argument("--plugins-dir", default="plugins", help="Reserved for CLI compatibility; target uses plugins/")
    market_p.add_argument("--summary", choices=("full", "json", "md"), default="full")
    market_p.set_defaults(func=cmd_convert_marketplace)

    validate_p = sub.add_parser("validate", help="Validate a converted plugin")
    validate_p.add_argument("path")
    validate_p.add_argument("--host", choices=("codex", "claude"), required=True)
    validate_p.add_argument("--no-external", action="store_true")
    validate_p.add_argument("--require-external-validator", action="store_true")
    validate_p.add_argument("--summary", choices=("full", "json", "md"), default="full")
    validate_p.set_defaults(func=cmd_validate)

    roundtrip_p = sub.add_parser("roundtrip", help="Convert to a target host and back")
    roundtrip_p.add_argument("path")
    roundtrip_p.add_argument("--to", choices=("codex", "claude"), required=True)
    roundtrip_p.add_argument("--tmp", required=True)
    roundtrip_p.add_argument("--mode", choices=("strict", "best-effort"), default="best-effort")
    roundtrip_p.add_argument("--from", dest="from_host", choices=("codex", "claude"))
    roundtrip_p.add_argument("--summary", choices=("full", "json", "md"), default="full")
    roundtrip_p.set_defaults(func=cmd_roundtrip)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except PluginPortError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
