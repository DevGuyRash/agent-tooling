#!/usr/bin/env python3
"""Compatibility commands backed by the shared artifact-task engine."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

from artifact_sync.engine import install_termination_handler, sync
from artifact_sync.model import ArtifactError, load_manifest, matches
from artifact_sync.snapshots import Snapshot
import rust_release

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = "packaging/artifacts.toml"


def host_platform_id():
    operating_system = {"linux": "linux", "darwin": "macos", "win32": "windows"}.get(sys.platform)
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(platform.machine().lower())
    if not operating_system or not arch:
        raise ArtifactError("host platform is unavailable", "select a declared platform set")
    return f"{operating_system}-{arch}"


def selected_rust(manifest, names=(), platform_set="required"):
    rust = {name: task for name, task in manifest.tasks.items() if "rust" in task.parameters}
    for name in names:
        if name not in rust:
            raise ArtifactError(f"unknown packaged Rust task: {name}", "valid tasks: " + ", ".join(rust))
    selected = [rust[name] for name in names] if names else list(rust.values())
    if platform_set == "host":
        selected = [task for task in selected if task.parameters["rust"].get("platform") == host_platform_id()]
    if not selected:
        raise ArtifactError("no packaged Rust tasks match the selection", "select a task declared in packaging/artifacts.toml")
    return selected


def watch_paths(manifest, names=(), include_tests=False):
    tasks = manifest.order(list(names) if names else None, automatic=not names)
    paths = {CONFIG, "scripts/package_skills.py", "scripts/artifacts.py", "scripts/artifact_sync/**"}
    if include_tests:
        paths.add("scripts/tests/**")
    for task in tasks:
        paths.update((*task.inputs, *task.optional_inputs, manifest.receipt_path(task.name)))
        for output in task.outputs:
            paths.update(output.destinations)
        rust = task.parameters.get("rust", {})
        if rust.get("launcher"):
            paths.add(rust_skill_root(task) + "/" + rust["launcher"])
    return sorted(paths)


def rust_skill_root(task):
    rust = task.parameters["rust"]
    return rust.get("skill_dir") or task.outputs[0].destinations[0].split("/dist/", 1)[0]


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bootstrap")
    refresh = sub.add_parser("dist-refresh")
    refresh.add_argument("--source", choices=["index"], default="index")
    refresh.add_argument("--stage", action="store_true")
    receipt = sub.add_parser("verify-dist-receipt")
    receipt.add_argument("--source", default="index")
    matrix = sub.add_parser("verify-target-matrix")
    stage = sub.add_parser("stage-host")
    sub.add_parser("verify-host")
    complete = sub.add_parser("verify-complete")
    compare = sub.add_parser("compare-artifacts")
    imported = sub.add_parser("sync-artifacts")
    for command in (compare, imported):
        command.add_argument("--artifacts-root", required=True, type=Path)
    for command in (refresh, receipt, matrix, complete, compare, imported):
        command.add_argument("--platform-set", choices=["host", "required", "ci", "all"], default="ci" if command in (compare, imported) else "required")
    for command in (refresh, receipt, stage):
        command.add_argument("--skill", action="append", default=[])
    sub.add_parser("smoke-launchers")
    sub.add_parser("launcher-smoke")
    vendor = sub.add_parser("vendor")
    vendor.add_argument("--sync", action="store_true")
    watch = sub.add_parser("watch-paths")
    match = sub.add_parser("matches-changed-files")
    match.add_argument("--changed-files-file", required=True, type=Path)
    for command in (watch, match):
        command.add_argument("--skill", action="append", default=[])
        command.add_argument("--include-tests", action="store_true")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.cmd == "bootstrap":
            subprocess.run(["cargo", "fetch", "--locked"], cwd=REPO_ROOT, check=True)
            return 0
        snapshot = Snapshot(REPO_ROOT, getattr(args, "source", "worktree"))
        item = snapshot.get(CONFIG)
        if item is None:
            raise ArtifactError("artifact manifest is absent from selected source")
        manifest = load_manifest(item.data, CONFIG)
        if args.cmd in {"watch-paths", "matches-changed-files"}:
            paths = watch_paths(manifest, args.skill, args.include_tests)
            if args.cmd == "watch-paths":
                print("\n".join(paths))
            else:
                changed = args.changed_files_file.read_text().splitlines()
                print("true" if any(matches(name, pattern) for name in changed for pattern in paths) else "false")
            return 0
        if args.cmd == "vendor":
            selected = [name for name, task in manifest.tasks.items() if task.automatic and not task.command]
            result = sync(REPO_ROOT, selected=selected, check=not args.sync) if selected else {"tasks": []}
        else:
            tasks = selected_rust(manifest, getattr(args, "skill", ()), getattr(args, "platform_set", "host"))
            selected = [task.name for task in tasks]
            if args.cmd == "verify-target-matrix":
                for task in tasks:
                    rust = task.parameters["rust"]
                    rust_release.build_command(rust, rust["platform"])
                    rust_release.target_recipe_version(rust, rust["platform"])
                result = {"tasks": selected}
            elif args.cmd in {"smoke-launchers", "launcher-smoke"}:
                for task in tasks:
                    rust = task.parameters["rust"]
                    skill_root = rust_skill_root(task)
                    subprocess.run([str(REPO_ROOT / skill_root / rust["launcher"]), *rust.get("smoke_args", [])], cwd=REPO_ROOT, check=True)
                result = {"tasks": selected, "status": "launchers exercised"}
            else:
                result = sync(REPO_ROOT, selected=selected, source=getattr(args, "source", "worktree"),
                              stage=getattr(args, "stage", False),
                              check=args.cmd in {"verify-host", "verify-complete", "verify-dist-receipt", "compare-artifacts"},
                              prepared=getattr(args, "artifacts_root", None))
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except ArtifactError as error:
        print(f"error: {error}\nhint: {error.hint}", file=sys.stderr)
        return error.code
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"error: packaging command failed: {error}\nhint: inspect the selected task and retry", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("error: interrupted\nhint: rerun the operation; publication recovery preserves owned files and the selected index", file=sys.stderr)
        return 130


if __name__ == "__main__":
    install_termination_handler()
    raise SystemExit(main())
