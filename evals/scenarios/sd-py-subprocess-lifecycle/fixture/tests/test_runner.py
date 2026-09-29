import sys
import unittest

from steprun.runner import run_step


class RunStepTest(unittest.TestCase):
    def test_captures_both_streams(self):
        r = run_step([sys.executable, "-c", "import sys; sys.stdout.write('a'); sys.stderr.write('b')"])
        self.assertEqual((r.stdout, r.stderr, r.returncode, r.timed_out), (b"a", b"b", 0, False))

    def test_returncode(self):
        self.assertEqual(run_step(["sh", "-c", "exit 7"]).returncode, 7)

    def test_timed_out_step_has_no_returncode(self):
        r = run_step(["sleep", "10"], timeout=0.2, grace=1)
        self.assertTrue(r.timed_out)
        self.assertIsNone(r.returncode)

    def test_duration(self):
        r = run_step(["sleep", "0.2"])
        self.assertGreaterEqual(r.duration, 0.2)
        self.assertLess(r.duration, 5)


if __name__ == "__main__":
    unittest.main()
