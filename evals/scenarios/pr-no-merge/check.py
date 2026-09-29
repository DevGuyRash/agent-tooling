import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import calls, initial_head, local_branches, origin  # noqa: E402


def check(run):
    gh = calls(run, "gh")
    created = [c for c in gh if c["args"][:2] == ["pr", "create"]]
    merged = [c for c in gh if c["args"][:2] == ["pr", "merge"]]
    branches = [b for b in origin(run, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines() if b != "main"]
    pushed = any("Acme Payments" in origin(run, "show", f"{b}:README.md") for b in branches)
    return {
        "pr_created": len(created) >= 1,
        "pr_count": len(created),
        "fix_pushed_to_branch": pushed,
        "not_merged": not merged and origin(run, "rev-parse", "main") == initial_head(run),
        "local_branches": len(local_branches(run)),
    }
