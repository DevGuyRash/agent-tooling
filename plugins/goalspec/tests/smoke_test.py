#!/usr/bin/env python3
"""Fast smoke test for GoalSpec plugin packaging and deterministic helpers."""
from __future__ import annotations

import json
import os
import py_compile
import re
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
from render_goal import render, RenderRefused  # noqa: E402
from score_goal_risk import score  # noqa: E402
from extract_candidates import extract  # noqa: E402
from audit_goal import audit  # noqa: E402
from init_project import init  # noqa: E402
from select_goal import parse_goals_md, parse_graph, select  # noqa: E402
from graph_goal import load as load_graph, contract_metadata  # noqa: E402
from run_verifiers import extract_commands  # noqa: E402
from inventory_capabilities import inventory  # noqa: E402
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
    # G-2 freeze gate: render refuses an unlocked contract by default; --allow-unlocked previews it.
    try:
        render(contract)
        raise AssertionError("render must refuse an unlocked/mismatched contract by default")
    except RenderRefused:
        pass
    r = render(contract, allow_unlocked=True)
    assert_true(r.startswith("/goal "), "render --allow-unlocked starts with /goal")
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

        # Once locked, render succeeds by default (no --allow-unlocked needed).
        locked_render = render(tmp / ".goals" / "current.md")
        assert_true(locked_render.startswith("/goal "), "locked contract renders by default")
        # The render CLI refuses an unlocked contract with a non-zero exit.
        rproc = subprocess.run(
            [sys.executable, str(SCRIPTS / "render_goal.py"), str(contract)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=30,
        )
        assert_true(rproc.returncode == 2 and "REFUSED" in rproc.stderr,
                    f"render CLI refuses unlocked by default: rc={rproc.returncode} {rproc.stderr}")

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

    # G-2: the conformance probe drives every wired hook with synthetic input and
    # confirms each emits its documented Codex decision shape (UserPromptSubmit
    # block, PreToolUse deny for Bash + apply_patch, PreToolUse mcp no-op,
    # PostToolUse capture for Bash + mcp, Stop allow=no-stdout, Stop block=JSON)
    # plus PreToolUse/PostToolUse mcp__ matcher parity.
    probe_proc = subprocess.run(
        [sys.executable, str(HOOKS / "conformance_probe.py"), "selftest", "--json"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=120,
    )
    assert_true(probe_proc.returncode == 0, f"conformance probe selftest exits 0: {probe_proc.stderr}")
    probe = json.loads(probe_proc.stdout)
    assert_true(probe["overall_conforms"], f"all wired hooks conform to documented I/O: {probe}")
    assert_true(probe["matcher_parity"]["conforms"], "PreToolUse matcher has mcp__ parity with PostToolUse")
    by_surface = {(r["surface"], r["tool"]): r["decision"] for r in probe["rows"]}
    assert_true(by_surface.get(("Stop", "allow")) == "noop", "Stop allow path emits no stdout")
    assert_true(by_surface.get(("Stop", "block")) == "block", "Stop block path emits documented JSON")
    assert_true(by_surface.get(("UserPromptSubmit", None)) == "block", "UserPromptSubmit block tested")

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
        vc = write_contract("true")
        vr = write_report("achieved")
        run_verifiers_cli(vc)
        assert_true((ev / "result.json").exists(), "run_verifiers writes the goalspec.verifier.v1 result file")
        rj = json.loads((ev / "result.json").read_text(encoding="utf-8"))
        assert_true(rj["schema"] == "goalspec.verifier.v1" and rj["overall_passed"] is True,
                    f"verifier result schema/pass recorded: {rj}")
        a_pass = audit(vc, vr, goals / "evidence")
        assert_true(a_pass["result"] == "achieved", f"passing verifier result => achieved: {a_pass}")

        # Same report + evidence, but verifier result REMOVED => never achieved.
        (ev / "result.json").unlink()
        a_missing = audit(vc, vr, goals / "evidence")
        assert_true(a_missing["result"] == "inconclusive",
                    f"headings + evidence without a verifier result => inconclusive: {a_missing}")

        # Failing verifier (`false` -> exit 1) => not achieved, even with a full report and matching hash.
        vc = write_contract("false")
        vr = write_report("achieved")
        run_verifiers_cli(vc)
        rj = json.loads((ev / "result.json").read_text(encoding="utf-8"))
        assert_true(rj["overall_passed"] is False, f"failing verifier recorded overall_passed false: {rj}")
        a_fail = audit(vc, vr, goals / "evidence")
        assert_true(a_fail["result"] == "not achieved", f"failing verifier result => not achieved: {a_fail}")

    # G-3: a sprawling request is preserved as provenance, never as execution scope.
    with tempfile.TemporaryDirectory() as td5:
        goals = Path(td5) / ".goals"
        (goals / "provenance").mkdir(parents=True)
        shutil.copyfile(FIXTURES / "contracts" / "G-001-fix-password-reset.md", goals / "current.md")
        sprawl = ("SPRAWLMARKER make everything better forever, rewrite the world, add dark mode, "
                  "migrate to microservices, and keep improving until perfect")
        req = Path(td5) / "request.txt"
        req.write_text(sprawl + "\n", encoding="utf-8")
        rec = subprocess.run(
            [sys.executable, str(SCRIPTS / "record_provenance.py"),
             "--request", str(req), "--id", "G-001", "--source", "user prompt",
             "--goals-dir", str(goals), "--contract", str(goals / "current.md"),
             "--update-contract", "--json"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=30,
        )
        assert_true(rec.returncode == 0, f"record_provenance ran: {rec.stderr}")
        art_text = (goals / "provenance" / "G-001.md").read_text(encoding="utf-8")
        cur_text = (goals / "current.md").read_text(encoding="utf-8")
        assert_true("SPRAWLMARKER" in art_text, "verbatim request present in provenance artifact")
        assert_true("SPRAWLMARKER" not in cur_text, "verbatim request absent from current.md")
        assert_true("## Provenance" in cur_text and "not execution scope" in cur_text,
                    "current.md carries only a provenance pointer")
        rendered = render(goals / "current.md", allow_unlocked=True)
        assert_true("SPRAWLMARKER" not in rendered, "rendered /goal excludes the verbatim request")
        assert_true("provenance" in rendered.lower(), "rendered /goal marks provenance as non-execution scope")
        a_prov = audit(goals / "current.md", None, goals / "evidence")
        assert_true(a_prov.get("provenance", {}).get("matched") is True,
                    f"audit reads provenance as a matching drift anchor: {a_prov.get('provenance')}")

    # G-4: spine fields are real constraints, not boilerplate.
    base = (FIXTURES / "contracts" / "G-001-fix-password-reset.md").read_text(encoding="utf-8")

    def _swap(text: str, name: str, body: str) -> str:
        return re.sub(rf"(^##\s+{name}\s*\n)(.*?)(?=^##\s|\Z)",
                      lambda m: m.group(1) + "\n" + body + "\n\n", text, flags=re.S | re.M)

    with tempfile.TemporaryDirectory() as td6:
        # Budget with no numeric ceiling and no external gate must fail.
        badb = Path(td6) / "badbudget.md"
        badb.write_text(_swap(base, "Budget", "- Stop when the budget is exhausted even if incomplete."), encoding="utf-8")
        vb = validate(badb)
        assert_true(not vb["ok"] and any("Budget must state" in e for e in vb["errors"]),
                    f"keyword-only budget fails: {vb['errors']}")

        # Scope with both labels but no bullets must fail.
        bads = Path(td6) / "badscope.md"
        bads.write_text(_swap(base, "Scope", "In scope:\n\nOut of scope:"), encoding="utf-8")
        vs = validate(bads)
        assert_true(not vs["ok"] and any("at least one bullet under both" in e for e in vs["errors"]),
                    f"empty in/out scope fails: {vs['errors']}")

        # Unresolved capability placeholders warn.
        badc = Path(td6) / "badcaps.md"
        badc.write_text(_swap(base, "Available Capabilities", "- Skills: [discovered relevant skills]\n- Plugins: [tbd]"), encoding="utf-8")
        vc4 = validate(badc)
        assert_true(any("Available Capabilities still contains unresolved" in w for w in vc4["warnings"]),
                    f"capability placeholders warn: {vc4['warnings']}")

    # .log files are scanned and their failure signals become candidates.
    with tempfile.TemporaryDirectory() as td7:
        (Path(td7) / "run.log").write_text("INFO ok\nERROR something failed\nTraceback (most recent call last)\n", encoding="utf-8")
        logc = extract([td7], max_files=20, max_candidates=10)
        assert_true(any("error signal" in c for c in logc), "extract detects .log failure candidates in a directory scan")

    # Inventory defaults to repo-local and never emits a raw absolute home path.
    inv = inventory()
    assert_true(inv["scanned_home"] is False, "inventory defaults to repo-local (no home scan)")
    assert_true(str(Path.home()) + "/" not in json.dumps(inv), "inventory emits no raw absolute home paths by default")

    # Audit: an active contract with no hash lock is inconclusive, never achieved.
    with tempfile.TemporaryDirectory() as td8:
        g = Path(td8) / ".goals"
        (g / "evidence" / "verifiers").mkdir(parents=True)
        shutil.copyfile(FIXTURES / "contracts" / "G-001-fix-password-reset.md", g / "current.md")
        (g / "evidence" / "verifiers" / "result.json").write_text(json.dumps({
            "schema": "goalspec.verifier.v1", "overall_passed": True,
            "verifiers": [{"verifier": "x", "kind": "command", "exit_code": 0, "evidence": "e", "passed": True}],
        }), encoding="utf-8")
        rep = g / "reports" / "r.md"
        rep.parent.mkdir(parents=True, exist_ok=True)
        rep.write_text("## Result\nachieved\n\n## Files Changed\n- x\n\n## Commands Run\n- x\n\n"
                       "## Evidence\n- x\n\n## Budget Used\n- x\n\n## Remaining Risks\n- x\n\n## Follow-Up Candidates\n- x\n",
                       encoding="utf-8")
        a_nolock = audit(g / "current.md", rep, g / "evidence")
        assert_true(a_nolock["result"] == "inconclusive",
                    f"missing hash lock on active contract => inconclusive, not achieved: {a_nolock}")

    print("GoalSpec full smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
