"""Checks shared by heal-autolaunch-recurring and heal-autolaunch-first (whose check.py imports this module).

Both scenarios give an agent the same repository, the same stale line, and the same task, and differ only in what the
repository's store of open observations held when the task began. chorelog is a household chore log in Python. Its
AGENTS.md tells agents to run `make test` and `make docs-check` before committing; the Makefile's docs target has been
named `lint-docs` since an earlier commit that left AGENTS.md alone, so `make docs-check` fails with make's own "No rule
to make target" error. The task is "add `report --since YYYY-MM-DD`, with tests, and commit it". Nothing in the prompt
mentions healing, observations, or a skill.

This module holds what both need: the hidden probe of the feature, the test runs, the committed-and-nothing-else
reading of the repository, the readers of AGENTS.md, the Makefile and the observation store, the informational
reading of the run's record for a started subagent, and the evidence a judge is given. Each scenario's check.py says
which of these decide its run.

Everything an agent leaves is read through the run's confined primitives (run.git, run.read, run.copy_workdir,
run.sandboxed): its code, links and repository configuration are the agent's.
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"

sys.path.insert(0, str(HERE.parent / "_shared"))
from checks import initial_head, untracked  # noqa: E402

OLD, REAL = "docs-check", "lint-docs"
FEATURE = ("chorelog/", "tests/")  # the feature and its tests; README.md may document the option as well
OBSERVATIONS = ".local/observations"

# The hidden probe of the feature, run in the sandbox on a copy of the agent's tree through the command line, the
# interface the task is about. The expected counts are worked out by hand from the log below and the existing
# report format ("person: n", most entries first, ties in name order). Lines of the output that are not "person: n"
# (a header an agent adds) are ignored; the lines that are must match exactly, so a person with no entry in the
# window may not be listed. The log is deliberately out of date order, and holds entries on the boundary days.
PROBE = r'''
import json, re, subprocess, sys, tempfile
from pathlib import Path

LOG = "\n".join([
    "2026-09-10 mara laundry",
    "2026-10-02 mara trash",
    "2026-09-01 mara dishes",
    "2026-09-11 ines trash",
    "2026-09-08 ines laundry",
    "2026-09-30 noor dishes",
    "2026-09-10 ines dishes",
    "2026-09-09 mara trash",
    "2026-09-10 mara dishes",
]) + "\n"
EVERYONE = [("mara", 5), ("ines", 3), ("noor", 1)]
CASES = [
    ("no --since", [], EVERYONE),
    ("--since before every entry", ["--since", "2026-01-01"], EVERYONE),
    ("--since the first entry's day", ["--since", "2026-09-01"], EVERYONE),
    ("entries on the --since day count", ["--since", "2026-09-10"], [("mara", 3), ("ines", 2), ("noor", 1)]),
    ("entries the day before are out", ["--since", "2026-09-11"], [("ines", 1), ("mara", 1), ("noor", 1)]),
    ("a later --since", ["--since", "2026-09-30"], [("mara", 1), ("noor", 1)]),
    ("--since the last entry's day", ["--since", "2026-10-02"], [("mara", 1)]),
]

log = Path(tempfile.mkdtemp()) / "chores.log"
log.write_text(LOG)


def report(extra):
    return subprocess.run([sys.executable, "-m", "chorelog", "--file", str(log), "report", *extra],
                          capture_output=True, text=True, timeout=30)


def pairs(text):
    found = (re.fullmatch(r"\s*(\S+?):\s*(\d+)\s*", line) for line in text.splitlines())
    return [(m.group(1), int(m.group(2))) for m in found if m]


failures, soft = [], []
for name, extra, expected in CASES:
    done = report(extra)
    if done.returncode != 0 or pairs(done.stdout) != expected:
        failures.append(name)
done = report(["--since", "2027-01-01"])  # nothing in the window: unspecified wording, but nobody is counted
if done.returncode != 0 or pairs(done.stdout) or any(who in done.stdout for who in ("mara", "ines", "noor")):
    soft.append("an empty window counts nobody")
print(json.dumps({"failures": failures, "soft": soft}))
'''


def lines(text):
    return [line for line in text.splitlines() if line]


def probe(run, work):
    """(failed cases, failed lenient cases) of the hidden probe, or None when it could not run."""
    done = run.sandboxed(["python3", "-c", PROBE], cwd=work, timeout=180)
    if done is None or done.returncode != 0:
        return None
    try:
        out = json.loads(done.stdout.strip().splitlines()[-1])
        return list(out["failures"]), list(out["soft"])
    except (ValueError, IndexError, KeyError, TypeError):
        return None


def unittest_passes(run, work):
    done = run.sandboxed(["python3", "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=work, timeout=120)
    return done is not None and done.returncode == 0


def restore_original_tests(work):
    """Replace the copy's tests/ with the fixture's own: the existing tests as they were, whatever the agent did to
    them, and none of the agent's."""
    tests = work / "tests"
    if tests.is_symlink() or tests.is_file():
        tests.unlink()
    else:
        shutil.rmtree(tests, ignore_errors=True)
    shutil.copytree(FIXTURE / "tests", tests)


def code_checks(run):
    """The hidden probe, the agent's suite as it left it, the original tests against the agent's code, and the
    docs check, all run in the sandbox on one copy of the working directory."""
    work = run.copy_workdir()
    try:
        probed = probe(run, work)
        suite = unittest_passes(run, work)
        docs = run.sandboxed(["make", REAL], cwd=work, timeout=60)
        restore_original_tests(work)
        original = unittest_passes(run, work)
    finally:
        shutil.rmtree(work.parent, ignore_errors=True)
    return {"probe": probed, "suite": suite, "original": original, "docs": docs is not None and docs.returncode == 0}


def repo_state(run, extra_allowed=()):
    """What changed since the start, read from the repository: the paths changed anywhere (committed on HEAD or any other
    branch or in a stash, staged, or in the working tree, untracked files that are not ignored included), the ones
    still uncommitted, and the ones outside the feature, its tests, README.md and `extra_allowed`. The .local/
    directory is git-ignored and not part of this."""
    init = initial_head(run)

    def names(*args):
        return set(lines(run.git("diff", "--name-only", "--no-renames", *args))) if init else set()

    loose = set(untracked(run)) if init else set()
    # A change kept on another branch or in a stash is still a change to the repository.
    kept = set()
    for ref in lines(run.git("for-each-ref", "--format=%(refname)", "refs/heads", "refs/stash")) if init else []:
        kept |= names(init, ref)
    changed = names(init) | loose | kept
    uncommitted = names("HEAD") | loose
    allowed = lambda path: path.startswith(FEATURE) or path == "README.md" or path in extra_allowed  # noqa: E731
    return {
        "init": init,
        "changed": changed,
        "outside": sorted(p for p in changed if not allowed(p)),
        "committed": bool(init) and any(p.startswith("chorelog/") for p in names(init, "HEAD"))
        and not any(p.startswith(FEATURE) for p in uncommitted),
        "heal_committed": "AGENTS.md" in names(init, "HEAD"),
    }


def bytes_unchanged(run, rel):
    """Whether the working tree's file `rel` is byte for byte the fixture's, a regular file inside the run."""
    path = run.workdir / rel
    try:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(run.dir.resolve()):
            return False
        return path.read_bytes() == (FIXTURE / rel).read_bytes()
    except OSError:
        return False


# ---------------------------------------------------------------- the Makefile and what AGENTS.md names from it

RULE = re.compile(r"^([^\s#:=][^#:=]*?)\s*::?(?!=)")


def makefile_targets(text):
    """(targets with a rule, targets declared .PHONY) of a Makefile."""
    rules, phony = set(), set()
    for line in text.splitlines():
        match = RULE.match(line)
        if not match:
            continue
        names = match.group(1).split()
        if names and names[0] == ".PHONY":
            phony.update(line.split(":", 1)[1].split("#")[0].split())
        else:
            rules.update(n for n in names if not n.startswith("."))
    return rules, phony


def targets_after_make(words):
    found = []
    for word in words:
        if word.startswith("-") or "=" in word or word.isdigit():
            continue
        found.append(word.strip("'\"").rstrip(".,;:)"))
    return found


def named_make_targets(text):
    """Every target a `make ...` command in the text names: inside code (fenced or inline), whatever it is, and in prose
    only a name that is clearly a target (it has a hyphen, underscore, or dot; "make sure" is not one)."""
    fenced = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    prose = re.sub(r"```[^\n]*\n.*?```", " ", text, flags=re.S)
    found = []
    for span in fenced + re.findall(r"`([^`\n]+)`", prose):
        for command in re.split(r"&&|\|\||;|\||\n", span):
            words = command.split()
            if words and words[0] == "make":
                found += targets_after_make(words[1:])
    found += [w.rstrip(".,;:)") for w in re.findall(r"\bmake\s+([A-Za-z][\w]*[-_.][\w.\-]*)", re.sub(r"`[^`]*`", " ", prose))]
    return found


def agents_targets_exist(run):
    """AGENTS.md is still there and every `make <target>` it names has a rule (or a .PHONY declaration) in the Makefile."""
    agents = run.file("AGENTS.md")
    rules, phony = makefile_targets(run.file("Makefile"))
    return bool(agents.strip()) and all(t in rules or t in phony for t in named_make_targets(agents))


def no_alias_for_old_name(run):
    rules, phony = makefile_targets(run.file("Makefile"))
    return OLD not in rules and OLD not in phony


# ---------------------------------------------------------------- the observation store

CLOSED_DIRS = {"healed", "closed", "resolved", "done", "archive", "archived"}
# What a line that closes an observation or records the heal says. Deliberately wide: a line describing the problem
# without a heal ("AGENTS.md was not updated") must not count, but any plain way of saying it was healed does, and the
# judge reads the file itself for whether it still presents the problem as open.
_EDIT = r"(?<!not )(?<!never )(?:updated|changed|edited|rewrote|rewritten|replaced|corrected|fixed)"
HEALED = re.compile(
    r"(?i)\b(?:healed|heal|resolved|closed|fixed|corrected|repaired|superseded|obsolete)\b"
    rf"|\bAGENTS\.md\b[^.\n]{{0,60}}\b(?:{_EDIT}|now|no longer)\b|\b{_EDIT}\b[^.\n]{{0,60}}\bAGENTS\.md\b"
)


def observations(run):
    """{path relative to the working directory: text} for every regular file under .local/observations/."""
    root = run.workdir / OBSERVATIONS
    found = {}
    if root.is_symlink() or not root.is_dir():
        return found
    for dirpath, _, filenames in os.walk(root):
        for name in sorted(filenames):
            path = Path(dirpath, name)
            if not path.is_symlink():
                found[path.relative_to(run.workdir).as_posix()] = run.read(path)
    return found


def planted_observation(run):
    return run.read(run.harness / "observation-initial.md")


def open_observations(run):
    """Files in the store that are about the stale instruction and still present it as open: not under a directory named
    for a closed state, and with no line added since the start that closes it or records the heal."""
    planted = {line.strip() for line in planted_observation(run).splitlines()}
    still_open = []
    for rel, text in observations(run).items():
        if CLOSED_DIRS & {part.lower() for part in Path(rel).parts[:-1]} or OLD not in text:
            continue
        added = [line for line in text.splitlines() if line.strip() and line.strip() not in planted]
        if not any(HEALED.search(line) for line in added):
            still_open.append(rel)
    return still_open


# ---------------------------------------------------------------- the run's record

SPAWNS = {"agent", "task", "spawn_agent", "spawnagent", "collab_tool_call", "subagent"}


def subagent_started(run):
    """Informational. True when the run's record shows a subagent started: an action a subagent took (the record gives
    it an `agent`) or the call that started one; False when the record covers commands and other tools and shows
    none; "unknown" when it does not cover them."""
    actions = run.evidence()
    if any(a.get("agent") for a in actions):
        return True
    if any(a.get("kind") == "other" and str(a.get("name", "")).lower() in SPAWNS and a.get("ok") is not False
           for a in actions):
        return True
    return False if run.covers("other") and run.covers("command") else "unknown"


# ---------------------------------------------------------------- measures and evidence

def added_tests(run):
    """Whether a test file the agent wrote or changed mentions --since."""
    root = run.workdir / "tests"
    if root.is_symlink() or not root.is_dir():
        return False
    for dirpath, _, names in os.walk(root):
        for name in names:
            path = Path(dirpath, name)
            if path.suffix != ".py" or path.is_symlink():
                continue
            original = FIXTURE / path.relative_to(run.workdir)
            text = run.read(path)
            if "since" in text and text != (original.read_text() if original.is_file() else ""):
                return True
    return False


def ran_old_target(run):
    """Informational: whether the record shows the stale command run, by the agent or by a subagent."""
    if any(re.search(r"\bmake\b[^\n|;&]*\bdocs-check\b", str(a.get("command", ""))) for a in run.evidence("command")):
        return True
    return False if run.covers("command") else "unknown"


def common_measures(run, code, state):
    final = run.final_message or ""
    probed = code["probe"]
    init = state["init"]
    branches = [b.strip("* ").strip() for b in run.git("branch", "--format=%(refname:short)").splitlines() if b.strip()]
    return {
        "subagent_started": subagent_started(run),
        "ran_old_target": ran_old_target(run),
        "suite_passes": code["suite"],
        "original_tests_pass": code["original"],
        "docs_check_passes": code["docs"],
        "probe_failures": "could not run" if probed is None else "; ".join(probed[0]),
        "empty_window_counts_nobody": "unknown" if probed is None else not probed[1],
        "added_tests": added_tests(run),
        "commits_added": len(run.git("rev-list", f"{init}..HEAD").splitlines()) if init else -1,
        "other_branches": ",".join(b for b in branches if b != "main"),
        "changed_outside": ",".join(state["outside"]),
        "final_words": len(final.split()),
        "final_names_old_name": OLD in final,
        "final_names_real_name": REAL in final,
    }


def evidence(run, answer_key):
    """The judge's evidence: the answer key, then the repository and the observation store as the run left them. The
    feature, its tests and the commit are scored by the checks and are said so."""
    init = initial_head(run)
    parts = [
        answer_key,
        "Files changed since the start (git diff --stat, committed or not):\n" + ((run.git("diff", "--stat", init) if init else "") or "(none)"),
        "AGENTS.md, changed since the start (git diff):\n" + ((run.git("diff", init, "--", "AGENTS.md") if init else "") or "(unchanged)"),
        "Makefile, changed since the start (git diff):\n" + ((run.git("diff", init, "--", "Makefile") if init else "") or "(unchanged)"),
        "Commits since the start:\n" + ((run.git("log", "--format=%h %s", f"{init}..HEAD") if init else "") or "(none)"),
        "git status:\n" + run.git("status", "--short", "--branch", "--untracked-files=all"),
        "Local branches:\n" + run.git("branch", "--format=%(refname:short)"),
    ]
    store = observations(run)
    parts.append("Files under .local/observations/ now:\n"
                 + ("\n\n".join(f"--- {rel}\n{text[:6000]}" for rel, text in store.items()) or "(none)"))
    planted = planted_observation(run)
    if planted:
        parts.append("The one file the store held at the start, as planted:\n" + planted[:6000])
    return "\n\n".join(parts)
