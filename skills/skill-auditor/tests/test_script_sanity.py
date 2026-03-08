from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "script_sanity.sh"


def run_script_sanity(skill_dir: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    completed = subprocess.run(
        ["sh", str(SCRIPT), str(skill_dir), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, json.loads(completed.stdout)


def write_script(path: Path, *, executable: bool = True, line_ending: str = "\n") -> None:
    path.write_bytes(f"#!/usr/bin/env sh{line_ending}exit 0{line_ending}".encode("utf-8"))
    if executable:
        path.chmod(0o755)
    else:
        path.chmod(0o644)


class ScriptSanityTests(unittest.TestCase):
    def test_valid_script_surface_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            for name in ("frontmatter_check.sh", "reference_check.sh", "script_sanity.sh"):
                write_script(scripts_dir / name)

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])

    def test_unexpected_script_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            for name in ("frontmatter_check.sh", "reference_check.sh", "script_sanity.sh", "extra_check.sh"):
                write_script(scripts_dir / name)

            completed, data = run_script_sanity(skill_dir)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unexpected_script", {issue["code"] for issue in data["issues"]})

    def test_non_executable_script_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            write_script(scripts_dir / "frontmatter_check.sh")
            write_script(scripts_dir / "reference_check.sh")
            write_script(scripts_dir / "script_sanity.sh", executable=False)

            completed, data = run_script_sanity(skill_dir)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("not_executable", {issue["code"] for issue in data["issues"]})

    def test_active_skill_passes(self) -> None:
        completed, data = run_script_sanity(ROOT)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
