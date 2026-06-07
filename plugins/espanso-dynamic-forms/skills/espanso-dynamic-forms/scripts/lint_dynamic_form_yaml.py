#!/usr/bin/env python3
"""Lint Espanso YAML for dynamic-form contract and anti-patterns."""

from __future__ import annotations

import argparse
import pathlib

REQUIRED_KEYS = (
    "ESPANSO_FORM_OPERATION=",
    "ESPANSO_FORM_PROVIDER=",
)

WARN_PATTERNS = (
    "Copied to clipboard",
    "copied result to clipboard",
)


def _iter_yaml_list_items(text: str) -> list[str]:
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.lstrip()
        if not line or line.startswith("#") or not line.startswith("-"):
            continue

        item = line[1:].lstrip()
        if not item:
            continue
        if item[0] in ("'", '"'):
            item = item[1:]
        items.append(item)
    return items


def _iter_layout_generator_args_blocks(text: str) -> list[list[str]]:
    lines = text.splitlines()
    blocks: list[list[str]] = []
    idx = 0

    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.lstrip()
        indent = len(raw) - len(stripped)
        if not stripped.startswith("-"):
            idx += 1
            continue

        item = stripped[1:].lstrip()
        if item.startswith(("name:", '"name:', "'name:")) and "layout_generator" in item:
            start_indent = indent
            idx += 1
            args_indent: int | None = None
            block_items: list[str] = []

            while idx < len(lines):
                candidate_raw = lines[idx]
                candidate_stripped = candidate_raw.lstrip()
                candidate_indent = len(candidate_raw) - len(candidate_stripped)

                if (
                    candidate_stripped.startswith("-")
                    and candidate_indent <= start_indent
                ):
                    break

                if candidate_stripped.startswith("args:"):
                    args_indent = candidate_indent
                    idx += 1
                    continue

                if args_indent is not None and candidate_indent > args_indent and candidate_stripped.startswith("-"):
                    value = candidate_stripped[1:].lstrip()
                    if value and value[0] in ("'", '"'):
                        value = value[1:]
                    block_items.append(value)

                idx += 1

            blocks.append(block_items)
            continue

        idx += 1

    return blocks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint dynamic-form YAML contract usage."
    )
    parser.add_argument("paths", nargs="+", help="YAML files or directories")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures",
    )
    return parser.parse_args()


def discover_yaml(paths: list[str]) -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for raw in paths:
        p = pathlib.Path(raw)
        if p.is_file() and p.suffix in (".yml", ".yaml"):
            out.append(p)
            continue
        if p.is_dir():
            out.extend(sorted(p.rglob("*.yml")))
            out.extend(sorted(p.rglob("*.yaml")))
    return out


def lint_text(text: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    list_items = _iter_yaml_list_items(text)
    args_blocks = _iter_layout_generator_args_blocks(text)

    if not args_blocks:
        missing = [key for key in REQUIRED_KEYS if not any(item.startswith(key) for item in list_items)]
        if missing:
            errors.append("missing required keys: " + ", ".join(missing))
    else:
        for block_index, block_items in enumerate(args_blocks, start=1):
            missing = [
                key
                for key in REQUIRED_KEYS
                if not any(item.startswith(key) for item in block_items)
            ]
            if missing:
                errors.append(
                    f"layout_generator args block {block_index} missing required keys: "
                    + ", ".join(missing)
                )

    if not any(item.startswith("ESPANSO_FORM_FIELD_") for item in list_items):
        warnings.append("no ESPANSO_FORM_FIELD_<name> keys found")

    for pattern in WARN_PATTERNS:
        if pattern in text:
            warnings.append(f"status-text pattern detected: {pattern}")

    return errors, warnings


def main() -> int:
    args = parse_args()
    files = discover_yaml(args.paths)
    if not files:
        print("FAIL no YAML files found")
        return 1

    failed = False
    for path in files:
        text = path.read_text(encoding="utf-8")
        errors, warnings = lint_text(text)

        if not errors and not warnings:
            print(f"OK   {path}")
            continue

        if errors:
            failed = True
            print(f"FAIL {path}")
            for item in errors:
                print(f"  - {item}")

        if warnings:
            if errors:
                print(f"WARN {path}")
            else:
                print(f"WARN {path}")
            for item in warnings:
                print(f"  - {item}")
            if args.strict:
                failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
