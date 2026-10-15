import unittest

from clubroll.validation import InvalidEmail, InvalidName, check_email, check_name


class CheckEmailTest(unittest.TestCase):
    def test_returns_the_stored_form(self):
        self.assertEqual(check_email("  Ann.Lee@Example.ORG "), "Ann.Lee@example.org")

    def test_plain_addresses(self):
        for address in ("ann@example.org", "a@b.co", "first.last@sub.example.co.uk", "ann+club@example.org"):
            self.assertEqual(check_email(address), address)

    def test_refuses_what_is_not_an_address(self):
        for address in ("", "ann", "ann@", "@example.org", "ann@@example.org", "ann@example", "ann@exa mple.org",
                        "a..b@example.org", ".ann@example.org"):
            with self.assertRaises(InvalidEmail, msg=address):
                check_email(address)

    def test_refuses_disposable_domains_and_their_subdomains(self):
        for address in ("ann@mailinator.com", "ann@MAILINATOR.COM", "ann@lists.mailinator.com"):
            with self.assertRaises(InvalidEmail, msg=address):
                check_email(address)
        self.assertEqual(check_email("ann@notmailinator.com"), "ann@notmailinator.com")

    def test_plus_tags_are_not_taken_by_big_providers(self):
        with self.assertRaises(InvalidEmail):
            check_email("ann+club@gmail.com")
        self.assertEqual(check_email("ann@gmail.com"), "ann@gmail.com")


class CheckNameTest(unittest.TestCase):
    def test_tidies_spaces(self):
        self.assertEqual(check_name("  Ann   Lee "), "Ann Lee")

    def test_refuses_empty_names(self):
        with self.assertRaises(InvalidName):
            check_name("   ")


if __name__ == "__main__":
    unittest.main()
