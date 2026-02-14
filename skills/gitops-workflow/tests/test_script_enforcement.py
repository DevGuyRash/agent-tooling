from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"


def run(cmd, *, cwd: Path, env=None, check=True):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


class ScriptSyntaxTests(unittest.TestCase):
    def test_shell_scripts_parse(self):
        targets = [
            SCRIPTS_DIR / "pr-workflow.sh",
            SCRIPTS_DIR / "governance-enforce.sh",
            SCRIPTS_DIR / "pr-unresolved-threads.sh",
        ]
        for target in targets:
            proc = run(["bash", "-n", str(target)], cwd=ROOT)
            self.assertEqual(proc.returncode, 0, f"bash -n failed for {target}\n{proc.stderr}")


class GovernanceWrapperBehaviorTests(unittest.TestCase):
    def test_governance_wrapper_runs_validate_plan_apply_audit_in_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "calls.log"

            fake_python3 = fake_bin / "python3"
            fake_python3.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "echo \"$*\" >> \"${FAKE_LOG}\"\n"
                "cmd=\"${2:-}\"\n"
                "if [[ \"$cmd\" == \"plan\" ]]; then\n"
                "  exit 3\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_python3.chmod(fake_python3.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_LOG"] = str(log_file)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "governance-enforce.sh")],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            calls = log_file.read_text(encoding="utf-8").strip().splitlines()
            self.assertGreaterEqual(len(calls), 4)
            self.assertIn(" validate ", f" {calls[0]} ")
            self.assertIn(" plan ", f" {calls[1]} ")
            self.assertIn(" apply ", f" {calls[2]} ")
            self.assertIn(" --write-codeowners", calls[2])
            self.assertIn(" audit ", f" {calls[3]} ")


class UnresolvedThreadsStrictModeTests(unittest.TestCase):
    def test_unresolved_threads_strict_mode_exits_three(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$1\" == \"api\" && \"$2\" == \"graphql\" ]]; then\n"
                "  has_after=\"false\"\n"
                "  for ((i=1; i<=$#; i++)); do\n"
                "    if [[ \"${!i}\" == \"-F\" ]]; then\n"
                "      next=$((i+1))\n"
                "      if [[ \"${!next}\" == after=* ]]; then\n"
                "        has_after=\"true\"\n"
                "      fi\n"
                "    fi\n"
                "  done\n"
                "  jq_expr=\"\"\n"
                "  for ((i=1; i<=$#; i++)); do\n"
                "    if [[ \"${!i}\" == \"--jq\" ]]; then\n"
                "      next=$((i+1))\n"
                "      jq_expr=\"${!next}\"\n"
                "      break\n"
                "    fi\n"
                "  done\n"
                "  if [[ \"$jq_expr\" == *\"pageInfo.hasNextPage\"* ]]; then\n"
                "    if [[ \"$has_after\" == \"false\" ]]; then\n"
                "      printf 'true\\n'\n"
                "    else\n"
                "      printf 'false\\n'\n"
                "    fi\n"
                "  elif [[ \"$jq_expr\" == *\"pageInfo.endCursor\"* ]]; then\n"
                "    printf 'CURSOR_1\\n'\n"
                "  elif [[ \"$jq_expr\" == *\"reviewThreads.nodes\"* ]]; then\n"
                "    if [[ \"$has_after\" == \"false\" ]]; then\n"
                "      printf '{\"author\":\"bot\",\"path\":\"a/b\",\"line\":1,\"url\":\"http://example/1\",\"body\":\"needs change\"}\\n'\n"
                "    else\n"
                "      printf '{\"author\":\"bot\",\"path\":\"a/b\",\"line\":2,\"url\":\"http://example/2\",\"body\":\"still unresolved\"}\\n'\n"
                "    fi\n"
                "  else\n"
                "    printf '\\n'\n"
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                "echo ''\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-unresolved-threads.sh"),
                    "7",
                    "--repo",
                    "acme/widget",
                    "--fail-on-unresolved",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
            self.assertIn("Unresolved inline review threads", proc.stdout)
            self.assertIn("http://example/1", proc.stdout)
            self.assertIn("http://example/2", proc.stdout)


class LabelsExportPaginationTests(unittest.TestCase):
    def test_labels_export_fetches_multiple_pages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$1\" == \"repo\" && \"$2\" == \"view\" ]]; then\n"
                "  printf 'acme/widget\\n'\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"$1\" == \"api\" ]]; then\n"
                "  if [[ \"$2\" == *\"&page=1\"* ]]; then\n"
                "    printf '[{\"name\":\"z-last\",\"color\":\"FFFFFF\",\"description\":\"z\"},{\"name\":\"a-first\",\"color\":\"ABCDEF\",\"description\":\"a\"}]\\n'\n"
                "  elif [[ \"$2\" == *\"&page=2\"* ]]; then\n"
                "    printf '[{\"name\":\"m-mid\",\"color\":\"123456\",\"description\":null}]\\n'\n"
                "  else\n"
                "    printf '[]\\n'\n"
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                "printf '\\n'\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                ["bash", str(SCRIPTS_DIR / "labels-export.sh")],
                cwd=ROOT,
                env=env,
                check=True,
            )

            self.assertIn('"name": "a-first"', proc.stdout)
            self.assertIn('"name": "m-mid"', proc.stdout)
            self.assertIn('"name": "z-last"', proc.stdout)
            self.assertLess(proc.stdout.find('"name": "a-first"'), proc.stdout.find('"name": "m-mid"'))
            self.assertLess(proc.stdout.find('"name": "m-mid"'), proc.stdout.find('"name": "z-last"'))


if __name__ == "__main__":
    unittest.main()
