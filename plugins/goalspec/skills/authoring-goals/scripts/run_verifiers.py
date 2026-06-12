#!/usr/bin/env python3
"""Extract verifier commands from a goal contract and optionally run them, writing evidence artifacts."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from common import (
    VERIFIER_RESULT_NAME,
    VERIFIER_RESULT_SCHEMA,
    check_pinned_companions,
    contract_workspace_root,
    extract_verifier_commands,
    parse_sections,
    sha256_file,
    verifier_kinds,
)


def pin_rows(pins: list[dict]) -> list[dict]:
    """Pin checks as verifier result entries, so the oracle file records them."""
    return [{
        "verifier": f"pinned companion {p['path']}",
        "kind": "pin",
        "exit_code": None,
        "evidence": p["reason"],
        "passed": p["passed"],
        "expected_sha256": p["expected_sha256"],
        "actual_sha256": p["actual_sha256"],
    } for p in pins]


def verifier_section(contract: Path) -> str:
    text = contract.read_text(encoding="utf-8")
    return parse_sections(text).get("Verifier", "")


def extract_commands(contract: Path) -> list[str]:
    return extract_verifier_commands(verifier_section(contract))


def run(commands: list[str], evidence_dir: Path, timeout: int) -> dict:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    verifiers = []
    for idx, cmd in enumerate(commands, 1):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = evidence_dir / f"{ts}-verifier-{idx}.txt"
        try:
            proc = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
            output = proc.stdout
            code = proc.returncode
        except subprocess.TimeoutExpired as e:
            partial = e.stdout or ""
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", "replace")
            output = partial + f"\nTIMEOUT after {timeout}s\n"
            code = 124
        out_path.write_text(f"$ {cmd}\nexit_code={code}\n\n{output}", encoding="utf-8")
        verifiers.append({
            "verifier": cmd,
            "kind": "command",
            "exit_code": code,
            "evidence": str(out_path),
            "passed": code == 0,
        })
    # A run with zero executed verifiers must never read as a pass.
    overall = bool(verifiers) and all(v["passed"] for v in verifiers)
    return {"ok": overall, "overall_passed": overall, "verifiers": verifiers}


def write_result(contract: Path, run_data: dict, result_file: Path, declared_kinds: set) -> Path:
    """Persist the goalspec.verifier.v1 oracle artifact audit reads."""
    payload = {
        "schema": VERIFIER_RESULT_SCHEMA,
        "contract": str(contract),
        "contract_sha256": sha256_file(contract) if contract.exists() else None,
        "generated_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "declared_kinds": sorted(declared_kinds),
        "overall_passed": run_data["overall_passed"],
        "verifiers": run_data["verifiers"],
    }
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", nargs="?", default=".goals/current.md")
    parser.add_argument("--evidence-dir", default=".goals/evidence/verifiers")
    parser.add_argument("--result-file", default=None,
                        help=f"Where to write the {VERIFIER_RESULT_NAME} oracle artifact (default: <evidence-dir>/{VERIFIER_RESULT_NAME}).")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--run", action="store_true", help="Actually run extracted commands. Without this, only list them.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    contract = Path(args.contract)
    section = verifier_section(contract) if contract.exists() else ""
    commands = extract_verifier_commands(section)
    declared = verifier_kinds(section)
    pins = check_pinned_companions(section, contract_workspace_root(contract)) if contract.exists() else []
    failed_pins = [p for p in pins if not p["passed"]]
    if not args.run:
        result = {"commands": commands, "ran": False, "declared_kinds": sorted(declared),
                  "pinned_companions": pins,
                  "note": "Pass --run to execute verifier commands and write the oracle result file."}
    else:
        evidence_dir = Path(args.evidence_dir)
        if failed_pins:
            # A missing/mutated pinned companion invalidates the oracle itself:
            # never execute commands against it; record a loud failure instead.
            run_data = {"ok": False, "overall_passed": False, "verifiers": pin_rows(pins)}
        else:
            run_data = run(commands, evidence_dir, args.timeout)
            run_data["verifiers"] = pin_rows(pins) + run_data["verifiers"]
        result = {"commands": commands, "ran": True, "declared_kinds": sorted(declared), **run_data}
        if commands or failed_pins:
            result_file = Path(args.result_file) if args.result_file else evidence_dir / VERIFIER_RESULT_NAME
            write_result(contract, run_data, result_file, declared)
            result["result_file"] = str(result_file)
        else:
            # No executable command: do not fabricate a pass/fail. Audit treats a
            # missing result file as inconclusive unless a human/artifact/MCP gate is declared.
            result["note"] = "No executable verifier commands found; no oracle result written. Record the human/artifact/MCP gate outcome in the run report."
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if not commands:
            print("No executable verifier commands found in contract. Use the declared human/artifact/MCP verifier and record its outcome in the report.")
            if declared:
                print(f"Declared verifier kinds: {', '.join(sorted(declared))}")
        for p in pins:
            print(f"pin {'ok' if p['passed'] else 'FAIL'} ({p['reason']}): {p['path']}")
        for c in commands:
            print(c)
        if args.run and (commands or failed_pins):
            for v in result["verifiers"]:
                print(f"exit {v['exit_code']} ({'pass' if v['passed'] else 'FAIL'}): {v['verifier']} -> {v['evidence']}")
            print(f"overall_passed={result['overall_passed']} -> {result.get('result_file')}")
    return 0 if (not args.run or result.get("ok", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
