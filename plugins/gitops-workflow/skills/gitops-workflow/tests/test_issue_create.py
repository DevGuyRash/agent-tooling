from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "issue-create.sh"


def run(cmd, *, cwd: Path, env=None, check=True):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


def init_repo(path: Path) -> None:
    run(["git", "init"], cwd=path)
    run(["git", "config", "user.email", "dev@example.com"], cwd=path)
    run(["git", "config", "user.name", "Dev"], cwd=path)
    run(["git", "checkout", "-b", "main"], cwd=path)
    readme = path / "README.md"
    readme.write_text("base\n", encoding="utf-8")
    run(["git", "add", "README.md"], cwd=path)
    run(["git", "commit", "-m", "docs: base"], cwd=path)


class IssueCreateTests(unittest.TestCase):
    def test_generates_body_from_skill_fallback_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            proc = run(
                ["bash", str(SCRIPT), "--title", "feat: track issue flow"],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            m = re.search(r"Issue body file prepared:\s*(\S+)", proc.stdout)
            self.assertIsNotNone(m, proc.stdout)
            body = Path(m.group(1)).read_text(encoding="utf-8")
            self.assertIn("# Summary", body)
            self.assertIn("## Acceptance Criteria", body)

    def test_create_requires_force_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            proc = run(
                ["bash", str(SCRIPT), "--title", "feat: track issue flow", "--create"],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("--create requires --force-create", proc.stderr)

    def test_create_requires_template_selection_when_multiple_remote_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            fake_bin = tmp_path / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$1\" == \"repo\" && \"$2\" == \"view\" ]]; then\n"
                "  if [[ \"$*\" == *\"defaultBranchRef\"* ]]; then\n"
                "    printf 'main\\n'\n"
                "  else\n"
                "    printf 'acme/widget\\n'\n"
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"$1\" == \"api\" ]]; then\n"
                "  case \"$2\" in\n"
                "    repos/acme/widget/contents/.github/ISSUE_TEMPLATE?ref=main)\n"
                "      printf '[{\"type\":\"file\",\"path\":\".github/ISSUE_TEMPLATE/bug.md\"},{\"type\":\"file\",\"path\":\".github/ISSUE_TEMPLATE/feature.md\"}]\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "    repos/acme/widget/contents/*)\n"
                "      printf '{}\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "  esac\n"
                "fi\n"
                "if [[ \"$1\" == \"issue\" && \"$2\" == \"create\" ]]; then\n"
                "  echo 'unexpected issue create' >&2\n"
                "  exit 1\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                [
                    "bash",
                    str(SCRIPT),
                    "--title",
                    "feat: track issue flow",
                    "--repo",
                    "acme/widget",
                    "--create",
                    "--force-create",
                ],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("template selection required before --create", proc.stderr)


if __name__ == "__main__":
    unittest.main()
