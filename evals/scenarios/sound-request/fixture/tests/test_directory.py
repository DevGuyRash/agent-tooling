import unittest

from billing.directory import User, UserDirectory


class TestUserDirectory(unittest.TestCase):
    def setUp(self):
        self.users = [
            User("ann@example.com", "Ann", "pro"),
            User("bo@example.com", "Bo", "basic"),
            User("cy@example.com", "Cy", "pro"),
        ]
        self.directory = UserDirectory(self.users)

    def test_finds_known_email(self):
        user = self.directory.find_by_email("bo@example.com")
        self.assertIs(user, self.users[1])

    def test_unknown_email_returns_none(self):
        self.assertIsNone(self.directory.find_by_email("nope@example.com"))

    def test_directory_can_be_rebuilt_with_new_users(self):
        fresh = UserDirectory([User("zed@example.com", "Zed", "pro")])
        self.assertIsNone(fresh.find_by_email("bo@example.com"))
        self.assertIs(fresh.find_by_email("zed@example.com"), fresh.users[0])


if __name__ == "__main__":
    unittest.main()
