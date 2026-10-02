import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from circdesk.cli import main

DATA = Path(__file__).parent / "data"
LOANS = str(DATA / "loans.csv")
PATRONS = str(DATA / "patrons.csv")
HEADER = "loan_id,patron_id,barcode,title,category,due,returned\n"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(list(argv))
        except SystemExit as exc:
            rc = exc.code
    return rc, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def _loans(self, rows):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = Path(d.name) / "loans.csv"
        p.write_text(HEADER + rows)
        return str(p)

    def test_receipt(self):
        self.assertEqual(run("receipt", LOANS, "L-30120"),
                         (0, "Returned: Spirited Away (31207001102945)\n"
                             "Due 2026-09-18, returned 2026-09-22: 4 days late\n"
                             "Fine: 5.00\n", ""))
        self.assertEqual(run("receipt", LOANS, "L-30115")[1],
                         "Returned: Paddington at the Zoo (31207000533109)\n"
                         "Due 2026-09-14, returned 2026-09-15: 1 day late\n"
                         "Fine: none\n")

    def test_receipt_errors(self):
        rc, out, err = run("receipt", LOANS, "L-99999")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("circdesk: no loan L-99999", err)
        self.assertEqual(run("receipt", LOANS, "L-30131")[0], 1)
        self.assertEqual(run("receipt", str(DATA / "missing.csv"), "L-1")[0], 1)

    def test_unknown_category(self):
        loans = self._loans("L-1,P-2041,312,Zine of the Month,zines,2026-09-01,2026-09-09\n")
        rc, _, err = run("receipt", loans, "L-1")
        self.assertEqual(rc, 1)
        self.assertIn("unknown category 'zines'", err)

    def test_notices(self):
        self.assertEqual(run("notices", LOANS, PATRONS, "--on", "2026-09-27"),
                         (0, "Kwame Mensah (P-2077)\n"
                             "  The Hobbit (31207000920017): due 2026-09-21, 6 days overdue, fine so far 0.90\n"
                             "1 notice, 1 item\n", ""))
        self.assertEqual(run("notices", LOANS, PATRONS, "--on", "2026-09-20"), (0, "No notices.\n", ""))

    def test_notice_for_unknown_patron(self):
        loans = self._loans("L-1,P-9999,312,Holes,children,2026-09-01,\n")
        rc, _, err = run("notices", loans, PATRONS, "--on", "2026-09-20")
        self.assertEqual(rc, 1)
        self.assertIn("P-9999", err)

    def test_account(self):
        self.assertEqual(run("account", LOANS, PATRONS, "P-2103", "--on", "2026-09-26"),
                         (0, "Ines de Vries (P-2103)\nNo fines.\n", ""))
        rc, _, err = run("account", LOANS, PATRONS, "P-0000", "--on", "2026-09-26")
        self.assertEqual(rc, 1)
        self.assertIn("circdesk: no patron P-0000", err)

    def test_usage(self):
        self.assertEqual(run()[0], 2)
        self.assertEqual(run("receipt", LOANS)[0], 2)
        self.assertEqual(run("notices", LOANS, PATRONS, "--on", "2026-13-40")[0], 2)


if __name__ == "__main__":
    unittest.main()
