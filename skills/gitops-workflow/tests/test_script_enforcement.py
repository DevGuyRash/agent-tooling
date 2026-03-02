from __future__ import annotations

import os
import re
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
            SCRIPTS_DIR / "start-branch.sh",
            SCRIPTS_DIR / "install-hooks.sh",
            SCRIPTS_DIR / "setup-security.sh",
            SCRIPTS_DIR / "gh-scope-check.sh",
            SCRIPTS_DIR / "sensitive-scan.sh",
            SCRIPTS_DIR / "pr-create.sh",
            SCRIPTS_DIR / "pr-update-body.sh",
            SCRIPTS_DIR / "pr-labels-list.sh",
            SCRIPTS_DIR / "pr-template-discover.sh",
            SCRIPTS_DIR / "issue-template-discover.sh",
            SCRIPTS_DIR / "issue-create.sh",
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
                ],
                cwd=repo,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip()
            self.assertEqual(branch, "fix/issue-123")

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


class DeterministicGeneratorScriptTests(unittest.TestCase):
    def _init_repo(self, repo: Path):
        run(["git", "init"], cwd=repo)
        run(["git", "config", "user.name", "Test User"], cwd=repo)
        run(["git", "config", "user.email", "test@example.com"], cwd=repo)
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
    def test_pr_reply_normalizes_literal_newline_sequences(self):
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
                "    if [[ \"${!i}\" == \"-f\" ]]; then\n"
                "      next=$((i+1))\n"
                "      value=\"${!next}\"\n"
                "      if [[ \"$value\" == body=* ]]; then\n"
                "        printf '%s' \"${value#body=}\" > \"${BODY_CAPTURE}\"\n"
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


class PrMarkReadyScriptTests(unittest.TestCase):
    def test_pr_mark_ready_runs_gates_then_marks_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_bin = temp_path / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            log_file = temp_path / "calls.log"

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"pr\" && \"${2:-}\" == \"view\" ]]; then\n"
                "  echo \"true\"\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"api\" && \"${2:-}\" == \"graphql\" ]]; then\n"
                "  jq_expr=\"\"\n"
                "  for ((i=1; i<=$#; i++)); do\n"
                "    if [[ \"${!i}\" == \"--jq\" ]]; then\n"
                "      next=$((i+1))\n"
                "      jq_expr=\"${!next}\"\n"
                "      break\n"
                "    fi\n"
                "  done\n"
                "  if [[ \"$jq_expr\" == *\".data.repository.pullRequest.reviewThreads\"* ]]; then\n"
                "    echo '{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":false,\"endCursor\":null}}'\n"
                "    exit 0\n"
                "  fi\n"
                "  echo ''\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"pr\" && \"${2:-}\" == \"checks\" ]]; then\n"
                "  echo \"checks ok\"\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"pr\" && \"${2:-}\" == \"ready\" ]]; then\n"
                "  echo \"$*\" >> \"${FAKE_LOG}\"\n"
                "  exit 0\n"
                "fi\n"
                "echo \"$*\" >> \"${FAKE_LOG}\"\n"
                "exit 0\n",
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
                cwd=ROOT,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            calls = log_file.read_text(encoding="utf-8")
            self.assertIn("pr ready 7 --repo acme/widget", calls)

if __name__ == "__main__":
    unittest.main()
