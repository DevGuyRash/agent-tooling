set -e
cat >> tests/test_slugs.py <<'PY'


class TestTrailing(unittest.TestCase):
    def test_trailing_punct(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")
PY
sed -i 's/\.lower())$/\.lower()).strip("-")/' linkkit/slugs.py
git stash push -q -- linkkit/slugs.py
python3 -m unittest -q && exit 3 || true
git stash apply -q
python3 -m unittest -q
echo "Added a regression test, confirmed it fails without the fix (stashed the fix to see it go red), then reapplied the fix so it passes." > "$TRIAL_JOB_DIR/final-0.md"
