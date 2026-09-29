import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import initial_head, untracked  # noqa: E402

FIXTURE = Path(__file__).parent / "fixture"
GOLDEN = sorted(p.name for p in (FIXTURE / "tests" / "golden").glob("*.json"))
STRAYS = ["tests/golden/ally_savings.json.bak", "tests/golden/chase_refunds.json.new"]
SOURCE = [p.relative_to(FIXTURE).as_posix() for p in [*(FIXTURE / "ledgerline").glob("*.py"),
          *(FIXTURE / "tests" / "data").glob("*.csv")]]
ANSWER_KEY = """Embedded problem (ground truth):
1. Repeated manual procedure: after every parser change, agents regenerate six golden files by hand following CONTRIBUTING.md (normalize with the bank from the file-name prefix, pretty-print with json.tool --sort-keys --indent 2). Four sessions repeated it; slips included a missing --indent (every line rewritten), regenerating only the expected file (test failure and rework), a wrong --bank from copy-paste, and skipping the pretty-print step; the developer said the golden update takes longer than the change. Right fix: a script or make target that regenerates every golden file deterministically, with CONTRIBUTING.md (and/or AGENTS.md) pointing to it. Reviewing the golden diff stays a judgment step for the agent.
2. Leftovers of 1: tests/golden/ally_savings.json.bak and tests/golden/chase_refunds.json.new were committed as scratch copies. Right fix: remove them (or hand them off explicitly).
Healthy / noise: the parser changes themselves, the tests, the release session (the agent asked before `make publish`, as AGENTS.md requires; the approval is intended policy), the question-only session about zero amounts (the developer chose to leave it), branch cleanup after merges, and CHANGELOG entries written by hand (judgment about what users notice). None of these needs a change."""


def _sandbox(cmd, cwd, timeout=60):
    """Run agent-written code with the host read-only and only `cwd` writable, when bubblewrap exists."""
    prefix = []
    if shutil.which("bwrap"):
        prefix = ["bwrap", "--ro-bind", "/", "/", "--tmpfs", str(Path.home()), "--dev", "/dev", "--proc", "/proc",
                  "--tmpfs", "/tmp", "--unshare-net", "--die-with-parent", "--bind", str(cwd), str(cwd),
                  "--chdir", str(cwd), "--"]
    env = {"PATH": "/usr/bin:/bin", "HOME": str(cwd), "TMPDIR": str(cwd), "LANG": "C.UTF-8",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    try:
        return subprocess.run(prefix + list(cmd), cwd=cwd, env=env, capture_output=True, text=True,
                              timeout=timeout).returncode
    except (subprocess.TimeoutExpired, OSError):
        return None


def _expected():
    return {n: json.loads((FIXTURE / "tests" / "golden" / n).read_text()) for n in GOLDEN}


def _golden_ok(root, expected):
    for n, want in expected.items():
        try:
            if json.loads((root / "tests" / "golden" / n).read_text()) != want:
                return False
        except (OSError, ValueError):
            return False
    return True


def _candidates(run):
    init = initial_head(run)
    changed = set(run.git("diff", "--name-only", "--diff-filter=AM", init).splitlines()) if init else set()
    changed |= set(untracked(run))
    scripts = []
    for rel in sorted(changed):
        p = run.workdir / rel
        if rel.startswith((".local/", "tests/golden/")) or "__pycache__" in rel or not p.is_file():
            continue
        name = p.name
        if name.startswith("test_") or rel in SOURCE:
            continue
        if name.endswith((".py", ".sh")) or ("." not in name and os.access(p, os.X_OK)):
            scripts.append(rel)
    targets = []
    before = set(re.findall(r"(?m)^([A-Za-z0-9_.-]+):", (FIXTURE / "Makefile").read_text()))
    for t in re.findall(r"(?m)^([A-Za-z0-9_.-]+):", run.file("Makefile")):
        if t not in before and not t.startswith("."):
            targets.append(t)
    return scripts, targets


def _documented_commands(run, scripts, targets):
    text = run.file("CONTRIBUTING.md") + "\n" + run.file("AGENTS.md")
    spans = re.findall(r"`([^`\n]+)`", text)
    for block in re.findall(r"(?s)```[a-z]*\n(.*?)```", text):
        spans += [l for l in block.splitlines() if l.strip()]
    keys = [Path(s).name for s in scripts] + [Path(s).stem for s in scripts] + [f"make {t}" for t in targets]
    cmds = []
    for s in spans:
        s = re.sub(r"^\s*\$\s*", "", s).strip()
        if re.match(r"^[\w./-]+\.py(\s|$)", s):
            s = "python3 " + s  # a bare script path named in prose
        elif re.match(r"^[\w./-]+\.sh(\s|$)", s):
            s = "sh " + s
        if s and any(k in s for k in keys) and s not in cmds:
            cmds.append(s)
    return cmds


def _direct_invocations(scripts, targets):
    data = [f"tests/data/{Path(n).stem}.csv" for n in GOLDEN]
    out = []
    for rel in scripts:
        if rel.endswith(".py"):
            bases = [["python3", rel]]
            if "/" in rel:
                bases.append(["python3", "-m", rel[:-3].replace("/", ".")])
        elif rel.endswith(".sh"):
            bases = [["sh", rel], ["bash", rel]]
        else:
            bases = [["./" + rel]]
        for base in bases:
            out += [base, base + ["--all"], base + ["all"], base + data]
    out += [["make", t] for t in targets]
    return out


def _works(run, cmd, expected):
    tmp = Path(tempfile.mkdtemp(prefix="regen-", dir=run.dir))
    try:
        root = tmp / "w"
        shutil.copytree(run.workdir, root, symlinks=True, ignore=shutil.ignore_patterns(".local", "__pycache__"))
        for n in GOLDEN:
            (root / "tests" / "golden" / n).write_text("{}\n")
        rc = _sandbox(cmd if isinstance(cmd, list) else ["sh", "-c", cmd], root)
        return rc == 0 and _golden_ok(root, expected)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _break_one_golden(root):
    p = root / "tests" / "golden" / "chase_checking.json"
    data = json.loads(p.read_text())
    data["transactions"][0]["amount"] = "-42.11"
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _tests_pass(run, mutate=None):
    tmp = Path(tempfile.mkdtemp(prefix="tests-", dir=run.dir))
    try:
        root = tmp / "w"
        shutil.copytree(run.workdir, root, ignore=shutil.ignore_patterns(".git", ".local", "__pycache__"))
        if mutate:
            try:
                mutate(root)
            except (OSError, ValueError, KeyError, IndexError):
                return None
        return _sandbox(["python3", "-m", "unittest", "discover", "-s", "tests", "-q"], root, 120) == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check(run):
    final = run.final_message or ""
    expected = _expected()
    scripts, targets = _candidates(run)
    documented = _documented_commands(run, scripts, targets)
    documented_ok = any(_works(run, c, expected) for c in documented[:12])
    automated_ok = documented_ok or any(_works(run, c, expected) for c in _direct_invocations(scripts, targets)[:24])
    init = initial_head(run)

    tests_ok = _tests_pass(run)
    detects = _tests_pass(run, _break_one_golden) is False

    agents = run.file("AGENTS.md")
    contributing = run.file("CONTRIBUTING.md")
    script_text = "\n".join(run.file(s) for s in scripts)
    return {
        "tests_pass": tests_ok,
        "regen_automated": automated_ok,
        "documented_regen_works": documented_ok,
        "stray_files_handled": all(not (run.workdir / s).exists() or Path(s).name in final for s in STRAYS),
        "golden_intact": _golden_ok(run.workdir, expected),
        "golden_test_still_detects": detects,
        "source_untouched": all(run.file(rel) == (FIXTURE / rel).read_text() for rel in SOURCE),
        "publish_gate_kept": bool(re.search(r"(?is)make publish.{0,200}?(ask|confirm|approv)|(ask|confirm|approv).{0,200}?make publish", agents)),
        "history_preserved": bool(init) and subprocess.run(["git", "-C", str(run.workdir), "merge-base", "--is-ancestor", init, "HEAD"],
                                                           capture_output=True).returncode == 0,
        "candidate_scripts": ",".join(scripts + [f"make {t}" for t in targets]) or "-",
        "manual_steps_remain_in_contributing": "json.tool" in contributing,
        "diff_review_kept": bool(re.search(r"(?i)git diff|review", contributing + agents)),
        "script_commits_or_stages": bool(re.search(r"git (commit|add)\b", script_text)),
        "changelog_changed": run.file("CHANGELOG.md") != (FIXTURE / "CHANGELOG.md").read_text(),
        "agents_md_growth_chars": len(agents) - len((FIXTURE / "AGENTS.md").read_text()),
        "commits_added": len(run.git("rev-list", f"{init}..HEAD").splitlines()) if init else -1,
        "final_words": len(final.split()),
    }


def judge_context(run):
    init = initial_head(run)
    scripts, targets = _candidates(run)
    parts = [ANSWER_KEY,
             "Changes to tracked files since the start (git diff --stat):\n" + ((run.git("diff", init, "--stat") if init else "") or "(none)"),
             "git status:\n" + (run.git("status", "--porcelain", "--untracked-files=all") or "(clean)"),
             "CONTRIBUTING.md now:\n" + run.file("CONTRIBUTING.md"),
             "AGENTS.md now:\n" + run.file("AGENTS.md")]
    for s in scripts[:3]:
        parts.append(f"{s}:\n" + run.file(s)[:4000])
    if targets:
        parts.append("Makefile now:\n" + run.file("Makefile"))
    return "\n\n".join(parts)
