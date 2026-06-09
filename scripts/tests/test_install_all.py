from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_ALL = REPO_ROOT / "scripts" / "install-all"


def write_fake_cli(path: Path, command_name: str) -> None:
    path.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json
            import os
            import sys

            with open(os.environ["AGENT_TOOLING_FAKE_CLI_LOG"], "a", encoding="utf-8") as handle:
                handle.write(json.dumps({{"command": {command_name!r}, "args": sys.argv[1:]}}) + "\\n")
            """
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def load_calls(log_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


class InstallAllTests(unittest.TestCase):
    def run_install_all_process(self, *args: str) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
        with tempfile.TemporaryDirectory(prefix="install-all-test-") as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            log_path = tmp_path / "cli.jsonl"
            log_path.touch()
            write_fake_cli(bin_dir / "codex", "codex")
            write_fake_cli(bin_dir / "claude", "claude")
            path_value = os.environ.get("PATH", os.defpath)
            env = {
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{path_value}",
                "AGENT_TOOLING_FAKE_CLI_LOG": str(log_path),
            }
            proc = subprocess.run(
                [str(INSTALL_ALL), *args],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=120,
            )
            return proc, load_calls(log_path)

    def run_install_all(self, *args: str) -> list[dict[str, object]]:
        proc, calls = self.run_install_all_process(*args)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        return calls

    def test_installs_all_plugins_to_codex_and_claude_with_sparse_marketplaces(self) -> None:
        calls = self.run_install_all("--source", "DevGuyRash/agent-tooling", "--ref", "main", "--claude-scope", "local")

        codex_calls = [call["args"] for call in calls if call["command"] == "codex"]
        claude_calls = [call["args"] for call in calls if call["command"] == "claude"]

        self.assertEqual(
            ["plugin", "marketplace", "add", "--ref", "main", "--sparse", ".agents/plugins", "--sparse", "plugins", "DevGuyRash/agent-tooling"],
            codex_calls[0],
        )
        self.assertEqual(["plugin", "marketplace", "upgrade", "agent-tooling"], codex_calls[1])
        self.assertEqual(
            ["plugin", "marketplace", "add", "--scope", "local", "DevGuyRash/agent-tooling", "--sparse", ".claude-plugin", "plugins"],
            claude_calls[0],
        )
        self.assertEqual(["plugin", "marketplace", "update", "agent-tooling"], claude_calls[1])

        codex_installs = codex_calls[2:]
        claude_installs = claude_calls[2:]
        self.assertEqual(11, len(codex_installs))
        self.assertEqual(11, len(claude_installs))
        self.assertEqual(["plugin", "add", "goalspec@agent-tooling"], codex_installs[6])
        self.assertEqual(["plugin", "install", "--scope", "local", "goalspec@agent-tooling"], claude_installs[6])

        codex_plugins = [args[-1] for args in codex_installs]
        claude_plugins = [args[-1] for args in claude_installs]
        self.assertEqual(codex_plugins, claude_plugins)

    def test_local_source_omits_sparse_and_ref_flags(self) -> None:
        calls = self.run_install_all("--source", str(REPO_ROOT), "--codex-only")

        self.assertEqual(
            {"command": "codex", "args": ["plugin", "marketplace", "add", str(REPO_ROOT)]},
            calls[0],
        )
        self.assertFalse(any(call["command"] == "claude" for call in calls))
        self.assertEqual(12, len(calls))

    def test_replace_marketplace_removes_existing_source_before_local_add(self) -> None:
        calls = self.run_install_all("--source", str(REPO_ROOT), "--include", "goalspec", "--replace-marketplace")

        self.assertEqual(
            [
                {"command": "codex", "args": ["plugin", "marketplace", "remove", "agent-tooling"]},
                {"command": "codex", "args": ["plugin", "marketplace", "add", str(REPO_ROOT)]},
                {"command": "codex", "args": ["plugin", "add", "goalspec@agent-tooling"]},
                {"command": "claude", "args": ["plugin", "marketplace", "remove", "agent-tooling"]},
                {"command": "claude", "args": ["plugin", "marketplace", "add", "--scope", "user", str(REPO_ROOT)]},
                {"command": "claude", "args": ["plugin", "install", "--scope", "user", "goalspec@agent-tooling"]},
            ],
            calls,
        )

    def test_claude_only_skips_codex(self) -> None:
        calls = self.run_install_all("--claude-only", "--include", "goalspec")

        self.assertFalse(any(call["command"] == "codex" for call in calls))
        self.assertEqual(
            [
                {
                    "command": "claude",
                    "args": ["plugin", "marketplace", "add", "--scope", "user", "DevGuyRash/agent-tooling", "--sparse", ".claude-plugin", "plugins"],
                },
                {
                    "command": "claude",
                    "args": ["plugin", "marketplace", "update", "agent-tooling"],
                },
                {
                    "command": "claude",
                    "args": ["plugin", "install", "--scope", "user", "goalspec@agent-tooling"],
                },
            ],
            calls,
        )

    def test_exclude_accepts_csv_globs_and_removes_matching_plugins(self) -> None:
        calls = self.run_install_all("--exclude", "rust*,gitops-workflow")

        codex_installs = [call["args"][-1] for call in calls if call["command"] == "codex" and call["args"][:2] == ["plugin", "add"]]
        claude_installs = [call["args"][-1] for call in calls if call["command"] == "claude" and call["args"][:2] == ["plugin", "install"]]

        self.assertEqual(9, len(codex_installs))
        self.assertEqual(codex_installs, claude_installs)
        self.assertNotIn("rust-development@agent-tooling", codex_installs)
        self.assertNotIn("gitops-workflow@agent-tooling", codex_installs)

    def test_include_and_exclude_are_repeatable_and_globbed(self) -> None:
        calls = self.run_install_all(
            "--include",
            "rust*,gitops-workflow",
            "--include",
            "goalspec",
            "--exclude",
            "rust*",
        )

        codex_installs = [call["args"][-1] for call in calls if call["command"] == "codex" and call["args"][:2] == ["plugin", "add"]]
        self.assertEqual(["gitops-workflow@agent-tooling", "goalspec@agent-tooling"], codex_installs)

    def test_unmatched_filter_fails_fast(self) -> None:
        proc, calls = self.run_install_all_process("--include", "missing-plugin")

        self.assertNotEqual(0, proc.returncode)
        self.assertIn("--include pattern(s) matched no plugins: missing-plugin", proc.stderr)
        self.assertEqual([], calls)


if __name__ == "__main__":
    unittest.main()
