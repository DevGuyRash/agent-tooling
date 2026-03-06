from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_SH = ROOT / "scripts" / "lib" / "bootstrap.sh"
BOOTSTRAP_PY = ROOT / "scripts" / "lib" / "bootstrap.py"


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
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init"], cwd=path)
    run(["git", "config", "user.email", "dev@example.com"], cwd=path)
    run(["git", "config", "user.name", "Dev"], cwd=path)


def write_shell_entrypoint(skill_root: Path, name: str, body: str) -> Path:
    script_dir = skill_root / "scripts"
    lib_dir = script_dir / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BOOTSTRAP_SH, lib_dir / "bootstrap.sh")
    (skill_root / "SKILL.md").write_text("# fixture\n", encoding="utf-8")
    script_path = script_dir / name
    script_path.write_text(body, encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


def write_python_entrypoint(skill_root: Path, name: str, body: str) -> Path:
    script_dir = skill_root / "scripts"
    lib_dir = script_dir / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BOOTSTRAP_PY, lib_dir / "bootstrap.py")
    (skill_root / "SKILL.md").write_text("# fixture\n", encoding="utf-8")
    script_path = script_dir / name
    script_path.write_text(body, encoding="utf-8")
    return script_path


class ShellEntrypointBootstrapTests(unittest.TestCase):
    def test_shell_entrypoint_prefers_repo_local_skill_copy_from_cwd(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            canonical_skill = temp_path / "canonical" / "skills" / "gitops-workflow"
            repo_root = temp_path / "repo"
            init_repo(repo_root)
            local_skill = repo_root / "skills" / "gitops-workflow"

            canonical = write_shell_entrypoint(
                canonical_skill,
                "demo.sh",
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "SCRIPT_DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd -P)\"\n"
                "source \"$SCRIPT_DIR/lib/bootstrap.sh\"\n"
                "gitops_workflow_maybe_reexec_repo_local_copy \"$SCRIPT_DIR\" \"demo.sh\" \"$@\"\n"
                "printf 'canonical\\n'\n",
            )
            write_shell_entrypoint(
                local_skill,
                "demo.sh",
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf 'local\\n'\n",
            )

            proc = run(["bash", str(canonical)], cwd=repo_root, check=False)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(proc.stdout.strip(), "local")

    def test_shell_entrypoint_uses_local_repo_hint_when_cwd_is_not_repo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            canonical_skill = temp_path / "canonical" / "skills" / "gitops-workflow"
            outside_dir = temp_path / "outside"
            outside_dir.mkdir(parents=True, exist_ok=True)
            repo_root = temp_path / "repo"
            init_repo(repo_root)
            local_skill = repo_root / "skills" / "gitops-workflow"

            canonical = write_shell_entrypoint(
                canonical_skill,
                "demo.sh",
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "SCRIPT_DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd -P)\"\n"
                "source \"$SCRIPT_DIR/lib/bootstrap.sh\"\n"
                "gitops_workflow_maybe_reexec_repo_local_copy \"$SCRIPT_DIR\" \"demo.sh\" \"$@\"\n"
                "printf 'canonical\\n'\n",
            )
            write_shell_entrypoint(
                local_skill,
                "demo.sh",
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf 'local\\n'\n",
            )

            proc = run(["bash", str(canonical), "--repo", str(repo_root)], cwd=outside_dir, check=False)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(proc.stdout.strip(), "local")

    def test_shell_entrypoint_ignores_remote_repo_slug_without_local_repo_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            canonical_skill = temp_path / "canonical" / "skills" / "gitops-workflow"
            outside_dir = temp_path / "outside"
            outside_dir.mkdir(parents=True, exist_ok=True)

            canonical = write_shell_entrypoint(
                canonical_skill,
                "demo.sh",
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "SCRIPT_DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd -P)\"\n"
                "source \"$SCRIPT_DIR/lib/bootstrap.sh\"\n"
                "gitops_workflow_maybe_reexec_repo_local_copy \"$SCRIPT_DIR\" \"demo.sh\" \"$@\"\n"
                "printf 'canonical\\n'\n",
            )

            proc = run(["bash", str(canonical), "--repo", "acme/widget"], cwd=outside_dir, check=False)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(proc.stdout.strip(), "canonical")


class PythonEntrypointBootstrapTests(unittest.TestCase):
    def test_python_entrypoint_prefers_repo_local_skill_copy_from_cwd(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            canonical_skill = temp_path / "canonical" / "skills" / "gitops-workflow"
            repo_root = temp_path / "repo"
            init_repo(repo_root)
            local_skill = repo_root / "skills" / "gitops-workflow"

            canonical = write_python_entrypoint(
                canonical_skill,
                "demo.py",
                "from __future__ import annotations\n"
                "import sys\n"
                "from pathlib import Path\n"
                "LIB_DIR = Path(__file__).resolve().parent / 'lib'\n"
                "if str(LIB_DIR) not in sys.path:\n"
                "    sys.path.insert(0, str(LIB_DIR))\n"
                "from bootstrap import maybe_reexec_repo_local_copy\n"
                "maybe_reexec_repo_local_copy(Path(__file__).resolve(), sys.argv)\n"
                "print('canonical')\n",
            )
            write_python_entrypoint(local_skill, "demo.py", "print('local')\n")

            proc = run(["python3", str(canonical)], cwd=repo_root, check=False)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(proc.stdout.strip(), "local")

    def test_python_entrypoint_uses_local_repo_hint_when_cwd_is_not_repo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            canonical_skill = temp_path / "canonical" / "skills" / "gitops-workflow"
            outside_dir = temp_path / "outside"
            outside_dir.mkdir(parents=True, exist_ok=True)
            repo_root = temp_path / "repo"
            init_repo(repo_root)
            local_skill = repo_root / "skills" / "gitops-workflow"

            canonical = write_python_entrypoint(
                canonical_skill,
                "demo.py",
                "from __future__ import annotations\n"
                "import sys\n"
                "from pathlib import Path\n"
                "LIB_DIR = Path(__file__).resolve().parent / 'lib'\n"
                "if str(LIB_DIR) not in sys.path:\n"
                "    sys.path.insert(0, str(LIB_DIR))\n"
                "from bootstrap import maybe_reexec_repo_local_copy\n"
                "maybe_reexec_repo_local_copy(Path(__file__).resolve(), sys.argv)\n"
                "print('canonical')\n",
            )
            write_python_entrypoint(local_skill, "demo.py", "print('local')\n")

            proc = run(["python3", str(canonical), "--repo", str(repo_root)], cwd=outside_dir, check=False)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(proc.stdout.strip(), "local")

    def test_python_entrypoint_ignores_remote_repo_slug_without_local_repo_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            canonical_skill = temp_path / "canonical" / "skills" / "gitops-workflow"
            outside_dir = temp_path / "outside"
            outside_dir.mkdir(parents=True, exist_ok=True)

            canonical = write_python_entrypoint(
                canonical_skill,
                "demo.py",
                "from __future__ import annotations\n"
                "import sys\n"
                "from pathlib import Path\n"
                "LIB_DIR = Path(__file__).resolve().parent / 'lib'\n"
                "if str(LIB_DIR) not in sys.path:\n"
                "    sys.path.insert(0, str(LIB_DIR))\n"
                "from bootstrap import maybe_reexec_repo_local_copy\n"
                "maybe_reexec_repo_local_copy(Path(__file__).resolve(), sys.argv)\n"
                "print('canonical')\n",
            )

            proc = run(["python3", str(canonical), "--repo", "acme/widget"], cwd=outside_dir, check=False)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(proc.stdout.strip(), "canonical")


if __name__ == "__main__":
    unittest.main()
