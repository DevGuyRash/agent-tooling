from __future__ import annotations

import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "staleness_check.sh"


def run_staleness_check(skill_dir: Path, *extra: str) -> dict:
    output = subprocess.check_output(
        ["sh", str(SCRIPT), str(skill_dir), "--format", "json", *extra],
        text=True,
    )
    return json.loads(output)


class StalenessCheckTests(unittest.TestCase):
    def test_executes_safe_local_script_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            script = scripts_dir / "run.sh"
            script.write_text(
                "#!/usr/bin/env sh\necho run help\n",
                encoding="utf-8",
            )
            script.chmod(0o755)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\nscripts/run.sh --help\n```\n",
                encoding="utf-8",
            )

            data = run_staleness_check(skill_dir)

        self.assertEqual(data["summary"]["executed"], 1)
        self.assertEqual(data["summary"]["executed_direct"], 1)
        self.assertEqual(data["examples"][0]["status"], "executed")
        self.assertEqual(data["examples"][0]["verification_mode"], "direct")

    def test_flags_missing_local_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\nscripts/missing.sh --help\n```\n",
                encoding="utf-8",
            )

            data = run_staleness_check(skill_dir)

        self.assertEqual(data["summary"]["missing_target"], 1)
        self.assertEqual(data["examples"][0]["status"], "missing-target")
        self.assertEqual(data["examples"][0]["reason_code"], "missing_local_target")

    def test_detects_cli_flag_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            cli = skill_dir / "fake-cli"
            cli.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env sh
                    case "$1" in
                        --help|-h)
                            echo "usage: fake-cli [--help]"
                            exit 0
                            ;;
                        --old-flag)
                            echo "error: unknown option: --old-flag"
                            exit 2
                            ;;
                        *)
                            echo "ok"
                            exit 0
                            ;;
                    esac
                    """
                ),
                encoding="utf-8",
            )
            cli.chmod(0o755)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\ntool --old-flag --help\n```\n",
                encoding="utf-8",
            )

            data = run_staleness_check(skill_dir, "--cli", str(cli))

        self.assertEqual(data["summary"]["flag_drift"], 1)
        self.assertEqual(data["examples"][0]["status"], "flag-drift")

    def test_multiline_fenced_command_is_single_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            script = scripts_dir / "run.sh"
            script.write_text(
                "#!/usr/bin/env sh\nif [ \"${1-}\" = \"--help\" ]; then echo help; fi\n",
                encoding="utf-8",
            )
            script.chmod(0o755)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\nscripts/run.sh \\\n  --help\n```\n",
                encoding="utf-8",
            )

            data = run_staleness_check(skill_dir)

        self.assertEqual(data["summary"]["total_examples"], 1)
        self.assertEqual(data["examples"][0]["status"], "executed")

    def test_inline_non_help_command_is_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\nRun `gh issue list --search \"keyword\"` to inspect.\n",
                encoding="utf-8",
            )

            data = run_staleness_check(skill_dir)

        self.assertEqual(data["summary"]["total_examples"], 1)
        self.assertEqual(data["examples"][0]["status"], "unsafe-skipped")
        self.assertEqual(data["examples"][0]["reason_code"], "nonlocal_without_cli")

    def test_placeholder_local_command_uses_help_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            script = scripts_dir / "run.sh"
            script.write_text(
                "#!/usr/bin/env sh\nif [ \"${1-}\" = \"--help\" ]; then echo usage; exit 0; fi\nexit 0\n",
                encoding="utf-8",
            )
            script.chmod(0o755)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\nbash \"$SKILL_ROOT/scripts/run.sh\" <target>\n```\n",
                encoding="utf-8",
            )

            data = run_staleness_check(skill_dir)

        self.assertEqual(data["summary"]["executed"], 1)
        self.assertEqual(data["summary"]["executed_help_fallback"], 1)
        self.assertEqual(data["examples"][0]["status"], "executed")
        self.assertEqual(data["examples"][0]["verification_mode"], "help-fallback")

    def test_placeholder_cli_command_uses_subcommand_help_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            cli = skill_dir / "fake-cli"
            cli.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env sh
                    if [ "$1" = "dispatch" ] && [ "$2" = "--help" ]; then
                        echo "dispatch usage"
                        exit 0
                    fi
                    if [ "$1" = "--help" ]; then
                        echo "usage"
                        exit 0
                    fi
                    echo "error"
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

            data = run_staleness_check(skill_dir, "--cli", str(cli))

        self.assertEqual(data["summary"]["executed"], 1)
        self.assertEqual(data["summary"]["executed_subcommand_help"], 1)
        self.assertEqual(data["examples"][0]["verification_mode"], "subcommand-help")

    def test_preserves_quoted_arguments_for_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            script = scripts_dir / "run.sh"
            script.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env sh
                    if [ "${1-}" = "--message" ] && [ "${2-}" = "hello world" ] && [ "${3-}" = "--help" ]; then
                        echo "ok"
                        exit 0
                    fi
                    echo "error: bad args"
                    exit 2
                    """
                ),
                encoding="utf-8",
            )
            script.chmod(0o755)
            (skill_dir / "SKILL.md").write_text(
                '# Skill\n\n```bash\nscripts/run.sh --message "hello world" --help\n```\n',
                encoding="utf-8",
            )

            data = run_staleness_check(skill_dir)

        self.assertEqual(data["summary"]["executed"], 1)
        self.assertEqual(data["examples"][0]["status"], "executed")
        self.assertEqual(data["examples"][0]["verification_mode"], "direct")

    def test_times_out_long_running_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            script = scripts_dir / "hang.sh"
            script.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env sh
                    sleep 2
                    """
                ),
                encoding="utf-8",
            )
            script.chmod(0o755)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\nscripts/hang.sh --help\n```\n",
                encoding="utf-8",
            )

            data = run_staleness_check(skill_dir, "--timeout-seconds", "1")

        self.assertEqual(data["summary"]["runtime_failed"], 1)
        self.assertEqual(data["examples"][0]["status"], "runtime-failed")
        self.assertEqual(data["examples"][0]["reason_code"], "timeout_exceeded")

    def test_json_is_backward_compatible_with_new_detail_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\nRun `gh issue list --search \"keyword\"` now.\n",
                encoding="utf-8",
            )

            data = run_staleness_check(skill_dir)

        for key in (
            "total_examples",
            "executed",
            "runtime_failed",
            "missing_target",
            "flag_drift",
            "unsafe_skipped",
            "placeholder_skipped",
            "claim_compare_required",
        ):
            self.assertIn(key, data["summary"])

        for key in (
            "executed_direct",
            "executed_help_fallback",
            "executed_subcommand_help",
            "extracted_fenced",
            "extracted_inline",
        ):
            self.assertIn(key, data["summary"])

        self.assertIn("reason_code", data["examples"][0])
        self.assertIn("normalized_command", data["examples"][0])
        self.assertIn("verification_mode", data["examples"][0])
        self.assertIn("raw_command", data["examples"][0])

    def test_skips_non_executable_local_file_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            references_dir = skill_dir / "references"
            references_dir.mkdir(parents=True)
            (references_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\n<skills-file-root>/references/guide.md --help\n```\n",
                encoding="utf-8",
            )

            data = run_staleness_check(skill_dir)

        self.assertEqual(data["summary"]["unsafe_skipped"], 1)
        self.assertEqual(data["examples"][0]["status"], "unsafe-skipped")
        self.assertEqual(data["examples"][0]["reason_code"], "non_executable_target")

    def test_preserves_empty_tsv_columns_for_example_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            script = scripts_dir / "run.sh"
            script.write_text(
                "#!/usr/bin/env sh\nif [ \"${1-}\" = \"--help\" ]; then echo usage; exit 0; fi\nexit 0\n",
                encoding="utf-8",
            )
            script.chmod(0o755)
            (skill_dir / "SKILL.md").write_text(
                "```bash\nscripts/run.sh --help\n```\n",
                encoding="utf-8",
            )

            data = run_staleness_check(skill_dir)

        self.assertEqual(data["summary"]["total_examples"], 1)
        self.assertEqual(data["examples"][0]["command"], "scripts/run.sh --help")
        self.assertEqual(data["examples"][0]["raw_command"], "scripts/run.sh --help")
        self.assertEqual(data["examples"][0]["claim_context_before"], "")
        self.assertEqual(data["examples"][0]["claim_context_after"], "")


if __name__ == "__main__":
    unittest.main()
