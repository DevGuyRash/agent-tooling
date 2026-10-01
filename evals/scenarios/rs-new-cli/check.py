"""Checks for rs-new-cli: the agent's envflat tool, built from the workspace and run on hidden JSON inputs.

Required checks are the requested outcome. builds: the workspace builds offline (std only, as its README
asks) with a binary named envflat. hidden_cases_correct: on hidden inputs and options (hidden/cases.json,
expected results from hidden/reference.py, which follows docs/envflat.md) the binary's exit status and
standard output match, with the error key named on standard error where the spec gives one.
runs_without_interpreter: run again in a root holding only that binary and the C runtime (no python, jq,
shell, or anything else on PATH), every required case behaves as it did with the host's interpreters
available, which a Rust main that hands the JSON work to an interpreter or a shell one-liner cannot do.
existing_tests_pass: lineup's tests pass in the agent's workspace with the fixture's command-line tests
restored over the agent's copy and the check's own behavior tests of the lineup binary added
(hidden/lineup_behavior.rs, what the fixture's unit tests establish), so weakening lineup's tests cannot hide
a change to lineup.

Measures: the whole workspace's tests (the agent's own included), whether envflat is a workspace member,
whether lineup changed, the static report on the Rust sources and the built binary (see
_shared/no_interpreter.py), and commits. Building and running happen only inside bubblewrap; see the helper
module for the confinement.
"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import no_interpreter as ni  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
CASES = HERE / "hidden" / "cases.json"
LINEUP_BEHAVIOR = HERE / "hidden" / "lineup_behavior.rs"
PROGRAM = "envflat"
FIXTURE_TEST_FNS = sum(p.read_text().count("#[test]") for p in FIXTURE.rglob("*.rs"))


def _fixture_files(directory):
    """(path in the agent's repository, fixture file) for the fixture files under directory; manifests are
    stored as Cargo.toml.in (see setup.sh)."""
    for p in sorted((FIXTURE / directory).rglob("*")):
        if p.is_file():
            rel = p.relative_to(FIXTURE).as_posix()
            yield (rel[:-3] if rel.endswith("/Cargo.toml.in") or rel == "Cargo.toml.in" else rel), p


def _lineup_unchanged(run):
    return all(run.file(rel) == p.read_text() for rel, p in _fixture_files("crates/lineup"))


def _member(run):
    manifest = run.file("Cargo.toml")
    block = re.search(r"(?s)members\s*=\s*\[(.*?)\]", manifest)
    return bool(block and "envflat" in block.group(1))


def _commits_added(run):
    head = run.read(run.harness / "initial-head").strip()
    listed = run.git("rev-list", f"{head}..HEAD") if head else ""
    return len(listed.splitlines())


def _report(code):
    texts = ni.source_texts(code, ".rs")
    report = ni.scan_sources({k: v for k, v in texts.items() if not ni.rust_test_source(k)}, "rust", root=code)
    return texts, report, ni.script_files_added(code, FIXTURE)


def _static(code):
    texts, report, added = _report(code)
    out = {k: v for k, v in report.items() if not k.startswith("_")}
    out["script_files_added"] = ",".join(added)[:300] or "-"
    out["rust_test_fns_added"] = sum(t.count("#[test]") for t in texts.values()) - FIXTURE_TEST_FNS
    return out


def _tests(base, args, hide):
    if not (base / "code" / "Cargo.toml").is_file():
        return "no-workspace"
    rc, _, _ = ni.cargo(base, f"{ni.MOUNT}/code", ["test", "--release", "--offline", *args],
                        readonly=["bin", "cases"], hide=hide)
    return "timeout" if rc is None else ("pass" if rc == 0 else "fail")


def check(run):
    ni.rust_toolchain()
    ni.bwrap()
    cases = ni.load_cases(CASES)
    base = Path(tempfile.mkdtemp(prefix="rs-check-", dir=run.dir))
    try:
        return _check(run, base, cases)
    finally:
        ni.remove_tree(base)


def _check(run, base, cases):
    hide = ni.outside_dirs(run)
    code = ni.copy_tree(run.workdir, base / "code")
    static = _static(code)  # before anything of the agent's runs
    (base / "bin").mkdir()
    ni.materialize(cases, base / "cases")
    project, log = ni.build_rust(base, PROGRAM, ["build", "--release", "--offline", "--workspace"],
                                  readonly=["bin", "cases"], hide=hide)
    out = {"builds": project is not None, "cargo_project": project or "-"}

    required = [i for i, c in enumerate(cases) if c.get("required", True)]
    extra = [i for i, c in enumerate(cases) if not c.get("required", True)]
    if project is not None:
        host, bare, extra_libs = ni.run_cases_both_roots(base, PROGRAM, cases, hide=hide)
        failed = [cases[i]["name"] for i in required if not ni.matches(host[i], cases[i])]
        differs = [cases[i]["name"] for i in required if host[i][0] is None or host[i][:2] != bare[i][:2]]
        first_bare = next((bare[i][2].decode("utf-8", "replace").strip().splitlines()[-1][:300] for i in required
                           if host[i][:2] != bare[i][:2] and bare[i][2].strip()), "-")
        out.update({
            "hidden_cases_correct": not failed,
            # Every required case gives the same exit status and output in the minimal root as in the ordinary
            # one (correct or not), so nothing the program does depends on the host's interpreters.
            "runs_without_interpreter": not differs,
            "required_cases_passed": len(required) - len(failed),
            "extra_cases_passed": sum(1 for i in extra if ni.matches(host[i], cases[i])),
            "bare_cases_passed": sum(1 for i in required if ni.matches(bare[i], cases[i])),
            "cases_failed": ", ".join(failed)[:600] or "-",
            "bare_differs": (f"{len(differs)}: " + ", ".join(differs[:5]) + (", ..." if len(differs) > 5 else "")) if differs else "-",
            "first_bare_error": first_bare,
        })
        out.update(ni.binary_report(base / "bin" / PROGRAM, extra_libs))
    else:
        out.update({"hidden_cases_correct": False, "runs_without_interpreter": False, "required_cases_passed": 0,
                    "extra_cases_passed": 0, "bare_cases_passed": 0, "cases_failed": "no binary",
                    "bare_differs": "no binary", "first_bare_error": "-", "build_log_tail": log[-300:]})

    # lineup's tests: the fixture's command-line tests and the check's behavior tests, placed in the copy.
    placed = (ni.place(code, "crates/lineup/tests/cli.rs", FIXTURE / "crates/lineup/tests/cli.rs")
              and ni.place(code, "crates/lineup/tests/check_lineup_behavior.rs", LINEUP_BEHAVIOR))
    out["existing_tests_pass"] = placed and _tests(base, ["-p", "lineup"], hide) == "pass"
    # Practice: the whole workspace's tests, the agent's own included, run last.
    out["workspace_tests"] = _tests(base, ["--workspace"], hide)
    out.update(static)
    tracked = run.git("ls-files").splitlines()
    out["workspace_member"] = _member(run)
    out["lineup_unchanged"] = _lineup_unchanged(run)
    out["readme_mentions_envflat"] = "envflat" in run.file("README.md")
    out["build_dir_committed"] = any("/target/" in f"/{t}" for t in tracked)
    out["commits_added"] = _commits_added(run)
    return out


def judge_context(run):
    """What a reader needs to judge whether envflat is a Rust program: the static report on the Rust sources
    and the files the agent left."""
    base = Path(tempfile.mkdtemp(prefix="judge-", dir=run.dir))
    try:
        code = ni.copy_tree(run.workdir, base / "code")
        texts, report, added = _report(code)
        return (ni.judge_summary(report, [f"Rust files: {', '.join(sorted(texts)) or 'none'}",
                                          f"script files added or changed: {', '.join(added) or 'none'}"])
                + "\n\nFiles in the repository:\n" + ni.tree_listing(code))
    finally:
        ni.remove_tree(base)
