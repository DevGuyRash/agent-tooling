import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "review-turn-stop.py"


class ReviewTurnStopTest(unittest.TestCase):
    """The hook asks for one review per Codex turn that changed its repository, and stays silent otherwise."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="review-turn-"))
        self.home = self.tmp / "codex-home"
        self.home.mkdir()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git = ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run(git + ["init", "-q"], check=True)
        (self.repo / "a.txt").write_text("a\n")
        subprocess.run(git + ["add", "a.txt"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "init"], check=True)

    def tearDown(self):
        subprocess.run(["rm", "-rf", str(self.tmp)])

    def stop(self, **payload):
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                           env={**os.environ, "CODEX_HOME": str(self.home)}, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_blocks_once_per_codex_turn_that_changed_the_repository(self):
        (self.repo / "a.txt").write_text("changed\n")
        first = self.stop(turn_id="t1", cwd=str(self.repo))
        self.assertEqual(first["decision"], "block")
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo)))
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo), stop_hook_active=True))
        self.assertEqual(self.stop(turn_id="t2", cwd=str(self.repo))["decision"], "block")

    def test_stays_silent_when_nothing_changed(self):
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(self.repo)))

    def test_stays_silent_outside_a_repository(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        (plain / "notes.txt").write_text("x\n")
        self.assertIsNone(self.stop(turn_id="t1", cwd=str(plain)))

    def test_stays_silent_without_a_codex_turn(self):
        (self.repo / "a.txt").write_text("changed\n")
        self.assertIsNone(self.stop(session_id="s1", cwd=str(self.repo)))


if __name__ == "__main__":
    unittest.main()
