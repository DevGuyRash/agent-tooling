#!/usr/bin/env python3
"""Launch a frozen goal with an external bound, then verify and audit it.

The live-fire lesson: no in-conversation mechanism can be the bound. The
executor honors budget text voluntarily, hooks may be inert on a given
runtime, and a stop gate can only nudge — the one guarantee that survived
live fire was the external wall-clock kill. Launching through this wrapper
is the supported way to run a /goal unattended.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import contract_lock_status
from render_goal import RenderRefused, render

SCRIPTS = Path(__file__).resolve().parent


def _run_script(name: str, args: list, cwd: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args, "--json"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=str(cwd), timeout=300,
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": f"{name} produced no JSON", "stderr": proc.stderr.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", nargs="?", default=".", help="Goal workspace (contains .goals/)")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="Hard wall-clock ceiling in seconds for the executor (default 1800)")
    parser.add_argument("--exec-cmd", default="codex exec -",
                        help="Executor command; receives the rendered /goal on stdin (default: 'codex exec -')")
    parser.add_argument("--skip-audit", action="store_true", help="Launch only; skip verifier run and audit")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ws = Path(args.workspace).resolve()
    contract = ws / ".goals" / "current.md"
    status = contract_lock_status(contract)
    if not status.get("locked") or status.get("matched") is False:
        print(f"LAUNCH REFUSED: contract is not locked/matched ({status.get('reason')}). "
              f"Lock it first: validate_goal.py {contract} --write-hash", file=sys.stderr)
        return 2
    try:
        rendered = render(contract)
    except RenderRefused as exc:
        print(f"LAUNCH REFUSED: {exc.reason}", file=sys.stderr)
        return 2

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    transcript = ws / ".goals" / "evidence" / "transcripts" / f"{ts}.log"
    transcript.parent.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc)
    outcome, exit_code = "exited", None
    with transcript.open("w", encoding="utf-8") as log:
        try:
            proc = subprocess.run(
                args.exec_cmd, shell=True, input=rendered, text=True,
                stdout=log, stderr=subprocess.STDOUT, cwd=str(ws), timeout=args.timeout,
            )
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            outcome = "timeout"
    duration = round((datetime.now(timezone.utc) - started).total_seconds(), 1)

    result = {
        "outcome": outcome,
        "executor_exit_code": exit_code,
        "duration_seconds": duration,
        "timeout_seconds": args.timeout,
        "transcript": str(transcript),
        "hash_after_run": contract_lock_status(contract),
    }

    if not args.skip_audit:
        result["verifiers"] = _run_script(
            "run_verifiers.py",
            [str(contract), "--run", "--evidence-dir", str(ws / ".goals" / "evidence" / "verifiers")], ws)
        reports = sorted((ws / ".goals" / "reports").glob("*.md")) if (ws / ".goals" / "reports").exists() else []
        audit_args = [str(contract), "--evidence-dir", str(ws / ".goals" / "evidence")]
        if reports:
            audit_args += ["--report", str(reports[-1])]
        result["audit"] = _run_script("audit_goal.py", audit_args, ws)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"outcome: {outcome} (executor exit {exit_code}, {duration}s of {args.timeout}s ceiling)")
        print(f"transcript: {transcript}")
        print(f"contract hash after run: {result['hash_after_run'].get('reason')}")
        if "audit" in result:
            print(f"verifier overall_passed: {result['verifiers'].get('overall_passed')}")
            print(f"audit result: {result['audit'].get('result')}")

    if outcome == "timeout":
        return 124
    if args.skip_audit:
        return 0 if exit_code == 0 else 1
    return 0 if result.get("audit", {}).get("result") == "achieved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
