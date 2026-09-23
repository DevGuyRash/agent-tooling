#!/usr/bin/env python3
"""Produce one declared Rust release in two independent source trees."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile

import rust_release as build


def main():
    try:
        parameters = json.loads(os.environ["ARTIFACT_TASK_PARAMETERS"])["rust"]
        root = Path(os.environ["ARTIFACT_SOURCE_ROOT"])
        output = Path(os.environ["ARTIFACT_OUTPUT_ROOT"])
        platform = parameters["platform"]
        skill = {**parameters, "skill_dir": "result"}
        expected = build.toolchain_channel()
        actual = build.command_version(["rustc", "--version"], "Rust compiler").split()
        if len(actual) < 2 or actual[1] != expected:
            raise ValueError(f"Rust compiler must match rust-toolchain.toml ({expected})")
        build.verify_release_tool(skill, platform)
        with tempfile.TemporaryDirectory(prefix="rust-artifact-") as temporary:
            stage = Path(temporary)
            trees = []
            outputs = []
            for suffix in ("a", "b"):
                source = stage / ("source-" + suffix)
                shutil.copytree(root, source, ignore=shutil.ignore_patterns("_out", "target", "__pycache__", ".git"))
                artifacts = stage / ("artifacts-" + suffix)
                artifacts.mkdir()
                # Each build has its own target tree. The existing release flags normalize source/toolchain paths.
                previous = os.environ.pop("CARGO_TARGET_DIR", None)
                try:
                    build.stage_from_frozen_index([(parameters["package"], skill, platform)], source, artifacts)
                finally:
                    if previous is not None:
                        os.environ["CARGO_TARGET_DIR"] = previous
                trees.append(source)
                outputs.append(artifacts)
            build.compare_built_artifacts(outputs[0], outputs[1], [(parameters["package"], skill, platform)])
            binary = outputs[0] / "result/dist" / platform / build.binary_name(skill, platform)
            target = output / parameters["binary"]
            shutil.copy2(binary, target)
            target.chmod(0o755)
            print(json.dumps({"package": parameters["package"], "platform": platform,
                              "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "reproducible": True},
                             separators=(",", ":")))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"error: Rust artifact preparation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
