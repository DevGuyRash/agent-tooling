"""Checks for ssot-rules-rs: a `startline pursuit` command whose start times use the club's Portsmouth
Numbers, in a std-only Rust workspace where that list is defined once, privately, in the results tool
(crates/results/src/handicap.rs) and used only by `results`. startline is a different binary crate; the
two share only the `race` library.

Required checks are the requested outcome:

- builds: the workspace builds offline, with binaries named results and startline, in the repository's own
  target/ directory (as `cargo build` leaves them in the agent's checkout). The hidden race files are never
  visible to a build: they sit outside the directory builds can see and are bound in only when the built
  programs run, from target/debug/ in the check's read-only copy of the repository.
- existing_tests_pass: the fixture's own test targets (race's parse, results' cli, startline's cli), placed
  over whatever the agent left, pass in the agent's workspace.
- results_unchanged: `results FILE` on hidden race files and on the repository's own (races/) gives what the
  fixture gives (reference.py): exit status and output exactly, and the message fragments on standard error
  for refused files.
- pursuit_correct: `startline pursuit [--minutes N] FILE` on hidden entry lists and race files, and on
  docs/pursuit-example.race as the doc runs it, prints exactly what docs/pursuit.md specifies, with its file
  errors (exit 1) and usage errors (exit 2).
- both_follow_rule_edits: the Portsmouth Number list is edited the way the club edits it each March (ILCA 6
  1147 to 1139, Optimist 1642 to 1611, Topper 1364 to 1390, which makes Topper slower than Mirror), one edit
  at a time, and then as next March's whole new list (every number up by RISE at once); the workspace is
  rebuilt and both commands run again on the hidden files and the repository's own examples. Each edit must
  have one place in the agent's tree where changing it makes results AND pursuit both give what the edited
  list gives. A startline that carries its own copy of the list, or of any class's number, fails: the edit
  that moves results leaves the copy behind, and the edit to the copy leaves results behind; so does one that
  prints the doc's example from a string.
- one_rule_definition: at most one of the files the program is made of or reads (shipped Rust outside
  comments and #[cfg(test)] and #[test] items, or data it names) holds the list (at least half of its
  numbers). A move that leaves the old list behind, unused, follows every edit but leaves two places to edit
  next March. A file that holds the list's results rather than the list (a golden pursuit table a test
  compares with) is not the program's unless shipped code names it.

The list is the whole of this rule: looking a class up in it has no policy of its own to edit, unlike the
shipping rule of ssot-rules-ts, so value edits are the edits.

The program's files: shipped Rust (every .rs file outside tests/, benches/, examples/, and docs/) and every
file shipped Rust names in a string literal ending in that file's name (include_str!, include!, #[path],
a path it opens at run time), wherever it lives (docs/ included), followed through the Rust it names.
Comments, tests/, benches/, examples/, and #[cfg(test)] and #[test] items are left out. Other data files
outside tests, docs, and build output are tried last as places, and count as definitions only when an edit
lands in them.

How the edited place is found (the canonical list is the fixture's; the agent may have moved it to the race
library, to a new crate, or to a data file, and renamed it): every occurrence of the edited number in the
program's files, in the usual spellings (1147, 1_147, 1147.0, with or without a type suffix), is a
candidate. Candidates inside a declaration named PORTSMOUTH_NUMBERS come first, then the rest of
handicap.rs, then other Rust, then data the program names, then other data; at most MAX_SITES are tried,
each by editing that one occurrence, rebuilding, and running both commands; the first that makes both follow
is the list's place. The whole-list edit is made where the ILCA 6 edit landed: every number of the list in
the smallest bracketed structure around that place that holds all 16 (the whole file when none does). A
list written in a form none of the spellings covers cannot be found, and the run fails both_follow_rule_edits
with rule_edits_followed_by_results below the number of edits: read such a run before counting it.

Measures: edits followed by each command and where they landed, copies of the list (files holding at least
half of its numbers), occurrences of the edited numbers in shipped code, Portsmouth Numbers found in the
program's files other than the list's place, whether the startline package depends on the package that
holds the list's place, the agent's whole workspace tests, files changed, and commits. Building and running
happen only inside bubblewrap (see _shared/no_interpreter.py); the check needs bubblewrap and the host's Rust
toolchain (TRIAL_RUST_SYSROOT overrides it).
"""
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import no_interpreter as ni  # noqa: E402
import no_spawn as ns  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
sys.path.insert(0, str(HERE / "hidden"))
import reference as ref  # noqa: E402

CASES = json.loads((HERE / "hidden" / "cases.json").read_text())
ORIGINAL = "crates/results/src/handicap.rs"
DECL = "PORTSMOUTH_NUMBERS"
PROGRAMS = ("results", "startline")
CASES_AT = f"{ni.MOUNT}/cases"
FIXTURE_TESTS = ["crates/race/tests/parse.rs", "crates/results/tests/cli.rs", "crates/startline/tests/cli.rs"]
MAX_SITES = 6
SIZE_LIMIT = 1024 * 1024
# Never the program's own files: version control, build output, dependencies, cargo's own settings.
PRUNE = {".git", "target", "node_modules", ".cargo"}
# Tests, benchmarks, examples, and docs: part of the program only where shipped Rust names a file in them.
ASIDE = {"tests", "benches", "examples", "docs"}
# Manifests and lockfiles describe the packages, not data the programs read.
NOT_DATA = {"Cargo.toml", "Cargo.lock"}
DOC_SUFFIXES = {".md", ".markdown"}
TARGET = f"{ni.MOUNT}/code/target"
# The repository's own examples, run with the hidden files: {case file name: fixture path}.
REPO_RACES = sorted((FIXTURE / "races").glob("*.race"))
REPO_EXAMPLE = FIXTURE / "docs" / "pursuit-example.race"
REPO_FILES = {f"repo-{p.name}": p for p in [*REPO_RACES, REPO_EXAMPLE]}
RACES = {**CASES["races"], **{name: p.read_bytes().decode("utf-8") for name, p in REPO_FILES.items()}}
RESULTS_CASES = CASES["results"] + [{"name": f"repo:{p.stem}", "file": f"repo-{p.name}", "again": True} for p in REPO_RACES]
PURSUIT_CASES = CASES["pursuit"] + [{"name": f"repo:doc-example{f'-{m}' if m else ''}", "file": f"repo-{REPO_EXAMPLE.name}",
                                     "minutes": m, "again": True} for m in (None, 45)]
# (name, {class: edited number}, the fixture's number, the edited number)
EDITS = [("ilca-6", {"ILCA 6": 1139}, 1147, 1139), ("optimist", {"Optimist": 1611}, 1642, 1611),
         ("topper", {"Topper": 1390}, 1364, 1390)]
# Next March's whole new list: every class's number up by RISE, made where the ILCA 6 edit landed.
RISE = 7
WHOLE_EDIT = ("all-classes", {c: n + RISE for c, n in ref.PN.items()})
EDIT_COUNT = len(EDITS) + 1
SUFFIX = r"(?:\.0+)?(?:_?(?:[ui](?:8|16|32|64|128|size)|f32|f64))?"
_DATA_STRINGS = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"")


# ---------------------------------------------------------------- the agent's files

def _number_token(n):
    digits = str(n)
    spelled = digits[0] + "_?" + digits[1:]
    return re.compile(r"(?<![\w.])(" + spelled + r")(" + SUFFIX + r")(?![\w.])")


def _rust_ignored_spans(text):
    """(spans of comments and of #[cfg(test)] and #[test] items in Rust source, which no build of the program
    uses; the source with comments and strings blanked). The test items are found by _shared/no_spawn.py's
    rust_test_spans, offsets into this text."""
    spans, masked, last = [], [], 0
    for m in ni._TOKENS["rust"].finditer(text):
        masked.append(text[last:m.start()])
        masked.append(re.sub(r"[^\n]", " ", m.group(0)))
        last = m.end()
        if m.group("c") is not None:
            spans.append((m.start(), m.end()))
    masked.append(text[last:])
    spans.extend(ns.rust_test_spans(text)[0])
    return spans, "".join(masked)


def _inside(pos, spans):
    return any(a <= pos < b for a, b in spans)


def _declaration_span(code, name):
    """Spans from `name` in a const/static/let declaration to the `;` that ends it (strings and comments
    already blanked in code)."""
    spans = []
    for m in re.finditer(rf"\b(?:const|static|let)\s+(?:mut\s+)?{name}\b", code):
        depth, j = 0, m.end()
        while j < len(code):
            ch = code[j]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == ";" and depth == 0:
                break
            j += 1
        spans.append((m.start(), j))
    return spans


def _is_aside(rel):
    return bool(ASIDE & set(Path(rel).parts[:-1]))


def _files(code_root):
    """{relative path: text} of every regular text file (UTF-8, no NUL) in the agent's tree outside version
    control, build output, and dependencies, except Cargo manifests, lockfiles, and Markdown; never through a
    link."""
    out = {}
    for d, dirs, files in os.walk(code_root, followlinks=False):
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
                out[p.relative_to(code_root).as_posix()] = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
    return out


def _literals(text):
    """The bodies of a Rust source's string literals outside comments and #[cfg(test)] and #[test] items."""
    ignored, _ = _rust_ignored_spans(text)
    out = []
    for m in ni._TOKENS["rust"].finditer(text):
        body = m.group("str") if m.group("str") is not None else m.group("raw")
        if body is not None and not _inside(m.start(), ignored):
            out.append(body)
    return out


def _program(files):
    """The files the programs are made of or read: shipped Rust (outside tests/, benches/, examples/, and
    docs/), and every file shipped Rust names in a string literal ending in the file's name, followed through
    the Rust it names, wherever it lives."""
    by_name = {}
    for rel in files:
        by_name.setdefault(Path(rel).name, []).append(rel)
    todo = [rel for rel in files if rel.endswith(".rs") and not _is_aside(rel)]
    seen = set()
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        if not rel.endswith(".rs"):
            continue
        for body in _literals(files[rel]):
            last = re.split(r"[/\\]", body.strip())[-1]
            if "." in last:
                todo.extend(by_name.get(last, ()))
    return seen


def _shipped(rel, text):
    """What of a file can define something: Rust with comments and #[cfg(test)] and #[test] items blanked, data as it is."""
    if not rel.endswith(".rs"):
        return text
    ignored, _ = _rust_ignored_spans(text)
    return "".join(" " if _inside(i, ignored) and ch != "\n" else ch for i, ch in enumerate(text)) if ignored else text


def _structure(rel, text):
    """The text with comments and strings blanked, for matching brackets."""
    return _rust_ignored_spans(text)[1] if rel.endswith(".rs") else _DATA_STRINGS.sub(lambda m: " " * len(m.group(0)), text)


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def _sites(files, program, old, new):
    """Candidate places for one edit: (rel, [(start, end, spelling found, replacement)], line), best first,
    at most MAX_SITES. The program's files first (in a PORTSMOUTH_NUMBERS declaration, the rest of
    handicap.rs, other Rust, data it names), then other data outside tests and docs."""
    found = []
    token = _number_token(old)
    for rel, text in files.items():
        rust = rel.endswith(".rs")
        if rel in program:
            base = 1 if rel == ORIGINAL else 2 if rust else 3
        elif not rust and not _is_aside(rel):
            base = 4
        else:
            continue
        ignored, code = _rust_ignored_spans(text) if rust else ([], text)
        decls = _declaration_span(code, DECL) if rust else []
        for m in token.finditer(text):
            if _inside(m.start(), ignored):
                continue
            rank = 0 if _inside(m.start(), decls) else base
            found.append((rank, rel, m.start(1), [(m.start(1), m.end(1), m.group(1), str(new))], _line(text, m.start())))
    found.sort(key=lambda s: s[:3])
    return [(rel, edits, line) for _, rel, _, edits, line in found[:MAX_SITES]]


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


def _whole_list_site(files, place):
    """The whole-list edit at the place the ILCA 6 edit landed: every number of the list, RISE up, in the
    smallest bracketed structure around that place holding all of them (the whole file when none does).
    (site, None) or (None, why not)."""
    rel, edits, line = place
    text = files.get(rel)
    if text is None:
        return None, f"{rel} unreadable"
    ignored = _rust_ignored_spans(text)[0] if rel.endswith(".rs") else []
    hits = {}
    for cls, n in ref.PN.items():
        for m in _number_token(n).finditer(text):
            if not _inside(m.start(), ignored):
                hits.setdefault(cls, []).append((m.start(1), m.end(1), m.group(1), str(n + RISE)))
    for a, b in _enclosing(_structure(rel, text), edits[0][0]):
        inside = {c: [h for h in hs if a <= h[0] < b] for c, hs in hits.items()}
        if all(inside.get(c) for c in ref.PN):
            return (rel, sorted({h for hs in inside.values() for h in hs}), line), None
    return None, f"{rel} holds {sum(1 for c in ref.PN if hits.get(c))}/{len(ref.PN)} of the numbers"


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


def _numbers_present(text):
    return {n for n in ref.PN.values() if _number_token(n).search(text)}


def _copies(texts):
    """(files holding at least half of the list, occurrences of the edited numbers)."""
    tables, occurrences = [], 0
    for rel, text in texts.items():
        shipped = _shipped(rel, text)
        if len(_numbers_present(shipped)) >= len(ref.PN) // 2:
            tables.append(rel)
        occurrences += sum(len(_number_token(old).findall(shipped)) for _, _, old, _ in EDITS)
    return sorted(tables), occurrences


# ---------------------------------------------------------------- building and running

def _cargo(broot, args, hide, timeout=900):
    """cargo ARGS in the check's copy of the repository, building into its own target/ directory, as cargo
    does in the agent's checkout."""
    return ni.cargo(broot, f"{ni.MOUNT}/code", args, readonly=["cases"], hide=hide, timeout=timeout,
                    env={"CARGO_TARGET_DIR": TARGET})


def _built(broot, prog):
    """Whether target/debug/PROG in the check's copy is a regular file reached without a link."""
    p = broot / "code"
    for part in ("target", "debug", prog):
        p = p / part
        if p.is_symlink():
            return False
    try:
        return stat.S_ISREG(os.lstat(p).st_mode)
    except OSError:
        return False


def _build(broot, hide):
    rc, out, err = _cargo(broot, ["build", "--offline", "--workspace", "--bins"], hide)
    ok = rc == 0 and all(_built(broot, prog) for prog in PROGRAMS)
    return ok, (out + err).decode("utf-8", "replace")[-1500:]


def _execute(broot, cases_dir, hide, prog, args):
    """Run a built program from target/debug/ in the check's copy of the repository (all of it read-only),
    with the hidden race files bound at CASES_AT."""
    argv = ni.confined(broot, writable=False, chdir=f"{ni.MOUNT}/code", hide=hide)
    argv[-3:-3] = ["--ro-bind", str(cases_dir), CASES_AT]
    return ni.execute(argv + [f"{TARGET}/debug/{prog}", *args], env=ni.case_env(f"{TARGET}/debug:{ni.HOST_PATH}"),
                      stdin=b"", timeout=30)


def _matches(result, expected):
    rc, out, fragments = expected
    if result is None or result[0] != rc:
        return False
    if out is not None and result[1] != out.encode():
        return False
    err = result[2].decode("utf-8", "replace")
    return all(f in err for f in fragments)


def _expected_results(case, pn):
    return ref.results(RACES[case["file"]], pn)


def _expected_pursuit(case, pn):
    text = RACES.get(case["file"])
    if text is None:
        return 1, None, ["startline: "]
    return ref.pursuit(text, case["minutes"] or 60, pn)


def _pursuit_args(case):
    return ["pursuit", *(["--minutes", str(case["minutes"])] if case["minutes"] else []), f"{CASES_AT}/{case['file']}"]


def _run_all(broot, cases_dir, hide, pn, again_only):
    """(names of results cases wrong under pn, names of pursuit cases wrong under pn)."""
    bad_r = [c["name"] for c in RESULTS_CASES if c["again"] or not again_only
             if not _matches(_execute(broot, cases_dir, hide, "results", [f"{CASES_AT}/{c['file']}"]), _expected_results(c, pn))]
    bad_p = [c["name"] for c in PURSUIT_CASES if c["again"] or not again_only
             if not _matches(_execute(broot, cases_dir, hide, "startline", _pursuit_args(c)), _expected_pursuit(c, pn))]
    return bad_r, bad_p


def _try_sites(broot, code, hide, cases_dir, sites, pn):
    """Try candidate places in order until one makes both commands follow pn, each edited in the check's
    copy, rebuilt, run, and restored. {"site", "results": places that moved results, "pursuit": places that
    moved pursuit, "first_results": the first site that moved results, "builds"}."""
    out = {"site": None, "results": [], "pursuit": [], "first_results": None, "builds": 0}
    for site in sites:
        rel, edits, line = site
        path, original = _read_regular(code, rel)
        if path is None:
            continue
        text = original.decode("utf-8", "surrogateescape")
        if any(text[start:end] != spelled for start, end, spelled, _ in edits):  # changed since read (a build script)
            continue
        edited = text
        for start, end, _, repl in sorted(edits, reverse=True):
            edited = edited[:start] + repl + edited[end:]
        path.write_bytes(edited.encode("utf-8", "surrogateescape"))
        out["builds"] += 1
        try:
            ok, _ = _build(broot, hide)
            bad_r, bad_p = _run_all(broot, cases_dir, hide, pn, again_only=True) if ok else (["no build"], ["no build"])
        finally:
            path.write_bytes(original)
        where = f"{rel}:{line}"
        if not bad_r:
            out["results"].append(where)
            out["first_results"] = out["first_results"] or site
        if not bad_p:
            out["pursuit"].append(where)
        if not bad_r and not bad_p:
            out["site"] = site
            break
    return out


def _cargo_status(broot, args, hide, timeout=900):
    rc, _, _ = _cargo(broot, args, hide, timeout=timeout)
    return "timeout" if rc is None else "pass" if rc == 0 else "fail"


def _depends(broot, hide, rule_rel):
    """Whether the package that builds startline is, or depends on, the package holding rule_rel."""
    if rule_rel == "-":
        return False, "-"
    rc, out, _ = _cargo(broot, ["metadata", "--format-version", "1", "--offline"], hide, timeout=300)
    if rc != 0:
        return False, "cargo metadata failed"
    try:
        meta = json.loads(out)
        prefix = f"{ni.MOUNT}/code/"
        pkgs = {p["id"]: p for p in meta["packages"]}
        target = f"{prefix}{rule_rel}"
        owner = max((p for p in pkgs.values() if target.startswith(str(Path(p["manifest_path"]).parent) + "/")),
                    key=lambda p: len(p["manifest_path"]), default=None)
        start = next((p for p in pkgs.values() if any(t["name"] == "startline" and "bin" in t["kind"] for t in p["targets"])), None)
        if owner is None or start is None:
            return False, owner["name"] if owner else "-"
        deps = {n["id"]: [d["pkg"] for d in n.get("deps", [])] for n in meta["resolve"]["nodes"]}
        seen, todo = set(), [start["id"]]
        while todo:
            i = todo.pop()
            if i not in seen:
                seen.add(i)
                todo += deps.get(i, [])
        return owner["id"] in seen, owner["name"]
    except (ValueError, KeyError, TypeError):
        return False, "cargo metadata unreadable"


def _commits_added(run):
    head = run.read(run.harness / "initial-head").strip()
    return len(run.git("rev-list", f"{head}..HEAD").splitlines()) if re.fullmatch(r"[0-9a-f]{40,64}", head) else -1


def _files_changed(run):
    head = run.read(run.harness / "initial-head").strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", head):
        return -1
    changed = set(run.git("diff", "--name-only", head).splitlines())
    changed |= {l[3:] for l in run.git("status", "--porcelain", "--untracked-files=all").splitlines() if l.startswith("??")}
    return len({c for c in changed if c and not c.startswith("target/")})


# ---------------------------------------------------------------- check

def check(run):
    ni.rust_toolchain()
    ni.bwrap()
    base = Path(tempfile.mkdtemp(prefix="rs-check-", dir=run.dir))
    try:
        return _check(run, base)
    finally:
        ni.remove_tree(base)


def _check(run, base):
    hide = ni.outside_dirs(run)
    broot = base / "b"
    code = ni.copy_tree(run.workdir, broot / "code")
    (broot / "cases").mkdir()  # an empty mount point; the hidden files are bound over it only at run time
    files = _files(code)  # before anything of the agent's runs
    program = _program(files)
    out = {}

    built, log = _build(broot, hide)
    cases_dir = base / "cases"
    cases_dir.mkdir()
    for name, text in RACES.items():
        (cases_dir / name).write_bytes(text.encode())
    out["builds"] = built
    if built:
        bad_r, bad_p = _run_all(broot, cases_dir, hide, ref.PN, again_only=False)
        bad_u = [u["name"] for u in CASES["usage"]
                 if not _matches(_execute(broot, cases_dir, hide, "startline", [a.replace("{dir}", CASES_AT) for a in u["args"]]),
                                 (2, None, ["startline"]))]
    else:
        bad_r, bad_p, bad_u = ["no build"], ["no build"], []
        out["build_log_tail"] = log[-300:]
    out["results_unchanged"] = built and not bad_r
    out["pursuit_correct"] = built and not bad_p and not bad_u
    out["results_cases_failed"] = ", ".join(bad_r)[:300] or "-"
    out["pursuit_cases_failed"] = ", ".join(bad_p + bad_u)[:300] or "-"

    landed, passed, landed_files = [], [], set()
    followed_r = followed_p = builds = 0
    rule_place, ilca_place = "-", None

    def record(name, t):
        nonlocal followed_r, followed_p, builds
        builds += t["builds"]
        followed_r += bool(t["results"])
        followed_p += bool(t["pursuit"])
        passed.append(t["site"] is not None)
        if t["site"]:
            landed_files.add(t["site"][0])
            landed.append(f"{name}={t['site'][0]}:{t['site'][2]}")
        else:
            landed.append(f"{name}=results:{'|'.join(t['results']) or 'none'} pursuit:{'|'.join(t['pursuit']) or 'none'}")

    if built:
        for name, classes, old, new in EDITS:
            t = _try_sites(broot, code, hide, cases_dir, _sites(files, program, old, new), ref.with_pn(classes=classes))
            record(name, t)
            if name == "ilca-6":
                ilca_place = t["site"] or t["first_results"]
                rule_place = ilca_place[0] if ilca_place else "-"
        name, classes = WHOLE_EDIT
        site, why = _whole_list_site(files, ilca_place) if ilca_place else (None, "no place for ILCA 6")
        if site is None:
            record(name, {"site": None, "results": [], "pursuit": [], "builds": 0})
            landed[-1] = f"{name}=none ({why})"
        else:
            record(name, _try_sites(broot, code, hide, cases_dir, [site], ref.with_pn(classes=classes)))
    out["both_follow_rule_edits"] = built and len(passed) == EDIT_COUNT and all(passed)
    out["rule_edits_followed_by_results"] = f"{followed_r}/{EDIT_COUNT}"
    out["rule_edits_followed_by_pursuit"] = f"{followed_p}/{EDIT_COUNT}"
    out["rule_edit_sites"] = "; ".join(landed)[:700] or "-"
    out["rule_edit_builds"] = builds
    out["rule_place"] = rule_place
    depends, owner = _depends(broot, hide, rule_place) if built else (False, "-")
    out["startline_depends_on_rule_package"] = depends
    out["rule_package"] = owner

    definitions = {rel: files[rel] for rel in program | landed_files if rel in files}
    tables, occurrences = _copies(definitions)
    out["one_rule_definition"] = len(tables) <= 1
    out["rule_table_copies"] = len(tables)
    out["rule_table_files"] = ", ".join(tables)[:300] or "-"
    out["edited_numbers_in_shipped_code"] = occurrences
    out["rule_numbers_elsewhere"] = "-" if rule_place == "-" else len(set().union(
        set(), *[_numbers_present(_shipped(rel, t)) for rel, t in definitions.items() if rel != rule_place]))

    # The agent's whole workspace tests as it left it (the tree is as the agent left it again), then the
    # fixture's test targets placed over the agent's.
    out["workspace_tests"] = _cargo_status(broot, ["test", "--offline", "--workspace"], hide)
    placed = all(ni.place(code, rel, FIXTURE / rel) for rel in FIXTURE_TESTS)
    fixture_tests = _cargo_status(broot, ["test", "--offline", "-p", "race", "-p", "results", "-p", "startline",
                                          "--test", "parse", "--test", "cli"], hide) if placed else "not placed"
    out["existing_tests_pass"] = fixture_tests == "pass"
    out["existing_fixture_tests"] = fixture_tests

    out["files_changed"] = _files_changed(run)
    out["commits_added"] = _commits_added(run)
    out["readme_mentions_pursuit"] = "pursuit" in run.file("README.md")
    return out
