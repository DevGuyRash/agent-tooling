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

# Campaign manifests (.goals/campaign-<slug>.md) are the frozen chain spine for
# autonomous multi-child execution. "Coverage" is intentionally absent here: its
# absence is a validation warning, not an error.
CAMPAIGN_REQUIRED_SECTIONS = [
    "Intent",
    "Completeness Dimensions",
    "Goal Graph",
    "Chain Budget",
    "Chain Failure Policy",
    "Selection Recommendation",
]

FAILURE_POLICIES = ["halt-on-failure", "skip-dependents-and-continue"]

CAMPAIGN_LOCK_NAME = "campaign.sha256"

# Machine-readable verifier result contract shared by run_verifiers.py (writer)
# and audit_goal.py (the deterministic oracle reader).
VERIFIER_RESULT_SCHEMA = "goalspec.verifier.v1"
VERIFIER_RESULT_NAME = "result.json"

# Provenance artifacts embed the verbatim original request between these
# markers so the audit drift anchor can extract it without markdown parsing.
# Requests are arbitrary text — a PRD carries its own ## headings, which break
# any section-based extraction — and must round-trip byte-exact.
# Extraction is first-BEGIN to last-END, so a request that itself contains the
# marker strings still round-trips. Writer: record_provenance.py; reader:
# audit_goal.py.
PROVENANCE_REQUEST_BEGIN = "<!-- goalspec:original-request:begin -->"
PROVENANCE_REQUEST_END = "<!-- goalspec:original-request:end -->"

# A verifier command is something the runner can execute and read an exit code from.
# Bias toward extraction: a silently skipped verifier (e.g. a `git diff
# --exit-code` check that never runs while overall_passed reports True) is worse
# than a loud false failure the author has to look at.
VERIFIER_COMMAND_RE = re.compile(
    r"^(npm|pnpm|yarn|pytest|python|python3|go|cargo|mvn|gradle|make|just|tox|ruff|eslint|vitest|jest|bun|deno|git|bash|sh|node|npx|test)\b"
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


def goals_relative(path: Path) -> str:
    """Spell a path from its last '.goals' component onward.

    Launch lines and provenance artifacts are read from the workspace root, so
    '.goals/...' is the spelling that resolves there even when this process was
    handed an absolute path. Paths outside any .goals/ pass through as-is.
    """
    parts = Path(path).parts
    if ".goals" in parts:
        idx = len(parts) - 1 - tuple(reversed(parts)).index(".goals")
        return "/".join(parts[idx:])
    return Path(path).as_posix()


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
            # GoalSpec's own verification scripts name the contract by path as
            # the sanctioned close-out flow (validate --check-hash, render,
            # audit, run_verifiers, campaign_status). Exempt them as read
            # context, but never when the same command can write the mentioned
            # path back (--write <path>) or re-arm the lock after a mutation
            # (--write-hash): those must stay deniable post-freeze.
            if (re.search(rf"\b(?:validate_goal|render_goal|audit_goal|run_verifiers|campaign_status)\.py\b[^\n;]*{re.escape(p)}", compact)
                    and "--write-hash" not in compact
                    and not re.search(rf"--write[=\s]+(?:\./)?{re.escape(p)}", compact)):
                continue
            if re.search(write_verbs, compact) or any(v in compact for v in ["rm -rf .goals", "truncate", "chmod"]):
                return p
            if p in [".goals/current.md", ".goals/current.sha256"] and not re.search(r"\b(read|cat|grep|rg|sed -n|head|tail)\b", compact):
                return p
    return None


def _lock_expected_hash(lock: Path) -> str:
    """First token of a lock file; '' when empty/whitespace-only.

    An empty token can never equal a real sha256, so a corrupted/truncated lock
    reads as a hash mismatch ('mutated') instead of crashing the gate with an
    IndexError.
    """
    parts = lock.read_text(encoding="utf-8").split()
    return parts[0] if parts else ""


def current_hash_status(cwd: Optional[str] = None) -> dict:
    _, current, lock = active_goal_paths(cwd)
    if not current.exists():
        return {"exists": False, "matched": None, "reason": "no current.md"}
    current_hash = sha256_file(current)
    if not lock.exists():
        return {"exists": True, "matched": None, "current_hash": current_hash, "reason": "no current.sha256"}
    expected = _lock_expected_hash(lock)
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
    expected = _lock_expected_hash(lock)
    return {
        "locked": True,
        "matched": expected == current_hash,
        "lock": str(lock),
        "expected_hash": expected,
        "current_hash": current_hash,
        "reason": "matched" if expected == current_hash else "hash mismatch",
    }


_HEREDOC_START_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def extract_verifier_commands(section: str) -> List[str]:
    """Pull executable verifier commands from a ## Verifier section body.

    Fenced shell blocks contribute every non-comment line; a line opening a
    heredoc (e.g. `python3 - <<'PY'`) consumes its body through the terminator
    as ONE multi-line command — authors naturally write inline scripts that
    way, and splitting the body into per-line shell commands produces a
    false-failing oracle (each Python line exits 127). An unterminated heredoc
    consumes to the end of its fence, degrading to one loud failure instead of
    many spurious ones. Inline `code` spans contribute only when they begin
    with a recognized runner so prose backticks do not masquerade as commands.
    Order-preserving and de-duplicated.

    Inline spans must not cross newlines: a newline-tolerant class lets the
    span regex pair the opening fence's third backtick with the closing
    fence's first, re-extracting the whole fence interior as one spurious
    multi-line command beginning with the language tag 'bash'.
    """
    commands: List[str] = []
    for m in re.finditer(r"```(?:bash|sh|shell)?\s*\n(.*?)```", section, re.S | re.I):
        lines = m.group(1).splitlines()
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if not s or s.startswith("#"):
                i += 1
                continue
            heredoc = _HEREDOC_START_RE.search(s)
            if heredoc:
                tag = heredoc.group(2)
                block = [lines[i]]
                i += 1
                while i < len(lines):
                    block.append(lines[i])
                    if lines[i].strip() == tag:
                        break
                    i += 1
                commands.append("\n".join(block))
                i += 1
                continue
            commands.append(s)
            i += 1
    for m in re.finditer(r"`([^`\n]+)`", section):
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


# Pinned companions: a contract MAY pin shared artifacts its verifier depends
# on (e.g. one verify script referenced by many chain children) with a
# '- Pinned: <path> sha256 <hash>' line in ## Verifier. run_verifiers.py checks
# pins before executing commands and audit_goal.py re-checks them, so a
# companion mutated after lock fails loudly instead of silently re-defining
# the oracle. Pins hash raw bytes (sha256sum-compatible), not decoded text.
PINNED_COMPANION_RE = re.compile(r"(?mi)^\s*-\s*Pinned:\s*`?(\S+?)`?\s+sha256\s+([0-9a-fA-F]{64})\s*$")


def extract_pinned_companions(section: str) -> List[Tuple[str, str]]:
    """(path, expected_sha256) pairs declared in a ## Verifier section body."""
    return [(m.group(1), m.group(2).lower()) for m in PINNED_COMPANION_RE.finditer(section)]


def contract_workspace_root(contract: Path) -> Path:
    """Workspace root for a contract: the parent of its enclosing .goals dir.

    Covers root contracts (.goals/current.md) and chain children
    (.goals/children/G-00N/current.md); falls back to the contract's own
    directory for loose files outside any .goals tree, so relative pin paths
    in fixtures resolve next to the contract instead of against the cwd.
    """
    contract = Path(contract).resolve()
    for p in contract.parents:
        if p.name == ".goals":
            return p.parent
    return contract.parent


def check_pinned_companions(section: str, root: Path) -> List[dict]:
    """Integrity rows for the section's declared pins; passed=False on missing/mutated."""
    rows: List[dict] = []
    for rel, expected in extract_pinned_companions(section):
        p = Path(rel)
        target = p if p.is_absolute() else Path(root) / p
        if not target.exists():
            rows.append({"path": rel, "expected_sha256": expected, "actual_sha256": None,
                         "passed": False, "reason": "pinned companion missing"})
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        rows.append({"path": rel, "expected_sha256": expected, "actual_sha256": actual,
                     "passed": actual == expected,
                     "reason": "matched" if actual == expected else "pinned companion mutated"})
    return rows


def contract_verifier_commands(contract: Path) -> Optional[List[str]]:
    """Executable verifier commands a contract declares, via the runner's own extractor.

    Returns None when the contract cannot be read (nothing can be concluded) vs []
    when it is readable and certainly attestation-only — only [] may ever drive
    behavior. Shares extract_verifier_commands with run_verifiers.py, so callers
    judging chain advanceability can never diverge from what would actually run.
    """
    try:
        text = Path(contract).read_text(encoding="utf-8")
    except OSError:
        return None
    return extract_verifier_commands(parse_sections(text).get("Verifier", ""))


def excise_section(text: str, title: str) -> str:
    """Remove every level-2 '## <title>' section (heading + body) from markdown.

    Body extent matches parse_sections: from the heading to the next level-2
    heading or end of text, so '###' sub-headings are consumed with their parent.
    No-op when the section is absent.
    """
    return re.sub(rf"(?ms)^##[ \t]+{re.escape(title)}[ \t]*\n.*?(?=^##\s|\Z)", "", text)


def campaign_review_anchor(text: str) -> str:
    """Anchor hash binding a Decomposition Review to the manifest it reviewed.

    sha256 over the manifest bytes with the '## Decomposition Review' section
    removed: writing or extending the review (verdicts, the Anchor line itself)
    never moves the anchor, while any edit to the graph/coverage/budget does —
    so a review recorded before the content it claims to have reviewed, or left
    stale after post-review edits, reads as an anchor mismatch. Threat model:
    this makes the observed honest failures (pre-baked, stale reviews) loud; it
    does not defeat an adversarial author who recomputes the anchor — locks
    defeat tampering, nothing mechanical defeats insincerity.
    """
    return sha256_text(excise_section(text, "Decomposition Review"))


# The meta-goal smell: a goal whose terminal state and verifier are about
# GoalSpec itself (locks, renders, hooks, probes) delivers no workspace value —
# substrate checks belong inside a value-bearing goal, never as the goal.
_GOALSPEC_MACHINERY_RE = re.compile(
    r"\.goals/|goalspec|conformance_probe|validate_goal|validate_campaign|render_goal|audit_goal|"
    r"audit_campaign|run_verifiers|campaign_status|record_provenance|launch_goal|select_goal|"
    r"graph_goal|init_project|inventory_capabilities|score_goal_risk|extract_candidates|"
    r"\bhooks?\b|prompt_guard|scope_guard|evidence_capture|stop_guard",
    re.I,
)
_ARTIFACT_PATH_RE = re.compile(
    r"[A-Za-z0-9_.][A-Za-z0-9_./-]*\.(?:py|md|rs|ts|tsx|js|jsx|json|toml|yaml|yml|html|css|sh|sql|txt|csv|png|svg)\b"
)
_GOALSPEC_SCRIPT_NAMES = frozenset({
    "validate_goal.py", "validate_campaign.py", "render_goal.py", "audit_goal.py",
    "audit_campaign.py", "run_verifiers.py", "campaign_status.py", "record_provenance.py",
    "launch_goal.py", "select_goal.py", "graph_goal.py", "init_project.py",
    "inventory_capabilities.py", "score_goal_risk.py", "extract_candidates.py",
    "conformance_probe.py", "goalspec.py", "prompt_guard.py", "scope_guard.py",
    "evidence_capture.py", "stop_guard.py",
})


def references_only_goalspec_machinery(text: str) -> bool:
    """True when text leans on GoalSpec machinery and names no other artifact.

    Heuristic, biased toward under-flagging: any concrete non-GoalSpec artifact
    path in the text clears it. Callers should emit warnings (or errors only at
    the campaign level when ALL ready work is meta), with wording that tells a
    false-positive author the fix: name a workspace artifact the goal delivers.
    """
    if not _GOALSPEC_MACHINERY_RE.search(text):
        return False
    for match in _ARTIFACT_PATH_RE.finditer(text):
        path = match.group(0)
        if path.startswith(".goals/") or "/.goals/" in path:
            continue
        if path.rsplit("/", 1)[-1] in _GOALSPEC_SCRIPT_NAMES:
            continue
        return False
    return True


# --- Campaign (chain) helpers ---


def parse_campaign_children(markdown: str) -> List[Dict[str, str]]:
    """Parse '### G-00N: Title' child blocks from a campaign's Goal Graph.

    Returns entries shaped for select_goal.select(): each carries an explicit
    'id' plus the '- Field:' values (status, depends_on, contract, ...).
    """
    children: List[Dict[str, str]] = []
    for block in re.split(r"(?m)^###\s+", markdown)[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        raw_title = lines[0].strip()
        body = "\n".join(lines[1:])

        def field(name: str, default: str = "") -> str:
            m = re.search(rf"(?mi)^-\s*{re.escape(name)}:\s*(.+?)\s*$", body)
            return m.group(1).strip() if m else default

        gid, title = split_goal_id_title(raw_title)
        children.append({
            "id": gid or raw_title,
            "title": title,
            "status": field("Status", "conditional").lower(),
            "risk": field("Risk", "medium").lower(),
            "depends_on": field("Depends on", "none"),
            "contract": field("Contract", ""),
            "terminal_state": field("Terminal state", ""),
            "verifier": field("Verifier", ""),
        })
    return children


def campaign_workspace_root(campaign: Path) -> Path:
    """Workspace root for a campaign manifest living at <root>/.goals/campaign-*.md."""
    campaign = Path(campaign).resolve()
    return campaign.parent.parent if campaign.parent.name == ".goals" else campaign.parent


def child_evidence_dir(root: Path, child_id: str) -> Path:
    """Per-child evidence directory under the campaign workspace."""
    return Path(root) / ".goals" / "evidence" / "children" / child_id


def child_report_path(root: Path, child_id: str) -> Path:
    """Per-child run report path; status checks it, audit reads it, render names it."""
    return Path(root) / ".goals" / "reports" / f"{child_id}-report.md"


def campaign_failure_policies(section: str) -> List[str]:
    """Policies declared in a '## Chain Failure Policy' section body, in canonical order."""
    return [p for p in FAILURE_POLICIES if re.search(rf"\b{re.escape(p)}\b", section)]


def campaign_chain_budget(section: str) -> Optional[int]:
    """Numeric ceiling from a '## Chain Budget' section body; None when absent."""
    m = re.search(r"\d+", section)
    return int(m.group(0)) if m else None


def infer_campaign_manifest(goals_dir: Path = Path(".goals")) -> Tuple[Optional[Path], str]:
    """The single .goals/campaign-*.md, or (None, reason) when ambiguous/absent."""
    candidates = sorted(Path(goals_dir).glob("campaign-*.md"))
    if len(candidates) == 1:
        return candidates[0], ""
    return None, f"Cannot infer campaign manifest (found {len(candidates)}); pass it explicitly."


def goal_mission_active(goals_dir: Path) -> bool:
    """A mission exists: a root contract (even unlocked) or a locked campaign chain."""
    goals = Path(goals_dir)
    return (goals / "current.md").exists() or (goals / CAMPAIGN_LOCK_NAME).exists()


def goal_workspace_locked(goals_dir: Path) -> bool:
    """The workspace is frozen: a complete root contract+lock pair or a campaign lock."""
    goals = Path(goals_dir)
    return ((goals / "current.md").exists() and (goals / "current.sha256").exists()) \
        or (goals / CAMPAIGN_LOCK_NAME).exists()


def child_contract_path(campaign: Path, child: Dict[str, str]) -> Optional[Path]:
    """Resolve a child's Contract: path relative to the campaign workspace root."""
    contract = (child.get("contract") or "").strip().strip("`")
    if not contract:
        return None
    p = Path(contract)
    return p if p.is_absolute() else campaign_workspace_root(campaign) / p


def campaign_aggregate_hash(campaign: Path) -> str:
    """Aggregate freeze hash: campaign bytes + every ready child's contract hash.

    Any manifest edit or ready-child contract swap changes this value, which is
    what .goals/campaign.sha256 records. Children are folded in sorted-id order
    so the hash does not depend on manifest ordering. Missing contracts fold in
    a sentinel so an unresolvable child can never hash-collide with a real one.
    """
    campaign = Path(campaign)
    text = read_text(campaign)
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    children = parse_campaign_children(text)
    ready = sorted((c for c in children if c.get("status") == "ready"), key=lambda c: c["id"])
    for child in ready:
        contract = child_contract_path(campaign, child)
        h.update(f"\n{child['id']}\n".encode("utf-8"))
        if contract and contract.exists():
            h.update(sha256_file(contract).encode("utf-8"))
        else:
            h.update(b"missing-contract")
    return h.hexdigest()


def campaign_lock_path(campaign: Path) -> Path:
    return Path(campaign).with_name(CAMPAIGN_LOCK_NAME)


def campaign_lock_status(campaign: Path) -> dict:
    """Lock status for a campaign manifest against its sibling campaign.sha256.

    Mirrors contract_lock_status's shape so callers (render/audit gates) can
    share one definition of locked / matched / mismatch.
    """
    campaign = Path(campaign)
    lock = campaign_lock_path(campaign)
    if not campaign.exists():
        return {"locked": False, "matched": None, "lock": str(lock), "reason": "missing campaign manifest"}
    current_hash = campaign_aggregate_hash(campaign)
    if not lock.exists():
        return {"locked": False, "matched": None, "lock": str(lock),
                "current_hash": current_hash, "reason": "no campaign.sha256 lock"}
    expected = _lock_expected_hash(lock)
    return {
        "locked": True,
        "matched": expected == current_hash,
        "lock": str(lock),
        "expected_hash": expected,
        "current_hash": current_hash,
        "reason": "matched" if expected == current_hash else "hash mismatch",
    }


def dependency_tokens(raw: str) -> List[str]:
    """All cleaned tokens of a 'Depends on:' value ('none'/'n/a'/'[]' -> [])."""
    if not raw or raw.strip().lower() in {"none", "n/a", "[]"}:
        return []
    return [p.strip(" `[]") for p in re.split(r"[,\s]+", raw) if p.strip(" `[]")]


def _dependency_ids(raw: str) -> List[str]:
    # Only well-formed G-<n> ids participate in graph math. Tokens this filter
    # drops are NOT silently ignorable for validation: select_goal.is_unblocked
    # parses dependencies more loosely at runtime, so validate_campaign must
    # reject anything dependency_tokens() yields that this does not.
    return [p for p in dependency_tokens(raw) if re.match(r"^G-\d+$", p)]


def dependency_map(children: Sequence[Dict[str, str]]) -> Dict[str, List[str]]:
    """child id -> list of ids it depends on (declared in the manifest)."""
    return {c["id"]: _dependency_ids(c.get("depends_on", "")) for c in children}


def find_cycles(deps: Dict[str, List[str]]) -> List[List[str]]:
    """Dependency cycles as id lists, via iterative DFS over the declared edges."""
    cycles: List[List[str]] = []
    visited: set = set()
    for start in deps:
        if start in visited:
            continue
        stack: List[Tuple[str, List[str]]] = [(start, [start])]
        while stack:
            node, path = stack.pop()
            for dep in deps.get(node, []):
                if dep in path:
                    cycle = path[path.index(dep):] + [dep]
                    if not any(set(cycle) == set(c) for c in cycles):
                        cycles.append(cycle)
                    continue
                if dep in deps:
                    stack.append((dep, path + [dep]))
        visited.add(start)
    return cycles


def propagate_dependency_failures(deps: Dict[str, List[str]], failed: Sequence[str]) -> Dict[str, str]:
    """Map of skipped child id -> the failed dependency that blocks it (transitive)."""
    blocked: Dict[str, str] = {}
    frontier = {f: f for f in failed}
    changed = True
    while changed:
        changed = False
        for gid, dep_ids in deps.items():
            if gid in blocked or gid in frontier:
                continue
            for dep in dep_ids:
                root_cause = frontier.get(dep) or blocked.get(dep)
                if root_cause:
                    blocked[gid] = root_cause
                    changed = True
                    break
    return blocked
