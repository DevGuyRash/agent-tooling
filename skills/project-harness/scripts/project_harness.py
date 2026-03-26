#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = SKILL_ROOT / "assets"
STATE_VERSION = "2.2.0"
MANAGED_MARKER = "# project-harness: managed-file"
IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".local",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "target",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".turbo",
    ".cache",
    "coverage",
    ".mypy_cache",
}

TASKFILE_NAMES = {"Taskfile.yml", "Taskfile.yaml", "taskfile.yml", "taskfile.yaml"}

CANONICAL_ALIASES = {
    "build": ["build"],
    "release": ["release"],
    "test": ["test"],
    "lint": ["lint"],
    "fmt": ["fmt", "format"],
    "fmt-check": ["fmt-check", "format-check", "fmtcheck", "check-format", "checkfmt", "format:check", "fmt:check"],
    "clean": ["clean"],
    "bootstrap": ["bootstrap", "setup", "install"],
    "ci": ["ci", "check"],
    "dev": ["dev", "start", "serve"],
}

NODE_FRAMEWORKS = {
    "next": "nextjs",
    "nuxt": "nuxt",
    "@remix-run/dev": "remix",
    "@sveltejs/kit": "sveltekit",
    "vite": "vite",
    "astro": "astro",
    "@nestjs/core": "nestjs",
}

PYTHON_FRAMEWORKS = {
    "django": "django",
    "flask": "flask",
    "fastapi": "fastapi",
}

OTHER_FRAMEWORK_HINTS = {
    "spring-boot": "spring-boot",
    "phoenix": "phoenix",
    "rails": "rails",
}


def eprint(msg: str) -> None:
    sys.stderr.write(msg + "\n")


def fail(message: str, hint: str | None = None, code: int = 1) -> int:
    eprint(f"error: {message}")
    if hint:
        eprint(f"hint: {hint}")
    return code


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def relpath(path: Path, root: Path) -> str:
    try:
        value = path.relative_to(root).as_posix()
    except ValueError:
        value = path.as_posix()
    return "." if value == "" else value


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def read_toml(path: Path) -> dict[str, Any]:
    if tomllib is None:
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_xml_text(path: Path) -> str:
    return read_text(path)


def walk_repo(repo: Path):
    for current, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        yield Path(current), files


def unique_sorted(values: list[str]) -> list[str]:
    return sorted({v for v in values if v})


def find_file(repo: Path, names: set[str]) -> list[Path]:
    hits: list[Path] = []
    for current, files in walk_repo(repo):
        for name in files:
            if name in names:
                hits.append(current / name)
    return hits


def parse_make_targets(path: Path) -> list[str]:
    targets: list[str] = []
    pattern = re.compile(r"^([A-Za-z0-9_.-]+)\s*:\s*")
    for line in read_text(path).splitlines():
        if line.startswith("\t") or line.startswith(" ") or line.startswith("."):
            continue
        match = pattern.match(line)
        if not match:
            continue
        target = match.group(1)
        if "%" in target or "/" in target:
            continue
        targets.append(target)
    return unique_sorted(targets)


def parse_taskfile_targets(path: Path) -> list[str]:
    targets: list[str] = []
    in_tasks = False
    for line in read_text(path).splitlines():
        if line.strip() == "tasks:":
            in_tasks = True
            continue
        if not in_tasks:
            continue
        if re.match(r"^[A-Za-z0-9_.-]", line):
            break
        match = re.match(r"^\s{2}([A-Za-z0-9_.-]+):\s*$", line)
        if match:
            targets.append(match.group(1))
    return unique_sorted(targets)


def task_target_map(targets: list[str], runner: str) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for canonical, aliases in CANONICAL_ALIASES.items():
        for alias in aliases:
            if alias in targets:
                mapped[canonical] = f"{runner} {alias}"
                break
    return mapped


def package_manager_from_package_json(package_json: dict[str, Any], directory: Path) -> str:
    package_manager = package_json.get("packageManager")
    if isinstance(package_manager, str):
        if package_manager.startswith("pnpm@"):
            return "pnpm"
        if package_manager.startswith("yarn@"):
            return "yarn"
        if package_manager.startswith("bun@"):
            return "bun"
        if package_manager.startswith("npm@"):
            return "npm"
    if (directory / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (directory / "yarn.lock").exists():
        return "yarn"
    if (directory / "bun.lockb").exists() or (directory / "bun.lock").exists():
        return "bun"
    return "npm"


def detect_node_frameworks(package_json: dict[str, Any]) -> list[str]:
    frameworks: list[str] = []
    deps: dict[str, Any] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        value = package_json.get(key)
        if isinstance(value, dict):
            deps.update(value)
    for dep, framework in NODE_FRAMEWORKS.items():
        if dep in deps:
            frameworks.append(framework)
    return unique_sorted(frameworks)


def detect_python_frameworks_from_pyproject(pyproject: dict[str, Any]) -> list[str]:
    text = json.dumps(pyproject).lower()
    hits: list[str] = []
    for dep, framework in PYTHON_FRAMEWORKS.items():
        if dep in text:
            hits.append(framework)
    return unique_sorted(hits)


def detect_components(repo: Path) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    languages: list[str] = []
    build_tools: list[str] = []
    frameworks: list[str] = []
    package_managers: list[str] = []
    binary_targets: list[str] = []
    task_runners: list[str] = []
    ci_systems: list[str] = []

    root_justfile = repo / "justfile"
    if root_justfile.exists():
        task_runners.append("just")

    root_makefile = repo / "Makefile"
    if root_makefile.exists():
        task_runners.append("make")

    root_taskfile = next((repo / name for name in TASKFILE_NAMES if (repo / name).exists()), None)
    if root_taskfile is not None:
        task_runners.append("task")

    github_workflows = list((repo / ".github" / "workflows").glob("*.yml")) + list((repo / ".github" / "workflows").glob("*.yaml"))
    if github_workflows:
        ci_systems.append("github-actions")
    if (repo / ".gitlab-ci.yml").exists():
        ci_systems.append("gitlab-ci")
    if (repo / ".circleci" / "config.yml").exists():
        ci_systems.append("circleci")
    if (repo / "azure-pipelines.yml").exists():
        ci_systems.append("azure-pipelines")

    make_targets = parse_make_targets(root_makefile) if root_makefile.exists() else []
    task_targets = parse_taskfile_targets(root_taskfile) if root_taskfile is not None else []

    # Rust
    for cargo_toml in find_file(repo, {"Cargo.toml"}):
        data = read_toml(cargo_toml)
        cargo_dir = cargo_toml.parent
        package = data.get("package", {}) if isinstance(data, dict) else {}
        workspace = isinstance(data.get("workspace"), dict)
        bins: list[str] = []
        for item in data.get("bin", []) if isinstance(data.get("bin"), list) else []:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                bins.append(item["name"])
        if not bins and isinstance(package, dict) and isinstance(package.get("name"), str):
            if (cargo_dir / "src" / "main.rs").exists():
                bins.append(str(package["name"]))
        components.append({
            "path": relpath(cargo_dir, repo),
            "language": "rust",
            "build_tool": "cargo",
            "workspace": workspace,
            "binary_targets": unique_sorted(bins),
        })
        languages.append("rust")
        build_tools.append("cargo")
        binary_targets.extend(bins)

    # Node / TypeScript
    for package_json_path in find_file(repo, {"package.json"}):
        package_dir = package_json_path.parent
        try:
            package_json = read_json(package_json_path)
        except Exception:
            package_json = {}
        scripts = package_json.get("scripts", {}) if isinstance(package_json.get("scripts"), dict) else {}
        manager = package_manager_from_package_json(package_json, package_dir)
        components.append({
            "path": relpath(package_dir, repo),
            "language": "javascript",
            "build_tool": "package-json",
            "package_manager": manager,
            "scripts": sorted(scripts.keys()),
            "workspace": bool(package_json.get("workspaces")) or (package_dir / "pnpm-workspace.yaml").exists(),
        })
        languages.append("javascript")
        build_tools.append("package-json")
        package_managers.append(manager)
        frameworks.extend(detect_node_frameworks(package_json))
        if scripts:
            task_runners.append("package-scripts")

    pyproject_hits = find_file(repo, {"pyproject.toml"})

    # Python
    for pyproject in pyproject_hits:
        py_dir = pyproject.parent
        data = read_toml(pyproject)
        tool = data.get("tool", {}) if isinstance(data, dict) else {}
        manager = "pip"
        if (py_dir / "uv.lock").exists() or isinstance(tool.get("uv"), dict):
            manager = "uv"
        elif (py_dir / "poetry.lock").exists() or isinstance(tool.get("poetry"), dict):
            manager = "poetry"
        elif (py_dir / "requirements.txt").exists():
            manager = "pip"
        components.append({
            "path": relpath(py_dir, repo),
            "language": "python",
            "build_tool": manager,
            "workspace": False,
        })
        languages.append("python")
        build_tools.append(manager)
        package_managers.append(manager)
        frameworks.extend(detect_python_frameworks_from_pyproject(data))

    if not pyproject_hits and (repo / "setup.py").exists():
        components.append({"path": ".", "language": "python", "build_tool": "pip", "workspace": False})
        languages.append("python")
        build_tools.append("pip")
        package_managers.append("pip")

    # Go
    for go_mod in find_file(repo, {"go.mod"}):
        go_dir = go_mod.parent
        bins: list[str] = []
        cmd_dir = go_dir / "cmd"
        if cmd_dir.exists():
            for child in cmd_dir.iterdir():
                if child.is_dir() and any(p.name == "main.go" for p in child.rglob("main.go")):
                    bins.append(child.name)
        elif (go_dir / "main.go").exists():
            bins.append(go_dir.name if go_dir != repo else repo.name)
        components.append({
            "path": relpath(go_dir, repo),
            "language": "go",
            "build_tool": "go",
            "workspace": False,
            "binary_targets": unique_sorted(bins),
        })
        languages.append("go")
        build_tools.append("go")
        binary_targets.extend(bins)

    # C / C++
    for cmake in find_file(repo, {"CMakeLists.txt"}):
        cpp_dir = cmake.parent
        components.append({
            "path": relpath(cpp_dir, repo),
            "language": "cpp",
            "build_tool": "cmake",
            "workspace": False,
        })
        languages.append("cpp")
        build_tools.append("cmake")

    # Ruby
    for gemfile in find_file(repo, {"Gemfile"}):
        ruby_dir = gemfile.parent
        components.append({
            "path": relpath(ruby_dir, repo),
            "language": "ruby",
            "build_tool": "bundler",
            "workspace": False,
        })
        languages.append("ruby")
        build_tools.append("bundler")
        if (ruby_dir / "config" / "routes.rb").exists():
            frameworks.append("rails")

    # Elixir
    for mix_exs in find_file(repo, {"mix.exs"}):
        mix_dir = mix_exs.parent
        components.append({
            "path": relpath(mix_dir, repo),
            "language": "elixir",
            "build_tool": "mix",
            "workspace": False,
        })
        languages.append("elixir")
        build_tools.append("mix")
        if (mix_dir / "lib").exists() and any("phoenix" in p.name.lower() for p in mix_dir.rglob("*phoenix*")):
            frameworks.append("phoenix")

    # Java / Kotlin Gradle
    for gradle in find_file(repo, {"build.gradle", "build.gradle.kts"}):
        gradle_dir = gradle.parent
        components.append({
            "path": relpath(gradle_dir, repo),
            "language": "java",
            "build_tool": "gradle",
            "workspace": (gradle_dir / "settings.gradle").exists() or (gradle_dir / "settings.gradle.kts").exists(),
        })
        languages.append("java")
        build_tools.append("gradle")
        gradle_text = read_text(gradle).lower()
        if "spring-boot" in gradle_text:
            frameworks.append("spring-boot")

    # Maven
    for pom in find_file(repo, {"pom.xml"}):
        pom_dir = pom.parent
        pom_text = read_xml_text(pom)
        if "spring-boot" in pom_text.lower():
            frameworks.append("spring-boot")
        components.append({
            "path": relpath(pom_dir, repo),
            "language": "java",
            "build_tool": "maven",
            "workspace": "<modules>" in pom_text,
        })
        languages.append("java")
        build_tools.append("maven")

    # .NET
    sln_hits = list(repo.rglob("*.sln"))
    csproj_hits = list(repo.rglob("*.csproj"))
    if sln_hits or csproj_hits:
        roots = {p.parent for p in sln_hits + csproj_hits}
        for dotnet_dir in sorted(roots):
            binaries: list[str] = []
            for csproj in dotnet_dir.glob("*.csproj"):
                csproj_text = read_text(csproj)
                if "<OutputType>Exe</OutputType>" in csproj_text or "<OutputType>WinExe</OutputType>" in csproj_text:
                    binaries.append(csproj.stem)
            components.append({
                "path": relpath(dotnet_dir, repo),
                "language": "dotnet",
                "build_tool": "dotnet",
                "workspace": bool(list(dotnet_dir.glob("*.sln"))),
                "binary_targets": unique_sorted(binaries),
            })
            languages.append("dotnet")
            build_tools.append("dotnet")
            binary_targets.extend(binaries)

    # Zig
    for build_zig in find_file(repo, {"build.zig"}):
        zig_dir = build_zig.parent
        components.append({
            "path": relpath(zig_dir, repo),
            "language": "zig",
            "build_tool": "zig",
            "workspace": False,
        })
        languages.append("zig")
        build_tools.append("zig")

    dockerfiles: list[str] = []
    for current, files in walk_repo(repo):
        for name in files:
            if name == "Dockerfile" or name.startswith("Dockerfile."):
                dockerfiles.append(relpath(current / name, repo))
    docker = {
        "dockerfiles": unique_sorted(dockerfiles),
        "compose_files": [relpath(p, repo) for p in find_file(repo, {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"})],
    }

    dist_dir = repo / "dist"
    dist_exists = dist_dir.exists()
    dist_os_subdirs = False
    if dist_exists:
        for child in dist_dir.iterdir():
            if child.is_dir() and re.fullmatch(r"[A-Za-z0-9_.-]+-[A-Za-z0-9_.-]+", child.name):
                dist_os_subdirs = True
                break

    gitignore_text = read_text(repo / ".gitignore") if (repo / ".gitignore").exists() else ""
    dist_ignored = bool(re.search(r"(?m)^(?:/)?dist/\s*$", gitignore_text))
    local_ignored = bool(re.search(r"(?m)^(?:/)?\.local/\s*$", gitignore_text))

    gitattributes_text = read_text(repo / ".gitattributes") if (repo / ".gitattributes").exists() else ""
    dist_lfs_tracked = bool(re.search(r"(?m)^dist(?:/\*\*|/\*)?\s+.*\bfilter=lfs\b", gitattributes_text))

    distribution_hints = {
        "has_compiled_binaries": bool(binary_targets),
        "binary_targets": unique_sorted(binary_targets),
        "dist_exists": dist_exists,
        "dist_os_subdirs": dist_os_subdirs,
        "dist_ignored": dist_ignored,
        "dist_lfs_tracked": dist_lfs_tracked,
        "local_ignored": local_ignored,
    }

    selection_defaults = {
        "architecture": choose_architecture(distribution_hints),
        "ci_mode": choose_ci_mode(unique_sorted(languages), unique_sorted(ci_systems), components, unique_sorted(task_runners)),
        "release_overlay": bool(binary_targets and not dist_exists),
        "dist_storage": "git-lfs" if dist_lfs_tracked else ("git" if dist_exists and not dist_ignored else ("artifacts" if binary_targets else "none")),
    }

    detected = {
        "repo_root": str(repo.resolve()),
        "languages": unique_sorted(languages),
        "build_tools": unique_sorted(build_tools),
        "frameworks": unique_sorted(frameworks),
        "components": dedupe_components(components),
        "package_managers": unique_sorted(package_managers),
        "task_runners": unique_sorted(task_runners),
        "ci_systems": unique_sorted(ci_systems),
        "docker": docker,
        "distribution_hints": distribution_hints,
        "selection_defaults": selection_defaults,
        "make_targets": make_targets,
        "task_targets": task_targets,
    }
    detected["notes"] = derive_notes(detected)
    return detected


def dedupe_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for component in sorted(components, key=lambda c: (c["path"], c["language"], c["build_tool"])):
        key = (component["path"], component["language"], component["build_tool"])
        if key in seen:
            continue
        seen.add(key)
        out.append(component)
    return out


def choose_architecture(distribution_hints: dict[str, Any]) -> str:
    if distribution_hints.get("dist_os_subdirs"):
        return "cross-os-dist"
    if distribution_hints.get("dist_exists") and not distribution_hints.get("dist_ignored"):
        return "committed-dist"
    if distribution_hints.get("dist_exists") and distribution_hints.get("dist_ignored"):
        return "local-dist"
    return "general"


def choose_ci_mode(languages: list[str], ci_systems: list[str], components: list[dict[str, Any]], task_runners: list[str]) -> str:
    if any(system != "github-actions" for system in ci_systems):
        return "none"
    if not languages and not components and not task_runners:
        return "none"
    if ci_systems:
        return "direct"
    if len(languages) > 1 or len(components) > 1:
        return "direct"
    return "just"


def derive_notes(detected: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    components = detected.get("components", [])
    task_runners = detected.get("task_runners", [])
    hints = detected.get("distribution_hints", {})
    if not components and not task_runners:
        notes.append("No build tool or task runner was detected. Generate a placeholder harness and replace the canonical recipes with project-specific commands.")
    if hints.get("has_compiled_binaries") and not hints.get("dist_exists"):
        notes.append("Compiled binary targets were detected without an existing dist/. Choose explicitly between local-dist, committed-dist, cross-os-dist, or CI-built artifacts.")
    if hints.get("dist_exists") and not hints.get("dist_ignored") and not hints.get("dist_lfs_tracked"):
        notes.append("Committed dist/ outputs will add binary blobs to Git history over time. Prefer Git LFS or CI-built release assets when binaries are large or change frequently.")
    if hints.get("dist_lfs_tracked"):
        notes.append("dist/ appears to be tracked by Git LFS. Verify archive behavior and bandwidth settings before relying on repository ZIP downloads.")
    if any(system != "github-actions" for system in detected.get("ci_systems", [])):
        notes.append("A non-GitHub CI system is present, so GitHub workflow generation defaults to none unless you override it.")
    if len(components) > 1:
        notes.append("Multiple components were detected. Prefer component-prefixed recipes plus aggregate top-level recipes.")
    return notes


def shell_quote_path(path: str) -> str:
    if path in (".", ""):
        return "."
    return "'" + path.replace("'", "'\"'\"'") + "'"


def component_prefix(component: dict[str, Any]) -> str:
    path = component["path"]
    if path == ".":
        return component["language"]
    return path.replace("/", "-").replace("_", "-")


def component_cd(command: str, component: dict[str, Any]) -> str:
    path = component["path"]
    if path == ".":
        return command
    return f"cd {shell_quote_path(path)} && {command}"


def manager_script_command(manager: str, script: str, *, passthrough_args: bool = False) -> str:
    passthrough = " {{args}}" if passthrough_args else ""
    if manager == "npm":
        return f"npm run {script} --if-present" + (" -- {{args}}" if passthrough_args else "")
    if manager == "pnpm":
        return f"pnpm run {script} --if-present" + (" -- {{args}}" if passthrough_args else "")
    if manager == "yarn":
        return f"yarn run {script}{passthrough}"
    if manager == "bun":
        return f"bun run {script}{passthrough}"
    return f"npm run {script} --if-present" + (" -- {{args}}" if passthrough_args else "")


def node_component_commands(component: dict[str, Any], repo: Path) -> dict[str, list[str]]:
    package_path = repo / component["path"] / "package.json" if component["path"] != "." else repo / "package.json"
    package_json = read_json(package_path) if package_path.exists() else {}
    scripts = package_json.get("scripts", {}) if isinstance(package_json.get("scripts"), dict) else {}
    manager = component.get("package_manager", "npm")

    commands: dict[str, list[str]] = {
        "build": [],
        "release": [],
        "test": [],
        "lint": [],
        "fmt": [],
        "fmt-check": [],
        "clean": [],
        "bootstrap": [],
        "dev": [],
    }

    if scripts:
        if "build" in scripts:
            commands["build"].append(component_cd(manager_script_command(manager, "build", passthrough_args=True), component))
        if "release" in scripts:
            commands["release"].append(component_cd(manager_script_command(manager, "release", passthrough_args=True), component))
        if "test" in scripts:
            commands["test"].append(component_cd(manager_script_command(manager, "test", passthrough_args=True), component))
        if "lint" in scripts:
            commands["lint"].append(component_cd(manager_script_command(manager, "lint"), component))
        if "fmt" in scripts:
            commands["fmt"].append(component_cd(manager_script_command(manager, "fmt"), component))
        elif "format" in scripts:
            commands["fmt"].append(component_cd(manager_script_command(manager, "format"), component))
        if "fmt:check" in scripts:
            commands["fmt-check"].append(component_cd(manager_script_command(manager, "fmt:check"), component))
        elif "format:check" in scripts:
            commands["fmt-check"].append(component_cd(manager_script_command(manager, "format:check"), component))
        if "clean" in scripts:
            commands["clean"].append(component_cd(manager_script_command(manager, "clean"), component))
        if "bootstrap" in scripts:
            commands["bootstrap"].append(component_cd(manager_script_command(manager, "bootstrap"), component))
        if "dev" in scripts:
            commands["dev"].append(component_cd(manager_script_command(manager, "dev"), component))
        elif "start" in scripts:
            commands["dev"].append(component_cd(manager_script_command(manager, "start"), component))

    if not commands["bootstrap"]:
        if manager == "pnpm":
            commands["bootstrap"].append(component_cd("pnpm install --frozen-lockfile", component))
        elif manager == "yarn":
            commands["bootstrap"].append(component_cd("yarn install", component))
        elif manager == "bun":
            commands["bootstrap"].append(component_cd("bun install", component))
        else:
            commands["bootstrap"].append(component_cd("npm ci", component))

    deps_text = json.dumps(package_json).lower()
    if not commands["build"] and "vite" in deps_text:
        commands["build"].append(component_cd("npx vite build {{args}}", component))
    if not commands["dev"] and "vite" in deps_text:
        commands["dev"].append(component_cd("npx vite", component))
    if not commands["test"] and "vitest" in deps_text:
        commands["test"].append(component_cd("npx vitest run {{args}}", component))
    if not commands["test"] and '"jest"' in deps_text:
        commands["test"].append(component_cd("npx jest {{args}}", component))
    if not commands["fmt"] and "prettier" in deps_text:
        commands["fmt"].append(component_cd("npx prettier --write .", component))
    if not commands["fmt-check"] and "prettier" in deps_text:
        commands["fmt-check"].append(component_cd("npx prettier --check .", component))
    if not commands["lint"] and "eslint" in deps_text:
        commands["lint"].append(component_cd("npx eslint .", component))
    return commands


def python_component_commands(component: dict[str, Any], repo: Path) -> dict[str, list[str]]:
    tool = component["build_tool"]
    component_root = repo / component["path"] if component["path"] != "." else repo
    has_build_system = (component_root / "pyproject.toml").exists() or (component_root / "setup.py").exists()
    has_requirements = (component_root / "requirements.txt").exists()
    has_dev_requirements = (component_root / "requirements-dev.txt").exists()
    commands: dict[str, list[str]] = {
        "build": [],
        "release": [],
        "test": [],
        "lint": [],
        "fmt": [],
        "fmt-check": [],
        "clean": [],
        "bootstrap": [],
        "dev": [],
    }
    if tool == "uv":
        commands["build"].append(component_cd("uv build", component))
        commands["release"].append(component_cd("uv build", component))
        commands["test"].append(component_cd("uv run pytest {{args}}", component))
        commands["lint"].append(component_cd("uv run ruff check .", component))
        commands["fmt"].append(component_cd("uv run ruff format .", component))
        commands["fmt-check"].append(component_cd("uv run ruff format --check .", component))
        commands["clean"].append(component_cd("rm -rf dist build .pytest_cache .ruff_cache", component))
        commands["bootstrap"].append(component_cd("uv sync", component))
    elif tool == "poetry":
        commands["build"].append(component_cd("poetry build", component))
        commands["release"].append(component_cd("poetry build", component))
        commands["test"].append(component_cd("poetry run pytest {{args}}", component))
        commands["lint"].append(component_cd("poetry run ruff check .", component))
        commands["fmt"].append(component_cd("poetry run ruff format .", component))
        commands["fmt-check"].append(component_cd("poetry run ruff format --check .", component))
        commands["clean"].append(component_cd("rm -rf dist build .pytest_cache .ruff_cache", component))
        commands["bootstrap"].append(component_cd("poetry install", component))
    else:
        if has_build_system:
            commands["build"].append(component_cd("python -m build", component))
            commands["release"].append(component_cd("python -m build", component))
        commands["test"].append(component_cd("python -m pytest {{args}}", component))
        commands["lint"].append(component_cd("ruff check .", component))
        commands["fmt"].append(component_cd("ruff format .", component))
        commands["fmt-check"].append(component_cd("ruff format --check .", component))
        commands["clean"].append(component_cd("rm -rf dist build *.egg-info .pytest_cache .ruff_cache", component))
        if has_dev_requirements:
            commands["bootstrap"].append(component_cd("python -m pip install -r requirements-dev.txt", component))
        elif has_requirements:
            commands["bootstrap"].append(component_cd("python -m pip install -r requirements.txt", component))
        elif has_build_system:
            commands["bootstrap"].append(component_cd('python -m pip install -e ".[dev]" || python -m pip install -e .', component))
        else:
            commands["bootstrap"].append(component_cd("python -m pip install --upgrade pip pytest ruff build", component))
    return commands


def rust_component_commands(component: dict[str, Any]) -> dict[str, list[str]]:
    commands: dict[str, list[str]] = {
        "build": [component_cd("cargo build {{args}}", component)],
        "release": [component_cd("cargo build --release", component)],
        "test": [component_cd("cargo test {{args}}", component)],
        "lint": [component_cd("cargo clippy -- -D warnings", component)],
        "fmt": [component_cd("cargo fmt", component)],
        "fmt-check": [component_cd("cargo fmt --check", component)],
        "clean": [component_cd("cargo clean", component)],
        "bootstrap": [component_cd("cargo fetch", component)],
        "dev": [],
    }
    if component.get("workspace"):
        commands["build"] = [component_cd("cargo build --workspace {{args}}", component)]
        commands["release"] = [component_cd("cargo build --workspace --release", component)]
        commands["test"] = [component_cd("cargo test --workspace {{args}}", component)]
        commands["lint"] = [component_cd("cargo clippy --workspace -- -D warnings", component)]
    return commands


def go_component_commands(component: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "build": [component_cd("go build {{args}} ./...", component)],
        "release": [component_cd("go build ./...", component)],
        "test": [component_cd("go test {{args}} ./...", component)],
        "lint": [component_cd("golangci-lint run", component)],
        "fmt": [component_cd("gofmt -w .", component)],
        "fmt-check": [component_cd("test -z \"$(gofmt -l .)\"", component)],
        "clean": [component_cd("go clean -cache", component)],
        "bootstrap": [component_cd("go mod download", component)],
        "dev": [],
    }


def cpp_component_commands(component: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "build": [component_cd("cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build", component)],
        "release": [component_cd("cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build", component)],
        "test": [component_cd("cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build && cd build && ctest --output-on-failure", component)],
        "lint": [],
        "fmt": [],
        "fmt-check": [],
        "clean": [component_cd("rm -rf build", component)],
        "bootstrap": [component_cd("cmake -S . -B build", component)],
        "dev": [],
    }


def dotnet_component_commands(component: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "build": [component_cd("dotnet build", component)],
        "release": [component_cd("dotnet build -c Release", component)],
        "test": [component_cd("dotnet test {{args}}", component)],
        "lint": [component_cd("dotnet format --verify-no-changes", component)],
        "fmt": [component_cd("dotnet format", component)],
        "fmt-check": [component_cd("dotnet format --verify-no-changes", component)],
        "clean": [component_cd("dotnet clean", component)],
        "bootstrap": [component_cd("dotnet restore", component)],
        "dev": [],
    }


def zig_component_commands(component: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "build": [component_cd("zig build {{args}}", component)],
        "release": [component_cd("zig build -Doptimize=ReleaseSafe", component)],
        "test": [component_cd("zig build test", component)],
        "lint": [],
        "fmt": [component_cd("zig fmt src/", component)],
        "fmt-check": [component_cd("zig fmt --check src/", component)],
        "clean": [component_cd("rm -rf zig-out zig-cache .zig-cache", component)],
        "bootstrap": [component_cd("zig build", component)],
        "dev": [],
    }


def ruby_component_commands(component: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "build": [component_cd("bundle exec rake build", component)],
        "release": [component_cd("bundle exec rake build", component)],
        "test": [component_cd("bundle exec rspec {{args}}", component)],
        "lint": [component_cd("bundle exec rubocop", component)],
        "fmt": [component_cd("bundle exec rubocop -A", component)],
        "fmt-check": [],
        "clean": [component_cd("rm -rf pkg tmp log", component)],
        "bootstrap": [component_cd("bundle install", component)],
        "dev": [],
    }


def elixir_component_commands(component: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "build": [component_cd("mix compile", component)],
        "release": [component_cd("mix compile", component)],
        "test": [component_cd("mix test {{args}}", component)],
        "lint": [component_cd("mix credo --strict", component)],
        "fmt": [component_cd("mix format", component)],
        "fmt-check": [component_cd("mix format --check-formatted", component)],
        "clean": [component_cd("mix clean && rm -rf _build deps", component)],
        "bootstrap": [component_cd("mix deps.get && mix compile", component)],
        "dev": [],
    }


def java_component_commands(component: dict[str, Any], repo: Path) -> dict[str, list[str]]:
    component_root = repo / component["path"] if component["path"] != "." else repo
    if component["build_tool"] == "gradle":
        runner = "./gradlew" if (component_root / "gradlew").exists() else "gradle"
        return {
            "build": [component_cd(f"{runner} build -x test", component)],
            "release": [component_cd(f"{runner} build -x test", component)],
            "test": [component_cd(f"{runner} test", component)],
            "lint": [component_cd(f"{runner} check", component)],
            "fmt": [],
            "fmt-check": [],
            "clean": [component_cd(f"{runner} clean", component)],
            "bootstrap": [component_cd(f"{runner} build", component)],
            "dev": [],
        }
    runner = "./mvnw" if (component_root / "mvnw").exists() else "mvn"
    return {
        "build": [component_cd(f"{runner} compile", component)],
        "release": [component_cd(f"{runner} package -DskipTests", component)],
        "test": [component_cd(f"{runner} test", component)],
        "lint": [component_cd(f"{runner} checkstyle:check", component)],
        "fmt": [],
        "fmt-check": [],
        "clean": [component_cd(f"{runner} clean", component)],
        "bootstrap": [component_cd(f"{runner} install -DskipTests", component)],
        "dev": [],
    }


def commands_for_component(component: dict[str, Any], repo: Path) -> dict[str, list[str]]:
    language = component["language"]
    if language == "rust":
        return rust_component_commands(component)
    if language == "python":
        return python_component_commands(component, repo)
    if language == "javascript":
        return node_component_commands(component, repo)
    if language == "go":
        return go_component_commands(component)
    if language == "cpp":
        return cpp_component_commands(component)
    if language == "dotnet":
        return dotnet_component_commands(component)
    if language == "zig":
        return zig_component_commands(component)
    if language == "ruby":
        return ruby_component_commands(component)
    if language == "elixir":
        return elixir_component_commands(component)
    if language == "java":
        return java_component_commands(component, repo)
    return {"build": [], "release": [], "test": [], "lint": [], "fmt": [], "fmt-check": [], "clean": [], "bootstrap": [], "dev": []}


def merge_recipe_commands(existing: dict[str, list[str]], new: dict[str, list[str]]) -> dict[str, list[str]]:
    out = {key: list(value) for key, value in existing.items()}
    for key, value in new.items():
        out.setdefault(key, [])
        for item in value:
            if item not in out[key]:
                out[key].append(item)
    return out


def make_initial_recipe_commands(repo: Path, detected: dict[str, Any]) -> dict[str, list[str]]:
    commands = {key: [] for key in ["build", "release", "test", "lint", "fmt", "fmt-check", "clean", "bootstrap", "ci", "dev"]}
    if "make" in detected["task_runners"]:
        mapped = task_target_map(detected.get("make_targets", []), "make")
        for key, value in mapped.items():
            commands[key].append(value)
    if "task" in detected["task_runners"]:
        mapped = task_target_map(detected.get("task_targets", []), "task")
        for key, value in mapped.items():
            if value not in commands[key]:
                commands[key].append(value)

    for component in detected["components"]:
        component_commands = commands_for_component(component, repo)
        commands = merge_recipe_commands(commands, component_commands)

    if detected["docker"]["compose_files"]:
        commands["docker-build"] = ["docker compose build"]
        commands["docker-up"] = ["docker compose up -d"]
        commands["docker-down"] = ["docker compose down"]
        commands["docker-logs"] = ["docker compose logs -f"]
        commands["docker-clean"] = ["docker compose down -v --rmi local"]

    return commands


def choose_dist_plan(detected: dict[str, Any], architecture: str) -> dict[str, Any]:
    if architecture not in {"local-dist", "committed-dist", "cross-os-dist"}:
        return {"supported": False, "reason": "architecture has no dist section"}

    dist_build: list[str] = []
    clean_build: list[str] = []
    stage_lines: list[str] = []
    supported_any = False

    if architecture == "cross-os-dist":
        dist_dir_expr = '"dist/" + os() + "-" + arch()'
    else:
        dist_dir_expr = '"dist"'

    dist_variables = [
        f'dist_dir := {dist_dir_expr}',
        'exe_suffix := if os() == "windows" { ".exe" } else { "" }',
    ]

    for component in detected["components"]:
        if component["language"] == "rust" and component.get("binary_targets"):
            supported_any = True
            dist_build.append(component_cd("cargo build --release", component))
            clean_build.append(component_cd("cargo clean", component))
            for binary in component["binary_targets"]:
                src_dir = component["path"]
                if src_dir == ".":
                    src = f'target/release/{binary}${{ if os() == "windows" {{ ".exe" }} else {{ "" }} }}'
                else:
                    src = f'{src_dir}/target/release/{binary}${{ if os() == "windows" {{ ".exe" }} else {{ "" }} }}'
                # Raw bash uses $bin style, not just interpolation.
                if component["path"] == ".":
                    stage_lines.append(f"cp {shell_quote_path(f'target/release/{binary}{{{{ exe_suffix }}}}')} \"{{{{ dist_dir }}}}/\"")
                else:
                    staged_source = f"{component['path']}/target/release/{binary}{{{{ exe_suffix }}}}"
                    stage_lines.append(
                        f"cp {shell_quote_path(staged_source)} \"{{{{ dist_dir }}}}/\""
                    )
        elif component["language"] == "go" and component.get("binary_targets"):
            supported_any = True
            path = component["path"]
            build_dir = ".local/harness/build"
            for binary in component["binary_targets"]:
                if path == ".":
                    source = f"./cmd/{binary}"
                    if not (Path(detected["repo_root"]) / "cmd" / binary).exists():
                        source = "."
                    dist_build.append(f'mkdir -p "{build_dir}" && go build -o "{build_dir}/{binary}{{{{ exe_suffix }}}}" {source}')
                    clean_build.append("rm -rf .local/harness/build")
                    stage_lines.append(f'cp ".local/harness/build/{binary}{{{{ exe_suffix }}}}" "{{{{ dist_dir }}}}/"')
                else:
                    repo_path = Path(detected["repo_root"]) / path
                    source = f"./cmd/{binary}"
                    if not (repo_path / "cmd" / binary).exists():
                        source = "."
                    dist_build.append(component_cd(f'mkdir -p ".local/harness/build" && go build -o ".local/harness/build/{binary}{{{{ exe_suffix }}}}" {source}', component))
                    clean_build.append(component_cd("rm -rf .local/harness/build", component))
                    stage_lines.append(
                        f"cp {shell_quote_path(f'{path}/.local/harness/build/{binary}{{{{ exe_suffix }}}}')} \"{{{{ dist_dir }}}}/\""
                    )

    if not supported_any:
        return {
            "supported": False,
            "reason": "no language with an obvious staged binary output was detected",
            "dist_variables": dist_variables,
        }

    return {
        "supported": True,
        "dist_variables": dist_variables,
        "dist_build": dist_build,
        "clean_build": unique_preserve_order(clean_build),
        "stage_lines": stage_lines,
    }


def unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def strip_args_placeholder(line: str) -> str:
    cleaned = line.replace("{{args}}", "").rstrip()
    cleaned = re.sub(r"\s+--\s*$", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def render_recipe_block(name: str, lines: list[str], *, args: bool = False, doc: str | None = None, private: bool = False, deps: list[str] | None = None, allow_empty: bool = False) -> str:
    head = ""
    if doc:
        head += f"# {doc}\n"
    if private:
        head += "[private]\n"
    signature = name
    if deps:
        signature += ": " + " ".join(deps)
    else:
        signature += " *args:" if args else ":"
    if not lines and allow_empty:
        return f"{head}{signature}\n\n"
    body_lines = lines or [f'@echo "No {name} command detected"']
    body = "\n".join(f"    {line}" for line in body_lines)
    return f"{head}{signature}\n{body}\n\n"


def build_variable_block(commands: dict[str, list[str]], architecture: str) -> str:
    lines: list[str] = []
    if any("dotnet" in cmd for cmds in commands.values() for cmd in cmds):
        lines.append("# dotnet commands rely on the installed SDK")
    return ("\n".join(lines) + "\n\n") if lines else ""


def component_label(component: dict[str, Any]) -> str:
    return component["path"] if component["path"] != "." else component["language"]


def render_component_recipe_blocks(repo: Path, detected: dict[str, Any]) -> str:
    components = detected.get("components", [])
    if len(components) <= 1 and not any(component.get("workspace") for component in components):
        return ""
    blocks: list[str] = []
    for component in components:
        prefix = component_prefix(component)
        label = component_label(component)
        commands = commands_for_component(component, repo)
        specs = [
            ("build", True, f"Build only {label}"),
            ("release", False, f"Build release outputs only for {label}"),
            ("test", True, f"Run tests only for {label}"),
            ("lint", False, f"Run linters only for {label}"),
            ("fmt", False, f"Format code only for {label}"),
            ("fmt-check", False, f"Check formatting only for {label}"),
            ("clean", False, f"Remove build artifacts only for {label}"),
            ("bootstrap", False, f"Install dependencies only for {label}"),
            ("dev", True, f"Run the main developer loop only for {label}"),
        ]
        for recipe, has_args, doc in specs:
            lines = commands.get(recipe, [])
            if not lines:
                continue
            blocks.append(render_recipe_block(f"{prefix}-{recipe}", lines, args=has_args, doc=doc))
    return "".join(blocks)


def guidance_comment_block(detected: dict[str, Any]) -> str:
    if detected.get("components") or detected.get("task_runners"):
        return ""
    return (
        "# No native build surface was detected.\n"
        "# Replace the placeholder recipes below with the repo's real lifecycle commands.\n"
        "# Start with bootstrap, fmt-check, lint, test, and build.\n\n"
    )


def build_dist_section(plan: dict[str, Any], architecture: str, dist_storage: str) -> tuple[str, str]:
    if not plan.get("supported"):
        return "", "\n".join(plan.get("dist_variables", [])) + ("\n\n" if plan.get("dist_variables") else "")

    dist_variables = "\n".join(plan["dist_variables"]) + "\n\n"
    dist_lines = list(plan["dist_build"]) + ["just _stage"]
    stage_lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        'mkdir -p "{{ dist_dir }}"',
        *plan["stage_lines"],
        'echo "Staged -> {{ dist_dir }}/"',
    ]
    preserve_dist = architecture in {"committed-dist", "cross-os-dist"} and dist_storage in {"git", "git-lfs"}
    dist_block = ""
    dist_block += render_recipe_block("dist", dist_lines, doc="Build release artifacts and stage them to dist/")
    dist_block += render_recipe_block("_stage", stage_lines, private=True, doc="Internal helper that copies release outputs into dist/")
    dist_block += render_recipe_block("clean-build", unique_preserve_order(plan["clean_build"]), doc="Remove build artifacts but preserve dist/")
    clean_dist_doc = "Remove staged dist outputs"
    if preserve_dist:
        clean_dist_doc = "Remove staged dist outputs. Use only when you intend to rebuild or restore committed deliverables."
    dist_block += render_recipe_block("clean-dist", ['rm -rf "{{ dist_dir }}"'], doc=clean_dist_doc)
    if preserve_dist:
        dist_block += render_recipe_block("clean", ["just clean-build"], doc="Remove build artifacts but preserve committed dist outputs")
    else:
        dist_block += render_recipe_block("clean", ["just clean-build", "just clean-dist"], doc="Remove both build artifacts and staged outputs")
    return dist_block, dist_variables


def render_justfile(repo: Path, detected: dict[str, Any], architecture: str, dist_storage: str) -> tuple[str, list[str]]:
    commands = make_initial_recipe_commands(repo, detected)
    warnings: list[str] = list(detected.get("notes", []))
    dist_block = ""
    dist_variables = ""
    if architecture in {"local-dist", "committed-dist", "cross-os-dist"}:
        plan = choose_dist_plan(detected, architecture)
        dist_block, dist_variables = build_dist_section(plan, architecture, dist_storage)
        if not plan.get("supported"):
            warnings.append(f"{architecture} selected but automatic staged outputs were not obvious; dist section was omitted")
    template_name = {
        "general": "just-general.just.tpl",
        "local-dist": "just-local-dist.just.tpl",
        "committed-dist": "just-committed-dist.just.tpl",
        "cross-os-dist": "just-cross-os-dist.just.tpl",
    }[architecture]
    template = read_text(ASSETS_DIR / template_name)

    ci_block = render_recipe_block("ci", [], doc="Run the normal CI surface", deps=["lint", "fmt-check", "test"], allow_empty=True)
    clean_block = ""
    if architecture not in {"local-dist", "committed-dist", "cross-os-dist"}:
        clean_block = render_recipe_block("clean", commands["clean"], doc="Remove build artifacts")
    bootstrap_block = render_recipe_block("bootstrap", commands["bootstrap"], doc="Install dependencies and prepare the repo")
    dev_block = render_recipe_block("dev", commands.get("dev", []), args=True, doc="Run the main developer loop")
    docker_block = ""
    if detected["docker"]["compose_files"]:
        docker_block += render_recipe_block("docker-build", commands.get("docker-build", []), doc="Build Docker services")
        docker_block += render_recipe_block("docker-up", commands.get("docker-up", []), doc="Start Docker services")
        docker_block += render_recipe_block("docker-down", commands.get("docker-down", []), doc="Stop Docker services")
        docker_block += render_recipe_block("docker-logs", commands.get("docker-logs", []), doc="Stream Docker logs")
        docker_block += render_recipe_block("docker-clean", commands.get("docker-clean", []), doc="Remove Docker volumes and local images")

    replacements = {
        "__GUIDANCE_BLOCK__": guidance_comment_block(detected),
        "__VARIABLES__": build_variable_block(commands, architecture),
        "__COMPONENT_BLOCKS__": render_component_recipe_blocks(repo, detected),
        "__DIST_VARIABLES__": dist_variables,
        "__BUILD_BLOCK__": render_recipe_block("build", commands["build"], args=True, doc="Build the project"),
        "__RELEASE_BLOCK__": render_recipe_block("release", [strip_args_placeholder(line) for line in (commands["release"] or commands["build"])], doc="Build release or optimized outputs"),
        "__DIST_BLOCK__": dist_block,
        "__TEST_BLOCK__": render_recipe_block("test", commands["test"], args=True, doc="Run tests"),
        "__LINT_BLOCK__": render_recipe_block("lint", commands["lint"], doc="Run linters"),
        "__FMT_BLOCK__": render_recipe_block("fmt", commands["fmt"], doc="Format code"),
        "__FMT_CHECK_BLOCK__": render_recipe_block("fmt-check", commands["fmt-check"], doc="Check formatting without changing files"),
        "__CI_BLOCK__": ci_block,
        "__CLEAN_BLOCK__": clean_block,
        "__BOOTSTRAP_BLOCK__": bootstrap_block,
        "__DEV_BLOCK__": dev_block,
        "__DOCKER_BLOCK__": docker_block,
    }
    output = template
    for key, value in replacements.items():
        output = output.replace(key, value)
    output = re.sub(r"\n{3,}", "\n\n", output).rstrip() + "\n"
    return output, warnings


def workflow_setup_steps(repo: Path, detected: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    languages = set(detected["languages"])
    package_managers = set(detected["package_managers"])
    build_tools = set(detected["build_tools"])

    if "python" in languages:
        steps.extend([
            "      - uses: actions/setup-python@v6",
            "        with:",
            "          python-version: '3.12'",
        ])
        if "poetry" in build_tools:
            steps.extend(["          cache: 'poetry'"])
        elif "pip" in build_tools and "uv" not in build_tools:
            steps.extend(["          cache: 'pip'"])
        if "uv" in build_tools:
            steps.extend([
                "      - uses: astral-sh/setup-uv@v6",
            ])
        if "poetry" in build_tools:
            steps.extend([
                "      - name: Install Poetry",
                "        shell: bash",
                "        run: python -m pip install --upgrade pip poetry",
            ])
    if "javascript" in languages:
        if "pnpm" in package_managers:
            steps.extend([
                "      - uses: pnpm/action-setup@v5",
            ])
        steps.extend([
            "      - uses: actions/setup-node@v6",
            "        with:",
            "          node-version: 'lts/*'",
        ])
        if "pnpm" in package_managers:
            steps.extend(["          cache: 'pnpm'"])
        elif "yarn" in package_managers:
            steps.extend(["          cache: 'yarn'"])
        elif "npm" in package_managers or not package_managers:
            steps.extend(["          cache: 'npm'"])
    if "go" in languages:
        steps.extend([
            "      - uses: actions/setup-go@v6",
            "        with:",
            "          go-version: 'stable'",
        ])
    if "rust" in languages:
        steps.extend([
            "      - name: Install Rust toolchain",
            "        shell: bash",
            "        run: |",
            "          if ! command -v rustup >/dev/null 2>&1; then",
            "            curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable",
            "            echo \"$HOME/.cargo/bin\" >> \"$GITHUB_PATH\"",
            "          fi",
            "          rustup toolchain install stable --profile minimal --component clippy rustfmt",
            "          rustup default stable",
        ])
    if "java" in languages:
        steps.extend([
            "      - uses: actions/setup-java@v5",
            "        with:",
            "          distribution: 'temurin'",
            "          java-version: '21'",
        ])
        if "gradle" in build_tools and "maven" not in build_tools:
            steps.extend(["          cache: 'gradle'"])
        elif "maven" in build_tools and "gradle" not in build_tools:
            steps.extend(["          cache: 'maven'"])
    if "dotnet" in languages:
        steps.extend([
            "      - uses: actions/setup-dotnet@v4",
            "        with:",
            "          dotnet-version: '8.0.x'",
        ])
    if "ruby" in languages:
        steps.extend([
            "      - uses: ruby/setup-ruby@v1",
            "        with:",
            "          bundler-cache: true",
        ])
    if "elixir" in languages:
        steps.extend([
            "      - uses: erlef/setup-beam@v1",
            "        with:",
            "          otp-version: '27'",
            "          elixir-version: '1.17'",
        ])
    return steps


def render_direct_workflow_steps(recipe_lines: list[str], name: str) -> list[str]:
    if not recipe_lines:
        return []
    out = [
        f"      - name: {name}",
        "        shell: bash",
        "        run: |",
    ]
    for line in recipe_lines:
        out.append(f"          {strip_args_placeholder(line)}")
    return out


def render_ci_workflow(repo: Path, detected: dict[str, Any], ci_mode: str) -> str:
    commands = make_initial_recipe_commands(repo, detected)
    setup_steps = workflow_setup_steps(repo, detected)
    if ci_mode == "just":
        template = read_text(ASSETS_DIR / "workflow-ci-just.yml.tpl")
        setup_block = "\n".join(setup_steps)
        bootstrap_step = "\n".join([
            "      - name: Bootstrap",
            "        shell: bash",
            "        run: just bootstrap",
        ])
        output = template.replace("__SETUP_STEPS__", setup_block + ("\n" if setup_block else ""))
        output = output.replace("__BOOTSTRAP_STEP__", bootstrap_step + "\n")
        return output
    template = read_text(ASSETS_DIR / "workflow-ci-direct.yml.tpl")
    bootstrap_steps = render_direct_workflow_steps(commands["bootstrap"], "Bootstrap")
    run_steps: list[str] = []
    run_steps.extend(render_direct_workflow_steps(commands["fmt-check"], "Check formatting"))
    run_steps.extend(render_direct_workflow_steps(commands["lint"], "Lint"))
    run_steps.extend(render_direct_workflow_steps(commands["test"], "Test"))
    setup_block = "\n".join(setup_steps)
    bootstrap_block = "\n".join(bootstrap_steps)
    run_block = "\n".join(run_steps)
    output = template.replace("__SETUP_STEPS__", setup_block + ("\n" if setup_block else ""))
    output = output.replace("__BOOTSTRAP_STEPS__", bootstrap_block + ("\n" if bootstrap_block else ""))
    output = output.replace("__RUN_STEPS__", run_block + ("\n" if run_block else ""))
    return output


def render_release_cross_os(repo: Path, detected: dict[str, Any]) -> str:
    plan = choose_dist_plan(detected, "cross-os-dist")
    if not plan.get("supported"):
        return ""
    commands = make_initial_recipe_commands(repo, detected)
    setup_block = "\n".join(workflow_setup_steps(repo, detected))
    bootstrap_block = "\n".join(render_direct_workflow_steps(commands["bootstrap"], "Bootstrap"))
    dist_steps = [
        "      - name: Build release outputs",
        "        shell: bash",
        "        run: |",
    ]
    exe_expr = "${{ matrix.os == 'windows-latest' && '.exe' || '' }}"
    for line in plan["dist_build"]:
        dist_steps.append(f"          {strip_args_placeholder(line.replace('{{ exe_suffix }}', exe_expr))}")
    dist_steps.extend([
        "      - name: Stage dist directory",
        "        shell: bash",
        "        run: |",
        "          mkdir -p \"dist/${{ matrix.platform_id }}\"",
    ])
    for line in plan["stage_lines"]:
        converted = line.replace('{{ dist_dir }}', 'dist/${{ matrix.platform_id }}').replace('{{ exe_suffix }}', exe_expr)
        dist_steps.append(f"          {converted}")
    template = read_text(ASSETS_DIR / "workflow-release-cross-os.yml.tpl")
    output = template.replace("__SETUP_STEPS__", setup_block + ("\n" if setup_block else ""))
    output = output.replace("__BOOTSTRAP_STEPS__", bootstrap_block + ("\n" if bootstrap_block else ""))
    output = output.replace("__DIST_STEPS__", "\n".join(dist_steps) + "\n")
    return output


def repo_state_path(repo: Path) -> Path:
    return repo / ".local" / "harness" / "state.json"


def render_dir(repo: Path) -> Path:
    return repo / ".local" / "harness" / "render"


def load_state(repo: Path) -> tuple[dict[str, Any], list[str]]:
    path = repo_state_path(repo)
    if not path.exists():
        return {}, []
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except Exception:
        backup = path.with_name(path.name + ".corrupt")
        if backup.exists():
            backup.unlink()
        path.replace(backup)
        return {}, [f"existing state file was unreadable and was moved to {backup.name}"]


def write_state(repo: Path, detected: dict[str, Any], selected: dict[str, Any], generated: dict[str, Any], warnings: list[str]) -> tuple[Path, list[str]]:
    state_dir = repo / ".local" / "harness"
    state_dir.mkdir(parents=True, exist_ok=True)
    existing, state_warnings = load_state(repo)
    persisted_warnings = unique_preserve_order([*warnings, *state_warnings])
    state = {
        "version": STATE_VERSION,
        "created_at": existing.get("created_at", utc_now()),
        "updated_at": utc_now(),
        "detected": {
            "languages": detected["languages"],
            "build_tools": detected["build_tools"],
            "frameworks": detected["frameworks"],
            "task_runners": detected["task_runners"],
            "ci_systems": detected["ci_systems"],
            "distribution_hints": detected.get("distribution_hints", {}),
        },
        "selected": selected,
        "generated": generated,
        "warnings": persisted_warnings,
        "notes": detected.get("notes", []),
    }
    path = repo_state_path(repo)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path, state_warnings


def ensure_gitignore(repo: Path, architecture: str) -> list[str]:
    gitignore = repo / ".gitignore"
    lines: list[str] = []
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8").splitlines()
        lines = existing[:]
    changed = False
    if ".local/" not in lines:
        lines.append(".local/")
        changed = True
    if architecture == "local-dist" and "dist/" not in lines:
        lines.append("dist/")
        changed = True
    if changed:
        gitignore.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    warnings: list[str] = []
    if architecture in {"committed-dist", "cross-os-dist"} and any(line.strip() == "dist/" for line in lines):
        warnings.append("dist/ is ignored in .gitignore but the selected architecture expects committed dist outputs")
    return warnings


def ensure_gitattributes(repo: Path, architecture: str, dist_storage: str) -> list[str]:
    warnings: list[str] = []
    gitattributes = repo / ".gitattributes"
    lines = gitattributes.read_text(encoding="utf-8").splitlines() if gitattributes.exists() else []
    managed_comment = "# project-harness: track committed dist outputs with Git LFS"
    managed_rule = "dist/** filter=lfs diff=lfs merge=lfs -text"
    filtered = [line for line in lines if line not in {managed_comment, managed_rule}]

    if dist_storage == "git-lfs" and architecture in {"committed-dist", "cross-os-dist"}:
        if any(line == managed_rule for line in lines):
            return warnings
        if filtered and filtered[-1].strip() != "":
            filtered.append("")
        filtered.append(managed_comment)
        filtered.append(managed_rule)
        gitattributes.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")
        warnings.append("added dist/** Git LFS tracking to .gitattributes")
        return warnings

    if filtered != lines:
        if filtered:
            gitattributes.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")
        elif gitattributes.exists():
            gitattributes.unlink()
        warnings.append("removed managed dist/** Git LFS tracking from .gitattributes")
    return warnings


def write_candidate(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def safe_write_target(target: Path, content: str) -> tuple[bool, str]:
    if target.exists():
        existing = target.read_text(encoding="utf-8", errors="ignore")
        if MANAGED_MARKER not in existing:
            return False, "existing unmanaged file blocked write"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return True, "written"


def command_model_for_execution(repo: Path, detected: dict[str, Any]) -> dict[str, list[str]]:
    return make_initial_recipe_commands(repo, detected)


def run_exec(argv: list[str], repo: Path, dry_run: bool = False) -> int:
    print(shlex.join(argv))
    if dry_run:
        return 0
    result = subprocess.run(argv, cwd=repo)
    return result.returncode


def run_shell(command: str, repo: Path, dry_run: bool = False) -> int:
    print(command)
    if dry_run:
        return 0
    shell_cmd: list[str]
    if shutil.which("bash"):
        shell_cmd = ["bash", "-lc", command]
    elif shutil.which("sh"):
        shell_cmd = ["sh", "-lc", command]
    else:
        return fail("no POSIX shell found", "install bash or sh, or run in Git Bash / WSL on Windows")
    result = subprocess.run(shell_cmd, cwd=repo)
    return result.returncode


def extract_required_tools(commands: dict[str, list[str]]) -> dict[str, bool]:
    tools: dict[str, bool] = {}
    candidates: set[str] = set()
    skip = {"cd", "rm", "mkdir", "test", "echo", "just"}
    for lines in commands.values():
        for line in lines:
            stripped = re.sub(r"\{\{.*?\}\}", "", line).strip()
            if not stripped:
                continue
            first = stripped.split("&&")[-1].strip().split()[0]
            if "/" in first or first in skip:
                continue
            candidates.add(first)
    for tool in sorted(candidates):
        tools[tool] = shutil.which(tool) is not None
    if shutil.which("just"):
        tools["just"] = True
    return tools


def do_detect(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    if not repo.exists():
        return fail(f"repo root does not exist: {repo}")
    detected = detect_components(repo)
    print(json.dumps(detected, indent=2 if args.pretty else None, sort_keys=True))
    return 0


def do_render_or_update(args: argparse.Namespace, write: bool) -> int:
    repo = Path(args.repo_root).resolve()
    if not repo.exists():
        return fail(f"repo root does not exist: {repo}")
    detected = detect_components(repo)
    architecture = args.architecture if args.architecture != "auto" else detected["selection_defaults"]["architecture"]
    ci_mode = args.ci_mode if args.ci_mode != "auto" else detected["selection_defaults"]["ci_mode"]
    dist_storage = args.dist_storage if args.dist_storage != "auto" else detected["selection_defaults"].get("dist_storage", "none")
    warnings: list[str] = list(detected.get("notes", []))
    if dist_storage == "artifacts" and architecture in {"committed-dist", "cross-os-dist"}:
        warnings.append("artifact-based dist storage conflicts with a committed dist architecture; prefer local-dist/general plus a release overlay")
    if dist_storage == "git-lfs" and architecture not in {"committed-dist", "cross-os-dist"}:
        warnings.append("Git LFS tracking only matters for committed dist outputs; local-dist/general usually should not add dist/** to .gitattributes")

    justfile_content, just_warnings = render_justfile(repo, detected, architecture, dist_storage)
    warnings.extend(just_warnings)
    ci_content = ""
    if ci_mode != "none":
        ci_content = render_ci_workflow(repo, detected, ci_mode)
    release_requested = bool(args.release_overlay or detected["selection_defaults"].get("release_overlay") or architecture == "cross-os-dist")
    release_content = ""
    if release_requested:
        release_content = render_release_cross_os(repo, detected)
        if not release_content:
            warnings.append("cross-OS release workflow was requested but the repo did not expose an obvious staged-binary plan")

    out_dir = render_dir(repo)
    out_dir.mkdir(parents=True, exist_ok=True)
    just_candidate = out_dir / "justfile"
    ci_candidate = out_dir / "ci.yml"
    release_candidate = out_dir / "release-cross-os.yml"
    gitattributes_candidate = out_dir / ".gitattributes"
    for stale_candidate in [just_candidate, ci_candidate, release_candidate, gitattributes_candidate]:
        if stale_candidate.exists():
            stale_candidate.unlink()

    candidates: list[str] = []
    write_candidate(just_candidate, justfile_content)
    candidates.append(just_candidate.name)
    if ci_content:
        write_candidate(ci_candidate, ci_content)
        candidates.append(ci_candidate.name)
    if release_content:
        write_candidate(release_candidate, release_content)
        candidates.append(release_candidate.name)
    if dist_storage == "git-lfs" and architecture in {"committed-dist", "cross-os-dist"}:
        write_candidate(gitattributes_candidate, "# project-harness: track committed dist outputs with Git LFS\ndist/** filter=lfs diff=lfs merge=lfs -text\n")
        candidates.append(gitattributes_candidate.name)

    managed_writes: list[str] = []
    candidate_only: list[str] = []

    if write:
        just_ok, _ = safe_write_target(repo / "justfile", justfile_content)
        if just_ok:
            managed_writes.append("justfile")
        else:
            candidate_only.append("justfile")
            warnings.append("existing unmanaged justfile was not overwritten")

        if ci_content:
            ci_target = repo / ".github" / "workflows" / "ci.yml"
            ci_ok, _ = safe_write_target(ci_target, ci_content)
            if ci_ok:
                managed_writes.append(".github/workflows/ci.yml")
            else:
                candidate_only.append(".github/workflows/ci.yml")
                warnings.append("existing unmanaged ci workflow was not overwritten")

        if release_content:
            release_target = repo / ".github" / "workflows" / "release-cross-os.yml"
            release_ok, _ = safe_write_target(release_target, release_content)
            if release_ok:
                managed_writes.append(".github/workflows/release-cross-os.yml")
            else:
                candidate_only.append(".github/workflows/release-cross-os.yml")
                warnings.append("existing unmanaged release workflow was not overwritten")

        warnings.extend(ensure_gitignore(repo, architecture))
        warnings.extend(ensure_gitattributes(repo, architecture, dist_storage))

    warnings = unique_preserve_order(warnings)

    selected = {
        "architecture": architecture,
        "ci_mode": ci_mode,
        "release_overlay": bool(release_requested and release_content),
        "dist_storage": dist_storage,
    }
    generated = {
        "render_dir": relpath(out_dir, repo),
        "managed_writes": managed_writes,
        "candidate_only": candidate_only,
    }
    state_path, state_warnings = write_state(repo, detected, selected, generated, warnings)
    warnings.extend(state_warnings)
    warnings = unique_preserve_order(warnings)
    payload = {
        "repo_root": str(repo),
        "selected": selected,
        "state_path": relpath(state_path, repo),
        "render_dir": relpath(out_dir, repo),
        "candidates": candidates,
        "managed_writes": managed_writes,
        "candidate_only": candidate_only,
        "warnings": warnings,
    }
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


def do_bootstrap(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    if not repo.exists():
        return fail(f"repo root does not exist: {repo}")
    if (repo / "justfile").exists() and shutil.which("just"):
        return run_exec(["just", "bootstrap"], repo, dry_run=args.dry_run)
    detected = detect_components(repo)
    commands = command_model_for_execution(repo, detected)
    lines = commands.get("bootstrap", [])
    if not lines:
        return fail("no bootstrap command detected", "render the harness first or inspect the language-specific reference")
    for line in lines:
        status = run_shell(strip_args_placeholder(line), repo, dry_run=args.dry_run)
        if status != 0:
            return status
    return 0


def do_run(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    if not repo.exists():
        return fail(f"repo root does not exist: {repo}")
    recipe = args.recipe
    if (repo / "justfile").exists() and shutil.which("just"):
        return run_exec(["just", recipe], repo, dry_run=args.dry_run)
    detected = detect_components(repo)
    commands = command_model_for_execution(repo, detected)
    lines = commands.get(recipe, [])
    if not lines:
        return fail(f"no command detected for recipe '{recipe}'", "render the harness first or inspect detection output")
    for line in lines:
        status = run_shell(strip_args_placeholder(line), repo, dry_run=args.dry_run)
        if status != 0:
            return status
    return 0


def do_doctor(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    if not repo.exists():
        return fail(f"repo root does not exist: {repo}")
    detected = detect_components(repo)
    commands = command_model_for_execution(repo, detected)
    tools = extract_required_tools(commands)
    payload = {
        "repo_root": str(repo),
        "languages": detected["languages"],
        "tool_status": tools,
        "has_justfile": (repo / "justfile").exists(),
        "just_available": shutil.which("just") is not None,
    }
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    missing = [tool for tool, ok in tools.items() if not ok]
    if missing:
        return fail("missing required tools: " + ", ".join(missing), "install the missing tools or use a different component profile")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect, render, update, bootstrap, and run a repo harness.")
    sub = parser.add_subparsers(dest="command", required=True)

    detect = sub.add_parser("detect", help="Inspect a repo and print detection JSON.")
    detect.add_argument("repo_root")
    detect.add_argument("--pretty", action="store_true")
    detect.set_defaults(func=do_detect)

    render = sub.add_parser("render", help="Preview candidate files into .local/harness/render without writing managed targets.")
    render.add_argument("repo_root")
    render.add_argument("--architecture", choices=["auto", "general", "local-dist", "committed-dist", "cross-os-dist"], default="auto")
    render.add_argument("--ci-mode", choices=["auto", "just", "direct", "none"], default="auto")
    render.add_argument("--dist-storage", choices=["auto", "none", "git", "git-lfs", "artifacts"], default="auto")
    render.add_argument("--release-overlay", action="store_true")
    render.add_argument("--pretty", action="store_true")
    render.set_defaults(func=lambda ns: do_render_or_update(ns, write=False))

    update = sub.add_parser("update", help="Write managed files when safe and refresh candidate outputs.")
    update.add_argument("repo_root")
    update.add_argument("--architecture", choices=["auto", "general", "local-dist", "committed-dist", "cross-os-dist"], default="auto")
    update.add_argument("--ci-mode", choices=["auto", "just", "direct", "none"], default="auto")
    update.add_argument("--dist-storage", choices=["auto", "none", "git", "git-lfs", "artifacts"], default="auto")
    update.add_argument("--release-overlay", action="store_true")
    update.add_argument("--pretty", action="store_true")
    update.set_defaults(func=lambda ns: do_render_or_update(ns, write=True))

    bootstrap = sub.add_parser("bootstrap", help="Run bootstrap via just if available, otherwise via direct fallback.")
    bootstrap.add_argument("repo_root")
    bootstrap.add_argument("--dry-run", action="store_true")
    bootstrap.set_defaults(func=do_bootstrap)

    run_cmd = sub.add_parser("run", help="Run a recipe via just if available, otherwise via direct fallback.")
    run_cmd.add_argument("repo_root")
    run_cmd.add_argument("recipe")
    run_cmd.add_argument("--dry-run", action="store_true")
    run_cmd.set_defaults(func=do_run)

    doctor = sub.add_parser("doctor", help="Report missing tools for the detected command surface.")
    doctor.add_argument("repo_root")
    doctor.add_argument("--pretty", action="store_true")
    doctor.set_defaults(func=do_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
