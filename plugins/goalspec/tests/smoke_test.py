#!/usr/bin/env python3
"""Fast smoke test for GoalSpec plugin packaging and deterministic helpers."""
from __future__ import annotations

import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "authoring-goals" / "scripts"
HOOKS = ROOT / "hooks" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HOOKS))
os.environ["GOALSPEC_NO_GIT"] = "1"

from validate_goal import validate  # noqa: E402
from render_goal import render  # noqa: E402
from score_goal_risk import score  # noqa: E402
from extract_candidates import extract  # noqa: E402
from audit_goal import audit  # noqa: E402
from init_project import init  # noqa: E402
from select_goal import parse_goals_md, parse_graph, select  # noqa: E402
from graph_goal import load as load_graph, contract_metadata  # noqa: E402
from run_verifiers import extract_commands  # noqa: E402
from common import sha256_file  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    files = list((SCRIPTS).glob("*.py")) + list((HOOKS).glob("*.py"))
    for f in files:
        py_compile.compile(str(f), doraise=True)

    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert_true(manifest["name"] == "goalspec", "manifest name")
    assert_true(manifest["skills"] == "./skills/", "manifest skills path")
    assert_true("hooks" not in manifest, "Codex manifest leaves hooks on default path")
    assert_true((ROOT / "hooks" / "hooks.json").exists(), "default hooks file exists")

    hook_cfg = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    for event in ["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"]:
        assert_true(event in hook_cfg["hooks"], f"missing hook event {event}")
    prompt_command = hook_cfg["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert_true("${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}" in prompt_command, "hook command supports both host roots")

    contract = FIXTURES / "contracts" / "G-001-fix-password-reset.md"
    v = validate(contract)
    assert_true(v["ok"], f"sample contract validates: {v}")
    r = render(contract)
    assert_true(r.startswith("/goal "), "render starts with /goal")
    assert_true("current.md" in r and "sha256" in r, "render references source and hash")
    risk = score("Improve the whole app as much as possible")
    assert_true(risk["forever_risk"] in {"high", "extreme"}, "risk scoring catches runaway phrasing")
    cands = extract([str(FIXTURES / "raw-inputs")], max_files=20, max_candidates=10)
    assert_true(len(cands) >= 1, "candidate extraction finds sample candidates")
    a = audit(contract, FIXTURES / "reports" / "G-001-sample-report.md", FIXTURES / "reports")
    # The sample report declares "inconclusive" and there is no verifier result file:
    # report headings + a non-empty evidence dir must NOT certify achievement (G-1 oracle gate).
    assert_true(a["result"] == "inconclusive", f"sample without verifier result is inconclusive, not achieved: {a}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        initialized = init(tmp, overwrite=False, install_agents=True, append_agents_md=True)
        assert_true((tmp / ".goals" / "GOALS.md").exists(), "init creates GOALS.md")
        assert_true((tmp / ".goals" / "graph.json").exists(), "init creates graph")
        assert_true((tmp / "AGENTS.md").exists(), "init appends AGENTS.md")
        assert_true((tmp / ".codex" / "agents" / "goal-auditor.toml").exists(), "init installs agent template")

        shutil.copyfile(contract, tmp / ".goals" / "current.md")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_goal.py"), str(tmp / ".goals" / "current.md"), "--write-hash", "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"},
            timeout=30,
        )
        assert_true(proc.returncode == 0, f"validate --write-hash: {proc.stderr} {proc.stdout}")
        assert_true((tmp / ".goals" / "current.sha256").exists(), "hash lock written")

        event = {
            "cwd": str(tmp),
            "tool_name": "apply_patch",
            "tool_input": {"command": "*** Begin Patch\n*** Update File: .goals/current.md\n@@\n-x\n+y\n*** End Patch"},
        }
        proc = subprocess.run(
            [sys.executable, str(HOOKS / "scope_guard.py")],
            input=json.dumps(event),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PLUGIN_ROOT": str(ROOT), "GOALSPEC_NO_GIT": "1"},
            timeout=30,
        )
        assert_true("permissionDecision" in proc.stdout, f"scope guard denied protected edit: {proc.stdout} {proc.stderr}")

    entries = parse_goals_md(FIXTURES / "registries" / "mixed-GOALS.md")
    selected = select(entries)
    assert_true(selected["selected"] is not None, "select_goal chooses a ready sample")
    gid, node = contract_metadata(contract)
    assert_true(gid.startswith("G-"), "graph metadata extracts goal id")
    cmds = extract_commands(contract)
    assert_true(isinstance(cmds, list), "verifier command extraction returns list")

    # Edge case: an incomplete contract fails validation AND yields concrete repair hints.
    with tempfile.TemporaryDirectory() as td2:
        bad_path = Path(td2) / "bad.md"
        bad_path.write_text("# Goal Contract: incomplete\n\n## Objective\nDo a thing\n", encoding="utf-8")
        bad = validate(bad_path)
        assert_true(not bad["ok"], "incomplete contract fails validation")
        assert_true(len(bad.get("repairs", [])) >= 1, "failed validation emits repair hints")

    # Edge case: a dependency cycle in the graph must not hang or crash selection.
    cyclic = {
        "schema": "goalspec.graph.v1",
        "nodes": {
            "G-001": {"title": "A", "status": "ready", "risk": "low"},
            "G-002": {"title": "B", "status": "ready", "risk": "low"},
        },
        "edges": [
            {"from": "G-001", "type": "depends_on", "to": "G-002"},
            {"from": "G-002", "type": "depends_on", "to": "G-001"},
        ],
    }
    with tempfile.TemporaryDirectory() as td3:
        gpath = Path(td3) / "graph.json"
        gpath.write_text(json.dumps(cyclic), encoding="utf-8")
        sel = select(parse_graph(gpath))
        assert_true("selected" in sel, "select handles a cyclic graph without crashing")

    # G-1: the goalspec.verifier.v1 result file is the deterministic oracle for
    # "achieved". Report headings and a non-empty evidence dir are necessary but
    # never sufficient — only a passing verifier result can certify achievement.
    with tempfile.TemporaryDirectory() as td4:
        goals = Path(td4) / ".goals"
        ev = goals / "evidence" / "verifiers"
        goals.mkdir(parents=True)

        def write_contract(cmd: str) -> Path:
            c = goals / "current.md"
            c.write_text(
                "# Goal Contract: G-900 Verifier Gate\n\n"
                "## Objective\nProve the verifier-pass gate.\n\n"
                "## Terminal State\nThis goal is complete when:\n"
                "- The demo verifier exits 0.\n- The audit oracle reads the verifier result.\n\n"
                "## Verifier\nCompletion must be verified by:\n\n"
                "```bash\n" + cmd + "\n```\n\n"
                "## Evidence Required\n- Files changed\n- Commands run\n- Budget used\n- Follow-up candidates\n",
                encoding="utf-8",
            )
            # Lock the hash so a passing verifier can be certified (hash_matched True).
            (goals / "current.sha256").write_text(f"{sha256_file(c)}  current.md\n", encoding="utf-8")
            return c

        def write_report(decl: str) -> Path:
            r = goals / "reports" / "report.md"
            r.parent.mkdir(parents=True, exist_ok=True)
            r.write_text(
                "# Goal Report: G-900\n\n## Result\n" + decl + "\n\n"
                "## Files Changed\n- none\n\n## Commands Run\n```text\ndemo\n```\n\n"
                "## Evidence\n- .goals/evidence/verifiers/result.json\n\n"
                "## Budget Used\n- iterations: 1\n\n## Remaining Risks\n- none\n\n"
                "## Follow-Up Candidates\n- none\n",
                encoding="utf-8",
            )
            return r

        def run_verifiers_cli(contract: Path) -> None:
            subprocess.run(
                [sys.executable, str(SCRIPTS / "run_verifiers.py"), str(contract), "--run",
                 "--evidence-dir", str(ev), "--json"],
                cwd=td4, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=60,
            )

        # Passing verifier (`true` -> exit 0) + report sections + matching hash => achieved.
        contract = write_contract("true")
        report = write_report("achieved")
        run_verifiers_cli(contract)
        assert_true((ev / "result.json").exists(), "run_verifiers writes the goalspec.verifier.v1 result file")
        rj = json.loads((ev / "result.json").read_text(encoding="utf-8"))
        assert_true(rj["schema"] == "goalspec.verifier.v1" and rj["overall_passed"] is True,
                    f"verifier result schema/pass recorded: {rj}")
        a_pass = audit(contract, report, goals / "evidence")
        assert_true(a_pass["result"] == "achieved", f"passing verifier result => achieved: {a_pass}")

        # Same report + evidence, but verifier result REMOVED => never achieved.
        (ev / "result.json").unlink()
        a_missing = audit(contract, report, goals / "evidence")
        assert_true(a_missing["result"] == "inconclusive",
                    f"headings + evidence without a verifier result => inconclusive: {a_missing}")

        # Failing verifier (`false` -> exit 1) => not achieved, even with a full report and matching hash.
        contract = write_contract("false")
        report = write_report("achieved")
        run_verifiers_cli(contract)
        rj = json.loads((ev / "result.json").read_text(encoding="utf-8"))
        assert_true(rj["overall_passed"] is False, f"failing verifier recorded overall_passed false: {rj}")
        a_fail = audit(contract, report, goals / "evidence")
        assert_true(a_fail["result"] == "not achieved", f"failing verifier result => not achieved: {a_fail}")

    print("GoalSpec full smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
