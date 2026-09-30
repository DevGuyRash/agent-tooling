import re

_WORD_RE = re.compile(r"[^a-z0-9]+")


def _normalize_title(title):
    """Lowercase a title and collapse runs of non-alphanumeric characters into single hyphens."""
    return _WORD_RE.sub("-", title.lower())


def slugify(title):
    """Turn a post title into a URL-safe slug, e.g. 'Hello, World!' -> 'hello-world'."""
    return _normalize_title(title)
