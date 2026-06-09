#!/usr/bin/env python3
"""Inventory existing Codex capabilities: skills, plugins, MCP servers, hooks, subagents, and project commands."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import List, Set

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None

from common import git_root_or_cwd


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_toml(path: Path):
    if tomllib is None:
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def first_yaml_field(text: str, field: str) -> str:
    m = re.search(rf"^{re.escape(field)}:\s*(.+?)\s*$", text, re.M)
    return m.group(1).strip().strip('"\'') if m else ""


def scan_skills(root: Path, home: Path, include_home: bool = True) -> List[dict]:
    dirs: List[Path] = []
    # Repo skill dirs from cwd to repo root.
    cur = Path.cwd().resolve()
    repo = root.resolve()
    for p in [cur, *cur.parents]:
        if repo in [p, *p.parents] or p == repo:
            d = p / ".agents" / "skills"
            if d.exists():
                dirs.append(d)
            if p == repo:
                break
    # Plugin-local and repo-local plugin skill dirs.
    for d in [root / "skills"]:
        if d.exists():
            dirs.append(d)
    for d in root.glob("plugins/*/skills"):
        if d.exists():
            dirs.append(d)
    if include_home:
        for d in [home / ".agents" / "skills", home / ".codex" / "skills"]:
            if d.exists():
                dirs.append(d)
        cache = home / ".codex" / "plugins" / "cache"
        if cache.exists():
            for d in cache.glob("*/*/*/skills"):
                if d.exists():
                    dirs.append(d)
    seen: Set[Path] = set()
    out = []
    for d in dirs:
        if d in seen:
            continue
        seen.add(d)
        for skill_md in d.glob("*/SKILL.md"):
            text = skill_md.read_text(encoding="utf-8", errors="ignore")
            out.append({
                "name": first_yaml_field(text, "name") or skill_md.parent.name,
                "description": first_yaml_field(text, "description"),
                "path": str(skill_md),
                "scope": "user" if str(skill_md).startswith(str(home)) else "repo",
            })
    return out


def scan_plugins(root: Path, home: Path, include_home: bool = True) -> List[dict]:
    out = []
    candidates = []
    for mf in [root / ".agents" / "plugins" / "marketplace.json", home / ".agents" / "plugins" / "marketplace.json"]:
        data = read_json(mf)
        if isinstance(data, dict):
            for p in data.get("plugins", []):
                src = p.get("source", {}) if isinstance(p, dict) else {}
                out.append({
                    "name": p.get("name", "unknown"),
                    "marketplace": str(mf),
                    "source": src,
                    "category": p.get("category"),
                    "kind": "marketplace-entry",
                })
                path = src.get("path")
                if src.get("source") == "local" and path:
                    candidates.append((mf.parent.parent.parent / path).resolve())
    if include_home:
        cache = home / ".codex" / "plugins" / "cache"
        if cache.exists():
            candidates.extend(cache.glob("*/*/*"))
    candidates.extend([root / "plugins" / "goalspec", root])
    seen: Set[Path] = set()
    for d in candidates:
        manifest = d / ".codex-plugin" / "plugin.json"
        if manifest.exists() and manifest not in seen:
            seen.add(manifest)
            data = read_json(manifest) or {}
            out.append({
                "name": data.get("name", d.name),
                "version": data.get("version"),
                "description": data.get("description"),
                "path": str(manifest),
                "skills": data.get("skills"),
                "hooks": data.get("hooks"),
                "kind": "manifest",
            })
    return out


def scan_mcp(root: Path, home: Path, include_home: bool = True) -> List[dict]:
    out = []
    config_files = [root / ".codex" / "config.toml", home / ".codex" / "config.toml"] if include_home else [root / ".codex" / "config.toml"]
    for cfg in config_files:
        data = read_toml(cfg)
        if isinstance(data, dict):
            servers = data.get("mcp_servers") or data.get("mcpServers") or {}
            if isinstance(servers, dict):
                for name, spec in servers.items():
                    out.append({"name": name, "source": str(cfg), "spec_keys": sorted(spec.keys()) if isinstance(spec, dict) else []})
    for mcp in [root / ".mcp.json", root / ".codex" / ".mcp.json", home / ".codex" / ".mcp.json"]:
        data = read_json(mcp)
        if isinstance(data, dict):
            servers = data.get("mcpServers") or data.get("mcp_servers") or data
            if isinstance(servers, dict):
                for name, spec in servers.items():
                    if isinstance(spec, dict):
                        out.append({"name": name, "source": str(mcp), "spec_keys": sorted(spec.keys())})
    # Best effort CLI query. This reads the user's ~/.codex config, so it is
    # home-scoped: only run it when home scanning is explicitly opted in.
    if include_home:
        try:
            result = subprocess.run(["codex", "mcp", "list"], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                full = result.stdout.strip()
                out.append({"name": "codex mcp list", "source": "codex-cli", "output": full[:4000], "truncated": len(full) > 4000})
        except Exception:
            pass
    return out


def scan_hooks(root: Path, home: Path, include_home: bool = True) -> List[dict]:
    out = []
    hook_files = [root / ".codex" / "hooks.json", root / "hooks" / "hooks.json"]
    cfgs = [root / ".codex" / "config.toml"]
    if include_home:
        hook_files.append(home / ".codex" / "hooks.json")
        cfgs.append(home / ".codex" / "config.toml")
    for hook_file in hook_files:
        data = read_json(hook_file)
        if isinstance(data, dict):
            hooks = data.get("hooks", {})
            if isinstance(hooks, dict):
                for event, groups in hooks.items():
                    out.append({"event": event, "source": str(hook_file), "groups": len(groups) if isinstance(groups, list) else "unknown"})
    for cfg in cfgs:
        data = read_toml(cfg)
        if isinstance(data, dict) and "hooks" in data:
            out.append({"event": "inline", "source": str(cfg), "groups": "config.toml"})
    return out


def scan_subagents(root: Path, home: Path, include_home: bool = True) -> List[dict]:
    out = []
    patterns = [
        root.glob(".agents/**/openai.yaml"),
        root.glob("skills/**/agents/openai.yaml"),
        root.glob("**/agents/openai.yaml"),
    ]
    if include_home and (home / ".agents").exists():
        patterns.append((home / ".agents").glob("**/openai.yaml"))
    seen: Set[Path] = set()
    for pat in patterns:
        for y in pat:
            if y in seen:
                continue
            seen.add(y)
            out.append({"path": str(y), "name": y.parent.parent.name if y.parent.name == "agents" else y.parent.name})
    return out


def scan_project_commands(root: Path) -> List[dict]:
    out = []
    pkg = root / "package.json"
    data = read_json(pkg)
    if isinstance(data, dict) and isinstance(data.get("scripts"), dict):
        scripts = data["scripts"]
        for name in ["test", "lint", "build", "typecheck", "coverage", "check"]:
            if name in scripts:
                out.append({"name": f"npm run {name}", "source": str(pkg), "command": scripts[name]})
    for file, tool in [("pyproject.toml", "python"), ("Makefile", "make"), ("justfile", "just"), ("Taskfile.yml", "task")]:
        p = root / file
        if p.exists():
            out.append({"name": tool, "source": str(p)})
    return out


def _normalize_home(value, home_str: str):
    """Rewrite any emitted absolute home path to ~/... so inventories are shareable
    and never leak a raw /home/<user> prefix (the repo itself often lives under home).
    Replaces embedded occurrences too, not just a leading prefix."""
    if isinstance(value, str):
        if not home_str:
            return value
        if value == home_str:
            return "~"
        return value.replace(home_str + "/", "~/")
    if isinstance(value, list):
        return [_normalize_home(v, home_str) for v in value]
    if isinstance(value, dict):
        return {k: _normalize_home(v, home_str) for k, v in value.items()}
    return value


def inventory(include_home=False) -> dict:
    root = git_root_or_cwd()
    home = Path.home()
    agents_md_paths = [root / "AGENTS.md"]
    if include_home:
        agents_md_paths.insert(0, home / ".codex" / "AGENTS.md")
    inv = {
        "repo_root": str(root),
        "scanned_home": include_home,
        "toml_support": tomllib is not None,
        "skills": scan_skills(root, home, include_home),
        "plugins": scan_plugins(root, home, include_home),
        "mcp_servers": scan_mcp(root, home, include_home),
        "hooks": scan_hooks(root, home, include_home),
        "subagents": scan_subagents(root, home, include_home),
        "project_commands": scan_project_commands(root),
        "agents_md": [str(p) for p in agents_md_paths if p.exists()],
        "goals_artifacts": [str(p) for p in [root / ".goals" / "current.md", root / ".goals" / "GOALS.md", root / ".goals" / "graph.json"] if p.exists()],
    }
    home_str = str(home)
    return {k: _normalize_home(v, home_str) for k, v in inv.items()}


def md_list(items, key="name"):
    if not items:
        return "  - none found"
    lines = []
    for item in items[:20]:
        name = item.get(key) or item.get("event") or item.get("path") or "unknown"
        src = item.get("source") or item.get("path") or item.get("marketplace") or ""
        extra = item.get("description") or item.get("command") or item.get("version") or ""
        lines.append(f"  - {name}" + (f" — {extra}" if extra else "") + (f" ({src})" if src else ""))
    if len(items) > 20:
        lines.append(f"  - ... {len(items)-20} more")
    return "\n".join(lines)


def to_markdown(inv: dict) -> str:
    toml_note = "" if inv.get("toml_support", True) else "\n_TOML parsing unavailable (Python <3.11): pyproject.toml and config.toml were skipped._\n"
    return f"""# Capability Inventory

Repo root: `{inv['repo_root']}`
{toml_note}
## Skills
{md_list(inv['skills'])}

## Plugins
{md_list(inv['plugins'])}

## MCP servers
{md_list(inv['mcp_servers'])}

## Hooks
{md_list(inv['hooks'], key='event')}

## Subagents / custom agents
{md_list(inv['subagents'], key='name')}

## Project commands
{md_list(inv['project_commands'])}

## AGENTS.md guidance
{md_list([{'name': p} for p in inv['agents_md']])}

## .goals artifacts
{md_list([{'name': p} for p in inv['goals_artifacts']])}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--include-home", action="store_true",
                        help="Also scan home/user directories (~/.codex, ~/.agents, plugin cache). Default is repo-local only.")
    parser.add_argument("--write", help="Write inventory to file")
    args = parser.parse_args()
    inv = inventory(include_home=args.include_home)
    output = json.dumps(inv, indent=2, ensure_ascii=False) if args.format == "json" else to_markdown(inv)
    if args.write:
        p = Path(args.write)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(output, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
