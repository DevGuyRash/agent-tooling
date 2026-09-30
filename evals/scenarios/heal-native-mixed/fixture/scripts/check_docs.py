"""Check that docs/commands.md documents exactly the commands the CLI provides."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shelfmark.cli import build_parser  # noqa: E402

REQUIRED_FILES = ["docs/commands.md", "docs/import-goodreads.md"]


def cli_commands():
    for action in build_parser()._actions:
        if action.__class__.__name__ == "_SubParsersAction":
            return set(action.choices)
    return set()


def main():
    errors = []
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            errors.append(f"missing required doc: {rel}")
    commands_md = ROOT / "docs" / "commands.md"
    text = commands_md.read_text() if commands_md.exists() else ""
    documented = set(re.findall(r"^## (\S+)", text, re.M))
    cli = cli_commands()
    for name in sorted(cli - documented):
        errors.append(f"docs/commands.md: command '{name}' is not documented")
    for name in sorted(documented - cli):
        errors.append(f"docs/commands.md: documents unknown command '{name}'")
    for e in errors:
        print(f"check_docs: {e}", file=sys.stderr)
    if errors:
        return 1
    print("check_docs: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
