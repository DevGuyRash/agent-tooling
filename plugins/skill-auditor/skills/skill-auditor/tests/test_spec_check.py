from __future__ import annotations

import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "spec_check.sh"


def run_spec_check(skill_dir: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    completed = subprocess.run(
        ["sh", str(SCRIPT), str(skill_dir), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, json.loads(completed.stdout)


def make_skill(
    tmp: str,
    *,
    slug: str = "demo-skill",
    name: str = "Demo Skill",
    description: str = "Check demo skills and explain findings. Use when the task involves: (1) Auditing demo skills, (2) Reviewing demo packaging.",
    body: str = "\n# Demo Skill\n",
    scripts: dict[str, str] | None = None,
    extra_files: dict[str, str] | None = None,
    references: dict[str, str] | None = None,
) -> Path:
    skill_dir = Path(tmp) / slug
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_md = f"---\nname: {name}\ndescription: >-\n  {description}\n---\n{body}"
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    if scripts:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        for fname, content in scripts.items():
            script_file = scripts_dir / fname
            script_file.write_text(content, encoding="utf-8")
            if fname.endswith(".sh"):
                script_file.chmod(script_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if references:
        ref_dir = skill_dir / "references"
        ref_dir.mkdir(exist_ok=True)
        for fname, content in references.items():
            (ref_dir / fname).write_text(content, encoding="utf-8")

    if extra_files:
        for fpath, content in extra_files.items():
            full = skill_dir / fpath
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")

    return skill_dir


class SpecCheckPassTests(unittest.TestCase):
    def test_valid_skill_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                scripts={"helper.sh": "#!/usr/bin/env sh\nset -eu\ntrap 'rm -f /tmp/x' EXIT\necho ok\n"},
            )
            completed, data = run_spec_check(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])
        self.assertEqual(data["issue_count"], 0)

    def test_active_skill_passes(self) -> None:
        completed, data = run_spec_check(ROOT)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])


class SlugValidationTests(unittest.TestCase):
    def test_uppercase_slug_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp, slug="Demo-Skill", name="Demo Skill")
            completed, data = run_spec_check(skill_dir)

        self.assertFalse(data["ok"])
        codes = {i["code"] for i in data["issues"]}
        self.assertIn("slug_format", codes)

    def test_double_hyphen_slug_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp, slug="demo--skill", name="Demo  Skill")
            completed, data = run_spec_check(skill_dir)

        self.assertFalse(data["ok"])
        codes = {i["code"] for i in data["issues"]}
        self.assertIn("slug_double_hyphen", codes)


class NameValidationTests(unittest.TestCase):
    def test_slug_name_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp, name="demo-skill")
            completed, data = run_spec_check(skill_dir)

        self.assertFalse(data["ok"])
        codes = {i["code"] for i in data["issues"]}
        self.assertIn("name_not_title_case", codes)

    def test_name_slug_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp, name="Wrong Name")
            completed, data = run_spec_check(skill_dir)

        self.assertFalse(data["ok"])
        codes = {i["code"] for i in data["issues"]}
        self.assertIn("name_slug_mismatch", codes)


class H1HeadingTests(unittest.TestCase):
    def test_mismatched_h1_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp, body="\n# Wrong Heading\n")
            completed, data = run_spec_check(skill_dir)

        self.assertFalse(data["ok"])
        codes = {i["code"] for i in data["issues"]}
        self.assertIn("h1_name_mismatch", codes)

    def test_matching_h1_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp, body="\n# Demo Skill\n")
            completed, data = run_spec_check(skill_dir)

        self.assertTrue(data["ok"])


class DescriptionTriggerListTests(unittest.TestCase):
    def test_missing_trigger_list_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                description="A simple skill that does things for people.",
            )
            completed, data = run_spec_check(skill_dir)

        self.assertTrue(data["ok"])
        codes = {w["code"] for w in data["warnings"]}
        self.assertIn("description_no_trigger_list", codes)

    def test_numbered_trigger_list_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp)
            completed, data = run_spec_check(skill_dir)

        self.assertTrue(data["ok"])
        codes = {w["code"] for w in data["warnings"]}
        self.assertNotIn("description_no_trigger_list", codes)


class FileSizeTests(unittest.TestCase):
    def test_skill_md_over_500_lines_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            long_body = "\n# Demo Skill\n" + "\n".join(f"Line {i}" for i in range(510))
            skill_dir = make_skill(tmp, body=long_body)
            completed, data = run_spec_check(skill_dir)

        self.assertFalse(data["ok"])
        codes = {i["code"] for i in data["issues"]}
        self.assertIn("skill_md_too_long", codes)

    def test_reference_over_300_lines_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            long_ref = "\n".join(f"Line {i}" for i in range(310))
            skill_dir = make_skill(tmp, references={"big-ref.md": long_ref})
            completed, data = run_spec_check(skill_dir)

        self.assertTrue(data["ok"])
        codes = {w["code"] for w in data["warnings"]}
        self.assertIn("reference_too_long", codes)


class LineEndingTests(unittest.TestCase):
    def test_crlf_in_md_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp, references={"notes.md": "line one\r\nline two\r\n"})
            completed, data = run_spec_check(skill_dir)

        self.assertFalse(data["ok"])
        codes = {i["code"] for i in data["issues"]}
        self.assertIn("crlf_line_endings", codes)


class SecretPatternTests(unittest.TestCase):
    def test_env_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp, extra_files={".env": "SECRET_KEY=abc123"})
            completed, data = run_spec_check(skill_dir)

        self.assertFalse(data["ok"])
        codes = {i["code"] for i in data["issues"]}
        self.assertIn("secret_pattern_file", codes)

    def test_credentials_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp, extra_files={"credentials.json": '{"key": "value"}'})
            completed, data = run_spec_check(skill_dir)

        self.assertFalse(data["ok"])
        codes = {i["code"] for i in data["issues"]}
        self.assertIn("secret_pattern_file", codes)


class ShellScriptTests(unittest.TestCase):
    def test_non_executable_script_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                scripts={"helper.sh": "#!/usr/bin/env sh\necho ok\n"},
            )
            script_path = skill_dir / "scripts" / "helper.sh"
            script_path.chmod(0o644)
            completed, data = run_spec_check(skill_dir)

        self.assertFalse(data["ok"])
        codes = {i["code"] for i in data["issues"]}
        self.assertIn("script_not_executable", codes)

    def test_missing_shebang_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                scripts={"helper.sh": "echo ok\n"},
            )
            completed, data = run_spec_check(skill_dir)

        self.assertFalse(data["ok"])
        codes = {i["code"] for i in data["issues"]}
        self.assertIn("script_missing_shebang", codes)

    def test_missing_trap_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                scripts={"helper.sh": "#!/usr/bin/env sh\nset -eu\necho ok\n"},
            )
            completed, data = run_spec_check(skill_dir)

        self.assertTrue(data["ok"])
        codes = {w["code"] for w in data["warnings"]}
        self.assertIn("script_no_trap", codes)

    def test_script_with_trap_no_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                scripts={"helper.sh": "#!/usr/bin/env sh\nset -eu\ntrap 'rm -f /tmp/x' EXIT\necho ok\n"},
            )
            completed, data = run_spec_check(skill_dir)

        self.assertTrue(data["ok"])
        codes = {w["code"] for w in data["warnings"]}
        self.assertNotIn("script_no_trap", codes)


class TextOutputTests(unittest.TestCase):
    def test_pass_text_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp)
            completed = subprocess.run(
                ["sh", str(SCRIPT), str(skill_dir), "--format", "text"],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("PASS spec_check", completed.stdout)

    def test_fail_text_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp, name="demo-skill")
            completed = subprocess.run(
                ["sh", str(SCRIPT), str(skill_dir), "--format", "text"],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("FAIL spec_check", completed.stdout)


if __name__ == "__main__":
    unittest.main()
