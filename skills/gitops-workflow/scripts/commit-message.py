#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


HEADER_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic Conventional Commit messages with mandatory bullet bodies."
    )
    parser.add_argument("--type", required=True, help="Conventional Commit type, for example feat or fix.")
    parser.add_argument("--scope", help="Optional Conventional Commit scope.")
    parser.add_argument("--subject", required=True, help="Imperative lowercase subject line without trailing punctuation.")
    parser.add_argument(
        "--bullet",
        action="append",
        default=[],
        help="Body bullet line. Repeat for multiple bullets. At least one is required.",
    )
    parser.add_argument(
        "--footer",
        action="append",
        default=[],
        help="Optional footer line. Repeat for multiple footers.",
    )
    parser.add_argument("--out", help="Write the generated message to this path instead of stdout.")
    return parser


def validate(args: argparse.Namespace) -> None:
    if not HEADER_RE.match(args.type):
        raise SystemExit(f"invalid --type '{args.type}'")
    if args.scope and not HEADER_RE.match(args.scope):
        raise SystemExit(f"invalid --scope '{args.scope}'")
    subject = args.subject.strip()
    if not subject:
        raise SystemExit("--subject must not be empty")
    if subject.endswith("."):
        raise SystemExit("--subject must not end with a period")
    if subject != subject.lower():
        raise SystemExit("--subject must be lowercase")
    if not args.bullet:
        raise SystemExit("at least one --bullet is required")
    for bullet in args.bullet:
        if not bullet.strip():
            raise SystemExit("--bullet must not be empty")
    for footer in args.footer:
        if not footer.strip():
            raise SystemExit("--footer must not be empty")


def render(args: argparse.Namespace) -> str:
    header = f"{args.type}({args.scope}): {args.subject}" if args.scope else f"{args.type}: {args.subject}"
    lines = [header, ""]
    lines.extend(f"- {bullet.strip()}" for bullet in args.bullet)
    if args.footer:
        lines.append("")
        lines.extend(footer.strip() for footer in args.footer)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate(args)
    message = render(args)
    if args.out:
      Path(args.out).write_text(message, encoding="utf-8")
    else:
      sys.stdout.write(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
