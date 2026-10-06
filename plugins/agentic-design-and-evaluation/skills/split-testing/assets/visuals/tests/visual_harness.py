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
