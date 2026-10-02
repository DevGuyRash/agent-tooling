"""Checks for ssot-rules-ts: a `feed` command for leafline-orders whose shipping column must be what checkout
charges, in a codebase where the shipping rule (packaging weight, free-shipping threshold, EU zone list, the
DHL rate table, and how they combine) is defined once, privately, in src/checkout.ts and used only by
quoteOrder.

Required checks are the requested outcome:

- existing_tests_pass: the fixture's own test files, placed over whatever the agent left in test/, pass with
  `node --test` in the agent's tree.
- quote_unchanged: `shop quote CATALOG ORDER --json` on hidden orders and on the repository's example
  orders gives what the fixture's rule gives (goods, parcel grams, shipping, total, lines), and refuses what
  it refuses (exit status 1, `shop:`).
- feed_correct: `shop feed CATALOG [--countries ...]` on a hidden catalog and on the repository's catalog
  (the example in docs/feed.md) prints exactly what docs/feed.md specifies (reference.py), and its usage and
  catalog errors exit 2 and 1.
- both_follow_rule_edits: the shipping rule is edited the way the shop would edit it, one edit at a time,
  and both commands run again on the hidden inputs and on the repository's own examples. Every value is
  edited both up and down (one EU rate, the free-shipping threshold, the packaging weight), Sweden is swapped
  for Norway in the EU list, every rate in the table goes up by a euro at once (DHL's yearly price rise), and
  how the rule compares is edited twice (goods exactly at the threshold no longer ship free; a parcel exactly
  at a band's limit goes in the next band). Each edit must have one place in the agent's tree where making
  it makes quote AND feed both give what the edited rule gives. A feed that carries its own copy of any part
  of the rule fails: of its values, any cell of the rate table included (the edit that moves quote leaves the
  copy behind, and the edit to the copy leaves quote behind), of its logic over shared values (the comparison
  edits), or a one-sided shortcut (whichever direction the shortcut is not on the safe side of), and so does
  a feed that answers the repository's own catalog from a table.
- one_rule_definition: the rate table appears in at most one of the files the program is made of or reads
  (comments left out). A move that leaves the old definition behind, unused, follows every edit but leaves
  two places to edit next time; the rate table is the part with a fingerprint specific enough to decide on
  (at least 8 of its 15 amounts in one file). Leftover single values (threshold literals) and EU lists are
  measured, not decided. Files that hold the rule's results rather than the rule (a feed written out, a
  golden file a test compares with) are not the program's unless its code names them.

The program's files: its code outside tests and docs, and every file that code names, by an import, a path,
or a string literal ending in the file's name, wherever that file lives (docs/ included), followed through
the code it names. Other data files outside tests and docs are tried last as places, and count as
definitions only when an edit lands in them.

How an edit's place is found (the canonical definition is the fixture's; the agent may have moved, renamed,
exported, or re-shaped it). A value edit tries every occurrence of the value in the program's files, in the
value's usual spellings (1290, 1_290, 12_90, 12.90, or 12.9 for an amount in cents; 49 for whole euros; 0.18
for grams in kilograms; SE as a token with any delimiter, so a quoted list, a zone map's keys, or a
space-separated string all count). Candidates inside a declaration with the fixture's name (PARCEL_RATES,
FREE_SHIPPING_FROM, EU_COUNTRIES, PACKAGING_GRAMS) come first, then the rest of src/checkout.ts, then other
code, then data the program names, then other data. The whole-table edit is made where the EU-rate edit
landed: every amount of the table in the smallest bracketed structure around that place that holds all 15
(the whole file when none does), in the spelling family found there. A comparison edit tries every <, <=, >,
and >= in the program's code outside comments and strings, turning a strict comparison into an inclusive one
or the other way round, which moves the boundary whichever way round the comparison is written, and then
every line holding several comparisons with all of them turned at once (a range test written with both
bounds): first those on a line that names what the related value edits landed in (for the threshold
comparison, the name the threshold is declared under, such as FREE_SHIPPING_FROM; for the band comparison,
the keys and names around the edited rate, such as a band row's upTo), then the rest; within each, those in
the files where the value edits landed first, then code that imports or names those files, then
src/checkout.ts, then other code; single comparisons before lines, and those written with spaces around them
first. At most MAX_SITES value candidates and MAX_COMPARISON_SITES comparison candidates are tried per edit;
each try makes one candidate's change in a fresh copy of the agent's tree and runs both commands; the first
that makes both follow is the edit's place. So a rule moved into a new module or a data file is followed by
behavior, not by name. A rule written so that none of the candidates is the edit (rates computed from
something else, a band lookup with no comparison) cannot be found, and the run fails both_follow_rule_edits
with rule_edits_followed_by_quote below the number of edits: read such a run before counting it.

Nothing is timed except command limits: each command of the unedited run may take BASE_TIMEOUT seconds, and
each command of an edited run ten times the slowest command of the unedited run (at least 60 seconds, at
most BASE_TIMEOUT). A command over its limit is reported as a timeout (`name(timeout)`, command_timeouts), not
as a wrong answer; when the unedited run has one, the edits are not tried.

Measures: how many edits each command follows, where each edit landed, copies of the rate table and the EU
list, threshold literals, and rate amounts outside the rule's place in the program's files, which new module
carries the feed, whether the files it names (by import, path, or file name) reach the rule's place, whether
it names the rule's parts by the fixture's names, the agent's own test suite, files changed, and commits.
Agent code runs only through run.sandboxed (no network, host read-only, home hidden, own PID namespace) on
fresh copies from run.copy_workdir, so the working directory stays as the agent left it. The check needs a
node on the system PATH that runs .ts files directly (Node 23.6 or later, or 22.18 or later); without one
the run is invalid, not failed.
"""
import json
import math
import os
import re
import shutil
import stat
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
sys.path.insert(0, str(HERE / "hidden"))
import reference as ref  # noqa: E402

CASES = json.loads((HERE / "hidden" / "cases.json").read_text())
CATALOG = CASES["catalog"]
VISIBLE_CATALOG_FILE = FIXTURE / "data" / "catalog.json"
VISIBLE_CATALOG = json.loads(VISIBLE_CATALOG_FILE.read_text())
VISIBLE_ORDERS = [(p, json.loads(p.read_text())) for p in sorted((FIXTURE / "data" / "orders").glob("*.json"))]
ORIGINAL = "src/checkout.ts"
DEFAULT_COUNTRIES = ["DE", "AT", "CH"]
FIXTURE_TESTS = sorted(p.relative_to(FIXTURE).as_posix() for p in (FIXTURE / "test").glob("*.test.ts"))
MAX_SITES = 12
MAX_COMPARISON_SITES = 20
BASE_TIMEOUT = 300
PARALLEL = 4
SIZE_LIMIT = 1024 * 1024
CODE_SUFFIXES = {".ts", ".mts", ".cts", ".tsx", ".js", ".mjs", ".cjs", ".jsx"}
# Never the program's own files: version control, dependencies, caches.
PRUNE = {".git", "node_modules", "coverage", ".cache"}
# Tests and docs: part of the program only where its code names a file in them.
ASIDE = {"test", "tests", "__tests__", "docs"}
# Package manifests, lockfiles, and compiler settings: they describe the package, not data the program reads.
NOT_DATA = {"package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock",
            "bun.lockb", "deno.json", "deno.lock", "tsconfig.json", "jsconfig.json"}
DOC_SUFFIXES = {".md", ".markdown"}
QUOTE_KEYS = ("order", "country", "goods", "grams", "shipping", "total")
LINE_KEYS = ("sku", "title", "qty", "price", "amount")
INTEGER_FORMS = ("cents", "thousands", "split")
DECIMAL_FORMS = ("euros", "short", "whole")


def _amount_forms(v):
    """{form: spelling} of an amount in cents: 4900, 4_900, 49_00, 49.00, 49.0, and 49 when it is whole euros."""
    euros, cents = divmod(v, 100)
    f = {"cents": str(v), "split": f"{euros}_{cents:02d}", "euros": f"{euros}.{cents:02d}", "short": repr(v / 100)}
    if v >= 1000:
        f["thousands"] = f"{v // 1000}_{v % 1000:03d}"
    if cents == 0:
        f["whole"] = str(euros)
    return f


def _cents_spellings(old, new):
    """(old, new) in each usual spelling of an amount in cents."""
    o, n = _amount_forms(old), _amount_forms(new)
    return list(dict.fromkeys((o[k], n[k]) for k in o if k in n))


def _grams_spellings(old, new):
    """(old, new) in each usual spelling of a weight in grams: 180, and 0.18 or 0.180 in kilograms."""
    return [(str(old), str(new)), (repr(old / 1000), repr(new / 1000)), (f"{old / 1000:.3f}", f"{new / 1000:.3f}")]


# Edits of the rule's values, each both ways where it is a number: (name, the edited rule, the fixture's name
# for that part of the rule, [(spelling, edited spelling)]).
VALUE_EDITS = [
    ("eu-rate-up", ref.mutated(rates={(1, "EU"): 1340}), "PARCEL_RATES", _cents_spellings(1290, 1340)),
    ("eu-rate-down", ref.mutated(rates={(1, "EU"): 1240}), "PARCEL_RATES", _cents_spellings(1290, 1240)),
    ("free-from-down", ref.mutated(free_from=3900), "FREE_SHIPPING_FROM", _cents_spellings(4900, 3900)),
    ("free-from-up", ref.mutated(free_from=5900), "FREE_SHIPPING_FROM", _cents_spellings(4900, 5900)),
    ("zone", ref.mutated(eu_swap=("SE", "NO")), "EU_COUNTRIES", [("SE", "NO")]),
    ("packaging-up", ref.mutated(packaging=260), "PACKAGING_GRAMS", _grams_spellings(180, 260)),
    ("packaging-down", ref.mutated(packaging=120), "PACKAGING_GRAMS", _grams_spellings(180, 120)),
]
ZONE_NAMES = ("DE", "EU", "WORLD")
CELLS = [(row, zone) for row in range(len(ref.RULE["rates"])) for zone in ZONE_NAMES]
RATE_VALUES = [v for row in ref.RULE["rates"] for v in row[1:]]
# DHL's yearly price rise: every rate of the table up by a euro, made at the table's place all at once.
RISE = 100


def _risen(keep=None):
    """The rule with every rate RISE cents higher, except the cell keep."""
    return ref.mutated(rates={cell: ref.RULE["rates"][cell[0]][ref.ZONES[cell[1]]] + RISE for cell in CELLS if cell != keep})


WHOLE_EDIT = ("all-rates-up", _risen())
# Edits of how the rule compares: "from €49" becoming "over €49", and "up to 1 kg" becoming "under 1 kg".
# Each with the value edits whose places name what it compares: the threshold, and the rate table's rows.
COMPARISON_EDITS = [
    ("free-from-strict", ref.mutated(free_strict=True), ("free-from-down", "free-from-up")),
    ("band-limit-exclusive", ref.mutated(band_exclusive=True), ("eu-rate-up", "eu-rate-down")),
]
EDIT_COUNT = len(VALUE_EDITS) + 1 + len(COMPARISON_EDITS)
TOGGLE = {"<=": "<", ">=": ">", "<": "<=", ">": ">="}
RULE_INTERNALS = r"\b(?:PARCEL_RATES|EU_COUNTRIES|FREE_SHIPPING_FROM|PACKAGING_GRAMS|upTo)\b"
EU_CODES = ref.RULE["eu"]
KEYWORDS = {"const", "let", "var", "export", "type", "return", "case", "default", "readonly", "static", "true",
            "false", "null", "undefined", "new", "as", "satisfies", "in", "of", "if", "else"}


# ---------------------------------------------------------------- the agent's files

def _is_aside(rel):
    parts = Path(rel).parts
    return bool(ASIDE & set(parts[:-1])) or ".test." in parts[-1] or ".spec." in parts[-1]


def _is_code(rel):
    return Path(rel).suffix.lower() in CODE_SUFFIXES


def _files(root):
    """{relative path: text} of every regular text file (UTF-8, no NUL) in the agent's tree outside version
    control, dependencies, and caches, except package manifests, lockfiles, and Markdown; never through a
    link."""
    out = {}
    for d, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(x for x in dirs if x not in PRUNE and not os.path.islink(os.path.join(d, x)))
        for n in sorted(files):
            p = Path(d) / n
            if n in NOT_DATA or p.suffix.lower() in DOC_SUFFIXES:
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


_JS_TOKENS = re.compile(r"(?P<c>//[^\n]*|/\*.*?\*/)|\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`", re.S)
_DATA_STRINGS = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"")


def _blank(text, strings=False):
    """JavaScript or TypeScript source with its comments (and its string literals, when strings is true)
    blanked to spaces, offsets and line breaks kept."""
    def sub(m):
        return re.sub(r"[^\n]", " ", m.group(0)) if m.group("c") is not None or strings else m.group(0)
    return _JS_TOKENS.sub(sub, text)


def _names_shown(text):
    """JavaScript or TypeScript source with its comments and its strings blanked, except strings that are a
    bare name (a key such as "upTo" used as band["upTo"])."""
    def sub(m):
        body = m.group(0)[1:-1]
        keep = m.group("c") is None and re.fullmatch(r"[A-Za-z_$][\w$]*", body)
        return m.group(0) if keep else re.sub(r"[^\n]", " ", m.group(0))
    return _JS_TOKENS.sub(sub, text)


def _structure(rel, text):
    """The text with comments and strings blanked, for matching brackets: code as code, data with its
    double-quoted strings blanked."""
    if _is_code(rel):
        return _blank(text, strings=True)
    return _DATA_STRINGS.sub(lambda m: " " * len(m.group(0)), text)


def _literals(text):
    """The bodies of the string literals of a JavaScript or TypeScript source, outside comments."""
    return [m.group(0)[1:-1] for m in _JS_TOKENS.finditer(text) if m.group("c") is None]


def _named(root, files, start):
    """The files reachable from start through code that names them (by a relative import, a path literal, or
    a string literal ending in the file's name), start included, wherever they live."""
    by_name = {}
    for rel in files:
        by_name.setdefault(Path(rel).name, []).append(rel)
    todo, seen = list(start), set()
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        if not _is_code(rel) or rel not in files:
            continue
        text = files[rel]
        named = set(_direct(root, rel, _blank(text)))
        for body in _literals(text):
            last = re.split(r"[/\\]", body.strip())[-1]
            if "." in last:
                named.update(by_name.get(last, ()))
        todo.extend(n for n in named if n in files)
    return seen


def _program(root, files):
    """The files the shipped program is made of or reads: code outside tests and docs, and every file such
    code names, followed through the code it names, wherever it lives."""
    return _named(root, files, [rel for rel in files if _is_code(rel) and not _is_aside(rel)])


def _token(spelling):
    return re.compile(r"(?<![\w.])" + re.escape(spelling) + r"(?![\w.])")


def _declaration_spans(text, name):
    """Spans of declarations or properties named `name`, from the name to the end of the statement."""
    spans = []
    for m in re.finditer(rf"\b{name}\b\s*(?::[^=;\n]*)?[=:]", text):
        i, depth = m.end(), 0
        while i < len(text):
            ch = text[i]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
                if depth < 0:
                    break
            elif depth == 0 and ch == ";":
                break
            elif depth == 0 and ch == "\n" and text[m.end():i].strip() and text[m.end():i].rstrip()[-1] not in "=,([{+-*/?:|&":
                break
            i += 1
        spans.append((m.start(), i))
    return spans


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def _line_text(text, line):
    return text.split("\n")[line - 1] if 0 < line <= text.count("\n") + 1 else ""


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


def _value_sites(files, program, name, spellings):
    """Candidate places for one value edit: (rel, [(start, end, old, new)], line), best first, at most
    MAX_SITES. The program's files first (in declarations with the fixture's name, the rest of
    src/checkout.ts, other code, data it names), then other data outside tests and docs."""
    found = []
    for rel, text in files.items():
        if rel in program:
            base = 1 if rel == ORIGINAL else 2 if _is_code(rel) else 3
        elif not _is_code(rel) and not _is_aside(rel):
            base = 4
        else:
            continue
        spans = _declaration_spans(text, name) if rel in program else []
        for old, new in spellings:
            for m in _token(old).finditer(text):
                rank = 0 if any(a <= m.start() < b for a, b in spans) else base
                found.append((rank, rel, m.start(), [(m.start(), m.end(), old, new)], _line(text, m.start())))
    found.sort(key=lambda s: s[:3])
    return [(rel, edits, line) for _, rel, _, edits, line in found[:MAX_SITES]]


def _whole_table_site(files, place):
    """The whole-table edit at the place the EU-rate edit landed: every amount of the table, RISE cents up,
    in the smallest bracketed structure around that place holding all of them (the whole file when none
    does), in the spelling family found there. (site, None) or (None, why not)."""
    rel, edits, line = place
    text = files.get(rel)
    if text is None:
        return None, f"{rel} unreadable"
    family = DECIMAL_FORMS if "." in edits[0][2] else INTEGER_FORMS
    searched = _blank(text) if _is_code(rel) else text
    hits = {}
    for v in RATE_VALUES:
        o, n = _amount_forms(v), _amount_forms(v + RISE)
        for k in family:
            if k in o and k in n:
                for m in _token(o[k]).finditer(searched):
                    hits.setdefault(v, []).append((m.start(), m.end(), o[k], n[k]))
    for a, b in _enclosing(_structure(rel, text), edits[0][0]):
        inside = {v: [h for h in hs if a <= h[0] < b] for v, hs in hits.items()}
        if all(inside.get(v) for v in RATE_VALUES):
            return (rel, sorted({h for hs in inside.values() for h in hs}), line), None
    return None, f"{rel} holds {sum(1 for v in RATE_VALUES if hits.get(v))}/{len(RATE_VALUES)} of the rates"


_BOUND = re.compile(r"""["']?([A-Za-z_$][\w$]*)["']?\s*(?::(?!:)|=(?![=>]))""")


def _bound_names(files, site):
    """Names the value a site edits is bound to: keys and declared names on its line and on the lines that
    open the brackets around it (a table's row, the table, the declaration holding it)."""
    rel, edits, line = site
    text = files.get(rel)
    if text is None:
        return set()
    lines = {line} | {_line(text, a) for a, _ in _enclosing(_structure(rel, text), edits[0][0])[:-1]}
    shown = _blank(text) if _is_code(rel) else text
    return {n for ln in lines for n in _BOUND.findall(_line_text(shown, ln))} - KEYWORDS


_COMPARISON = re.compile(r"(?<![<>=!])(<=|>=|<|>)(?![<>=])")


def _comparison_sites(root, files, program, rule_files, names):
    """Candidate places for an edit of how the rule compares, as (rel, [(start, end, old, new)], line): each
    <, <=, >, and >= in the program's code outside comments and strings, toggled between strict and
    inclusive, and then each line holding several (a range test such as `g > b.over && g <= b.upTo` moves
    its boundary only when both turn), all toggled at once. Those on a line naming one of names first; then
    in rule_files, in code that imports or names one of them, src/checkout.ts, and other code; within each,
    single comparisons before lines, and those with spaces around them first; at most MAX_COMPARISON_SITES."""
    code_files = [rel for rel in sorted(program) if _is_code(rel) and rel in files]
    near = {rel for rel in code_files if _direct(root, rel, files[rel]) & rule_files}
    named = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")\b") if names else None
    found = []
    for rel in code_files:
        text = files[rel]
        code = _blank(text, strings=True)
        shown = _names_shown(text)
        rank = 0 if rel in rule_files else 1 if rel in near else 2 if rel == ORIGINAL else 3
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
    """Put the fixture's file at copy/rel, replacing what is there; False when a directory on the way is a
    link or not a directory."""
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
    (d / "orders").mkdir(parents=True)
    (d / "examples").mkdir()
    (d / "catalog.json").write_text(json.dumps(CATALOG, ensure_ascii=False))
    (d / "broken.json").write_text(CASES["broken_catalog"])
    for o in CASES["orders"]:
        (d / "orders" / f"{o['name']}.json").write_text(json.dumps(o["order"]))
    shutil.copyfile(VISIBLE_CATALOG_FILE, d / "examples" / "catalog.json")
    for p, _ in VISIBLE_ORDERS:
        shutil.copyfile(p, d / "examples" / p.name)
    return d


def _jobs(cases_dir, errors):
    """[(kind, name, argv, judge(result, rule) -> bool)]: quote and feed on the hidden inputs and on the
    repository's own examples (data/orders, and data/catalog.json with the default countries, the example in
    docs/feed.md), plus the usage and catalog errors when errors is true."""
    catalog = str(cases_dir / "catalog.json")
    examples = cases_dir / "examples"
    jobs = []
    for o in CASES["orders"]:
        jobs.append(("quote", o["name"], ["quote", catalog, str(cases_dir / "orders" / f"{o['name']}.json"), "--json"],
                     lambda r, rule, order=o["order"]: _quote_ok(r, _expected_quote(rule, CATALOG, order))))
    for p, order in VISIBLE_ORDERS:
        jobs.append(("quote", f"repo:{p.stem}", ["quote", str(examples / "catalog.json"), str(examples / p.name), "--json"],
                     lambda r, rule, order=order: _quote_ok(r, _expected_quote(rule, VISIBLE_CATALOG, order))))
    for f in CASES["feed"]:
        jobs.append(("feed", f["name"], ["feed", catalog] + (["--countries", ",".join(f["countries"])] if f["countries"] else []),
                     lambda r, rule, c=f["countries"]: _feed_ok(r, ref.feed(rule, CATALOG, c or DEFAULT_COUNTRIES))))
    jobs.append(("feed", "repo:doc-example", ["feed", str(examples / "catalog.json")],
                 lambda r, rule: _feed_ok(r, ref.feed(rule, VISIBLE_CATALOG, DEFAULT_COUNTRIES))))
    if errors:
        for u in CASES["usage"]:
            args = [a.replace("{catalog}", catalog).replace("{dir}", str(cases_dir)) for a in u["args"]]
            jobs.append(("usage", u["name"], args,
                         lambda r, rule, rc=u["rc"]: r is not None and r[0] == rc and "shop:" in r[2]))
    return jobs


def _shop(run, copy, args, timeout):
    """Run `node bin/shop.ts ARGS` from the agent's tree, confined; ((exit status, stdout, stderr) or None on
    timeout, seconds taken)."""
    began = time.monotonic()
    r = run.sandboxed(["sh", "-c", 'cd "$1" && shift && exec "$@"', "sh", str(copy), "node", "bin/shop.ts", *args],
                      cwd=copy.parent, timeout=timeout, env={"NO_COLOR": "1"})
    return (None if r is None else (r.returncode, r.stdout, r.stderr)), time.monotonic() - began


def _run(run, site=None, timeout=BASE_TIMEOUT):
    """Both commands on the hidden inputs and the repository's examples in a fresh copy of the agent's tree,
    with one edit applied when site is given (and then without the usage cases). [(kind, name, judge,
    result, seconds)], or None when the edit could not be made."""
    copy = run.copy_workdir()
    try:
        if site is not None and not _apply(copy, site):
            return None
        cases_dir = _write_cases(copy.parent)
        jobs = _jobs(cases_dir, errors=site is None)
        with ThreadPoolExecutor(PARALLEL) as pool:
            results = list(pool.map(lambda j: _shop(run, copy, j[2], timeout), jobs))
        return [(kind, name, judge, r, secs) for (kind, name, _, judge), (r, secs) in zip(jobs, results)]
    finally:
        shutil.rmtree(copy.parent, ignore_errors=True)


def _expected_quote(rule, catalog, order):
    try:
        return ref.quote(rule, catalog, order)
    except ref.Refused:
        return None


def _quote_ok(result, expected):
    if result is None:
        return False
    rc, out, err = result
    if expected is None:
        return rc == 1 and "shop:" in err
    if rc != 0:
        return False
    try:
        got = json.loads(out)
        lines = got["lines"]
        return (all(got.get(k) == expected[k] for k in QUOTE_KEYS) and len(lines) == len(expected["lines"])
                and all(g.get(k) == e[k] for g, e in zip(lines, expected["lines"]) for k in LINE_KEYS))
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def _feed_ok(result, expected):
    return result is not None and result[0] == 0 and result[1] == expected


def _verdicts(results, rule):
    """{kind: [names of cases of that kind wrong under rule, "(timeout)" after those over their limit]}."""
    bad = {"quote": [], "feed": [], "usage": []}
    for kind, name, judge, r, _ in results:
        if r is None:
            bad[kind].append(f"{name}(timeout)")
        elif not judge(r, rule):
            bad[kind].append(name)
    return bad


def _timeouts(results):
    return sum(1 for *_, r, _ in results if r is None)


def _discriminating():
    """Raise unless every edit changes some hidden quote and some hidden feed line, and unless every cell of
    the rate table shows in some hidden feed line under the whole-table edit: an edit (or a cell) the hidden
    inputs cannot tell from the fixture's rule would be followed by anything."""
    feeds = [f["countries"] or DEFAULT_COUNTRIES for f in CASES["feed"]]
    for name, rule in [(e[0], e[1]) for e in VALUE_EDITS] + [WHOLE_EDIT] + [(e[0], e[1]) for e in COMPARISON_EDITS]:
        quotes_move = any(_expected_quote(rule, CATALOG, o["order"]) != _expected_quote(ref.RULE, CATALOG, o["order"])
                          for o in CASES["orders"])
        feed_moves = any(ref.feed(rule, CATALOG, c) != ref.feed(ref.RULE, CATALOG, c) for c in feeds)
        if not (quotes_move and feed_moves):
            raise RuntimeError(f"the hidden cases no longer tell the {name} edit from the fixture's rule; fix hidden/cases.json")
    risen = [ref.feed(WHOLE_EDIT[1], CATALOG, c) for c in feeds]
    for cell in CELLS:
        if all(ref.feed(_risen(keep=cell), CATALOG, c) == r for c, r in zip(feeds, risen)):
            raise RuntimeError(f"no hidden feed line shows the rate for band {cell[0] + 1}, zone {cell[1]}; fix hidden/cases.json")


def _node_ready(run):
    """Raise (the run is then invalid, not failed) unless the confined node runs a .ts file directly."""
    d = Path(tempfile.mkdtemp(prefix="node-probe-", dir=run.dir))
    try:
        (d / "probe.ts").write_text("const n: number = 21;\nconsole.log(n * 2);\n")
        r = run.sandboxed(["sh", "-c", "command -v node >/dev/null || exit 127; exec node probe.ts"], cwd=d, timeout=60,
                          env={"NO_COLOR": "1"})
    finally:
        shutil.rmtree(d, ignore_errors=True)
    if r is None or r.returncode != 0 or r.stdout.strip() != "42":
        detail = "timed out" if r is None else "no node on the system PATH" if r.returncode == 127 else (r.stderr or r.stdout)[-200:]
        raise RuntimeError(f"needs a node on the system PATH that runs .ts files directly (Node 23.6+ or 22.18+): {detail}")


# ---------------------------------------------------------------- finding each edit's place

def _try_sites(run, sites, rule, timeout):
    """Try candidate places in order until one makes both commands follow rule. {"site": the place or None,
    "quote": places that moved quote, "feed": places that moved feed, "first_quote": the first site that
    moved quote, "tries", "timeouts"}."""
    out = {"site": None, "quote": [], "feed": [], "first_quote": None, "tries": 0, "timeouts": 0}
    for site in sites:
        results = _run(run, site, timeout)
        out["tries"] += 1
        if results is None:
            continue
        out["timeouts"] += _timeouts(results)
        bad = _verdicts(results, rule)
        where = f"{site[0]}:{site[2]}"
        if not bad["quote"]:
            out["quote"].append(where)
            out["first_quote"] = out["first_quote"] or site
        if not bad["feed"]:
            out["feed"].append(where)
        if not bad["quote"] and not bad["feed"]:
            out["site"] = site
            return out
    return out


def _rule_edits(run, root, files, program, timeout):
    """(measures, the rule's place, files where an edit landed, command timeouts)."""
    landed, passed = {}, []
    followed_quote = followed_feed = tried = timeouts = 0
    rule_files, landed_files, names, rule_place, eu_place = set(), set(), {}, "-", None

    def record(name, t):
        nonlocal followed_quote, followed_feed, tried, timeouts
        tried += t["tries"]
        timeouts += t["timeouts"]
        followed_quote += bool(t["quote"])
        followed_feed += bool(t["feed"])
        passed.append(t["site"] is not None)
        where = f"{t['site'][0]}:{t['site'][2]}" if t["site"] else None
        landed[name] = where or f"quote:{'|'.join(t['quote']) or 'none'} feed:{'|'.join(t['feed']) or 'none'}"
        if t["site"]:
            landed_files.add(t["site"][0])

    for name, rule, decl, spellings in VALUE_EDITS:
        t = _try_sites(run, _value_sites(files, program, decl, spellings), rule, timeout)
        record(name, t)
        rule_files |= {w.rsplit(":", 1)[0] for w in t["quote"]}
        if t["site"]:
            names[name] = _bound_names(files, t["site"])
        if name == "eu-rate-up":
            eu_place = t["site"] or t["first_quote"]
            rule_place = eu_place[0] if eu_place else "-"

    name, rule = WHOLE_EDIT
    site, why = _whole_table_site(files, eu_place) if eu_place else (None, "no place for the EU rate")
    if site is None:
        record(name, {"site": None, "quote": [], "feed": [], "tries": 0, "timeouts": 0})
        landed[name] = f"none ({why})"
    else:
        record(name, _try_sites(run, [site], rule, timeout))

    for name, rule, related in COMPARISON_EDITS:
        named = set().union(*[names.get(r, set()) for r in related]) or set().union(*names.values())
        record(name, _try_sites(run, _comparison_sites(root, files, program, rule_files, named), rule, timeout))

    out = {
        "both_follow_rule_edits": all(passed),
        "rule_edits_followed_by_quote": f"{followed_quote}/{EDIT_COUNT}",
        "rule_edits_followed_by_feed": f"{followed_feed}/{EDIT_COUNT}",
        "rule_edits_followed_by_both": f"{sum(passed)}/{EDIT_COUNT}",
        "rule_edit_sites": "; ".join(f"{k}={v}" for k, v in landed.items())[:1000],
        "rule_edit_tries": tried,
    }
    return out, rule_place, landed_files, timeouts


# ---------------------------------------------------------------- static measures

def _shipped_text(rel, text):
    """What of a file can define something: code with its comments blanked, data as it is."""
    return _blank(text) if _is_code(rel) else text


def _values_present(text, values):
    """The values of a list of amounts in cents that a text spells in cents, thousands, or euros."""
    found = set()
    for v in values:
        f = _amount_forms(v)
        if any(_token(f[k]).search(text) for k in ("cents", "thousands", "euros") if k in f):
            found.add(v)
    return found


def _copies(texts):
    shipped = {rel: _shipped_text(rel, t) for rel, t in texts.items()}
    tables = sorted(rel for rel, t in shipped.items() if len(_values_present(t, RATE_VALUES)) >= 8)
    zones = [rel for rel, t in shipped.items() if sum(1 for c in EU_CODES if _token(c).search(t)) >= 20]
    threshold = sum(len(_token(s).findall(t)) for t in shipped.values() for s in ("4900", "4_900", "49_00", "49.00"))
    return tables, zones, threshold


_IMPORT = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"'\n]+)["']""")
_PATHLIKE = re.compile(r"""["'`](\.{1,2}/[^"'`\n]+|(?:data|src|lib|config|docs)/[^"'`\n]+)["'`]""")


def _resolve(root, rel, spec):
    base = (Path(rel).parent / spec) if spec.startswith(".") else Path(spec)
    norm = Path(os.path.normpath(base.as_posix()))
    if norm.as_posix().startswith(".."):
        return None
    stem = norm.as_posix()
    tries = [stem, stem + ".ts", stem + ".js", stem + ".mts", stem + ".mjs", stem + "/index.ts", stem + "/index.js"]
    if stem.endswith(".js"):
        tries.insert(1, stem[:-3] + ".ts")
    for t in tries:
        p = Path(root) / t
        if p.is_file() and not p.is_symlink():
            return t
    return None


def _direct(root, rel, text):
    """Files a module imports or requires by a relative path, or names by a path literal."""
    specs = [m.group(1) for m in _IMPORT.finditer(text) if m.group(1).startswith(".")]
    specs += [m.group(1) for m in _PATHLIKE.finditer(text)]
    found = set()
    for spec in specs:
        for base in (rel, "x"):  # relative to the module, then to the repository root
            hit = _resolve(root, base, spec)
            if hit:
                found.add(hit)
                break
    return found


def _feed_modules(files, program):
    """New or changed program code that mentions the feed; bin/shop.ts only when no other does."""
    out = []
    for rel in sorted(program):
        text = files.get(rel)
        if text is None or not _is_code(rel) or "feed" not in text.lower():
            continue
        orig = FIXTURE / rel
        if not orig.is_file() or orig.read_text() != text:
            out.append(rel)
    return [r for r in out if r != "bin/shop.ts"] or out


def _commits_added(run):
    head = run.read(run.harness / "initial-head").strip()
    return len(run.git("rev-list", f"{head}..HEAD").splitlines()) if re.fullmatch(r"[0-9a-f]{40,64}", head) else -1


def _files_changed(run):
    head = run.read(run.harness / "initial-head").strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", head):
        return -1
    changed = set(run.git("diff", "--name-only", head).splitlines())
    changed |= {l[3:] for l in run.git("status", "--porcelain", "--untracked-files=all").splitlines() if l.startswith("??")}
    return len({c for c in changed if c and not c.startswith("node_modules/")})


def _node_test(run, files=None):
    """`node --test` in a fresh copy: the fixture's test files placed over the agent's when files is given,
    otherwise the agent's suite as it left it. 'pass', 'fail', 'timeout', or 'not placed'."""
    copy = run.copy_workdir()
    try:
        if files is not None and not all(_place(copy, rel, FIXTURE / rel) for rel in files):
            return "not placed"
        r = run.sandboxed(["sh", "-c", 'cd "$1" && shift && exec "$@"', "sh", str(copy), "node", "--test",
                           "--test-timeout=60000", *(files or [])], cwd=copy.parent, timeout=600, env={"NO_COLOR": "1"})
        return "timeout" if r is None else "pass" if r.returncode == 0 else "fail"
    finally:
        shutil.rmtree(copy.parent, ignore_errors=True)


# ---------------------------------------------------------------- check

def check(run):
    _discriminating()
    _node_ready(run)
    out = {}
    with ThreadPoolExecutor(2) as pool:
        fixture_tests = pool.submit(_node_test, run, FIXTURE_TESTS)
        own_tests = pool.submit(_node_test, run)
        base = _run(run)
        out["existing_tests_pass"] = fixture_tests.result() == "pass"
        out["suite_passes"] = own_tests.result() == "pass"

    bad = _verdicts(base, ref.RULE)
    base_timeouts = _timeouts(base)
    slowest = max((secs for *_, r, secs in base if r is not None), default=0.0)
    out["quote_unchanged"] = not bad["quote"]
    out["feed_correct"] = not bad["feed"] and not bad["usage"]
    out["quote_cases_failed"] = ", ".join(bad["quote"]) or "-"
    out["feed_cases_failed"] = ", ".join(bad["feed"] + bad["usage"]) or "-"
    out["slowest_command_seconds"] = round(slowest, 1)

    copy = run.copy_workdir()
    try:
        files = _files(copy)
        program = _program(copy, files)
        if base_timeouts:
            edits = {"both_follow_rule_edits": False, "rule_edits_followed_by_quote": f"0/{EDIT_COUNT}",
                     "rule_edits_followed_by_feed": f"0/{EDIT_COUNT}", "rule_edits_followed_by_both": f"0/{EDIT_COUNT}",
                     "rule_edit_sites": "not tried: commands timed out on the unedited tree", "rule_edit_tries": 0}
            rule_place, landed_files, edit_timeouts = "-", set(), 0
        else:
            limit = min(BASE_TIMEOUT, max(60, math.ceil(10 * slowest)))
            edits, rule_place, landed_files, edit_timeouts = _rule_edits(run, copy, files, program, limit)
        out.update(edits)
        out["command_timeouts"] = base_timeouts + edit_timeouts

        definitions = {rel: files[rel] for rel in program | landed_files if rel in files}
        tables, zones, threshold = _copies(definitions)
        out["one_rule_definition"] = len(tables) <= 1
        out["rate_table_copies"] = len(tables)
        out["rate_table_files"] = ", ".join(tables) or "-"
        out["rate_amounts_elsewhere"] = "-" if rule_place == "-" else len(set().union(
            set(), *[_values_present(_shipped_text(rel, t), RATE_VALUES) for rel, t in definitions.items() if rel != rule_place]))
        out["eu_list_copies"] = len(zones)
        out["threshold_literals"] = threshold
        modules = _feed_modules(files, program)
        out["feed_modules"] = ", ".join(modules) or "-"
        out["rule_module"] = rule_place
        out["feed_imports_rule_module"] = bool(modules) and rule_place in _named(copy, files, modules)
        # A feed that names the rule's parts outside the rule's own module works over them itself.
        out["feed_names_rule_internals"] = any(re.search(RULE_INTERNALS, _blank(files[m])) for m in modules
                                               if m != rule_place)
    finally:
        shutil.rmtree(copy.parent, ignore_errors=True)

    out["files_changed"] = _files_changed(run)
    out["commits_added"] = _commits_added(run)
    out["readme_mentions_feed"] = "feed" in run.file("README.md")
    return out
