#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELD_ORDER = (
    "state",
    "mode",
    "repo",
    "branch",
    "head_before",
    "head_after",
    "sync_status",
    "batch_commit_status",
    "local_commit_created",
    "local_commit_sha",
    "push_started",
    "push_completed",
    "push_succeeded",
    "resume_eligible",
    "last_error_summary",
    "next_action",
)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _sanitize(value: object) -> str:
    if isinstance(value, bool):
        return _bool_text(value)
    if value is None:
        return ""
    return str(value).replace("\t", " ").replace("\n", " ")


def probe_state(
    *,
    path: Path,
    repo_root: str,
    branch: str,
    head_oid: str,
    tracked: int,
    untracked: int,
    sequencer: str,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    state = "none"
    next_action = "continue with the requested workflow"
    local_commit_sha = ""
    resume_eligible = False

    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = "stale"
            next_action = "remove the invalid raw ship checkpoint before continuing"
            payload = {}
        else:
            local_commit_sha = str(payload.get("local_commit_sha", "") or "")
            state = "stale"
            next_action = "discard the stale raw ship checkpoint before continuing"
            if payload.get("mode") != "raw":
                next_action = "discard the stale raw ship checkpoint before continuing"
            elif payload.get("repo") != repo_root:
                next_action = "discard the stale raw ship checkpoint before continuing"
            elif tracked or untracked:
                next_action = "clean or commit local changes before rerunning ship raw"
            elif sequencer:
                next_action = "finish or abort the in-progress git operation before rerunning ship raw"
            elif not branch or branch == "DETACHED":
                next_action = "reattach HEAD before rerunning ship raw"
            elif payload.get("branch") != branch:
                next_action = f"return to branch '{payload.get('branch', '')}' or discard the stale raw ship checkpoint"
            elif not payload.get("local_commit_created"):
                next_action = "discard the stale raw ship checkpoint before continuing"
            elif not local_commit_sha:
                next_action = "discard the stale raw ship checkpoint before continuing"
            elif payload.get("head_after") != head_oid or local_commit_sha != head_oid:
                next_action = "branch HEAD moved since the interrupted raw ship; rerun ship raw from the current HEAD"
            elif payload.get("push_succeeded"):
                next_action = "discard the completed raw ship checkpoint before continuing"
            elif not payload.get("resume_eligible", False):
                next_action = "discard the stale raw ship checkpoint before continuing"
            else:
                state = "resume-eligible"
                resume_eligible = True
                next_action = "rerun 'ship raw' to resume the pending push"

    return {
        "state": state,
        "mode": str(payload.get("mode", "") or ""),
        "repo": str(payload.get("repo", "") or ""),
        "branch": str(payload.get("branch", "") or ""),
        "head_before": str(payload.get("head_before", "") or ""),
        "head_after": str(payload.get("head_after", "") or ""),
        "sync_status": str(payload.get("sync_status", "") or ""),
        "batch_commit_status": str(payload.get("batch_commit_status", "") or ""),
        "local_commit_created": bool(payload.get("local_commit_created", False)),
        "local_commit_sha": local_commit_sha,
        "push_started": bool(payload.get("push_started", False)),
        "push_completed": bool(payload.get("push_completed", False)),
        "push_succeeded": bool(payload.get("push_succeeded", False)),
        "resume_eligible": resume_eligible,
        "last_error_summary": str(payload.get("last_error_summary", "") or ""),
        "next_action": next_action,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe persisted raw ship checkpoint state for gitops workflow scripts."
    )
    parser.add_argument("command", choices=("probe",))
    parser.add_argument("--path", required=True, help="Path to the raw ship checkpoint JSON file.")
    parser.add_argument("--repo-root", required=True, help="Resolved repository root path.")
    parser.add_argument("--branch", required=True, help="Current branch name or DETACHED.")
    parser.add_argument("--head-oid", required=True, help="Current HEAD oid.")
    parser.add_argument("--tracked", required=True, type=int, help="Dirty tracked file count.")
    parser.add_argument("--untracked", required=True, type=int, help="Dirty untracked file count.")
    parser.add_argument("--sequencer", default="", help="Current sequencer state summary.")
    parser.add_argument("--format", choices=("json", "lines"), default="json")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    result = probe_state(
        path=Path(args.path),
        repo_root=args.repo_root,
        branch=args.branch,
        head_oid=args.head_oid,
        tracked=args.tracked,
        untracked=args.untracked,
        sequencer=args.sequencer,
    )
    if args.format == "lines":
        for field in FIELD_ORDER:
            print(_sanitize(result[field]))
    else:
        print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
