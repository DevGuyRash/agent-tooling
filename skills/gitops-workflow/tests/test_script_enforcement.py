from __future__ import annotations

import json
import os
import re
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


class ScriptSyntaxTests(unittest.TestCase):
    def test_shell_scripts_parse(self):
        targets = [
            SCRIPTS_DIR / "gitops-help.sh",
            SCRIPTS_DIR / "start-branch.sh",
            SCRIPTS_DIR / "finish-work.sh",
            SCRIPTS_DIR / "install-hooks.sh",
            SCRIPTS_DIR / "setup-security.sh",
            SCRIPTS_DIR / "gh-scope-check.sh",
            SCRIPTS_DIR / "ensure-worktree.sh",
            SCRIPTS_DIR / "reconcile-tree.sh",
            SCRIPTS_DIR / "recover-repo-state.sh",
            SCRIPTS_DIR / "repo-state.sh",
            SCRIPTS_DIR / "sensitive-scan.sh",
            SCRIPTS_DIR / "sync-raw.sh",
            SCRIPTS_DIR / "ship.sh",
            SCRIPTS_DIR / "doctor.sh",
            SCRIPTS_DIR / "pr-create.sh",
            SCRIPTS_DIR / "pr-update-body.sh",
            SCRIPTS_DIR / "pr-labels-list.sh",
            SCRIPTS_DIR / "pr-template-discover.sh",
            SCRIPTS_DIR / "issue-template-discover.sh",
            SCRIPTS_DIR / "issue-create.sh",
            SCRIPTS_DIR / "lib" / "common.sh",
            SCRIPTS_DIR / "lib" / "git-state.sh",
            SCRIPTS_DIR / "lib" / "router.sh",
            SCRIPTS_DIR / "pr-comment.sh",
            SCRIPTS_DIR / "pr-request-review.sh",
            SCRIPTS_DIR / "pr-mark-ready.sh",
            SCRIPTS_DIR / "pr-reply.sh",
            SCRIPTS_DIR / "pr-workflow.sh",
            SCRIPTS_DIR / "pr-merge-squash.sh",
            SCRIPTS_DIR / "governance-enforce.sh",
            SCRIPTS_DIR / "pr-unresolved-threads.sh",
            SCRIPTS_DIR / "pr-resolve-threads.sh",
        ]
        for target in targets:
            proc = run(["bash", "-n", str(target)], cwd=ROOT)
            self.assertEqual(proc.returncode, 0, f"bash -n failed for {target}\n{proc.stderr}")


class PythonScriptCompileTests(unittest.TestCase):
    def test_python_scripts_compile(self):
        targets = [
            SCRIPTS_DIR / "batch-commit.py",
            SCRIPTS_DIR / "commit-message.py",
            SCRIPTS_DIR / "pr-readiness-report.py",
            SCRIPTS_DIR / "lib" / "raw_ship_state.py",
        ]
        proc = run(["python3", "-m", "py_compile", *(str(target) for target in targets)], cwd=ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class PushTransportHelperTests(unittest.TestCase):
    def test_noninteractive_ssh_command_adds_connection_bounds(self):
        env = os.environ.copy()
        env["GIT_SSH_COMMAND"] = "ssh"
        proc = run(
            ["bash", "-lc", f"source {json.dumps(str(SCRIPTS_DIR / 'lib' / 'git-state.sh'))}; gitops_noninteractive_ssh_command"],
            cwd=ROOT,
            env=env,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("-oBatchMode=yes", proc.stdout)
        self.assertIn("-oConnectTimeout=20", proc.stdout)
        self.assertIn("-oConnectionAttempts=1", proc.stdout)


class BatchCommitSigningTests(unittest.TestCase):
    def _init_repo(self, repo: Path):
        run(["git", "init"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "commit.gpgsign", "false"], cwd=repo)
        run(["git", "config", "tag.gpgsign", "false"], cwd=repo)

    def _write_commit_signing_wrapper(self, temp_dir: Path, log_file: Path) -> Path:
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        wrapper = temp_dir / "git"
        wrapper.write_text(
            '#!/usr/bin/env python3\nimport json\nimport os\nimport sys\n\nREAL_GIT = {real_git!r}\nLOG_FILE = {log_file!r}\nargs = sys.argv[1:]\nwith open(LOG_FILE, "a", encoding="utf-8") as handle:\n    handle.write(json.dumps(args) + "\\n")\nif "commit" in args and "--only" in args:\n    if "commit.gpgsign=false" in args:\n        os.execv(REAL_GIT, [REAL_GIT, *args])\n    sys.stderr.write("error: gpg failed to sign the data\\nfatal: failed to write commit object\\n")\n    raise SystemExit(1)\nos.execv(REAL_GIT, [REAL_GIT, *args])\n'.format(real_git=real_git, log_file=str(log_file)),
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        return wrapper

    def test_batch_commit_reports_signing_failure_with_helper_when_unsigned_retry_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo = temp_path / "repo"
            fake_bin = temp_path / "bin"
            log_file = temp_path / "git.log"
            repo.mkdir()
            fake_bin.mkdir()
            self._init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            (repo / "README.md").write_text("base\nupdated\n", encoding="utf-8")
            self._write_commit_signing_wrapper(fake_bin, log_file)

            proc = run(
                ["python3", str(SCRIPTS_DIR / "batch-commit.py"), "--repo", str(repo), "--json"],
                cwd=ROOT,
                env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
                check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(payload["failure_class"], "commit-signing-unavailable")
            self.assertTrue(payload["unsigned_retry_available"])
            self.assertFalse(payload["unsigned_retry_enabled"])
            self.assertFalse(payload["unsigned_retry_used"])
            self.assertIn("GITOPS_ALLOW_UNSIGNED_COMMIT_RETRY=1", payload["helper_text"])
            self.assertEqual(payload["commits"], [])
            log_lines = log_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(sum('"commit"' in line and '"--only"' in line for line in log_lines), 1)
            self.assertFalse(any("commit.gpgsign=false" in line for line in log_lines))

    def test_batch_commit_retries_once_unsigned_when_enabled_after_signing_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo = temp_path / "repo"
            fake_bin = temp_path / "bin"
            log_file = temp_path / "git.log"
            repo.mkdir()
            fake_bin.mkdir()
            self._init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            (repo / "README.md").write_text("base\nupdated\n", encoding="utf-8")
            self._write_commit_signing_wrapper(fake_bin, log_file)

            env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "GITOPS_ALLOW_UNSIGNED_COMMIT_RETRY": "1"}
            proc = run(
                ["python3", str(SCRIPTS_DIR / "batch-commit.py"), "--repo", str(repo), "--json"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "committed")
            self.assertTrue(payload["signing_disabled"])
            self.assertTrue(payload["unsigned_retry_enabled"])
            self.assertTrue(payload["unsigned_retry_used"])
            self.assertEqual(len(payload["commits"]), 1)
            log_lines = log_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(sum('"commit"' in line and '"--only"' in line for line in log_lines), 2)
            self.assertTrue(any("commit.gpgsign=false" in line for line in log_lines))


class SensitiveScanWorkflowSafetyTests(unittest.TestCase):
    def test_workflow_extracts_gitleaks_in_temp_dir_without_repo_cleanup(self):
        workflow = (ROOT / "assets" / "github" / "workflows" / "sensitive-scan.yml").read_text(encoding="utf-8")
        self.assertIn('workdir="$(mktemp -d)"', workflow)
        self.assertIn('trap \'rm -rf "$workdir"\' EXIT', workflow)
        self.assertNotIn("README.md LICENSE", workflow)


class ForcePushSafetyTests(unittest.TestCase):
    FORCE_PUSH_PATTERN = re.compile(
        r"(?m)^[ \t]*(?!#).*?\bgit\b[^\n#]*\bpush\b[^\n#]*[ \t]--force(?!-with-lease)(?:[ \t]|$)"
    )

    def test_scripts_do_not_use_git_push_force(self):
        for script in SCRIPTS_DIR.glob("*.sh"):
            text = script.read_text(encoding="utf-8")
            self.assertNotRegex(text, self.FORCE_PUSH_PATTERN, f"forbidden force push in {script.name}")

    def test_force_push_pattern_matches_forbidden_usage(self):
        self.assertRegex("git push --force", self.FORCE_PUSH_PATTERN)
        self.assertRegex("git push origin main --force", self.FORCE_PUSH_PATTERN)

    def test_force_push_pattern_excludes_allowed_or_commented_usage(self):
        self.assertNotRegex("git push --force-with-lease", self.FORCE_PUSH_PATTERN)
        self.assertNotRegex("# git push --force", self.FORCE_PUSH_PATTERN)


class GovernanceWrapperBehaviorTests(unittest.TestCase):
    def test_governance_wrapper_runs_validate_plan_apply_audit_in_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "calls.log"

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$1\" == \"api\" ]]; then\n"
                "  echo '{}'\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

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
                ["bash", str(SCRIPTS_DIR / "governance-enforce.sh"), "--repo", "acme/widget"],
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

    def test_governance_wrapper_requires_repo_for_preflight(self):
        proc = run(
            ["bash", str(SCRIPTS_DIR / "governance-enforce.sh")],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("--repo is required", proc.stderr)

    def test_governance_wrapper_stops_when_capability_preflight_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "calls.log"

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "echo 'Resource not accessible by integration' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            fake_python3 = fake_bin / "python3"
            fake_python3.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "echo \"$*\" >> \"${FAKE_LOG}\"\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_python3.chmod(fake_python3.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_LOG"] = str(log_file)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "governance-enforce.sh"), "--repo", "acme/widget"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
            self.assertFalse(log_file.exists(), "python3 governance sequence should not run after preflight failure")


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
                "  if [[ \"$jq_expr\" == *\".data.repository.pullRequest.reviewThreads\"* ]]; then\n"
                "    if [[ \"$has_after\" == \"false\" ]]; then\n"
                "      cat <<'JSON'\n"
                "{\"nodes\":[{\"isResolved\":false,\"comments\":{\"nodes\":[{\"author\":{\"login\":\"bot\"},\"path\":\"a/b\",\"line\":1,\"url\":\"http://example/1\",\"body\":\"needs change\"}]}}],\"pageInfo\":{\"hasNextPage\":true,\"endCursor\":\"CURSOR_1\"}}\n"
                "JSON\n"
                "    else\n"
                "      cat <<'JSON'\n"
                "{\"nodes\":[{\"isResolved\":false,\"comments\":{\"nodes\":[{\"author\":{\"login\":\"bot\"},\"path\":\"a/b\",\"line\":2,\"url\":\"http://example/2\",\"body\":\"still unresolved\"}]}}],\"pageInfo\":{\"hasNextPage\":false,\"endCursor\":null}}\n"
                "JSON\n"
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
            self.assertIn('"threadId"', proc.stdout)

    def test_threads_script_can_show_resolved_threads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$1\" == \"api\" && \"$2\" == \"graphql\" ]]; then\n"
                "  jq_expr=\"\"\n"
                "  for ((i=1; i<=$#; i++)); do\n"
                "    if [[ \"${!i}\" == \"--jq\" ]]; then\n"
                "      next=$((i+1))\n"
                "      jq_expr=\"${!next}\"\n"
                "      break\n"
                "    fi\n"
                "  done\n"
                "  if [[ \"$jq_expr\" == *\".data.repository.pullRequest.reviewThreads\"* ]]; then\n"
                "    cat <<'JSON'\n"
                "{\"nodes\":[{\"isResolved\":true,\"comments\":{\"nodes\":[{\"author\":{\"login\":\"bot\"},\"path\":\"a/b\",\"line\":9,\"url\":\"http://example/resolved\",\"body\":\"done\"}]}},{\"isResolved\":false,\"comments\":{\"nodes\":[{\"author\":{\"login\":\"bot\"},\"path\":\"a/b\",\"line\":10,\"url\":\"http://example/unresolved\",\"body\":\"todo\"}]}}],\"pageInfo\":{\"hasNextPage\":false,\"endCursor\":null}}\n"
                "JSON\n"
                "  else\n"
                "    printf '\\n'\n"
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
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-unresolved-threads.sh"),
                    "7",
                    "--repo",
                    "acme/widget",
                    "--state",
                    "resolved",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("Resolved inline review threads", proc.stdout)
            self.assertIn("http://example/resolved", proc.stdout)
            self.assertNotIn("http://example/unresolved", proc.stdout)

    def test_threads_script_rejects_invalid_state_value(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-unresolved-threads.sh"),
                "7",
                "--state",
                "closed",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("invalid --state", proc.stderr)


class PrWorkflowOutputTests(unittest.TestCase):
    def _fake_gh_script(self) -> str:
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ \"$1\" == \"pr\" && \"$2\" == \"view\" ]]; then\n"
            "  if [[ \"$*\" == *\"--comments\"* ]]; then\n"
            "    echo \"FULL COMMENTS\"; exit 0\n"
            "  fi\n"
            "  if [[ \"$*\" == *\"--json comments\"* ]]; then\n"
            "    echo \"2\"; exit 0\n"
            "  fi\n"
            "  if [[ \"$*\" == *\"--json number,title,state,isDraft,reviewDecision,mergeable,baseRefName,headRefName,url\"* ]]; then\n"
            "    echo '{\"number\":7,\"title\":\"t\",\"state\":\"OPEN\"}'; exit 0\n"
            "  fi\n"
            "fi\n"
            "if [[ \"$1\" == \"pr\" && \"$2\" == \"checks\" ]]; then\n"
            "  echo \"checks\"; exit 0\n"
            "fi\n"
            "if [[ \"$1\" == \"api\" && \"$2\" == \"graphql\" ]]; then\n"
            "  jq_expr=\"\"\n"
            "  for ((i=1; i<=$#; i++)); do\n"
            "    if [[ \"${!i}\" == \"--jq\" ]]; then\n"
            "      next=$((i+1)); jq_expr=\"${!next}\"; break\n"
            "    fi\n"
            "  done\n"
            "  if [[ \"$jq_expr\" == *\".data.repository.pullRequest.reviewThreads\"* ]]; then\n"
            "    echo '{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false,\"endCursor\":null}}'; exit 0\n"
            "  fi\n"
            "fi\n"
            "echo ''\n"
            "exit 0\n"
        )

    def test_pr_workflow_defaults_to_concise_comments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(self._fake_gh_script(), encoding="utf-8")
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                ["bash", str(SCRIPTS_DIR / "pr-workflow.sh"), "7", "--repo", "acme/widget"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("full comments: skipped", proc.stdout)
            self.assertNotIn("FULL COMMENTS", proc.stdout)

    def test_pr_workflow_full_comments_flag_shows_verbose_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(self._fake_gh_script(), encoding="utf-8")
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"

            proc = run(
                ["bash", str(SCRIPTS_DIR / "pr-workflow.sh"), "7", "--repo", "acme/widget", "--full-comments"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("FULL COMMENTS", proc.stdout)


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


class ResolveThreadsScriptTests(unittest.TestCase):
    def test_resolve_threads_dry_run_all(self):
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
                "    if [[ \"$has_after\" == \"false\" ]]; then printf 'true\\n'; else printf 'false\\n'; fi\n"
                "  elif [[ \"$jq_expr\" == *\"pageInfo.endCursor\"* ]]; then\n"
                "    printf 'CURSOR_1\\n'\n"
                "  elif [[ \"$jq_expr\" == *\"reviewThreads.nodes\"* ]]; then\n"
                "    if [[ \"$has_after\" == \"false\" ]]; then\n"
                "      printf 'PRRT_1\\tauthor-a\\tfileA\\thttp://example/1\\n'\n"
                "    else\n"
                "      printf 'PRRT_2\\tauthor-b\\tfileB\\thttp://example/2\\n'\n"
                "    fi\n"
                "  else\n"
                "    printf '\\n'\n"
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
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-resolve-threads.sh"),
                    "7",
                    "--repo",
                    "acme/widget",
                    "--all",
                    "--dry-run",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("Selected unresolved threads: 2", proc.stdout)
            self.assertIn("DRY-RUN resolve thread: PRRT_1", proc.stdout)
            self.assertIn("DRY-RUN resolve thread: PRRT_2", proc.stdout)


class StartBranchScriptTests(unittest.TestCase):
    def _init_repo(self, repo: Path):
        run(["git", "init"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "commit.gpgsign", "false"], cwd=repo)
        run(["git", "config", "tag.gpgsign", "false"], cwd=repo)

    def test_start_branch_auto_stashes_dirty_tree_and_restores(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
            run(["git", "add", "tracked.txt"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)

            (repo / "tracked.txt").write_text("base\nlocal-change\n", encoding="utf-8")
            (repo / "notes.tmp").write_text("scratch\n", encoding="utf-8")

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "start-branch.sh"),
                    "feat",
                    "stash-flow",
                    "--base",
                    "main",
                    "--stash-name",
                    "local-wip",
                    "--no-worktree",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip()
            self.assertEqual(branch, "feat/stash-flow")
            self.assertIn("local-change", (repo / "tracked.txt").read_text(encoding="utf-8"))
            self.assertTrue((repo / "notes.tmp").exists())
            stash_list = run(["git", "stash", "list"], cwd=repo).stdout.strip()
            self.assertEqual(stash_list, "")
            hook_path = run(["git", "rev-parse", "--git-path", "hooks/pre-commit"], cwd=repo).stdout.strip()
            hook_file = Path(hook_path) if Path(hook_path).is_absolute() else repo / hook_path
            self.assertTrue(hook_file.exists())
            hook_text = hook_file.read_text(encoding="utf-8")
            self.assertIn("gitops-workflow-managed-pre-commit", hook_text)

    def test_start_branch_omitted_slug_uses_issue_slug(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "start-branch.sh"),
                    "fix",
                    "--issue",
                    "123",
                    "--base",
                    "main",
                    "--no-worktree",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip()
            self.assertEqual(branch, "fix/issue-123")

    def test_start_branch_worktree_mode_creates_linked_checkout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._init_repo(repo)

            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "start-branch.sh"),
                    "feat",
                    "linked-mode",
                    "--base",
                    "main",
                    "--worktree",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip(), "main")

            expected_path = Path(f"{repo}.worktrees") / "feat" / "linked-mode"
            self.assertTrue(expected_path.exists())
            self.assertIn(f"Next workdir: {expected_path}", proc.stdout)
            self.assertEqual(
                run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=expected_path).stdout.strip(),
                "feat/linked-mode",
            )

    def test_start_branch_worktree_mode_rejects_existing_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._init_repo(repo)

            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)

            existing_path = Path(f"{repo}.worktrees") / "feat" / "linked-mode"
            existing_path.mkdir(parents=True, exist_ok=True)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "start-branch.sh"),
                    "feat",
                    "linked-mode",
                    "--base",
                    "main",
                    "--worktree",
                ],
                cwd=repo,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("worktree path already exists", proc.stderr)

    def test_start_branch_stash_pop_failure_keeps_stash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            (repo / "conflict.txt").write_text("tracked on main\n", encoding="utf-8")
            run(["git", "add", "conflict.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: add conflict file"], cwd=repo)

            run(["git", "checkout", "-b", "scratch", "HEAD~1"], cwd=repo)
            (repo / "conflict.txt").write_text("scratch local\n", encoding="utf-8")

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "start-branch.sh"),
                    "feat",
                    "collision",
                    "--base",
                    "main",
                    "--no-worktree",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
            self.assertIn("stash restore failed", proc.stderr)
            stash_list = run(["git", "stash", "list"], cwd=repo).stdout
            self.assertIn("gitops-workflow:start-branch:", stash_list)

    def test_start_branch_missing_option_value_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            proc_issue = run(
                ["bash", str(SCRIPTS_DIR / "start-branch.sh"), "feat", "--issue"],
                cwd=repo,
                check=False,
            )
            self.assertNotEqual(proc_issue.returncode, 0)
            self.assertIn("option '--issue' requires a value", proc_issue.stderr)

            proc_base = run(
                ["bash", str(SCRIPTS_DIR / "start-branch.sh"), "feat", "x", "--base"],
                cwd=repo,
                check=False,
            )
            self.assertNotEqual(proc_base.returncode, 0)
            self.assertIn("option '--base' requires a value", proc_base.stderr)

    def test_start_branch_uses_trunk_when_origin_head_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "trunk"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "start-branch.sh"), "feat", "trunk-based", "--no-worktree"],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("Base branch: trunk", proc.stdout)
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip(), "feat/trunk-based")

    def test_start_branch_adopts_remote_existing_branch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            work = Path(temp_dir) / "work"
            clone = Path(temp_dir) / "clone"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            work.mkdir()
            self._init_repo(work)
            run(["git", "remote", "add", "origin", str(origin)], cwd=work)
            run(["git", "checkout", "-b", "main"], cwd=work)
            (work / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=work)
            run(["git", "commit", "-m", "chore: base"], cwd=work)
            run(["git", "push", "-u", "origin", "main"], cwd=work)
            run(["git", "checkout", "-b", "feat/remote-only"], cwd=work)
            (work / "feature.txt").write_text("remote\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=work)
            run(["git", "commit", "-m", "feat: remote branch"], cwd=work)
            run(["git", "push", "-u", "origin", "feat/remote-only"], cwd=work)

            run(["git", "clone", str(origin), str(clone)], cwd=Path(temp_dir))
            run(["git", "config", "user.name", "Test User"], cwd=clone)
            run(["git", "config", "user.email", "test@example.com"], cwd=clone)
            run(["git", "config", "commit.gpgsign", "false"], cwd=clone)
            run(["git", "config", "tag.gpgsign", "false"], cwd=clone)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "start-branch.sh"), "feat", "remote-only", "--existing", "--no-worktree"],
                cwd=clone,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=clone).stdout.strip(), "feat/remote-only")
            upstream = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd=clone).stdout.strip()
            self.assertEqual(upstream, "origin/feat/remote-only")

    def test_start_branch_recovers_detached_head_before_branch_creation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            run(["git", "checkout", "HEAD^0"], cwd=repo)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "start-branch.sh"), "feat", "from-detached", "--base", "main", "--no-worktree"],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip(), "feat/from-detached")

    def test_start_branch_json_output_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "start-branch.sh"), "feat", "json-mode", "--base", "main", "--json"],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "created")
            self.assertEqual(payload["branch"], "feat/json-mode")
            self.assertEqual(payload["mode"], "worktree")


class EnsureWorktreeScriptTests(unittest.TestCase):
    def _init_repo(self, repo: Path):
        run(["git", "init"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "commit.gpgsign", "false"], cwd=repo)
        run(["git", "config", "tag.gpgsign", "false"], cwd=repo)
        run(["git", "checkout", "-b", "main"], cwd=repo)
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        run(["git", "add", "README.md"], cwd=repo)
        run(["git", "commit", "-m", "chore: base"], cwd=repo)

    def test_ensure_worktree_creates_linked_checkout_for_current_feature_branch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._init_repo(repo)
            run(["git", "checkout", "-b", "feat/in-place"], cwd=repo)
            (repo / "local.txt").write_text("work\n", encoding="utf-8")

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ensure-worktree.sh"), "--json"],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "created")
            worktree_path = Path(payload["path"])
            self.assertTrue(worktree_path.exists())
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip(), "main")
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_path).stdout.strip(), "feat/in-place")
            self.assertTrue((worktree_path / "local.txt").exists())

    def test_ensure_worktree_reuses_existing_linked_checkout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._init_repo(repo)
            create_proc = run(
                ["bash", str(SCRIPTS_DIR / "start-branch.sh"), "feat", "existing", "--worktree"],
                cwd=repo,
                check=False,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "ensure-worktree.sh"), "--repo", str(repo), "--branch", "feat/existing", "--json"],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "adopted")
            self.assertTrue(Path(payload["path"]).exists())


class SyncAndReconcileScriptTests(unittest.TestCase):
    def _init_repo(self, repo: Path):
        run(["git", "init"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "commit.gpgsign", "false"], cwd=repo)
        run(["git", "config", "tag.gpgsign", "false"], cwd=repo)

    def _clone_with_identity(self, origin: Path, clone: Path, temp_dir: Path):
        run(["git", "clone", str(origin), str(clone)], cwd=temp_dir)
        run(["git", "config", "user.name", "Test User"], cwd=clone)
        run(["git", "config", "user.email", "test@example.com"], cwd=clone)
        run(["git", "config", "commit.gpgsign", "false"], cwd=clone)
        run(["git", "config", "tag.gpgsign", "false"], cwd=clone)

    def _write_fetch_git_wrapper(
        self,
        temp_dir: Path,
        *,
        ssh_stderr: str,
        https_exit: int,
        https_stderr: str,
        https_exec_target: Path | None = None,
    ) -> Path:
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        wrapper = Path(temp_dir) / "git"
        wrapper.write_text(
            '#!/usr/bin/env python3\nimport json\nimport os\nimport sys\n\nREAL_GIT = {real_git!r}\nHTTPS_URL = "https://github.com/example/example.git"\nHTTPS_EXEC_TARGET = {https_exec_target!r}\nargs = sys.argv[1:]\nlog_path = os.environ.get("FAKE_GIT_LOG")\nif log_path:\n    with open(log_path, "a", encoding="utf-8") as handle:\n        handle.write(json.dumps(args) + "\\n")\nif "fetch" in args and "--prune" in args:\n    if "origin" in args:\n        sys.stderr.write({ssh_stderr!r})\n        raise SystemExit(255)\n    if HTTPS_URL in args:\n        if HTTPS_EXEC_TARGET:\n            rewritten = [HTTPS_EXEC_TARGET if arg == HTTPS_URL else arg for arg in args]\n            os.execv(REAL_GIT, [REAL_GIT, *rewritten])\n        sys.stderr.write({https_stderr!r})\n        raise SystemExit({https_exit})\nos.execv(REAL_GIT, [REAL_GIT, *args])\n'.format(real_git=real_git, ssh_stderr=ssh_stderr, https_exit=https_exit, https_stderr=https_stderr, https_exec_target=str(https_exec_target) if https_exec_target else ""),
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        return wrapper

    def _write_push_success_without_remote_update_wrapper(self, temp_dir: Path) -> Path:
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        wrapper = Path(temp_dir) / "git"
        wrapper.write_text(
            '#!/usr/bin/env python3\nimport os\nimport sys\n\nREAL_GIT = {real_git!r}\nargs = sys.argv[1:]\nif "push" in args and "--dry-run" not in args:\n    raise SystemExit(0)\nos.execv(REAL_GIT, [REAL_GIT, *args])\n'.format(real_git=real_git),
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        return wrapper

    def test_sync_raw_blocks_dirty_checkout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            (repo / "README.md").write_text("dirty\n", encoding="utf-8")

            proc = run(
                ["bash", str(SCRIPTS_DIR / "sync-raw.sh"), "--repo", str(repo), "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["results"][0]["status"], "skipped-no-origin")
            self.assertEqual((repo / "README.md").read_text(encoding="utf-8"), "dirty\n")

    def test_repo_state_uses_https_fallback_after_ssh_fetch_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            seed = Path(temp_dir) / "seed"
            repo = Path(temp_dir) / "repo"
            log_file = Path(temp_dir) / "git.log"
            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            seed.mkdir()
            self._init_repo(seed)
            run(["git", "checkout", "-b", "main"], cwd=seed)
            run(["git", "remote", "add", "origin", str(origin)], cwd=seed)
            (seed / "README.md").write_text("remote\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=seed)
            run(["git", "commit", "-m", "chore: remote base"], cwd=seed)
            run(["git", "push", "-u", "origin", "main"], cwd=seed)
            repo.mkdir()
            self._init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            run(["git", "remote", "add", "origin", "git@github.com:example/example.git"], cwd=repo)
            run(["git", "remote", "set-url", "--push", "origin", "git@github.com:example/example.git"], cwd=repo)
            self._write_fetch_git_wrapper(
                Path(temp_dir),
                ssh_stderr="Permission denied (publickey).\n",
                https_exit=0,
                https_stderr="",
                https_exec_target=origin,
            )
            env = os.environ.copy()
            env["PATH"] = f"{Path(temp_dir)}:{env['PATH']}"
            env["FAKE_GIT_LOG"] = str(log_file)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "repo-state.sh"), "--repo", str(repo), "--no-recurse-related", "--json"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            result = payload["results"][0]
            self.assertEqual(result["fetch_status"], "fetched")
            self.assertEqual(result["fetch_transport_attempts"], ["ssh", "https"])
            self.assertEqual(result["fetch_transport_used"], "https")
            self.assertEqual(result["fetch_fallback_reason"], "ssh-publickey-auth-failed")
            self.assertEqual(result["fetch_remote_url_kind"], "ssh")
            self.assertEqual(
                run(["git", "remote", "get-url", "origin"], cwd=repo).stdout.strip(),
                "git@github.com:example/example.git",
            )
            self.assertEqual(
                run(["git", "remote", "get-url", "--push", "origin"], cwd=repo).stdout.strip(),
                "git@github.com:example/example.git",
            )
            self.assertEqual(
                run(["git", "rev-parse", "refs/remotes/origin/main"], cwd=repo).stdout.strip(),
                run(["git", "--git-dir", str(origin), "rev-parse", "refs/heads/main"], cwd=Path(temp_dir)).stdout.strip(),
            )
            log_lines = log_file.read_text(encoding="utf-8").splitlines()
            self.assertTrue(any('"https://github.com/example/example.git"' in line for line in log_lines))
            self.assertFalse(any("remote.origin.url=https://github.com/example/example.git" in line for line in log_lines))

    def test_sync_raw_blocks_fetch_without_https_fallback_on_host_verification_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            log_file = Path(temp_dir) / "git.log"
            repo.mkdir()
            self._init_repo(repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)
            run(["git", "remote", "add", "origin", "git@github.com:example/example.git"], cwd=repo)
            self._write_fetch_git_wrapper(
                Path(temp_dir),
                ssh_stderr="Host key verification failed.\n",
                https_exit=97,
                https_stderr="unexpected https fallback\n",
            )
            env = os.environ.copy()
            env["PATH"] = f"{Path(temp_dir)}:{env['PATH']}"
            env["FAKE_GIT_LOG"] = str(log_file)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "sync-raw.sh"), "--repo", str(repo), "--no-recurse-related", "--json"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            result = payload["results"][0]
            self.assertEqual(result["status"], "blocked-fetch")
            self.assertEqual(result["fetch_status"], "warning")
            self.assertEqual(result["fetch_transport_attempts"], ["ssh"])
            self.assertEqual(result["fetch_transport_used"], "")
            self.assertEqual(result["fetch_fallback_reason"], "ssh-host-verification-failed")
            self.assertEqual(result["fetch_remote_url_kind"], "ssh")
            self.assertIn("Host key verification failed", result["fetch_note"])
            log_lines = log_file.read_text(encoding="utf-8").splitlines()
            self.assertFalse(any('"https://github.com/example/example.git"' in line for line in log_lines))

    def test_sync_raw_dirty_checkout_uses_stash_then_restores(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            work = Path(temp_dir) / "work"
            clone = Path(temp_dir) / "clone"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            work.mkdir()
            self._init_repo(work)
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
                ["bash", str(SCRIPTS_DIR / "sync-raw.sh"), "--repo", str(clone), "--no-recurse-related", "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["results"][0]["status"], "synced-with-fallback")
            content = (clone / "README.md").read_text(encoding="utf-8")
            self.assertIn("remote", content)
            self.assertIn("local", content)
            self.assertEqual(run(["git", "stash", "list"], cwd=clone).stdout.strip(), "")

    def test_sync_raw_pushes_ahead_branch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            origin = temp_path / "origin.git"
            work = temp_path / "work"
            clone = temp_path / "clone"

            run(["git", "init", "--bare", str(origin)], cwd=temp_path)
            work.mkdir()
            self._init_repo(work)
            run(["git", "checkout", "-b", "main"], cwd=work)
            run(["git", "remote", "add", "origin", str(origin)], cwd=work)
            (work / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=work)
            run(["git", "commit", "-m", "chore: base"], cwd=work)
            run(["git", "push", "-u", "origin", "main"], cwd=work)

            self._clone_with_identity(origin, clone, temp_path)
            (clone / "README.md").write_text("base\nlocal\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=clone)
            run(["git", "commit", "-m", "feat: local advance"], cwd=clone)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "sync-raw.sh"), "--repo", str(clone), "--no-recurse-related", "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            result = payload["results"][0]
            self.assertEqual(result["status"], "pushed")
            self.assertEqual(result["history_action"], "noop")
            self.assertEqual(result["push_action"], "push")
            self.assertEqual(result["ahead_before"], 1)
            self.assertEqual(result["ahead_after"], 0)
            self.assertEqual(
                run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip(),
                run(["git", "--git-dir", str(origin), "rev-parse", "refs/heads/main"], cwd=temp_path).stdout.strip(),
            )

    def test_sync_raw_rebases_diverged_branch_and_pushes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            origin = temp_path / "origin.git"
            work = temp_path / "work"
            clone = temp_path / "clone"

            run(["git", "init", "--bare", str(origin)], cwd=temp_path)
            work.mkdir()
            self._init_repo(work)
            run(["git", "checkout", "-b", "main"], cwd=work)
            run(["git", "remote", "add", "origin", str(origin)], cwd=work)
            (work / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=work)
            run(["git", "commit", "-m", "chore: base"], cwd=work)
            run(["git", "push", "-u", "origin", "main"], cwd=work)

            self._clone_with_identity(origin, clone, temp_path)

            (work / "remote.txt").write_text("remote\n", encoding="utf-8")
            run(["git", "add", "remote.txt"], cwd=work)
            run(["git", "commit", "-m", "feat: remote advance"], cwd=work)
            run(["git", "push"], cwd=work)

            (clone / "local.txt").write_text("local\n", encoding="utf-8")
            run(["git", "add", "local.txt"], cwd=clone)
            run(["git", "commit", "-m", "feat: local advance"], cwd=clone)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "sync-raw.sh"), "--repo", str(clone), "--no-recurse-related", "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            result = payload["results"][0]
            self.assertEqual(result["status"], "rebased-and-pushed")
            self.assertEqual(result["history_action"], "rebase")
            self.assertEqual(result["push_action"], "push")
            self.assertEqual(result["ahead_before"], 1)
            self.assertEqual(result["behind_before"], 1)
            self.assertEqual(result["ahead_after"], 0)
            self.assertEqual(result["behind_after"], 0)
            log_subjects = run(["git", "log", "--pretty=%s", "-2"], cwd=clone).stdout
            self.assertIn("feat: local advance", log_subjects)
            self.assertIn("feat: remote advance", log_subjects)
            self.assertEqual(
                run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip(),
                run(["git", "--git-dir", str(origin), "rev-parse", "refs/heads/main"], cwd=temp_path).stdout.strip(),
            )

    def test_sync_raw_no_push_defers_publish_for_ahead_branch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            origin = temp_path / "origin.git"
            work = temp_path / "work"
            clone = temp_path / "clone"

            run(["git", "init", "--bare", str(origin)], cwd=temp_path)
            work.mkdir()
            self._init_repo(work)
            run(["git", "checkout", "-b", "main"], cwd=work)
            run(["git", "remote", "add", "origin", str(origin)], cwd=work)
            (work / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=work)
            run(["git", "commit", "-m", "chore: base"], cwd=work)
            run(["git", "push", "-u", "origin", "main"], cwd=work)

            self._clone_with_identity(origin, clone, temp_path)
            (clone / "README.md").write_text("base\nlocal\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=clone)
            run(["git", "commit", "-m", "feat: local advance"], cwd=clone)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "sync-raw.sh"), "--repo", str(clone), "--no-recurse-related", "--no-push", "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            result = payload["results"][0]
            self.assertEqual(result["status"], "push-deferred")
            self.assertEqual(result["push_action"], "deferred")
            self.assertEqual(result["ahead_after"], 1)
            self.assertNotEqual(
                run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip(),
                run(["git", "--git-dir", str(origin), "rev-parse", "refs/heads/main"], cwd=temp_path).stdout.strip(),
            )

    def test_sync_raw_blocks_push_when_remote_head_does_not_move_after_nominal_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            origin = temp_path / "origin.git"
            work = temp_path / "work"
            clone = temp_path / "clone"

            run(["git", "init", "--bare", str(origin)], cwd=temp_path)
            work.mkdir()
            self._init_repo(work)
            run(["git", "checkout", "-b", "main"], cwd=work)
            run(["git", "remote", "add", "origin", str(origin)], cwd=work)
            (work / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=work)
            run(["git", "commit", "-m", "chore: base"], cwd=work)
            run(["git", "push", "-u", "origin", "main"], cwd=work)

            self._clone_with_identity(origin, clone, temp_path)
            (clone / "README.md").write_text("base\nlocal\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=clone)
            run(["git", "commit", "-m", "feat: local advance"], cwd=clone)

            self._write_push_success_without_remote_update_wrapper(temp_path)
            env = os.environ.copy()
            env["PATH"] = f"{temp_path}:{env['PATH']}"

            proc = run(
                ["bash", str(SCRIPTS_DIR / "sync-raw.sh"), "--repo", str(clone), "--no-recurse-related", "--json"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            result = payload["results"][0]
            self.assertEqual(result["status"], "blocked-push")
            self.assertFalse(result["push_verified"])
            self.assertEqual(result["push_verification_transport_used"], "other")
            self.assertIn("instead of local HEAD", result["push_verification_note"])
            self.assertEqual(
                run(["git", "--git-dir", str(origin), "rev-parse", "refs/heads/main"], cwd=temp_path).stdout.strip(),
                run(["git", "rev-parse", "refs/remotes/origin/main"], cwd=clone).stdout.strip(),
            )

    def test_sync_raw_merge_strategy_merges_diverged_branch_and_pushes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            origin = temp_path / "origin.git"
            work = temp_path / "work"
            clone = temp_path / "clone"

            run(["git", "init", "--bare", str(origin)], cwd=temp_path)
            work.mkdir()
            self._init_repo(work)
            run(["git", "checkout", "-b", "main"], cwd=work)
            run(["git", "remote", "add", "origin", str(origin)], cwd=work)
            (work / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=work)
            run(["git", "commit", "-m", "chore: base"], cwd=work)
            run(["git", "push", "-u", "origin", "main"], cwd=work)

            self._clone_with_identity(origin, clone, temp_path)

            (work / "remote.txt").write_text("remote\n", encoding="utf-8")
            run(["git", "add", "remote.txt"], cwd=work)
            run(["git", "commit", "-m", "feat: remote advance"], cwd=work)
            run(["git", "push"], cwd=work)

            (clone / "local.txt").write_text("local\n", encoding="utf-8")
            run(["git", "add", "local.txt"], cwd=clone)
            run(["git", "commit", "-m", "feat: local advance"], cwd=clone)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "sync-raw.sh"), "--repo", str(clone), "--no-recurse-related", "--pull-strategy", "merge", "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            result = payload["results"][0]
            self.assertEqual(result["status"], "merged-and-pushed")
            self.assertEqual(result["history_action"], "merge")
            self.assertEqual(result["push_action"], "push")
            self.assertEqual(result["ahead_after"], 0)
            self.assertEqual(result["behind_after"], 0)
            self.assertIn("Merge", run(["git", "log", "--pretty=%s", "-1"], cwd=clone).stdout)

    def test_sync_raw_ff_only_blocks_diverged_branch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            origin = temp_path / "origin.git"
            work = temp_path / "work"
            clone = temp_path / "clone"

            run(["git", "init", "--bare", str(origin)], cwd=temp_path)
            work.mkdir()
            self._init_repo(work)
            run(["git", "checkout", "-b", "main"], cwd=work)
            run(["git", "remote", "add", "origin", str(origin)], cwd=work)
            (work / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=work)
            run(["git", "commit", "-m", "chore: base"], cwd=work)
            run(["git", "push", "-u", "origin", "main"], cwd=work)

            self._clone_with_identity(origin, clone, temp_path)

            (work / "remote.txt").write_text("remote\n", encoding="utf-8")
            run(["git", "add", "remote.txt"], cwd=work)
            run(["git", "commit", "-m", "feat: remote advance"], cwd=work)
            run(["git", "push"], cwd=work)

            (clone / "local.txt").write_text("local\n", encoding="utf-8")
            run(["git", "add", "local.txt"], cwd=clone)
            run(["git", "commit", "-m", "feat: local advance"], cwd=clone)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "sync-raw.sh"), "--repo", str(clone), "--no-recurse-related", "--pull-strategy", "ff-only", "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            result = payload["results"][0]
            self.assertEqual(result["status"], "blocked-fast-forward")
            self.assertEqual(result["history_action"], "blocked")
            self.assertEqual(result["push_action"], "noop")
            self.assertEqual(result["ahead_before"], 1)
            self.assertEqual(result["behind_before"], 1)

    def test_sync_raw_publishes_branch_without_upstream(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            origin = temp_path / "origin.git"
            work = temp_path / "work"
            clone = temp_path / "clone"

            run(["git", "init", "--bare", str(origin)], cwd=temp_path)
            work.mkdir()
            self._init_repo(work)
            run(["git", "checkout", "-b", "main"], cwd=work)
            run(["git", "remote", "add", "origin", str(origin)], cwd=work)
            (work / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=work)
            run(["git", "commit", "-m", "chore: base"], cwd=work)
            run(["git", "push", "-u", "origin", "main"], cwd=work)

            self._clone_with_identity(origin, clone, temp_path)
            run(["git", "checkout", "-b", "feat/publish-me"], cwd=clone)
            (clone / "feature.txt").write_text("feature\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=clone)
            run(["git", "commit", "-m", "feat: publish branch"], cwd=clone)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "sync-raw.sh"), "--repo", str(clone), "--no-recurse-related", "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            result = payload["results"][0]
            self.assertEqual(result["status"], "published")
            self.assertEqual(result["history_action"], "publish")
            self.assertEqual(result["push_action"], "push-set-upstream")
            self.assertEqual(
                run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=clone).stdout.strip(),
                "origin/feat/publish-me",
            )
            self.assertEqual(
                run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip(),
                run(["git", "--git-dir", str(origin), "rev-parse", "refs/heads/feat/publish-me"], cwd=temp_path).stdout.strip(),
            )

    def test_reconcile_tree_creates_isolated_gitlink_commit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "parent"
            child_src = Path(temp_dir) / "child-src"
            child_origin = Path(temp_dir) / "child-origin.git"

            child_src.mkdir()
            self._init_repo(child_src)
            run(["git", "checkout", "-b", "main"], cwd=child_src)
            (child_src / "README.md").write_text("child\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=child_src)
            run(["git", "commit", "-m", "chore: child base"], cwd=child_src)
            run(["git", "init", "--bare", str(child_origin)], cwd=Path(temp_dir))
            run(["git", "remote", "add", "origin", str(child_origin)], cwd=child_src)
            run(["git", "push", "-u", "origin", "main"], cwd=child_src)

            parent.mkdir()
            self._init_repo(parent)
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
            (parent / "notes.txt").write_text("keep me dirty\n", encoding="utf-8")
            (child_checkout / "feature.txt").write_text("next\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=child_checkout)
            run(["git", "commit", "-m", "feat: advance submodule"], cwd=child_checkout)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "reconcile-tree.sh"), "--repo", str(parent), "--mode", "apply"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            log = run(["git", "log", "-1", "--pretty=%B"], cwd=parent).stdout
            self.assertIn("chore(submodules): update gitlinks", log)
            self.assertIn("- update deps/child to", log)
            parent_status = run(["git", "status", "--short"], cwd=parent).stdout
            self.assertIn("?? notes.txt", parent_status)
            self.assertNotIn("M  deps/child", parent_status)


class RepoStateAndRecoveryScriptTests(unittest.TestCase):
    def _init_repo(self, repo: Path):
        run(["git", "init"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "commit.gpgsign", "false"], cwd=repo)
        run(["git", "config", "tag.gpgsign", "false"], cwd=repo)
        run(["git", "checkout", "-b", "main"], cwd=repo)
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        run(["git", "add", "README.md"], cwd=repo)
        run(["git", "commit", "-m", "chore: base"], cwd=repo)

    def test_repo_state_json_reports_tree_scope_from_submodule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "parent"
            child_src = Path(temp_dir) / "child-src"
            child_origin = Path(temp_dir) / "child-origin.git"

            child_src.mkdir()
            self._init_repo(child_src)
            run(["git", "init", "--bare", str(child_origin)], cwd=Path(temp_dir))
            run(["git", "remote", "add", "origin", str(child_origin)], cwd=child_src)
            run(["git", "push", "-u", "origin", "main"], cwd=child_src)

            parent.mkdir()
            self._init_repo(parent)
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

            proc = run(
                ["bash", str(SCRIPTS_DIR / "repo-state.sh"), "--repo", str(child_checkout), "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["scope"], "tree")
            roles = {item["repo"]: item["role"] for item in payload["results"]}
            self.assertEqual(roles[str(parent)], "root")
            self.assertEqual(roles[str(child_checkout)], "current")
            child_item = next(item for item in payload["results"] if item["repo"] == str(child_checkout))
            self.assertEqual(child_item["gitlink_status"], "child-ahead")
            self.assertEqual(child_item["recovery_class"], "none")

    def test_repo_state_json_reports_resume_eligible_raw_ship_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            head = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
            common_dir = run(
                ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                cwd=repo,
            ).stdout.strip()
            state_path = Path(common_dir) / "gitops-workflow" / "ship-state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                json.dumps(
                    {
                        "mode": "raw",
                        "repo": str(repo.resolve()),
                        "branch": "main",
                        "head_before": head,
                        "head_after": head,
                        "sync_status": "up-to-date",
                        "batch_commit_status": "created",
                        "local_commit_created": True,
                        "local_commit_sha": head,
                        "push_started": True,
                        "push_completed": True,
                        "push_succeeded": False,
                        "resume_eligible": True,
                        "last_error_summary": "timed out before push completed",
                        "updated_at": "2026-04-12T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            proc = run(
                ["bash", str(SCRIPTS_DIR / "repo-state.sh"), "--repo", str(repo), "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            item = payload["results"][0]
            self.assertEqual(item["raw_ship_state"], "resume-eligible")
            self.assertTrue(item["raw_ship_resume_eligible"])
            self.assertEqual(item["raw_ship_local_commit_sha"], head)
            self.assertEqual(item["raw_ship_last_error_summary"], "timed out before push completed")
            self.assertEqual(item["raw_ship_next_action"], "rerun 'ship raw' to resume the pending push")
            self.assertEqual(item["next_action"], "rerun 'ship raw' to resume the pending push")

    def test_recover_repo_state_aborts_merge_and_reports_recovered(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "feature"], cwd=repo)
            (repo / "README.md").write_text("feature\n", encoding="utf-8")
            run(["git", "commit", "-am", "feat: feature change"], cwd=repo)
            run(["git", "checkout", "main"], cwd=repo)
            (repo / "README.md").write_text("main\n", encoding="utf-8")
            run(["git", "commit", "-am", "fix: main change"], cwd=repo)
            merge_proc = run(["git", "merge", "feature"], cwd=repo, check=False)
            self.assertNotEqual(merge_proc.returncode, 0, merge_proc.stdout + merge_proc.stderr)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "recover-repo-state.sh"), "--repo", str(repo), "--json", "--no-recurse-related"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["continued"])
            result = payload["results"][0]
            self.assertEqual(result["recovery_action"], "abort-merge")
            self.assertEqual(result["outcome"], "recovered")
            self.assertFalse((repo / ".git" / "MERGE_HEAD").exists())
            self.assertEqual(run(["git", "status", "--short"], cwd=repo).stdout.strip(), "")

    def test_start_branch_aborts_rebase_and_continues(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "feature"], cwd=repo)
            (repo / "README.md").write_text("feature\n", encoding="utf-8")
            run(["git", "commit", "-am", "feat: feature change"], cwd=repo)
            run(["git", "checkout", "main"], cwd=repo)
            (repo / "README.md").write_text("main\n", encoding="utf-8")
            run(["git", "commit", "-am", "fix: main change"], cwd=repo)
            run(["git", "checkout", "feature"], cwd=repo)
            rebase_proc = run(["git", "rebase", "main"], cwd=repo, check=False)
            self.assertNotEqual(rebase_proc.returncode, 0, rebase_proc.stdout + rebase_proc.stderr)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "start-branch.sh"), "feat", "after-rebase-recovery", "--base", "main", "--no-worktree"],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip(), "feat/after-rebase-recovery")
            self.assertFalse((repo / ".git" / "rebase-merge").exists())
            self.assertFalse((repo / ".git" / "rebase-apply").exists())

    def test_sync_raw_aborts_merge_and_continues(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            origin = Path(temp_dir) / "origin.git"
            work = Path(temp_dir) / "work"
            clone = Path(temp_dir) / "clone"

            run(["git", "init", "--bare", str(origin)], cwd=Path(temp_dir))
            work.mkdir()
            self._init_repo(work)
            run(["git", "remote", "add", "origin", str(origin)], cwd=work)
            run(["git", "push", "-u", "origin", "main"], cwd=work)

            run(["git", "clone", str(origin), str(clone)], cwd=Path(temp_dir))
            run(["git", "config", "user.name", "Test User"], cwd=clone)
            run(["git", "config", "user.email", "test@example.com"], cwd=clone)
            run(["git", "config", "commit.gpgsign", "false"], cwd=clone)
            run(["git", "config", "tag.gpgsign", "false"], cwd=clone)

            run(["git", "checkout", "-b", "topic"], cwd=clone)
            (clone / "README.md").write_text("topic\n", encoding="utf-8")
            run(["git", "commit", "-am", "feat: topic change"], cwd=clone)
            run(["git", "checkout", "main"], cwd=clone)
            (clone / "README.md").write_text("main\n", encoding="utf-8")
            run(["git", "commit", "-am", "fix: main change"], cwd=clone)
            merge_proc = run(["git", "merge", "topic"], cwd=clone, check=False)
            self.assertNotEqual(merge_proc.returncode, 0, merge_proc.stdout + merge_proc.stderr)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "sync-raw.sh"), "--repo", str(clone), "--no-recurse-related", "--json"],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["results"][0]["status"], "pushed")
            self.assertFalse((clone / ".git" / "MERGE_HEAD").exists())


class FinishWorkScriptTests(unittest.TestCase):
    def _init_repo(self, repo: Path):
        run(["git", "init"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "commit.gpgsign", "false"], cwd=repo)
        run(["git", "config", "tag.gpgsign", "false"], cwd=repo)
        run(["git", "checkout", "-b", "main"], cwd=repo)
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        run(["git", "add", "README.md"], cwd=repo)
        run(["git", "commit", "-m", "chore: base"], cwd=repo)

    def _env_without_gh(self, root: Path):
        fake_bin = Path(tempfile.mkdtemp(prefix="no-gh-bin-"))
        fake_gh = fake_bin / "gh"
        fake_gh.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
        fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        return env

    def test_finish_work_switches_to_base_and_deletes_merged_branch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "feat/cleanup-branch"], cwd=repo)
            (repo / "feature.txt").write_text("done\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: add cleanup flow"], cwd=repo)

            run(["git", "checkout", "main"], cwd=repo)
            run(["git", "merge", "--no-ff", "feat/cleanup-branch", "-m", "merge feat/cleanup-branch"], cwd=repo)
            run(["git", "checkout", "feat/cleanup-branch"], cwd=repo)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "finish-work.sh"), "--base", "main"],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip(), "main")

            branch_check = run(
                ["git", "show-ref", "--verify", "refs/heads/feat/cleanup-branch"],
                cwd=repo,
                check=False,
            )
            self.assertNotEqual(branch_check.returncode, 0)

    def test_finish_work_removes_linked_worktree_and_returns_main_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._init_repo(repo)

            create_proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "start-branch.sh"),
                    "feat",
                    "cleanup-worktree",
                    "--base",
                    "main",
                    "--worktree",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)
            worktree_path = Path(f"{repo}.worktrees") / "feat" / "cleanup-worktree"

            (worktree_path / "feature.txt").write_text("done\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=worktree_path)
            run(["git", "commit", "-m", "feat: add worktree cleanup"], cwd=worktree_path)

            run(["git", "checkout", "main"], cwd=repo)
            run(["git", "merge", "--no-ff", "feat/cleanup-worktree", "-m", "merge feat/cleanup-worktree"], cwd=repo)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "finish-work.sh"), "--base", "main"],
                cwd=worktree_path,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertFalse(worktree_path.exists())
            self.assertIn(f"Next workdir: {repo}", proc.stdout)

            branch_check = run(
                ["git", "show-ref", "--verify", "refs/heads/feat/cleanup-worktree"],
                cwd=repo,
                check=False,
            )
            self.assertNotEqual(branch_check.returncode, 0)

    def test_finish_work_refuses_cleanup_when_branch_not_confirmed_on_base(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "feat/not-merged"], cwd=repo)
            (repo / "feature.txt").write_text("done\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: pending merge"], cwd=repo)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "finish-work.sh"), "--base", "main"],
                cwd=repo,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("is not confirmed on 'main'", proc.stderr)

    def test_finish_work_refuses_dirty_target_branch_checkout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "feat/dirty-branch"], cwd=repo)
            (repo / "feature.txt").write_text("done\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: add dirty cleanup"], cwd=repo)
            run(["git", "checkout", "main"], cwd=repo)
            run(["git", "merge", "--no-ff", "feat/dirty-branch", "-m", "merge feat/dirty-branch"], cwd=repo)
            run(["git", "checkout", "feat/dirty-branch"], cwd=repo)
            (repo / "local.txt").write_text("local change\n", encoding="utf-8")

            proc = run(
                ["bash", str(SCRIPTS_DIR / "finish-work.sh"), "--base", "main"],
                cwd=repo,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("current checkout", proc.stderr)
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip(), "feat/dirty-branch")

    def test_finish_work_allows_dirty_base_checkout_when_cleaning_other_branch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "feat/delete-other"], cwd=repo)
            (repo / "feature.txt").write_text("done\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: add other branch cleanup"], cwd=repo)
            run(["git", "checkout", "main"], cwd=repo)
            run(["git", "merge", "--no-ff", "feat/delete-other", "-m", "merge feat/delete-other"], cwd=repo)
            (repo / "local.txt").write_text("keep me\n", encoding="utf-8")

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "finish-work.sh"),
                    "--base",
                    "main",
                    "--branch",
                    "feat/delete-other",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip(), "main")
            self.assertEqual((repo / "local.txt").read_text(encoding="utf-8"), "keep me\n")
            branch_check = run(
                ["git", "show-ref", "--verify", "refs/heads/feat/delete-other"],
                cwd=repo,
                check=False,
            )
            self.assertNotEqual(branch_check.returncode, 0)

    def test_finish_work_dry_run_allows_dirty_base_checkout_when_cleaning_other_branch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "feat/delete-other"], cwd=repo)
            (repo / "feature.txt").write_text("done\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: add other branch cleanup"], cwd=repo)
            run(["git", "checkout", "main"], cwd=repo)
            run(["git", "merge", "--no-ff", "feat/delete-other", "-m", "merge feat/delete-other"], cwd=repo)
            (repo / "local.txt").write_text("keep me\n", encoding="utf-8")

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "finish-work.sh"),
                    "--base",
                    "main",
                    "--branch",
                    "feat/delete-other",
                    "--dry-run",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn('DRY-RUN: git branch -D "feat/delete-other"', proc.stdout)
            self.assertNotIn('DRY-RUN: git checkout "main"', proc.stdout)
            self.assertEqual((repo / "local.txt").read_text(encoding="utf-8"), "keep me\n")

    def test_finish_work_refuses_dirty_main_checkout_target_from_linked_worktree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._init_repo(repo)

            create_proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "start-branch.sh"),
                    "feat",
                    "cleanup-worktree",
                    "--base",
                    "main",
                    "--worktree",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)
            worktree_path = Path(f"{repo}.worktrees") / "feat" / "cleanup-worktree"

            run(["git", "checkout", "-b", "feat/main-dirty"], cwd=repo)
            (repo / "main-only.txt").write_text("done\n", encoding="utf-8")
            run(["git", "add", "main-only.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: add main dirty target"], cwd=repo)
            run(["git", "checkout", "main"], cwd=repo)
            run(["git", "merge", "--no-ff", "feat/main-dirty", "-m", "merge feat/main-dirty"], cwd=repo)
            run(["git", "checkout", "feat/main-dirty"], cwd=repo)
            (repo / "local.txt").write_text("dirty\n", encoding="utf-8")

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "finish-work.sh"),
                    "--base",
                    "main",
                    "--branch",
                    "feat/main-dirty",
                ],
                cwd=worktree_path,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("main checkout", proc.stderr)
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip(), "feat/main-dirty")
            self.assertTrue(worktree_path.exists())

    def test_finish_work_refuses_dirty_target_linked_worktree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._init_repo(repo)

            for name in ("cleanup-worktree", "other-worktree"):
                create_proc = run(
                    [
                        "bash",
                        str(SCRIPTS_DIR / "start-branch.sh"),
                        "feat",
                        name,
                        "--base",
                        "main",
                        "--worktree",
                    ],
                    cwd=repo,
                    check=False,
                )
                self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)

            target_path = Path(f"{repo}.worktrees") / "feat" / "cleanup-worktree"
            caller_path = Path(f"{repo}.worktrees") / "feat" / "other-worktree"

            (target_path / "feature.txt").write_text("done\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=target_path)
            run(["git", "commit", "-m", "feat: add target cleanup"], cwd=target_path)
            run(["git", "checkout", "main"], cwd=repo)
            run(["git", "merge", "--no-ff", "feat/cleanup-worktree", "-m", "merge feat/cleanup-worktree"], cwd=repo)
            (target_path / "local.txt").write_text("dirty\n", encoding="utf-8")

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "finish-work.sh"),
                    "--base",
                    "main",
                    "--branch",
                    "feat/cleanup-worktree",
                ],
                cwd=caller_path,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("linked worktree", proc.stderr)
            self.assertTrue(target_path.exists())

    def test_finish_work_accepts_offline_squash_merged_branch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)
            env = self._env_without_gh(repo)

            run(["git", "checkout", "-b", "feat/offline-squash"], cwd=repo)
            (repo / "feature.txt").write_text("alpha\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: add offline squash"], cwd=repo)
            (repo / "feature.txt").write_text("alpha\nbeta\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: extend offline squash"], cwd=repo)

            squashed = run(["git", "diff", "main...feat/offline-squash"], cwd=repo).stdout
            run(["git", "checkout", "main"], cwd=repo)
            patch_proc = subprocess.run(
                ["git", "apply", "-"],
                input=squashed,
                cwd=str(repo),
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(patch_proc.returncode, 0)
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: squash offline branch"], cwd=repo)
            run(["git", "checkout", "feat/offline-squash"], cwd=repo)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "finish-work.sh"), "--base", "main"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip(), "main")

    def test_finish_work_rejects_offline_branch_when_base_diff_does_not_match(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)
            env = self._env_without_gh(repo)

            run(["git", "checkout", "-b", "feat/offline-mismatch"], cwd=repo)
            (repo / "feature.txt").write_text("branch change\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: add offline mismatch"], cwd=repo)
            run(["git", "checkout", "main"], cwd=repo)
            (repo / "feature.txt").write_text("different base\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: unrelated base change"], cwd=repo)
            run(["git", "checkout", "feat/offline-mismatch"], cwd=repo)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "finish-work.sh"), "--base", "main"],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("is not confirmed on 'main'", proc.stderr)

    def test_finish_work_from_linked_checkout_cleans_branch_in_main_checkout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._init_repo(repo)

            create_proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "start-branch.sh"),
                    "feat",
                    "cleanup-worktree",
                    "--base",
                    "main",
                    "--worktree",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)
            worktree_path = Path(f"{repo}.worktrees") / "feat" / "cleanup-worktree"

            run(["git", "checkout", "-b", "feat/main-checkout-target"], cwd=repo)
            (repo / "main-only.txt").write_text("done\n", encoding="utf-8")
            run(["git", "add", "main-only.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: add main checkout target"], cwd=repo)
            run(["git", "checkout", "main"], cwd=repo)
            run(["git", "merge", "--no-ff", "feat/main-checkout-target", "-m", "merge feat/main-checkout-target"], cwd=repo)
            run(["git", "checkout", "feat/main-checkout-target"], cwd=repo)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "finish-work.sh"),
                    "--base",
                    "main",
                    "--branch",
                    "feat/main-checkout-target",
                ],
                cwd=worktree_path,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("Target branch is checked out in the main checkout.", proc.stdout)
            self.assertTrue(repo.exists())
            self.assertTrue(worktree_path.exists())
            self.assertEqual(run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip(), "main")
            branch_check = run(
                ["git", "show-ref", "--verify", "refs/heads/feat/main-checkout-target"],
                cwd=repo,
                check=False,
            )
            self.assertNotEqual(branch_check.returncode, 0)

    def test_finish_work_dry_run_from_linked_checkout_skips_main_checkout_removal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            self._init_repo(repo)

            create_proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "start-branch.sh"),
                    "feat",
                    "cleanup-worktree",
                    "--base",
                    "main",
                    "--worktree",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)
            worktree_path = Path(f"{repo}.worktrees") / "feat" / "cleanup-worktree"

            run(["git", "checkout", "-b", "feat/main-checkout-target"], cwd=repo)
            (repo / "main-only.txt").write_text("done\n", encoding="utf-8")
            run(["git", "add", "main-only.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: add main checkout target"], cwd=repo)
            run(["git", "checkout", "main"], cwd=repo)
            run(["git", "merge", "--no-ff", "feat/main-checkout-target", "-m", "merge feat/main-checkout-target"], cwd=repo)
            run(["git", "checkout", "feat/main-checkout-target"], cwd=repo)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "finish-work.sh"),
                    "--base",
                    "main",
                    "--branch",
                    "feat/main-checkout-target",
                    "--dry-run",
                ],
                cwd=worktree_path,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn('DRY-RUN: git -C "', proc.stdout)
            self.assertIn(f'DRY-RUN: git -C "{repo}" checkout "main"', proc.stdout)
            self.assertIn('DRY-RUN: git -C "', proc.stdout)
            self.assertIn('branch -D "feat/main-checkout-target"', proc.stdout)
            self.assertNotIn(f'worktree remove "{repo}"', proc.stdout)
            self.assertTrue(repo.exists())
            self.assertTrue(worktree_path.exists())

    def test_finish_work_json_output_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)

            run(["git", "checkout", "-b", "feat/json-cleanup"], cwd=repo)
            (repo / "feature.txt").write_text("done\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: json cleanup"], cwd=repo)
            run(["git", "checkout", "main"], cwd=repo)
            run(["git", "merge", "--no-ff", "feat/json-cleanup", "-m", "merge feat/json-cleanup"], cwd=repo)

            proc = run(
                ["bash", str(SCRIPTS_DIR / "finish-work.sh"), "--branch", "feat/json-cleanup", "--base", "main", "--json"],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "cleaned")
            self.assertEqual(payload["branch"], "feat/json-cleanup")
            self.assertEqual(payload["base"], "main")


class MergeSquashScriptTests(unittest.TestCase):
    def _write_fake_gh(self, fake_gh: Path):
        fake_gh.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "cmd1=\"${1:-}\"\n"
            "cmd2=\"${2:-}\"\n"
            "if [[ \"$cmd1\" == \"api\" && \"$cmd2\" == \"graphql\" ]]; then\n"
            "  jq_expr=\"\"\n"
            "  for ((i=1; i<=$#; i++)); do\n"
            "    if [[ \"${!i}\" == \"--jq\" ]]; then\n"
            "      next=$((i+1))\n"
            "      jq_expr=\"${!next}\"\n"
            "      break\n"
            "    fi\n"
            "  done\n"
            "  if [[ \"$jq_expr\" == *\".data.repository.pullRequest.reviewThreads\"* ]]; then\n"
            "    if [[ \"${UNRESOLVED_THREADS:-0}\" == \"1\" ]]; then\n"
            "      cat <<'JSON'\n"
            "{\"nodes\":[{\"isResolved\":false,\"comments\":{\"nodes\":[{\"author\":{\"login\":\"bot\"},\"path\":\"a/b\",\"line\":2,\"url\":\"http://example/2\",\"body\":\"still unresolved\"}]}}],\"pageInfo\":{\"hasNextPage\":false,\"endCursor\":null}}\n"
            "JSON\n"
            "    else\n"
            "      cat <<'JSON'\n"
            "{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false,\"endCursor\":null}}\n"
            "JSON\n"
            "    fi\n"
            "  else\n"
            "    printf ''\n"
            "  fi\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"$cmd1\" == \"pr\" && \"$cmd2\" == \"checks\" ]]; then\n"
            "  if [[ \"${FAIL_CHECKS:-0}\" == \"1\" ]]; then\n"
            "    echo 'required check failed' >&2\n"
            "    exit 1\n"
            "  fi\n"
            "  if [[ \"${NO_REQUIRED_CHECKS:-0}\" == \"1\" ]]; then\n"
            "    echo 'no required checks reported on the branch' >&2\n"
            "    exit 1\n"
            "  fi\n"
            "  echo 'required checks passed'\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"$cmd1\" == \"pr\" && \"$cmd2\" == \"view\" ]]; then\n"
            "  if [[ \"${MERGE_MINIMAL_SECTIONS:-0}\" == \"1\" ]]; then\n"
            "    cat <<'JSON'\n"
            "{\n"
            "  \"number\": 7,\n"
            "  \"title\": \"feat(cli): add deterministic merge\",\n"
            "  \"isDraft\": false,\n"
            "  \"url\": \"https://github.com/acme/widget/pull/7\",\n"
            "  \"reviewDecision\": \"APPROVED\",\n"
            "  \"mergeStateStatus\": \"CLEAN\",\n"
            "  \"headRefOid\": \"abcdef1234567890\",\n"
            "  \"commits\": [\n"
            "    {\"oid\": \"1111111aaaaaaa\", \"messageHeadline\": \"feat(cli): add deterministic merge\", \"messageBody\": \"\"}\n"
            "  ]\n"
            "}\n"
            "JSON\n"
            "    exit 0\n"
            "  fi\n"
            "  cat <<'JSON'\n"
            "{\n"
            "  \"number\": 7,\n"
            "  \"title\": \"feat(cli): add deterministic merge\",\n"
            "  \"isDraft\": false,\n"
            "  \"url\": \"https://github.com/acme/widget/pull/7\",\n"
            "  \"reviewDecision\": \"APPROVED\",\n"
            "  \"mergeStateStatus\": \"CLEAN\",\n"
            "  \"headRefOid\": \"abcdef1234567890\",\n"
            "  \"commits\": [\n"
            "    {\"oid\": \"1111111aaaaaaa\", \"messageHeadline\": \"feat(cli): add deterministic merge\", \"messageBody\": \"\"},\n"
            "    {\"oid\": \"2222222bbbbbbb\", \"messageHeadline\": \"fix(tests): stabilize mocks\", \"messageBody\": \"\"}\n"
            "  ]\n"
            "}\n"
            "JSON\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"$cmd1\" == \"pr\" && \"$cmd2\" == \"merge\" ]]; then\n"
            "  echo \"$*\" >> \"${FAKE_LOG}\"\n"
            "  exit 0\n"
            "fi\n"
            "printf '\\n'\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

    def test_merge_squash_script_uses_deterministic_gh_merge_flags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "calls.log"

            fake_gh = fake_bin / "gh"
            self._write_fake_gh(fake_gh)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_LOG"] = str(log_file)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-merge-squash.sh"),
                    "7",
                    "--repo",
                    "acme/widget",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("`1111111` feat(cli): add deterministic merge", proc.stdout)
            self.assertIn("`2222222` fix(tests): stabilize mocks", proc.stdout)
            merge_call = log_file.read_text(encoding="utf-8")
            self.assertIn("pr merge 7 --squash", merge_call)
            self.assertIn("--subject feat(cli): add deterministic merge", merge_call)
            self.assertIn("--body-file", merge_call)
            self.assertIn("--match-head-commit abcdef1234567890", merge_call)
            self.assertIn("--delete-branch", merge_call)

    def test_merge_squash_omits_empty_optional_sections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "calls.log"

            fake_gh = fake_bin / "gh"
            self._write_fake_gh(fake_gh)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_LOG"] = str(log_file)
            env["MERGE_MINIMAL_SECTIONS"] = "1"

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-merge-squash.sh"),
                    "7",
                    "--repo",
                    "acme/widget",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("## New Features", proc.stdout)
            self.assertNotIn("## Bug Fixes", proc.stdout)
            self.assertNotIn("## Breaking Changes", proc.stdout)
            self.assertIn("## Commits", proc.stdout)
            self.assertIn("## Refs", proc.stdout)
            self.assertNotIn("_none_", proc.stdout)

    def test_merge_squash_admin_override_allows_failed_checks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "calls.log"

            fake_gh = fake_bin / "gh"
            self._write_fake_gh(fake_gh)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_LOG"] = str(log_file)
            env["FAIL_CHECKS"] = "1"

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-merge-squash.sh"),
                    "7",
                    "--repo",
                    "acme/widget",
                    "--admin",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("Admin override enabled; continuing despite required-check failures.", proc.stdout)
            merge_call = log_file.read_text(encoding="utf-8")
            self.assertIn("--delete-branch", merge_call)
            self.assertIn(" --admin", merge_call)

    def test_merge_squash_allows_missing_required_checks_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "calls.log"

            fake_gh = fake_bin / "gh"
            self._write_fake_gh(fake_gh)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_LOG"] = str(log_file)
            env["NO_REQUIRED_CHECKS"] = "1"

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-merge-squash.sh"),
                    "7",
                    "--repo",
                    "acme/widget",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("No required checks are configured for this PR; continuing.", proc.stdout)
            merge_call = log_file.read_text(encoding="utf-8")
            self.assertIn("pr merge 7 --squash", merge_call)

    def test_merge_squash_body_out_writes_editable_draft(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            fake_gh = fake_bin / "gh"
            self._write_fake_gh(fake_gh)

            draft_file = temp_path / "squash.md"
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_LOG"] = str(temp_path / "calls.log")

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-merge-squash.sh"),
                    "7",
                    "--repo",
                    "acme/widget",
                    "--body-out",
                    str(draft_file),
                    "--dry-run",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(draft_file.exists())
            body = draft_file.read_text(encoding="utf-8")
            self.assertIn("## Commits", body)
            self.assertIn("feat(cli): add deterministic merge", body)

    def test_merge_squash_body_file_uses_explicit_body(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "calls.log"
            fake_gh = fake_bin / "gh"
            self._write_fake_gh(fake_gh)

            custom_body = temp_path / "custom.md"
            custom_body.write_text("## Overview\n\nEdited body.\n", encoding="utf-8")

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_LOG"] = str(log_file)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-merge-squash.sh"),
                    "7",
                    "--repo",
                    "acme/widget",
                    "--body-file",
                    str(custom_body),
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("Edited body.", proc.stdout)
            merge_call = log_file.read_text(encoding="utf-8")
            self.assertIn(f"--body-file {custom_body}", merge_call)


class DeterministicGeneratorScriptTests(unittest.TestCase):
    def _init_repo(self, repo: Path):
        run(["git", "init"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
        run(["git", "config", "commit.gpgsign", "false"], cwd=repo)
        run(["git", "config", "tag.gpgsign", "false"], cwd=repo)
        run(["git", "checkout", "-b", "main"], cwd=repo)
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        run(["git", "add", "README.md"], cwd=repo)
        run(["git", "commit", "-m", "chore: base"], cwd=repo)

    def test_generate_squash_message_omits_empty_sections_and_keeps_refs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)
            run(["git", "checkout", "-b", "feat/omit-empty"], cwd=repo)
            (repo / "feature.txt").write_text("hello\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat(cli): add json output"], cwd=repo)

            proc = run(
                [
                    "python3",
                    str(SCRIPTS_DIR / "generate-squash-message.py"),
                    "--summary",
                    "add json output",
                    "--base",
                    "main",
                    "--pr",
                    "77",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("## New Features", proc.stdout)
            self.assertNotIn("## Bug Fixes", proc.stdout)
            self.assertNotIn("## Breaking Changes", proc.stdout)
            self.assertIn("## Commits", proc.stdout)
            self.assertIn("## Refs", proc.stdout)
            self.assertIn("- #77", proc.stdout)
            self.assertNotIn("- #123", proc.stdout)

    def test_generate_squash_message_deduplicates_summary_bullets_but_keeps_commits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)
            run(["git", "checkout", "-b", "feat/dedupe"], cwd=repo)

            for idx in range(2):
                (repo / f"feature-{idx}.txt").write_text(f"{idx}\n", encoding="utf-8")
                run(["git", "add", f"feature-{idx}.txt"], cwd=repo)
                run(["git", "commit", "-m", "feat(cli): add json output"], cwd=repo)

            proc = run(
                [
                    "python3",
                    str(SCRIPTS_DIR / "generate-squash-message.py"),
                    "--summary",
                    "add json output",
                    "--base",
                    "main",
                    "--pr",
                    "77",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(proc.stdout.count("- cli: add json output"), 1)
            self.assertEqual(proc.stdout.count("`"), 4)

    def test_generate_release_notes_omits_empty_sections_and_keeps_refs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)
            (repo / "docs.md").write_text("docs\n", encoding="utf-8")
            run(["git", "add", "docs.md"], cwd=repo)
            run(["git", "commit", "-m", "docs: add docs"], cwd=repo)

            proc = run(
                [
                    "python3",
                    str(SCRIPTS_DIR / "generate-release-notes.py"),
                    "--since",
                    "HEAD~1",
                    "--version",
                    "v0.1.0",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertNotIn("## New Features", proc.stdout)
            self.assertNotIn("## Bug Fixes", proc.stdout)
            self.assertIn("## Commits", proc.stdout)
            self.assertIn("- (none)", proc.stdout)
            self.assertIn("## Refs", proc.stdout)
            self.assertIn("- HEAD~1", proc.stdout)
            self.assertNotIn("- #123", proc.stdout)

    def test_pr_create_omits_optional_placeholder_sections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            self._init_repo(repo)
            run(["git", "checkout", "-b", "feat/pr-body"], cwd=repo)
            (repo / "feature.txt").write_text("hello\n", encoding="utf-8")
            run(["git", "add", "feature.txt"], cwd=repo)
            run(["git", "commit", "-m", "feat: add body generation test"], cwd=repo)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-create.sh"),
                    "--title",
                    "feat(test): ensure body generation",
                    "--base",
                    "main",
                    "--head",
                    "feat/pr-body",
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            match = re.search(r"PR body file created: (.+)", proc.stdout)
            self.assertIsNotNone(match, proc.stdout)
            body_path = Path(match.group(1).strip())
            body = body_path.read_text(encoding="utf-8")

            self.assertNotIn("# Screenshots / logs (optional)", body)
            self.assertIn("# Refs", body)
            self.assertIn("- (none provided)", body)
            self.assertNotIn("#<issue-if-applicable>", body)


class PrCommentScriptTests(unittest.TestCase):
    def test_pr_comment_normalizes_literal_newline_sequences(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            body_capture = temp_path / "body.txt"

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "body_file=''\n"
                "for ((i=1; i<=$#; i++)); do\n"
                "  if [[ \"${!i}\" == \"--body-file\" ]]; then\n"
                "    next=$((i+1))\n"
                "    body_file=\"${!next}\"\n"
                "  fi\n"
                "done\n"
                "cat \"$body_file\" > \"${BODY_CAPTURE}\"\n"
                "echo \"ok\"\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["BODY_CAPTURE"] = str(body_capture)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-comment.sh"),
                    "7",
                    "--body",
                    "@codex review\\n/gemini review\\n\\nFinal pass.",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            body = body_capture.read_text(encoding="utf-8")
            self.assertIn("@codex review\n/gemini review\n\nFinal pass.\n", body)

    def test_pr_comment_missing_body_value_fails_with_actionable_error(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-comment.sh"),
                "7",
                "--body",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("option '--body' requires a value", proc.stderr)

    def test_pr_comment_missing_repo_value_fails_with_actionable_error(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-comment.sh"),
                "7",
                "--body",
                "hello",
                "--repo",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("option '--repo' requires a value", proc.stderr)

    def test_pr_comment_reports_argument_error_before_missing_gh(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            shim_dir = Path(temp_dir) / "bin"
            shim_dir.mkdir(parents=True, exist_ok=True)
            os.symlink("/bin/bash", shim_dir / "bash")
            env = os.environ.copy()
            env["PATH"] = str(shim_dir)
            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-comment.sh"),
                    "7",
                    "--body",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn("option '--body' requires a value", proc.stderr)
            self.assertNotIn("missing required command: gh", proc.stderr)


class PrRequestReviewScriptTests(unittest.TestCase):
    def test_pr_request_review_posts_ordered_triggers_with_optional_note(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            body_capture = temp_path / "body.txt"

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "body_file=''\n"
                "for ((i=1; i<=$#; i++)); do\n"
                "  if [[ \"${!i}\" == \"--body-file\" ]]; then\n"
                "    next=$((i+1))\n"
                "    body_file=\"${!next}\"\n"
                "  fi\n"
                "done\n"
                "cat \"$body_file\" > \"${BODY_CAPTURE}\"\n"
                "echo \"ok\"\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["BODY_CAPTURE"] = str(body_capture)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-request-review.sh"),
                    "8",
                    "--note",
                    "Final verification pass requested.",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            body = body_capture.read_text(encoding="utf-8")
            self.assertTrue(body.startswith("@codex review\n/gemini review\n"))
            self.assertIn("Final verification pass requested.\n", body)

    def test_pr_request_review_missing_repo_value_fails_with_actionable_error(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-request-review.sh"),
                "8",
                "--repo",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("option '--repo' requires a value", proc.stderr)

    def test_pr_request_review_missing_note_value_fails_with_actionable_error(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-request-review.sh"),
                "8",
                "--note",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("option '--note' requires a value", proc.stderr)


class PrReplyScriptTests(unittest.TestCase):
    def test_pr_reply_missing_pr_number_fails(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-reply.sh"),
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("missing <pr_number>", proc.stderr)

    def test_pr_reply_missing_comment_id_fails(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-reply.sh"),
                "8",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("missing <comment_id>", proc.stderr)

    def test_pr_reply_non_numeric_pr_number_fails(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-reply.sh"),
                "x",
                "12345",
                "--body",
                "ok",
                "--repo",
                "acme/widget",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("invalid <pr_number>: must be numeric", proc.stderr)

    def test_pr_reply_non_numeric_comment_id_fails(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-reply.sh"),
                "8",
                "abc",
                "--body",
                "ok",
                "--repo",
                "acme/widget",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("invalid <comment_id>: must be numeric", proc.stderr)

    def test_pr_reply_rejects_positional_body(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-reply.sh"),
                "8",
                "12345",
                "legacy body",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("unknown argument: legacy body", proc.stderr)

    def test_pr_reply_requires_body_source(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-reply.sh"),
                "8",
                "12345",
                "--repo",
                "acme/widget",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("missing reply text; pass --body or --body-file", proc.stderr)

    def test_pr_reply_rejects_option_token_as_body_value(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-reply.sh"),
                "8",
                "12345",
                "--body",
                "--repo=acme/widget",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("option '--body' requires a value", proc.stderr)

    def test_pr_reply_body_equals_accepts_help_literal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            body_capture = temp_path / "reply_body.txt"

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"repo\" && \"${2:-}\" == \"view\" ]]; then\n"
                "  echo \"acme/widget\"\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"api\" ]]; then\n"
                "  for ((i=1; i<=$#; i++)); do\n"
                "    if [[ \"${!i}\" == \"-F\" ]]; then\n"
                "      next=$((i+1))\n"
                "      value=\"${!next}\"\n"
                "      if [[ \"$value\" == body=@* ]]; then\n"
                "        cat \"${value#body=@}\" > \"${BODY_CAPTURE}\"\n"
                "      fi\n"
                "    fi\n"
                "  done\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["BODY_CAPTURE"] = str(body_capture)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-reply.sh"),
                    "8",
                    "12345",
                    "--body=--help",
                    "--repo",
                    "acme/widget",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            body = body_capture.read_text(encoding="utf-8")
            self.assertEqual(body, "--help")

    def test_pr_reply_body_equals_accepts_markdown_separator(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            body_capture = temp_path / "reply_body.txt"

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"repo\" && \"${2:-}\" == \"view\" ]]; then\n"
                "  echo \"acme/widget\"\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"api\" ]]; then\n"
                "  for ((i=1; i<=$#; i++)); do\n"
                "    if [[ \"${!i}\" == \"-F\" ]]; then\n"
                "      next=$((i+1))\n"
                "      value=\"${!next}\"\n"
                "      if [[ \"$value\" == body=@* ]]; then\n"
                "        cat \"${value#body=@}\" > \"${BODY_CAPTURE}\"\n"
                "      fi\n"
                "    fi\n"
                "  done\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["BODY_CAPTURE"] = str(body_capture)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-reply.sh"),
                    "8",
                    "12345",
                    "--body=---",
                    "--repo",
                    "acme/widget",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            body = body_capture.read_text(encoding="utf-8")
            self.assertEqual(body, "---")

    def test_pr_reply_body_equals_rejects_empty_value(self):
        proc = run(
            [
                "bash",
                str(SCRIPTS_DIR / "pr-reply.sh"),
                "8",
                "12345",
                "--body=",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("option '--body' requires a value", proc.stderr)

    def test_pr_reply_normalizes_literal_newline_sequences_in_body(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            body_capture = temp_path / "reply_body.txt"

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"repo\" && \"${2:-}\" == \"view\" ]]; then\n"
                "  echo \"acme/widget\"\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"api\" ]]; then\n"
                "  for ((i=1; i<=$#; i++)); do\n"
                "    if [[ \"${!i}\" == \"-F\" ]]; then\n"
                "      next=$((i+1))\n"
                "      value=\"${!next}\"\n"
                "      if [[ \"$value\" == body=@* ]]; then\n"
                "        cat \"${value#body=@}\" > \"${BODY_CAPTURE}\"\n"
                "      fi\n"
                "    fi\n"
                "  done\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["BODY_CAPTURE"] = str(body_capture)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-reply.sh"),
                    "8",
                    "12345",
                    "--body",
                    "line one\\nline two",
                    "--repo",
                    "acme/widget",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            body = body_capture.read_text(encoding="utf-8")
            self.assertEqual(body, "line one\nline two")

    def test_pr_reply_body_preserves_leading_at_literal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            body_capture = temp_path / "reply_body.txt"

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"repo\" && \"${2:-}\" == \"view\" ]]; then\n"
                "  echo \"acme/widget\"\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"api\" ]]; then\n"
                "  for ((i=1; i<=$#; i++)); do\n"
                "    if [[ \"${!i}\" == \"-F\" ]]; then\n"
                "      next=$((i+1))\n"
                "      value=\"${!next}\"\n"
                "      if [[ \"$value\" == body=@* ]]; then\n"
                "        cat \"${value#body=@}\" > \"${BODY_CAPTURE}\"\n"
                "      fi\n"
                "    fi\n"
                "  done\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["BODY_CAPTURE"] = str(body_capture)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-reply.sh"),
                    "8",
                    "12345",
                    "--body",
                    "@/etc/passwd",
                    "--repo",
                    "acme/widget",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            body = body_capture.read_text(encoding="utf-8")
            self.assertEqual(body, "@/etc/passwd")

    def test_pr_reply_body_file_uses_file_transport(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            body_capture = temp_path / "reply_body.txt"
            mode_capture = temp_path / "mode.txt"
            body_file = temp_path / "reply.md"
            body_file.write_text("hello from file\n", encoding="utf-8")

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"repo\" && \"${2:-}\" == \"view\" ]]; then\n"
                "  echo \"acme/widget\"\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"api\" ]]; then\n"
                "  for ((i=1; i<=$#; i++)); do\n"
                "    if [[ \"${!i}\" == \"-F\" ]]; then\n"
                "      printf '%s' \"${!i}\" > \"${MODE_CAPTURE}\"\n"
                "      next=$((i+1))\n"
                "      value=\"${!next}\"\n"
                "      if [[ \"$value\" == body=@* ]]; then\n"
                "        cat \"${value#body=@}\" > \"${BODY_CAPTURE}\"\n"
                "      fi\n"
                "    fi\n"
                "  done\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["BODY_CAPTURE"] = str(body_capture)
            env["MODE_CAPTURE"] = str(mode_capture)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-reply.sh"),
                    "8",
                    "12345",
                    "--body-file",
                    str(body_file),
                    "--repo",
                    "acme/widget",
                ],
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            body = body_capture.read_text(encoding="utf-8")
            mode = mode_capture.read_text(encoding="utf-8")
            self.assertEqual(body, "hello from file\n")
            self.assertEqual(mode, "-F")


class PrMarkReadyScriptTests(unittest.TestCase):
    def test_pr_mark_ready_runs_gates_then_marks_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            repo = temp_path / "repo"
            repo.mkdir()
            run(["git", "init"], cwd=repo)
            run(["git", "config", "user.name", "Test User"], cwd=repo)
            run(["git", "config", "user.email", "test@example.com"], cwd=repo)
            run(["git", "config", "commit.gpgsign", "false"], cwd=repo)
            run(["git", "checkout", "-b", "main"], cwd=repo)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=repo)
            run(["git", "commit", "-m", "chore: base"], cwd=repo)

            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "calls.log"

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "echo \"$*\" >> \"${FAKE_LOG}\"\n"
                "if [[ \"${1:-}\" == \"pr\" && \"${2:-}\" == \"checks\" ]]; then\n"
                "  echo '[{\"bucket\":\"pass\",\"completedAt\":null,\"description\":\"\",\"event\":\"push\",\"link\":\"https://example.test/check/1\",\"name\":\"ci\",\"startedAt\":null,\"state\":\"SUCCESS\",\"workflow\":\"CI\"}]'\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"api\" && \"${2:-}\" == \"graphql\" ]]; then\n"
                "  cat <<'JSON'\n"
                "{\"data\":{\"repository\":{\"pullRequest\":{\"number\":7,\"title\":\"feat: ready\",\"url\":\"https://example.test/pr/7\",\"state\":\"OPEN\",\"isDraft\":true,\"baseRefName\":\"main\",\"headRefName\":\"feat/ready\",\"reviewDecision\":\"REVIEW_REQUIRED\",\"mergeable\":\"MERGEABLE\",\"mergeStateStatus\":\"CLEAN\",\"reviewRequests\":{\"nodes\":[]},\"latestReviews\":{\"nodes\":[]},\"reviewThreads\":{\"pageInfo\":{\"hasNextPage\":false,\"endCursor\":null},\"nodes\":[]}}}}}\n"
                "JSON\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"pr\" && \"${2:-}\" == \"ready\" ]]; then\n"
                "  exit 0\n"
                "fi\n"
                "echo \"unexpected gh command: $*\" >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FAKE_LOG"] = str(log_file)

            proc = run(
                [
                    "bash",
                    str(SCRIPTS_DIR / "pr-mark-ready.sh"),
                    "7",
                    "--repo",
                    "acme/widget",
                ],
                cwd=repo,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            calls = log_file.read_text(encoding="utf-8")
            self.assertIn("pr ready 7 --repo acme/widget", calls)


class SkillDocumentationTests(unittest.TestCase):
    def test_skill_docs_cover_raw_sync_worktrees_and_commit_bodies(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        checks = (ROOT / "references" / "CHECKLISTS.md").read_text(encoding="utf-8")
        conventional = (ROOT / "references" / "CONVENTIONAL_COMMITS.md").read_text(encoding="utf-8")
        routing = (ROOT / "references" / "SCRIPT_ROUTING.md").read_text(encoding="utf-8")

        self.assertIn("sync raw", skill.lower())
        self.assertIn("raw sync", skill.lower())
        self.assertIn("ship raw", skill.lower())
        self.assertIn("ship sync", skill.lower())
        self.assertIn("doctor", skill.lower())
        self.assertIn("ensure-worktree.sh", skill)
        self.assertIn("windows", skill.lower())
        self.assertIn("mandatory bullet-list body", conventional.lower())
        self.assertNotIn("headline-only is acceptable", conventional.lower())
        self.assertIn("auto-adopt the linked worktree", checks.lower())
        self.assertIn("sync-raw.sh", routing)
        self.assertIn("ship.sh", routing)
        self.assertIn("doctor.sh", routing)
        self.assertIn("reconcile-tree.sh", routing)
        self.assertIn("gitops-help.sh --json", skill)
        self.assertIn("gitops-help.sh", routing)


class GitOpsHelpScriptTests(unittest.TestCase):
    def test_default_help_lists_common_commands(self):
        proc = run(["bash", str(SCRIPTS_DIR / "gitops-help.sh")], cwd=ROOT, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = proc.stdout
        self.assertIn("ship raw", text)
        self.assertIn("ship sync", text)
        self.assertIn("ship ready", text)
        self.assertIn("sync raw", text)
        self.assertIn("doctor fix", text)
        self.assertIn("start work", text)

    def test_json_help_returns_stable_catalog(self):
        proc = run(["bash", str(SCRIPTS_DIR / "gitops-help.sh"), "--json"], cwd=ROOT, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["topic"], "all")
        self.assertGreater(len(payload["entries"]), 5)
        item = next(entry for entry in payload["entries"] if entry["id"] == "ship-raw")
        self.assertEqual(item["topic"], "ship")
        self.assertIn("ship raw", item["phrases"])
        self.assertEqual(item["script"], "ship.sh")
        self.assertIn("bash scripts/ship.sh", item["usage"])
        self.assertIn("details_source", item)
        self.assertTrue(item["supports_json"])
        self.assertTrue(item["stays_on_current_branch"])

    def test_topic_help_limits_output(self):
        proc = run(["bash", str(SCRIPTS_DIR / "gitops-help.sh"), "--topic", "ship"], cwd=ROOT, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = proc.stdout
        self.assertIn("Ship Workflows", text)
        self.assertIn("ship raw", text)
        self.assertNotIn("doctor fix", text)

    def test_verbose_help_includes_backing_script_help(self):
        proc = run(
            ["bash", str(SCRIPTS_DIR / "gitops-help.sh"), "--topic", "ship", "--verbose"],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = proc.stdout
        self.assertIn("== ship.sh ==", text)
        self.assertIn("Usage:", text)
        self.assertIn("ship raw", text)

    def test_invalid_topic_fails_cleanly(self):
        proc = run(
            ["bash", str(SCRIPTS_DIR / "gitops-help.sh"), "--topic", "unknown"],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("invalid --topic", proc.stderr)

if __name__ == "__main__":
    unittest.main()
