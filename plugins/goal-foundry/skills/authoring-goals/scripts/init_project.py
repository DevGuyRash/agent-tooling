#!/usr/bin/env python3
"""Initialize Goal Foundry project artifacts in a Codex workspace."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

from common import git_root_or_cwd

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATES = SKILL_DIR / "assets" / "templates"
AGENTS_SNIPPET = SKILL_DIR / "assets" / "AGENTS.snippet.md"
CODEX_AGENT_TEMPLATES = SKILL_DIR / "assets" / "codex-agents"

DIRS = [
    "candidates",
    "completed",
    "abandoned",
    "blocked",
    "reports",
    "evidence",
    "evidence/events",
    "decisions",
]


def copy_if_missing(src: Path, dst: Path, overwrite: bool = False) -> bool:
    if dst.exists() and not overwrite:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def init(root: Path, overwrite: bool = False, install_agents: bool = False, append_agents_md: bool = False) -> dict:
    root = root.resolve()
    goals = root / ".goals"
    created = []
    for d in DIRS:
        p = goals / d
        p.mkdir(parents=True, exist_ok=True)
        created.append(str(p.relative_to(root)))

    mapping = {
        TEMPLATES / "GOALS.md": goals / "GOALS.md",
        TEMPLATES / "frontier.md": goals / "frontier.md",
        TEMPLATES / "report.md": goals / "reports" / "report-template.md",
        TEMPLATES / "campaign.md": goals / "campaign-template.md",
        TEMPLATES / "current.md": goals / "current.template.md",
    }
    copied = []
    for src, dst in mapping.items():
        if copy_if_missing(src, dst, overwrite):
            copied.append(str(dst.relative_to(root)))

    graph = goals / "graph.json"
    if overwrite or not graph.exists():
        graph.write_text(json.dumps({
            "schema": "goal-foundry.graph.v1",
            "created": date.today().isoformat(),
            "nodes": {},
            "edges": []
        }, indent=2) + "\n", encoding="utf-8")
        copied.append(str(graph.relative_to(root)))

    snippet_target = goals / "AGENTS.goal-foundry.snippet.md"
    if AGENTS_SNIPPET.exists() and copy_if_missing(AGENTS_SNIPPET, snippet_target, overwrite):
        copied.append(str(snippet_target.relative_to(root)))

    if append_agents_md:
        agents = root / "AGENTS.md"
        snippet = AGENTS_SNIPPET.read_text(encoding="utf-8")
        marker = "## Goal Foundry rule"
        old = agents.read_text(encoding="utf-8") if agents.exists() else ""
        if marker not in old:
            agents.write_text((old.rstrip() + "\n\n" + snippet.strip() + "\n") if old else snippet.strip() + "\n", encoding="utf-8")
            copied.append(str(agents.relative_to(root)))

    if install_agents:
        target_dir = root / ".codex" / "agents"
        target_dir.mkdir(parents=True, exist_ok=True)
        for src in CODEX_AGENT_TEMPLATES.glob("*.toml"):
            dst = target_dir / src.name
            if copy_if_missing(src, dst, overwrite):
                copied.append(str(dst.relative_to(root)))

    return {"root": str(root), "created_dirs": created, "created_or_updated_files": copied}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="Workspace root. Defaults to git root or cwd.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing template files.")
    parser.add_argument("--install-agents", action="store_true", help="Copy optional read-only custom agent templates into .codex/agents/.")
    parser.add_argument("--append-agents-md", action="store_true", help="Append the compact Goal Foundry rule to AGENTS.md if absent.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else git_root_or_cwd()
    result = init(root, args.overwrite, args.install_agents, args.append_agents_md)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Initialized Goal Foundry at {result['root']}")
        for p in result["created_or_updated_files"]:
            print(f"- {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
