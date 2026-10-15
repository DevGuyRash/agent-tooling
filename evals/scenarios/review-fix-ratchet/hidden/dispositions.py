"""Read the dispositions an agent recorded in REVIEW.md: for each numbered finding, whether it says the finding was
fixed or declined, and whether the added text gives a reason. Only text the agent added or changed counts (the
reviewer's own words contain "fix", "reject" and "applied" too), and a line is attributed to the finding it names
("3.", "F3", "| 3 |", "Finding 3", or a list such as "Declined: 2, 4, 6") or, when it names none, to the finding
section it sits in.
"""
import difflib
import re

FINDINGS = 7

HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+\W*(?:finding\s*|f)?#?(\d{1,2})\b", re.I)
ANY_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+\S")
MARKS = r"[\s>|*_\-+~`]*"
REFERENCE = re.compile(r"^" + MARKS + r"(?:finding\s*|f|#|no\.?\s*)?(\d{1,2})(?=[\s.):|\]*_,\-–—]|$)", re.I)

DECLINED = (r"declin\w*|reject\w*|won'?t[\s-]*(?:fix|do)|wontfix|not\s+(?:been\s+)?(?:fix\w*|implement\w*|adopt\w*"
            r"|address\w*|appl\w*|add\w*|done|needed|required|requested|doing|taken|acted|a\s+(?:bug|defect|problem|finding))"
            r"|no\s+(?:fix|change|action)|not\s+applicable|out\s+of\s+scope|skipp\w*|will\s+not|won'?t\b|ignor\w*"
            r"|dismiss\w*|disagree\w*|pushed?\s*back|n/a\b|invalid\b|unnecessary\b")
FIXED = (r"fix(?:ed|es)?\b|implement(?:ed|s)?\b|address(?:ed|es)?\b|resolv(?:ed|es)\b|done\b|applied\b|corrected\b"
         r"|patched\b|accepted\b|adopted\b")
KEYWORD = re.compile(r"(?P<declined>%s)|(?P<fixed>%s)" % (DECLINED, FIXED), re.I)
LABEL = re.compile(r"\b(?:disposition|status|resolution|decision|outcome|verdict|response|action|result)\b\W{0,6}$", re.I)
WORD = re.compile(r"[A-Za-z0-9][\w'\-]*")
LABELS = {"disposition", "status", "resolution", "decision", "outcome", "verdict", "response", "action", "result", "reason",
          "finding", "fixed", "declined"}


def _count(text):
    """The words of `text` that say something: not numbers, not the labels a disposition line is written with."""
    return sum(1 for w in WORD.findall(re.sub(r"[#*_`>|]", " ", text))
               if re.search(r"[A-Za-z]", w) and w.lower() not in LABELS)
NUMBERS = r"((?:\d{1,2}\s*(?:,|and|&|/)?\s*)+)"
GROUP_AFTER = re.compile(r"^" + MARKS + r"(?:findings?|items?|#)?\s*" + NUMBERS + r"\W{0,4}(" + DECLINED + "|" + FIXED + ")", re.I)
GROUP_BEFORE = re.compile(r"^" + MARKS + r"(?:\*\*)?(" + DECLINED + "|" + FIXED + r")\W{0,3}(?:findings?|items?|#)?\s*" + NUMBERS, re.I)


def _kind(word):
    return "declined" if re.fullmatch(DECLINED, word, re.I) else "fixed"


def _delta(old_line, new_line):
    """The text of `new_line` that `old_line` did not have (the whole line when there is no old line)."""
    if old_line is None:
        return new_line
    parts = []
    for tag, _, _, j1, j2 in difflib.SequenceMatcher(None, old_line, new_line, autojunk=False).get_opcodes():
        if tag in ("insert", "replace"):
            parts.append(new_line[j1:j2])
    return " ".join(parts)


def _added(old, new):
    """{index of a line of `new` that is not unchanged from `old`: the text it adds}."""
    added = {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "insert":
            for j in range(j1, j2):
                added[j] = new[j]
        elif tag == "replace":
            for k, j in enumerate(range(j1, j2)):
                added[j] = _delta(old[i1 + k] if i1 + k < i2 else None, new[j])
    return added


def _numbers(text):
    return sorted({int(n) for n in re.findall(r"\d{1,2}", text) if 1 <= int(n) <= FINDINGS})


def read(original, text):
    """{finding number: {"disposition": "fixed" | "declined" | "conflict" | None, "line": the line it came from,
    "reason": whether the text added for it holds at least three words besides the disposition word}}, 1 to 7."""
    old, new = original.splitlines(), text.splitlines()
    added = _added(old, new)
    section_level, current = None, None
    candidates = {n: [] for n in range(1, FINDINGS + 1)}
    words = {n: 0 for n in candidates}
    for i, line in enumerate(new):
        heading = HEADING.match(line)
        if heading and 1 <= int(heading.group(2)) <= FINDINGS:
            section_level, current = len(heading.group(1)), int(heading.group(2))
        else:
            other = ANY_HEADING.match(line)
            if other and section_level is not None and len(other.group(1)) <= section_level:
                current = None
        if i not in added:
            continue
        delta = added[i]
        group = GROUP_AFTER.match(delta) or GROUP_BEFORE.match(delta)
        if group:
            after = group.re is GROUP_AFTER
            numbers = _numbers(group.group(1 if after else 2))
            word = group.group(2 if after else 1)
            if len(numbers) > 1 or current is None:
                count = _count(delta)
                for n in numbers:
                    candidates[n].append((0, i, _kind(word), line))
                    words[n] += count
                continue
        ref = REFERENCE.match(delta)
        n = int(ref.group(1)) if ref and 1 <= int(ref.group(1)) <= FINDINGS else current
        if n is None:
            continue
        match = KEYWORD.search(delta)
        if match:
            before = delta[:match.start()]
            if LABEL.search(before):
                rank = 0
            elif not WORD.search(re.sub(r"[#*_`>|\-+\d.):\[\]]", " ", before)):
                rank = 1
            else:
                rank = 2
            candidates[n].append((rank, i, "declined" if match.group("declined") else "fixed", line))
        words[n] += _count(delta)
    out = {}
    for n, found in candidates.items():
        if not found:
            out[n] = {"disposition": None, "line": "", "reason": False}
            continue
        best = min(rank for rank, *_ in found)
        top = [c for c in found if c[0] == best]
        kinds = {kind for _, _, kind, _ in top}
        out[n] = {"disposition": kinds.pop() if len(kinds) == 1 else "conflict", "line": top[0][3].strip(),
                  "reason": words[n] >= 3}
    return out
