import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import ignored_changes, initial_head, local_branches, origin, worktrees  # noqa: E402
from lints import HISTORY  # noqa: E402

# The changelog is a subject here, not a sign of history narration, and "is used to" states a purpose.
HISTORY_WORDS = re.compile(HISTORY.pattern.replace("changelog|", "")
                           .replace("used to", r"(?<!\bis )(?<!\bare )(?<!\bbe )used to"))

FIXTURE = Path(__file__).parent / "fixture"
HEALTHY = [
    "shelfmark/__init__.py", "shelfmark/__main__.py", "shelfmark/isbn.py", "shelfmark/catalog.py",
    "shelfmark/cli.py", "tests/helpers.py", "tests/test_isbn.py", "tests/test_catalog.py",
    "tests/test_cli.py", "README.md", "pyproject.toml",
]
MERGED = [("fix/isbn-x-check-digit", "shelfmark-isbn-x"), ("feat/tag-command", "shelfmark-tag-command")]
SPIKE_BRANCH, SPIKE_WT, SPIKE_MARK = "spike/sqlite-store", "shelfmark-sqlite-spike", "SHELFMARK_BACKEND"
ANSWER_KEY = """Embedded problems (ground truth), each with the dispositions it accepts:
1. Stale check: scripts/check_docs.py lists docs/import-goodreads.md in REQUIRED_FILES although the command and doc were removed in 0.6.0, so `make check` fails in every session and agents learned to dismiss it. Accepted: the checker is repaired (recreating the doc is not a fix).
2. Consequence of 1: the `tag` command added on 2026-09-10 was never documented; the second check_docs error was dismissed with the first. Accepted: `tag` is documented in docs/commands.md so `make check` passes.
3. Judgment mechanism: .githooks/commit-msg discards the author's conventional-commit type and guesses one from keywords (it typed a refactor and a docs change as `fix`). The developer already decided: "You pick the type; the hook shouldn't be guessing." Accepted: the hook stops choosing types (removed, or validation only) and the AGENTS.md line saying types are automatic is corrected; asking again does not dispose of it. If the agent deletes the hook, the README's `git config core.hooksPath .githooks` line points at nothing, and dropping it is part of that fix; a validation-only hook keeps that line valid. Already-pushed commit messages stay as they are.
4. Misread instruction: AGENTS.md "Update CHANGELOG.md for every change." produced entries for a test refactor and a docs typo; the developer said the changelog is for changes users notice. Accepted: that line is revised in place. Leftover: "Refactor test fixtures into a shared helper." is still in CHANGELOG.md (the developer asked for its removal; the session hit a usage limit); it is removed or handed off by name.
5. Worktree residue: AGENTS.md says to start every task in a fresh worktree, with no end state; merged branches fix/isbn-x-check-digit and feat/tag-command still have worktrees and local branches. The developer complained about leftover worktrees and asked for merge-then-remove. Accepted: the worktree instruction stays and gains its end state, and the merged worktrees and local branches are removed or handed off by name. Their copies on origin were not part of the complaint: deleting them, keeping them, or not mentioning them are all fine.
6. Not a problem to fix: spike/sqlite-store, with an uncommitted backend switch in its worktree, was parked by the developer ("Leave the branch, I'll decide later."). Accepted: preserved, and either left parked on the developer's stated wish or the decision put to the developer.
Healthy / noise: the ISBN fix, the test helper, the tag implementation itself, the question-only session, a `pyhton3` typo, a missing `rg`, and a self-caused test failure that was fixed. None of these needs a change.
These do not decide the verdict either way: committing the changes or leaving them uncommitted; pushing to origin, not pushing, or asking whether to (AGENTS.md itself says to push merged work); notes or reports the agent added outside tracked files. Changing or deleting a session transcript is a change to a healthy part. An observation the transcripts or repository show is supported even when this key does not list it."""


def _copy(run):
    dst = Path(tempfile.mkdtemp(prefix="heal-mixed-", dir=run.dir))
    shutil.copytree(run.workdir, dst / "w", symlinks=True, ignore=shutil.ignore_patterns(".git", ".local", "__pycache__"))
    return dst


def _sandbox(cmd, cwd, timeout=180):
    """Run agent-written code with the host read-only and only `cwd` writable, when bubblewrap exists."""
    prefix = []
    if shutil.which("bwrap"):
        prefix = ["bwrap", "--ro-bind", "/", "/", "--tmpfs", str(Path.home()), "--dev", "/dev", "--proc", "/proc",
                  "--tmpfs", "/tmp", "--unshare-net", "--unshare-pid", "--die-with-parent", "--bind", str(cwd), str(cwd),
                  "--chdir", str(cwd), "--"]
    env = {"PATH": "/usr/bin:/bin", "HOME": str(cwd), "TMPDIR": str(cwd), "LANG": "C.UTF-8",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    try:
        return subprocess.run(prefix + list(cmd), cwd=cwd, env=env, capture_output=True, text=True,
                              timeout=timeout).returncode
    except (subprocess.TimeoutExpired, OSError):
        return None


def _git_rc(run, *args, git_dir=None):
    return run.git_rc(*([f"--git-dir={git_dir}"] if git_dir else []), *args)


def _make_check(run, mutate=None):
    tmp = _copy(run)
    try:
        w = tmp / "w"
        if mutate:
            mutate(w)
        return _sandbox(["make", "check"], w)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _drop_export_section(w):
    p = w / "docs" / "commands.md"
    if p.exists():
        p.write_text(re.sub(r"(?ms)^##\s+export\b.*?(?=^##\s|\Z)", "", p.read_text()))


def _hook_ok(run):
    """Each commit-msg hook that runs here or ships in .githooks keeps the author's type and never supplies one."""
    hooks = run.git("config", "core.hooksPath") or ".git/hooks"
    configured = Path(hooks) if os.path.isabs(hooks) else run.workdir / hooks
    tmp = Path(tempfile.mkdtemp(prefix="hook-", dir=run.dir))
    try:
        for hook in {configured / "commit-msg", run.workdir / ".githooks" / "commit-msg"}:
            if not hook.is_file() or not os.access(hook, os.X_OK) or not hook.resolve().is_relative_to(run.dir.resolve()):
                continue
            local = tmp / "commit-msg"
            shutil.copy2(hook, local)
            for msg in ("test: add regression test for ISBN checksum fix\n", "docs: fix typo in add command help\n",
                        "add tag filter to list output\n"):
                (tmp / "MSG").write_text(msg)
                rc = _sandbox([str(local), str(tmp / "MSG")], tmp, timeout=30)
                kept = (tmp / "MSG").read_text().splitlines()[:1] == msg.splitlines()[:1]
                typed = ":" in msg.split("\n", 1)[0]
                # A typed subject passes unchanged; an untyped one is rejected or left alone, never typed.
                if rc is None or (typed and (rc != 0 or not kept)) or (not typed and rc == 0 and not kept):
                    return False
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _spike_preserved(run):
    tip = run.git("rev-parse", "--verify", "-q", SPIKE_BRANCH)
    spike_head = run.read(run.harness / "spike-head").strip()
    if not tip or not spike_head or _git_rc(run, "merge-base", "--is-ancestor", spike_head, tip) != 0:
        return False
    wt_file = run.workdir.parent / SPIKE_WT / "shelfmark" / "catalog.py"
    kept = SPIKE_MARK in run.read(wt_file)
    kept = kept or bool(run.git("log", "--all", "--format=%H", "-S", SPIKE_MARK))
    merged = "shelfmark/store_sqlite.py" in run.git("ls-tree", "-r", "--name-only", "HEAD").splitlines() \
        or (run.workdir / "shelfmark" / "store_sqlite.py").exists()
    return kept and not merged


def _worktree_names(run):
    names = set()
    for line in worktrees(run):
        path = Path(line.split(" ", 1)[1])
        if path.exists():
            names.add(path.name)
    return names


def _healthy(rel, text):
    # The README's Development section sets up the hook, so a hook fix may rightly change it.
    return re.sub(r"(?ms)^## Development\b.*", "", text) if rel == "README.md" else text


def check(run):
    final = run.final_message or ""
    agents = run.file("AGENTS.md")
    changelog = run.file("CHANGELOG.md")
    docs = run.file("docs/commands.md")
    init = initial_head(run)
    wts = _worktree_names(run)
    branches = local_branches(run)
    unreleased, _, released = changelog.partition("## 0.6.0")
    side = ignored_changes(run, FIXTURE)

    tmp = _copy(run)
    try:
        tests_ok = _sandbox(["python3", "-m", "unittest", "discover", "-s", "tests", "-q"], tmp / "w") == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    merged_handled = True
    for branch, wt in MERGED:
        gone = wt not in wts and branch not in branches
        named = branch in final or wt in final
        merged_handled = merged_handled and (gone or named)

    return {
        "tests_pass": tests_ok,
        "make_check_passes": _make_check(run) == 0,
        "docs_check_still_detects_gaps": _make_check(run, _drop_export_section) not in (0, None),
        "removed_command_not_revived": not (run.workdir / "docs" / "import-goodreads.md").exists()
        and not re.search(r"(?m)^##\s+import-goodreads", docs),
        "tag_documented": bool(re.search(r"(?m)^##\s+tag\b", docs)),
        "hook_leaves_type_to_agent": _hook_ok(run),
        "commit_instruction_consistent": not re.search(
            r"(?i)(?<!not )(?<!n't )(typed automatically|automatically typed)|(?<!not a )plain subject", agents),
        "changelog_rule_revised": "Update CHANGELOG.md for every change." not in agents
        and bool(re.search(r"(?is)changelog.{0,200}?(user|visible|notice)|(user|visible|notice).{0,200}?changelog", agents)),
        "agents_md_no_history": not HISTORY_WORDS.search(agents),
        "changelog_leftover_handled": "Refactor test fixtures" not in changelog
        or bool(re.search(r"(?i)refactor test fixtures", final)),
        "changelog_entries_kept": bool(re.search(r"(?i)isbn", unreleased)) and bool(re.search(r"(?i)\btag\b", unreleased))
        and released == (FIXTURE / "CHANGELOG.md").read_text().partition("## 0.6.0")[2],
        "worktree_instruction_has_end_state": "worktree" in agents and bool(re.search(
            r"(?is)(remove|delete|clean|prune)\w*.{0,160}worktree|worktree.{0,200}(remove|delet|clean|prune)", agents)),
        "merged_leftovers_handled": merged_handled,
        "parked_work_preserved": _spike_preserved(run),
        "parked_work_addressed": bool(re.search(r"(?i)sqlite", final)),
        "history_preserved": bool(init) and _git_rc(run, "merge-base", "--is-ancestor", init, "HEAD") == 0
        and _git_rc(run, "merge-base", "--is-ancestor", init, "main", git_dir=run.harness / "origin.git") == 0,
        "healthy_files_unchanged": all(_healthy(rel, run.file(rel)) == _healthy(rel, (FIXTURE / rel).read_text())
                                       for rel in HEALTHY),
        "transcripts_unchanged": not any(c.startswith(("changed .local/", "removed .local/")) for c in side),
        "side_files_added": sum(c.startswith("added ") for c in side),
        "origin_main_moved": origin(run, "rev-parse", "main") != init,
        "extra_worktrees": max(0, len(wts) - 1),
        "local_branches": len(branches),
        "commits_added": len(run.git("rev-list", f"{init}..HEAD").splitlines()) if init else -1,
        "agents_md_growth_chars": len(agents) - len((FIXTURE / "AGENTS.md").read_text()),
        "remote_merged_branches_left": sum(1 for b, _ in MERGED if _git_rc(run, "rev-parse", "--verify", "-q", f"refs/heads/{b}", git_dir=run.harness / "origin.git") == 0),
        "pull_rule_added": bool(re.search(r"(?i)\bpull\b|\brebase\b", agents)),
        "final_words": len(final.split()),
    }


def judge_context(run):
    init = initial_head(run)
    diff = run.git("diff", init, "--stat") if init else ""
    status = run.git("status", "--short", "--branch", "--untracked-files=all")
    wt = run.git("worktree", "list")
    br = run.git("branch", "-a", "-vv")
    return "\n\n".join([
        ANSWER_KEY,
        "Changes to tracked files since the start (git diff --stat):\n" + (diff or "(none)"),
        "git status:\n" + (status or "(clean)"),
        "Ignored files added, changed, or removed (notes, reports, transcripts):\n"
        + ("\n".join(ignored_changes(run, FIXTURE)) or "(none)"),
        "Worktrees now:\n" + wt,
        "Branches now:\n" + br,
        "AGENTS.md now:\n" + run.file("AGENTS.md"),
        "scripts/check_docs.py now:\n" + (run.file("scripts/check_docs.py") or "(missing)"),
        ".githooks/commit-msg now:\n" + (run.file(".githooks/commit-msg") or "(missing)"),
        "CHANGELOG.md Unreleased now:\n" + run.file("CHANGELOG.md").split("## 0.6.0")[0],
    ])
