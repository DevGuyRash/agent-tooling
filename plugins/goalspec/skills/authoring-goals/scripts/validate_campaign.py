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
    campaign_review_anchor,
    campaign_workspace_root,
    child_contract_path,
    contract_lock_status,
    contract_verifier_commands,
    dependency_map,
    dependency_tokens,
    find_cycles,
    parse_campaign_children,
    parse_sections,
    references_only_goalspec_machinery,
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
    # An empty or partial mirror is a dead artifact: tooling that reads the
    # graph sees nothing while the manifest declares a whole dependency tree.
    if children and not graph_entries:
        return [f"graph.json mirror is empty while the manifest declares {len(children)} children; "
                "run graph_goal.py --sync-campaign <manifest> to mirror nodes/edges, or remove the mirror"]
    out = []
    missing_nodes = [c["id"] for c in children if c["id"] not in graph_entries]
    if missing_nodes:
        shown = ", ".join(missing_nodes[:8]) + ("..." if len(missing_nodes) > 8 else "")
        out.append(f"graph.json mirror lacks node(s): {shown} (run graph_goal.py --sync-campaign)")
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

    # Chain Budget must bind: a concrete numeric ceiling on children attempted.
    budget = sections.get("Chain Budget", "")
    if budget and campaign_chain_budget(budget) is None:
        errors.append("Chain Budget must state a concrete numeric ceiling (max children attempted)")

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
        # Id coherence: manifest heading id == contract directory name == contract
        # title id. The workspace root slot (.goals/current.md) is exempt from the
        # directory check: it is the documented human-stepped compile target, and
        # only chain children live under .goals/children/<id>/.
        if (contract.name == "current.md" and contract.parent.name != child["id"]
                and contract.parent.name != ".goals"):
            errors.append(
                f"Child id mismatch: heading {child['id']} vs contract directory {contract.parent.name}")
        title_id = _contract_title_id(contract)
        if title_id and title_id != child["id"]:
            errors.append(f"Child id mismatch: heading {child['id']} vs contract title id {title_id}")
        # Chain pause points: a child whose contract declares no executable
        # verifier command can only advance on an audited gate outcome.
        if contract_verifier_commands(contract) == []:
            result.setdefault("attestation_only", []).append(child["id"])
            warnings.append(
                f"Ready child {child['id']} is attestation-only: its ## Verifier has no executable "
                "command, so an autonomous chain pauses there until its report records the gate "
                "outcome (fine human-stepped; add an executable oracle if you want the chain to "
                "advance unattended)")

    # A child entry must BE a goal sketch, not deferred homework: a milestone
    # name plus "Missing decision" restates the source roadmap and adds no
    # execution information. Ready and conditional children must sketch their
    # Terminal state and Verifier; blocked children warn (their gate may hide
    # the work's shape); not-launchable children are an explicit parking lane.
    for child in children:
        status = child.get("status", "")
        if status == "not-launchable":
            continue
        missing = [label for key, label in (("terminal_state", "Terminal state"), ("verifier", "Verifier"))
                   if not child.get(key, "").strip()]
        if not missing:
            continue
        msg = (f"Child {child['id']} ({status}) is a stub: missing {' and '.join(missing)} — "
               "sketch what done means and how it is checked, or the decomposition adds "
               "nothing over its source documents")
        (warnings if status == "blocked" else errors).append(msg)

    # Materialize everything, lock the horizon: the tail (conditional/blocked
    # children) carries full UNLOCKED contracts — depth is always maximal, only
    # locking is horizon-scoped. A manifest sketch is a skeleton, not an end state.
    for child in children:
        if child.get("status") not in {"conditional", "blocked"}:
            continue
        contract = child_contract_path(campaign, child)
        if contract is None:
            warnings.append(
                f"Child {child['id']} ({child.get('status')}) has no 'Contract:' path — materialize the "
                "tail as a full unlocked contract (lock it at selection); a manifest sketch is not an "
                "end state")
        elif not contract.exists():
            warnings.append(
                f"Child {child['id']} ({child.get('status')}) names a contract that does not exist yet: "
                f"{contract} — write the full unlocked contract now; lock it at selection")
        else:
            v_tail = validate_contract(contract)
            for err in v_tail.get("errors", []):
                warnings.append(f"Child {child['id']} tail contract will need this fixed before promotion: {err}")

    # Meta-goal smell: GoalSpec machinery as the deliverable. One meta child is
    # a warning; a campaign whose ENTIRE ready set is meta has no launchable
    # value and must either materialize real work or name the blocking decision.
    meta_ids = {c["id"] for c in children
                if references_only_goalspec_machinery(
                    " ".join([c.get("title", ""), c.get("terminal_state", ""), c.get("verifier", "")]))}
    for cid in sorted(meta_ids):
        warnings.append(
            f"Child {cid} is a meta-goal: its terminal state and verifier reference only GoalSpec "
            "machinery. Verify the substrate inside a value-bearing child; if this is a false "
            "positive, name a concrete workspace artifact the child delivers")
    if ready and all(c["id"] in meta_ids for c in ready):
        if re.search(r"(?mi)^\s*-?\s*Owner decision required:\s*\S", text):
            warnings.append(
                "Every ready child is a meta-goal; the declared 'Owner decision required:' line is "
                "the only path to value-bearing work — resolve it before launching anything")
        else:
            errors.append(
                "Every ready child is a meta-goal (GoalSpec machinery only). Materialize at least one "
                "value-bearing ready child, or declare the blocker on an 'Owner decision required:' line")

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
    if "Decomposition Review" not in sections:
        warnings.append(
            "No ## Decomposition Review section: after the manifest validates, an independent "
            "adversarial review (launchability rubric check 10) must record its verdict and what it "
            "changed before handoff")

    # Review anchor: binds the recorded review to the manifest content it
    # reviewed. Always emitted so the honest flow is copy-paste cheap; all
    # review checks stay warnings (an error here would deadlock the
    # apply-findings loop and break legacy campaigns).
    anchor = campaign_review_anchor(text)
    result["review_anchor"] = anchor
    review = sections.get("Decomposition Review", "")
    if review.strip():
        declared = re.findall(r"(?mi)^\s*-?\s*Anchor:\s*`?([0-9a-fA-F]{64})`?\s*$", review)
        if not declared:
            warnings.append(
                "## Decomposition Review records no 'Anchor: <sha256>' line; copy the review anchor "
                "from this validation output so any post-review manifest edit reads as staleness")
        elif anchor not in (d.lower() for d in declared):
            warnings.append(
                f"Decomposition Review is stale: the manifest changed after this review (recorded "
                f"anchor {declared[-1][:12]}..., current {anchor[:12]}...). Re-review or confirm the "
                "verdicts still hold, then update the Anchor line")
        missing_verdicts = [c["id"] for c in children
                            if not re.search(rf"\b{re.escape(c['id'])}\b", review)]
        if missing_verdicts:
            warnings.append(
                "Decomposition Review has no per-child verdict for: " + ", ".join(missing_verdicts)
                + " — record one verdict per child (confirmed | weak | theater)")

    root = campaign_workspace_root(campaign)
    # Reviewer availability is a capability fact (same class as the mirror
    # check): when the adversary is absent, the review can only have been a
    # self-review — say so where the author is already looking.
    if not (root / ".codex" / "agents" / "decomposition-reviewer.toml").exists():
        warnings.append(
            "decomposition-reviewer agent template is not installed in this project "
            "(.codex/agents/decomposition-reviewer.toml); install it with goalspec.py init "
            "(installed by default), spawn the plugin-shipped goalspec:decomposition-reviewer "
            "on Claude Code, or self-review against rubric check 10 — and note which one the "
            "recorded review reflects")
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
        if result.get("review_anchor"):
            print(f"review anchor: {result['review_anchor']}")
        for err in result.get("errors", []):
            print(f"ERROR: {err}")
        for warn in result.get("warnings", []):
            print(f"WARN: {warn}")
        if result.get("hash_written"):
            print(f"hash written: {result['hash_written']}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
