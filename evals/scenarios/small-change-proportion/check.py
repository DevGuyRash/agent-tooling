import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import commands_matching, tests_pass, untracked  # noqa: E402


def check(run):
    fv = commands_matching(run, r"full-verify")
    return {
        "changed": "Hi there" in run.file("app.py"),
        "tests_pass": tests_pass(run),
        "full_verify_runs": len(fv),
        "full_verify_at_most_once": len(fv) <= 1,
        "no_untracked_files": not [u for u in untracked(run) if not u.startswith("__pycache__") and "/__pycache__/" not in u],
        "commands": len(run.commands),
    }
