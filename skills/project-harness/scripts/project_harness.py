#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
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
STATE_VERSION = "2.6.0"
MANAGED_MARKER = "# project-harness: managed-file"
GITATTRIBUTES_BEGIN = "# BEGIN project-harness managed gitattributes"
GITATTRIBUTES_END = "# END project-harness managed gitattributes"
GITATTRIBUTES_SECTION_MARKER = "# project-harness: managed-section"
GITATTRIBUTES_TEXT_RULES = [
    "* text=auto eol=lf",
    "",
    "# Documentation, configuration, and repo metadata",
    "*.md text eol=lf",
    "*.markdown text eol=lf",
    "*.txt text eol=lf",
    "*.rst text eol=lf",
    "*.adoc text eol=lf",
    "*.json text eol=lf",
    "*.jsonc text eol=lf",
    "*.json5 text eol=lf",
    "*.yml text eol=lf",
    "*.yaml text eol=lf",
    "*.toml text eol=lf",
    "*.ini text eol=lf",
    "*.cfg text eol=lf",
    "*.conf text eol=lf",
    "*.env text eol=lf",
    "*.example text eol=lf",
    "*.lock text eol=lf",
    ".gitignore text eol=lf",
    ".gitattributes text eol=lf",
    ".editorconfig text eol=lf",
    ".dockerignore text eol=lf",
    "Cargo.lock text eol=lf",
    "go.sum text eol=lf",
    "package-lock.json text eol=lf",
    "pnpm-lock.yaml text eol=lf",
    "yarn.lock text eol=lf",
    "poetry.lock text eol=lf",
    "uv.lock text eol=lf",
    "",
    "# Shells, task runners, and build entrypoints",
    "*.sh text eol=lf",
    "*.bash text eol=lf",
    "*.zsh text eol=lf",
    "*.fish text eol=lf",
    "*.ps1 text eol=lf",
    "*.psm1 text eol=lf",
    "*.psd1 text eol=lf",
    "*.bat text eol=lf",
    "*.cmd text eol=lf",
    "Makefile text eol=lf",
    "makefile text eol=lf",
    "*.mk text eol=lf",
    "Dockerfile text eol=lf",
    "Dockerfile.* text eol=lf",
    "*.Dockerfile text eol=lf",
    "justfile text eol=lf",
    "*.just text eol=lf",
    "Taskfile.yml text eol=lf",
    "Taskfile.yaml text eol=lf",
    "",
    "# Web, templates, and markup",
    "*.html text eol=lf",
    "*.htm text eol=lf",
    "*.css text eol=lf",
    "*.scss text eol=lf",
    "*.sass text eol=lf",
    "*.less text eol=lf",
    "*.xml text eol=lf",
    "*.svg text eol=lf",
    "*.tmpl text eol=lf",
    "*.tpl text eol=lf",
    "*.hbs text eol=lf",
    "*.mustache text eol=lf",
    "*.jinja text eol=lf",
    "*.jinja2 text eol=lf",
    "",
    "# Application source",
    "*.js text eol=lf",
    "*.jsx text eol=lf",
    "*.mjs text eol=lf",
    "*.cjs text eol=lf",
    "*.ts text eol=lf",
    "*.tsx text eol=lf",
    "*.py text eol=lf",
    "*.pyi text eol=lf",
    "*.rs text eol=lf",
    "*.go text eol=lf",
    "*.java text eol=lf",
    "*.kt text eol=lf",
    "*.kts text eol=lf",
    "*.scala text eol=lf",
    "*.c text eol=lf",
    "*.h text eol=lf",
    "*.cc text eol=lf",
    "*.cpp text eol=lf",
    "*.cxx text eol=lf",
    "*.hpp text eol=lf",
    "*.hxx text eol=lf",
    "*.cs text eol=lf",
    "*.csproj text eol=lf",
    "*.sln text eol=lf",
    "*.fs text eol=lf",
    "*.fsproj text eol=lf",
    "*.php text eol=lf",
    "*.rb text eol=lf",
    "*.lua text eol=lf",
    "*.pl text eol=lf",
    "*.pm text eol=lf",
    "*.swift text eol=lf",
    "*.r text eol=lf",
    "*.R text eol=lf",
    "*.sql text eol=lf",
    "*.graphql text eol=lf",
    "*.gql text eol=lf",
    "*.proto text eol=lf",
    "*.tf text eol=lf",
    "*.tfvars text eol=lf",
    "*.hcl text eol=lf",
    "*.nix text eol=lf",
    "*.ex text eol=lf",
    "*.exs text eol=lf",
    "*.erl text eol=lf",
    "*.hrl text eol=lf",
    "*.clj text eol=lf",
    "*.cljs text eol=lf",
    "*.cljc text eol=lf",
    "",
    "# Data, automation, and office-adjacent source",
    "*.csv text eol=lf",
    "*.tsv text eol=lf",
    "*.ndjson text eol=lf",
    "*.fx text eol=lf",
    "*.pq text eol=lf",
    "*.vba text eol=lf",
]
GITATTRIBUTES_BINARY_RULES = [
    "# Images and icons",
    "*.png binary",
    "*.jpg binary",
    "*.jpeg binary",
    "*.gif binary",
    "*.webp binary",
    "*.avif binary",
    "*.ico binary",
    "*.bmp binary",
    "*.tif binary",
    "*.tiff binary",
    "*.psd binary",
    "",
    "# Documents and spreadsheets",
    "*.pdf binary",
    "*.doc binary",
    "*.docx binary",
    "*.ppt binary",
    "*.pptx binary",
    "*.xls binary",
    "*.xlsx binary",
    "*.xlsm binary",
    "*.ods binary",
    "*.odt binary",
    "*.odp binary",
    "",
    "# Archives and packaged artifacts",
    "*.zip binary",
    "*.gz binary",
    "*.tgz binary",
    "*.bz2 binary",
    "*.xz binary",
    "*.7z binary",
    "*.rar binary",
    "*.tar binary",
    "*.jar binary",
    "*.war binary",
    "*.nupkg binary",
    "*.whl binary",
    "",
    "# Media and fonts",
    "*.mp3 binary",
    "*.mp4 binary",
    "*.mov binary",
    "*.avi binary",
    "*.webm binary",
    "*.wav binary",
    "*.flac binary",
    "*.ogg binary",
    "*.ttf binary",
    "*.otf binary",
    "*.woff binary",
    "*.woff2 binary",
    "",
    "# Executables, libraries, bytecode, and databases",
    "*.exe binary",
    "*.dll binary",
    "*.so binary",
    "*.dylib binary",
    "*.a binary",
    "*.lib binary",
    "*.class binary",
    "*.pyc binary",
    "*.wasm binary",
    "*.sqlite binary",
    "*.sqlite3 binary",
    "*.db binary",
]
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
    "out",
    "pkg",
    "extension-dist",
    "_build",
    ".output",
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

    detected_components = classify_components(repo, dedupe_components(components), unique_sorted(ci_systems), unique_sorted(task_runners))

    selection_defaults = {
        "architecture": choose_architecture(distribution_hints),
        "ci_mode": choose_ci_mode(unique_sorted(languages), unique_sorted(ci_systems), detected_components, unique_sorted(task_runners)),
        "release_overlay": bool(binary_targets and not dist_exists),
        "dist_storage": "git-lfs" if dist_lfs_tracked else ("git" if dist_exists and not dist_ignored else ("artifacts" if binary_targets else "none")),
        "change_detection": "none",
    }

    detected = {
        "repo_root": str(repo.resolve()),
        "languages": unique_sorted(languages),
        "build_tools": unique_sorted(build_tools),
        "frameworks": unique_sorted(frameworks),
        "components": detected_components,
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


def component_depth(component: dict[str, Any]) -> int:
    path = component["path"]
    if path == ".":
        return 0
    return len([part for part in path.split("/") if part])


def component_root_path(repo: Path, component: dict[str, Any]) -> Path:
    return repo / component["path"] if component["path"] != "." else repo


def workspace_member_patterns(repo: Path, component: dict[str, Any]) -> list[str]:
    root = component_root_path(repo, component)
    path = component["path"]
    patterns: list[str] = []
    if component["language"] == "rust":
        cargo_toml = root / "Cargo.toml"
        data = read_toml(cargo_toml) if cargo_toml.exists() else {}
        workspace = data.get("workspace", {}) if isinstance(data, dict) else {}
        members = workspace.get("members", []) if isinstance(workspace, dict) else []
        if isinstance(members, list):
            for item in members:
                if isinstance(item, str):
                    patterns.append(item if path == "." else f"{path}/{item}")
    if component["language"] == "javascript":
        package_json_path = root / "package.json"
        package_json = read_json(package_json_path) if package_json_path.exists() else {}
        workspaces = package_json.get("workspaces")
        packages: list[str] = []
        if isinstance(workspaces, list):
            packages = [item for item in workspaces if isinstance(item, str)]
        elif isinstance(workspaces, dict):
            raw_packages = workspaces.get("packages", [])
            if isinstance(raw_packages, list):
                packages = [item for item in raw_packages if isinstance(item, str)]
        for item in packages:
            patterns.append(item if path == "." else f"{path}/{item}")
    return patterns


def workspace_member_watch_patterns(repo: Path, component: dict[str, Any]) -> list[str]:
    patterns: list[str] = []
    for item in workspace_member_patterns(repo, component):
        normalized = item.rstrip("/")
        if not normalized:
            continue
        if any(char in normalized for char in "*?["):
            patterns.append(normalized)
        else:
            patterns.append(f"{normalized}/**")
    return unique_preserve_order(patterns)


def matches_workspace_patterns(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def component_has_runnable_surface(repo: Path, component: dict[str, Any]) -> bool:
    root = component_root_path(repo, component)
    language = component["language"]
    if component["path"] == "." or component.get("workspace"):
        return True
    if language == "javascript":
        scripts = component.get("scripts", [])
        if isinstance(scripts, list) and scripts:
            return True
        return any((root / name).exists() for name in ["package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb"])
    if language == "rust":
        return bool(component.get("binary_targets")) or (root / "src" / "main.rs").exists() or (root / "src" / "lib.rs").exists()
    if language == "python":
        return any((root / name).exists() for name in ["pyproject.toml", "setup.py", "requirements.txt", "requirements-dev.txt"])
    if language == "go":
        return (root / "go.mod").exists()
    if language == "dotnet":
        return any(root.glob("*.csproj")) or any(root.glob("*.sln"))
    if language == "java":
        return any((root / name).exists() for name in ["pom.xml", "build.gradle", "build.gradle.kts"])
    if language == "cpp":
        return (root / "CMakeLists.txt").exists()
    if language == "zig":
        return (root / "build.zig").exists()
    if language == "ruby":
        return (root / "Gemfile").exists()
    if language == "elixir":
        return (root / "mix.exs").exists()
    return False


def classify_components(repo: Path, components: list[dict[str, Any]], ci_systems: list[str], task_runners: list[str]) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    top_level_component_set = bool(components) and all(component_depth(component) <= 1 for component in components if component["path"] != ".")
    workspace_patterns: list[str] = []
    for component in components:
        if component.get("workspace"):
            workspace_patterns.extend(workspace_member_patterns(repo, component))

    for component in components:
        candidate = dict(component)
        runnable_surface = component_has_runnable_surface(repo, component)
        evidence_strength = "weak"
        promotion = "candidate"
        promotion_reason = "nested-or-ambiguous-surface"
        depth = component_depth(component)

        if not runnable_surface:
            promotion_reason = "no-defendable-runnable-surface"
        elif component["path"] == ".":
            evidence_strength = "strong"
            promotion = "promoted"
            promotion_reason = "repo-root-surface"
        elif component.get("workspace"):
            evidence_strength = "strong"
            promotion = "promoted"
            promotion_reason = "workspace-root-surface"
        elif matches_workspace_patterns(component["path"], workspace_patterns):
            evidence_strength = "strong"
            promotion = "promoted"
            promotion_reason = "workspace-member"
        elif depth == 1 and top_level_component_set:
            evidence_strength = "strong"
            promotion = "promoted"
            promotion_reason = "top-level-component-set"
        elif depth == 1 and (ci_systems or task_runners):
            evidence_strength = "strong"
            promotion = "promoted"
            promotion_reason = "repo-level-tasking-signals"

        candidate["evidence_strength"] = evidence_strength
        candidate["promotion"] = promotion
        candidate["promotion_reason"] = promotion_reason
        candidate["runnable_surface"] = runnable_surface
        classified.append(candidate)
    return classified


def promoted_components(detected: dict[str, Any]) -> list[dict[str, Any]]:
    return [component for component in detected.get("components", []) if component.get("promotion") == "promoted"]


def promoted_runnable_components(detected: dict[str, Any]) -> list[dict[str, Any]]:
    return [component for component in promoted_components(detected) if component.get("runnable_surface")]


def choose_ci_mode(languages: list[str], ci_systems: list[str], components: list[dict[str, Any]], task_runners: list[str]) -> str:
    promoted = [component for component in components if component.get("promotion") == "promoted" and component.get("runnable_surface", True)]
    promoted_languages = unique_sorted([component["language"] for component in promoted])
    if any(system != "github-actions" for system in ci_systems):
        return "none"
    if not promoted and not task_runners:
        return "none"
    if not promoted_languages and not promoted and not task_runners:
        return "none"
    if ci_systems:
        return "direct"
    if len(promoted_languages) > 1 or len(promoted) > 1:
        return "direct"
    return "just"


def derive_notes(detected: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    components = detected.get("components", [])
    promoted = promoted_components(detected)
    promoted_runnable = promoted_runnable_components(detected)
    candidate_components = [component for component in components if component.get("promotion") != "promoted"]
    task_runners = detected.get("task_runners", [])
    hints = detected.get("distribution_hints", {})
    if not promoted_runnable and not task_runners:
        notes.append("No build tool or task runner was detected. Generate a placeholder harness and replace the canonical recipes with project-specific commands.")
    if hints.get("has_compiled_binaries") and not hints.get("dist_exists"):
        notes.append("Compiled binary targets were detected without an existing dist/. Choose explicitly between local-dist, committed-dist, cross-os-dist, or CI-built artifacts.")
    if hints.get("dist_exists") and not hints.get("dist_ignored") and not hints.get("dist_lfs_tracked"):
        notes.append("Committed dist/ outputs will add binary blobs to Git history over time. Prefer Git LFS or CI-built release assets when binaries are large or change frequently.")
    if hints.get("dist_lfs_tracked"):
        notes.append("dist/ appears to be tracked by Git LFS. Verify archive behavior and bandwidth settings before relying on repository ZIP downloads.")
    if any(system != "github-actions" for system in detected.get("ci_systems", [])):
        notes.append("A non-GitHub CI system is present, so GitHub workflow generation defaults to none unless you override it.")
    if len(promoted) > 1:
        notes.append("Multiple components were detected. Prefer component-prefixed recipes plus aggregate top-level recipes.")
    if candidate_components:
        summary = ", ".join(component["path"] for component in candidate_components[:5])
        if len(candidate_components) > 5:
            summary += ", ..."
        notes.append(f"Candidate components were detected but withheld from generated surfaces until stronger repo-level evidence exists: {summary}.")
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
    # Keep component-scoped commands self-contained so multiline CI run blocks
    # do not inherit a prior `cd` from an earlier command.
    return f"(cd {shell_quote_path(path)} && {command})"


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

    for component in promoted_runnable_components(detected):
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

    for component in promoted_runnable_components(detected):
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


def canonical_recipe_doc(recipe: str) -> str:
    docs = {
        "bootstrap": "Install dependencies, tooling, and local prerequisites for normal development",
        "build": "Compile the detected project surfaces in the default build profile",
        "release": "Compile optimized or distributable outputs for release packaging",
        "test": "Run the repo's automated test surface",
        "lint": "Run static analysis and policy checks",
        "fmt": "Rewrite source files into the canonical project style",
        "fmt-check": "Verify formatting without rewriting source files",
        "ci": "Run the pull-request verification surface in local sequence",
        "clean": "Remove generated build artifacts and local caches",
        "dev": "Start the main interactive developer loop",
        "hooks-install": "Install repo-owned Git hooks for this clone",
        "docker-build": "Build the repo's Docker images or compose services",
        "docker-up": "Start the repo's Docker services in the background",
        "docker-down": "Stop running Docker services for this repo",
        "docker-logs": "Stream Docker service logs for local debugging",
        "docker-clean": "Remove Docker volumes, caches, and local images created for this repo",
    }
    return docs[recipe]


def component_recipe_doc(recipe: str, label: str) -> str:
    docs = {
        "bootstrap": f"Install dependencies and local prerequisites only for {label}",
        "build": f"Compile only {label} in the default build profile",
        "release": f"Compile optimized or distributable outputs only for {label}",
        "test": f"Run automated tests only for {label}",
        "lint": f"Run static analysis and policy checks only for {label}",
        "fmt": f"Rewrite source files into the canonical style only for {label}",
        "fmt-check": f"Verify formatting only for {label} without rewriting files",
        "clean": f"Remove generated build artifacts only for {label}",
        "dev": f"Start the main interactive developer loop only for {label}",
    }
    return docs[recipe]


def render_recipe_block(name: str, lines: list[str], *, args: bool = False, doc: str | None = None, private: bool = False, deps: list[str] | None = None, allow_empty: bool = False) -> str:
    head = ""
    if doc:
        doc = " ".join(doc.split())
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
    if any("cargo" in cmd for cmds in commands.values() for cmd in cmds):
        lines.append("# Cargo may be installed in ~/.cargo/bin which non-login shells miss")
        lines.append('export PATH := env_var("HOME") / ".cargo" / "bin" + ":" + env_var("PATH")')
    if any("dotnet" in cmd for cmds in commands.values() for cmd in cmds):
        lines.append("# dotnet commands rely on the installed SDK")
    return ("\n".join(lines) + "\n\n") if lines else ""


def display_language(language: str) -> str:
    names = {
        "csharp": "C#",
        "javascript": "JavaScript",
        "rust": "Rust",
        "typescript": "TypeScript",
    }
    return names.get(language, language)


def component_label(component: dict[str, Any]) -> str:
    if component["path"] != ".":
        return component["path"]
    language = display_language(component["language"])
    if component.get("workspace"):
        return f"the repo-root {language} workspace"
    return f"the repo-root {language} surface"


def render_component_recipe_blocks(repo: Path, detected: dict[str, Any]) -> str:
    components = promoted_runnable_components(detected)
    if len(components) <= 1 and not any(component.get("workspace") for component in components):
        return ""
    blocks: list[str] = []
    for component in components:
        prefix = component_prefix(component)
        label = component_label(component)
        commands = commands_for_component(component, repo)
        specs = [
            ("build", True),
            ("release", False),
            ("test", True),
            ("lint", False),
            ("fmt", False),
            ("fmt-check", False),
            ("clean", False),
            ("bootstrap", False),
            ("dev", True),
        ]
        for recipe, has_args in specs:
            lines = commands.get(recipe, [])
            if not lines:
                continue
            blocks.append(render_recipe_block(f"{prefix}-{recipe}", lines, args=has_args, doc=component_recipe_doc(recipe, label)))
    return "".join(blocks)


def guidance_comment_block(detected: dict[str, Any]) -> str:
    if promoted_runnable_components(detected) or detected.get("task_runners"):
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
    dist_block += render_recipe_block("dist", dist_lines, doc="Compile release outputs and stage them into dist/ for local packaging")
    dist_block += render_recipe_block("_stage", stage_lines, private=True, doc="Internal helper that copies compiled release outputs into dist/")
    dist_block += render_recipe_block("clean-build", unique_preserve_order(plan["clean_build"]), doc="Remove compiled build artifacts while preserving staged dist outputs")
    clean_dist_doc = "Remove staged dist payloads without touching source files"
    if preserve_dist:
        clean_dist_doc = "Remove staged dist payloads. Use only when you intend to rebuild or restore committed deliverables."
    dist_block += render_recipe_block("clean-dist", ['rm -rf "{{ dist_dir }}"'], doc=clean_dist_doc)
    if preserve_dist:
        dist_block += render_recipe_block("clean", ["just clean-build"], doc="Remove build artifacts while preserving committed dist deliverables")
    else:
        dist_block += render_recipe_block("clean", ["just clean-build", "just clean-dist"], doc="Remove both compiled build artifacts and staged dist payloads")
    return dist_block, dist_variables


def should_generate_repo_hooks(architecture: str, dist_storage: str) -> bool:
    return architecture in {"committed-dist", "cross-os-dist"} and dist_storage in {"git", "git-lfs"}


def render_repo_hook() -> str:
    return (
        "#!/usr/bin/env sh\n"
        "# Generated by project-harness.\n"
        "# project-harness: managed-file\n"
        "set -eu\n\n"
        "if ! command -v just >/dev/null 2>&1; then\n"
        "  echo \"error: just is required for the managed pre-push hook\" >&2\n"
        "  exit 1\n"
        "fi\n\n"
        "just ci\n"
        "just dist\n"
        "dist_status=$(git status --short -- dist || true)\n"
        "if [ -n \"$dist_status\" ]; then\n"
        "  echo \"error: dist/ changed after local verification. Commit refreshed dist outputs before pushing.\" >&2\n"
        "  printf '%s\\n' \"$dist_status\" >&2\n"
        "  exit 1\n"
        "fi\n"
    )


def render_hooks_block() -> str:
    return render_recipe_block(
        "hooks-install",
        [
            "chmod +x githooks/pre-push",
            "git config --local core.hooksPath githooks",
        ],
        doc=canonical_recipe_doc("hooks-install"),
    )


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

    ci_block = render_recipe_block("ci", [], doc=canonical_recipe_doc("ci"), deps=["lint", "fmt-check", "test"], allow_empty=True)
    clean_block = ""
    hooks_block = ""
    if architecture not in {"local-dist", "committed-dist", "cross-os-dist"}:
        clean_block = render_recipe_block("clean", commands["clean"], doc=canonical_recipe_doc("clean"))
    if should_generate_repo_hooks(architecture, dist_storage):
        hooks_block = render_hooks_block()
    bootstrap_block = render_recipe_block("bootstrap", commands["bootstrap"], doc=canonical_recipe_doc("bootstrap"))
    dev_block = render_recipe_block("dev", commands.get("dev", []), args=True, doc=canonical_recipe_doc("dev"))
    docker_block = ""
    if detected["docker"]["compose_files"]:
        docker_block += render_recipe_block("docker-build", commands.get("docker-build", []), doc=canonical_recipe_doc("docker-build"))
        docker_block += render_recipe_block("docker-up", commands.get("docker-up", []), doc=canonical_recipe_doc("docker-up"))
        docker_block += render_recipe_block("docker-down", commands.get("docker-down", []), doc=canonical_recipe_doc("docker-down"))
        docker_block += render_recipe_block("docker-logs", commands.get("docker-logs", []), doc=canonical_recipe_doc("docker-logs"))
        docker_block += render_recipe_block("docker-clean", commands.get("docker-clean", []), doc=canonical_recipe_doc("docker-clean"))

    replacements = {
        "__GUIDANCE_BLOCK__": guidance_comment_block(detected),
        "__VARIABLES__": build_variable_block(commands, architecture),
        "__COMPONENT_BLOCKS__": render_component_recipe_blocks(repo, detected),
        "__DIST_VARIABLES__": dist_variables,
        "__BUILD_BLOCK__": render_recipe_block("build", commands["build"], args=True, doc=canonical_recipe_doc("build")),
        "__RELEASE_BLOCK__": render_recipe_block("release", [strip_args_placeholder(line) for line in (commands["release"] or commands["build"])], doc=canonical_recipe_doc("release")),
        "__DIST_BLOCK__": dist_block,
        "__TEST_BLOCK__": render_recipe_block("test", commands["test"], args=True, doc=canonical_recipe_doc("test")),
        "__LINT_BLOCK__": render_recipe_block("lint", commands["lint"], doc=canonical_recipe_doc("lint")),
        "__FMT_BLOCK__": render_recipe_block("fmt", commands["fmt"], doc=canonical_recipe_doc("fmt")),
        "__FMT_CHECK_BLOCK__": render_recipe_block("fmt-check", commands["fmt-check"], doc=canonical_recipe_doc("fmt-check")),
        "__CI_BLOCK__": ci_block,
        "__HOOKS_BLOCK__": hooks_block,
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
    components = promoted_runnable_components(detected)
    languages = {component["language"] for component in components}
    package_managers = {component.get("package_manager", component.get("build_tool")) for component in components}
    build_tools = {component["build_tool"] for component in components}

    def component_root(component: dict[str, Any]) -> Path:
        path = component["path"]
        return repo / path if path != "." else repo

    def existing_paths(candidates: list[Path]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for candidate in candidates:
            if not candidate.exists():
                continue
            rel = candidate.relative_to(repo).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            out.append(rel)
        return out

    def add_multiline_input(key: str, values: list[str]) -> None:
        if not values:
            return
        if len(values) == 1:
            steps.extend([f"          {key}: {values[0]}"])
            return
        steps.extend([f"          {key}: |"])
        for value in values:
            steps.extend([f"            {value}"])

    def cache_paths_for(language: str, build_tool: str, filenames: list[str]) -> list[str]:
        paths: list[str] = []
        for component in components:
            if component["language"] != language or component.get("build_tool") != build_tool:
                continue
            root = component_root(component)
            paths.extend(existing_paths([root / name for name in filenames]))
        return paths

    if "python" in languages:
        python_cache_paths = cache_paths_for("python", "pip", ["requirements.txt", "requirements-dev.txt", "pyproject.toml"])
        poetry_cache_paths = cache_paths_for("python", "poetry", ["poetry.lock", "pyproject.toml"])
        uv_cache_paths = cache_paths_for("python", "uv", ["uv.lock", "pyproject.toml", "requirements.txt", "requirements-dev.txt"])
        steps.extend([
            "      - uses: actions/setup-python@v6",
            "        with:",
            "          python-version: '3.x'  # latest stable Python 3",
        ])
        if "poetry" in build_tools:
            steps.extend(["          cache: 'poetry'"])
            add_multiline_input("cache-dependency-path", poetry_cache_paths)
        elif "pip" in build_tools and "uv" not in build_tools:
            steps.extend(["          cache: 'pip'"])
            add_multiline_input("cache-dependency-path", python_cache_paths)
        if "uv" in build_tools:
            steps.extend([
                "      - uses: astral-sh/setup-uv@v6",
                "        with:",
                "          enable-cache: true",
            ])
            add_multiline_input("cache-dependency-glob", uv_cache_paths)
        if "poetry" in build_tools:
            steps.extend([
                "      - name: Install Poetry",
                "        shell: bash",
                "        run: python -m pip install --upgrade pip poetry",
            ])
    if "javascript" in languages:
        pnpm_cache_paths: list[str] = []
        yarn_cache_paths: list[str] = []
        npm_cache_paths: list[str] = []
        for component in components:
            if component["language"] != "javascript":
                continue
            root = component_root(component)
            manager = component.get("package_manager")
            if manager == "pnpm":
                pnpm_cache_paths.extend(existing_paths([root / "pnpm-lock.yaml"]))
            elif manager == "yarn":
                yarn_cache_paths.extend(existing_paths([root / "yarn.lock"]))
            elif manager == "npm":
                npm_cache_paths.extend(existing_paths([root / "package-lock.json", root / "npm-shrinkwrap.json"]))
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
            add_multiline_input("cache-dependency-path", pnpm_cache_paths)
        elif "yarn" in package_managers:
            steps.extend(["          cache: 'yarn'"])
            add_multiline_input("cache-dependency-path", yarn_cache_paths)
        elif "npm" in package_managers or not package_managers:
            steps.extend(["          cache: 'npm'"])
            add_multiline_input("cache-dependency-path", npm_cache_paths)
    if "go" in languages:
        go_cache_paths: list[str] = []
        for component in components:
            if component["language"] != "go":
                continue
            go_cache_paths.extend(existing_paths([component_root(component) / "go.sum"]))
        steps.extend([
            "      - uses: actions/setup-go@v6",
            "        with:",
            "          go-version: 'stable'",
        ])
        add_multiline_input("cache-dependency-path", go_cache_paths)
    if "rust" in languages:
        steps.extend([
            "      - uses: dtolnay/rust-toolchain@stable",
            "        with:",
            "          components: clippy, rustfmt",
            "      - uses: Swatinem/rust-cache@v2",
        ])
    if "java" in languages:
        gradle_cache_paths = cache_paths_for(
            "java",
            "gradle",
            [
                "build.gradle",
                "build.gradle.kts",
                "settings.gradle",
                "settings.gradle.kts",
                "gradle/libs.versions.toml",
                "gradle/wrapper/gradle-wrapper.properties",
            ],
        )
        maven_cache_paths = cache_paths_for("java", "maven", ["pom.xml"])
        steps.extend([
            "      - uses: actions/setup-java@v5",
            "        with:",
            "          distribution: 'temurin'",
            "          java-version: '21'",
            "          check-latest: true",
        ])
        if "gradle" in build_tools and "maven" not in build_tools:
            steps.extend(["          cache: 'gradle'"])
            add_multiline_input("cache-dependency-path", gradle_cache_paths)
        elif "maven" in build_tools and "gradle" not in build_tools:
            steps.extend(["          cache: 'maven'"])
            add_multiline_input("cache-dependency-path", maven_cache_paths)
    if "dotnet" in languages:
        steps.extend([
            "      - uses: actions/setup-dotnet@v4",
            "        with:",
            "          dotnet-version: '9.0.x'",
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
            "          otp-version: '> 0'",
            "          elixir-version: '> 0'",
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


def ci_layout_default(detected: dict[str, Any], ci_mode: str) -> str:
    return "single"


def replace_trigger_block(template: str, trigger_block: str) -> str:
    default_block = "on:\n  push:\n    branches: [main]\n  pull_request:\n"
    return template.replace(default_block, trigger_block + "\n", 1)


def trigger_block_body(trigger_block: str) -> str:
    lines = trigger_block.splitlines()
    if not lines or lines[0] != "on:":
        return trigger_block
    return "\n".join(f"  {line}" for line in lines[1:])


def render_ci_trigger_block(detected: dict[str, Any], ci_paths: str) -> tuple[str, list[str]]:
    if ci_paths != "components":
        return "on:\n  push:\n    branches: [main]\n  pull_request:", []

    components = promoted_runnable_components(detected)
    component_paths = sorted({component["path"] for component in components if component["path"] != "."})
    if any(component["path"] == "." for component in components):
        return (
            "on:\n  push:\n    branches: [main]\n  pull_request:",
            ["component path filters were omitted because root-level components or workspace manifests can change generated CI behavior"],
        )
    if len(component_paths) < 2:
        return (
            "on:\n  push:\n    branches: [main]\n  pull_request:",
            ["component path filters require at least two non-root components; filter overlay was omitted"],
        )

    tracked_paths = [
        ".github/workflows/**",
        ".github/CODEOWNERS",
        ".gitattributes",
        ".gitignore",
        "justfile",
        "Makefile",
        "Taskfile.yml",
        "Taskfile.yaml",
        "taskfile.yml",
        "taskfile.yaml",
        *[f"{path}/**" for path in component_paths],
    ]
    lines = [
        "on:",
        "  push:",
        "    branches: [main]",
        "    paths:",
    ]
    lines.extend([f"      - '{path}'" for path in tracked_paths])
    lines.extend([
        "  pull_request:",
        "    paths:",
    ])
    lines.extend([f"      - '{path}'" for path in tracked_paths])
    return "\n".join(lines), []


def render_ci_job(
    job_id: str,
    job_name: str,
    steps: list[str],
    needs: list[str] | None = None,
    job_if: str | None = None,
) -> str:
    lines = [f"  {job_id}:", f"    name: {job_name}"]
    if needs:
        if len(needs) == 1:
            lines.append(f"    needs: {needs[0]}")
        else:
            lines.append("    needs:")
            lines.extend([f"      - {need}" for need in needs])
    if job_if:
        lines.append(f"    if: {job_if}")
    lines.extend([
        "    runs-on: ubuntu-latest",
        "    timeout-minutes: 20",
        "    defaults:",
        "      run:",
        "        shell: bash",
        "    steps:",
        "      - uses: actions/checkout@v6",
        "        with:",
        "          fetch-depth: 1",
    ])
    lines.extend(steps)
    return "\n".join(lines)


def prefixed_patterns(prefix: str, patterns: list[str]) -> list[str]:
    if prefix == ".":
        return patterns
    return [f"{prefix}/{pattern}" for pattern in patterns]


def component_wide_pattern(prefix: str) -> str:
    return "**" if prefix == "." else f"{prefix}/**"


def change_detection_patterns_for_component(repo: Path, component: dict[str, Any]) -> tuple[list[str], list[str]]:
    prefix = component["path"]
    language = component["language"]
    warnings: list[str] = []

    if language == "rust":
        patterns = prefixed_patterns(prefix, [
            "Cargo.toml",
            "Cargo.lock",
            "build.rs",
            ".cargo/config",
            ".cargo/config.toml",
            "src/**",
            "tests/**",
            "examples/**",
            "benches/**",
        ])
        patterns.extend([
            ".cargo/config",
            ".cargo/config.toml",
        ])
        patterns.extend(workspace_member_watch_patterns(repo, component))
        return patterns, warnings

    if language == "javascript":
        patterns = prefixed_patterns(prefix, [
            "package.json",
            "package-lock.json",
            "npm-shrinkwrap.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "bun.lock",
            "bun.lockb",
            "tsconfig.json",
            "tsconfig.*.json",
            "vite.config.*",
            "vitest.config.*",
            "webpack.config.*",
            "rollup.config.*",
            "babel.config.*",
            "index.html",
            "public/**",
            "src/**",
            "lib/**",
            "test/**",
            "tests/**",
            "scripts/**",
            "*.js",
            "*.cjs",
            "*.mjs",
            "*.ts",
            "*.cts",
            "*.mts",
            "*.tsx",
        ])
        patterns.extend(workspace_member_watch_patterns(repo, component))
        return patterns, warnings

    if language == "python":
        return prefixed_patterns(prefix, [
            "pyproject.toml",
            "requirements.txt",
            "requirements-dev.txt",
            "requirements-test.txt",
            "requirements/*.txt",
            "setup.py",
            "setup.cfg",
            "poetry.lock",
            "uv.lock",
            "Pipfile",
            "Pipfile.lock",
            "src/**",
            "tests/**",
            "scripts/**",
            "*.py",
        ]), warnings

    if language == "go":
        patterns = prefixed_patterns(prefix, [
            "go.mod",
            "go.sum",
            "*.go",
            "cmd/**",
            "pkg/**",
            "internal/**",
            "tests/**",
        ])
        patterns.extend([
            "go.work",
            "go.work.sum",
        ])
        return patterns, warnings

    if language in {"java", "kotlin"}:
        return prefixed_patterns(prefix, [
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "settings.gradle",
            "settings.gradle.kts",
            "gradle.properties",
            "gradle/**",
            "gradlew",
            "gradlew.bat",
            "src/**",
            "tests/**",
        ]), warnings

    if language == "dotnet":
        patterns = prefixed_patterns(prefix, [
            "*.sln",
            "*.csproj",
            "*.fsproj",
            "*.vbproj",
            "packages.lock.json",
            "Directory.Build.props",
            "Directory.Build.targets",
            "*.cs",
            "*.fs",
            "*.vb",
            "*.resx",
            "*.props",
            "*.targets",
            "Properties/**",
            "appsettings.json",
            "appsettings.*.json",
            "wwwroot/**",
            "src/**",
            "tests/**",
        ])
        patterns.append("global.json")
        return patterns, warnings

    if language == "cpp":
        patterns = prefixed_patterns(prefix, [
            "CMakeLists.txt",
            "cmake/**",
            "*.c",
            "*.cc",
            "*.cpp",
            "*.cxx",
            "*.h",
            "*.hh",
            "*.hpp",
            "*.hxx",
            "app/**",
            "lib/**",
            "src/**",
            "include/**",
            "test/**",
            "tests/**",
        ])
        patterns.append(component_wide_pattern(prefix))
        return patterns, warnings

    if language == "zig":
        return prefixed_patterns(prefix, [
            "build.zig",
            "build.zig.zon",
            "src/**",
            "lib/**",
            "test/**",
            "tests/**",
        ]), warnings

    if language == "ruby":
        return prefixed_patterns(prefix, [
            "Gemfile",
            "Gemfile.lock",
            "Rakefile",
            "*.gemspec",
            "lib/**",
            "app/**",
            "config/**",
            "bin/**",
            "exe/**",
            "spec/**",
            "test/**",
        ]), warnings

    if language == "elixir":
        return prefixed_patterns(prefix, [
            "mix.exs",
            "mix.lock",
            "lib/**",
            "config/**",
            "priv/**",
            "test/**",
        ]), warnings

    warnings.append(
        f"git-diff change detection fell back to broad component watching for {prefix} because no language-specific watch model exists yet"
    )
    return [component_wide_pattern(prefix)], warnings


def build_change_detection_paths(repo: Path, detected: dict[str, Any]) -> tuple[list[str], list[str]]:
    repo_meta_patterns = [
        ".github/workflows/**",
        ".gitattributes",
        ".gitignore",
        "justfile",
        "Makefile",
        *sorted(TASKFILE_NAMES),
    ]
    component_patterns: list[str] = []
    warnings: list[str] = []

    for component in promoted_runnable_components(detected):
        derived_patterns, component_warnings = change_detection_patterns_for_component(repo, component)
        warnings.extend(component_warnings)
        component_patterns.extend(derived_patterns)

    if not component_patterns:
        warnings.append(
            "git-diff change detection did not derive any component-scoped build inputs; falling back to an unconditional build job"
        )
        return [], unique_preserve_order(warnings)

    patterns = repo_meta_patterns + component_patterns
    return unique_preserve_order(patterns), unique_preserve_order(warnings)


def render_git_diff_detection_job(job_id: str, job_name: str, output_name: str, patterns: list[str]) -> str:
    patterns_json = json.dumps(patterns, separators=(",", ":"))
    lines = [
        f"  {job_id}:",
        f"    name: {job_name}",
        "    runs-on: ubuntu-latest",
        "    timeout-minutes: 10",
        "    outputs:",
        f"      {output_name}: ${{{{ steps.detect.outputs.{output_name} }}}}",
        "    defaults:",
        "      run:",
        "        shell: bash",
        "    steps:",
        "      - uses: actions/checkout@v6",
        "        with:",
        "          fetch-depth: 0",
        "      - name: Detect build-relevant changes",
        "        id: detect",
        "        run: |",
        "          set -euo pipefail",
        "          event_name=\"${{ github.event_name }}\"",
        "          base_sha=\"\"",
        "          head_sha=\"${{ github.sha }}\"",
        "          if [ \"$event_name\" = \"pull_request\" ]; then",
        "            base_sha=\"${{ github.event.pull_request.base.sha }}\"",
        "          elif [ \"$event_name\" = \"push\" ]; then",
        "            base_sha=\"${{ github.event.before }}\"",
        "          fi",
        "          if [ -z \"$base_sha\" ] || [ \"$base_sha\" = \"0000000000000000000000000000000000000000\" ]; then",
        f"            echo \"{output_name}=true\" >> \"$GITHUB_OUTPUT\"",
        "            exit 0",
        "          fi",
        "          changed_files_file=\"$(mktemp)\"",
        "          git diff --name-only \"$base_sha\" \"$head_sha\" > \"$changed_files_file\"",
        "          CHANGED_FILES_PATH=\"$changed_files_file\" GITHUB_OUTPUT_PATH=\"$GITHUB_OUTPUT\" python3 - <<'PY'",
        "import fnmatch",
        "import json",
        "import os",
        "from pathlib import Path",
        "",
        f"patterns = {patterns_json}",
        "changed_files = [",
        "    (line.strip()[2:] if line.strip().startswith('./') else line.strip())",
        "    for line in Path(os.environ['CHANGED_FILES_PATH']).read_text(encoding='utf-8').splitlines()",
        "    if line.strip()",
        "]",
        "matched = any(",
        "    any(fnmatch.fnmatch(changed, pattern) for pattern in patterns)",
        "    for changed in changed_files",
        ")",
        "with open(os.environ['GITHUB_OUTPUT_PATH'], 'a', encoding='utf-8') as fh:",
        f"    fh.write('{output_name}=' + ('true' if matched else 'false') + '\\n')",
        "PY",
    ]
    return "\n".join(lines)


def render_split_direct_ci(
    repo: Path,
    trigger_block: str,
    detected: dict[str, Any],
    setup_steps: list[str],
    commands: dict[str, list[str]],
    change_detection: str,
) -> tuple[str, list[str]]:
    bootstrap_steps = render_direct_workflow_steps(commands["bootstrap"], "Bootstrap")
    lint_steps: list[str] = []
    lint_steps.extend(render_direct_workflow_steps(commands["fmt-check"], "Check formatting"))
    lint_steps.extend(render_direct_workflow_steps(commands["lint"], "Lint"))
    test_steps = render_direct_workflow_steps(commands["test"], "Test")
    build_lines = commands["build"] or commands["release"]
    build_steps = render_direct_workflow_steps(build_lines, "Build")
    warnings: list[str] = []
    pre_jobs = ""
    build_needs: list[str] | None = None
    build_if: str | None = None

    shared_steps = list(setup_steps) + bootstrap_steps
    jobs: dict[str, str] = {}
    if lint_steps:
        jobs["lint"] = render_ci_job("lint", "lint", shared_steps + lint_steps)
    if test_steps:
        jobs["test"] = render_ci_job("test", "test", shared_steps + test_steps)
    if build_steps:
        if change_detection == "git-diff":
            patterns, path_warnings = build_change_detection_paths(repo, detected)
            warnings.extend(path_warnings)
            if patterns:
                pre_jobs = render_git_diff_detection_job("detect-changes", "detect changes", "build_changed", patterns)
                build_needs = ["detect-changes"]
                build_if = "needs.detect-changes.outputs.build_changed == 'true'"
            else:
                warnings.append(
                    "git-diff change detection was requested but no build-relevant path groups were derived; falling back to an unconditional build job"
                )
        jobs["build"] = render_ci_job("build", "build", shared_steps + build_steps, needs=build_needs, job_if=build_if)
    elif change_detection == "git-diff":
        warnings.append(
            "git-diff change detection was requested but split direct CI did not produce a distinct build job; falling back to ordinary job execution"
        )

    if not jobs:
        run_steps = render_direct_workflow_steps(commands["bootstrap"], "Bootstrap")
        run_steps.extend(render_direct_workflow_steps(commands["test"], "Test"))
        jobs["lint"] = render_ci_job("ci", "ci", list(setup_steps) + run_steps)

    split_template = read_text(ASSETS_DIR / "workflow-ci-direct-split.yml.tpl")
    split_template = split_template.replace("__ON_BLOCK__", trigger_block_body(trigger_block))
    split_template = split_template.replace("__PRE_JOBS__", pre_jobs + ("\n\n" if pre_jobs else ""))
    split_template = split_template.replace("__LINT_JOB__", jobs.get("lint", ""))
    split_template = split_template.replace("__TEST_JOB__", jobs.get("test", ""))
    split_template = split_template.replace("__BUILD_JOB__", jobs.get("build", ""))
    return re.sub(r"\n{3,}", "\n\n", split_template).rstrip() + "\n", warnings


def render_ci_workflow(
    repo: Path,
    detected: dict[str, Any],
    ci_mode: str,
    ci_layout: str,
    ci_paths: str,
    change_detection: str,
) -> tuple[str, list[str]]:
    commands = make_initial_recipe_commands(repo, detected)
    setup_steps = workflow_setup_steps(repo, detected)
    trigger_block, warnings = render_ci_trigger_block(detected, ci_paths)
    if ci_mode == "just":
        template = read_text(ASSETS_DIR / "workflow-ci-just.yml.tpl")
        template = replace_trigger_block(template, trigger_block)
        setup_block = "\n".join(setup_steps)
        bootstrap_step = "\n".join([
            "      - name: Bootstrap",
            "        shell: bash",
            "        run: just bootstrap",
        ])
        output = template.replace("__SETUP_STEPS__", setup_block + ("\n" if setup_block else ""))
        output = output.replace("__BOOTSTRAP_STEP__", bootstrap_step + "\n")
        return output, warnings
    template = read_text(ASSETS_DIR / "workflow-ci-direct.yml.tpl")
    template = replace_trigger_block(template, trigger_block)
    if ci_layout == "split":
        split_output, split_warnings = render_split_direct_ci(repo, trigger_block, detected, setup_steps, commands, change_detection)
        return split_output, warnings + split_warnings
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
    return output, warnings


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
            "components": detected.get("components", []),
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


def render_gitattributes_section(architecture: str, dist_storage: str) -> str:
    lines = [
        GITATTRIBUTES_BEGIN,
        "# Generated by project-harness. Review before editing.",
        GITATTRIBUTES_SECTION_MARKER,
        *GITATTRIBUTES_TEXT_RULES,
        "",
    ]
    if dist_storage == "git-lfs" and architecture in {"committed-dist", "cross-os-dist"}:
        lines.extend([
            "# Project Harness committed distribution outputs",
            "dist/** filter=lfs diff=lfs merge=lfs -text",
            "",
        ])
    lines.extend([
        *GITATTRIBUTES_BINARY_RULES,
        GITATTRIBUTES_END,
    ])
    return "\n".join(lines).rstrip() + "\n"


def insertion_index_after_leading_comments(lines: list[str]) -> int:
    index = 0
    while index < len(lines) and (lines[index].strip() == "" or lines[index].lstrip().startswith("#")):
        index += 1
    return index


def merge_gitattributes(existing: str, managed_section: str) -> str:
    existing_lines = existing.splitlines()
    begin_index = next((idx for idx, line in enumerate(existing_lines) if line.strip() == GITATTRIBUTES_BEGIN), None)
    end_index = next((idx for idx, line in enumerate(existing_lines) if line.strip() == GITATTRIBUTES_END), None)
    section_lines = managed_section.rstrip("\n").splitlines()

    if begin_index is not None and end_index is not None and begin_index <= end_index:
        merged = [*existing_lines[:begin_index], *section_lines, *existing_lines[end_index + 1 :]]
    else:
        insert_at = insertion_index_after_leading_comments(existing_lines)
        prefix = existing_lines[:insert_at]
        suffix = existing_lines[insert_at:]
        merged = [*prefix]
        if merged and merged[-1].strip() != "":
            merged.append("")
        merged.extend(section_lines)
        if suffix:
            merged.append("")
            merged.extend(suffix)

    return "\n".join(merged).rstrip() + "\n"


def render_gitattributes_file(repo: Path, architecture: str, dist_storage: str) -> str:
    section = render_gitattributes_section(architecture, dist_storage)
    gitattributes = repo / ".gitattributes"
    existing = gitattributes.read_text(encoding="utf-8", errors="ignore") if gitattributes.exists() else ""
    return merge_gitattributes(existing, section)


def ensure_gitattributes(repo: Path, architecture: str, dist_storage: str) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    gitattributes = repo / ".gitattributes"
    content = render_gitattributes_file(repo, architecture, dist_storage)
    existing = gitattributes.read_text(encoding="utf-8", errors="ignore") if gitattributes.exists() else ""
    if existing == content:
        return False, warnings
    gitattributes.write_text(content, encoding="utf-8")
    warnings.append("updated repo-root .gitattributes with the project-harness managed baseline")
    return True, warnings


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
    existing_state, existing_state_warnings = load_state(repo)
    existing_selected = existing_state.get("selected", {}) if isinstance(existing_state, dict) else {}
    detected = detect_components(repo)
    architecture = args.architecture if args.architecture != "auto" else str(existing_selected.get("architecture", detected["selection_defaults"]["architecture"]))
    ci_mode = args.ci_mode if args.ci_mode != "auto" else str(existing_selected.get("ci_mode", detected["selection_defaults"]["ci_mode"]))
    ci_layout_default_value = ci_layout_default(detected, ci_mode)
    ci_layout = args.ci_layout if args.ci_layout != "auto" else str(existing_selected.get("ci_layout", ci_layout_default_value))
    ci_paths = args.ci_paths if args.ci_paths != "none" or "ci_paths" not in existing_selected else str(existing_selected.get("ci_paths", "none"))
    dist_storage = args.dist_storage if args.dist_storage != "auto" else str(existing_selected.get("dist_storage", detected["selection_defaults"].get("dist_storage", "none")))
    change_detection = (
        args.change_detection
        if args.change_detection != "auto"
        else str(existing_selected.get("change_detection", detected["selection_defaults"].get("change_detection", "none")))
    )
    warnings: list[str] = [*existing_state_warnings, *detected.get("notes", [])]
    if dist_storage == "artifacts" and architecture in {"committed-dist", "cross-os-dist"}:
        warnings.append("artifact-based dist storage conflicts with a committed dist architecture; prefer local-dist/general plus a release overlay")
    if dist_storage == "git-lfs" and architecture not in {"committed-dist", "cross-os-dist"}:
        warnings.append("Git LFS tracking only matters for committed dist outputs; local-dist/general usually should not add dist/** to .gitattributes")
    if ci_mode != "direct" and ci_layout == "split":
        warnings.append("split CI layout only applies to direct CI; falling back to a single job")
        ci_layout = "single"
    if change_detection == "git-diff" and ci_mode != "direct":
        warnings.append("git-diff change detection is currently generated only for direct CI; falling back to none")
        change_detection = "none"
    if change_detection == "git-diff" and ci_layout != "split":
        warnings.append("git-diff change detection currently requires split direct CI with a distinct build job; falling back to none")
        change_detection = "none"

    justfile_content, just_warnings = render_justfile(repo, detected, architecture, dist_storage)
    warnings.extend(just_warnings)
    ci_content = ""
    if ci_mode != "none":
        ci_content, ci_warnings = render_ci_workflow(repo, detected, ci_mode, ci_layout, ci_paths, change_detection)
        warnings.extend(ci_warnings)
    if args.release_overlay is not None:
        release_requested = bool(args.release_overlay)
    elif args.architecture != "auto":
        release_requested = False
    elif "release_overlay" in existing_selected:
        release_requested = bool(existing_selected.get("release_overlay"))
    else:
        release_requested = bool(detected["selection_defaults"].get("release_overlay"))
    if architecture == "cross-os-dist" and args.release_overlay is not False:
        release_requested = True
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
    hook_candidate = out_dir / "githooks" / "pre-push"
    gitattributes_candidate = out_dir / ".gitattributes"
    for stale_candidate in [just_candidate, ci_candidate, release_candidate, hook_candidate, gitattributes_candidate]:
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
    hook_content = render_repo_hook() if should_generate_repo_hooks(architecture, dist_storage) else ""
    if hook_content:
        write_candidate(hook_candidate, hook_content)
        hook_candidate.chmod(0o755)
        candidates.append("githooks/pre-push")
    gitattributes_content = render_gitattributes_file(repo, architecture, dist_storage)
    write_candidate(gitattributes_candidate, gitattributes_content)
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

        if hook_content:
            hook_target = repo / "githooks" / "pre-push"
            hook_ok, _ = safe_write_target(hook_target, hook_content)
            if hook_ok:
                hook_target.chmod(0o755)
                managed_writes.append("githooks/pre-push")
            else:
                candidate_only.append("githooks/pre-push")
                warnings.append("existing unmanaged githooks/pre-push was not overwritten")

        warnings.extend(ensure_gitignore(repo, architecture))
        gitattributes_changed, gitattributes_warnings = ensure_gitattributes(repo, architecture, dist_storage)
        if gitattributes_changed:
            managed_writes.append(".gitattributes")
        warnings.extend(gitattributes_warnings)

    warnings = unique_preserve_order(warnings)

    selected = {
        "architecture": architecture,
        "ci_mode": ci_mode,
        "ci_layout": ci_layout,
        "ci_paths": ci_paths,
        "change_detection": change_detection,
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
    existing_state, _existing_state_warnings = load_state(repo)
    existing_selected = existing_state.get("selected", {}) if isinstance(existing_state, dict) else {}
    detected = detect_components(repo)
    architecture = str(existing_selected.get("architecture", detected["selection_defaults"]["architecture"]))
    dist_storage = str(existing_selected.get("dist_storage", detected["selection_defaults"].get("dist_storage", "none")))
    if not args.dry_run:
        ensure_gitattributes(repo, architecture, dist_storage)
    if (repo / "justfile").exists() and shutil.which("just"):
        return run_exec(["just", "bootstrap"], repo, dry_run=args.dry_run)
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
    render.add_argument("--ci-layout", choices=["auto", "single", "split"], default="auto")
    render.add_argument("--ci-paths", choices=["none", "components"], default="none")
    render.add_argument("--change-detection", choices=["auto", "none", "git-diff"], default="auto")
    render.add_argument("--dist-storage", choices=["auto", "none", "git", "git-lfs", "artifacts"], default="auto")
    render_release = render.add_mutually_exclusive_group()
    render_release.add_argument("--release-overlay", action="store_const", const=True, dest="release_overlay")
    render_release.add_argument("--no-release-overlay", action="store_const", const=False, dest="release_overlay")
    render.add_argument("--pretty", action="store_true")
    render.set_defaults(release_overlay=None)
    render.set_defaults(func=lambda ns: do_render_or_update(ns, write=False))

    update = sub.add_parser("update", help="Write managed files when safe and refresh candidate outputs.")
    update.add_argument("repo_root")
    update.add_argument("--architecture", choices=["auto", "general", "local-dist", "committed-dist", "cross-os-dist"], default="auto")
    update.add_argument("--ci-mode", choices=["auto", "just", "direct", "none"], default="auto")
    update.add_argument("--ci-layout", choices=["auto", "single", "split"], default="auto")
    update.add_argument("--ci-paths", choices=["none", "components"], default="none")
    update.add_argument("--change-detection", choices=["auto", "none", "git-diff"], default="auto")
    update.add_argument("--dist-storage", choices=["auto", "none", "git", "git-lfs", "artifacts"], default="auto")
    update_release = update.add_mutually_exclusive_group()
    update_release.add_argument("--release-overlay", action="store_const", const=True, dest="release_overlay")
    update_release.add_argument("--no-release-overlay", action="store_const", const=False, dest="release_overlay")
    update.add_argument("--pretty", action="store_true")
    update.set_defaults(release_overlay=None)
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
