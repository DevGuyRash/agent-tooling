#!/usr/bin/env python3
"""Fast smoke test for GoalSpec plugin packaging and deterministic helpers."""
from __future__ import annotations

import hashlib
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
from render_goal import render_campaign_with_meta, render_with_meta  # noqa: E402
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
    ec_cli = subprocess.run(
        [sys.executable, str(SCRIPTS / "extract_candidates.py"), str(FIXTURES / "raw-inputs"), "--format", "json"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=30)
    assert_true(ec_cli.returncode == 0 and "candidates" in json.loads(ec_cli.stdout),
                f"extract_candidates --format json works (flag parity): {ec_cli.stderr}")
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
        assert_true((tmp / ".codex" / "agents" / "decomposition-reviewer.toml").exists(),
                    "init installs the decomposition-reviewer template")
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

        # evt-0188: requests are arbitrary text. A PRD-shaped request carrying
        # its own ## headings — including hostile ones that collide with the
        # artifact's template sections — must round-trip the drift anchor.
        prd = ("# PRD: sprawling product\n\n## Vision\nEverything forever.\n\n"
               "## Features\n- feature one\n- feature two\n\n"
               "## Source\nthis hostile heading lives inside the request\n\n"
               "## Compiled-Into\nso does this one\n")
        req2 = Path(td5) / "request-prd.md"
        req2.write_text(prd, encoding="utf-8")
        rec2 = subprocess.run(
            [sys.executable, str(SCRIPTS / "record_provenance.py"),
             "--request", str(req2), "--id", "G-001", "--source", "PRD.md",
             "--goals-dir", str(goals), "--contract", str(goals / "current.md"),
             "--update-contract", "--json"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=30,
        )
        assert_true(rec2.returncode == 0, f"record_provenance accepts a PRD-shaped request: {rec2.stderr}")
        art2 = (goals / "provenance" / "G-001.md").read_text(encoding="utf-8")
        # Writer immunity: the hostile request headings appear exactly once,
        # inside the marker envelope, and the template's own Source /
        # Compiled-Into sections survive intact after the request insertion.
        from common import PROVENANCE_REQUEST_BEGIN, PROVENANCE_REQUEST_END  # noqa: E402
        b_idx, e_idx = art2.find(PROVENANCE_REQUEST_BEGIN), art2.rfind(PROVENANCE_REQUEST_END)
        assert_true(0 < b_idx < e_idx, "provenance artifact wraps the request in markers")
        hostile = art2.find("this hostile heading lives inside the request")
        assert_true(b_idx < hostile < e_idx and art2.count("hostile heading") == 1,
                    "hostile request headings stay inside the marker envelope")
        assert_true(re.search(r"^- Request hash: [0-9a-f]{64}$", art2[e_idx:], re.M) is not None,
                    "template Compiled-Into section survives a hostile request")
        a_prd = audit(goals / "current.md", None, goals / "evidence")
        assert_true(a_prd["provenance"]["matched"] is True
                    and a_prd["provenance"].get("matched_via") == "markers",
                    f"PRD-shaped request anchors via markers: {a_prd['provenance']}")

        # Backward compat: a legacy marker-less artifact (old writer shape,
        # request inlined before the template's ## Source) still anchors via
        # the heading-span candidate — even when the request itself contains
        # a ## Source heading (the artifact's own trailing one wins).
        legacy = ("# Provenance: G-001\n\n> Reference only.\n\n## Original Request\n\n"
                  + prd.strip() + "\n\n## Source\n\nPRD.md\n\n## Compiled-Into\n\n"
                  "- Contract: .goals/current.md\n")
        (goals / "provenance" / "G-001.md").write_text(legacy, encoding="utf-8")
        a_leg = audit(goals / "current.md", None, goals / "evidence")
        assert_true(a_leg["provenance"]["matched"] is True
                    and a_leg["provenance"].get("matched_via") == "heading-span",
                    f"legacy heading-bearing artifact anchors via heading-span: {a_leg['provenance']}")

        # Real drift must still alarm: tamper one byte of the preserved request.
        (goals / "provenance" / "G-001.md").write_text(
            legacy.replace("Everything forever.", "Everything, forever."), encoding="utf-8")
        a_drift = audit(goals / "current.md", None, goals / "evidence")
        assert_true(a_drift["provenance"]["matched"] is False,
                    f"tampered request still reads as drift: {a_drift['provenance']}")

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

        # Authoring-closure gap (live EdgeCourt run, 2026-06-11): the plugin's
        # own verification scripts naming the contract are the sanctioned
        # close-out flow and must pass the guard post-lock...
        assert_true("permissionDecision" not in run_scope(
            f"python3 {SCRIPTS}/validate_goal.py .goals/current.md --check-hash --json"),
            "post-lock validate --check-hash naming the contract is not denied")
        assert_true("permissionDecision" not in run_scope(
            f"python3 {SCRIPTS}/render_goal.py .goals/current.md --write .goals/rendered-goal.md --json"),
            "post-lock render --write to the rendered projection is not denied")
        assert_true("permissionDecision" not in run_scope(
            f"python3 {SCRIPTS}/audit_goal.py .goals/current.md --report .goals/reports/r.md --json"),
            "post-lock audit naming the contract is not denied")
        # ...while the write-capable shapes of the same scripts stay deniable.
        assert_true("permissionDecision" in run_scope(
            f"python3 {SCRIPTS}/validate_goal.py .goals/current.md --write-hash"),
            "post-lock --write-hash re-arm is still denied")
        assert_true("permissionDecision" in run_scope(
            f"python3 {SCRIPTS}/render_goal.py --write .goals/current.md"),
            "render --write targeting the frozen contract is still denied")
        # rendered-* projections are executor-writable (re-render is the
        # recovery path; the launch line's file hash makes tampering loud).
        patch_rendered = subprocess.run(
            [sys.executable, str(HOOKS / "scope_guard.py")],
            input=json.dumps({"cwd": str(ws), "tool_name": "apply_patch",
                              "tool_input": {"command": "*** Begin Patch\n*** Update File: .goals/rendered-goal.md\n@@\n-a\n+b\n*** End Patch"}}),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "PLUGIN_ROOT": str(ROOT), "GOALSPEC_NO_GIT": "1"}, timeout=30,
        )
        assert_true("permissionDecision" not in patch_rendered.stdout,
                    "patching the rendered projection is not denied")

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

        # Gate coherence: a sign-off declared only in Terminal State is invisible
        # to the audit oracle; declared inside ## Verifier it is enforceable.
        gated = Path(td14) / "gated.md"
        gated.write_text(_swap(base, "Terminal State",
                               "This goal is complete when:\n- The feature suite exits 0.\n"
                               "- The owner signs off on the artifact."), encoding="utf-8")
        vg = validate(gated)
        assert_true(any("cannot enforce it" in w for w in vg["warnings"]),
                    f"sign-off outside ## Verifier warns: {vg['warnings']}")
        gated_ok = Path(td14) / "gatedok.md"
        gated_ok.write_text(_swap(_swap(base, "Terminal State",
                                        "This goal is complete when:\n- The feature suite exits 0.\n"
                                        "- The owner signs off on the artifact."),
                                  "Verifier",
                                  "Completion must be verified by:\n- `pytest -q`\n"
                                  "- Human gate: the owner reviews and signs off."), encoding="utf-8")
        vgo = validate(gated_ok)
        assert_true(not any("cannot enforce it" in w for w in vgo["warnings"]),
                    f"gate inside ## Verifier does not warn: {vgo['warnings']}")

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

    # Live-run regression (EdgeCourt 1.6.0 authoring): a fenced heredoc verifier
    # (`python3 - <<'PY' ... PY`) must extract as ONE multi-line command, not as
    # per-line shell commands that 127 a perfect artifact into a false failure.
    heredoc_section = (
        "Completion must be verified by:\n\n"
        "```bash\n"
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "# a python comment inside the body must not be dropped\n"
        "required = [\"# EC-V001\"]\n"
        "raise SystemExit(0)\n"
        "PY\n"
        "git diff --quiet -- data.csv\n"
        "```\n"
    )
    heredoc_cmds = _evc(heredoc_section)
    assert_true(len(heredoc_cmds) == 2 and heredoc_cmds[1] == "git diff --quiet -- data.csv",
                f"heredoc consumes its body as one command; trailing commands still extract: {len(heredoc_cmds)}")
    assert_true(heredoc_cmds[0].startswith("python3 - <<'PY'") and heredoc_cmds[0].rstrip().endswith("PY")
                and "# a python comment inside the body" in heredoc_cmds[0],
                f"heredoc body survives verbatim, comments included: {heredoc_cmds[0]!r}")
    with tempfile.TemporaryDirectory() as thd:
        goals = Path(thd) / ".goals"
        goals.mkdir(parents=True)
        c = goals / "current.md"
        c.write_text(_swap(base, "Verifier",
                           "Completion must be verified by:\n\n```bash\npython3 - <<'PY'\n"
                           "import sys\nsys.exit(0)\nPY\n```\n"), encoding="utf-8")
        hd = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_verifiers.py"), str(c), "--run",
             "--evidence-dir", str(goals / "evidence" / "verifiers"), "--json"],
            cwd=thd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=60)
        hj = json.loads(hd.stdout)
        assert_true(hd.returncode == 0 and hj["overall_passed"] is True and len(hj["verifiers"]) == 1,
                    f"heredoc verifier runs as one passing command: rc={hd.returncode} {hj.get('verifiers')}")

    # evt-0182 regression pin: an inline-span regex that crosses newlines pairs
    # the opening fence's 3rd backtick with the closing fence's 1st and re-emits
    # the whole fence interior as one spurious multi-line 'bash ...' command.
    evt_section = (
        "Completion must be verified by running:\n\n"
        "```bash\npython3 verify.py\ngit diff --quiet -- data.csv\n```\n\n"
        "Expected: both exit 0. A rigged `verify.py` cannot fool the oracle; "
        "run `python3 -m pytest -q` when a suite exists.\n"
    )
    evt_cmds = _evc(evt_section)
    assert_true(evt_cmds == ["python3 verify.py", "git diff --quiet -- data.csv", "python3 -m pytest -q"],
                f"evt-0182: exactly the fence lines + qualifying spans, no fence-bleed command: {evt_cmds}")

    # Projection truthfulness (fleet run v11-b): a fence-style Verifier section
    # has no bullets; the rendered summary falls back to the extracted commands
    # and this field never projects "not specified".
    with tempfile.TemporaryDirectory() as td17b:
        fence_only = Path(td17b) / "fenceonly.md"
        fence_only.write_text(_swap(base, "Verifier",
                                    "Completion must be verified by running:\n\n"
                                    "```bash\npython3 verify_contacts_clean.py\ngit diff --quiet -- contacts.csv\n```\n"),
                              encoding="utf-8")
        rfo = render(fence_only, allow_unlocked=True)
        assert_true("Verifier summary: python3 verify_contacts_clean.py; git diff --quiet -- contacts.csv" in rfo,
                    "fence-only verifier commands appear in the rendered summary")
        assert_true("Verifier summary: not specified" not in rfo, "verifier summary is never 'not specified'")
        prose_only = Path(td17b) / "proseonly.md"
        prose_only.write_text(_swap(base, "Verifier",
                                    "The owner reviews and ratifies the artifact by hand.\n"), encoding="utf-8")
        rpo = render(prose_only, allow_unlocked=True)
        assert_true("Verifier summary: see the Verifier section in .goals/current.md." in rpo,
                    "bullet-less, command-less verifier points at the section instead of 'not specified'")

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

    # Pinned companions: a contract MAY freeze shared verifier artifacts
    # ('- Pinned: <path> sha256 <h>' in ## Verifier). A missing/mutated
    # companion fails run_verifiers loudly with no commands executed, and the
    # audit re-checks pins itself so a post-run mutation can never certify.
    with tempfile.TemporaryDirectory() as td19:
        ws = Path(td19)
        goals = ws / ".goals"
        (goals / "reports").mkdir(parents=True)
        companion = ws / "scripts" / "verify_shop.py"
        companion.parent.mkdir(parents=True)
        companion.write_bytes(b"import sys; sys.exit(0)\n")
        pin_hash = hashlib.sha256(companion.read_bytes()).hexdigest()
        c = goals / "current.md"
        c.write_text(_swap(base, "Verifier",
                           "Completion must be verified by:\n"
                           "- `python3 scripts/verify_shop.py`\n"
                           f"- Pinned: scripts/verify_shop.py sha256 {pin_hash}\n"
                           "- Expected result: exit code 0."), encoding="utf-8")
        (goals / "current.sha256").write_text(f"{sha256_file(c)}  current.md\n", encoding="utf-8")
        v_pin = validate(c)
        assert_true(v_pin["ok"], f"pin-bearing contract validates: {v_pin['errors']}")
        rep = goals / "reports" / "r.md"
        rep.write_text("## Result\nachieved\n\n## Files Changed\n- x\n\n## Commands Run\n- x\n\n"
                       "## Evidence\n- x\n\n## Budget Used\n- x\n\n## Remaining Risks\n- x\n\n"
                       "## Follow-Up Candidates\n- x\n", encoding="utf-8")

        def run_pin_verifiers():
            return subprocess.run(
                [sys.executable, str(SCRIPTS / "run_verifiers.py"), str(c), "--run",
                 "--evidence-dir", str(goals / "evidence" / "verifiers"), "--json"],
                cwd=td19, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=60)

        ok_run = run_pin_verifiers()
        oj = json.loads(ok_run.stdout)
        assert_true(ok_run.returncode == 0 and oj["overall_passed"] is True,
                    f"matching pin + passing command => overall pass: rc={ok_run.returncode} {oj}")
        assert_true(any(v["kind"] == "pin" and v["passed"] for v in oj["verifiers"]),
                    f"pin check recorded in the oracle result: {oj['verifiers']}")
        a_pin_ok = audit(c, rep, goals / "evidence")
        assert_true(a_pin_ok["result"] == "achieved", f"intact pin certifies normally: {a_pin_ok['result']}")

        # 1-byte tamper: the run fails loudly and never executes commands
        # against the mutated companion.
        companion.write_bytes(b"import sys; sys.exit(0) \n")
        bad_run = run_pin_verifiers()
        bj = json.loads(bad_run.stdout)
        assert_true(bad_run.returncode == 1 and bj["overall_passed"] is False,
                    f"tampered companion fails the verifier run: rc={bad_run.returncode}")
        assert_true(any(v["kind"] == "pin" and v["evidence"] == "pinned companion mutated"
                        for v in bj["verifiers"]),
                    f"failure names the mutated pin: {bj['verifiers']}")
        assert_true(not any(v["kind"] == "command" for v in bj["verifiers"]),
                    f"no command executes against a mutated companion: {bj['verifiers']}")
        a_pin_bad = audit(c, rep, goals / "evidence")
        assert_true(a_pin_bad["result"] == "not achieved"
                    and any("pinned companion mutated" in e for e in a_pin_bad["errors"]),
                    f"audit refuses achieved on a mutated pin: {a_pin_bad}")

        # Post-run mutation: a stale passing result file alone must not certify.
        companion.write_bytes(b"import sys; sys.exit(0)\n")
        run_pin_verifiers()
        companion.write_bytes(b"# late edit\nimport sys; sys.exit(0)\n")
        a_pin_late = audit(c, rep, goals / "evidence")
        assert_true(a_pin_late["result"] == "not achieved",
                    f"companion mutated after the run still refuses achieved: {a_pin_late['result']}")

    # --- Campaign chain execution (autonomous multi-child /goal) ---
    # The plan is frozen, evidence is the truth, checkmarks are a derived view.

    def make_campaign(root: Path, specs: list, policy: str = "halt-on-failure",
                      budget: int = 5, lock: bool = True) -> Path:
        """Build a campaign workspace: manifest + a full locked contract per ready child.

        specs: [{"id", "status", "depends_on", "cmd", "attestation"}] — cmd is the child's
        verifier command; attestation=True swaps the Verifier to a human-gate-only bullet
        (no executable command), making the child a chain pause point.
        """
        goals = root / ".goals"
        (goals / "reports").mkdir(parents=True, exist_ok=True)
        blocks = []
        for spec in specs:
            cid, status = spec["id"], spec.get("status", "ready")
            deps = spec.get("depends_on", "none")
            lines = [f"### {cid}: Chain child {cid}", "", f"- Status: {status}", f"- Depends on: {deps}",
                     f"- Terminal state: child {cid} delivers its contracted workspace change.",
                     "- Verifier: `python3 -c \"import sys; sys.exit(0)\"`"]
            if status == "ready":
                lines.append(f"- Contract: .goals/children/{cid}/current.md")
                cdir = goals / "children" / cid
                cdir.mkdir(parents=True, exist_ok=True)
                ctext = base.replace("# Goal Contract: G-001 Fix Password Reset Flow",
                                     f"# Goal Contract: {cid} Chain Child", 1)
                if spec.get("attestation"):
                    ctext = _swap(ctext, "Verifier",
                                  "Completion must be verified by:\n"
                                  "- Human gate: the owner reviews and ratifies the delivered artifact.")
                else:
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

    # Anti-theater gates: a decomposition must add execution information over
    # its sources. Stub children error, a meta-only ready set errors (unless an
    # owner decision is declared), and an empty graph mirror warns until synced.
    with tempfile.TemporaryDirectory() as tat:
        goals = Path(tat) / ".goals"
        goals.mkdir(parents=True)
        manifest = goals / "campaign-anti-theater.md"
        base_manifest = (
            "# Campaign: Anti Theater\n\n## Intent\nProve the decomposition quality gates.\n\n"
            "## Completeness Dimensions\n- value\n\n## Chain Budget\n- Max children attempted: 3.\n\n"
            "## Chain Failure Policy\n- halt-on-failure\n\n## Coverage\n- request -> G-002\n\n"
            "## Goal Graph\n\n"
            "### G-001: Substrate readiness preflight\n\n"
            "- Status: ready\n- Depends on: none\n- Contract: .goals/children/G-001/current.md\n"
            "- Terminal state: GoalSpec artifacts validate, render, and the hook selftest conforms.\n"
            "- Verifier: `validate_goal.py .goals/current.md --check-hash`; `conformance_probe.py selftest`\n\n"
            "### G-002: Milestone two\n\n- Status: conditional\n- Depends on: G-001\n- Missing decision: owner sign-off\n\n"
            "### G-003: Milestone three\n\n- Status: blocked\n- Depends on: G-002\n- Missing decision: legal gate\n\n"
            "## Selection Recommendation\nRun G-001 first.\n")
        manifest.write_text(base_manifest, encoding="utf-8")
        (goals / "graph.json").write_text(json.dumps(
            {"schema": "goalspec.graph.v1", "nodes": {}, "edges": []}), encoding="utf-8")
        v_at = validate_campaign(manifest)
        assert_true(any("G-002 (conditional) is a stub" in e for e in v_at["errors"]),
                    f"conditional stub child errors: {v_at['errors']}")
        assert_true(any("G-003 (blocked) is a stub" in w for w in v_at["warnings"]),
                    f"blocked stub child warns: {v_at['warnings']}")
        assert_true(any("G-001 is a meta-goal" in w for w in v_at["warnings"]),
                    f"meta child warns: {v_at['warnings']}")
        assert_true(any("Every ready child is a meta-goal" in e for e in v_at["errors"]),
                    f"meta-only ready set errors: {v_at['errors']}")
        assert_true(any("graph.json mirror is empty" in w for w in v_at["warnings"]),
                    f"empty graph mirror warns: {v_at['warnings']}")

        # Sketched children + a declared owner decision turn the hard failures
        # into the loud-but-explicit refusal path.
        sketched = base_manifest.replace(
            "- Missing decision: owner sign-off\n",
            "- Missing decision: owner sign-off\n"
            "- Terminal state: the milestone-two artifact set exists and its suite passes.\n"
            "- Verifier: `pytest -q tests/milestone_two`\n").replace(
            "- Missing decision: legal gate\n",
            "- Missing decision: legal gate\n"
            "- Terminal state: the gated integration ships behind the approved flag.\n"
            "- Verifier: `pytest -q tests/milestone_three`\n").replace(
            "## Selection Recommendation\nRun G-001 first.\n",
            "## Selection Recommendation\nRun G-001 first.\n\n- Owner decision required: approve milestone-two sign-off.\n")
        manifest.write_text(sketched, encoding="utf-8")
        v_ok = validate_campaign(manifest)
        assert_true(not any("is a stub" in e for e in v_ok["errors"]),
                    f"sketched children clear the stub gate: {v_ok['errors']}")
        assert_true(not any("Every ready child is a meta-goal" in e for e in v_ok["errors"]),
                    f"owner-decision line downgrades the meta-only error: {v_ok['errors']}")
        assert_true(any("Owner decision required" in w for w in v_ok["warnings"]),
                    f"declared owner decision still warns loudly: {v_ok['warnings']}")

        # Human-stepped campaigns compile the active child into the workspace
        # root slot; that layout must not read as an id mismatch.
        root_slot = sketched.replace("- Contract: .goals/children/G-001/current.md",
                                     "- Contract: .goals/current.md")
        manifest.write_text(root_slot, encoding="utf-8")
        (goals / "current.md").write_text("# Goal Contract: G-001 Substrate readiness preflight\n\n"
                                          "## Objective\nx\n", encoding="utf-8")
        v_root = validate_campaign(manifest)
        assert_true(not any("id mismatch" in e for e in v_root["errors"]),
                    f"root-slot contract is not an id mismatch: {v_root['errors']}")
        manifest.write_text(sketched, encoding="utf-8")

        # Deterministic mirror sync: the manifest is the truth, the graph follows.
        sync = subprocess.run(
            [sys.executable, str(SCRIPTS / "graph_goal.py"), "--graph", str(goals / "graph.json"),
             "--sync-campaign", str(manifest)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=30,
        )
        assert_true(sync.returncode == 0, f"graph sync runs: {sync.stderr}")
        gdata = json.loads((goals / "graph.json").read_text(encoding="utf-8"))
        assert_true(set(gdata["nodes"]) == {"G-001", "G-002", "G-003"}
                    and {"from": "G-002", "type": "depends_on", "to": "G-001"} in gdata["edges"],
                    f"sync mirrors nodes and edges from the manifest: {gdata}")
        v_synced = validate_campaign(manifest)
        assert_true(not any("graph.json mirror" in w for w in v_synced["warnings"]),
                    f"synced mirror clears the graph warnings: {v_synced['warnings']}")
        assert_true(any("No ## Decomposition Review" in w for w in v_synced["warnings"]),
                    f"missing adversarial-review record warns: {v_synced['warnings']}")
        assert_true(re.fullmatch(r"[0-9a-f]{64}", v_synced.get("review_anchor", "")),
                    f"validation always emits a 64-hex review anchor: {v_synced.get('review_anchor')}")
        # A review without an Anchor line or per-child verdicts is recorded but not closed.
        manifest.write_text(sketched + "\n## Decomposition Review\n\n"
                            "Reviewer verdict: value-add confirmed; tightened the G-002 verifier sketch.\n",
                            encoding="utf-8")
        v_rev = validate_campaign(manifest)
        assert_true(not any("No ## Decomposition Review" in w for w in v_rev["warnings"]),
                    f"recorded review clears the presence warning: {v_rev['warnings']}")
        assert_true(any("records no 'Anchor:" in w for w in v_rev["warnings"]),
                    f"anchor-less review warns: {v_rev['warnings']}")
        assert_true(any("no per-child verdict" in w and "G-001" in w and "G-003" in w
                        and "G-002" not in w.split("for:")[1] for w in v_rev["warnings"]),
                    f"missing verdicts warn naming exactly the unmentioned children: {v_rev['warnings']}")
        # Close the review properly: fresh anchor + one verdict per child => zero review warnings.
        anchor = v_rev["review_anchor"]
        closed = (sketched + "\n## Decomposition Review\n\n"
                  "- G-001: confirmed — substrate child carries its own oracle.\n"
                  "- G-002: weak — sketch only; materializes at selection.\n"
                  "- G-003: weak — blocked on the legal gate, sketch present.\n\n"
                  f"Anchor: {anchor}\n")
        manifest.write_text(closed, encoding="utf-8")
        v_closed = validate_campaign(manifest)
        assert_true(v_closed["review_anchor"] == anchor,
                    "review-section edits never move the anchor (self-reference soundness)")
        assert_true(not any("Decomposition Review" in w or "Anchor" in w for w in v_closed["warnings"]),
                    f"anchored review with full verdicts is clean: {v_closed['warnings']}")
        # Any post-review edit OUTSIDE the review section reads as staleness.
        manifest.write_text(closed.replace("Milestone two", "Milestone two renamed"), encoding="utf-8")
        v_stale = validate_campaign(manifest)
        assert_true(any("stale" in w and "changed after this review" in w for w in v_stale["warnings"]),
                    f"post-review graph edit warns as stale anchor: {v_stale['warnings']}")
        manifest.write_text(sketched, encoding="utf-8")

    # Meta-goal smell at the single-contract level.
    with tempfile.TemporaryDirectory() as tmeta:
        meta_c = Path(tmeta) / "meta.md"
        meta_c.write_text(_swap(_swap(base, "Objective",
                                      "The workspace has a validated GoalSpec readiness package and hook conformance is reported."),
                                "Terminal State",
                                "This goal is complete when:\n"
                                "- `.goals/current.md` validates and `.goals/rendered-goal.md` is produced by `render_goal.py`.\n"
                                "- `conformance_probe.py selftest` conforms and hook status is recorded in `.goals/reports/preflight.md`.\n"),
                          encoding="utf-8")
        v_meta = validate(meta_c)
        assert_true(any("Meta-goal" in w for w in v_meta["warnings"]),
                    f"GoalSpec-machinery-only contract warns as meta-goal: {v_meta['warnings']}")
        v_base = validate(contract)
        assert_true(not any("Meta-goal" in w for w in v_base["warnings"]),
                    f"value-bearing contract does not warn as meta-goal: {v_base['warnings']}")

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

    # Pointer render mode: a limit-independent dual-hash launch line; the full
    # render lives in a written file the executor reads, never in the prompt.
    def render_cli(*argv: str):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "render_goal.py"), *argv],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=30,
        )

    with tempfile.TemporaryDirectory() as tp1:
        goals = Path(tp1) / ".goals"
        goals.mkdir(parents=True)
        shutil.copyfile(contract, goals / "current.md")
        (goals / "current.sha256").write_text(f"{sha256_file(goals / 'current.md')}  current.md\n", encoding="utf-8")
        pj = render_cli(str(goals / "current.md"), "--pointer", "--json")
        assert_true(pj.returncode == 0, f"pointer render of a locked goal succeeds: {pj.stderr}")
        pm = json.loads(pj.stdout)
        line, pfile = pm["pointer_line"], Path(pm["pointer_file"])
        assert_true(len(line) <= 400, f"pointer line stays <= 400 chars: {len(line)}")
        assert_true(line.startswith("/goal "), "pointer line is a paste-ready /goal")
        assert_true(pm["mission_sha256"] in line and pm["pointer_file_sha256"] in line,
                    "pointer line carries both hashes")
        assert_true(".goals/rendered-goal.md" in line and ".goals/current.md" in line,
                    "pointer line names the pointer file and keeps the prompt_guard anchor")
        assert_true("stop and report contract mutated" in line, "pointer line carries the stop rule")
        assert_true(pfile.read_text(encoding="utf-8") == pm["rendered"] + "\n",
                    "written pointer file matches the rendered text")
        assert_true(pm["pointer_file_sha256"] == sha256_file(pfile),
                    "pointer line hash is computed from the written bytes")
        ph = render_cli(str(goals / "current.md"), "--pointer")
        assert_true(pm["rendered"] in ph.stdout and ph.stdout.rstrip().endswith(line),
                    "human mode prints the full render first and the launch line last")
        # Tamper one byte (simulating a formatter rewrite): the recomputed sha
        # must diverge from the line's, i.e. the mismatch is loudly detectable.
        pfile.write_text(pfile.read_text(encoding="utf-8").replace("frozen", "frozen ", 1), encoding="utf-8")
        assert_true(sha256_file(pfile) != pm["pointer_file_sha256"],
                    "tampered pointer file is detectable against the line's file sha")
        # Pointer never renders unlocked/mismatched and never composes with --allow-unlocked.
        (goals / "current.sha256").unlink()
        pun = render_cli(str(goals / "current.md"), "--pointer")
        assert_true(pun.returncode == 2 and "REFUSED" in pun.stderr,
                    f"pointer refuses an unlocked contract: rc={pun.returncode}")
        pao = render_cli(str(goals / "current.md"), "--pointer", "--allow-unlocked")
        assert_true(pao.returncode == 2 and "REFUSED" in pao.stderr,
                    f"--pointer --allow-unlocked is refused: rc={pao.returncode}")

    with tempfile.TemporaryDirectory() as tp2:
        ws = Path(tp2)
        m = make_campaign(ws, [{"id": "G-001", "status": "ready", "depends_on": "none"}])
        cj = render_cli("--campaign", str(m), "--pointer", "--json")
        assert_true(cj.returncode == 0, f"campaign pointer render succeeds: {cj.stderr}")
        cm = json.loads(cj.stdout)
        cline = cm["pointer_line"]
        assert_true(len(cline) <= 400, f"campaign pointer line stays <= 400 chars: {len(cline)}")
        assert_true(".goals/rendered-campaign.md" in cline and ".goals/campaign-" in cline,
                    "campaign pointer line names the pointer file and keeps the prompt_guard anchor")
        assert_true(cm["mission_sha256"] in cline and cm["pointer_file_sha256"] in cline,
                    "campaign pointer line carries both hashes")
        cfile = ws / ".goals" / "rendered-campaign.md"
        assert_true(cfile.read_text(encoding="utf-8") == cm["rendered"] + "\n",
                    "campaign pointer file matches the rendered chain text")

    # --- Attestation-advance: human-gated children pause the chain, audit advances it ---
    # The rendered mission is durable across threads: it never centers a child;
    # campaign_status derives the next pending one, pauses at unratified gates,
    # and resumes after the owner records the gate outcome.
    with tempfile.TemporaryDirectory() as ta1:
        ws = Path(ta1)
        m = make_campaign(ws, [{"id": "G-001", "attestation": True, "depends_on": "none"},
                               {"id": "G-002", "depends_on": "G-001"}])
        v_att = validate_campaign(m)
        assert_true(v_att["ok"] and v_att.get("attestation_only") == ["G-001"],
                    f"attestation-only child validates with the pause-point signal: {v_att.get('attestation_only')}")
        assert_true(any("attestation-only" in w and "G-001" in w for w in v_att["warnings"]),
                    f"validate warns about the pause point: {v_att['warnings']}")

        s_fresh = derive_status(m)
        assert_true(s_fresh["next_child"] == "G-001" and not s_fresh["chain_should_stop"],
                    f"unattempted attestation child stays workable, not stopped: {s_fresh['next_child']}")
        assert_true(s_fresh["attestation_only"] == ["G-001"]
                    and any("pause point" in w for w in s_fresh["warnings"]),
                    f"status names the pause points: {s_fresh['warnings']}")

        # Attempt: work done, report written, gate still pending => clean pause.
        ev1 = child_evidence_dir(ws, "G-001")
        ev1.mkdir(parents=True, exist_ok=True)
        (ev1 / "artifact.txt").write_text("delivered artifact\n", encoding="utf-8")
        rep1 = ws / ".goals" / "reports" / "G-001-report.md"
        rep1.write_text(
            "# Goal Report: G-001\n\n## Result\nblocked: awaiting owner ratification\n\n"
            "## Files Changed\n- x\n\n## Commands Run\n- none\n\n"
            "## Evidence\n- .goals/evidence/children/G-001/artifact.txt\n\n## Budget Used\n- 1\n\n"
            "## Remaining Risks\n- Human gate: pending owner ratification.\n\n## Follow-Up Candidates\n- none\n",
            encoding="utf-8")
        s_pause = derive_status(m)
        assert_true(s_pause["chain_should_stop"] and s_pause["next_child"] is None,
                    f"attempted-but-unratified attestation child pauses the chain: {s_pause['stop_reason']}")
        assert_true("G-001" in (s_pause["stop_reason"] or "") and "relaunch" in s_pause["stop_reason"],
                    f"pause reason teaches the resume path: {s_pause['stop_reason']}")
        assert_true(not (s_pause["chain_should_stop"] and s_pause["next_child"]),
                    "never-both invariant holds at the pause")
        a_withheld = audit_campaign(m)
        assert_true(a_withheld["result"] != "campaign achieved",
                    f"roll-up withholds certification while the gate is pending: {a_withheld['result']}")

        # Owner ratifies => the audit verdict advances the chain to G-002.
        rep1.write_text(rep1.read_text(encoding="utf-8")
                        .replace("blocked: awaiting owner ratification", "achieved")
                        .replace("Human gate: pending owner ratification.",
                                 "Human gate: approved by the owner."), encoding="utf-8")
        s_ratified = derive_status(m)
        g1_row = next(r for r in s_ratified["children"] if r["id"] == "G-001")
        assert_true(g1_row["status"] == "achieved-pending-audit" and s_ratified["next_child"] == "G-002",
                    f"ratified attestation child advances the chain: {g1_row['status']} -> {s_ratified['next_child']}")

        # Machine child completes => all achieved; roll-up certifies.
        chain_evidence(ws, m, "G-002", passed=True)
        chain_report(ws, "G-002")
        s_done = derive_status(m)
        assert_true(s_done["chain_should_stop"] and "all ready children achieved" in (s_done["stop_reason"] or ""),
                    f"completed chain stops cleanly: {s_done['stop_reason']}")
        a_done = audit_campaign(m)
        assert_true(a_done["result"] == "campaign achieved",
                    f"ratified gate + machine result => campaign achieved: {a_done['result']}")

        # Idempotent re-injection: the rendered mission routes by state, never by name.
        meta_att = render_campaign_with_meta(m)
        r_att = meta_att["rendered"]
        assert_true("take its next_child" in r_att and "durable across threads" in r_att,
                    "chain text derives the next child from state with the resume framing")
        assert_true("never write a ratification line yourself" in r_att,
                    "chain text carries the no-self-ratification constraint")
        assert_true("start with G-" not in r_att and "begin with G-" not in r_att,
                    "chain text never centers a specific starting child")

        # Mixed child (command + human gate) still advances on the machine path.
        ws2 = Path(ta1) / "mixed"
        m2 = make_campaign(ws2, [{"id": "G-001", "depends_on": "none"}])
        child2 = ws2 / ".goals" / "children" / "G-001" / "current.md"
        child2.write_text(_swap(child2.read_text(encoding="utf-8"), "Verifier",
                                "Completion must be verified by:\n- `python3 -c \"import sys; sys.exit(0)\"`\n"
                                "- Human gate: the owner reviews and ratifies the artifact."), encoding="utf-8")
        (child2.parent / "current.sha256").write_text(f"{sha256_file(child2)}  current.md\n", encoding="utf-8")
        campaign_lock_path(m2).write_text(f"{campaign_aggregate_hash(m2)}  {m2.name}\n", encoding="utf-8")
        v_mixed = validate_campaign(m2)
        assert_true(v_mixed["ok"] and not v_mixed.get("attestation_only"),
                    f"mixed child (command + gate) is not a pause point: {v_mixed.get('attestation_only')}")
        meta_mixed = render_campaign_with_meta(m2)
        assert_true(meta_mixed["rendered"].startswith("/goal "), "mixed-child campaign renders")
        chain_evidence(ws2, m2, "G-001", passed=True)
        chain_report(ws2, "G-001")
        s_mixed = derive_status(m2)
        assert_true(s_mixed["achieved_pending_audit"] == 1,
                    f"mixed child advances on the machine result: {s_mixed['children']}")
        a_mixed = audit_campaign(m2)
        assert_true(a_mixed["result"] != "campaign achieved",
                    f"roll-up still withholds the mixed child until ratification: {a_mixed['result']}")

    # --- Vendored chain runtime: the frozen mission carries its own instruments ---
    from render_goal import CHAIN_RUNTIME_FILES  # noqa: E402
    with tempfile.TemporaryDirectory() as tv1:
        ws = Path(tv1)
        m = make_campaign(ws, two_chain)
        meta_v = render_campaign_with_meta(m)
        runtime = meta_v["vendored_runtime"]
        bin_dir = ws / ".goals" / "bin"
        for name in CHAIN_RUNTIME_FILES:
            assert_true((bin_dir / name).exists(), f"vendored runtime contains {name}")
            recomputed = hashlib.sha256((bin_dir / name).read_bytes()).hexdigest()
            assert_true(runtime["files"][name] == recomputed,
                        f"vendored hash recorded for {name} matches the written bytes")
        manifest_text = (bin_dir / "MANIFEST.sha256").read_text(encoding="utf-8")
        for name, digest in runtime["files"].items():
            assert_true(f"{digest}  {name}" in manifest_text, f"MANIFEST records {name}")
        r_v = meta_v["rendered"]
        assert_true(".goals/bin/campaign_status.py" in r_v and ".goals/bin/run_verifiers.py" in r_v,
                    "chain text invokes the vendored runtime")
        assert_true(str(SCRIPTS) not in r_v,
                    "chain text carries no plugin-tree absolute path (survives upgrades)")
        # Runtime import-closure proof: the vendored status tool runs from the
        # workspace with no plugin tree on the path.
        env_clean = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env_clean["GOALSPEC_NO_GIT"] = "1"
        vp = subprocess.run([sys.executable, ".goals/bin/campaign_status.py",
                             ".goals/campaign-test.md", "--json", "--no-write"],
                            cwd=tv1, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env_clean, timeout=60)
        assert_true(vp.returncode == 0, f"vendored campaign_status runs import-clean: {vp.stderr}")
        assert_true(json.loads(vp.stdout)["next_child"] == "G-001",
                    "vendored status tool derives the chain state correctly")
        # Static closure guard: every local import of a vendored file is itself vendored.
        local_scripts = {p.name for p in SCRIPTS.glob("*.py")}
        for name in CHAIN_RUNTIME_FILES:
            for mod in re.findall(r"(?m)^(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)",
                                  (SCRIPTS / name).read_text(encoding="utf-8")):
                if f"{mod}.py" in local_scripts:
                    assert_true(f"{mod}.py" in CHAIN_RUNTIME_FILES,
                                f"vendored {name} imports {mod}.py which is not in CHAIN_RUNTIME_FILES")
        # Tamper => audit warns; re-render restores.
        (bin_dir / "run_verifiers.py").write_bytes(b"# tampered\n")
        a_tamper = audit_campaign(m)
        assert_true(any("vendored chain runtime mutated" in w for w in a_tamper["warnings"]),
                    f"audit warns on a mutated vendored runtime: {a_tamper['warnings']}")
        render_campaign_with_meta(m)
        restored = hashlib.sha256((bin_dir / "run_verifiers.py").read_bytes()).hexdigest()
        assert_true(restored == runtime["files"]["run_verifiers.py"],
                    "re-render restores the vendored runtime")

    # --- Decision-register harvest: sources' own open decisions become candidates ---
    with tempfile.TemporaryDirectory() as tdh:
        prd_like = Path(tdh) / "PRD.md"
        items = "\n".join(f"{i}. Open item number {i}." for i in range(1, 34))
        prd_like.write_text(
            "# PRD\n\n## 18. Scope\n\n- in scope thing\n- another\n\n"
            "## 19. Open Questions for `ARCHITECTURE.md` and `ROADMAP.md`\n\n" + items + "\n\n"
            "## 20. Rollout\n\n1. step one\n2. step two\n", encoding="utf-8")
        dh = extract([str(prd_like)], max_files=5, max_candidates=100)
        decisions = [c for c in dh if "needs human decision" in c]
        assert_true(len(decisions) == 33, f"PRD-shaped register yields exactly its 33 items: {len(decisions)}")
        assert_true("Open item number 1." in decisions[0] and "PRD.md:" in decisions[0],
                    "decision candidates carry the item text and file:line source")
        assert_true(not any("step one" in c or "in scope thing" in c for c in dh),
                    "neighboring sections contribute no decision candidates")
        capped = Path(tdh) / "cap.md"
        capped.write_text("## Unresolved\n\n" + "\n".join(f"- item {i}" for i in range(60)) + "\n",
                          encoding="utf-8")
        dcap = [c for c in extract([str(capped)], max_files=5, max_candidates=100)
                if "needs human decision" in c]
        assert_true(len(dcap) == 40, f"per-file decision cap holds: {len(dcap)}")
        as_txt = Path(tdh) / "notes.txt"
        as_txt.write_text("## Open Questions\n\n1. not markdown\n", encoding="utf-8")
        assert_true(not [c for c in extract([str(as_txt)], 5, 100) if "needs human decision" in c],
                    "non-markdown files never enter register mode")
        lvl3 = Path(tdh) / "design.md"
        lvl3.write_text("### To Be Decided\n\n- charting library\n\nProse with open questions inline.\n",
                        encoding="utf-8")
        d3 = [c for c in extract([str(lvl3)], 5, 100) if "needs human decision" in c]
        assert_true(len(d3) == 1 and "charting library" in d3[0],
                    f"level-3 register harvested; mid-paragraph prose is not: {len(d3)}")

    # --- Reviewer availability: installed by default, shipped on Claude hosts ---
    with tempfile.TemporaryDirectory() as tag:
        tmp2 = Path(tag) / "defaults"
        tmp2.mkdir()
        init(tmp2)
        for toml_name in ("goal-auditor.toml", "goal-discoverer.toml", "decomposition-reviewer.toml"):
            assert_true((tmp2 / ".codex" / "agents" / toml_name).exists(),
                        f"init installs {toml_name} by default")
        tmp3 = Path(tag) / "optout"
        tmp3.mkdir()
        no_agents = subprocess.run(
            [sys.executable, str(SCRIPTS / "init_project.py"), "--root", str(tmp3), "--no-agents"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=30)
        assert_true(no_agents.returncode == 0 and not (tmp3 / ".codex" / "agents").exists(),
                    f"--no-agents opts out of agent templates: {no_agents.stderr}")
        tmp4 = Path(tag) / "alias"
        tmp4.mkdir()
        alias = subprocess.run(
            [sys.executable, str(SCRIPTS / "init_project.py"), "--root", str(tmp4), "--install-agents"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=30)
        assert_true(alias.returncode == 0 and (tmp4 / ".codex" / "agents" / "decomposition-reviewer.toml").exists(),
                    "--install-agents stays a working no-op alias")
    claude_agent = ROOT / "agents" / "decomposition-reviewer.md"
    assert_true(claude_agent.exists(), "plugin ships the Claude decomposition-reviewer agent")
    agent_text = claude_agent.read_text(encoding="utf-8")
    assert_true(agent_text.startswith("---") and "name: decomposition-reviewer" in agent_text
                and "tools: Read, Grep, Glob" in agent_text,
                "Claude agent has read-only frontmatter")
    assert_true("verdict for EVERY child" in agent_text and "Anchor" in agent_text,
                "Claude agent demands per-child verdicts and the anchor handshake")

    # --- Provenance Compiled-Into names what the request actually compiled into ---
    with tempfile.TemporaryDirectory() as tpv:
        ws = Path(tpv)
        m = make_campaign(ws, [{"id": "G-001", "depends_on": "none"}], lock=False)
        req = ws / "request.txt"
        req.write_text("build the whole destination\n", encoding="utf-8")
        rec3 = subprocess.run(
            [sys.executable, str(SCRIPTS / "record_provenance.py"),
             "--request", str(req), "--id", "campaign-test", "--source", "user prompt",
             "--goals-dir", str(ws / ".goals"), "--contract", str(m), "--json"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=30)
        assert_true(rec3.returncode == 0, f"record_provenance accepts a campaign manifest: {rec3.stderr}")
        art3 = (ws / ".goals" / "provenance" / "campaign-test.md").read_text(encoding="utf-8")
        assert_true("- Contract: .goals/campaign-test.md" in art3,
                    "Compiled-Into names the campaign manifest, not a hardcoded current.md")

    # Single-goal renders are re-injection-safe too: an already-achieved contract
    # is verified and reported, never redone.
    single_render = render(contract, allow_unlocked=True)
    assert_true("already certify this contract achieved" in single_render,
                "single-goal render carries the idempotent re-entry sentence")
    assert_true("open-world discovery" in single_render and "Execute closed-world" in single_render
                and ".goals/focus.md" in single_render,
                "single-goal render carries the executor doctrine and the focus-first read")

    # --- Task trees: declarative outcome decomposition with positional ids ---
    from common import excise_section, flatten_task_tree, parse_task_tree  # noqa: E402
    tree = parse_task_tree(
        "- [ ] Outcome one\n"
        "  - [x] Sub one (authored box state is ignored)\n"
        "    - [ ] Sub-sub one\n"
        "      - extra-indented child clamps to the next level\n"
        "  - [ ] Sub two\n"
        "- Outcome two (plain bullet accepted)\n")
    ids = [n["id"] for n in flatten_task_tree(tree)]
    assert_true(ids == ["1", "1.1", "1.1.1", "1.1.1.1", "1.2", "2"],
                f"task tree ids are positional dotted paths: {ids}")
    assert_true(parse_task_tree("") == [] and parse_task_tree("prose only\n") == [],
                "empty/prose Tasks sections parse to an empty tree")

    # validate_goal nudges toward depth: the fixture carries a tree (no warning);
    # removing the section warns.
    v_tasks = validate(contract)
    assert_true(not any("## Tasks" in w for w in v_tasks["warnings"]),
                f"fixture with a Tasks tree does not warn: {v_tasks['warnings']}")
    with tempfile.TemporaryDirectory() as tnt:
        no_tree = Path(tnt) / "notree.md"
        no_tree.write_text(excise_section(base, "Tasks"), encoding="utf-8")
        v_nt = validate(no_tree)
        assert_true(v_nt["ok"] and any("No ## Tasks outcome tree" in w for w in v_nt["warnings"]),
                    f"missing Tasks tree warns (never errors): {v_nt['warnings']}")

    # --- Focus cursor: single-goal lifecycle (show -> done -> undo -> stale) ---
    def focus_cli(ws: Path, *argv: str):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "focus.py"), *argv, "--root", str(ws)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "GOALSPEC_NO_GIT": "1"}, timeout=60)

    with tempfile.TemporaryDirectory() as tf1:
        ws = Path(tf1)
        (ws / ".goals").mkdir(parents=True)
        c = ws / ".goals" / "current.md"
        shutil.copyfile(contract, c)
        (ws / ".goals" / "current.sha256").write_text(f"{sha256_file(c)}  current.md\n", encoding="utf-8")
        fj = focus_cli(ws, "show", "--json")
        assert_true(fj.returncode == 0, f"focus show works: {fj.stderr}")
        fmeta = json.loads(fj.stdout)
        assert_true(fmeta["goal_id"] == "G-001" and fmeta["tasks_done"] == 0 and fmeta["tasks_total"] >= 6,
                    f"focus projects the goal and its open tree: {fmeta.get('goal_id')} {fmeta.get('tasks_total')}")
        ftext = (ws / ".goals" / "focus.md").read_text(encoding="utf-8")
        assert_true("never authoritative" in ftext and "focus.py done" in ftext
                    and "Open-world discovery first" in ftext,
                    "focus.md carries the cursor doctrine and the advance commands")
        fd = focus_cli(ws, "done", "1.1", "2.1", "--json")
        assert_true(fd.returncode == 0 and json.loads(fd.stdout)["tasks_done"] == 2,
                    f"focus done marks outcomes: {fd.stderr}")
        assert_true("- [x] 1.1 " in (ws / ".goals" / "focus.md").read_text(encoding="utf-8"),
                    "marked outcomes render as [x] in the projection")
        state = json.loads((ws / ".goals" / "evidence" / "tasks" / "G-001.json").read_text(encoding="utf-8"))
        assert_true(state["schema"] == "goalspec.tasks.v1" and set(state["done"]) == {"1.1", "2.1"},
                    f"task state persists under evidence with the schema: {state}")
        bad = focus_cli(ws, "done", "9.9")
        assert_true(bad.returncode == 2 and "unknown task id" in bad.stderr,
                    f"unknown task ids are refused loudly: rc={bad.returncode}")
        fu = focus_cli(ws, "undo", "2.1", "--json")
        assert_true(json.loads(fu.stdout)["tasks_done"] == 1, "undo reverses a mark")
        # Re-lock with changed content: the cursor is stale and discarded loudly.
        c.write_text(c.read_text(encoding="utf-8") + "\n<!-- revised -->\n", encoding="utf-8")
        (ws / ".goals" / "current.sha256").write_text(f"{sha256_file(c)}  current.md\n", encoding="utf-8")
        fs = focus_cli(ws, "show", "--json")
        sm = json.loads(fs.stdout)
        assert_true(sm["tasks_done"] == 0 and any("stale" in w for w in sm["warnings"]),
                    f"a re-locked contract invalidates the cursor with a warning: {sm['warnings']}")

    # --- Focus cursor: campaign mode follows the chain and pauses with it ---
    with tempfile.TemporaryDirectory() as tf2:
        ws = Path(tf2)
        m = make_campaign(ws, [{"id": "G-001", "attestation": True, "depends_on": "none"},
                               {"id": "G-002", "depends_on": "G-001"}])
        # init's scaffolded template must never make a one-campaign workspace ambiguous.
        (ws / ".goals" / "campaign-template.md").write_text("# Campaign: Replace With Name\n", encoding="utf-8")
        f0 = json.loads(focus_cli(ws, "show", "--json").stdout)
        assert_true(f0["mode"] == "campaign" and f0["goal_id"] == "G-001",
                    f"campaign focus names the derived next child: {f0.get('goal_id')}")
        ev1 = child_evidence_dir(ws, "G-001")
        ev1.mkdir(parents=True, exist_ok=True)
        (ev1 / "artifact.txt").write_text("x\n", encoding="utf-8")
        rep1 = ws / ".goals" / "reports" / "G-001-report.md"
        rep1.write_text("# r\n\n## Result\nachieved\n\n## Files Changed\n- x\n\n## Commands Run\n- x\n\n"
                        "## Evidence\n- x\n\n## Budget Used\n- x\n\n"
                        "## Remaining Risks\n- Human gate: approved by the owner.\n\n## Follow-Up Candidates\n- none\n",
                        encoding="utf-8")
        f1 = json.loads(focus_cli(ws, "show", "--json").stdout)
        assert_true(f1["goal_id"] == "G-002", f"focus advances with the chain: {f1.get('goal_id')}")
        chain_evidence(ws, m, "G-002", passed=True)
        chain_report(ws, "G-002")
        f2 = json.loads(focus_cli(ws, "show", "--json").stdout)
        assert_true(f2.get("goal_id") is None and "achieved" in (f2.get("chain_note") or ""),
                    f"a completed chain projects its stop note, not a goal: {f2.get('chain_note')}")

    # --- Focus + guard + vendoring: the cursor moves through the armed run ---
    with tempfile.TemporaryDirectory() as tf3:
        ws = Path(tf3)
        m = make_campaign(ws, two_chain)
        meta_f = render_campaign_with_meta(m)
        assert_true("Read .goals/focus.md first" in meta_f["rendered"],
                    "chain text opens with the focus-first read")
        assert_true(meta_f["focus"].get("file", "").endswith("focus.md")
                    and (ws / ".goals" / "focus.md").exists(),
                    f"campaign render writes the initial focus projection: {meta_f['focus']}")
        assert_true((ws / ".goals" / "bin" / "focus.py").exists(),
                    "focus.py is vendored with the chain runtime")
        vf = subprocess.run([sys.executable, ".goals/bin/focus.py", "show", "--root", str(ws), "--json"],
                            cwd=tf3, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"} | {"GOALSPEC_NO_GIT": "1"},
                            timeout=60)
        assert_true(vf.returncode == 0 and json.loads(vf.stdout)["goal_id"] == "G-001",
                    f"vendored focus.py runs import-clean from the workspace: {vf.stderr}")

        def run_scope_ws(command: str) -> str:
            proc = subprocess.run(
                [sys.executable, str(HOOKS / "scope_guard.py")],
                input=json.dumps({"cwd": str(ws), "tool_name": "Bash", "tool_input": {"command": command}}),
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={**os.environ, "PLUGIN_ROOT": str(ROOT), "GOALSPEC_NO_GIT": "1"}, timeout=30)
            return proc.stdout

        assert_true("permissionDecision" not in run_scope_ws("python3 .goals/bin/focus.py done 1.1"),
                    "moving the cursor via the vendored CLI passes the armed guard")
        assert_true("permissionDecision" in run_scope_ws("echo x >> .goals/focus.md"),
                    "hand-writing the focus projection is denied while armed")

    # Single-goal render of the canonical mission slot vendors the runtime and
    # writes the projection; --allow-unlocked previews never write anything.
    with tempfile.TemporaryDirectory() as tf4:
        ws = Path(tf4)
        (ws / ".goals").mkdir(parents=True)
        c = ws / ".goals" / "current.md"
        shutil.copyfile(contract, c)
        (ws / ".goals" / "current.sha256").write_text(f"{sha256_file(c)}  current.md\n", encoding="utf-8")
        meta_s = render_with_meta(c)
        assert_true(meta_s.get("focus", {}).get("file", "").endswith("focus.md")
                    and (ws / ".goals" / "bin" / "focus.py").exists(),
                    "locked single-goal render vendors the runtime and writes focus.md")
    assert_true("focus" not in render_with_meta(contract, allow_unlocked=True),
                "preview renders write no focus projection")

    # --- Materialize-everything floor: contract-less tail children warn ---
    with tempfile.TemporaryDirectory() as tmm:
        ws = Path(tmm)
        m = make_campaign(ws, [{"id": "G-001", "depends_on": "none"}], lock=False)
        cond = ("\n### G-002: Conditional without a contract\n\n- Status: conditional\n- Depends on: G-001\n"
                "- Missing decision: Owner decision required: pick the provider.\n"
                "- Terminal state: the provider integration exists and its suite passes.\n"
                "- Verifier: `pytest -q tests/provider`\n")
        m.write_text(m.read_text(encoding="utf-8").replace("\n## Selection Recommendation",
                                                            cond + "\n## Selection Recommendation"),
                     encoding="utf-8")
        v_mat = validate_campaign(m)
        assert_true(v_mat["ok"] and any("materialize the tail" in w and "G-002" in w for w in v_mat["warnings"]),
                    f"contract-less conditional child warns: {v_mat['warnings']}")
        # Materialized but invalid tail contract: errors surface as promotion warnings.
        cdir = ws / ".goals" / "children" / "G-002"
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "current.md").write_text("# Goal Contract: G-002 Tail\n\n## Objective\nx\n", encoding="utf-8")
        m.write_text(m.read_text(encoding="utf-8").replace(
            "- Missing decision: Owner decision required: pick the provider.",
            "- Contract: .goals/children/G-002/current.md\n- Missing decision: Owner decision required: pick the provider."),
            encoding="utf-8")
        v_mat2 = validate_campaign(m)
        assert_true(v_mat2["ok"] and any("before promotion" in w and "G-002" in w for w in v_mat2["warnings"]),
                    f"invalid tail contract surfaces promotion warnings: {v_mat2['warnings']}")

    # Worked examples stay structurally honest (cheap drift guard).
    examples_text = (ROOT / "skills" / "authoring-goals" / "references" / "examples.md").read_text(encoding="utf-8")
    assert_true("## Tasks" in examples_text and ".goals/focus.md:" in examples_text
                and ".goals/children/G-001/current.md:" in examples_text,
                "examples.md carries the file-block artifacts (contract with Tasks, focus projection)")

    print("GoalSpec full smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
