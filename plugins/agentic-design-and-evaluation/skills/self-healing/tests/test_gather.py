"""What gather.py extracts from the session records of any agent harness, faithfully and without interpretation."""
import bz2
import datetime as dt
import gzip
import importlib.util
import json
import lzma
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gather.py"


def _load_gather():
    """Import gather.py as a module (by path, not via sys.path) for direct unit tests of its
    pure functions, alongside the subprocess-level integration tests below."""
    spec = importlib.util.spec_from_file_location("gather_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gather = _load_gather()

# Git in these tests reads neither the developer's global git configuration nor the system's.
# A global setting that signs every commit (through an agent that asks for approval, say) makes
# each commit in a temporary repository slow or failing, and nothing here depends on what such
# a configuration says; the temporary repositories get everything they need from the test.
GIT_ISOLATION = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

# gather.py runs with an empty home and from an empty directory of the suite's own (see setUpModule), so that
# what it writes does not depend on whose machine this is: the repository the suite is run from is not "the one
# gather.py runs in", and no path the tests make is abbreviated to ~.
SCRATCH = None


def setUpModule():
    global SCRATCH
    SCRATCH = Path(tempfile.mkdtemp(prefix="gather-scratch-"))
    unittest.addModuleCleanup(shutil.rmtree, SCRATCH, ignore_errors=True)
    (SCRATCH / "home").mkdir()
    (SCRATCH / "cwd").mkdir()


def git(repo, *args):
    env = dict(os.environ)
    env.update(GIT_ISOLATION)
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, text=True, env=env)


def make_repo(path, branches=(), stash=None):
    """A git repository of one commit on main, with these branches and, if given, one stash with this message."""
    path.mkdir(parents=True)
    identity = ["-c", "user.name=a", "-c", "user.email=a@b"]
    git(path, "init", "-q", "-b", "main")
    (path / "f").write_text("x")
    git(path, "add", "f")
    git(path, *identity, "commit", "-qm", "init")
    for branch in branches:
        git(path, "branch", branch)
    if stash:
        (path / "f").write_text("y")
        git(path, *identity, "stash", "push", "-m", stash)
    return path


def run_gather_script(args, extra_env=None, cwd=None):
    """gather.py as a command, the way an executor runs it."""
    env = {key: value for key, value in os.environ.items()  # the platform's data directories follow the home
           if key not in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "APPDATA", "LOCALAPPDATA")}
    env.update(GIT_ISOLATION)
    env.update({"HOME": str(SCRATCH / "home"), "USERPROFILE": str(SCRATCH / "home")})
    if extra_env:
        env.update(extra_env)
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", env=env, cwd=str(cwd or SCRATCH / "cwd"))


UTC = dt.timezone.utc
CLOCK = dt.datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)


def at(n):
    """The n-th second of the fixtures' clock, as a log record carries it."""
    return (CLOCK + dt.timedelta(seconds=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


def shown(n):
    """The same instant as a transcript line shows it."""
    return (CLOCK + dt.timedelta(seconds=n)).isoformat(timespec="seconds")


def hours_ago(hours):
    return (dt.datetime.now(UTC) - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def uid(n):
    """An identifier shaped like the UUIDs harnesses give their records and their sessions."""
    return f"0199abcd-ef01-7234-8bcd-{n:012d}"


def jl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))
    return path


def stamped(records):
    """These records with the fixtures' clock in them, one second apart: record i is raw line i + 1, at(i)."""
    return [{"timestamp": at(i), **record} for i, record in enumerate(records)]


def item(ts, it):
    """A record of the shape some harnesses write: a completed item, in a payload, in an event."""
    return {"timestamp": ts, "type": "event_msg", "payload": {"type": "item_completed", "item": it}}


def text_blocks(t):
    return [{"type": "text", "text": t}]


def index_rows(out):
    """The index's session rows, each as its list of cells: session, place, start, end, cwd, records, user-role
    text, other text, tool calls, size, readable, raw log."""
    lines = (out / "index.md").read_text(encoding="utf-8").splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("|---")) + 1  # the rows are those after the table's rule
    return [[c.strip() for c in line.split("|")[1:-1]] for line in lines[first:] if line.startswith("| ")]


def places_of(out):
    """The index's list of places, one entry for each, as the index words it (without the dash of its list)."""
    lines = (out / "index.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Places")) + 1
    return [line[2:] for line in lines[start:lines.index("", start)]]


def cells_of(out, session_id):
    """The cells of the index row for a session (see index_rows)."""
    for cells in index_rows(out):
        if cells[0] == session_id:
            return cells
    raise AssertionError(f"the index has no row for {session_id}: {[row[0] for row in index_rows(out)]}")


def link_of(cells):
    return re.search(r"\]\((.+)\)$", cells[10]).group(1)


def transcript_of(out, session_id):
    """The text of the transcript the index links for a session."""
    return (out / link_of(cells_of(out, session_id))).read_text(encoding="utf-8")


def transcript_at(out, raw):
    """The text of the transcript the index links for the session in this raw log."""
    for cells in index_rows(out):
        if cells[11] == str(raw):
            return (out / link_of(cells)).read_text(encoding="utf-8")
    raise AssertionError(f"the index has no row for {raw}: {[row[11] for row in index_rows(out)]}")


def header_of(text):
    """The nine lines of a transcript's header: its title, a blank line, the place, the raw log, the working
    directory, the number of records, what most records carry, the first record, and a blank line. (Whether the
    last of the lines of text has the two trailing spaces of a line break before the blank one is not looked at.)"""
    lines = text.splitlines()[:9]
    if len(lines) < 9 or not lines[0].startswith("# Session ") or lines[1] != "" or lines[8] != "":
        raise AssertionError(f"not a transcript's header: {lines}")
    lines[7] = lines[7].rstrip()
    return lines


def body_of(text):
    """The lines of a transcript after its header."""
    header_of(text)
    return text.splitlines()[9:]


def facts_of(*facts):
    """The group of facts a line shows after its label: {flag, key=value}."""
    return "{" + ", ".join(facts) + "}"


def row(raw, n, label, text, kind="", facts=(), when=None):
    """The line of a transcript for what raw line n of a stamped log (see stamped) holds: its time, its label, the
    facts it shows (after a space), what kind of piece of the record it is if not text, and where it is in the raw
    log."""
    group = " " + facts_of(*facts) if facts else ""
    piece = f" - {kind}" if kind else ""
    return f"[{shown(n - 1) if when is None else when}] {label}{group}{piece}: {text}  ({raw}:{n})"


def covered_by(lines, raw, unit):
    """The raw lines (unit "line") or record numbers (unit "record") that these transcript lines say they come from:
    the one each line names, and every number in the range of each note. Every line must name some."""
    where = {"line": rf"{re.escape(str(raw))}:(\d+)", "record": rf"{re.escape(str(raw))} record (\d+)"}[unit]
    covered = set()
    for line in lines:
        ref = re.search(rf"\((?:raw log {unit}s? (\d+)(?:-(\d+))?|{where})\)$", line)
        if not ref:
            raise AssertionError(f"a line that says where it comes from nowhere: {line}")
        if ref.group(3):
            covered.add(int(ref.group(3)))
        else:
            covered.update(range(int(ref.group(1)), int(ref.group(2) or ref.group(1)) + 1))
    return covered


def written(out):
    """Every file under an output directory, with its text."""
    return [(path, path.read_text(encoding="utf-8")) for path in sorted(out.rglob("*")) if path.is_file()]


class LogHome(unittest.TestCase):
    """A temporary directory to put synthetic session logs in and run gather.py over."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.logs = self.root / "logs"
        self.logs.mkdir()
        self.runs = 0

    def gather(self, *places, since="2000-01-01", extra=(), extra_env=None, cwd=None, places_given=True):
        """gather.py over these places (self.logs by default, or none with places_given false), into a new output
        directory, which this returns."""
        self.runs += 1
        out = self.root / f"out{self.runs}"
        window = ["--since", since] if since else []  # None: the window gather.py has without being told
        given = (places or (self.logs,)) if places_given else ()
        r = run_gather_script([*given, *window, "--out", out, *extra], extra_env=extra_env, cwd=cwd)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.stdout = r.stdout
        return out

    def session_ids(self, out):
        return {cells[0] for cells in index_rows(out)}

    def index_row(self, out, session_id):
        return cells_of(out, session_id)

    def transcript(self, out, session_id):
        return transcript_of(out, session_id)


# ---------------------------------------------------------------------------- the general cases

class GatherTest(LogHome):
    """gather.py run the way an executor runs it, over the logs of three harnesses that write three shapes: a
    rollout, which wraps each message in a payload and that in an item; a transcript, a message object to a
    record; and a chat, one JSON document. gather.py knows none of them: each is a set of records, and each
    is shown in its own words."""

    TOKEN = "gh" + "p_" + "a" * 30  # assembled at run time: nothing secret-shaped is committed
    CWD = "/srv/agent-fixture"

    def setUp(self):
        super().setUp()
        self.rollouts, self.transcripts, self.chats = (self.root / name for name in ("rollouts", "transcripts", "chats"))
        self.rollout = self.rollouts / "2026" / "09" / "28" / "rollout-a.jsonl"
        jl(self.rollout, [
            {"timestamp": "2026-09-28T10:00:00Z", "type": "session_meta", "payload": {"id": uid(1), "cwd": self.CWD}},
            item("2026-09-28T10:00:01Z", {"type": "UserMessage", "id": uid(2), "content": text_blocks("Fix the build and open a PR")}),
            item("2026-09-28T10:01:00Z", {"type": "CommandExecution", "id": uid(3), "command": ["bash", "-lc", "pytest -q"],
                                          "cwd": self.CWD, "status": "completed", "exit_code": 1,
                                          "aggregated_output": "FAILED test_x with token " + self.TOKEN}),
            item("2026-09-28T10:02:00Z", {"type": "AgentMessage", "id": uid(4), "content": text_blocks("Consolidated into one PR.")}),
            {"timestamp": "2026-09-28T10:03:00Z", "type": "compacted", "payload": {"message": "summary"}},
            item("2026-09-28T10:04:00Z", {"type": "FutureItemType", "id": uid(5), "some_field": "x"}),
            {"timestamp": "2026-09-28T10:05:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {}}},
            {"timestamp": "2026-09-28T10:06:00Z", "type": "brand_new_top_level_record", "payload": {"x": 1}},
        ])
        self.transcript_raw = self.transcripts / "proj" / "main.jsonl"
        jl(self.transcript_raw, [
            {"timestamp": "2026-09-28T10:00:00Z", "type": "user", "cwd": self.CWD, "sessionId": "claude-a",
             "message": {"content": "Run the tests"}},
            {"timestamp": "2026-09-28T10:01:00Z", "type": "assistant", "sessionId": "claude-a",
             "message": {"content": [{"type": "text", "text": "Running them now."},
                                     {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest -q"}}]}},
            {"timestamp": "2026-09-28T10:01:05Z", "type": "user", "sessionId": "claude-a",
             "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "FAILED"}]}},
            {"timestamp": "2026-09-28T10:02:00Z", "type": "assistant", "sessionId": "claude-a",
             "message": {"content": [{"type": "text", "text": "Tests fail; fixing."}]}},
            {"timestamp": "2026-09-28T10:03:00Z", "type": "pr-link", "sessionId": "claude-a", "url": "https://example/pr/1"},
            {"timestamp": "2026-09-28T10:04:00Z", "type": "system", "sessionId": "claude-a", "subtype": "compact_boundary"},
        ])
        self.chat_raw = write_json(self.chats / "hash1" / "chats" / "session-2026-09-28T10-00-abc12345.json", {
            "sessionId": "gem-1", "startTime": "2026-09-28T10:00:00Z", "lastUpdated": "2026-09-28T10:05:00Z",
            "messages": [
                {"type": "user", "content": "Build it now", "timestamp": "2026-09-28T10:00:00Z"},
                {"type": "gemini", "content": "All done here", "timestamp": "2026-09-28T10:01:00Z",
                 "toolCalls": [{"name": "run_shell_command", "args": {"command": "pytest -q"}, "status": "error", "result": "boom"}]},
                {"type": "future-message-kind", "timestamp": "2026-09-28T10:02:00Z"}]})

    def places(self):
        return [self.rollouts, self.transcripts, self.chats]

    def test_a_rollout_reads_as_its_records_say_and_every_record_is_a_line_or_a_note(self):
        out = self.gather(*self.places())
        text = transcript_of(out, uid(1))  # the id of the session_meta record: no record carries a sessionId
        raw = self.rollout
        self.assertEqual(header_of(text), [
            f"# Session {uid(1)}", "", f"place: {self.rollouts}  ", f"raw log: {raw}  ", f"cwd: {self.CWD}  ", "records: 8  ",
            "most records carry: (nothing in common)  ",
            'first record: session_meta {"timestamp": "2026-09-28T10:00:00Z", "type": "session_meta", '
            f'"payload": {{"id": "{uid(1)}", "cwd": "{self.CWD}"}}}}', ""])
        # By hand: the working directory is named by two of the eight records, which is "few" (the most a fact may
        # be on and be shown on lines is a quarter of them, two), so the command shows it; so does its status.
        command, facts = "event_msg > item_completed > CommandExecution", (f"cwd={self.CWD}", "status=completed")
        self.assertEqual(body_of(text), [
            "[2026-09-28T10:00:00+00:00] note: session_meta  (raw log line 1)",
            f"[2026-09-28T10:00:01+00:00] event_msg > item_completed > UserMessage: Fix the build and open a PR  ({raw}:2)",
            row(raw, 3, command, "bash -lc pytest -q", "tool call", facts, when="2026-09-28T10:01:00+00:00"),
            row(raw, 3, command, "(exit_code 1) FAILED test_x with token [masked]", "tool result", facts, when="2026-09-28T10:01:00+00:00"),
            f"[2026-09-28T10:02:00+00:00] event_msg > item_completed > AgentMessage: Consolidated into one PR.  ({raw}:4)",
            f"[2026-09-28T10:03:00+00:00] compacted: summary  ({raw}:5)",
            "[2026-09-28T10:04:00+00:00] note: event_msg > item_completed > FutureItemType, event_msg > token_count, "
            "brand_new_top_level_record through 2026-09-28T10:06:00+00:00  (raw log lines 6-8)"])

    def test_a_transcript_reads_as_its_records_say_and_what_every_record_shares_is_named_once(self):
        out = self.gather(*self.places())
        text = transcript_of(out, "claude-a")
        raw = self.transcript_raw
        self.assertEqual(header_of(text), [
            "# Session claude-a", "", f"place: {self.transcripts}  ", f"raw log: {raw}  ", f"cwd: {self.CWD}  ", "records: 6  ",
            "most records carry: (nothing in common)  ",  # the session id, shared by all, is the title; ids are no facts
            'first record: user {"timestamp": "2026-09-28T10:00:00Z", "type": "user", '
            f'"cwd": "{self.CWD}", "sessionId": "claude-a", "message": {{"content": "Run the tests"}}}}', ""])
        self.assertEqual(body_of(text), [
            row(raw, 1, "user", "Run the tests", facts=(f"cwd={self.CWD}",), when="2026-09-28T10:00:00+00:00"),
            f"[2026-09-28T10:01:00+00:00] assistant: Running them now.  ({raw}:2)",
            f'[2026-09-28T10:01:00+00:00] assistant - tool call: Bash({{"command": "pytest -q"}})  ({raw}:2)',
            f"[2026-09-28T10:01:05+00:00] user - tool result (error): FAILED  ({raw}:3)",
            f"[2026-09-28T10:02:00+00:00] assistant: Tests fail; fixing.  ({raw}:4)",
            "[2026-09-28T10:03:00+00:00] note: pr-link, system > compact_boundary through 2026-09-28T10:04:00+00:00  "
            "(raw log lines 5-6)"])

    def test_a_chat_document_reads_as_its_records_say_and_its_own_times_bound_the_session(self):
        out = self.gather(*self.places())
        text = transcript_of(out, "gem-1")
        raw = self.chat_raw
        self.assertEqual(header_of(text), [
            "# Session gem-1", "", f"place: {self.chats}  ", f"raw log: {raw}  ", "cwd: (no record names one)  ", "records: 3  ",
            "most records carry: (nothing in common)  ",
            'first record: user {"type": "user", "content": "Build it now", "timestamp": "2026-09-28T10:00:00Z"}', ""])
        self.assertEqual(body_of(text), [
            f"[2026-09-28T10:00:00+00:00] user: Build it now  ({raw} record 1)",
            f"[2026-09-28T10:01:00+00:00] gemini: All done here  ({raw} record 2)",
            f'[2026-09-28T10:01:00+00:00] gemini - tool call: run_shell_command({{"command": "pytest -q"}})  ({raw} record 2)',
            f"[2026-09-28T10:01:00+00:00] gemini - tool result: (status error) boom  ({raw} record 2)",
            "[2026-09-28T10:02:00+00:00] note: future-message-kind  (raw log record 3)"])

    def test_the_index_counts_what_the_transcripts_show(self):
        out = self.gather(*self.places())
        # session, place, start, end, cwd, records, user-role text, other text, tool calls
        self.assertEqual(cells_of(out, uid(1))[:9], [
            uid(1), str(self.rollouts), "2026-09-28T10:00:00+00:00", "2026-09-28T10:06:00+00:00", self.CWD, "8", "1", "2", "1"])
        self.assertEqual(cells_of(out, "claude-a")[:9], [
            "claude-a", str(self.transcripts), "2026-09-28T10:00:00+00:00", "2026-09-28T10:04:00+00:00", self.CWD, "6", "1", "2", "1"])
        # The chat's own first and last times bound it beyond its records' (the last of which is at 10:02).
        self.assertEqual(cells_of(out, "gem-1")[:9], [
            "gem-1", str(self.chats), "2026-09-28T10:00:00+00:00", "2026-09-28T10:05:00+00:00", "", "3", "1", "1", "1"])
        for cells, raw in ((cells_of(out, uid(1)), self.rollout), (cells_of(out, "claude-a"), self.transcript_raw),
                           (cells_of(out, "gem-1"), self.chat_raw)):
            self.assertRegex(cells[9], r"^\d+(\.\d)?(B|KB)$")
            self.assertEqual(cells[11], str(raw))
            self.assertRegex(link_of(cells), r"^sessions/s-[0-9a-f]{12}\.md$")
            self.assertEqual(cells[10], f"[{link_of(cells)}]({link_of(cells)})")

    def test_prints_the_output_directory_and_what_it_read(self):
        out = self.gather(*self.places())
        # By hand: three sessions of 8, 6 and 3 records; the notes are 1 + 3 of the rollout (two lines), 2 of the
        # transcript (one line) and 1 of the chat (one line).
        self.assertEqual(self.stdout.splitlines(), [
            f"wrote {out}", "sessions: 3 from 3 place(s), 17 records", "unrendered-but-noted records: 7 (in 4 transcript lines)",
            f"{self.rollouts}: 1 record file(s); 1 session(s) in the window",
            f"{self.transcripts}: 1 record file(s); 1 session(s) in the window",
            f"{self.chats}: 1 record file(s); 1 session(s) in the window"])

    def test_masks_token_like_strings_in_every_file_it_writes(self):
        out = self.gather(*self.places())
        files = written(out)
        self.assertGreater(len(files), 4)
        for path, text in files:
            self.assertNotIn(self.TOKEN, text, path.name)
            self.assertNotIn(self.TOKEN, path.name)
        self.assertIn("with token [masked]", transcript_of(out, uid(1)))

    def test_a_record_with_nothing_to_show_is_noted_not_silently_dropped(self):
        jl(self.logs / "empty.jsonl", stamped([
            {"type": "user", "sessionId": "empty-1", "message": {"content": ""}},
            {"type": "assistant", "sessionId": "empty-1", "message": {"content": []}},
            {"type": "user", "sessionId": "empty-1", "message": {"content": "   \n  "}}]))
        write_json(self.logs / "empty.json", {"sessionId": "gem-empty", "messages": [
            {"type": "gemini", "content": "", "timestamp": at(0)}]})
        out = self.gather()
        self.assertEqual(body_of(transcript_of(out, "empty-1")), [
            f"[{shown(0)}] note: user x2, assistant through {shown(2)}  (raw log lines 1-3)"])
        self.assertEqual(body_of(transcript_of(out, "gem-empty")), [f"[{shown(0)}] note: gemini  (raw log record 1)"])

    def test_malformed_records_are_noted_not_fatal(self):
        bad = self.root / "bad"
        jl(bad / "rollout-bad.jsonl", [
            {"timestamp": at(0), "type": "session_meta", "payload": {"id": 12345, "cwd": ["not", "a", "string"]}},
            [],  # a record that is not an object
            {"timestamp": at(2), "type": "response_item", "payload": "not-an-object"},
            item(at(3), {"type": "UserMessage", "id": uid(1), "content": text_blocks("still readable")})])
        jl(bad / "transcript-bad.jsonl", [
            {"timestamp": at(0), "type": "user", "sessionId": "t-bad", "cwd": ["not", "a", "string"], "message": "not an object"},
            {"timestamp": at(1), "type": "assistant", "sessionId": "t-bad", "message": {"content": [{"type": "text", "text": None}]}},
            {"timestamp": at(2), "type": "assistant", "sessionId": "t-bad",
             "message": {"content": [{"type": "text", "text": "still readable too"}]}}])
        write_json(bad / "bad-list.json", ["not", "an", "object"])
        write_json(bad / "bad-messages.json", {"sessionId": "gem-bad-1", "messages": {"not": "a list"}})
        write_json(bad / "bad-toolcalls.json", {"sessionId": "gem-bad-2", "messages": [
            {"type": "gemini", "content": "All fine here", "timestamp": at(0), "toolCalls": ["not-an-object"]}]})
        out = self.gather(bad)
        self.assertTrue((out / "index.md").is_file())
        rollout, transcript = bad / "rollout-bad.jsonl", bad / "transcript-bad.jsonl"
        # By hand: the session record's id is a number, so it names nothing; its list of short strings is what it
        # lists, so it is a line; the list that is no record and the payload that is no object are notes in a row.
        self.assertEqual(body_of(transcript_at(out, rollout)), [
            row(rollout, 1, "session_meta", "cwd: not, a, string"),
            f"[{shown(2)}] note: a record that is not an object (list), response_item  (raw log lines 2-3)",
            f"[{shown(3)}] event_msg > item_completed > UserMessage: still readable  ({rollout}:4)"])
        self.assertIn("records: 3  ", transcript_at(out, rollout).splitlines())  # the list is no record
        self.assertEqual(body_of(transcript_at(out, transcript)), [
            row(transcript, 1, "user", "not an object"),
            f"[{shown(1)}] note: assistant  (raw log line 2)",
            row(transcript, 3, "assistant", "still readable too")])
        self.assertEqual(body_of(transcript_of(out, "gem-bad-2")), [
            f"[{shown(0)}] gemini: All fine here  ({bad / 'bad-toolcalls.json'} record 1)"])
        self.assertEqual(places_of(out), [
            f"{bad}: 5 record file(s); 3 session(s) in the window; 2 not read, a JSON document with no list of records "
            f"(e.g. {bad / 'bad-list.json'})"])

    def test_survives_a_non_utf8_locale_and_preserves_unicode_text(self):
        jl(self.logs / "escaped.jsonl", [{"timestamp": at(0), "type": "user", "sessionId": "unicode-1",
                                          "message": {"content": "café → ✓ 日本語"}}])
        # The same text as the bytes a harness writes, and a byte that is no UTF-8 at all.
        raw = self.logs / "bytes.jsonl"
        raw.write_bytes(b'{"timestamp": "' + at(0).encode() + b'", "type": "user", "sessionId": "unicode-2", '
                        b'"message": {"content": "caf\xc3\xa9 \xe2\x86\x92 \xff end"}}\n')
        out = self.gather(extra_env={"LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"})
        self.assertIn("] user: café → ✓ 日本語  (", transcript_of(out, "unicode-1"))
        self.assertIn("] user: café → \ufffd end  (", transcript_of(out, "unicode-2"))

    def test_default_out_is_a_private_temp_directory_not_the_cwd(self):
        cwd, tmp = self.root / "cwd", self.root / "tmp"
        cwd.mkdir()
        tmp.mkdir()
        r = run_gather_script([self.rollouts, "--since", "2000-01-01"], cwd=cwd,
                              extra_env={"TMPDIR": str(tmp), "TMP": str(tmp), "TEMP": str(tmp)})
        self.assertEqual(r.returncode, 0, r.stderr)
        wrote = [line for line in r.stdout.splitlines() if line.startswith("wrote ")]
        self.assertEqual(len(wrote), 1, r.stdout)
        written_dir = Path(wrote[0][len("wrote "):])
        self.assertTrue(written_dir.is_dir())
        self.assertEqual(written_dir.parent.resolve(), tmp.resolve())  # a new directory of the system's temporary one
        self.assertTrue((written_dir / "index.md").is_file())
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(written_dir.stat().st_mode), 0o700)
        self.assertEqual(list(cwd.iterdir()), [])  # nothing was written into the directory it ran in

    def test_refuses_nonempty_out_without_force(self):
        empty = self.root / "run-empty"
        empty.mkdir()
        r0 = run_gather_script([self.rollouts, "--since", "2000-01-01", "--out", empty])
        self.assertEqual(r0.returncode, 0, r0.stderr)  # a directory that exists with nothing in it is fine
        out = self.root / "run-refuse"
        out.mkdir(parents=True)
        (out / "stray-file.txt").write_text("pre-existing")
        r = run_gather_script([self.rollouts, "--since", "2000-01-01", "--out", out])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("error:", r.stderr)
        self.assertIn("--force", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse((out / "index.md").exists())
        self.assertEqual((out / "stray-file.txt").read_text(), "pre-existing")  # untouched
        # --force allows writing into it anyway.
        r2 = run_gather_script([self.rollouts, "--since", "2000-01-01", "--out", out, "--force"])
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertTrue((out / "index.md").exists())
        self.assertTrue((out / "stray-file.txt").exists())

    def test_missing_git_binary_is_reported_explicitly(self):
        out = self.root / "run-no-git"
        empty_path_dir = self.root / "empty-path"
        empty_path_dir.mkdir()
        # An empty directory as the whole PATH: no git, no crontab or systemctl either. sys.executable is an
        # absolute path, so launching Python itself doesn't depend on PATH resolution.
        r = run_gather_script([self.transcripts, "--since", "2000-01-01", "--out", out], extra_env={"PATH": str(empty_path_dir)})
        self.assertEqual(r.returncode, 0, r.stderr)
        workspace = (out / "workspace.md").read_text(encoding="utf-8")
        self.assertIn("git was not found on PATH", workspace)
        self.assertNotIn("No session named a working directory", workspace)
        self.assertIn("- cron: crontab: not found on PATH", workspace.splitlines())
        self.assertIn("- systemd --user timers: systemctl: not found on PATH", workspace.splitlines())

    def test_every_raw_line_and_every_record_is_a_line_or_inside_a_noted_range(self):
        # Records of every kind there are -- lines, reminders counted into notes, notes -- with lines that are no
        # record among them (not JSON, a list, a bare string) and a blank one. Nothing is dropped: whatever a file
        # holds is where some line says it is, or inside the range of a note.
        raws = [json.dumps(r) for r in stamped(repeating_records())]
        raws.append('"a bare string"')
        raws.insert(10, "[]")                      # between two lines of reminders
        raws.insert(7, "this line is not JSON")    # between two lines
        raws.insert(1, "")                         # a blank line holds nothing
        raw = self.logs / "everything.jsonl"
        raw.write_text("\n".join(raws) + "\n")
        document = write_json(self.logs / "everything.json", {"events": stamped(repeating_records())})
        out = self.gather()
        self.assertEqual(covered_by(body_of(transcript_at(out, raw)), raw, "line"), {n for n, text in enumerate(raws, 1) if text.strip()})
        self.assertEqual(covered_by(body_of(transcript_at(out, document)), document, "record"), set(range(1, 32)))


# ---------------------------------------------------------------------------- places

class PlacesTest(LogHome):
    """The places gather.py is given -- a file of records, a directory searched for them, one that is not there,
    none at all -- and what the index and standard output say that each held, the files it did not read included."""

    def log(self, path, session_id, text="hello there"):
        return jl(path, [{"timestamp": at(0), "type": "user", "sessionId": session_id, "message": {"content": text}}])

    def test_a_file_is_a_place_and_a_directory_is_searched_and_its_other_files_are_counted(self):
        single = self.log(self.root / "single.jsonl", "single")
        tree = self.root / "tree"
        self.log(tree / "a.jsonl", "a")
        self.log(tree / "sub" / "b.ndjson", "b")
        write_json(tree / "sub" / "deeper" / "c.json", {"sessionId": "c", "messages": [
            {"type": "user", "content": "from c", "timestamp": at(0)}]})
        (tree / "notes.md").write_text("prose\n")
        (tree / "sub" / "data.csv").write_text("a,b\n")
        out = self.gather(single, tree)
        expected = [f"{single}: 1 record file(s); 1 session(s) in the window",
                    f"{tree}: 3 record file(s); 3 session(s) in the window; 2 other file(s) not read"]
        self.assertEqual(places_of(out), expected)
        self.assertEqual(self.stdout.splitlines()[3:], expected)  # and standard output says the same
        self.assertEqual({cells[0]: cells[1] for cells in index_rows(out)},
                         {"single": str(single), "a": str(tree), "b": str(tree), "c": str(tree)})
        self.assertEqual(cells_of(out, "b")[11], str(tree / "sub" / "b.ndjson"))

    def test_a_symbolic_link_to_a_directory_is_not_followed(self):
        tree = self.root / "tree"
        self.log(tree / "a.jsonl", "a")
        elsewhere = self.log(self.root / "elsewhere" / "z.jsonl", "z")
        try:
            os.symlink(elsewhere.parent, tree / "linked", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this system makes no symbolic links")
        out = self.gather(tree)
        self.assertEqual(places_of(out), [f"{tree}: 1 record file(s); 1 session(s) in the window"])
        self.assertEqual(self.session_ids(out), {"a"})

    def test_a_missing_place_is_named_and_the_others_are_still_read(self):
        present = self.log(self.root / "present.jsonl", "present")
        missing = self.root / "no-such-place"
        out = self.gather(missing, present)
        expected = [f"{missing}: not found", f"{present}: 1 record file(s); 1 session(s) in the window"]
        self.assertEqual(places_of(out), expected)
        self.assertEqual(self.stdout.splitlines()[3:], expected)
        self.assertEqual(self.session_ids(out), {"present"})

    def test_no_places_and_none_found_is_an_index_that_says_so_and_a_zero_exit(self):
        out = self.root / "none-given"
        r = run_gather_script(["--since", "2000-01-01", "--out", out])  # the suite's home is empty
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(places_of(out), ["none found: name the places where the harnesses that did the work keep their "
                                          "session records"])
        self.assertEqual(index_rows(out), [])
        self.assertEqual(r.stdout.splitlines()[:2], [f"wrote {out}", "sessions: 0 from 0 place(s), 0 records"])
        self.assertIn("no places given; found 0: name any others where the harnesses that did the work keep their records",
                      r.stdout)
        self.assertTrue((out / "workspace.md").is_file())

    def conversation(self, path, session_id, when):
        return jl(path, [{"timestamp": when, "type": "user", "sessionId": session_id, "message": {"content": "fix the build"}},
                         {"timestamp": when, "type": "assistant", "sessionId": session_id, "message": {"content": "done"}}])

    def test_with_no_places_the_stores_of_recent_conversations_under_the_home_are_found_and_read(self):
        # Discovery knows no harness: a place is the directory just under a hidden directory of the home, or under one
        # in the platform's data, state or configuration directories, that holds recent records labeled with who speaks
        # (or that directory itself, when its own files do). Records of no conversation (an app's log, a browser's list of
        # extensions), records not written since --since, and copies in the cache directory are not places.
        home = self.root / "home"
        recent = hours_ago(1)
        self.conversation(home / ".agent-a" / "sessions" / "2026" / "10" / "17" / "rollout-1.jsonl", "a-1", recent)
        write_json(home / ".agent-a" / "settings.json", {"theme": "dark"})
        self.conversation(home / ".agent-b" / "session.jsonl", "b-1", recent)
        old = self.conversation(home / ".agent-c" / "history" / "old.jsonl", "c-1", hours_ago(24 * 30))
        stale = (dt.datetime.now(UTC) - dt.timedelta(days=30)).timestamp()
        os.utime(old, (stale, stale))
        write_json(home / ".local" / "share" / "chat-app" / "chats" / "c1.json", {"sessionId": "chat-1", "messages": [
            {"role": "user", "content": "what failed?", "timestamp": recent},
            {"role": "model", "content": "the lint step", "timestamp": recent}]})
        write_json(home / ".config" / "browser" / "profile" / "extensions.json", {"addons": [
            {"type": "extension", "id": "x1", "updated": recent, "name": "reader"},
            {"type": "theme", "id": "x2", "updated": recent, "name": "night"}]})
        jl(home / ".config" / "editor" / "logs" / "main.jsonl", [{"timestamp": recent, "type": "info", "message": "window opened"},
                                                                {"timestamp": recent, "type": "warning", "message": "slow start"}])
        self.conversation(home / ".cache" / "trials" / "run-1" / "session.jsonl", "copy-1", recent)
        out = self.gather(since=None, extra_env={"HOME": str(home), "USERPROFILE": str(home)}, places_given=False)
        self.assertEqual([line.split(":")[0] for line in places_of(out)],
                         ["~/.agent-a/sessions", "~/.agent-b", "~/.local/share/chat-app/chats"])
        self.assertEqual(self.session_ids(out), {"a-1", "b-1", "chat-1"})
        self.assertIn("no places given; found 3: name any others where the harnesses that did the work keep their records",
                      self.stdout)
        self.assertTrue((out / "index.md").read_text(encoding="utf-8").splitlines()[2].startswith("Places (none were given;"))

    def test_with_places_given_the_stores_found_that_none_of_them_covers_are_named_and_not_read(self):
        # A given place covers a store it is or holds; one given inside a store leaves the rest of that store out.
        home = self.root / "home"
        recent = hours_ago(1)
        self.conversation(home / ".agent-a" / "sessions" / "s1.jsonl", "a-1", recent)
        self.conversation(home / ".agent-b" / "projects" / "p" / "s2.jsonl", "b-1", recent)
        self.conversation(home / ".agent-b" / "projects" / "q" / "s3.jsonl", "b-2", recent)
        self.conversation(home / ".agent-e" / "chats" / "s4.jsonl", "e-1", recent)
        out = self.gather(home / ".agent-a", home / ".agent-b" / "projects" / "p", since=None,
                          extra_env={"HOME": str(home), "USERPROFILE": str(home)})
        self.assertEqual(self.session_ids(out), {"a-1", "b-1"})
        lines = (out / "index.md").read_text(encoding="utf-8").splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("Also holding recent session records")) + 1
        self.assertEqual(lines[start:lines.index("", start)], ["- ~/.agent-b/projects", "- ~/.agent-e/chats"])
        self.assertIn("also found, not read: ~/.agent-e/chats: name it to read it", self.stdout.splitlines())

    def test_discovery_reads_a_stores_newest_directories_first_within_its_budget(self):
        # A store's ancestors keep old times while new sessions land in its newest directory, so each directory just
        # under a root is read newest directory first; an older sibling larger than the budget does not hide today's.
        home = self.root / "home"
        store = home / ".agent-d" / "sessions"
        for n in range(30):
            self.conversation(store / "2026" / "09" / f"old-{n}.jsonl", f"old-{n}", hours_ago(24 * 30))
        stale = (dt.datetime.now(UTC) - dt.timedelta(days=30)).timestamp()
        for path in (store / "2026" / "09").iterdir():
            os.utime(path, (stale, stale))
        os.utime(store / "2026" / "09", (stale, stale))
        self.conversation(store / "2026" / "10" / "new.jsonl", "new", hours_ago(1))
        since = dt.datetime.now(UTC) - dt.timedelta(days=7)
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}), \
                mock.patch.object(gather, "DISCOVERY_BUDGET", 10):
            for key in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "APPDATA", "LOCALAPPDATA"):
                os.environ.pop(key, None)
            self.assertEqual(gather.discover_places(since), [store])

    def test_a_file_without_a_record_suffix_named_as_a_place_is_one_other_file_not_read(self):
        # What it holds would be a record if it were read as JSON Lines; it is not read at all.
        notes = self.root / "notes.md"
        notes.write_text('# Notes\n{"type": "user", "message": {"content": "this is prose, not a record"}}\n')
        todo = self.root / "todo.txt"
        todo.write_text("buy milk\n")
        out = self.gather(notes, todo)
        self.assertEqual(places_of(out), [
            f"{notes}: 0 record file(s); 0 session(s) in the window; 1 other file(s) not read",
            f"{todo}: 0 record file(s); 0 session(s) in the window; 1 other file(s) not read"])
        self.assertEqual(index_rows(out), [])
        self.assertEqual(list((out / "sessions").iterdir()), [])
        self.assertIn("sessions: 0 from 2 place(s), 0 records", self.stdout)

    def test_a_directory_with_nothing_to_read_has_its_line_all_the_same(self):
        empty = self.root / "empty"
        empty.mkdir()
        others = self.root / "others"
        (others / "deep").mkdir(parents=True)
        (others / "a.txt").write_text("x")
        (others / "deep" / "b.log").write_text("y")
        out = self.gather(empty, others)
        self.assertEqual(places_of(out), [f"{empty}: 0 record file(s); 0 session(s) in the window",
                                          f"{others}: 0 record file(s); 0 session(s) in the window; 2 other file(s) not read"])

    @unittest.skipIf(os.name == "nt", "a home directory is shown as ~/ on POSIX")
    def test_a_tilde_in_a_place_is_the_home_directory_and_is_shown_as_one(self):
        home = self.root / "home"
        self.log(home / "logs" / "a.jsonl", "tilde-a")
        out = self.gather("~/logs", extra_env={"HOME": str(home), "USERPROFILE": str(home)})
        self.assertEqual(places_of(out), ["~/logs: 1 record file(s); 1 session(s) in the window"])
        cells = cells_of(out, "tilde-a")
        self.assertEqual((cells[1], cells[11]), ("~/logs", "~/logs/a.jsonl"))
        self.assertEqual(transcript_of(out, "tilde-a").splitlines()[2:4], ["place: ~/logs  ", f"raw log: {home}/logs/a.jsonl  "])

    def test_a_log_that_holds_no_record_is_not_read_and_one_of_garbage_is_a_session_of_notes(self):
        odd = self.root / "odd"
        odd.mkdir()
        (odd / "empty.jsonl").write_text("")
        (odd / "blank.jsonl").write_text("\n  \n\n")
        (odd / "garbage.jsonl").write_text("not json at all\nstill not json\n")
        out = self.gather(odd)
        self.assertEqual(places_of(out), [
            f"{odd}: 3 record file(s); 1 session(s) in the window; 2 not read, no records (e.g. {odd / 'blank.jsonl'})"])
        # By hand: no record, no time, so the file's own time places it; two unparseable lines in a row are one note.
        self.assertEqual(cells_of(out, "garbage")[2:9], ["", "", "", "0", "0", "0", "0"])
        self.assertEqual(body_of(transcript_of(out, "garbage")), ["[] note: unparseable line x2  (raw log lines 1-2)"])

    @unittest.skipUnless(os.name == "posix", "directory permissions are those of POSIX")
    def test_a_directory_that_cannot_be_read_is_reported_in_its_places_line_and_the_rest_is_read(self):
        tree = self.root / "tree"
        self.log(tree / "ok.jsonl", "ok")
        locked, deeper = tree / "locked", tree / "sub" / "locked2"
        self.log(locked / "hidden.jsonl", "hidden")
        self.log(deeper / "hidden2.jsonl", "hidden2")
        for directory in (locked, deeper):
            directory.chmod(0)
            self.addCleanup(directory.chmod, 0o700)  # so that the test's own directory can be removed
        if os.access(locked, os.R_OK):
            self.skipTest("this user can read a directory whatever its mode (root, say)")
        out = self.gather(tree)
        # By hand: the walk goes down in order of name, so "locked" is the first it cannot open, and "sub" is read to find
        # the second. Neither holds a file it could count, so one record file is all there is.
        self.assertEqual(places_of(out), [
            f"{tree}: 1 record file(s); 1 session(s) in the window; 2 director(ies) could not be read "
            f"(e.g. {locked}: Permission denied)"])
        self.assertEqual(self.session_ids(out), {"ok"})


# ---------------------------------------------------------------------------- compressed logs

class CompressedTest(LogHome):
    """A log compressed with gzip, bzip2, xz or zstd is read as the log it holds."""

    OPENERS = {".gz": gzip.open, ".bz2": bz2.open, ".xz": lzma.open}

    @staticmethod
    def rows(name):
        return [{"timestamp": at(i), **record} for i, record in enumerate([
            {"type": "user", "sessionId": name, "message": {"content": f"{name} said hello"}},
            {"type": "assistant", "sessionId": name, "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}}])]

    def compress(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(json.dumps(r) for r in rows) + "\n"
        if path.suffix == ".zst":
            try:
                from compression import zstd
            except ImportError:
                if not shutil.which("zstd"):
                    self.skipTest("neither Python's compression.zstd nor a zstd command is available to read or write zstd")
                subprocess.run(["zstd", "-q", "-f", "-o", str(path)], input=text.encode("utf-8"), check=True)
            else:
                with zstd.open(path, "wt", encoding="utf-8") as fh:
                    fh.write(text)
        else:
            with self.OPENERS[path.suffix](path, "wt", encoding="utf-8") as fh:
                fh.write(text)
        return path

    def assert_read_as_a_log(self, out, path, name):
        text = transcript_at(out, path)
        self.assertEqual(text.splitlines()[3], f"raw log: {path}  ")
        self.assertEqual(body_of(text), [row(path, 1, "user", f"{name} said hello"),
                                         row(path, 2, "assistant", 'Bash({"command": "ls"})', "tool call")])

    def test_gzip_bzip2_and_xz_logs_and_a_compressed_document_are_read(self):
        d = self.root / "packed"
        logs = {name: self.compress(d / f"{name}.jsonl.{ext}", self.rows(name)) for name, ext in (("gz", "gz"), ("bz2", "bz2"), ("xz", "xz"))}
        plain = jl(d / "plain.jsonl", self.rows("plain"))
        document = d / "doc.json.gz"
        with gzip.open(document, "wt", encoding="utf-8") as fh:
            json.dump({"sessionId": "docgz", "messages": [{"type": "user", "content": "docgz said hello", "timestamp": at(0)}]}, fh)
        out = self.gather(d)
        self.assertEqual(places_of(out), [f"{d}: 5 record file(s); 5 session(s) in the window"])
        for name, path in logs.items():
            self.assert_read_as_a_log(out, path, name)
        self.assert_read_as_a_log(out, plain, "plain")
        self.assertEqual(body_of(transcript_of(out, "docgz")), [f"[{shown(0)}] user: docgz said hello  ({document} record 1)"])

    def test_a_compressed_log_no_record_names_is_named_for_its_file(self):
        d = self.root / "unnamed"
        self.compress(d / "rollout-7.jsonl.gz", [{"timestamp": at(0), "type": "user", "message": {"content": "no name"}}])
        out = self.gather(d)
        self.assertEqual(self.session_ids(out), {"rollout-7"})

    def test_a_zstd_log_is_read_where_python_or_a_zstd_command_can_read_it(self):
        d = self.root / "packed"
        path = self.compress(d / "zst.jsonl.zst", self.rows("zst"))
        out = self.gather(d)
        self.assertEqual(places_of(out), [f"{d}: 1 record file(s); 1 session(s) in the window"])
        self.assert_read_as_a_log(out, path, "zst")

    def test_a_compressed_log_old_by_its_files_time_is_reported_not_read_and_a_plain_one_is_read_by_its_last_record(self):
        # Every log below holds a record from an hour ago, and --since is a day ago. A JSON Lines log that was
        # written long ago by its file's clock is still read, for its last record is recent; a compressed one has
        # no end to read cheaply, and its file's time, which compressing it set, is old: it is not read, and the
        # index says so, rather than count it among the sessions that fall outside the window.
        d = self.root / "ages"
        month_ago = dt.datetime.now(UTC).timestamp() - 30 * 86400
        recent = [{"timestamp": hours_ago(1), "type": "user", "sessionId": "x", "message": {"content": "an hour ago"}}]
        fresh = self.compress(d / "fresh.jsonl.gz", [{**r, "sessionId": "fresh"} for r in recent])
        stale = self.compress(d / "stale.jsonl.gz", [{**r, "sessionId": "stale"} for r in recent])
        plain = jl(d / "plain.jsonl", [{**r, "sessionId": "plain"} for r in recent])
        # A compressed log written now whose records are old is read, and falls outside the window by its records.
        self.compress(d / "old.jsonl.gz", [{"timestamp": "2020-01-01T00:00:00Z", "type": "user", "sessionId": "old",
                                            "message": {"content": "years ago"}}])
        for path in (stale, plain):
            os.utime(path, (month_ago, month_ago))
        out = self.gather(d, since="1d")
        self.assertEqual(self.session_ids(out), {"fresh", "plain"})
        self.assertEqual(places_of(out), [
            f"{d}: 4 record file(s); 2 session(s) in the window; 1 outside it; "
            f"1 not read, compressed, and older than --since by its file's time (e.g. {stale})"])  # "outside" is the old one by its records
        self.assertIn("an hour ago", transcript_at(out, fresh))

    def test_a_corrupt_compressed_log_is_reported_as_not_read_and_costs_no_other_file_its_evidence(self):
        d = self.root / "mixed"
        jl(d / "good.jsonl", self.rows("good"))
        (d / "corrupt.jsonl.gz").write_bytes(b"this is not gzip data")
        out = self.gather(d)
        self.assertRegex(places_of(out)[0], rf"^{re.escape(str(d))}: 2 record file\(s\); 1 session\(s\) in the window; "
                                            rf"1 not read, .+ \(e\.g\. {re.escape(str(d / 'corrupt.jsonl.gz'))}\)$")
        self.assertEqual(self.session_ids(out), {"good"})


# ---------------------------------------------------------------------------- JSON documents

class JsonDocumentTest(LogHome):
    """A JSON document is read as the session it holds: its records are its longest list of objects that carry a
    type, a role or a time; the session id and the times it names at its top level count; and a document with no
    such list is reported in the index as not read, with the reason."""

    def setUp(self):
        super().setUp()
        self.chat = write_json(self.logs / "chat.json", {
            "sessionId": "gem-doc", "startTime": at(0), "lastUpdated": at(9),
            "files": [{"path": "a"}, {"path": "b"}, {"path": "c"}, {"path": "d"}, {"path": "e"}],  # the longest list, of objects that carry nothing
            "drafts": [{"type": "draft", "content": "an unused draft"}],
            "messages": [
                {"type": "user", "content": "Build it now", "timestamp": at(3)},
                {"role": "model", "parts": [{"text": "All done here"}], "timestamp": at(5)},
                {"type": "info", "timestamp": at(6)}]})

    def test_the_records_are_the_longest_list_of_objects_that_carry_a_type_a_role_or_a_time(self):
        out = self.gather()
        raw = self.chat
        text = transcript_of(out, "gem-doc")
        self.assertIn("records: 3  ", text.splitlines())
        # Their references read "record N", and a note says so too.
        self.assertEqual(body_of(text), [
            f"[{shown(3)}] user: Build it now  ({raw} record 1)",
            f"[{shown(5)}] model: All done here  ({raw} record 2)",
            f"[{shown(6)}] note: info  (raw log record 3)"])

    def test_the_session_id_and_the_times_at_the_top_level_count(self):
        # The id is the document's, not the file's name; the session spans its top-level first and last times,
        # beyond those of its records (at 3, 5 and 6 seconds).
        out = self.gather()
        self.assertEqual(cells_of(out, "gem-doc")[2:4], [shown(0), shown(9)])
        self.assertEqual(self.session_ids(out), {"gem-doc"})
        # Only its last update is at or after 8 seconds, and it puts the session in that window and not in the next.
        self.assertEqual(self.session_ids(self.gather(since=at(8))), {"gem-doc"})
        out = self.gather(since=at(10))
        self.assertEqual(self.session_ids(out), set())
        self.assertEqual(places_of(out), [f"{self.logs}: 1 record file(s); 0 session(s) in the window; 1 outside it"])

    def test_a_list_of_records_is_found_at_the_top_and_down_in_objects(self):
        write_json(self.root / "docs" / "toplist.json", [
            {"type": "user", "content": "from a bare list", "timestamp": at(0)},
            {"type": "assistant", "content": "second one here", "timestamp": at(1)}])
        write_json(self.root / "docs" / "nested.json", {"session": {"events": [
            {"type": "user", "content": "from a list below", "timestamp": at(2)}]}})
        out = self.gather(self.root / "docs")
        top, nested = self.root / "docs" / "toplist.json", self.root / "docs" / "nested.json"
        self.assertEqual(body_of(transcript_of(out, "toplist")), [
            f"[{shown(0)}] user: from a bare list  ({top} record 1)", f"[{shown(1)}] assistant: second one here  ({top} record 2)"])
        self.assertEqual(body_of(transcript_of(out, "nested")), [f"[{shown(2)}] user: from a list below  ({nested} record 1)"])

    def test_a_document_with_no_list_of_records_is_reported_as_not_read_with_the_reason(self):
        d = self.root / "unread"
        write_json(d / "settings.json", {"settings": {"theme": "dark"}, "items": [1, 2, 3]})
        write_json(d / "rows.json", {"rows": [{"a": 1}, {"b": 2}]})  # objects, and none carries a type, a role or a time
        (d / "broken.json").write_text("{not json")
        out = self.gather(d)
        self.assertEqual(places_of(out), [
            f"{d}: 3 record file(s); 0 session(s) in the window; "
            f"2 not read, a JSON document with no list of records (e.g. {d / 'rows.json'}); "
            f"1 not read, not a JSON document (JSONDecodeError) (e.g. {d / 'broken.json'})"])
        self.assertEqual(index_rows(out), [])

    def test_a_documents_working_directory_counts_toward_the_sessions(self):
        write_json(self.logs / "top.json", {"sessionId": "doc-top", "cwd": "/srv/doc-dir", "messages": [
            {"type": "user", "content": "from a doc", "timestamp": at(0)}]})
        write_json(self.logs / "vote.json", {"sessionId": "doc-vote", "workingDirectory": "/srv/top", "messages": [
            {"type": "user", "content": "one here", "cwd": "/srv/records", "timestamp": at(0)},
            {"type": "user", "content": "two here", "cwd": "/srv/records", "timestamp": at(1)}]})
        out = self.gather()
        self.assertEqual(cells_of(out, "doc-top")[4], "/srv/doc-dir")           # no record names one, the document does
        self.assertIn("cwd: /srv/doc-dir  ", transcript_of(out, "doc-top").splitlines())
        self.assertEqual(cells_of(out, "doc-vote")[4], "/srv/records")          # one vote, and two records outvote it


# ---------------------------------------------------------------------------- workspace facts

class WorkspaceTest(LogHome):
    """workspace.md names, for each git repository the sessions name as a working directory and for the one
    gather.py runs in, its branches, worktrees and stashes, and lists the scheduled jobs the operating system
    can: facts, not verdicts."""

    PREFIX = "## Scheduled"

    def named_repos(self, workspace):
        return [line for line in workspace.splitlines() if line.startswith("## ") and not line.startswith(self.PREFIX)]

    def test_git_workspace_reports_branches_a_worktree_and_a_stash_as_facts(self):
        repo = make_repo(self.root / "repo", branches=["done-feature"], stash="wip")
        worktree = self.root / "repo-wt"
        git(repo, "worktree", "add", "-q", str(worktree), "-b", "topic")
        jl(self.logs / "a.jsonl", stamped([{"type": "user", "sessionId": "ws-a", "cwd": str(repo), "message": {"content": "hello there"}}]))
        workspace = (self.gather() / "workspace.md").read_text(encoding="utf-8")
        lines = workspace.splitlines()
        # By hand: both branches were made at the default branch's only commit, so both are merged into it; topic is
        # checked out in the worktree, which git marks "+ topic" in its list of merged branches and the fact does not.
        self.assertEqual(lines[:9], [
            "# Workspace facts", "", f"## {repo.resolve()}", "",
            "- default branch: main", "- local branches (2): done-feature, topic", "- merged into default (2): done-feature, topic",
            f"- worktrees (1): {worktree.resolve()}", "- stashes (1): stash@{0}: On main: wip"])
        self.assertNotIn("+ topic", workspace)

    def test_every_directory_the_sessions_name_and_the_one_it_runs_in_are_looked_at_once_each(self):
        a = make_repo(self.root / "repo-a")
        (a / "sub").mkdir()
        b = make_repo(self.root / "repo-b", branches=["only-in-b"])
        c = make_repo(self.root / "repo-c", stash="from-c")
        plain = self.root / "not-a-repo"
        plain.mkdir()
        # A is named most, and by a directory below it as well; a directory that is no repository is named once;
        # B only at the top level of a JSON document, whose records name no directory.
        jl(self.logs / "a.jsonl", stamped([
            {"type": "user", "sessionId": "named-a", "cwd": str(a), "message": {"content": "one"}},
            {"type": "user", "sessionId": "named-a", "workdir": str(a), "message": {"content": "two"}},
            {"type": "user", "sessionId": "named-a", "cwd": str(a), "message": {"content": "three"}},
            {"type": "user", "sessionId": "named-a", "cwd": str(a / "sub"), "message": {"content": "four"}},
            {"type": "user", "sessionId": "named-a", "cwd": str(plain), "message": {"content": "five"}}]))
        write_json(self.logs / "b.json", {"sessionId": "named-b", "cwd": str(b), "messages": [
            {"type": "user", "content": "from b", "timestamp": at(0)}]})
        out = self.gather(cwd=c)
        workspace = (out / "workspace.md").read_text(encoding="utf-8")
        self.assertEqual(self.named_repos(workspace), [f"## {a.resolve()}", f"## {b.resolve()}", f"## {c.resolve()}"])
        self.assertIn("- local branches (1): only-in-b", workspace)
        self.assertIn("- stashes (1): stash@{0}: On main: from-c", workspace)
        self.assertNotIn(str(plain), workspace)
        # The index names a session's working directory as its most common one.
        self.assertEqual(cells_of(out, "named-a")[4], str(a))

    def test_directories_that_are_no_repository_are_said_to_be_none_and_not_an_error(self):
        jl(self.logs / "a.jsonl", stamped([{"type": "user", "sessionId": "x", "cwd": "/srv/no/such/dir", "message": {"content": "hello there"}}]))
        workspace = (self.gather() / "workspace.md").read_text(encoding="utf-8")
        self.assertIn("No session named a working directory that resolves to a git repository, and this one is not in one.",
                      workspace.splitlines())
        self.assertEqual(self.named_repos(workspace), [])

    @unittest.skipIf(os.name == "nt", "the fake commands are shell scripts")
    def test_the_scheduled_jobs_the_system_lists_are_facts_with_their_secrets_masked(self):
        secret = "gh" + "p_" + "a" * 30  # assembled at run time: nothing secret-shaped is committed
        escaped = '{"p\\u0061ssword": "say violet kettle now"}'  # a credential that only a pass that decodes JSON can see
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        crontab = ["# a comment", "", f"0 3 * * * /usr/local/bin/backup {secret}", "@reboot /usr/local/bin/start",
                   f"0 4 * * * curl -d '{escaped}' http://localhost"]
        systemctl = ["Sat 2026-10-17 03:00:00 UTC 2h left - - backup.timer backup.service", ""]
        for name, lines in (("crontab", crontab), ("systemctl", systemctl)):
            # A command that prints what is in the file beside it, with the shell's own commands alone (the PATH is only this).
            (bin_dir / f"{name}.out").write_text("\n".join(lines) + "\n")
            script = bin_dir / name
            script.write_text("#!/bin/sh\nwhile IFS= read -r line; do printf '%s\\n' \"$line\"; done < \"$0.out\"\n")
            script.chmod(0o755)
        out = self.gather(extra_env={"PATH": str(bin_dir)})
        workspace = (out / "workspace.md").read_text(encoding="utf-8")
        lines = workspace.splitlines()
        self.assertIn("- cron: 0 3 * * * /usr/local/bin/backup [masked]", lines)
        self.assertIn("- cron: @reboot /usr/local/bin/start", lines)
        self.assertIn("- cron: 0 4 * * * curl -d '{\"[masked]\"}' http://localhost", lines)
        self.assertNotIn("- cron: # a comment", lines)  # a comment is not a job
        self.assertIn("- systemd --user timers: Sat 2026-10-17 03:00:00 UTC 2h left - - backup.timer backup.service", lines)
        for word in (secret, "violet", "kettle"):
            self.assertNotIn(word, workspace)


# ---------------------------------------------------------------------------- how a record is shown

class StampedLog(LogHome):
    """A test over one JSON Lines log of stamped records (see stamped): record i is raw line i + 1, at second i."""

    def read(self, records, name="log.jsonl", **options):
        """Write the records as self.raw, gather it, and return the lines of its transcript below the header."""
        self.raw = jl(self.logs / name, stamped(records))
        self.out = self.gather(**options)
        self.text = transcript_at(self.out, self.raw)
        return body_of(self.text)

    def read_each(self, logs):
        """Write each of these logs (a name, and its records, stamped), gather them together, and return the lines below
        the header of the transcript of each, and the path of each raw log: what a log of one record names is in its
        header, as every fact of a log of one record is, so its lines show none."""
        raws = {name: jl(self.logs / f"{name}.jsonl", stamped(records)) for name, records in logs.items()}
        self.out = self.gather()
        return {name: body_of(transcript_at(self.out, raw)) for name, raw in raws.items()}, raws


class LabelTest(StampedLog):
    """A record is labeled in its own words: the values of its type, role, subtype and kind fields, at its top
    level and down the objects that hold its message, each value once."""

    ORDER = ("message", "payload", "item", "data", "msg", "event")

    def test_a_label_is_the_values_of_the_type_and_role_fields_down_the_objects_that_hold_the_message(self):
        records = [
            {"type": "assistant", "message": {"role": "assistant", "content": "plain reply here"}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "from the payload"}},
            {"type": "attachment", "attachment": {"type": "x", "text": "named by its type"}},
            {"type": "t", "role": "r", "subtype": "s", "kind": "k", "text": "all four keys"},
            {"type": "user", "role": "user", "message": {"role": "user", "type": "user", "content": "said once"}},
            {"note": "nothing here that a label can name"},
            {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "AgentMessage", "content": [
                {"type": "text", "text": "two levels down"}]}}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": "answered in the stream"}]}}]
        lines = self.read(records)
        raw = self.raw
        self.assertEqual(lines, [
            row(raw, 1, "assistant", "plain reply here"),                       # the message repeats the type: said once
            row(raw, 2, "event_msg > user_message", "from the payload"),
            row(raw, 3, "attachment > x", "named by its type"),                 # a type that names a field of the record
            row(raw, 4, "t > r > s > k", "all four keys"),                      # in the order type, role, subtype, kind
            row(raw, 5, "user", "said once"),                                   # on the record and in its message: once
            f"[{shown(5)}] note: (no type or role)  (raw log line 6)",          # nothing to name it by
            row(raw, 7, "event_msg > item_completed > AgentMessage", "two levels down"),
            row(raw, 8, "response_item > message > assistant", "answered in the stream")])

    def test_the_field_a_records_type_names_holds_its_message_before_the_usual_fields_do(self):
        lines = self.read([{"type": "attachment", "message": {"content": "not this one"},
                            "attachment": {"type": "chosen", "content": "this one"}}])
        self.assertEqual(lines, [row(self.raw, 1, "attachment > chosen", "this one")])

    def test_without_one_the_message_is_in_the_first_of_message_payload_item_data_msg_and_event(self):
        # Record i holds the objects from ORDER[i] on, and is shown by the first of them, whatever order it wrote them in.
        records = [{"type": "r", **{name: {"text": f"via {name}"} for name in reversed(self.ORDER[i:])}} for i in range(len(self.ORDER))]
        lines = self.read(records)
        self.assertEqual(lines, [row(self.raw, i + 1, "r", f"via {name}") for i, name in enumerate(self.ORDER)])


class ContentTest(StampedLog):
    """A record's content is shown part by part, each as what it says it is: text, thinking, a tool call, a tool
    result with whether it failed, or an image."""

    IMAGE = "QkFTRTY0LURBVEE" * 20  # what a base64 image looks like in a log: not for a transcript
    LONG_THOUGHT = " ".join(f"w{n:04d}" for n in range(400))  # 2,399 characters; word n is characters 6n to 6n + 4
    LONG_TEXT = " ".join(f"v{n:04d}" for n in range(500))     # 2,999 characters

    def records(self):
        token = "gh" + "p_" + "a" * 30  # assembled at run time: nothing secret-shaped is committed
        return [
            {"type": "user", "message": {"content": "plain string content"}},
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "a text part"}, {"type": "input_text", "text": "an input_text part"},
                {"type": "output_text", "text": "an output_text part"}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "thinking", "thinking": "The failure is in the\nlinker step.", "signature": "c2ln"}]}},
            {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "", "signature": "c2ln"}]}},
            {"type": "assistant", "message": {"content": [{"type": "reasoning", "text": "reasoned about it"}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "toolu_0123456789abcdef", "name": "Bash", "input": {"command": "pytest -q"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "toolu_0123456789abcdef", "is_error": True, "content": "FAILED test_x"}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "toolu_0123456789abcdef",
                 "content": [{"type": "text", "text": "line one"}, {"type": "text", "text": "line two"}]}]}},
            {"type": "user", "message": {"content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": self.IMAGE}},
                {"type": "text", "text": "see this screenshot"}]}},
            {"role": "user", "content": ["first string part", {"type": "text", "text": "second part"}]},
            {"role": "model", "parts": [{"text": "a part with only text"}]},
            {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": self.LONG_THOUGHT}]}},
            {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "a" * 1500 + "b" * 500}]}},
            {"type": "user", "message": {"content": self.LONG_TEXT}},
            {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": f"The token {token} is in the env."}]}}]

    def trimmed(self, text, n):
        return f"{text}... [trimmed; full text at {self.raw}:{n}]"

    def test_each_part_is_shown_as_what_it_says_it_is(self):
        lines = self.read(self.records())
        raw = self.raw
        self.assertEqual(lines[:14], [
            row(raw, 1, "user", "plain string content"),
            row(raw, 2, "assistant", "a text part"),
            row(raw, 2, "assistant", "an input_text part"),                      # text, not a tool result
            row(raw, 2, "assistant", "an output_text part"),
            row(raw, 3, "assistant", "The failure is in the linker step.", "thinking"),
            f"[{shown(3)}] note: assistant  (raw log line 4)",                    # a signature and no thought
            row(raw, 5, "assistant", "reasoned about it", "thinking"),
            row(raw, 6, "assistant", 'Bash({"command": "pytest -q"})', "tool call"),
            row(raw, 7, "user", "FAILED test_x", "tool result (error)"),
            row(raw, 8, "user", "line one line two", "tool result"),
            row(raw, 9, "user", "[image]"),
            row(raw, 9, "user", "see this screenshot"),
            row(raw, 10, "user", "first string part"),
            row(raw, 10, "user", "second part")])
        self.assertEqual(lines[14], row(raw, 11, "model", "a part with only text"))
        self.assertNotIn("QkFTRTY0LURBVEE", self.text)  # an image is named, not dumped

    def test_a_result_part_that_has_an_exit_status_shows_it_first(self):
        lines = self.read([{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "exit_code": 2, "content": "boom"},
            {"type": "tool_result", "tool_use_id": "t2", "status": "ok", "content": "fine"}]}}])
        self.assertEqual(lines, [row(self.raw, 1, "user", "(exit_code 2) boom", "tool result"),
                                 row(self.raw, 1, "user", "(status ok) fine", "tool result")])

    def test_thinking_is_cut_at_1500_characters_and_masked(self):
        lines = self.read(self.records())
        raw = self.raw
        # By hand: the first 1,500 characters of the words are words 0 to 249 (1,499 characters) and the space after.
        self.assertEqual(lines[15], row(raw, 12, "assistant", self.trimmed(" ".join(f"w{n:04d}" for n in range(250)), 12), "thinking"))
        self.assertEqual(lines[16], row(raw, 13, "assistant", self.trimmed("a" * 1500, 13), "thinking"))
        self.assertEqual(lines[18], row(raw, 15, "assistant", "The token [masked] is in the env.", "thinking"))

    def test_other_text_is_cut_at_2000_characters(self):
        lines = self.read(self.records())
        # By hand: 333 words (words 0 to 332) are 1,997 characters, and a space and the two characters "v0" make 2,000.
        self.assertEqual(lines[17], row(self.raw, 14, "user", self.trimmed(" ".join(f"v{n:04d}" for n in range(333)) + " v0", 14)))

    def test_max_chars_cuts_the_text_and_the_thinking_if_it_is_smaller(self):
        lines = self.read(self.records(), extra=["--max-chars", "100"])
        raw = self.raw
        # By hand: 100 characters are words 0 to 15 (95 characters), a space, and the four characters "v001" or "w001".
        self.assertEqual(lines[15], row(raw, 12, "assistant", self.trimmed(" ".join(f"w{n:04d}" for n in range(16)) + " w001", 12), "thinking"))
        self.assertEqual(lines[16], row(raw, 13, "assistant", self.trimmed("a" * 100, 13), "thinking"))
        self.assertEqual(lines[17], row(raw, 14, "user", self.trimmed(" ".join(f"v{n:04d}" for n in range(16)) + " v001", 14)))
        self.assertEqual(lines[0], row(raw, 1, "user", "plain string content"))  # what fits is whole


class HolderShapesTest(StampedLog):
    """What a harness writes beside its messages -- a call with a name and arguments, a command with its output and
    how it ended, lists of calls and of thoughts -- is shown as the tool call, tool result or thinking it is."""

    def test_a_name_with_arguments_an_output_field_and_a_command_are_a_tool_call_and_a_tool_result(self):
        command = "event_msg > item_completed > CommandExecution"
        lines = self.read([
            {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "input": "ls -la /tmp"}},
            {"type": "response_item", "payload": {"type": "function_call_output", "output": "total 0"}},
            {"type": "event_msg", "payload": {"type": "item_completed", "item": {
                "type": "CommandExecution", "command": ["bash", "-lc", "pytest -q"], "status": "completed",
                "exit_code": 1, "aggregated_output": "FAILED test_x"}}},
            {"type": "event_msg", "payload": {"type": "item_completed", "item": {
                "type": "CommandExecution", "command": ["ls"], "status": "failed to start", "aggregated_output": "no such file"}}},
            {"type": "exec_end", "stdout": "out text", "stderr": "err text", "exit_code": 2},
            {"type": "user", "message": {"content": "closing line here"}},
            {"type": "user", "message": {"content": "and another one"}},
            {"type": "user", "message": {"content": "and yet another"}}])
        raw = self.raw
        # By hand: of eight records, a quarter, two, is the most a fact may be on and still be shown on lines; the status
        # of the first is on one. The exit code is the status the line gives when the item has both, so that status is not
        # shown by the line and is a fact; the status of the second is shown by its line, and is not.
        completed = ("status=completed",)
        self.assertEqual(lines[:6], [
            row(raw, 1, "response_item > custom_tool_call", "exec(ls -la /tmp)", "tool call"),
            row(raw, 2, "response_item > function_call_output", "total 0", "tool result"),
            row(raw, 3, command, "bash -lc pytest -q", "tool call", completed),
            row(raw, 3, command, "(exit_code 1) FAILED test_x", "tool result", completed),
            row(raw, 4, command, "ls", "tool call"),
            row(raw, 4, command, "(status failed to start) no such file", "tool result")])
        # Several output fields are all shown, with the exit status first.
        self.assertRegex(lines[6], rf"^\[{re.escape(shown(4))}\] exec_end - tool result: \(exit_code 2\) .*out text.*err text  \({re.escape(str(raw))}:5\)$")

    def test_a_command_given_as_text_and_a_call_with_parameters_are_tool_calls_too(self):
        lines = self.read([{"type": "local_shell_call", "command": "ls -la"},
                           {"type": "exec", "cmd": "echo hi"},
                           {"type": "response_item", "payload": {"type": "function_call", "name": "lookup", "parameters": {"q": "x"}}}])
        raw = self.raw
        self.assertEqual(lines, [row(raw, 1, "local_shell_call", "ls -la", "tool call"), row(raw, 2, "exec", "echo hi", "tool call"),
                                 row(raw, 3, "response_item > function_call", 'lookup({"q": "x"})', "tool call")])

    def test_lists_of_tool_calls_and_of_thoughts_beside_a_message_are_shown_too(self):
        lines = self.read([
            {"type": "gemini", "content": "all done here", "toolCalls": [
                {"name": "run_shell_command", "args": {"command": "pytest -q"}, "status": "error", "result": "boom"}]},
            {"role": "assistant", "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'}}]},
            {"type": "gemini", "content": "thinking out loud now", "thoughts": [
                {"subject": "Plan", "description": "Check the log"}, "a bare thought"]}])
        raw = self.raw
        self.assertEqual(lines, [
            row(raw, 1, "gemini", "all done here"),
            row(raw, 1, "gemini", 'run_shell_command({"command": "pytest -q"})', "tool call"),
            row(raw, 1, "gemini", "(status error) boom", "tool result"),
            row(raw, 2, "assistant", 'get_weather({"city": "Paris"})', "tool call"),   # a call a "function" object wraps
            row(raw, 3, "gemini", "thinking out loud now"),
            row(raw, 3, "gemini", "Plan - Check the log", "thinking"),
            row(raw, 3, "gemini", "a bare thought", "thinking")])

    def test_reasoning_a_record_holds_is_thinking_and_reasoning_with_nothing_readable_is_a_note(self):
        lines = self.read([
            {"type": "response_item", "payload": {"type": "reasoning", "summary": [{"type": "summary_text", "text": "Plan the fix"}]}},
            {"type": "user", "message": {"content": "a line between"}},
            {"type": "response_item", "payload": {"type": "reasoning", "summary": []}}])
        self.assertEqual(lines, [
            row(self.raw, 1, "response_item > reasoning", "Plan the fix", "thinking"),
            row(self.raw, 2, "user", "a line between"),
            f"[{shown(2)}] note: response_item > reasoning  (raw log line 3)"])

    def test_a_record_with_a_message_also_shows_the_command_output_and_exit_status_it_holds(self):
        lines = self.read([
            {"type": "hook_error", "content": "lint failed here", "command": "lint --all", "stdout": "checked 3 files",
             "stderr": "found 2 problems", "exitCode": 1},
            {"type": "build", "content": "built ok", "stdout": "built ok"},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}],
                                              "command": "ls -la"}}])
        raw = self.raw
        # All of them, in order: the message, what ran, what it produced and how it ended.
        self.assertEqual(lines[:2], [row(raw, 1, "hook_error", "lint failed here"), row(raw, 1, "hook_error", "lint --all", "tool call")])
        self.assertRegex(lines[2], rf"^\[{re.escape(shown(0))}\] hook_error - tool result: \(exitCode 1\) .*checked 3 files.*found 2 problems  "
                                   rf"\({re.escape(str(raw))}:1\)$")
        # A text already shown is not shown again, and the call a record holds is not added to one its content has.
        self.assertEqual(lines[3:], [row(raw, 2, "build", "built ok"), row(raw, 3, "assistant", 'Bash({"command": "ls"})', "tool call")])

    def test_a_tool_named_under_tool_tool_name_or_toolname_is_a_tool_call_and_a_server_prefixes_it(self):
        bodies, raws = self.read_each({
            "server": [{"type": "mcp_tool_call", "server": "github", "tool": "create_issue", "arguments": {"title": "x"}}],
            "camel": [{"type": "invoke", "toolName": "Lookup", "args": {"q": "z"}}],
            "snake": [{"type": "invoke", "tool_name": "Fetch", "input": "https://example.test/a"}],
            "name_first": [{"type": "invoke", "name": "first", "tool": "second", "input": {}}]})
        self.assertEqual(bodies["server"], [row(raws["server"], 1, "mcp_tool_call", 'github/create_issue({"title": "x"})', "tool call")])
        self.assertEqual(bodies["camel"], [row(raws["camel"], 1, "invoke", 'Lookup({"q": "z"})', "tool call")])
        self.assertEqual(bodies["snake"], [row(raws["snake"], 1, "invoke", "Fetch(https://example.test/a)", "tool call")])
        self.assertEqual(bodies["name_first"], [row(raws["name_first"], 1, "invoke", "first({})", "tool call")])  # a "name" is the name

    def test_a_result_field_that_is_an_object_or_a_list_with_no_text_in_it_is_shown_as_compact_json(self):
        lines = self.read([
            {"type": "tool_end", "output": {"exit": 0, "files": 3}},
            {"type": "image_end", "output": [{"type": "image", "url": "u"}]},
            {"type": "words_end", "output": {"text": "plain words"}},
            {"type": "empty_end", "output": {}},
            {"type": "nested_end", "result": {"meta": {"count": 3}}},
            {"type": "user", "message": {"content": [{"type": "function_call_output", "call_id": "c1", "output": {"exit": 0}}]}}])
        raw = self.raw
        self.assertEqual(lines, [
            row(raw, 1, "tool_end", '{"exit": 0, "files": 3}', "tool result"),
            row(raw, 2, "image_end", '[{"type": "image", "url": "u"}]', "tool result"),
            row(raw, 3, "words_end", "plain words", "tool result"),                      # one with text in it shows the text
            f"[{shown(3)}] note: empty_end  (raw log line 4)",                           # and one with nothing in it shows nothing
            row(raw, 5, "nested_end", '{"meta": {"count": 3}}', "tool result"),
            row(raw, 6, "user", '{"exit": 0}', "tool result")])                          # in a part, too


class NestedToolTest(StampedLog):
    """Harnesses wrap a tool call, or a result, in objects a level or two down; the wrapper is not what is shown,
    what it holds is."""

    def test_a_tool_call_is_found_in_an_object_nested_up_to_three_levels_under_a_part_or_a_holder(self):
        def part(**fields):
            return {"role": "assistant", "content": [{"type": "toolRequest", **fields}]}
        lines = self.read([
            part(id=uid(1), toolCall={"status": "success", "value": {"name": "shell", "arguments": {"command": "ls -la"}}}),
            part(toolCall={"name": "level_one", "arguments": {"n": 1}}),
            part(outer={"inner": {"name": "level_two", "arguments": {"n": 2}}}),
            part(outer={"middle": {"inner": {"name": "level_three", "arguments": {"n": 3}}}}),
            part(outer={"a": {"b": {"c": {"name": "level_four", "arguments": {"n": 4}}}}}),
            {"type": "response_item", "payload": {"type": "tool_request", "toolCall": {"value": {
                "name": "shell", "arguments": {"command": "pwd"}}}}},
            part(toolCall={"value": {"command": ["git", "status"]}})])
        raw = self.raw
        self.assertEqual(lines, [
            row(raw, 1, "assistant", 'shell({"command": "ls -la"})', "tool call"),
            row(raw, 2, "assistant", 'level_one({"n": 1})', "tool call"),
            row(raw, 3, "assistant", 'level_two({"n": 2})', "tool call"),
            row(raw, 4, "assistant", 'level_three({"n": 3})', "tool call"),         # three levels down: the deepest looked in
            f"[{shown(4)}] note: assistant  (raw log line 5)",                         # four down: not looked in, so nothing to show
            row(raw, 6, "response_item > tool_request", 'shell({"command": "pwd"})', "tool call"),   # in a holder, not a part
            row(raw, 7, "assistant", "git status", "tool call")])

    def test_a_tool_results_text_is_found_wherever_it_is_nested(self):
        def part(**fields):
            return {"role": "user", "content": [{"type": "toolResponse", **fields}]}
        lines = self.read([
            part(id=uid(1), toolResult={"status": "success", "value": [{"type": "text", "text": "file one"}, {"type": "text", "text": "file two"}]}),
            part(toolResult={"a": {"b": {"c": [{"type": "text", "text": "deep text"}]}}}),
            part(isError=True, toolResult={"value": [{"type": "text", "text": "it failed"}]}),
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
                                          "content": {"meta": {"body": [{"type": "text", "text": "found by search"}]}}}]},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": uid(2),
                                                  "output": {"wrapper": {"lines": [{"text": "holder level nested"}]}}}}])
        raw = self.raw
        self.assertEqual(lines, [
            row(raw, 1, "user", "file one file two", "tool result"),
            row(raw, 2, "user", "deep text", "tool result"),
            row(raw, 3, "user", "it failed", "tool result (error)"),
            row(raw, 4, "user", "found by search", "tool result"),
            row(raw, 5, "response_item > function_call_output", "holder level nested", "tool result")])


class FallbackTextTest(StampedLog):
    """A record with no content shows the first of its text, message, prompt, summary and body that is a string,
    except that a summary of one word is a setting, not a summary; beside a list of tool calls or of thoughts too."""

    def test_the_first_text_field_that_is_a_string_is_the_text_and_a_one_word_summary_is_not(self):
        lines = self.read([
            {"type": "user", "message": "continue"},
            {"type": "settings", "summary": "auto"},
            {"type": "summary", "summary": "Fix the build failures"},
            {"type": "prompt", "prompt": "a prompt string"},
            {"type": "body", "body": "a body string"},
            {"type": "both", "message": "the second field", "text": "the first field"},
            {"type": "user", "content": "the content wins", "text": "ignored text"},
            {"type": "user", "content": "", "text": "fallback after empty"}])
        raw = self.raw
        # A one-word message is shown as the line's text, and only there: what a line shows as content is no fact.
        self.assertEqual(lines[0], row(raw, 1, "user", "continue"))
        self.assertEqual(lines[1:], [
            f"[{shown(1)}] note: settings  (raw log line 2)",
            row(raw, 3, "summary", "Fix the build failures"),
            row(raw, 4, "prompt", "a prompt string"),
            row(raw, 5, "body", "a body string"),
            row(raw, 6, "both", "the first field"),
            row(raw, 7, "user", "the content wins"),
            row(raw, 8, "user", "fallback after empty")])

    def test_a_text_field_is_shown_beside_a_list_of_tool_calls_or_of_thoughts(self):
        # "Lists of tool calls and of thoughts beside the message are shown too": the message is shown, and so are they.
        lines = self.read([
            {"type": "assistant", "text": "reviewing the original requirement", "toolCalls": [{"name": "run", "args": {"a": 1}}]},
            {"type": "assistant", "message": "checking the next step", "tool_calls": [{"name": "look", "arguments": {"b": 2}}]},
            {"type": "assistant", "summary": "weighing both options", "thoughts": ["a bare thought"]}])
        raw = self.raw
        self.assertEqual(lines, [
            row(raw, 1, "assistant", "reviewing the original requirement"),
            row(raw, 1, "assistant", 'run({"a": 1})', "tool call"),
            row(raw, 2, "assistant", "checking the next step"),
            row(raw, 2, "assistant", 'look({"b": 2})', "tool call"),
            row(raw, 3, "assistant", "weighing both options"),
            row(raw, 3, "assistant", "a bare thought", "thinking")])

    def test_a_text_field_that_is_a_list_of_text_parts_is_the_text(self):
        image = "QkFTRTY0LURBVEE" * 20  # what a base64 image looks like in a log: not for a transcript
        lines = self.read([
            {"type": "attachment", "attachment": {"type": "queued_command", "prompt": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image}},
                {"type": "text", "text": "see this screenshot"}, {"type": "text", "text": "and this one"}]}},
            {"type": "report", "body": [{"text": "a body"}, {"text": "of parts"}]},
            {"type": "digest", "summary": [{"text": "one"}]},                                  # a summary of one word is none
            {"type": "gallery", "prompt": [{"type": "image", "source": {"type": "base64", "data": "AAAA"}}]}])  # and no text is none
        raw = self.raw
        self.assertEqual(lines, [
            row(raw, 1, "attachment > queued_command", "see this screenshot and this one"),
            row(raw, 2, "report", "a body of parts"),
            f"[{shown(2)}] note: digest, gallery through {shown(3)}  (raw log lines 3-4)"])
        self.assertNotIn(image, self.text)


# ---------------------------------------------------------------------------- facts, repetition, and what the index counts

class FactsTest(StampedLog):
    """A record's short facts -- a flag, a branch, an origin's kind -- are on its line if few records of its file carry
    them, and named once in the transcript's header if most do. An identifier, or a flag that is not set, is no fact."""

    def record(self, i, kind, text, **more):
        base = {"type": kind, "version": "2.0.1", "gitBranch": "main", "isSidechain": False, "uuid": uid(100 + i),
                "parentUuid": uid(99 + i) if i else None, "sessionId": uid(1), "message": {"role": kind, "content": text}}
        return {**base, **more}

    def setUp(self):
        super().setUp()
        record = self.record
        self.lines = self.read([
            record(0, "user", "first question here"),
            record(1, "assistant", "the answer one", requestId="req_" + "011CVx3Rk9mQ2vDzX7bR4sT1pL8n", build="a1b2c3d4e5f6a7b8c9d0",
                   seq=1234567, pid="12345678"),
            record(2, "user", "a meta note here", isMeta=True),
            record(3, "assistant", "the answer two"),
            record(4, "user", "a branch that differs", gitBranch="topic"),
            record(5, "assistant", "the answer three"),
            record(6, "user", "a peers words here", isMeta=True, origin={"kind": "peer"}),
            record(7, "assistant", "the answer four")])

    def test_a_fact_few_records_carry_is_on_their_lines_and_what_most_share_is_named_once_in_the_header(self):
        raw = self.raw
        # By hand: of eight records, the version and the branch main are on seven or eight, which is most, so the
        # header has them (by name, in order) and no line does; a fact is on lines if it is on a quarter of the
        # records or fewer (two): the meta flag is on two, the other branch and the origin's kind on one each.
        self.assertEqual(self.text.splitlines()[6], "most records carry: gitBranch=main, version=2.0.1  ")
        self.assertEqual(self.lines, [
            row(raw, 1, "user", "first question here"),
            row(raw, 2, "assistant", "the answer one"),
            row(raw, 3, "user", "a meta note here", facts=("isMeta",)),
            row(raw, 4, "assistant", "the answer two"),
            row(raw, 5, "user", "a branch that differs", facts=("gitBranch=topic",)),
            row(raw, 6, "assistant", "the answer three"),
            row(raw, 7, "user", "a peers words here", facts=("isMeta", "origin.kind=peer")),   # a small object's field, in the record's order
            row(raw, 8, "assistant", "the answer four")])

    def test_a_flag_that_is_not_set_and_identifiers_are_never_facts(self):
        # Each of these is on one record or on all of them, and none is shown or named: a false flag says what its
        # absence says; a UUID, a token-shaped request id, a long hex id or a long number is an identifier.
        for fragment in ("isSidechain", "uuid", "parentUuid", "sessionId", "requestId", "build", "pid", "seq", "req_011CVx",
                         "a1b2c3d4e5f6a7b8c9d0", "12345678", "1234567", uid(1), uid(100)):
            self.assertNotIn(fragment, "\n".join(self.lines) + "\n" + self.text.splitlines()[6], fragment)

    def test_a_flag_that_is_set_on_most_records_is_named_once_by_the_header(self):
        lines = self.read([{"type": "user", "isSidechain": True, "message": {"content": "sub task text"}},
                           {"type": "assistant", "isSidechain": True, "message": {"content": "on it now"}},
                           {"type": "user", "message": {"content": "a record outside it"}},
                           {"type": "assistant", "isSidechain": True, "message": {"content": "done here"}}], name="sidechain.jsonl")
        self.assertEqual(self.text.splitlines()[6], "most records carry: isSidechain=true  ")
        self.assertEqual(lines, [row(self.raw, 1, "user", "sub task text"), row(self.raw, 2, "assistant", "on it now"),
                                 row(self.raw, 3, "user", "a record outside it"), row(self.raw, 4, "assistant", "done here")])

    def test_a_set_flag_is_on_every_line_it_is_set_on_unless_most_records_share_it(self):
        words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet", "kilo", "lima"]
        meta, sidechain, topic, model = {0, 3, 6, 9}, {1, 3, 5, 7, 9, 11}, {4, 5, 10, 11}, {2, 8}
        records = []
        for i, word in enumerate(words):
            record = {"type": "user" if i % 2 == 0 else "assistant", "message": {"content": f"{word} speaks"}}
            record.update({**({"isMeta": True} if i in meta else {}), **({"isSidechain": True} if i in sidechain else {}),
                           **({"gitBranch": "topic"} if i in topic else {}), **({"model": "m1"} if i in model else {})})
            records.append(record)
        lines = self.read(records, name="flags.jsonl")
        # By hand: of twelve records, a value may be on three or fewer to be on their lines, and on six or more to be in
        # the header. The meta flag is on four, which is neither: it is a flag, and a flag is on its lines; the branch is
        # on four, which is neither, and a value is nowhere. The sidechain flag is on six, so the header has it and no
        # line does; the model is on two, so their lines have it.
        self.assertEqual(self.text.splitlines()[6], "most records carry: isSidechain=true  ")
        self.assertEqual(lines, [
            row(self.raw, i + 1, "user" if i % 2 == 0 else "assistant", f"{word} speaks",
                facts=(*(("isMeta",) if i in meta else ()), *(("model=m1",) if i in model else ())))
            for i, word in enumerate(words)])


def repeating_records():
    """31 records: reminders that repeat, a call repeated beside other lines of its label and one repeated alone, and notes."""
    tool_call = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}}
    poll = {"type": "poller", "message": {"content": [{"type": "tool_use", "name": "Check", "input": {"id": 7}}]}}
    return [
        {"type": "user", "message": {"content": "start of the run"}},                                                       # 0
        *[{"type": "attachment", "attachment": {"type": "token_reminder", "text": f"tokens left: {left}"}}
          for left in (1000, 900, 800, 700, 600)],                                                                           # 1-5
        {"type": "system", "message": {"content": "five reminders passed"}},                                                # 6
        *[{"type": "attachment", "attachment": {"type": "cost_reminder", "text": f"cost so far: ${cost}"}}
          for cost in (10, 20, 30, 40)],                                                                                     # 7-10
        *[{"type": "attachment", "attachment": {"type": "skill_listing", "text": f"listing of {name}"}}
          for name in ("alpha", "beta", "gamma", "delta", "epsilon")],                                                       # 11-15
        {"type": "assistant", "message": {"content": "done here"}},                                                         # 16
        *[tool_call] * 5,                                                                                                    # 17-21
        {"type": "user", "message": {"content": "between two runs"}},                                                       # 22
        *[poll] * 5,                                                                                                         # 23-27
        *[{"type": "progress"}] * 2,                                                                                         # 28-29
        {"type": "user", "message": {"content": "the end"}}]                                                                 # 30


class RepetitionTest(StampedLog):
    """A label whose records all say the same plain text, but for digits, with the same facts, five times or more is a
    reminder the harness repeats: it is counted in a note, not written out each time. Four times, or different words, or
    different facts stay lines; so does a call, a result or reasoning, and so do a user's words."""

    def test_five_repeats_but_for_digits_are_one_counted_note_and_fewer_or_different_ones_stay_lines(self):
        lines = self.read(repeating_records())
        raw = self.raw
        self.assertEqual(lines, [
            row(raw, 1, "user", "start of the run"),
            f"[{shown(1)}] note: attachment > token_reminder: tokens left: # x5 through {shown(5)}  (raw log lines 2-6)",   # five, but for their digits, and what they say is kept
            row(raw, 7, "system", "five reminders passed"),
            *[row(raw, 8 + k, "attachment > cost_reminder", f"cost so far: ${cost}") for k, cost in enumerate((10, 20, 30, 40))],  # four
            *[row(raw, 12 + k, "attachment > skill_listing", f"listing of {name}")
              for k, name in enumerate(("alpha", "beta", "gamma", "delta", "epsilon"))],                           # five, in different words
            row(raw, 17, "assistant", "done here"),
            # The same call five times stays lines, each saying it is the line before's: beside another line of its label,
            row(raw, 18, "assistant", 'Bash({"command": "ls"})', "tool call"),
            *[row(raw, 19 + k, "assistant", "(the same text as the line before)", "tool call") for k in range(4)],
            row(raw, 23, "user", "between two runs"),
            # and alone: a call is never folded.
            row(raw, 24, "poller", 'Check({"id": 7})', "tool call"),
            *[row(raw, 25 + k, "poller", "(the same text as the line before)", "tool call") for k in range(4)],
            f"[{shown(28)}] note: progress x2 through {shown(29)}  (raw log lines 29-30)",
            row(raw, 31, "user", "the end")])

    def test_what_a_note_stands_for_is_not_counted_as_text_or_tool_calls(self):
        self.read(repeating_records())
        # By hand: 3 user lines; the system line, four costs, five listings and "done here" are other text; the ten
        # calls, five beside "done here" and five a poller made, are tool calls; the reminders and the two progress
        # records are in notes, and a note is none of them.
        self.assertEqual(cells_of(self.out, self.raw.stem)[5:9], ["31", "3", "11", "10"])

    def test_a_record_of_several_plain_texts_repeats_whole_and_its_note_keeps_them_joined_by_semicolons(self):
        def step(i):
            return {"type": "assistant", "message": {"content": [
                {"type": "text", "text": f"checking file {i}"}, {"type": "text", "text": "then the next one"}]}}
        lines = self.read([{"type": "user", "message": {"content": "start"}}, *[step(i) for i in range(5)],
                           {"type": "user", "message": {"content": "end"}}])
        raw = self.raw
        # Five records of two pieces each, the same but for their digits: each becomes a note, and as they are in a row
        # they are one line, counted. The note says what they said, the pieces joined by "; ".
        self.assertEqual(lines, [
            row(raw, 1, "user", "start"),
            f"[{shown(1)}] note: assistant: checking file #; then the next one x5 through {shown(5)}  (raw log lines 2-6)",
            row(raw, 7, "user", "end")])

    def test_a_record_with_a_tool_call_is_never_folded(self):
        lines = self.read([{"type": "assistant", "message": {"content": [
            {"type": "text", "text": f"checking file {i}"}, {"type": "tool_use", "name": "Bash", "input": {"command": f"ls {i}"}}]}}
            for i in range(5)])
        # Five records of a text and a call, the same but for their digits: ten lines, for nothing a call holds is dropped.
        self.assertEqual(lines, [line for i in range(5) for line in (
            row(self.raw, i + 1, "assistant", f"checking file {i}"),
            row(self.raw, i + 1, "assistant", f'Bash({{"command": "ls {i}"}})', "tool call"))])

    def test_a_record_of_thinking_is_never_folded(self):
        lines = self.read([{"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": f"weighing option {i}"}]}}
                           for i in range(5)])
        self.assertEqual(lines, [row(self.raw, i + 1, "assistant", f"weighing option {i}", "thinking") for i in range(5)])

    def test_a_record_with_a_tool_result_is_never_folded(self):
        # A text and a result with an exit code, five times, the same but for the digits of the code: ten lines.
        lines = self.read([{"type": "assistant", "content": "checking step", "stdout": "done", "exitCode": i} for i in range(5)])
        self.assertEqual(lines, [line for i in range(5) for line in (
            row(self.raw, i + 1, "assistant", "checking step"), row(self.raw, i + 1, "assistant", f"(exitCode {i}) done", "tool result"))])

    def test_the_exit_codes_and_the_flag_of_results_that_are_alike_but_for_them_are_still_to_read(self):
        # The same, with a flag on the third: ten lines, with the exit codes, and the flag on the lines of the record.
        lines = self.read([{"type": "assistant", "content": "checking step", "stdout": "done", "exitCode": i,
                            **({"isMeta": True} if i == 2 else {})} for i in range(5)])
        self.assertEqual(lines, [line for i in range(5) for line in (
            row(self.raw, i + 1, "assistant", "checking step", facts=("isMeta",) if i == 2 else ()),
            row(self.raw, i + 1, "assistant", f"(exitCode {i}) done", "tool result", ("isMeta",) if i == 2 else ()))])

    def test_a_label_with_a_call_among_its_records_is_not_folded_though_five_of_its_records_are_alike(self):
        lines = self.read([*[{"type": "attachment", "attachment": {"type": "token_reminder", "text": f"tokens left: {left}"}}
                             for left in (500, 400, 300, 200, 100)],
                           {"type": "attachment", "attachment": {"type": "token_reminder", "name": "Check", "input": {"id": 1}}}])
        # "A label whose every record shows the same plain text": the sixth shows a call, so the label does not.
        self.assertEqual(lines, [
            *[row(self.raw, i + 1, "attachment > token_reminder", f"tokens left: {left}") for i, left in enumerate((500, 400, 300, 200, 100))],
            row(self.raw, 6, "attachment > token_reminder", 'Check({"id": 1})', "tool call")])

    def test_records_are_folded_only_if_their_facts_are_the_same(self):
        def ping(i, **more):
            return {"type": "attachment", "attachment": {"type": "ping", "text": f"ping {i}"}, **more}
        talk = [{"type": "user", "message": {"content": f"{word} speaks"}}
                for word in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf")]
        bodies, raws = self.read_each({"same": [ping(i, isMeta=True) for i in range(5)] + talk,
                                       "differ": [ping(0), ping(1), ping(2, isMeta=True), ping(3), ping(4)] + talk})
        speaking = lambda raw: [row(raw, 6 + k, "user", f"{word} speaks") for k, word in enumerate(
            ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf"))]
        # By hand: of twelve records, a flag on five is on their lines, not in the header (that is for six or more). Five
        # records with the same flag are a reminder, and one note; one flag on the third makes the five differ.
        self.assertEqual(bodies["same"], [f"[{shown(0)}] note: attachment > ping: ping # x5 through {shown(4)}  (raw log lines 1-5)",
                                          *speaking(raws["same"])])
        self.assertEqual(bodies["differ"], [row(raws["differ"], i + 1, "attachment > ping", f"ping {i}", facts=("isMeta",) if i == 2 else ())
                                            for i in range(5)] + speaking(raws["differ"]))

    def test_a_label_is_folded_only_if_every_one_of_its_records_shows_the_same(self):
        lines = self.read([*[{"type": "worker", "message": {"content": f"step {i}"}} for i in range(5)],
                           {"type": "worker", "message": {"content": "finished early"}}])
        self.assertEqual(lines, [*[row(self.raw, i + 1, "worker", f"step {i}") for i in range(5)],
                                 row(self.raw, 6, "worker", "finished early")])

    def test_a_users_words_are_never_folded_however_often_they_are_repeated(self):
        def codex(text):
            return {"type": "event_msg", "payload": {"type": "item_completed", "item": {
                "type": "UserMessage", "content": [{"type": "text", "text": text}]}}}
        lines = self.read([*[{"type": "user", "message": {"content": "continue"}}] * 5,
                           *[{"role": "human", "content": f"go on {i}"} for i in range(5)],
                           *[codex("Fix it")] * 5])
        raw, codex_label = self.raw, "event_msg > item_completed > UserMessage"
        self.assertEqual(lines, [
            row(raw, 1, "user", "continue"), *[row(raw, n, "user", "(the same text as the line before)") for n in range(2, 6)],
            *[row(raw, 6 + i, "human", f"go on {i}") for i in range(5)],
            row(raw, 11, codex_label, "Fix it"), *[row(raw, n, codex_label, "(the same text as the line before)") for n in range(12, 16)]])
        self.assertEqual(cells_of(self.out, "log")[5:9], ["15", "15", "0", "0"])   # every one of them is a user's line

    def test_a_folded_note_is_cut_at_160_characters(self):
        lines = self.read([{"type": "attachment", "attachment": {"type": "long", "text": "word " * 80 + str(i)}} for i in range(5)])
        # By hand: the label and ": " are 19 characters, and the words, with their digit as #, give 141 more.
        kept = "attachment > long: " + "word " * 28 + "w" + "..."
        self.assertEqual(lines, [f"[{shown(0)}] note: {kept} x5 through {shown(4)}  (raw log lines 1-5)"])

    def test_each_folded_record_is_a_note_at_its_own_place(self):
        def ping(i):
            return {"type": "attachment", "attachment": {"type": "ping", "text": f"ping {i}"}}
        replies = ["reply one", "reply two", "reply three", "reply four"]
        lines = self.read([ping(0), *[r for i, reply in enumerate(replies) for r in ({"type": "user", "message": {"content": reply}}, ping(i + 1))]])
        raw = self.raw
        self.assertEqual(lines, [
            f"[{shown(0)}] note: attachment > ping: ping #  (raw log line 1)",
            row(raw, 2, "user", "reply one"), f"[{shown(2)}] note: attachment > ping: ping #  (raw log line 3)",
            row(raw, 4, "user", "reply two"), f"[{shown(4)}] note: attachment > ping: ping #  (raw log line 5)",
            row(raw, 6, "user", "reply three"), f"[{shown(6)}] note: attachment > ping: ping #  (raw log line 7)",
            row(raw, 8, "user", "reply four"), f"[{shown(8)}] note: attachment > ping: ping #  (raw log line 9)"])


class SameTextTest(StampedLog):
    """A line whose text is that of the line before it (a harness that logs a message twice, under two record types)
    says so, and still has its own place in the raw log; a note or another kind of piece in between makes it new."""

    def test_a_line_that_repeats_the_line_before_says_so_with_its_own_raw_position(self):
        lines = self.read([
            {"type": "user", "message": {"content": "Please fix the build"}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "Please fix the build"}},
            {"type": "assistant", "message": {"content": "Looking now"}},
            {"type": "progress"},
            {"type": "assistant", "message": {"content": "Looking now"}},
            {"type": "assistant", "message": {"content": "Looking now"}},
            {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "Looking now"}]}}])
        raw = self.raw
        self.assertEqual(lines, [
            row(raw, 1, "user", "Please fix the build"),
            row(raw, 2, "event_msg > user_message", "(the same text as the line before)"),
            row(raw, 3, "assistant", "Looking now"),
            f"[{shown(3)}] note: progress  (raw log line 4)",
            row(raw, 5, "assistant", "Looking now"),                              # a note came between: not the line before's
            row(raw, 6, "assistant", "(the same text as the line before)"),
            row(raw, 7, "assistant", "Looking now", "thinking")])                  # the same words, but thinking, not text


class IndexCountsTest(StampedLog):
    """The index counts each session's records, the text lines of its transcript from records whose label names a user
    or a human and from the others, and its tool calls: thinking, tool results and notes are none of them."""

    def test_the_counts_are_those_of_the_lines_of_the_transcript(self):
        lines = self.read([
            {"type": "user", "message": {"content": "first user words"}},
            {"role": "human", "content": "human words here"},
            {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "UserMessage", "content": [
                {"type": "text", "text": "codex style user"}]}}},
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "assistant words"},
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                {"type": "tool_use", "name": "Read", "input": {"path": "a.txt"}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "a.txt"}]}},
            {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "weighing options"}]}},
            {"type": "system", "message": {"content": "system words"}},
            {"type": "progress"}])
        raw = self.raw
        self.assertEqual(lines, [
            row(raw, 1, "user", "first user words"),
            row(raw, 2, "human", "human words here"),
            row(raw, 3, "event_msg > item_completed > UserMessage", "codex style user"),   # a label that names a user, in any case
            row(raw, 4, "assistant", "assistant words"),
            row(raw, 4, "assistant", 'Bash({"command": "ls"})', "tool call"),
            row(raw, 4, "assistant", 'Read({"path": "a.txt"})', "tool call"),
            row(raw, 5, "user", "a.txt", "tool result"),
            row(raw, 6, "assistant", "weighing options", "thinking"),
            row(raw, 7, "system", "system words"),
            f"[{shown(7)}] note: progress  (raw log line 8)"])
        # records, user-role text, other text, tool calls: 8 records; three user lines; "assistant words" and "system words"; two calls
        self.assertEqual(cells_of(self.out, "log")[5:9], ["8", "3", "2", "2"])


class ShortIdTest(StampedLog):
    """A field named as an identifier is no fact however short its value: every record has its own, and as a fact it
    would sit on every line."""

    def test_a_short_id_is_on_no_line(self):
        words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]  # distinct, not alike but for digits
        lines = self.read([{"type": "user", "id": f"m{i}", "toolUseId": f"t{i}", "message_id": f"x{i}",
                            "message": {"role": "user", "content": f"{word} speaks"}} for i, word in enumerate(words, 1)])
        self.assertEqual(lines, [row(self.raw, i, "user", f"{word} speaks") for i, word in enumerate(words, 1)])


class ListedNamesTest(StampedLog):
    """A record with no content shows the names it lists: the paths of the instruction files that reached an agent, the
    names of the skills it was given, not their text."""

    def test_a_record_with_nothing_else_shows_the_names_it_lists(self):
        lines = self.read([
            {"type": "attachment", "attachment": {"type": "instructions", "files": [
                {"path": "/srv/a/CLAUDE.md", "type": "User", "content": "BODY-NOT-WANTED"}, {"path": "/srv/a/AGENTS.md", "type": "Project"}]}},
            {"type": "attachment", "attachment": {"type": "invoked_skills", "skills": [
                {"name": "demo-skill", "content": "SKILL-BODY-NOT-WANTED"}, {"name": "other-skill"}]}},
            {"type": "attachment", "attachment": {"type": "skill_listing", "names": ["alpha", "beta", "gamma"],
                                                  "titles": [{"title": "T1"}, {"title": "T2"}], "skillCount": 3}},
            {"type": "attachment", "attachment": {"type": "opened", "tabs": [{"file": "a.txt"}, {"name": "b"}, {"x": 1}]}},
            {"type": "attachment", "attachment": {"type": "skill_listing", "names": ["a", "b"], "content": "the listing text"}},
            {"type": "attachment", "attachment": {"type": "empty", "names": [], "counts": [1, 2], "long": ["x" * 301]}}])
        raw = self.raw
        self.assertEqual(lines, [
            row(raw, 1, "attachment > instructions", "files: /srv/a/CLAUDE.md, /srv/a/AGENTS.md"),
            row(raw, 2, "attachment > invoked_skills", "skills: demo-skill, other-skill"),
            row(raw, 3, "attachment > skill_listing", "names: alpha, beta, gamma | titles: T1, T2"),   # several lists, joined by " | "
            row(raw, 4, "attachment > opened", "tabs: a.txt, b"),
            row(raw, 5, "attachment > skill_listing", "the listing text"),                           # content is what it shows, not the names
            f"[{shown(5)}] note: attachment > empty  (raw log line 6)"])                            # an empty list, numbers, a long string: none
        self.assertNotIn("NOT-WANTED", self.text)

    def test_each_element_of_a_list_is_a_name_on_its_own_whatever_the_others_are(self):
        lines = self.read([
            {"type": "attachment", "attachment": {"type": "instructions", "files": ["/srv/AGENTS.md", {"path": "/srv/CLAUDE.md"}]}},
            {"type": "attachment", "attachment": {"type": "instructions", "files": [{"path": "/srv/CLAUDE.md"}, "/srv/AGENTS.md"]}},
            {"type": "attachment", "attachment": {"type": "opened", "tabs": [
                {"file": "a.txt"}, "b.txt", {"x": 1}, 3, {"title": "T"}, None, {"name": "n"}]}}])
        raw = self.raw
        # By hand: a string is a name, and so is an object's path, name, title or file; a number, a null and an object
        # with none of them are none.
        self.assertEqual(lines, [
            row(raw, 1, "attachment > instructions", "files: /srv/AGENTS.md, /srv/CLAUDE.md"),
            row(raw, 2, "attachment > instructions", "files: /srv/CLAUDE.md, /srv/AGENTS.md"),
            row(raw, 3, "attachment > opened", "tabs: a.txt, b.txt, T, n")])


class OperationTest(LogHome):
    """A record that is one operation ("$set", "$rewindTo"), with no type, role, subtype or kind, is labeled by its one
    field and shows that field's whole value: a string as it is, anything else as compact JSON."""

    def test_a_record_that_is_one_operation_is_labeled_by_its_field_and_shows_its_value(self):
        raw = jl(self.logs / "ops.jsonl", [
            {"$set": {"lastUpdated": "2026-09-29T00:00:04Z"}},
            {"$rewindTo": "m2"},
            {"$push": {"messages": [1, 2]}},
            {"op": 7},
            {"$set": {"n": 1}, "x": 2},          # two fields: no operation
            {"$clear": ""}])                      # nothing to show
        out = self.gather()
        text = transcript_at(out, raw)
        lines = body_of(text)
        self.assertEqual(lines, [
            f'[2026-09-29T00:00:04+00:00] $set: {{"lastUpdated": "2026-09-29T00:00:04Z"}}  ({raw}:1)',
            f"[] $rewindTo: m2  ({raw}:2)",                                                  # what the line shows is no fact
            f'[] $push: {{"messages": [1, 2]}}  ({raw}:3)', f"[] op: 7  ({raw}:4)",
            "[] note: (no type or role), $clear  (raw log lines 5-6)"])
        self.assertEqual(header_of(text)[7], 'first record: $set {"$set": {"lastUpdated": "2026-09-29T00:00:04Z"}}')
        self.assertEqual(cells_of(out, "ops")[2:9], ["2026-09-29T00:00:04+00:00", "2026-09-29T00:00:04+00:00", "", "6", "0", "4", "0"])

    def test_the_whole_value_of_the_one_field_is_shown_and_never_read_as_a_call_a_message_or_facts(self):
        # The value is what the record says, and what it holds -- a command, a model, a flag; a name and a text -- is no
        # call, no message and no fact: "$set" is an operation on a document, whatever the document is made of.
        raw = jl(self.logs / "whole.jsonl", [
            {"$set": {"command": "echo sample", "model": "chosen-model", "enabled": False}},
            {"$push": [{"name": "demo", "text": "important message"}]}])
        text = transcript_at(self.gather(), raw)
        self.assertEqual(body_of(text), [
            f'[] $set: {{"command": "echo sample", "model": "chosen-model", "enabled": false}}  ({raw}:1)',
            f'[] $push: [{{"name": "demo", "text": "important message"}}]  ({raw}:2)'])
        self.assertEqual(header_of(text)[6], "most records carry: (nothing in common)  ")


class HeaderTest(LogHome):
    """The header of a transcript names the first record: its label, and its short values to four levels deep as JSON
    (a session's own metadata: its id, its origin, the thread that started it), masked and cut like any text."""

    def first_record(self, record, **options):
        """The header's line of the first record, in a log whose first two lines are no record, then this one, and a later one."""
        raw = self.logs / "first.jsonl"
        raw.write_text("\n".join(["not a record", "[1]", json.dumps(record),
                                  json.dumps({"timestamp": at(9), "type": "user", "message": {"content": "later"}})]) + "\n")
        self.raw = raw
        return header_of(transcript_at(self.gather(**options), raw))[7]

    def test_it_holds_the_first_records_short_values_to_four_levels_as_json_masked(self):
        payload = {"id": "thread-abc", "cwd": "/srv/x", "originator": "cli",
                   "source": {"kind": "exec", "parent": {"id": "p-1", "depth": 2, "deeper": {"k": 1, "five": {"x": "too deep"}}}},
                   "flag": True, "off": False, "ratio": 1.5, "auth": "Bear" + "er abc123def456ghi", "edge": "y" * 200,
                   "long": "x" * 201, "multi": "line one\nline two", "none": None, "list": [1, 2], "empty": "", "nothing": {},
                   "hollow": {"none": None, "list": [3]}}
        line = self.first_record({"timestamp": at(0), "type": "session_meta", "payload": payload})
        # By hand, in the order of the record, as json.dumps writes them: its strings of 200 characters or fewer on one
        # line (its time is one), its numbers and its flags, the false one too; not the string of 201, the one with a
        # line break, the empty one, the null or the list; no object left empty by that, the one that was empty or the
        # one that held only those; nothing from the fifth level of objects down (the payload is the first); and a
        # credential masked.
        self.assertEqual(
            line,
            'first record: session_meta {"timestamp": "' + at(0) + '", "type": "session_meta", "payload": {"id": "thread-abc", '
            '"cwd": "/srv/x", "originator": "cli", "source": {"kind": "exec", "parent": {"id": "p-1", "depth": 2, '
            '"deeper": {"k": 1}}}, "flag": true, "off": false, "ratio": 1.5, "auth": "[masked]", "edge": "' + "y" * 200 + '"}}')

    def test_text_that_is_not_ascii_is_written_as_it_is_and_a_quote_as_json_escapes_it(self):
        line = self.first_record({"timestamp": at(0), "type": "session_meta", "payload": {"title": "café → ✓ 日本語", "quote": 'say "hi"'}})
        self.assertEqual(line, 'first record: session_meta {"timestamp": "' + at(0) + '", "type": "session_meta", '
                         '"payload": {"title": "café → ✓ 日本語", "quote": "say \\"hi\\""}}')

    def test_a_credential_phrase_in_the_first_record_is_masked_whole_and_no_word_of_it_is_written(self):
        phrase = " ".join(("correct", "horse", "battery", "staple"))
        line = self.first_record({"timestamp": at(0), "type": "session_meta", "payload": {"id": "thread-abc", "password": phrase}})
        for path, text in written(self.root / "out1"):
            for word in phrase.split():
                self.assertNotIn(word, text, path.name)
        # The pair is masked as the masker masks a quoted credential, whole, whatever the words in it are.
        self.assertEqual(line, 'first record: session_meta {"timestamp": "' + at(0) + '", "type": "session_meta", '
                         '"payload": {"id": "thread-abc", "[masked]"}}')

    def test_it_has_no_cap_on_how_many_values_it_holds(self):
        line = self.first_record({"type": "meta", **{f"k{i:02d}": i for i in range(60)}})
        self.assertEqual(line, 'first record: meta {"type": "meta", ' + ", ".join(f'"k{i:02d}": {i}' for i in range(60)) + "}")

    def test_it_is_cut_at_max_chars_with_the_trimmed_marker_like_the_text_below_it(self):
        records = {"type": "meta", **{f"k{i:02d}": i for i in range(60)}}
        # By hand: `{"type": "meta", ` is 17 characters and each of the entries `"k00": 0, ` 10, so 100 characters are the
        # entries k00 to k07 and the three characters `"k0` of the next.
        self.assertEqual(self.first_record(records, extra=["--max-chars", "100"]),
                         'first record: meta {"type": "meta", ' + "".join(f'"k{i:02d}": {i}, ' for i in range(8)) + '"k0'
                         + f"... [trimmed; full text at {self.raw}:3]")

    def test_with_five_characters_the_first_record_is_cut_like_the_text_of_the_line(self):
        raw = jl(self.logs / "short.jsonl", [{"timestamp": at(0), "type": "user", "message": {"content": "hello world"}}])
        document = write_json(self.logs / "short.json", {"messages": [{"timestamp": at(0), "type": "user", "content": "hello world"}]})
        out = self.gather(extra=["--max-chars", "5"])
        # (The first five characters of the JSON, which begins with the record's time, are `{"tim`.)
        text = transcript_at(out, raw)
        self.assertEqual(header_of(text)[7], f'first record: user {{"tim... [trimmed; full text at {raw}:1]')
        self.assertEqual(body_of(text), [f"[{shown(0)}] user: hello... [trimmed; full text at {raw}:1]  ({raw}:1)"])
        # In a JSON document the record is pointed to by its number, in the line and in the header alike.
        text = transcript_at(out, document)
        self.assertEqual(header_of(text)[7], f'first record: user {{"tim... [trimmed; full text at {document} record 1]')
        self.assertEqual(body_of(text), [f"[{shown(0)}] user: hello... [trimmed; full text at {document} record 1]  ({document} record 1)"])

    def test_a_log_with_no_record_has_none(self):
        raw = self.logs / "none.jsonl"
        raw.write_text("not a record\n[1]\n")
        text = transcript_at(self.gather(), raw)
        self.assertEqual(header_of(text)[5:8], ["records: 0  ", "most records carry: (nothing in common)  ", "first record: (none)"])


class DocumentedEdgesTest(StampedLog):
    """Edges of the documentation that gather.py once departed from, each the documentation's sentence worked out on a
    small log: what a line shows is no fact, and what no line shows is; a labeled record of one field is a note, lists
    beside a message are not listed again, and a result with no text in it is shown as it is."""

    def test_a_record_with_a_label_and_one_field_is_a_note_not_a_line(self):
        # "A record with none of these is a note naming its label." A single field is shown as a value only for "a record
        # with none of" type, role, subtype and kind ("an operation such as $set"); {"type": "progress"} has one.
        raw = jl(self.logs / "one.jsonl", [{"type": "progress"}, {"message": {"role": "user"}}])
        self.assertEqual(body_of(transcript_at(self.gather(), raw)), ["[] note: progress, user  (raw log lines 1-2)"])

    def test_the_value_of_a_single_field_operation_is_what_the_line_shows_so_it_is_no_fact(self):
        # "An identifier ... and what the line shows as content are never facts."
        raw = jl(self.logs / "ops.jsonl", [{"$rewindTo": "m2"}, {"$rewindTo": "m3"}, {"$rewindTo": "m4"}, {"$rewindTo": "m5"}])
        self.assertEqual(body_of(transcript_at(self.gather(), raw)), [f"[] $rewindTo: m{i + 2}  ({raw}:{i + 1})" for i in range(4)])

    def test_the_tool_and_the_server_a_call_names_are_what_the_line_shows_so_they_are_no_facts(self):
        # The same sentence.
        calls = [("github", "create_issue"), ("gitlab", "open_pr"), ("slack", "post"), ("jira", "link")]
        lines = self.read([{"type": "mcp_tool_call", "server": server, "tool": tool, "arguments": {"n": i}}
                           for i, (server, tool) in enumerate(calls)])
        self.assertEqual(lines, [row(self.raw, i + 1, "mcp_tool_call", f'{server}/{tool}({{"n": {i}}})', "tool call")
                                 for i, (server, tool) in enumerate(calls)])

    def test_the_output_and_the_status_a_result_shows_are_what_the_line_shows_so_they_are_no_facts(self):
        # The same sentence.
        results = [("boom", "failed"), ("crash", "killed"), ("oops", "stopped"), ("fatal", "aborted")]
        lines = self.read([{"type": "exec_end", "stderr": stderr, "status": status} for stderr, status in results])
        self.assertEqual(lines, [row(self.raw, i + 1, "exec_end", f"(status {status}) {stderr}", "tool result")
                                 for i, (stderr, status) in enumerate(results)])

    def test_a_status_that_no_result_line_shows_is_a_fact(self):
        # Facts are "short values it carries besides its content" and "what the line shows as content are never facts". A
        # status is shown by a result line, and a record whose output is a line break, an empty list or an empty string
        # has none: its status is shown by nothing, so it is a fact.
        others = [{"type": "user", "message": {"content": "first of the others"}},
                  {"type": "assistant", "message": {"content": "second of the others"}},
                  {"type": "user", "message": {"content": "third of the others"}}]
        bodies, raws = self.read_each({
            "blank": [{"type": "exec_end", "content": "command finished", "stdout": "\n", "status": "failed"}, *others],
            "empty": [{"type": "exec_end", "content": "command stopped", "output": [], "stderr": "", "status": "killed"}, *others]})
        for name, text, status in (("blank", "command finished", "failed"), ("empty", "command stopped", "killed")):
            raw = raws[name]
            self.assertEqual(bodies[name], [
                row(raw, 1, "exec_end", text, facts=(f"status={status}",)),
                row(raw, 2, "user", "first of the others"), row(raw, 3, "assistant", "second of the others"),
                row(raw, 4, "user", "third of the others")])

    def test_a_server_or_a_tool_that_no_call_shows_is_a_fact(self):
        # The same sentences, for the tool and the server of a call: a call shows them (see
        # test_the_tool_and_the_server_a_call_names_are_what_the_line_shows_so_they_are_no_facts), and a record that names
        # a server, or a tool, and holds no arguments for it to be called with is no call.
        others = [{"type": "user", "message": {"content": "first of the others"}},
                  {"type": "assistant", "message": {"content": "second of the others"}},
                  {"type": "user", "message": {"content": "third of the others"}}]
        bodies, raws = self.read_each({
            "server": [{"type": "mcp_connection", "server": "catalog", "text": "connection timed out"}, *others],
            "tool": [{"type": "tool_status", "tool": "search", "text": "the tool is slow"}, *others]})
        for name, label, text, fact in (("server", "mcp_connection", "connection timed out", "server=catalog"),
                                        ("tool", "tool_status", "the tool is slow", "tool=search")):
            raw = raws[name]
            self.assertEqual(bodies[name], [
                row(raw, 1, label, text, facts=(fact,)),
                row(raw, 2, "user", "first of the others"), row(raw, 3, "assistant", "second of the others"),
                row(raw, 4, "user", "third of the others")])

    def test_a_record_with_a_list_of_tool_calls_or_thoughts_and_no_message_shows_them_and_does_not_list_their_names(self):
        # "Lists of tool calls and of thoughts beside the message are shown too, and a record with nothing else shows the
        # names it lists": a record with these has something else.
        lines = self.read([{"type": "gemini", "toolCalls": [{"name": "run", "args": {"a": 1}}]},
                           {"type": "gemini", "thoughts": ["a bare thought"]}])
        self.assertEqual(lines, [row(self.raw, 1, "gemini", 'run({"a": 1})', "tool call"),
                                 row(self.raw, 2, "gemini", "a bare thought", "thinking")])

    def test_a_result_part_that_holds_no_text_shows_the_result_itself(self):
        # "a tool result ... from a result part (its text wherever it is nested, or the result itself where it holds no
        # text)": the count is the result, and is shown, as it is when it is in an output field.
        lines = self.read([{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": {"count": 3}},
            {"type": "toolResponse", "toolResult": {"status": "success", "value": {"count": 4}}}]}}])
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"- tool result: .*\"count\": 3")
        self.assertRegex(lines[1], r"- tool result: .*\"count\": 4")


class CallFactsTest(StampedLog):
    """A call's fields are content where the line shows that call, wherever the call is held, and facts where it does
    not."""

    def test_the_name_of_a_call_held_in_an_object_beside_the_message_is_shown_by_the_line_so_it_is_no_fact(self):
        # "... what the line shows as content are never facts" (gather.py's documentation of facts). The line shows the
        # call in the object under the payload as shell(...), so the object holding it gives no facts, as a call in the
        # object that holds the message does not (see DocumentedEdgesTest).
        lines = self.read([
            {"type": "response_item", "payload": {"type": "tool_request", "toolCall": {"name": "shell", "arguments": {"command": "pwd"}}}},
            {"type": "user", "message": {"content": "alpha speaks"}}, {"type": "user", "message": {"content": "bravo speaks"}},
            {"type": "user", "message": {"content": "charlie speaks"}}])
        self.assertEqual(lines[0], row(self.raw, 1, "response_item > tool_request", 'shell({"command": "pwd"})', "tool call"))

    def test_a_name_that_no_call_shows_is_a_fact(self):
        # "short values it carries besides its content" (gather.py's documentation of facts), as for the tool and the server
        # of a record that is no call (see DocumentedEdgesTest). A record with a name and no arguments to call it with is
        # no call, so no line shows the name, and the line names it among its facts.
        lines = self.read([
            {"type": "skill_loaded", "name": "demo-skill", "text": "skill loaded"},
            {"type": "user", "message": {"content": "alpha speaks"}}, {"type": "user", "message": {"content": "bravo speaks"}},
            {"type": "user", "message": {"content": "charlie speaks"}}])
        self.assertEqual(lines[0], row(self.raw, 1, "skill_loaded", "skill loaded", facts=("name=demo-skill",)))


class SessionFactsTest(LogHome):
    """What a session file says about itself: its id, from a sessionId field and else from the file's name, and its
    working directory, the most common absolute path in the fields that name one."""

    def test_the_session_id_is_a_sessionid_field_wherever_a_record_holds_it_else_the_files_name(self):
        jl(self.logs / "with-id.jsonl", stamped([
            {"type": "user", "message": {"content": "no id here"}},
            {"type": "user", "sessionId": "alpha", "message": {"content": "an id here"}},
            {"type": "event_msg", "payload": {"type": "ping", "sessionId": "alpha"}}]))
        jl(self.logs / "nested-id.jsonl", stamped([
            {"type": "event_msg", "payload": {"type": "session_meta", "sessionId": "from-payload", "text": "hello from the payload"}}]))
        jl(self.logs / "no-id.jsonl", stamped([{"type": "user", "message": {"content": "nothing to name it"}}]))
        out = self.gather()
        self.assertEqual(self.session_ids(out), {"alpha", "from-payload", "no-id"})
        self.assertEqual(transcript_of(out, "alpha").splitlines()[0], "# Session alpha")
        self.assertEqual(cells_of(out, "no-id")[11], str(self.logs / "no-id.jsonl"))

    def test_the_working_directory_is_the_most_common_absolute_path_in_a_field_that_names_one(self):
        jl(self.logs / "cwd.jsonl", stamped([
            {"type": "user", "sessionId": "cwd-1", "cwd": "/srv/alpha", "message": {"content": "one"}},
            {"type": "user", "sessionId": "cwd-1", "workdir": "/srv/alpha", "message": {"content": "two"}},
            {"type": "user", "sessionId": "cwd-1", "workingDirectory": "/srv/alpha", "message": {"content": "three"}},
            {"type": "session_meta", "sessionId": "cwd-1", "payload": {"cwd": "/srv/alpha"}},
            {"type": "user", "sessionId": "cwd-1", "cwd": "/srv/beta", "message": {"content": "four"}},
            {"type": "user", "sessionId": "cwd-1", "projectRoot": "/srv/beta", "message": {"content": "five"}},
            *[{"type": "user", "sessionId": "cwd-1", "cwd": "relative/dir", "message": {"content": f"rel {k}"}} for k in range(5)],
            {"type": "user", "sessionId": "cwd-1", "cwd": ["not", "a", "string"], "message": {"content": "nine"}}]))
        out = self.gather()
        # alpha four times, beta twice; a relative path, five times, or a value that is not text is no directory.
        self.assertEqual(cells_of(out, "cwd-1")[4], "/srv/alpha")
        self.assertIn("cwd: /srv/alpha  ", transcript_of(out, "cwd-1").splitlines())

    def test_a_record_whose_label_names_a_session_gives_the_sessions_id_when_no_session_id_field_came_first(self):
        jl(self.logs / "a.jsonl", stamped([
            {"type": "session_meta", "payload": {"id": "thread-abc", "cwd": "/srv/x"}},
            {"type": "user", "sessionId": "later-id", "message": {"content": "hi there"}}]))     # the first to name it wins
        jl(self.logs / "b.jsonl", stamped([
            {"type": "user", "sessionId": "first-id", "message": {"content": "hi there"}},
            {"type": "session_meta", "payload": {"id": "late-meta"}}]))                           # a field that came first wins
        jl(self.logs / "c.jsonl", stamped([{"type": "session", "id": "plain-session", "version": 3}]))      # the record's own id
        jl(self.logs / "d.jsonl", stamped([{"type": "event_msg", "payload": {"type": "session_configured", "id": "configured-1"}}]))
        jl(self.logs / "e.jsonl", stamped([{"type": "sessions", "id": "not-a-session-id"},               # the word is "session"
                                           {"type": "session_meta", "payload": {"id": 12345}}]))         # and its id is text
        out = self.gather()
        self.assertEqual(self.session_ids(out), {"thread-abc", "first-id", "plain-session", "configured-1", "e"})


# ---------------------------------------------------------------------------- pointers

class PointerMaskingTest(LogHome):
    """A raw log is pointed to by its path -- in the index, the header of its transcript and every line's reference.
    A name made of words, dates, UUIDs and hex ids keeps working as a pointer. A name shaped like a token is a secret
    wherever it is, and is masked in all of them; so is the same string in a record's text or a working directory."""

    HALVES = ("Zk9mQ2vDzX7bR4sT1pL8n", "Hy6tG3fE0dC8bA5zY2xW9", "Mn4bV7cX1zL0kJ3hG6fD9", "Pq2wE5rT8yU1iO4pA7sD0",
              "Lk8jH5gF2dS9aQ6wE3rT0")  # 21 characters each: assembled at run time into 42, which are tokens
    PLACE, DIR, FILE, CWD, TEXT = (half * 2 for half in HALVES)
    SPLIT = HALVES[0] + "-" + HALVES[1]  # a token split at a hyphen: two words of 21 characters
    UUID = "0199abcd-ef01-7234-8bcd-0123456789ab"
    SHA = "a1b2c3d4" * 8  # a sha256 digest in the name of a directory

    def log(self, path, session_id, text):
        return jl(path, stamped([{"type": "user", "sessionId": session_id, "cwd": "/srv/pointers", "message": {"content": text}}]))

    def hide(self, path, run):
        """The path as the files show it, with the run of its name that is shaped like a token masked."""
        return str(path).replace(run, "[masked]")

    def setUp(self):
        super().setUp()
        # Names as harnesses make them: a working directory encoded in a project's directory name, a UUID, a rollout's
        # date and UUID, a subagent's id; a digest as the name of a directory.
        self.encoded = self.root / "-home-user-agent-tooling--claude-worktrees-heal-gather-2026-q3-roadmap"
        self.kept = {
            "pointer-uuid": self.log(self.encoded / f"{self.UUID}.jsonl", "pointer-uuid", "hello from the uuid"),
            "pointer-rollout": self.log(self.encoded / f"rollout-2026-10-15T09-11-58-{self.UUID}.jsonl", "pointer-rollout", "hello from the rollout"),
            "pointer-sub": self.log(self.encoded / self.UUID / "subagents" / "agent-a1b2c3d4e5f6a7b8.jsonl", "pointer-sub", "hello from the subagent")}
        self.chat = write_json(self.root / "gemini" / self.SHA / "chats" / "session-2026-10-15T10-00-abc12345.json", {
            "sessionId": "pointer-chat", "messages": [{"type": "user", "content": "hello from the chat", "timestamp": at(0)}]})
        # Names shaped like a token: a place, a directory, a file (whose name the record's text repeats), a split one.
        self.token_place = self.root / self.PLACE
        self.logs2 = self.root / "logs2"
        self.a = jl(self.token_place / "a.jsonl", stamped([{
            "type": "user", "sessionId": "token-a", "cwd": f"/srv/{self.CWD}", "message": {"content": f"my id is {self.TEXT} ok"}}]))
        self.b = self.log(self.logs2 / self.DIR / "b.jsonl", "token-b", "hello from b")
        self.c = self.log(self.logs2 / f"rollout-{self.FILE}.jsonl", "token-c", f"the file is rollout-{self.FILE}.jsonl")
        self.d = self.log(self.logs2 / f"{self.SPLIT}.jsonl", "token-d", "hello from d")
        self.masked = {"token-a": self.hide(self.a, self.PLACE), "token-b": self.hide(self.b, self.DIR),
                       "token-c": self.hide(self.c, "rollout-" + self.FILE), "token-d": self.hide(self.d, self.SPLIT)}
        self.out = self.gather(self.encoded, self.token_place, self.logs2, self.root / "gemini")

    def test_a_name_of_words_dates_uuids_and_hex_ids_is_a_pointer_that_keeps_working(self):
        out = self.out
        for session_id, raw in self.kept.items():
            cells = cells_of(out, session_id)
            self.assertEqual((cells[1], cells[11]), (str(self.encoded), str(raw)))
            self.assertEqual(transcript_of(out, session_id).splitlines()[2:4], [f"place: {self.encoded}  ", f"raw log: {raw}  "])
        # Every line's reference is the path as it is.
        for session_id, text in (("pointer-uuid", "hello from the uuid"), ("pointer-rollout", "hello from the rollout"),
                                 ("pointer-sub", "hello from the subagent")):
            self.assertEqual(body_of(transcript_of(out, session_id)), [row(self.kept[session_id], 1, "user", text)])
        self.assertEqual(body_of(transcript_of(out, "pointer-chat")), [f"[{shown(0)}] user: hello from the chat  ({self.chat} record 1)"])
        self.assertEqual(cells_of(out, "pointer-chat")[11], str(self.chat))   # the digest, 64 hex characters, is in the path as it is

    def test_a_name_shaped_like_a_token_is_masked_in_the_index_the_header_the_references_and_what_is_printed(self):
        out = self.out
        self.assertEqual(places_of(out), [
            f"{self.encoded}: 3 record file(s); 3 session(s) in the window",
            f"{self.hide(self.token_place, self.PLACE)}: 1 record file(s); 1 session(s) in the window",
            f"{self.logs2}: 3 record file(s); 3 session(s) in the window",
            f"{self.root / 'gemini'}: 1 record file(s); 1 session(s) in the window"])
        self.assertEqual(self.stdout.splitlines()[3:], places_of(out))   # what it prints is masked the same way
        for session_id, shown_path in self.masked.items():
            cells = cells_of(out, session_id)
            self.assertEqual(cells[11], shown_path)
            self.assertTrue((out / link_of(cells)).is_file())   # the link is to a name no masking touches, so it leads there
            self.assertEqual(transcript_of(out, session_id).splitlines()[3], f"raw log: {shown_path}  ")
        self.assertEqual(cells_of(out, "token-a")[1], self.hide(self.token_place, self.PLACE))
        self.assertEqual(transcript_of(out, "token-a").splitlines()[2], f"place: {self.hide(self.token_place, self.PLACE)}  ")
        self.assertEqual(body_of(transcript_of(out, "token-b")), [f"[{shown(0)}] user: hello from b  ({self.masked['token-b']}:1)"])

    def test_the_same_string_in_a_records_text_or_in_a_working_directory_is_masked(self):
        out = self.out
        self.assertEqual(body_of(transcript_of(out, "token-a")), [f"[{shown(0)}] user: my id is [masked] ok  ({self.masked['token-a']}:1)"])
        self.assertEqual(body_of(transcript_of(out, "token-c")),
                         [f"[{shown(0)}] user: the file is [masked].jsonl  ({self.masked['token-c']}:1)"])
        self.assertEqual(cells_of(out, "token-a")[4], "/srv/[masked]")
        self.assertIn("cwd: /srv/[masked]  ", transcript_of(out, "token-a").splitlines())
        # Not one file holds an id, or is named by one.
        for path, text in written(out):
            for secret in (*self.HALVES, self.PLACE, self.DIR, self.FILE, self.CWD, self.TEXT, self.SPLIT):
                self.assertNotIn(secret, text, path.name)
                self.assertNotIn(secret, path.name)


class WordPointerTest(LogHome):
    """A run of a raw log's name made of words keeps working as a pointer. A word of eight characters or more that mixes
    upper case, lower case and digits is no word of a name -- it is a token, or a piece of one -- so a run it is in is
    masked wherever it is written, though none of its words is long enough to be a token by itself."""

    WORD = "Ab3dEf5Gh7"          # ten characters: no token by itself
    RUN = "-".join([WORD] * 4)    # four of them joined (forty-three characters), put together here as in a path
    UUID = "0199abcd-ef01-7234-8bcd-0123456789ab"
    HEX = "agent-a1b2c3d4e5f6a7b8-c9d0e1f2a3b4c5d6-e7f8a9b0c1d2e3f4"

    def log(self, path, session_id):
        return jl(path, stamped([{"type": "user", "sessionId": session_id, "cwd": "/srv/pointers",
                                  "message": {"content": f"hello from {session_id}"}}]))

    def hide(self, path):
        return str(path).replace(self.RUN, "[masked]")

    def setUp(self):
        super().setUp()
        self.named_place = self.root / self.RUN              # a place so named
        self.logs2 = self.root / "logs2"
        self.masked = {"word-place": self.log(self.named_place / "a.jsonl", "word-place"),
                       "word-dir": self.log(self.logs2 / self.RUN / "b.jsonl", "word-dir")}   # and a directory so named
        # Names as harnesses make them: a rollout's date and UUID, a UUID, a subagent's lower-case hex words.
        self.kept = {"kept-rollout": self.log(self.logs2 / f"rollout-2026-10-15T09-11-58-{self.UUID}.jsonl", "kept-rollout"),
                     "kept-uuid": self.log(self.logs2 / f"{self.UUID}.jsonl", "kept-uuid"),
                     "kept-hex": self.log(self.logs2 / f"{self.HEX}.jsonl", "kept-hex")}
        self.out = self.gather(self.named_place, self.logs2)

    def test_the_run_is_masked_in_the_index_the_header_the_references_and_what_is_printed(self):
        out = self.out
        self.assertEqual(places_of(out), [f"{self.hide(self.named_place)}: 1 record file(s); 1 session(s) in the window",
                                          f"{self.logs2}: 4 record file(s); 4 session(s) in the window"])
        self.assertEqual(self.stdout.splitlines()[3:], places_of(out))
        for session_id, raw in self.masked.items():
            text = transcript_of(out, session_id)
            self.assertEqual(cells_of(out, session_id)[11], self.hide(raw))
            self.assertTrue((out / link_of(cells_of(out, session_id))).is_file())   # the link is to a name no masking touches
            self.assertEqual(text.splitlines()[3], f"raw log: {self.hide(raw)}  ")
            self.assertEqual(body_of(text), [row(self.hide(raw), 1, "user", f"hello from {session_id}")])
        self.assertEqual(cells_of(out, "word-place")[1], self.hide(self.named_place))
        self.assertEqual(transcript_of(out, "word-place").splitlines()[2], f"place: {self.hide(self.named_place)}  ")
        for path, text in written(out):
            for secret in (self.WORD, self.RUN):
                self.assertNotIn(secret, text, path.name)
                self.assertNotIn(secret, path.name)
        self.assertNotIn(self.WORD, self.stdout)

    def test_a_name_made_of_a_date_a_uuid_or_hex_words_is_still_a_pointer_that_keeps_working(self):
        out = self.out
        for session_id, raw in self.kept.items():
            cells = cells_of(out, session_id)
            self.assertEqual((cells[1], cells[11]), (str(self.logs2), str(raw)))
            text = transcript_of(out, session_id)
            self.assertEqual(text.splitlines()[3], f"raw log: {raw}  ")
            self.assertEqual(body_of(text), [row(raw, 1, "user", f"hello from {session_id}")])


# ---------------------------------------------------------------------------- the time window

class WindowTest(LogHome):
    """A session is in the window by its own records' times, not by when its file was last written."""

    def session_log(self, name, session_id, stamps):
        return jl(self.logs / "proj" / f"{name}.jsonl", [
            {"timestamp": t, "type": "user", "sessionId": session_id, "cwd": "/srv/agent-fixture",
             "message": {"content": f"message {i}"}} for i, t in enumerate(stamps)])

    def three_sessions(self):
        # Every file below was just written, so its modification time is "now" for all of them.
        self.session_log("old", "log-old", ["2020-01-01T00:00:00Z", "2020-01-01T00:05:00Z"])
        self.session_log("fresh", "log-fresh", [hours_ago(3), hours_ago(2)])
        self.session_log("spanning", "log-spanning", [hours_ago(24 * 10), hours_ago(1)])

    def test_a_file_written_today_whose_records_are_old_is_not_in_a_recent_window(self):
        self.three_sessions()
        out = self.gather(since="1d")
        self.assertEqual(self.session_ids(out), {"log-fresh", "log-spanning"})
        # A session that straddles --since is kept whole, its old record included.
        self.assertIn("] user: message 0  (", self.transcript(out, "log-spanning"))
        self.assertEqual(places_of(out), [f"{self.logs}: 3 record file(s); 2 session(s) in the window; 1 outside it"])

    def test_until_selects_by_the_day_a_session_began_not_by_its_file(self):
        self.three_sessions()
        out = self.gather(since="2000-01-01", extra=["--until", "2020-01-01"])
        self.assertEqual(self.session_ids(out), {"log-old"})

    def test_until_ends_at_the_midnight_after_its_date_and_a_session_at_that_midnight_is_out(self):
        self.session_log("last-second", "log-last-second", ["2020-01-01T23:59:59Z"])
        self.session_log("midnight", "log-midnight", ["2020-01-02T00:00:00Z"])
        for name, stamped_at in (("in", dt.datetime(2020, 1, 1, 23, 59, 59, tzinfo=UTC)), ("out", dt.datetime(2020, 1, 2, tzinfo=UTC))):
            raw = jl(self.logs / "proj" / f"untimed-{name}.jsonl", [{"type": "user", "sessionId": f"log-untimed-{name}", "message": {"content": "hello"}}])
            os.utime(raw, (stamped_at.timestamp(), stamped_at.timestamp()))  # no record timestamps: the file's time decides
        out = self.gather(since="2000-01-01", extra=["--until", "2020-01-01"])
        self.assertEqual(self.session_ids(out), {"log-last-second", "log-untimed-in"})

    def test_until_refuses_anything_but_a_date_before_it_reads_or_writes_anything(self):
        for value in ("2020-01-01T12:00:00Z", "2020-01-01 12:00", "3d", "2020-02-30", "20200101", "9999-12-31"):
            out = self.root / f"refused-{value.replace(':', '').replace(' ', '_')}"
            r = run_gather_script([self.logs, "--since", "2000-01-01", "--until", value, "--out", out])
            self.assertNotEqual(r.returncode, 0, value)
            self.assertIn(f"error: invalid --until value {value!r}", r.stderr)
            self.assertIn("use a date, YYYY-MM-DD", r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertFalse(out.exists(), value)

    def test_since_refuses_what_is_neither_a_number_of_days_nor_a_date(self):
        out = self.root / "refused-since"
        r = run_gather_script([self.logs, "--since", "last tuesday", "--out", out])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("error: invalid --since value 'last tuesday'", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse(out.exists())

    def test_the_window_is_the_last_seven_days_unless_since_says_otherwise(self):
        self.session_log("week", "log-week", [hours_ago(24 * 6)])
        self.session_log("fortnight", "log-fortnight", [hours_ago(24 * 8)])
        self.assertEqual(self.session_ids(self.gather(since=None)), {"log-week"})

    def test_a_session_without_record_timestamps_is_placed_by_its_files_modification_time(self):
        for name in ("stale", "recent"):
            jl(self.logs / "proj" / f"{name}.jsonl", [{"type": "user", "sessionId": f"log-untimed-{name}", "message": {"content": "hello"}}])
        month_ago = dt.datetime.now(UTC).timestamp() - 30 * 86400
        os.utime(self.logs / "proj" / "stale.jsonl", (month_ago, month_ago))
        out = self.gather(since="1d")
        self.assertEqual(self.session_ids(out), {"log-untimed-recent"})

    def test_a_session_whose_newest_record_is_followed_by_a_thousand_older_ones_is_in_the_window(self):
        # Records are not always in time order (a replay, a resume, a rewrite): the end of this file holds only
        # old ones, and the newest sits ahead of them, past what the end of the file shows. It was just written.
        pad = "x" * 200
        jl(self.logs / "proj" / "disordered.jsonl", [
            {"timestamp": hours_ago(1), "type": "user", "sessionId": "log-disordered", "message": {"content": "the newest words " + pad}}]
           + [{"timestamp": hours_ago(24 * 10), "type": "user", "sessionId": "log-disordered", "message": {"content": "old " + pad}}
              for _ in range(1000)])
        out = self.gather(since="1d")
        self.assertEqual(self.session_ids(out), {"log-disordered"})
        self.assertIn("the newest words", self.transcript(out, "log-disordered"))

    def test_a_file_stamped_days_before_the_records_in_it_is_still_read(self):
        # Logs synced from a machine whose clock ran behind, or written under a wrong clock: the file system
        # stamped each file three days ago, yet the newest record in it is inside the window.
        stamped_at = dt.datetime.now(UTC).timestamp() - 3 * 86400
        transcript = self.session_log("skewed", "log-skewed", [hours_ago(23)])
        rollout = jl(self.logs / "rollout-skewed.jsonl", [
            {"timestamp": hours_ago(23), "type": "session_meta", "payload": {"id": "rollout-skewed", "cwd": "/srv/x"}},
            item(hours_ago(22), {"type": "UserMessage", "id": uid(2), "content": text_blocks("hi")})])
        chat = jl(self.logs / "chats" / "session-skewed.jsonl", [
            {"sessionId": "gem-skewed", "startTime": hours_ago(23)},
            {"id": "m1", "type": "user", "content": "hi", "timestamp": hours_ago(22)}])
        for raw in (transcript, rollout, chat):
            os.utime(raw, (stamped_at, stamped_at))
        self.assertEqual(self.session_ids(self.gather(since="1d")), {"log-skewed", "rollout-skewed", "gem-skewed"})

    def test_a_log_is_not_opened_by_its_reader_unless_its_last_record_or_its_file_reaches_since(self):
        ancient = dt.datetime(2020, 1, 1, tzinfo=UTC).timestamp()
        recent_log = self.session_log("recent", "log-recent", [hours_ago(2)])
        os.utime(recent_log, (ancient, ancient))              # written a long time ago, by its file system's clock
        old_log = self.session_log("old", "log-old", [hours_ago(24 * 10)])
        os.utime(old_log, (ancient, ancient))                 # old by both its records and its file's clock
        touched_log = self.session_log("touched", "log-touched", [hours_ago(24 * 10)])
        since = dt.datetime.now(UTC) - dt.timedelta(days=1)   # its records are old but it was just written: read
        with mock.patch.object(gather, "read_session", return_value=(None, "not read here")) as read:
            gather.gather_places([self.logs / "proj"], since, None, 2000)
        self.assertEqual([call.args[0] for call in read.call_args_list], [recent_log, touched_log])

    def test_a_record_the_transcript_only_notes_still_counts_as_the_sessions_latest(self):
        stamp = hours_ago(1)
        jl(self.logs / "rollout-telemetry.jsonl", [
            {"timestamp": "2020-01-01T00:00:00Z", "type": "session_meta", "payload": {"id": "rollout-telemetry", "cwd": "/srv/agent-fixture"}},
            item("2020-01-01T00:00:01Z", {"type": "UserMessage", "id": uid(2), "content": text_blocks("hello")}),
            {"timestamp": stamp, "type": "event_msg", "payload": {"type": "token_count", "info": {}}}])
        out = self.gather(since="1d")
        self.assertEqual(self.session_ids(out), {"rollout-telemetry"})
        self.assertEqual(self.index_row(out, "rollout-telemetry")[3],
                         dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).isoformat())  # "end"

    def test_log_lines_and_documents_are_placed_by_their_records_too(self):
        for name, stamp in (("old", "2020-01-01T00:00:00Z"), ("fresh", hours_ago(2))):
            jl(self.logs / f"rollout-{name}.jsonl", [
                {"timestamp": stamp, "type": "session_meta", "payload": {"id": f"rollout-{name}", "cwd": "/srv/agent-fixture"}},
                item(stamp, {"type": "UserMessage", "id": uid(2), "content": text_blocks("hello")})])
            write_json(self.logs / "chats" / f"session-{name}.json", {
                "sessionId": f"gem-{name}", "startTime": stamp, "lastUpdated": stamp,
                "messages": [{"type": "user", "content": "hello", "timestamp": stamp}]})
        out = self.gather(since="1d")
        self.assertEqual(self.session_ids(out), {"rollout-fresh", "gem-fresh"})


class WindowRuleTest(unittest.TestCase):
    """The edges of the window rule, where an off-by-one would quietly lose or admit a session."""

    def session(self, start, end):
        s = gather.Session(Path("raw.jsonl"), Path("."))
        s.start, s.end = start, end
        return s

    def test_latest_record_at_since_is_in_and_a_second_earlier_is_out(self):
        since = dt.datetime(2026, 1, 3, 10, 0, 0, tzinfo=UTC)
        one_second = dt.timedelta(seconds=1)
        early = dt.datetime(2026, 1, 1, tzinfo=UTC)
        self.assertTrue(gather.session_in_window(self.session(early, since), since, None))
        self.assertFalse(gather.session_in_window(self.session(early, since - one_second), since, None))

    def test_earliest_record_anywhere_in_the_until_day_is_in_and_the_midnight_after_it_is_out(self):
        until = gather.parse_until("2026-01-01")  # the whole of that day is meant
        one_second = dt.timedelta(seconds=1)
        end = dt.datetime(2026, 2, 1, tzinfo=UTC)
        midnight_before, midnight_after = dt.datetime(2026, 1, 1, tzinfo=UTC), dt.datetime(2026, 1, 2, tzinfo=UTC)
        self.assertTrue(gather.session_in_window(self.session(midnight_before, end), None, until))
        self.assertTrue(gather.session_in_window(self.session(midnight_after - one_second, end), None, until))
        self.assertFalse(gather.session_in_window(self.session(midnight_after, end), None, until))
        self.assertFalse(gather.session_in_window(self.session(midnight_after + one_second, end), None, until))

    def test_until_is_the_midnight_that_ends_the_day_it_names(self):
        for named, ends in (("2026-01-01", dt.datetime(2026, 1, 2, tzinfo=UTC)), ("2026-12-31", dt.datetime(2027, 1, 1, tzinfo=UTC)),
                            ("2028-02-28", dt.datetime(2028, 2, 29, tzinfo=UTC)), ("2026-02-28", dt.datetime(2026, 3, 1, tzinfo=UTC))):
            self.assertEqual(gather.parse_until(named), ends, named)
        self.assertIsNone(gather.parse_until(None))
        self.assertIsNone(gather.parse_until(""))

    def test_until_refuses_what_is_not_a_date_with_a_message_that_says_what_to_give(self):
        for value in ("2026-01-01T12:00:00Z", "2026-01-01 12:00", "2026-01-01T00:00:00+02:00", "3d", "yesterday", "2026-02-30",
                      "20260101", "2026-1-1", "2026-01-01 ", "9999-12-31", "0000-01-01"):
            with self.assertRaises(SystemExit) as caught:
                gather.parse_until(value)
            message = str(caught.exception)
            self.assertIn(f"invalid --until value {value!r}", message)
            self.assertIn("YYYY-MM-DD", message)

    def test_no_bounds_admit_everything(self):
        s = self.session(dt.datetime(2000, 1, 1, tzinfo=UTC), dt.datetime(2000, 1, 2, tzinfo=UTC))
        self.assertTrue(gather.session_in_window(s, None, None))

    def test_without_timestamps_the_file_modification_time_decides(self):
        tmp = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        raw = tmp / "raw.jsonl"
        raw.write_text("{}\n")
        stamp = dt.datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
        os.utime(raw, (stamp.timestamp(), stamp.timestamp()))
        s = gather.Session(raw, tmp)
        self.assertIsNone(s.start)
        self.assertTrue(gather.session_in_window(s, stamp - dt.timedelta(days=1), stamp + dt.timedelta(days=1)))
        self.assertFalse(gather.session_in_window(s, stamp + dt.timedelta(days=1), None))
        self.assertFalse(gather.session_in_window(s, None, stamp - dt.timedelta(days=2)))

    def test_without_timestamps_a_file_stamped_at_the_midnight_after_the_until_day_is_out(self):
        tmp = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        raw = tmp / "raw.jsonl"
        raw.write_text("{}\n")
        s = gather.Session(raw, tmp)
        until = gather.parse_until("2026-01-01")
        midnight_after = dt.datetime(2026, 1, 2, tzinfo=UTC)
        os.utime(raw, (midnight_after.timestamp() - 1, midnight_after.timestamp() - 1))
        self.assertTrue(gather.session_in_window(s, None, until))
        os.utime(raw, (midnight_after.timestamp(), midnight_after.timestamp()))
        self.assertFalse(gather.session_in_window(s, None, until))

    def log(self, rows, name="raw.jsonl", written=dt.datetime(2020, 1, 1, tzinfo=UTC)):
        """A log of these rows, last written (by its file system's clock) long ago unless `written` says when."""
        tmp = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        raw = tmp / name
        jl(raw, rows)
        self.stamp_file(raw, written)
        return raw

    def stamp_file(self, raw, when):
        os.utime(raw, (when.timestamp(), when.timestamp()))

    def test_a_file_is_skipped_only_if_neither_its_last_record_nor_its_modification_time_reaches_since(self):
        last = dt.datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
        one, month = dt.timedelta(seconds=1), dt.timedelta(days=30)
        raw = self.log([{"timestamp": "2026-01-01T00:00:00Z", "type": "user"}, {"timestamp": "2026-01-10T12:00:00Z", "type": "user"}])
        for written, since, expected in (
            (last - month, last, True),                   # written long ago by its clock, but its last record is since
            (last - month, last - dt.timedelta(days=5), True),
            (last - month, last + one, False),            # neither reaches since
            (last + month, last + one, True),             # its last record is older, but the file was written since: read
            (last + month, last + month, True),           # (at since exactly)
            (last + month, last + month + one, False),    # neither reaches since
        ):
            self.stamp_file(raw, written)
            self.assertEqual(gather.could_hold_window(raw, since), expected, (written.isoformat(), since.isoformat()))
        self.assertTrue(gather.could_hold_window(raw, None))
        self.assertFalse(gather.could_hold_window(raw.parent / "missing.jsonl", None))

    def test_a_newer_record_before_a_thousand_older_ones_does_not_hide_a_file_that_was_written_since(self):
        since = dt.datetime(2026, 1, 5, tzinfo=UTC)
        newer = {"timestamp": "2026-01-10T12:00:00Z", "type": "user", "pad": "x" * 200}
        older = [{"timestamp": "2026-01-01T00:00:00Z", "type": "user", "pad": "x" * 200} for _ in range(1000)]
        raw = self.log([newer] + older, written=dt.datetime(2026, 1, 11, tzinfo=UTC))   # the end of the file holds nothing newer
        self.assertTrue(gather.could_hold_window(raw, since))

    def test_the_last_record_is_found_however_long_it_is_and_even_if_it_is_still_being_written(self):
        early = {"timestamp": "2026-01-01T00:00:00Z", "type": "user"}
        t_early, t_late = dt.datetime(2026, 1, 1, tzinfo=UTC), dt.datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
        # A last record far longer than the end of the file the first read looks at.
        big = self.log([early, {"timestamp": "2026-01-10T12:00:00Z", "type": "user", "message": {"content": "x" * 300_000}}])
        self.assertEqual(gather.last_record_time(big), t_late)
        # A last line that has been cut short (the agent is writing it now) is not a record: the one before it is.
        cut = self.log([early])
        with cut.open("a") as fh:
            fh.write(json.dumps({"timestamp": "2026-01-10T12:00:00Z", "type": "user"})[:30])
        self.assertEqual(gather.last_record_time(cut), t_early)
        # Records after the last timestamped one that carry none do not hide it.
        tail = self.log([early] + [{"type": "summary", "summary": "no time"}] * 5000)
        self.assertEqual(gather.last_record_time(tail), t_early)
        # A log with no time in it, and one that is empty, have none to give.
        self.assertIsNone(gather.last_record_time(self.log([{"type": "user"}, {}])))
        self.assertIsNone(gather.last_record_time(self.log([])))
        self.assertIsNone(gather.last_record_time(big.parent / "missing.jsonl"))

    def test_a_logs_last_time_is_the_latest_time_of_its_records_and_one_in_an_object_under_a_record_counts(self):
        sec = dt.timedelta(seconds=1)
        base = dt.datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
        message = {"id": "m1", "type": "user", "content": "hi", "timestamp": "2026-01-10T12:00:00Z"}
        by_update = self.log([{"sessionId": "g", "startTime": "2026-01-10T11:00:00Z"}, message,
                              {"$set": {"lastUpdated": "2026-01-10T12:30:00Z"}}])
        self.assertTrue(gather.could_hold_window(by_update, base + dt.timedelta(minutes=30)))
        self.assertFalse(gather.could_hold_window(by_update, base + dt.timedelta(minutes=30) + sec))
        by_message = self.log([{"sessionId": "g", "startTime": "2026-01-10T11:00:00Z"}, message])
        self.assertTrue(gather.could_hold_window(by_message, base))
        self.assertFalse(gather.could_hold_window(by_message, base + sec))

    def test_without_a_time_in_any_record_the_file_modification_time_decides_exactly(self):
        written = dt.datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
        one = dt.timedelta(seconds=1)
        raw = self.log([{"type": "user", "message": {"content": "no time"}}, {}])
        self.stamp_file(raw, written)
        self.assertTrue(gather.could_hold_window(raw, written))
        self.assertFalse(gather.could_hold_window(raw, written + one))   # no slack: this is the rule that places the session

    def test_a_single_json_document_has_no_last_record_to_read_and_is_read_whole(self):
        raw = self.log([], name="session-old.json")
        raw.write_text(json.dumps({"sessionId": "g", "lastUpdated": "2020-01-01T00:00:00Z", "messages": []}))
        self.stamp_file(raw, dt.datetime(2020, 1, 1, tzinfo=UTC))
        self.assertTrue(gather.could_hold_window(raw, dt.datetime(2026, 1, 1, tzinfo=UTC)))

    def test_a_compressed_log_has_no_end_to_read_cheaply_and_its_files_time_decides(self):
        # Only the name and the file's time are looked at, so what the file holds does not matter to this rule.
        since = dt.datetime(2026, 1, 10, tzinfo=UTC)
        recent_record = [{"timestamp": "2026-01-10T12:00:00Z", "type": "user"}]
        for suffix in (".gz", ".bz2", ".xz", ".zst"):
            raw = self.log(recent_record, name=f"raw.jsonl{suffix}", written=since - dt.timedelta(seconds=1))
            self.assertFalse(gather.could_hold_window(raw, since), suffix)
            self.stamp_file(raw, since)
            self.assertTrue(gather.could_hold_window(raw, since), suffix)


class RecordTimeTest(unittest.TestCase):
    """A record's time is the first plausible time -- an ISO time, or seconds or milliseconds since the epoch, after
    the year 2000 -- in one of its time fields, at its top level or in an object under it."""

    T = dt.datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
    EPOCH = dt.datetime(2026, 9, 21, 14, 13, 20, tzinfo=UTC)  # 1,790,000,000 seconds after 1970

    def test_the_forms_of_a_time_and_the_names_of_a_field_that_holds_one(self):
        iso = "2026-01-10T12:00:00Z"
        for record, expected in (
            ({"timestamp": iso}, self.T),
            ({"time": "2026-01-10T14:00:00+02:00"}, self.T),                       # an offset is kept to the instant
            ({"created": "2026-01-10T12:00:00"}, self.T),                          # no offset: UTC
            ({"date": "2026-01-10"}, dt.datetime(2026, 1, 10, tzinfo=UTC)),
            ({"ts": 1_790_000_000}, self.EPOCH),                                   # seconds since the epoch
            ({"created": 1_790_000_000_000}, self.EPOCH),                          # milliseconds
            ({"created_at": iso}, self.T), ({"createdAt": iso}, self.T), ({"updated": iso}, self.T),
            ({"lastUpdated": iso}, self.T), ({"started": iso}, self.T), ({"startTime": iso}, self.T),
            ({"time": {"created": iso}}, self.T),                                  # an object a time field names
            ({"meta": {"timestamp": iso}}, self.T),                                # and any object under the record
            ({"time": 3000, "timestamp": iso}, self.T),                            # a duration is no time: the next field is
        ):
            self.assertEqual(gather.record_time(record), expected, record)

    def test_what_is_not_a_time_is_not_one(self):
        iso = "2026-01-10T12:00:00Z"
        for record in ({}, {"timestamp": True}, {"timestamp": "not a time"}, {"timestamp": "3026-01-01T00:00:00Z"},
                       {"date": "1999-12-31T23:59:59Z"}, {"time": 3000}, {"timestamp": None}, {"timestamp": [iso]},
                       {"updated_by": iso}, {"events": [{"timestamp": iso}]}):
            self.assertIsNone(gather.record_time(record), record)


# ---------------------------------------------------------------------------- masking, everywhere

class MaskedEverywhereTest(LogHome):
    """Nothing gather.py writes carries a credential that a log or a git repository holds: not a transcript line, not
    a header, not a cell of the index, not a fact of the workspace file, and not a file name. Every value that
    reaches a file is masked, whichever code composed it."""

    def setUp(self):
        super().setUp()
        self.token = "gh" + "p_" + "a" * 30        # assembled at run time: nothing secret-shaped is committed
        self.random = "Zk9mQ2vDzX7bR4sT1pL8n" * 2  # 42 characters with no prefix: only the catch-all finds it
        self.mixed = f"{self.token}-{self.random}"  # both, joined: a pass by prefix finds only the first
        self.escaped = '{"p\\u0061ssword": "say violet kettle now"}'  # one only a pass that decodes JSON can see
        self.secrets = (self.token, self.random, "hunter22", "violet", "kettle")
        # The working directory is a repository whose own name, branch, and stash carry the credential.
        self.repo = make_repo(self.root / f"repo-{self.mixed}", branches=[self.mixed], stash=f"wip {self.mixed} {self.escaped}")
        git(self.repo, "worktree", "add", "-q", str(self.root / f"wt-{self.mixed}"), self.mixed)

        def record(kind, **fields):
            return {"timestamp": at(0), "type": kind, "sessionId": f"claude-{self.random}", "agentId": self.random,
                    "cwd": str(self.repo), **fields}
        # A session whose id and agent's id are a token, a hook whose every field is a token, and JSON-shaped credentials.
        self.transcript_raw = jl(self.logs / "transcripts" / "plain-session.jsonl", [
            record("user", message={"content": 'set {"password": "hunter22"} please'}),
            record("attachment", attachment={"type": "hook_non_blocking_error", "hookName": f"Stop-{self.mixed}",
                                             "hookEvent": f"Stop-{self.mixed}", "exitCode": self.mixed, "timedOut": True,
                                             "timeoutMs": self.mixed, "stderr": '{"password": "hunter22"}'}),
            record("assistant", message={"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                                       "input": {"command": "curl -d '{\"password\": \"hunter22\"}' http://x"}}]}),
            record("user", message={"content": [{"type": "tool_result", "tool_use_id": self.mixed, "content": '{"password": "hunter22"}'}]})])
        jl(self.logs / "rollouts" / "rollout-a.jsonl", [
            {"timestamp": at(0), "type": "session_meta", "payload": {"id": f"codex-{self.random}", "cwd": str(self.repo)}},
            item(at(1), {"type": "UserMessage", "id": uid(1), "content": text_blocks("hello")})])
        write_json(self.logs / "chats" / "session-a.json", {
            "sessionId": f"gem-{self.random}", "startTime": at(0), "lastUpdated": at(1),
            "messages": [{"type": "user", "content": "hi", "timestamp": at(0)}]})
        self.out = self.gather()

    def test_no_file_or_file_name_holds_a_credential(self):
        files = written(self.out)
        self.assertGreater(len(files), 4)
        for path, text in files:
            for secret in self.secrets:
                self.assertNotIn(secret, text, f"{path.name} holds {secret[:8]}...")
                self.assertNotIn(secret, path.name)

    def test_every_field_of_a_hook_record_is_masked_and_the_line_is_still_there(self):
        text = transcript_at(self.out, self.transcript_raw)
        m = r"(?:\[masked\])+"  # one marker for each credential in a field (two, where a prefixed token and a prefixless one sit together)
        hook = next(line for line in text.splitlines() if " attachment > hook_non_blocking_error" in line)
        self.assertRegex(hook, rf'^\[.*\] attachment > hook_non_blocking_error(?: ?\{{[^}}]*\}})? - tool result: \(exitCode {m}\) \{{"\[masked\]"\}}  \(')
        self.assertIn('] user: set {"[masked]"} please  (', text)

    def test_headers_and_index_cells_are_masked_but_the_pointers_in_them_still_work(self):
        for cells in index_rows(self.out):
            self.assertTrue((self.out / link_of(cells)).is_file(), cells[10])  # the readable link resolves
        # A raw log whose name is long and mixed (like a UUID) is a pointer, not a secret: it is not masked.
        plain = jl(self.root / "plain" / "proj" / ("rollout-2026-10-15T09-11-58-" + "01a14055-5d49-7033-a5ee-9c4a77e02fa2.jsonl"),
                   [{"timestamp": at(0), "type": "user", "sessionId": "claude-plain", "message": {"content": "hi"}}])
        out = self.gather(self.root / "plain")
        self.assertIn(f"raw log: {plain}  ", transcript_of(out, "claude-plain").splitlines())
        self.assertEqual(cells_of(out, "claude-plain")[11], str(plain))

    def test_the_workspace_facts_are_masked(self):
        workspace = (self.out / "workspace.md").read_text(encoding="utf-8")
        lines = workspace.splitlines()
        # The repository's name, its branch (one, merged), its worktree and its stash, each with the credential in it masked as two.
        self.assertIn(f"## {self.root.resolve()}/repo-[masked][masked]", lines)
        self.assertIn("- local branches (1): [masked][masked]", lines)
        self.assertIn("- merged into default (1): [masked][masked]", lines)
        self.assertIn(f"- worktrees (1): {self.root.resolve()}/wt-[masked][masked]", lines)
        self.assertIn('- stashes (1): stash@{0}: On main: wip [masked][masked] {"[masked]"}', lines)

    def test_a_credential_in_the_name_of_a_place_that_is_missing_is_masked_in_the_index_and_in_what_is_printed(self):
        missing = self.root / f"no-such-{self.token}"
        out = self.gather(self.logs, missing)
        expected = f"{self.root}/no-such-[masked]: not found"
        self.assertEqual(places_of(out)[1], expected)
        self.assertEqual(self.stdout.splitlines()[-1], expected)
        self.assertNotIn(self.token, self.stdout)
        for path, text in written(out):
            self.assertNotIn(self.token, text, path.name)


# ---------------------------------------------------------------------------- a credential in JSON in a string

class JsonInStringTest(LogHome):
    """A credential in JSON that sits inside a string -- a command that carries a request body, a tool's
    output that is a JSON document, a document inside a document -- is masked as the value it is, not
    looked for in the escaped text it becomes inside the JSON around it."""

    WORDS = ("violet", "kettle")

    def setUp(self):
        super().setUp()
        body = json.dumps({"password": 'say "violet kettle" now'})
        self.curl = "curl --data " + body
        nested = json.dumps({"cmd": self.curl})
        self.deep = body
        for _ in range(7):                       # a document in a document in a document... seven deep
            self.deep = json.dumps({"cmd": self.deep})
        jl(self.logs / "transcript.jsonl", [
            {"timestamp": at(0), "type": "assistant", "sessionId": "tr-j", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"cmd": self.curl}}]}},
            {"timestamp": at(1), "type": "user", "sessionId": "tr-j", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": nested}]}},
            {"timestamp": at(2), "type": "user", "sessionId": "tr-j", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t2", "content": '{"p\\u0061ssword": "say violet kettle now"}'}]}},
            {"timestamp": at(3), "type": "attachment", "sessionId": "tr-j", "attachment": {
                "type": "hook_non_blocking_error", "hookName": "Stop", "hookEvent": "Stop", "exitCode": 1, "stderr": nested}}])
        jl(self.logs / "rollout-j.jsonl", [
            {"timestamp": at(0), "type": "session_meta", "payload": {"id": "rollout-j", "cwd": "/srv/j"}},
            {"timestamp": at(1), "type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
                                                                    "call_id": "c1", "arguments": nested}},
            {"timestamp": at(2), "type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
                                                                    "call_id": "c2", "arguments": self.deep}},
            {"timestamp": at(3), "type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1",
                                                                    "output": json.dumps({"output": self.curl})}}])
        write_json(self.logs / "chat-j.json", {"sessionId": "gem-j", "startTime": at(0), "lastUpdated": at(1), "messages": [
            {"type": "gemini", "content": "All set here", "timestamp": at(1),
             "toolCalls": [{"name": "run", "args": {"cmd": self.curl}, "status": "ok", "result": nested}]}]})
        self.out = self.gather(extra=["--max-chars", "100000"])
        self.masked = '{"cmd": "curl --data {\\"[masked]\\"}"}'     # the request body's credential, the rest as it was

    def test_no_word_of_the_credential_reaches_any_file(self):
        for path, text in written(self.out):
            for word in self.WORDS:
                self.assertNotIn(word, text, f"{path.name} holds {word!r}")

    def test_a_tool_call_a_result_and_a_hook_say_what_they_did_with_the_credential_gone(self):
        transcript = self.transcript(self.out, "tr-j")
        self.assertIn(f" - tool call: Bash({self.masked})  (", transcript)
        self.assertIn(f" - tool result: {self.masked}  (", transcript)
        self.assertIn(' - tool result: {"[masked]"}  (', transcript)   # the key was written password
        self.assertIn(f" - tool result: (exitCode 1) {self.masked}  (", transcript)
        rollout = self.transcript(self.out, "rollout-j")
        self.assertIn(f" - tool call: exec_command({self.masked})  (", rollout)
        self.assertIn(' - tool result: {"output": "curl --data {\\"[masked]\\"}"}  (', rollout)
        chat = self.transcript(self.out, "gem-j")
        self.assertIn(f" - tool call: run({self.masked})  (", chat)
        self.assertIn(f" - tool result: (status ok) {self.masked}  (", chat)

    def test_a_document_seven_deep_is_masked_inside_too(self):
        expected = '{"[masked]"}'
        for _ in range(7):
            expected = json.dumps({"cmd": expected})
        self.assertIn(f" - tool call: exec_command({expected})  (", self.transcript(self.out, "rollout-j"))


# ---------------------------------------------------------------------------- a document in every place a log holds text

class DocumentsEverywhere:
    """Mixin: each document in DOCS -- (a name, the document, the words of the credential in it) -- is put in every
    place a log holds text: a tool result, a hook's output, a record's type, its thinking, its text, its working
    directory, a field that every record carries and one that a record does, a tool call's arguments and its output,
    and a JSON document's own session id and its tool call's result. gather.py is run over them. The test mixed in with LogHome checks that no word of
    any credential reaches any file, and that each document did reach its transcript, masked."""

    DOCS = ()

    def setUp(self):
        super().setUp()
        for name, doc, _ in self.DOCS:
            session = f"s-{name}"
            jl(self.logs / "transcripts" / f"{name}.jsonl", stamped([
                {"type": "user", "sessionId": session, "tag": doc, "cwd": "/" + doc,   # a working directory is a value of a log, too
                 "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": doc}]}},
                {"type": "attachment", "sessionId": session, "tag": doc,
                 "attachment": {"type": "hook_non_blocking_error", "hookName": "Stop", "hookEvent": "Stop", "exitCode": 1, "stderr": doc}},
                {"type": doc, "sessionId": session, "tag": doc},      # a record whose type is a document: a note's label, or none
                {"type": "assistant", "sessionId": session, "tag": doc, "message": {"content": [{"type": "thinking", "thinking": doc}]}},
                {"type": "user", "sessionId": session, "tag": doc, "message": {"content": doc}},
                {"type": doc, "sessionId": session, "tag": doc, "message": {"content": "labelled words"}}]))   # its label is on a line
            jl(self.logs / "rollouts" / f"{name}.jsonl", stamped([
                {"type": "session_meta", "payload": {"id": f"codex-{name}", "cwd": f"/srv/{name}"}},
                {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "c1",
                                                      "label": doc, "arguments": doc}},
                {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1", "output": doc}}]))
            write_json(self.logs / "chats" / f"{name}.json", {
                "sessionId": doc, "startTime": at(0), "lastUpdated": at(1), "messages": [
                    {"type": "gemini", "content": "ok then", "timestamp": at(1),
                     "toolCalls": [{"name": "run", "args": {"n": 1}, "status": "ok", "result": doc}]}]})
        self.out = self.gather()

    def test_no_word_of_any_credential_reaches_any_file(self):
        files = written(self.out)
        self.assertGreater(len(files), 3 * len(self.DOCS))         # a transcript for each of the three logs of each document, and more
        for name, _, words in self.DOCS:
            self.assertIn("[masked]", transcript_of(self.out, f"s-{name}"), name)
            for path, text in files:
                for word in words:
                    self.assertNotIn(word, text, f"{path.name} holds {word!r} (the document {name!r})")


class CutDocumentTest(DocumentsEverywhere, LogHome):
    """Masking comes before the cut to --max-chars. A JSON document longer than the limit, cut first, no
    longer decodes, and a credential under a key written with an escape (p\\u0061ssword) would be shown;
    masked first, the document is decoded to its end and the cut falls on what is already masked."""

    DOC = '{"p\\u0061ssword": "say violet kettle now", "pad": "' + "x" * 3000 + '"}'
    DOCS = (("cut", DOC, ("violet", "kettle")),)

    def test_every_line_cut_from_the_document_shows_it_masked_as_far_as_the_cut_reaches(self):
        shown_ = r'\{"\[masked\]", "pad": "x{100,}'
        cut = r"\.\.\. \[trimmed; full text at "
        group = r"(?: ?\{[^}]*\})?"  # the facts a line may show
        transcript = transcript_of(self.out, "s-cut")
        self.assertRegex(transcript, r"\] user - tool result: " + shown_ + cut)
        self.assertRegex(transcript, r"\] attachment > hook_non_blocking_error" + group + r" - tool result: \(exitCode 1\) " + shown_ + cut)
        self.assertRegex(transcript, r"\] assistant - thinking: " + shown_ + cut)
        self.assertRegex(transcript, r"\] user: " + shown_ + cut)
        self.assertIn("] note: (no type or role)  (raw log line 3)", transcript)   # a document is no label
        rollout = transcript_of(self.out, "codex-cut")  # named by its session record
        self.assertRegex(rollout, r" - tool call: exec_command\(" + shown_ + cut)
        self.assertRegex(rollout, r" - tool result: " + shown_ + cut)
        self.assertRegex(transcript_at(self.out, self.logs / "chats" / "cut.json"), r"\] gemini - tool result: \(status ok\) " + shown_ + cut)


class EveryEscapeTest(DocumentsEverywhere, LogHome):
    """JSON is decoded whatever escapes it uses. A credential the patterns cannot see for an escape in it --
    a slash written \\/ in a URL, a tab, a newline, a return, a form feed or an em space written as an
    escape between "Bearer" and its token -- is found, in an object or an array, in a string alone or one
    that holds a document, in a key, and in what is left of a document cut short. (Decoding used to wait
    for an escaped quote or a \\u00 escape, and a document with any other escape went to the patterns as it
    was written.)"""

    DOCS = (
        ("solidus", '{"url":"https:\\/\\/alice:violetkettle@example.com"}', ("violetkettle",)),
        ("tab", '{"h":"Bearer\\tAbC123xyz789QQ"}', ("AbC123xyz789QQ",)),
        ("newline", '{"h":"Bearer\\nAbC123xyz789QQ"}', ("AbC123xyz789QQ",)),
        ("return", '{"h":"Bearer\\rAbC123xyz789QQ"}', ("AbC123xyz789QQ",)),
        ("formfeed", '{"h":"Bearer\\fAbC123xyz789QQ"}', ("AbC123xyz789QQ",)),
        ("emspace", '{"h":"Bearer\\u2003AbC123xyz789QQ"}', ("AbC123xyz789QQ",)),
        ("string", '"https:\\/\\/alice:violetkettle@example.com"', ("violetkettle",)),
        ("again", json.dumps('{"url":"https:\\/\\/alice:violetkettle@example.com"}'), ("violetkettle",)),     # a result that is a JSON string holding JSON
        ("key", '{"Bearer\\tAbC123xyz789QQ": 1}', ("AbC123xyz789QQ",)),
        ("cut", '{"a": 1, "u": "https:\\/\\/alice:violetkettle@example.com", "b": "xx', ("violetkettle",)),   # a document the log itself cut short
    )


class LaterDocumentTest(DocumentsEverywhere, LogHome):
    """The whole text is masked, then cut. A document that follows one that masking makes shorter -- or a
    run that masking makes eight characters -- slides into what is shown, and it has been read all the same:
    scanning used to stop at where the text would have been cut, measured on the text as it was written."""

    HEAD = json.dumps({"q": '"', "password": "a" * 3000})       # masked, it is a few characters long
    DOCS = (
        ("plain", HEAD + ' {"password":"say violet kettle now"}', ("violet", "kettle")),
        ("escaped", HEAD + ' {"p\\u0061ssword":"say violet kettle now"}', ("violet", "kettle")),
        ("solidus", HEAD + ' {"url":"https:\\/\\/alice:violetkettle@example.com"}', ("violetkettle",)),
        ("run", "A1" * 100_000 + ' {"p\\u0061ssword":"say violet kettle now"}', ("violet", "kettle")),
    )


# ---------------------------------------------------------------------------- a quoted credential, whole

class QuotedCredentialTest(LogHome):
    """A credential in quotes is masked to the quote that closes it: a passphrase of several words does
    not survive as its second word, whichever shape of record carried it, in whichever field."""

    WORDS = ("passphrase", "horse", "battery", "staple", "violet", "kettle")

    def setUp(self):
        super().setUp()
        short, long_, spoken = "short passphrase", "correct horse battery staple", "quiet violet kettle"
        # A user's words, a tool call's input (an object), a tool result, a hook's stderr.
        jl(self.logs / "transcript.jsonl", [
            {"timestamp": at(0), "type": "user", "sessionId": "q-t", "message": {"content": f'use {{"password": "{short}"}} now'}},
            {"timestamp": at(1), "type": "assistant", "sessionId": "q-t", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "login", "password": long_}}]}},
            {"timestamp": at(2), "type": "user", "sessionId": "q-t", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": f'{{"secret": "{spoken}"}}'}]}},
            {"timestamp": at(3), "type": "attachment", "sessionId": "q-t", "attachment": {
                "type": "hook_non_blocking_error", "hookName": "Stop", "hookEvent": "Stop", "exitCode": 1,
                "stderr": f"token = '{long_}'"}}])
        # A function call whose arguments are JSON holding a shell command that holds JSON.
        arguments = json.dumps({"cmd": f"curl -d '{json.dumps({'password': short})}' http://localhost"})
        jl(self.logs / "rollout-q.jsonl", [
            {"timestamp": at(0), "type": "session_meta", "payload": {"id": "rollout-q", "cwd": "/srv/q"}},
            item(at(1), {"type": "UserMessage", "id": uid(2), "content": text_blocks(f'password: "{spoken}"')}),
            {"timestamp": at(2), "type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
                                                                    "call_id": "c1", "arguments": arguments}}])
        # A tool call's arguments (an object) and its result.
        write_json(self.logs / "chat-q.json", {"sessionId": "gem-q", "startTime": at(0), "lastUpdated": at(1), "messages": [
            {"type": "gemini", "content": "All set here", "timestamp": at(1),
             "toolCalls": [{"name": "login", "args": {"api_key": spoken}, "status": "ok", "result": f"password='{long_}'"}]}]})
        self.out = self.gather()

    def test_no_word_of_any_credential_reaches_any_file(self):
        for path, text in written(self.out):
            for word in self.WORDS:
                self.assertNotIn(word, text, f"{path.name} holds {word!r}")

    def test_the_lines_are_still_there_with_a_marker_where_the_credential_was(self):
        transcript = self.transcript(self.out, "q-t")
        self.assertIn('] user: use {"[masked]"} now  (', transcript)
        self.assertIn(' - tool call: Bash({"command": "login", "[masked]"})  (', transcript)
        self.assertIn(" - tool result: (exitCode 1) [masked]'  (", transcript)
        self.assertIn(' - tool result: {"[masked]"}  (', transcript)
        self.assertIn('UserMessage: [masked]"  (', self.transcript(self.out, "rollout-q"))
        self.assertIn(" - tool result: (status ok) [masked]'  (", self.transcript(self.out, "gem-q"))

    def test_the_writer_masks_a_quoted_credential_in_a_name_no_field_masker_saw(self):
        if os.name == "nt":
            self.skipTest("a quote and a colon cannot be in a file name here")
        # The raw log's own path reaches the files only through the writer.
        jl(self.logs / 'proj-password: "short passphrase"' / "named.jsonl", [
            {"timestamp": at(0), "type": "user", "sessionId": "q-named", "message": {"content": "hi"}}])
        out = self.gather()
        self.assertEqual(self.session_ids(out) & {"q-named"}, {"q-named"})
        for path, text in written(out):
            self.assertNotIn("passphrase", text, path.name)


# ---------------------------------------------------------------------------- no record aborts a run

class NoRecordAbortsTest(LogHome):
    """A log is data, and some of it will be odd: valid JSON that decodes to a lone surrogate, a
    number of thousands of digits, a nesting deeper than the stack. None of it may abort a run or cost
    a file its good records."""

    DEEP = "[" * 1_000_000                     # deeper than the stack a process is usually given
    HUGE = '{"type": "user", "sessionId": "x", "big": ' + "1" * 5000 + ', "message": {"content": "big number"}}'
    # (a ValueError on Python 3.11 and later; a record like any other before that)

    @staticmethod
    def fate(text):
        """The note label for a line that json cannot decode, as this interpreter's json says (None if it can)."""
        try:
            json.loads(text)
        except json.JSONDecodeError:
            return "unparseable line"
        except (ValueError, RecursionError) as exc:
            return f"unparseable line ({exc.__class__.__name__})"
        return None

    def raw_lines(self, path, lines):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")

    def test_a_lone_surrogate_in_any_field_is_written_as_text_not_raised(self):
        # json.dumps writes the surrogate as the escape \ud800, which is valid JSON and decodes to a lone one.
        jl(self.logs / "transcript.jsonl", [
            {"timestamp": at(0), "type": "user", "sessionId": "tr-\ud800", "cwd": "/srv/x-\ud800",
             "message": {"content": "hello \ud800 there"}},
            {"timestamp": at(1), "type": "future-\ud800", "sessionId": "tr-\ud800"},
            {"timestamp": at(2), "type": "attachment", "sessionId": "tr-\ud800", "attachment": {
                "type": "hook_success", "hookName": "Stop-\ud800", "hookEvent": "Stop", "stdout": "ok \ud800"}}])
        jl(self.logs / "rollout-s.jsonl", [
            {"timestamp": at(0), "type": "session_meta", "payload": {"id": "rollout-s", "cwd": "/srv/y-\ud800"}},
            {"timestamp": at(1), "type": "event_msg", "payload": {"type": "future-\ud800"}},
            item(at(2), {"type": "UserMessage", "id": uid(2), "content": text_blocks("still here")})])
        write_json(self.logs / "chat-s.json", {"sessionId": "gem-\ud800", "startTime": at(0), "lastUpdated": at(1), "messages": [
            {"type": "future-\ud800", "content": "x", "timestamp": at(0)}, {"type": "user", "content": "gem words", "timestamp": at(1)}]})
        out = self.gather()
        # Written, the surrogate is the six characters of its escape.
        transcript = transcript_of(out, "tr-\\ud800")
        self.assertIn(": hello \\ud800 there  (", transcript)
        self.assertIn("] note: future-\\ud800  (raw log line 2)", transcript)
        self.assertIn(" - tool result: ok \\ud800  (", transcript)
        self.assertIn(": still here  (", transcript_of(out, "rollout-s"))
        self.assertIn("] user: gem words  (", transcript_of(out, "gem-\\ud800"))
        self.assertTrue((out / "workspace.md").is_file())
        self.assertEqual(len(self.session_ids(out)), 3)

    @unittest.skipUnless(os.name == "posix", "file names are arbitrary bytes only on POSIX")
    def test_a_path_with_bytes_that_are_not_utf8_is_printed_and_written_not_raised(self):
        # A file name can hold any byte; Python reads one it cannot decode as a lone surrogate (here \udcff).
        missing = Path(os.fsdecode(bytes(self.root) + b"/no-such-\xff"))
        out = self.root / "odd-path-run"
        r = run_gather_script([self.logs, missing, "--since", "2000-01-01", "--out", out])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no-such-\\udcff: not found", r.stdout)
        self.assertIn("no-such-\\udcff: not found", (out / "index.md").read_text(encoding="utf-8"))

    def test_a_line_that_cannot_be_decoded_costs_a_file_that_line_and_no_more(self):
        good1 = json.dumps({"timestamp": at(0), "type": "user", "sessionId": "tr-bad", "message": {"content": "first words"}})
        good2 = json.dumps({"timestamp": at(1), "type": "assistant", "sessionId": "tr-bad",
                            "message": {"content": [{"type": "text", "text": "last words"}]}})
        self.raw_lines(self.logs / "transcript-bad.jsonl", [good1, self.HUGE, self.DEEP, good2])
        self.raw_lines(self.logs / "rollout-bad.jsonl", [
            json.dumps({"timestamp": at(0), "type": "session_meta", "payload": {"id": "rollout-bad", "cwd": "/srv/a"}}),
            self.HUGE, self.DEEP, json.dumps(item(at(1), {"type": "UserMessage", "id": uid(2), "content": text_blocks("rollout words")}))])
        self.raw_lines(self.logs / "chat-bad.jsonl", [
            json.dumps({"sessionId": "gem-bad", "startTime": at(0)}),
            json.dumps({"id": uid(3), "type": "user", "content": "gem first", "timestamp": at(1)}), self.HUGE, self.DEEP,
            json.dumps({"id": uid(4), "type": "user", "content": "gem last", "timestamp": at(2)})])
        (self.logs / "undecodable.json").write_text(self.DEEP)  # a document that is one undecodable value
        # Whether the nest is too deep for the decoder depends on the stack, which gather inherits from this
        # process: a RecursionError here is one there, and a stack deep enough to read it leaves json's own error.
        deep, huge = self.fate(self.DEEP), self.fate(self.HUGE)
        out = self.gather()
        transcript = transcript_of(out, "tr-bad")
        self.assertIn("] user: first words  (", transcript)
        self.assertIn("] assistant: last words  (", transcript)
        self.assertIn(deep, transcript)
        self.assertIn("UserMessage: rollout words  (", transcript_of(out, "rollout-bad"))
        chat = transcript_of(out, "gem-bad")
        self.assertIn("] user: gem first  (", chat)
        self.assertIn("] user: gem last  (", chat)
        self.assertIn(deep, chat)
        if huge:
            self.assertIn(huge, transcript)
        # Records are the lines that decoded to an object: the two good ones, and the big-number one where json can read it.
        self.assertEqual(cells_of(out, "tr-bad")[5], str(2 + (huge is None)))
        # The document that is one undecodable value is a file not read, with the reason, not a failed run.
        document_error = "RecursionError" if deep == "unparseable line (RecursionError)" else "JSONDecodeError"
        self.assertEqual(places_of(out), [
            f"{self.logs}: 4 record file(s); 3 session(s) in the window; 1 not read, not a JSON document ({document_error}) "
            f"(e.g. {self.logs / 'undecodable.json'})"])


# ---------------------------------------------------------------------------- transcript names

class TranscriptNamesTest(LogHome):
    """The index links every transcript by its name, and the writer masks every line it writes, the index
    included. A name taken from a log -- a session id can be a long, mixed run like a token -- would be
    written to the index masked and to disk as it was: the link would lead nowhere. So a name is made
    of a short hash of the raw log's path, which masking cannot touch."""

    IDS = ("short", "session-" + "q" * 26 + "7", uid(1), "x9" * 40, "Zk9mQ2vDzX7bR4sT1pL8n" * 2,
           "id with spaces/and:odd*chars", "gh" + "p_" + "a" * 30)  # the last assembled at run time: nothing secret-shaped is committed

    def setUp(self):
        super().setUp()
        for n, session_id in enumerate(self.IDS):
            jl(self.logs / "proj" / f"s{n}.jsonl", [
                {"timestamp": at(n), "type": "user", "sessionId": session_id, "message": {"content": f"hello {n}"}}])
        # A harness's subagent can carry its parent's session id; two raw logs, two transcripts.
        jl(self.logs / "proj" / "s1" / "subagents" / "agent-aaa.jsonl", [
            {"timestamp": at(9), "type": "user", "sessionId": self.IDS[1], "isSidechain": True, "message": {"content": "subtask"}}])
        self.out = self.gather()

    def links(self, out=None):
        return [(cells[11], link_of(cells)) for cells in index_rows(out or self.out)]

    def test_every_link_in_the_index_leads_to_a_transcript_that_exists(self):
        links = [link for _, link in self.links()]
        self.assertEqual(len(links), len(self.IDS) + 1)
        self.assertEqual(len(set(links)), len(links))
        for link in links:
            self.assertTrue((self.out / link).is_file(), link)
        self.assertEqual(sorted(p.name for p in (self.out / "sessions").iterdir()), sorted(Path(l).name for l in links))

    def test_a_name_is_s_and_a_short_hash_that_the_writer_leaves_alone(self):
        for _, link in self.links():
            self.assertRegex(link, r"^sessions/s-[0-9a-f]{12}\.md$")
            self.assertEqual(gather.mask_written(link), link)

    def test_the_same_raw_logs_get_the_same_names_on_another_run(self):
        self.assertEqual(sorted(self.links()), sorted(self.links(self.gather())))

    def test_an_id_that_is_a_credential_reaches_no_file(self):
        for path, text in written(self.out):
            for secret in (self.IDS[-1], self.IDS[4], "x9" * 40):
                self.assertNotIn(secret, text, path.name)


# ---------------------------------------------------------------------------- notes, in isolation

def second(n):
    """The n-th second of 2026, as gather.py holds a record's time."""
    return dt.datetime(2026, 1, 1, 0, 0, n, tzinfo=UTC)


class NoteRunTest(unittest.TestCase):
    """How notes become lines, on every shape of run, without any log files."""

    def session(self):
        return gather.Session(Path("raw.jsonl"), Path("."))

    def lines(self, s):
        return [line for _, line in gather.session_lines(s)]

    def test_a_single_note_has_no_count_and_no_end_time(self):
        s = self.session()
        s.note(second(1), "type=a", ("line", 5))
        self.assertEqual(self.lines(s), ["[2026-01-01T00:00:01+00:00] note: type=a  (raw log line 5)"])

    def test_consecutive_notes_of_one_type_are_one_line_with_a_count_and_their_range(self):
        s = self.session()
        for sec, n in ((1, 5), (2, 6), (9, 9)):
            s.note(second(sec), "type=a", ("line", n))
        self.assertEqual(self.lines(s), [
            "[2026-01-01T00:00:01+00:00] note: type=a x3 through 2026-01-01T00:00:09+00:00  (raw log lines 5-9)"])

    def test_interleaved_types_keep_first_appearance_order_and_per_type_counts(self):
        s = self.session()
        for label, n in (("type=a", 1), ("type=b", 2), ("type=a", 3), ("type=c", 4), ("type=b", 5)):
            s.note(second(0), label, ("line", n))
        self.assertEqual(self.lines(s), [
            "[2026-01-01T00:00:00+00:00] note: type=a x2, type=b x2, type=c  (raw log lines 1-5)"])

    def test_a_rendered_entry_ends_the_run(self):
        s = self.session()
        s.note(second(1), "type=a", ("line", 1))
        s.entries.append(gather.Entry("2026-01-01T00:00:02+00:00", "", "hello", "raw.jsonl:2", label="user"))
        s.note(second(3), "type=a", ("line", 3))
        self.assertEqual(self.lines(s), [
            "[2026-01-01T00:00:01+00:00] note: type=a  (raw log line 1)",
            "[2026-01-01T00:00:02+00:00] user: hello  (raw.jsonl:2)",
            "[2026-01-01T00:00:03+00:00] note: type=a  (raw log line 3)"])

    def test_notes_without_timestamps_use_the_first_stamp_there_is(self):
        s = self.session()
        s.note(None, "type=a", ("line", 1))
        s.note(None, "type=b", ("line", 2))
        s.note(second(5), "type=a", ("line", 3))
        self.assertEqual(self.lines(s), [
            "[2026-01-01T00:00:05+00:00] note: type=a x2, type=b  (raw log lines 1-3)"])
        t = self.session()
        t.note(None, "unparseable line", ("line", 7))
        self.assertEqual(self.lines(t), ["[] note: unparseable line  (raw log line 7)"])

    def test_records_and_the_whole_file_are_located_by_their_own_words(self):
        s = self.session()
        s.note(None, "type=info", ("msg", 1))
        s.note(None, "type=info", ("msg", 3))
        s.entries.append(gather.Entry("", "", "ok", "raw.json record 4", label="agent"))
        s.note(None, "unreadable session file", None)
        self.assertEqual(self.lines(s), [
            "[] note: type=info x2  (raw log records 1-3)",
            "[] agent: ok  (raw.json record 4)",
            "[] note: unreadable session file  (raw log)"])

    def test_a_run_of_raw_lines_and_record_numbers_keeps_the_range_of_each_in_the_order_they_appear(self):
        s = self.session()
        s.note(None, "unparseable line", ("line", 2))
        s.note(None, "type=info", ("msg", 0))
        s.note(None, "unparseable line", ("line", 9))
        s.note(None, "type=info", ("msg", 3))
        t = self.session()
        t.note(None, "type=info", ("msg", 4))
        t.note(None, "unparseable line", ("line", 7))
        self.assertEqual(self.lines(s), ["[] note: unparseable line x2, type=info x2  (raw log lines 2-9, records 0-3)"])
        self.assertEqual(self.lines(t), ["[] note: type=info, unparseable line  (raw log record 4, line 7)"])

    def test_a_whole_file_note_in_a_run_keeps_its_place_beside_the_ranges(self):
        s = self.session()
        s.note(None, "unrecognized shape", None)
        s.note(None, "type=info", ("msg", 1))
        s.note(None, "type=info", ("msg", 2))
        self.assertEqual(self.lines(s), [
            "[] note: unrecognized shape, type=info x2  (raw log records 1-2, whole file)"])

    def test_a_label_built_from_log_content_is_masked_and_bounded(self):
        s = self.session()
        s.note(None, "type=" + "gh" + "p_" + "a" * 30 + "x" * 500, ("line", 1))
        text = self.lines(s)[0]
        self.assertNotIn("gh" + "p_", text)
        self.assertLess(len(text), 400)


# ---------------------------------------------------------------------------- the suite's own git

class GitIsolationTest(unittest.TestCase):
    """The git these tests run ignores the developer's global configuration, whatever it says."""

    def test_a_global_setting_that_would_break_every_commit_does_not_reach_the_suites_git(self):
        tmp = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        hostile = tmp / "gitconfig"
        hostile.write_text(f"[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = {(tmp / 'no-such-signer').as_posix()}\n")
        repo = tmp / "repo"
        repo.mkdir()
        identity = ["-c", "user.name=a", "-c", "user.email=a@b"]
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(hostile)}):
            git(repo, "init", "-q", "-b", "main")
            (repo / "f").write_text("x")
            git(repo, "add", "f")
            # The control: the same commit, with that configuration in force, cannot be made.
            bitten = subprocess.run(["git", "-C", str(repo), *identity, "commit", "-qm", "init"],
                                    capture_output=True, text=True, env=dict(os.environ))
            self.assertNotEqual(bitten.returncode, 0, "the hostile configuration should have broken this commit")
            git(repo, *identity, "commit", "-qm", "init")


# ---------------------------------------------------------------------------- masking, by function

class MaskingTest(unittest.TestCase):
    """mask() must not turn ordinary words into false positives, and must not leave real
    secret-shaped strings or evidence-destroying hex runs on the wrong side of the line."""

    def test_does_not_mask_ordinary_hyphenated_words(self):
        self.assertEqual(gather.mask("Add a task-management-system module"), "Add a task-management-system module")
        self.assertEqual(gather.mask("ask-for-confirmation-first"), "ask-for-confirmation-first")
        self.assertEqual(gather.mask("Use bearer authentication"), "Use bearer authentication")

    def test_leaves_a_bare_git_sha_or_sha256_digest_unmasked(self):
        sha1 = "a1b2c3d4" * 5  # 40 hex chars
        sha256 = "a1b2c3d4" * 8  # 64 hex chars
        self.assertIn(sha1, gather.mask(f"commit {sha1}"))
        self.assertIn(sha256, gather.mask(f"digest {sha256}"))

    def test_masks_real_secret_shapes(self):
        cases = [
            "Authorization: Bearer " + "sk-" + "ant-abc123def456",
            "gh" + "p_" + "a1b2c3" * 5,
            "glpat-" + "aB3cD4eF5gH6iJ7kL8m9",
            "AIza" + "SyDaB3cD4eF5gH6iJ7kL8mN9oP0qR1sT2uX",
            "Authorization: Ba" + "sic QWxhZGRpbjpvcGVuc2VzYW1lMTIz",
            'password: "hunter22"',
        ]
        for text in cases:
            self.assertIn("[masked]", gather.mask(text), text)

    def test_masks_json_shaped_credentials_in_every_way_they_are_written(self):
        # The closing quote sits between the key and the colon, and may itself be escaped (JSON inside a
        # JSON string, as a tool call's arguments are); the key may continue a longer, joined name. The value
        # is put together here, since secret scanners take a credential's name beside one for a leak.
        value = "abcdef" + "123456"
        for text in ('{"password": "hunter22"}', '{"password":"hunter22"}', '{\\"password\\": \\"hunter22\\"}',
                     "{'password': 'hunter22'}", f'{{"client_secret": "{value}"}}', f'{{"access_token":"{value}"}}',
                     f'{{"api_key": "{value}"}}', f'{{"x-api-key": "{value}"}}', 'DB_PASSWORD=hunter22',
                     f"export GITHUB_TOKEN={value}", '{"password": 12345678}'):
            out = gather.mask(text)
            self.assertNotIn("hunter22", out, text)
            self.assertNotIn("abcdef123456", out, text)
            self.assertNotIn("12345678", out, text)
            self.assertIn("[masked]", out, text)

    def test_masks_the_whole_of_a_quoted_credential_even_with_spaces_in_it(self):
        # A quoted value runs to the quote that closes it, however many words that makes; the text
        # around it stays. (Expected by hand: the key and its quotes up to the value's last character
        # become one marker, the closing quote and what follows stay.)
        cases = {
            '{"password": "short passphrase"}': '{"[masked]"}',
            '{"password": "correct horse battery staple"}': '{"[masked]"}',
            "{'password': 'correct horse battery staple'}": "{'[masked]'}",
            "password = 'correct horse battery staple' # kept": "[masked]' # kept",
            '{"password": "it\'s a secret phrase", "user": "bob"}': '{"[masked]", "user": "bob"}',
            '{"password": "say \\"hello there\\" now"}': '{"[masked]"}',
            '{\\"password\\": \\"short passphrase\\"}': '{\\"[masked]\\"}',
            '{"api_key": "two words here", "n": 1}': '{"[masked]", "n": 1}',
            'TOKEN: "one two three"': '[masked]"',
            # No closing quote on the line: the value is taken to run to the end of it, and no further.
            '{"password": "correct horse battery staple': '{"[masked]',
            'token: "abc def ghi\nnext line stays': '[masked]\nnext line stays',
        }
        for text, expected in cases.items():
            self.assertEqual(gather.mask(text), expected, text)
            self.assertEqual(gather.mask_known(text), expected, text)

    def test_a_quoted_credential_is_masked_whole_however_deep_the_json_around_it_is(self):
        # JSON inside a JSON string, inside another, and so on, as a tool call's arguments hold a command
        # that holds a request body: each level escapes every quote (and backslash) of the one inside it.
        def escaped(text, levels):
            for _ in range(levels):
                text = json.dumps(text)[1:-1]
            return text
        for levels in range(6):
            text = escaped('{"password": "say \\"violet kettle\\" now", "user": "bob"}', levels)
            expected = escaped('{"', levels) + "[masked]" + escaped('", "user": "bob"}', levels)
            self.assertEqual(gather.mask(text), expected, levels)
            self.assertEqual(gather.mask_known(text), expected, levels)

    def test_json_in_a_string_is_masked_as_the_values_it_holds(self):
        # The reviewer's shape: a command that carries a request body whose value has quotes of its own.
        body = json.dumps({"password": 'say "violet kettle" now'})
        command = json.dumps({"cmd": "curl --data " + body})
        self.assertEqual(gather.mask(command), '{"cmd": "curl --data {\\"[masked]\\"}"}')
        self.assertEqual(gather.mask({"cmd": "curl --data " + body}), '{"cmd": "curl --data {\\"[masked]\\"}"}')
        self.assertEqual(gather.mask(["run", {"cmd": "curl --data " + body}]), '["run", {"cmd": "curl --data {\\"[masked]\\"}"}]')
        # Around other text, as a tool call renders its arguments.
        self.assertEqual(gather.mask(f"exec_command({command}) status=ok"), 'exec_command({"cmd": "curl --data {\\"[masked]\\"}"}) status=ok')
        # A document inside a document, as deep as it goes.
        deep, expected = body, '{"[masked]"}'
        for _ in range(9):
            deep, expected = json.dumps({"cmd": deep}), json.dumps({"cmd": expected})
        self.assertEqual(gather.mask(deep), expected)
        # An array holds the string as well as an object does.
        self.assertEqual(gather.mask(json.dumps(["x", "curl --data " + body])), '["x", "curl --data {\\"[masked]\\"}"]')
        # A key written with an escape is the key it names.
        self.assertEqual(gather.mask('{"p\\u0061ssword": "say violet kettle now"}'), '{"[masked]"}')

    def test_objects_and_arrays_inside_one_another_are_each_masked_once_whichever_way_they_nest(self):
        text = '{"a": {"password": "say violet kettle now"}, "b": ["x", {"token": "one two three"}], "q": "say \\"hi\\""}'
        self.assertEqual(gather.mask(text), '{"a": {"[masked]"}, "b": ["x", {"[masked]"}], "q": "say \\"hi\\""}')
        body = json.dumps({"password": 'say "violet kettle" now'})
        deep, expected = body, '{"[masked]"}'
        for _ in range(9):                      # an array holding a string that is an array holding a string...
            deep, expected = json.dumps(["x", deep]), json.dumps(["x", expected])
        self.assertEqual(gather.mask(deep), expected)
        self.assertEqual(gather.mask(["x", deep]), json.dumps(["x", expected]))
        self.assertEqual(gather.mask({"k": deep}), json.dumps({"k": expected}))

    def test_a_text_is_masked_before_it_is_cut(self):
        doc = '{"p\\u0061ssword": "say violet kettle now", "pad": "' + "x" * 3000 + '"}'
        for shown in (gather.trim(doc, 2000, "r"), gather.trim("exec_command(" + doc + ")", 2000, "r"), gather.safe_label(doc)):
            self.assertNotIn("violet", shown)
            self.assertIn('"[masked]", "pad": "x', shown)
        # By hand: the masked document begins {"[masked]", "pad": " -- 21 characters -- and the cut keeps 40.
        self.assertEqual(gather.safe_label(doc, 40), '{"[masked]", "pad": "' + "x" * 19 + "...")
        # What the cut leaves of text that was not cut is what it was. A text is cut only if what masking leaves
        # of all of it, spaces gone, is longer than the limit: one that fits is shown whole, and says nothing.
        self.assertEqual(gather.trim('{"a": 1}', 2000, "r"), '{"a": 1}')
        self.assertEqual(gather.trim("a" + " " * 5000 + "b", 2000, "r"), "a b")
        # A run of 200,000 characters masked is eight, and the document far behind it is in what is shown, masked
        # (by hand: the run is [masked]; the key, written \u0061, is password, and its value goes with it).
        self.assertEqual(gather.trim("A1" * 100_000 + ' {"p\\u0061ssword":"say violet kettle now"}', 2000, "r"), '[masked] {"[masked]"}')

    def test_a_document_is_decoded_wherever_it_is_in_a_text_and_however_long_it_is(self):
        # The review's cases, by hand: a document with a million characters after it, before it, or in it is
        # read as the values it holds, whatever hides its credential from the patterns (a slash, a tab, or a
        # letter of its key written as an escape).
        million = " x" * 500_000
        doc, masked = '{"url":"https:\\/\\/alice:violetkettle@example.com"}', '{"url": "https://[masked]@example.com"}'
        key = '{"p' + "\\" + 'u0061ssword":"violetkettle"}'                  # "password" with its a escaped
        self.assertEqual(gather.mask(key + million), '{"[masked]"}' + million)
        self.assertEqual(gather.mask(doc + million), masked + million)
        self.assertEqual(gather.mask(million + doc), million + masked)
        for text, shown in ((doc, masked), ('{"h":"Bearer\\tAbC123xyz789QQ"}', '{"h": "[masked]"}')):
            self.assertTrue(gather.trim(text + million, 100, "r").startswith(shown + " x x"), text)
        self.assertTrue(gather.mask(doc[:-1] + ',"pad":"' + million + '"}').startswith(masked[:-1] + ', "pad": " x x'))

    def test_json_is_decoded_whatever_escapes_it_uses_or_none(self):
        # By hand: a document is read as the values it holds and written again, where something in it was
        # masked, with ": " and ", " between its parts. URL_CREDS takes the userinfo of a URL; a bearer token is
        # the word, white space (a tab, a newline, a return, a form feed and an em space are all white space) and a
        # run of ten or more characters with a digit in them.
        self.assertEqual(gather.mask('{"url":"https:\\/\\/alice:violetkettle@example.com"}'), '{"url": "https://[masked]@example.com"}')
        for escape in ("\\t", "\\n", "\\r", "\\f", "\\u2003", "\\u0020", " "):
            self.assertEqual(gather.mask('{"h":"Bearer' + escape + 'AbC123xyz789QQ"}'), '{"h": "[masked]"}', escape)
        # With no escape in it at all, a document is decoded, too.
        self.assertEqual(gather.mask('{"a":1,"password":"say violet kettle now","b":[1,2]}'), '{"a": 1, "[masked]", "b": [1, 2]}')
        # A string with an escape in it is read alone, or as a result that is a document encoded again; so is a key,
        # and so is the last whole string of a document the log cut short.
        self.assertEqual(gather.mask('"https:\\/\\/alice:violetkettle@example.com"'), '"https://[masked]@example.com"')
        again = json.dumps('{"url":"https:\\/\\/alice:violetkettle@example.com"}')
        self.assertEqual(gather.mask(again), '"{\\"url\\": \\"https://[masked]@example.com\\"}"')
        self.assertEqual(gather.mask("result: " + again + " done"), 'result: "{\\"url\\": \\"https://[masked]@example.com\\"}" done')
        self.assertEqual(gather.mask('{"Bearer\\tAbC123xyz789QQ": 1}'), '{"[masked]": 1}')
        self.assertEqual(gather.mask('{"a": 1, "u": "https:\\/\\/alice:violetkettle@example.com", "b": "xx'),
                         '{"a": 1, "u": "https://[masked]@example.com", "b": "xx')
        # A string with no escape is the patterns' to read, and what they leave is left as it was written.
        for text in ('say "hello" and "bye" {x} [y]', 'print("a\\tb"); x = "plain"; y = "c\\nd"', '"\\d+\\s"'):
            self.assertEqual(gather.mask(text), text)
        # An escape far past anything that is shown changes nothing about what is shown.
        shown = gather.trim('{"a":1,"password":"say violet kettle now"} ' + "x" * 5000 + ' \\" ', 2000, "r")
        self.assertTrue(shown.startswith('{"a": 1, "[masked]"} xxxx'), shown[:60])

    def test_brackets_that_look_like_json_and_are_not_end_the_search_only_when_they_pile_up(self):
        doc, masked = '{"url":"https:\\/\\/alice:violetkettle@example.com"}', '{"url": "https://[masked]@example.com"}'
        miss = '{"a": x} '                     # a key and its colon, as JSON begins, and then not JSON
        few = miss * (gather.JSON_MISSES // 2)  # far more than fifty, which used to end the look
        self.assertEqual(gather.mask(few + doc), few + masked)
        many = miss * (2 * gather.JSON_MISSES)
        self.assertEqual(gather.mask(many + doc), many + doc)      # given up on: the patterns alone read the rest
        # Nesting too deep for the decoder to read counts as reading all that follows it.
        deep = "[" * 200_000
        self.assertEqual(gather.mask(deep + " " + doc), deep + " " + doc)
        # What is not a bracket followed by what JSON has after one is no miss at all, and is not tried.
        times = "[12:00:00] note\n" * (3 * gather.JSON_MISSES)
        self.assertEqual(gather.mask(times + doc), times + masked)

    def test_every_document_the_decoder_can_read_is_found_and_what_only_looks_like_one_is_not(self):
        import random
        rnd = random.Random(2026)
        atoms = [0, 1, -1, 3.5, 1e10, 1.5e-7, 1e22, -2.5e-10, True, False, None, float("nan"), float("inf"), float("-inf"), "", "a b", 'q"uote',
                 "back\\slash", "tab\tnew\nline", "caf\u00e9", "[1, 2]", '{"a": 1}', "[", "]", "{", ":", "\x00"]

        def value(depth=0):
            r = rnd.random()
            if depth > 4 or r < 0.4:
                return rnd.choice(atoms)
            if r < 0.7:
                return [value(depth + 1) for _ in range(rnd.randint(0, 4))]
            return {rnd.choice(["a", "key", "", "k k", 'q"', "x\\y"]): value(depth + 1) for _ in range(rnd.randint(0, 4))}

        shapes = [{}, {"indent": 2}, {"indent": 0}, {"separators": (",", ":")}, {"ensure_ascii": False}, {"indent": "\t"}, {"sort_keys": True}]
        for _ in range(2000):
            doc = json.dumps(rnd.choice([[value()], {"k": value()}, [], {}, [value(), value()]]), **rnd.choice(shapes))
            self.assertTrue(gather._JSON_START.match(doc), doc)
        for _ in range(2000):
            string = json.dumps("".join(rnd.choice(["a", " ", "/", "\t", "\n", '"', "\\", "\u00e9", "\u2003", "\x00", "\x1f", "\ud800"]) for _ in range(rnd.randint(0, 8))),
                                ensure_ascii=rnd.random() < 0.5)
            self.assertEqual(bool(gather._JSON_START.match(string)), "\\" in string, string)       # found if there is an escape, not if there is none
        for text in ("[12:00:00]", "[2026-10-01 12:00]", "[type]", "[name] x", "{x}", "[1x", "[1.]", "[01]", "[-]", "[tru]",
                     '{"a" 1}', "{'a': 1}", "x[0:2]", "arr[i]", "[truex]", "[NaNx]", '"\\d"', '"a\\qb"', '"a\\u00zzb"', '"a\\\n"'):
            self.assertIsNone(gather._JSON_START.match(text), text)

    def test_json_with_nothing_to_mask_comes_through_exactly_as_it_was_written(self):
        for text in ('{"a":1,"b":[1,2,{"c":"d"}]}', '[1, 2,  3]', '{"a": "x", "n": null, "t": true}', 'if (x) { y = [1, 2]; } {not json} [also not]',
                     '{"stdout": "{\\"ok\\": true}", "n": 1.50}'):
            self.assertEqual(gather.mask(text), text)

    def test_looking_for_json_in_text_costs_time_in_proportion_to_the_text(self):
        import time
        for text in ("[" * 200_000, "{" * 200_000, '{"a":' * 100_000, "[{" * 100_000, '{"a": 1} ' * 100_000, '["x", ' * 100_000,
                     "[1,x" * 300_000, '{"a": x} ' * 100_000, "[1x" * 300_000, "[12:00:00] x " * 100_000):
            t0 = time.time()
            gather.mask(text)
            self.assertLess(time.time() - t0, 3.0, text[:12])

    def test_the_documents_in_and_after_one_the_log_cut_short_are_decoded_however_deep_it_was_cut(self):
        # By hand: a document cut short forty levels deep is not JSON, and no bracket still open where it was
        # cut begins JSON, but each whole document in it does, and so does one after it.
        item = '{"id": 7, "url": "https:\\/\\/alice:violetkettle@example.com"}'
        cut = '{"a": ' * 39 + "[" + ", ".join([item] * 4000) + ', {"id": 7, '
        shown = gather.mask(cut + 'then {"h":"Bearer\\tAbC123xyz789QQ"}')
        self.assertEqual(shown.count('{"id": 7, "url": "https://[masked]@example.com"}'), 4000)
        self.assertNotIn("violetkettle", shown)
        self.assertTrue(shown.endswith(', {"id": 7, then {"h": "[masked]"}'), shown[-60:])

    def test_an_integer_too_long_for_python_to_convert_does_not_end_the_search(self):
        # The review's case, by hand: a 5,000-digit integer is JSON, though Python will not convert it; read as
        # its digits it costs nothing, and the document after the forty brackets still open is decoded.
        text = "[" * 40 + json.dumps(" x" * 100_000) + "," + "1" * 5000 + ' {"h":"Bearer\\tAbC123xyz789QQ"}'
        self.assertTrue(gather.mask(text).endswith(' {"h": "[masked]"}'))

    def test_finding_the_brackets_still_open_takes_little_memory_however_long_a_string_in_them(self):
        # The review's case: a document whose one string is two million characters long, not closed. Measured:
        # 288 MiB at the peak when a pattern read each string whole.
        import tracemalloc
        text = '{"a":"' + " x" * 1_000_000 + '",'
        tracemalloc.start()
        try:
            gather.mask(text)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 64 * 2**20)

    def test_misses_far_into_a_long_text_cost_time_in_proportion_to_it(self):
        # One miss in every 128 characters of 4 million, as many as the search allows: the decoder's error
        # counts the lines before it, so decoding from the text itself took 13.5 s; a window from the bracket
        # makes each cost what was read.
        import time
        text = ('{"a": x} ' + "y" * 119) * 31_250
        t0 = time.time()
        gather.mask(text)
        self.assertLess(time.time() - t0, 3.0)

    def test_brackets_that_share_a_long_tail_cost_time_in_proportion_to_it(self):
        # Each of 900 brackets nested one in the next has the decoder read all that follows them before it
        # fails: numbers, a string left open, or nulls and then a nest too deep to read. Measured: 17 to 20 s
        # for the first with the previous search, 6.2 s for the second when a bracket still open where a
        # document around it failed was decoded again, and 5.3 s for the third when a nest too deep counted a
        # hundred.
        import time
        for name, text in (("numbers", "[1," * 900 + "1," * 400_000), ("open string", "[1," * 900 + '"' + "a1" * 4_000_000),
                           ("too deep", "[null," * 900 + "null," * 760_000 + "[" * 200_000)):
            t0 = time.time()
            gather.mask(text)
            self.assertLess(time.time() - t0, 3.0, name)

    def test_a_quoted_value_too_short_to_be_a_credential_is_left_alone(self):
        for text in ('{"password": "a b"}', "{'secret': 'x y'}", 'token: ""', '{"token": "ab cd"}'):
            self.assertEqual(gather.mask(text), text)

    def test_a_quote_that_does_not_close_on_its_line_does_not_take_the_next_line_with_it(self):
        text = 'token: "\nthe next line is not a credential\n"'
        self.assertEqual(gather.mask(text), text)

    def test_a_credential_name_and_its_quote_cost_linear_time_even_when_the_quote_never_closes(self):
        # The second text is the worst case for testing a value against its closing quote at every
        # character: 3,000 keys, each opened by a longer run of backslashes than the next, so that none
        # is ever closed by a later one (4.5 million characters; 9 seconds if the run is not capped).
        import time
        worst = "".join("password: " + "\\" * n + '"' for n in range(3000, 0, -1))
        for text in ('password: "' + "word " * 60_000, worst):
            t0 = time.time()
            gather.mask(text)
            gather.mask_known(text)
            self.assertLess(time.time() - t0, 3.0, text[:20])

    def test_does_not_mask_what_only_looks_like_a_credential_name(self):
        for text in ("X25519Secret::generate(&mut OsRng)", "CancellationToken::new()", "InvalidPassword: failed to fill",
                     "token_count: 1234567", '"max_tokens": 4096', '"password": "abc"', "password-manager: enabled"):
            self.assertEqual(gather.mask(text), text)

    def test_the_writer_masks_every_line_it_writes_by_shape_and_leaves_a_pointer_alone(self):
        tmp = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        token = "gh" + "p_" + "a" * 30
        pointer = "rollout-2026-10-15T09-11-58-" + "01a14055-5d49-7033-a5ee-9c4a77e02fa2.jsonl"  # a run of 64: a date, a UUID, hex words
        target = tmp / "out.md"
        gather.write_text_private(target, f"a header with {token}\nraw log: {tmp}/{pointer}:12\n| cell | {{\"password\": \"hunter22\"}} |\n")
        self.assertEqual(target.read_text(encoding="utf-8").splitlines(), [
            "a header with [masked]", f"raw log: {tmp}/{pointer}:12", '| cell | {"[masked]"} |'])

    def test_a_run_in_a_path_is_kept_only_if_it_is_shaped_like_a_name(self):
        half, other = "Zk9mQ2vDzX7bR4sT1pL8n", "Hy6tG3fE0dC8bA5zY2xW9"  # 21 characters: a word that is a token at 20
        h19 = "Zk9mQ2vDzX7bR4sT1pL"                                    # 19: not a token at 20, but mixed case and digits
        token = half * 2
        uuid = "0199abcd-ef01-7234-8bcd-0123456789ab"
        greek = "-".join(("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa"))  # 56, and a year
        # Words joined by hyphens, underscores, dots, pluses or equals signs, none token-shaped (20 characters or more
        # with a letter and a digit) or random-looking (8 or more mixing upper case, lower case and digits): a name.
        kept = [
            f"/h/.claude/projects/-home-user-agent-tooling--claude-worktrees-heal-gather-2026-q3-roadmap/{uuid}.jsonl:12",
            f"/h/.codex/sessions/2026/10/15/rollout-2026-10-15T09-11-58-{uuid}.jsonl:1",       # a date and a UUID
            f"/h/.gemini/tmp/{'a1b2c3d4' * 8}/chats/session-2026-10-15T10-00-abc12345.json#msg3",   # a sha256: evidence, not a secret
            f"/h/.gemini/tmp/{'a1b2c3d4' * 5}/chats/s.json",                                   # and so is a sha1
            f"/h/.claude/projects/-home-user/{uuid}/subagents/agent-a1b2c3d4e5f6a7b8.jsonl:3",
            f"/h/x/{'-' * 50}/{'a' * 50}/{'7' * 50}",                                          # a uniform run is no token
            f"/h/a-long-prefix-name{uuid}.jsonl",                                              # words, and hex words
            "/h/agent-a1b2c3d4e5f6a7b8-c9d0e1f2a3b4c5d6-e7f8a9b0c1d2e3f4.jsonl",
            f"/h/{greek}-2026.log",
            "/h/job=nightly+branch=main+suite=full+retries=3+shard=2of8.json",                 # 55 characters of short words, joined by = and +
            "/h/.claude/projects/-home-user-agent-tooling-zk9mq2vdzx7br4st1pl/s.jsonl",        # a word of 19, in lower case
            "/h/.claude/projects/-home-user-agent-tooling--claude-worktrees-Zk9mQ2v/s.jsonl",  # mixed case and digits, but 7
            "/h/.claude/projects/-home-user-agent-tooling-repos-zk9mq2vdzx7b/s.jsonl",         # 12, with no upper case
            "/h/.claude/projects/-home-user-agent-tooling-repos-ZK9MQ2VDZX7B/s.jsonl",         # 12, with no lower case
            "/h/.claude/projects/-home-user-agent-tooling-2026-ProjectsFolder/s.jsonl",        # upper and lower case, no digit
        ]
        # A run with a word in it that is one of those is a token, whatever it is joined to, and is masked whole.
        masked = {
            f"/h/{token}/a.jsonl:1": "/h/[masked]/a.jsonl:1",
            f"/h/-home-user-{token}/b.jsonl": "/h/[masked]/b.jsonl",
            f"/h/{half}-{half}/c.jsonl": "/h/[masked]/c.jsonl",                                # a token split at a hyphen
            f"/h/{half}+{other}=/c.jsonl": "/h/[masked]/c.jsonl",                              # ...at a plus and an equals sign
            f"/h/{uuid}-{token}/d.jsonl": "/h/[masked]/d.jsonl",
            f"/h/rollout-2026-10-15T09-11-58-{token}.jsonl": "/h/[masked].jsonl",
            f"/h/rollout-2026-10-15T09-11-58-{uuid}-{token}.jsonl": "/h/[masked].jsonl",
            f"/h/{half}-rollout-2026-10-15T09-11-58-{uuid}.jsonl": "/h/[masked].jsonl",
            f"/h/{'a1b2c3d4' * 6}/e.jsonl": "/h/[masked]/e.jsonl",                              # 48 hex characters: not a sha
            f"/h/{half}a1b2c3d4e5f6a7b8{half}/f.jsonl": "/h/[masked]/f.jsonl",
            f"/logs/{half}2026-10-15{half}/s.jsonl": "/logs/[masked]/s.jsonl",                 # a date does not part two halves
            f"/logs/-home-user-{half}-{half}/s.jsonl": "/logs/[masked]/s.jsonl",
            "/h/.claude/projects/-home-user-agent-tooling-zk9mq2vdzx7br4st1pl8/s.jsonl": "/h/.claude/projects/[masked]/s.jsonl",  # a word of 20
            "/h/.claude/projects/-home-user-agent-tooling-repos-Zk9mQ2vDzX7b/s.jsonl": "/h/.claude/projects/[masked]/s.jsonl",   # a mixed word of 12
            "/h/.claude/projects/-home-user-agent-tooling-repos-Zk9mQ2vDzX7/s.jsonl": "/h/.claude/projects/[masked]/s.jsonl",    # of 11
            "/h/.claude/projects/-home-user-agent-tooling--claude-worktrees-Zk9mQ2vD/s.jsonl": "/h/.claude/projects/[masked]/s.jsonl",   # of 8
            f"/logs/{'-'.join(['Ab3dEf5Gh7'] * 4)}/s.jsonl": "/logs/[masked]/s.jsonl",         # four words of 10, as a name
            f"/logs/-{h19}-{h19}-{h19}/s.jsonl": "/logs/[masked]/s.jsonl",                     # words of 19 that mix case and digits
        }
        tmp = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        target = tmp / "out.md"
        gather.write_text_private(target, "\n".join(kept + list(masked)) + "\n")
        self.assertEqual(target.read_text(encoding="utf-8").split("\n")[:-1], kept + list(masked.values()))

    def test_masking_by_shape_is_the_full_masker_less_its_catch_all(self):
        value = "abcdef" + "123456"                  # put together here, as above
        for text in ("plain words", "Authorization: Bear" + "er abc123def456ghi", "postgres://" + "admin:S3cr3tPassw0rd@host/db",
                     "see sk-" + "a1b2c3d4e5f6a7b8", "x" * 5000, f'a "token": "{value}" b', f"TOKEN: {value}",
                     "https://example.com/path", "a basic outline", "bearer authentication"):
            unfiltered = gather.SPECIFIC_SECRETS.sub("[masked]", gather.URL_CREDS.sub(r"\1[masked]@", text))
            self.assertEqual(gather.mask_known(text), unfiltered, text)

    def test_masks_url_userinfo_credentials(self):
        out = gather.mask("postgres://" + "admin:S3cr3tPassw0rd@host/db")
        self.assertNotIn("S3cr3tPassw0rd", out)
        self.assertIn("postgres://", out)
        self.assertIn("@host/db", out)

    def test_mask_is_not_quadratic_on_a_long_uniform_run(self):
        # A long run of one repeated character (padding, separators, a progress bar) is
        # ordinary build output, not a secret -- and unlike a real secret it has no short
        # literal anchor, so a lookahead- or backtracking-prone pattern degrades to O(n^2) on
        # it specifically. 300k chars comfortably reproduces the multi-second-per-10k blowup
        # this regresses without making a slow test suite even when the fix regresses.
        import time
        for masker in (gather.mask, gather.mask_written):
            for text in ("a" * 300_000, "-" * 300_000, "7" * 300_000, "a1b2c3d4-" * 40_000):
                t0 = time.time()
                masker(text)
                elapsed = time.time() - t0
                self.assertLess(elapsed, 3.0, f"{masker.__name__}() took {elapsed:.2f}s on a uniform run (quadratic regression)")

    def test_trim_masks_the_whole_of_a_huge_text_in_time_in_proportion_to_it(self):
        import time
        # 3 million characters of ordinary words: all of them are read, in time in proportion to them, and what is
        # shown is the first 2,000 of what is left.
        huge = "lorem ipsum 123 dolor sit amet " * 100_000
        t0 = time.time()
        out = gather.trim(huge, 2000, "file:1")
        label = gather.safe_label(huge)
        elapsed = time.time() - t0
        self.assertLess(elapsed, 10.0, f"trim() and safe_label() took {elapsed:.2f}s on a {len(huge):,}-char input")
        self.assertEqual(out, huge[:2000].rstrip() + "... [trimmed; full text at file:1]")
        self.assertEqual(label, huge[:200].rstrip() + "...")

    def test_url_creds_does_not_leak_a_secret_that_straddles_the_trim_cutoff(self):
        # A generic (unprefixed) secret starting well before the cutoff must still be masked
        # even though it, or the text after it, gets cut off by --max-chars.
        text = "prefix " + ("k9mQ2vDzX7bR4sT1pL8n" * 3) + " suffix"  # 60+ chars, digits+letters
        out = gather.trim(text, limit=20, ref="file:1")
        self.assertIn("[masked]", out)


class LaunchdAgentsTest(unittest.TestCase):
    """launchd_agents() only runs its real logic on darwin; sys.platform and Path.home are
    patched to exercise that logic on this (Linux) machine, the way the drift/portability
    reviews did to reach macOS-only code without a Mac."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="launchd-test-"))
        self.agents_dir = self.tmp / "Library" / "LaunchAgents"
        self.agents_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self):
        import unittest.mock as mock
        with mock.patch.object(gather.sys, "platform", "darwin"), \
             mock.patch.object(gather.Path, "home", return_value=self.tmp):
            return gather.launchd_agents()

    def test_truncated_plist_is_a_note_not_a_crash(self):
        (self.agents_dir / "broken.plist").write_bytes(b"<?xml version=\"1.0\"?><plist><dict><key>Label")
        rows, err = self._run()
        self.assertIsNone(err)
        self.assertEqual(len(rows), 1)
        self.assertIn("unreadable plist", rows[0])

    def test_plist_whose_root_is_an_array_is_a_note_not_a_crash(self):
        import plistlib
        (self.agents_dir / "array-root.plist").write_bytes(plistlib.dumps(["not", "a", "dict"]))
        rows, err = self._run()
        self.assertIsNone(err)
        self.assertEqual(len(rows), 1)
        self.assertIn("unexpected plist shape", rows[0])

    def test_well_formed_plist_is_still_read_normally(self):
        import plistlib
        (self.agents_dir / "ok.plist").write_bytes(plistlib.dumps({"Label": "com.example.job", "StartInterval": 3600}))
        rows, err = self._run()
        self.assertIsNone(err)
        self.assertEqual(len(rows), 1)
        self.assertIn("com.example.job", rows[0])



class PureFunctionTest(unittest.TestCase):

    def test_two_raw_logs_whose_hashes_collide_still_get_two_files(self):
        sessions = [gather.Session(Path("a.jsonl"), Path(".")), gather.Session(Path("b.jsonl"), Path(".")),
                    gather.Session(Path("sub/a.jsonl"), Path("."))]
        with mock.patch.object(gather, "short_hash", return_value="0" * 12):
            gather.assign_output_names(sessions)
        self.assertEqual([s.out_name for s in sessions], ["s-000000000000", "s-000000000000-2", "s-000000000000-3"])

    def test_a_name_is_a_short_hash_of_the_raw_logs_path_whatever_the_order_the_sessions_come_in(self):
        def named(paths):
            sessions = [gather.Session(Path(p), Path(".")) for p in paths]
            gather.assign_output_names(sessions)
            return {str(s.path): s.out_name for s in sessions}
        first, second_run = named(["/x/a.jsonl", "/x/b.jsonl"]), named(["/x/b.jsonl", "/x/a.jsonl"])
        self.assertEqual(first, second_run)
        self.assertEqual(len(set(first.values())), 2)
        for name in first.values():
            self.assertRegex(name, r"^s-[0-9a-f]{12}$")

    def test_rel_or_abs_does_not_conflate_sibling_directories(self):
        home = str(Path.home())
        self.assertEqual(gather.rel_or_abs(Path(home)), "~")
        self.assertEqual(gather.rel_or_abs(Path(home + "/sub")), "~/sub")
        # A sibling directory that merely starts with the same characters as $HOME must not be
        # rendered as if it were under $HOME.
        self.assertEqual(gather.rel_or_abs(Path(home + "-other/project")), home + "-other/project")

    def test_parse_when_accepts_trailing_z_and_keeps_a_given_offset(self):
        z = gather.parse_when("2026-01-01T00:00:00Z")
        self.assertEqual(z, gather.dt.datetime(2026, 1, 1, tzinfo=gather.UTC))
        offset = gather.parse_when("2026-01-01T05:00:00+05:00")
        self.assertEqual(offset.astimezone(gather.UTC), gather.dt.datetime(2026, 1, 1, tzinfo=gather.UTC))

    def test_parse_when_takes_a_number_of_days_back_from_now(self):
        before = dt.datetime.now(UTC) - dt.timedelta(days=7)
        parsed = gather.parse_when("7d")
        self.assertTrue(before <= parsed <= dt.datetime.now(UTC) - dt.timedelta(days=7))

    def test_parse_when_rejects_garbage_with_a_clean_error_not_a_traceback(self):
        with self.assertRaises(SystemExit):
            gather.parse_when("not-a-date")

    def test_a_size_is_shown_in_bytes_below_a_kilobyte_and_in_larger_units_with_one_decimal_above(self):
        for size, text in ((0, "0B"), (999, "999B"), (1023, "1023B"), (1024, "1.0KB"), (1536, "1.5KB"),
                           (1024 ** 2, "1.0MB"), (5 * 1024 ** 3, "5.0GB")):
            self.assertEqual(gather.human_size(size), text, size)


if __name__ == "__main__":
    unittest.main()
