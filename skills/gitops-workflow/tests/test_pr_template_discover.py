from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pr-template-discover.sh"


def run(cmd, *, cwd: Path, env=None, check=True):
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=check,
    )


class PrTemplateDiscoverDecodeTests(unittest.TestCase):
    def test_template_extract_uses_bsd_base64_decode_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$1\" == \"repo\" && \"$2\" == \"view\" ]]; then\n"
                "  printf 'main\\n'\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"$1\" == \"api\" ]]; then\n"
                "  case \"$2\" in\n"
                "    repos/acme/widget/contents/*pull_request_template.md?ref=main)\n"
                "      printf '{\"type\":\"file\",\"encoding\":\"base64\",\"content\":\"IyBIZWxsbyBmcm9tIHRlbXBsYXRlCi0gU3RlcCAxCg==\"}\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "    repos/acme/widget/contents/.github/PULL_REQUEST_TEMPLATE?ref=main)\n"
                "      printf '[]\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "  esac\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            fake_base64 = fake_bin / "base64"
            fake_base64.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"--decode\" ]]; then\n"
                "  exit 1\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"-D\" ]]; then\n"
                "  python3 -c 'import base64,sys; sys.stdout.write(base64.b64decode(sys.stdin.read()).decode(\"utf-8\"))'\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_base64.chmod(fake_base64.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                [
                    "bash",
                    str(SCRIPT),
                    "--repo",
                    "acme/widget",
                    "--template-id",
                    ".github/pull_request_template.md",
                ],
                cwd=ROOT,
                env=env,
            )

            self.assertEqual(proc.stdout, "# Hello from template\n- Step 1\n")


if __name__ == "__main__":
    unittest.main()
