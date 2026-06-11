#!/usr/bin/env python3
"""Derive campaign chain status from per-child verifier evidence.

This is a projection, never an authority: the frozen manifest is the plan,
per-child verifier evidence is the truth, and the checkmarks written here are a
derived view. It is also the runtime brainstem of an autonomous chain — the
executor re-runs it after every child and follows next_child — so it must never
crash on malformed evidence: anything unreadable degrades to 'pending' with a
warning, never to achieved and never to a traceback.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from common import (
    campaign_chain_budget,
    campaign_failure_policies,
    campaign_workspace_root,
    child_contract_path,
    child_evidence_dir,
    child_report_path,
    dependency_map,
    infer_campaign_manifest,
    parse_campaign_children,
    parse_sections,
    propagate_dependency_failures,
    sha256_file,
)
from select_goal import select

ACHIEVED = "achieved-pending-audit"
FAILED = "failed"
PENDING = "pending"

STATUS_MARK = {ACHIEVED: "✓", FAILED: "✗", PENDING: "–"}


def _failure_policy(text: str) -> str:
    # Validation requires exactly one declared policy; anything else (legacy or
    # malformed manifest) falls back to the safer halt-on-failure.
    policies = campaign_failure_policies(parse_sections(text).get("Chain Failure Policy", ""))
    return policies[0] if len(policies) == 1 else "halt-on-failure"


def _read_result(evidence: Path, warnings: list[str], child_id: str) -> dict | None:
    result_file = evidence / "verifiers" / "result.json"
    if not result_file.exists():
        return None
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        warnings.append(f"{child_id}: verifier result unreadable ({exc.__class__.__name__}); treating as pending")
        return None
    if not isinstance(data, dict):
        warnings.append(f"{child_id}: verifier result is not an object; treating as pending")
        return None
    return data


def derive_status(campaign: Path) -> dict:
    out: dict = {"campaign": str(campaign), "children": [], "warnings": []}
    try:
        text = campaign.read_text(encoding="utf-8")
    except OSError as exc:
        out["error"] = f"Cannot read campaign manifest: {exc}"
        return out
    root = campaign_workspace_root(campaign)
    children = parse_campaign_children(text)
    deps = dependency_map(children)
    budget = campaign_chain_budget(parse_sections(text).get("Chain Budget", ""))
    policy = _failure_policy(text)
    warnings = out["warnings"]

    statuses: dict[str, str] = {}
    attempted = 0
    verifier_failures_total = 0
    rows = []
    for child in children:
        cid = child["id"]
        row = {"id": cid, "title": child.get("title"), "manifest_status": child.get("status"),
               "depends_on": child.get("depends_on")}
        if child.get("status") != "ready":
            row["status"] = f"not-in-chain:{child.get('status')}"
            rows.append(row)
            continue
        evidence = child_evidence_dir(root, cid)
        if evidence.exists() and any(evidence.rglob("*")):
            attempted += 1
            row["attempted"] = True
        result = _read_result(evidence, warnings, cid)
        contract = child_contract_path(campaign, child)
        status = PENDING
        if result is not None:
            verifier_failures_total += sum(1 for v in result.get("verifiers", []) if not v.get("passed"))
            if result.get("overall_passed") is True:
                stamped = result.get("contract_sha256")
                if not stamped:
                    warnings.append(f"{cid}: verifier result has no contract_sha256; cannot trust it — pending")
                elif not (contract and contract.exists()):
                    warnings.append(f"{cid}: contract missing; evidence cannot be matched — pending")
                elif stamped != sha256_file(contract):
                    warnings.append(f"{cid}: verifier result is for a different contract version (stale) — pending")
                elif not child_report_path(root, cid).exists():
                    warnings.append(f"{cid}: verifiers passed but report .goals/reports/{cid}-report.md is missing — pending")
                else:
                    status = ACHIEVED
            else:
                status = FAILED
        row["status"] = status
        statuses[cid] = status
        rows.append(row)

    failed_ids = [cid for cid, s in statuses.items() if s == FAILED]
    skipped = propagate_dependency_failures(deps, failed_ids)
    for row in rows:
        cause = skipped.get(row["id"])
        if cause and statuses.get(row["id"]) == PENDING:
            row["status"] = f"skipped:dependency-failed:{cause}"
            statuses[row["id"]] = row["status"]

    # A2: select() only unblocks on 'completed', and graph.json is frozen mid-run.
    # Overlay evidence-derived completion onto the manifest entries and let the
    # existing selector remain the brain.
    entries = []
    for child in children:
        entry = dict(child)
        s = statuses.get(child["id"])
        if s == ACHIEVED:
            entry["status"] = "completed"
        elif s == FAILED or (s or "").startswith("skipped:"):
            entry["status"] = "blocked"
        entries.append(entry)
    selection = select(entries)
    next_child = (selection.get("selected") or {}).get("id")

    achieved_n = sum(1 for s in statuses.values() if s == ACHIEVED)
    ready_n = len(statuses)
    chain_should_stop, stop_reason = False, None
    if budget is not None and attempted >= budget and achieved_n < ready_n:
        chain_should_stop, stop_reason = True, f"chain budget exhausted ({attempted}/{budget} children attempted)"
    elif policy == "halt-on-failure" and failed_ids:
        chain_should_stop, stop_reason = True, f"halt-on-failure: {', '.join(sorted(failed_ids))} failed"
    elif not next_child:
        chain_should_stop = True
        stop_reason = ("all ready children achieved (pending audit)" if achieved_n == ready_n
                       else "no ready unblocked child remains")
    if chain_should_stop:
        # Never hand the executor a stop signal AND a next child: a literal
        # chain loop keys off next_child, so the two must not contradict.
        next_child = None

    out.update({
        "children": rows,
        "ready_total": ready_n,
        "achieved_pending_audit": achieved_n,
        "failed": len(failed_ids),
        "skipped": len(skipped),
        "attempted_count": attempted,
        "verifier_failures_total": verifier_failures_total,
        "chain_budget": budget,
        "failure_policy": policy,
        "next_child": next_child,
        "chain_should_stop": chain_should_stop,
        "stop_reason": stop_reason,
    })
    return out


def render_view(status: dict) -> str:
    lines = [
        "# Campaign Status (derived view — never authoritative; evidence is the truth)",
        "",
        f"- Campaign: {status.get('campaign')}",
        f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"- Progress: {status.get('achieved_pending_audit', 0)}/{status.get('ready_total', 0)} "
        f"achieved-pending-audit; attempts {status.get('attempted_count', 0)}"
        + (f"/{status['chain_budget']}" if status.get("chain_budget") is not None else ""),
        f"- Next child: {status.get('next_child') or 'none'}",
        f"- Chain should stop: {status.get('chain_should_stop')}"
        + (f" ({status.get('stop_reason')})" if status.get("stop_reason") else ""),
        "",
    ]
    for row in status.get("children", []):
        s = row.get("status", "")
        mark = STATUS_MARK.get(s, "✗" if s.startswith("skipped:") else " ")
        lines.append(f"- {mark} {row['id']}: {s}")
    for warn in status.get("warnings", []):
        lines.append(f"- WARN: {warn}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", nargs="?", default=None,
                        help="Campaign manifest path (default: the single .goals/campaign-*.md)")
    parser.add_argument("--no-write", action="store_true",
                        help="Do not write the .goals/reports/campaign-status.md view")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    campaign = Path(args.campaign) if args.campaign else None
    if campaign is None:
        campaign, reason = infer_campaign_manifest()
        if campaign is None:
            print(reason)
            return 2

    status = derive_status(campaign)
    if status.get("error"):
        print(status["error"])
        return 2

    view = render_view(status)
    if not args.no_write:
        view_path = campaign_workspace_root(campaign) / ".goals" / "reports" / "campaign-status.md"
        view_path.parent.mkdir(parents=True, exist_ok=True)
        view_path.write_text(view, encoding="utf-8")
        status["view"] = str(view_path)
    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print(view, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
