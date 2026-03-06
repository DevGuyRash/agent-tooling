#!/usr/bin/env python3
"""Deterministic CODEOWNERS linter for gitops-workflow skill."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from bootstrap import maybe_reexec_repo_local_copy


maybe_reexec_repo_local_copy(Path(__file__).resolve(), sys.argv)


def parse_lines(path: Path) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    normalized: List[str] = []

    for idx, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            errors.append(f"line {idx}: missing owners")
            continue
        pattern, owners = parts[0], parts[1:]
        for owner in owners:
            if not (owner.startswith("@") or "@" in owner):
                errors.append(f"line {idx}: invalid owner token '{owner}'")
        normalized.append(f"{pattern} {' '.join(sorted(set(owners)))}")

    return normalized, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=".github/CODEOWNERS")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 2

    normalized, errors = parse_lines(path)
    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 2

    sorted_lines = sorted(normalized)
    if normalized != sorted_lines:
        print("Error: CODEOWNERS entries are not lexicographically sorted by pattern", file=sys.stderr)
        return 3

    print("CODEOWNERS lint passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
