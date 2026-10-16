"""Reading a review written in Markdown, for review-flags-excess: its blocks, their clauses, and negation.

A review has no fixed format: headings with a paragraph under each, bullet lists, numbered findings, tables, or plain
paragraphs. This module turns any of them into blocks that a check can read the same way.

- A line that is only bold, or only capitals ("**B. Unrequested (remove)**", "OK AS WRITTEN"), is read as a heading.
- A block is one heading, one list item (with its continuation lines), one table row, or one paragraph. Its frames are
  the texts that frame it: the two nearest headings above it, the line ending in a colon that leads into its list, and
  the list item it is nested under. A cue in a frame ("Things nobody asked for") reaches the blocks under it.
- A clause is a stretch of a block that says one thing: a sentence, cut again at a semicolon, at a contrast word
  (but, however, although, while, yet, unlike), and around a parenthesis of four words or more. Clauses are the
  unit of "near": a cue and a name that share a clause belong together; a cue and a name in different clauses do not,
  unless the second clause points back at the first (see excess_signals.py).
- Negation is read per cue: a negator (not, no, never, nothing, n't, without, ...) within five words before it, with no
  comma, colon, semicolon, or table cell between, turns it round ("not unnecessary", "no over-engineering", "don't remove").
"""
import re

SMART = {"\u2013": "-", "\u2014": " - ", "\u2012": "-", "\u2011": "-", "\u2212": "-", "\u2192": "->", "\u2018": "'",
         "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " ", "\u2022": "-", "\u2713": "ok", "\u2714": "ok"}

HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
FENCE = re.compile(r"^ {0,3}(?:```|~~~)[ \t]*([A-Za-z0-9_+-]*)")
TEXT_FENCES = {"", "yaml", "yml", "markdown", "md", "text", "txt", "plain", "plaintext"}
RULE = re.compile(r"^ {0,3}([-*_])([ \t]*\1){2,}[ \t]*$")
ITEM = re.compile(r"^([ \t]*)(?:[-*+]|\d{1,3}[.)])[ \t]+(?:\[[ xX]\][ \t]+)?(.*)$")
ROW = re.compile(r"^[ \t]*\|(.*)$")
TABLE_RULE = re.compile(r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-{2,}:?[ \t]*)*\|?[ \t]*$")
NEGATORS = {"not", "no", "never", "nothing", "none", "neither", "nor", "without", "cannot", "hardly", "nobody"}
WORD = re.compile(r"[A-Za-z0-9_']+")
CONTRAST = re.compile(r"(?:(?<=[\s,])|^)(?=(?:but|however|although|though|whereas|while|yet|unlike)\b)", re.I)
SENTENCE = re.compile(r"(?<=[.!?])(?<!e\.g\.)(?<!i\.e\.)(?<!etc\.)(?<!vs\.)(?<!cf\.)\s+(?=\S)|;\s*")
PAREN = re.compile(r"\(([^()]*)\)")
LONGEST = 600  # characters in a clause; a longer stretch with no sentence end is cut into pieces of at most this


BOLD_LINE = re.compile(r"^[ \t]*(?:\*\*|__)([^*_].*?)(?:\*\*|__)[ \t]*:?[ \t]*$")
CAPS_LINE = re.compile(r"^[ \t]*([A-Z][A-Z0-9 /&()',.-]{3,60}):?[ \t]*$")


def label_lines(raw):
    """A line that is only bold, or only capitals, is a label for what follows: it becomes a level-6 heading."""
    out = []
    for line in raw.replace("\r\n", "\n").split("\n"):
        m = BOLD_LINE.match(line) or CAPS_LINE.match(line)
        out.append("###### " + m.group(1).strip() if m and not RULE.match(line) and not TABLE_RULE.match(line) else line)
    return "\n".join(out)


def clean(text):
    """The text with Markdown marks, smart punctuation, and link targets taken out."""
    for old, new in SMART.items():
        text = text.replace(old, new)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(\*\*|__|~~|`)", "", text)
    return text.replace("\r\n", "\n")


class Block:
    def __init__(self, kind, text, frames, section, level=0, lines=()):
        self.kind = kind  # heading, item, row, or para
        self.text = text
        self.lines = list(lines)  # the lines a paragraph was written on
        self.frames = frames
        self.section = section  # which heading section it sits in (0 before the first heading)
        self.level = level  # of a heading

    def __repr__(self):
        return "Block(%s, %r, frames=%r)" % (self.kind, self.text[:40], [f[:20] for f in self.frames])


def blocks(raw):
    """The blocks of a Markdown review, in order."""
    lines = clean(label_lines(raw)).split("\n")
    out, headings, parents = [], [], []  # headings: [(level, text)]; parents: [(indent, text)] of open list items
    current, leadin, section, fenced, hang, opaque = None, None, 0, False, 0, False

    def frames(extra=()):  # the two nearest headings, so a title never frames the whole review
        return [t for _, t in headings][-2:] + ([leadin] if leadin else []) + list(extra)

    def flush():
        nonlocal current, leadin
        if current is not None:
            kind, indent, parts, frame, sect = current
            text = re.sub(r"\s+", " ", " ".join(parts)).strip()
            if text:
                out.append(Block(kind, text, frame, sect, lines=[p.strip() for p in parts if p.strip()]))
                if kind == "para":
                    label = len(WORD.findall(text)) <= 3 and not re.search(r"[.!?]$", text)
                    leadin = text if text.endswith(":") or label else None
            current = None

    for number, line in enumerate(lines):
        fence = FENCE.match(line)
        if fence:
            fenced = not fenced
            opaque = fenced and fence.group(1).lower() not in TEXT_FENCES  # code is one stretch of text; a review in a fence is a review
            if current is None and opaque:
                current = ("para", 0, [], frames(), section)
            elif not fenced:
                opaque = False
            continue
        if fenced and opaque:
            if current is None:
                current = ("para", 0, [], frames(), section)
            current[2].append(line.strip())
            continue
        if not line.strip():
            flush()
            continue
        heading = HEADING.match(line)
        underline = SETEXT.match(line)
        if heading or (underline and current is not None and current[0] == "para" and len(current[2]) == 1):
            if heading:
                level, text = len(heading.group(1)), heading.group(2)
                flush()
            else:  # the paragraph above is a heading
                level, text = 1 if underline.group(1)[0] == "=" else 2, " ".join(current[2])
                current = None
            headings[:] = [h for h in headings if h[0] < level]
            frame = frames()
            headings.append((level, text))
            section += 1
            parents.clear()
            leadin = None
            out.append(Block("heading", text, frame, section, level))
            continue
        if RULE.match(line):
            flush()
            continue
        if ROW.match(line):
            if TABLE_RULE.match(line):
                flush()
                if out and out[-1].kind == "row":  # the row before the rule was the table's header, not a finding
                    out.pop()
                continue
            flush()
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            leadin = None
            out.append(Block("row", " | ".join(c for c in cells if c), frames(), section))
            continue
        indent_now = len(line) - len(line.lstrip(" \t"))
        if current is not None and current[0] == "para" and len(current[2]) == 1 and indent_now >= 2 and not ITEM.match(line):
            label = current[2][0]  # a label line with indented lines under it: the label frames each of them
            current = None
            out.append(Block("para", label, frames(), section))
            leadin = label
            hang = indent_now
            current = ("item", indent_now, [line.strip()], frames(), section)
            continue
        if current is not None and current[0] == "item" and hang and indent_now == hang and not ITEM.match(line):
            flush()
            current = ("item", indent_now, [line.strip()], frames(), section)
            continue
        item = ITEM.match(line)
        if item:
            hang = 0
            if current is not None and current[0] == "para":  # a paragraph with the list right under it leads into it
                lead = re.sub(r"\s+", " ", " ".join(current[2])).strip()
                flush()
                leadin = lead
            else:
                flush()
            indent = len(item.group(1).replace("\t", "    "))
            while parents and parents[-1][0] >= indent:
                parents.pop()
            frame = frames([t for _, t in parents])
            parents.append((indent, item.group(2)))
            current = ("item", indent, [item.group(2)], frame, section)
            continue
        if current is None:
            leadin = None  # a paragraph after a list is not part of what the list was led into
            current = ("para", 0, [line.strip()], frames(), section)
        else:
            current[2].append(line.strip())
    flush()
    return out


def findings_in(block):
    """The texts a block holds as separate findings: a paragraph written one finding to a line ("Bug: ...", "Not needed:
    ...") is read line by line, where a line that ends a sentence is followed by a line that starts one; anything else is one."""
    if block.kind != "para" or len(block.lines) < 2:
        return [block.text]
    groups = [[block.lines[0]]]
    for line in block.lines[1:]:
        if re.search(r"[.!?:]$", groups[-1][-1]) and re.match(r"[A-Z0-9(\[]", line):
            groups.append([line])
        else:
            groups[-1].append(line)
    return [re.sub(r"\s+", " ", " ".join(g)).strip() for g in groups]


def clauses(text, kind="para", names=None):
    """The clauses of a block's text (see the module docstring); a table row is one clause. A parenthetical stays in its
    clause when `names(text)` finds nothing named outside the parentheses: "Unrequested option (--rounding, four modes)"."""
    if kind == "row":
        return [text]
    pieces = []
    outside = PAREN.sub(" ", text)

    def keep_short(match):
        inner = match.group(1)
        if len(WORD.findall(inner)) >= 4 and not (names is not None and not names(outside)):
            pieces.append(inner)
            return " "
        return " %s " % inner

    text = PAREN.sub(keep_short, text)
    out = []
    for sentence in [text] + pieces:
        for part in SENTENCE.split(sentence):
            for clause in CONTRAST.split(part or ""):
                clause = re.sub(r"\s+", " ", clause).strip(" ,")
                while len(clause) > LONGEST:  # a run-on line is read in pieces, so reading stays linear in its length
                    cut = clause.rfind(" ", 0, LONGEST) if " " in clause[:LONGEST] else LONGEST
                    out.append(clause[:cut].strip())
                    clause = clause[cut:].strip()
                if clause:
                    out.append(clause)
    return out


def negated(clause, start, window=5):
    """Whether a negator stands within `window` words before `start`, with no comma, colon, semicolon, dash, or table cell between."""
    before = clause[:start]
    cut = max(before.rfind(","), before.rfind(":"), before.rfind(";"), before.rfind("|"), before.rfind(" - "))
    for token in WORD.findall(before[cut + 1:])[-window:]:
        word = token.lower()
        if word in NEGATORS or word.endswith("n't"):
            return True
    return False


def negated_after(clause, end, window=3):
    """Whether a negator follows within `window` words after `end`: "says nothing", "has no", "does not say"."""
    for token in WORD.findall(clause[end:])[:window]:
        word = token.lower()
        if word in NEGATORS or word.endswith("n't"):
            return True
    return False


def words(text):
    return len(re.findall(r"\S+", text))
