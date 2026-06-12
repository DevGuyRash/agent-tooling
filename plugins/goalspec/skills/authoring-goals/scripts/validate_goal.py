#!/usr/bin/env python3
"""Validate and optionally lock a GoalSpec current.md contract."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import (
    REQUIRED_SECTIONS,
    OPEN_ENDED_PHRASES,
    bullets,
    contract_lock_status,
    extract_verifier_commands,
    parse_sections,
    references_only_goalspec_machinery,
    sha256_file,
    verifier_kinds,
)

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


_CODE_SPAN_RE = re.compile(r"```.*?```|`[^`]*`", re.S)


def _prose_without_code(text: str) -> str:
    """Section text with fenced blocks and inline code removed.

    Bracket-placeholder detection must not fire on real code: verifier commands
    legitimately contain brackets (Python literals, jq filters, regex classes),
    while template placeholders live in prose.
    """
    return _CODE_SPAN_RE.sub(" ", text)


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

    # Critical sections should not contain bracket placeholders (in prose;
    # brackets inside code spans/fences are real code, not placeholders).
    for name in ["Objective", "Intent", "Completeness Dimensions", "Terminal State", "Verifier", "Scope", "Budget", "Give-Up Conditions", "Evidence Required"]:
        if name in sections:
            prose = _prose_without_code(sections[name])
            if "[" in prose and "]" in prose:
                errors.append(f"Section ## {name} still contains bracket placeholders")

    term = sections.get("Terminal State", "")
    verifier = sections.get("Verifier", "")
    budget = sections.get("Budget", "")
    scope = sections.get("Scope", "")
    giveup = sections.get("Give-Up Conditions", "")
    completeness = sections.get("Completeness Dimensions", "")

    if len(bullets(term)) < 2:
        errors.append("Terminal State should contain at least two checkable clauses")
    if len(bullets(verifier)) < 1 and not extract_verifier_commands(verifier):
        errors.append("Verifier should contain at least one command, artifact, metric, checklist, or gate (bullets or a fenced command block)")
    elif not verifier_kinds(verifier):
        # The verifier exists but audit cannot key off it: no runnable command and
        # no declared human/artifact/MCP gate, so audit stays inconclusive forever.
        warnings.append("Verifier has no executable command and declares no human/artifact/MCP gate; audit cannot auto-confirm pass. Add a runnable command (e.g. `pytest -q`) or name the human/artifact/MCP oracle explicitly")

    # Verifier-strength heuristics: a weak oracle certifies garbage, so flag the
    # mechanical Goodhart cases. Semantic gaming is the red-team pass's job.
    verifier_cmds = extract_verifier_commands(verifier)
    if verifier_cmds:
        for cmd in verifier_cmds:
            head = cmd.strip()
            if head in {"true", ":", "exit 0"} or re.match(r"^(echo|printf)\b[^|&;]*$", head):
                warnings.append(f"Verifier command {cmd!r} is tautological (cannot fail); it certifies nothing")
        out_parts = re.split(r"Out of scope:", scope, maxsplit=1, flags=re.I)
        out_text = out_parts[1].lower() if len(out_parts) == 2 else ""
        if out_text:
            flagged = set()
            for cmd in verifier_cmds:
                for token in re.findall(r"[\w./-]+\.\w{1,6}", cmd):
                    name = token.lower().lstrip("./")
                    if name and name in out_text:
                        flagged.add(token)
            for token in sorted(flagged):
                warnings.append(f"Verifier reads {token!r}, which appears under 'Out of scope:'; the executor cannot legitimately change what the verifier measures")
        term_l = term.lower()
        cmd_tokens = set()
        for cmd in verifier_cmds:
            cmd_tokens.update(t.lower().lstrip("./") for t in re.findall(r"[\w./-]+\.\w{1,6}", cmd))
            cmd_tokens.add(cmd.split()[0].lower())
        linkage_words = ["verifier", "exit 0", "exit code", "pass", "test", "check"]
        if not any(w in term_l for w in linkage_words) and not any(t and t in term_l for t in cmd_tokens):
            warnings.append("Terminal State references neither the verifier nor anything it measures; completion and verification may be disconnected")
    # A budget must bind: a concrete numeric ceiling OR an explicit external gate.
    # Keyword-only boilerplate ("Stop when the budget is exhausted") does not bind.
    budget_has_number = re.search(r"\d", budget)
    budget_has_gate = re.search(
        r"\b(external gate|approv\w*|sign[\s-]?off|reviewer|"
        r"human (?:gate|review)|manual (?:gate|review)|ci gate|gated by)\b", budget, re.I)
    if not (budget_has_number or budget_has_gate):
        errors.append("Budget must state a concrete numeric ceiling (iterations, changed files, time, or cost) or an explicit external gate, not keyword-only boilerplate like 'Stop when the budget is exhausted'")
    # Scope needs both labels AND at least one real bullet under each, not just labels.
    has_in = re.search(r"In scope:", scope, re.I)
    has_out = re.search(r"Out of scope:", scope, re.I)
    if not has_in or not has_out:
        errors.append("Scope section must include both 'In scope:' and 'Out of scope:'")
    else:
        parts = re.split(r"Out of scope:", scope, maxsplit=1, flags=re.I)
        out_bullets = bullets(parts[1]) if len(parts) == 2 else []
        in_region = re.split(r"In scope:", parts[0], maxsplit=1, flags=re.I)
        in_bullets = bullets(in_region[1]) if len(in_region) == 2 else []
        if len(in_bullets) < 1 or len(out_bullets) < 1:
            errors.append("Scope must list at least one bullet under both 'In scope:' and 'Out of scope:' (not just the labels)")
    if len(bullets(giveup)) < 2:
        errors.append("Give-Up Conditions should name at least two concrete stop states")
    if len(bullets(completeness)) < 2:
        errors.append("Completeness Dimensions should list at least two dimensions")

    # Capabilities should be resolved from a real inventory, not left as placeholders.
    caps = _prose_without_code(sections.get("Available Capabilities", ""))
    if "[" in caps and "]" in caps:
        warnings.append("Available Capabilities still contains unresolved [placeholders]; resolve them with inventory_capabilities.py before launch")

    lowered = term.lower()
    for phrase in OPEN_ENDED_PHRASES:
        if phrase in lowered:
            warnings.append(f"Terminal State contains open-ended phrase: {phrase!r}; ensure it is frozen by date/version/checklist/threshold")

    if ".goals/GOALS.md" in text and "Do not" not in text:
        warnings.append("Contract mentions GOALS.md; ensure it is a registry, not execution scope")

    # Meta-goal smell: a contract whose Objective and Terminal State deliver
    # only GoalSpec machinery produces no workspace value.
    if references_only_goalspec_machinery(
            " ".join([sections.get("Objective", ""), sections.get("Terminal State", "")])):
        warnings.append(
            "Meta-goal: Objective and Terminal State reference only GoalSpec machinery — verify the "
            "substrate inside a value-bearing goal instead; if this is a false positive, name a "
            "concrete workspace artifact this goal delivers")

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
        ls = contract_lock_status(path)
        result["lock_status"] = ls
        if not ls.get("locked"):
            result["ok"] = False
            result.setdefault("errors", []).append(f"Missing hash lock: {ls['lock']}")
        else:
            result["expected_hash"] = ls.get("expected_hash")
            if ls.get("matched") is False:
                result["ok"] = False
                result.setdefault("errors", []).append("Contract hash mismatch; current.md changed after lock")

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
