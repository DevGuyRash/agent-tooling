#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run_cmd(script: Path, *args: str, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=check,
        env=env,
    )
    return proc


def run_json(script: Path, *args: str, env: dict[str, str] | None = None) -> dict:
    proc = run_cmd(script, *args, env=env)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise AssertionError(f"expected JSON output, got: {proc.stdout!r}") from exc


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def assert_just_parses(justfile: Path) -> None:
    if not shutil.which("just"):
        return
    proc = subprocess.run(
        ["just", "--justfile", str(justfile), "--list"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Available recipes:" in proc.stdout, proc.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the project_harness generator.")
    parser.add_argument("--skill-root", required=True)
    args = parser.parse_args(argv)

    skill_root = Path(args.skill_root).resolve()
    script = skill_root / "scripts" / "project_harness.py"
    if not script.exists():
        raise SystemExit("missing project_harness.py")

    with tempfile.TemporaryDirectory(prefix="project-harness-smoke-") as tmp:
        tmpdir = Path(tmp)

        # 1) no-example repo -> placeholder harness, CI none
        repo1 = tmpdir / "generic"
        repo1.mkdir()
        write(repo1 / "README.md", "# generic\n")
        detected1 = run_json(script, "detect", str(repo1))
        assert detected1["selection_defaults"]["ci_mode"] == "none", detected1
        render1 = run_json(script, "render", str(repo1))
        just1 = (repo1 / ".local" / "harness" / "render" / "justfile").read_text(encoding="utf-8")
        assert "No native build surface was detected" in just1
        assert "ci.yml" not in render1["candidates"], render1

        # 2) single-package Node repo -> just CI with bootstrap and direct execution surfaces
        repo2 = tmpdir / "node"
        repo2.mkdir()
        write(repo2 / "package.json", json.dumps({
            "name": "node-app",
            "packageManager": "pnpm@10",
            "scripts": {
                "build": "node build.js",
                "test": "node test.js",
                "lint": "node lint.js"
            }
        }, indent=2) + "\n")
        write(repo2 / "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
        render2 = run_json(script, "render", str(repo2))
        assert "ci.yml" in render2["candidates"], render2
        ci2 = (repo2 / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert "extractions/setup-just@v3" in ci2, ci2
        assert "just bootstrap" in ci2, ci2
        assert "actions/setup-node@v6" in ci2, ci2
        assert "fetch-depth: 1" in ci2, ci2
        assert "cache: 'pnpm'" in ci2, ci2
        assert "cache-dependency-path: pnpm-lock.yaml" in ci2, ci2
        bootstrap2 = run_cmd(script, "bootstrap", str(repo2), "--dry-run")
        assert bootstrap2.stdout.strip() == "pnpm install --frozen-lockfile", bootstrap2.stdout
        run2 = run_cmd(script, "run", str(repo2), "test", "--dry-run")
        assert run2.stdout.strip() == "pnpm run test --if-present", run2.stdout
        doctor2 = run_json(script, "doctor", str(repo2), "--pretty")
        assert doctor2["tool_status"].get("pnpm") is not None, doctor2

        # 3) monorepo -> component-prefixed recipes
        repo3 = tmpdir / "mono"
        repo3.mkdir()
        write(repo3 / "backend" / "Cargo.toml", "[package]\nname = 'backend'\nversion = '0.1.0'\nedition = '2021'\n\n[[bin]]\nname = 'backend'\npath = 'src/main.rs'\n")
        write(repo3 / "backend" / "src" / "main.rs", "fn main() {}\n")
        write(repo3 / "frontend" / "package.json", json.dumps({
            "name": "frontend",
            "scripts": {"build": "vite build", "test": "vitest run", "lint": "eslint ."},
            "devDependencies": {"vite": "1.0.0", "vitest": "1.0.0", "eslint": "1.0.0"}
        }, indent=2) + "\n")
        write(repo3 / "frontend" / "package-lock.json", "{}\n")
        render3 = run_json(script, "render", str(repo3))
        just3 = (repo3 / ".local" / "harness" / "render" / "justfile").read_text(encoding="utf-8")
        assert "backend-build" in just3, just3
        assert "frontend-test" in just3, just3
        assert "ci.yml" in render3["candidates"], render3
        ci3 = (repo3 / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert "fetch-depth: 1" in ci3, ci3
        assert "cache-dependency-path: frontend/package-lock.json" in ci3, ci3
        assert render3["selected"]["ci_layout"] == "single", render3
        assert "  ci:\n" in ci3, ci3
        assert "  lint:\n" not in ci3, ci3
        render3_split = run_json(script, "render", str(repo3), "--ci-layout", "split")
        ci3_split = (repo3 / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert render3_split["selected"]["ci_layout"] == "split", render3_split
        assert "  ci:\n" not in ci3_split, ci3_split
        assert "  lint:\n" in ci3_split, ci3_split
        assert "    name: lint" in ci3_split, ci3_split
        assert "  test:\n" in ci3_split, ci3_split
        assert "    name: test" in ci3_split, ci3_split
        assert "  build:\n" in ci3_split, ci3_split
        assert "    name: build" in ci3_split, ci3_split
        render3_single = run_json(script, "render", str(repo3), "--ci-layout", "single")
        ci3_single = (repo3 / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert render3_single["selected"]["ci_layout"] == "single", render3_single
        assert "  ci:\n" in ci3_single, ci3_single
        assert "  lint:\n" not in ci3_single, ci3_single
        render3_paths = run_json(script, "render", str(repo3), "--ci-paths", "components")
        assert render3_paths["selected"]["ci_paths"] == "components", render3_paths
        ci3_paths = (repo3 / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert "    paths:\n" in ci3_paths, ci3_paths
        assert "      - 'backend/**'" in ci3_paths, ci3_paths
        assert "      - 'frontend/**'" in ci3_paths, ci3_paths

        repo3b = tmpdir / "components-only"
        repo3b.mkdir()
        write(repo3b / "backend" / "Cargo.toml", "[package]\nname = 'backend'\nversion = '0.1.0'\nedition = '2021'\n")
        write(repo3b / "backend" / "src" / "lib.rs", "pub fn ok() {}\n")
        write(repo3b / "frontend" / "package.json", json.dumps({
            "name": "frontend",
            "scripts": {"build": "vite build", "test": "vitest run", "lint": "eslint ."},
            "devDependencies": {"vite": "1.0.0", "vitest": "1.0.0", "eslint": "1.0.0"}
        }, indent=2) + "\n")
        write(repo3b / "frontend" / "package-lock.json", "{}\n")
        render3b_paths = run_json(script, "render", str(repo3b), "--ci-mode", "direct", "--ci-paths", "components")
        ci3b_paths = (repo3b / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert "    paths:\n" in ci3b_paths, ci3b_paths
        assert "      - 'backend/**'" in ci3b_paths, ci3b_paths
        assert "      - 'frontend/**'" in ci3b_paths, ci3b_paths
        assert "ci.yml" in render3b_paths["candidates"], render3b_paths
        assert "(cd 'backend' && cargo test " in ci3b_paths, ci3b_paths
        assert "(cd 'frontend' && npm ci)" in ci3b_paths, ci3b_paths
        assert "\n          cd 'backend' && cargo test " not in ci3b_paths, ci3b_paths

        repo3d = tmpdir / "rust-bins"
        repo3d.mkdir()
        write(repo3d / "cli-a" / "Cargo.toml", "[package]\nname = 'cli-a'\nversion = '0.1.0'\nedition = '2021'\n\n[[bin]]\nname = 'cli-a'\npath = 'src/main.rs'\n")
        write(repo3d / "cli-a" / "src" / "main.rs", "fn main() {}\n")
        write(repo3d / "cli-b" / "Cargo.toml", "[package]\nname = 'cli-b'\nversion = '0.1.0'\nedition = '2021'\n\n[[bin]]\nname = 'cli-b'\npath = 'src/main.rs'\n")
        write(repo3d / "cli-b" / "src" / "main.rs", "fn main() {}\n")
        render3d = run_json(script, "render", str(repo3d), "--architecture", "cross-os-dist")
        release3d = (repo3d / ".local" / "harness" / "render" / "release-cross-os.yml").read_text(encoding="utf-8")
        assert "release-cross-os.yml" in render3d["candidates"], render3d
        assert "(cd 'cli-a' && cargo build --release)" in release3d, release3d
        assert "(cd 'cli-b' && cargo build --release)" in release3d, release3d

        repo3c = tmpdir / "root-workspace"
        repo3c.mkdir()
        write(repo3c / "Cargo.toml", "[workspace]\nmembers = ['backend']\n")
        write(repo3c / "backend" / "Cargo.toml", "[package]\nname = 'backend'\nversion = '0.1.0'\nedition = '2021'\n")
        write(repo3c / "backend" / "src" / "lib.rs", "pub fn ok() {}\n")
        render3c_paths = run_json(script, "render", str(repo3c), "--ci-mode", "direct", "--ci-paths", "components")
        ci3c_paths = (repo3c / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert any("root-level components or workspace manifests" in warning for warning in render3c_paths["warnings"]), render3c_paths
        assert "    paths:\n" not in ci3c_paths, ci3c_paths

        repo3e = tmpdir / "guided-components"
        repo3e.mkdir()
        write(repo3e / "app" / "package.json", json.dumps({
            "name": "app",
            "scripts": {"test": "node test.js", "lint": "node lint.js"}
        }, indent=2) + "\n")
        write(repo3e / "app" / "package-lock.json", "{\n}\n")
        write(repo3e / "tools" / "internal" / "helper" / "package.json", json.dumps({
            "name": "helper"
        }, indent=2) + "\n")
        render3e = run_json(script, "render", str(repo3e))
        just3e = (repo3e / ".local" / "harness" / "render" / "justfile").read_text(encoding="utf-8")
        state3e = json.loads((repo3e / ".local" / "harness" / "state.json").read_text(encoding="utf-8"))
        helper3e = next(component for component in state3e["detected"]["components"] if component["path"] == "tools/internal/helper")
        app3e = next(component for component in state3e["detected"]["components"] if component["path"] == "app")
        assert app3e["promotion"] == "promoted", state3e
        assert app3e["runnable_surface"] is True, state3e
        assert helper3e["promotion"] == "candidate", state3e
        assert helper3e["runnable_surface"] is False, state3e
        assert "(cd 'app' && npm run test --if-present -- {{args}})" in just3e, just3e
        assert "tools-internal-helper-test" not in just3e, just3e
        assert "ci.yml" in render3e["candidates"], render3e
        ci3e = (repo3e / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert "cache-dependency-path: app/package-lock.json" in ci3e, ci3e
        assert "tools/internal/helper" not in ci3e, ci3e
        assert any("tools/internal/helper" in note for note in state3e["notes"]), state3e

        repo3f = tmpdir / "weak-manifest-only"
        repo3f.mkdir()
        write(repo3f / "tools" / "helper" / "package.json", json.dumps({
            "name": "helper"
        }, indent=2) + "\n")
        render3f = run_json(script, "render", str(repo3f))
        just3f = (repo3f / ".local" / "harness" / "render" / "justfile").read_text(encoding="utf-8")
        state3f = json.loads((repo3f / ".local" / "harness" / "state.json").read_text(encoding="utf-8"))
        helper3f = next(component for component in state3f["detected"]["components"] if component["path"] == "tools/helper")
        assert helper3f["promotion"] == "candidate", state3f
        assert helper3f["runnable_surface"] is False, state3f
        assert "No native build surface was detected" in just3f, just3f
        assert "tools-helper-test" not in just3f, just3f
        assert "ci.yml" not in render3f["candidates"], render3f

        repo3g = tmpdir / "cross-language-candidate"
        repo3g.mkdir()
        write(repo3g / "app" / "package.json", json.dumps({
            "name": "app",
            "scripts": {"test": "node test.js", "lint": "node lint.js"}
        }, indent=2) + "\n")
        write(repo3g / "app" / "package-lock.json", "{\n}\n")
        write(repo3g / "tools" / "helper" / "pyproject.toml", "[build-system]\nrequires = ['setuptools']\nbuild-backend = 'setuptools.build_meta'\n")
        render3g = run_json(script, "render", str(repo3g))
        state3g = json.loads((repo3g / ".local" / "harness" / "state.json").read_text(encoding="utf-8"))
        helper3g = next(component for component in state3g["detected"]["components"] if component["path"] == "tools/helper")
        assert render3g["selected"]["ci_mode"] == "just", render3g
        assert helper3g["promotion"] == "candidate", state3g
        ci3g = (repo3g / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert "actions/setup-node@v6" in ci3g, ci3g
        assert "actions/setup-python@v6" not in ci3g, ci3g

        # 4) dist renders keep justfiles parseable and clear stale candidates between runs
        repo4 = tmpdir / "dist-renders"
        repo4.mkdir()
        write(repo4 / "Cargo.toml", "[package]\nname = 'tool'\nversion = '0.1.0'\nedition = '2021'\n\n[[bin]]\nname = 'tool'\npath = 'src/main.rs'\n")
        write(repo4 / "src" / "main.rs", "fn main() {}\n")
        for architecture in ("local-dist", "committed-dist", "cross-os-dist"):
            render4 = run_json(script, "render", str(repo4), "--architecture", architecture, "--dist-storage", "git-lfs")
            just4 = repo4 / ".local" / "harness" / "render" / "justfile"
            just4_text = just4.read_text(encoding="utf-8")
            assert "# Internal helper that copies release outputs into dist/\n[private]\n_stage:" in just4_text, just4_text
            assert_just_parses(just4)
            if architecture in {"committed-dist", "cross-os-dist"}:
                assert ".gitattributes" in render4["candidates"], render4
            if architecture == "cross-os-dist":
                release4 = (repo4 / ".local" / "harness" / "render" / "release-cross-os.yml").read_text(encoding="utf-8")
                assert "fetch-depth: 1" in release4, release4
                assert "retention-days: 7" in release4, release4
        general4 = run_json(script, "render", str(repo4), "--architecture", "general", "--dist-storage", "none")
        assert ".gitattributes" not in general4["candidates"], general4
        assert not (repo4 / ".local" / "harness" / "render" / ".gitattributes").exists()

        # 5) Go recipes keep forwarded args before package targets
        repo5 = tmpdir / "go"
        repo5.mkdir()
        write(repo5 / "go.mod", "module example.com/tool\n\ngo 1.23.0\n")
        write(repo5 / "main.go", "package main\nfunc main() {}\n")
        render5 = run_json(script, "render", str(repo5))
        just5 = (repo5 / ".local" / "harness" / "render" / "justfile").read_text(encoding="utf-8")
        assert "go build {{args}} ./..." in just5, just5
        assert "go test {{args}} ./..." in just5, just5
        assert "ci.yml" in render5["candidates"], render5
        ci5 = (repo5 / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert "fetch-depth: 1" in ci5, ci5
        render5_paths = run_json(script, "render", str(repo5), "--ci-mode", "direct", "--ci-paths", "components")
        assert any("root-level components or workspace manifests" in warning for warning in render5_paths["warnings"]), render5_paths
        ci5_paths = (repo5 / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert "    paths:\n" not in ci5_paths, ci5_paths

        # 5b) Go workspace CI uses dependency-path-aware caching
        repo5b = tmpdir / "go-workspace"
        repo5b.mkdir()
        write(repo5b / "svc-a" / "go.mod", "module example.com/svc-a\n\ngo 1.23.0\n")
        write(repo5b / "svc-a" / "go.sum", "example.com/mod v1.0.0 h1:abc\n")
        write(repo5b / "svc-a" / "main.go", "package main\nfunc main() {}\n")
        write(repo5b / "svc-b" / "go.mod", "module example.com/svc-b\n\ngo 1.23.0\n")
        write(repo5b / "svc-b" / "go.sum", "example.com/mod v1.0.0 h1:def\n")
        write(repo5b / "svc-b" / "main.go", "package main\nfunc main() {}\n")
        render5b = run_json(script, "render", str(repo5b))
        ci5b = (repo5b / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert "cache-dependency-path: |" in ci5b, ci5b
        assert "svc-a/go.sum" in ci5b, ci5b
        assert "svc-b/go.sum" in ci5b, ci5b
        assert "ci.yml" in render5b["candidates"], render5b

        # 5c) Python and uv CI use dependency-aware caches
        repo5c = tmpdir / "python-caches"
        repo5c.mkdir()
        write(repo5c / "api" / "pyproject.toml", "[project]\nname = 'api'\nversion = '0.1.0'\n")
        write(repo5c / "api" / "poetry.lock", "[[package]]\nname = 'demo'\nversion = '0.1.0'\n")
        write(repo5c / "worker" / "pyproject.toml", "[project]\nname = 'worker'\nversion = '0.1.0'\n[tool.uv]\n")
        write(repo5c / "worker" / "uv.lock", "version = 1\n")
        render5c = run_json(script, "render", str(repo5c))
        ci5c = (repo5c / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert "cache: 'poetry'" in ci5c, ci5c
        assert "cache-dependency-path: |" in ci5c, ci5c
        assert "api/poetry.lock" in ci5c, ci5c
        assert "api/pyproject.toml" in ci5c, ci5c
        assert "enable-cache: true" in ci5c, ci5c
        assert "cache-dependency-glob: |" in ci5c, ci5c
        assert "worker/uv.lock" in ci5c, ci5c
        assert "ci.yml" in render5c["candidates"], render5c

        # 5d) dotnet setup stays valid without assuming an automatic cache layout
        repo5d = tmpdir / "dotnet-cache"
        repo5d.mkdir()
        write(repo5d / "app" / "app.csproj", "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><OutputType>Exe</OutputType></PropertyGroup></Project>\n")
        write(repo5d / "app" / "packages.lock.json", "{\n  \"version\": 1\n}\n")
        render5d = run_json(script, "render", str(repo5d))
        ci5d = (repo5d / ".local" / "harness" / "render" / "ci.yml").read_text(encoding="utf-8")
        assert "uses: actions/setup-dotnet@v4" in ci5d, ci5d
        assert "cache: true" not in ci5d, ci5d
        assert "cache-dependency-path" not in ci5d, ci5d
        assert "ci.yml" in render5d["candidates"], render5d

        # 6) unmanaged targets stay untouched during update
        repo6 = tmpdir / "unmanaged-update"
        repo6.mkdir()
        write(repo6 / "package.json", json.dumps({
            "name": "keep-user-files",
            "scripts": {"test": "node test.js"}
        }, indent=2) + "\n")
        write(repo6 / "justfile", "user-managed: \n\t@echo keep\n")
        write(repo6 / ".github" / "workflows" / "ci.yml", "name: user-ci\n")
        update6 = run_json(script, "update", str(repo6))
        assert update6["candidate_only"] == [".github/workflows/ci.yml", "justfile"] or update6["candidate_only"] == ["justfile", ".github/workflows/ci.yml"], update6
        assert (repo6 / "justfile").read_text(encoding="utf-8") == "user-managed: \n\t@echo keep\n"
        assert (repo6 / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8") == "name: user-ci\n"
        assert (repo6 / ".local" / "harness" / "render" / "justfile").exists()

        # 7) managed Git LFS rule is reversible when the selection changes away from committed dist
        repo7 = tmpdir / "lfs-migrate"
        repo7.mkdir()
        write(repo7 / "Cargo.toml", "[package]\nname = 'tool'\nversion = '0.1.0'\nedition = '2021'\n\n[[bin]]\nname = 'tool'\npath = 'src/main.rs'\n")
        write(repo7 / "src" / "main.rs", "fn main() {}\n")
        run_json(script, "update", str(repo7), "--architecture", "cross-os-dist", "--dist-storage", "git-lfs")
        gitattributes7 = (repo7 / ".gitattributes").read_text(encoding="utf-8")
        assert "dist/** filter=lfs diff=lfs merge=lfs -text" in gitattributes7, gitattributes7
        run_json(script, "update", str(repo7), "--architecture", "general", "--dist-storage", "none")
        if (repo7 / ".gitattributes").exists():
            assert "dist/** filter=lfs diff=lfs merge=lfs -text" not in (repo7 / ".gitattributes").read_text(encoding="utf-8")

        # 8) corrupt state is preserved and surfaced instead of disappearing silently
        repo8 = tmpdir / "corrupt-state"
        repo8.mkdir()
        write(repo8 / "package.json", json.dumps({"name": "corrupt-state"}, indent=2) + "\n")
        write(repo8 / ".local" / "harness" / "state.json", "{not json\n")
        render8 = run_json(script, "render", str(repo8))
        assert any("state.json.corrupt" in warning for warning in render8["warnings"]), render8
        assert (repo8 / ".local" / "harness" / "state.json.corrupt").exists()
        state8 = json.loads((repo8 / ".local" / "harness" / "state.json").read_text(encoding="utf-8"))
        assert any("state.json.corrupt" in warning for warning in state8["warnings"]), state8

        # 9) dist warning and persisted state cover negative recovery branches
        repo9 = tmpdir / "negative-dist"
        repo9.mkdir()
        write(repo9 / ".gitignore", "dist/\n")
        render9 = run_json(script, "render", str(repo9), "--architecture", "cross-os-dist", "--dist-storage", "git")
        assert any("dist section was omitted" in warning for warning in render9["warnings"]), render9
        update9 = run_json(script, "update", str(repo9), "--architecture", "cross-os-dist", "--dist-storage", "git")
        assert any("dist/ is ignored" in warning for warning in update9["warnings"]), update9
        state9 = json.loads((repo9 / ".local" / "harness" / "state.json").read_text(encoding="utf-8"))
        assert any("dist/ is ignored" in warning for warning in state9["warnings"]), state9

        # 10) existing justfiles execute recipes without shell interpolation
        repo10 = tmpdir / "safe-run"
        repo10.mkdir()
        write(repo10 / "justfile", "# project-harness: managed-file\ntest:\n    @echo ok\n")
        fake_bin = tmpdir / "bin"
        fake_bin.mkdir()
        write(fake_bin / "just", "#!/usr/bin/env sh\nprintf '%s\\n' \"$@\"\n")
        os.chmod(fake_bin / "just", 0o755)
        marker10 = repo10 / "injected.txt"
        env10 = os.environ.copy()
        env10["PATH"] = str(fake_bin) + os.pathsep + env10.get("PATH", "")
        proc10 = run_cmd(
            script,
            "run",
            str(repo10),
            f"test; printf injected > {marker10}",
            env=env10,
        )
        assert proc10.returncode == 0, proc10.stderr
        assert not marker10.exists(), proc10.stdout

    print("project_harness smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
