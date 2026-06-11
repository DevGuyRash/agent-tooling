#!/usr/bin/env python3
"""Audit a GoalSpec run report against a frozen goal contract."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import (
    PROVENANCE_REQUEST_BEGIN,
    PROVENANCE_REQUEST_END,
    REPORT_FIELDS,
    VERIFIER_RESULT_SCHEMA,
    bullets,
    contract_lock_status,
    extract_verifier_commands,
    parse_sections,
    sha256_text,
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


def _request_candidates(text: str) -> list:
    """Admissible readings of a provenance artifact's verbatim request.

    The request is arbitrary text (a PRD carries its own ## headings), so no
    single markdown parse is canonical (evt-0188). sha256 equality against the
    contract pointer decides the match, which makes extra candidates safe:
    they can only clear false drift alarms, never falsely accept. Ordered most
    exact first: marker envelope (current writer; first-BEGIN to last-END, so
    marker strings inside the request still round-trip), then the span from
    '## Original Request' to the artifact's own trailing '## Source' heading
    (legacy marker-less artifacts, including heading-bearing requests), then
    the plain section parse (hand-written artifacts without a Source section).
    """
    candidates: list = []
    begin = text.find(PROVENANCE_REQUEST_BEGIN)
    end = text.rfind(PROVENANCE_REQUEST_END)
    if begin != -1 and end > begin:
        candidates.append(("markers", text[begin + len(PROVENANCE_REQUEST_BEGIN):end]))
    head = re.search(r"^##\s+Original Request\s*$", text, re.M)
    if head:
        trailing_sources = [m for m in re.finditer(r"^##\s+Source\s*$", text, re.M)
                            if m.start() > head.end()]
        if trailing_sources:
            candidates.append(("heading-span", text[head.end():trailing_sources[-1].start()]))
    section = parse_sections(text).get("Original Request", "")
    if section.strip():
        candidates.append(("section", section))
    return [(via, c.strip()) for via, c in candidates if c.strip()]


def _provenance_check(contract_sections: dict, contract: Path) -> dict:
    """Read the ## Provenance pointer as a drift/completeness anchor (informational).

    Never gates the verdict — provenance is reference only — but surfaces whether the
    verbatim request is preserved and still matches the pointer's request hash.
    """
    info: dict = {"present": False}
    prov = contract_sections.get("Provenance", "")
    if not prov.strip():
        return info
    info["present"] = True
    m_art = re.search(r"Artifact:\s*(\S+)", prov)
    m_hash = re.search(r"Request hash:\s*([0-9a-fA-F]{64}|pending)", prov)
    info["artifact"] = m_art.group(1) if m_art else None
    info["pointer_hash"] = m_hash.group(1) if m_hash else None
    if not info["artifact"]:
        return info
    root = contract.parent.parent if contract.parent.name == ".goals" else Path.cwd()
    art_path = (root / info["artifact"])
    info["artifact_exists"] = art_path.exists()
    if art_path.exists():
        try:
            candidates = _request_candidates(art_path.read_text(encoding="utf-8"))
        except OSError:
            info["matched"] = None
            return info
        info["artifact_request_hash"] = sha256_text(candidates[0][1]) if candidates else None
        pointer = info.get("pointer_hash")
        if pointer in (None, "pending"):
            info["matched"] = False
        else:
            matched_via = next((via for via, c in candidates if sha256_text(c) == pointer), None)
            info["matched"] = matched_via is not None
            if matched_via:
                info["matched_via"] = matched_via
                info["artifact_request_hash"] = pointer
    return info


def _human_gate_resolved(report_text: str) -> bool:
    """True when the report records an explicit human ratification.

    A declared human gate is an oracle the executor cannot satisfy itself;
    certifying achieved while it is pending is self-ratification by omission
    (observed live: two runs audited achieved off the command oracle alone
    while the human gate was still pending the owner).
    """
    for line in report_text.splitlines():
        lowered = line.lower()
        if "human" not in lowered:
            continue
        if not re.search(r"\b(gate|review|ratif\w*|sign[\s-]?off|approv\w*)\b", lowered):
            continue
        if re.search(r"\b(pending|awaiting|not yet|unratified|unresolved|todo)\b", lowered):
            continue
        if re.search(r"\b(ratified|approved|confirmed|accepted|signed[\s-]?off)\b", lowered):
            return True
    return False


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

    # Anchor the freeze check at the contract's sibling lock, not the workspace
    # root: campaign children live at .goals/children/G-00N/current.md and the
    # root pair (if any) says nothing about them.
    hash_status = contract_lock_status(contract)
    result["hash_status"] = hash_status
    hash_matched = hash_status.get("matched")
    # A contract with no sibling current.sha256 is not frozen: it can never be
    # certified achieved, only inconclusive (or contract mutated on mismatch).
    if hash_matched is None and "no current.sha256" in (hash_status.get("reason") or ""):
        result["missing_checks"].append(f"No hash lock ({hash_status.get('lock')}); contract is not frozen — cannot certify achieved")

    contract_sections = parse_sections(contract.read_text(encoding="utf-8"))
    verifier_section = contract_sections.get("Verifier", "")
    terminal_count = len(bullets(contract_sections.get("Terminal State", "")))
    declared_kinds = verifier_kinds(verifier_section)
    has_exec_verifier = bool(extract_verifier_commands(verifier_section))
    declares_nonexec = bool(declared_kinds & {"human", "artifact", "mcp"})
    if terminal_count:
        result["satisfied_checks"].append(f"Contract has {terminal_count} terminal-state clause(s)")
    result["satisfied_checks"].append(f"Contract verifier kinds: {sorted(declared_kinds) or ['unclassified']}")

    # Provenance drift/completeness anchor (informational; never gates the verdict).
    prov = _provenance_check(contract_sections, contract)
    result["provenance"] = prov
    if prov.get("present"):
        if prov.get("artifact_exists") and prov.get("matched"):
            result["satisfied_checks"].append("Provenance artifact present and request hash matches (drift anchor)")
        elif prov.get("artifact_exists") and prov.get("matched") is False:
            result["warnings"].append("Provenance request hash drift: contract pointer hash does not match the artifact's Original Request")
        elif prov.get("artifact") and not prov.get("artifact_exists"):
            result["warnings"].append(f"Provenance pointer references a missing artifact: {prov.get('artifact')}")

    # --- Report sections (presence is necessary but never sufficient) ---
    report_sections_ok = True
    report_decl = ""
    rtext = ""
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
            if "human" in declared_kinds and not _human_gate_resolved(rtext):
                result["result"] = "inconclusive"
                result["missing_checks"].append(
                    "Declared human gate is unresolved: the report must record explicit human ratification "
                    "(e.g. 'human gate: approved by owner') before achieved can be certified")
            else:
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
