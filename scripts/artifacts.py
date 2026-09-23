#!/usr/bin/env python3
"""Synchronize declared repository artifact tasks."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

if sys.version_info < (3, 11):
    print("error: artifact commands require Python 3.11+\nhint: run this entry with a supported python3", file=sys.stderr)
    raise SystemExit(2)

from artifact_sync.bootstrap import bootstrap, install_hooks
from artifact_sync.engine import install_termination_handler, sync
from artifact_sync.model import ArtifactError, load_manifest
from artifact_sync.snapshots import Snapshot, repository


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArtifactError(message, "use --help for supported arguments")


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default="packaging/artifacts.toml")
    commands = parser.add_subparsers(dest="operation", required=True, parser_class=Parser)
    for operation in ("sync", "check", "list"):
        child = commands.add_parser(operation)
        child.add_argument("--task", action="append", default=[])
        child.add_argument("--source", default="worktree", help="worktree, index, or commit:<git-object>")
        if operation == "sync":
            child.add_argument("--stage", action="store_true", help="publish generated outputs into the selected index")
            child.add_argument("--replace", action="store_true", help="replace reviewed manual output differences")
            child.add_argument("--prepared", type=Path, help="restore from outputs and receipts for the exact inputs")
    commands.add_parser("pre-commit")
    setup = commands.add_parser("bootstrap", help="enable repository hooks and verify contributor readiness")
    setup.add_argument("--task", action="append", default=[])
    setup.add_argument("--require-tools", action="store_true", help="fail when tools for selected tasks are unavailable")
    setup.add_argument("--replace-hooks", action="store_true", help="select repository hooks over an existing custom hook setup")
    hooks = commands.add_parser("hooks-install", help="enable repository hooks without artifact checks")
    hooks.add_argument("--replace-hooks", action="store_true")
    push = commands.add_parser("pre-push")
    push.add_argument("remote", nargs="?")
    push.add_argument("url", nargs="?")
    try:
        args = parser.parse_args(argv)
        root = repository(args.repo)
        code = 0
        if args.operation == "bootstrap":
            result, code = bootstrap(root, selected=args.task or None, manifest_path=args.manifest,
                                     require_tools=args.require_tools, replace_hooks=args.replace_hooks)
        elif args.operation == "hooks-install":
            result = {"hooks": install_hooks(root, replace=args.replace_hooks)}
        elif args.operation == "list":
            snapshot = Snapshot(root, args.source)
            item = snapshot.get(args.manifest)
            if item is None:
                raise ArtifactError("artifact manifest not found")
            manifest = load_manifest(item.data, args.manifest)
            tasks = manifest.order(args.task or list(manifest.tasks), automatic=False)
            result = [{"task": task.name, "automatic": task.automatic, "cache": task.cache,
                       "needs": task.needs, "destinations": [d for o in task.outputs for d in o.destinations]}
                      for task in tasks]
        elif args.operation == "pre-commit":
            snapshot = Snapshot(root, "index")
            if snapshot.get(args.manifest) is None:
                result = {"source": "index", "status": "no artifact manifest in proposed commit"}
            else:
                result = sync(root, source="index", stage=True, automatic=True, manifest_path=args.manifest)
        elif args.operation == "pre-push":
            revisions = []
            for line in sys.stdin:
                parts = line.split()
                if len(parts) != 4:
                    raise ArtifactError("invalid pre-push ref input")
                _local_ref, local_oid, _remote_ref, _remote_oid = parts
                if set(local_oid) == {"0"}:
                    continue
                if local_oid not in revisions:
                    revisions.append(local_oid)
            result = []
            for revision in revisions:
                source = "commit:" + revision
                snapshot = Snapshot(root, source)
                if snapshot.get(args.manifest) is None:
                    result.append({"source": snapshot.source, "status": "no artifact manifest"})
                else:
                    result.append(sync(root, source=source, check=True, automatic=True, manifest_path=args.manifest))
        else:
            result = sync(root, source=args.source, selected=args.task or None, check=args.operation == "check",
                          stage=getattr(args, "stage", False), replace=getattr(args, "replace", False),
                          prepared=getattr(args, "prepared", None), manifest_path=args.manifest)
        print(json.dumps(result, separators=(",", ":")))
        return code
    except ArtifactError as exc:
        print(f"error: {exc}\nhint: {exc.hint}", file=sys.stderr)
        return exc.code
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"error: artifact operation could not complete: {exc}\nhint: inspect the selected paths and retry", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("error: interrupted\nhint: rerun the operation; publication recovery preserves owned files and the selected index", file=sys.stderr)
        return 130


if __name__ == "__main__":
    install_termination_handler()
    raise SystemExit(main())
