"""Contributor setup using the same task declarations and artifact verification."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

from .engine import missing_tools, sync
from .model import ArtifactError, load_manifest
from .snapshots import Snapshot, git


def config_values(root, key, scope=None, *, path=False):
    command = ["git", "-C", str(root), "config"]
    if scope:
        command.append(scope)
    if path:
        command.append("--path")
    result = subprocess.run([*command, "--null", "--get-all", key], capture_output=True, timeout=10)
    if result.returncode not in (0, 1):
        raise ArtifactError(f"could not read Git setting {key}", "check the repository configuration")
    return [os.fsdecode(value) for value in result.stdout.split(b"\0")[:-1]] if result.returncode == 0 else []


def install_hooks(root: Path, *, replace=False):
    expected = root / "githooks"
    if expected.is_symlink():
        raise ArtifactError("repository hooks directory is a symlink", "restore the maintained githooks directory")
    hooks = [expected / name for name in ("pre-commit", "pre-push")]
    for hook in hooks:
        if hook.is_symlink() or not hook.is_file() or not hook.read_bytes().startswith(b"#!/usr/bin/env sh\n"):
            raise ArtifactError(f"missing or invalid maintained hook: {hook.name}", "restore the tracked githooks files and rerun bootstrap")
    python = shutil.which("python3")
    if not python:
        raise ArtifactError("repository hooks require python3 on PATH", "provide Python 3.11+ and rerun bootstrap")
    try:
        checked = subprocess.run([python, "-c", "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"],
                                 capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ArtifactError("could not check the hook's python3 runtime", "provide Python 3.11+ on PATH") from exc
    if checked.returncode:
        raise ArtifactError("repository hooks require Python 3.11+ on PATH", "update python3 before enabling the hooks")
    configured = config_values(root, "core.hooksPath", path=True)
    active = (root / configured[-1]).resolve() if configured else Path(git(root, "rev-parse", "--path-format=absolute", "--git-path", "hooks").decode().strip())
    if configured and active != expected and not replace:
        raise ArtifactError("a custom core.hooksPath is already configured",
                            "retain that hook setup or explicitly select the repository hooks with --replace-hooks")
    if not configured and active.is_dir() and not replace:
        existing = [p.name for p in active.iterdir() if not p.name.endswith(".sample") and p.is_file() and os.access(p, os.X_OK)]
        if existing:
            raise ArtifactError("existing native Git hooks would be bypassed: " + ", ".join(sorted(existing)),
                                "retain those hooks or explicitly select the repository hooks with --replace-hooks")
    scope = "--worktree" if git_bool(root, "extensions.worktreeConfig") else "--local"
    previous = config_values(root, "core.hooksPath", scope)
    modes = {hook: hook.stat().st_mode & 0o777 for hook in hooks}
    changed = previous != ["githooks"]
    configured_by_us = False
    try:
        for hook, mode in modes.items():
            if os.name == "posix" and not mode & 0o111:
                hook.chmod(mode | 0o111)
        if changed:
            git(root, "config", scope, "--replace-all", "core.hooksPath", "githooks")
            configured_by_us = True
        effective = config_values(root, "core.hooksPath", path=True)
        if not effective or (root / effective[-1]).resolve() != expected:
            raise ArtifactError("another Git configuration overrides the repository hooks",
                                "resolve the overriding core.hooksPath setting and rerun bootstrap")
    except BaseException:
        if configured_by_us and config_values(root, "core.hooksPath", scope) == ["githooks"]:
            subprocess.run(["git", "-C", str(root), "config", scope, "--unset-all", "core.hooksPath"], capture_output=True)
            for value in previous:
                git(root, "config", scope, "--add", "core.hooksPath", value)
        for hook, mode in modes.items():
            if os.name == "posix" and hook.is_file() and not hook.is_symlink() and hook.stat().st_mode & 0o777 == mode | 0o111:
                hook.chmod(mode)
        raise
    return {"status": "enabled" if changed else "already-enabled", "path": "githooks", "scope": scope.removeprefix("--")}


def git_bool(root, key):
    result = subprocess.run(["git", "-C", str(root), "config", "--bool", "--get", key], capture_output=True, timeout=10)
    if result.returncode not in (0, 1):
        raise ArtifactError(f"invalid Git boolean setting: {key}")
    return result.stdout.strip() == b"true"


def bootstrap(root, *, selected=None, manifest_path="packaging/artifacts.toml", require_tools=False, replace_hooks=False):
    snapshot = Snapshot(root)
    item = snapshot.get(manifest_path)
    if item is None:
        raise ArtifactError("artifact manifest is missing", "restore packaging/artifacts.toml before contributor setup")
    manifest = load_manifest(item.data, manifest_path)
    tasks = manifest.order(selected, automatic=not selected)
    unavailable = {}
    for task in tasks:
        for tool in missing_tools(root, task):
            unavailable.setdefault(tool, []).append(task.name)
    hooks = install_hooks(root, replace=replace_hooks)
    code = 0
    try:
        checked = sync(root, selected=selected, check=True, manifest_path=manifest_path)
        artifacts = {"status": "current", "tasks": [task["task"] for task in checked["tasks"]]}
    except ArtifactError as error:
        artifacts = {"status": "needs-attention", "error": str(error), "hint": error.hint}
        code = error.code
    tools = [{"tool": tool, "tasks": names} for tool, names in sorted(unavailable.items())]
    if tools:
        prefix = "error: " if require_tools else "note: "
        print(prefix + "build tools missing for regeneration: " + "; ".join(f"{entry['tool']} ({', '.join(entry['tasks'])})" for entry in tools), file=sys.stderr)
        if require_tools:
            print("hint: provide the selected tasks' runtimes on PATH and rerun bootstrap; version pins remain with their maintained producers", file=sys.stderr)
            code = code or 2
    if code and artifacts["status"] != "current":
        print(f"error: {artifacts['error']}\nhint: {artifacts['hint']}", file=sys.stderr)
    return {"hooks": hooks, "artifacts": artifacts, "missing_build_tools": tools,
            "tool_check": "executable availability; producers enforce pinned versions when building"}, code
