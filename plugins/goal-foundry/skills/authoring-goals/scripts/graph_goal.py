#!/usr/bin/env python3
"""Initialize or update .goals/graph.json with goal nodes and relationships."""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from common import parse_sections


def load(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"schema": "goal-foundry.graph.v1", "created": date.today().isoformat(), "nodes": {}, "edges": []}


def contract_metadata(contract: Path) -> tuple[str, dict]:
    text = contract.read_text(encoding="utf-8")
    m = re.search(r"^#\s+Goal Contract:\s*(.+?)\s*$", text, re.M)
    title = m.group(1).strip() if m else contract.stem
    gid_match = re.match(r"(G-\d+)", title)
    gid = gid_match.group(1) if gid_match else contract.stem
    sec = parse_sections(text)
    node = {
        "title": title,
        "status": "active" if contract.name == "current.md" else "ready",
        "contract": contract.as_posix(),
        "objective": " ".join(sec.get("Objective", "").split())[:300],
        "risk": "medium",
        "updated": date.today().isoformat(),
    }
    return gid, node


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default=".goals/graph.json")
    parser.add_argument("--add-contract", help="Add/update node from a goal contract markdown file")
    parser.add_argument("--id", help="Node id override")
    parser.add_argument("--status", help="Node status override")
    parser.add_argument("--edge", nargs=3, metavar=("FROM", "TYPE", "TO"), action="append", help="Add edge, e.g. G-002 depends_on G-001")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    path = Path(args.graph)
    data = load(path)
    if args.add_contract:
        gid, node = contract_metadata(Path(args.add_contract))
        if args.id:
            gid = args.id
        if args.status:
            node["status"] = args.status
        data.setdefault("nodes", {})[gid] = {**data.setdefault("nodes", {}).get(gid, {}), **node}
    if args.edge:
        existing = {(e.get("from"), e.get("type"), e.get("to")) for e in data.setdefault("edges", [])}
        for fr, typ, to in args.edge:
            if (fr, typ, to) not in existing:
                data["edges"].append({"from": fr, "type": typ, "to": to})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"Updated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
