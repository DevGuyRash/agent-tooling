import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "review-turn-stop.py"


class ReviewTurnStopTest(unittest.TestCase):
    """The hook asks for one review per turn that changed its repository, where the stop event names the turn, and stays
    silent otherwise."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="review-turn-"))
        self.home = self.tmp / "cache-home"
        self.home.mkdir()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.commit("a.txt", "a\n", "2026-01-01T00:00:00+0000")

    def git(self, *args, date=None):
        """git in the fixture repository, with no global or system configuration, and its commits dated `date`."""
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        if date:
            env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                       check=True, env=env)

    def commit(self, name, text, date):
        (self.repo / name).write_text(text)
        self.git("add", name)
        self.git("commit", "-q", "-m", name, date=date)

    def transcript(self, turn, started, *extra):
        """A session transcript, of the shape one harness writes (an event_msg with a task_started payload), in which `turn` began at `started`, with `extra` records after."""
        path = self.tmp / "rollout.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in (
            {"timestamp": "2026-01-01T00:00:01.000Z", "type": "session_meta", "payload": {"id": "s1"}},
            {"timestamp": started, "type": "event_msg", "payload": {"type": "task_started", "turn_id": turn}}, *extra)))
        return str(path)

    def tearDown(self):
        subprocess.run(["rm", "-rf", str(self.tmp)])

    def stop(self, raw=None, **payload):
        r = subprocess.run([sys.executable, str(HOOK)], input=raw if raw is not None else json.dumps(payload),
                           capture_output=True, text=True, env={**os.environ, "XDG_CACHE_HOME": str(self.home)}, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_blocks_once_per_turn_that_changed_the_repository(self):
        (self.repo / "a.txt").write_text("changed\n")
        first = self.stop(turn_id="t1", cwd=str(self.repo))
        self.assertEqual(first["decision"], "block")
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo)))
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), stop_hook_active=True))
        self.assertEqual(self.stop(turn_id="t2", cwd=str(self.repo))["decision"], "block")

    def test_stays_silent_when_nothing_changed(self):
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo)))
        log = self.transcript("t1", "2026-01-01T00:05:00.000Z")  # the only commit predates the turn
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=log))

    def test_stays_silent_outside_a_repository(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        (plain / "notes.txt").write_text("x\n")
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(plain)))

    def test_blocks_once_for_a_turn_that_committed_its_work(self):
        # By hand: the turn began at 00:05 and its commit is from 00:10, so the clean tree hides a change.
        self.commit("b.txt", "b\n", "2026-01-01T00:10:00+0000")
        log = self.transcript("t1", "2026-01-01T00:05:00.565Z")
        self.assertEqual(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=log)["decision"], "block")
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=log))

    def test_stays_silent_when_every_commit_predates_the_turn(self):
        self.commit("b.txt", "b\n", "2026-01-01T00:10:00+0000")
        log = self.transcript("t1", "2026-01-01T00:20:00.000Z")
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=log))

    def test_stays_silent_on_a_clean_tree_when_the_turn_start_cannot_be_read(self):
        self.commit("b.txt", "b\n", "2026-01-01T00:10:00+0000")
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo)))
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=str(self.tmp / "missing.jsonl")))
        other = self.transcript("t0", "2026-01-01T00:05:00.000Z")  # another turn's start is not this turn's
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=other))

    def test_a_commit_in_the_second_before_the_turn_began_is_not_the_turns(self):
        # By hand: git keeps whole seconds, so the commit at 00:05:00 reads as 00:05:00 against a start of 00:05:00.565.
        self.commit("b.txt", "b\n", "2026-01-01T00:05:00+0000")
        log = self.transcript("t1", "2026-01-01T00:05:00.565Z")
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=log))

    def test_work_committed_on_a_detached_head_is_reviewed(self):
        self.git("checkout", "-q", "--detach")
        self.commit("b.txt", "b\n", "2026-01-01T00:10:00+0000")
        log = self.transcript("t1", "2026-01-01T00:05:00.000Z")
        self.assertEqual(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=log)["decision"], "block")

    def test_a_commit_on_another_branch_is_not_this_turns_work(self):
        # Another session's worktree commits on its own branch; this turn, on main, changed nothing.
        self.git("branch", "other")
        self.git("worktree", "add", "-q", str(self.tmp / "other"), "other")
        (self.tmp / "other" / "c.txt").write_text("c\n")
        subprocess.run(["git", "-C", str(self.tmp / "other"), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "c.txt"],
                       check=True, env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        subprocess.run(["git", "-C", str(self.tmp / "other"), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "c"],
                       check=True, env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                                        "GIT_AUTHOR_DATE": "2026-01-01T00:10:00+0000", "GIT_COMMITTER_DATE": "2026-01-01T00:10:00+0000"})
        log = self.transcript("t1", "2026-01-01T00:05:00.000Z")
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=log))

    def test_records_that_only_mention_the_turn_neither_break_the_hook_nor_start_the_turn(self):
        self.commit("b.txt", "b\n", "2026-01-01T00:10:00+0000")
        log = self.tmp / "odd.jsonl"
        log.write_text("".join(json.dumps(r) + "\n" for r in (
            {"timestamp": "2026-01-01T00:05:00.000Z", "payload": ["task_started", "t1"]},
            ["task_started", "t1"],
            {"timestamp": "2026-01-01T00:05:00.000Z", "type": "event_msg", "payload": {"last_agent_message": "turn t1"}},
            {"timestamp": "not a time", "payload": {"turn_id": "t1"}},
            {"payload": {"turn_id": "t1"}})))
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=str(log)))
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path={"not": "a path"}))
        self.assertIsNone(self.stop(raw='["not", "an", "object"]'))

    def test_a_turn_named_in_a_list_or_with_its_own_time_starts_it(self):
        self.commit("b.txt", "b\n", "2026-01-01T00:10:00+0000")
        for records in ([{"timestamp": "2026-01-01T00:05:00.000Z", "events": [{"turn_id": "t1"}]}],
                        [{"event": {"timestamp": "2026-01-01T00:05:00.000Z", "turn_id": "t1"}}]):
            log = self.tmp / "shape.jsonl"
            log.write_text("".join(json.dumps(r) + "\n" for r in records))
            for marker in self.home.rglob(".review-turn-*"):
                marker.unlink()
            self.assertEqual(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=str(log))["decision"], "block")

    def test_a_turn_named_deeper_in_other_content_does_not_start_it(self):
        # An earlier turn's tool result that mentions the next turn is not that turn beginning.
        self.commit("b.txt", "b\n", "2026-01-01T00:03:00+0000")
        log = self.tmp / "ref.jsonl"
        log.write_text("".join(json.dumps(r) + "\n" for r in (
            {"timestamp": "2026-01-01T00:01:00.000Z", "payload": {"output": {"next_turn": {"turn_id": "t1"}}}},
            {"timestamp": "2026-01-01T00:05:00.000Z", "payload": {"turn_id": "t1"}})))
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=str(log)))

    def test_turns_numbered_within_their_session_are_reviewed_in_each_session(self):
        (self.repo / "a.txt").write_text("changed\n")
        self.assertEqual(self.stop(session_id="A", turn_id="1", cwd=str(self.repo))["decision"], "block")
        self.assertIsNone(self.stop(session_id="A", turn_id="1", cwd=str(self.repo)))
        self.assertEqual(self.stop(session_id="B", turn_id="1", cwd=str(self.repo))["decision"], "block")
        # Two pairs whose parts would join to the same text are still two turns.
        self.assertEqual(self.stop(session_id="A-B", turn_id="1", cwd=str(self.repo))["decision"], "block")
        self.assertEqual(self.stop(session_id="A", turn_id="B-1", cwd=str(self.repo))["decision"], "block")

    def test_without_a_usable_cache_directory_the_marker_goes_to_the_temporary_directory(self):
        (self.repo / "a.txt").write_text("changed\n")
        blocked = self.tmp / "file-not-dir"  # a file where the cache directory would be
        blocked.write_text("x")
        temporary = self.tmp / "tmp"
        temporary.mkdir()

        def stop():
            r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"turn_id": "t9", "cwd": str(self.repo)}),
                               capture_output=True, text=True, timeout=30,
                               env={**os.environ, "XDG_CACHE_HOME": str(blocked), "TMPDIR": str(temporary)})
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout.strip()
        self.assertIn('"block"', stop())
        self.assertEqual(stop(), "")
        self.assertEqual(len([p for p in temporary.iterdir() if p.name.startswith(".review-turn-")]), 1)

    def test_with_nowhere_to_keep_a_marker_it_asks_nothing(self):
        # No cache directory and no temporary directory: without a marker the review would be asked at every stop, so
        # it is asked at none. The temporary directory's failure is made in the hook's own process.
        (self.repo / "a.txt").write_text("changed\n")
        blocked = self.tmp / "file-not-dir"
        blocked.write_text("x")
        site = self.tmp / "site"
        site.mkdir()
        (site / "sitecustomize.py").write_text(
            "import tempfile\n"
            "def _none():\n    raise FileNotFoundError('no usable temporary directory')\n"
            "tempfile.gettempdir = _none\n")
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"turn_id": "t8", "cwd": str(self.repo)}),
                           capture_output=True, text=True, timeout=30,
                           env={**os.environ, "XDG_CACHE_HOME": str(blocked), "PYTHONPATH": str(site)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_any_record_naming_the_turn_starts_it_at_its_earliest_time(self):
        # A harness of another shape: the turn named in a turnId field, under a "time". The earliest such record is the
        # turn's start, so the commit at 00:10 is this turn's and the one at 00:03 is not.
        self.commit("b.txt", "b\n", "2026-01-01T00:03:00+0000")
        log = self.tmp / "other.jsonl"
        log.write_text("".join(json.dumps(r) + "\n" for r in (
            {"time": "2026-01-01T00:08:00.000Z", "event": {"kind": "turn.end", "turnId": "t1"}},
            {"time": "2026-01-01T00:05:00.000Z", "event": {"kind": "turn.begin", "turnId": "t1"}})))
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=str(log)))
        self.commit("c.txt", "c\n", "2026-01-01T00:10:00+0000")
        self.assertEqual(self.stop(turn_id="t2", cwd=str(self.repo), transcript_path=str(log)), None)
        self.assertEqual(self.stop(turn_id="t1", cwd=str(self.repo), transcript_path=str(log))["decision"], "block")

    def test_stays_silent_when_the_stop_event_names_no_turn(self):
        (self.repo / "a.txt").write_text("changed\n")
        self.assertIsNone(self.stop(session_id="s1", cwd=str(self.repo)))


if __name__ == "__main__":
    unittest.main()
