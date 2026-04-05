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
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "packaging" / "skills.toml"


def load_config() -> dict[str, dict[str, object]]:
    with open(CONFIG_PATH, "rb") as fh:
        data = tomllib.load(fh)
    return data["skills"]


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


def repo_dist_payload_paths() -> list[Path]:
    dist_root = REPO_ROOT / "skills"
    if not dist_root.exists():
        return []
    paths: list[Path] = []
    for path in sorted(dist_root.glob("*/dist/**/*")):
        if path.is_file() or path.is_symlink():
            paths.append(path)
    return paths


def stale_dist_paths(expected_paths: list[Path]) -> list[Path]:
    expected = {path.resolve() for path in expected_paths}
    stale: list[Path] = []
    for path in repo_dist_payload_paths():
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
    packages = []
    for _, skill in selected:
        packages.extend(["-p", str(skill["package"])])
    run(["cargo", "build", "--workspace", "--release", "--locked", *packages], env=build_env())

    for _, skill in selected:
        skill_dir = REPO_ROOT / str(skill["skill_dir"])
        dist_dir = skill_dir / "dist" / platform_id
        dist_dir.mkdir(parents=True, exist_ok=True)
        target_name = binary_name(str(skill["binary"]), platform_id)
        src = REPO_ROOT / "target" / "release" / target_name
        dst = dist_dir / target_name
        shutil.copy2(src, dst)
        mode = os.stat(dst).st_mode
        os.chmod(dst, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


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
    for stale_path in stale_dist_paths(expected_paths):
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
    for stale_path in stale_dist_paths(expected_paths):
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
    else:  # pragma: no cover
        raise SystemExit(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
