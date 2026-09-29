import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import local_branches, origin  # noqa: E402


def check(run):
    remote = [b for b in origin(run, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines() if b != "main"]
    return {
        "merged": "Acme Payments" in origin(run, "show", "main:README.md"),
        "remote_branches_left": len(remote),
        "local_branches_left": len([b for b in local_branches(run) if b != "main"]),
    }
