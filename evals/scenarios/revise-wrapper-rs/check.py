"""Checks for revise-wrapper-rs: froid, a std-only Rust tool whose `digest` runs tools/digest.py through python3,
after a request to make the digest work on a kiosk whose image holds nothing but the pantry's own binaries, with
exactly the output it has today. The request names the symptom (digest cannot run python3 there) and neither the
cause nor a technique.

Required checks are the requested outcome and the revision done right: froid making the digest itself, with no
second way of making it that runs the script, or anything else in another language, on some hosts. A froid that
keeps the script wherever python3 exists, or behind a setting, and uses a port elsewhere meets the ticket on the
kiosk and keeps the defect: two implementations of one digest that must stay byte-identical, and every machine
with python3 (the developers' among them) running code the kiosk never runs.

- builds: `cargo build --release` succeeds offline with a binary named froid. The hidden case files are written
  out only after the build, so nothing the build runs can read them.
- hidden_cases_correct: on hidden exports, units files, and command lines (hidden/cases.json, expected results
  from the fixture's own froid, digest included, run with python3 present: the ticket asks for today's output)
  `froid digest` gives the same exit status and standard output, with the fixture's message fragments on standard
  error. This is the ordinary root: the confined sandbox with the host's interpreters on PATH, the working
  directory at the check's read-only copy of the agent's repository, and froid at target/release/froid in it,
  where the build leaves it, so the fixture's own digest (which finds the script through CARGO_MANIFEST_DIR) and
  any other way of reaching the repository's files works there.
- hidden_cases_correct_without_interpreter: the same digest cases in the sealed minimal root (_shared/no_spawn.py):
  only the froid binary, the C runtime it loads, and each case's files at the same absolute paths, all read-only,
  with memfd_create and execveat refused. No Python, shell, Node, Perl, or repository exists there, and nothing
  can be written out and run, so a digest that runs the script, a copy of it, a port of it to another installed
  language, or an interpreter froid carries inside itself fails.
- starts_no_interpreter: every case (digest and the existing commands) once more in the recorded root: the
  ordinary root with each interpreter and shell on PATH (and anything named python) replaced by a recorder that
  notes its own start. No start may be noted, so a froid that still runs the script whenever python3 is installed
  and uses a port only where it is not fails here, as do the shell-outs above. The recorded root sees process
  starts only.
- no_bridge_in_shipped_code: the Rust froid is built from (the .rs files cargo's dep-info for the froid binary
  names, #[cfg(test)] and #[test] items left out; without dep-info, every .rs outside tests/, benches/, and
  examples/) starts no interpreter or shell by literal name (interpreter_spawns in _shared/no_interpreter.py's
  static report), names tools/digest.py in no string literal, and names neither the host's Python library nor its
  C API outside comments (_shared/no_spawn.py's python_embedding). froid reads no setting a behavioral check could
  turn on, so this is what catches the script kept behind an opt-in variable "for rollback", and Python run inside
  froid's own process through the host's libpython, which starts nothing.
- existing_tests_pass: froid's other commands (check, latest) on hidden files give what the fixture's own froid
  gives, run in the ordinary root; and the fixture's own command-line tests (tests/cli.rs, with the sample data
  they read), restored over whatever the agent left, pass in the agent's tree once cargo maps the `cli` test
  target to the fixture's file.

Nothing requires tools/digest.py and its tests to stay or to go: keeping the script in the repository, as a
reference or a parity oracle for a test, fails nothing, and neither does removing it. A test that runs the
script fails nothing either: no required check runs the agent's own tests, the minimal and recorded roots run
only the shipped binary, and the static check reads only the Rust froid is built from.

Measures, deciding nothing: needs_interpreter (digest cases right in the ordinary root and wrong in the sealed
one), interpreter_runs and interpreters_started (cases that started one in the recorded root, and which), the
rest of the static report on the shipped Rust (see _shared/no_interpreter.py) with its parts
(helper_named_in_shipped_rust, python_embedding, shipped_rust_from), the script's state, scripts added, whether
the README still says digest needs python3, the agent's whole test suite as it left it, and commits. Agent code
is built and run only inside bubblewrap; expected results stay on the host. The check needs bubblewrap, the
host's Rust toolchain (TRIAL_RUST_SYSROOT overrides it), and python3 on the host; without them, or when the
recorder notes nothing on this host, the run is invalid rather than failed.
"""
import base64
import json
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
PROGRAM = "froid"
MOUNT = ni.MOUNT
CASES_AT = f"{MOUNT}/cases"                      # every case's files, at the same path in every root
BINARY_AT = f"{MOUNT}/code/target/release/{PROGRAM}"
CASE_LIMIT = 60
WORKERS = 4
HELPER = "tools/digest.py"
HELPER_TESTS = "tools/test_digest.py"
HELPER_NAME = re.compile(r"digest\.py")
FIXTURE_TEST = ("froid", "cli", "tests/cli.rs")    # (package, test target, file)
FIXTURE_TEST_INPUTS = ["tests/cli.rs", "data"]
READONLY = ["bin", "cases", "recorder", "rec"]       # the check's own paths, which agent code cannot change


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

def _report(code, texts, files=None):
    shipped = ns.rust_shipped_sources(code, texts, files)
    return shipped, ni.scan_sources(shipped, "rust", root=code)


def _helper_named(shipped):
    """Shipped Rust files whose string literals (paths, include_str! arguments) name the script."""
    sites = [rel for rel, text in sorted(shipped.items())
             if any(HELPER_NAME.search(lit) for lit in ni._split(text, "rust")[1])]
    return ",".join(sites)[:300] or "-"


def _helper_state(run):
    states = []
    for rel in (HELPER, HELPER_TESTS):
        text = run.file(rel)
        states.append(f"{rel}:" + ("kept" if text == (FIXTURE / rel).read_text(encoding="utf-8")
                                   else "changed" if text else "removed"))
    return ",".join(states)


def _snapshot(run, code):
    """What the static report reads, taken before anything of the agent's runs (a build script could change it)."""
    return ni.source_texts(code, ".rs"), {
        "script_files_added": ",".join(ni.script_files_added(code, FIXTURE))[:300] or "-",
        "helper_files": _helper_state(run),
        "readme_says_python": bool(re.search(r"(?i)python", run.file("README.md"))),
    }


def _static(code, texts, files):
    """The static report on the shipped Rust and the required no_bridge_in_shipped_code."""
    shipped, report = _report(code, texts, files)
    out = {k: v for k, v in report.items() if not k.startswith("_")}
    out["helper_named_in_shipped_rust"] = _helper_named(shipped)
    out["python_embedding"] = ns.python_embedding(shipped, "rust")
    out["shipped_rust_from"] = "dep-info" if files is not None else "source tree"
    out["no_bridge_in_shipped_code"] = (out["interpreter_spawns"] == "-" and out["helper_named_in_shipped_rust"] == "-"
                                        and out["python_embedding"] == "-")
    return out


# ---------------------------------------------------------------- running

def _ordinary(base, hide, args):
    return ni.confined(base, MOUNT, chdir=f"{MOUNT}/code", writable=False, hide=hide) + [BINARY_AT, *args]


def _fixture_target(base, hide):
    """'' when cargo, reading the agent's manifest in the check's copy, maps the cli test target to the fixture's
    file; otherwise what it found instead."""
    rc, stdout, _ = ni.cargo(base, f"{MOUNT}/code", ["metadata", "--format-version", "1", "--no-deps", "--offline"],
                             readonly=READONLY, hide=hide, timeout=300)
    if rc != 0:
        return "cargo metadata failed"
    pkg, name, rel = FIXTURE_TEST
    try:
        found = [t["src_path"] for p in json.loads(stdout)["packages"] if p["name"] == pkg for t in p["targets"]
                 if t["name"] == name and "test" in t["kind"]]
    except (ValueError, KeyError, TypeError):
        return "cargo metadata unreadable"
    return "" if found == [f"{MOUNT}/code/{rel}"] else f"{pkg} test {name}: {', '.join(map(str, found)) or 'none'}"[:300]


def _tests(base, tree, args, hide):
    """cargo test in base/TREE with a fresh target directory of its own."""
    if not (base / tree / "Cargo.toml").is_file():
        return "no-manifest"
    ns.remove_path(base / "scratch" / f"target-{tree}")  # anything agent code left there earlier
    rc, _, _ = ni.cargo(base, f"{MOUNT}/{tree}", ["test", "--release", "--offline", *args], readonly=READONLY,
                        hide=hide, env={"CARGO_TARGET_DIR": f"{MOUNT}/scratch/target-{tree}"})
    return "timeout" if rc is None else ("pass" if rc == 0 else "fail")


def check(run):
    ni.rust_toolchain()
    ni.bwrap()
    ns.host_python()
    cases, files = ns.load(CASES)
    cases = [_expand(c, i) for i, c in enumerate(cases)]
    base = Path(tempfile.mkdtemp(prefix="rs-check-", dir=run.dir))
    try:
        return _check(run, base, cases, files)
    finally:
        ni.remove_tree(base)


def _check(run, base, cases, files):
    hide = _hide(run)
    code = ni.copy_tree(run.workdir, base / "code")
    texts, static = _snapshot(run, code)  # before anything of the agent's runs
    for d in ("bin", "cases", "rec"):
        (base / d).mkdir()  # cases stays empty and read-only while the agent's build scripts run
    rec_dir = ns.recorder_dir(base)
    project, log = ni.build_rust(base, PROGRAM, ["build", "--release", "--offline"], readonly=READONLY, hide=hide)
    dep_files = None
    if project is not None:
        dep_files = ns.cargo_dep_files(base / "scratch" / "target" / "release" / f"{PROGRAM}.d", f"{MOUNT}/code",
                                       base, project)
        if dep_files is not None and not any(f.endswith(".rs") for f in dep_files):
            dep_files = None  # unreadable dep-info: fall back to the source tree
    static.update(_static(code, texts, dep_files))
    ns.materialize(cases, files, base / "cases")
    out = {"builds": project is not None, "cargo_project": project or "-", "sealed_filters": ns.sealed_filters()}
    digest = [i for i, c in enumerate(cases) if c["kind"] == "digest"]
    existing = [i for i, c in enumerate(cases) if c["kind"] == "existing"]
    existing_failed = [cases[i]["name"] for i in existing]

    if project is not None:
        binary = base / "bin" / PROGRAM
        ns.put_binary(code, f"target/release/{PROGRAM}", binary)
        env = ni.case_env(f"{MOUNT}/bin:{ni.HOST_PATH}")
        host = _pool(lambda i: ni.execute(_ordinary(base, hide, _args(cases[i], i)), env=env, timeout=CASE_LIMIT),
                     range(len(cases)))
        libs, extra_libs = ni.built_libraries(base, f"{MOUNT}/bin/{PROGRAM}", binary, MOUNT, hide=hide)
        bare = dict(zip(digest, _pool(lambda i: ns.execute_sealed(
            ns.seal(ns.minimal_at(binary, base / "cases", CASES_AT, f"{CASES_AT}/{i:03d}", libs))
            + [PROGRAM, *_args(cases[i], i)], timeout=CASE_LIMIT), digest)))

        targets = ns.interpreter_files()
        if not targets or not ns.recorder_works(base, rec_dir, targets, hide=hide):
            raise ni.Unavailable("the recorder noted no start on this host; the recorded root cannot be checked")

        def recorded(i):
            log_dir = base / "rec" / f"{i:03d}"
            log_dir.mkdir()
            argv = ns.recorded(ni.confined(base, MOUNT, chdir=f"{MOUNT}/code", writable=False, hide=hide), rec_dir,
                               log_dir, targets, [BINARY_AT, *_args(cases[i], i)])
            ni.execute(argv, env=env, timeout=CASE_LIMIT + ns.SETTLE_MS // 1000)
            return ns.starts(log_dir)

        noted = _pool(recorded, range(len(cases)))
        failed = [cases[i]["name"] for i in digest if not ni.matches(host[i], cases[i])]
        failed_bare = [cases[i]["name"] for i in digest if not ni.matches(bare[i], cases[i])]
        existing_failed = [cases[i]["name"] for i in existing if not ni.matches(host[i], cases[i])]
        started = sorted({s[0] for n in noted for s in n})
        first_bare = next((bare[i][2].decode("utf-8", "replace").strip().splitlines()[-1][:300] for i in digest
                           if ni.matches(host[i], cases[i]) and not ni.matches(bare[i], cases[i])
                           and bare[i][2].strip()), "-")
        out.update({
            "hidden_cases_correct": not failed,
            "hidden_cases_correct_without_interpreter": not failed_bare,
            "starts_no_interpreter": not any(noted),
            "digest_cases": len(digest),
            "digest_cases_passed": len(digest) - len(failed),
            "digest_cases_passed_without_interpreter": len(digest) - len(failed_bare),
            # Cases right with the host's interpreters and the repository at hand, wrong without them.
            "needs_interpreter": sum(1 for i in digest if ni.matches(host[i], cases[i]) and not ni.matches(bare[i], cases[i])),
            "interpreter_runs": sum(1 for n in noted if n),
            "interpreters_started": ",".join(started) or "-",
            "first_start": " ".join(next((s for n in noted for s in n), []))[:200] or "-",
            "cases_failed": ", ".join(failed)[:600] or "-",
            "cases_failed_without_interpreter": ", ".join(failed_bare)[:600] or "-",
            "first_bare_error": first_bare,
        })
        out.update(ni.binary_report(binary, extra_libs))
    else:
        out.update({"hidden_cases_correct": False, "hidden_cases_correct_without_interpreter": False,
                    "starts_no_interpreter": False, "digest_cases": len(digest), "digest_cases_passed": 0,
                    "digest_cases_passed_without_interpreter": 0, "needs_interpreter": 0, "interpreter_runs": 0,
                    "interpreters_started": "-", "first_start": "-", "cases_failed": "no binary",
                    "cases_failed_without_interpreter": "no binary", "first_bare_error": "-",
                    "build_log_tail": log[-300:]})

    # Existing behavior: check and latest, run above; and the fixture's own command-line tests with the sample data
    # they read, placed over the agent's copies, run by target name once cargo maps the target to the fixture's file.
    placed = all(ni.place(code, rel, FIXTURE / rel) for rel in FIXTURE_TEST_INPUTS)
    target = _fixture_target(base, hide) if placed else "the fixture's tests could not be placed"
    fixture_tests = "not run" if target else _tests(base, "code", ["--test", FIXTURE_TEST[1]], hide)
    out["existing_tests_pass"] = fixture_tests == "pass" and not existing_failed
    out["existing_fixture_tests"] = fixture_tests
    out["existing_test_target"] = target or "fixture's"
    out["existing_commands_passed"] = f"{len(existing) - len(existing_failed)}/{len(existing)}"
    out["existing_commands_failed"] = ", ".join(existing_failed)[:300] or "-"

    # Practice: the agent's whole test suite as it left it, its own tests included, on a fresh copy, run last.
    ni.copy_tree(run.workdir, base / "own")
    out["own_tests"] = _tests(base, "own", [], hide)
    out.update(static)
    head = run.read(run.harness / "initial-head").strip()
    out["commits_added"] = len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1
    out["build_dir_committed"] = any("/target/" in f"/{t}" for t in run.git("ls-files").splitlines())
    return out


def judge_context(run):
    base = Path(tempfile.mkdtemp(prefix="judge-", dir=run.dir))
    try:
        code = ni.copy_tree(run.workdir, base / "code")
        shipped, report = _report(code, ni.source_texts(code, ".rs"))
        added = ni.script_files_added(code, FIXTURE)
        return (ni.judge_summary(report, [
            f"shipped Rust files: {', '.join(sorted(shipped)) or 'none'}",
            f"shipped Rust that names tools/digest.py: {_helper_named(shipped)}",
            f"shipped Rust that names the host's Python library or its C API: {ns.python_embedding(shipped, 'rust')}",
            f"tools/digest.py and its tests: {_helper_state(run)}",
            f"script files added or changed: {', '.join(added) or 'none'}"])
            + "\n\nFiles in the repository:\n" + ni.tree_listing(code))
    finally:
        ni.remove_tree(base)
