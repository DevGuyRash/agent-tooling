from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import tempfile
import time
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

def raw_ship_state_path(repo: Path) -> Path:
    proc = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=repo)
    return Path(proc.stdout.strip()) / "gitops-workflow" / "ship-state.json"


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

    def write_fake_git_push_success_without_remote_update(self, bin_dir: Path) -> Path:
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        fake = bin_dir / "git"
        fake.write_text(
            '#!/usr/bin/env python3\nimport os\nimport sys\n\nREAL_GIT = {real_git!r}\nargs = sys.argv[1:]\nif "push" in args and "--dry-run" not in args:\n    raise SystemExit(0)\nos.execv(REAL_GIT, [REAL_GIT, *args])\n'.format(real_git=real_git),
            encoding="utf-8",
        )
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return fake

    def write_fake_git_push_success_with_auth_error_without_remote_update(self, bin_dir: Path) -> Path:
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        fake = bin_dir / "git"
        fake.write_text(
            '#!/usr/bin/env python3\nimport os\nimport sys\n\nREAL_GIT = {real_git!r}\nargs = sys.argv[1:]\nif "push" in args and "--dry-run" not in args:\n    sys.stderr.write("sign_and_send_pubkey: signing failed for RSA \\"/home/test/.ssh/id_rsa\\" from agent: agent refused operation\\n")\n    sys.stderr.write("git@github.com: Permission denied (publickey).\\n")\n    sys.stderr.write("fatal: Could not read from remote repository.\\n")\n    raise SystemExit(0)\nos.execv(REAL_GIT, [REAL_GIT, *args])\n'.format(real_git=real_git),
            encoding="utf-8",
        )
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return fake

    def write_fake_git_commit_signing_failure(self, bin_dir: Path, log_file: Path) -> Path:
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        fake = bin_dir / "git"
        fake.write_text(
            '#!/usr/bin/env python3\nimport json\nimport os\nimport sys\n\nREAL_GIT = {real_git!r}\nLOG_FILE = {log_file!r}\nargs = sys.argv[1:]\nwith open(LOG_FILE, "a", encoding="utf-8") as handle:\n    handle.write(json.dumps(args) + "\\n")\nif "commit" in args and "--only" in args:\n    if "commit.gpgsign=false" in args:\n        os.execv(REAL_GIT, [REAL_GIT, *args])\n    sys.stderr.write("error: gpg failed to sign the data\\nfatal: failed to write commit object\\n")\n    raise SystemExit(1)\nos.execv(REAL_GIT, [REAL_GIT, *args])\n'.format(real_git=real_git, log_file=str(log_file)),
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
    def test_ship_raw_agent_orchestration_completes_after_apply(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            work = Path(temp_dir) / "work"
            clone = Path(temp_dir) / "clone"
            plan_path = Path(temp_dir) / "agent-plan.json"

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
            run(["git", "config", "commit.gpgsign", "false"], cwd=clone)
            run(["git", "config", "tag.gpgsign", "false"], cwd=clone)
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
            self.assertFalse(payload["completed"])
            self.assertTrue(payload["agent_handoff_required"])
            self.assertEqual(payload["agent_handoff_kind"], "commit-apply")
            stages = {item["stage"]: item for item in payload["results"]}
            self.assertIn("scope", stages)
            self.assertIn("batch_plan", stages)
            self.assertIn("agent_handoff", stages)
            self.assertNotIn("batch_commit", stages)
            self.assertNotIn("push", stages)
            self.assertEqual(stages["batch_plan"]["details"]["status"], "planned")
            self.assertEqual(stages["batch_plan"]["details"]["repos"][0]["changed_paths"], ["README.md"])
            self.assertFalse(stages["agent_handoff"]["details"]["user_prompt_required"])
            self.assertEqual(
                run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip(),
                run(["git", "rev-parse", "refs/remotes/origin/main"], cwd=clone).stdout.strip(),
            )

            plan_path.write_text(
                json.dumps(
                    {
                        "commits": [
                            {
                                "repo": str(clone),
                                "type": "docs",
                                "subject": "update gitops workflow guidance",
                                "bullets": [
                                    "switch commit batching defaults to agent-authored plans",
                                    "keep raw workflows internal-handoff driven instead of deterministic by default",
                                ],
                                "paths": ["README.md"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            apply_proc = run(
                ["python3", str(SCRIPTS_DIR / "batch-commit.py"), "apply", "--plan", str(plan_path), "--mode", "raw", "--json"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(apply_proc.returncode, 0, apply_proc.stdout + apply_proc.stderr)

            final_proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "raw", "--json"],
                cwd=clone,
                env=env,
                check=False,
            )
            self.assertEqual(final_proc.returncode, 0, final_proc.stdout + final_proc.stderr)
            final_payload = json.loads(final_proc.stdout)
            self.assertTrue(final_payload["continued"])
            self.assertTrue(final_payload["completed"])
            self.assertFalse(final_payload["agent_handoff_required"])
            final_stages = {item["stage"]: item for item in final_payload["results"]}
            self.assertIn("sync", final_stages)
            self.assertNotIn("push", final_stages)
            self.assertEqual(final_stages["sync"]["status"], "ok")
            self.assertEqual(final_stages["sync"]["details"]["status"], "pushed")
            self.assertEqual(final_stages["sync"]["details"]["push_action"], "push")
            self.assertTrue(final_stages["sync"]["details"]["push_verified"])
            self.assertNotIn("batch_plan", final_stages)
            commit_body = run(["git", "log", "-1", "--pretty=%B"], cwd=clone).stdout
            self.assertIn("docs: update gitops workflow guidance", commit_body)
            self.assertIn("- switch commit batching defaults to agent-authored plans", commit_body)
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
            push_items = [item for item in payload["results"] if item["stage"] == "push"]
            readiness_items = [item for item in payload["results"] if item["stage"] == "readiness"]
            self.assertEqual(len(pr_items), 1)
            self.assertEqual(len(push_items), 1)
            self.assertEqual(len(readiness_items), 1)
            self.assertIn("existing PR #7", pr_items[0]["note"])
            self.assertIn("details", push_items[0])
            self.assertFalse(push_items[0]["details"]["manual_bypass_available"])
            self.assertEqual(readiness_items[0]["status"], "ok")
            self.assertEqual(readiness_items[0]["details"]["readiness"]["status"], "ready")
            calls = log_file.read_text(encoding="utf-8")
            self.assertIn("pr view --json number,url,isDraft,baseRefName,headRefName,title", calls)
            self.assertIn("pr checks 7 --required --json", calls)
            self.assertIn("api graphql", calls)
            self.assertNotIn("pr create", calls)

    def test_ship_sync_runs_sync_only_and_preserves_dirty_tree(self):
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
            run(["git", "config", "commit.gpgsign", "false"], cwd=clone)
            run(["git", "config", "tag.gpgsign", "false"], cwd=clone)

            (work / "README.md").write_text("base\nremote\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=work)
            run(["git", "commit", "-m", "feat: remote advance"], cwd=work)
            run(["git", "push"], cwd=work)

            (clone / "README.md").write_text("base\nlocal\n", encoding="utf-8")

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "sync", "--json"],
                cwd=clone,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["mode"], "sync")
            self.assertEqual(payload["stop"], "sync")
            self.assertTrue(payload["continued"])
            stages = payload["results"]
            self.assertEqual([item["stage"] for item in stages], ["preflight", "scope", "sync"])
            self.assertEqual(stages[1]["status"], "ok")
            self.assertTrue(stages[1]["details"]["requires_agent_confirmation"] is False)
            self.assertEqual(stages[2]["status"], "ok")
            self.assertEqual(stages[2]["details"]["status"], "synced-with-fallback")
            self.assertEqual(stages[2]["details"]["restore_action"], "snapshot-fallback")
            self.assertEqual(
                run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=clone).stdout.strip(),
                "main",
            )
            self.assertEqual(run(["git", "stash", "list"], cwd=clone).stdout.strip(), "")
            content = (clone / "README.md").read_text(encoding="utf-8")
            self.assertIn("remote", content)
            self.assertIn("local", content)
            self.assertNotIn("batch_commit", {item["stage"] for item in stages})
            self.assertNotIn("push", {item["stage"] for item in stages})
            self.assertNotIn("pr", {item["stage"] for item in stages})

    def test_sync_raw_streams_push_hook_progress_to_stderr(self):
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
            run(["git", "config", "commit.gpgsign", "false"], cwd=clone)
            run(["git", "config", "tag.gpgsign", "false"], cwd=clone)
            (clone / "README.md").write_text("base\nlocal\n", encoding="utf-8")
            run(["git", "commit", "-am", "docs: local change\n\n- keep a local commit ready to push\n"], cwd=clone)

            hook = clone / ".git" / "hooks" / "pre-push"
            hook.write_text(
                "#!/usr/bin/env sh\n"
                "set -eu\n"
                "echo 'hook: push progress visible' >&2\n",
                encoding="utf-8",
            )
            hook.chmod(hook.stat().st_mode | stat.S_IXUSR)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "sync-raw.sh"), "--json"],
                cwd=clone,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["results"][0]["status"], "pushed")
            self.assertIn("hook: push progress visible", proc.stderr)

    def test_ship_raw_default_does_not_start_pre_push_hook_before_agent_plan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            repo = Path(temp_dir) / "repo"
            marker = Path(temp_dir) / "hook-started"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            repo.mkdir()
            self.init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            run(["git", "remote", "add", "origin", str(origin)], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            run(["git", "push", "-u", "origin", "main"], cwd=repo)
            (repo / "README.md").write_text("base\ninterrupted\n", encoding="utf-8")

            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            fake_gitleaks = self.write_fake_gitleaks(fake_bin)
            env = os.environ.copy()
            env["GITLEAKS_BIN"] = str(fake_gitleaks)
            env["SENSITIVE_SCAN_DISABLE_UPDATE"] = "1"

            hook = repo / ".git" / "hooks" / "pre-push"
            hook.write_text(
                "#!/usr/bin/env sh\n"
                "set -eu\n"
                f"echo started > {json.dumps(str(marker))}\n"
                "echo 'hook: waiting for termination' >&2\n"
                "while :; do sleep 1; done\n",
                encoding="utf-8",
            )
            hook.chmod(hook.stat().st_mode | stat.S_IXUSR)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "raw", "--json"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["continued"])
            self.assertFalse(payload["completed"])
            self.assertTrue(payload["agent_handoff_required"])
            self.assertFalse(marker.exists(), "pre-push hook should not run before the agent applies the commit plan")
            stages = {item["stage"]: item for item in payload["results"]}
            self.assertIn("batch_plan", stages)
            self.assertIn("agent_handoff", stages)
            self.assertNotIn("batch_commit", stages)

    def test_ship_raw_fallback_deterministic_publishes_after_opt_in(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            work = Path(temp_dir) / "work"
            clone = Path(temp_dir) / "clone"
            hook_log = Path(temp_dir) / "push-hook.log"

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
            run(["git", "config", "commit.gpgsign", "false"], cwd=clone)
            run(["git", "config", "tag.gpgsign", "false"], cwd=clone)
            run(["git", "checkout", "-b", "feat/raw"], cwd=clone)
            run(["git", "push", "-u", "origin", "feat/raw"], cwd=clone)
            (clone / "existing.txt").write_text("ahead\n", encoding="utf-8")
            run(["git", "add", "existing.txt"], cwd=clone)
            run(["git", "commit", "-m", "feat: existing ahead commit"], cwd=clone)
            (clone / "README.md").write_text("base\ndirty\n", encoding="utf-8")

            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            fake_gitleaks = self.write_fake_gitleaks(fake_bin)
            env = os.environ.copy()
            env["GITLEAKS_BIN"] = str(fake_gitleaks)
            env["SENSITIVE_SCAN_DISABLE_UPDATE"] = "1"

            hook = clone / ".git" / "hooks" / "pre-push"
            hook.write_text(
                "#!/usr/bin/env sh\n"
                "set -eu\n"
                f"printf 'hook\\n' >> {json.dumps(str(hook_log))}\n",
                encoding="utf-8",
            )
            hook.chmod(hook.stat().st_mode | stat.S_IXUSR)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "raw", "--fallback-deterministic", "--json"],
                cwd=clone,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["continued"])
            self.assertIn("batch_commit", {item["stage"] for item in payload["results"]})
            sync_items = [item for item in payload["results"] if item["stage"] == "sync"]
            self.assertEqual(sync_items[0]["details"]["push_action"], "deferred")
            self.assertIn(sync_items[-1]["details"]["status"], {"published", "rebased-and-pushed", "pulled-and-pushed", "pushed"})
            self.assertEqual(hook_log.read_text(encoding="utf-8").splitlines(), ["hook"])
            self.assertEqual(
                run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip(),
                run(["git", "--git-dir", str(origin), "rev-parse", "refs/heads/feat/raw"], cwd=Path(temp_dir)).stdout.strip(),
            )

    def test_ship_raw_stops_before_pr_readiness_when_dirty_work_needs_agent_plan(self):
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
            self.assertTrue(payload["continued"])
            self.assertFalse(payload["completed"])
            self.assertTrue(payload["agent_handoff_required"])
            stages = {item["stage"]: item for item in payload["results"]}
            self.assertIn("batch_plan", stages)
            self.assertIn("agent_handoff", stages)
            self.assertNotIn("pr", stages)
            self.assertNotIn("readiness", stages)
            self.assertFalse(log_file.exists())

    def test_ship_raw_fallback_surfaces_unsigned_retry_helper_after_commit_signing_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            repo = Path(temp_dir) / "repo"
            log_file = Path(temp_dir) / "git.log"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            repo.mkdir()
            self.init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            run(["git", "remote", "add", "origin", str(origin)], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            run(["git", "push", "-u", "origin", "main"], cwd=repo)
            run(["git", "checkout", "-b", "feat/raw"], cwd=repo)
            run(["git", "push", "-u", "origin", "feat/raw"], cwd=repo)
            (repo / "README.md").write_text("base\nraw\n", encoding="utf-8")

            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            self.write_fake_git_commit_signing_failure(fake_bin, log_file)
            fake_gitleaks = self.write_fake_gitleaks(fake_bin)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["GITLEAKS_BIN"] = str(fake_gitleaks)
            env["SENSITIVE_SCAN_DISABLE_UPDATE"] = "1"

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "raw", "--fallback-deterministic", "--json"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertFalse(payload["continued"])
            self.assertFalse(payload["completed"])
            stages = {item["stage"]: item for item in payload["results"]}
            self.assertEqual(stages["batch_commit"]["status"], "blocked")
            self.assertEqual(stages["batch_commit"]["details"]["failure_class"], "commit-signing-unavailable")
            self.assertTrue(stages["batch_commit"]["details"]["unsigned_retry_available"])
            self.assertFalse(stages["batch_commit"]["details"]["unsigned_retry_enabled"])
            self.assertIn("GITOPS_ALLOW_UNSIGNED_COMMIT_RETRY=1", stages["batch_commit"]["details"]["helper_text"])
            self.assertNotIn("pr", stages)
            log_lines = log_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(sum('"commit"' in line and '"--only"' in line for line in log_lines), 1)

    def test_ship_raw_fallback_blocks_when_publish_verification_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            repo = Path(temp_dir) / "repo"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            repo.mkdir()
            self.init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            run(["git", "remote", "add", "origin", str(origin)], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            run(["git", "push", "-u", "origin", "main"], cwd=repo)
            run(["git", "checkout", "-b", "feat/raw"], cwd=repo)
            run(["git", "push", "-u", "origin", "feat/raw"], cwd=repo)
            (repo / "README.md").write_text("base\nraw\n", encoding="utf-8")

            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            self.write_fake_git_push_success_without_remote_update(fake_bin)
            fake_gitleaks = self.write_fake_gitleaks(fake_bin)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["GITLEAKS_BIN"] = str(fake_gitleaks)
            env["SENSITIVE_SCAN_DISABLE_UPDATE"] = "1"

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "raw", "--fallback-deterministic", "--json"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertFalse(payload["continued"])
            self.assertFalse(payload["completed"])
            sync_items = [item for item in payload["results"] if item["stage"] == "sync"]
            self.assertEqual(sync_items[-1]["status"], "blocked")
            self.assertFalse(sync_items[-1]["details"]["push_verified"])
            self.assertEqual(sync_items[-1]["details"]["push_verification_transport_used"], "other")
            self.assertIn("instead of local HEAD", sync_items[-1]["details"]["push_verification_note"])
            self.assertFalse(sync_items[-1]["details"]["manual_bypass_available"])
            self.assertEqual(
                run(["git", "--git-dir", str(origin), "rev-parse", "refs/heads/feat/raw"], cwd=Path(temp_dir)).stdout.strip(),
                run(["git", "rev-parse", "refs/remotes/origin/feat/raw"], cwd=repo).stdout.strip(),
            )

    def test_ship_raw_fallback_surfaces_manual_bypass_when_publish_logs_ssh_auth_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            repo = Path(temp_dir) / "repo"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            repo.mkdir()
            self.init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            run(["git", "remote", "add", "origin", str(origin)], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            run(["git", "push", "-u", "origin", "main"], cwd=repo)
            run(["git", "checkout", "-b", "feat/raw"], cwd=repo)
            run(["git", "push", "-u", "origin", "feat/raw"], cwd=repo)
            run(["git", "remote", "set-url", "--push", "origin", "git@github.com:example/example.git"], cwd=repo)
            (repo / "README.md").write_text("base\nraw\n", encoding="utf-8")

            fake_bin = Path(temp_dir) / "bin"
            fake_bin.mkdir()
            self.write_fake_git_push_success_with_auth_error_without_remote_update(fake_bin)
            fake_gitleaks = self.write_fake_gitleaks(fake_bin)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["GITLEAKS_BIN"] = str(fake_gitleaks)
            env["SENSITIVE_SCAN_DISABLE_UPDATE"] = "1"

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "raw", "--fallback-deterministic", "--json"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertFalse(payload["completed"])
            sync_items = [item for item in payload["results"] if item["stage"] == "sync"]
            self.assertEqual(sync_items[-1]["status"], "blocked")
            self.assertTrue(sync_items[-1]["details"]["manual_bypass_available"])
            self.assertEqual(sync_items[-1]["details"]["manual_bypass_reason"], "ssh-auth-unavailable")
            self.assertEqual(sync_items[-1]["details"]["manual_bypass_transport"], "https")
            self.assertTrue(sync_items[-1]["details"]["manual_bypass_skips_hooks"])
            self.assertIn("push --no-verify", sync_items[-1]["details"]["manual_bypass_command"])

    def test_ship_raw_pushes_existing_local_commit_when_repo_is_already_clean(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            repo = Path(temp_dir) / "repo"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            repo.mkdir()
            self.init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            run(["git", "remote", "add", "origin", str(origin)], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            run(["git", "push", "-u", "origin", "main"], cwd=repo)

            (repo / "README.md").write_text("base\nresume\n", encoding="utf-8")
            run(
                ["git", "commit", "-am", "docs: resume pending raw ship\n\n- keep the local raw ship commit intact\n"],
                cwd=repo,
            )
            head = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ship.sh"), "raw", "--json"],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["continued"])
            stages = {item["stage"]: item for item in payload["results"]}
            self.assertNotIn("batch_plan", stages)
            self.assertNotIn("batch_commit", stages)
            self.assertNotIn("next_action", stages)
            self.assertEqual(
                run(["git", "--git-dir", str(origin), "rev-parse", "refs/heads/main"], cwd=Path(temp_dir)).stdout.strip(),
                head,
            )

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
            self.assertFalse(payload["completed"])
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
            run(["git", "config", "commit.gpgsign", "false"], cwd=child_checkout)
            run(["git", "config", "tag.gpgsign", "false"], cwd=child_checkout)
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
