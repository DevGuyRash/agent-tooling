#!/usr/bin/env python3
"""Writes the seven meterwatch agent sessions as Goose session files, where Goose keeps them, inside this
run's own private HOME - never inside the repository fixture.

Harness: Goose (https://github.com/block/goose, now https://github.com/aaif-goose/goose). Releases up to v1.9.x
keep each session as one JSON Lines file, `<data dir>/sessions/<YYYYMMDD_HHMMSS>.jsonl`, with `<data dir>` the XDG
data directory of the app `goose` (`~/.local/share/goose`). From v1.10.0 on, new sessions go into a SQLite
database (`sessions/sessions.db`) and the importer reads these JSON Lines files as legacy records, so this
scenario models a developer who still runs a v1.9 Goose. Format sources, all at tag v1.9.3
(3fd207603520ebc9fa8af99ee80ace29f440b775) unless noted:

- crates/goose/src/session/storage.rs: `ensure_session_dir` (`<data_dir>/sessions`), `generate_session_id`
  (`Local::now()` as `%Y%m%d_%H%M%S`, so the file name carries the machine's LOCAL wall-clock time), the `.jsonl`
  extension, and `save_messages_with_metadata`: the first line is `SessionMetadata`
  (working_dir, description, schedule_id, message_count, total_tokens, input_tokens, output_tokens,
  accumulated_total_tokens, accumulated_input_tokens, accumulated_output_tokens, extension_data, recipe), every
  following line one `Message`, compact `serde_json`, file mode 0600.
- crates/goose/src/conversation/message.rs: `Message` = id (null unless the provider or the agent set one), role
  ("user" | "assistant"), created (Unix seconds, UTC), content (array), metadata (userVisible, agentVisible);
  `MessageContent` is tagged by "type": "text", "toolRequest" (id, toolCall), "toolResponse" (id, toolResult);
  tool_result_serde writes `{"status": "success", "value": ...}`; ToolCall is `{name, arguments}`.
- crates/goose/src/agents/agent.rs: the user message that carries tool results has the id `msg_<uuid v4>`;
  crates/goose/src/providers/formats/anthropic.rs builds one assistant message per response (text blocks, then
  tool_use blocks as toolRequest items, Anthropic's own tool-use ids) with no message id.
- crates/goose-mcp/src/developer/rmcp_developer.rs and text_editor.rs: tool names reach the model as
  `developer__shell` and `developer__text_editor`; `shell` returns the merged stdout/stderr (no exit status) as two
  text contents (audience assistant; audience user with priority 0.0); `text_editor` `str_replace` answers with
  "The file X has been edited, and the section now reads:" and a snippet (see `snippet`), annotated the same way
  (the user copy with priority 0.2). rmcp 0.6.2 serializes annotations as `{"audience": [...], "priority": ...}`.
- crates/goose/src/session/legacy.rs on main (bfcc6ee6f1ee18d0c4c852a65c49b25f87ee40dc) still reads exactly this
  layout, and documentation/docs/guides/sessions/session-management.md at v1.9.3 names `~/.local/share/goose/sessions`.

Everything an agent did in a session is derived from the repository itself, so the logs cannot drift from it: file
edits are the hunks between the history states (history/cK on top of fixture/), test and `make` output comes from
really running that state's tests in the developer's time zone (a POSIX `HST10`, Pacific/Honolulu, no daylight
saving), and `git` output (stat lines, short hashes) comes from the repository setup.sh just built.

The developer's machine is on Hawaii time; CI and the shipped code are on UTC. That is the problem the sessions
carry (see check.py's ANSWER_KEY): the repository alone shows a time-dependent test helper but never that it fails.

Usage:
  goose_sessions.py dates ANCHOR_ISO                 print `export` lines (commit dates, subjects, branches)
  goose_sessions.py render ANCHOR_ISO HOME LEDGER CWD   write the sessions under HOME and a checksum ledger
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
UTC = timezone.utc
ZONE = timedelta(hours=-10)  # the developer's machine: Pacific/Honolulu (HST); no daylight saving time
ZONE_ABBR = "HST"
DEV_TZ = "HST10"  # the same zone as a POSIX string, so no tz database is needed to reproduce the sessions
REMOTE = "github.com:acme-dev/meterwatch.git"
INDEX_URL = "https://packages.acme.example"
SESSION_DIR = Path(".local") / "share" / "goose" / "sessions"

# key, branch (None: committed on main), subject. The single source for setup.sh (see `dates`).
COMMITS = [
    ("base", None, "chore: release 0.2.0"),
    ("keyfilter", "feat/key-filter", "feat: filter daily totals by key"),
    ("top", "feat/top", "feat: add top command"),
    ("docs", None, "docs: describe the invoice flags"),
    ("invoice", "fix/invoice-end-day", "fix: include the last day in invoice --to"),
    ("total", "feat/daily-total", "feat: add --total to daily"),
    ("release", None, "chore: release 0.3.0"),
    ("since", "feat/daily-since", "feat: add --since to daily"),
]
SUBJECT = {key: subject for key, _, subject in COMMITS}

# How long before the anchor each session's CLI was launched: (days, hours, minutes, seconds). Consecutive
# sessions are more than 24 hours apart, so each lands on its own calendar day wherever the anchor falls, and the
# oldest is inside a week.
BACK = {
    "key-filter": (6, 14, 7, 19),
    "invoice-question": (5, 13, 22, 41),
    "top": (4, 12, 41, 8),
    "invoice-end": (3, 11, 19, 52),
    "total": (2, 10, 44, 27),
    "release": (1, 9, 12, 3),
    "since": (0, 7, 53, 36),
}
BASE_BACK = timedelta(days=9, hours=3, minutes=21)  # the 0.2.0 release commit
FIRST_RELEASE_BACK = timedelta(days=31, hours=5)  # 0.1.0, only for the changelog heading
SENTINELS = {"2026-09-01": "first", "2026-09-26": "base", "2026-10-13": "release"}  # CHANGELOG.md in the fixture


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def parse_anchor(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def start_of(anchor: datetime, key: str) -> datetime:
    d, h, m, s = BACK[key]
    return anchor - timedelta(days=d, hours=h, minutes=m, seconds=s)


def changelog_dates(anchor: datetime) -> dict[str, str]:
    """The three release dates CHANGELOG.md carries as sentinels. The 0.3.0 date is the day the release session ran
    `date`, which the session itself decides, so the release session is played once to find it (dates are all the
    same length, so playing it again with the real one changes nothing about its timing)."""
    local = lambda t: (t + ZONE).strftime("%Y-%m-%d")  # noqa: E731
    dates = {
        "2026-09-01": local(anchor - FIRST_RELEASE_BACK),
        "2026-09-26": local(anchor - BASE_BACK),
        "2026-10-13": local(start_of(anchor, "release")),
    }
    rec = s_release(Ctx(anchor, load_states(dates), "/work", dry=True))
    dates["2026-10-13"] = local(rec.marks["date"])
    return dates


def fix_dates(text: str, dates: dict[str, str]) -> str:
    """Replace each sentinel date once, in a single pass: a real date may equal another sentinel."""
    return re.sub("|".join(map(re.escape, dates)), lambda m: dates[m.group(0)], text)


# ------------------------------------------------------------------------------------------ repository states

def read_tree(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    return {p.relative_to(root).as_posix(): p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


def load_states(dates: dict[str, str]) -> list[dict[str, str]]:
    """State k = the fixture with history/c0..ck laid over it, the way setup.sh rebuilds the history."""
    current = read_tree(HERE / "fixture")
    final = dict(current)
    states = []
    for k in range(8):
        current.update(read_tree(HERE / "history" / f"c{k}"))
        states.append({rel: fix_dates(text, dates) for rel, text in current.items()})
    assert current == final, "history/c7 must end at the fixture"
    return states


def hunks(old_text: str, new_text: str, gap: int = 3) -> list[tuple[str, str]]:
    """The edits that turn old_text into new_text as (old_str, new_str) pairs, each old_str unique in old_text."""
    a, b = old_text.splitlines(keepends=True), new_text.splitlines(keepends=True)
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
    groups: list[list] = []
    for op in ops:
        if groups and op[1] - groups[-1][-1][2] <= gap:
            groups[-1].append(op)
        else:
            groups.append([op])
    out = []
    for group in groups:
        lo, hi, jl, jh = group[0][1], group[-1][2], group[0][3], group[-1][4]
        while True:
            old = "".join(a[lo:hi])
            if old and old_text.count(old) == 1:
                break
            if lo > 0:
                lo, jl = lo - 1, jl - 1
            elif hi < len(a):
                hi, jh = hi + 1, jh + 1
            else:
                break
        out.append(("".join(a[lo:hi]), "".join(b[jl:jh])))
    return out


LANG = {"py": "python", "md": "markdown", "toml": "toml", "yml": "yaml", "sh": "bash"}


def snippet(content_before: str, old: str, new_content: str) -> str:
    """text_editor_replace's snippet, line for line (including its habit of running to the end of the file)."""
    replacement_line = content_before.split(old)[0].count("\n")
    start = max(0, replacement_line - 4)
    end = replacement_line + 4 + new_content.count("\n")
    lines = new_content.splitlines()
    return "\n".join(lines[start:start + (end - start + 1)])


# ------------------------------------------------------------------------------------------------ test runs

def run_unittest(files: dict[str, str], tz: str, args: tuple[str, ...] = ()) -> tuple[int, str]:
    """Really run `python3 -m unittest discover -s tests -q ARGS` on a tree, with the TZ the developer's shell has."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "TZ": tz, "LANG": "C.UTF-8",
               "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(root)}
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q", *args], cwd=root,
                           env=env, capture_output=True, text=True, timeout=120)
        return r.returncode, (r.stdout + r.stderr).replace(str(root), "{cwd}")


def make_test(files, tz=DEV_TZ):
    rc, out = run_unittest(files, tz)
    return "python3 -m unittest discover -s tests -q\n" + out + ("make: *** [Makefile:4: test] Error 1\n" if rc else "")


def tail(text: str, n: int) -> str:
    return "".join(text.splitlines(keepends=True)[-n:])


def unittest_k(files, pattern, tz=DEV_TZ):
    return run_unittest(files, tz, ("-k", pattern))[1]


# ------------------------------------------------------------------------------------------------ the recorder

ALNUM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def jdump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def content_text(text, audience, priority=None):
    annotations = {"audience": [audience]}
    if priority is not None:
        annotations["priority"] = priority
    return {"type": "text", "text": text, "annotations": annotations}


def message(role, created, content, mid=None):
    return {"id": mid, "role": role, "created": created, "content": content,
            "metadata": {"userVisible": True, "agentVisible": True}}


class Ctx:
    def __init__(self, anchor, states, cwd, dry, git_run=None, shas=None):
        self.anchor, self.states, self.cwd, self.dry = anchor, states, cwd, dry
        self.git_run, self.shas = git_run, shas or {}

    def sha(self, key):
        return self.shas.get(key, "0000000")

    def full(self, key):
        return self.shas.get(key + ":full", "0" * 40)

    def git(self, *args):
        return "" if self.dry else self.git_run(*args)


class Rec:
    """Builds one session's message list. Times follow the real agent loop: an assistant message is stamped when the
    model's reply arrives; the user message carrying tool results is stamped when it is created, just before the tool
    runs; the next reply comes after the tool finished and the model answered."""

    def __init__(self, ctx: Ctx, key: str, base_state: int, description: str):
        self.ctx, self.key, self.description = ctx, key, description
        self.start = start_of(ctx.anchor, key)
        self.t = self.start.timestamp()
        self.rng = random.Random(f"meterwatch/{key}")
        self.files = dict(ctx.states[base_state])
        self.messages: list[dict] = []
        self.marks: dict[str, datetime] = {}

    # -- plumbing
    def _id(self, n):
        return "".join(self.rng.choice(ALNUM) for _ in range(n))

    def _latency(self, *parts):
        return 2.5 + sum(len(p) for p in parts) / 45.0 + self.rng.random() * 3.0

    def _abs(self, rel):
        return f"{self.ctx.cwd}/{rel}"

    def mark(self, name):
        self.marks[name] = datetime.fromtimestamp(self.t, UTC)

    # -- messages
    def user(self, text, think):
        self.t += think
        self.messages.append(message("user", int(self.t), [{"type": "text", "text": text}]))

    def say(self, text):
        self.t += self._latency(text)
        self.messages.append(message("assistant", int(self.t), [{"type": "text", "text": text}]))

    def tool(self, text, name, args, contents, run_s=1.0, mark=None):
        # how long the model takes to write a call must not depend on where this run's checkout happens to be
        self.t += self._latency(text or "", jdump(args).replace(self.ctx.cwd, ""))
        created = int(self.t)
        if callable(contents):
            contents = contents(created)
        tid = "toolu_01" + self._id(22)
        items = ([{"type": "text", "text": text}] if text else []) + [
            {"type": "toolRequest", "id": tid, "toolCall": {"status": "success",
                                                             "value": {"name": f"developer__{name}", "arguments": args}}}]
        self.messages.append(message("assistant", created, items))
        response_id = "msg_" + str(uuid.UUID(int=self.rng.getrandbits(128), version=4))
        self.messages.append(message("user", created + (1 if self.rng.random() < 0.3 else 0),
                                     [{"type": "toolResponse", "id": tid,
                                       "toolResult": {"status": "success", "value": contents}}], mid=response_id))
        if mark:
            self.mark(mark)
        self.t += run_s

    # -- tools
    def sh(self, text, command, output, run_s=1.0, mark=None):
        def contents(created):
            out = (output(created) if callable(output) else output).replace("{cwd}", self.ctx.cwd)
            assert len(out.splitlines()) <= 100, f"{self.key}: {command!r} printed more than the 100 lines the shell tool keeps"
            return [content_text(out, "assistant"), content_text(out, "user", 0.0)]
        self.tool(text, "shell", {"command": command}, contents, run_s, mark)

    def str_replace(self, text, rel, old, new):
        content = self.files[rel]
        assert content.count(old) == 1, f"{self.key}: {rel}: old_str occurs {content.count(old)} times: {old[:50]!r}"
        updated = content.replace(old, new)
        lang = LANG.get(rel.rsplit(".", 1)[-1], "")
        shown = f"```{lang}\n{snippet(content, old, updated)}\n```\n"
        path = self._abs(rel)
        self.tool(text, "text_editor", {"command": "str_replace", "path": path, "old_str": old, "new_str": new},
                  [content_text(f"The file {path} has been edited, and the section now reads:\n{shown}\n"
                                "Review the changes above for errors. Undo and edit the file again if necessary!\n",
                            "assistant"),
                   content_text(shown, "user", 0.2)], run_s=0.2)
        self.files[rel] = updated

    def edit(self, text, rel, target_state, typo=None):
        """One str_replace per hunk between the file as it is now and as it is in target_state."""
        goal = self.ctx.states[target_state][rel]
        pairs = hunks(self.files[rel], goal)
        for i, (old, new) in enumerate(pairs):
            if typo and typo[1] in new:
                new = new.replace(typo[1], typo[0], 1)
                typo = None
            self.str_replace(text if i == 0 else None, rel, old, new)

    def settle(self, state):
        """The repository after a rebase or checkout: the tracked files are those of `state`."""
        self.files = dict(self.ctx.states[state])

    def status_short(self, committed_state):
        base = self.ctx.states[committed_state]
        return "".join(f" M {rel}\n" for rel in sorted(self.files) if rel in base and base[rel] != self.files[rel])

    # -- the file
    def finish(self, target_state=None):
        if target_state is not None:
            want = self.ctx.states[target_state]
            assert self.files == want, f"{self.key}: workspace differs from state c{target_state}: " + ", ".join(
                rel for rel in sorted(set(self.files) | set(want)) if self.files.get(rel) != want.get(rel))
        return self

    def render(self) -> tuple[str, str, datetime]:
        cum_in, cum_out, last = 0, 0, (0, 0)
        history_chars = 0
        for m in self.messages:
            size = len(jdump(m["content"]))
            if m["role"] == "assistant":
                tokens_in = 7200 + history_chars // 4
                tokens_out = max(24, size // 4)
                cum_in, cum_out, last = cum_in + tokens_in, cum_out + tokens_out, (tokens_in, tokens_out)
            history_chars += size
        metadata = {"working_dir": self.ctx.cwd, "description": self.description, "schedule_id": None,
                    "message_count": len(self.messages), "total_tokens": sum(last), "input_tokens": last[0],
                    "output_tokens": last[1], "accumulated_total_tokens": cum_in + cum_out,
                    "accumulated_input_tokens": cum_in, "accumulated_output_tokens": cum_out,
                    "extension_data": {}, "recipe": None}
        lines = [jdump(metadata)] + [jdump(m) for m in self.messages]
        stamp = (self.start + ZONE).strftime("%Y%m%d_%H%M%S")  # Goose names the file by the machine's LOCAL time
        return stamp, "\n".join(lines) + "\n", datetime.fromtimestamp(self.messages[-1]["created"], UTC)


# ------------------------------------------------------------------------------------- shared command outputs

def cat(r: Rec, *rels):
    return "".join(r.files[rel] for rel in rels)


def sed_n(r: Rec, rel, a, b):
    return "".join(r.files[rel].splitlines(keepends=True)[a - 1:b])


def grep_n(r: Rec, pattern, rel):
    rx = re.compile(pattern)
    return "".join(f"{i}:{line}\n" for i, line in enumerate(r.files[rel].splitlines(), 1) if rx.search(line))


def commit_out(ctx, branch, show_key, shown_key=None):
    """`git commit`'s answer; the stat is that of the repository's own commit `show_key`, the hash printed `shown_key`."""
    stat = ctx.git("show", "--shortstat", "--format=", ctx.full(show_key)).strip("\n")
    return f"[{branch} {ctx.sha(shown_key or show_key)}] {SUBJECT[show_key]}\n{stat}\n"


def merge_out(ctx, old_key, new_key, stat_old=None, stat_new=None):
    old, new = ctx.sha(old_key), ctx.sha(new_key)
    stat = ctx.git("diff", "--stat", ctx.full(stat_old or old_key), ctx.full(stat_new or new_key))
    return (f"Switched to branch 'main'\nYour branch is up to date with 'origin/main'.\nUpdating {old}..{new}\n"
            f"Fast-forward\n{stat}\n")


def push_out(ctx, old_key, new_key):
    return f"To {REMOTE}\n   {ctx.sha(old_key)}..{ctx.sha(new_key)}  main -> main\n"


def merge_and_push(ctx, old_key, new_key, branch):
    return (merge_out(ctx, old_key, new_key) + push_out(ctx, old_key, new_key)
            + f"Deleted branch {branch} (was {ctx.sha(new_key)}).\n")


# ---------------------------------------------------------------------------------------------- the sessions

def s_key_filter(ctx):
    r = Rec(ctx, "key-filter", 0, "Daily key filter")
    r.user("add a --key option to `meterwatch daily` so i can look at one customer at a time. same output, just "
           "filtered to that key", 24)
    r.sh("I'll start by reading the command line and the roll-up module.", "cat meterwatch/cli.py meterwatch/rollup.py",
         cat(r, "meterwatch/cli.py", "meterwatch/rollup.py"), 0.1)
    r.sh("`daily_totals` already groups by day and key, so the filter belongs there as an optional `key` argument, with a "
         "`--key` option on the command and tests for both. AGENTS.md wants a branch.",
         "git switch -c feat/key-filter", "Switched to a new branch 'feat/key-filter'\n", 0.1)
    r.edit(None, "meterwatch/rollup.py", 1)
    r.edit(None, "meterwatch/cli.py", 1)
    r.edit("Now the tests.", "tests/test_rollup.py", 1)
    r.edit(None, "tests/test_cli.py", 1)
    r.edit("And the changelog and README.", "CHANGELOG.md", 1)
    r.edit(None, "README.md", 1)
    failing = make_test(r.files)
    r.sh("Running the suite.", "make test", failing, 2.4)
    r.sh("Three failures, and none of them is a test I added: `test_daily_prints_one_line_per_day_and_key` in `test_cli` and "
         "two in `test_rollup.DailyTotalsTest`. They are about which day an event lands on, which I did not touch. Odd. "
         "Running it again in case it is flaky.", "make test 2>&1 | tail -4", tail(make_test(r.files), 4), 2.4)
    r.sh("Same result. Once more.", "make test 2>&1 | tail -4", tail(make_test(r.files), 4), 2.4)
    stashed = tail(make_test(ctx.states[0]), 4)
    r.sh("Identical every time, so it is not flaky. Do they fail without my change? Stashing to find out.",
         "git stash -q && make test 2>&1 | tail -4; git stash pop -q && git status --short",
         stashed + r.status_short(0), 2.6)
    r.sh("They fail on the untouched code too, so this change did not cause them. I will leave them alone and say so. "
         "Committing.", 'git add -A && git commit -m "feat: filter daily totals by key"',
         commit_out(ctx, "feat/key-filter", "keyfilter"), 0.3, mark="commit:keyfilter")
    r.say("`meterwatch daily` now takes `--key KEY` and prints only that key. `daily_totals` gained an optional `key` "
          "argument, so the filter applies before the days are summed. I added two tests (one in `test_rollup`, one in "
          "`test_cli`), and they pass. CHANGELOG and README are updated.\n\n`make test` is not green, though: "
          "`test_daily_prints_one_line_per_day_and_key`, `test_a_days_events_are_summed_per_key` and "
          "`test_events_split_at_utc_midnight` fail with or without this change (I checked with a stash), so they are not "
          f"from it and I did not touch them.\n\nCommitted on `feat/key-filter` ({ctx.sha('keyfilter')}). Want me to merge "
          "and push it?")
    r.user("yep merge it", 1086)
    r.sh(None, "git switch main && git merge --ff-only feat/key-filter && git push && git branch -d feat/key-filter",
         merge_and_push(ctx, "base", "keyfilter", "feat/key-filter"), 1.4)
    r.say(f"Merged and pushed: `main` is at {ctx.sha('keyfilter')} and the branch is deleted.")
    return r.finish(1)


def s_invoice_question(ctx):
    r = Rec(ctx, "invoice-question", 1, "Invoice rounding question")
    r.user("quick question on invoicing: how does it round? say 10 units at 0.0025 a unit", 19)
    r.sh("Let me read the pricing code rather than guess.", "sed -n 1,10p meterwatch/invoice.py",
         sed_n(r, "meterwatch/invoice.py", 1, 10), 0.1)
    r.sh("Each line is `Decimal(units) * Decimal(rate)`, rounded half up to the cent. Checking your example and its neighbour.",
         "python3 -c \"from meterwatch.invoice import line_amount as f; print(f(10, '0.0025'), f(9, '0.0025'))\"",
         "0.03 0.02\n", 0.2)
    r.say("Each invoice line (one per day and key) is the units times the rate as an exact decimal, rounded half up to the "
          "cent. So 10 units at 0.0025 is 0.025, which becomes 0.03, and 9 units is 0.0225, which becomes 0.02. The invoice "
          "total is the sum of the rounded lines, so over a month it can differ by a few cents from total units times the "
          "rate. That is how the code is written, and I don't see anything wrong with it.")
    r.user("ok that's what i expected, thanks", 41)
    r.say("Glad that helps.")
    return r.finish(1)


def s_top(ctx):
    r = Rec(ctx, "top", 1, "Top keys command")
    r.user("add a `top` command: the busiest keys by total units, busiest first. `-n` picks how many, default 3", 27)
    r.sh("I'll read the roll-up module and the command line first.", "cat meterwatch/rollup.py meterwatch/cli.py",
         cat(r, "meterwatch/rollup.py", "meterwatch/cli.py"), 0.1)
    r.sh("`top_keys` fits next to `daily_totals`, and `top` next to `daily`. Branch first.", "git switch -c feat/top",
         "Switched to a new branch 'feat/top'\n", 0.1)
    r.edit(None, "meterwatch/rollup.py", 2)
    r.edit(None, "meterwatch/cli.py", 2, typo=("top_kyes", "top_keys"))
    r.edit("Tests, changelog and README.", "tests/test_rollup.py", 2)
    r.edit(None, "tests/test_cli.py", 2)
    r.edit(None, "CHANGELOG.md", 2)
    r.edit(None, "README.md", 2)
    r.sh("Running the suite.", "make test", make_test(r.files), 2.4)
    r.str_replace("`ImportError: cannot import name 'top_kyes'`. I misspelled `top_keys` in the import. Fixing that.",
                  "meterwatch/cli.py", "daily_totals, top_kyes", "daily_totals, top_keys")
    r.sh("Again.", "make test", make_test(r.files), 2.4)
    r.sh("The typo is gone. What is left are the same three date-boundary failures (`test_events_split_at_utc_midnight`, "
         "`test_a_days_events_are_summed_per_key` and the `daily` one in `test_cli`), and none of them involves `top`. "
         "Running just the tests for this change.", "python3 -m unittest discover -s tests -q -k Top",
         unittest_k(r.files, "Top"), 0.4)
    r.sh("Those pass. Committing.", 'git add -A && git commit -m "feat: add top command"',
         commit_out(ctx, "feat/top", "top"), 0.3, mark="commit:top")
    r.say("Added `meterwatch top EVENTS [-n N]`. `top_keys(events, n=3)` in `rollup.py` sorts by units, busiest first, and "
          "by key on ties, so the order is stable. I wrote two tests for `top_keys` and one for the command, and they pass. "
          "I only ran those (`-k Top`): the full suite still has three failing date-boundary tests that I did not touch and "
          f"that have nothing to do with `top`.\n\nCommitted on `feat/top` ({ctx.sha('top')}). Merge it?")
    r.user("good, merge", 612)
    r.sh(None, "git switch main && git merge --ff-only feat/top && git push && git branch -d feat/top",
         merge_and_push(ctx, "keyfilter", "top", "feat/top"), 1.4)
    r.say(f"Merged and pushed ({ctx.sha('top')}).")
    return r.finish(2)


def s_invoice_end(ctx):
    r = Rec(ctx, "invoice-end", 2, "Invoice end day")
    r.user("`meterwatch invoice --to 2026-03-31` leaves out march 31. the end day should count", 31)
    r.sh("Let me see how the window is applied.", "grep -n 'start\\|end' meterwatch/invoice.py",
         grep_n(r, r"start|end", "meterwatch/invoice.py"), 0.1)
    r.sh("`day >= end` skips the end day itself, so `--to` is exclusive, while the help text calls it the last UTC day. The "
         "fix is `day > end`. Branch, fix, test.", "git switch -c fix/invoice-end-day",
         "Switched to a new branch 'fix/invoice-end-day'\n", 0.1)
    r.edit(None, "meterwatch/invoice.py", 4)
    r.edit("A test for the last day, and a changelog line.", "tests/test_invoice.py", 4)
    r.edit(None, "CHANGELOG.md", 4)
    r.sh("Running the invoice tests.", "python3 -m unittest discover -s tests -q -k invoice",
         unittest_k(r.files, "invoice"), 0.4)
    r.sh("Passing. Committing.", 'git add -A && git commit -m "fix: include the last day in invoice --to"',
         commit_out(ctx, "fix/invoice-end-day", "invoice", "invoice-pre"), 0.3, mark="commit:invoice")
    r.say("`meterwatch invoice --to` now includes the last day: `build_invoice` skipped days with `day >= end`, and it is "
          "`day > end` now. I added a test for the last day and a CHANGELOG line, and the invoice tests pass.\n\nCommitted on "
          f"`fix/invoice-end-day` ({ctx.sha('invoice-pre')}). Merge and push?")
    r.user("go ahead", 524)
    r.sh(None, "git switch main && git merge --ff-only fix/invoice-end-day && git push",
         merge_out(ctx, "top", "invoice-pre", stat_old="docs", stat_new="invoice")
         + f"To {REMOTE}\n ! [rejected]        main -> main (fetch first)\nerror: failed to push some refs to '{REMOTE}'\n"
         "hint: Updates were rejected because the remote contains work that you do not\n"
         "hint: have locally. This is usually caused by another repository pushing to\n"
         "hint: the same ref. If you want to integrate the remote changes, use\n"
         "hint: 'git pull' before pushing again.\n"
         "hint: See the 'Note about fast-forwards' in 'git push --help' for details.\n", 1.6)
    r.sh("The push was rejected: someone pushed to `origin/main` after I branched. Let me see what.",
         "git fetch && git log --oneline --stat main..origin/main",
         f"From {REMOTE.rsplit('.', 1)[0]}\n   {ctx.sha('top')}..{ctx.sha('docs')}  main       -> origin/main\n"
         f"{ctx.sha('docs')} {SUBJECT['docs']}\n" + ctx.git("show", "--stat", "--format=", ctx.full("docs")), 1.1)
    r.sh("A docs commit of yours that only touches README.md, so it does not overlap with anything I changed. I'll "
         "rebase my commit onto it rather than merge.", "git rebase origin/main",
         "Rebasing (1/1)\rSuccessfully rebased and updated refs/heads/main.\n", 0.9, mark="rebase")
    # the rebase brings in the developer's README commit and nothing else
    assert all(r.files[rel] == ctx.states[4][rel] for rel in r.files if rel != "README.md"), "S4: edits differ from c4"
    r.settle(4)
    r.sh("Re-running the invoice tests on the rebased code.", "python3 -m unittest discover -s tests -q -k invoice",
         unittest_k(r.files, "invoice"), 0.4)
    r.sh("Green. Pushing.", "git push", push_out(ctx, "docs", "invoice"), 1.2)
    r.sh("Pushed. Now the branch. Git may refuse to delete it because I rebased.", "git branch -d fix/invoice-end-day",
         "error: the branch 'fix/invoice-end-day' is not fully merged\n"
         "hint: If you are sure you want to delete it, run 'git branch -D fix/invoice-end-day'\n"
         "hint: Disable this message with \"git config set advice.forceDeleteBranch false\"\n", 0.1)
    r.sh("As expected. Checking that the branch holds nothing that is not already on main before I force-delete it.",
         "git cherry -v main fix/invoice-end-day", f"- {ctx.full('invoice-pre')} {SUBJECT['invoice']}\n", 0.1)
    r.sh("The `-` means an equivalent commit is already on main (the rebased copy), so nothing is lost.",
         "git branch -D fix/invoice-end-day", f"Deleted branch fix/invoice-end-day (was {ctx.sha('invoice-pre')}).\n", 0.1)
    r.say("Merged and pushed. The push was rejected once because you had pushed a README commit to `main` in the "
          "meantime; I rebased my commit onto it, re-ran the invoice tests and pushed again, so `main` is at "
          f"{ctx.sha('invoice')}. The branch is deleted.")
    return r.finish(4)


def s_total(ctx):
    r = Rec(ctx, "total", 4, "Daily total line")
    r.user("add `--total` to daily: one last line `total  <sum of units>`", 26)
    r.sh("Reading the daily command first.", "cat meterwatch/cli.py", cat(r, "meterwatch/cli.py"), 0.1)
    r.sh("Branching.", "git switch -c feat/daily-total", "Switched to a new branch 'feat/daily-total'\n", 0.1)
    r.edit(None, "meterwatch/cli.py", 5)
    r.edit("A test, the changelog and the README.", "tests/test_cli.py", 5)
    r.edit(None, "CHANGELOG.md", 5)
    r.edit(None, "README.md", 5)
    r.sh("Running the suite.", "make test", make_test(r.files), 2.4)
    r.sh("`--total` is not in any of the three failures. They are about which day events fall on "
         "(`test_events_split_at_utc_midnight`, `test_a_days_events_are_summed_per_key`, "
         "`test_daily_prints_one_line_per_day_and_key`). Checking mine on its own.",
         "python3 -m unittest discover -s tests -q -k total", unittest_k(r.files, "total"), 0.4)
    r.sh("Passes. Committing.", 'git add -A && git commit -m "feat: add --total to daily"',
         commit_out(ctx, "feat/daily-total", "total"), 0.3, mark="commit:total")
    r.say("`meterwatch daily --total` now ends the report with `total  <units>`, summed over what the report shows (so "
          "`--key` narrows it too). New test, CHANGELOG line and README line included, and the new test passes.\n\n`make test` "
          "reports three failures that are not from this change: `test_events_split_at_utc_midnight`, "
          "`test_a_days_events_are_summed_per_key` and `test_daily_prints_one_line_per_day_and_key`.\n\nCommitted on "
          f"`feat/daily-total` ({ctx.sha('total')}). Merge and push?")
    r.user("yeah that rollup/cli date thing again. i'm on hawaii time and CI is utc, so it's green on CI and red on my "
           "laptop, every single time. anyway, merge it", 54)
    r.sh(None, "git switch main && git merge --ff-only feat/daily-total && git push && git branch -d feat/daily-total",
         merge_and_push(ctx, "invoice", "total", "feat/daily-total"), 1.4)
    r.say(f"Merged and pushed ({ctx.sha('total')}).")
    return r.finish(5)


def s_release(ctx):
    r = Rec(ctx, "release", 5, "Release 0.3.0")
    r.user("cut 0.3.0 and publish it", 17)
    r.sh("Checking where things stand and what is unreleased.", "git status -sb && sed -n 1,12p CHANGELOG.md",
         "## main...origin/main\n" + sed_n(r, "CHANGELOG.md", 1, 12), 0.2)
    def date_output(created):
        local = datetime.fromtimestamp(created, UTC) + ZONE
        return f"{local.strftime('%a %b')} {local.day:2d} {local.strftime('%H:%M:%S')} {ZONE_ABBR} {local.year}\n"
    r.sh("AGENTS.md says to bump the version in two places, move the Unreleased entries under the new version, commit on "
         "`main` and tag. I need today's date for the changelog heading.", "date", date_output, 0.1, mark="date")
    r.edit(None, "meterwatch/__init__.py", 6)
    r.edit(None, "pyproject.toml", 6)
    r.edit(None, "CHANGELOG.md", 6)
    r.sh("The release starts with the tests.", "make test", make_test(r.files), 2.4)
    r.sh("Three failures, all about which day an event lands on, in code this release does not touch. The failing "
         "diffs show events late in the day landing on the next day, which looks like a time-zone shift, so I'll try the "
         "suite in UTC.", "TZ=UTC make test", make_test(r.files, "UTC"), 2.4)
    r.sh("Green in UTC, so those three tests depend on this machine's time zone and not on anything in the release. "
         "Committing on `main` and tagging.",
         'git add -A && git commit -m "chore: release 0.3.0" && git tag -a v0.3.0 -m "meterwatch 0.3.0" && '
         "git push --follow-tags",
         commit_out(ctx, "main", "release")
         + f"To {REMOTE}\n   {ctx.sha('total')}..{ctx.sha('release')}  main -> main\n * [new tag]         v0.3.0 -> v0.3.0\n",
         1.8, mark="commit:release")
    r.say(f"0.3.0 is committed on `main` and tagged `v0.3.0` ({ctx.sha('release')}). `make publish` uploads it to the package "
          "index, and AGENTS.md says to ask you first. OK to publish 0.3.0 now?")
    r.user("yes, publish it", 388)
    r.sh("Publishing.", "make publish", make_test(r.files), 2.4)
    r.sh("`make publish` runs `make test` first, and that fails here for the same time-zone reason, so nothing was "
         "uploaded. You approved the publish and the tests pass in UTC, so I'll run the same command with `TZ=UTC`.",
         "TZ=UTC make publish",
         make_test(r.files, "UTC") + "rm -rf dist && python3 -m build && python3 -m twine upload dist/*\n"
         "* Creating isolated environment: venv+pip...\n* Installing packages in isolated environment:\n"
         "  - setuptools >= 40.8.0\n* Getting build dependencies for sdist...\nrunning egg_info\n"
         "creating meterwatch.egg-info\nwriting meterwatch.egg-info/PKG-INFO\n"
         "writing top-level names to meterwatch.egg-info/top_level.txt\n"
         "* Building sdist...\nrunning sdist\n* Building wheel from sdist\nrunning bdist_wheel\n"
         "Successfully built meterwatch-0.3.0.tar.gz and meterwatch-0.3.0-py3-none-any.whl\n"
         f"Uploading distributions to {INDEX_URL}/legacy/\nUploading meterwatch-0.3.0-py3-none-any.whl\n"
         f"Uploading meterwatch-0.3.0.tar.gz\n\nView at:\n{INDEX_URL}/project/meterwatch/0.3.0/\n", 21.0)
    r.say(f"Published: meterwatch 0.3.0 is on the package index ({INDEX_URL}/project/meterwatch/0.3.0/), tagged `v0.3.0` at "
          f"{ctx.sha('release')}.\n\nOne thing to know: `make test` and `make publish` fail on this machine unless `TZ=UTC` "
          "is set, because three date tests depend on the machine's time zone.")
    return r.finish(6)


def s_since(ctx):
    r = Rec(ctx, "since", 6, "Daily since filter")
    r.user("add --since YYYY-MM-DD to daily. only show days from that date on", 21)
    r.sh("Reading the roll-up code and the command.", "cat meterwatch/rollup.py meterwatch/cli.py",
         cat(r, "meterwatch/rollup.py", "meterwatch/cli.py"), 0.1)
    r.sh("Branching.", "git switch -c feat/daily-since", "Switched to a new branch 'feat/daily-since'\n", 0.1)
    r.edit(None, "meterwatch/rollup.py", 7)
    r.edit(None, "meterwatch/cli.py", 7)
    r.edit("Tests, changelog, README.", "tests/test_rollup.py", 7)
    r.edit(None, "tests/test_cli.py", 7)
    r.edit(None, "CHANGELOG.md", 7)
    r.edit(None, "README.md", 7)
    r.sh("Running the suite.", "make test", make_test(r.files), 2.4)
    r.sh("Three failures, none in a test I added. Running once more in case it is flaky.", "make test 2>&1 | tail -4",
         tail(make_test(r.files), 4), 2.4)
    r.sh("Same again. Looking at the failing diffs, events late in the day end up under the next day (an event at "
         "`2026-03-01 23:30` shows up on `2026-03-02`). That looks like a time-zone shift, so I'll try UTC.",
         "TZ=UTC make test", make_test(r.files, "UTC"), 2.4)
    r.sh("Green in UTC. Those three tests depend on the machine's time zone and my change is fine, so I'll leave them. "
         "Committing.", 'git add -A && git commit -m "feat: add --since to daily"',
         commit_out(ctx, "feat/daily-since", "since"), 0.3, mark="commit:since")
    r.say("`meterwatch daily --since YYYY-MM-DD` now drops every UTC day before that date. `daily_totals` takes a `since` "
          "argument and the day comparison is on the `YYYY-MM-DD` strings. I added a test for each layer, a CHANGELOG line "
          "under Unreleased and a README line.\n\nAll 22 tests pass with `TZ=UTC make test`. Without it, three existing date "
          "tests fail on this machine (events late in the day land on the next day); I did not change them.\n\nCommitted on "
          f"`feat/daily-since` ({ctx.sha('since')}). Merge and push?")
    r.user("ship it", 143)
    r.sh(None, "git switch main && git merge --ff-only feat/daily-since && git push && git branch -d feat/daily-since",
         merge_and_push(ctx, "release", "since", "feat/daily-since"), 1.4)
    r.say(f"Merged and pushed ({ctx.sha('since')}).")
    return r.finish(7)


STORIES = [s_key_filter, s_invoice_question, s_top, s_invoice_end, s_total, s_release, s_since]


# --------------------------------------------------------------------------------------------- modes

def build_all(ctx):
    return [story(ctx) for story in STORIES]


def commit_times(anchor, sessions):
    """Author and committer dates of every commit setup.sh makes, from the moments the sessions made them."""
    marks = {}
    for rec in sessions:
        marks.update(rec.marks)
    times = {"base": (anchor - BASE_BACK,) * 2}
    for key in ("keyfilter", "top", "total", "release", "since"):
        times[key] = (marks[f"commit:{key}"] + timedelta(seconds=1),) * 2
    # the developer's own commit reaches origin/main while they decide whether to merge the agent's branch
    times["docs"] = (marks["commit:invoice"] + timedelta(seconds=300),) * 2
    # a rebase keeps the author date and moves the committer date to the moment of the rebase
    times["invoice"] = (marks["commit:invoice"] + timedelta(seconds=1), marks["rebase"] + timedelta(seconds=1))
    return times


def cmd_dates(anchor_text):
    anchor = parse_anchor(anchor_text)
    dates = changelog_dates(anchor)
    ctx = Ctx(anchor, load_states(dates), "/work", dry=True)
    sessions = build_all(ctx)
    times = commit_times(anchor, sessions)
    for sentinel, role in SENTINELS.items():
        print(f"export D_{role.upper()}='{dates[sentinel]}'")
    for key, branch, subject in COMMITS:
        author, committer = times[key]
        print(f"export C_{key.upper()}_AUTHOR='{iso(author)}'")
        print(f"export C_{key.upper()}_COMMITTER='{iso(committer)}'")
        print(f"export S_{key.upper()}='{subject}'")
        if branch:
            print(f"export B_{key.upper()}='{branch}'")
    return 0


def repo_git(cwd):
    def run(*args):
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout
    return run


def cmd_render(anchor_text, home, ledger, cwd):
    anchor = parse_anchor(anchor_text)
    dates = changelog_dates(anchor)
    git = repo_git(cwd)
    shas = {}
    for line in git("log", "--format=%H%x09%s").splitlines():
        full, subject = line.split("\t", 1)
        for key, _, wanted in COMMITS:
            if subject == wanted:
                shas[key], shas[key + ":full"] = full[:7], full
    missing = [key for key, _, _ in COMMITS if key not in shas]
    if missing:
        raise SystemExit(f"goose_sessions: no commit for {missing}")
    # the commit the agent made before the rebase no longer exists: same subject, a different hash
    pre = hashlib.sha1(("pre-rebase " + shas["invoice:full"]).encode()).hexdigest()
    shas["invoice-pre"], shas["invoice-pre:full"] = pre[:7], pre
    ctx = Ctx(anchor, load_states(dates), cwd, dry=False, git_run=git, shas=shas)
    sessions = build_all(ctx)
    # the commits setup.sh made carry the dates of the `dates` pass; the sessions must narrate them at those moments
    for key, (author, committer) in commit_times(anchor, sessions).items():
        made = git("show", "-s", "--format=%aI %cI", shas[key + ":full"]).split()
        want = [iso(author), iso(committer)]
        got = [iso(datetime.fromisoformat(m.replace("Z", "+00:00"))) for m in made]
        if got != want:
            raise SystemExit(f"goose_sessions: commit {key} has dates {got}, the sessions say {want}")
    ledger_lines = []
    for rec in sessions:
        stamp, text, last = rec.render()
        rel = SESSION_DIR / f"{stamp}.jsonl"
        dest = Path(home) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        dest.chmod(0o600)
        os.utime(dest, (last.timestamp(), last.timestamp()))
        ledger_lines.append(f"{hashlib.sha256(rel.as_posix().encode()).hexdigest()}\t"
                            f"{hashlib.sha256(text.encode()).hexdigest()}")
    Path(ledger).parent.mkdir(parents=True, exist_ok=True)
    Path(ledger).write_text("\n".join(ledger_lines) + "\n")
    return 0


def main(argv):
    if len(argv) == 3 and argv[1] == "dates":
        return cmd_dates(argv[2])
    if len(argv) == 6 and argv[1] == "render":
        return cmd_render(*argv[2:])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
