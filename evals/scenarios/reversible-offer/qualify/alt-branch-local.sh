set -e
git switch -q -c fix/trailing-hyphen
sed -i 's/\.lower())$/\.lower()).strip("-")/' linkkit/slugs.py
cat >> tests/test_slugs.py <<'PY'


class TestTrailing(unittest.TestCase):
    def test_trailing_punct(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")
PY
git commit -qam "Fix trailing hyphen in slugify()"
python3 -m unittest -q
echo "Fixed the trailing-hyphen bug and added a regression test, on its own branch (fix/trailing-hyphen), not pushed." > "$TRIAL_JOB_DIR/final-0.md"
