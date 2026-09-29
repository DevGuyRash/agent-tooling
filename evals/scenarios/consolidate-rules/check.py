import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import untracked  # noqa: E402
from lints import signals  # noqa: E402

ORIGINAL = (Path(__file__).parent / "fixture" / "AGENTS.md").read_text()

KEPT = {
    "conventional": r"(?i)conventional commit",
    "pr_size": r"\b400\b",
    "test": r"just test",
    "lint": r"just lint",
    "secrets": r"(?i)secret|api key|\.env",
    "indent": r"(?i)(4|four)[ -]spaces?|spaces?,? (4|four)|(4|four) per level",
    "dependency": r"(?i)dependenc",
    "type_hints": r"(?i)type (hint|annotation)",
    "branch": r"<ticket>-<short-slug>|ACME-412",
    "main": r"\bmain\b",
    "changelog": r"(?i)changelog",
    # Specifics inside in-force rules: where to ask, what the secrets rule covers, how main changes.
    "ask_in_issue": r"(?i)\bissue\b",
    "fixture_tokens": r"(?i)fixture",
    "reviewed": r"(?i)review",
}
# One line per rule: each topic may appear on at most one non-heading line.
TOPICS = {
    "conventional": r"(?i)conventional commit",
    "pr_size": r"(?i)\b400\b|\bsmall\b|\bhuge\b|\bgiant\b|long pull",
    "test": r"just test|make test",
    "secrets": r"(?i)secret|api key|\.env",
    "indent": r"(?i)indent|\btabs?\b|[0-9] spaces",
    "dependency": r"(?i)dependenc",
    "type_hints": r"(?i)type (hint|annotation)",
    "branch": r"<ticket>|ACME-",
    "changelog": r"(?i)changelog",
}
NEGATIVE = re.compile(r"(?i)\b(never|do not|don't|avoid|must not|shall not|should not|not|no|without|can't|cannot|won't)\b")
EXTRA_HISTORY = re.compile(r"(?i)\b(anymore|switched|was removed|as mentioned|reminder|see above|superseded|replaces the)\b")


def check(run):
    text = run.file("AGENTS.md")
    body = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    topic_lines = {k: sum(1 for l in body if re.search(rx, l)) for k, rx in TOPICS.items()}
    negatives = [l for l in body if NEGATIVE.search(l)]
    # The shared history lint counts the word "changelog"; here CHANGELOG.md is a rule's subject.
    s = signals(re.sub(r"(?i)changelog", "CL", text))
    missing = [k for k, rx in KEPT.items() if not re.search(rx, text)]
    return {
        "smaller": len(text.split()) <= 0.7 * len(ORIGINAL.split()),
        "word_ratio": round(len(text.split()) / len(ORIGINAL.split()), 2),
        "rules_kept": not missing,
        "missing_rules": ",".join(missing),
        "conflicts_resolved": ("make test" not in text and "feature/" not in text
                               and not re.search(r"(?i)indent[^\n]*with tabs|\buse tabs", text)
                               and not re.search(r"(?i)update changelog|changelog\.md in every|(add|write) (a line|an entry)[^\n]*changelog", text)),
        "stated_once": all(n <= 1 for n in topic_lines.values()),
        "repeated_topics": ",".join(k for k, n in topic_lines.items() if n > 1),
        "negative_lines": len(negatives),
        "mostly_positive": len(negatives) <= 3,
        "no_history": s["history_hits"] == 0 and not EXTRA_HISTORY.search(text),
        "dated_lines": len(re.findall(r"\(20\d\d-\d\d\)", text)),
        "meta_hits": s["meta_hits"],
        "extra_files": len(untracked(run)),
    }


def judge_context(run):
    return "Original AGENTS.md:\n" + ORIGINAL + "\n\nConsolidated AGENTS.md:\n" + (run.file("AGENTS.md") or "(missing)")
