import tempfile
import unittest
from pathlib import Path

from shopcrm.contacts import (Contact, ExportError, find_matches, normalize_email, normalize_phone, read_export,
                              same_customer, to_row)

DATA = Path(__file__).resolve().parent / "data"
HEADER = "customer_id,created_at,first_name,last_name,email,phone,orders,total_spent,accepts_marketing\n"


def contact(customer_id=1, email="", phone="", created_at="2024-01-01T00:00:00Z"):
    return Contact(customer_id, created_at, "A", "B", email, phone, 1, 1000, False)


class NormalizeTest(unittest.TestCase):
    def test_email(self):
        self.assertEqual(normalize_email("  Ines.Calloway@Example.COM "), "ines.calloway@example.com")
        self.assertEqual(normalize_email(""), "")
        self.assertEqual(normalize_email("none"), "")
        self.assertEqual(normalize_email("n/a"), "")

    def test_phone(self):
        for raw in ("(206) 555-0110", "206.555.0110", "+1 206 555 0110", "1-206-555-0110", "2065550110"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_phone(raw), "2065550110")

    def test_phone_that_never_matches(self):
        for raw in ("", "555-0101", "000-000-0000", "1-111-111-1111", "999 999 9999", "+44 20 7946 0958", "n/a"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_phone(raw), "")


class SameCustomerTest(unittest.TestCase):
    def test_same_email(self):
        self.assertTrue(same_customer(contact(email="a@x.com"), contact(email=" A@X.com")))

    def test_same_phone(self):
        self.assertTrue(same_customer(contact(phone="(206) 555-0110"), contact(phone="+1 206 555 0110")))

    def test_nothing_in_common(self):
        self.assertFalse(same_customer(contact(email="a@x.com", phone="2065550110"),
                                       contact(email="b@x.com", phone="2065550111")))

    def test_blanks_and_placeholders_never_match(self):
        self.assertFalse(same_customer(contact(), contact()))
        self.assertFalse(same_customer(contact(email="none", phone="000-000-0000"),
                                       contact(email="none", phone="000-000-0000")))


class ExportTest(unittest.TestCase):
    def test_read_sample(self):
        contacts = read_export(DATA / "sample-export.csv")
        self.assertEqual([c.customer_id for c in contacts], [2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008])
        self.assertEqual(contacts[3].last_name, "Marsh, Jr.")
        self.assertEqual(contacts[0].total_spent, 8740)
        self.assertTrue(contacts[0].accepts_marketing)
        self.assertEqual(to_row(contacts[3]), ["2004", "2023-03-01T07:05:33Z", "Theo", "Marsh, Jr.",
                                               "theo.marsh@example.net", "+1 312 555 0199", "2", "61.00", "yes"])

    def test_bad_row_names_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text(HEADER + "1,2024-01-01T00:00:00Z,A,B,,,1,1.00,no\n"
                            "2,yesterday,A,B,,,1,1.00,no\n")
            with self.assertRaisesRegex(ExportError, r"bad\.csv:3: created_at"):
                read_export(path)

    def test_wrong_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "other.csv"
            path.write_text("id,email\n1,a@x.com\n")
            with self.assertRaisesRegex(ExportError, "not a customer export"):
                read_export(path)


class FindMatchesTest(unittest.TestCase):
    def setUp(self):
        self.contacts = read_export(DATA / "sample-export.csv")

    def ids(self, query):
        return [c.customer_id for c in find_matches(self.contacts, query)]

    def test_by_email(self):
        self.assertEqual(self.ids("ravi.n@EXAMPLE.org"), [2002, 2006])

    def test_by_phone(self):
        self.assertEqual(self.ids("206-555-0110"), [2001, 2003, 2008])

    def test_placeholder_matches_nothing(self):
        self.assertEqual(self.ids("000-000-0000"), [])
        self.assertEqual(self.ids("none"), [])


if __name__ == "__main__":
    unittest.main()
