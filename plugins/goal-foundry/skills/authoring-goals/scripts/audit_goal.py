#!/usr/bin/env python3
"""Audit a Goal Foundry run report against a frozen goal contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import REPORT_FIELDS, current_hash_status, parse_sections, bullets


def audit(contract: Path, report: Path | None = None, evidence_dir: Path | None = None) -> dict:
    result = {
        "result": "inconclusive",
        "contract": str(contract),
        "report": str(report) if report else None,
        "errors": [],
        "warnings": [],
        "satisfied_checks": [],
        "missing_checks": [],
    }
    if not contract.exists():
        result["result"] = "not achieved"
        result["errors"].append(f"Missing contract: {contract}")
        return result
    hash_status = current_hash_status(str(contract.parent.parent if contract.parent.name == ".goals" else Path.cwd()))
    result["hash_status"] = hash_status
    if hash_status.get("matched") is False:
        result["result"] = "contract mutated"
        result["errors"].append("Contract hash mismatch; current.md changed after launch")

    contract_sections = parse_sections(contract.read_text(encoding="utf-8"))
    terminal_count = len(bullets(contract_sections.get("Terminal State", "")))
    verifier_count = len(bullets(contract_sections.get("Verifier", "")))
    if terminal_count:
        result["satisfied_checks"].append(f"Contract has {terminal_count} terminal-state clause(s)")
    if verifier_count:
        result["satisfied_checks"].append(f"Contract has {verifier_count} verifier clause(s)")

    if report and report.exists():
        rtext = report.read_text(encoding="utf-8")
        rsections = parse_sections(rtext)
        for field in REPORT_FIELDS:
            if field not in rsections or not rsections[field].strip():
                result["missing_checks"].append(f"Report missing or empty section: ## {field}")
            else:
                result["satisfied_checks"].append(f"Report contains ## {field}")
        if "achieved" in rtext.lower() and result["missing_checks"]:
            result["warnings"].append("Report appears to claim achievement but lacks required evidence fields")
    else:
        result["missing_checks"].append("No run report provided or report file missing")

    evidence_dir = evidence_dir or contract.parent / "evidence"
    if evidence_dir.exists() and any(evidence_dir.rglob("*")):
        result["satisfied_checks"].append(f"Evidence directory has files: {evidence_dir}")
    else:
        result["missing_checks"].append(f"Evidence directory is missing or empty: {evidence_dir}")

    if result["errors"]:
        pass
    elif result["missing_checks"]:
        result["result"] = "inconclusive"
    else:
        result["result"] = "achieved"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", nargs="?", default=".goals/current.md")
    parser.add_argument("--report", help="Run report markdown path")
    parser.add_argument("--evidence-dir", default=".goals/evidence")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    res = audit(Path(args.contract), Path(args.report) if args.report else None, Path(args.evidence_dir))
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(f"Audit result: {res['result']}")
        for x in res["errors"]:
            print(f"ERROR: {x}")
        for x in res["warnings"]:
            print(f"WARN: {x}")
        for x in res["missing_checks"]:
            print(f"MISSING: {x}")
        for x in res["satisfied_checks"]:
            print(f"OK: {x}")
    return 0 if res["result"] == "achieved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
