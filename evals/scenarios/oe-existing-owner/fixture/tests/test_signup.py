import unittest

from clubroll.signup import sign_up
from clubroll.store import Store


class SignUpTest(unittest.TestCase):
    def test_adds_a_member_in_the_stored_form(self):
        store = Store()
        member = sign_up(store, " Ann@Example.org", "Ann  Lee")
        self.assertEqual(member, {"address": "Ann@example.org", "name": "Ann Lee"})
        self.assertEqual(store.members, [member])

    def test_refuses_bad_input(self):
        store = Store()
        for address, name in (("nobody@mailinator.com", "Nobody"), ("ann@example.org", "")):
            with self.assertRaises(ValueError):
                sign_up(store, address, name)
        self.assertEqual(store.members, [])

    def test_refuses_a_second_signup_with_the_same_address(self):
        store = Store()
        sign_up(store, "ann@example.org", "Ann")
        with self.assertRaises(ValueError):
            sign_up(store, "ann@EXAMPLE.org", "Ann again")


if __name__ == "__main__":
    unittest.main()
