#!/usr/bin/env python3
"""Audit a completed campaign chain against its frozen manifest and child contracts.

Recomputes everything from primary artifacts: the aggregate campaign lock, each
ready child's contract + sibling lock, verifier evidence, and per-child reports.
Never reads the derived campaign-status.md view or the informational
campaign-report.md — those are projections, not evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from audit_goal import audit as audit_child
from common import (
    bullets,
    campaign_lock_status,
    campaign_workspace_root,
    child_contract_path,
    child_evidence_dir,
    child_report_path,
    dependency_map,
    infer_campaign_manifest,
    parse_campaign_children,
    parse_sections,
    propagate_dependency_failures,
)

FAILED_VERDICTS = {"not achieved", "contract mutated", "scope violation"}


def _vendored_runtime_warnings(root: Path) -> list[str]:
    """Integrity check over .goals/bin/MANIFEST.sha256 (informational, never the verdict).

    The verdict derives from primary artifacts re-checked here and wrapper-side;
    a mutated vendored runtime only means executor-side status/verifier output
    was untrustworthy along the way.
    """
    manifest = Path(root) / ".goals" / "bin" / "MANIFEST.sha256"
    if not manifest.exists():
        return []
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [f"vendored runtime manifest unreadable: {manifest}"]
    out: list[str] = []
    for line in lines:
        parts = line.split()
        if len(parts) != 2:
            continue
        expected, name = parts
        target = manifest.parent / name
        if not target.exists():
            out.append(f"vendored chain runtime missing: .goals/bin/{name} (re-render the campaign to restore)")
            continue
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            out.append(f"vendored chain runtime mutated: .goals/bin/{name} — executor-side status/verifier "
                       "runs were untrustworthy; wrapper-side re-runs and this audit remain authoritative")
    return out


def _harvest_follow_ups(report: Path) -> list[str]:
    if not report.exists():
        return []
    try:
        sections = parse_sections(report.read_text(encoding="utf-8"))
    except OSError:
        return []
    return [b for b in bullets(sections.get("Follow-Up Candidates", ""))
            if not re.match(r"^(none|n/?a)\b", b.strip(), re.I)]


def audit_campaign(campaign: Path) -> dict:
    result: dict = {
        "result": "not achieved",
        "campaign": str(campaign),
        "children": [],
        "errors": [],
        "warnings": [],
        "follow_up_candidates": [],
    }
    lock = campaign_lock_status(campaign)
    result["lock_status"] = lock
    if not campaign.exists():
        result["errors"].append(f"Missing campaign manifest: {campaign}")
        return result
    if not lock.get("locked"):
        result["result"] = "campaign mutated"
        result["errors"].append("Campaign is not locked (.goals/campaign.sha256 missing); nothing frozen to audit against")
        return result
    if lock.get("matched") is False:
        result["result"] = "campaign mutated"
        result["errors"].append("Campaign aggregate hash mismatch: the manifest or a ready child contract changed after lock")
        return result

    root = campaign_workspace_root(campaign)
    result["warnings"].extend(_vendored_runtime_warnings(root))
    children = parse_campaign_children(campaign.read_text(encoding="utf-8"))
    ready = [c for c in children if c.get("status") == "ready"]
    deps = dependency_map(children)

    verdicts: dict[str, str] = {}
    for child in ready:
        cid = child["id"]
        contract = child_contract_path(campaign, child)
        report = child_report_path(root, cid)
        if contract is None:
            verdicts[cid] = "not achieved"
            result["errors"].append(f"{cid}: no Contract: path in the manifest")
            result["children"].append({"id": cid, "result": "not achieved"})
            continue
        child_audit = audit_child(
            contract,
            report=report if report.exists() else None,
            evidence_dir=child_evidence_dir(root, cid),
        )
        verdicts[cid] = child_audit["result"]
        result["children"].append({
            "id": cid,
            "result": child_audit["result"],
            "contract": str(contract),
            "report": str(report) if report.exists() else None,
            "errors": child_audit.get("errors", []),
            "missing_checks": child_audit.get("missing_checks", []),
        })
        result["follow_up_candidates"].extend(
            f"{cid}: {item}" for item in _harvest_follow_ups(report))

    # Label skipped children by the failing dependency, not as their own failure.
    failed_ids = [cid for cid, v in verdicts.items() if v in FAILED_VERDICTS]
    skipped = propagate_dependency_failures(deps, failed_ids)
    for row in result["children"]:
        cause = skipped.get(row["id"])
        if cause and row["result"] not in {"achieved"} and row["result"] not in FAILED_VERDICTS:
            row["result"] = f"skipped:dependency-failed:{cause}"
            verdicts[row["id"]] = row["result"]

    achieved_n = sum(1 for v in verdicts.values() if v == "achieved")
    total = len(ready)
    if any(v == "contract mutated" for v in verdicts.values()):
        result["result"] = "campaign mutated"
        result["errors"].append("A child contract mutated after lock (and escaped the aggregate gate)")
    elif total and achieved_n == total:
        result["result"] = "campaign achieved"
    elif achieved_n:
        result["result"] = f"partial: {achieved_n}/{total}"
    else:
        result["result"] = "not achieved"
    result["achieved"] = achieved_n
    result["ready_total"] = total
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", nargs="?", default=None,
                        help="Campaign manifest path (default: the single .goals/campaign-*.md)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    campaign = Path(args.campaign) if args.campaign else None
    if campaign is None:
        campaign, reason = infer_campaign_manifest()
        if campaign is None:
            print(reason)
            return 2

    res = audit_campaign(campaign)
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(f"Campaign audit: {res['result']}")
        for row in res["children"]:
            print(f"- {row['id']}: {row['result']}")
        for x in res["errors"]:
            print(f"ERROR: {x}")
        for x in res["warnings"]:
            print(f"WARN: {x}")
        for x in res["follow_up_candidates"]:
            print(f"FOLLOW-UP: {x}")
    if res["result"] == "campaign achieved":
        return 0
    if res["result"] == "campaign mutated":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
