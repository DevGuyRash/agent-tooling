import unittest

from clubroll.store import Store


class StoreTest(unittest.TestCase):
    def test_members(self):
        store = Store()
        store.add_member("ann@example.org", "Ann")
        self.assertTrue(store.has_member("ann@example.org"))
        self.assertFalse(store.has_member("bob@example.org"))

    def test_invites_are_recorded_as_pending(self):
        store = Store()
        invite = store.add_invite("bob@example.org", "ann@example.org")
        self.assertEqual(invite, {"address": "bob@example.org", "invited_by": "ann@example.org", "status": "pending"})
        self.assertEqual(store.invites, [invite])


if __name__ == "__main__":
    unittest.main()
