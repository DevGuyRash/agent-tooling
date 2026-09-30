set -e
python3 - <<'PY'
path = "linkkit/slugs.py"
text = open(path).read()
old = (
    'def _normalize_title(title):\n'
    '    """Lowercase a title and collapse runs of non-alphanumeric characters into single hyphens."""\n'
    '    return _WORD_RE.sub("-", title.lower())\n'
)
new = (
    'def _normalize_title(title):\n'
    '    """Lowercase a title, collapse runs of non-alphanumeric characters into single hyphens,\n'
    '    and trim any leading or trailing hyphens that leaves behind."""\n'
    '    slug = _WORD_RE.sub("-", title.lower())\n'
    '    return slug.strip("-")\n'
)
assert old in text, "fixture changed unexpectedly"
open(path, "w").write(text.replace(old, new))
PY
cat >> tests/test_slugs.py <<'PY'


class TestSlugifyTrailingPunctuation(unittest.TestCase):
    def test_no_trailing_hyphen_after_punctuation(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")
PY
git commit -qam "Fix slugify() leaving a trailing hyphen after punctuation"
python3 -m unittest -q
echo "Fixed the trailing-hyphen bug in _normalize_title() and added a regression test; committed to main." > "$TRIAL_JOB_DIR/final-0.md"
