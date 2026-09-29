"""Read mirrorsync configuration files.

The format is a small INI dialect described in README.md. ``parse`` turns the
text of a configuration file into ``{section: {key: value}}``, keeping the
order of the file, and raises ``ConfigError`` (carrying the 1-based line
number) for anything it cannot read. ``load`` does the same for a path.
"""

COMMENT_PREFIXES = ("#", ";")
SEPARATORS = ("=", ":")


class ConfigError(ValueError):
    """The configuration text is not valid; ``lineno`` is the offending line."""

    def __init__(self, lineno, message):
        super().__init__(f"line {lineno}: {message}")
        self.lineno = lineno
        self.message = message


def load(path):
    """Parse the configuration file at ``path`` (UTF-8, with or without a BOM)."""
    with open(path, encoding="utf-8-sig") as f:
        return parse(f.read())


def parse(text):
    """Parse configuration text into an ordered ``{section: {key: value}}`` dict."""
    sections = {}
    current = None   # keys of the section being read
    open_key = None  # the key whose value a continuation line extends
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            open_key = None  # a blank line closes a multi-line value
            continue
        if line.startswith(COMMENT_PREFIXES):
            continue  # comments may sit inside a multi-line value
        if open_key is not None and raw[0] in " \t":
            current[open_key] += "\n" + line
            continue
        open_key = None
        if line.startswith("["):
            name = _section_name(line, lineno)
            if name in sections:
                raise ConfigError(lineno, f"duplicate section [{name}]")
            current = sections[name] = {}
        elif current is None:
            raise ConfigError(lineno, "key outside of any section")
        else:
            key, value = _key_value(line, lineno)
            if key in current:
                raise ConfigError(lineno, f"duplicate key {key!r}")
            current[key] = value
            open_key = key
    return sections


def _section_name(line, lineno):
    if not line.endswith("]"):
        raise ConfigError(lineno, "section header must end with ']'")
    name = line[1:-1]
    if not name:
        raise ConfigError(lineno, "empty section header")
    return name.strip()


def _key_value(line, lineno):
    cuts = [i for i in (line.find(sep) for sep in SEPARATORS) if i >= 0]
    if not cuts:
        raise ConfigError(lineno, "expected 'key = value'")
    cut = min(cuts)
    key = line[:cut].strip().lower()
    if not key:
        raise ConfigError(lineno, "empty key")
    return key, line[cut + 1:].strip()
