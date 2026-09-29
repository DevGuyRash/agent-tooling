"""Command line: ``python3 -m mirrorsync check CONFIG``."""
import sys

from .config import ConfigError, load

USAGE = "usage: python3 -m mirrorsync check CONFIG"
REQUIRED = ("url", "dest")


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] != "check":
        print(USAGE, file=sys.stderr)
        return 2
    path = args[1]
    try:
        config = load(path)
    except (OSError, ConfigError) as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return 1
    defaults = config.get("defaults", {})
    problems = 0
    for name, section in config.items():
        if name == "defaults":
            continue
        settings = {**defaults, **section}
        missing = [key for key in REQUIRED if not settings.get(key)]
        if missing:
            print(f"{path}: [{name}] is missing {', '.join(missing)}", file=sys.stderr)
            problems += 1
        else:
            print(f"{name}: {settings['url']} -> {settings['dest']}")
    return 1 if problems else 0
