import unittest

from stampcard.batch import run
from stampcard.directory import Directory
from stampcard.report import register_format, render


def empty_summary():
    return run([], Directory({}.get), lambda message: None)


class FormatsTest(unittest.TestCase):
    def test_text_is_the_default_format(self):  # R10
        summary = empty_summary()
        self.assertEqual(render(summary), render(summary, "text"))
        self.assertTrue(render(summary).startswith("stampcard report\n"))

    def test_a_registered_format_is_used(self):
        register_format("count", lambda summary: "%d\n" % summary.events)
        self.assertEqual(render(empty_summary(), "count"), "0\n")

    def test_an_unknown_format_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "unknown format: nope"):
            render(empty_summary(), "nope")


if __name__ == "__main__":
    unittest.main()
