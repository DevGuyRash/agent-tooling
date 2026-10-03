"""Small, exact edits to files in the working tree for the reference behaviors: edit.py FILE OLD NEW [OLD NEW ...]
replaces each OLD (which must occur exactly once) with NEW."""
import sys
from pathlib import Path

path, pairs = Path(sys.argv[1]), sys.argv[2:]
text = path.read_text()
for old, new in zip(pairs[::2], pairs[1::2]):
    if text.count(old) != 1:
        raise SystemExit(f"{path}: {old!r} occurs {text.count(old)} times")
    text = text.replace(old, new)
path.write_text(text)
