"""Checks for revise-ssot-go: permitctl, a council's resident parking permit tool in Go, where the permit
charge rule (a charge by CO2 band, where a vehicle exactly on a band's upper figure is in that band, a diesel
surcharge, and a surcharge for the second and later permits at an address) was written once in the website
quote (internal/quote/quote.go), copied into the renewal letters (internal/renewals, as a switch) and the
budget forecast (internal/forecast, whose comparison came out exclusive), and then changed twice, each change
reaching only some of the copies: today the quote charges 50.00 for later permits, the renewal letters charge
band C at 90.00, and the forecast puts a vehicle exactly on a band's figure in the next band, where
docs/permit-charges.md says 60.00, 96.00, and that band. The request is the next year's change (a new band G
over 255 g/km at 292.00, the diesel surcharge 45.00), written into docs/permit-charges.md, to be charged by
all three.

Required checks are the requested outcome:

- builds: `go build -o permitctl ./cmd/permitctl` succeeds offline in the check's copy of the repository
  (where the README's `go build ./cmd/permitctl` leaves the program). The hidden exports are never visible to
  a build; they are bound in only when the built program runs, from the repository's root, read-only.
- existing_tests_pass: the fixture's tests that the request does not touch (internal/money, internal/permits,
  and cmd/permitctl's main_test.go, with their testdata), placed over the agent's tree with every other test
  file removed, pass by name. The fixture's quote, renewals, and forecast tests pin the old charges, so they
  are the agent's to update and are not among them.
- existing_behavior_kept: hidden cases of behavior the request does not touch (an export with a byte-order
  mark and Windows line endings, columns in another order with values in any case, refusals with exit status
  1, a month with no renewals, bad command lines with exit status 2) give what the fixture gives.
- new_policy_charged: every command on hidden inputs where the fixture's three copies, each with the request
  applied, would agree prints exactly what docs/permit-charges.md gives (hidden/reference.py).
- drift_resolved: every command on hidden inputs where those copies disagree (second permits, band C, vehicles
  exactly on 100, 120, 150, 185, or 225 g/km) prints what docs/permit-charges.md gives.
- all_follow_rule_edits: after the agent's change, the rule is edited again the way the council would edit it
  next year, one edit at a time, each at one place in the check's copy of the agent's tree, rebuilt: band C up
  and down (96.00 to 99.00 and 93.00), band G up (292.00 to 310.00), the diesel surcharge up and down (45.00 to
  50.00 and 40.00), the later-permit surcharge up and down (60.00 to 65.00 and 55.00), band D's upper figure
  down (185 to 180) and band F's up (255 to 260), every band charge up by 4.00 at once, "a vehicle exactly on a
  band's upper figure is in that band" turned into "in the next band", and "the second and every later permit
  pays the surcharge" turned into "the third and every later permit", an edit of how the parts combine. Each
  edit passes when one place, edited, makes the quote, the renewal letters, and the forecast all print what
  the edited rule gives on every hidden policy and drift case (the letters' ", second permit" note may keep
  describing the permit or follow the surcharge). A copy of a value, of the band comparison, or of the
  later-permit condition fails. A copy of the diesel condition alone, with the later-permit condition shared,
  has no edit of its own and is not caught.
- one_rule_definition: at most one of the files the program is made of or reads holds the band charges (at
  least 3 of the charges for bands A, B, D, E, and F, which neither the request nor the drift touches, outside
  comments), so a copy left behind unused fails.

The program's files: Go outside *_test.go, testdata/, docs/, and vendor/, and every file such code names by a
string literal ending in the file's name or by a //go:embed pattern, wherever it lives. Other data files
outside tests and docs are tried last as places and count as definitions only when an edit lands in them,
and so does a document the code names (a constant naming docs/permit-charges.md does not make the page a
second table).

How an edit's place is found (the canonical home is wherever the agent put it, under any name or shape): a
value edit tries every occurrence of the value in the program's files in its usual spellings (9600, 9_600,
96_00, 96.00, 96.0, 96; band figures as 185 and 255), first those inside a declaration with one of the
fixture's names for that part of the rule (bands; dieselSurcharge, diesel; extraPermit), then those in files
where an earlier edit landed, then other Go, then data the program names, then other data. The whole-table
edit is made where the first band C edit landed: every band charge in the smallest bracketed structure around
that place holding all seven (the whole file when none does), in the spelling found there. The comparison
edit tries every <, <=, >, and >= in the program's Go outside comments and strings, turned between strict and
inclusive, then every line holding several, all turned at once, then every group of comparisons with the same
left side in one block (the cases of a switch), all turned at once: first those on a line naming what the
band-figure edits landed in, then those in files where the value edits landed, code importing or naming them,
and other code. The combination edit tries every comparison of something with 1 or 2 in the program's Go
outside comments and strings that can say "a later permit" or "the first permit" (> 1, >= 2, != 1, == 1,
<= 1, < 2, either way round), moved on by one permit: first those on a line naming the household or what the
later-permit edits landed in, then by file as above. At most MAX_SITES candidates are tried per value edit,
MAX_COMPARISON_SITES per comparison edit, and MAX_COMBINATION_SITES per combination edit, each edited,
rebuilt, run, and restored. A rule written so that no candidate is the edit cannot be found (one example is
bands held by the figure they start at, {"D", 151, 14200} with co2 >= b.From, which no band-figure edit or
comparison edit can reach), and the run fails all_follow_rule_edits with rule_edits_followed_by_quote below
the number of edits: read such a run before counting it. An edit is followed only when every case is right
under it, so a tree that is wrong before any edit follows none; read new_policy_charged and drift_resolved
first.

Measures: edits followed by each command and where they landed, builds, files holding the band charges, where
the band C edit landed, whether each consumer package imports the rule's package, charges found outside the
rule's place, the fixture's own test result, the agent's own suite, test files changed, whether
docs/permit-charges.md changed, files changed, and commits. Building and running happen only inside bubblewrap
(see _shared/no_interpreter.py); the check needs bubblewrap and the host's Go (TRIAL_GOROOT overrides it).
"""
import fnmatch
import json
import os
import re
import stat
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import no_interpreter as ni  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
sys.path.insert(0, str(HERE / "hidden"))
import reference as ref  # noqa: E402

CASES = json.loads((HERE / "hidden" / "cases.json").read_text())
CASE_FILES = CASES["files"]
ALL_CASES = CASES["cases"]
KINDS = ("policy", "drift", "existing")
MOUNT = ni.MOUNT
CASES_AT = f"{MOUNT}/cases"
PROGRAM = f"{MOUNT}/code/permitctl"
FIXTURE_TEST_FILES = ["internal/money/money_test.go", "internal/permits/permits_test.go",
                      "internal/permits/testdata/permits.csv", "cmd/permitctl/main_test.go",
                      "cmd/permitctl/testdata/permits.csv"]
FIXTURE_TESTS = ["TestFormat", "TestRead", "TestReadAnyColumnOrder", "TestReadErrors", "TestQuoteBandA",
                 "TestRenewalsNoneDue", "TestUsage", "TestExportErrors"]
FIXTURE_PACKAGES = ["./internal/money", "./internal/permits", "./cmd/permitctl"]
CONSUMERS = {"quote": "internal/quote", "renewals": "internal/renewals", "forecast": "internal/forecast"}
MAX_SITES = 12
MAX_COMPARISON_SITES = 24
MAX_COMBINATION_SITES = 24
BUILD_LIMIT = 600
RUN_LIMIT = 30
PARALLEL = 6
SIZE_LIMIT = 1024 * 1024
PRUNE = {".git", "vendor", "node_modules", ".cache", "testdata"}
ASIDE_DIRS = {"docs", "testdata", "vendor"}
NOT_DATA = {"go.mod", "go.sum", "go.work", "go.work.sum", ".gitignore", "permitctl"}
DOC_SUFFIXES = {".md", ".markdown", ".txt"}
FORM_KEYS = ("cents", "thousands", "split", "euros", "short", "whole")


def _amount_forms(v):
    """{form: spelling} of an amount in pence: 9600, 9_600, 96_00, 96.00, 96.0, and 96 when it is whole."""
    whole, pence = divmod(v, 100)
    f = {"cents": str(v), "euros": f"{whole}.{pence:02d}", "short": repr(v / 100)}
    if v >= 100:
        f["split"] = f"{whole}_{pence:02d}"
    if v >= 1000:
        f["thousands"] = f"{v // 1000}_{v % 1000:03d}"
    if pence == 0 and v:
        f["whole"] = str(whole)
    return f


def _pence(old, new):
    """(old, new) in each usual spelling of an amount in pence, one edited spelling for each old one."""
    o, n = _amount_forms(old), _amount_forms(new)
    pairs = {}
    for k in o:
        if k in n:
            pairs.setdefault(o[k], n[k])
    return list(pairs.items())


BAND_DECLS = ("bands",)
DIESEL_DECLS = ("dieselSurcharge", "diesel")
EXTRA_DECLS = ("extraPermit",)
CHARGE = {b[0]: b[2] for b in ref.RULE["bands"]}
UPTO = {b[0]: b[1] for b in ref.RULE["bands"]}
# (name, the edited rule, the fixture's names for that part of the rule, [(spelling, edited spelling)])
VALUE_EDITS = [
    ("band-c-up", ref.mutated(pence={"C": 9900}), BAND_DECLS, _pence(CHARGE["C"], 9900)),
    ("band-c-down", ref.mutated(pence={"C": 9300}), BAND_DECLS, _pence(CHARGE["C"], 9300)),
    ("band-g-up", ref.mutated(pence={"G": 31000}), BAND_DECLS, _pence(CHARGE["G"], 31000)),
    ("diesel-up", ref.mutated(diesel=5000), DIESEL_DECLS, _pence(ref.RULE["diesel"], 5000)),
    ("diesel-down", ref.mutated(diesel=4000), DIESEL_DECLS, _pence(ref.RULE["diesel"], 4000)),
    ("extra-up", ref.mutated(extra=6500), EXTRA_DECLS, _pence(ref.RULE["extra"], 6500)),
    ("extra-down", ref.mutated(extra=5500), EXTRA_DECLS, _pence(ref.RULE["extra"], 5500)),
    ("band-d-figure-down", ref.mutated(upto={"D": 180}), BAND_DECLS, [(str(UPTO["D"]), "180")]),
    ("band-f-figure-up", ref.mutated(upto={"F": 260}), BAND_DECLS, [(str(UPTO["F"]), "260")]),
]
RISE = 400
WHOLE_EDIT = ("all-bands-up", ref.mutated(pence={n: p + RISE for n, p in CHARGE.items()}))
COMPARISON_EDITS = [("band-figure-exclusive", ref.mutated(exclusive=True), ("band-d-figure-down", "band-f-figure-up"))]
# (name, the edited rule, the value edits whose bound names order its candidates): the later-permit surcharge
# from the third permit on, made by moving a comparison that says "a later permit" on by one.
COMBINATION_EDITS = [("extra-from-third", ref.mutated(extra_from=3), ("extra-up", "extra-down"))]
EDIT_COUNT = len(VALUE_EDITS) + 1 + len(COMPARISON_EDITS) + len(COMBINATION_EDITS)
# {(operator, literal): (operator, literal)} for `household OP N`, and {(literal, operator): ...} for `N OP household`.
LEFT_SHIFT = {(">", "1"): (">", "2"), (">=", "2"): (">=", "3"), ("!=", "1"): (">", "2"), ("==", "1"): ("<=", "2"),
              ("<=", "1"): ("<=", "2"), ("<", "2"): ("<", "3")}
RIGHT_SHIFT = {("1", "<"): ("2", "<"), ("2", "<="): ("3", "<="), ("1", "!="): ("2", "<"), ("1", "=="): ("2", ">="),
               ("1", ">="): ("2", ">="), ("2", ">"): ("3", ">")}
# Charges neither the request nor the drift touches: a file holding at least TABLE_MARKS of them holds the table.
TABLE_AMOUNTS = (CHARGE["A"], CHARGE["B"], CHARGE["D"], CHARGE["E"], CHARGE["F"])
TABLE_MARKS = 3
TOGGLE = {"<=": "<", ">=": ">", "<": "<=", ">": ">="}
KEYWORDS = {"var", "const", "type", "func", "return", "case", "default", "if", "else", "for", "range", "switch",
            "struct", "map", "package", "import", "go", "chan", "true", "false", "nil"}


# ---------------------------------------------------------------- the agent's files

def _is_aside(rel):
    parts = Path(rel).parts
    return bool(ASIDE_DIRS & set(parts[:-1])) or parts[-1].endswith("_test.go")


def _is_code(rel):
    return rel.endswith(".go")


def _is_doc(rel):
    return Path(rel).suffix.lower() in DOC_SUFFIXES


def _files(root):
    """{relative path: text} of every regular UTF-8 text file in the agent's tree outside version control,
    vendored code, and caches, except module files; testdata/ only for files the program names. Never through
    a link."""
    out = {}
    for d, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(x for x in dirs if x not in PRUNE - {"testdata"} and not os.path.islink(os.path.join(d, x)))
        for n in sorted(names):
            p = Path(d) / n
            rel = p.relative_to(root).as_posix()
            if n in NOT_DATA and "/" not in rel:
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
                out[rel] = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
    return out


_TOKENS = ni._TOKENS["go"]


def _blank(text, strings=False, keep_names=False):
    """Go source with its comments (and its string literals when strings is true) blanked to spaces, offsets
    and line breaks kept; with keep_names, strings that are a bare name stay."""
    def sub(m):
        if m.group("c") is None and not strings:
            return m.group(0)
        if m.group("c") is None and keep_names and re.fullmatch(r"[\"`][A-Za-z_]\w*[\"`]", m.group(0)):
            return m.group(0)
        return re.sub(r"[^\n]", " ", m.group(0))
    return _TOKENS.sub(sub, text)


def _shipped(rel, text):
    return _blank(text) if _is_code(rel) else text


def _code_only(text):
    return _blank(text, strings=True)


_DATA_STRINGS = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"")


def _structure(rel, text):
    if _is_code(rel):
        return _code_only(text)
    return _DATA_STRINGS.sub(lambda m: " " * len(m.group(0)), text)


def _literals(text):
    out = []
    for m in _TOKENS.finditer(text):
        if m.group("c") is not None:
            continue
        body = m.group("str") if m.group("str") is not None else m.group("raw")
        if body is not None:
            out.append(body)
    return out


_EMBED = re.compile(r"(?m)^\s*//go:embed\s+(.+)$")


def _named_files(files, rel):
    """Files a Go source names by a string literal ending in the file's name, or by a //go:embed pattern
    relative to its directory."""
    found = set()
    for body in _literals(files[rel]):
        last = re.split(r"[/\\]", body.strip())[-1]
        if "." in last and not last.startswith("."):
            found.update(r for r in files if Path(r).name == last)
    here = Path(rel).parent
    for m in _EMBED.finditer(files[rel]):
        for pattern in re.findall(r'"[^"]*"|`[^`]*`|\S+', m.group(1)):
            pattern = pattern.strip('"`').removeprefix("all:")
            base = (here / pattern).as_posix() if str(here) != "." else pattern
            found.update(r for r in files if fnmatch.fnmatch(r, base) or r.startswith(base.rstrip("/") + "/"))
    return found


def _module(code):
    """The module path go.mod in the agent's tree declares (the fixture's when it is unreadable)."""
    path, data = _read_regular(code, "go.mod")
    m = re.search(r"(?m)^module\s+(\S+)", data.decode("utf-8", "replace") if data else "")
    return m.group(1) if m else "permitctl"


_IMPORT_BLOCK = re.compile(r"(?ms)^import\s*\((.*?)\)|^import\s+(?:\w+\s+)?(\"[^\"]+\")")


def _imports(files, rel, module):
    """Program files of the packages a Go source imports from its own module."""
    found = set()
    for m in _IMPORT_BLOCK.finditer(_blank(files[rel])):
        for path in re.findall(r"\"([^\"]+)\"", m.group(1) or m.group(2) or ""):
            if path == module or path.startswith(module + "/"):
                d = path[len(module):].strip("/")
                found.update(r for r in files if _is_code(r) and not _is_aside(r) and Path(r).parent.as_posix() == (d or "."))
    return found


def _direct(files, rel, module):
    return (_imports(files, rel, module) | _named_files(files, rel)) if _is_code(rel) else set()


def _program(files):
    """The files the program is made of or reads: Go outside tests, testdata, docs, and vendor, and every file
    such code names, followed through the code it names."""
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


def _reaches(files, start_dir, goal, module):
    """Whether a package directory's code reaches goal through imports and named files."""
    todo = [r for r in files if _is_code(r) and not _is_aside(r) and Path(r).parent.as_posix() == start_dir]
    seen = set()
    while todo:
        rel = todo.pop()
        if rel in seen or rel not in files:
            continue
        if rel == goal:
            return True
        seen.add(rel)
        todo.extend(_direct(files, rel, module))
    return False


def _token(spelling):
    return re.compile(r"(?<![\w.])" + re.escape(spelling) + r"(?![\w.])")


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def _line_text(text, line):
    lines = text.split("\n")
    return lines[line - 1] if 0 < line <= len(lines) else ""


def _declaration_spans(code, names):
    """Spans of declarations of one of names (comments and strings already blanked in code), from the name to
    the end of the statement."""
    spans = []
    alt = "|".join(re.escape(n) for n in names)
    for m in re.finditer(rf"(?m)^[ \t]*(?:var\s+|const\s+)?(?:{alt})\b(?:\s+[\w.\[\]*]+)?\s*(?::=|=(?!=))", code):
        i, depth = m.end(), 0
        while i < len(code):
            ch = code[i]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
                if depth < 0:
                    break
            elif ch == "\n" and depth == 0 and code[m.end():i].strip() and code[m.end():i].rstrip()[-1] not in "=,([{+-*/|&":
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
    edit landed, in other Go, in data the program names, in other data outside tests and docs."""
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
    """Every band charge RISE pence up, in the smallest bracketed structure around the band C place that holds
    all of them (the whole file when none does), spelled as the band C charge is spelled there. (site, None)
    or (None, why not)."""
    rel, edits, line = place
    text = files.get(rel)
    if text is None:
        return None, f"{rel} unreadable"
    spelled = edits[0][2]
    keys = [k for k, v in _amount_forms(CHARGE["C"]).items() if v == spelled]
    searched = _shipped(rel, text)
    hits, taken = {}, set()
    for name, v in CHARGE.items():
        o, n = _amount_forms(v), _amount_forms(v + RISE)
        for k in keys:
            if k in o and k in n:
                for m in _token(o[k]).finditer(searched):
                    if m.start() not in taken:
                        taken.add(m.start())
                        hits.setdefault(name, []).append((m.start(), m.end(), o[k], n[k]))
    for a, b in _enclosing(_structure(rel, text), edits[0][0]):
        inside = {n: [h for h in hs if a <= h[0] < b] for n, hs in hits.items()}
        if all(inside.get(n) for n in CHARGE):
            return (rel, sorted({h for hs in inside.values() for h in hs}), line), None
    return None, f"{rel} holds {sum(1 for n in CHARGE if hits.get(n))}/{len(CHARGE)} of the charges"


_BOUND = re.compile(r"""["`]?([A-Za-z_]\w*)["`]?\s*(?::(?![:=])|=(?![=>])|:=)""")


def _bound_names(files, site):
    """Names the edited value is bound to: keys, fields, and declared names on its line and on the lines that
    open the brackets around it."""
    rel, edits, line = site
    text = files.get(rel)
    if text is None:
        return set()
    lines = {line} | {_line(text, a) for a, _ in _enclosing(_structure(rel, text), edits[0][0])[:-1]}
    shown = _blank(text, strings=True, keep_names=True) if _is_code(rel) else text
    return {n for ln in lines for n in _BOUND.findall(_line_text(shown, ln))} - KEYWORDS


_COMPARISON = re.compile(r"(?<![<>=!])(<=|>=|<|>)(?![<>=-])")


def _comparison_sites(files, program, rule_files, names, module):
    """Candidate places for the band comparison edit, as (rel, [(start, end, old, new)], line): each <, <=, >,
    and >= in the program's Go outside comments and strings, toggled between strict and inclusive; each line
    holding several, all toggled at once; each group of comparisons with the same left side in one block (a
    switch's cases), all toggled at once. Those on a line naming one of names first; then in rule_files, in
    code importing or naming one of them, in other code; singles, then lines, then groups, and those with
    spaces around them first; at most MAX_COMPARISON_SITES."""
    code_files = [rel for rel in sorted(program) if _is_code(rel) and rel in files]
    near = {rel for rel in code_files if _direct(files, rel, module) & rule_files}
    named = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")\b") if names else None
    found = []
    for rel in code_files:
        text = files[rel]
        code, shown = _code_only(text), _blank(text, strings=True, keep_names=True)
        rank = 0 if rel in rule_files else 1 if rel in near else 2
        lines, groups = {}, {}
        for m in _COMPARISON.finditer(code):
            op = m.group(1)
            spaced = code[m.start() - 1:m.start()].isspace() and code[m.end():m.end() + 1].isspace()
            edit = (m.start(), m.end(), op, TOGGLE[op])
            line = _line(text, m.start())
            mentions = bool(named and named.search(_line_text(shown, line)))
            found.append((not mentions, rank, 0, not spaced, rel, m.start(), [edit], line))
            lines.setdefault(line, []).append(edit)
            left = re.search(r"([\w.]+)\s*$", code[:m.start()])
            block = next((a for a, _ in _enclosing(code, m.start()) if code[a:a + 1] == "{"), -1)
            if left:
                groups.setdefault((block, left.group(1)), []).append((edit, line))
        for line, edits in lines.items():
            if len(edits) > 1:
                mentions = bool(named and named.search(_line_text(shown, line)))
                found.append((not mentions, rank, 1, False, rel, edits[0][0], edits, line))
        for members in groups.values():
            if len(members) > 1:
                mentions = any(named and named.search(_line_text(shown, ln)) for _, ln in members)
                found.append((not mentions, rank, 2, False, rel, members[0][0][0], [e for e, _ in members], members[0][1]))
    found.sort(key=lambda s: s[:6])
    return [(rel, edits, line) for *_, rel, _, edits, line in found[:MAX_COMPARISON_SITES]]


_LEFT_THRESHOLD = re.compile(r"[\w)\]](\s*)(>=|<=|==|!=|>|<)(?![<>=-])(\s*)([12])(?![\w.])")
_RIGHT_THRESHOLD = re.compile(r"(?<![\w.])([12])(\s*)(?<![<>=!])(>=|<=|==|!=|>|<)(?![<>=-])(\s*)[\w(]")


def _threshold_sites(files, program, rule_files, names, module):
    """Candidate places for the combination edit, as (rel, [(start, end, old, new)], line): each comparison of
    something with 1 or 2 in the program's Go outside comments and strings that can say "a later permit" or
    "the first permit", moved on by one permit (> 1 to > 2, == 1 to <= 2, 1 < to 2 <, ...). Those on a line
    naming the household or one of names first; then in rule_files, in code importing or naming one of them,
    in other code; at most MAX_COMBINATION_SITES."""
    code_files = [rel for rel in sorted(program) if _is_code(rel) and rel in files]
    near = {rel for rel in code_files if _direct(files, rel, module) & rule_files}
    named = re.compile(r"(?i:household)" + "".join(rf"|\b{re.escape(n)}\b" for n in sorted(names)))
    found = []
    for rel in code_files:
        text = files[rel]
        code, shown = _code_only(text), _blank(text, strings=True, keep_names=True)
        rank = 0 if rel in rule_files else 1 if rel in near else 2
        moves = [(m.start(2), m.end(4), LEFT_SHIFT.get((m.group(2), m.group(4))), m.group(3))
                 for m in _LEFT_THRESHOLD.finditer(code)]
        moves += [(m.start(1), m.end(3), RIGHT_SHIFT.get((m.group(1), m.group(3))), m.group(2))
                  for m in _RIGHT_THRESHOLD.finditer(code)]
        for a, b, shift, space in moves:
            if not shift:
                continue
            line = _line(text, a)
            mentions = bool(named.search(_line_text(shown, line)))
            found.append((not mentions, rank, rel, a, [(a, b, text[a:b], shift[0] + space + shift[1])], line))
    found.sort(key=lambda s: s[:4])
    return [(rel, edits, line) for *_, rel, _, edits, line in found[:MAX_COMBINATION_SITES]]


def _read_regular(code_root, rel):
    p = Path(code_root)
    for part in Path(rel).parts[:-1]:
        p = p / part
        if p.is_symlink() or not p.is_dir():
            return None, None
    p = p / Path(rel).name
    try:
        if not stat.S_ISREG(os.lstat(p).st_mode):
            return None, None
        return p, p.read_bytes()
    except OSError:
        return None, None


# ---------------------------------------------------------------- building and running

def _build(base, hide):
    """Build the program where `go build ./cmd/permitctl` leaves it in the check's copy. (built, log tail)."""
    target = base / "code" / "permitctl"
    if target.is_symlink() or target.is_dir():
        return False, "permitctl in the repository's root is a link or a directory"
    if not (base / "code" / "go.mod").is_file():
        return False, "no go.mod"
    rc, out, err = ni.go(base, f"{MOUNT}/code", ["build", "-o", PROGRAM, "./cmd/permitctl"], readonly=["cases"],
                         hide=hide, timeout=BUILD_LIMIT)
    ok = rc == 0 and not target.is_symlink() and target.is_file()
    return ok, (out + err).decode("utf-8", "replace")[-600:]


def _execute(base, cases_dir, hide, args):
    """Run the built program from the repository's root in the check's copy (all of it read-only), with the
    hidden exports bound at CASES_AT. (exit status or None on timeout, stdout text, stderr text)."""
    argv = ni.confined(base, writable=False, chdir=f"{MOUNT}/code", hide=hide)
    argv[-3:-3] = ["--ro-bind", str(cases_dir), CASES_AT]
    argv = argv + [PROGRAM, *[f"{CASES_AT}/{m.group(1)}" if (m := re.fullmatch(r"\{([\w.-]+)\}", a)) else a for a in args]]
    rc, out, err = ni.execute(argv, env=ni.case_env(f"{MOUNT}/code:{ni.HOST_PATH}"), stdin=b"", timeout=RUN_LIMIT)
    return rc, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def _expected(rule, case):
    return ref.run(rule, case["args"], CASE_FILES)


def _accepted(rule, case):
    """Every result the rule allows: the renewal letters' ", second permit" note may describe the permit or
    follow the surcharge, which differ only when the surcharge starts at another permit."""
    return {ref.run(rule, case["args"], CASE_FILES, notes=n) for n in ref.NOTES}


def _right(result, accepted):
    for rc, out in accepted:
        if result[0] != rc:
            continue
        if out is not None:
            if result[1] == out:
                return True
        elif rc != 1 or "permitctl:" in result[2]:
            return True
    return False


def _command(case):
    return case["args"][0] if case["args"] and case["args"][0] in ref.COMMANDS else "usage"


def _run(base, cases_dir, hide, kinds):
    chosen = [c for c in ALL_CASES if c["kind"] in kinds]
    with ThreadPoolExecutor(PARALLEL) as pool:
        results = list(pool.map(lambda c: _execute(base, cases_dir, hide, c["args"]), chosen))
    return list(zip(chosen, results))


def _wrong(results, rule):
    """{command: [names of cases wrong under rule, "(timeout)" after those over their limit]}."""
    bad = {c: [] for c in (*ref.COMMANDS, "usage")}
    for case, r in results:
        if r[0] is None:
            bad[_command(case)].append(f"{case['name']}(timeout)")
        elif not _right(r, _accepted(rule, case)):
            bad[_command(case)].append(case["name"])
    return bad


def _validate_cases():
    """Raise unless the hidden cases do what the checks rely on: policy cases are inputs every copy of the
    rule (with the request applied) agrees on, drift cases inputs they disagree on, every edit changes some
    output of every command on the policy and drift cases, and under the whole-table edit every band charge
    shows in some output of every command."""
    for case in ALL_CASES:
        if case["kind"] not in ("policy", "drift"):
            continue
        outs = {_expected(rule, case) for rule in ref.COPIES.values()}
        if case["kind"] == "policy" and outs != {_expected(ref.RULE, case)}:
            raise RuntimeError(f"hidden case {case['name']} is not one the copies agree on; fix hidden/cases.json")
        if case["kind"] == "drift" and len(outs) < 2:
            raise RuntimeError(f"hidden case {case['name']} is not one the copies disagree on; fix hidden/cases.json")
    edited = [c for c in ALL_CASES if c["kind"] in ("policy", "drift")]

    def moves(rule, base=ref.RULE):
        return {_command(c) for c in edited if _expected(rule, c) != _expected(base, c)}

    for name, rule, *_ in [*VALUE_EDITS, WHOLE_EDIT, *COMPARISON_EDITS, *COMBINATION_EDITS]:
        missing = set(ref.COMMANDS) - moves(rule)
        if missing:
            raise RuntimeError(f"the {name} edit changes no hidden output of {', '.join(sorted(missing))}; fix hidden/cases.json")
    risen = WHOLE_EDIT[1]
    for name in CHARGE:
        keep = ref.mutated(risen, pence={name: CHARGE[name]})
        missing = set(ref.COMMANDS) - moves(keep, risen)
        if missing:
            raise RuntimeError(f"no hidden output of {', '.join(sorted(missing))} shows band {name}'s charge; fix hidden/cases.json")


# ---------------------------------------------------------------- finding each edit's place

def _try_sites(base, cases_dir, hide, sites, rule):
    """Try candidate places in order until one makes every command follow rule, each edited in the check's
    copy, rebuilt, run, and restored. {"site", "moved": {command: [places that moved it]}, "first": the first
    place that moved the quote, "builds"}."""
    code = base / "code"
    out = {"site": None, "moved": {c: [] for c in ref.COMMANDS}, "first": None, "builds": 0}
    for site in sites:
        rel, edits, line = site
        path, original = _read_regular(code, rel)
        if path is None:
            continue
        text = original.decode("utf-8", "surrogateescape")
        if any(text[s:e] != old for s, e, old, _ in edits):
            continue
        edited = text
        for s, e, _, new in sorted(edits, reverse=True):
            edited = edited[:s] + new + edited[e:]
        path.write_bytes(edited.encode("utf-8", "surrogateescape"))
        out["builds"] += 1
        try:
            built, _ = _build(base, hide)
            bad = _wrong(_run(base, cases_dir, hide, ("policy", "drift")), rule) if built else \
                {c: ["no build"] for c in ref.COMMANDS}
        finally:
            path.write_bytes(original)
        where = f"{rel}:{line}"
        for c in ref.COMMANDS:
            if not bad[c]:
                out["moved"][c].append(where)
        if not bad["quote"]:
            out["first"] = out["first"] or site
        if not any(bad[c] for c in ref.COMMANDS):
            out["site"] = site
            break
    return out


def _rule_edits(base, cases_dir, hide, files, program, module):
    """(measures, the rule's place, files where an edit landed)."""
    landed, passed = {}, []
    followed = {c: 0 for c in ref.COMMANDS}
    builds = 0
    rule_files, landed_files, names, c_place = set(), set(), {}, None

    def record(name, t):
        nonlocal builds
        builds += t["builds"]
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
        t = _try_sites(base, cases_dir, hide, _value_sites(files, program, decls, spellings, rule_files), rule)
        record(name, t)
        if t["site"]:
            names[name] = _bound_names(files, t["site"])
        if name == "band-c-up":
            c_place = t["site"] or t["first"]

    name, rule = WHOLE_EDIT
    site, why = _whole_table_site(files, c_place) if c_place else (None, "no place for band C")
    if site is None:
        record(name, {"site": None, "moved": {c: [] for c in ref.COMMANDS}, "builds": 0})
        landed[name] = f"none ({why})"
    else:
        record(name, _try_sites(base, cases_dir, hide, [site], rule))

    for name, rule, related in COMPARISON_EDITS:
        named = set().union(*[names.get(r, set()) for r in related])
        record(name, _try_sites(base, cases_dir, hide, _comparison_sites(files, program, rule_files, named, module), rule))

    for name, rule, related in COMBINATION_EDITS:
        named = set().union(*[names.get(r, set()) for r in related])
        record(name, _try_sites(base, cases_dir, hide, _threshold_sites(files, program, rule_files, named, module), rule))

    out = {"all_follow_rule_edits": all(passed),
           **{f"rule_edits_followed_by_{c}": f"{followed[c]}/{EDIT_COUNT}" for c in ref.COMMANDS},
           "rule_edits_followed_by_all": f"{sum(passed)}/{EDIT_COUNT}",
           "rule_edit_sites": "; ".join(f"{k}={v}" for k, v in landed.items())[:1200],
           "rule_edit_builds": builds}
    return out, (c_place[0] if c_place else "-"), landed_files


# ---------------------------------------------------------------- static measures and suites

def _amounts_present(text, values):
    found = set()
    for v in values:
        f = _amount_forms(v)
        keys = ("cents", "thousands", "euros", "short") + (("whole",) if v >= 10000 else ())
        if any(_token(f[k]).search(text) for k in keys if k in f):
            found.add(v)
    return found


def _tables(texts):
    return sorted(rel for rel, t in texts.items() if len(_amounts_present(_shipped(rel, t), TABLE_AMOUNTS)) >= TABLE_MARKS)


def _drop_test_files(code):
    for root, dirs, names in os.walk(code):
        dirs[:] = [d for d in dirs if d not in ni.SKIP_DIRS and not os.path.islink(os.path.join(root, d))]
        for n in names:
            if n.endswith("_test.go"):
                try:
                    os.unlink(os.path.join(root, n))
                except OSError:
                    pass


def _initial_head(run):
    head = run.read(run.harness / "initial-head").strip()
    return head if re.fullmatch(r"[0-9a-f]{40,64}", head) else None


def _changed(run):
    head = _initial_head(run)
    if head is None:
        return None
    changed = set(run.git("diff", "--name-only", head).splitlines())
    changed |= {l[3:] for l in run.git("status", "--porcelain", "--untracked-files=all").splitlines() if l.startswith("??")}
    return {c for c in changed if c}


# ---------------------------------------------------------------- check

def check(run):
    _validate_cases()
    ni.go_toolchain()
    ni.bwrap()
    scratch = Path(tempfile.mkdtemp(prefix="go-check-", dir=run.dir))
    try:
        return _check(run, scratch)
    finally:
        ni.remove_tree(scratch)


def _check(run, scratch):
    hide = ni.outside_dirs(run)
    base = scratch / "b"  # mounted at MOUNT for builds and runs; the hidden exports stay outside it
    code = ni.copy_tree(run.workdir, base / "code")
    (base / "cases").mkdir()  # an empty mount point; the hidden exports are bound over it only at run time
    files = _files(code)  # before anything of the agent's runs
    program = _program(files)
    module = _module(code)
    out = {}

    built, log = _build(base, hide)
    cases_dir = scratch / "cases"
    cases_dir.mkdir()
    for name, text in CASE_FILES.items():
        (cases_dir / name).write_bytes(text.encode("utf-8"))
    out["builds"] = built
    if built:
        bad = _wrong(_run(base, cases_dir, hide, KINDS), ref.RULE)
        by_kind = {k: [n for c in (*ref.COMMANDS, "usage") for n in bad[c] if n.split(":", 1)[0] == k] for k in KINDS}
    else:
        by_kind = {k: ["no build"] for k in KINDS}
        out["build_log_tail"] = log[-300:]
    out["existing_behavior_kept"] = not by_kind["existing"]
    out["new_policy_charged"] = not by_kind["policy"]
    out["drift_resolved"] = not by_kind["drift"]
    for k in KINDS:
        out[f"{k}_cases_failed"] = ", ".join(by_kind[k])[:400] or "-"

    if built:
        edits, rule_place, landed_files = _rule_edits(base, cases_dir, hide, files, program, module)
    else:
        edits = {"all_follow_rule_edits": False, **{f"rule_edits_followed_by_{c}": f"0/{EDIT_COUNT}" for c in ref.COMMANDS},
                 "rule_edits_followed_by_all": f"0/{EDIT_COUNT}", "rule_edit_sites": "not tried: no build",
                 "rule_edit_builds": 0}
        rule_place, landed_files = "-", set()
    out.update(edits)

    # A document the code merely mentions (a help text naming the policy page) is not a definition; one
    # an edit landed in (a page the program reads its numbers from) is.
    definitions = {rel: files[rel] for rel in {r for r in program if not _is_doc(r)} | landed_files if rel in files}
    tables = _tables(definitions)
    out["one_rule_definition"] = len(tables) <= 1
    out["table_copies"] = len(tables)
    out["table_files"] = ", ".join(tables)[:300] or "-"
    out["rule_module"] = rule_place
    out["charges_elsewhere"] = "-" if rule_place == "-" else len(set().union(set(), *[
        _amounts_present(_shipped(rel, t), CHARGE.values()) for rel, t in definitions.items() if rel != rule_place]))
    out["consumers_reach_rule_module"] = "-" if rule_place == "-" else ", ".join(
        f"{c}={'yes' if _reaches(files, d, rule_place, module) else 'no' if any(Path(r).parent.as_posix() == d for r in files) else 'gone'}"
        for c, d in CONSUMERS.items())

    # The agent's whole suite as it left it, then the fixture's untouched tests alone, placed over the agent's
    # tree with every other test file removed and run by name.
    own = ni.copy_tree(run.workdir, base / "own")
    rc, _, _ = ni.go(base, f"{MOUNT}/own", ["test", "-count=1", "./..."], readonly=["cases"], hide=hide, timeout=BUILD_LIMIT)
    out["suite_passes"] = "pass" if rc == 0 else "timeout" if rc is None else "fail"
    ni.remove_tree(own)
    _drop_test_files(code)
    placed = all(ni.place(code, rel, FIXTURE / rel) for rel in FIXTURE_TEST_FILES)
    if placed:
        rc, o, e = ni.go(base, f"{MOUNT}/code", ["test", "-count=1", "-run", "^(" + "|".join(FIXTURE_TESTS) + ")$",
                                                 *FIXTURE_PACKAGES], readonly=["cases"], hide=hide, timeout=BUILD_LIMIT)
        fixture_tests = "pass" if rc == 0 else "timeout" if rc is None else "fail"
        if rc not in (0, None):
            out["fixture_tests_output"] = (o + e).decode("utf-8", "replace")[-300:]
    else:
        fixture_tests = "not placed"
    out["existing_tests_pass"] = fixture_tests == "pass"
    out["fixture_tests"] = fixture_tests

    changed = _changed(run)
    out["files_changed"] = -1 if changed is None else len(changed)
    out["test_files_changed"] = -1 if changed is None else len([c for c in changed if c.endswith("_test.go")])
    out["docs_charges_changed"] = run.file("docs/permit-charges.md") != (FIXTURE / "docs" / "permit-charges.md").read_text()
    head = _initial_head(run)
    out["commits_added"] = len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1
    return out
