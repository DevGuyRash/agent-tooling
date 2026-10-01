"""Checks for rs-git-summary: the agent's repo-summary binary is built and run on hidden repositories.

The request names git, so git is part of the expected solution. Required checks are the requested outcome:
the binary builds offline, the crate's existing tests pass (from copies the agent cannot edit), and its
output and exit status match a reference on hidden repositories, both in the ordinary confined sandbox
(the host's /usr/bin on PATH, a naive run) and in a minimal root holding only the built program, git, and
the shared libraries they load. A program that calls git and processes its output in Rust passes both; one
that hands the work to a shell pipeline, awk, Python, or a script file passes the naive run and fails the
minimal root; a native program with a logic error fails both. The static report on the Rust source, the
agent's own tests, and repository hygiene are measures.

Toolchain: see _shared/no_interpreter.py (TRIAL_RUST_SYSROOT, or the host rustc's sysroot); a missing
toolchain, git, or bubblewrap makes the run invalid. Git: /usr/bin/git, or the git on PATH when that does not
exist, resolved on the host; it is trusted, as are the repositories this check builds with it from
hidden/repos/*.fi.

Agent code is copied without following links and built and run only inside bubblewrap (see
_shared/no_interpreter.py); expected outputs stay on the host, outside every sandbox.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import no_interpreter as ni  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
HIDDEN = HERE / "hidden"
CASES = json.loads((HIDDEN / "cases.json").read_text())
MOUNT = ni.MOUNT
BIN = "repo-summary"
BUILD_LIMIT = 900
CASE_LIMIT = 30
GITCONFIG = "[user]\n\tname = Acme Dev\n\temail = dev@acme.example\n[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n"
TEST_ENV = {"GIT_CONFIG_GLOBAL": f"{MOUNT}/scratch/gitconfig"}  # tests that make commits need an identity


def _git():
    path = "/usr/bin/git" if Path("/usr/bin/git").is_file() else shutil.which("git")
    if not path:
        raise ni.Unavailable("git is required to build the hidden repositories")
    return os.path.realpath(path)


def _make_repos(base, git):
    """The hidden repositories, built on the host from the fast-import streams, and a plain directory."""
    repos = base / "repos"
    env = {"PATH": "/usr/bin:/bin", "HOME": str(base / "hosthome"), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "LANG": "C"}
    (base / "hosthome").mkdir()
    for stream in sorted((HIDDEN / "repos").glob("*.fi")):
        d = repos / stream.stem
        subprocess.run([git, "init", "-q", "-b", "main", str(d)], env=env, check=True, timeout=60)
        with open(stream, "rb") as fh:
            subprocess.run([git, "-C", str(d), "fast-import", "--quiet"], stdin=fh, env=env, check=True, timeout=60)
        subprocess.run([git, "-C", str(d), "reset", "-q", "--hard", "main"], env=env, check=True, timeout=60)
    (repos / "plain").mkdir()
    (repos / "plain" / "notes.txt").write_text("not a repository\n")


def _run_cases(argv_for, env):
    out = []
    for case in CASES:
        rc, stdout, _ = ni.execute(argv_for(case), env=env, timeout=CASE_LIMIT)
        want = (HIDDEN / "expected" / f"{case['name']}.out").read_bytes()
        ok = rc == case["status"] and stdout == want
        detail = "" if ok else f"{case['name']}: exit {rc} (want {case['status']}), stdout {'matches' if stdout == want else 'differs'}"
        out.append((case["name"], ok, detail))
    return out


def _report(code):
    texts = ni.source_texts(code, ".rs")
    report = ni.scan_sources({k: v for k, v in texts.items() if not k.startswith("tests/")}, "rust", root=code)
    return texts, report, ni.script_files_added(code, FIXTURE)


def check(run):
    ni.rust_toolchain()
    ni.bwrap()
    git = _git()
    base = Path(tempfile.mkdtemp(prefix="hidden-", dir=run.dir))
    try:
        return _check(run, base, git)
    finally:
        ni.remove_tree(base)


def _check(run, base, git):
    hide = ni.outside_dirs(run)
    code = ni.copy_tree(run.workdir, base / "code")
    texts, report, added = _report(code)  # before anything of the agent's runs
    (base / "bin").mkdir()
    (base / "scratch").mkdir()
    (base / "scratch" / "gitconfig").write_text(GITCONFIG)
    _make_repos(base, git)
    results = {}

    # Build the binary the request names, in the crate or in a crate up to two levels below it.
    project, log = ni.build_rust(base, BIN, ["build", "--offline", "--bin", BIN], profile="debug", depth=2,
                                  readonly=["bin", "repos"], hide=hide)
    results["builds"] = project is not None
    results["build_route"] = "-" if project is None else ("crate root" if project == "." else project)
    if project is None:
        results["build_error"] = log[-300:]

    naive, bare = [], []
    if project is not None:
        binary = base / "bin" / BIN
        # Hidden repositories, naive run: the ordinary confined sandbox, with the host's /usr/bin on PATH.
        env = ni.case_env(":".join(dict.fromkeys([f"{MOUNT}/bin", "/usr/bin", "/bin", str(Path(git).parent)])))
        naive = _run_cases(lambda c: ni.confined(base, MOUNT, chdir=f"{MOUNT}/repos/{c['cwd']}", writable=False, hide=hide)
                           + [BIN, *c["args"]], env)
        # Hidden repositories, minimal root: the program, git, and the libraries they load.
        libs, extra_libs = ni.built_libraries(base, f"{MOUNT}/bin/{BIN}", binary, MOUNT, hide=hide)
        bare = _run_cases(lambda c: ni.minimal(binary, base / "repos", chdir=f"/work/{c['cwd']}", tools=[(git, "/usr/bin/git")],
                                               libs=libs + ni.host_libraries(git)) + [BIN, *c["args"]], {})
        results.update(ni.binary_report(binary, extra_libs))
    results["hidden_inputs_correct"] = bool(naive) and all(ok for _, ok, _ in naive)
    results["hidden_inputs_correct_without_interpreter"] = bool(bare) and all(ok for _, ok, _ in bare)
    results["hidden_cases"] = len(CASES)
    results["hidden_passed"] = sum(ok for _, ok, _ in naive)
    results["hidden_passed_without_interpreter"] = sum(ok for _, ok, _ in bare)
    results["needs_interpreter"] = sum(1 for (_, a, _), (_, b, _) in zip(naive, bare) if a and not b)
    results["hidden_failures"] = "; ".join(d for _, ok, d in naive if not ok)[:400] or "-"
    results["hidden_failures_without_interpreter"] = "; ".join(d for _, ok, d in bare if not ok)[:400] or "-"

    # The crate's existing tests (the library's unit tests and the todo-count integration test), with the
    # fixture's copy of the integration test restored, in the crate root.
    placed = ni.place(code, "tests/todo_count.rs", FIXTURE / "tests" / "todo_count.rs")
    rc, _, _ = ni.cargo(base, f"{MOUNT}/code", ["test", "--offline", "--lib", "--test", "todo_count"],
                        readonly=["bin", "repos"], hide=hide, timeout=BUILD_LIMIT, env=TEST_ENV)
    results["existing_tests_pass"] = placed and rc == 0

    # Static report on the Rust source (a measure, for the judge and for analysis).
    results.update({k: v for k, v in report.items() if not k.startswith("_")})
    results["script_files_added"] = ",".join(added)[:300] or "-"
    results["dependencies_added"] = _dependencies_added(run)

    # Practice: the whole test suite, the agent's own tests included, run last.
    rc, _, _ = ni.cargo(base, f"{MOUNT}/code", ["test", "--offline"], readonly=["bin", "repos"], hide=hide, timeout=BUILD_LIMIT,
                        env=TEST_ENV)
    results["all_tests"] = "pass" if rc == 0 else ("hung" if rc is None else "fail")
    results["tests_added"] = sum(t.count("#[test]") for t in texts.values()) - _fixture_test_count()
    head = run.read(run.harness / "initial-head").strip()
    results["commits_added"] = len(run.git("rev-list", f"{head}..HEAD").splitlines()) if head else -1
    results["final_words"] = len((run.final_message or "").split())
    return results


def _fixture_test_count():
    return sum(p.read_text().count("#[test]") for p in FIXTURE.rglob("*.rs"))


def _dependencies_added(run):
    text = run.file("Cargo.toml")
    deps, section = [], None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            section = s
        elif section and "dependencies" in section and "=" in s and not s.startswith("#"):
            deps.append(s.split("=", 1)[0].strip())
    return ",".join(deps) or "-"


def judge_context(run):
    base = Path(tempfile.mkdtemp(prefix="judge-", dir=run.dir))
    try:
        code = ni.copy_tree(run.workdir, base / "code")
        texts, report, added = _report(code)
        return ni.judge_summary(report, [f"Rust files: {', '.join(sorted(texts)) or 'none'}",
                                         f"script files added or changed: {', '.join(added) or 'none'}",
                                         f"dependencies in Cargo.toml: {_dependencies_added(run)}"])
    finally:
        ni.remove_tree(base)
