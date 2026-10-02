"""Reading the decision record an agent wrote from a repository's decisions/TEMPLATE.md.

Used by support-prompt-decision and router-prompt-decision (review-rule-prereg uses only the path
helpers). The template's front matter carries `outcome: <adopt | reject | inconclusive>` and the
candidate's and incumbent's pass counts; everything the agent wrote is read through the run's confined
primitives (run.git, run.file).
"""
import re

# An unfilled template slot such as "<adopt | reject | inconclusive>"; a lone "<" or "|" in a filled-in
# value ("adopt (gap < spread)") is the agent's own text.
TEMPLATE_SLOT = re.compile(r"<[^<>]*>")
_NOT = (r"(?:do(?:es)?\s+not|did\s+not|don'?t|doesn'?t|won'?t|will\s+not|would\s+not|wouldn'?t|cannot|can'?t|"
        r"should\s+not|shouldn'?t|not|no|never)")
_ACT = r"(?:adopt|switch|ship|accept|approv|roll\s*out|go\s+ahead)\w*"
# Earliest match wins, so "do not adopt" and "not adopted" read as reject, "hold (pending a fix)" as
# inconclusive, and "adopt (no detectable difference)" as adopt.
OUTCOME_PATTERNS = [
    ("reject", re.compile(r"(?i)\b(?:reject\w*|declin\w*|keep\w*|stay\w*\s+(?:on|with)|no\s+change|"
                          + _NOT + r"\s+(?:yet\s+)?" + _ACT + r")")),
    ("inconclusive", re.compile(r"(?i)\b(?:inconclusive|undecided|no[- ]call|no\s+detectable|can(?:not|'t)\s+tell|"
                                r"tie\b|hold\w*|on\s+hold|defer\w*|pending|paus\w*|postpon\w*|wait\w*)")),
    ("adopt", re.compile(r"(?i)\b" + _ACT)),
]
FRACTION = re.compile(r"(\d+(?:\.\d+)?)\s*(?:/|of|out\s+of)\s*(\d+)")
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def changed_paths(run) -> list[str]:
    """Paths added, modified, or deleted since the fixture's initial commit (committed or not)."""
    base = run.read(run.harness / "initial-head").strip() or "HEAD"
    changed = set(p for p in run.git("diff", "--name-only", base).splitlines() if p.strip())
    for line in run.git("status", "--porcelain", "--untracked-files=all").splitlines():
        if line.startswith("??"):
            changed.add(line[3:].strip().strip('"'))
    return sorted(changed)


def altered_paths(run) -> list[str]:
    """Paths of the fixture that were modified or deleted since its initial commit (committed or not);
    files the agent added are not included."""
    base = run.read(run.harness / "initial-head").strip() or "HEAD"
    return sorted(p for p in run.git("diff", "--name-only", "--no-renames", "--diff-filter=DMT", base).splitlines()
                  if p.strip())


def frontmatter(text: str) -> dict:
    m = re.match(r"\A\s*---\s*\n(.*?)\n---\s*(?:\n|\Z)", text or "", re.S)
    out = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip().strip("'\"").strip()
    return out


def _outcome_of(value: str) -> str | None:
    hits = [(m.start(), name) for name, rx in OUTCOME_PATTERNS for m in [rx.search(value)] if m]
    return min(hits)[1] if hits else None


def classify_outcome(value: str | None) -> str | None:
    if not value or TEMPLATE_SLOT.search(value):
        return None
    if "|" in value and len({o for o in map(_outcome_of, value.split("|")) if o}) > 1:
        return None  # the template's list of choices with the brackets removed
    return _outcome_of(value)


def parse_figure(value: str | None):
    """(number, denominator or None, percent or None, decimals given) from a pass-count field, or None."""
    if not value or TEMPLATE_SLOT.search(value):
        return None
    m = FRACTION.search(value)
    if m:
        return float(m.group(1)), int(m.group(2)), None, "." in m.group(1)
    m = PERCENT.search(value)
    if m:
        return None, None, float(m.group(1)), "." in m.group(1)
    m = NUMBER.search(value)
    return (float(m.group(0)), None, None, "." in m.group(0)) if m else None


def figure_matches(value: str | None, options: list[tuple[float, int]], bare_runs: int) -> bool:
    """Whether a pass-count field states one of the (passes, runs) options, to the precision it is written
    in: passes/runs (a whole number must equal the option, a decimal must agree to 0.05, so a rounded mean
    never passes for another run's count), a percentage (within 0.06 points when written with decimals,
    0.51 when whole), or bare passes when that option's runs is `bare_runs` (one run of the design, the
    size the template asks about)."""
    parsed = parse_figure(value)
    if not parsed:
        return False
    num, den, pct, decimals = parsed
    for n, d in options:
        if pct is not None and abs(pct - 100.0 * n / d) <= (0.06 if decimals else 0.51):
            return True
        if num is not None and (abs(num - n) < 0.051 if decimals else num == n) \
                and (den == d or (den is None and d == bare_runs)):
            return True
    return False


def find_records(run, folder: str, earlier_records: set[str]) -> list[str]:
    """Decision records the agent wrote: new .md files under `folder` (not the fixture's earlier records),
    or, failing that, the template filled in place."""
    changed = changed_paths(run)
    added = [p for p in changed if p.startswith(folder + "/") and p.endswith(".md")
             and p not in earlier_records and p != f"{folder}/TEMPLATE.md" and run.file(p)]
    if added:
        return added
    template = f"{folder}/TEMPLATE.md"
    if template in changed and classify_outcome(frontmatter(run.file(template)).get("outcome")):
        return [template]
    return []


def read_decision(run, folder: str, earlier_records: set[str]) -> dict:
    """{records, outcome, fields, text}: outcome is None when no record parses or records disagree; fields
    are the front matter of the first record whose outcome parses, else of the first record."""
    records = find_records(run, folder, earlier_records)
    outcomes, fields, first, texts = set(), {}, {}, []
    for rel in records:
        text = run.file(rel)
        texts.append(f"--- {rel} ---\n{text}")
        fm = frontmatter(text)
        first = first or fm
        o = classify_outcome(fm.get("outcome"))
        if o:
            outcomes.add(o)
            if not fields:
                fields = fm
    return {"records": records, "outcome": outcomes.pop() if len(outcomes) == 1 else None,
            "fields": fields or first, "text": "\n\n".join(texts)}
