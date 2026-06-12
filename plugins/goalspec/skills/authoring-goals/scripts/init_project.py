#!/usr/bin/env python3
"""Initialize GoalSpec project artifacts in a Codex workspace."""
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
    "provenance",
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


GITIGNORE_MARKER = "# GoalSpec evidence hygiene"
GITIGNORE_BLOCK = (
    f"{GITIGNORE_MARKER}\n"
    "# Evidence may hold raw tool I/O (best-effort redacted) and runtime state — keep it local.\n"
    "# Reports stay tracked so completed runs remain reviewable.\n"
    ".goals/evidence/\n"
    ".goals/run_state.json\n"
)


def ensure_gitignore(root: Path) -> bool:
    """Append GoalSpec evidence-ignore rules to .gitignore (idempotent). Reports stay reviewable."""
    gi = root / ".gitignore"
    old = gi.read_text(encoding="utf-8") if gi.exists() else ""
    if GITIGNORE_MARKER in old:
        return False
    gi.write_text((old.rstrip() + "\n\n" + GITIGNORE_BLOCK) if old.strip() else GITIGNORE_BLOCK, encoding="utf-8")
    return True


def init(root: Path, overwrite: bool = False, install_agents: bool = True, append_agents_md: bool = False,
         write_gitignore: bool = True) -> dict:
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
        TEMPLATES / "provenance.md": goals / "provenance" / "provenance-template.md",
    }
    copied = []
    for src, dst in mapping.items():
        if copy_if_missing(src, dst, overwrite):
            copied.append(str(dst.relative_to(root)))

    graph = goals / "graph.json"
    if overwrite or not graph.exists():
        graph.write_text(json.dumps({
            "schema": "goalspec.graph.v1",
            "created": date.today().isoformat(),
            "nodes": {},
            "edges": []
        }, indent=2) + "\n", encoding="utf-8")
        copied.append(str(graph.relative_to(root)))

    snippet_target = goals / "AGENTS.goalspec.snippet.md"
    if AGENTS_SNIPPET.exists() and copy_if_missing(AGENTS_SNIPPET, snippet_target, overwrite):
        copied.append(str(snippet_target.relative_to(root)))

    if append_agents_md:
        agents = root / "AGENTS.md"
        snippet = AGENTS_SNIPPET.read_text(encoding="utf-8")
        marker = "## GoalSpec rule"
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

    if write_gitignore and ensure_gitignore(root):
        copied.append(".gitignore")

    return {"root": str(root), "created_dirs": created, "created_or_updated_files": copied}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="Workspace root. Defaults to git root or cwd.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing template files.")
    parser.add_argument("--install-agents", action="store_true",
                        help="Deprecated no-op: the read-only agent templates install by default; use --no-agents to opt out.")
    parser.add_argument("--no-agents", action="store_true",
                        help="Skip installing the read-only .codex/agents/*.toml agent templates.")
    parser.add_argument("--append-agents-md", action="store_true", help="Append the compact GoalSpec rule to AGENTS.md if absent.")
    parser.add_argument("--no-gitignore", action="store_true", help="Do not write GoalSpec evidence-ignore rules to .gitignore.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else git_root_or_cwd()
    # Explicit opt-out beats the deprecated no-op opt-in when both are passed.
    result = init(root, args.overwrite, install_agents=not args.no_agents,
                  append_agents_md=args.append_agents_md, write_gitignore=not args.no_gitignore)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Initialized GoalSpec at {result['root']}")
        for p in result["created_or_updated_files"]:
            print(f"- {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
