#!/usr/bin/env python3
"""Record a verbatim request as provenance and emit only a pointer for current.md.

The renderer tells the executor to treat .goals/current.md as the source of truth,
so the raw request must never live inside current.md — an inline sprawl would be
execution-visible and could re-attract a vague run. This writes the verbatim
request to .goals/provenance/<id>.md (reference only, not execution scope) and
returns a compact ## Provenance pointer (artifact path + request hash) to place in
current.md instead.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from common import contract_lock_status, sha256_text

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE = SCRIPT_DIR.parent / "assets" / "templates" / "provenance.md"

_FALLBACK_TEMPLATE = (
    "# Provenance: G-000\n\n"
    "> Reference only. Not execution scope. Execute only the frozen .goals/current.md.\n\n"
    "## Original Request\n\n[verbatim]\n\n## Source\n\n[source]\n\n"
    "## Compiled-Into\n\n- Contract: .goals/current.md\n- Contract hash: pending\n"
    "- Request hash: pending\n- Compiled: YYYY-MM-DD\n"
)


def _replace_section(text: str, name: str, body: str) -> str:
    pattern = re.compile(rf"(^##\s+{re.escape(name)}\s*\n)(.*?)(?=^##\s|\Z)", re.S | re.M)
    new, n = pattern.subn(lambda m: m.group(1) + "\n" + body.rstrip() + "\n\n", text)
    if n == 0:
        new = text.rstrip() + f"\n\n## {name}\n\n{body.rstrip()}\n"
    return new


def _derive_goal_id(contract: Path) -> str:
    if contract.exists():
        head = contract.read_text(encoding="utf-8").splitlines()[:1]
        if head:
            m = re.search(r"\bG-\d+\b", head[0])
            if m:
                return m.group(0)
    return "current"


def build_provenance(request: str, goal_id: str, source: str, contract: Path) -> tuple[str, str, str]:
    request_hash = sha256_text(request.strip())
    ls = contract_lock_status(contract) if contract.exists() else {}
    contract_hash = ls.get("expected_hash") or ls.get("current_hash") or "pending"
    text = TEMPLATE.read_text(encoding="utf-8") if TEMPLATE.exists() else _FALLBACK_TEMPLATE
    text = re.sub(r"^# Provenance:.*$", f"# Provenance: {goal_id}", text, count=1, flags=re.M)
    text = _replace_section(text, "Original Request", request.strip())
    text = _replace_section(text, "Source", source.strip() or "[unspecified]")
    compiled = (
        "- Contract: .goals/current.md\n"
        f"- Contract hash: {contract_hash}\n"
        f"- Request hash: {request_hash}\n"
        f"- Compiled: {date.today().isoformat()}"
    )
    text = _replace_section(text, "Compiled-Into", compiled)
    return text, request_hash, contract_hash


def pointer_block(goal_id: str, request_hash: str) -> str:
    return (
        "## Provenance\n\n"
        f"- Artifact: .goals/provenance/{goal_id}.md\n"
        f"- Request hash: {request_hash}\n"
        "- Reference only; not execution scope. The verbatim original request lives in the artifact "
        "and must not be executed or re-derived. Execute only this frozen contract.\n"
    )


def update_contract(contract: Path, block: str) -> bool:
    if not contract.exists():
        return False
    text = contract.read_text(encoding="utf-8")
    if re.search(r"^##\s+Provenance\s*$", text, re.M):
        text = re.sub(r"(^##\s+Provenance\s*\n)(.*?)(?=^##\s|\Z)", block + "\n", text, flags=re.S | re.M)
    else:
        m = re.search(r"^##\s+Objective\s*$", text, re.M)
        if m:
            text = text[: m.start()] + block + "\n" + text[m.start():]
        else:
            text = text.rstrip() + "\n\n" + block
    contract.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", default="-", help="Path to the verbatim request file, or - for stdin.")
    parser.add_argument("--id", default=None, help="Goal id for the artifact name (default: derived from contract, else 'current').")
    parser.add_argument("--source", default="", help="Where the request came from (user prompt, issue #, PRD path).")
    parser.add_argument("--goals-dir", default=".goals")
    parser.add_argument("--contract", default=".goals/current.md")
    parser.add_argument("--update-contract", action="store_true", help="Insert/replace the ## Provenance pointer in the contract.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    request = sys.stdin.read() if args.request == "-" else Path(args.request).read_text(encoding="utf-8")
    if not request.strip():
        print("Refusing to record empty provenance.", file=sys.stderr)
        return 2

    contract = Path(args.contract)
    goal_id = args.id or _derive_goal_id(contract)
    prov_text, request_hash, contract_hash = build_provenance(request, goal_id, args.source, contract)

    artifact = Path(args.goals_dir) / "provenance" / f"{goal_id}.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(prov_text, encoding="utf-8")

    block = pointer_block(goal_id, request_hash)
    updated = update_contract(contract, block) if args.update_contract else False

    result = {
        "artifact": str(artifact),
        "goal_id": goal_id,
        "request_hash": request_hash,
        "contract_hash": contract_hash,
        "contract_updated": updated,
        "pointer": block,
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Wrote provenance artifact: {artifact}")
        print(f"Request hash: {request_hash}")
        if updated:
            print(f"Inserted ## Provenance pointer into {contract}")
        else:
            print("Paste this ## Provenance pointer into current.md (do NOT paste the request):\n")
            print(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
