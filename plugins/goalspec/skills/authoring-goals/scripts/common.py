#!/usr/bin/env python3
"""Shared helpers for GoalSpec scripts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REQUIRED_SECTIONS = [
    "Objective",
    "Intent",
    "Context",
    "Available Capabilities",
    "Completeness Dimensions",
    "Terminal State",
    "Verifier",
    "Scope",
    "Budget",
    "Give-Up Conditions",
    "Priority Order",
    "Follow-Up Policy",
    "Evidence Required",
]

OPEN_ENDED_PHRASES = [
    "keep improving",
    "keep up to date",
    "as much as possible",
    "until satisfied",
    "best practices",
    "make better",
    "clean up",
    "polish",
    "modernize",
    "optimize",
    "harden",
    "stabilize",
    "productionize",
    "improve",
]

REPORT_FIELDS = [
    "Files Changed",
    "Commands Run",
    "Evidence",
    "Budget Used",
    "Remaining Risks",
    "Follow-Up Candidates",
]

# Machine-readable verifier result contract shared by run_verifiers.py (writer)
# and audit_goal.py (the deterministic oracle reader).
VERIFIER_RESULT_SCHEMA = "goalspec.verifier.v1"
VERIFIER_RESULT_NAME = "result.json"

# A verifier command is something the runner can execute and read an exit code from.
VERIFIER_COMMAND_RE = re.compile(
    r"^(npm|pnpm|yarn|pytest|python|python3|go|cargo|mvn|gradle|make|just|tox|ruff|eslint|vitest|jest|bun|deno)\b"
)

# Patterns that mark a verifier as a non-executable oracle. A human/artifact/MCP
# gate cannot produce a machine pass/fail, so audit may fall back to the report
# attestation for those kinds; metric thresholds still need a command to measure.
_VERIFIER_KIND_PATTERNS = {
    "human": r"\b(human|manual(?:ly)?|reviewer|review by|sign[\s-]?off|approv(?:e|al)|inspect|screenshot|by hand|stakeholder)\b",
    "artifact": r"\b(artifact|file exists|path exists|exists at|present at|generated file|output file|produced file)\b",
    "mcp": r"(mcp__|\bMCP\b|model context protocol)",
    "metric": r"(\bthreshold\b|\bcoverage\b|\bp9[05]\b|\blatency\b|>=|<=|\b\d+\s?%|\bpercent\b)",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_text(read_text(path))


def parse_sections(markdown: str) -> Dict[str, str]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", markdown, re.M))
    sections: Dict[str, str] = {}
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        sections[title] = markdown[start:end].strip()
    return sections


def split_goal_id_title(raw_title: str) -> Tuple[Optional[str], str]:
    """Split a goal heading like 'G-001 Title' or 'G-001: Title' into (id, title).

    Returns (None, title) when no 'G-<n>' prefix is present, leaving the id
    fallback to the caller. Prevents the id from being doubled into the title.
    """
    raw = raw_title.strip()
    m = re.match(r"^(G-\d+)\b[:\-\s]*(.*)$", raw)
    if m:
        return m.group(1), (m.group(2).strip() or raw)
    return None, raw


def bullets(text: str) -> List[str]:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("- ") or re.match(r"^\d+\.\s+", s):
            out.append(re.sub(r"^(?:- |\d+\.\s+)", "", s).strip())
    return out


def nonempty_without_placeholders(text: str) -> bool:
    if not text.strip():
        return False
    if "[" in text and "]" in text:
        return False
    return True


def load_json_stdin() -> dict:
    try:
        import sys
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def git_root_or_cwd(cwd: Optional[str] = None) -> Path:
    start = Path(cwd or os.getcwd()).resolve()
    if os.environ.get("GOALSPEC_NO_GIT") == "1":
        return start
    # Fast path: walk upward for .git before invoking git. This avoids slow git calls
    # in temporary test directories and non-repo workspaces.
    for p in [start, *start.parents]:
        if (p / ".git").exists():
            return p.resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=0.75,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
    except Exception:
        pass
    return start


def active_goal_paths(cwd: Optional[str] = None) -> Tuple[Path, Path, Path]:
    root = git_root_or_cwd(cwd)
    return root / ".goals", root / ".goals" / "current.md", root / ".goals" / "current.sha256"


def relpath(path: Path, root: Optional[Path] = None) -> str:
    root = root or git_root_or_cwd()
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def write_event(cwd: str, payload: dict, prefix: str = "event", root: Optional[Path] = None) -> Path:
    from datetime import datetime, timezone
    root = Path(root) if root else git_root_or_cwd(cwd)
    events = root / ".goals" / "evidence" / "events"
    events.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = events / f"{ts}-{prefix}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def extract_patch_paths(command: str) -> List[str]:
    paths: List[str] = []
    patterns = [
        r"^\*\*\*\s+(?:Update|Add|Delete)\s+File:\s+(.+?)\s*$",
        r"^diff --git a/(.+?) b/(.+?)$",
        r"^---\s+a/(.+?)$",
        r"^\+\+\+\s+b/(.+?)$",
    ]
    for line in command.splitlines():
        for pat in patterns:
            m = re.match(pat, line.strip())
            if m:
                for g in m.groups():
                    if g and g != "/dev/null":
                        paths.append(g.strip())
    return sorted(set(paths))


def command_mentions_write_to_protected(command: str, protected_paths: Sequence[str]) -> Optional[str]:
    compact = command.replace("\\ ", " ")
    write_verbs = r"(?:>|>>|tee\s+|cp\s+|mv\s+|rm\s+|sed\s+-i|perl\s+-pi|python\S*\s+.*open\()"
    for p in protected_paths:
        if p in compact:
            if re.search(rf"\b(cat|less|grep|rg|sed\s+-n|head|tail|wc|sha256sum|shasum)\b[^\n;]*{re.escape(p)}", compact):
                continue
            if re.search(write_verbs, compact) or any(v in compact for v in ["rm -rf .goals", "truncate", "chmod"]):
                return p
            if p in [".goals/current.md", ".goals/current.sha256"] and not re.search(r"\b(read|cat|grep|rg|sed -n|head|tail)\b", compact):
                return p
    return None


def current_hash_status(cwd: Optional[str] = None) -> dict:
    _, current, lock = active_goal_paths(cwd)
    if not current.exists():
        return {"exists": False, "matched": None, "reason": "no current.md"}
    current_hash = sha256_file(current)
    if not lock.exists():
        return {"exists": True, "matched": None, "current_hash": current_hash, "reason": "no current.sha256"}
    expected = lock.read_text(encoding="utf-8").strip().split()[0]
    return {
        "exists": True,
        "matched": expected == current_hash,
        "expected_hash": expected,
        "current_hash": current_hash,
        "reason": "matched" if expected == current_hash else "hash mismatch",
    }


def contract_lock_status(path: Path) -> dict:
    """Path-relative lock status for a contract and its sibling current.sha256.

    Unlike current_hash_status (which resolves the active goal via the git root),
    this checks the lock next to a given contract path — the convention used by
    validate --write-hash/--check-hash and the render freeze gate, so they share
    one definition of locked / matched / mismatch.
    """
    path = Path(path)
    lock = path.with_name("current.sha256")
    if not path.exists():
        return {"locked": False, "matched": None, "lock": str(lock), "reason": "missing contract"}
    current_hash = sha256_file(path)
    if not lock.exists():
        return {"locked": False, "matched": None, "lock": str(lock),
                "current_hash": current_hash, "reason": "no current.sha256 lock"}
    expected = lock.read_text(encoding="utf-8").strip().split()[0]
    return {
        "locked": True,
        "matched": expected == current_hash,
        "lock": str(lock),
        "expected_hash": expected,
        "current_hash": current_hash,
        "reason": "matched" if expected == current_hash else "hash mismatch",
    }


def extract_verifier_commands(section: str) -> List[str]:
    """Pull executable verifier commands from a ## Verifier section body.

    Fenced shell blocks contribute every non-comment line; inline `code` spans
    contribute only when they begin with a recognized runner so prose backticks
    do not masquerade as commands. Order-preserving and de-duplicated.
    """
    commands: List[str] = []
    for m in re.finditer(r"```(?:bash|sh|shell)?\s*\n(.*?)```", section, re.S | re.I):
        for line in m.group(1).splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                commands.append(s)
    for m in re.finditer(r"`([^`]+)`", section):
        c = m.group(1).strip()
        if VERIFIER_COMMAND_RE.match(c):
            commands.append(c)
    return list(dict.fromkeys(commands))


def verifier_kinds(section: str) -> set:
    """Classify a ## Verifier section into the oracle kinds it declares.

    Returns a subset of {command, human, artifact, mcp, metric}. 'command' means
    audit expects a machine pass/fail result; human/artifact/mcp mark a
    non-executable oracle whose outcome lives in the run report attestation.
    """
    kinds = set()
    if extract_verifier_commands(section):
        kinds.add("command")
    for kind, pat in _VERIFIER_KIND_PATTERNS.items():
        if re.search(pat, section, re.I):
            kinds.add(kind)
    return kinds


def verifier_result_path(goals_dir: Path) -> Path:
    """Canonical location of the machine-readable verifier result file."""
    return Path(goals_dir) / "evidence" / "verifiers" / VERIFIER_RESULT_NAME
