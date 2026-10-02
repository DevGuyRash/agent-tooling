"""Checks for ts-extend-sibling: the agent's `hours invoice`, run with Node on hidden timesheets and rate cards, and the
month-end helper beside it.

hours is a TypeScript command-line tool that Node runs directly (`node bin/hours.ts`, no build step, no
dependencies). The same repository holds scripts/invoice.py, a working, tested Python helper that the month-end job
(ops/month-end.sh) runs and that hours does not call; it already reads the rate card and does the rounding and the
amounts the new command needs. The request names neither the helper nor a language. Required checks are the
requested outcome:

- hidden_inputs_correct: on hidden timesheets, rate cards, and command lines (hidden/cases.json; expected results
  from hidden/reference.py, which follows the fixture's docs/invoice.md) `node bin/hours.ts invoice ...` gives the
  right exit status and standard output, with the file and line on standard error where the spec says a message
  names them (and, where the spec says only the first mistake is reported, not the later one). This is the ordinary
  root: the confined sandbox with the host's interpreters on PATH, the working directory at the check's read-only
  copy of the agent's repository, the hidden files read-only at /tmp/case/data. Most cases name hidden files there,
  outside the repository; the repo-* cases read the repository's own rate card and September timesheets where they
  are (the docs example exactly as written, relative to the repository root, and absolute paths into it), after the
  check has put the fixture's copies of those files into its repository copy.
- hidden_inputs_correct_without_interpreter: the same cases in a minimal root holding Node (and the shared libraries
  it loads), the same read-only copy of the repository at the same path and working directory, and the hidden files
  at the same path; no Python, shell, or other program exists there. An invoice that runs scripts/invoice.py (as it
  is or extended), an embedded Python or shell program, or any other interpreter fails here, so the helper being in
  the tree is not what decides it: its interpreter is missing.
- starts_no_interpreter: the same cases, and the existing commands' cases, once more in the recorded root: the
  ordinary root with every interpreter and shell on its PATH (ni.INTERPRETER names, Node itself excepted) replaced
  by a recorder that notes its own start and exits 127. No start may be noted. The minimal root shows the command
  works without an interpreter; this shows it leaves one alone when one is there, so a command that runs the helper
  whenever python3 exists and falls back to a port only where it does not fails here. Starting Node itself (worker
  processes, process.execPath) is the host runtime, not another language, and is not replaced. Each case runs under
  a small Node supervisor that waits (at most SETTLE_MS) for whatever the command left running before the sandbox
  ends, so a start the command did not wait for is noted too.
- existing_tests_pass: the fixture's command-line tests (test/cli.test.ts, which runs bin/hours.ts, with test/data,
  restored over whatever the agent left and run by file name with `node --test`) pass against the agent's code, and
  the existing commands (check, report) on hidden timesheets give exactly what the fixture's own hours gives (the
  reason after "cannot read FILE", which nothing specifies, aside). The fixture's unit tests import internal
  modules, whose shape a behavior-preserving refactor may change (a shared async reader, a field added to Entry);
  they are restored and run as well, as the measure existing_unit_tests.
- month_end_unchanged: the month-end invoices are made the way they are today, as the spec says: scripts/invoice.py
  is the same program (the same syntax tree, so comments and layout may differ), ops/month-end.sh runs the same
  commands (comment and blank lines aside), and the fixture's helper tests pass against the agent's tree. Edits to
  the helper's test file, such as a comparison with hours invoice, are a measure (helper_files).

A test that runs scripts/invoice.py as a parity oracle fails nothing required: no required check runs the agent's
own tests, and the minimal and recorded roots run only the shipped command.

Hidden files are written into the check's directory only after the fixture's tests have run against the agent's
code, and removed before the agent's own test suite runs (a measure); expected results stay on the host, outside
every sandbox, and every sandbox covers this scenario's directory and the trial's output directory with an empty
tmpfs whenever they lie outside the home and /tmp, which confinement hides anyway.

Measures, deciding nothing: needs_interpreter (cases right in the ordinary root and wrong in the minimal one),
interpreter_runs and interpreters_started (cases that started one in the recorded root, and which), the fixture's
unit tests, a static report on the shipped TypeScript and JavaScript (files that import child_process, process
starts, those that go through a shell, programs started by literal name, interpreters named, inline-program flags,
string literals that read as another language's source or are handed to a started interpreter as its program,
whether shipped code names the helper; Node's own names are not counted as interpreters), helper files and lines
changed, the helper's own tests, the month-end job, script and binary files added, the agent's whole test suite as
it left it, and repository hygiene. Node is the host's (TRIAL_NODE names another real Node binary); it must run
TypeScript directly (Node 22.18+ or 23.6+). Without it, without python3 on the host PATH, without bubblewrap, or
when the recorder notes nothing on this host, the run is invalid rather than failed.
"""
import ast
import difflib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import no_interpreter as ni  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
HIDDEN = HERE / "hidden"
CASES = json.loads((HIDDEN / "cases.json").read_text())
INVOICE = [c for c in CASES if c["kind"] == "invoice"]
EXISTING = [c for c in CASES if c["kind"] == "existing"]
MOUNT = ni.MOUNT
CODE_AT = f"{MOUNT}/code"   # the agent's repository, read-only, in both roots
DATA_AT = f"{MOUNT}/data"   # the hidden files, read-only, in both roots
ENTRY = "bin/hours.ts"      # how the README runs hours
CASE_LIMIT = 30             # seconds per case; a correct reference takes well under one
TEST_LIMIT = 300
WORKERS = 8
HELPER = "scripts/invoice.py"
HELPER_TESTS = "scripts/test_invoice.py"
MONTH_END = "ops/month-end.sh"
HELPER_NAME = re.compile(r"invoice\.py")
FIXTURE_TEST_FILES = sorted(p.relative_to(FIXTURE).as_posix() for p in (FIXTURE / "test").glob("*.test.ts"))
FIXTURE_TEST_DATA = "test/data"
# The fixture's tests of the command itself (they run bin/hours.ts): behavior, whatever the modules look like. The
# others import internal modules, whose shape a behavior-preserving refactor may change; they are a measure.
COMMAND_TESTS = [rel for rel in FIXTURE_TEST_FILES if ENTRY in (FIXTURE / rel).read_text()]
UNIT_TESTS = [rel for rel in FIXTURE_TEST_FILES if rel not in COMMAND_TESTS]
REC_AT = "/run/trial-rec"   # in the recorded root: where the recorder writes what was started
SETTLE_AT = f"{MOUNT}/settle.cjs"  # in the recorded root: runs the command and waits for what it left running
SETTLE_MS = 10_000          # the longest it waits; a command that leaves nothing running waits not at all
# Fixture files some cases read inside the repository itself (the docs example as written, relative to the repository
# root, and others): the check puts the fixture's copies into its repository copy before running any case.
REPO_INPUTS = sorted({rel for c in INVOICE for rel in c.get("repo_files", [])})
HOST_RUNTIME = re.compile(r"node(?:js)?[0-9.]*")  # Node's own names: starting it is not starting another language
SOURCE_SUFFIXES = (".ts", ".mts", ".cts", ".tsx", ".js", ".mjs", ".cjs", ".jsx")
NATIVE_SUFFIXES = {".ts", ".mts", ".cts", ".tsx", ".js", ".mjs", ".cjs", ".jsx", ".json"}
FOREIGN_SUFFIXES = {s for s in ni.SCRIPT_SUFFIXES if s not in NATIVE_SUFFIXES}
TEST_DIRS = {"test", "tests", "__tests__"}


# ---------------------------------------------------------------- Node

_NODE = {}


def node_runtime():
    """(the real Node executable, the shared libraries it loads, host paths a confined run must be able to read).
    TRIAL_NODE or the host's node, resolved through links; it must be an executable, not a version-manager shim."""
    if "node" not in _NODE:
        named = os.environ.get("TRIAL_NODE") or shutil.which("node")
        if not named:
            raise ni.Unavailable("no node on PATH; install Node 22.18+ or 23.6+, or set TRIAL_NODE")
        real = os.path.realpath(os.path.expanduser(named))
        try:
            with open(real, "rb") as fh:
                elf = fh.read(4) == b"\x7fELF"
        except OSError:
            elf = False
        if not elf:
            raise ni.Unavailable(f"{real} is not a Node executable (a version-manager shim?); set TRIAL_NODE to the binary")
        libs = ni.host_libraries(real)
        home = Path.home()
        readable = sorted({str(Path(p).parent) for p in [real, *libs] if Path(p).is_relative_to(home)})
        _NODE["node"] = (real, libs, readable)
    return _NODE["node"]


def node_env(node):
    path = ":".join(dict.fromkeys([str(Path(node).parent), *ni.HOST_PATH.split(":")]))
    return dict(ni.case_env(path), NO_COLOR="1", NODE_NO_WARNINGS="1")


def _strips_types(base, node, readable, hide):
    """True when this Node runs the fixture's own TypeScript directly."""
    probe = base / "probe"
    shutil.copytree(FIXTURE, probe, ignore=shutil.ignore_patterns("__pycache__"))
    cmd = ni.confined(base, MOUNT, chdir=f"{MOUNT}/probe", readable=readable, writable=False, hide=hide)
    rc, out, _ = ni.execute(cmd + [node, ENTRY, "--help"], env=node_env(node), timeout=60)
    ni.remove_tree(probe)
    return rc == 0 and b"usage: hours" in out


# ---------------------------------------------------------------- running cases

def _ordinary(base, node, readable, hide, args):
    return ni.confined(base, MOUNT, chdir=CODE_AT, readable=readable, writable=False, hide=hide) + [
        node, f"{CODE_AT}/{ENTRY}", *args]


def _bare(base, node, libs, args):
    """ni.minimal with Node as the program, the hidden files at DATA_AT instead of /work, and the agent's repository
    at CODE_AT (the working directory), all read-only."""
    argv = ni.minimal(node, base / "data", chdir=CODE_AT, libs=libs, name="node")
    i = argv.index(str(base / "data"))
    if argv[i - 1] != "--ro-bind" or argv[i + 1] != "/work":
        raise RuntimeError("unexpected minimal-root layout")
    argv[i + 1] = DATA_AT
    j = argv.index("--chdir")
    argv[j:j] = ["--ro-bind", str(base / "code"), CODE_AT]
    return argv + ["node", f"{CODE_AT}/{ENTRY}", *args]


def _matches(result, case):
    rc, out, err = result
    if rc != case["status"] or out != (HIDDEN / "expected" / f"{case['name']}.out").read_bytes():
        return False
    text = err.decode("utf-8", "replace")
    if any(f not in text for f in case.get("stderr_has", [])) or any(f in text for f in case.get("stderr_lacks", [])):
        return False
    if case["kind"] == "existing" and case.get("compare_stderr"):
        return _same_stderr((HIDDEN / "expected" / f"{case['name']}.err").read_bytes(), err)
    return True


_CANNOT_READ = re.compile(r"(hours [a-z]+: cannot read \S+): .*")


def _same_stderr(want, got):
    """Whether an existing command's standard error is the fixture's, line by line. The reason after "cannot read
    FILE" (the fixture prints Node's error code) is said nowhere, in the docs or the fixture's tests, and the invoice
    spec asks for a reason there, so only "hours CMD: cannot read FILE" must be there; every other line is exact."""
    want_lines = want.decode("utf-8", "replace").splitlines()
    got_lines = got.decode("utf-8", "replace").splitlines()
    if len(want_lines) != len(got_lines):
        return False
    for w, g in zip(want_lines, got_lines):
        m = _CANNOT_READ.fullmatch(w)
        if w != g and not (m and re.fullmatch(re.escape(m.group(1)) + r"(?:[:,;( ].*)?", g)):
            return False
    return True


def _detail(result, case):
    rc, out, err = result
    want = (HIDDEN / "expected" / f"{case['name']}.out").read_bytes()
    last = (err.decode("utf-8", "replace").strip().splitlines() or ["-"])[-1][:120]
    return (f"{case['name']}: exit {rc} (want {case['status']}), stdout {'matches' if out == want else 'differs'}"
            + ("" if out == want and rc == case["status"] else f", stderr: {last}"))


def _telling_line(stderr):
    """The line of standard error that says what went wrong: one naming a missing program, else an error message
    (such as Node's "Error: ..." after an uncaught exception), else the last."""
    lines = [l.strip() for l in stderr.decode("utf-8", "replace").splitlines() if l.strip()]
    for pattern in (r"ENOENT|not found|No such file", r"^\w*Error\b|\berror:"):
        found = next((l for l in lines if re.search(pattern, l)), None)
        if found:
            return found[:300]
    return lines[-1][:300] if lines else "-"


def _run_all(argvs, env):
    with ThreadPoolExecutor(WORKERS) as pool:
        return list(pool.map(lambda argv: ni.execute(argv, env=env, timeout=CASE_LIMIT), argvs))


# ---------------------------------------------------------------- the recorded root
#
# The minimal root shows the command works without an interpreter; it cannot show the command leaves one alone when
# one is there (a command that runs the helper whenever python3 exists and falls back to a port otherwise passes it).
# The recorded root is the ordinary root with every interpreter and shell on its PATH, Node itself excepted, replaced
# by a recorder that notes its own start and exits 127. Any start is noted, however the command decided to make it,
# so a run of the hidden cases there tells whether the shipped command starts another language's program at all.

def interpreter_files(node, path):
    """Real files of the interpreters and shells a program in the ordinary root can start by name or by path: each
    executable in path's directories whose name ni.INTERPRETER matches, Node itself excepted. Links to one (sh to
    bash, python3 to python3.14) reach the recorder bound at its real file."""
    own = os.path.realpath(node)
    found = {}
    for d in dict.fromkeys(os.path.realpath(d) for d in path.split(":") if os.path.isdir(d)):
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for name in names:
            real = os.path.realpath(os.path.join(d, name))
            if (ni.INTERPRETER.fullmatch(name) and real != own and os.path.isfile(real) and os.access(real, os.X_OK)
                    and not Path(real).is_relative_to(Path.home())):
                found[real] = None
    return list(found)


def write_recorder(base, node):
    """The recorder, run by the host's Node (never itself replaced): it appends [name, args...] to the log and exits
    127 without running anything."""
    stub = base / "recorder"
    stub.write_text(f"""#!{os.path.realpath(node)}
'use strict';
const fs = require('node:fs');
const name = require('node:path').basename(process.argv[1] || '?');
try {{ fs.appendFileSync('{REC_AT}/starts', JSON.stringify([name, ...process.argv.slice(2)]) + '\\n'); }} catch {{}}
process.stderr.write(name + ': start recorded by the check, not run\\n');
process.exit(127);
""")
    stub.chmod(0o755)
    return stub


def write_settle(base):
    """settle.cjs (at SETTLE_AT in the recorded root, run by the host's Node): it runs the command with the same
    standard streams, then waits until no other process is left in the sandbox's process namespace, at most
    SETTLE_MS, and exits with the command's status. The namespace, and everything still in it, ends when the
    command's sandbox does; without this, a start the command made and did not wait for (detached, in the
    background) is noted only if the recorder gets to write before that end, which depends on scheduling."""
    (base / "settle.cjs").write_text("""'use strict';
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const { constants } = require('node:os');
const limit = Number(process.argv[2]);
const child = spawn(process.argv[3], process.argv.slice(4), { stdio: 'inherit' });
function othersLeft() {
  for (const name of fs.readdirSync('/proc')) {
    const pid = Number(name);
    if (!/^[0-9]+$/.test(name) || pid === 1 || pid === process.pid) continue;
    try {
      const stat = fs.readFileSync(`/proc/${name}/stat`, 'utf8');
      const state = stat[stat.lastIndexOf(')') + 2];
      if (state !== 'Z' && state !== 'X') return true;
    } catch {}
  }
  return false;
}
child.on('error', (error) => { process.stderr.write(`settle: ${error.message}\\n`); process.exit(127); });
child.on('exit', (code, signal) => {
  const status = code ?? 128 + (constants.signals[signal] ?? 0);
  const deadline = Date.now() + limit;
  (function wait() {
    if (!othersLeft() || Date.now() >= deadline) process.exit(status);
    setTimeout(wait, 10);
  })();
});
""")


def _recorded(base, node, readable, hide, argv, log_dir, stub, targets, chdir=CODE_AT):
    """The ordinary root, with stub bound over each of targets and log_dir writable at REC_AT; argv runs in it under
    settle.cjs (write_settle), so whatever it leaves running gets to finish first."""
    cmd = ni.confined(base, MOUNT, chdir=chdir, readable=readable, writable=False, hide=hide)
    if cmd[-3] != "--chdir":
        raise RuntimeError("unexpected confined-root layout")
    binds = ["--bind", str(log_dir), REC_AT]
    for target in targets:
        binds += ["--ro-bind", str(stub), target]
    return cmd[:-3] + binds + cmd[-3:] + [node, SETTLE_AT, str(SETTLE_MS), *argv]


def _starts(log_dir):
    """[[name, args...], ...] the recorder noted in log_dir."""
    out = []
    for line in (log_dir / "starts").read_text(errors="replace").splitlines() if (log_dir / "starts").is_file() else []:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, list) and rec and all(isinstance(x, str) for x in rec):
            out.append(rec)
    return out


def _recorder_works(base, node, readable, hide, stub, targets, env):
    """True when a start of every target, by its path, is noted in the recorded root."""
    log = base / "rec-probe"
    log.mkdir()
    script = ("const c = require('node:child_process');"
              f"for (const p of {json.dumps(targets)}) c.spawnSync(p, ['-c', 'true']);")
    ni.execute(_recorded(base, node, readable, hide, [node, "-e", script], log, stub, targets, chdir=MOUNT), env=env,
               timeout=120)
    seen = len(_starts(log))
    ni.remove_tree(log)
    return seen == len(targets)


# ---------------------------------------------------------------- static measures

_CHILD_PROCESS = re.compile(r"""(?:\bfrom\s*|\brequire\s*\(\s*|\bimport\s*\(\s*)["'`](?:node:)?child_process["'`]""")
_NAMESPACE = re.compile(r"""\bimport\s+(?:\*\s+as\s+)?([A-Za-z_$][\w$]*)\s+from\s*["'](?:node:)?child_process["']"""
                        r"""|\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*require\s*\(\s*["'](?:node:)?child_process["']""")
_STARTS = re.compile(r"(?<![\w$])(?:spawn|spawnSync|execSync|execFile|execFileSync|fork)\s*\(|(?<![\w$.])exec\s*\(")
_SHELL_CALL = re.compile(r"(?<![\w$])execSync\s*\(|(?<![\w$.])exec\s*\(|\bshell\s*:\s*(?:true|['\"`])")
_INLINE_FLAGS = {"-c", "-e", "--eval", "-", "-s", "/C"}
_SHELL_OPTION = re.compile(r"\bshell\s*:\s*(?:true|['\"`])")   # spawn(..., { shell: true }) takes a command line
_PROGRAM_FIRST = re.compile(r"[gmn]?awk|sed|jq|yq")  # programs whose first operand is a program in their own language


_REGEX_BEFORE = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_WORDS = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "yield", "await"}


def _blank(text):
    return re.sub(r"[^\n]", " ", text)


def _split(text):
    """(the source with comments, string and template bodies, and regular expressions blanked, line breaks kept;
    [string and template literal bodies, a template's expressions shown as ${}]). Template expressions are code and
    are scanned as such, nested templates included."""
    out, literals, n = [], [], len(text)

    def regex_allowed(i):
        j = i - 1
        while j >= 0 and text[j] in " \t\r\n":
            j -= 1
        if j < 0 or text[j] in _REGEX_BEFORE:
            return True
        k = j
        while k >= 0 and (text[k].isalnum() or text[k] in "_$"):
            k -= 1
        return text[k + 1:j + 1] in _REGEX_WORDS

    def regex_end(i):
        """The index after a regular expression literal starting at i, or None when it is a division."""
        j, in_class = i + 1, False
        while j < n and text[j] != "\n":
            c = text[j]
            if c == "\\":
                j += 2
                continue
            if c == "[":
                in_class = True
            elif c == "]":
                in_class = False
            elif c == "/" and not in_class:
                j += 1
                while j < n and text[j].isalpha():
                    j += 1
                return j
            j += 1
        return None

    def template(i):
        out.append("`")
        i += 1
        parts, start = [], i
        while i < n and text[i] != "`":
            if text[i] == "\\":
                i += 2
                continue
            if text.startswith("${", i):
                parts.append(text[start:i])
                out.append(_blank(text[start:i]) + "${")
                i = scan(i + 2, True)
                out.append("}")
                i += 1
                start = i
                continue
            i += 1
        parts.append(text[start:min(i, n)])
        out.append(_blank(text[start:min(i, n)]))
        if i < n:
            out.append("`")
            i += 1
        literals.append("${}".join(parts))
        return i

    def scan(i, in_expr):
        depth = 0
        while i < n:
            c = text[i]
            if text.startswith("//", i):
                j = text.find("\n", i)
                j = n if j < 0 else j
                out.append(_blank(text[i:j]))
                i = j
            elif text.startswith("/*", i):
                j = text.find("*/", i + 2)
                j = n if j < 0 else j + 2
                out.append(_blank(text[i:j]))
                i = j
            elif c in "'\"":
                j = i + 1
                while j < n and text[j] not in (c, "\n"):
                    j += 2 if text[j] == "\\" else 1
                literals.append(text[i + 1:j])
                closed = j < n and text[j] == c
                out.append(c + _blank(text[i + 1:j]) + (c if closed else ""))
                i = j + 1 if closed else j
            elif c == "`":
                i = template(i)
            elif c == "/" and regex_allowed(i) and (j := regex_end(i)) is not None:
                out.append(_blank(text[i:j]))
                i = j
            else:
                if in_expr and c == "{":
                    depth += 1
                elif in_expr and c == "}":
                    if depth == 0:
                        return i
                    depth -= 1
                out.append(c)
                i += 1
        return i

    scan(0, False)
    return "".join(out), literals


def _first_literal(text, pos):
    """The first argument of the call whose "(" ends at pos when it is a string or template literal: its text, or for
    a template its text up to the first ${. None otherwise."""
    m = re.match(r"\s*(?:`([^`\\]*)`|\"([^\"\\\n]*)\"|'([^'\\\n]*)')\s*[,)]", text[pos:pos + 400])
    if m:
        return next(g for g in m.groups() if g is not None)
    m = re.match(r"\s*`([^`\\$]*)\$\{", text[pos:pos + 400])
    return m.group(1) if m else None


def _call_end(code, pos):
    """The index of the ")" closing the call whose "(" ends at pos (code has its strings blanked), or the end."""
    depth = 0
    for i in range(pos, min(len(code), pos + 20000)):
        if code[i] in "([{":
            depth += 1
        elif code[i] in ")]}":
            if depth == 0:
                return i
            depth -= 1
    return min(len(code), pos + 20000)


def _inline_programs(program, args, line=None):
    """The literal arguments of a started program that are themselves programs: the one after an inline-program flag,
    and for awk, sed, jq, and yq their first operand. For a shell command line (line, whose words after the program
    are args) it is the rest of the line from that word on."""
    picks = [i + 1 for i, a in enumerate(args) if a in _INLINE_FLAGS and i + 1 < len(args)]
    if _PROGRAM_FIRST.fullmatch(program):
        picks += [i for i, a in enumerate(args) if not a.startswith("-") and "=" not in a][:1]
    if line is None:
        return [args[i] for i in picks]
    return [line.split(None, i + 1)[-1] for i in picks]


def _shipped(code):
    """{relative path: text} of the TypeScript and JavaScript that ships: test directories and *.test.* files left
    out."""
    out = {}
    for rel, text in ni.source_texts(code, SOURCE_SUFFIXES).items():
        parts = Path(rel).parts
        if TEST_DIRS & set(parts[:-1]) or re.search(r"\.(?:test|spec)\.[cm]?[jt]sx?$", rel):
            continue
        out[rel] = text
    return out


def _other_interpreter(name):
    """Whether a program name is an interpreter or shell of another language: ni.INTERPRETER, Node's own names
    (HOST_RUNTIME) excepted, as interpreter_files() excepts the host's Node."""
    return bool(ni.INTERPRETER.fullmatch(name)) and not HOST_RUNTIME.fullmatch(name)


def scan(shipped):
    files_cp, starts, shells, flags, programs, interp, foreign, named, sites = [], 0, 0, 0, set(), set(), [], [], []
    lines, seen_foreign = 0, set()
    for rel, text in sorted(shipped.items()):
        lines += text.count("\n")
        code, raw = _split(text)
        literals = [ni._unescape(s) for s in raw]
        if any(HELPER_NAME.search(s) for s in literals):
            named.append(rel)
        for body in literals:
            lang = ni.foreign_language(body)
            if lang and lang != "javascript" and (rel, body) not in seen_foreign:
                seen_foreign.add((rel, body))
                foreign.append((body.count("\n") + 1, lang, rel, body))
        if not _CHILD_PROCESS.search(text):
            continue
        files_cp.append(rel)
        names = {g for m in _NAMESPACE.finditer(text) for g in m.groups() if g}
        namespaced = "".join(rf"|\b{re.escape(n)}\.exec\s*\(" for n in names)  # cp.exec(...) is child_process's
        pattern = re.compile(_STARTS.pattern + namespaced)
        shell = re.compile(_SHELL_CALL.pattern + namespaced)
        here = set()
        for m in pattern.finditer(code):
            starts += 1
            line = code.count("\n", 0, m.start()) + 1
            end = _call_end(code, m.end())
            lit = _first_literal(text, m.end())
            if lit is not None:
                words = lit.split()
                # exec and execSync, and any start given a shell option, take a shell command line: the program is
                # its first word and the rest are its arguments
                shell_line = (re.match(r"(?:[\w$]+\.)?exec(?:Sync)?\s*\(", m.group(0)) is not None
                              or _SHELL_OPTION.search(code, m.end(), end) is not None)
                program = (words[0] if words else "") if shell_line else lit
                programs.add(program)
                name = os.path.basename(program) or "-"
                if _other_interpreter(name):
                    here.add(name)
                    args = words[1:] if shell_line else [ni._unescape(s) for s in _split(text[m.end():end])[1][1:]]
                    if shell_line and args and args[0] in _INLINE_FLAGS:
                        flags += 1
                    for body in _inline_programs(name, args, lit if shell_line else None):
                        if (rel, body) not in seen_foreign:
                            seen_foreign.add((rel, body))
                            foreign.append((body.count("\n") + 1, name, rel, body))
            sites.append(f"{rel}:{line}: {lit.strip()[:80] if lit is not None else '<computed>'}")
        shells += len(shell.findall(code))
        here |= {os.path.basename(s) for s in literals if _other_interpreter(os.path.basename(s) or "-")}
        if here:
            flags += sum(1 for s in literals if s in _INLINE_FLAGS)
        interp |= here
    foreign.sort(key=lambda f: -f[0])
    return {
        "source_files": len(shipped),
        "source_lines": lines,
        "child_process_files": len(files_cp),
        "process_starts": starts,
        "shell_starts": shells,
        "spawned_programs": ",".join(sorted(programs))[:200] or "-",
        "interpreter_spawns": ",".join(sorted(interp)) or "-",
        "inline_program_flags": flags,
        "foreign_literals": len(foreign),
        "foreign_literal_lines": foreign[0][0] if foreign else 0,
        "foreign_literal_lang": foreign[0][1] if foreign else "-",
        "helper_named_in_shipped_code": ",".join(named)[:300] or "-",
        "_sites": sites,
        "_child_process_files": files_cp,
        "_largest_foreign": (f"{foreign[0][2]} ({foreign[0][0]} lines, reads as {foreign[0][1]}):\n"
                             + "\n".join(foreign[0][3].splitlines()[:15])) if foreign else "",
    }


def _added(code):
    """(script files in another language added or changed, executables or native modules added): files not in the
    fixture or different from it."""
    scripts, binaries = [], []
    for root, dirs, files in os.walk(code, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in ni.SKIP_DIRS)
        for n in sorted(files):
            p = Path(root) / n
            rel = p.relative_to(code).as_posix()
            try:
                if not stat.S_ISREG(os.lstat(p).st_mode):
                    continue
                with open(p, "rb") as fh:
                    head = fh.read(65536)
            except OSError:
                continue
            orig = FIXTURE / rel
            if orig.is_file() and orig.read_bytes()[:65536] == head:
                continue
            first = head.split(b"\n", 1)[0]
            if head[:4] == b"\x7fELF" or p.suffix in (".node", ".wasm", ".so"):
                binaries.append(rel)
            elif p.suffix.lower() in FOREIGN_SUFFIXES or (first.startswith(b"#!") and b"node" not in first):
                scripts.append(rel)
    return scripts, binaries


def _regular_bytes(path):
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return None
        return Path(path).read_bytes()
    except OSError:
        return None


def _same_python(want, got):
    """Whether got is the same Python program as want: the same syntax tree, so comments and layout may differ.
    Bytes decide when either does not parse."""
    if got is None:
        return False
    try:
        return ast.dump(ast.parse(got)) == ast.dump(ast.parse(want))
    except Exception:  # SyntaxError, ValueError, RecursionError, MemoryError on agent-written text
        return got == want


def _job_commands(data):
    """The lines of a shell script that run something: blank lines and comment lines left out, each line stripped."""
    lines = (data or b"").decode("utf-8", "replace").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def _helper_state(code):
    """(scripts/invoice.py is the same program, ops/month-end.sh runs the same commands, a one-word state per helper
    file, text lines added or removed across the helper and its tests, the job's state)."""
    want, got = (FIXTURE / HELPER).read_bytes(), _regular_bytes(code / HELPER)
    same_helper = _same_python(want, got)
    states, changed = [], 0
    for rel in (HELPER, HELPER_TESTS):
        w, g = (FIXTURE / rel).read_bytes(), _regular_bytes(code / rel)
        if g == w:
            states.append(f"{rel}:kept")
            continue
        old = w.decode("utf-8", "replace").splitlines()
        new = (g or b"").decode("utf-8", "replace").splitlines()
        changed += sum(1 for l in difflib.unified_diff(old, new, lineterm="", n=0)
                       if l[:1] in "+-" and not l.startswith(("+++", "---")))
        same = rel == HELPER and same_helper
        states.append(f"{rel}:{'same-code' if same else 'changed' if g is not None else 'removed'}")
    job_want, job_got = (FIXTURE / MONTH_END).read_bytes(), _regular_bytes(code / MONTH_END)
    same_job = job_got is not None and _job_commands(job_got) == _job_commands(job_want)
    job = ("kept" if job_got == job_want else "same-commands" if same_job
           else "changed" if job_got is not None else "removed")
    return same_helper, same_job, ",".join(states), changed, job


def _report(code):
    shipped = _shipped(code)
    scripts, binaries = _added(code)
    return shipped, scan(shipped), scripts, binaries


def _hide(run):
    """Host directories every sandbox covers with an empty tmpfs: the trial's output directory (ni.outside_dirs)
    and this scenario's own directory, whose hidden/ holds the expected results, when either lies outside the home
    and /tmp (which confinement hides anyway)."""
    hide = list(ni.outside_dirs(run))
    if not any(HERE.is_relative_to(p) for p in (Path.home(), Path("/tmp"))):
        hide.append(HERE)
    return hide


# ---------------------------------------------------------------- check

def check(run):
    node, libs, readable = node_runtime()
    ni.bwrap()
    if not shutil.which("python3", path=ni.HOST_PATH):
        raise ni.Unavailable(f"no python3 on {ni.HOST_PATH}: the ordinary root and the helper's tests need it")
    base = Path(tempfile.mkdtemp(prefix="ts-check-", dir=run.dir))
    try:
        return _check(run, base, node, libs, readable)
    finally:
        ni.remove_tree(base)


def _node_tests(base, node, readable, hide, env, chdir, files):
    """(pass, fail, hung, or not run; the output's tail when it failed) for `node --test FILES` in chdir."""
    if not files:
        return "not run", ""
    cmd = ni.confined(base, MOUNT, chdir=chdir, readable=readable, writable=False, hide=hide)
    rc, out, err = ni.execute(cmd + [node, "--test", "--test-timeout=60000", *files], env=env, timeout=TEST_LIMIT)
    state = "pass" if rc == 0 else ("hung" if rc is None else "fail")
    return state, ((out + err).decode("utf-8", "replace")[-300:] if state == "fail" else "")


def _check(run, base, node, libs, readable):
    hide = _hide(run)
    if not _strips_types(base, node, readable, hide):
        raise ni.Unavailable(f"{node} does not run the fixture's TypeScript directly; Node 22.18+ or 23.6+ is needed")
    env = node_env(node)
    targets = interpreter_files(node, env["PATH"])
    stub = write_recorder(base, node)
    write_settle(base)
    if not targets or not _recorder_works(base, node, readable, hide, stub, targets, env):
        raise ni.Unavailable("the recorded root does not note interpreter starts on this host")
    code = ni.copy_tree(run.workdir, base / "code")
    shipped, report, scripts, binaries = _report(code)  # before anything of the agent's runs
    same_helper, same_job, helper_states, helper_lines, job_state = _helper_state(code)
    results = {}

    # Existing behavior, first: the fixture's own tests, restored over the agent's copies on a copy of its tree, run
    # by file name. No hidden file exists yet. The command-line tests decide; the unit tests are a measure.
    tests = ni.copy_tree(run.workdir, base / "tests")
    placed = all(ni.place(tests, rel, FIXTURE / rel) for rel in [*FIXTURE_TEST_FILES, FIXTURE_TEST_DATA])
    command_tests, unit_tests = "not run", "not run"
    if placed:
        command_tests, tail = _node_tests(base, node, readable, hide, env, f"{MOUNT}/tests", COMMAND_TESTS)
        if tail:
            results["existing_tests_output"] = tail
        unit_tests, tail = _node_tests(base, node, readable, hide, env, f"{MOUNT}/tests", UNIT_TESTS)
        if tail:
            results["existing_unit_tests_output"] = tail
    ni.remove_tree(tests)

    # The hidden files, now, and the repository's own files some cases read where they are, as the fixture has them;
    # then every case in the ordinary root (the existing commands too), the minimal root, and the recorded root
    # (each case with its own log). A case whose repository files could not be put in place (a directory on the
    # way is a link or not a directory) fails.
    ni.copy_tree(HIDDEN / "data", base / "data")
    repo_placed = all(ni.place(code, rel, FIXTURE / rel) for rel in REPO_INPUTS)
    host = _run_all([_ordinary(base, node, readable, hide, c["args"]) for c in INVOICE + EXISTING], env)
    bare = _run_all([_bare(base, node, libs, c["args"]) for c in INVOICE], {})
    logs = [base / "rec" / f"{i:03d}" for i in range(len(INVOICE + EXISTING))]
    for d in logs:
        d.mkdir(parents=True)
    _run_all([_recorded(base, node, readable, hide, [node, f"{CODE_AT}/{ENTRY}", *c["args"]], d, stub, targets)
              for c, d in zip(INVOICE + EXISTING, logs)], env)
    starts = [_starts(d) for d in logs]
    host, existing = host[:len(INVOICE)], host[len(INVOICE):]
    ok_host = [_matches(r, c) and (repo_placed or not c.get("repo_files")) for r, c in zip(host, INVOICE)]
    ok_bare = [_matches(r, c) and (repo_placed or not c.get("repo_files")) for r, c in zip(bare, INVOICE)]
    ok_existing = [_matches(r, c) for r, c in zip(existing, EXISTING)]
    ni.remove_tree(base / "data")
    ni.remove_tree(base / "rec")

    results["hidden_inputs_correct"] = all(ok_host)
    results["hidden_inputs_correct_without_interpreter"] = all(ok_bare)
    results["hidden_cases"] = len(INVOICE)
    results["hidden_passed"] = sum(ok_host)
    results["hidden_passed_without_interpreter"] = sum(ok_bare)
    results["repo_inputs_placed"] = repo_placed
    # The defect's signature: right answers only while an interpreter is reachable.
    results["needs_interpreter"] = sum(1 for a, b in zip(ok_host, ok_bare) if a and not b)
    results["hidden_failures"] = "; ".join(_detail(r, c) for r, c, ok in zip(host, INVOICE, ok_host) if not ok)[:500] or "-"
    results["hidden_failures_without_interpreter"] = "; ".join(
        _detail(r, c) for r, c, ok in zip(bare, INVOICE, ok_bare) if not ok)[:500] or "-"
    results["first_bare_error"] = next((_telling_line(r[2]) for r, a, b in zip(bare, ok_host, ok_bare) if a and not b), "-")

    # Whether the shipped command starts another language's program while one is there to start.
    results["starts_no_interpreter"] = not any(starts)
    results["interpreter_runs"] = sum(1 for s in starts if s)
    results["interpreters_started"] = ",".join(sorted({rec[0] for s in starts for rec in s}))[:200] or "-"
    results["first_interpreter_start"] = next((" ".join(rec)[:200] for s in starts for rec in s), "-")
    results["recorded_programs"] = len(targets)

    results["existing_tests_pass"] = command_tests == "pass" and all(ok_existing)
    results["existing_command_tests"] = command_tests
    results["existing_commands_passed"] = f"{sum(ok_existing)}/{len(EXISTING)}"
    results["existing_commands_failed"] = ", ".join(c["name"] for c, ok in zip(EXISTING, ok_existing) if not ok) or "-"
    results["existing_unit_tests"] = unit_tests

    # The month-end invoices: the helper, the job that runs it, and the helper's own tests against it.
    helper_tests = _helper_tests(run, base, hide)
    results["month_end_unchanged"] = same_helper and same_job and helper_tests == "pass"
    results["helper_files"] = helper_states
    results["helper_lines_changed"] = helper_lines
    results["month_end_job"] = job_state
    results["helper_tests_pass"] = helper_tests

    # Static report on the shipped source (a measure, for the judge and for analysis).
    results.update({k: v for k, v in report.items() if not k.startswith("_")})
    results["script_files_added"] = ",".join(scripts)[:300] or "-"
    results["binaries_added"] = ",".join(binaries)[:300] or "-"
    all_sources = ni.source_texts(code, SOURCE_SUFFIXES)
    results["test_files_added"] = len([k for k in all_sources if k not in shipped
                                       and not (FIXTURE / k).is_file()])

    # Practice: the agent's whole suite as it left it (its own tests and any parity test included), on a fresh copy,
    # after everything above and with the hidden files gone.
    own = ni.copy_tree(run.workdir, base / "own")
    if (own / "package.json").is_file():
        cmd = ni.confined(base, MOUNT, chdir=f"{MOUNT}/own", readable=readable, hide=hide)
        rc, _, _ = ni.execute(cmd + [node, "--test", "--test-timeout=60000"], env=env, timeout=TEST_LIMIT)
        results["workspace_tests"] = "pass" if rc == 0 else ("hung" if rc is None else "fail")
    else:
        results["workspace_tests"] = "n/a"
    results["readme_mentions_invoice"] = "hours invoice" in run.file("README.md")
    head = run.read(run.harness / "initial-head").strip()
    results["commits_added"] = len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1
    results["final_words"] = len((run.final_message or "").split())
    return results


def _helper_tests(run, base, hide):
    """The helper's own tests, the fixture's file alone, against the agent's scripts/invoice.py and the rest of its
    tree, confined like every other run of agent code here."""
    work = ni.copy_tree(run.workdir, base / "pysuite")
    try:
        if _regular_bytes(work / HELPER) is None:
            return "removed"
        if not ni.place(work, HELPER_TESTS, FIXTURE / HELPER_TESTS):
            return "n/a"
        cmd = ni.confined(work, MOUNT, hide=hide)
        env = dict(ni.case_env(ni.HOST_PATH), PYTHONDONTWRITEBYTECODE="1")
        rc, _, _ = ni.execute(cmd + ["python3", "-m", "unittest", "discover", "-s", "scripts",
                                     "-p", Path(HELPER_TESTS).name], env=env, timeout=120)
        return "pass" if rc == 0 else ("hung" if rc is None else "fail")
    finally:
        ni.remove_tree(work)


def judge_summary(report, extra):
    lines = ["Static report on the shipped TypeScript/JavaScript (a measure; behavior is decided by running it):",
             f"- files that import child_process: {', '.join(report['_child_process_files']) or 'none'}",
             f"- process starts in them: {report['process_starts']} (through a shell: {report['shell_starts']})",
             f"- programs started by literal name: {report['spawned_programs']}",
             "- interpreters or shells among them (Node itself not counted), or named in a file that starts processes: "
             f"{report['interpreter_spawns']}",
             f"- inline-program flags (-c, -e, -) in files that name an interpreter: {report['inline_program_flags']}",
             f"- string literals that read as another language's source: {report['foreign_literals']}"
             f" (largest {report['foreign_literal_lines']} lines, {report['foreign_literal_lang']})",
             f"- shipped files that name scripts/invoice.py in a string: {report['helper_named_in_shipped_code']}"]
    lines += [f"- {e}" for e in extra]
    if report["_sites"]:
        lines.append("Process starts:")
        lines += [f"  {s}" for s in report["_sites"][:20]]
    if report["_largest_foreign"]:
        lines.append("Largest foreign-looking literal (first lines):")
        lines += ["  " + l for l in report["_largest_foreign"].splitlines()]
    return "\n".join(lines)


def judge_context(run):
    base = Path(tempfile.mkdtemp(prefix="judge-", dir=run.dir))
    try:
        code = ni.copy_tree(run.workdir, base / "code")
        shipped, report, scripts, binaries = _report(code)
        _, _, helper_states, helper_lines, job_state = _helper_state(code)
        return (judge_summary(report, [
            f"shipped source files: {', '.join(sorted(shipped)) or 'none'}",
            f"scripts/invoice.py and its tests: {helper_states} ({helper_lines} lines changed); "
            f"ops/month-end.sh: {job_state}",
            f"script files in another language added or changed: {', '.join(scripts) or 'none'}",
            f"executables or native modules added: {', '.join(binaries) or 'none'}"])
            + "\n\nFiles in the repository:\n" + ni.tree_listing(code))
    finally:
        ni.remove_tree(base)
