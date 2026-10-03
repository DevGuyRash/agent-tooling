"""Known implementations of the listings package, as files to write over the package in a copy of the agent's
tree. Every variant has the fixture's modules and public names and differs only in the slug rule:

- right: the fixture with hidden/right/listings/slug.py: accented letters keep their base letter, ß, æ, and œ
  become ss, ae, and oe, ł and ø become l and o, and everything else as before (the ticket's rule).
- wrong-old: the fixture as handed over: every letter outside a-z is a separator.
- wrong-no-spelled: right without the letters that do not decompose (ß, æ, œ, ø, ł, đ stay separators), the rule a
  first attempt with unicodedata alone gives.
- wrong-no-collapse: right, but each separator becomes its own hyphen (a rule the ticket keeps; the fixture's tests
  pin it).
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture"
PACKAGE = "listings"
NAMES = ("right", "wrong-old", "wrong-no-spelled", "wrong-no-collapse")

REPLACEMENTS = {
    "right": [],
    "wrong-no-spelled": [("listings/slug.py", 'spelled = "".join(_SPELLED.get(ch, ch) for ch in title)', "spelled = title")],
    "wrong-no-collapse": [("listings/slug.py", '_SEPARATORS = re.compile(r"[^a-z0-9]+")', '_SEPARATORS = re.compile(r"[^a-z0-9]")')],
}


def fixture_package():
    return {p.relative_to(FIXTURE).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted((FIXTURE / PACKAGE).glob("*.py"))}


def variant(name):
    """{relative path: text} for the whole package of one known implementation."""
    files = fixture_package()
    if name == "wrong-old":
        return files
    for p in sorted((HERE / "right" / PACKAGE).glob("*.py")):
        files[f"{PACKAGE}/{p.name}"] = p.read_text(encoding="utf-8")
    for rel, old, new in REPLACEMENTS[name]:
        if files[rel].count(old) != 1:
            raise RuntimeError(f"variant {name}: {rel} no longer holds {old!r} exactly once")
        files[rel] = files[rel].replace(old, new)
    return files
