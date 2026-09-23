#!/usr/bin/env python3
"""Apply the reviewed layout fixes to the pinned Mermaid browser artifact.

This manual, offline command accepts only the exact upstream distribution. It
uses exact replacements recorded in mermaid-vendor-patches.json; all other code
and bundled notices stay intact. Each patch has a stable ID and a rationale.
It does not fetch, install, or run as part of report assembly or normal builds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

UPSTREAM_SHA256 = "28fca7ae6ebc7ed7bb63bde63136a74bfef14f296a57e403657eeb8b32836073"
MANIFEST = json.loads(Path(__file__).with_name("mermaid-vendor-patches.json").read_text(encoding="utf-8"))
PATCHED_SHA256 = MANIFEST["artifactSha256"]
if MANIFEST.get("upstreamSha256") != UPSTREAM_SHA256 or not re.fullmatch(r"[0-9a-f]{64}", PATCHED_SHA256):
    raise ValueError("patch manifest does not identify the reviewed upstream and output")


def replacements() -> list[tuple[str, bytes, bytes]]:
    result = []
    names = set()
    for entry in MANIFEST["patches"]:
        patch_id = entry["id"]
        if not isinstance(patch_id, str) or not patch_id or patch_id in names:
            raise ValueError("patch IDs must be non-empty and unique")
        names.add(patch_id)
        for index, change in enumerate(entry["replacements"]):
            before = change["before"]
            if ("after" in change) == ("afterFile" in change):
                raise ValueError(f"replacement requires exactly one of after or afterFile: {patch_id}")
            if "afterFile" in change:
                root = Path(__file__).resolve().parent
                source = (root / change["afterFile"]).resolve()
                if not source.is_relative_to(root) or not source.is_file():
                    raise ValueError(f"replacement source must be a file within scripts: {patch_id}")
                after = source.read_text(encoding="utf-8")
            else:
                after = change["after"]
            if not isinstance(before, str) or not isinstance(after, str) or not before or not after or before == after:
                raise ValueError(f"invalid exact replacement in {patch_id}")
            result.append((f"{patch_id}:{index + 1}", before.encode("utf-8"), after.encode("utf-8")))
    if not result:
        raise ValueError("patch manifest contains no changes")
    return result


def patch(data: bytes) -> bytes:
    if hashlib.sha256(data).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("input is not the pinned, unmodified Mermaid 12.0.0 artifact")
    result = data
    for name, before, after in replacements():
        if result.count(before) != 1:
            raise ValueError(f"layout expression is not unique in the pinned input: {name}")
        result = result.replace(before, after, 1)
    if hashlib.sha256(result).hexdigest() != PATCHED_SHA256:
        raise ValueError("patched artifact differs from the reviewed result")
    return result


def restore_upstream(data: bytes) -> bytes:
    """Prove every byte outside the reviewed replacements is still upstream."""
    if hashlib.sha256(data).hexdigest() != PATCHED_SHA256:
        raise ValueError("input does not match the reviewed patched artifact")
    result = data
    for name, before, after in reversed(replacements()):
        if result.count(after) != 1:
            raise ValueError(f"patched expression is not unique: {name}")
        result = result.replace(after, before, 1)
    if hashlib.sha256(result).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("reversing reviewed changes did not recover the exact upstream bytes")
    return result


def write_output(path: Path, data: bytes, replace: bool) -> None:
    if path.is_symlink():
        raise ValueError("output must not be a symlink")
    if path.exists():
        if path.read_bytes() == data:
            return
        if not replace:
            raise ValueError("output differs; use --replace to replace it deliberately")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(filename)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="original pinned mermaid.min.js")
    parser.add_argument("--output", required=True, type=Path, help="distinct patched artifact destination")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--replace", action="store_true")
    action.add_argument("--check", action="store_true", help="compare the destination without writing")
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError("input and output must be distinct paths")
        result = patch(args.input.read_bytes())
        if args.check:
            if not args.output.is_file() or args.output.read_bytes() != result:
                raise ValueError("destination does not match the reviewed patch")
        else:
            write_output(args.output, result, args.replace)
        print(f"verified {args.output}: {PATCHED_SHA256}")
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
