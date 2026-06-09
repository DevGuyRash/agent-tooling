#!/usr/bin/env python3
"""Validate and optionally lock a GoalSpec current.md contract."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import REQUIRED_SECTIONS, OPEN_ENDED_PHRASES, bullets, parse_sections, sha256_file, verifier_kinds

# Concrete repair hints keyed by a substring of the error message they address.
REPAIR_HINTS = {
    "Missing contract": "Author .goals/current.md (or run init_project.py to scaffold it) before validating.",
    "Missing required section": "Add the missing '## <name>' section with concrete content.",
    "Empty required section": "Fill the empty required section with concrete content.",
    "bracket placeholders": "Replace [bracketed placeholders] with concrete content.",
    "Terminal State": "Add 2+ checkable bullets to ## Terminal State, each a proposition the world either satisfies or not (e.g. '- `pytest -q` exits 0').",
    "Verifier": "Add at least one concrete verifier under ## Verifier: a command, artifact path, metric threshold, checklist, or human gate.",
    "Budget": "State a hard ceiling under ## Budget (e.g. 'Max 8 changed files' or 'Stop after 5 iterations').",
    "Scope section": "Under ## Scope add two labelled lists, 'In scope:' and 'Out of scope:', each with bullets.",
    "Give-Up Conditions": "Name 2+ concrete stop states under ## Give-Up Conditions (e.g. 'Stop if the migration cannot run in <30 min').",
    "Completeness Dimensions": "List 2+ value dimensions under ## Completeness Dimensions the work must cover (e.g. correctness, performance, security).",
}


def suggest_repairs(errors: list) -> list:
    repairs = []
    for err in errors:
        for key, hint in REPAIR_HINTS.items():
            if key in err and hint not in repairs:
                repairs.append(hint)
    return repairs


def validate(path: Path) -> dict:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    sections = parse_sections(text)
    errors = []
    warnings = []

    if not path.exists():
        errs = [f"Missing contract: {path}"]
        return {"ok": False, "errors": errs, "warnings": [], "repairs": suggest_repairs(errs)}

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
    elif not verifier_kinds(verifier):
        # The verifier exists but audit cannot key off it: no runnable command and
        # no declared human/artifact/MCP gate, so audit stays inconclusive forever.
        warnings.append("Verifier has no executable command and declares no human/artifact/MCP gate; audit cannot auto-confirm pass. Add a runnable command (e.g. `pytest -q`) or name the human/artifact/MCP oracle explicitly")
    budget_has_keyword = re.search(r"\b(max|maximum|limit|ceiling|budget|stop when|iterations?|files?|dependencies?|time|cost)\b", budget, re.I)
    budget_has_number = re.search(r"\d", budget)
    if not (budget_has_keyword or budget_has_number):
        errors.append("Budget section must state a concrete ceiling (a number of iterations, changed files, time, or cost) and a stop rule")
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

    # Evidence section needs commands/results/artifacts. Accept common phrasings, not exact labels.
    evidence = sections.get("Evidence Required", "").lower()
    evidence_needs = {
        "Files changed": ["files changed", "files modified", "changed files", "modified files"],
        "Commands run": ["commands run", "commands executed", "command output", "verifier output"],
        "Budget used": ["budget used", "budget consumed", "budget spent", "iterations used"],
        "Follow-up": ["follow-up", "follow up", "followup", "next steps"],
    }
    for label, synonyms in evidence_needs.items():
        if not any(s in evidence for s in synonyms):
            warnings.append(f"Evidence Required may be missing: {label}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "repairs": suggest_repairs(errors),
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
        for fix in result.get("repairs", []):
            print(f"REPAIR: {fix}")
        if result.get("hash_written"):
            print(f"hash written: {result['hash_written']}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
