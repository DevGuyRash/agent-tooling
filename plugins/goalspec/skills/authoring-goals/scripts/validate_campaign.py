#!/usr/bin/env python3
"""Validate and optionally lock a GoalSpec campaign manifest for chain execution.

A campaign is launchable as an autonomous chain only when the manifest itself is
coherent AND every ready child is a full, validated, individually locked contract.
The lock written here (.goals/campaign.sha256) is an aggregate hash over the
manifest bytes plus every ready child's contract hash: editing the manifest or
swapping any child contract breaks it.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import (
    CAMPAIGN_REQUIRED_SECTIONS,
    FAILURE_POLICIES,
    bullets,
    campaign_aggregate_hash,
    campaign_chain_budget,
    campaign_failure_policies,
    campaign_lock_path,
    campaign_lock_status,
    campaign_workspace_root,
    child_contract_path,
    contract_lock_status,
    dependency_map,
    dependency_tokens,
    find_cycles,
    parse_campaign_children,
    parse_sections,
)
from validate_goal import validate as validate_contract


def _contract_title_id(contract: Path) -> str | None:
    from graph_goal import contract_metadata
    try:
        gid, _ = contract_metadata(contract)
    except OSError:
        return None
    # contract_metadata falls back to the stem ("current") when the title has
    # no G-<n> id; only a real id participates in coherence checks.
    return gid if re.match(r"^G-\d+$", gid or "") else None


def _graph_mirror_divergence(root: Path, children: list[dict]) -> list[str]:
    """graph.json is an unlocked mirror; divergence from the manifest is a warning."""
    graph_path = root / ".goals" / "graph.json"
    if not graph_path.exists():
        return []
    try:
        from select_goal import parse_graph
        graph_entries = {e["id"]: e for e in parse_graph(graph_path) if e.get("id")}
    except Exception:
        return [f"graph.json mirror is unreadable: {graph_path}"]
    out = []
    for child in children:
        mirror = graph_entries.get(child["id"])
        if not mirror:
            continue
        if mirror.get("status") not in {child.get("status"), "active"}:
            out.append(
                f"graph.json mirror diverges for {child['id']}: status {mirror.get('status')!r} "
                f"vs manifest {child.get('status')!r} (the hash-locked manifest is the truth)")
    return out


def validate_campaign(campaign: Path) -> dict:
    result: dict = {"ok": False, "campaign": str(campaign), "errors": [], "warnings": [], "children": []}
    if not campaign.exists():
        result["errors"].append(f"Missing campaign manifest: {campaign}")
        return result

    text = campaign.read_text(encoding="utf-8")
    sections = parse_sections(text)
    errors = result["errors"]
    warnings = result["warnings"]

    for name in CAMPAIGN_REQUIRED_SECTIONS:
        if name not in sections:
            errors.append(f"Missing required section: ## {name}")
        elif not sections[name].strip():
            errors.append(f"Empty required section: ## {name}")

    # Chain Budget must bind: a concrete numeric ceiling on child attempts.
    budget = sections.get("Chain Budget", "")
    if budget and campaign_chain_budget(budget) is None:
        errors.append("Chain Budget must state a concrete numeric ceiling (max child attempts)")

    policies = campaign_failure_policies(sections.get("Chain Failure Policy", ""))
    if "Chain Failure Policy" in sections:
        if len(policies) != 1:
            errors.append(
                "Chain Failure Policy must declare exactly one of: " + " | ".join(FAILURE_POLICIES))
        else:
            result["failure_policy"] = policies[0]

    children = parse_campaign_children(text)
    result["children"] = [{k: c.get(k) for k in ("id", "title", "status", "depends_on", "contract")}
                          for c in children]
    by_id: dict[str, dict] = {}
    for child in children:
        if child["id"] in by_id:
            errors.append(f"Duplicate child id in Goal Graph: {child['id']}")
        by_id[child["id"]] = child
    ready = [c for c in children if c.get("status") == "ready"]
    if not ready:
        errors.append("Campaign has no ready child; a chain needs at least one ready, locked contract")

    # Every ready child must be a full validated + locked contract.
    for child in ready:
        contract = child_contract_path(campaign, child)
        if contract is None:
            errors.append(f"Ready child {child['id']} has no 'Contract:' path")
            continue
        if not contract.exists():
            errors.append(f"Ready child {child['id']} contract missing: {contract}")
            continue
        v = validate_contract(contract)
        if not v.get("ok"):
            errors.append(f"Ready child {child['id']} contract fails validation: " + "; ".join(v.get("errors", [])))
        ls = contract_lock_status(contract)
        if not ls.get("locked"):
            errors.append(f"Ready child {child['id']} contract is not locked: {ls.get('reason')}")
        elif ls.get("matched") is False:
            errors.append(f"Ready child {child['id']} contract hash mismatch: {contract}")
        # Id coherence: manifest heading id == contract directory name == contract title id.
        if contract.name == "current.md" and contract.parent.name != child["id"]:
            errors.append(
                f"Child id mismatch: heading {child['id']} vs contract directory {contract.parent.name}")
        title_id = _contract_title_id(contract)
        if title_id and title_id != child["id"]:
            errors.append(f"Child id mismatch: heading {child['id']} vs contract title id {title_id}")

    # Dependency sanity over declared manifest edges (the hash-locked truth).
    # Reject tokens graph math drops but the runtime selector would parse:
    # select_goal.is_unblocked reads 'Depends on:' more loosely, so a malformed
    # id (e.g. 'T-001') would pass validation yet block its child forever.
    for child in children:
        bad = [t for t in dependency_tokens(child.get("depends_on", ""))
               if not re.match(r"^G-\d+$", t)]
        if bad:
            errors.append(
                f"Child {child['id']} has malformed dependency token(s): {', '.join(bad)} "
                "(use G-<n> ids or 'none')")
    deps = dependency_map(children)
    ready_ids = {c["id"] for c in ready}
    for gid, dep_ids in deps.items():
        for dep in dep_ids:
            if dep not in by_id:
                errors.append(f"Child {gid} depends on unknown id {dep}")
            elif gid in ready_ids and dep not in ready_ids:
                errors.append(
                    f"Ready child {gid} depends on non-ready child {dep}; the chain could never unblock it")
    for cycle in find_cycles(deps):
        errors.append("Dependency cycle: " + " -> ".join(cycle))

    # Integration gap: several ready children but nothing verifies the combined result.
    if len(ready) >= 2:
        has_integrator = any(set(deps.get(c["id"], [])) >= (ready_ids - {c["id"]}) for c in ready)
        if not has_integrator:
            warnings.append(
                "No integration child depends on all other ready children; nothing verifies the integrated whole")

    coverage = sections.get("Coverage", "")
    if not coverage.strip() or not bullets(coverage):
        warnings.append(
            "No ## Coverage map: list each explicit requirement of the original request -> child id "
            "or 'deferred: <reason>' so uncovered asks are visible before launch")
    if "Provenance" not in sections:
        warnings.append(
            "No ## Provenance pointer; record the verbatim request (record_provenance.py) so the audit "
            "has a drift anchor")

    root = campaign_workspace_root(campaign)
    warnings.extend(_graph_mirror_divergence(root, children))

    result["ok"] = not errors
    if result["ok"]:
        result["aggregate_sha256"] = campaign_aggregate_hash(campaign)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", help="Campaign manifest path (.goals/campaign-<slug>.md)")
    parser.add_argument("--write-hash", action="store_true",
                        help="Write .goals/campaign.sha256 (aggregate hash) when valid")
    parser.add_argument("--check-hash", action="store_true",
                        help="Check .goals/campaign.sha256 against the current aggregate hash")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    campaign = Path(args.campaign)
    result = validate_campaign(campaign)

    if args.check_hash:
        ls = campaign_lock_status(campaign)
        result["lock_status"] = ls
        if not ls.get("locked"):
            result["ok"] = False
            result["errors"].append(f"Missing campaign hash lock: {ls['lock']}")
        elif ls.get("matched") is False:
            result["ok"] = False
            result["errors"].append("Campaign aggregate hash mismatch; manifest or a ready child changed after lock")

    if args.write_hash and result.get("ok"):
        lock = campaign_lock_path(campaign)
        lock.write_text(f"{result['aggregate_sha256']}  {campaign.name}\n", encoding="utf-8")
        result["hash_written"] = str(lock)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Campaign validation: {'OK' if result.get('ok') else 'FAILED'}")
        if result.get("aggregate_sha256"):
            print(f"aggregate sha256: {result['aggregate_sha256']}")
        for err in result.get("errors", []):
            print(f"ERROR: {err}")
        for warn in result.get("warnings", []):
            print(f"WARN: {warn}")
        if result.get("hash_written"):
            print(f"hash written: {result['hash_written']}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
