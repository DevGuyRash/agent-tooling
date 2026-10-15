import unittest

from beacon import signing


class SigningTest(unittest.TestCase):
    def test_verify_accepts_what_sign_made(self):
        signature = signing.sign({"a": 1, "b": 2}, b"k")
        self.assertTrue(signing.verify({"b": 2, "a": 1}, signature, b"k"))

    def test_verify_rejects_another_key_or_payload(self):
        signature = signing.sign({"a": 1}, b"k")
        self.assertFalse(signing.verify({"a": 1}, signature, b"other"))
        self.assertFalse(signing.verify({"a": 2}, signature, b"k"))


if __name__ == "__main__":
    unittest.main()
