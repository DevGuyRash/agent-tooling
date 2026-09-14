from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "script_sanity.sh"

def run_script_sanity(skill_dir: Path, *extra: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    completed = subprocess.run(
        ["sh", str(SCRIPT), str(skill_dir), "--format", "json", *extra],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, json.loads(completed.stdout)


def write_script(path: Path, *, executable: bool = True, line_ending: str = "\n", content: str | None = None) -> None:
    if content is None:
        content = f"#!/usr/bin/env sh{line_ending}exit 0{line_ending}"
    path.write_bytes(content.encode("utf-8"))
    if executable:
        path.chmod(0o755)
    else:
        path.chmod(0o644)


class ErrorTests(unittest.TestCase):
    """A directly executable text file needs a usable shebang."""

    def test_non_executable_shell_file_is_observed_without_assuming_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            write_script(scripts_dir / "start.sh")
            write_script(scripts_dir / "repair.sh", executable=False)

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertIn("not_executable", {o["code"] for o in data["observations"]})

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

        self.assertEqual(completed.returncode, 1)
        self.assertIn("missing_shebang", {e["code"] for e in data["errors"]})

    def test_executable_shell_launcher_without_shebang_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            script_path = scripts_dir / "start.sh"
            script_path.write_text("echo hi\n", encoding="utf-8")
            script_path.chmod(0o755)

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("missing_shebang", {e["code"] for e in data["errors"]})

    def test_crlf_in_executable_script_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            write_script(scripts_dir / "start.sh", line_ending="\r\n")

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("crlf_in_executable", {e["code"] for e in data["errors"]})

    def test_a_target_with_an_error_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            script_path = scripts_dir / "repair.sh"
            script_path.write_text("echo repair\n", encoding="utf-8")
            script_path.chmod(0o755)

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertGreater(data["error_count"], 0)


class ObservationTests(unittest.TestCase):
    """CRLF outside an executable is observable without being a policy verdict."""

    def test_crlf_in_a_non_executable_file_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            refs_dir = skill_dir / "references"
            skill_dir.mkdir()
            refs_dir.mkdir()
            (refs_dir / "notes.md").write_bytes(b"line one\r\nline two\r\n")

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        codes = {o["code"] for o in data["observations"]}
        self.assertEqual(codes, {"crlf"})

class CleanTargetTests(unittest.TestCase):
    def test_missing_scripts_directory_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            skill_dir.mkdir()

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertEqual(data["observation_count"], 0)
        self.assertEqual(data["script_count"], 0)

    def test_valid_script_surface_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            scripts_dir = skill_dir / "scripts"
            skill_dir.mkdir()
            scripts_dir.mkdir()
            for name in ("start.sh", "verify.sh", "helper.py"):
                write_script(scripts_dir / name)

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertEqual(data["observation_count"], 0)
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["observations"], [])

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
        self.assertEqual(data["error_count"], 0)
        self.assertEqual(data["observation_count"], 0)

    def test_active_skill_passes(self) -> None:
        completed, data = run_script_sanity(ROOT)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)


class ObservationsOnlyExitTests(unittest.TestCase):
    def test_a_target_whose_only_findings_are_observations_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            refs_dir = skill_dir / "references"
            skill_dir.mkdir()
            refs_dir.mkdir()
            (refs_dir / "notes.md").write_bytes(b"line one\r\nline two\r\n")

            completed, data = run_script_sanity(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertGreater(data["observation_count"], 0)


class SourceTagTests(unittest.TestCase):
    def test_every_observation_source_is_open_standard_or_repo_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            refs_dir = skill_dir / "references"
            skill_dir.mkdir()
            refs_dir.mkdir()
            (refs_dir / "notes.md").write_bytes(b"line one\r\nline two\r\n")

            completed, data = run_script_sanity(skill_dir)

        self.assertGreater(data["observation_count"], 0)
        for obs in data["observations"]:
            if "source" in obs:
                self.assertIn(obs["source"], {"open-standard", "repo-overlay"})

class UsageExitTests(unittest.TestCase):
    def test_unusable_input_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            skill_dir.mkdir()

            bad_flag = subprocess.run(
                ["sh", str(SCRIPT), str(skill_dir), "--nope"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(bad_flag.returncode, 2)

            bad_format = subprocess.run(
                ["sh", str(SCRIPT), str(skill_dir), "--format", "xml"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(bad_format.returncode, 2)
            self.assertIn("hint:", bad_format.stderr)

        missing_dir = subprocess.run(
            ["sh", str(SCRIPT), "/tmp/definitely-not-a-real-skill-dir-xyz"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(missing_dir.returncode, 2)


class MixedLineEndingTests(unittest.TestCase):
    def test_body_crlf_does_not_claim_broken_shebang(self):
        for relative in ("scripts/run.py", "examples/run.py"):
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as tmp:
                target=Path(tmp)/"fixture"
                path=target/relative;path.parent.mkdir(parents=True)
                path.write_bytes(b"#!/usr/bin/env python3\nprint('RUN_OK')\r\n")
                path.chmod(0o755)
                executed=subprocess.run([str(path)],text=True,capture_output=True)
                self.assertEqual(executed.returncode,0,executed.stderr)
                self.assertEqual(executed.stdout.strip(),"RUN_OK")
                proc=subprocess.run(['sh',str(SCRIPT),str(target),'--format','json'],text=True,capture_output=True)
                data=json.loads(proc.stdout)
                self.assertEqual(proc.returncode,0,proc.stdout)
                self.assertEqual(data['errors'],[])
                self.assertIn('crlf',{o['code'] for o in data['observations']})

if __name__ == "__main__":
    unittest.main()
