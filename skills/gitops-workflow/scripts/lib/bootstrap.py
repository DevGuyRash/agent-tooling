from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


BOOTSTRAP_ENV = "GITOPS_WORKFLOW_BOOTSTRAP_ACTIVE"


def _extract_repo_arg(argv: Sequence[str]) -> str | None:
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg == "--repo":
            return argv[index + 1] if index + 1 < len(argv) else None
        if arg.startswith("--repo="):
            return arg.split("=", 1)[1]
        index += 1
    return None


def _repo_root_from_path(path_hint: str | None) -> Path | None:
    if not path_hint:
        return None
    try:
        output = subprocess.check_output(
            ["git", "-C", path_hint, "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return None
    return Path(output).resolve()


def _repo_root_from_cwd() -> Path | None:
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return None
    return Path(output).resolve()


def maybe_reexec_repo_local_copy(script_path: Path, argv: Sequence[str]) -> None:
    if os.environ.get(BOOTSTRAP_ENV) == "1":
        return

    resolved_script = script_path.resolve()
    current_skill_root = resolved_script.parent.parent
    skill_name = current_skill_root.name
    script_name = resolved_script.name

    repo_roots: list[Path] = []
    repo_hint = _extract_repo_arg(argv)
    hinted_root = _repo_root_from_path(repo_hint)
    if hinted_root is not None:
        repo_roots.append(hinted_root)
    cwd_root = _repo_root_from_cwd()
    if cwd_root is not None and cwd_root not in repo_roots:
        repo_roots.append(cwd_root)

    for repo_root in repo_roots:
        candidate_skill_root = (repo_root / "skills" / skill_name).resolve()
        candidate_script = candidate_skill_root / "scripts" / script_name
        if not (candidate_skill_root / "SKILL.md").is_file() or not candidate_script.is_file():
            continue
        if candidate_skill_root == current_skill_root:
            continue

        env = os.environ.copy()
        env[BOOTSTRAP_ENV] = "1"
        executable = sys.executable or "python3"
        os.execvpe(executable, [executable, str(candidate_script), *argv[1:]], env)
