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
    def test_missing_scripts_directory_passes_for_instruction_only_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            skill_dir.mkdir()

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])
        self.assertEqual(data["script_count"], 0)

    def test_valid_script_surface_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            for name in ("start.sh", "verify.sh", "helper.py"):
                write_script(scripts_dir / name)

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])

    def test_generic_script_names_do_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            for name in ("build.sh", "check.sh", "lint.sh", "repair.sh"):
                write_script(scripts_dir / name)

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])

    def test_non_executable_script_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            write_script(scripts_dir / "start.sh")
            write_script(scripts_dir / "verify.sh")
            write_script(scripts_dir / "repair.sh", executable=False)

            completed, data = run_script_sanity(skill_dir)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("not_executable", {issue["code"] for issue in data["issues"]})

    def test_executable_python_script_without_shebang_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            script_path = scripts_dir / "helper.py"
            script_path.write_text("print('hi')\n", encoding="utf-8")
            script_path.chmod(0o755)

            completed, data = run_script_sanity(skill_dir)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("missing_shebang", {issue["code"] for issue in data["issues"]})

    def test_executable_binary_without_extension_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            binary_path = scripts_dir / "tool"
            binary_path.write_bytes(b"\x7fELF\x02\x01\x01\x00binary payload")
            binary_path.chmod(0o755)

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])

    def test_active_skill_passes(self) -> None:
        completed, data = run_script_sanity(ROOT)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
