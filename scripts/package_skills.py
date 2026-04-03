#!/usr/bin/env python3
from __future__ import annotations

import argparse
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

    if sys_name.startswith("linux"):
        os_id = "linux"
    elif sys_name == "darwin":
        os_id = "macos"
    elif sys_name in {"win32", "cygwin"}:
        os_id = "windows"
    else:  # pragma: no cover - explicit failure path
        raise SystemExit(f"unsupported host platform: {sys_name}")

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

    return f"{os_id}-{arch}"


def binary_name(binary: str, platform_id: str) -> str:
    return f"{binary}.exe" if platform_id.startswith("windows-") else binary


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def tracked_dist_paths(config: dict[str, dict[str, object]], platform_id: str) -> list[Path]:
    paths: list[Path] = []
    for skill in config.values():
        skill_dir = REPO_ROOT / str(skill["skill_dir"])
        paths.append(skill_dir / "dist" / platform_id / binary_name(str(skill["binary"]), platform_id))
    return paths


def bootstrap() -> None:
    run(["cargo", "fetch", "--locked"])


def stage_host() -> None:
    config = load_config()
    platform_id = host_platform_id()
    packages = []
    for skill in config.values():
        packages.extend(["-p", str(skill["package"])])
    run(["cargo", "build", "--workspace", "--release", "--locked", *packages])

    for skill in config.values():
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
    relevant = [str(path.relative_to(REPO_ROOT)) for path in tracked_dist_paths(config, platform_id)]
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
    sub.add_parser("stage-host")
    sub.add_parser("verify-host")
    sub.add_parser("smoke-launchers")
    args = parser.parse_args()

    if args.cmd == "bootstrap":
        bootstrap()
    elif args.cmd == "stage-host":
        stage_host()
    elif args.cmd == "verify-host":
        verify_host()
    elif args.cmd == "smoke-launchers":
        smoke_launchers()
    else:  # pragma: no cover
        raise SystemExit(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
