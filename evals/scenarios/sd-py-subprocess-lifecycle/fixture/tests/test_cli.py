import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def steprun(*args):
    """Run the steprun command line and return the completed process (output as bytes)."""
    return subprocess.run([sys.executable, "-m", "steprun", *args], cwd=ROOT, capture_output=True, timeout=60)


def python(code):
    return [sys.executable, "-c", code]


class OutputTest(unittest.TestCase):
    def test_stdout_and_stderr_go_to_their_own_streams(self):
        r = steprun("--", *python("import sys; print('to out'); print('to err', file=sys.stderr)"))
        self.assertEqual(r.stdout, b"to out\n")
        self.assertTrue(r.stderr.startswith(b"to err\n"), r.stderr)

    def test_status_line_uses_label(self):
        r = steprun("--label", "unit", "--", "true")
        self.assertEqual(r.returncode, 0)
        self.assertRegex(r.stderr.decode(), r"^steprun: unit: exited 0 after \d+\.\ds\n$")

    def test_status_line_defaults_to_command_line(self):
        r = steprun("--", "sh", "-c", "exit 0")
        self.assertIn(b"steprun: sh -c 'exit 0': exited 0", r.stderr)


class ExitStatusTest(unittest.TestCase):
    def test_exit_status_is_passed_through(self):
        self.assertEqual(steprun("--", *python("raise SystemExit(3)")).returncode, 3)

    def test_death_by_signal_is_128_plus_signal(self):
        r = steprun("--", *python("import os, signal; os.kill(os.getpid(), signal.SIGKILL)"))
        self.assertEqual(r.returncode, 137)

    def test_timeout_exits_124(self):
        started = time.monotonic()
        r = steprun("--timeout", "0.5", "--grace", "1", "--", "sleep", "10")
        self.assertEqual(r.returncode, 124)
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn(b"steprun: sleep 10: timed out after 0.5s", r.stderr)

    def test_command_not_found(self):
        r = steprun("--", "steprun-no-such-command")
        self.assertEqual(r.returncode, 127)
        self.assertIn(b"command not found", r.stderr)

    def test_command_not_executable(self):
        r = steprun("--", str(ROOT / "README.md"))
        self.assertEqual(r.returncode, 126)

    def test_missing_command_is_a_usage_error(self):
        self.assertEqual(steprun().returncode, 2)
        self.assertEqual(steprun("--timeout", "5").returncode, 2)


if __name__ == "__main__":
    unittest.main()
