#!/usr/bin/env python3
"""Update or initialize .goals/GOALS.md with a lightweight registry entry."""
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from common import parse_sections, split_goal_id_title

DEFAULT_LEDGER = """# GOALS.md

This file is a registry, not an execution target. Do not run `/goal` against this entire file. Compile one ready item into `.goals/current.md` before execution.

## Active

_No active goal._

## Ready

## Conditional

## Blocked / Not Launchable

## Completed

## Abandoned

## Follow-Up Candidates
"""


def title_from_contract(text: str) -> str:
    m = re.search(r"^#\s+Goal Contract:\s*(.+?)\s*$", text, re.M)
    return m.group(1).strip() if m else "Untitled goal"


def objective_from_contract(text: str) -> str:
    sec = parse_sections(text).get("Objective", "").strip()
    return " ".join(sec.split())[:240] if sec else ""


def insert_under_heading(ledger: str, heading: str, entry: str) -> str:
    pattern = rf"(^##\s+{re.escape(heading)}\s*$)"
    m = re.search(pattern, ledger, re.M)
    if not m:
        return ledger.rstrip() + f"\n\n## {heading}\n\n{entry}\n"
    insert_at = m.end()
    return ledger[:insert_at] + "\n\n" + entry.rstrip() + "\n" + ledger[insert_at:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", default=".goals/current.md")
    parser.add_argument("--ledger", default=".goals/GOALS.md")
    parser.add_argument("--status", default="active", choices=["active", "ready", "conditional", "blocked", "completed", "abandoned", "follow-up"])
    parser.add_argument("--id", default=None)
    args = parser.parse_args()

    current = Path(args.current)
    ledger = Path(args.ledger)
    if not current.exists():
        raise SystemExit(f"Missing current contract: {current}")
    text = current.read_text(encoding="utf-8")
    raw_title = title_from_contract(text)
    # Split the "G-001 Title" heading into id + title so the entry reads
    # "### G-001: Title" instead of doubling the id into the title.
    gid_part, title = split_goal_id_title(raw_title)
    goal_id = args.id or gid_part or "G-000"
    objective = objective_from_contract(text)
    heading_map = {
        "active": "Active",
        "ready": "Ready",
        "conditional": "Conditional",
        "blocked": "Blocked / Not Launchable",
        "completed": "Completed",
        "abandoned": "Abandoned",
        "follow-up": "Follow-Up Candidates",
    }
    heading = heading_map[args.status]
    entry = f"""### {goal_id}: {title}

- Status: {args.status}
- Updated: {date.today().isoformat()}
- Contract: `{current.as_posix()}`
- Objective: {objective}
"""
    old = ledger.read_text(encoding="utf-8") if ledger.exists() else DEFAULT_LEDGER
    if args.status == "active":
        # A goal is now active, so drop the "no active goal" placeholder.
        old = old.replace("\n_No active goal._\n", "\n")
    new = insert_under_heading(old, heading, entry)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(new, encoding="utf-8")
    print(f"Updated {ledger} under ## {heading}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
