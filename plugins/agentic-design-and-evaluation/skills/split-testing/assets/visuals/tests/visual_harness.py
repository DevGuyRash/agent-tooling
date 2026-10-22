"""Shared paths and helpers for the visual library's tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = Path(__file__).resolve().parent
VISUALS = TESTS.parent
EXAMPLES = VISUALS / "examples"
REPORT = VISUALS / "report.py"
NODE = shutil.which("node")
PYTHON_ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


TRIAL_SECTIONS = ["setup", "arms", "cases", "grid", "failures", "checks", "pairwise", "cost", "invalid", "runs"]
COMPARISON_SECTIONS = ["compared", "results", "differences", "groups", "cases", "judgments", "decision", "observations", "sources"]


def story_for(trial: dict | None = None, comparison: dict | None = None) -> dict:
    """A complete story for a test fixture whose test is about something else: every part present and every
    alternative and case described, in deliberately plain filler words."""
    story = {"background": "Background for a reader new to this test fixture.", "intent": "What the fixture's decider wanted.",
             "questions": ["What the fixture tests."], "rule": "How the fixture's decision was made.", "covers": "What the fixture covers.", "notCovered": "What it does not."}
    if trial is not None:
        runs = [r for r in trial.get("runs", []) if isinstance(r, dict)]
        story["alternatives"] = {a: f"Arm {a}." for a in dict.fromkeys(r["arm"] for r in runs if isinstance(r.get("arm"), str))}
        story["cases"] = {c: f"Case {c}." for c in dict.fromkeys(r["scenario"] for r in runs if isinstance(r.get("scenario"), str))}
    if comparison is not None:
        story["alternatives"] = {a["id"]: f"Alternative {a['id']}." for a in comparison.get("alternatives", []) if isinstance(a, dict) and isinstance(a.get("id"), str)}
        cases = [c["id"] for c in comparison.get("cases", []) if isinstance(c, dict) and isinstance(c.get("id"), str)]
        if cases:
            story["cases"] = {c: f"Case {c}." for c in cases}
    return story


def told(narrative: dict, trial: dict | None = None, comparison: dict | None = None) -> dict:
    """The narrative with a complete story and a reading for every section its composition can show."""
    sections = TRIAL_SECTIONS if trial is not None else COMPARISON_SECTIONS
    return {**narrative, "story": story_for(trial, comparison), "readings": {s: f"What the {s} views show here." for s in sections}}


PROSE_BLOCKS = ("text", "callout", "list", "facts", "verdict", "diagram")


def told_spec(spec: dict, trial: dict | None = None, comparison: dict | None = None) -> dict:
    """The specification with a complete story, a reading in every section and, in a section of several views,
    each view's own reading."""
    def read(b):
        if not isinstance(b, dict) or b.get("type") in PROSE_BLOCKS or not isinstance(b.get("type"), str):
            return b
        return {**b, "read": {**(b["read"] if isinstance(b.get("read"), dict) else {}), "says": "What this view shows here."}}

    def section(s):
        if not isinstance(s, dict):
            return s
        blocks = [read(b) for b in s["blocks"]] if isinstance(s.get("blocks"), list) else s.get("blocks")
        return {**s, "reading": "What these views show here.", **({"blocks": blocks} if isinstance(s.get("blocks"), list) else {})}
    return {**spec, "story": story_for(trial, comparison), "sections": [section(s) for s in spec.get("sections", [])]}


def run_python(*args: object, cwd: Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a Python script from this library with the current interpreter."""
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, timeout=timeout, cwd=cwd, env=PYTHON_ENV)


def run_node(*args: object, timeout: int = 60) -> subprocess.CompletedProcess:
    if not NODE:
        raise unittest.SkipTest("node is not on PATH")
    return subprocess.run([NODE, *map(str, args)], capture_output=True, text=True, timeout=timeout, cwd=TESTS)


_CASES: dict[str, list[dict]] = {}


def node_cases(script: str) -> list[dict]:
    """Run a case script (see harness.cjs) once and return its results."""
    if script not in _CASES:
        _CASES[script] = _run_cases(script)
    return _CASES[script]


def _run_cases(script: str) -> list[dict]:
    result = run_node(TESTS / script)
    if result.returncode != 0:
        raise AssertionError(f"{script} exited {result.returncode}:\n{result.stderr[-4000:]}")
    lines = result.stdout.strip().splitlines()
    if not lines:
        raise AssertionError(f"{script} printed no results:\n{result.stderr[-4000:]}")
    return json.loads(lines[-1])


class NodeCases(unittest.TestCase):
    """One subtest per case of a Node case script."""

    script = ""
    minimum = 1

    def run_script_cases(self) -> None:
        cases = node_cases(self.script)
        regular = [c for c in cases if not c["defect"]]
        self.assertGreaterEqual(len(regular), self.minimum, f"{self.script} ran fewer cases than expected")
        for case in regular:
            with self.subTest(case=case["name"]):
                if case["error"]:
                    self.fail(case["error"])

    def check_known_defects(self) -> None:
        """Known library defects are skipped while they reproduce. Once one is
        fixed, the case fails so that it becomes an ordinary test."""
        defects = [c for c in node_cases(self.script) if c["defect"]]
        if not defects:
            self.skipTest("no known defects")
        for case in defects:
            with self.subTest(case=case["name"]):
                if case["error"]:
                    self.skipTest(f"known library defect (node tests/{self.script} prints the output)")
                self.fail(f"the known defect “{case['name']}” no longer reproduces: change test.defect to test in {self.script}")


class Scratch:
    """A private temporary directory removed on exit."""

    def __enter__(self) -> Path:
        self._directory = tempfile.TemporaryDirectory(prefix="av-test-")
        return Path(self._directory.name)

    def __exit__(self, *exc: object) -> None:
        self._directory.cleanup()


def write_hostile_fixtures(directory: Path) -> dict[str, Path]:
    """The hostile trial, narrative and specification from fixtures.cjs, as files."""
    result = run_node(TESTS / "fixtures.cjs", "--write", directory)
    if result.returncode != 0:
        raise AssertionError(f"fixtures.cjs failed:\n{result.stderr}")
    return {name: directory / f"hostile-{name}.json" for name in ("trial", "narrative", "spec")}
