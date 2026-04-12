from __future__ import annotations

import json
import os
import shutil
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


class GitOpsScriptTestCase(unittest.TestCase):
    def init_repo(self, repo: Path):
        run(["git", "init"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "commit.gpgsign", "false"], cwd=repo)
        run(["git", "config", "tag.gpgsign", "false"], cwd=repo)

    def write_fake_gitleaks(self, bin_dir: Path) -> Path:
        fake = bin_dir / "gitleaks"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ \"${1:-}\" == \"version\" ]]; then\n"
            "  echo 'gitleaks version 8.30.0'\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${2:-}\" == \"--help\" || \"${1:-}\" == \"--help\" ]]; then\n"
            "  exit 0\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return fake

    def write_fake_gh(self, bin_dir: Path) -> Path:
        fake = bin_dir / "gh"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "[[ -n \"${FAKE_LOG:-}\" ]] && echo \"$*\" >> \"${FAKE_LOG}\"\n"
            "if [[ \"${1:-}\" == \"repo\" && \"${2:-}\" == \"view\" ]]; then\n"
            "  echo \"${FAKE_REPO_SLUG:-acme/widget}\"\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == \"pr\" && \"${2:-}\" == \"view\" ]]; then\n"
            "  if [[ \"${FAKE_PR_EXISTS:-true}\" != \"true\" ]]; then\n"
            "    echo 'no pull request found' >&2\n"
            "    exit 1\n"
            "  fi\n"
            "  python3 - <<'PY'\n"
            "import json, os\n"
            "payload = {\n"
            "    'number': int(os.environ.get('FAKE_PR_NUMBER', '7')),\n"
            "    'url': os.environ.get('FAKE_PR_URL', 'https://example.test/pr/7'),\n"
            "    'isDraft': os.environ.get('FAKE_PR_IS_DRAFT', 'true') == 'true',\n"
            "    'baseRefName': os.environ.get('FAKE_PR_BASE', 'main'),\n"
            "    'headRefName': os.environ.get('FAKE_PR_HEAD', 'feat/existing'),\n"
            "    'title': os.environ.get('FAKE_PR_TITLE', 'feat: existing'),\n"
            "}\n"
            "print(json.dumps(payload))\n"
            "PY\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == \"pr\" && \"${2:-}\" == \"checks\" ]]; then\n"
            "  printf '%s\\n' \"${FAKE_CHECKS_JSON:-[{\\\"bucket\\\":\\\"pass\\\",\\\"completedAt\\\":null,\\\"description\\\":\\\"\\\",\\\"event\\\":\\\"push\\\",\\\"link\\\":\\\"https://example.test/check/1\\\",\\\"name\\\":\\\"ci\\\",\\\"startedAt\\\":null,\\\"state\\\":\\\"SUCCESS\\\",\\\"workflow\\\":\\\"CI\\\"}]}\"\n"
            "  exit \"${FAKE_CHECKS_EXIT:-0}\"\n"
            "fi\n"
            "if [[ \"${1:-}\" == \"api\" && \"${2:-}\" == \"graphql\" ]]; then\n"
            "  python3 - <<'PY'\n"
            "import json, os\n"
            "requested = []\n"
            "for reviewer in [x for x in os.environ.get('FAKE_REQUESTED_REVIEWERS', '').split(',') if x]:\n"
            "    requested.append({'requestedReviewer': {'__typename': 'User', 'login': reviewer}})\n"
            "latest_reviews = []\n"
            "review_state = os.environ.get('FAKE_LATEST_REVIEW_STATE', '')\n"
            "if review_state:\n"
            "    latest_reviews.append({'state': review_state, 'submittedAt': '2026-04-11T00:00:00Z', 'author': {'login': 'reviewer'}})\n"
            "threads = []\n"
            "for index in range(int(os.environ.get('FAKE_UNRESOLVED_THREADS', '0'))):\n"
            "    threads.append({\n"
            "        'id': f'THREAD{index + 1}',\n"
            "        'isResolved': False,\n"
            "        'comments': {'nodes': [{'author': {'login': 'reviewer'}, 'path': 'README.md', 'line': index + 1, 'url': f'https://example.test/thread/{index + 1}', 'body': 'needs change'}]},\n"
            "    })\n"
            "for index in range(int(os.environ.get('FAKE_RESOLVED_THREADS', '0'))):\n"
            "    threads.append({\n"
            "        'id': f'RTHREAD{index + 1}',\n"
            "        'isResolved': True,\n"
            "        'comments': {'nodes': [{'author': {'login': 'reviewer'}, 'path': 'README.md', 'line': index + 10, 'url': f'https://example.test/resolved/{index + 1}', 'body': 'resolved'}]},\n"
            "    })\n"
            "payload = {\n"
            "    'data': {\n"
            "        'repository': {\n"
            "            'pullRequest': {\n"
            "                'number': int(os.environ.get('FAKE_PR_NUMBER', '7')),\n"
            "                'title': os.environ.get('FAKE_PR_TITLE', 'feat: existing'),\n"
            "                'url': os.environ.get('FAKE_PR_URL', 'https://example.test/pr/7'),\n"
            "                'state': 'OPEN',\n"
            "                'isDraft': os.environ.get('FAKE_PR_IS_DRAFT', 'true') == 'true',\n"
            "                'baseRefName': os.environ.get('FAKE_PR_BASE', 'main'),\n"
            "                'headRefName': os.environ.get('FAKE_PR_HEAD', 'feat/existing'),\n"
            "                'reviewDecision': os.environ.get('FAKE_REVIEW_DECISION', 'REVIEW_REQUIRED'),\n"
            "                'mergeable': os.environ.get('FAKE_MERGEABLE', 'MERGEABLE'),\n"
            "                'mergeStateStatus': os.environ.get('FAKE_MERGE_STATE_STATUS', 'CLEAN'),\n"
            "                'reviewRequests': {'nodes': requested},\n"
            "                'latestReviews': {'nodes': latest_reviews},\n"
            "                'reviewThreads': {'pageInfo': {'hasNextPage': False, 'endCursor': None}, 'nodes': threads},\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
            "print(json.dumps(payload))\n"
            "PY\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == \"pr\" && \"${2:-}\" == \"ready\" ]]; then\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == \"pr\" && \"${2:-}\" == \"create\" ]]; then\n"
            "  echo 'unexpected pr create' >&2\n"
            "  exit 1\n"
            "fi\n"
            "echo \"unexpected gh command: $*\" >&2\n"
            "exit 1\n",
            encoding="utf-8",
        )
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return fake

    def ready_env(self, temp_dir: str, *, include_gitleaks: bool = False) -> tuple[dict[str, str], Path]:
        fake_bin = Path(temp_dir) / "bin"
        fake_bin.mkdir()
        fake_gh = self.write_fake_gh(fake_bin)
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        env["FAKE_REPO_SLUG"] = "acme/widget"
        env["FAKE_PR_EXISTS"] = "true"
        env["FAKE_PR_IS_DRAFT"] = "true"
        env["FAKE_REVIEW_DECISION"] = "REVIEW_REQUIRED"
        env["FAKE_MERGEABLE"] = "MERGEABLE"
        env["FAKE_MERGE_STATE_STATUS"] = "CLEAN"
        env["FAKE_UNRESOLVED_THREADS"] = "0"
        env["FAKE_RESOLVED_THREADS"] = "0"
        env["FAKE_CHECKS_JSON"] = json.dumps(
            [
                {
                    "bucket": "pass",
                    "completedAt": None,
                    "description": "",
                    "event": "push",
                    "link": "https://example.test/check/1",
                    "name": "ci",
                    "startedAt": None,
                    "state": "SUCCESS",
                    "workflow": "CI",
                }
            ]
        )
        env["FAKE_CHECKS_EXIT"] = "0"
        if include_gitleaks:
            fake_gitleaks = self.write_fake_gitleaks(fake_bin)
            env["GITLEAKS_BIN"] = str(fake_gitleaks)
            env["SENSITIVE_SCAN_DISABLE_UPDATE"] = "1"
        return env, fake_gh


class StartBranchFallbackTests(GitOpsScriptTestCase):
    def test_start_branch_reports_worktree_no_checkout_when_checkout_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self.init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)

            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            real_git = shutil.which("git")
            self.assertIsNotNone(real_git)
            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f"real_git={real_git!r}\n"
                "args=\"$*\"\n"
                "if [[ \"$args\" == *\"worktree add -b feat/fallback-mode\"* && \"$args\" != *\"--no-checkout\"* ]]; then\n"
                "  echo 'fatal: smudge filter blocked checkout' >&2\n"
                "  exit 1\n"
                "fi\n"
                "exec \"$real_git\" \"$@\"\n",
                encoding="utf-8",
            )
            fake_git.chmod(fake_git.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "start-branch.sh"),
                    "feat",
                    "fallback-mode",
                    "--base",
                    "main",
                    "--json",
                ],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["mode"], "worktree-no-checkout")
            self.assertTrue(Path(payload["path"]).exists())
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip(), "main")


class ShipWorkflowTests(GitOpsScriptTestCase):
    def test_ship_raw_syncs_commits_and_pushes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            work = Path(temp_dir) / "work"
            clone = Path(temp_dir) / "clone"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            work.mkdir()
            self.init_repo(work)
            run(["git", "checkout", "-b", "main"], cwd=work)
            run(["git", "remote", "add", "origin", str(origin)], cwd=work)
            (work / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=work)
            run(["git", "commit", "-m", "chore: base"], cwd=work)
            run(["git", "push", "-u", "origin", "main"], cwd=work)

            run(["git", "clone", str(origin), str(clone)], cwd=Path(temp_dir))
            run(["git", "config", "user.name", "Test User"], cwd=clone)
            run(["git", "config", "user.email", "test@example.com"], cwd=clone)
            (clone / "README.md").write_text("base\nlocal\n", encoding="utf-8")

            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            fake_gitleaks = self.write_fake_gitleaks(fake_bin)
            env = os.environ.copy()
            env["GITLEAKS_BIN"] = str(fake_gitleaks)
            env["SENSITIVE_SCAN_DISABLE_UPDATE"] = "1"

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "raw", "--json"],
                cwd=clone,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["mode"], "raw")
            self.assertTrue(payload["continued"])
            stages = {item["stage"]: item for item in payload["results"]}
            self.assertIn("batch_commit", stages)
            self.assertIn("push", stages)
            commit_body = run(["git", "log", "-1", "--pretty=%B"], cwd=clone).stdout
            self.assertIn("docs: update documentation", commit_body)
            self.assertIn("- refresh the documented workflow", commit_body)
            self.assertEqual(
                run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip(),
                run(["git", "--git-dir", str(origin), "rev-parse", "refs/heads/main"], cwd=Path(temp_dir)).stdout.strip(),
            )

    def test_ship_reuses_existing_pr_without_creating_duplicate_and_records_readiness(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            repo = Path(temp_dir) / "repo"
            log_file = Path(temp_dir) / "gh.log"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            repo.mkdir()
            self.init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            run(["git", "remote", "add", "origin", str(origin)], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            run(["git", "push", "-u", "origin", "main"], cwd=repo)
            run(["git", "checkout", "-b", "feat/existing"], cwd=repo)
            run(["git", "push", "-u", "origin", "feat/existing"], cwd=repo)

            env, _ = self.ready_env(temp_dir)
            env["FAKE_LOG"] = str(log_file)
            env["FAKE_PR_HEAD"] = "feat/existing"
            env["FAKE_PR_TITLE"] = "feat: existing"

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "--json"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            pr_items = [item for item in payload["results"] if item["stage"] == "pr"]
            readiness_items = [item for item in payload["results"] if item["stage"] == "readiness"]
            self.assertEqual(len(pr_items), 1)
            self.assertEqual(len(readiness_items), 1)
            self.assertIn("existing PR #7", pr_items[0]["note"])
            self.assertEqual(readiness_items[0]["status"], "ok")
            self.assertEqual(readiness_items[0]["details"]["readiness"]["status"], "ready")
            calls = log_file.read_text(encoding="utf-8")
            self.assertIn("pr view --json number,url,isDraft,baseRefName,headRefName,title", calls)
            self.assertIn("pr checks 7 --required --json", calls)
            self.assertIn("api graphql", calls)
            self.assertNotIn("pr create", calls)

    def test_ship_raw_reports_pr_readiness_snapshot_when_pr_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            repo = Path(temp_dir) / "repo"
            log_file = Path(temp_dir) / "gh.log"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            repo.mkdir()
            self.init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            run(["git", "remote", "add", "origin", str(origin)], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            run(["git", "push", "-u", "origin", "main"], cwd=repo)
            run(["git", "checkout", "-b", "feat/existing"], cwd=repo)
            run(["git", "push", "-u", "origin", "feat/existing"], cwd=repo)
            (repo / "README.md").write_text("base\nraw\n", encoding="utf-8")

            env, _ = self.ready_env(temp_dir, include_gitleaks=True)
            env["FAKE_LOG"] = str(log_file)
            env["FAKE_PR_HEAD"] = "feat/existing"

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "raw", "--json"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            stages = {item["stage"]: item for item in payload["results"]}
            self.assertIn("pr", stages)
            self.assertIn("readiness", stages)
            self.assertEqual(stages["readiness"]["status"], "ok")
            self.assertEqual(stages["readiness"]["details"]["pr"]["head_branch"], "feat/existing")
            calls = log_file.read_text(encoding="utf-8")
            self.assertIn("pr checks 7 --required --json", calls)
            self.assertNotIn("pr create", calls)

    def test_ship_ready_audits_existing_pr_without_marking_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            repo = Path(temp_dir) / "repo"
            log_file = Path(temp_dir) / "gh.log"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            repo.mkdir()
            self.init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            run(["git", "remote", "add", "origin", str(origin)], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            run(["git", "push", "-u", "origin", "main"], cwd=repo)
            run(["git", "checkout", "-b", "feat/existing"], cwd=repo)
            run(["git", "push", "-u", "origin", "feat/existing"], cwd=repo)

            env, _ = self.ready_env(temp_dir)
            env["FAKE_LOG"] = str(log_file)
            env["FAKE_PR_HEAD"] = "feat/existing"

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "ready", "--json"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            stages = {item["stage"]: item for item in payload["results"]}
            self.assertIn("pr", stages)
            self.assertIn("readiness", stages)
            self.assertTrue(payload["continued"])
            calls = log_file.read_text(encoding="utf-8")
            self.assertNotIn("pr create", calls)
            self.assertNotIn("pr ready", calls)

    def test_ship_ready_without_pr_reports_missing_pr_without_creating_one(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            repo = Path(temp_dir) / "repo"
            log_file = Path(temp_dir) / "gh.log"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            repo.mkdir()
            self.init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            run(["git", "remote", "add", "origin", str(origin)], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            run(["git", "push", "-u", "origin", "main"], cwd=repo)
            run(["git", "checkout", "-b", "feat/missing-pr"], cwd=repo)
            run(["git", "push", "-u", "origin", "feat/missing-pr"], cwd=repo)

            env, _ = self.ready_env(temp_dir)
            env["FAKE_LOG"] = str(log_file)
            env["FAKE_PR_EXISTS"] = "false"
            env["FAKE_PR_HEAD"] = "feat/missing-pr"

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "ready", "--json"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertFalse(payload["continued"])
            pr_item = next(item for item in payload["results"] if item["stage"] == "pr")
            self.assertEqual(pr_item["status"], "blocked")
            self.assertIn("ship ready audits an existing PR only", pr_item["note"])
            calls = log_file.read_text(encoding="utf-8")
            self.assertNotIn("pr create", calls)
            self.assertNotIn("pr ready", calls)


class MarkReadyWorkflowTests(GitOpsScriptTestCase):
    def test_pr_mark_ready_blocks_when_readiness_report_is_not_clear(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self.init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)

            env, _ = self.ready_env(temp_dir)
            log_file = Path(temp_dir) / "gh.log"
            env["FAKE_LOG"] = str(log_file)
            env["FAKE_UNRESOLVED_THREADS"] = "1"
            env["FAKE_CHECKS_JSON"] = json.dumps(
                [
                    {
                        "bucket": "pending",
                        "completedAt": None,
                        "description": "",
                        "event": "push",
                        "link": "https://example.test/check/1",
                        "name": "ci",
                        "startedAt": None,
                        "state": "PENDING",
                        "workflow": "CI",
                    }
                ]
            )

            proc = run(
                ["bash", str(SCRIPTS_DIR / "pr-mark-ready.sh"), "7", "--repo", "acme/widget"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
            self.assertIn("not safe to mark ready", proc.stderr)
            calls = log_file.read_text(encoding="utf-8")
            self.assertNotIn("pr ready 7 --repo acme/widget", calls)

    def test_pr_mark_ready_marks_ready_when_readiness_report_is_clear(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self.init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)

            env, _ = self.ready_env(temp_dir)
            log_file = Path(temp_dir) / "gh.log"
            env["FAKE_LOG"] = str(log_file)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "pr-mark-ready.sh"), "7", "--repo", "acme/widget"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            calls = log_file.read_text(encoding="utf-8")
            self.assertIn("pr ready 7 --repo acme/widget", calls)


class DoctorWorkflowTests(GitOpsScriptTestCase):
    def test_doctor_fix_reports_reconcile_actions_without_committing_parent_gitlinks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "parent"
            child_src = Path(temp_dir) / "child-src"
            child_origin = Path(temp_dir) / "child-origin.git"

            child_src.mkdir()
            self.init_repo(child_src)
            run(["git", "checkout", "-b", "main"], cwd=child_src)
            (child_src / "README.md").write_text("child\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=child_src)
            run(["git", "commit", "-m", "chore: child base"], cwd=child_src)
            run(["git", "init", "--bare", str(child_origin)], cwd=Path(temp_dir))
            run(["git", "remote", "add", "origin", str(child_origin)], cwd=child_src)
            run(["git", "push", "-u", "origin", "main"], cwd=child_src)

            parent.mkdir()
            self.init_repo(parent)
            run(["git", "checkout", "-b", "main"], cwd=parent)
            (parent / "README.md").write_text("parent\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=parent)
            run(["git", "commit", "-m", "chore: parent base"], cwd=parent)
            run(["git", "config", "protocol.file.allow", "always"], cwd=parent)
            run(["git", "-c", "protocol.file.allow=always", "submodule", "add", str(child_origin), "deps/child"], cwd=parent)
            run(["git", "commit", "-m", "chore: add submodule"], cwd=parent)

            child_checkout = parent / "deps" / "child"
            run(["git", "config", "user.name", "Test User"], cwd=child_checkout)
            run(["git", "config", "user.email", "test@example.com"], cwd=child_checkout)
            (child_checkout / "feature.txt").write_text("next\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=child_checkout)
            run(["git", "commit", "-m", "feat: advance child"], cwd=child_checkout)
            before_head = run(["git", "rev-parse", "HEAD"], cwd=parent).stdout.strip()

            proc = run(
                ["bash", str(SCRIPTS_DIR / "doctor.sh"), "fix", "--repo", str(parent), "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["mode"], "doctor-fix")
            self.assertTrue(payload["reconcile_actions"])
            parent_item = next(item for item in payload["results"] if item["repo"] == str(parent))
            self.assertTrue(parent_item["reconcile_actions"])
            self.assertEqual(before_head, run(["git", "rev-parse", "HEAD"], cwd=parent).stdout.strip())


if __name__ == "__main__":
    unittest.main()
