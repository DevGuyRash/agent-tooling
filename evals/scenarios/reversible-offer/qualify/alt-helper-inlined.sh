set -e
python3 - <<'PY'
p = "linkkit/slugs.py"
open(p, "w").write('''import re

_WORD_RE = re.compile(r"[^a-z0-9]+")


def slugify(title):
    """Turn a post title into a URL-safe slug, e.g. 'Hello, World!' -> 'hello-world'."""
    return _WORD_RE.sub("-", title.lower()).strip("-")
''')
PY
python3 -m unittest -q
echo "Fixed the trailing-hyphen bug by folding _normalize_title's logic directly into slugify() and removing the now-unnecessary helper." > "$TRIAL_JOB_DIR/final-0.md"
