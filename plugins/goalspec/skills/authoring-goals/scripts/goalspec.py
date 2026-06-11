#!/usr/bin/env python3
"""GoalSpec helper CLI for Codex projects.

Semantic authoring belongs to the $authoring-goals skill. This wrapper delegates to
deterministic helper scripts for scaffolding, validation, rendering, inventory,
selection, graph/ledger updates, verifier runs, and audits.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

COMMANDS = {
    "init": ("init_project", "Initialize .goals artifacts"),
    "inventory": ("inventory_capabilities", "Inventory Codex capabilities"),
    "validate": ("validate_goal", "Validate/lock .goals/current.md"),
    "render": ("render_goal", "Render a paste-ready Codex /goal objective"),
    "risk": ("score_goal_risk", "Score raw goal text for runaway risk"),
    "extract": ("extract_candidates", "Extract candidate goals from files/folders"),
    "provenance": ("record_provenance", "Record the verbatim request as provenance (not execution scope)"),
    "select": ("select_goal", "Select next ready unblocked goal"),
    "graph": ("graph_goal", "Update .goals/graph.json"),
    "ledger": ("update_ledger", "Update .goals/GOALS.md"),
    "audit": ("audit_goal", "Audit a run against the current contract"),
    "verifiers": ("run_verifiers", "List or run verifier commands from a contract"),
    "launch": ("launch_goal", "Launch a frozen goal or campaign with an external wall-clock bound"),
    "validate-campaign": ("validate_campaign", "Validate/lock a campaign manifest for chain execution"),
    "campaign-status": ("campaign_status", "Derive chain status from per-child verifier evidence"),
    "audit-campaign": ("audit_campaign", "Audit a completed campaign chain (lock gate + per-child roll-up)"),
}


def usage() -> str:
    lines = ["Usage: goalspec.py <command> [args...]", "", "Commands:"]
    width = max(len(k) for k in COMMANDS)
    for k, (_, desc) in COMMANDS.items():
        lines.append(f"  {k:<{width}}  {desc}")
    lines.append("\nUse `goalspec.py <command> --help` for command-specific help.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print(usage())
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}\n\n{usage()}", file=sys.stderr)
        return 2
    script = SCRIPT_DIR / f"{COMMANDS[cmd][0]}.py"
    return subprocess.call([sys.executable, str(script), *rest])


if __name__ == "__main__":
    raise SystemExit(main())
