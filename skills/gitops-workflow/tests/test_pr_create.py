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
            self.assertIn("@gemini-code-assist", body)
            self.assertNotIn("<!-- 1–3 sentences", body)

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


if __name__ == "__main__":
    unittest.main()

