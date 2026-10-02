import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from shopcrm.cli import main

HEADER = "customer_id,created_at,first_name,last_name,email,phone,orders,total_spent,accepts_marketing"
EXAMPLE = HEADER + """
1001,2023-02-11T09:15:02Z,Dana,Whitfield,dana.w@example.com,,2,64.00,no
1002,2023-03-02T17:40:55Z,Omar,Haddad,omar@example.net,(503) 555-0187,1,18.50,yes
1003,2023-05-19T12:01:13Z,Dana,Whitfield,,503-555-0142,1,22.00,no
1004,2023-06-07T08:22:40Z,D,Whitfield, Dana.W@Example.com ,+1 503 555 0142,3,95.25,yes
1005,2023-07-21T19:05:09Z,Omar,Haddad,none,000-000-0000,1,12.00,no
1006,2021-11-30T10:00:00Z,Dana,Whitfield,n/a,5035550142,4,140.00,no
"""


def dedupe(text):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "export.csv"
        path.write_text(text)
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["dedupe", str(path)])
    return code, out.getvalue().splitlines()


class DedupeTest(unittest.TestCase):
    def test_docs_example(self):
        code, lines = dedupe(EXAMPLE)
        self.assertEqual(code, 0)
        self.assertEqual(lines, [
            HEADER + ",merged_ids",
            "1006,2021-11-30T10:00:00Z,Dana,Whitfield,dana.w@example.com,5035550142,10,321.25,yes,1001 1003 1004",
            "1002,2023-03-02T17:40:55Z,Omar,Haddad,omar@example.net,(503) 555-0187,1,18.50,yes,",
            "1005,2023-07-21T19:05:09Z,Omar,Haddad,,,1,12.00,no,",
        ])

    def test_a_late_row_ties_two_people_together(self):
        code, lines = dedupe(HEADER + """
1,2024-01-01T00:00:00Z,A,X,a@example.com,,1,1.00,no
2,2024-01-02T00:00:00Z,B,Y,,(212) 555-0101,1,2.00,no
3,2024-01-03T00:00:00Z,A,X,A@example.com,212.555.0101,1,3.00,yes
""")
        self.assertEqual(code, 0)
        self.assertEqual(lines[1:], ["1,2024-01-01T00:00:00Z,A,X,a@example.com,(212) 555-0101,3,6.00,yes,2 3"])

    def test_empty_export(self):
        self.assertEqual(dedupe(HEADER + "\n"), (0, [HEADER + ",merged_ids"]))


if __name__ == "__main__":
    unittest.main()
