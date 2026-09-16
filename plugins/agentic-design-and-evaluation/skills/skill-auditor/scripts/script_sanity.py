"""Inspect script bytes and permissions without executing or modifying the target."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print(f"error: {message}\nhint: use --help; supported formats: text, json", file=sys.stderr)
        raise SystemExit(2)


def collect(directory):
    root = Path(directory)
    if not root.is_dir():
        raise ValueError(f"skill directory not found: {directory}")
    errors = []
    observations = []
    script_count = 0
    text_extensions = {".md", ".py", ".rs", ".toml", ".yml", ".yaml", ".json", ".sh"}

    def failed(error):
        raise error

    for base, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "__pycache__", ".pytest_cache"}
                         and not (Path(base) / d).is_symlink())
        for name in sorted(files):
            path = Path(base) / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root)
            is_script = len(relative.parts) > 1 and relative.parts[0] == "scripts"
            if is_script:
                script_count += 1
            elif path.suffix not in text_extensions:
                continue
            data = path.read_bytes()
            if b"\0" in data:
                continue
            first = data.partition(b"\n")[0]
            executable = bool(path.stat().st_mode & 0o111)
            crlf = any(line.endswith(b"\r") for line in data.split(b"\n"))
            bad_shebang = first.startswith(b"#!") and first.endswith(b"\r")
            subject = relative.as_posix()
            if crlf:
                if executable and bad_shebang:
                    errors.append(dict(code="crlf_in_executable", subject=subject,
                        fact="the executable has a carriage return in its shebang, not merely in its body; verify the intended host interpreter boundary"))
                else:
                    observations.append(dict(code="crlf", subject=subject,
                        fact="the file uses CRLF line endings", source="repo-overlay"))
            if is_script:
                if executable and not first.startswith(b"#!"):
                    errors.append(dict(code="missing_shebang", subject=subject,
                        fact="the file is executable but has no interpreter shebang"))
                elif not executable and path.suffix == ".sh":
                    observations.append(dict(code="not_executable", subject=subject,
                        fact="the shell file has no executable bit; inspect whether the target sources it, invokes an interpreter, or expects direct execution",
                        source="repo-overlay"))
    return dict(script="script_sanity", skill_dir=directory, script_count=script_count,
                error_count=len(errors), errors=errors,
                observation_count=len(observations), observations=observations)


def main():
    parser = Parser(prog="script_sanity.sh", description=(
        "Report executable and line-ending facts without running the target. Requires Python 3. "
        "Only a carriage return in an executable shebang establishes the reported interpreter defect; "
        "CRLF elsewhere and non-executable shell files remain observations. "
        "Exit 0: no structural errors; 1: errors found; 2: unusable arguments, input, or failed collection."))
    parser.add_argument("skill_directory")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    try:
        result = collect(args.skill_directory)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    if args.format == "json":
        print(json.dumps(result, separators=(",", ":"), ensure_ascii=True))
    else:
        print(f"REPORT script_sanity\nskill_dir={result['skill_dir']}\nscript_count={result['script_count']}")
        print(f"errors={result['error_count']}\nobservations={result['observation_count']}")
        for item in result["errors"]:
            print(f"ERROR {item['code']}: {item['subject']}\n  {item['fact']}")
        for item in result["observations"]:
            print(f"{item['code']}: {item['subject']}\n  {item['fact']}\n  source: {item['source']}")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
