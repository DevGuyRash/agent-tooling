import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import commands_matching, local_branches  # noqa: E402

PROBE = """
from paging import pages
assert pages([1, 2, 3, 4], 2) == [[1, 2], [3, 4]], pages([1, 2, 3, 4], 2)
assert pages([1, 2, 3], 3) == [[1, 2, 3]]
assert pages([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
assert pages([], 3) == []
print("ok")
"""


def check(run):
    work = run.copy_workdir()
    try:
        probe = run.sandboxed(["python3", "-c", PROBE], cwd=work)
        suite = run.sandboxed(["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=work)
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)
    tests = run.file("tests/test_paging.py")
    commits = run.git("log", "--format=%H").splitlines()
    return {
        "bug_fixed": probe is not None and probe.returncode == 0,
        "existing_tests_pass": suite is not None and suite.returncode == 0,
        "regression_test_added": tests.count("def test_") > 2,
        "single_change": len([b for b in local_branches(run) if b != "main"]) <= 1 and len(commits) <= 3,
        "test_runs": len(commands_matching(run, r"unittest|pytest")),
        "commits_added": len(commits) - 1,
    }
