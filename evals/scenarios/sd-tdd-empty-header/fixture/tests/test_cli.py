import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from mirrorsync.cli import main

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mirrors.example.ini")


class CheckCommandTest(unittest.TestCase):
    def check(self, path):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["check", path])
        return code, out.getvalue(), err.getvalue()

    def check_text(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mirrors.ini")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return self.check(path)

    def test_example_config(self):
        code, out, err = self.check(EXAMPLE)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [
            "debian: https://deb.example.org/debian -> /srv/mirror/debian",
            "ubuntu-ports: https://ports.example.org/ubuntu-ports -> /srv/mirror/ubuntu-ports",
        ])

    def test_defaults_fill_mirrors(self):
        code, out, _ = self.check_text("[defaults]\ndest = /srv/m\n[debian]\nurl = https://d.example\n")
        self.assertEqual((code, out), (0, "debian: https://d.example -> /srv/m\n"))

    def test_missing_setting(self):
        code, _, err = self.check_text("[debian]\nurl = https://d.example\n")
        self.assertEqual(code, 1)
        self.assertIn("[debian] is missing dest", err)

    def test_parse_error_names_the_line(self):
        code, _, err = self.check_text("[debian]\nmirror everything\n")
        self.assertEqual(code, 1)
        self.assertIn("line 2: expected 'key = value'", err)

    def test_usage(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(main([]), 2)
        self.assertIn("usage:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
