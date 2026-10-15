import unittest

from .fakes import make_accounts


class AccountsTest(unittest.TestCase):
    def test_add_user_and_devices(self):
        accounts, transport, _ = make_accounts()
        accounts.add_user("u1", "Ada")
        accounts.add_device("u1", "d1")
        accounts.add_device("u1", "d2")
        self.assertEqual(accounts.user("u1").devices, ["d1", "d2"])
        self.assertEqual(transport.sent, [])

    def test_duplicate_user_is_refused(self):
        accounts, _, _ = make_accounts()
        accounts.add_user("u1", "Ada")
        with self.assertRaises(ValueError):
            accounts.add_user("u1", "Ada again")

    def test_set_display_name(self):
        accounts, _, _ = make_accounts()
        accounts.add_user("u1", "Ada")
        accounts.set_display_name("u1", "Ada L.")
        self.assertEqual(accounts.user("u1").display_name, "Ada L.")


if __name__ == "__main__":
    unittest.main()
