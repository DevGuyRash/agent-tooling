#!/usr/bin/env python3
"""Report which GoalSpec hook surfaces fire and conform to documented Codex I/O.

Codex hook behavior can lag the docs, so this probe never assumes coverage: it
exercises the wired hooks against synthetic events (selftest), or records what
actually fired on the live runtime (observe) and summarizes it (report). When a
configured surface is not confirmed, the probe says so and points at the freeze
backstop — render-refuse-unlocked + the audit hash — instead of pretending the
hook caught everything.

Subcommands:
  selftest [--json]   Drive each wired hook with synthetic input and classify
                      its decision against the documented shape. Offline.
  observe             Wire as a hook: append the event/tool seen to
                      .goals/evidence/conformance/observed.json. Exit 0, no stdout.
  report  [--json]    Summarize configured (hooks.json) vs observed surfaces.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _hook_common import SCRIPTS  # noqa: F401
from common import load_json_stdin, sha256_text

HOOKS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = HOOKS_DIR.parents[1]
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"

# Documented surfaces the probe cares about. Each maps to the event it rides on.
DOCUMENTED_SURFACES = [
    ("UserPromptSubmit", None),
    ("PreToolUse", "Bash"),
    ("PreToolUse", "apply_patch"),
    ("PreToolUse", "mcp__"),
    ("PostToolUse", "Bash"),
    ("PostToolUse", "apply_patch"),
    ("PostToolUse", "mcp__"),
    ("Stop", None),
]

MINIMAL_CONTRACT = (
    "# Goal Contract: G-PROBE\n\n## Objective\nProbe conformance.\n\n"
    "## Terminal State\nThis goal is complete when:\n- a probe runs.\n- it reports.\n\n"
    "## Verifier\nCompletion must be verified by:\n\n```bash\ntrue\n```\n"
)


def classify(stdout: str) -> str:
    """Map a hook's stdout to a documented decision kind."""
    s = stdout.strip()
    if not s:
        return "noop"
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return "invalid-json"
    if not isinstance(data, dict):
        return "json-other"
    hso = data.get("hookSpecificOutput")
    if isinstance(hso, dict):
        if hso.get("permissionDecision") == "deny":
            return "deny"
        if hso.get("additionalContext"):
            return "context"
    if data.get("decision") == "block":
        return "block"
    if data.get("continue") is True:
        return "continue"
    return "json-other"


def _run_hook(script: str, event: dict, cwd: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)],
        input=json.dumps(event),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env={**os.environ, "PLUGIN_ROOT": str(PLUGIN_ROOT), "GOALSPEC_NO_GIT": "1"},
        timeout=30,
    )
    return proc.stdout


def _build_workspace(root: Path) -> Path:
    """A locked, active contract workspace so the freeze-time hooks engage."""
    goals = root / ".goals"
    (goals / "evidence").mkdir(parents=True, exist_ok=True)
    current = goals / "current.md"
    current.write_text(MINIMAL_CONTRACT, encoding="utf-8")
    (goals / "current.sha256").write_text(f"{sha256_text(MINIMAL_CONTRACT)}  current.md\n", encoding="utf-8")
    return goals


def selftest(as_json: bool) -> int:
    with tempfile.TemporaryDirectory() as td:
        ws = str(td)
        _build_workspace(Path(td))
        empty = Path(td) / "empty"
        empty.mkdir()
        patch = "*** Begin Patch\n*** Update File: .goals/current.md\n@@\n-a\n+b\n*** End Patch"
        cases = [
            # (surface, tool, script, event, cwd, expected-decisions)
            ("UserPromptSubmit", None, "prompt_guard.py",
             {"prompt": "/goal complete .goals/current.md", "cwd": str(empty)}, str(empty), {"block"}),
            ("PreToolUse", "Bash", "scope_guard.py",
             {"tool_name": "Bash", "tool_input": {"command": "rm -rf .goals/"}, "cwd": ws}, ws, {"deny"}),
            ("PreToolUse", "apply_patch", "scope_guard.py",
             {"tool_name": "apply_patch", "tool_input": {"command": patch}, "cwd": ws}, ws, {"deny"}),
            ("PreToolUse", "mcp__", "scope_guard.py",
             {"tool_name": "mcp__srv__call", "tool_input": {}, "cwd": ws}, ws, {"noop"}),
            ("PostToolUse", "Bash", "evidence_capture.py",
             {"hook_event_name": "PostToolUse", "tool_name": "Bash",
              "tool_input": {"command": "echo hi"}, "tool_response": "hi", "cwd": ws}, ws, {"context"}),
            ("PostToolUse", "mcp__", "evidence_capture.py",
             {"hook_event_name": "PostToolUse", "tool_name": "mcp__srv__call",
              "tool_input": {}, "tool_response": {"ok": 1}, "cwd": ws}, ws, {"context"}),
            ("Stop", "allow", "stop_guard.py",
             {"last_assistant_message": "still working on it", "cwd": ws}, ws, {"noop"}),
            ("Stop", "block", "stop_guard.py",
             {"last_assistant_message": "All done — implemented and complete.", "cwd": ws}, ws, {"block"}),
        ]
        rows = []
        for surface, tool, script, event, cwd, expected in cases:
            decision = classify(_run_hook(script, event, cwd))
            rows.append({
                "surface": surface,
                "tool": tool,
                "script": script,
                "decision": decision,
                "expected": sorted(expected),
                "conforms": decision in expected,
            })

    matcher_row = _matcher_parity()
    overall = all(r["conforms"] for r in rows) and matcher_row["conforms"]
    out = {
        "mode": "selftest",
        "overall_conforms": overall,
        "rows": rows,
        "matcher_parity": matcher_row,
        "note": "Selftest exercises wired hooks with synthetic input. Live Codex "
                "coverage may lag; render-refuse-unlocked + the audit hash are the freeze backstop.",
    }
    if as_json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print("GoalSpec hook conformance probe (selftest)")
        for r in rows:
            label = f"{r['surface']}:{r['tool']}" if r["tool"] else r["surface"]
            print(f"  {'OK ' if r['conforms'] else 'BAD'} {label:<26} {r['script']:<20} -> {r['decision']}")
        print(f"  {'OK ' if matcher_row['conforms'] else 'BAD'} {'matcher-parity (Pre==Post mcp)':<26} hooks.json -> {matcher_row['reason']}")
        print(f"overall: {'CONFORMS' if overall else 'NONCONFORMING'}")
        print(out["note"])
    return 0 if overall else 1


def _load_hooks_cfg() -> dict:
    try:
        return json.loads(HOOKS_JSON.read_text(encoding="utf-8")).get("hooks", {})
    except (OSError, json.JSONDecodeError):
        return {}


def _matcher_parity() -> dict:
    cfg = _load_hooks_cfg()

    def matcher_for(event: str) -> str:
        entries = cfg.get(event, [])
        return entries[0].get("matcher", "") if entries else ""

    pre = matcher_for("PreToolUse")
    post = matcher_for("PostToolUse")
    conforms = "mcp__" in pre and "mcp__" in post
    return {"pre": pre, "post": post, "conforms": conforms,
            "reason": "mcp__ in both" if conforms else "mcp__ missing from PreToolUse or PostToolUse"}


def _observed_path(cwd: str) -> Path:
    root = Path(cwd or os.getcwd())
    return root / ".goals" / "evidence" / "conformance" / "observed.json"


def observe() -> int:
    event = load_json_stdin()
    cwd = event.get("cwd") or os.getcwd()
    path = _observed_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        data = {}
    seen = data.setdefault("seen", {})
    name = event.get("hook_event_name") or event.get("hookEventName") or "unknown"
    tool = event.get("tool_name") or ""
    key = f"{name}:{tool}" if tool else name
    seen[key] = int(seen.get(key, 0)) + 1
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0  # no stdout: never interfere with the event it rides on


def report(cwd: str, as_json: bool) -> int:
    cfg = _load_hooks_cfg()
    configured_events = sorted(cfg.keys())
    path = _observed_path(cwd)
    observed = {}
    if path.exists():
        try:
            observed = json.loads(path.read_text(encoding="utf-8")).get("seen", {})
        except (OSError, json.JSONDecodeError):
            observed = {}

    def is_observed(event: str, tool) -> bool:
        if not observed:
            return False
        if tool is None:
            return any(k == event or k.startswith(event + ":") for k in observed)
        return any(k == f"{event}:{tool}" or (tool == "mcp__" and k.startswith(f"{event}:mcp__")) for k in observed)

    rows = [{"surface": e, "tool": t, "configured": e in configured_events,
             "observed": is_observed(e, t)} for e, t in DOCUMENTED_SURFACES]
    any_observations = bool(observed)
    out = {
        "mode": "report",
        "configured_events": configured_events,
        "matcher_parity": _matcher_parity(),
        "rows": rows,
        "has_runtime_observations": any_observations,
        "note": ("No runtime observations yet; coverage is CONFIGURED-only. Rely on "
                 "render-refuse-unlocked + the audit hash as the freeze backstop."
                 if not any_observations else
                 "Configured surfaces not in observed are not yet confirmed on this runtime; "
                 "degrade gracefully and lean on render-refuse-unlocked + the audit hash."),
    }
    if as_json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print("GoalSpec hook conformance probe (report)")
        for r in rows:
            label = f"{r['surface']}:{r['tool']}" if r["tool"] else r["surface"]
            print(f"  configured={'Y' if r['configured'] else 'N'} observed={'Y' if r['observed'] else 'N'}  {label}")
        print(out["note"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")
    p_self = sub.add_parser("selftest", help="Drive wired hooks with synthetic input (offline).")
    p_self.add_argument("--json", action="store_true")
    sub.add_parser("observe", help="Record a live event into .goals/evidence/conformance/observed.json.")
    p_report = sub.add_parser("report", help="Summarize configured vs observed surfaces.")
    p_report.add_argument("--json", action="store_true")
    p_report.add_argument("--cwd", default=None)
    args = parser.parse_args()

    if args.cmd == "observe":
        return observe()
    if args.cmd == "report":
        return report(args.cwd or os.getcwd(), getattr(args, "json", False))
    # Default to selftest.
    return selftest(getattr(args, "json", False))


if __name__ == "__main__":
    raise SystemExit(main())
