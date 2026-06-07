#!/usr/bin/env python3
from __future__ import annotations

import argparse
import filecmp
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "packaging" / "skills.toml"
TOOLCHAIN_PATH = REPO_ROOT / "rust-toolchain.toml"
ROOT_WATCH_PATHS = [
    Path("packaging/skills.toml"),
    Path("scripts/package_skills.py"),
    Path("Cargo.toml"),
    Path("Cargo.lock"),
    Path("rust-toolchain.toml"),
]


def load_config() -> dict[str, dict[str, object]]:
    with open(CONFIG_PATH, "rb") as fh:
        data = tomllib.load(fh)
    return data["skills"]


def load_toml(path: Path) -> dict[str, object]:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def host_platform_id() -> str:
    sys_name = sys.platform
    machine = platform.machine().lower()

    if not sys_name.startswith("linux"):  # pragma: no cover - explicit failure path
        raise SystemExit(f"unsupported host platform: {sys_name}; only Linux packaging is supported")

    aliases = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }
    try:
        arch = aliases[machine]
    except KeyError as exc:  # pragma: no cover - explicit failure path
        raise SystemExit(f"unsupported host architecture: {machine}") from exc

    return f"linux-{arch}"


def binary_name(binary: str, platform_id: str) -> str:
    return binary


def toolchain_channel() -> str:
    with open(TOOLCHAIN_PATH, "rb") as fh:
        data = tomllib.load(fh)
    toolchain = data.get("toolchain")
    if not isinstance(toolchain, dict) or not isinstance(toolchain.get("channel"), str):
        raise SystemExit("rust-toolchain.toml must define [toolchain].channel")
    return toolchain["channel"]


def remap_prefixes() -> list[tuple[Path, str]]:
    prefixes: list[tuple[Path, str]] = [(REPO_ROOT, "/workspace")]

    cargo_home = Path(os.environ.get("CARGO_HOME", str(Path.home() / ".cargo"))).resolve()
    rustup_home = Path(os.environ.get("RUSTUP_HOME", str(Path.home() / ".rustup"))).resolve()

    prefixes.append((cargo_home, "/cargo-home"))
    prefixes.append((rustup_home, "/rustup-home"))
    return prefixes


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    remap_flags = [
        f"--remap-path-prefix={source}={dest}"
        for source, dest in remap_prefixes()
    ]
    rustflags = env.get("RUSTFLAGS", "").strip()
    env["RUSTFLAGS"] = " ".join([*remap_flags, rustflags]).strip()
    return env


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=REPO_ROOT, check=True, env=env)


def docker_available() -> bool:
    return shutil.which("docker") is not None


def env_value(name: str, *, deprecated: str | None = None, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    if deprecated:
        legacy = os.environ.get(deprecated)
        if legacy:
            return legacy
    return default


def dist_build_mode() -> str:
    mode = env_value(
        "AGENT_TOOLING_DIST_BUILD_MODE",
        deprecated="AGENT_SKILLS_DIST_BUILD_MODE",
        default="auto",
    ).strip().lower()
    if mode not in {"auto", "container", "host"}:
        raise SystemExit(
            "AGENT_TOOLING_DIST_BUILD_MODE must be one of: auto, container, host"
        )
    return mode


def use_container_build(platform_id: str) -> bool:
    if platform_id != "linux-x86_64":
        return False

    mode = dist_build_mode()
    if mode == "host":
        return False
    if mode == "container":
        if not docker_available():
            raise SystemExit("docker is required for AGENT_TOOLING_DIST_BUILD_MODE=container")
        return True
    return docker_available()


def container_image() -> str:
    return env_value(
        "AGENT_TOOLING_RUST_IMAGE",
        deprecated="AGENT_SKILLS_RUST_IMAGE",
        default=f"rust:{toolchain_channel()}",
    )


def container_rustflags() -> str:
    remap_flags = [
        "--remap-path-prefix=/work=/workspace",
        "--remap-path-prefix=/usr/local/cargo=/cargo-home",
        "--remap-path-prefix=/usr/local/rustup=/rustup-home",
    ]
    rustflags = os.environ.get("RUSTFLAGS", "").strip()
    return " ".join([*remap_flags, rustflags]).strip()


def install_dist_binary(skill: dict[str, object], platform_id: str, src: Path) -> None:
    skill_dir = REPO_ROOT / str(skill["skill_dir"])
    dist_dir = skill_dir / "dist" / platform_id
    dist_dir.mkdir(parents=True, exist_ok=True)
    target_name = binary_name(str(skill["binary"]), platform_id)
    dst = dist_dir / target_name
    shutil.copy2(src, dst)
    mode = os.stat(dst).st_mode
    os.chmod(dst, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def stage_host_native(selected: list[tuple[str, dict[str, object]]], platform_id: str) -> None:
    packages = []
    for _, skill in selected:
        packages.extend(["-p", str(skill["package"])])
    run(["cargo", "build", "--workspace", "--release", "--locked", *packages], env=build_env())

    for _, skill in selected:
        target_name = binary_name(str(skill["binary"]), platform_id)
        src = REPO_ROOT / "target" / "release" / target_name
        install_dist_binary(skill, platform_id, src)


def stage_host_container(selected: list[tuple[str, dict[str, object]]], platform_id: str) -> None:
    packages = []
    for _, skill in selected:
        packages.extend(["-p", str(skill["package"])])

    create = subprocess.run(
        [
            "docker",
            "create",
            "-v",
            f"{REPO_ROOT}:/work:ro",
            "-w",
            "/work",
            "-e",
            "CARGO_TARGET_DIR=/tmp/target",
            "-e",
            f"RUSTFLAGS={container_rustflags()}",
            container_image(),
            "cargo",
            "build",
            "--workspace",
            "--release",
            "--locked",
            *packages,
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    container_id = create.stdout.strip()
    if not container_id:
        raise SystemExit("docker create did not return a container id")

    extract_dir = Path(tempfile.mkdtemp(prefix="package-skills-container-"))
    try:
        subprocess.run(["docker", "start", "-a", container_id], cwd=REPO_ROOT, check=True)
        for _, skill in selected:
            target_name = binary_name(str(skill["binary"]), platform_id)
            extracted = extract_dir / target_name
            subprocess.run(
                ["docker", "cp", f"{container_id}:/tmp/target/release/{target_name}", str(extracted)],
                cwd=REPO_ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            install_dist_binary(skill, platform_id, extracted)
    finally:
        subprocess.run(
            ["docker", "rm", "-f", container_id],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        shutil.rmtree(extract_dir, ignore_errors=True)


def selected_skill_entries(
    config: dict[str, dict[str, object]],
    skill_names: list[str] | None = None,
) -> list[tuple[str, dict[str, object]]]:
    if not skill_names:
        return list(config.items())

    selected: list[tuple[str, dict[str, object]]] = []
    seen: set[str] = set()
    unknown: list[str] = []
    for skill_name in skill_names:
        if skill_name in seen:
            continue
        seen.add(skill_name)
        skill = config.get(skill_name)
        if skill is None:
            unknown.append(skill_name)
            continue
        selected.append((skill_name, skill))
    if unknown:
        choices = ", ".join(sorted(config))
        missing = ", ".join(sorted(unknown))
        raise SystemExit(f"unknown packaged skill(s): {missing}; expected one of: {choices}")
    return selected


def dependency_tables(manifest: dict[str, object]) -> list[dict[str, object]]:
    tables: list[dict[str, object]] = []
    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
        raw = manifest.get(key)
        if isinstance(raw, dict):
            tables.append(raw)

    for table_name, table_value in manifest.items():
        if not isinstance(table_name, str) or not table_name.startswith("target."):
            continue
        if not isinstance(table_value, dict):
            continue
        for key in ("dependencies", "dev-dependencies", "build-dependencies"):
            raw = table_value.get(key)
            if isinstance(raw, dict):
                tables.append(raw)
    return tables


def discover_workspace_manifests() -> list[Path]:
    manifests: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("Cargo.toml")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if "target" in rel_parts or ".git" in rel_parts:
            continue
        if any(part.startswith(".local") for part in rel_parts):
            continue
        manifests.append(path)
    return manifests


def manifest_dependency_dirs(manifest_path: Path, manifest: dict[str, object]) -> list[Path]:
    deps: list[Path] = []
    for table in dependency_tables(manifest):
        for spec in table.values():
            if not isinstance(spec, dict):
                continue
            raw_path = spec.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            dep_path = (manifest_path.parent / raw_path).resolve()
            dep_manifest = dep_path / "Cargo.toml" if dep_path.is_dir() else dep_path
            if dep_manifest.name != "Cargo.toml":
                dep_manifest = dep_manifest / "Cargo.toml"
            if dep_manifest.is_file():
                deps.append(dep_manifest.parent.resolve())
    return deps


def cargo_package_graph() -> tuple[dict[str, Path], dict[Path, list[Path]]]:
    package_dirs: dict[str, Path] = {}
    dependency_dirs: dict[Path, list[Path]] = {}

    for manifest_path in discover_workspace_manifests():
        manifest = load_toml(manifest_path)
        crate_dir = manifest_path.parent.resolve()
        dependency_dirs[crate_dir] = manifest_dependency_dirs(manifest_path, manifest)
        package = manifest.get("package")
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        if isinstance(name, str) and name.strip():
            package_dirs[name] = crate_dir

    return package_dirs, dependency_dirs


def path_within_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
        return True
    except ValueError:
        return False


def package_source_dirs(
    config: dict[str, dict[str, object]],
    skill_names: list[str] | None = None,
) -> list[Path]:
    selected = selected_skill_entries(config, skill_names)
    package_dirs, dependency_dirs = cargo_package_graph()

    queue: list[Path] = []
    missing_packages: list[str] = []
    for _, skill in selected:
        package_name = str(skill["package"])
        crate_dir = package_dirs.get(package_name)
        if crate_dir is None:
            missing_packages.append(package_name)
            continue
        queue.append(crate_dir)

    if missing_packages:
        missing = ", ".join(sorted(missing_packages))
        raise SystemExit(f"packaged skill crate(s) not found in workspace: {missing}")

    ordered: list[Path] = []
    seen: set[Path] = set()
    while queue:
        crate_dir = queue.pop(0)
        if crate_dir in seen or not path_within_repo(crate_dir):
            continue
        seen.add(crate_dir)
        ordered.append(crate_dir)
        for dep_dir in dependency_dirs.get(crate_dir, []):
            if dep_dir not in seen:
                queue.append(dep_dir)

    return ordered


def normalize_repo_path(path: str) -> str:
    trimmed = path.strip().replace("\\", "/")
    while trimmed.startswith("./"):
        trimmed = trimmed[2:]
    return trimmed.strip("/")


def watched_repo_paths(
    config: dict[str, dict[str, object]],
    skill_names: list[str] | None = None,
    *,
    include_tests: bool = False,
) -> list[str]:
    selected = selected_skill_entries(config, skill_names)
    watched: list[str] = [path.as_posix() for path in ROOT_WATCH_PATHS]

    for crate_dir in package_source_dirs(config, skill_names):
        watched.append(crate_dir.relative_to(REPO_ROOT).as_posix())

    for _, skill in selected:
        skill_dir = REPO_ROOT / str(skill["skill_dir"])
        launcher = skill_dir / str(skill["launcher"])
        watched.append(launcher.relative_to(REPO_ROOT).as_posix())
        watched.append((skill_dir / "dist").relative_to(REPO_ROOT).as_posix())
        if include_tests:
            watched.append((skill_dir / "tests").relative_to(REPO_ROOT).as_posix())

    deduped: list[str] = []
    seen: set[str] = set()
    for path in watched:
        normalized = normalize_repo_path(path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def path_matches_watch_list(changed_path: str, watched_paths: list[str]) -> bool:
    normalized = normalize_repo_path(changed_path)
    if not normalized:
        return False
    for watched in watched_paths:
        if normalized == watched or normalized.startswith(f"{watched}/"):
            return True
    return False


def matches_changed_files(
    changed_files: list[str],
    config: dict[str, dict[str, object]],
    skill_names: list[str] | None = None,
    *,
    include_tests: bool = False,
) -> bool:
    watched = watched_repo_paths(config, skill_names, include_tests=include_tests)
    for changed in changed_files:
        if path_matches_watch_list(changed, watched):
            return True
    return False


def load_changed_files(path: Path) -> list[str]:
    return [
        normalize_repo_path(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if normalize_repo_path(line)
    ]


def skill_platforms(skill: dict[str, object], key: str) -> list[str]:
    raw = skill.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise SystemExit(f"{key} must be a list of platform ids")
    return list(raw)


def selected_platforms(config: dict[str, dict[str, object]], platform_set: str) -> list[str]:
    if platform_set == "host":
        return [host_platform_id()]

    ordered: list[str] = []
    seen: set[str] = set()
    manifest_keys = {
        "required": ("required_platforms",),
        "ci": ("ci_platforms", "required_platforms"),
        "all": ("ci_platforms", "required_platforms"),
    }
    keys = manifest_keys[platform_set]
    for skill in config.values():
        for key in keys:
            for platform_id in skill_platforms(skill, key):
                if platform_id in seen:
                    continue
                seen.add(platform_id)
                ordered.append(platform_id)
    if ordered:
        return ordered
    return [host_platform_id()]


def dist_path_for_skill(skill: dict[str, object], platform_id: str) -> Path:
    skill_dir = REPO_ROOT / str(skill["skill_dir"])
    return skill_dir / "dist" / platform_id / binary_name(str(skill["binary"]), platform_id)


def tracked_dist_paths(config: dict[str, dict[str, object]], platform_ids: list[str]) -> list[Path]:
    paths: list[Path] = []
    for skill in config.values():
        for platform_id in platform_ids:
            paths.append(dist_path_for_skill(skill, platform_id))
    return paths


def repo_dist_payload_roots(config: dict[str, dict[str, object]] | None = None) -> list[Path]:
    roots: set[Path] = set()
    if config is None:
        config = load_config()
    for skill in config.values():
        roots.add(REPO_ROOT / str(skill["skill_dir"]) / "dist")
    for path in REPO_ROOT.glob("plugins/*/skills/*/dist"):
        roots.add(path)
    for path in REPO_ROOT.glob("skills/*/dist"):
        roots.add(path)
    return sorted(roots)


def repo_dist_payload_paths(config: dict[str, dict[str, object]] | None = None) -> list[Path]:
    paths: list[Path] = []
    for dist_root in repo_dist_payload_roots(config):
        if not dist_root.exists():
            continue
        for path in sorted(dist_root.glob("**/*")):
            if path.is_file() or path.is_symlink():
                paths.append(path)
    return paths


def stale_dist_paths(
    expected_paths: list[Path],
    config: dict[str, dict[str, object]] | None = None,
) -> list[Path]:
    expected = {path.resolve() for path in expected_paths}
    stale: list[Path] = []
    for path in repo_dist_payload_paths(config):
        if path.resolve() in expected:
            continue
        stale.append(path)
    return stale


def bootstrap() -> None:
    run(["cargo", "fetch", "--locked"])


def stage_host(skill_names: list[str] | None = None) -> None:
    config = load_config()
    selected = selected_skill_entries(config, skill_names)
    platform_id = host_platform_id()
    if use_container_build(platform_id):
        stage_host_container(selected, platform_id)
    else:
        stage_host_native(selected, platform_id)


def verify_host() -> None:
    config = load_config()
    platform_id = host_platform_id()
    stage_host()
    relevant = [str(path.relative_to(REPO_ROOT)) for path in tracked_dist_paths(config, [platform_id])]
    result = subprocess.run(
        ["git", "status", "--short", "--", *relevant],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        print(result.stdout, end="")
        raise SystemExit("packaged binaries changed; refresh and commit the staged dist outputs")


def ensure_tracked(paths: list[Path]) -> None:
    missing = []
    untracked = []
    for path in paths:
        if not path.exists() or path.is_symlink():
            missing.append(path)
            continue
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            untracked.append(path)
    if missing:
        for path in missing:
            print(f"missing dist payload: {path.relative_to(REPO_ROOT)}")
        raise SystemExit("required packaged dist outputs are missing")
    if untracked:
        for path in untracked:
            print(f"untracked dist payload: {path.relative_to(REPO_ROOT)}")
        raise SystemExit("required packaged dist outputs must be committed to git")


def verify_complete(platform_set: str) -> None:
    config = load_config()
    ensure_tracked(tracked_dist_paths(config, selected_platforms(config, platform_set)))


def artifact_source_path(artifacts_root: Path, rel_path: Path) -> Path | None:
    direct = artifacts_root / rel_path
    if direct.is_file():
        return direct
    if not artifacts_root.exists():
        return None
    for child in sorted(artifacts_root.iterdir()):
        candidate = child / rel_path
        if candidate.is_file():
            return candidate
    return None


def compare_artifacts(artifacts_root: Path, platform_set: str) -> None:
    config = load_config()
    expected_paths = tracked_dist_paths(config, selected_platforms(config, platform_set))
    mismatches = False
    for target in expected_paths:
        rel_path = target.relative_to(REPO_ROOT)
        source = artifact_source_path(artifacts_root, rel_path)
        if source is None:
            print(f"missing artifact payload: {rel_path}")
            mismatches = True
            continue
        if not target.exists():
            print(f"repository is missing payload: {rel_path}")
            mismatches = True
            continue
        if not filecmp.cmp(source, target, shallow=False):
            print(f"artifact payload differs: {rel_path}")
            mismatches = True
    for stale_path in stale_dist_paths(expected_paths, config):
        print(f"stale dist payload: {stale_path.relative_to(REPO_ROOT)}")
        mismatches = True
    if mismatches:
        raise SystemExit("artifact payloads do not match the committed dist tree")


def sync_artifacts(artifacts_root: Path, platform_set: str) -> None:
    config = load_config()
    changed: list[Path] = []
    expected_paths = tracked_dist_paths(config, selected_platforms(config, platform_set))
    for target in expected_paths:
        rel_path = target.relative_to(REPO_ROOT)
        source = artifact_source_path(artifacts_root, rel_path)
        if source is None:
            raise SystemExit(f"missing artifact payload: {rel_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or not filecmp.cmp(source, target, shallow=False):
            shutil.copy2(source, target)
            mode = os.stat(target).st_mode
            os.chmod(target, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            changed.append(rel_path)
    for stale_path in stale_dist_paths(expected_paths, config):
        stale_path.unlink()
        changed.append(stale_path.relative_to(REPO_ROOT))
    for rel_path in changed:
        print(rel_path)


def smoke_launchers() -> None:
    config = load_config()
    for skill in config.values():
        launcher = REPO_ROOT / str(skill["skill_dir"]) / str(skill["launcher"])
        smoke_args = [str(arg) for arg in skill.get("smoke_args", [])]
        run([str(launcher), *smoke_args])


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bootstrap")
    stage = sub.add_parser("stage-host")
    stage.add_argument("--skill", action="append", default=[])
    sub.add_parser("verify-host")
    complete = sub.add_parser("verify-complete")
    complete.add_argument("--platform-set", choices=["host", "required", "ci", "all"], default="required")
    compare = sub.add_parser("compare-artifacts")
    compare.add_argument("--artifacts-root", required=True)
    compare.add_argument("--platform-set", choices=["host", "required", "ci", "all"], default="ci")
    sync = sub.add_parser("sync-artifacts")
    sync.add_argument("--artifacts-root", required=True)
    sync.add_argument("--platform-set", choices=["host", "required", "ci", "all"], default="ci")
    sub.add_parser("smoke-launchers")
    watch = sub.add_parser("watch-paths")
    watch.add_argument("--skill", action="append", default=[])
    watch.add_argument("--include-tests", action="store_true")
    match = sub.add_parser("matches-changed-files")
    match.add_argument("--skill", action="append", default=[])
    match.add_argument("--include-tests", action="store_true")
    match.add_argument("--changed-files-file", required=True)
    args = parser.parse_args()

    if args.cmd == "bootstrap":
        bootstrap()
    elif args.cmd == "stage-host":
        stage_host(args.skill)
    elif args.cmd == "verify-host":
        verify_host()
    elif args.cmd == "verify-complete":
        verify_complete(args.platform_set)
    elif args.cmd == "compare-artifacts":
        compare_artifacts(Path(args.artifacts_root), args.platform_set)
    elif args.cmd == "sync-artifacts":
        sync_artifacts(Path(args.artifacts_root), args.platform_set)
    elif args.cmd == "smoke-launchers":
        smoke_launchers()
    elif args.cmd == "watch-paths":
        for path in watched_repo_paths(load_config(), args.skill, include_tests=args.include_tests):
            print(path)
    elif args.cmd == "matches-changed-files":
        changed_files = load_changed_files(Path(args.changed_files_file))
        changed = matches_changed_files(
            changed_files,
            load_config(),
            args.skill,
            include_tests=args.include_tests,
        )
        print("true" if changed else "false")
    else:  # pragma: no cover
        raise SystemExit(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
