from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PR_CREATE_SCRIPT = ROOT / "scripts" / "pr-create.sh"


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


def commit_file(repo: Path, name: str, content: str, msg: str) -> None:
    f = repo / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    run(["git", "add", name], cwd=repo)
    run(["git", "commit", "-m", msg], cwd=repo)


class PrCreateScriptTests(unittest.TestCase):
    def test_help_outputs_stable_usage_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            proc = run(
                [
                    "bash",
                    str(PR_CREATE_SCRIPT),
                    "--help",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("Usage:", proc.stdout)
            self.assertIn("--title", proc.stdout)
            self.assertIn("--template-id", proc.stdout)

    def test_prefills_sections_from_git_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            commit_file(repo, "README.md", "base\n", "docs: base")
            run(["git", "checkout", "-b", "feat/demo"], cwd=repo)
            commit_file(repo, "skills/demo.txt", "change\n", "feat(demo): add sample change")

            proc = run(
                [
                    "bash",
                    str(PR_CREATE_SCRIPT),
                    "--title",
                    "feat(demo): add sample change",
                    "--base",
                    "main",
                    "--head",
                    "feat/demo",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            m = re.search(r"PR body file created:\s*(\S+)", proc.stdout)
            self.assertIsNotNone(m, proc.stdout)

            body_path = Path(m.group(1))
            body = body_path.read_text(encoding="utf-8")
            self.assertIn("# Summary", body)
            self.assertIn("This PR introduces changes from `feat/demo` into `main`", body)
            self.assertIn("# Changes", body)
            self.assertIn("- feat(demo): add sample change", body)
            self.assertIn("# Testing", body)
            self.assertIn("git diff --stat \"main...feat/demo\"", body)
            self.assertIn("# Reviewers / bots", body)
            self.assertIn("@codex", body)
            self.assertIn("/gemini review", body)

    def test_remote_template_content_suppresses_generated_fallback_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            fake_bin = tmp_path / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            commit_file(repo, "README.md", "base\n", "docs: base")
            run(["git", "checkout", "-b", "feat/demo"], cwd=repo)
            commit_file(repo, "skills/demo.txt", "change\n", "feat(demo): add sample change")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"repo\" && \"${2:-}\" == \"view\" ]]; then\n"
                "  if [[ \"$*\" == *\"defaultBranchRef\"* ]]; then\n"
                "    echo \"main\"\n"
                "  else\n"
                "    echo \"acme/widget\"\n"
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"api\" ]]; then\n"
                "  endpoint=\"${2:-}\"\n"
                "  case \"$endpoint\" in\n"
                "    repos/acme/widget/contents/.github/pull_request_template.md?ref=main)\n"
                "      echo '{\"type\":\"file\",\"encoding\":\"base64\",\"content\":\"IyBSZW1vdGUgVGVtcGxhdGUKCi0gZnJvbSByZXBvCg==\"}'\n"
                "      exit 0\n"
                "      ;;\n"
                "    repos/acme/widget/contents/.github/PULL_REQUEST_TEMPLATE?ref=main|repos/acme/widget/contents/PULL_REQUEST_TEMPLATE?ref=main|repos/acme/widget/contents/docs/PULL_REQUEST_TEMPLATE?ref=main)\n"
                "      echo '[]'\n"
                "      exit 0\n"
                "      ;;\n"
                "    repos/acme/widget/contents/*)\n"
                "      echo '{}'\n"
                "      exit 0\n"
                "      ;;\n"
                "  esac\n"
                "  echo '[]'\n"
                "  exit 0\n"
                "fi\n"
                "echo \"$*\" >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                [
                    "bash",
                    str(PR_CREATE_SCRIPT),
                    "--title",
                    "feat(demo): add sample change",
                    "--base",
                    "main",
                    "--head",
                    "feat/demo",
                ],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            m = re.search(r"PR body file created:\s*(\S+)", proc.stdout)
            self.assertIsNotNone(m, proc.stdout)
            body = Path(m.group(1)).read_text(encoding="utf-8")
            self.assertIn("Remote PR template source: acme/widget:.github/pull_request_template.md", body)
            self.assertIn("# Remote Template", body)
            self.assertIn("- from repo", body)
            self.assertNotIn("# Summary", body)
            self.assertNotIn("# Changes", body)
            self.assertNotIn("# Reviewers / bots", body)

    def test_fails_when_no_commits_between_base_and_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            commit_file(repo, "README.md", "base\n", "docs: base")

            proc = run(
                [
                    "bash",
                    str(PR_CREATE_SCRIPT),
                    "--title",
                    "docs: no-op",
                    "--base",
                    "main",
                    "--head",
                    "main",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("no commits between main and main", proc.stderr)

    def test_create_requires_force_create_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)
            commit_file(repo, "README.md", "base\n", "docs: base")
            run(["git", "checkout", "-b", "feat/demo"], cwd=repo)
            commit_file(repo, "skills/demo.txt", "change\n", "feat(demo): add sample change")

            proc = run(
                [
                    "bash",
                    str(PR_CREATE_SCRIPT),
                    "--title",
                    "feat(demo): add sample change",
                    "--base",
                    "main",
                    "--head",
                    "feat/demo",
                    "--create",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("--create requires --force-create", proc.stderr)

    def test_create_with_force_create_invokes_gh(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            fake_bin = tmp_path / "bin"
            gh_args = tmp_path / "gh-args.txt"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)

            init_repo(repo)
            commit_file(repo, "README.md", "base\n", "docs: base")
            run(["git", "checkout", "-b", "feat/demo"], cwd=repo)
            commit_file(repo, "skills/demo.txt", "change\n", "feat(demo): add sample change")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"repo\" && \"${2:-}\" == \"view\" ]]; then\n"
                "  if [[ \"$*\" == *\"defaultBranchRef\"* ]]; then\n"
                "    echo \"main\"\n"
                "  else\n"
                "    echo \"acme/widget\"\n"
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"api\" ]]; then\n"
                "  endpoint=\"${2:-}\"\n"
                "  if [[ \"$endpoint\" == *\"/labels?per_page=100&page=1\"* ]]; then\n"
                "    echo '[]'\n"
                "    exit 0\n"
                "  fi\n"
                "  if [[ \"$endpoint\" == *\"/contents/\"* ]]; then\n"
                "    echo '{}'\n"
                "    exit 0\n"
                "  fi\n"
                "  echo '[]'\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"pr\" && \"${2:-}\" == \"create\" ]]; then\n"
                "  echo \"$*\" > \"${GH_ARGS_FILE}\"\n"
                "  exit 0\n"
                "fi\n"
                "echo \"$*\" > \"${GH_ARGS_FILE}\"\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["GH_ARGS_FILE"] = str(gh_args)

            proc = run(
                [
                    "bash",
                    str(PR_CREATE_SCRIPT),
                    "--title",
                    "feat(demo): add sample change",
                    "--base",
                    "main",
                    "--head",
                    "feat/demo",
                    "--repo",
                    "acme/widget",
                    "--create",
                    "--force-create",
                    "--no-labels",
                ],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            args = gh_args.read_text(encoding="utf-8")
            self.assertIn("pr create", args)
            self.assertIn("--title feat(demo): add sample change", args)
            self.assertIn("--draft", args)

    def test_create_with_ready_omits_draft_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            fake_bin = tmp_path / "bin"
            gh_args = tmp_path / "gh-args.txt"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)

            init_repo(repo)
            commit_file(repo, "README.md", "base\n", "docs: base")
            run(["git", "checkout", "-b", "feat/demo"], cwd=repo)
            commit_file(repo, "skills/demo.txt", "change\n", "feat(demo): add sample change")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"repo\" && \"${2:-}\" == \"view\" ]]; then\n"
                "  if [[ \"$*\" == *\"defaultBranchRef\"* ]]; then\n"
                "    echo \"main\"\n"
                "  else\n"
                "    echo \"acme/widget\"\n"
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"api\" ]]; then\n"
                "  endpoint=\"${2:-}\"\n"
                "  if [[ \"$endpoint\" == *\"/labels?per_page=100&page=1\"* ]]; then\n"
                "    echo '[]'\n"
                "    exit 0\n"
                "  fi\n"
                "  if [[ \"$endpoint\" == *\"/contents/\"* ]]; then\n"
                "    echo '{}'\n"
                "    exit 0\n"
                "  fi\n"
                "  echo '[]'\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"pr\" && \"${2:-}\" == \"create\" ]]; then\n"
                "  echo \"$*\" > \"${GH_ARGS_FILE}\"\n"
                "  exit 0\n"
                "fi\n"
                "echo \"$*\" > \"${GH_ARGS_FILE}\"\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["GH_ARGS_FILE"] = str(gh_args)

            proc = run(
                [
                    "bash",
                    str(PR_CREATE_SCRIPT),
                    "--title",
                    "feat(demo): add sample change",
                    "--base",
                    "main",
                    "--head",
                    "feat/demo",
                    "--create",
                    "--force-create",
                    "--ready",
                    "--no-labels",
                ],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            args = gh_args.read_text(encoding="utf-8")
            self.assertIn("pr create", args)
            self.assertNotIn("--draft", args)

    def test_create_requires_label_selection_when_labels_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            fake_bin = tmp_path / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)

            init_repo(repo)
            commit_file(repo, "README.md", "base\n", "docs: base")
            run(["git", "checkout", "-b", "feat/demo"], cwd=repo)
            commit_file(repo, "skills/demo.txt", "change\n", "feat(demo): add sample change")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"repo\" && \"${2:-}\" == \"view\" ]]; then\n"
                "  if [[ \"$*\" == *\"defaultBranchRef\"* ]]; then\n"
                "    echo \"main\"\n"
                "  else\n"
                "    echo \"acme/widget\"\n"
                "  fi\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"api\" ]]; then\n"
                "  endpoint=\"${2:-}\"\n"
                "  if [[ \"$endpoint\" == *\"/labels?per_page=100&page=1\"* ]]; then\n"
                "    echo '[{\"name\":\"bug\",\"color\":\"ffffff\",\"description\":\"Bug fix\"}]'\n"
                "    exit 0\n"
                "  fi\n"
                "  if [[ \"$endpoint\" == *\"/labels?per_page=100&page=2\"* ]]; then\n"
                "    echo '[]'\n"
                "    exit 0\n"
                "  fi\n"
                "  if [[ \"$endpoint\" == *\"/contents/\"* ]]; then\n"
                "    echo '{}'\n"
                "    exit 0\n"
                "  fi\n"
                "  echo '[]'\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"pr\" && \"${2:-}\" == \"create\" ]]; then\n"
                "  echo \"unexpected create\" >&2\n"
                "  exit 1\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                [
                    "bash",
                    str(PR_CREATE_SCRIPT),
                    "--title",
                    "feat(demo): add sample change",
                    "--base",
                    "main",
                    "--head",
                    "feat/demo",
                    "--create",
                    "--force-create",
                ],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("Label selection is required before PR creation", proc.stdout)

    def test_changes_section_excludes_base_only_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            commit_file(repo, "README.md", "base\n", "docs: base")
            run(["git", "checkout", "-b", "feat/demo"], cwd=repo)
            commit_file(repo, "feature.txt", "feat\n", "feat(demo): branch-only change")
            run(["git", "checkout", "main"], cwd=repo)
            commit_file(repo, "main.txt", "main update\n", "chore(main): base-only change")
            run(["git", "checkout", "feat/demo"], cwd=repo)

            proc = run(
                [
                    "bash",
                    str(PR_CREATE_SCRIPT),
                    "--title",
                    "feat(demo): branch-only change",
                    "--base",
                    "main",
                    "--head",
                    "feat/demo",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            m = re.search(r"PR body file created:\s*(\S+)", proc.stdout)
            self.assertIsNotNone(m, proc.stdout)
            body = Path(m.group(1)).read_text(encoding="utf-8")
            self.assertIn("feat(demo): branch-only change", body)
            self.assertNotIn("chore(main): base-only change", body)

    def test_preview_command_escapes_malicious_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            commit_file(repo, "README.md", "base\n", "docs: base")
            run(["git", "checkout", "-b", "feat/demo"], cwd=repo)
            commit_file(repo, "feature.txt", "feat\n", "feat(demo): branch-only change")

            proc = run(
                [
                    "bash",
                    str(PR_CREATE_SCRIPT),
                    "--title",
                    'feat: ok"; echo PWNED; echo "',
                    "--base",
                    "main",
                    "--head",
                    "feat/demo",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("gh pr create --title ", proc.stdout)
            self.assertNotIn('gh pr create --title "feat: ok"; echo PWNED; echo ""', proc.stdout)
            self.assertIn("\\;\\ echo\\ PWNED\\;", proc.stdout)
            self.assertIn("--base main", proc.stdout)
            self.assertIn("--head feat/demo", proc.stdout)
            self.assertIn("--draft", proc.stdout)

    def test_preview_command_includes_selected_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            fake_bin = tmp_path / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            commit_file(repo, "README.md", "base\n", "docs: base")
            run(["git", "checkout", "-b", "feat/demo"], cwd=repo)
            commit_file(repo, "feature.txt", "feat\n", "feat(demo): branch-only change")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"api\" ]]; then\n"
                "  echo '{}'\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"repo\" && \"${2:-}\" == \"view\" ]]; then\n"
                "  echo \"acme/widget\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                [
                    "bash",
                    str(PR_CREATE_SCRIPT),
                    "--title",
                    "feat(demo): branch-only change",
                    "--base",
                    "main",
                    "--head",
                    "feat/demo",
                    "--repo",
                    "acme/widget",
                    "--label",
                    "bug",
                ],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("--base main", proc.stdout)
            self.assertIn("--head feat/demo", proc.stdout)
            self.assertIn("--repo acme/widget", proc.stdout)
            self.assertIn("--draft", proc.stdout)
            self.assertIn("--label bug", proc.stdout)

    def test_invalid_explicit_repo_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            fake_bin = tmp_path / "bin"
            repo.mkdir(parents=True, exist_ok=True)
            fake_bin.mkdir(parents=True, exist_ok=True)
            init_repo(repo)

            commit_file(repo, "README.md", "base\n", "docs: base")
            run(["git", "checkout", "-b", "feat/demo"], cwd=repo)
            commit_file(repo, "feature.txt", "feat\n", "feat(demo): branch-only change")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"repo\" && \"${2:-}\" == \"view\" ]]; then\n"
                "  echo \"acme/widget\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            fake_jq = fake_bin / "jq"
            fake_jq.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "cat\n",
                encoding="utf-8",
            )
            fake_jq.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                [
                    "bash",
                    str(PR_CREATE_SCRIPT),
                    "--title",
                    "feat(demo): test stderr passthrough",
                    "--base",
                    "main",
                    "--head",
                    "feat/demo",
                    "--repo",
                    "../meta",
                ],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("invalid --repo", proc.stderr)


if __name__ == "__main__":
    unittest.main()
