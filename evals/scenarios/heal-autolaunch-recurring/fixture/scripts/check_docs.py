"""Check that README.md documents every chorelog command."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    commands = re.findall(r'add_parser\("([a-z-]+)"', (ROOT / "chorelog" / "cli.py").read_text())
    readme = (ROOT / "README.md").read_text()
    missing = [name for name in commands if f"chorelog {name}" not in readme]
    for name in missing:
        print(f"README.md does not document `chorelog {name}`", file=sys.stderr)
    if not missing:
        print("docs ok")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
