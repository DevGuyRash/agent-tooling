from __future__ import annotations

import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "discoverability_check.sh"


def run_discoverability_check(skill_dir: Path, *extra: str) -> dict:
    output = subprocess.check_output(
        ["sh", str(SCRIPT), str(skill_dir), "--format", "json", *extra],
        text=True,
    )
    return json.loads(output)


class DiscoverabilityCheckTests(unittest.TestCase):
    def test_run_is_stderr_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\ntool dispatch --role <ROLE>\ntool dispatch --help\n```\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                ["sh", str(SCRIPT), str(skill_dir), "--format", "json"],
                text=True,
                capture_output=True,
                check=True,
            )

        self.assertEqual(completed.stderr, "")

    def test_flags_missing_doc_helper_for_enum_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\ntool dispatch --role <ROLE>\n```\n",
                encoding="utf-8",
            )

            data = run_discoverability_check(skill_dir)

        self.assertEqual(data["summary"]["total_enum_options"], 1)
        self.assertEqual(data["summary"]["doc_discovery_examples"], 0)
        self.assertEqual(data["summary"]["discovery_gaps"], 1)

    def test_ignores_non_enum_placeholder_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\naudit run --cli <binary>\n```\n",
                encoding="utf-8",
            )

            data = run_discoverability_check(skill_dir)

        self.assertEqual(data["summary"]["total_enum_options"], 0)
        self.assertEqual(data["summary"]["discovery_gaps"], 0)

    def test_passes_with_doc_helper_and_cli_help_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            cli = skill_dir / "fake-cli"
            cli.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env sh
                    if [ "${1-}" = "--help" ]; then
                        echo "Usage: fake-cli"
                        echo "  dispatch    Dispatch prompts"
                        echo "  --list-roles"
                        exit 0
                    fi
                    if [ "${1-}" = "dispatch" ] && [ "${2-}" = "--help" ]; then
                        echo "Usage: fake-cli dispatch --role <ROLE>"
                        echo "  --role <ROLE>"
                        echo "  --list"
                        exit 0
                    fi
                    echo "error: unknown"
                    exit 1
                    """
                ),
                encoding="utf-8",
            )
            cli.chmod(0o755)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\ntool dispatch --role <ROLE>\ntool dispatch --help\n```\n",
                encoding="utf-8",
            )

            data = run_discoverability_check(skill_dir, "--cli", str(cli))

        self.assertEqual(data["summary"]["discovery_gaps"], 0)
        self.assertEqual(data["summary"]["option_help_coverage_failures"], 0)
        self.assertEqual(data["options"][0]["status"], "found-in-help")

    def test_flags_missing_cli_helper_and_missing_option_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            cli = skill_dir / "fake-cli"
            cli.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env sh
                    if [ "${1-}" = "--help" ]; then
                        echo "Usage: fake-cli"
                        echo "  dispatch    Dispatch prompts"
                        exit 0
                    fi
                    if [ "${1-}" = "dispatch" ] && [ "${2-}" = "--help" ]; then
                        echo "Usage: fake-cli dispatch"
                        exit 0
                    fi
                    echo "error: unknown"
                    exit 1
                    """
                ),
                encoding="utf-8",
            )
            cli.chmod(0o755)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\ntool dispatch --role <ROLE>\n```\n",
                encoding="utf-8",
            )

            data = run_discoverability_check(skill_dir, "--cli", str(cli))

        self.assertGreaterEqual(data["summary"]["discovery_gaps"], 1)
        self.assertEqual(data["summary"]["option_help_coverage_failures"], 1)
        self.assertEqual(data["options"][0]["status"], "missing-in-help")

    def test_json_contains_expected_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\nNo CLI options here.\n",
                encoding="utf-8",
            )

            data = run_discoverability_check(skill_dir)

        for key in (
            "total_enum_options",
            "doc_discovery_examples",
            "doc_next_step_examples",
            "phased_workflow_detected",
            "cli_help_checked",
            "cli_no_arg_usage",
            "cli_list_like_helpers",
            "cli_step_guidance",
            "option_help_coverage_failures",
            "discovery_gaps",
        ):
            self.assertIn(key, data["summary"])
        self.assertIsInstance(data["options"], list)

    def test_detects_step_guidance_for_phased_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            cli = skill_dir / "fake-cli"
            cli.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env sh
                    if [ $# -eq 0 ]; then
                        echo "Usage: fake-cli <command>"
                        echo "Commands:"
                        echo "  next-steps"
                        echo "  step"
                        exit 0
                    fi
                    if [ "${1-}" = "--help" ]; then
                        echo "Usage: fake-cli"
                        echo "  next-steps"
                        echo "  step"
                        exit 0
                    fi
                    if [ "${1-}" = "step" ] && [ "${2-}" = "--help" ]; then
                        echo "Usage: fake-cli step <N>"
                        exit 0
                    fi
                    if [ "${1-}" = "next-steps" ] && [ "${2-}" = "--help" ]; then
                        echo "Usage: fake-cli next-steps"
                        exit 0
                    fi
                    exit 0
                    """
                ),
                encoding="utf-8",
            )
            cli.chmod(0o755)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n## Workflow\n\nPhase 1 starts here.\n\n```bash\nfake-cli next-steps\nfake-cli step <N>\n```\n",
                encoding="utf-8",
            )

            data = run_discoverability_check(skill_dir, "--cli", str(cli))

        self.assertGreaterEqual(data["summary"]["doc_next_step_examples"], 1)
        self.assertGreaterEqual(data["summary"]["cli_step_guidance"], 1)
        self.assertEqual(data["summary"]["cli_no_arg_usage"], 1)


if __name__ == "__main__":
    unittest.main()
