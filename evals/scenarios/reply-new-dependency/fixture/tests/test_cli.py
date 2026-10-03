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


class PlotsCommandTests(unittest.TestCase):
    def test_lists_every_plot_in_plot_order(self):
        code, out, _ = run("plots")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("Plot"))
        self.assertEqual([l.split()[0] for l in lines[1:4]], ["A1", "A2", "A3"])
        self.assertEqual(len(lines), 30)
        self.assertIn("A10", lines[10])

    def test_vacant_only(self):
        code, out, _ = run("plots", "--vacant")
        self.assertEqual(code, 0)
        self.assertEqual([l.split()[0] for l in out.splitlines()[1:]], ["A6", "B6", "C5"])

    def test_register_error(self):
        code, out, err = run("plots", "--plots", "missing.csv")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err, "plotkeeper: cannot read missing.csv\n")


class WaitingCommandTests(unittest.TestCase):
    def test_longest_waiting_first(self):
        code, out, _ = run("waiting")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "  1. George Lam (since 2024-11-03, wants full)")
        self.assertEqual(len(out.splitlines()), 4)


if __name__ == "__main__":
    unittest.main()
