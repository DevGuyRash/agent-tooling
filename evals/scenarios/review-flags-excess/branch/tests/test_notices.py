import tempfile
import unittest
from pathlib import Path
from unittest import mock

from toolroom.models import Member
from toolroom.notices import render_notice, write_notice, write_notices
from toolroom.overdue import Overdue

BRAM = Member("M-1", "Bram Okafor", "standard")
ROWS = [
    Overdue("L-2", "M-1", "Bram Okafor", "Cordless drill", 10, 500),
    Overdue("L-1", "M-1", "Bram Okafor", "Tile cutter", 3, 150),
]


class FlakyPath:
    """A path whose first `failures` writes fail."""

    def __init__(self, failures):
        self.failures = failures
        self.text = None

    def write_text(self, text, encoding=None):
        if self.failures:
            self.failures -= 1
            raise OSError("locked")
        self.text = text


class NoticeTest(unittest.TestCase):
    def test_greets_lists_and_totals(self):
        self.assertEqual(
            render_notice(BRAM, ROWS),
            "Dear Bram Okafor,\n\nThese loans are overdue:\n  Cordless drill  10 days  5.00\n  Tile cutter  3 days  1.50\n\nTotal owed: 6.50\n",
        )

    def test_one_notice_per_member_in_a_new_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "notices"
            write_notices(target, ROWS, {"M-1": BRAM})
            self.assertEqual([p.name for p in target.iterdir()], ["M-1.txt"])
            self.assertIn("Total owed: 6.50", (target / "M-1.txt").read_text(encoding="utf-8"))


@mock.patch("toolroom.notices.time.sleep")
class WriteNoticeTest(unittest.TestCase):
    def test_a_locked_file_is_tried_again_a_second_later(self, sleep):
        path = FlakyPath(failures=2)
        self.assertIsNone(write_notice(path, "text"))
        self.assertEqual((path.text, sleep.call_args_list), ("text", [mock.call(1.0), mock.call(1.0)]))

    def test_three_attempts_and_then_the_error(self, sleep):
        path = FlakyPath(failures=5)
        self.assertEqual(str(write_notice(path, "text")), "locked")
        self.assertEqual((path.failures, sleep.call_count), (2, 2))

    def test_a_skipped_notice_is_reported_on_standard_error(self, sleep):
        with mock.patch("toolroom.notices.write_notice", return_value=OSError("locked")), mock.patch("sys.stderr") as err:
            with tempfile.TemporaryDirectory() as tmp:
                write_notices(tmp, ROWS, {"M-1": BRAM})
        self.assertIn("could not write notice for M-1: locked", "".join(c.args[0] for c in err.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
