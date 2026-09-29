"""Helpers shared by scenario checks. What an agent left is read and run only through the run's confined
primitives (run.git, run.read, run.copy_workdir, run.sandboxed): its repository configuration, links, and
code are the agent's."""
import re
import shutil
from pathlib import Path


def calls(run, tool):
    return [c for c in run.calls if c.get("tool") == tool]


def origin(run, *args):
    return run.git(f"--git-dir={run.harness / 'origin.git'}", *args)


def initial_head(run):
    return run.read(run.harness / "initial-head").strip()


def tests_pass(run, *cmd):
    """The project's tests, run confined on a copy of the working directory."""
    work = run.copy_workdir()
    try:
        r = run.sandboxed(list(cmd or ("python3", "-m", "unittest", "-q")), cwd=work, timeout=120)
        return r is not None and r.returncode == 0
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)


def worktrees(run):
    out = run.git("worktree", "list", "--porcelain")
    return [l for l in out.splitlines() if l.startswith("worktree ")]


def local_branches(run):
    return [b.strip("* ").strip() for b in run.git("branch", "--format=%(refname:short)").splitlines() if b.strip()]


def ignored_changes(run, fixture):
    """Git-ignored files the run added, changed, or removed, compared with the fixture (whose session transcripts are ignored files)."""
    listed = run.git("ls-files", "--others", "--ignored", "--exclude-standard")
    changes = []
    for rel in sorted(p for p in listed.splitlines() if p and "__pycache__/" not in p and ".egg-info/" not in p):
        src = Path(fixture) / rel
        if not src.is_file():
            changes.append(f"added {rel}")
        elif src.read_text(errors="replace") != run.read(run.workdir / rel):
            changes.append(f"changed {rel}")
    for src in sorted((Path(fixture) / ".local").rglob("*")):
        rel = src.relative_to(fixture).as_posix()
        if src.is_file() and not (run.workdir / rel).exists():
            changes.append(f"removed {rel}")
    return changes


def commands_matching(run, pattern):
    rx = re.compile(pattern)
    return [c for c in run.commands if rx.search(c)]


def untracked(run):
    return [l[3:] for l in run.git("status", "--porcelain", "--untracked-files=all").splitlines() if l.startswith("??")]
