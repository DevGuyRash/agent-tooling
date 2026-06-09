#!/usr/bin/env python3
"""Render .goals/current.md into a paste-ready Codex /goal objective."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import bullets, parse_sections, sha256_file


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


def render_with_meta(path: Path, max_chars: int = 4000) -> dict:
    text = path.read_text(encoding="utf-8")
    sections = parse_sections(text)
    h = sha256_file(path)
    terminal = compact_list(bullets(sections.get("Terminal State", "")), max_items=6, max_len=900)
    verifier = compact_list(bullets(sections.get("Verifier", "")), max_items=5, max_len=700)
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

    rendered = f"""/goal Complete the frozen goal contract in .goals/current.md. First read that file and treat it as the source of truth. Contract sha256 at render time: {h}. Completeness dimensions: {completeness}. Terminal state summary: {terminal}. Verifier summary: {verifier}. Respect out-of-scope boundaries, including: {out_text}. Budget summary: {budget}. Stop and report blocked/incomplete if any give-up condition occurs, including: {giveup}. Do not treat .goals/GOALS.md as execution scope. Do not modify .goals/current.md or .goals/current.sha256 during execution. Write only .goals/evidence/ and .goals/reports/ inside .goals/. Final report must include: {evidence}. Record adjacent work as follow-up candidates, not implicit scope."""
    rendered = " ".join(rendered.split())
    full_chars = len(rendered)
    truncated = full_chars > max_chars
    if truncated:
        rendered = rendered[: max_chars - 160].rstrip() + " ... See .goals/current.md for full non-droppable contract clauses; if this projection conflicts with current.md, current.md wins."
    return {"rendered": rendered, "truncated": truncated, "chars": len(rendered), "full_chars": full_chars}


def render(path: Path, max_chars: int = 4000) -> str:
    return render_with_meta(path, max_chars)["rendered"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=".goals/current.md")
    parser.add_argument("--write", help="Write rendered objective to this path")
    parser.add_argument("--max-chars", type=int, default=4000)
    parser.add_argument("--json", action="store_true", help="Emit JSON with rendered text and truncation metadata")
    args = parser.parse_args()
    meta = render_with_meta(Path(args.path), args.max_chars)
    output = meta["rendered"]
    if args.write:
        out = Path(args.write)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output + "\n", encoding="utf-8")
    if meta["truncated"]:
        import sys
        print(
            f"WARNING: rendered objective truncated to {args.max_chars} chars "
            f"({meta['full_chars']} projected); full contract remains in .goals/current.md.",
            file=sys.stderr,
        )
    if args.json:
        print(json.dumps(meta, indent=2, ensure_ascii=False))
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
