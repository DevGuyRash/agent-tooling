import os
import tempfile
import unittest

from mirrorsync.config import ConfigError, load, parse


class ParseTest(unittest.TestCase):
    def test_sections_keys_and_values(self):
        text = (
            "[debian]\n"
            "url = https://deb.example.org/debian\n"
            "dest = /srv/mirror/debian\n"
            "\n"
            "[ubuntu-ports]\n"
            "url = https://ports.example.org/ubuntu-ports\n"
        )
        self.assertEqual(parse(text), {
            "debian": {"url": "https://deb.example.org/debian", "dest": "/srv/mirror/debian"},
            "ubuntu-ports": {"url": "https://ports.example.org/ubuntu-ports"},
        })

    def test_file_order_is_kept(self):
        config = parse("[b]\nz = 1\ny = 2\n[a]\n")
        self.assertEqual(list(config), ["b", "a"])
        self.assertEqual(list(config["b"]), ["z", "y"])

    def test_colon_separator(self):
        self.assertEqual(parse("[a]\nretries: 3\n"), {"a": {"retries": "3"}})

    def test_first_separator_splits(self):
        config = parse("[a]\nurl = http://mirror:8080/x?y=1\nmotd: key=value\n")
        self.assertEqual(config["a"], {"url": "http://mirror:8080/x?y=1", "motd": "key=value"})

    def test_keys_are_lowercased_and_trimmed(self):
        self.assertEqual(parse("[a]\n  Retry Delay   =   30s  \n"), {"a": {"retry delay": "30s"}})

    def test_empty_value(self):
        self.assertEqual(parse("[a]\nexclude =\n"), {"a": {"exclude": ""}})

    def test_section_names_are_case_sensitive(self):
        self.assertEqual(list(parse("[Debian]\n[debian]\n")), ["Debian", "debian"])

    def test_section_without_keys(self):
        self.assertEqual(parse("[a]\n"), {"a": {}})

    def test_comments_and_blank_lines(self):
        text = "# top\n; also a comment\n\n[a]\n  # indented comment\nk = v\n\n"
        self.assertEqual(parse(text), {"a": {"k": "v"}})

    def test_hash_after_value_is_part_of_value(self):
        self.assertEqual(parse("[a]\ncolor = #ff0000 # red\n")["a"]["color"], "#ff0000 # red")

    def test_multiline_value(self):
        text = "[a]\nexclude =\n    *.iso\n\t*-dbg_*\nnext = 1\n"
        self.assertEqual(parse(text)["a"], {"exclude": "\n*.iso\n*-dbg_*", "next": "1"})

    def test_comment_inside_multiline_value(self):
        text = "[a]\nexclude = *.iso\n    # not yet: *.img\n    *.tmp\n"
        self.assertEqual(parse(text)["a"]["exclude"], "*.iso\n*.tmp")

    def test_blank_line_closes_multiline_value(self):
        text = "[a]\nexclude = *.iso\n\n    retries = 3\n"
        self.assertEqual(parse(text)["a"], {"exclude": "*.iso", "retries": "3"})

    def test_windows_line_endings(self):
        self.assertEqual(parse("[a]\r\nk = v\r\n"), {"a": {"k": "v"}})

    def test_empty_text(self):
        self.assertEqual(parse(""), {})


class ParseErrorTest(unittest.TestCase):
    def assertRejected(self, text, lineno):
        with self.assertRaises(ConfigError) as caught:
            parse(text)
        self.assertEqual(caught.exception.lineno, lineno)

    def test_key_outside_section(self):
        self.assertRejected("k = v\n[a]\n", 1)

    def test_line_without_separator(self):
        self.assertRejected("[a]\nk = v\njust words\n", 3)

    def test_empty_key(self):
        self.assertRejected("[a]\n= v\n", 2)
        self.assertRejected("[a]\n   : v\n", 2)

    def test_malformed_section_header(self):
        self.assertRejected("[a]\nk = v\n[b\n", 3)
        self.assertRejected("[b] # main mirror\n", 1)

    def test_duplicate_key(self):
        self.assertRejected("[a]\nK = 1\nk = 2\n", 3)

    def test_duplicate_section(self):
        self.assertRejected("[a]\n[b]\n[a]\n", 3)

    def test_message_names_the_line(self):
        with self.assertRaises(ConfigError) as caught:
            parse("[a]\n\nnonsense\n")
        self.assertEqual(str(caught.exception), "line 3: expected 'key = value'")


class LoadTest(unittest.TestCase):
    def test_load_strips_byte_order_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mirrors.ini")
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write("[debian]\nurl = https://deb.example.org/debian\n")
            self.assertEqual(load(path), {"debian": {"url": "https://deb.example.org/debian"}})


if __name__ == "__main__":
    unittest.main()
