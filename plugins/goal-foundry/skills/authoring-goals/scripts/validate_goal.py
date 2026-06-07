#!/usr/bin/env python3
"""Validate and optionally lock a Goal Foundry current.md contract."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import REQUIRED_SECTIONS, OPEN_ENDED_PHRASES, bullets, nonempty_without_placeholders, parse_sections, sha256_file


def validate(path: Path) -> dict:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    sections = parse_sections(text)
    errors = []
    warnings = []

    if not path.exists():
        return {"ok": False, "errors": [f"Missing contract: {path}"], "warnings": []}

    for name in REQUIRED_SECTIONS:
        if name not in sections:
            errors.append(f"Missing required section: ## {name}")
        elif not sections[name].strip():
            errors.append(f"Empty required section: ## {name}")

    # Critical sections should not contain bracket placeholders.
    for name in ["Objective", "Intent", "Completeness Dimensions", "Terminal State", "Verifier", "Scope", "Budget", "Give-Up Conditions", "Evidence Required"]:
        if name in sections and "[" in sections[name] and "]" in sections[name]:
            errors.append(f"Section ## {name} still contains bracket placeholders")

    term = sections.get("Terminal State", "")
    verifier = sections.get("Verifier", "")
    budget = sections.get("Budget", "")
    scope = sections.get("Scope", "")
    giveup = sections.get("Give-Up Conditions", "")
    completeness = sections.get("Completeness Dimensions", "")

    if len(bullets(term)) < 2:
        errors.append("Terminal State should contain at least two checkable clauses")
    if len(bullets(verifier)) < 1:
        errors.append("Verifier should contain at least one command, artifact, metric, checklist, or gate")
    if not re.search(r"\b(max|maximum|limit|ceiling|budget|stop when|iterations?|files?|dependencies?|time|cost)\b", budget, re.I):
        errors.append("Budget section must include a concrete ceiling and stop rule")
    if not re.search(r"In scope:\s*\n", scope, re.I) or not re.search(r"Out of scope:\s*\n", scope, re.I):
        errors.append("Scope section must include both 'In scope:' and 'Out of scope:'")
    if len(bullets(giveup)) < 2:
        errors.append("Give-Up Conditions should name at least two concrete stop states")
    if len(bullets(completeness)) < 2:
        errors.append("Completeness Dimensions should list at least two dimensions")

    lowered = term.lower()
    for phrase in OPEN_ENDED_PHRASES:
        if phrase in lowered:
            warnings.append(f"Terminal State contains open-ended phrase: {phrase!r}; ensure it is frozen by date/version/checklist/threshold")

    if ".goals/GOALS.md" in text and "Do not" not in text:
        warnings.append("Contract mentions GOALS.md; ensure it is a registry, not execution scope")

    # Evidence section needs commands/results/artifacts.
    evidence = sections.get("Evidence Required", "")
    for need in ["Files changed", "Commands run", "Budget used", "Follow-up"]:
        if need.lower() not in evidence.lower():
            warnings.append(f"Evidence Required may be missing: {need}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "sha256": sha256_file(path),
        "sections_present": sorted(sections.keys()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=".goals/current.md", help="Goal contract path")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--write-hash", action="store_true", help="Write .goals/current.sha256 next to current.md when valid")
    parser.add_argument("--check-hash", action="store_true", help="Check .goals/current.sha256 against current.md")
    args = parser.parse_args()

    path = Path(args.path)
    result = validate(path)

    if args.check_hash:
        lock = path.with_name("current.sha256")
        if not lock.exists():
            result["ok"] = False
            result.setdefault("errors", []).append(f"Missing hash lock: {lock}")
        else:
            expected = lock.read_text(encoding="utf-8").strip().split()[0]
            if expected != result.get("sha256"):
                result["ok"] = False
                result.setdefault("errors", []).append("Contract hash mismatch; current.md changed after lock")
            result["expected_hash"] = expected

    if args.write_hash and result.get("ok"):
        lock = path.with_name("current.sha256")
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(f"{result['sha256']}  {path.name}\n", encoding="utf-8")
        result["hash_written"] = str(lock)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Goal validation: {'OK' if result.get('ok') else 'FAILED'}")
        if result.get("sha256"):
            print(f"sha256: {result['sha256']}")
        for err in result.get("errors", []):
            print(f"ERROR: {err}")
        for warn in result.get("warnings", []):
            print(f"WARN: {warn}")
        if result.get("hash_written"):
            print(f"hash written: {result['hash_written']}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
