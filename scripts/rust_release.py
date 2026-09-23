"""Pinned Rust release operations used by ordinary artifact tasks."""
from __future__ import annotations

import filecmp
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN_PATH = REPO_ROOT / "rust-toolchain.toml"

def target_config(skill: dict[str, object], platform_id: str) -> dict[str, object]:
    raw_targets = skill.get("targets")
    if raw_targets is None:
        return {}
    if not isinstance(raw_targets, dict):
        raise SystemExit("targets must be a table of per-platform settings")
    target = raw_targets.get(platform_id)
    if target is None:
        return {}
    if not isinstance(target, dict):
        raise SystemExit(f"target config for {platform_id} must be a table")
    return target


def binary_name(skill: dict[str, object], platform_id: str) -> str:
    target = target_config(skill, platform_id)
    artifact = target.get("artifact")
    if artifact is None:
        return str(skill["binary"])
    if not isinstance(artifact, str) or not artifact.strip():
        raise SystemExit(f"artifact for {platform_id} must be a non-empty string")
    return artifact


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


def build_env_for_root(repo_root: Path, cargo_target: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["RUSTFLAGS"] = release_rustflags_for_target(repo_root, cargo_target)
    env.pop("CARGO_ENCODED_RUSTFLAGS", None)
    env["PATH"] = strip_dev_cache_intercepts(env.get("PATH", ""))
    env["CARGO_INCREMENTAL"] = "0"
    env["SOURCE_DATE_EPOCH"] = "1"
    env["TZ"] = "UTC"
    env["LC_ALL"] = "C"
    return env


def release_rustflags_for_target(repo_root: Path, cargo_target: str | None) -> str:
    return release_rustflags(
        repo_root=str(repo_root),
        cargo_home=str(remap_prefixes()[1][0]),
        rustup_home=str(remap_prefixes()[2][0]),
        cargo_target=cargo_target,
    )


def release_rustflags(
    *,
    repo_root: str,
    cargo_home: str,
    rustup_home: str,
    cargo_target: str | None,
) -> str:
    remap_flags = [
        f"--remap-path-prefix={source}={dest}"
        for source, dest in [
            (repo_root, "/workspace"),
            (cargo_home, "/cargo-home"),
            (rustup_home, "/rustup-home"),
        ]
    ]
    flags = [
        *remap_flags,
        "-Cstrip=symbols",
        "-Cdebuginfo=0",
        "-Ccodegen-units=1",
    ]
    if cargo_target and cargo_target.endswith("-windows-msvc"):
        flags.extend(
            [
                "-Clink-arg=/Brepro",
                "-Clink-arg=/DEBUG:NONE",
                "-Clink-arg=/timestamp:1",
            ]
        )
    return " ".join(flags)


def strip_dev_cache_intercepts(path_value: str) -> str:
    entries = [entry for entry in path_value.split(os.pathsep) if entry]
    filtered = [entry for entry in entries if "/dev-cache/intercepts" not in entry]
    return os.pathsep.join(filtered)


def run(cmd: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd or REPO_ROOT, check=True, env=env)


def cargo_target_triple(skill: dict[str, object], platform_id: str) -> str | None:
    raw = target_config(skill, platform_id).get("cargo_target")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise SystemExit(f"cargo_target for {platform_id} must be a non-empty string")
    return raw


def target_recipe(skill: dict[str, object], platform_id: str) -> str:
    raw = target_config(skill, platform_id).get("recipe", "cargo-release")
    if not isinstance(raw, str) or not raw.strip():
        raise SystemExit(f"recipe for {platform_id} must be a non-empty string")
    return raw


def target_recipe_version(skill: dict[str, object], platform_id: str) -> str:
    raw = target_config(skill, platform_id).get("recipe_version")
    if not isinstance(raw, str) or not raw.strip():
        raise SystemExit(f"recipe_version for {platform_id} must be a non-empty string")
    return raw


def cargo_release_dir(frozen_root: Path, cargo_target: str | None) -> Path:
    if cargo_target:
        return frozen_root / "target" / cargo_target / "release"
    return frozen_root / "target" / "release"


def build_command(skill: dict[str, object], platform_id: str) -> list[str]:
    recipe = target_recipe(skill, platform_id)
    cargo_target = cargo_target_triple(skill, platform_id)
    if cargo_target is None:
        raise SystemExit(f"cargo_target is required for reproducible release target {platform_id}")
    common = [
        "--release",
        "--frozen",
        "-p",
        str(skill["package"]),
        "--target",
        cargo_target,
    ]
    if recipe == "cargo-zigbuild":
        return ["cargo", "zigbuild", *common]
    if recipe == "cargo-xwin":
        return ["cargo", "xwin", "build", *common]
    raise SystemExit(f"unsupported build recipe for {platform_id}: {recipe}")


def command_version(command: list[str], label: str) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"{label} is unavailable; install the pinned release tool") from error
    return (result.stdout or result.stderr).strip()


def verify_release_tool(skill: dict[str, object], platform_id: str) -> None:
    target = target_config(skill, platform_id)
    recipe = target_recipe(skill, platform_id)
    version = target_recipe_version(skill, platform_id)
    if recipe == "cargo-zigbuild":
        actual = command_version(["cargo-zigbuild", "--version"], "cargo-zigbuild")
        if version not in actual:
            raise SystemExit(f"cargo-zigbuild version mismatch; expected {version}, got {actual}")
        zig_version = target.get("zig_version")
        if not isinstance(zig_version, str) or not zig_version:
            raise SystemExit(f"zig_version is required for {platform_id}")
        actual_zig = command_version(["zig", "version"], "Zig")
        if actual_zig != zig_version:
            raise SystemExit(f"Zig version mismatch; expected {zig_version}, got {actual_zig}")
    elif recipe == "cargo-xwin":
        actual = command_version(["cargo-xwin", "--version"], "cargo-xwin")
        if version not in actual:
            raise SystemExit(f"cargo-xwin version mismatch; expected {version}, got {actual}")
        llvm_version = target.get("llvm_version")
        if not isinstance(llvm_version, str) or not llvm_version:
            raise SystemExit(f"llvm_version is required for {platform_id}")
        actual_llvm = command_version(["clang", "--version"], "LLVM/Clang")
        if llvm_version not in actual_llvm.splitlines()[0]:
            raise SystemExit(
                f"LLVM/Clang version mismatch; expected {llvm_version}, got {actual_llvm.splitlines()[0]}"
            )
        if shutil.which("lld-link") is None:
            raise SystemExit("lld-link is unavailable; install the pinned LLVM toolchain")
    else:
        raise SystemExit(f"unsupported build recipe for {platform_id}: {recipe}")


def stage_from_frozen_index(
    selected_targets: list[tuple[str, dict[str, object], str]],
    frozen_root: Path,
    artifacts_root: Path,
) -> None:
    for _, skill, platform_id in selected_targets:
        verify_release_tool(skill, platform_id)
        cargo_target = cargo_target_triple(skill, platform_id)
        run(
            build_command(skill, platform_id),
            cwd=frozen_root,
            env=build_env_for_root(frozen_root, cargo_target),
        )
        source = cargo_release_dir(frozen_root, cargo_target) / binary_name(skill, platform_id)
        if not source.is_file():
            raise SystemExit(f"build did not produce {source}")
        destination = artifacts_root / str(skill["skill_dir"]) / "dist" / platform_id / binary_name(skill, platform_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        mode = os.stat(destination).st_mode
        os.chmod(destination, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def compare_built_artifacts(
    first: Path,
    second: Path,
    selected_targets: list[tuple[str, dict[str, object], str]],
) -> None:
    for _, skill, platform_id in selected_targets:
        relative = Path(str(skill["skill_dir"])) / "dist" / platform_id / binary_name(skill, platform_id)
        first_path = first / relative
        second_path = second / relative
        if not first_path.is_file() or not second_path.is_file():
            raise SystemExit(f"reproducibility build is missing {relative}")
        if not filecmp.cmp(first_path, second_path, shallow=False):
            raise SystemExit(f"non-reproducible release artifact: {relative}")
