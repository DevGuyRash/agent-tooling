#!/usr/bin/env python3
"""Plant heal-clean's six past agent sessions as the hosts themselves actually keep them, instead of as
markdown transcripts inside the repository checkout: three as Codex rollout JSONL under
``.codex/sessions/YYYY/MM/DD/``, three as Claude Code project JSONL under ``.claude/projects/<encoded-cwd>/``,
each in that host's real current on-disk record shape. Both live under one ``home`` directory (the run's
private $HOME) so a healing pass that only knows the documented host convention, or a script that walks
``~/.codex/sessions`` and ``~/.claude/projects``, finds them the same way it would on a real machine.

Two modes, both run by setup.sh:

``dates`` prints (as ``export KEY=value`` lines, for setup.sh to ``eval``) the git-history commit instant
each of setup.sh's own six commits should use, tied to the same anchor the sessions below use - so the
rebuilt repository's commits, tags, and CHANGELOG.md release dates never drift away from the sessions that
narrate them, however long ago "now" has moved since this scenario was authored (see qualify/README.md's
"commits vs. sessions" note). Two commits (the 0.3.0 release and the README docs commit) have no session of
their own; they take the same day-offset as the nearest story (0.3.0 before `metric`'s 6-day-old session,
the docs commit sharing `mixed-numbers`' 5-day-old date, both at their own original time of day), so the
whole rebuilt history and the six sessions stay in one coherent, moving-with-"now" week.

``write HOME MANIFEST CWD [ANCHOR_ISO]`` writes the six sessions under ``home`` and a checksum ledger to
``manifest`` (see below); ``cwd`` is the real absolute path of the checkout (``$PWD`` from setup.sh)
standing in for the sessions' fictional ``/home/dev/repos/pantry``, substituted into each session's own
recorded ``cwd`` (and, for the three Claude sessions, into the encoded project-folder name) so a gatherer
that gets a session's own recorded working directory finds a real git repository, not a fictional path that
does not exist (see check.py's ``native_logs_unchanged``). ``ANCHOR_ISO`` defaults to now (UTC); each of the
six sessions is dated ``offset_days`` before it, so all six land inside a ``--since 7d`` window whenever the
scenario actually runs, without the fixture ever hard-coding a calendar date.

The checksum ledger ``write`` writes is keyed by ``sha256(relative-path)`` -> ``sha256(content)``, never by
the plaintext relative path: ``verify()`` only needs it to confirm the six planted files are undisturbed, so
it carries no path text and no "codex"/"claude"/"heal" wording (setup.sh writes it outside the directory the
agent is actually told it may look in - see ``references/trials.md``'s "--add-dir"). This also means
``verify()`` never has to re-render a story's expected content from a recomputed "now" or from a file's own
mtime (both of which can disagree with what was actually written, across a midnight rollover or a same-
content touch that only bumps mtime - see the review this replaced), and it never flags an unlisted file
merely appearing under either log root: once a session's own recorded cwd is a real, resolvable directory
(the point of the `cwd` argument above), a real `claude` executor's own live process writes its own session
into that very same `~/.claude/projects/<encoded-cwd>/` folder just by running, and there is no reliable way
to tell that file apart from a planted one by name, directory, or timestamp alone - so this checks exactly
what the answer key promises (the six planted files' own integrity), not exclusive ownership of the
directories they happen to sit in.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
LOCAL_OFFSET = timedelta(hours=-7)  # this scenario's persona has always dated things US-Pacific
DEFAULT_CWD = "/home/dev/repos/pantry"  # used only if a caller supplies none (e.g. ad hoc testing)
CODEX_CLI_VERSION = "0.159.2"
CLAUDE_CLI_VERSION = "2.1.281"
CLAUDE_MODEL = "claude-opus-4-1"
MANIFEST_NAME = ".session-checksums"


def _iso(when: datetime) -> str:
    return when.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _local(when: datetime) -> datetime:
    """Codex's own on-disk folder/file naming uses the local wall clock, not UTC (one of the small tells a
    fabricated log carries otherwise); kept as a fixed offset rather than read from the host running this
    script, so the same scenario produces the same shape wherever it runs."""
    return (when.astimezone(UTC) + LOCAL_OFFSET).replace(tzinfo=None)


def encode_cwd(cwd: str) -> str:
    """The slugging Claude Code uses for a project's log directory name: every character that is not a
    letter or digit becomes '-' (not just '/' - a real encoded path such as a run's own job directory
    carries '.', '_', and '/' all turned into '-')."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def uuid7(ts_ms: int) -> str:
    """A time-ordered UUIDv7 (RFC 9562): the shape real Codex session/thread/item ids carry (a v5 id, as
    this file used to mint for reproducibility, is one of the small tells a fabricated Codex log carries).
    Reproducibility no longer matters once `verify()` checks a checksum ledger captured at write time
    instead of re-deriving expected content, so this is free to be genuinely random, like a real id."""
    rand = os.urandom(10)
    b = bytearray(16)
    b[0:6] = (ts_ms & 0xFFFFFFFFFFFF).to_bytes(6, "big")
    b[6] = 0x70 | (rand[0] & 0x0F)
    b[7] = rand[1]
    b[8] = 0x80 | (rand[2] & 0x3F)
    b[9:16] = rand[3:10]
    return str(uuid.UUID(bytes=bytes(b)))


# ---------------------------------------------------------------- the six stories
#
# Step kinds: ("user"|"agent"|"assistant", text[, gap]) a message; ("exec", cmd, exit_code, output, gap) a
# plain Codex shell command; ("patch", [paths], gap) a Codex apply_patch call, rendered as its own
# FileChange item, never folded into a shell command real Codex would never actually chain it with;
# ("bash", cmd, output, is_error, gap) a Claude Bash tool call; ("read"|"edit", path, gap) a Claude
# Read/Edit tool call. `gap` is seconds until the next step; omitted on a user/agent/assistant step, it
# defaults to 20.

STORIES = [
    {"key": "metric", "host": "codex", "offset_days": 6, "hhmmss": "09:48:31", "steps": [
        ("user", "Add a --metric option to `pantry scale` that prints grams and millilitres instead of "
                  "cups and spoons. Whole numbers are fine."),
        ("exec", "git switch -c feat/metric && sed -n 1,80p pantry/scale.py pantry/units.py", 0,
         "Switched to a new branch 'feat/metric'\n...", 24),
        ("agent", "Plan: a `to_metric` helper in `units.py` (mass to grams, volume to millilitres), a "
                   "`metric` flag through `scale_line`/`scale_text`, and `--metric` on the CLI. Tests "
                   "first for `1 cup milk` -> `237 ml milk`.", 90),
        ("patch", ["pantry/units.py", "pantry/scale.py", "pantry/cli.py", "tests/test_scale.py",
                    "tests/test_units.py"], 130),
        ("exec", "make check", 1,
         "python3 -m unittest discover -s tests -q\n"
         "FAIL: test_metric (test_scale.ScaleTest.test_metric)\n"
         "AssertionError: '236.6 ml milk' != '237 ml milk'\n"
         "Ran 11 tests in 0.003s\nFAILED (failures=1)\nmake: *** [Makefile:4: test] Error 1", 8),
        ("agent", "I formatted with one decimal, but you asked for whole numbers and my test expects "
                   "them. Switching to `round()`.", 14),
        ("patch", ["pantry/scale.py"], 4),
        ("exec", "make check", 0,
         "python3 -m unittest discover -s tests -q\nRan 11 tests in 0.003s\nOK\n"
         "python3 -m compileall -q pantry tests", 22),
        ("patch", ["CHANGELOG.md", "README.md"], 4),
        ("exec", "git add -A && git commit -m \"feat: add scale --metric\"", 0,
         "[feat/metric 70ca611] feat: add scale --metric\n 7 files changed, 31 insertions(+), 6 deletions(-)", 1166),
        ("exec", "git switch main && git merge --ff-only feat/metric && git push && git branch -d feat/metric",
         0, "Switched to branch 'main'\nUpdating 0f6d7f1..70ca611\nFast-forward\n"
            "Deleted branch feat/metric (was 70ca611).", 5),
        ("agent", "`pantry scale FILE --factor F --metric` now prints grams and millilitres rounded to "
                   "whole numbers; units it doesn't know (like `egg`) are left as they are. Merged to "
                   "main as 70ca611."),
    ]},
    {"key": "mixed-numbers", "host": "claude", "offset_days": 5, "hhmmss": "09:10:04", "steps": [
        ("user", "`pantry scale recipes/pancakes.txt --factor 2` says \"2 1/2 cups flour\". The recipe "
                  "says 1 1/2 cups, so it should be 3."),
        ("bash", "git switch -c fix/mixed-numbers && python3 -m pantry scale recipes/pancakes.txt --factor 2 | sed -n 3,4p",
         "Switched to a new branch 'fix/mixed-numbers'\n2 1/2 cups flour\n6 1/2 tsp baking powder", False, 19),
        ("read", "pantry/scale.py", 22),
        ("assistant", "The quantity pattern matches `1` and leaves `1/2` in the rest of the line, so only "
                       "the whole part is scaled. I'll accept a mixed number (`<whole> <num>/<den>`) as "
                       "one quantity and sum its parts.", 108),
        ("edit", "pantry/scale.py", 25),
        ("edit", "tests/test_scale.py", 15),
        ("edit", "tests/test_cli.py", 11),
        ("bash", "make check",
         "python3 -m unittest discover -s tests -q\nRan 12 tests in 0.002s\nOK\npython3 -m compileall -q pantry tests",
         False, 19),
        ("edit", "CHANGELOG.md", 12),
        ("bash", "git add -A && git commit -m \"fix: parse mixed numbers like 1 1/2\" && git switch main && "
                 "git merge --ff-only fix/mixed-numbers && git push",
         "[fix/mixed-numbers 5b0c9e4] fix: parse mixed numbers like 1 1/2\n"
         " 4 files changed, 9 insertions(+), 4 deletions(-)\nSwitched to branch 'main'\n"
         "Updating 70ca611..5b0c9e4\nFast-forward\n"
         "! [rejected]        main -> main (fetch first)\n"
         "error: failed to push some refs to 'github.com:acme-dev/pantry.git'", True, 8),
        ("bash", "git fetch && git log --oneline main..origin/main",
         "10be98a docs: describe the recipe format", False, 8),
        ("assistant", "You pushed a README change this morning. It doesn't overlap with mine, so I'll "
                       "rebase onto it and push.", 7),
        ("bash", "git pull --rebase && make check && git push",
         "Successfully rebased and updated refs/heads/main.\npython3 -m unittest discover -s tests -q\n"
         "Ran 12 tests in 0.002s\nOK\n10be98a..266e2c5  main -> main", False, 700),
        ("bash", "git branch -d fix/mixed-numbers", "error: the branch 'fix/mixed-numbers' is not fully merged.", True, 4),
        ("bash", "git diff fix/mixed-numbers main --stat", " README.md | 2 ++\n 1 file changed, 2 insertions(+)", False, 3),
        ("bash", "git branch -D fix/mixed-numbers", "Deleted branch fix/mixed-numbers (was 5b0c9e4).", False, 3),
        ("assistant", "Fixed: `1 1/2 cups flour` scaled by 2 is now `3 cups flour`. The push was rejected "
                       "once because of your README commit; I rebased onto it (main is 266e2c5) and "
                       "deleted the branch, which differed from main only by your README change after "
                       "the rebase."),
    ]},
    {"key": "release-0.4.0", "host": "codex", "offset_days": 4, "hhmmss": "13:05:12", "steps": [
        ("user", "Release 0.4.0."),
        ("exec", "git status -sb && sed -n 1,12p CHANGELOG.md", 0,
         "## main...origin/main\n# Changelog\n\n## Unreleased\n\n"
         "- Parse mixed numbers such as `1 1/2 cups`.\n- Add `scale --metric` to print grams and millilitres.", 24),
        ("patch", ["CHANGELOG.md", "pantry/__init__.py", "pyproject.toml"], 6),
        ("exec", "make check", 0, "python3 -m unittest discover -s tests -q\nRan 12 tests in 0.002s\nOK", 11),
        ("exec", "git commit -am \"chore: release 0.4.0\" && git tag -a v0.4.0 -m \"pantry 0.4.0\" && git push --follow-tags",
         0, "[main 72f894c] chore: release 0.4.0\n 3 files changed, 4 insertions(+), 2 deletions(-)\n"
            "266e2c5..72f894c  main -> main\n * [new tag]         v0.4.0 -> v0.4.0", 9),
        ("agent", "0.4.0 is committed and tagged. `make release` publishes it to the package index; per "
                   "AGENTS.md I'm checking with you first. Publish now?", 379),
        ("user", "go", 5),
        ("exec", "make release", 0,
         "python3 -m unittest discover -s tests -q\nRan 12 tests in 0.002s\nOK\n"
         "rm -rf dist && python3 -m build && python3 -m twine upload dist/*\n"
         "Successfully built pantry-0.4.0.tar.gz and pantry-0.4.0-py3-none-any.whl\n"
         "https://pypi.org/project/pantry/0.4.0/", 4),
        ("agent", "Published pantry 0.4.0 (https://pypi.org/project/pantry/0.4.0/), tagged v0.4.0 at 72f894c."),
    ]},
    {"key": "ounces", "host": "claude", "offset_days": 3, "hhmmss": "16:20:57", "steps": [
        ("user", "`pantry convert 8 oz g` says it can't convert. Add ounces and pounds."),
        ("bash", "git switch -c feat/ounces", "Switched to a new branch 'feat/ounces'", False, 6),
        ("read", "pantry/units.py", 30),
        ("edit", "pantry/units.py", 35),
        ("edit", "tests/test_units.py", 16),
        ("edit", "tests/test_scale.py", 9),
        ("bash", "make chekc", "make: *** No rule to make target 'chekc'.  Stop.", True, 3),
        ("bash", "make check",
         "python3 -m unittest discover -s tests -q\nRan 13 tests in 0.002s\nOK\npython3 -m compileall -q pantry tests",
         False, 19),
        ("bash", "python3 -m pantry convert 8 oz g && python3 -m pantry convert 2 lb oz", "226.80 g\n32.00 oz", False, 18),
        ("edit", "CHANGELOG.md", 13),
        ("bash", "git add -A && git commit -m \"feat: convert ounces and pounds\"",
         "[feat/ounces 9c603f6] feat: convert ounces and pounds\n 4 files changed, 9 insertions(+), 1 deletion(-)",
         False, 867),
        ("user", "merge", 4),
        ("bash", "git switch main && git merge --ff-only feat/ounces && git push && git branch -d feat/ounces",
         "Switched to branch 'main'\nUpdating 72f894c..9c603f6\nFast-forward\nDeleted branch feat/ounces (was 9c603f6).",
         False, 5),
        ("assistant", "Merged (9c603f6). `convert` and `scale --metric` handle `oz` and `lb` (and their spelled-out names)."),
    ]},
    {"key": "pypi-check", "host": "codex", "offset_days": 2, "hhmmss": "11:02:48", "steps": [
        ("user", "Is 0.4.0 the newest pantry on the package index?"),
        ("exec", "pip index versions pantry", 1,
         "WARNING: Retrying ... Failed to establish a new connection: [Errno -3] Temporary failure in "
         "name resolution\nERROR: No matching distribution found for pantry", 32),
        ("agent", "DNS failed for the package index just now; trying again.", 11),
        ("exec", "pip index versions pantry", 0, "pantry (0.4.0)\nAvailable versions: 0.4.0, 0.3.0, 0.2.0, 0.1.0", 5),
        ("agent", "Yes. The index lists 0.4.0 as the latest (0.4.0, 0.3.0, 0.2.0, 0.1.0), which matches "
                   "the v0.4.0 tag. The first lookup failed on a temporary DNS error; the retry worked."),
    ]},
    {"key": "pancakes", "host": "claude", "offset_days": 1, "hhmmss": "07:40:13", "steps": [
        ("user", "Scale recipes/pancakes.txt by 3 for Saturday, and give me the metric version too."),
        ("bash", "python3 -m pantry scale recipes/pancakes.txt --factor 3 && echo ---- && "
                 "python3 -m pantry scale recipes/pancakes.txt --factor 3 --metric",
         "Pancakes (serves 4)\n\n4 1/2 cups flour\n10 1/2 tsp baking powder\n3 tbsp sugar\n3/4 tsp salt\n"
         "3 3/4 cups milk\n3 egg\n9 tbsp butter, melted\n----\nPancakes (serves 4)\n\n1065 ml flour\n"
         "52 ml baking powder\n44 ml sugar\n4 ml salt\n887 ml milk\n3 egg\n133 ml butter, melted",
         False, 11),
        ("assistant", "Tripled (serves 12):\n\n- 4 1/2 cups flour (1065 ml)\n- 10 1/2 tsp baking powder (52 ml)\n"
                       "- 3 tbsp sugar (44 ml)\n- 3/4 tsp salt (4 ml)\n- 3 3/4 cups milk (887 ml)\n- 3 eggs\n"
                       "- 9 tbsp melted butter (133 ml)\n\nThe title line still says \"serves 4\" because "
                       "pantry leaves non-ingredient lines unchanged.", 31),
        ("user", "perfect, thanks"),
    ]},
]

# Git-history commit instants with no session of their own: offset_days mirrors the nearest story's, so
# they land on the same moving-with-"now" week (see history_dates below). hhmmss is each commit's own
# original time of day (kept fixed; only the calendar day moves with "now").
_NO_SESSION_COMMITS = {
    "v030": (8, "18:02:10"),   # chore: release 0.3.0 - before `metric`'s 6-day-old session
    "docs": (5, "08:51:30"),   # docs: describe the recipe format - same day as `mixed-numbers`, earlier
}
# The four commits a story's own session actually makes, keyed the same way, at that commit's real moment
# (kept fixed; only the calendar day moves with "now").
_SESSION_COMMITS = {
    "metric": "10:07:45",
    "mixed": "09:26:12",       # story key "mixed-numbers"; kept short so the exported var is METRIC/MIXED/...
    "v040": "13:12:40",        # story key "release-0.4.0"
    "ounces": "16:38:02",
}
_SESSION_KEY_FOR = {"metric": "metric", "mixed": "mixed-numbers", "v040": "release-0.4.0", "ounces": "ounces"}


def _story_start(story: dict, anchor: datetime) -> datetime:
    h, m, s = (int(x) for x in story["hhmmss"].split(":"))
    day = (anchor.astimezone(UTC) - timedelta(days=story["offset_days"])).date()
    return datetime(day.year, day.month, day.day, h, m, s, tzinfo=UTC)


PACIFIC = timezone(timedelta(hours=-7))


def history_dates(anchor: datetime) -> dict[str, str]:
    """The instant each of setup.sh's own six commits should use, and the bare date each CHANGELOG.md
    release heading should show, tied to the same `anchor` the six sessions above use (see this module's
    docstring). Kept in -07:00, matching the sessions' own narrative clock."""
    anchor_date = anchor.astimezone(PACIFIC).date()
    out: dict[str, str] = {}
    for key, (offset_days, hhmmss) in _NO_SESSION_COMMITS.items():
        day = anchor_date - timedelta(days=offset_days)
        h, m, s = (int(x) for x in hhmmss.split(":"))
        out[f"{key.upper()}_COMMIT"] = datetime(day.year, day.month, day.day, h, m, s, tzinfo=PACIFIC).isoformat()
        out[f"{key.upper()}_DATE"] = day.isoformat()
    for key, hhmmss in _SESSION_COMMITS.items():
        story = next(s for s in STORIES if s["key"] == _SESSION_KEY_FOR[key])
        day = anchor_date - timedelta(days=story["offset_days"])
        h, m, s = (int(x) for x in hhmmss.split(":"))
        out[f"{key.upper()}_COMMIT"] = datetime(day.year, day.month, day.day, h, m, s, tzinfo=PACIFIC).isoformat()
        out[f"{key.upper()}_DATE"] = day.isoformat()
    return out


# ---------------------------------------------------------------- Codex rollout JSONL

def render_codex(story: dict, when: datetime, cwd: str) -> tuple[str, str, datetime]:
    session_id = uuid7(int(when.timestamp() * 1000))
    lines: list[str] = []
    ordinal = 0
    last_ts = when

    def emit(ts: datetime, typ: str, payload: dict) -> None:
        nonlocal ordinal, last_ts
        lines.append(json.dumps({"timestamp": _iso(ts), "ordinal": ordinal, "type": typ, "payload": payload},
                                 separators=(",", ":")))
        ordinal += 1
        last_ts = max(last_ts, ts)

    emit(when, "session_meta", {"id": session_id, "timestamp": _iso(when), "cwd": cwd,
                                 "originator": "codex_exec", "cli_version": CODEX_CLI_VERSION, "source": "cli",
                                 "thread_source": "user", "model_provider": "openai"})
    t, turn_id = when, None
    for step in story["steps"]:
        role = step[0]
        if role == "user":
            text = step[1]
            gap = step[2] if len(step) > 2 else 20
            turn_id = str(uuid.uuid4())
            emit(t, "event_msg", {"type": "task_started", "turn_id": turn_id, "started_at": int(t.timestamp())})
            emit(t, "response_item", {"type": "message", "role": "user",
                                       "content": [{"type": "input_text", "text": text}]})
            emit(t, "event_msg", {"type": "item_completed", "thread_id": session_id, "turn_id": turn_id,
                                   "item": {"type": "UserMessage", "id": str(uuid.uuid4()),
                                             "content": [{"type": "text", "text": text}]},
                                   "started_at_ms": int(t.timestamp() * 1000),
                                   "completed_at_ms": int(t.timestamp() * 1000)})
        elif role == "agent":
            text = step[1]
            gap = step[2] if len(step) > 2 else 20
            emit(t, "response_item", {"type": "message", "role": "assistant",
                                       "content": [{"type": "output_text", "text": text}]})
            emit(t, "event_msg", {"type": "item_completed", "thread_id": session_id, "turn_id": turn_id,
                                   "item": {"type": "AgentMessage", "id": str(uuid.uuid4()),
                                             "content": [{"type": "Text", "text": text}]},
                                   "started_at_ms": int(t.timestamp() * 1000),
                                   "completed_at_ms": int(t.timestamp() * 1000)})
            if turn_id:
                emit(t, "event_msg", {"type": "task_complete", "turn_id": turn_id, "last_agent_message": text,
                                       "completed_at": int(t.timestamp())})
        elif role == "exec":
            cmd, exit_code, output, gap = step[1], step[2], step[3], step[4]
            call_id = str(uuid.uuid4())
            emit(t, "response_item", {"type": "function_call", "name": "exec_command", "call_id": call_id,
                                       "arguments": json.dumps({"cmd": cmd, "workdir": cwd})})
            emit(t, "response_item", {"type": "function_call_output", "call_id": call_id,
                                       "output": f"Wall time: 0.400 seconds\nProcess exited with code "
                                                 f"{exit_code}\nOutput:\n{output}"})
            emit(t, "event_msg", {"type": "item_completed", "thread_id": session_id, "turn_id": turn_id,
                                   "item": {"type": "CommandExecution", "id": str(uuid.uuid4()),
                                             "command": ["bash", "-lc", cmd], "cwd": cwd,
                                             "status": "completed" if exit_code == 0 else "failed",
                                             "exit_code": exit_code, "aggregated_output": output},
                                   "started_at_ms": int(t.timestamp() * 1000),
                                   "completed_at_ms": int((t + timedelta(seconds=1)).timestamp() * 1000)})
        elif role == "patch":
            paths, gap = step[1], step[2]
            call_id = str(uuid.uuid4())
            emit(t, "response_item", {"type": "function_call", "name": "apply_patch", "call_id": call_id,
                                       "arguments": json.dumps({"files": paths})})
            emit(t, "response_item", {"type": "function_call_output", "call_id": call_id,
                                       "output": f"Success. Updated {len(paths)} "
                                                 f"file{'s' if len(paths) != 1 else ''}."})
            emit(t, "event_msg", {"type": "item_completed", "thread_id": session_id, "turn_id": turn_id,
                                   "item": {"type": "FileChange", "id": str(uuid.uuid4()),
                                             "changes": [{"path": p, "kind": "update"} for p in paths],
                                             "status": "completed"},
                                   "started_at_ms": int(t.timestamp() * 1000),
                                   "completed_at_ms": int(t.timestamp() * 1000)})
        else:
            raise ValueError(f"unknown codex step role {role!r}")
        t = t + timedelta(seconds=gap)
    local_when = _local(when)
    stamp = local_when.strftime("%Y-%m-%dT%H-%M-%S")
    rel = f".codex/sessions/{local_when.strftime('%Y/%m/%d')}/rollout-{stamp}-{session_id}.jsonl"
    return rel, "\n".join(lines) + "\n", last_ts


def codex_dir(home: Path) -> Path:
    return home / ".codex" / "sessions"


# ---------------------------------------------------------------- Claude Code project JSONL

_BRANCH_SWITCH = re.compile(r"git switch (?:-c )?(\S+)")


def render_claude(story: dict, when: datetime, cwd: str) -> tuple[str, str, datetime]:
    session_id = str(uuid.uuid4())  # real Claude Code session ids are v4, unlike Codex's v7
    lines: list[str] = []
    parent = None
    branch = "main"
    last_ts = when

    def emit(ts: datetime, kind: str, message: dict, extra: dict | None = None) -> None:
        nonlocal parent, last_ts
        u = str(uuid.uuid4())
        rec = {"type": kind, "uuid": u, "parentUuid": parent, "sessionId": session_id, "cwd": cwd,
               "gitBranch": branch, "isSidechain": False, "userType": "external", "entrypoint": "cli",
               "version": CLAUDE_CLI_VERSION, "timestamp": _iso(ts), "message": message}
        if extra:
            rec.update(extra)
        lines.append(json.dumps(rec, separators=(",", ":")))
        parent = u
        last_ts = max(last_ts, ts)

    t = when
    for step in story["steps"]:
        role = step[0]
        if role == "user":
            emit(t, "user", {"role": "user", "content": step[1]})
            gap = step[2] if len(step) > 2 else 20
        elif role == "assistant":
            emit(t, "assistant", {"role": "assistant", "model": CLAUDE_MODEL,
                                   "id": f"msg_{uuid.uuid4().hex[:24]}",
                                   "content": [{"type": "text", "text": step[1]}], "stop_reason": "end_turn"})
            gap = step[2] if len(step) > 2 else 20
        elif role in ("read", "edit"):
            path, gap = step[1], step[2]
            name = "Read" if role == "read" else "Edit"
            call_id = f"toolu_{uuid.uuid4().hex[:24]}"
            emit(t, "assistant", {"role": "assistant", "model": CLAUDE_MODEL, "id": f"msg_{uuid.uuid4().hex[:24]}",
                                   "content": [{"type": "tool_use", "id": call_id, "name": name,
                                                 "input": {"file_path": path}}], "stop_reason": "tool_use"})
            content = f"(contents of {path})" if role == "read" else f"Updated {path}"
            emit(t + timedelta(seconds=2), "user",
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id,
                                                 "content": content, "is_error": False}]},
                 extra={"toolUseResult": {"stdout": content, "stderr": "", "interrupted": False}})
        elif role == "bash":
            cmd, output, is_error, gap = step[1], step[2], step[3], step[4]
            call_id = f"toolu_{uuid.uuid4().hex[:24]}"
            emit(t, "assistant", {"role": "assistant", "model": CLAUDE_MODEL, "id": f"msg_{uuid.uuid4().hex[:24]}",
                                   "content": [{"type": "tool_use", "id": call_id, "name": "Bash",
                                                 "input": {"command": cmd}}], "stop_reason": "tool_use"})
            matches = list(_BRANCH_SWITCH.finditer(cmd))
            if matches:
                branch = matches[-1].group(1)
            emit(t + timedelta(seconds=2), "user",
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id,
                                                 "content": output, "is_error": is_error}]},
                 extra={"toolUseResult": {"stdout": "" if is_error else output,
                                            "stderr": output if is_error else "", "interrupted": False}})
        else:
            raise ValueError(f"unknown claude step role {role!r}")
        t = t + timedelta(seconds=gap)
    rel = f".claude/projects/{encode_cwd(cwd)}/{session_id}.jsonl"
    return rel, "\n".join(lines) + "\n", last_ts


def claude_dir(home: Path, cwd: str) -> Path:
    return home / ".claude" / "projects" / encode_cwd(cwd)


# ---------------------------------------------------------------- write / verify

def write_all(home: Path, manifest_path: Path, anchor: datetime, cwd: str) -> list[Path]:
    """Write every story into `home`, and record a sha256(relative path) -> sha256(content) checksum
    ledger at `manifest_path` for `verify()` (see this module's docstring)."""
    written = []
    manifest_lines = []
    for story in STORIES:
        when = _story_start(story, anchor)
        renderer = render_codex if story["host"] == "codex" else render_claude
        rel, data, last_ts = renderer(story, when, cwd)
        dest = home / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(data)
        stamp = last_ts.timestamp()
        os.utime(dest, (stamp, stamp))  # each file's mtime is its own last record, not "whenever setup.sh ran"
        manifest_lines.append(f"{hashlib.sha256(rel.encode()).hexdigest()}\t{hashlib.sha256(data.encode()).hexdigest()}")
        written.append(dest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("\n".join(manifest_lines) + "\n")
    return written


def verify(home: Path, manifest: str, read=None) -> dict:
    """Compare the six planted files against the checksum ledger `write_all` recorded at plant time. See
    this module's docstring for why this is ledger-based rather than a re-derived-content or mtime
    comparison, and why an unlisted extra `.jsonl` file under either root is never itself a problem.
    `read` defaults to a plain file read; a caller checking an agent-writable tree should pass something
    like a trial.py Run's own `run.read` instead, so a symlink the agent planted cannot make this read
    outside the run directory (an escape simply reads back as "", which correctly shows up as "changed
    below")."""
    read = read or (lambda p: p.read_text(errors="replace"))
    if not manifest.strip():
        return {"ok": False, "problems": ["no manifest recorded by setup.sh"], "found": 0}
    expected = {}
    for line in manifest.strip().splitlines():
        if "\t" in line:
            path_hash, content_hash = line.split("\t", 1)
            expected[path_hash] = content_hash
    found = {}  # sha256(relative path) -> relative path, for every file under either root
    for root in (".codex/sessions", ".claude/projects"):
        base = home / root
        if not base.is_dir() or base.is_symlink():
            continue
        # followlinks=False: a symlink the agent planted under its own home is never descended into, so a
        # self-referential loop there cannot hang this check the way rglob could.
        for dirpath, _, filenames in os.walk(base, followlinks=False):
            for name in sorted(filenames):
                p = Path(dirpath) / name
                if p.is_file() and not p.is_symlink():
                    rel = p.relative_to(home).as_posix()
                    found[hashlib.sha256(rel.encode()).hexdigest()] = rel
    problems = []
    for h, content_hash in expected.items():
        rel = found.get(h)
        if rel is None:
            problems.append(f"missing (planted file {h[:12]}...)")
        else:
            content = read(home / rel)
            if not content or hashlib.sha256(content.encode()).hexdigest() != content_hash:
                problems.append(f"changed: {rel}")
    return {"ok": not problems, "problems": sorted(problems), "found": len(expected)}


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "dates":
        anchor_arg = datetime.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime.now(UTC)
        for k, v in history_dates(anchor_arg).items():
            print(f"export {k}={v}")
    elif mode == "write" and len(sys.argv) >= 5:
        home_dir = Path(sys.argv[2])
        manifest_arg = Path(sys.argv[3])
        cwd_arg = sys.argv[4]
        anchor_arg = datetime.fromisoformat(sys.argv[5]) if len(sys.argv) > 5 else datetime.now(UTC)
        for p in write_all(home_dir, manifest_arg, anchor_arg, cwd_arg):
            print(p)
    else:
        sys.exit(__doc__)
