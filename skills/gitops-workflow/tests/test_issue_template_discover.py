from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "issue-template-discover.sh"


def run(cmd, *, cwd: Path, env=None, check=True):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


class IssueTemplateDiscoverTests(unittest.TestCase):
    def test_discovers_templates_in_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)

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
                "      printf '[{\"type\":\"file\",\"path\":\".github/ISSUE_TEMPLATE/bug.md\"},{\"type\":\"file\",\"path\":\".github/ISSUE_TEMPLATE/feature.MD\"},{\"type\":\"file\",\"path\":\".github/ISSUE_TEMPLATE/config.yaml\"}]\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "    repos/acme/widget/contents/*)\n"
                "      printf '{}\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "  esac\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(["bash", str(SCRIPT), "--repo", "acme/widget", "--format", "json"], cwd=ROOT, env=env)
            payload = json.loads(proc.stdout)
            ids = [entry["id"] for entry in payload["templates"]]
            self.assertIn(".github/ISSUE_TEMPLATE/bug.md", ids)
            self.assertIn(".github/ISSUE_TEMPLATE/feature.MD", ids)
            self.assertIn(".github/ISSUE_TEMPLATE/config.yaml", ids)

    def test_extracts_template_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)

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
                "    repos/acme/widget/contents/.github/ISSUE_TEMPLATE/bug.md?ref=main)\n"
                "      printf '{\"type\":\"file\",\"encoding\":\"base64\",\"content\":\"IyBCdWcgVGVtcGxhdGUKCi0gU3RlcA==\"}\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "    repos/acme/widget/contents/.github/ISSUE_TEMPLATE?ref=main)\n"
                "      printf '[{\"type\":\"file\",\"path\":\".github/ISSUE_TEMPLATE/bug.md\"}]\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "    repos/acme/widget/contents/*)\n"
                "      printf '{}\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "  esac\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                ["bash", str(SCRIPT), "--repo", "acme/widget", "--template-id", ".github/ISSUE_TEMPLATE/bug.md"],
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(proc.stdout, "# Bug Template\n\n- Step")


if __name__ == "__main__":
    unittest.main()
