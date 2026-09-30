import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from pantry.cli import main

RECIPE = Path(__file__).resolve().parents[1] / "recipes" / "pancakes.txt"


class CliTest(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(list(argv))
        return code, out.getvalue()

    def test_scale_recipe(self):
        code, out = self.run_cli("scale", str(RECIPE), "--factor", "2")
        self.assertEqual(code, 0)
        self.assertIn("2 tbsp sugar", out)
        self.assertIn("2 egg", out)

    def test_convert(self):
        code, out = self.run_cli("convert", "2", "cup", "ml")
        self.assertEqual(out.strip(), "473.18 ml")


if __name__ == "__main__":
    unittest.main()
