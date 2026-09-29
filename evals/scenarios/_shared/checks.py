"""Helpers shared by scenario checks."""
import re
import subprocess


def calls(run, tool):
    return [c for c in run.calls if c.get("tool") == tool]


def origin(run, *args):
    r = subprocess.run(["git", f"--git-dir={run.harness / 'origin.git'}", *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def initial_head(run):
    return (run.harness / "initial-head").read_text().strip() if (run.harness / "initial-head").exists() else ""


def tests_pass(run, *cmd):
    cmd = cmd or ("python3", "-m", "unittest", "-q")
    r = subprocess.run(list(cmd), cwd=run.workdir, capture_output=True, text=True, timeout=120)
    return r.returncode == 0


def worktrees(run):
    out = run.git("worktree", "list", "--porcelain")
    return [l for l in out.splitlines() if l.startswith("worktree ")]


def local_branches(run):
    return [b.strip("* ").strip() for b in run.git("branch", "--format=%(refname:short)").splitlines() if b.strip()]


def commands_matching(run, pattern):
    rx = re.compile(pattern)
    return [c for c in run.commands if rx.search(c)]


def untracked(run):
    return [l[3:] for l in run.git("status", "--porcelain", "--untracked-files=all").splitlines() if l.startswith("??")]
