from __future__ import annotations

import json
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


class PrTemplateDiscoverCoverageTests(unittest.TestCase):
    def test_template_id_takes_precedence_over_json_listing_for_local_templates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            run(["git", "init"], cwd=repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            template_path = repo / ".github" / "pull_request_template.md"
            template_path.parent.mkdir(parents=True, exist_ok=True)
            template_path.write_text("# Local Template\n", encoding="utf-8")

            proc = run(
                [
                    "bash",
                    str(SCRIPT),
                    "--format",
                    "json",
                    "--template-id",
                    "local:.github/pull_request_template.md",
                ],
                cwd=repo,
            )

            self.assertEqual(proc.stdout, "# Local Template\n")

    def test_discovers_local_templates_without_github_cli(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            run(["git", "init"], cwd=repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            template_dir = repo / ".github" / "PULL_REQUEST_TEMPLATE"
            template_dir.mkdir(parents=True, exist_ok=True)
            (template_dir / "feature.md").write_text("# Local Template\n", encoding="utf-8")

            proc = run(
                ["bash", str(SCRIPT), "--format", "json"],
                cwd=repo,
            )

            payload = json.loads(proc.stdout)
            self.assertEqual(payload["repo"], "")
            self.assertEqual(payload["ref"], "")
            self.assertEqual(
                payload["templates"],
                [
                    {
                        "id": "local:.github/PULL_REQUEST_TEMPLATE/feature.md",
                        "path": ".github/PULL_REQUEST_TEMPLATE/feature.md",
                        "source": "local",
                    }
                ],
            )

    def test_local_only_skips_repo_inference_and_remote_calls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            repo = tmp_path / "repo"
            fake_bin = tmp_path / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)
            run(["git", "init"], cwd=repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            template_path = repo / ".github" / "pull_request_template.md"
            template_path.parent.mkdir(parents=True, exist_ok=True)
            template_path.write_text("# Local Template\n", encoding="utf-8")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "echo \"unexpected gh invocation: $*\" >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                ["bash", str(SCRIPT), "--local-only", "--format", "json"],
                cwd=repo,
                env=env,
            )

            payload = json.loads(proc.stdout)
            self.assertEqual(payload["repo"], "")
            self.assertEqual(payload["ref"], "")
            self.assertEqual(
                payload["templates"],
                [
                    {
                        "id": "local:.github/pull_request_template.md",
                        "path": ".github/pull_request_template.md",
                        "source": "local",
                    }
                ],
            )
            self.assertEqual(proc.stderr, "")

    def test_uses_local_templates_when_default_branch_lookup_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            repo = tmp_path / "repo"
            fake_bin = tmp_path / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)
            run(["git", "init"], cwd=repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            template_path = repo / ".github" / "pull_request_template.md"
            template_path.parent.mkdir(parents=True, exist_ok=True)
            template_path.write_text("# Local Template\n", encoding="utf-8")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$1\" == \"repo\" && \"$2\" == \"view\" ]]; then\n"
                "  if [[ \"$*\" == *\"defaultBranchRef\"* ]]; then\n"
                "    echo 'authentication required' >&2\n"
                "    exit 1\n"
                "  fi\n"
                "  printf 'acme/widget\\n'\n"
                "  exit 0\n"
                "fi\n"
                "echo \"unexpected gh invocation: $*\" >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                ["bash", str(SCRIPT), "--format", "json"],
                cwd=repo,
                env=env,
            )

            payload = json.loads(proc.stdout)
            self.assertEqual(payload["repo"], "acme/widget")
            self.assertEqual(payload["ref"], "")
            self.assertEqual(
                payload["templates"],
                [
                    {
                        "id": "local:.github/pull_request_template.md",
                        "path": ".github/pull_request_template.md",
                        "source": "local",
                    }
                ],
            )
            self.assertIn("authentication required", proc.stderr)
            self.assertIn("continuing with local PR templates only", proc.stderr)

    def test_explicit_repo_uses_local_templates_when_gh_repo_view_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            repo = tmp_path / "repo"
            fake_bin = tmp_path / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)
            run(["git", "init"], cwd=repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            run(["git", "remote", "add", "origin", "https://github.com/acme/widget.git"], cwd=repo)
            template_path = repo / ".github" / "pull_request_template.md"
            template_path.parent.mkdir(parents=True, exist_ok=True)
            template_path.write_text("# Local Template\n", encoding="utf-8")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$1\" == \"repo\" && \"$2\" == \"view\" ]]; then\n"
                "  echo 'authentication required' >&2\n"
                "  exit 1\n"
                "fi\n"
                "echo \"unexpected gh invocation: $*\" >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                ["bash", str(SCRIPT), "--repo", "acme/widget", "--format", "json"],
                cwd=repo,
                env=env,
            )

            payload = json.loads(proc.stdout)
            self.assertEqual(payload["repo"], "acme/widget")
            self.assertEqual(payload["ref"], "")
            self.assertEqual(
                payload["templates"],
                [
                    {
                        "id": "local:.github/pull_request_template.md",
                        "path": ".github/pull_request_template.md",
                        "source": "local",
                    }
                ],
            )
            self.assertIn("authentication required", proc.stderr)
            self.assertIn("continuing with local PR templates only", proc.stderr)

    def test_explicit_repo_uses_local_templates_for_ssh_origin_when_gh_repo_view_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            repo = tmp_path / "repo"
            fake_bin = tmp_path / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)
            run(["git", "init"], cwd=repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            run(["git", "remote", "add", "origin", "ssh://git@github.com/acme/widget.git"], cwd=repo)
            template_path = repo / ".github" / "pull_request_template.md"
            template_path.parent.mkdir(parents=True, exist_ok=True)
            template_path.write_text("# Local Template\n", encoding="utf-8")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$1\" == \"repo\" && \"$2\" == \"view\" ]]; then\n"
                "  echo 'authentication required' >&2\n"
                "  exit 1\n"
                "fi\n"
                "echo \"unexpected gh invocation: $*\" >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                ["bash", str(SCRIPT), "--repo", "acme/widget", "--format", "json"],
                cwd=repo,
                env=env,
            )

            payload = json.loads(proc.stdout)
            self.assertEqual(payload["repo"], "acme/widget")
            self.assertEqual(payload["ref"], "")
            self.assertEqual(
                payload["templates"],
                [
                    {
                        "id": "local:.github/pull_request_template.md",
                        "path": ".github/pull_request_template.md",
                        "source": "local",
                    }
                ],
            )
            self.assertIn("authentication required", proc.stderr)
            self.assertIn("continuing with local PR templates only", proc.stderr)

    def test_explicit_repo_uses_local_templates_for_https_origin_with_credentials(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            repo = tmp_path / "repo"
            fake_bin = tmp_path / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)
            run(["git", "init"], cwd=repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            run(
                ["git", "remote", "add", "origin", "https://ci:token@github.com/acme/widget.git"],
                cwd=repo,
            )
            template_path = repo / ".github" / "pull_request_template.md"
            template_path.parent.mkdir(parents=True, exist_ok=True)
            template_path.write_text("# Local Template\n", encoding="utf-8")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$1\" == \"repo\" && \"$2\" == \"view\" ]]; then\n"
                "  echo 'authentication required' >&2\n"
                "  exit 1\n"
                "fi\n"
                "echo \"unexpected gh invocation: $*\" >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                ["bash", str(SCRIPT), "--repo", "acme/widget", "--format", "json"],
                cwd=repo,
                env=env,
            )

            payload = json.loads(proc.stdout)
            self.assertEqual(payload["repo"], "acme/widget")
            self.assertEqual(payload["ref"], "")
            self.assertEqual(
                payload["templates"],
                [
                    {
                        "id": "local:.github/pull_request_template.md",
                        "path": ".github/pull_request_template.md",
                        "source": "local",
                    }
                ],
            )
            self.assertIn("authentication required", proc.stderr)
            self.assertIn("continuing with local PR templates only", proc.stderr)

    def test_invalid_repo_slug_is_rejected(self):
        proc = run(
            [
                "bash",
                str(SCRIPT),
                "--repo",
                "../meta",
                "--format",
                "json",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("invalid --repo", proc.stderr)

    def test_discovers_uppercase_and_multi_directory_templates(self):
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
                "    repos/acme/widget/contents/.github/PULL_REQUEST_TEMPLATE.md?ref=main|repos/acme/widget/contents/PULL_REQUEST_TEMPLATE.md?ref=main|repos/acme/widget/contents/docs/PULL_REQUEST_TEMPLATE.md?ref=main)\n"
                "      printf '{\"type\":\"file\"}\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "    repos/acme/widget/contents/.github/pull_request_template.md?ref=main|repos/acme/widget/contents/pull_request_template.md?ref=main|repos/acme/widget/contents/docs/pull_request_template.md?ref=main)\n"
                "      printf '{}\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "    repos/acme/widget/contents/.github/PULL_REQUEST_TEMPLATE?ref=main)\n"
                "      printf '[{\"type\":\"file\",\"path\":\".github/PULL_REQUEST_TEMPLATE/a.md\"},{\"type\":\"file\",\"path\":\".github/PULL_REQUEST_TEMPLATE/B.MD\"},{\"type\":\"file\",\"path\":\".github/PULL_REQUEST_TEMPLATE/a.md\"},{\"type\":\"file\",\"path\":\".github/PULL_REQUEST_TEMPLATE/not.txt\"}]\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "    repos/acme/widget/contents/PULL_REQUEST_TEMPLATE?ref=main)\n"
                "      printf '[{\"type\":\"file\",\"path\":\"PULL_REQUEST_TEMPLATE/root.md\"}]\\n'\n"
                "      exit 0\n"
                "      ;;\n"
                "    repos/acme/widget/contents/docs/PULL_REQUEST_TEMPLATE?ref=main)\n"
                "      printf '[{\"type\":\"file\",\"path\":\"docs/PULL_REQUEST_TEMPLATE/doc.md\"}]\\n'\n"
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
                [
                    "bash",
                    str(SCRIPT),
                    "--repo",
                    "acme/widget",
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                env=env,
            )

            payload = json.loads(proc.stdout)
            ids = [entry["id"] for entry in payload["templates"]]
            self.assertEqual(ids, sorted(set(ids)))
            self.assertIn("remote:.github/PULL_REQUEST_TEMPLATE.md", ids)
            self.assertIn("remote:PULL_REQUEST_TEMPLATE.md", ids)
            self.assertIn("remote:docs/PULL_REQUEST_TEMPLATE.md", ids)
            self.assertIn("remote:.github/PULL_REQUEST_TEMPLATE/a.md", ids)
            self.assertIn("remote:.github/PULL_REQUEST_TEMPLATE/B.MD", ids)
            self.assertIn("remote:PULL_REQUEST_TEMPLATE/root.md", ids)
            self.assertIn("remote:docs/PULL_REQUEST_TEMPLATE/doc.md", ids)
            self.assertNotIn("remote:.github/PULL_REQUEST_TEMPLATE/not.txt", ids)

    def test_extracts_uppercase_template_by_id(self):
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
                "    repos/acme/widget/contents/.github/PULL_REQUEST_TEMPLATE.md?ref=main)\n"
                "      printf '{\"type\":\"file\",\"encoding\":\"base64\",\"content\":\"IyBVUFBFUiBURU1QTEFURQo=\"}\\n'\n"
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
                [
                    "bash",
                    str(SCRIPT),
                    "--repo",
                    "acme/widget",
                    "--template-id",
                    "remote:.github/PULL_REQUEST_TEMPLATE.md",
                ],
                cwd=ROOT,
                env=env,
            )

            self.assertEqual(proc.stdout, "# UPPER TEMPLATE\n")


if __name__ == "__main__":
    unittest.main()
