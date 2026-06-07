#!/usr/bin/env python3
"""Extract verifier commands from a goal contract and optionally run them, writing evidence artifacts."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from common import parse_sections


def extract_commands(contract: Path) -> list[str]:
    text = contract.read_text(encoding="utf-8")
    sec = parse_sections(text).get("Verifier", "")
    commands: list[str] = []
    # Prefer fenced shell blocks.
    for m in re.finditer(r"```(?:bash|sh|shell)?\s*\n(.*?)```", sec, re.S | re.I):
        for line in m.group(1).splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                commands.append(s)
    # Also accept inline `command` bullets that look command-like.
    for m in re.finditer(r"`([^`]+)`", sec):
        c = m.group(1).strip()
        if re.match(r"^(npm|pnpm|yarn|pytest|python|python3|go|cargo|mvn|gradle|make|just|tox|ruff|eslint|vitest|jest|bun|deno)\b", c):
            commands.append(c)
    return list(dict.fromkeys(commands))


def run(commands: list[str], evidence_dir: Path, timeout: int) -> dict:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for idx, cmd in enumerate(commands, 1):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = evidence_dir / f"{ts}-verifier-{idx}.txt"
        try:
            proc = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
            output = proc.stdout
            code = proc.returncode
        except subprocess.TimeoutExpired as e:
            output = (e.stdout or "") + f"\nTIMEOUT after {timeout}s\n"
            code = 124
        out_path.write_text(f"$ {cmd}\nexit_code={code}\n\n{output}", encoding="utf-8")
        results.append({"command": cmd, "exit_code": code, "evidence": str(out_path)})
    return {"ok": all(r["exit_code"] == 0 for r in results), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", nargs="?", default=".goals/current.md")
    parser.add_argument("--evidence-dir", default=".goals/evidence/verifiers")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--run", action="store_true", help="Actually run extracted commands. Without this, only list them.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    commands = extract_commands(Path(args.contract))
    if not args.run:
        result = {"commands": commands, "ran": False, "note": "Pass --run to execute verifier commands."}
    else:
        result = {"commands": commands, "ran": True, **run(commands, Path(args.evidence_dir), args.timeout)}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if not commands:
            print("No executable verifier commands found in contract. Use manual/human/MCP verifier as specified.")
        for c in commands:
            print(c)
        if args.run:
            for r in result["results"]:
                print(f"exit {r['exit_code']}: {r['command']} -> {r['evidence']}")
    return 0 if (not args.run or result.get("ok", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
