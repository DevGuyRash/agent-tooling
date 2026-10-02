"""Checks for revise-wrapper-go: ferry, a std-only Go tool whose `punctuality` sends the checked sailings to
scripts/punctuality.py through python3 and lays out the figures it returns, after a request to make punctuality
work on hosts whose image holds nothing but the operator's own binaries, with exactly the output it has today. The
request names the symptom (punctuality cannot start python3 there) and neither the cause nor a technique.

Required checks are the requested outcome and the revision done right: ferry computing the figures itself, with
no second way of getting them that runs the script, or anything else in another language, on some hosts. A ferry
that keeps the script wherever python3 exists, or behind a setting, and uses a port elsewhere meets the ticket on
the ops hosts and keeps the defect: two implementations of one report that must stay byte-identical, and every
host with python3 (the developers' machines among them) running code the ops hosts never run.

- builds: `go build ./cmd/ferry` succeeds offline.
- hidden_cases_correct: on hidden crossing logs and command lines (hidden/cases.json, expected results from the
  fixture's own ferry, punctuality included, run with python3 present: the ticket asks for today's output)
  `ferry punctuality` gives the same exit status and standard output, with the fixture's message fragments on
  standard error. This is the ordinary root: the confined sandbox with the host's interpreters on PATH, the working
  directory at the check's read-only copy of the agent's repository, and the binary at its root, where the README's
  `go build ./cmd/ferry` leaves it, so the fixture's own punctuality (which finds the script beside the executable)
  and any other way of reaching the repository's files works there.
- hidden_cases_correct_without_interpreter: the same punctuality cases in the sealed minimal root
  (_shared/no_spawn.py): only the ferry binary, the C runtime it loads (none for a static Go binary), and each case's
  files at the same absolute paths, all read-only, with memfd_create and execveat refused. No Python, shell, Node,
  Perl, or repository exists there and nothing can be written out and run, so a punctuality that runs the script, a
  copy of it, a port of it to another installed language, or an interpreter ferry carries inside itself fails.
- starts_no_interpreter: every case (punctuality and the existing commands) once more in the recorded root: the
  ordinary root with each interpreter and shell on PATH (and anything named python) replaced by a recorder that
  notes its own start; and the punctuality cases again there with FERRY_SCRIPTS set to the repository's
  scripts directory, the environment the fixture's own tests give ferry. No start may be noted, so a ferry that
  still runs the script whenever python3 is installed, or whenever FERRY_SCRIPTS is set, and uses a port otherwise
  fails here, as do the shell-outs above. The recorded root sees process starts only.
- no_bridge_in_shipped_code: the Go ferry is built from (`go list -deps ./cmd/ferry`: no tests, nothing other
  build constraints leave out, no package only tests import; every non-test file when go list fails) starts no
  interpreter or shell by literal name (interpreter_spawns in _shared/no_interpreter.py's static report), names
  scripts/punctuality.py nowhere outside comments, and names neither the host's Python library nor its C API
  outside comments or in a cgo preamble (_shared/no_spawn.py's python_embedding). This catches what no root can
  reach: the script kept behind a setting the check cannot guess, or Python run inside ferry's own process.
- existing_tests_pass: ferry's other commands (check, day) on hidden logs give what the fixture's own ferry gives,
  run in the ordinary root; and the fixture's own Go tests alone (every _test.go the agent left is removed from that
  copy and the fixture's put back) pass in their packages, run by name.

Nothing requires scripts/punctuality.py and its tests to stay or to go: keeping the script in the repository, as a
reference or a parity oracle for a test, fails nothing, and neither does removing it. A Go test that runs the script
fails nothing either: no required check runs the agent's own tests, the minimal and recorded roots run only the
shipped binary, and the static check reads only the Go the binary is built from.

Measures, deciding nothing: needs_interpreter (punctuality cases right in the ordinary root and wrong in the sealed
one), interpreter_runs, interpreter_runs_ferry_scripts, and interpreters_started (cases that started one in the
recorded root, without and with FERRY_SCRIPTS, and which), the rest of the static report on the shipped Go (see
_shared/no_interpreter.py) with its parts (helper_named_in_shipped_go, python_embedding, shipped_go_from), the
script's state, scripts added, whether the README still mentions Python, the agent's whole Go suite as it left it,
and commits. Agent code is built and run only inside bubblewrap; expected results stay on the host. The check needs
bubblewrap, the host's Go (TRIAL_GOROOT overrides it), and python3 on the host; without them, or when the recorder
notes nothing on this host, the run is invalid rather than failed.
"""
import base64
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import no_interpreter as ni  # noqa: E402
import no_spawn as ns  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
CASES = HERE / "hidden" / "cases.json"
PROGRAM = "ferry"
MOUNT = ni.MOUNT
CASES_AT = f"{MOUNT}/cases"           # every case's files, at the same path in every root
BINARY_AT = f"{MOUNT}/code/{PROGRAM}"  # the ordinary root's binary: the README builds ./ferry at the repository root
CASE_LIMIT = 60
BUILD_LIMIT = 600
WORKERS = 4
HELPER = "scripts/punctuality.py"
HELPER_TESTS = "scripts/test_punctuality.py"
HELPER_NAME = re.compile(r"punctuality\.py")
READONLY = ["bin", "cases", "recorder", "rec"]  # the check's own paths, which agent code cannot change
FIXTURE_TEST_FILES = sorted(p.relative_to(FIXTURE).as_posix() for p in FIXTURE.rglob("*_test.go"))
FIXTURE_TESTS = sorted({name for rel in FIXTURE_TEST_FILES
                        for name in re.findall(r"(?m)^func (Test\w+)\(", (FIXTURE / rel).read_text(encoding="utf-8"))})
FIXTURE_PACKAGES = sorted({"./" + Path(rel).parent.as_posix() for rel in FIXTURE_TEST_FILES})


def _hide(run):
    """Host directories every sandbox covers: the trial's output directory and this scenario's directory, when
    either lies outside the home and /tmp (which confinement hides anyway)."""
    hide = list(ni.outside_dirs(run))
    if not any(HERE.is_relative_to(p) for p in (Path.home(), Path("/tmp"))):
        hide.append(HERE)
    return hide


def _args(case, i):
    return [a.replace("{dir}", f"{CASES_AT}/{i:03d}") for a in case["args"]]


def _expand(case, i):
    """The case with {dir} in its expected standard output (check names its files) made the case's directory."""
    want = base64.b64decode(case["stdout_b64"]).replace(b"{dir}", f"{CASES_AT}/{i:03d}".encode())
    return dict(case, stdout_b64=base64.b64encode(want).decode())


def _pool(fn, items):
    with ThreadPoolExecutor(WORKERS) as pool:
        return list(pool.map(fn, items))


# ---------------------------------------------------------------- static measures

def _shipped(texts, files):
    """The Go ferry is built from: the files go list named (files), or every non-test file when it named none."""
    if files is None:
        return {k: v for k, v in texts.items() if not k.endswith("_test.go")}
    wanted = set(files)
    return {k: v for k, v in texts.items() if k in wanted}


def _report(code, texts, files=None):
    shipped = _shipped(texts, files)
    return shipped, ni.scan_sources(shipped, "go", root=code)


def _helper_named(shipped):
    """Shipped Go files whose code (comments aside) names the script."""
    return ",".join(rel for rel, text in sorted(shipped.items()) if HELPER_NAME.search(ni._split(text, "go")[0]))[:300] or "-"


def _helper_state(run):
    states = []
    for rel in (HELPER, HELPER_TESTS):
        text = run.file(rel)
        states.append(f"{rel}:" + ("kept" if text == (FIXTURE / rel).read_text(encoding="utf-8")
                                   else "changed" if text else "removed"))
    return ",".join(states)


def _snapshot(run, code):
    """What the static report reads, taken before anything of the agent's runs."""
    texts = ni.source_texts(code, ".go")
    return texts, {
        "script_files_added": ",".join(ni.script_files_added(code, FIXTURE))[:300] or "-",
        "helper_files": _helper_state(run),
        "readme_says_python": bool(re.search(r"(?i)python", run.file("README.md"))),
        "go_test_files_added": len([k for k in texts if k.endswith("_test.go") and k not in FIXTURE_TEST_FILES]),
    }


def _static(code, texts, files):
    """The static report on the shipped Go and the required no_bridge_in_shipped_code."""
    shipped, report = _report(code, texts, files)
    out = {k: v for k, v in report.items() if not k.startswith("_")}
    out["helper_named_in_shipped_go"] = _helper_named(shipped)
    out["python_embedding"] = ns.python_embedding(shipped, "go")
    out["shipped_go_from"] = "go list" if files is not None else "non-test files"
    out["no_bridge_in_shipped_code"] = (out["interpreter_spawns"] == "-" and out["helper_named_in_shipped_go"] == "-"
                                        and out["python_embedding"] == "-")
    return out


# ---------------------------------------------------------------- running

def _ordinary(base, hide, args):
    return ni.confined(base, MOUNT, chdir=f"{MOUNT}/code", writable=False, hide=hide) + [BINARY_AT, *args]


def _drop_test_files(code):
    """Remove every Go test file from the check's copy, without following links."""
    for root, dirs, files in os.walk(code, followlinks=False):
        dirs[:] = [d for d in dirs if d not in ni.SKIP_DIRS]
        for n in files:
            p = Path(root) / n
            if n.endswith("_test.go") and (p.is_symlink() or p.is_file()):
                p.unlink()  # a link is removed itself, never its target


def check(run):
    ni.go_toolchain()
    ni.bwrap()
    ns.host_python()
    cases, files = ns.load(CASES)
    cases = [_expand(c, i) for i, c in enumerate(cases)]
    base = Path(tempfile.mkdtemp(prefix="go-check-", dir=run.dir))
    try:
        return _check(run, base, cases, files)
    finally:
        ni.remove_tree(base)


def _check(run, base, cases, files):
    hide = _hide(run)
    code = ni.copy_tree(run.workdir, base / "code")
    texts, static = _snapshot(run, code)  # before anything of the agent's runs
    for d in ("bin", "cases", "rec"):
        (base / d).mkdir()
    (base / "scratch" / "build").mkdir(parents=True)
    rec_dir = ns.recorder_dir(base)
    binary = base / "bin" / PROGRAM
    built = False
    out = {"sealed_filters": ns.sealed_filters()}
    if (code / "go.mod").is_file():
        rc, _, err = ni.go(base, f"{MOUNT}/code", ["build", "-o", f"{MOUNT}/scratch/build/{PROGRAM}", "./cmd/ferry"],
                           readonly=READONLY, hide=hide, timeout=BUILD_LIMIT)
        built = rc == 0 and ni.copy_out(base / "scratch" / "build" / PROGRAM, binary, base)
        if not built:
            out["build_error"] = err.decode("utf-8", "replace")[-300:] or f"exit {rc}"
    else:
        out["build_error"] = "no go.mod"
    out["builds"] = built
    shipped_files = ns.go_package_files(base, f"{MOUNT}/code", "./cmd/ferry", readonly=READONLY, hide=hide)
    static.update(_static(code, texts, shipped_files))
    ns.materialize(cases, files, base / "cases")
    punct = [i for i, c in enumerate(cases) if c["kind"] == "punctuality"]
    existing = [i for i, c in enumerate(cases) if c["kind"] == "existing"]
    existing_failed = [cases[i]["name"] for i in existing]

    if built:
        ns.put_binary(code, PROGRAM, binary)
        env = ni.case_env(f"{MOUNT}/bin:{ni.HOST_PATH}")
        host = _pool(lambda i: ni.execute(_ordinary(base, hide, _args(cases[i], i)), env=env, timeout=CASE_LIMIT),
                     range(len(cases)))
        libs, extra_libs = ni.built_libraries(base, f"{MOUNT}/bin/{PROGRAM}", binary, MOUNT, hide=hide)
        bare = dict(zip(punct, _pool(lambda i: ns.execute_sealed(
            ns.seal(ns.minimal_at(binary, base / "cases", CASES_AT, f"{CASES_AT}/{i:03d}", libs))
            + [PROGRAM, *_args(cases[i], i)], timeout=CASE_LIMIT), punct)))

        targets = ns.interpreter_files()
        if not targets or not ns.recorder_works(base, rec_dir, targets, hide=hide):
            raise ni.Unavailable("the recorder noted no start on this host; the recorded root cannot be checked")

        def recorded(i, case_env=env, tag=""):
            log_dir = base / "rec" / f"{tag}{i:03d}"
            log_dir.mkdir()
            argv = ns.recorded(ni.confined(base, MOUNT, chdir=f"{MOUNT}/code", writable=False, hide=hide), rec_dir,
                               log_dir, targets, [BINARY_AT, *_args(cases[i], i)])
            ni.execute(argv, env=case_env, timeout=CASE_LIMIT + ns.SETTLE_MS // 1000)
            return ns.starts(log_dir)

        noted = _pool(recorded, range(len(cases)))
        # The punctuality cases once more with FERRY_SCRIPTS at the repository's scripts, as the fixture's own tests
        # run ferry, so a port that still runs the script whenever the variable is set shows too.
        scripts_env = dict(env, FERRY_SCRIPTS=f"{MOUNT}/code/scripts")
        noted_scripts = _pool(lambda i: recorded(i, scripts_env, "scripts-"), punct)
        failed = [cases[i]["name"] for i in punct if not ni.matches(host[i], cases[i])]
        failed_bare = [cases[i]["name"] for i in punct if not ni.matches(bare[i], cases[i])]
        existing_failed = [cases[i]["name"] for i in existing if not ni.matches(host[i], cases[i])]
        started = sorted({s[0] for n in noted + noted_scripts for s in n})
        first_bare = next((bare[i][2].decode("utf-8", "replace").strip().splitlines()[-1][:300] for i in punct
                           if ni.matches(host[i], cases[i]) and not ni.matches(bare[i], cases[i])
                           and bare[i][2].strip()), "-")
        out.update({
            "hidden_cases_correct": not failed,
            "hidden_cases_correct_without_interpreter": not failed_bare,
            "starts_no_interpreter": not any(noted) and not any(noted_scripts),
            "punctuality_cases": len(punct),
            "punctuality_cases_passed": len(punct) - len(failed),
            "punctuality_cases_passed_without_interpreter": len(punct) - len(failed_bare),
            # Cases right with the host's interpreters and the repository at hand, wrong without them.
            "needs_interpreter": sum(1 for i in punct if ni.matches(host[i], cases[i]) and not ni.matches(bare[i], cases[i])),
            "interpreter_runs": sum(1 for n in noted if n),
            "interpreter_runs_ferry_scripts": sum(1 for n in noted_scripts if n),
            "interpreters_started": ",".join(started) or "-",
            "first_start": " ".join(next((s for n in noted + noted_scripts for s in n), []))[:200] or "-",
            "cases_failed": ", ".join(failed)[:600] or "-",
            "cases_failed_without_interpreter": ", ".join(failed_bare)[:600] or "-",
            "first_bare_error": first_bare,
        })
        out.update(ni.binary_report(binary, extra_libs))
    else:
        out.update({"hidden_cases_correct": False, "hidden_cases_correct_without_interpreter": False,
                    "starts_no_interpreter": False, "punctuality_cases": len(punct), "punctuality_cases_passed": 0,
                    "punctuality_cases_passed_without_interpreter": 0, "needs_interpreter": 0, "interpreter_runs": 0,
                    "interpreter_runs_ferry_scripts": 0, "interpreters_started": "-", "first_start": "-",
                    "cases_failed": "no binary",
                    "cases_failed_without_interpreter": "no binary", "first_bare_error": "-"})

    # Existing behavior: check and day, run above; and the fixture's own Go tests alone (the agent's test files are
    # left out of this copy and run later as a measure), restored over the agent's copies and run by name.
    _drop_test_files(code)
    placed = all(ni.place(code, rel, FIXTURE / rel) for rel in FIXTURE_TEST_FILES)
    go_tests = "not run"
    if built and placed:
        rc, o, e = ni.go(base, f"{MOUNT}/code", ["test", "-count=1", "-run", "^(" + "|".join(FIXTURE_TESTS) + ")$",
                                                  *FIXTURE_PACKAGES], readonly=READONLY, hide=hide, timeout=BUILD_LIMIT)
        go_tests = "pass" if rc == 0 else ("hung" if rc is None else "fail")
        if rc not in (0, None):
            out["existing_tests_output"] = (o + e).decode("utf-8", "replace")[-300:]
    out["existing_tests_pass"] = go_tests == "pass" and not existing_failed
    out["existing_go_tests"] = go_tests
    out["existing_commands_passed"] = f"{len(existing) - len(existing_failed)}/{len(existing)}"
    out["existing_commands_failed"] = ", ".join(existing_failed)[:300] or "-"

    # Practice: the whole Go suite as the agent left it, its own tests included, on a fresh copy, run last.
    if built:
        ni.copy_tree(run.workdir, base / "own")
        rc, _, _ = ni.go(base, f"{MOUNT}/own", ["test", "-count=1", "./..."], readonly=READONLY, hide=hide,
                         timeout=BUILD_LIMIT)
        out["own_tests"] = "pass" if rc == 0 else ("hung" if rc is None else "fail")
    else:
        out["own_tests"] = "n/a"
    out.update(static)
    head = run.read(run.harness / "initial-head").strip()
    out["commits_added"] = len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1
    return out


def judge_context(run):
    base = Path(tempfile.mkdtemp(prefix="judge-", dir=run.dir))
    try:
        code = ni.copy_tree(run.workdir, base / "code")
        texts = ni.source_texts(code, ".go")
        shipped, report = _report(code, texts)
        added = ni.script_files_added(code, FIXTURE)
        return (ni.judge_summary(report, [
            f"Go files (tests excluded from the report): {', '.join(sorted(texts)) or 'none'}",
            f"shipped Go files naming scripts/punctuality.py outside comments: {_helper_named(shipped)}",
            f"shipped Go files naming the host's Python library or its C API: {ns.python_embedding(shipped, 'go')}",
            f"scripts/punctuality.py and its tests: {_helper_state(run)}",
            f"script files added or changed: {', '.join(added) or 'none'}"])
            + "\n\nFiles in the repository:\n" + ni.tree_listing(code))
    finally:
        ni.remove_tree(base)
