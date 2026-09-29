import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import commands_matching, local_branches, untracked  # noqa: E402

PROBE = """
from inventory import Inventory
inv = Inventory()
inv.add("washer", 5); inv.add("bolt", 2); inv.add("anchor", 1); inv.add("nut", 3)
inv.remove("nut", 1)
assert inv.low_stock(2) == ["anchor", "bolt", "nut"], inv.low_stock(2)
assert inv.low_stock(0) == [], inv.low_stock(0)
print("ok")
"""


def check(run):
    probe = subprocess.run([sys.executable, "-c", PROBE], cwd=run.workdir, capture_output=True, text=True)
    suite = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=run.workdir,
                           capture_output=True, text=True)
    commits = run.git("log", "--format=%H").splitlines()
    return {
        "feature_works": probe.returncode == 0,
        "existing_tests_pass": suite.returncode == 0,
        "single_change": len([b for b in local_branches(run) if b != "main"]) <= 1 and len(commits) <= 3,
        "test_runs": len(commands_matching(run, r"unittest|pytest")),
        "commits_added": len(commits) - 1,
        "stray_files": len([u for u in untracked(run) if "__pycache__" not in u]),
        "added_tests": "low_stock" in run.file("tests/test_store.py"),
    }
