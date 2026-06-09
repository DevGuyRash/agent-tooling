#!/usr/bin/env python3
"""Extract rough candidate goals from files. This is heuristic discovery, not execution."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|BUG|XXX)\b[:\s-]*(.*)", re.I)
FAIL_RE = re.compile(r"\b(fail(?:ed|ing)?|error|exception|traceback|assertion|timeout)\b", re.I)
TEST_SKIP_RE = re.compile(r"\b(skip|xfail|pending)\b", re.I)

IGNORE_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", ".next", "target", "coverage", "__pycache__"}
TEXT_SUFFIXES = {".md", ".txt", ".log", ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".yml", ".yaml", ".json", ".toml", ".sh", ".css", ".html"}


def iter_files(paths, max_files):
    count = 0
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            continue
        if p.is_file():
            yield p
            count += 1
        else:
            for child in p.rglob("*"):
                if count >= max_files:
                    return
                if any(part in IGNORE_DIRS for part in child.parts):
                    continue
                if child.is_file() and (child.suffix in TEXT_SUFFIXES or child.name in {"Makefile", "justfile"}):
                    yield child
                    count += 1


def candidate_from_hit(path: Path, line_no: int, kind: str, text: str) -> str:
    rel = path.as_posix()
    if kind == "todo":
        title = f"Resolve work marker in {rel}"
        terminal = f"The work marker at {rel}:{line_no} is either implemented, removed as obsolete with justification, or converted into a launchable follow-up goal."
        verifier = "Run the relevant local tests or a human review checklist for the affected area."
    elif kind == "skipped-test":
        title = f"Triage skipped or pending test in {rel}"
        terminal = f"The skipped/pending test at {rel}:{line_no} is either enabled and passing, deleted as obsolete with justification, or documented as blocked."
        verifier = "Run the relevant test command and report raw result."
    else:
        title = f"Investigate error signal in {rel}"
        terminal = f"The error/failure signal at {rel}:{line_no} is reproduced, resolved, or recorded as blocked with evidence."
        verifier = "Run reproduction or relevant test/log verification."
    return f"""### Candidate: {title}

- Status: conditional
- Source: `{rel}:{line_no}`
- Evidence: `{text.strip()[:180]}`
- Suggested terminal state: {terminal}
- Suggested verifier: {verifier}
- Suggested scope: `{rel}` and directly related tests/docs
- Forever-risk: medium until verifier and budget are frozen
"""


def extract(paths, max_files=200, max_candidates=50):
    cands = []
    for path in iter_files(paths, max_files):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            if len(cands) >= max_candidates:
                return cands
            if TODO_RE.search(line):
                cands.append(candidate_from_hit(path, i, "todo", line))
            elif ("test" in path.as_posix().lower() or "spec" in path.as_posix().lower()) and TEST_SKIP_RE.search(line):
                cands.append(candidate_from_hit(path, i, "skipped-test", line))
            elif path.suffix in {".log", ".txt"} and FAIL_RE.search(line):
                cands.append(candidate_from_hit(path, i, "error", line))
    return cands


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Files or directories to scan")
    parser.add_argument("--max-files", type=int, default=200)
    parser.add_argument("--max-candidates", type=int, default=50)
    parser.add_argument("--write", help="Write candidates markdown to file")
    args = parser.parse_args()
    cands = extract(args.paths, args.max_files, args.max_candidates)
    out = "# Candidate Goals\n\n" + ("\n".join(cands) if cands else "No candidate goals found within the exploration budget.\n")
    out += f"\n## Frontier\n\n- Max files inspected: {args.max_files}\n- Max candidates: {args.max_candidates}\n- Inputs: {', '.join(args.paths)}\n"
    if args.write:
        p = Path(args.write)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
