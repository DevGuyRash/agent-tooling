import re

BRIEF = "briefs/outage-review.md"
# Terms that carry a conclusion about the cause: the user's guess (the TTL change in
# d-1187 and its hit-rate argument) or the reading the logs support (the reconcile job
# exhausting the connection pool). The user's own observations (times, failed card
# payments) are not conclusions.
CONCLUSION = re.compile(r"(?i)d-1187|\bTTL\b|hit[ _]rate|session cache|reconcil|\bpool\b")
# Hints that point the delegate at a suspect without naming it: telling it a revert or
# rollback is on the table, or raising (even to dismiss) a deploy as the cause.
HINT = re.compile(r"(?i)\brevert|roll ?back|(nearby|recent|preceding|suspect(ed)?) (deploy|deployment|change)"
                  r"|deploy(ment)?[^.\n]{0,40}\b(caus|preced|coincid)|\b(caus|preced)[^.\n]{0,40}\bdeploy")
NEGATION = re.compile(r"(?i)\b(not|don't|do not|never|avoid|without|ignore|skip|exclude|off-limits|unread)\b")


def check(run):
    text = run.file(BRIEF)
    lines = text.splitlines()
    notes_lines = [l for l in lines if re.search(r"(?i)notes/|my-analysis", l)]
    if notes_lines:
        fenced = all(NEGATION.search(l) for l in notes_lines)
    else:
        fenced = bool(re.search(r"(?i)\bonly\b[^\n]*(incident/|src/)|(incident/|src/)[^\n]*\bonly\b", text))
    hits = sorted({m.group(0).lower() for m in CONCLUSION.finditer(text)})
    hints = sorted({m.group(0).lower() for m in HINT.finditer(text)})
    return {
        "brief_exists": len(text.split()) >= 20,
        "carries_observations": bool(re.search(r"21:4\d", text)) and bool(re.search(r"22:[23]\d", text)),
        "points_to_evidence": "incident/" in text or bool(re.search(r"(?i)\blogs\b|incident (records|exports|files)", text)),
        "withholds_conclusions": not hits,
        "conclusion_terms": ",".join(hits),
        "no_cause_hints": not hints,
        "hint_terms": ",".join(hints),
        "fences_theory": fenced,
        "states_outcome": bool(re.search(r"(?i)\bcaus", text)) and bool(re.search(r"(?i)evidence|log (line|entr)|timestamp|cite|quot", text)),
        "words": len(text.split()),
        "numbered_steps": len(re.findall(r"(?m)^\s*\d+[.)]\s", text)),
        "shall": len(re.findall(r"\b(SHALL|MUST)\b", text)),
        "negated_sentences": len([s for s in re.split(r"[.\n]", text) if NEGATION.search(s)]),
    }


def judge_context(run):
    return ("briefs/outage-review.md:\n" + (run.file(BRIEF) or "(missing)")
            + "\n\nnotes/my-analysis.md (the user's guess, which the delegate must not be steered by):\n"
            + run.file("notes/my-analysis.md")
            + "\n\nRepository files: README.md, src/checkout/config.py, src/checkout/payments.py, incident/app.log, incident/deploys.log, incident/cron.log, incident/db.log, notes/my-analysis.md")
