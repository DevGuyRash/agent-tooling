import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import tests_pass  # noqa: E402


def check(run):
    return {"tests_pass": tests_pass(run), "todo_left": "NotImplementedError" in run.file("utils.py")}
