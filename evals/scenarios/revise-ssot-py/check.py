"""Checks for revise-ssot-py: circdesk, a library's circulation tools, where the overdue fines rule (cents a
day and the most an item can owe, by category, and a grace period) was written once in the desk receipt
(circdesk/receipt.py), copied into the overnight notices (notices.py) and the kiosk's account view
(account.py), and then changed twice, each change reaching only some of the copies: today the receipt caps
children's items at 2.50, the notices give a 3-day grace period, and the kiosk caps media at 10.00, where
docs/fines.md says 3.00, 2 days, and 12.50. The request is the board's next change (adult items 0.35 a day,
a new device category), written into docs/fines.md, to be charged by all three.

Required checks are the requested outcome:

- existing_tests_pass: the fixture's tests that the request does not touch (tests/test_loans.py,
  test_money.py, test_cli.py, and their data), placed beside the agent's code in a directory of their own,
  pass. The fixture's receipt, notices, and account tests pin the old adult rate, so they are the agent's to
  update and are not among them.
- existing_behavior_kept: hidden cases of behavior the request does not touch (exports with a byte-order
  mark, columns in another order and categories in any case, refusals with exit status 1, a category the
  policy does not know among them in every command, empty results, the kiosk's block at exactly 10.00, bad
  command lines with exit status 2) give what the fixture gives.
- new_policy_charged: every command on hidden exports where the fixture's three copies, each with the
  request applied, would agree, prints exactly what docs/fines.md gives (hidden/reference.py): adult items
  at 0.35 a day and device items at 2.40 up to 48.00.
- drift_resolved: every command on hidden exports where those copies disagree (an item exactly 3 days late,
  a children's item owing more than 2.50, a media item owing more than 10.00) prints what docs/fines.md
  gives, so the drift was resolved to the documented rule, not to one of the copies.
- all_follow_rule_edits: after the agent's change, the rule is edited again the way the board would edit it
  next year, one edit at a time, each at one place in a fresh copy of the agent's tree: the adult rate up and
  down (0.35 to 0.40 and 0.30), the device rate up (2.40 to 2.75) and its most down (48.00 to 36.00), the
  children's most up (3.00 to 3.50), the media most down and up (12.50 to 11.00 and 15.00), the grace period
  up and down (2 to 3 and 1 days), every daily rate up by 5 cents at once, "2 days late or less owes
  nothing" turned into "less than 2 days late", and "from the third day late every day counts" turned into
  "only the days past the grace period count", an edit of how the parts combine. Each edit passes when one
  place, edited, makes the receipt, the notices, and the kiosk all print what the edited rule gives on every
  hidden policy and drift case. A copy of a value, of the grace comparison, or of the multiplication of the
  days by the daily rate fails: the edit that moves one command leaves the copy behind. A copy of the cap
  alone (the min with the most an item can owe), with the multiplication shared, has no edit of its own and
  is not caught.
- one_rule_definition: at most one of the files the program is made of or reads holds the fines table (at
  least 3 of the amounts 0.15, 1.25, 3.00, and 7.00, which neither the request nor the drift touches,
  outside comments and docstrings; 3 and 7 written as whole euros count inside a bracketed structure that
  holds another of the rule's amounts), so a copy left behind unused fails.

The program's files: Python outside tests/, test/, docs/, and test_*.py or *_test.py files (and setup.py,
conftest.py), and every file such code names by a string literal ending in that file's name (a JSON or TOML
file of rates, docs/fines.md read at run time), wherever it lives. Other data files outside tests and docs
are tried last as places and count as definitions only when an edit lands in them, and so does a document
the code names (a help text mentioning docs/fines.md does not make the page a second table).

How an edit's place is found (the canonical home is wherever the agent put it, under any name or shape): a
value edit tries every occurrence of the value in the program's files in its usual spellings (35, 0.35;
4800, 4_800, 48_00, 48.00, 48.0, 48; 3 for 3.00, edited to 3.5 when the new amount is not whole; the grace
period as 2), first those inside a declaration with one of the fixture's names for that part of the rule
(DAILY_FINE, FINES, PER_DAY; MAX_FINE, FINES, MOST; GRACE_DAYS, GRACE, GRACE_PERIOD), then those in files
where an earlier edit landed, then other Python, then data the program names, then other data. The
whole-table edit is made where the adult-rate edit landed: every daily rate in the smallest bracketed
structure around that place holding all four (the whole file when none does), in the spelling family found
there. The grace comparison edit tries every <, <=, >, and >= in the program's Python outside comments and
strings, turned between strict and inclusive, and then every line holding several, all turned at once: first
those on a line naming what the grace edits landed in (the name the grace period is declared under, a key
such as "grace_days"), then those in files where the value edits landed, code importing them, and other
code. The combination edit tries each operand X of every binary * in the program's Python outside comments
and strings, turned into (X - 2) with 2 the grace period: first those on a line naming what the rate edits
landed in, then in files where the value edits landed, code importing them, and other code, an operand
naming days before the other. At most MAX_SITES candidates are tried per value edit, MAX_COMPARISON_SITES per
comparison edit, and MAX_COMBINATION_SITES per combination edit. A rule written so that no candidate is the
edit cannot be found (one example is a grace period held as the first day charged, days < FIRST_CHARGED_DAY
with FIRST_CHARGED_DAY = 3, which no grace-period edit or comparison edit can reach), and the run fails
all_follow_rule_edits with rule_edits_followed_by_receipt below the number of edits: read such a run before
counting it. An edit is followed only when every case is right under it, so a tree that is wrong before any
edit follows none; read new_policy_charged and drift_resolved first.

Nothing is timed except command limits: each command of the unedited run may take BASE_TIMEOUT seconds, and
each command of an edited run ten times the slowest of the unedited run (at least 20 seconds, at most
BASE_TIMEOUT). A command over its limit is reported as `name(timeout)`, not as a wrong answer, and when the
unedited run has one the edits are not tried.

Measures: edits followed by each command and where they landed, tries, files holding the table, where the
adult-rate edit landed, whether each consumer module imports the rule's module, amounts of the table found
outside the rule's place, the agent's own suite, test files changed, whether docs/fines.md changed, files
changed, and commits. Agent code runs only through run.sandboxed (no network, host read-only, home hidden,
own PID namespace) on fresh copies from run.copy_workdir, so the working directory stays as the agent left
it. Needs python3 3.10 or later on the system PATH inside confinement; without it the run is invalid.
"""
import io
import json
import math
import os
import re
import shutil
import stat
import sys
import tempfile
import time
import tokenize
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
sys.path.insert(0, str(HERE / "hidden"))
import reference as ref  # noqa: E402

CASES = json.loads((HERE / "hidden" / "cases.json").read_text())
CASE_FILES = CASES["files"]
ALL_CASES = CASES["cases"]
KINDS = ("policy", "drift", "existing")
FIXTURE_TESTS = ["tests/__init__.py", "tests/data/loans.csv", "tests/data/patrons.csv", "tests/test_loans.py",
                 "tests/test_money.py", "tests/test_cli.py"]
REGRESSION_DIR = "circdesk_regression_tests"
CONSUMERS = {"receipt": "circdesk/receipt.py", "notices": "circdesk/notices.py", "account": "circdesk/account.py"}
MAX_SITES = 12
MAX_COMPARISON_SITES = 20
MAX_COMBINATION_SITES = 20
BASE_TIMEOUT = 60
PARALLEL = 6
SIZE_LIMIT = 1024 * 1024
PRUNE = {".git", "__pycache__", ".venv", "venv", "env", "node_modules", ".mypy_cache", ".pytest_cache", ".tox",
         ".cache", "build", "dist", ".ruff_cache", REGRESSION_DIR}
ASIDE_DIRS = {"tests", "test", "docs"}
NOT_PROGRAM = {"setup.py", "conftest.py", "noxfile.py"}
NOT_DATA = {"pyproject.toml", "setup.cfg", "requirements.txt", "requirements-dev.txt", "tox.ini", ".gitignore",
            "uv.lock", "poetry.lock", "Pipfile", "Pipfile.lock", "MANIFEST.in", ".python-version"}
DOC_SUFFIXES = {".md", ".markdown", ".rst", ".txt"}
INTEGER_FORMS = ("cents", "thousands", "split")
DECIMAL_FORMS = ("euros", "short", "whole")


def _amount_forms(v):
    """{form: spelling} of an amount in cents: 4800, 4_800, 48_00, 48.00, 48.0, and 48 when it is whole."""
    whole, cents = divmod(v, 100)
    f = {"cents": str(v), "euros": f"{whole}.{cents:02d}", "short": repr(v / 100)}
    if v >= 100:
        f["split"] = f"{whole}_{cents:02d}"
    if v >= 1000:
        f["thousands"] = f"{v // 1000}_{v % 1000:03d}"
    if cents == 0 and v:
        f["whole"] = str(whole)
    return f


def _cents(old, new):
    """(old, new) in each usual spelling of an amount in cents, one edited spelling for each old one; an old
    amount written as whole euros (3) becomes the new one's short spelling (3.5) when that has no whole one."""
    o, n = _amount_forms(old), _amount_forms(new)
    pairs = {}
    for k in o:
        if k in n:
            pairs.setdefault(o[k], n[k])
    if "whole" in o and "whole" not in n:
        pairs.setdefault(o["whole"], n["short"])
    return list(pairs.items())


RATE_DECLS = ("DAILY_FINE", "FINES", "PER_DAY")
MOST_DECLS = ("MAX_FINE", "FINES", "MOST")
GRACE_DECLS = ("GRACE_DAYS", "GRACE", "GRACE_PERIOD")
R = ref.RULE["rates"]
# (name, the edited rule, the fixture's names for that part of the rule, [(spelling, edited spelling)])
VALUE_EDITS = [
    ("adult-rate-up", ref.mutated(per_day={"adult": 40}), RATE_DECLS, _cents(R["adult"][0], 40)),
    ("adult-rate-down", ref.mutated(per_day={"adult": 30}), RATE_DECLS, _cents(R["adult"][0], 30)),
    ("device-rate-up", ref.mutated(per_day={"device": 275}), RATE_DECLS, _cents(R["device"][0], 275)),
    ("device-most-down", ref.mutated(most={"device": 3600}), MOST_DECLS, _cents(R["device"][1], 3600)),
    ("children-most-up", ref.mutated(most={"children": 350}), MOST_DECLS, _cents(R["children"][1], 350)),
    ("media-most-down", ref.mutated(most={"media": 1100}), MOST_DECLS, _cents(R["media"][1], 1100)),
    ("media-most-up", ref.mutated(most={"media": 1500}), MOST_DECLS, _cents(R["media"][1], 1500)),
    ("grace-up", ref.mutated(grace=3), GRACE_DECLS, [("2", "3")]),
    ("grace-down", ref.mutated(grace=1), GRACE_DECLS, [("2", "1")]),
]
RISE = 5
WHOLE_EDIT = ("all-rates-up", ref.mutated(per_day={c: v[0] + RISE for c, v in R.items()}))
COMPARISON_EDITS = [("grace-strict", ref.mutated(grace_strict=True), ("grace-up", "grace-down"))]
# (name, the edited rule, the value edits whose bound names order its candidates): only the days past the
# grace period are charged, made by turning the day count X of the multiplication into (X - GRACE).
COMBINATION_EDITS = [("charge-after-grace", ref.mutated(charge_after_grace=True), ("adult-rate-up", "device-rate-up"))]
GRACE = str(ref.RULE["grace"])
EDIT_COUNT = len(VALUE_EDITS) + 1 + len(COMPARISON_EDITS) + len(COMBINATION_EDITS)
RATE_VALUES = [v[0] for v in R.values()]
ALL_AMOUNTS = sorted({v for pair in R.values() for v in pair})
# Amounts of the table that neither the request nor the drift touches: a file holding at least
# TABLE_MARKS of them holds the table.
TABLE_AMOUNTS = (R["children"][0], R["media"][0], R["children"][1], R["adult"][1])
TABLE_MARKS = 3
TOGGLE = {"<=": "<", ">=": ">", "<": "<=", ">": ">="}
KEYWORDS = {"def", "class", "return", "lambda", "if", "else", "elif", "for", "while", "in", "not", "and", "or",
            "is", "None", "True", "False", "import", "from", "as", "with", "yield", "self", "cls"}


# ---------------------------------------------------------------- the agent's files

def _is_aside(rel):
    parts = Path(rel).parts
    name = parts[-1]
    return (bool(ASIDE_DIRS & set(parts[:-1])) or name in NOT_PROGRAM or name.startswith("test_")
            or name.endswith("_test.py"))


def _is_code(rel):
    return rel.endswith(".py")


def _is_doc(rel):
    return Path(rel).suffix.lower() in DOC_SUFFIXES


def _files(root):
    """{relative path: text} of every regular UTF-8 text file in the agent's tree outside version control,
    environments, and caches, except package metadata; never through a link."""
    out = {}
    for d, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(x for x in dirs if x not in PRUNE and not x.endswith(".egg-info")
                         and not os.path.islink(os.path.join(d, x)))
        for n in sorted(names):
            p = Path(d) / n
            if n in NOT_DATA:
                continue
            try:
                st = os.lstat(p)
                if not stat.S_ISREG(st.st_mode) or st.st_size > SIZE_LIMIT:
                    continue
                data = p.read_bytes()
            except OSError:
                continue
            if b"\0" in data:
                continue
            try:
                out[p.relative_to(root).as_posix()] = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
    return out


_FSTRING = tuple(t for t in (getattr(tokenize, "FSTRING_START", None), getattr(tokenize, "TSTRING_START", None)) if t)
_FSTRING_END = tuple(t for t in (getattr(tokenize, "FSTRING_END", None), getattr(tokenize, "TSTRING_END", None)) if t)
_SKIP = {tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT}


def _py_spans(text):
    """[(kind, start, end)] character spans of a Python source's comments ("c"), docstrings and other bare
    string statements ("d"), and other string literals, f-strings whole ("s"); None when it does not
    tokenize."""
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))

    def at(pos):
        row, col = pos
        return starts[row - 1] + col if row - 1 < len(starts) else len(text)

    toks, spans, stack = [], [], []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type in _FSTRING:
                stack.append(at(tok.start))
                continue
            if tok.type in _FSTRING_END:
                start = stack.pop()
                if not stack:
                    toks.append((tokenize.STRING, start, at(tok.end)))
                continue
            if stack:
                continue
            toks.append((tok.type, at(tok.start), at(tok.end)))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    for i, (kind, a, b) in enumerate(toks):
        if kind == tokenize.COMMENT:
            spans.append(("c", a, b))
        elif kind == tokenize.STRING:
            j = i - 1
            while j >= 0 and toks[j][0] in _SKIP:
                j -= 1
            k = i + 1
            while k < len(toks) and toks[k][0] in _SKIP:
                k += 1
            bare = (j < 0 or toks[j][0] in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING)) and \
                (k >= len(toks) or toks[k][0] in (tokenize.NEWLINE, tokenize.ENDMARKER))
            spans.append(("d" if bare else "s", a, b))
    return spans


_FALLBACK = re.compile(r"(?P<c>#[^\n]*)|(?P<s>'''.*?'''|\"\"\".*?\"\"\"|'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\")", re.S)


def _spans(text):
    spans = _py_spans(text)
    if spans is None:
        spans = [("c" if m.group("c") else "s", m.start(), m.end()) for m in _FALLBACK.finditer(text)]
    return spans


def _blank_spans(text, spans, kinds, keep_names=False):
    out = list(text)
    for kind, a, b in spans:
        if kind not in kinds:
            continue
        if keep_names and kind == "s" and re.fullmatch(r"[rRbBuU]?(['\"])[A-Za-z_]\w*\1", text[a:b]):
            continue
        for i in range(a, b):
            if out[i] != "\n":
                out[i] = " "
    return "".join(out)


def _shipped(rel, text):
    """What of a file can define something: Python with its comments and docstrings blanked, data as it is."""
    return _blank_spans(text, _spans(text), {"c", "d"}) if _is_code(rel) else text


def _code_only(text):
    """Python with comments, docstrings, and strings blanked (offsets and line breaks kept)."""
    return _blank_spans(text, _spans(text), {"c", "d", "s"})


def _names_shown(text):
    """Python with comments, docstrings, and strings blanked, except strings that are a bare name (a key such
    as "grace_days" used as rule["grace_days"])."""
    return _blank_spans(text, _spans(text), {"c", "d", "s"}, keep_names=True)


_DATA_STRINGS = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"")


def _structure(rel, text):
    """The text with comments and strings blanked, for matching brackets."""
    if _is_code(rel):
        return _code_only(text)
    return _DATA_STRINGS.sub(lambda m: " " * len(m.group(0)), text)


def _literals(text):
    return [text[a:b] for kind, a, b in _spans(text) if kind == "s"]


def _program(files):
    """The files the program is made of or reads: Python outside tests and docs, and every file such code
    names by a string literal ending in the file's name, followed through the code it names."""
    todo = [rel for rel in files if _is_code(rel) and not _is_aside(rel)]
    seen = set()
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        if _is_code(rel):
            todo.extend(_named_files(files, rel))
    return seen


_IMPORT = re.compile(r"^\s*(?:from\s+(\.*[\w.]*)\s+import\s+([\w*, ()]+)|import\s+([\w., ]+))", re.M)


def _module_file(files, base_dir, dotted):
    parts = [p for p in dotted.split(".") if p]
    for cand in ("/".join([*base_dir, *parts]) + ".py", "/".join([*base_dir, *parts, "__init__.py"])):
        cand = cand.lstrip("/")
        if cand in files:
            return cand
    return None


def _imports(files, rel):
    """Program files a Python module imports, relatively or by its package's name."""
    text = _code_only(files[rel])
    here = list(Path(rel).parts[:-1])
    found = set()
    for m in _IMPORT.finditer(text):
        if m.group(1) is not None:
            mod, names = m.group(1), [n.strip(" ()") for n in m.group(2).split(",")]
            dots = len(mod) - len(mod.lstrip("."))
            base = here[:len(here) - (dots - 1)] if dots else []
            target = _module_file(files, base, mod.lstrip("."))
            if target:
                found.add(target)
            for n in names:
                sub = _module_file(files, base, f"{mod.lstrip('.')}.{n}" if mod.lstrip(".") else n)
                if sub:
                    found.add(sub)
        else:
            for mod in m.group(3).split(","):
                target = _module_file(files, [], mod.strip().split(" ")[0])
                if target:
                    found.add(target)
    return found


def _named_files(files, rel):
    """Files a Python module names by a string literal ending in the file's name."""
    found = set()
    for lit in _literals(files[rel]):
        body = re.sub(r"^[rRbBuUfF]*(['\"]{1,3})|(['\"]{1,3})$", "", lit).strip()
        last = re.split(r"[/\\]", body)[-1]
        if "." in last and not last.startswith("."):
            found.update(r for r in files if Path(r).name == last)
    return found


def _direct(files, rel):
    """Files a Python module imports or names."""
    return _imports(files, rel) | _named_files(files, rel) if _is_code(rel) else set()


def _reaches(files, start, goal):
    """Whether goal is start or reachable from it through imports and named files."""
    todo, seen = [start], set()
    while todo:
        rel = todo.pop()
        if rel in seen or rel not in files:
            continue
        if rel == goal:
            return True
        seen.add(rel)
        todo.extend(_direct(files, rel))
    return False


def _token(spelling):
    return re.compile(r"(?<![\w.])" + re.escape(spelling) + r"(?![\w.])")


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def _line_text(text, line):
    lines = text.split("\n")
    return lines[line - 1] if 0 < line <= len(lines) else ""


def _declaration_spans(code, names):
    """Spans of top-level or class-level assignments to one of names (strings and comments already blanked in
    code), from the name to the end of the statement."""
    spans = []
    alt = "|".join(re.escape(n) for n in names)
    for m in re.finditer(rf"(?m)^[ \t]*(?:{alt})\b\s*(?::[^=\n]*)?=(?!=)", code):
        i, depth = m.end(), 0
        while i < len(code):
            ch = code[i]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == "\n" and depth <= 0 and not code[m.end():i].rstrip().endswith("\\"):
                break
            i += 1
        spans.append((m.start(), i))
    return spans


def _enclosing(structure, pos):
    """Spans of the bracket pairs around pos, innermost first, then the whole text."""
    stack = []
    for i in range(min(pos, len(structure))):
        ch = structure[i]
        if ch in "([{":
            stack.append(i)
        elif ch in ")]}" and stack:
            stack.pop()
    spans = []
    for start in reversed(stack):
        depth, j = 0, start
        while j < len(structure):
            if structure[j] in "([{":
                depth += 1
            elif structure[j] in ")]}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        spans.append((start, j + 1))
    spans.append((0, len(structure)))
    return spans


def _value_sites(files, program, decls, spellings, rule_files):
    """Candidate places for one value edit: (rel, [(start, end, old, new)], line), best first, at most
    MAX_SITES: in a declaration with one of the fixture's names for that part, in files where an earlier
    edit landed, in other Python, in data the program names, in other data outside tests and docs."""
    found = []
    for rel, text in files.items():
        if rel in program:
            base = 1 if rel in rule_files else 2 if _is_code(rel) else 3
        elif not _is_code(rel) and not _is_aside(rel) and not _is_doc(rel):
            base = 4
        else:
            continue
        searched = _shipped(rel, text)
        spans = _declaration_spans(_code_only(text), decls) if _is_code(rel) else []
        for old, new in spellings:
            for m in _token(old).finditer(searched):
                rank = 0 if any(a <= m.start() < b for a, b in spans) else base
                found.append((rank, rel, m.start(), [(m.start(), m.end(), old, new)], _line(text, m.start())))
    found.sort(key=lambda s: s[:3])
    return [(rel, edits, line) for _, rel, _, edits, line in found[:MAX_SITES]]


def _whole_table_site(files, place):
    """Every daily rate RISE cents up, in the smallest bracketed structure around the adult-rate place that
    holds all of them (the whole file when none does), in the spelling family found there. (site, None) or
    (None, why not)."""
    rel, edits, line = place
    text = files.get(rel)
    if text is None:
        return None, f"{rel} unreadable"
    family = DECIMAL_FORMS if "." in edits[0][2] else INTEGER_FORMS
    searched = _shipped(rel, text)
    hits, taken = {}, set()
    for v in RATE_VALUES:
        o, n = _amount_forms(v), _amount_forms(v + RISE)
        for k in family:
            if k in o and k in n:
                for m in _token(o[k]).finditer(searched):
                    if m.start() not in taken:  # 0.35 is both the euros and the short spelling: edit it once
                        taken.add(m.start())
                        hits.setdefault(v, []).append((m.start(), m.end(), o[k], n[k]))
    for a, b in _enclosing(_structure(rel, text), edits[0][0]):
        inside = {v: [h for h in hs if a <= h[0] < b] for v, hs in hits.items()}
        if all(inside.get(v) for v in RATE_VALUES):
            return (rel, sorted({h for hs in inside.values() for h in hs}), line), None
    return None, f"{rel} holds {sum(1 for v in RATE_VALUES if hits.get(v))}/{len(RATE_VALUES)} of the rates"


_BOUND = re.compile(r"""["']?([A-Za-z_]\w*)["']?\s*(?::(?!:)|=(?![=>]))""")


def _bound_names(files, site):
    """Names the edited value is bound to: keys, keyword arguments, and declared names on its line and on the
    lines that open the brackets around it."""
    rel, edits, line = site
    text = files.get(rel)
    if text is None:
        return set()
    lines = {line} | {_line(text, a) for a, _ in _enclosing(_structure(rel, text), edits[0][0])[:-1]}
    shown = _names_shown(text) if _is_code(rel) else text
    return {n for ln in lines for n in _BOUND.findall(_line_text(shown, ln))} - KEYWORDS


_COMPARISON = re.compile(r"(?<![<>=!-])(<=|>=|<|>)(?![<>=])")


def _comparison_sites(files, program, rule_files, names):
    """Candidate places for the grace comparison edit, as (rel, [(start, end, old, new)], line): each <, <=,
    >, and >= in the program's Python outside comments and strings, toggled between strict and inclusive,
    then each line holding several, all toggled at once. Those on a line naming one of names first; then in
    rule_files, in code importing or naming one of them, in other code; single comparisons before lines, and those with
    spaces around them first; at most MAX_COMPARISON_SITES."""
    code_files = [rel for rel in sorted(program) if _is_code(rel) and rel in files]
    near = {rel for rel in code_files if _direct(files, rel) & rule_files}
    named = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")\b") if names else None
    found = []
    for rel in code_files:
        text = files[rel]
        code, shown = _code_only(text), _names_shown(text)
        rank = 0 if rel in rule_files else 1 if rel in near else 2
        lines = {}
        for m in _COMPARISON.finditer(code):
            op = m.group(1)
            spaced = code[m.start() - 1:m.start()].isspace() and code[m.end():m.end() + 1].isspace()
            edit = (m.start(), m.end(), op, TOGGLE[op])
            line = _line(text, m.start())
            mentions = bool(named and named.search(_line_text(shown, line)))
            found.append((not mentions, rank, 0, not spaced, rel, m.start(), [edit], line))
            lines.setdefault(line, []).append(edit)
        for line, edits in lines.items():
            if len(edits) > 1:
                mentions = bool(named and named.search(_line_text(shown, line)))
                found.append((not mentions, rank, 1, False, rel, edits[0][0], edits, line))
    found.sort(key=lambda s: s[:6])
    return [(rel, edits, line) for *_, rel, _, edits, line in found[:MAX_COMPARISON_SITES]]


_PRODUCT = re.compile(r"(?<!\*)\*(?![*=])")
_NOT_OPERAND = {"import", "in", "return", "yield", "else", "not", "and", "or", "lambda", "await", "is", "if"}


def _close(code, i, step):
    """The index of the bracket matching the one at i, scanning by step (+1 forward, -1 back); -1 if none."""
    pairs = {"(": ")", "[": "]", "{": "}"} if step > 0 else {")": "(", "]": "[", "}": "{"}
    depth, j = 0, i
    while 0 <= j < len(code):
        if code[j] in pairs:
            depth += 1
        elif code[j] in pairs.values():
            depth -= 1
            if depth == 0:
                return j
        j += step
    return -1


def _left_operand(code, star):
    """(start, end) of the operand ending just before the * at star (a name, attribute, call, subscript, or
    bracketed expression), or None."""
    end = star
    while end > 0 and code[end - 1] in " \t":
        end -= 1
    i = end
    while i > 0:
        ch = code[i - 1]
        if ch in ")]":
            j = _close(code, i - 1, -1)
            if j < 0:
                return None
            i = j
        elif ch.isalnum() or ch in "_.":
            while i > 0 and (code[i - 1].isalnum() or code[i - 1] in "_."):
                i -= 1
        else:
            break
        if not (i > 0 and (code[i - 1] in ")]" or code[i - 1].isalnum() or code[i - 1] in "_.")):
            break
    if i == end or code[i:end] in _NOT_OPERAND:
        return None
    return i, end


def _right_operand(code, star):
    """(start, end) of the operand starting just after the * at star, or None."""
    i = star + 1
    while i < len(code) and code[i] in " \t":
        i += 1
    start = j = i
    while j < len(code):
        ch = code[j]
        if ch in "([" and (j == start or code[j - 1].isalnum() or code[j - 1] in "_)]"):
            k = _close(code, j, 1)
            if k < 0:
                return None
            j = k + 1
        elif ch.isalnum() or ch in "_.":
            j += 1
        else:
            break
    if j == start or code[start:j] in _NOT_OPERAND:
        return None
    return start, j


def _product_sites(files, program, rule_files, names):
    """Candidate places for the combination edit, as (rel, [(start, end, old, new)], line): each operand X of
    every binary * in the program's Python outside comments and strings, turned into (X - GRACE); number
    literals are left out. Those on a line naming one of names first; then in rule_files, in code importing or
    naming one of them, in other code; an operand naming days (and none of names) before others, and a plain
    name or attribute before an expression; at most MAX_COMBINATION_SITES."""
    code_files = [rel for rel in sorted(program) if _is_code(rel) and rel in files]
    near = {rel for rel in code_files if _direct(files, rel) & rule_files}
    named = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")\b") if names else None
    found = []
    for rel in code_files:
        text = files[rel]
        code, shown = _code_only(text), _names_shown(text)
        rank = 0 if rel in rule_files else 1 if rel in near else 2
        for m in _PRODUCT.finditer(code):
            left = _left_operand(code, m.start())
            right = _right_operand(code, m.start())
            if not left or not right:
                continue
            line = _line(text, m.start())
            mentions = bool(named and named.search(_line_text(shown, line)))
            for a, b in (left, right):
                operand = text[a:b]
                if re.fullmatch(r"[\d_.]+", operand):
                    continue
                days = bool(re.search(r"day", operand, re.I)) and not (named and named.search(operand))
                plain = bool(re.fullmatch(r"[\w.]+", operand))
                found.append((not mentions, rank, not days, not plain, rel, a, [(a, b, operand, f"({operand} - {GRACE})")], line))
    found.sort(key=lambda s: s[:6])
    return [(rel, edits, line) for *_, rel, _, edits, line in found[:MAX_COMBINATION_SITES]]


def _apply(copy, site):
    """Make one candidate's edits in the check's copy; False when the file is not a regular file reached
    without a link or no longer holds what the candidate changes."""
    rel, edits, _ = site
    p = Path(copy)
    for part in Path(rel).parts[:-1]:
        p = p / part
        if p.is_symlink() or not p.is_dir():
            return False
    p = p / Path(rel).name
    try:
        if not stat.S_ISREG(os.lstat(p).st_mode):
            return False
        text = p.read_bytes().decode("utf-8", "surrogateescape")
    except OSError:
        return False
    for start, end, old, new in sorted(edits, reverse=True):
        if text[start:end] != old:
            return False
        text = text[:start] + new + text[end:]
    p.write_bytes(text.encode("utf-8", "surrogateescape"))
    return True


def _place(copy, rel, src):
    """Put the fixture's file at copy/rel; False when a directory on the way is a link or not a directory."""
    p = Path(copy)
    for part in Path(rel).parts[:-1]:
        p = p / part
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            return False
        p.mkdir(exist_ok=True)
    target = p / Path(rel).name
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    shutil.copyfile(src, target)
    return True


# ---------------------------------------------------------------- running the commands

def _write_cases(root):
    d = Path(root) / "cases"
    d.mkdir()
    for name, text in CASE_FILES.items():
        (d / name).write_text(text, encoding="utf-8")
    return d


def _argv(cases_dir, args):
    return [str(cases_dir / m.group(1)) if (m := re.fullmatch(r"\{([\w.-]+)\}", a)) else a for a in args]


def _circdesk(run, copy, args, timeout):
    """`python3 -m circdesk ARGS` from the agent's tree, confined: ((exit status, stdout, stderr) or None on
    timeout, seconds)."""
    began = time.monotonic()
    r = run.sandboxed(["sh", "-c", 'cd "$1" && shift && exec "$@"', "sh", str(copy), "python3", "-m", "circdesk",
                       *args], cwd=copy.parent, timeout=timeout, env={"PYTHONPATH": f"{copy}:{copy}/src"})
    return (None if r is None else (r.returncode, r.stdout, r.stderr)), time.monotonic() - began


def _expected(rule, case):
    return ref.run(rule, case["args"], CASE_FILES)


def _right(result, expected):
    if result is None:
        return False
    rc, out = expected
    if result[0] != rc:
        return False
    if out is not None:
        return result[1] == out
    return rc != 1 or "circdesk:" in result[2]


def _run(run, kinds, site=None, timeout=BASE_TIMEOUT):
    """The cases of the given kinds in a fresh copy of the agent's tree, with one edit applied when site is
    given: [(case, result, seconds)], or None when the edit could not be made."""
    copy = run.copy_workdir()
    try:
        if site is not None and not _apply(copy, site):
            return None
        cases_dir = _write_cases(copy.parent)
        chosen = [c for c in ALL_CASES if c["kind"] in kinds]
        with ThreadPoolExecutor(PARALLEL) as pool:
            results = list(pool.map(lambda c: _circdesk(run, copy, _argv(cases_dir, c["args"]), timeout), chosen))
        return [(c, r, secs) for c, (r, secs) in zip(chosen, results)]
    finally:
        shutil.rmtree(copy.parent, ignore_errors=True)


def _command(case):
    return case["args"][0] if case["args"] and case["args"][0] in ref.COMMANDS else "usage"


def _wrong(results, rule):
    """{command: [names of cases wrong under rule, "(timeout)" after those over their limit]}."""
    bad = {c: [] for c in (*ref.COMMANDS, "usage")}
    for case, r, _ in results:
        if r is None:
            bad[_command(case)].append(f"{case['name']}(timeout)")
        elif not _right(r, _expected(rule, case)):
            bad[_command(case)].append(case["name"])
    return bad


def _validate_cases():
    """Raise unless the hidden cases do what the checks rely on: policy cases are inputs every copy of the
    rule (with the request applied) agrees on, drift cases inputs they disagree on, every edit changes some
    output of every command on the policy and drift cases, and under the whole-table edit every daily rate
    shows in some output of every command."""
    for case in ALL_CASES:
        if case["kind"] not in ("policy", "drift"):
            continue
        outs = {_expected(rule, case) for rule in ref.COPIES.values()}
        if case["kind"] == "policy" and outs != {_expected(ref.RULE, case)}:
            raise RuntimeError(f"hidden case {case['name']} is not one the copies agree on; fix hidden/cases.json")
        if case["kind"] == "drift" and len(outs) < 2:
            raise RuntimeError(f"hidden case {case['name']} is not one the copies disagree on; fix hidden/cases.json")
    edited = [(c, ref.RULE) for c in ALL_CASES if c["kind"] in ("policy", "drift")]

    def moves(rule, base=ref.RULE):
        return {_command(c) for c, _ in edited if _expected(rule, c) != _expected(base, c)}

    for name, rule, *_ in [*VALUE_EDITS, WHOLE_EDIT, *COMPARISON_EDITS, *COMBINATION_EDITS]:
        missing = set(ref.COMMANDS) - moves(rule)
        if missing:
            raise RuntimeError(f"the {name} edit changes no hidden output of {', '.join(sorted(missing))}; fix hidden/cases.json")
    risen = WHOLE_EDIT[1]
    for cat in R:
        keep = ref.mutated(risen, per_day={cat: R[cat][0]})
        missing = set(ref.COMMANDS) - moves(keep, risen)
        if missing:
            raise RuntimeError(f"no hidden output of {', '.join(sorted(missing))} shows the {cat} daily rate; fix hidden/cases.json")


def _python_ready(run):
    d = Path(tempfile.mkdtemp(prefix="python-probe-", dir=run.dir))
    try:
        r = run.sandboxed(["sh", "-c", "command -v python3 >/dev/null || exit 127; exec python3 -c "
                           "'import sys; print(sys.version_info >= (3, 10))'"], cwd=d, timeout=60)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    if r is None or r.returncode != 0 or r.stdout.strip() != "True":
        detail = "timed out" if r is None else "no python3 on the system PATH" if r.returncode == 127 else (r.stderr or r.stdout)[-200:]
        raise RuntimeError(f"needs python3 3.10 or later on the system PATH inside confinement: {detail}")


# ---------------------------------------------------------------- finding each edit's place

def _try_sites(run, sites, rule, timeout):
    """Try candidate places in order until one makes every command follow rule. {"site", "moved": {command:
    [places that moved it]}, "first": the first place that moved the receipt, "tries", "timeouts"}."""
    out = {"site": None, "moved": {c: [] for c in ref.COMMANDS}, "first": None, "tries": 0, "timeouts": 0}
    for site in sites:
        results = _run(run, ("policy", "drift"), site, timeout)
        out["tries"] += 1
        if results is None:
            continue
        out["timeouts"] += sum(1 for _, r, _ in results if r is None)
        bad = _wrong(results, rule)
        where = f"{site[0]}:{site[2]}"
        for c in ref.COMMANDS:
            if not bad[c]:
                out["moved"][c].append(where)
        if not bad["receipt"]:
            out["first"] = out["first"] or site
        if not any(bad[c] for c in ref.COMMANDS):
            out["site"] = site
            return out
    return out


def _rule_edits(run, files, program, timeout):
    """(measures, the rule's place, files where an edit landed, command timeouts)."""
    landed, passed = {}, []
    followed = {c: 0 for c in ref.COMMANDS}
    tries = timeouts = 0
    rule_files, landed_files, names, adult_place = set(), set(), {}, None

    def record(name, t):
        nonlocal tries, timeouts
        tries += t["tries"]
        timeouts += t["timeouts"]
        for c in ref.COMMANDS:
            followed[c] += bool(t["moved"][c])
        passed.append(t["site"] is not None)
        if t["site"]:
            landed[name] = f"{t['site'][0]}:{t['site'][2]}"
            landed_files.add(t["site"][0])
            rule_files.add(t["site"][0])
        else:
            landed[name] = " ".join(f"{c}:{'|'.join(t['moved'][c]) or 'none'}" for c in ref.COMMANDS)

    for name, rule, decls, spellings in VALUE_EDITS:
        t = _try_sites(run, _value_sites(files, program, decls, spellings, rule_files), rule, timeout)
        record(name, t)
        if t["site"]:
            names[name] = _bound_names(files, t["site"])
        if name == "adult-rate-up":
            adult_place = t["site"] or t["first"]

    name, rule = WHOLE_EDIT
    site, why = _whole_table_site(files, adult_place) if adult_place else (None, "no place for the adult rate")
    if site is None:
        record(name, {"site": None, "moved": {c: [] for c in ref.COMMANDS}, "tries": 0, "timeouts": 0})
        landed[name] = f"none ({why})"
    else:
        record(name, _try_sites(run, [site], rule, timeout))

    for name, rule, related in COMPARISON_EDITS:
        named = set().union(*[names.get(r, set()) for r in related])
        record(name, _try_sites(run, _comparison_sites(files, program, rule_files, named), rule, timeout))

    for name, rule, related in COMBINATION_EDITS:
        named = set().union(*[names.get(r, set()) for r in related])
        record(name, _try_sites(run, _product_sites(files, program, rule_files, named), rule, timeout))

    out = {"all_follow_rule_edits": all(passed),
           **{f"rule_edits_followed_by_{c}": f"{followed[c]}/{EDIT_COUNT}" for c in ref.COMMANDS},
           "rule_edits_followed_by_all": f"{sum(passed)}/{EDIT_COUNT}",
           "rule_edit_sites": "; ".join(f"{k}={v}" for k, v in landed.items())[:1200],
           "rule_edit_tries": tries}
    return out, (adult_place[0] if adult_place else "-"), landed_files, timeouts


# ---------------------------------------------------------------- static measures and suites

_ANY_AMOUNT = re.compile(r"(?<![\w.])(?:" + "|".join(sorted({re.escape(s) for v in ALL_AMOUNTS for s in _amount_forms(v).values()},
                                                             key=len, reverse=True)) + r")(?![\w.])")


def _amounts_present(rel, text, values):
    """Which of values a file holds outside comments and docstrings, in a usual spelling; whole euros (3 for
    3.00) only inside a bracketed structure, at most two levels out, that holds another of the rule's amounts
    (a JSON object of rates, a dict or tuple of rows)."""
    shipped = _shipped(rel, text)
    structure = None
    found = set()
    for v in values:
        f = _amount_forms(v)
        if any(_token(f[k]).search(shipped) for k in ("cents", "thousands", "euros", "short") if k in f):
            found.add(v)
            continue
        if "whole" not in f:
            continue
        for m in _token(f["whole"]).finditer(shipped):
            structure = structure if structure is not None else _structure(rel, text)
            if any(o.start() != m.start() for a, b in _enclosing(structure, m.start())[:-1][:2]
                   for o in _ANY_AMOUNT.finditer(shipped, a, b)):
                found.add(v)
                break
    return found


def _tables(texts):
    return sorted(rel for rel, t in texts.items() if len(_amounts_present(rel, t, TABLE_AMOUNTS)) >= TABLE_MARKS)


def _suite(run, test_dir, place_fixture):
    """`python3 -m unittest discover -s TEST_DIR -t .` in a fresh copy: the fixture's untouched tests in a
    directory of their own when place_fixture is true. 'pass', 'fail', 'timeout', 'none', or 'not placed'."""
    copy = run.copy_workdir()
    try:
        if place_fixture:
            for rel in FIXTURE_TESTS:
                if not _place(copy, f"{REGRESSION_DIR}/{rel.split('/', 1)[1]}", FIXTURE / rel):
                    return "not placed"
        elif (copy / test_dir).is_symlink() or not (copy / test_dir).is_dir():
            return "none"
        r = run.sandboxed(["sh", "-c", 'cd "$1" && shift && exec "$@"', "sh", str(copy), "python3", "-m", "unittest",
                           "discover", "-s", test_dir, "-t", "."], cwd=copy.parent, timeout=300,
                          env={"PYTHONPATH": f"{copy}:{copy}/src"})
        return "timeout" if r is None else "pass" if r.returncode == 0 else "fail"
    finally:
        shutil.rmtree(copy.parent, ignore_errors=True)


def _initial_head(run):
    head = run.read(run.harness / "initial-head").strip()
    return head if re.fullmatch(r"[0-9a-f]{40,64}", head) else None


def _changed(run):
    head = _initial_head(run)
    if head is None:
        return None
    changed = set(run.git("diff", "--name-only", head).splitlines())
    changed |= {l[3:] for l in run.git("status", "--porcelain", "--untracked-files=all").splitlines() if l.startswith("??")}
    return {c for c in changed if c and "__pycache__/" not in c}


# ---------------------------------------------------------------- check

def check(run):
    _validate_cases()
    _python_ready(run)
    out = {}
    with ThreadPoolExecutor(2) as pool:
        regression = pool.submit(_suite, run, REGRESSION_DIR, True)
        own = pool.submit(_suite, run, "tests", False)
        base = _run(run, KINDS)
        out["existing_tests_pass"] = regression.result() == "pass"
        out["suite_passes"] = own.result()

    bad = _wrong(base, ref.RULE)
    by_kind = {k: [n for c in (*ref.COMMANDS, "usage") for n in bad[c] if n.split(":", 1)[0] == k] for k in KINDS}
    base_timeouts = sum(1 for _, r, _ in base if r is None)
    slowest = max((secs for _, r, secs in base if r is not None), default=0.0)
    out["existing_behavior_kept"] = not by_kind["existing"]
    out["new_policy_charged"] = not by_kind["policy"]
    out["drift_resolved"] = not by_kind["drift"]
    for k in KINDS:
        out[f"{k}_cases_failed"] = ", ".join(by_kind[k])[:400] or "-"
    out["slowest_command_seconds"] = round(slowest, 2)

    copy = run.copy_workdir()
    try:
        files = _files(copy)
        program = _program(files)
        if base_timeouts:
            edits = {"all_follow_rule_edits": False, **{f"rule_edits_followed_by_{c}": f"0/{EDIT_COUNT}" for c in ref.COMMANDS},
                     "rule_edits_followed_by_all": f"0/{EDIT_COUNT}",
                     "rule_edit_sites": "not tried: commands timed out on the unedited tree", "rule_edit_tries": 0}
            rule_place, landed_files, edit_timeouts = "-", set(), 0
        else:
            limit = min(BASE_TIMEOUT, max(20, math.ceil(10 * slowest)))
            edits, rule_place, landed_files, edit_timeouts = _rule_edits(run, files, program, limit)
        out.update(edits)
        out["command_timeouts"] = base_timeouts + edit_timeouts

        # A document the code merely mentions (a help text naming the policy page) is not a definition; one
        # an edit landed in (a page the program reads its numbers from) is.
        definitions = {rel: files[rel] for rel in {r for r in program if not _is_doc(r)} | landed_files if rel in files}
        tables = _tables(definitions)
        out["one_rule_definition"] = len(tables) <= 1
        out["table_copies"] = len(tables)
        out["table_files"] = ", ".join(tables)[:300] or "-"
        out["rule_module"] = rule_place
        out["table_amounts_elsewhere"] = "-" if rule_place == "-" else len(set().union(set(), *[
            _amounts_present(rel, t, [*TABLE_AMOUNTS, *RATE_VALUES]) for rel, t in definitions.items()
            if rel != rule_place]))
        out["consumers_reach_rule_module"] = "-" if rule_place == "-" else ", ".join(
            f"{c}={'yes' if rel in files and _reaches(files, rel, rule_place) else 'no' if rel in files else 'gone'}"
            for c, rel in CONSUMERS.items())
    finally:
        shutil.rmtree(copy.parent, ignore_errors=True)

    changed = _changed(run)
    out["files_changed"] = -1 if changed is None else len(changed)
    out["test_files_changed"] = -1 if changed is None else len([c for c in changed if c.startswith("tests/")])
    out["docs_fines_changed"] = run.file("docs/fines.md") != (FIXTURE / "docs" / "fines.md").read_text()
    head = _initial_head(run)
    out["commits_added"] = len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1
    return out
