#!/usr/bin/env python3
"""Select the next launchable goal from .goals/GOALS.md or graph.json."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List, Dict

STATUS_ORDER = {"ready": 0, "conditional": 5, "blocked": 99, "not-launchable": 99, "completed": 99, "abandoned": 99}
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "extreme": 3}


def parse_goals_md(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    entries = []
    current_section = ""
    blocks = re.split(r"(?m)^###\s+", text)
    pre = blocks[0]
    # Section inference is approximate; each goal should carry Status.
    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        body = "\n".join(lines[1:])
        def field(name: str, default: str = "") -> str:
            m = re.search(rf"(?mi)^-\s*{re.escape(name)}:\s*(.+?)\s*$", body)
            return m.group(1).strip() if m else default
        status = field("Status", "conditional").lower()
        risk = field("Risk", "medium").lower()
        depends = field("Depends on", "none")
        entries.append({
            "title": title,
            "status": status,
            "risk": risk,
            "depends_on": depends,
            "contract": field("Contract", ""),
            "terminal_state": field("Terminal state", ""),
            "verifier": field("Verifier", ""),
        })
    return entries


def parse_graph(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    entries = []
    # Support both graph schema variants used by Goal Foundry helpers:
    # {"nodes": {"G-001": {...}}, "edges": [...]} and {"goals": [{...}], "edges": [...]}.
    if isinstance(data.get("nodes"), dict):
        edges = data.get("edges", [])
        blocked_by = {}
        for e in edges:
            if e.get("type") == "depends_on":
                blocked_by.setdefault(e.get("from"), []).append(e.get("to"))
        for gid, node in data.get("nodes", {}).items():
            entries.append({
                "id": gid,
                "title": node.get("title", gid),
                "status": node.get("status", "conditional").lower(),
                "risk": node.get("risk", "medium").lower(),
                "depends_on": ", ".join(blocked_by.get(gid, [])) or node.get("depends_on", "none"),
                "contract": node.get("contract", ""),
                "verifier": node.get("verifier", ""),
            })
    if isinstance(data.get("goals"), list):
        for node in data.get("goals", []):
            gid = node.get("id") or node.get("title", "unknown")
            depends = node.get("depends_on") or "none"
            if isinstance(depends, list):
                depends = ", ".join(depends) if depends else "none"
            entries.append({
                "id": gid,
                "title": node.get("title", gid),
                "status": str(node.get("status", "conditional")).lower(),
                "risk": str(node.get("risk", "medium")).lower(),
                "depends_on": depends,
                "contract": node.get("contract", ""),
                "verifier": node.get("verifier", ""),
            })
    return entries


def is_unblocked(entry: Dict[str, str], completed_ids: set[str]) -> bool:
    deps = entry.get("depends_on", "none")
    if not deps or deps.lower() in {"none", "n/a", "[]"}:
        return True
    parts = [p.strip(" `[]") for p in re.split(r"[,\s]+", deps) if p.strip()]
    ids = [p for p in parts if re.match(r"[A-Z]-?\d+|G-\d+", p)]
    return all(d in completed_ids for d in ids)


def select(entries: List[Dict[str, str]]) -> dict:
    completed = {e.get("id") or e.get("title", "").split(":", 1)[0] for e in entries if e.get("status") == "completed"}
    candidates = []
    for i, e in enumerate(entries):
        if e.get("status") != "ready":
            continue
        if not is_unblocked(e, completed):
            continue
        score = STATUS_ORDER.get(e.get("status", "conditional"), 50) + RISK_ORDER.get(e.get("risk", "medium"), 2)
        if e.get("contract") and "pending" not in e.get("contract", "").lower():
            score -= 1
        candidates.append((score, i, e))
    if not candidates:
        return {"selected": None, "reason": "No ready, unblocked goal found."}
    _, _, chosen = sorted(candidates, key=lambda x: (x[0], x[1]))[0]
    return {"selected": chosen, "reason": "Selected lowest-risk ready unblocked goal."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goals", default=".goals/GOALS.md")
    parser.add_argument("--graph", default=".goals/graph.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    entries = parse_graph(Path(args.graph)) or parse_goals_md(Path(args.goals))
    result = select(entries)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if not result["selected"]:
            print("No launchable goal selected: " + result["reason"])
        else:
            s = result["selected"]
            print("Selected goal:")
            for k, v in s.items():
                print(f"- {k}: {v}")
            print("Reason: " + result["reason"])
    return 0 if result["selected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
