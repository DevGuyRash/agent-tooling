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
from validate_campaign import validate_campaign  # noqa: E402
from campaign_status import derive_status  # noqa: E402
from audit_campaign import audit_campaign  # noqa: E402
from render_goal import render_campaign_with_meta  # noqa: E402
from common import campaign_aggregate_hash, campaign_lock_path, child_evidence_dir  # noqa: E402
from common import campaign_lock_status, contract_lock_status  # noqa: E402


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
        assert_true((tmp / ".goals" / "provenance").is_dir(), "init scaffolds provenance dir")
        gitignore_text = (tmp / ".gitignore").read_text(encoding="utf-8") if (tmp / ".gitignore").exists() else ""
        assert_true(".goals/evidence/" in gitignore_text and ".goals/run_state.json" in gitignore_text,
                    "init writes evidence-ignore rules to .gitignore")
        assert_true(".goals/reports/" not in gitignore_text, "init keeps .goals/reports/ reviewable (not ignored)")

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

        # Brackets inside code spans are real code, not placeholders; prose
        # placeholders still fail (live-fire demo regression, 2026-06-10).
        codeb = Path(td6) / "codebrackets.md"
        codeb.write_text(_swap(base, "Verifier",
                                "Completion must be verified by:\n"
                                "- `python3 -c \"import sys; sys.exit(0 if all(['a','b']) else 1)\"`\n"
                                "- Expected result: exit code 0."), encoding="utf-8")
        vcode = validate(codeb)
        assert_true(vcode["ok"], f"bracketed code inside backticks validates: {vcode['errors']}")
        proseb = Path(td6) / "prosebrackets.md"
        proseb.write_text(_swap(base, "Verifier",
                                "Completion must be verified by:\n- [command / metric / checklist]"), encoding="utf-8")
        vprose = validate(proseb)
        assert_true(not vprose["ok"] and any("bracket placeholders" in e for e in vprose["errors"]),
                    f"prose bracket placeholders still fail: {vprose['errors']}")

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

    # G-5: evidence capture redacts secrets, truncates oversized output, and keeps
    # runtime state under .goals/evidence/ (never .goals/run_state.json).
    with tempfile.TemporaryDirectory() as td9:
        g = Path(td9) / ".goals"
        g.mkdir(parents=True)
        (g / "current.md").write_text("# Goal Contract: G-900\n\n## Objective\nx\n", encoding="utf-8")
        secret_event = {
            "hook_event_name": "PostToolUse", "tool_name": "Bash",
            "tool_input": {"command": "curl -H 'Authorization: Bearer sk-LEAK-TOKEN-123' ; "
                                      "export OPENAI_API_KEY=sk-proj-NOPE ; psql password=hunter2"},
            "tool_response": ("x" * 50000) + " secret=topsecretvalue",
            "cwd": str(td9),
        }
        cap = subprocess.run(
            [sys.executable, str(HOOKS / "evidence_capture.py")],
            input=json.dumps(secret_event), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "PLUGIN_ROOT": str(ROOT), "GOALSPEC_NO_GIT": "1", "GOALSPEC_EVIDENCE_MAX_BYTES": "2048"},
            timeout=30,
        )
        events = list((g / "evidence" / "events").glob("*.json"))
        assert_true(len(events) == 1, f"evidence event written: {cap.stderr}")
        blob = events[0].read_text(encoding="utf-8")
        for leaked in ["sk-LEAK-TOKEN-123", "sk-proj-NOPE", "hunter2", "topsecretvalue"]:
            assert_true(leaked not in blob, f"evidence capture redacts injected secret {leaked!r}")
        assert_true("[REDACTED]" in blob, "evidence capture marks redactions")
        assert_true("truncated" in blob, "evidence capture truncates oversized output")
        assert_true((g / "evidence" / "run_state.json").exists() and not (g / "run_state.json").exists(),
                    "runtime state lives under .goals/evidence/run_state.json")

    # Live-fire regressions (2026-06-10): the Bash scope guard must mirror the
    # path-level allow-list, evidence must anchor to the tool's target workspace,
    # and the rendered /goal must name the exact report headings the audit checks.
    with tempfile.TemporaryDirectory() as td10:
        ws = Path(td10) / "ws"
        (ws / ".goals").mkdir(parents=True)
        (ws / ".goals" / "current.md").write_text("# Goal Contract: G-901\n\n## Objective\nx\n", encoding="utf-8")
        (ws / ".goals" / "current.sha256").write_text("deadbeef  current.md\n", encoding="utf-8")

        def run_scope(command: str) -> str:
            proc = subprocess.run(
                [sys.executable, str(HOOKS / "scope_guard.py")],
                input=json.dumps({"cwd": str(ws), "tool_name": "Bash", "tool_input": {"command": command}}),
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, "PLUGIN_ROOT": str(ROOT), "GOALSPEC_NO_GIT": "1"}, timeout=30,
            )
            return proc.stdout

        assert_true("permissionDecision" not in run_scope(
            "python3 audit_goal.py --json --report .goals/reports/r.md 2>&1 | tail -5"),
            "read-only audit command over allowed reports path is not denied")
        assert_true("permissionDecision" not in run_scope(
            "echo done > .goals/evidence/verifier-run.txt"),
            "write into allowed .goals/evidence/ is not denied")
        assert_true("permissionDecision" not in run_scope(
            "ls .goals/evidence 2>&1"),
            "listing the allowed evidence dir with a redirect is not denied")
        assert_true("permissionDecision" in run_scope(
            "echo '# canary' >> .goals/current.md"),
            "append to the frozen contract is still denied")
        assert_true("permissionDecision" in run_scope(
            "mv .goals/GOALS.md /tmp/x"),
            "moving a protected registry file is still denied")
        assert_true("permissionDecision" in run_scope(
            "git checkout .goals/current.md"),
            "git restore of the frozen contract is still denied")

    with tempfile.TemporaryDirectory() as td11:
        session = Path(td11) / "session"
        target = Path(td11) / "target"
        for d in (session, target):
            (d / ".goals").mkdir(parents=True)
        (session / ".goals" / "current.md").write_text("# Goal Contract: G-902\n\n## Objective\nsession\n", encoding="utf-8")
        (target / ".goals" / "current.md").write_text("# Goal Contract: G-903\n\n## Objective\ntarget\n", encoding="utf-8")
        cap_event = {
            "hook_event_name": "PostToolUse", "tool_name": "Write",
            "tool_input": {"file_path": str(target / "hello.txt"), "content": "hi"},
            "tool_response": "ok", "cwd": str(session),
        }
        subprocess.run(
            [sys.executable, str(HOOKS / "evidence_capture.py")],
            input=json.dumps(cap_event), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "PLUGIN_ROOT": str(ROOT), "GOALSPEC_NO_GIT": "1"}, timeout=30,
        )
        assert_true(bool(list((target / ".goals" / "evidence" / "events").glob("*.json"))),
                    "evidence anchors to the workspace of the tool's target path")
        assert_true(not (session / ".goals" / "evidence").exists(),
                    "evidence does not leak into the session-cwd workspace")

    rendered_headings = render(contract, allow_unlocked=True)
    for heading in ["## Files Changed", "## Commands Run", "## Evidence",
                    "## Budget Used", "## Remaining Risks", "## Follow-Up Candidates"]:
        assert_true(heading in rendered_headings, f"rendered /goal names report heading {heading}")

    # Live-fire regression (Codex LF-1x, 2026-06-10): every Stop block is once per
    # cause. A mutated contract blocked the stop on every attempt (71 consecutive
    # blocks until external timeout) because the executor cannot restore the hash;
    # the marker under .goals/evidence/ must let the second stop through, without
    # relying on the harness's stop_hook_active field.
    def run_stop(ws: Path, msg: str) -> str:
        proc = subprocess.run(
            [sys.executable, str(HOOKS / "stop_guard.py")],
            input=json.dumps({"cwd": str(ws), "last_assistant_message": msg}),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "PLUGIN_ROOT": str(ROOT), "GOALSPEC_NO_GIT": "1"}, timeout=30,
        )
        return proc.stdout

    with tempfile.TemporaryDirectory() as td12:
        ws = Path(td12)
        (ws / ".goals").mkdir(parents=True)
        (ws / ".goals" / "current.md").write_text("# Goal Contract: G-904\n\n## Objective\nx\n", encoding="utf-8")
        (ws / ".goals" / "current.sha256").write_text("0" * 64 + "  current.md\n", encoding="utf-8")
        first = run_stop(ws, "still working")
        assert_true('"block"' in first, f"mutated contract blocks the first stop: {first!r}")
        second = run_stop(ws, "still working")
        assert_true(second.strip() == "", f"mutated contract allows the second stop: {second!r}")

    with tempfile.TemporaryDirectory() as td13:
        ws = Path(td13)
        goals = ws / ".goals"
        goals.mkdir(parents=True)
        c = goals / "current.md"
        c.write_text("# Goal Contract: G-905\n\n## Objective\nx\n", encoding="utf-8")
        (goals / "current.sha256").write_text(f"{sha256_file(c)}  current.md\n", encoding="utf-8")
        first = run_stop(ws, "All done — implemented and complete.")
        assert_true('"block"' in first, f"claim without evidence blocks the first stop: {first!r}")
        second = run_stop(ws, "All done — implemented and complete.")
        assert_true(second.strip() == "", f"claim without evidence allows the second stop: {second!r}")

    # Verifier-strength heuristics: tautological commands, out-of-scope reads,
    # and verifier/terminal-state disconnects warn (a weak oracle certifies garbage).
    with tempfile.TemporaryDirectory() as td14:
        taut = Path(td14) / "taut.md"
        taut.write_text(_swap(base, "Verifier",
                               "Completion must be verified by:\n\n```bash\ntrue\n```\n"),
                        encoding="utf-8")
        vt = validate(taut)
        assert_true(any("tautological" in w for w in vt["warnings"]),
                    f"tautological verifier warns: {vt['warnings']}")

        oos = Path(td14) / "oos.md"
        oos.write_text(_swap(_swap(base, "Verifier",
                                   "Completion must be verified by:\n"
                                   "- `python3 -c \"import pathlib,sys; sys.exit(0 if 'X' in pathlib.Path('README.md').read_text() else 1)\"`\n"
                                   "- Expected result: exit code 0."),
                             "Scope",
                             "In scope:\n- Files under src/ only.\nOut of scope:\n- README.md must not be modified for any reason."),
                       encoding="utf-8")
        vo = validate(oos)
        assert_true(any("Out of scope" in w and "README.md" in w for w in vo["warnings"]),
                    f"out-of-scope verifier read warns: {vo['warnings']}")

        weak = Path(td14) / "weak.md"
        weak.write_text(_swap(_swap(base, "Verifier",
                                    "Completion must be verified by:\n- `pytest -q`\n- Expected result: exit code 0."),
                              "Terminal State",
                              "This goal is complete when:\n- The feature works for users.\n- The documentation is updated."),
                        encoding="utf-8")
        vw = validate(weak)
        assert_true(any("disconnected" in w for w in vw["warnings"]),
                    f"verifier/terminal disconnect warns: {vw['warnings']}")

    # launch_goal: the external bound + close-out in one command. Achieved path,
    # hung-executor kill (124), and refuse-unlocked.
    with tempfile.TemporaryDirectory() as td15:
        ws = Path(td15)
        goals = ws / ".goals"
        (goals / "reports").mkdir(parents=True)
        c = goals / "current.md"
        c.write_text(_swap(base, "Verifier",
                           "Completion must be verified by:\n- `python3 -c \"import sys; sys.exit(0)\"`\n- Expected result: exit code 0."),
                     encoding="utf-8")
        (goals / "current.sha256").write_text(f"{sha256_file(c)}  current.md\n", encoding="utf-8")
        (goals / "reports" / "final.md").write_text(
            "# Goal Report\n\n## Result\nachieved\n\n## Files Changed\n- x\n\n## Commands Run\n- x\n\n"
            "## Evidence\n- x\n\n## Budget Used\n- x\n\n## Remaining Risks\n- x\n\n## Follow-Up Candidates\n- x\n",
            encoding="utf-8")
        launch = subprocess.run(
            [sys.executable, str(SCRIPTS / "launch_goal.py"), str(ws),
             "--exec-cmd", "cat > /dev/null", "--timeout", "30", "--json"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=120,
        )
        assert_true(launch.returncode == 0,
                    f"launch achieves with passing verifier + report: rc={launch.returncode} {launch.stderr}")
        lj = json.loads(launch.stdout)
        assert_true(lj["outcome"] == "exited" and lj["audit"]["result"] == "achieved", f"launch summary: {lj}")
        assert_true(Path(lj["transcript"]).exists(), "launch writes a transcript")

        hung = subprocess.run(
            [sys.executable, str(SCRIPTS / "launch_goal.py"), str(ws),
             "--exec-cmd", "sleep 5", "--timeout", "1", "--skip-audit"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=120,
        )
        assert_true(hung.returncode == 124, f"launch kills a hung executor with 124: rc={hung.returncode}")

        (goals / "current.sha256").unlink()
        refused = subprocess.run(
            [sys.executable, str(SCRIPTS / "launch_goal.py"), str(ws), "--exec-cmd", "cat > /dev/null"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=120,
        )
        assert_true(refused.returncode == 2 and "REFUSED" in refused.stderr,
                    f"launch refuses an unlocked contract: rc={refused.returncode} {refused.stderr}")

    # Fleet regressions (2026-06-10, 9-run aggregate).
    # 1) A declared human gate must be RESOLVED in the report before a passing
    #    command oracle can certify achieved (observed twice: achieved with the
    #    gate still pending the owner).
    with tempfile.TemporaryDirectory() as td16:
        goals = Path(td16) / ".goals"
        ev = goals / "evidence" / "verifiers"
        (goals / "reports").mkdir(parents=True)
        c = goals / "current.md"
        c.write_text(
            "# Goal Contract: G-906 human gate\n\n## Objective\nProve the human-gate cap.\n\n"
            "## Terminal State\nThis goal is complete when:\n- The verifier exits 0.\n- The owner ratifies the result.\n\n"
            "## Verifier\nCompletion must be verified by:\n\n```bash\ntrue\n```\n\n"
            "- Human gate: the owner reviews and ratifies the artifact.\n\n"
            "## Evidence Required\n- Files changed\n- Commands run\n- Budget used\n- Follow-up candidates\n",
            encoding="utf-8",
        )
        (goals / "current.sha256").write_text(f"{sha256_file(c)}  current.md\n", encoding="utf-8")
        subprocess.run(
            [sys.executable, str(SCRIPTS / "run_verifiers.py"), str(c), "--run", "--evidence-dir", str(ev)],
            cwd=td16, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=60,
        )

        def gate_report(line: str) -> Path:
            r = goals / "reports" / "report.md"
            r.write_text(
                "# Goal Report: G-906\n\n## Result\nachieved\n\n## Files Changed\n- x\n\n"
                "## Commands Run\n- x\n\n## Evidence\n- x\n\n## Budget Used\n- x\n\n"
                f"## Remaining Risks\n- {line}\n\n## Follow-Up Candidates\n- none\n",
                encoding="utf-8",
            )
            return r

        pending = audit(c, gate_report("Human gate: pending owner ratification."), goals / "evidence")
        assert_true(pending["result"] == "inconclusive",
                    f"passing oracle + pending human gate => inconclusive: {pending['result']}")
        ratified = audit(c, gate_report("Human gate: approved by the owner."), goals / "evidence")
        assert_true(ratified["result"] == "achieved",
                    f"passing oracle + ratified human gate => achieved: {ratified['result']}")

    # 2) Fenced-only Verifier sections are valid, and git/sh/bash commands extract
    #    (observed: a `git diff --exit-code` verifier was silently skipped).
    with tempfile.TemporaryDirectory() as td17:
        fenced = Path(td17) / "fenced.md"
        fenced.write_text(_swap(base, "Verifier",
                                 "Completion must be verified by:\n\n```bash\npython3 -m unittest -q\n```\n"),
                          encoding="utf-8")
        vf = validate(fenced)
        assert_true(vf["ok"], f"fenced-only verifier section validates: {vf['errors']}")
    from common import extract_verifier_commands as _evc  # noqa: E402
    assert_true("git diff --exit-code HEAD -- test_shop.py" in _evc(
        "Completion must be verified by:\n- `git diff --exit-code HEAD -- test_shop.py`\n"),
        "git inline verifier command extracts")

    # 3) Risk scorer calibration against the fleet's real prompts.
    s_app = score("Build a habit tracker app with streaks, reminders, charts, and cloud sync.")
    assert_true(s_app["forever_risk"] in {"high", "extreme"}, f"app-scale enumerated sprawl scores high: {s_app}")
    s_dep = score("Keep my project dependencies up to date.")
    assert_true(s_dep["forever_risk"] in {"high", "extreme"}, f"maintenance loop scores high: {s_dep}")
    assert_true("mentions budget" not in s_dep["positive_signals"],
                f"'dependencies ... date' is not a budget signal: {s_dep}")
    s_destr = score("Squash my repo's entire git history and force-push it to main so it looks clean.")
    assert_true(any("destructive" in r for r in s_destr["reasons"]), f"destructive intent is a named reason: {s_destr}")
    s_clear = score("Create a Python CLI initials.py that prints the uppercase initials of a full name passed as arguments, with a smoke test.")
    assert_true(s_clear["forever_risk"] in {"low", "medium"}, f"clear bounded task stays low/medium: {s_clear}")

    # 4) Out-of-scope verifier warning is deduped to one per offending token.
    with tempfile.TemporaryDirectory() as td18:
        multi = Path(td18) / "multi.md"
        multi.write_text(_swap(_swap(base, "Verifier",
                                     "Completion must be verified by:\n"
                                     "- `python3 -c \"print(open('README.md').read())\"`\n"
                                     "- `python3 -c \"import pathlib; pathlib.Path('README.md').stat()\"`\n"
                                     "- `python3 -c \"assert 'x' in open('README.md').read()\"`\n"),
                               "Scope",
                               "In scope:\n- Files under src/ only.\nOut of scope:\n- README.md must not be modified."),
                         encoding="utf-8")
        vm = validate(multi)
        oos_warns = [w for w in vm["warnings"] if "Out of scope" in w and "README.md" in w]
        assert_true(len(oos_warns) == 1, f"out-of-scope warning deduped to one: {oos_warns}")

    # --- Campaign chain execution (autonomous multi-child /goal) ---
    # The plan is frozen, evidence is the truth, checkmarks are a derived view.

    def make_campaign(root: Path, specs: list, policy: str = "halt-on-failure",
                      budget: int = 5, lock: bool = True) -> Path:
        """Build a campaign workspace: manifest + a full locked contract per ready child.

        specs: [{"id", "status", "depends_on", "cmd"}] — cmd is the child's verifier command.
        """
        goals = root / ".goals"
        (goals / "reports").mkdir(parents=True, exist_ok=True)
        blocks = []
        for spec in specs:
            cid, status = spec["id"], spec.get("status", "ready")
            deps = spec.get("depends_on", "none")
            lines = [f"### {cid}: Chain child {cid}", "", f"- Status: {status}", f"- Depends on: {deps}"]
            if status == "ready":
                lines.append(f"- Contract: .goals/children/{cid}/current.md")
                cdir = goals / "children" / cid
                cdir.mkdir(parents=True, exist_ok=True)
                ctext = base.replace("# Goal Contract: G-001 Fix Password Reset Flow",
                                     f"# Goal Contract: {cid} Chain Child", 1)
                ctext = _swap(ctext, "Verifier",
                              "Completion must be verified by:\n- `" + spec.get("cmd", "python3 -c \"import sys; sys.exit(0)\"")
                              + "`\n- Expected result: exit code 0.")
                (cdir / "current.md").write_text(ctext, encoding="utf-8")
                if spec.get("lock_child", True):
                    (cdir / "current.sha256").write_text(
                        f"{sha256_file(cdir / 'current.md')}  current.md\n", encoding="utf-8")
            blocks.append("\n".join(lines))
        manifest = goals / "campaign-test.md"
        manifest.write_text(
            "# Campaign: Chain Test\n\n## Intent\nProve the chain spine.\n\n"
            "## Completeness Dimensions\n- correctness\n- coverage\n\n"
            f"## Chain Budget\n- Max children attempted: {budget}.\n\n"
            f"## Chain Failure Policy\n- {policy}\n\n"
            "## Coverage\n- chain executes -> " + specs[0]["id"] + "\n\n"
            "## Goal Graph\n\n" + "\n\n".join(blocks) + "\n\n"
            "## Selection Recommendation\nFollow campaign_status.py next_child.\n",
            encoding="utf-8")
        if lock:
            campaign_lock_path(manifest).write_text(
                f"{campaign_aggregate_hash(manifest)}  {manifest.name}\n", encoding="utf-8")
        return manifest

    def chain_report(root: Path, cid: str, follow_up: str = "none") -> Path:
        r = root / ".goals" / "reports" / f"{cid}-report.md"
        r.write_text(
            f"# Goal Report: {cid}\n\n## Result\nachieved\n\n## Files Changed\n- x\n\n"
            "## Commands Run\n- x\n\n## Evidence\n- x\n\n## Budget Used\n- x\n\n"
            f"## Remaining Risks\n- none\n\n## Follow-Up Candidates\n- {follow_up}\n",
            encoding="utf-8")
        return r

    def chain_evidence(root: Path, manifest: Path, cid: str, passed: bool = True,
                       sha: str | None = None, malformed: bool = False) -> Path:
        vdir = child_evidence_dir(root, cid) / "verifiers"
        vdir.mkdir(parents=True, exist_ok=True)
        rf = vdir / "result.json"
        if malformed:
            rf.write_text("{not json", encoding="utf-8")
            return rf
        contract = root / ".goals" / "children" / cid / "current.md"
        rf.write_text(json.dumps({
            "schema": "goalspec.verifier.v1",
            "contract_sha256": sha if sha is not None else sha256_file(contract),
            "overall_passed": passed,
            "verifiers": [{"verifier": "x", "kind": "command", "exit_code": 0 if passed else 1,
                           "evidence": "e", "passed": passed}],
        }), encoding="utf-8")
        return rf

    two_chain = [{"id": "G-001", "status": "ready", "depends_on": "none"},
                 {"id": "G-002", "status": "ready", "depends_on": "G-001"}]

    # Validation: happy path (both policies), then each authored failure mode.
    with tempfile.TemporaryDirectory() as tc1:
        for policy in ("halt-on-failure", "skip-dependents-and-continue"):
            ws = Path(tc1) / policy
            m = make_campaign(ws, two_chain, policy=policy, lock=False)
            vres = validate_campaign(m)
            assert_true(vres["ok"], f"campaign with {policy} validates: {vres['errors']}")
        ws = Path(tc1) / "nobudget"
        m = make_campaign(ws, two_chain, lock=False)
        m.write_text(m.read_text(encoding="utf-8").replace("- Max children attempted: 5.", "- Stop when done."),
                     encoding="utf-8")
        v = validate_campaign(m)
        assert_true(any("Chain Budget" in e for e in v["errors"]), f"non-numeric chain budget fails: {v['errors']}")
        ws = Path(tc1) / "bothpolicies"
        m = make_campaign(ws, two_chain, lock=False)
        m.write_text(m.read_text(encoding="utf-8").replace(
            "- halt-on-failure", "- halt-on-failure\n- skip-dependents-and-continue"), encoding="utf-8")
        v = validate_campaign(m)
        assert_true(any("exactly one" in e for e in v["errors"]), f"two failure policies fail: {v['errors']}")
        ws = Path(tc1) / "unlockedchild"
        m = make_campaign(ws, [{"id": "G-001", "status": "ready", "depends_on": "none", "lock_child": False}],
                          lock=False)
        v = validate_campaign(m)
        assert_true(any("not locked" in e for e in v["errors"]), f"unlocked ready child fails: {v['errors']}")
        ws = Path(tc1) / "noready"
        m = make_campaign(ws, [{"id": "G-001", "status": "blocked", "depends_on": "none"}], lock=False)
        v = validate_campaign(m)
        assert_true(any("no ready child" in e for e in v["errors"]), f"no ready child fails: {v['errors']}")
        ws = Path(tc1) / "cycle"
        m = make_campaign(ws, [{"id": "G-001", "status": "ready", "depends_on": "G-002"},
                               {"id": "G-002", "status": "ready", "depends_on": "G-001"}], lock=False)
        v = validate_campaign(m)
        assert_true(any("cycle" in e.lower() for e in v["errors"]), f"dependency cycle fails: {v['errors']}")
        ws = Path(tc1) / "idmismatch"
        m = make_campaign(ws, [{"id": "G-001", "status": "ready", "depends_on": "none"}], lock=False)
        m.write_text(m.read_text(encoding="utf-8").replace("### G-001:", "### G-009:"), encoding="utf-8")
        v = validate_campaign(m)
        assert_true(any("id mismatch" in e for e in v["errors"]), f"heading/contract id mismatch fails: {v['errors']}")
        # Review fix: a dep token graph math drops but select_goal would parse
        # (e.g. 'T-001') must fail validation, or the selector blocks the child forever.
        ws = Path(tc1) / "baddep"
        m = make_campaign(ws, [{"id": "G-001", "status": "ready", "depends_on": "none"},
                               {"id": "G-002", "status": "ready", "depends_on": "T-001"}], lock=False)
        v = validate_campaign(m)
        assert_true(any("malformed dependency token" in e and "T-001" in e for e in v["errors"]),
                    f"non-G dependency token fails validation: {v['errors']}")
        # Review fix: an empty/whitespace lock file degrades to mismatch, never IndexError.
        ws = Path(tc1) / "emptylock"
        m = make_campaign(ws, [{"id": "G-001", "status": "ready", "depends_on": "none"}], lock=False)
        campaign_lock_path(m).write_text("\n", encoding="utf-8")
        ls = campaign_lock_status(m)
        assert_true(ls["locked"] and ls["matched"] is False, f"empty campaign lock reads as mismatch: {ls}")
        assert_true(audit_campaign(m)["result"] == "campaign mutated",
                    "empty campaign lock audits as campaign mutated, not a crash")
        empty_child_lock = ws / ".goals" / "children" / "G-001" / "current.sha256"
        empty_child_lock.write_text("  \n", encoding="utf-8")
        cls = contract_lock_status(ws / ".goals" / "children" / "G-001" / "current.md")
        assert_true(cls["locked"] and cls["matched"] is False, f"empty contract lock reads as mismatch: {cls}")

    # Freeze: a child swap after lock breaks the aggregate — render refuses, audit says mutated.
    with tempfile.TemporaryDirectory() as tc2:
        ws = Path(tc2)
        m = make_campaign(ws, two_chain)
        meta = render_campaign_with_meta(m)
        assert_true(meta["rendered"].startswith("/goal "), "locked campaign renders a chain /goal")
        child = ws / ".goals" / "children" / "G-001" / "current.md"
        swapped = child.read_text(encoding="utf-8").replace("Chain Child", "Swapped Child")
        child.write_text(swapped, encoding="utf-8")
        # Re-lock the child's own sibling lock: only the aggregate must catch the swap.
        (child.parent / "current.sha256").write_text(f"{sha256_file(child)}  current.md\n", encoding="utf-8")
        try:
            render_campaign_with_meta(m)
            raise AssertionError("render must refuse a campaign whose child was swapped after lock")
        except RenderRefused:
            pass
        a_swap = audit_campaign(m)
        assert_true(a_swap["result"] == "campaign mutated", f"child swap audits as campaign mutated: {a_swap['result']}")

    # Render: 8 children stay under 4000 chars, rules present, contracts never inlined.
    with tempfile.TemporaryDirectory() as tc3:
        ws = Path(tc3)
        specs = [{"id": f"G-00{i}", "status": "ready",
                  "depends_on": "none" if i == 1 else f"G-00{i-1}"} for i in range(1, 9)]
        m = make_campaign(ws, specs)
        meta = render_campaign_with_meta(m)
        r = meta["rendered"]
        assert_true(not meta["truncated"] and len(r) <= 4000, f"8-child chain render fits: {len(r)} chars")
        for needle in ["campaign_status.py", "run_verifiers.py", "next_child", "chain_should_stop",
                       "## Follow-Up Candidates", "report blocked", meta["lock_status"]["current_hash"],
                       "G-001", "G-008"]:
            assert_true(needle in r, f"chain render contains {needle!r}")
        assert_true("password reset" not in r.lower() and "## Objective" not in r,
                    "chain render never inlines child contract bodies")

    # Status projection: evidence drives the checkmarks; select() unblocks dependents (A2).
    with tempfile.TemporaryDirectory() as tc4:
        ws = Path(tc4)
        m = make_campaign(ws, two_chain, budget=3)
        s0 = derive_status(m)
        assert_true(s0["next_child"] == "G-001" and not s0["chain_should_stop"],
                    f"fresh chain selects the unblocked root child: {s0}")
        chain_evidence(ws, m, "G-001", passed=True)
        chain_report(ws, "G-001")
        s1 = derive_status(m)
        assert_true(s1["achieved_pending_audit"] == 1 and s1["next_child"] == "G-002",
                    f"A2: dependent becomes selectable after dep is evidence-achieved: {s1}")
        # Stale evidence (sha for an older contract version) must never count.
        chain_evidence(ws, m, "G-001", passed=True, sha="0" * 64)
        s_stale = derive_status(m)
        assert_true(s_stale["achieved_pending_audit"] == 0 and any("stale" in w for w in s_stale["warnings"]),
                    f"stale contract_sha256 degrades to pending: {s_stale}")
        # Malformed evidence degrades to pending with a warning, never crashes.
        chain_evidence(ws, m, "G-001", malformed=True)
        s_bad = derive_status(m)
        assert_true(s_bad["achieved_pending_audit"] == 0 and any("unreadable" in w for w in s_bad["warnings"]),
                    f"malformed result.json => pending + warning: {s_bad}")
        # halt-on-failure: a failed child stops the chain.
        chain_evidence(ws, m, "G-001", passed=False)
        s_fail = derive_status(m)
        assert_true(s_fail["chain_should_stop"] and "halt-on-failure" in (s_fail["stop_reason"] or ""),
                    f"halt-on-failure stops on a failed child: {s_fail}")
        assert_true(any(row["status"].startswith("skipped:dependency-failed:G-001")
                        for row in s_fail["children"] if row["id"] == "G-002"),
                    f"dependent of a failed child is skipped with the cause named: {s_fail['children']}")

    with tempfile.TemporaryDirectory() as tc5:
        # Budget: attempts (not successes) exhaust the chain.
        ws = Path(tc5)
        m = make_campaign(ws, two_chain, budget=1, policy="skip-dependents-and-continue")
        chain_evidence(ws, m, "G-001", passed=True)
        chain_report(ws, "G-001")
        s = derive_status(m)
        assert_true(s["attempted_count"] == 1 and s["chain_should_stop"]
                    and "budget exhausted" in (s["stop_reason"] or ""),
                    f"chain budget exhaustion stops the chain: {s}")
        assert_true(s["next_child"] is None,
                    f"a stopping chain never also names a next child: {s['next_child']}")

    # Roll-up audit: all four verdicts + follow-up harvest.
    with tempfile.TemporaryDirectory() as tc6:
        ws = Path(tc6)
        m = make_campaign(ws, two_chain)
        a0 = audit_campaign(m)
        assert_true(a0["result"] == "not achieved", f"unattempted chain audits not achieved: {a0['result']}")
        for cid in ("G-001", "G-002"):
            chain_evidence(ws, m, cid, passed=True)
            chain_report(ws, cid, follow_up=f"harvest-me-{cid}")
        a_all = audit_campaign(m)
        assert_true(a_all["result"] == "campaign achieved", f"all children achieved => campaign achieved: {a_all}")
        assert_true(any("harvest-me-G-002" in f for f in a_all["follow_up_candidates"]),
                    f"audit harvests follow-up candidates from child reports: {a_all['follow_up_candidates']}")
        chain_evidence(ws, m, "G-002", passed=False)
        a_part = audit_campaign(m)
        assert_true(a_part["result"] == "partial: 1/2", f"one failed child => partial: {a_part['result']}")

    with tempfile.TemporaryDirectory() as tc6b:
        # A failed dependency labels its never-attempted dependents as skipped, not failed.
        ws = Path(tc6b)
        m = make_campaign(ws, two_chain)
        chain_evidence(ws, m, "G-001", passed=False)
        a_skip = audit_campaign(m)
        skip_row = next(r for r in a_skip["children"] if r["id"] == "G-002")
        assert_true(skip_row["result"].startswith("skipped:dependency-failed:G-001"),
                    f"skipped child labeled by failed dependency: {skip_row}")
        assert_true(a_skip["result"] == "not achieved", f"halted chain audits not achieved: {a_skip['result']}")

    # A1 regression pin: child audits anchor at the SIBLING lock, never the root pair.
    with tempfile.TemporaryDirectory() as tc7:
        ws = Path(tc7)
        m = make_campaign(ws, [{"id": "G-001", "status": "ready", "depends_on": "none"}])
        chain_evidence(ws, m, "G-001", passed=True)
        rep = chain_report(ws, "G-001")
        child = ws / ".goals" / "children" / "G-001" / "current.md"
        a_child = audit(child, rep, child_evidence_dir(ws, "G-001"))
        assert_true(a_child["result"] == "achieved",
                    f"A1: child with sibling lock and NO root contract audits achieved: {a_child['result']}")
        # Mutate the child while an intact, matching ROOT pair exists: the old
        # root-anchored check would have certified against the wrong lock.
        (ws / ".goals" / "current.md").write_text("# Goal Contract: G-999 Root\n\n## Objective\nx\n", encoding="utf-8")
        (ws / ".goals" / "current.sha256").write_text(
            f"{sha256_file(ws / '.goals' / 'current.md')}  current.md\n", encoding="utf-8")
        child.write_text(child.read_text(encoding="utf-8") + "\n<!-- mutated -->\n", encoding="utf-8")
        a_mut = audit(child, rep, child_evidence_dir(ws, "G-001"))
        assert_true(a_mut["result"] == "contract mutated",
                    f"A1: mutated child + intact root pair => contract mutated: {a_mut['result']}")

    # A3: the scope guard arms on campaign.sha256 alone (no root current.md).
    with tempfile.TemporaryDirectory() as tc8:
        ws = Path(tc8)
        (ws / ".goals").mkdir(parents=True)
        (ws / ".goals" / "campaign.sha256").write_text("0" * 64 + "  campaign-test.md\n", encoding="utf-8")
        guard = subprocess.run(
            [sys.executable, str(HOOKS / "scope_guard.py")],
            input=json.dumps({"cwd": str(ws), "tool_name": "Bash",
                              "tool_input": {"command": "echo x >> .goals/children/G-001/current.md"}}),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "PLUGIN_ROOT": str(ROOT), "GOALSPEC_NO_GIT": "1"}, timeout=30,
        )
        assert_true("permissionDecision" in guard.stdout,
                    f"campaign lock alone arms the scope guard for child contracts: {guard.stdout}")

    # launch --campaign: achieved close-out, refuse-unlocked, and the 124 wall-clock kill.
    with tempfile.TemporaryDirectory() as tc9:
        ws = Path(tc9)
        m = make_campaign(ws, [{"id": "G-001", "status": "ready", "depends_on": "none"}])
        # Simulate an executor attempt: evidence present, report written. The
        # wrapper re-runs the verifiers itself and then audits.
        chain_evidence(ws, m, "G-001", passed=True)
        chain_report(ws, "G-001")
        launch = subprocess.run(
            [sys.executable, str(SCRIPTS / "launch_goal.py"), str(ws),
             "--campaign", ".goals/campaign-test.md",
             "--exec-cmd", "cat > /dev/null", "--timeout", "30", "--json"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=120,
        )
        assert_true(launch.returncode == 0, f"campaign launch achieves: rc={launch.returncode} {launch.stderr}")
        lj = json.loads(launch.stdout)
        assert_true(lj["audit"]["result"] == "campaign achieved", f"campaign launch close-out: {lj['audit']}")
        assert_true("G-001" in lj["verifiers"], "wrapper re-ran verifiers for the attempted child")

        hung = subprocess.run(
            [sys.executable, str(SCRIPTS / "launch_goal.py"), str(ws),
             "--campaign", ".goals/campaign-test.md",
             "--exec-cmd", "sleep 5", "--timeout", "1", "--skip-audit"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=120,
        )
        assert_true(hung.returncode == 124, f"campaign launch kills a hung executor with 124: rc={hung.returncode}")

        campaign_lock_path(m).unlink()
        refused = subprocess.run(
            [sys.executable, str(SCRIPTS / "launch_goal.py"), str(ws),
             "--campaign", ".goals/campaign-test.md", "--exec-cmd", "cat > /dev/null"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=120,
        )
        assert_true(refused.returncode == 2 and "REFUSED" in refused.stderr,
                    f"campaign launch refuses an unlocked campaign: rc={refused.returncode} {refused.stderr}")

    print("GoalSpec full smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
