#!/usr/bin/env python3
"""Render .goals/current.md into a paste-ready Codex /goal objective."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import (
    REPORT_FIELDS,
    bullets,
    campaign_lock_status,
    child_contract_path,
    contract_lock_status,
    extract_verifier_commands,
    parse_campaign_children,
    parse_sections,
    sha256_file,
)


class RenderRefused(Exception):
    """Raised when rendering an unlocked or hash-mismatched contract without override."""

    def __init__(self, reason: str, status: dict):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def compact_list(items, max_items=5, max_len=600):
    if not items:
        return "not specified"
    chosen = items[:max_items]
    text = "; ".join(chosen)
    if len(items) > max_items:
        text += f"; plus {len(items)-max_items} more clause(s) in .goals/current.md"
    if len(text) > max_len:
        text = text[: max_len - 20].rstrip() + "..."
    return text


def goals_relative(path: Path) -> str:
    """Spell a path from its last '.goals' component onward.

    The launch line is pasted into an executor whose cwd is the workspace root,
    so '.goals/...' is the spelling that resolves there even when this process
    was handed an absolute path. Paths outside any .goals/ pass through as-is.
    """
    parts = Path(path).parts
    if ".goals" in parts:
        idx = len(parts) - 1 - tuple(reversed(parts)).index(".goals")
        return "/".join(parts[idx:])
    return Path(path).as_posix()


def pointer_launch_line(pointer_ref: str, pointer_sha256: str, mission_anchor: str) -> str:
    """The limit-independent launch line shared by both render modes (target <= 400 chars).

    Dual anchors: the mission hash freezes the contract/campaign and the file
    hash freezes the rendered pointer bytes, so a post-render rewrite of the
    pointer file (e.g. a markdown formatter) fails loud at launch instead of
    silently launching a drifted payload.
    """
    return (
        f"/goal Read {pointer_ref} first and execute that frozen mission; "
        "the file is the source of truth over this line. "
        f"File sha256 {pointer_sha256}. "
        f"Mission: {mission_anchor}. "
        "If either hash does not match, stop and report contract mutated."
    )


def render_with_meta(path: Path, max_chars: int = 4000, allow_unlocked: bool = False) -> dict:
    text = path.read_text(encoding="utf-8")
    # Freeze gate: refuse to project an unlocked or mismatched contract into a
    # /goal by default. Hooks are defense-in-depth; this refusal plus the audit
    # hash are the real backstop that keeps execution bound to a frozen contract.
    status = contract_lock_status(path)
    if not allow_unlocked and (not status.get("locked") or status.get("matched") is False):
        raise RenderRefused(
            f"GoalSpec refuses to render an unlocked or mismatched contract ({status.get('reason')}). "
            f"Lock it first: validate_goal.py {path} --write-hash. "
            "Pass --allow-unlocked to override (e.g. for a preview before locking).",
            status,
        )
    sections = parse_sections(text)
    h = status.get("current_hash") or sha256_file(path)
    terminal = compact_list(bullets(sections.get("Terminal State", "")), max_items=6, max_len=900)
    # Fence-style Verifier sections have no bullets (fleet run v11-b projected
    # "Verifier summary: not specified" while four verifiers ran green), so fall
    # back to the extracted commands; this field never projects "not specified".
    verifier_section = sections.get("Verifier", "")
    verifier_items = bullets(verifier_section) or extract_verifier_commands(verifier_section)
    if verifier_items:
        verifier = compact_list(verifier_items, max_items=5, max_len=700)
    else:
        verifier = "see the Verifier section in .goals/current.md"
    out_scope = sections.get("Scope", "")
    # Extract out-of-scope bullets after marker.
    out_items = []
    in_out = out_scope.split("Out of scope:", 1)
    if len(in_out) == 2:
        out_items = bullets(in_out[1])
    out_text = compact_list(out_items, max_items=6, max_len=700)
    budget = compact_list(bullets(sections.get("Budget", "")), max_items=5, max_len=500)
    giveup = compact_list(bullets(sections.get("Give-Up Conditions", "")), max_items=6, max_len=700)
    evidence = compact_list(bullets(sections.get("Evidence Required", "")), max_items=6, max_len=600)
    completeness = compact_list(bullets(sections.get("Completeness Dimensions", "")), max_items=6, max_len=500)
    # Name the exact section headings the audit oracle checks (common.REPORT_FIELDS):
    # executors otherwise improvise headings and honest reports audit as incomplete.
    report_headings = "; ".join(f"## {field}" for field in REPORT_FIELDS)

    rendered = f"""/goal Complete the frozen goal contract in .goals/current.md. First read that file and treat it as the source of truth. Contract sha256 at render time: {h}. Completeness dimensions: {completeness}. Terminal state summary: {terminal}. Verifier summary: {verifier}. Respect out-of-scope boundaries, including: {out_text}. Budget summary: {budget}. Stop and report blocked/incomplete if any give-up condition occurs, including: {giveup}. Do not treat .goals/GOALS.md or .goals/provenance/ as execution scope; provenance preserves the original request for reference only and must not be executed or re-derived. Do not modify .goals/current.md or .goals/current.sha256 during execution. Write only .goals/evidence/ and .goals/reports/ inside .goals/. Final report must use these exact section headings: {report_headings} — and must include: {evidence}. Record adjacent work as follow-up candidates, not implicit scope."""
    rendered = " ".join(rendered.split())
    full_chars = len(rendered)
    truncated = full_chars > max_chars
    if truncated:
        rendered = rendered[: max_chars - 160].rstrip() + " ... See .goals/current.md for full non-droppable contract clauses; if this projection conflicts with current.md, current.md wins."
    return {"rendered": rendered, "truncated": truncated, "chars": len(rendered),
            "full_chars": full_chars, "lock_status": status}


def render(path: Path, max_chars: int = 4000, allow_unlocked: bool = False) -> str:
    return render_with_meta(path, max_chars, allow_unlocked)["rendered"]


def render_campaign_with_meta(path: Path, max_chars: int = 4000) -> dict:
    """Render a locked campaign into ONE chain /goal.

    There is no --allow-unlocked for campaigns: an unattended chain with no
    frozen mission is exactly the runaway this plugin exists to prevent. The
    gate requires the aggregate campaign lock AND every ready child's own
    sibling lock to match.
    """
    status = campaign_lock_status(path)
    if not status.get("locked") or status.get("matched") is False:
        raise RenderRefused(
            f"GoalSpec refuses to render an unlocked or mismatched campaign ({status.get('reason')}). "
            f"Lock it first: validate_campaign.py {path} --write-hash. "
            "There is no unlocked override for campaigns.",
            status,
        )
    children = parse_campaign_children(path.read_text(encoding="utf-8"))
    ready = [c for c in children if c.get("status") == "ready"]
    if not ready:
        raise RenderRefused("Campaign has no ready child; nothing to chain.", status)
    for child in ready:
        contract = child_contract_path(path, child)
        cls = contract_lock_status(contract) if contract else {"locked": False, "reason": "no Contract: path"}
        if not cls.get("locked") or cls.get("matched") is False:
            raise RenderRefused(
                f"GoalSpec refuses to render the campaign: child {child['id']} is not locked/matched "
                f"({cls.get('reason')}). Lock it: validate_goal.py {contract} --write-hash.",
                status,
            )

    ids = ", ".join(c["id"] for c in ready)
    scripts_dir = Path(__file__).resolve().parent
    report_headings = "; ".join(f"## {field}" for field in REPORT_FIELDS)
    rendered = f"""/goal Execute the frozen campaign chain in {path}. The campaign manifest and every child contract are frozen; campaign aggregate sha256 at render time: {status['current_hash']}. Ready children (each a full contract at .goals/children/<id>/current.md): {ids}. Chain procedure, per child: (1) run `python3 {scripts_dir}/campaign_status.py {path} --json` and take its next_child — skip children already marked achieved when resuming; (2) re-read that child's .goals/children/<id>/current.md and treat it as the source of truth, honoring its own budget, scope, and give-up conditions; (3) do the work; (4) run `python3 {scripts_dir}/run_verifiers.py .goals/children/<id>/current.md --run --evidence-dir .goals/evidence/children/<id>/verifiers`; (5) write the child report at .goals/reports/<id>-report.md using these exact section headings: {report_headings}; (6) refresh campaign_status.py and continue with its next_child. Stop the chain when campaign_status.py reports chain_should_stop (chain budget exhausted, failure policy triggered, or no ready unblocked child remains). If campaign_status.py itself fails or its output is unreadable, stop immediately and report blocked — do not improvise the chain order. Never modify the campaign manifest, any child contract, any .sha256 lock, .goals/GOALS.md, or .goals/graph.json; write only under .goals/evidence/ and .goals/reports/. Record adjacent discoveries in each child report's Follow-Up Candidates, never as new scope. When the chain stops, write a final informational summary at .goals/reports/campaign-report.md (the audit reads per-child evidence, not this summary)."""
    rendered = " ".join(rendered.split())
    full_chars = len(rendered)
    truncated = full_chars > max_chars
    if truncated:
        rendered = rendered[: max_chars - 160].rstrip() + f" ... See {path} and the child contracts for full non-droppable clauses; if this projection conflicts with them, they win."
    return {"rendered": rendered, "truncated": truncated, "chars": len(rendered),
            "full_chars": full_chars, "lock_status": status,
            "ready_children": [c["id"] for c in ready]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=None)
    parser.add_argument("--campaign", help="Render a locked campaign manifest as ONE chain /goal (mutually exclusive with a contract path)")
    parser.add_argument("--write", help="Write rendered objective to this path")
    parser.add_argument("--max-chars", type=int, default=None,
                        help="Character budget for the rendered objective (default 4000; "
                             "unlimited in --pointer mode unless set, since the pointer file "
                             "is read by the executor, never pasted into a prompt).")
    parser.add_argument("--allow-unlocked", action="store_true",
                        help="Render even if the contract is unlocked or hash-mismatched (preview only; not for launch; single goals only).")
    parser.add_argument("--pointer", action="store_true",
                        help="Write the full render to a file (default .goals/rendered-goal.md / "
                             ".goals/rendered-campaign.md) and print a short dual-hash launch line "
                             "for prompt-length-limited platforms (locked missions only).")
    parser.add_argument("--json", action="store_true", help="Emit JSON with rendered text and truncation metadata")
    args = parser.parse_args()
    if args.campaign and args.path:
        print("RENDER REFUSED: pass either a contract path or --campaign, not both.", file=sys.stderr)
        return 2
    if args.campaign and args.allow_unlocked:
        print("RENDER REFUSED: --allow-unlocked does not apply to campaigns; lock everything first.", file=sys.stderr)
        return 2
    if args.pointer and args.allow_unlocked:
        print("RENDER REFUSED: --pointer never renders an unlocked or mismatched mission; "
              "lock it first (validate_goal.py --write-hash). --allow-unlocked is preview-only.",
              file=sys.stderr)
        return 2
    max_chars = args.max_chars if args.max_chars is not None else (10**9 if args.pointer else 4000)
    try:
        if args.campaign:
            meta = render_campaign_with_meta(Path(args.campaign), max_chars)
        else:
            meta = render_with_meta(Path(args.path or ".goals/current.md"), max_chars,
                                    allow_unlocked=args.allow_unlocked)
    except RenderRefused as exc:
        print(f"RENDER REFUSED: {exc.reason}", file=sys.stderr)
        if args.json:
            print(json.dumps({"refused": True, "reason": exc.reason, "lock_status": exc.status},
                             indent=2, ensure_ascii=False))
        return 2
    output = meta["rendered"]
    if args.pointer:
        mission_path = Path(args.campaign) if args.campaign else Path(args.path or ".goals/current.md")
        default_name = "rendered-campaign.md" if args.campaign else "rendered-goal.md"
        pointer_file = Path(args.write) if args.write else mission_path.with_name(default_name)
        pointer_file.parent.mkdir(parents=True, exist_ok=True)
        pointer_file.write_text(output + "\n", encoding="utf-8")
        mission_hash = meta["lock_status"]["current_hash"]
        if args.campaign:
            mission_anchor = f"campaign {goals_relative(mission_path)} aggregate sha256 {mission_hash}"
        else:
            # Anchor on the literal '.goals/current.md' (like the rendered text
            # itself does): the launch line must keep the substring that
            # prompt_guard's /goal launch checks engage on.
            mission_anchor = f"contract .goals/current.md sha256 {mission_hash}"
        meta["pointer_file"] = str(pointer_file)
        meta["pointer_file_sha256"] = sha256_file(pointer_file)
        meta["mission_sha256"] = mission_hash
        meta["pointer_line"] = pointer_launch_line(
            goals_relative(pointer_file), meta["pointer_file_sha256"], mission_anchor)
    elif args.write:
        out = Path(args.write)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output + "\n", encoding="utf-8")
    if meta["truncated"]:
        print(
            f"WARNING: rendered objective truncated to {max_chars} chars "
            f"({meta['full_chars']} projected); full contract remains in .goals/current.md.",
            file=sys.stderr,
        )
    if args.json:
        print(json.dumps(meta, indent=2, ensure_ascii=False))
    else:
        print(output)
        if args.pointer:
            print()
            print(f"--- pointer launch line (paste only the line below; "
                  f"the full mission stays in {meta['pointer_file']}) ---")
            print(meta["pointer_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
