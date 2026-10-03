import contextlib
import io
import unittest

from plotkeeper.cli import main


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class RenewalsTests(unittest.TestCase):
    def test_docs_example(self):
        code, out, _ = run("renewals", "--season", "2026")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0], "Renewals for season 2026-27, due by 31 October 2026")
        self.assertEqual(lines[1], "Margaret Hollis: A1, A4, B8, C4: rent £294.25, water £42.00, "
                                   "membership £5.00, total £341.25")
        self.assertIn("Sam Kowalski: A10: rent £45.84, water £6.00, membership £5.00, total £56.84", lines)
        self.assertEqual(lines[-1], "20 holders, 25 plots, total due £1,621.09")

    def test_season_is_required(self):
        code, out, _ = run("renewals")
        self.assertEqual((code, out), (2, ""))

    def test_register_error(self):
        code, out, err = run("renewals", "--season", "2026", "--plots", "missing.csv")
        self.assertEqual((code, out, err), (1, "", "plotkeeper: cannot read missing.csv\n"))


if __name__ == "__main__":
    unittest.main()
