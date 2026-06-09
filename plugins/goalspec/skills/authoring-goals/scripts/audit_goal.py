#!/usr/bin/env python3
"""Audit a GoalSpec run report against a frozen goal contract."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import (
    REPORT_FIELDS,
    VERIFIER_RESULT_SCHEMA,
    bullets,
    current_hash_status,
    extract_verifier_commands,
    parse_sections,
    verifier_kinds,
    verifier_result_path,
)

# Phrases an executor may write into the report's ## Result line. These can only
# DOWNGRADE the verdict (declare blocked / scope violation); they can never
# upgrade to "achieved" — only a passing verifier result does that.
_SCOPE_DECL = re.compile(r"scope[\s-]?violation|out[\s-]?of[\s-]?scope", re.I)
_BLOCKED_DECL = re.compile(r"\bblocked\b", re.I)


def _load_verifier_result(evidence_dir: Path | None, explicit: Path | None) -> tuple[Path | None, dict | None]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit)
    if evidence_dir:
        candidates.append(verifier_result_path(evidence_dir))  # <evidence>/verifiers/result.json
        candidates.append(evidence_dir / "verifiers" / "result.json")
        candidates.append(evidence_dir / "result.json")
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return path, None
            return path, (data if isinstance(data, dict) else None)
    return None, None


def _report_result_decl(report_text: str) -> str:
    body = parse_sections(report_text).get("Result", "")
    for line in body.splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def audit(contract: Path, report: Path | None = None, evidence_dir: Path | None = None,
          verifier_result: Path | None = None) -> dict:
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
    hash_matched = hash_status.get("matched")

    contract_sections = parse_sections(contract.read_text(encoding="utf-8"))
    verifier_section = contract_sections.get("Verifier", "")
    terminal_count = len(bullets(contract_sections.get("Terminal State", "")))
    declared_kinds = verifier_kinds(verifier_section)
    has_exec_verifier = bool(extract_verifier_commands(verifier_section))
    declares_nonexec = bool(declared_kinds & {"human", "artifact", "mcp"})
    if terminal_count:
        result["satisfied_checks"].append(f"Contract has {terminal_count} terminal-state clause(s)")
    result["satisfied_checks"].append(f"Contract verifier kinds: {sorted(declared_kinds) or ['unclassified']}")

    # --- Report sections (presence is necessary but never sufficient) ---
    report_sections_ok = True
    report_decl = ""
    if report and report.exists():
        rtext = report.read_text(encoding="utf-8")
        report_decl = _report_result_decl(rtext)
        normalized = {k.strip().lower(): v for k, v in parse_sections(rtext).items()}
        for field in REPORT_FIELDS:
            body = normalized.get(field.strip().lower())
            if (not body or not body.strip()) and re.search(rf"^#{{2,4}}\s+{re.escape(field)}\s*$", rtext, re.I | re.M):
                body = "present"  # heading exists at a non-level-2 depth
            if not body or not body.strip():
                report_sections_ok = False
                result["missing_checks"].append(f"Report missing or empty section: ## {field}")
            else:
                result["satisfied_checks"].append(f"Report contains ## {field}")
    else:
        report_sections_ok = False
        result["missing_checks"].append("No run report provided or report file missing")

    # --- Evidence directory (presence is necessary but never sufficient) ---
    evidence_dir = evidence_dir or contract.parent / "evidence"
    evidence_present = evidence_dir.exists() and any(evidence_dir.rglob("*"))
    if evidence_present:
        result["satisfied_checks"].append(f"Evidence directory has files: {evidence_dir}")
    else:
        result["missing_checks"].append(f"Evidence directory is missing or empty: {evidence_dir}")

    # --- The verifier result file is the deterministic oracle ---
    vres_path, vres = _load_verifier_result(evidence_dir, verifier_result)
    overall_passed = None
    if vres_path and vres is None:
        result["warnings"].append(f"Verifier result file present but unreadable/invalid: {vres_path}")
    elif vres is not None:
        if vres.get("schema") != VERIFIER_RESULT_SCHEMA:
            result["warnings"].append(f"Verifier result schema is not {VERIFIER_RESULT_SCHEMA}: {vres.get('schema')!r}")
        overall_passed = bool(vres.get("overall_passed"))
        passed_n = sum(1 for v in vres.get("verifiers", []) if v.get("passed"))
        total_n = len(vres.get("verifiers", []))
        result["verifier_result"] = {"path": str(vres_path), "overall_passed": overall_passed,
                                     "passed": passed_n, "total": total_n}
        if overall_passed:
            result["satisfied_checks"].append(f"Verifier result PASSED ({passed_n}/{total_n})")
        else:
            result["missing_checks"].append(f"Verifier result did NOT pass ({passed_n}/{total_n})")
    else:
        if has_exec_verifier:
            result["missing_checks"].append(
                "No verifier result file; run run_verifiers.py --run to produce the oracle artifact")
        elif declares_nonexec:
            result["warnings"].append(
                "Contract declares a non-executable verifier (human/artifact/MCP); relying on report attestation as the recorded oracle")
        else:
            result["missing_checks"].append(
                "Verifier is neither an executable command nor a declared human/artifact/MCP gate; audit cannot confirm pass")

    # --- Derive the verdict deterministically (oracle-first) ---
    if hash_matched is False:
        result["result"] = "contract mutated"
        result["errors"].append("Contract hash mismatch; current.md changed after launch")
    elif report_decl and _SCOPE_DECL.search(report_decl):
        result["result"] = "scope violation"
        result["errors"].append(f"Run report declares a scope violation: {report_decl!r}")
    elif overall_passed is False:
        result["result"] = "not achieved"
        result["errors"].append("Verifier evidence did not pass; goal is not achieved")
    elif overall_passed is True:
        if report_sections_ok and evidence_present and hash_matched is True:
            result["result"] = "achieved"
        else:
            result["result"] = "inconclusive"
            if hash_matched is not True:
                result["warnings"].append("Verifier passed but contract hash is not locked/matched; cannot certify achieved")
    elif report_decl and _BLOCKED_DECL.search(report_decl):
        result["result"] = "blocked"
        result["warnings"].append(f"Run report declares the goal blocked: {report_decl!r}")
    elif declares_nonexec and not has_exec_verifier:
        # Human/artifact/MCP oracle: the report attestation is the recorded result.
        achieved_claim = bool(re.search(r"\bachieved\b", report_decl, re.I)) and not re.search(r"not\s+achieved", report_decl, re.I)
        if achieved_claim and report_sections_ok and evidence_present and hash_matched is True:
            result["result"] = "achieved"
        else:
            result["result"] = "inconclusive"
    else:
        result["result"] = "inconclusive"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", nargs="?", default=".goals/current.md")
    parser.add_argument("--report", help="Run report markdown path")
    parser.add_argument("--evidence-dir", default=".goals/evidence")
    parser.add_argument("--verifier-result", help="Explicit path to the goalspec.verifier.v1 result file")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    res = audit(
        Path(args.contract),
        Path(args.report) if args.report else None,
        Path(args.evidence_dir),
        Path(args.verifier_result) if args.verifier_result else None,
    )
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
