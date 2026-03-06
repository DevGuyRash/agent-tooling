#!/usr/bin/env python3
"""Deterministic GitHub governance reconciliation for gitops-workflow skill.

Commands:
  - validate: validate policy contract
  - plan: compute deterministic drift
  - apply: reconcile GitHub/local state to policy
  - audit: report drift (json/markdown)
  - export: snapshot current repo governance into policy contract

Design goals:
  - idempotent reconciliation
  - stable diff ordering
  - fail-closed apply behavior
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote

LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from bootstrap import maybe_reexec_repo_local_copy


maybe_reexec_repo_local_copy(Path(__file__).resolve(), sys.argv)

SCHEMA_VERSION = "github-governance/v1"

EXIT_OK = 0
EXIT_INVALID_POLICY = 2
EXIT_DRIFT = 3
EXIT_APPLY_FAILED = 4
EXIT_PERMISSIONS = 5

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_POLICY_PATH = str(SKILL_ROOT / "assets" / "config" / "github-governance-policy.v1.json")
DEFAULT_CODEOWNERS_PATH = ".github/CODEOWNERS"


class GovernanceError(Exception):
    """Error with an explicit CLI exit code."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class DriftItem:
    """Normalized governance drift record."""

    resource_type: str
    resource_id: str
    action: str
    before: Any
    after: Any
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resourceType": self.resource_type,
            "resourceId": self.resource_id,
            "action": self.action,
            "before": self.before,
            "after": self.after,
            "status": self.status,
        }


class GitHubClient:
    """Minimal wrapper around `gh api` with deterministic JSON handling."""

    def __init__(self, runner: Optional[Any] = None) -> None:
        self._runner = runner or run_cmd

    def api_json(self, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Any:
        cmd = ["gh", "api"]
        method_u = method.upper()
        if method_u != "GET":
            cmd.extend(["-X", method_u])
        cmd.append(path)

        input_text = None
        if payload is not None:
            cmd.extend(["--input", "-"])
            input_text = json.dumps(payload, sort_keys=True)

        try:
            raw = self._runner(cmd, input_text=input_text)
        except GovernanceError:
            raise
        except subprocess.CalledProcessError as exc:
            output = decode_output(exc)
            lowered = output.lower()
            if "resource not accessible by integration" in lowered or "requires" in lowered and "scope" in lowered:
                raise GovernanceError(output.strip() or "insufficient GitHub token scopes", EXIT_PERMISSIONS)
            if "not found" in lowered:
                raise GovernanceError(output.strip() or f"GitHub API path not found: {path}", EXIT_INVALID_POLICY)
            raise GovernanceError(output.strip() or f"gh api failed for {path}", EXIT_APPLY_FAILED)
        except FileNotFoundError as exc:
            # Ensure a missing `gh` binary maps to a deterministic governance exit code.
            raise GovernanceError(str(exc), EXIT_PERMISSIONS)

        if raw.strip() == "":
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GovernanceError(f"Invalid JSON response from GitHub API for {path}: {exc}", EXIT_APPLY_FAILED)


class GovernanceManager:
    """Core deterministic governance logic."""

    def __init__(self, client: GitHubClient) -> None:
        self.client = client

    def plan(self, policy: Dict[str, Any], repo: Optional[str] = None) -> Dict[str, Any]:
        resolved_repo = repo or repo_from_policy(policy)
        labels_drift = self._plan_labels(policy, resolved_repo)
        rules_drift = self._plan_rules(policy, resolved_repo)
        codeowners_drift = self._plan_codeowners(policy)

        drift = sorted(
            labels_drift + rules_drift + codeowners_drift,
            key=lambda d: (d.resource_type, d.resource_id, d.action),
        )
        return {
            "repo": resolved_repo,
            "hasDrift": any(item.action != "none" for item in drift),
            "drift": [item.to_dict() for item in drift if item.action != "none"],
        }

    def apply(self, policy: Dict[str, Any], repo: Optional[str], write_codeowners: bool) -> Dict[str, Any]:
        plan = self.plan(policy, repo)
        if not plan["hasDrift"]:
            return {"repo": plan["repo"], "applied": [], "hasDrift": False}

        results: List[Dict[str, Any]] = []
        failures: List[str] = []

        for item in plan["drift"]:
            rtype = item["resourceType"]
            action = item["action"]
            rid = item["resourceId"]
            try:
                if rtype == "label":
                    self._apply_label_action(plan["repo"], action, rid, item)
                elif rtype == "ruleset":
                    self._apply_ruleset_action(plan["repo"], action, rid, item)
                elif rtype == "codeowners":
                    if not write_codeowners:
                        raise GovernanceError(
                            "CODEOWNERS drift detected. Re-run with --write-codeowners to reconcile local file.",
                            EXIT_APPLY_FAILED,
                        )
                    self._apply_codeowners_action(item)
                else:
                    raise GovernanceError(f"Unsupported drift item type: {rtype}", EXIT_APPLY_FAILED)
                results.append({"resourceType": rtype, "resourceId": rid, "action": action, "status": "applied"})
            except GovernanceError as exc:
                failures.append(f"{rtype}/{rid}: {exc}")

        if failures:
            raise GovernanceError("; ".join(failures), EXIT_APPLY_FAILED)

        return {"repo": plan["repo"], "applied": results, "hasDrift": True}

    def audit(self, policy: Dict[str, Any], repo: Optional[str]) -> Dict[str, Any]:
        return self.plan(policy, repo)

    def export(self, repo: str) -> Dict[str, Any]:
        owner, name = split_repo(repo)
        repo_json = self.client.api_json(f"repos/{owner}/{name}")

        labels_raw = self._list_labels(repo)
        labels = sorted((normalize_label(label) for label in labels_raw), key=lambda l: l["name"])

        required_checks = []
        rulesets: List[Dict[str, Any]] = []
        try:
            for rs in self._list_rulesets(repo):
                n = normalize_ruleset(rs)
                rulesets.append(n)
                required_checks.extend(extract_required_checks(n))
        except GovernanceError:
            rulesets = []

        required_checks = sorted({c for c in required_checks})
        policy = {
            "schemaVersion": SCHEMA_VERSION,
            "repository": {
                "owner": owner,
                "name": name,
                "defaultBranch": repo_json.get("default_branch", "main"),
            },
            "rulesets": rulesets,
            "requiredChecks": required_checks,
            "codeowners": {
                "path": DEFAULT_CODEOWNERS_PATH,
                "entries": parse_codeowners_file(Path(DEFAULT_CODEOWNERS_PATH)),
            },
            "labels": labels,
            "options": default_options(),
        }
        return canonicalize(policy)

    def _plan_labels(self, policy: Dict[str, Any], repo: str) -> List[DriftItem]:
        current = {normalize_label(l)["name"]: normalize_label(l) for l in self._list_labels(repo)}
        desired = {label["name"]: normalize_label(label) for label in policy["labels"]}

        drift: List[DriftItem] = []

        for name in sorted(desired):
            if name not in current:
                drift.append(
                    DriftItem(
                        resource_type="label",
                        resource_id=name,
                        action="create",
                        before=None,
                        after=desired[name],
                        status="pending",
                    )
                )
                continue
            if desired[name] != current[name]:
                drift.append(
                    DriftItem(
                        resource_type="label",
                        resource_id=name,
                        action="update",
                        before=current[name],
                        after=desired[name],
                        status="pending",
                    )
                )

        for name in sorted(current):
            if name not in desired:
                drift.append(
                    DriftItem(
                        resource_type="label",
                        resource_id=name,
                        action="delete",
                        before=current[name],
                        after=None,
                        status="pending",
                    )
                )

        return drift

    def _plan_rules(self, policy: Dict[str, Any], repo: str) -> List[DriftItem]:
        desired_rulesets = desired_rulesets_from_policy(policy)
        options = policy["options"]

        try:
            current_raw = self._list_rulesets(repo)
            current = {normalize_ruleset(r)["name"]: normalize_ruleset(r) for r in current_raw}
            current_ids = {
                normalize_ruleset(r)["name"]: r.get("id") for r in current_raw if normalize_ruleset(r).get("name")
            }
        except GovernanceError as exc:
            if options.get("allowLegacyBranchProtection", False):
                return self._plan_legacy_branch_protection(policy, repo)
            raise GovernanceError(
                f"Rulesets unavailable and legacy fallback disabled: {exc}", EXIT_INVALID_POLICY
            )

        desired = {ruleset["name"]: ruleset for ruleset in desired_rulesets}

        drift: List[DriftItem] = []
        for name in sorted(desired):
            if name not in current:
                drift.append(
                    DriftItem(
                        resource_type="ruleset",
                        resource_id=name,
                        action="create",
                        before=None,
                        after=desired[name],
                        status="pending",
                    )
                )
                continue
            merged_after = dict(desired[name])
            merged_after["id"] = current_ids.get(name)
            if desired[name] != current[name]:
                drift.append(
                    DriftItem(
                        resource_type="ruleset",
                        resource_id=name,
                        action="update",
                        before=current[name],
                        after=merged_after,
                        status="pending",
                    )
                )

        if options.get("rulesetsExact", True):
            for name in sorted(current):
                if name not in desired:
                    drift.append(
                        DriftItem(
                            resource_type="ruleset",
                            resource_id=name,
                            action="delete",
                            before={"id": current_ids.get(name), **current[name]},
                            after=None,
                            status="pending",
                        )
                    )

        return drift

    def _plan_legacy_branch_protection(self, policy: Dict[str, Any], repo: str) -> List[DriftItem]:
        desired = legacy_branch_protection_from_policy(policy)
        branch = policy["repository"]["defaultBranch"]
        path = f"repos/{repo}/branches/{quote(branch, safe='')}/protection"
        current = self.client.api_json(path)
        normalized_current = normalize_legacy_branch_protection(current)
        normalized_desired = normalize_legacy_branch_protection(desired)

        if normalized_current == normalized_desired:
            return []
        return [
            DriftItem(
                resource_type="ruleset",
                resource_id=f"legacy-branch-protection:{branch}",
                action="update",
                before=normalized_current,
                after=normalized_desired,
                status="pending",
            )
        ]

    def _plan_codeowners(self, policy: Dict[str, Any]) -> List[DriftItem]:
        codeowners = policy["codeowners"]
        path = Path(codeowners["path"])
        desired_content = render_codeowners(codeowners["entries"]) + "\n"
        before_content = ""
        if path.exists():
            before_content = path.read_text(encoding="utf-8")

        if before_content == desired_content:
            return []

        return [
            DriftItem(
                resource_type="codeowners",
                resource_id=str(path),
                action="update",
                before=before_content,
                after=desired_content,
                status="pending",
            )
        ]

    def _list_labels(self, repo: str) -> List[Dict[str, Any]]:
        owner, name = split_repo(repo)
        labels: List[Dict[str, Any]] = []
        page = 1
        while True:
            page_data = self.client.api_json(f"repos/{owner}/{name}/labels?per_page=100&page={page}")
            if not page_data:
                break
            if not isinstance(page_data, list):
                raise GovernanceError("Unexpected labels API response shape", EXIT_APPLY_FAILED)
            labels.extend(page_data)
            if len(page_data) < 100:
                break
            page += 1
        return labels

    def _list_rulesets(self, repo: str) -> List[Dict[str, Any]]:
        owner, name = split_repo(repo)
        data = self.client.api_json(f"repos/{owner}/{name}/rulesets")
        if not isinstance(data, list):
            raise GovernanceError("Unexpected rulesets API response shape", EXIT_APPLY_FAILED)
        return data

    def _apply_label_action(self, repo: str, action: str, label_name: str, item: Dict[str, Any]) -> None:
        owner, name = split_repo(repo)
        encoded = quote(label_name, safe="")
        if action == "create":
            self.client.api_json(f"repos/{owner}/{name}/labels", method="POST", payload=item["after"])
            return
        if action == "update":
            payload = {"new_name": item["after"]["name"], "color": item["after"]["color"], "description": item["after"].get("description", "")}
            self.client.api_json(f"repos/{owner}/{name}/labels/{encoded}", method="PATCH", payload=payload)
            return
        if action == "delete":
            self.client.api_json(f"repos/{owner}/{name}/labels/{encoded}", method="DELETE")
            return
        raise GovernanceError(f"Unsupported label action: {action}", EXIT_APPLY_FAILED)

    def _apply_ruleset_action(self, repo: str, action: str, name: str, item: Dict[str, Any]) -> None:
        owner, repo_name = split_repo(repo)

        if name.startswith("legacy-branch-protection:"):
            branch = name.split(":", 1)[1]
            path = f"repos/{owner}/{repo_name}/branches/{quote(branch, safe='')}/protection"
            self.client.api_json(path, method="PUT", payload=item["after"])
            return

        if action == "create":
            self.client.api_json(f"repos/{owner}/{repo_name}/rulesets", method="POST", payload=item["after"])
            return

        if action == "update":
            ruleset_id = (item.get("before") or {}).get("id") or (item.get("after") or {}).get("id")
            if ruleset_id is None:
                raise GovernanceError(f"Missing ruleset id for update: {name}", EXIT_APPLY_FAILED)
            payload = dict(item["after"])
            payload.pop("id", None)
            self.client.api_json(f"repos/{owner}/{repo_name}/rulesets/{ruleset_id}", method="PUT", payload=payload)
            return

        if action == "delete":
            ruleset_id = (item.get("before") or {}).get("id")
            if ruleset_id is None:
                raise GovernanceError(f"Missing ruleset id for delete: {name}", EXIT_APPLY_FAILED)
            self.client.api_json(f"repos/{owner}/{repo_name}/rulesets/{ruleset_id}", method="DELETE")
            return

        raise GovernanceError(f"Unsupported ruleset action: {action}", EXIT_APPLY_FAILED)

    def _apply_codeowners_action(self, item: Dict[str, Any]) -> None:
        path = Path(item["resourceId"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item["after"], encoding="utf-8")


def run_cmd(cmd: Sequence[str], input_text: Optional[str] = None) -> str:
    """Run a command and return stdout as text."""
    try:
        proc = subprocess.run(
            list(cmd),
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise exc

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, list(cmd), output=proc.stdout, stderr=proc.stderr)
    return proc.stdout


def decode_output(exc: subprocess.CalledProcessError) -> str:
    output = exc.output if isinstance(exc.output, str) else ""
    stderr = exc.stderr if isinstance(exc.stderr, str) else ""
    return f"{output}\n{stderr}".strip()


def split_repo(repo: str) -> Tuple[str, str]:
    if "/" not in repo:
        raise GovernanceError(f"Repo must be owner/name, got: {repo}", EXIT_INVALID_POLICY)
    owner, name = repo.split("/", 1)
    owner = owner.strip()
    name = name.strip()
    if not owner or not name:
        raise GovernanceError(f"Repo must be owner/name, got: {repo}", EXIT_INVALID_POLICY)
    return owner, name


def repo_from_policy(policy: Dict[str, Any]) -> str:
    repo = policy["repository"]
    return f"{repo['owner']}/{repo['name']}"


def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: canonicalize(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(v) for v in value]
    return value


def default_options() -> Dict[str, Any]:
    return {
        "allowLegacyBranchProtection": False,
        "rulesetsExact": True,
        "managedRulesetName": "default-branch-protection",
        "requiredApprovingReviewCount": 1,
        "dismissStaleReviews": True,
        "requireCodeOwnerReview": True,
        "requireLastPushApproval": False,
        "requireLinearHistory": True,
        "requireSignedCommits": False,
        "blockForcePushes": True,
    }


def validate_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(policy, dict):
        raise GovernanceError("Policy must be a JSON object", EXIT_INVALID_POLICY)

    allowed_top = {
        "schemaVersion",
        "repository",
        "rulesets",
        "requiredChecks",
        "codeowners",
        "labels",
        "options",
        "bypass",
    }
    unknown = sorted(set(policy) - allowed_top)
    if unknown:
        raise GovernanceError(f"Unknown policy keys: {', '.join(unknown)}", EXIT_INVALID_POLICY)

    if policy.get("schemaVersion") != SCHEMA_VERSION:
        raise GovernanceError(
            f"schemaVersion must be '{SCHEMA_VERSION}'",
            EXIT_INVALID_POLICY,
        )

    repository = policy.get("repository")
    if not isinstance(repository, dict):
        raise GovernanceError("repository must be an object", EXIT_INVALID_POLICY)

    for field in ("owner", "name", "defaultBranch"):
        value = repository.get(field)
        if not isinstance(value, str) or value.strip() == "":
            raise GovernanceError(f"repository.{field} must be a non-empty string", EXIT_INVALID_POLICY)

    rulesets = policy.get("rulesets", [])
    if not isinstance(rulesets, list):
        raise GovernanceError("rulesets must be a list", EXIT_INVALID_POLICY)

    normalized_rulesets: List[Dict[str, Any]] = []
    ruleset_names = set()
    for index, ruleset in enumerate(rulesets):
        if not isinstance(ruleset, dict):
            raise GovernanceError(f"rulesets[{index}] must be an object", EXIT_INVALID_POLICY)
        name = ruleset.get("name")
        if not isinstance(name, str) or not name.strip():
            raise GovernanceError(f"rulesets[{index}].name must be a non-empty string", EXIT_INVALID_POLICY)
        if name in ruleset_names:
            raise GovernanceError(f"Duplicate ruleset name: {name}", EXIT_INVALID_POLICY)
        ruleset_names.add(name)
        normalized_rulesets.append(normalize_ruleset(ruleset))

    required_checks = policy.get("requiredChecks", [])
    if not isinstance(required_checks, list):
        raise GovernanceError("requiredChecks must be a list", EXIT_INVALID_POLICY)

    normalized_checks = []
    seen_checks = set()
    for idx, check in enumerate(required_checks):
        if not isinstance(check, str) or not check.strip():
            raise GovernanceError(f"requiredChecks[{idx}] must be a non-empty string", EXIT_INVALID_POLICY)
        name = check.strip()
        if name in seen_checks:
            raise GovernanceError(f"requiredChecks contains duplicate entry: {name}", EXIT_INVALID_POLICY)
        seen_checks.add(name)
        normalized_checks.append(name)

    labels = policy.get("labels", [])
    if not isinstance(labels, list):
        raise GovernanceError("labels must be a list", EXIT_INVALID_POLICY)
    normalized_labels: List[Dict[str, Any]] = []
    seen_labels = set()
    for idx, label in enumerate(labels):
        if not isinstance(label, dict):
            raise GovernanceError(f"labels[{idx}] must be an object", EXIT_INVALID_POLICY)
        normalized = normalize_label(label)
        if normalized["name"] in seen_labels:
            raise GovernanceError(f"Duplicate label name: {normalized['name']}", EXIT_INVALID_POLICY)
        seen_labels.add(normalized["name"])
        normalized_labels.append(normalized)

    codeowners = policy.get("codeowners", {"path": DEFAULT_CODEOWNERS_PATH, "entries": []})
    if not isinstance(codeowners, dict):
        raise GovernanceError("codeowners must be an object", EXIT_INVALID_POLICY)

    path = codeowners.get("path", DEFAULT_CODEOWNERS_PATH)
    if not isinstance(path, str) or not path.strip():
        raise GovernanceError("codeowners.path must be a non-empty string", EXIT_INVALID_POLICY)

    entries = codeowners.get("entries", [])
    if not isinstance(entries, list):
        raise GovernanceError("codeowners.entries must be a list", EXIT_INVALID_POLICY)

    normalized_entries: List[Dict[str, Any]] = []
    seen_patterns = set()
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise GovernanceError(f"codeowners.entries[{idx}] must be an object", EXIT_INVALID_POLICY)
        pattern = entry.get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            raise GovernanceError(f"codeowners.entries[{idx}].pattern must be a non-empty string", EXIT_INVALID_POLICY)
        owners = entry.get("owners")
        if not isinstance(owners, list) or not owners:
            raise GovernanceError(f"codeowners.entries[{idx}].owners must be a non-empty list", EXIT_INVALID_POLICY)
        normalized_owners: List[str] = []
        for owner in owners:
            if not isinstance(owner, str) or not owner.strip():
                raise GovernanceError(f"codeowners.entries[{idx}] has empty owner", EXIT_INVALID_POLICY)
            token = owner.strip()
            if not (token.startswith("@") or "@" in token):
                raise GovernanceError(
                    f"codeowners.entries[{idx}] owner '{token}' must be @handle, @org/team, or email",
                    EXIT_INVALID_POLICY,
                )
            normalized_owners.append(token)
        if pattern in seen_patterns:
            raise GovernanceError(f"Duplicate CODEOWNERS pattern: {pattern}", EXIT_INVALID_POLICY)
        seen_patterns.add(pattern)
        normalized_entries.append({"pattern": pattern, "owners": sorted(set(normalized_owners))})

    options = default_options()
    user_options = policy.get("options", {})
    if not isinstance(user_options, dict):
        raise GovernanceError("options must be an object", EXIT_INVALID_POLICY)
    unknown_option_keys = sorted(set(user_options) - set(options))
    if unknown_option_keys:
        raise GovernanceError(f"Unknown options keys: {', '.join(unknown_option_keys)}", EXIT_INVALID_POLICY)

    for key, default in options.items():
        if key not in user_options:
            continue
        value = user_options[key]
        if isinstance(default, bool) and not isinstance(value, bool):
            raise GovernanceError(f"options.{key} must be boolean", EXIT_INVALID_POLICY)
        if isinstance(default, int) and not isinstance(value, int):
            raise GovernanceError(f"options.{key} must be integer", EXIT_INVALID_POLICY)
        if isinstance(default, str) and not isinstance(value, str):
            raise GovernanceError(f"options.{key} must be string", EXIT_INVALID_POLICY)
    options.update(user_options)

    bypass = policy.get("bypass", [])
    if not isinstance(bypass, list):
        raise GovernanceError("bypass must be a list", EXIT_INVALID_POLICY)
    normalized_bypass: List[Dict[str, Any]] = []
    for idx, entry in enumerate(bypass):
        if not isinstance(entry, dict):
            raise GovernanceError(f"bypass[{idx}] must be an object", EXIT_INVALID_POLICY)
        actor_type = entry.get("actor_type")
        actor_id = entry.get("actor_id")
        bypass_mode = entry.get("bypass_mode", "always")
        if actor_type not in {"OrganizationAdmin", "RepositoryRole", "Team", "Integration"}:
            raise GovernanceError(f"bypass[{idx}].actor_type is invalid", EXIT_INVALID_POLICY)
        if not isinstance(actor_id, int):
            raise GovernanceError(f"bypass[{idx}].actor_id must be integer", EXIT_INVALID_POLICY)
        if bypass_mode not in {"always", "pull_request"}:
            raise GovernanceError(f"bypass[{idx}].bypass_mode is invalid", EXIT_INVALID_POLICY)
        normalized_bypass.append(
            {
                "actor_type": actor_type,
                "actor_id": actor_id,
                "bypass_mode": bypass_mode,
            }
        )

    validated = {
        "schemaVersion": SCHEMA_VERSION,
        "repository": {
            "owner": repository["owner"].strip(),
            "name": repository["name"].strip(),
            "defaultBranch": repository["defaultBranch"].strip(),
        },
        "rulesets": sorted(normalized_rulesets, key=lambda r: r["name"]),
        "requiredChecks": sorted(normalized_checks),
        "codeowners": {
            "path": path.strip(),
            "entries": sorted(normalized_entries, key=lambda e: e["pattern"]),
        },
        "labels": sorted(normalized_labels, key=lambda l: l["name"]),
        "options": options,
        "bypass": sorted(normalized_bypass, key=lambda b: (b["actor_type"], b["actor_id"], b["bypass_mode"])),
    }
    return validated


def normalize_label(label: Dict[str, Any]) -> Dict[str, Any]:
    if "name" not in label:
        raise GovernanceError("label.name is required", EXIT_INVALID_POLICY)
    name = str(label["name"]).strip()
    if not name:
        raise GovernanceError("label.name must be non-empty", EXIT_INVALID_POLICY)

    color = str(label.get("color", "ededed")).strip().lstrip("#").lower()
    if len(color) != 6 or any(c not in "0123456789abcdef" for c in color):
        raise GovernanceError(f"Label '{name}' color must be a 6-digit hex value", EXIT_INVALID_POLICY)

    description = str(label.get("description", "")).strip()

    return {
        "name": name,
        "color": color,
        "description": description,
    }


def normalize_ruleset(ruleset: Dict[str, Any]) -> Dict[str, Any]:
    if "name" not in ruleset:
        raise GovernanceError("ruleset.name is required", EXIT_INVALID_POLICY)

    normalized = {
        "name": str(ruleset["name"]).strip(),
        "target": str(ruleset.get("target", "branch")),
        "enforcement": str(ruleset.get("enforcement", "active")),
        "conditions": canonicalize(ruleset.get("conditions", {})),
        "rules": normalize_rules(ruleset.get("rules", [])),
        "bypass_actors": sorted(
            [canonicalize(actor) for actor in ruleset.get("bypass_actors", [])],
            key=lambda a: (
                str(a.get("actor_type", "")),
                int(a.get("actor_id", -1)),
                str(a.get("bypass_mode", "")),
            ),
        ),
    }
    if not normalized["name"]:
        raise GovernanceError("ruleset.name must be non-empty", EXIT_INVALID_POLICY)
    return normalized


def normalize_rules(rules: Any) -> List[Dict[str, Any]]:
    if not isinstance(rules, list):
        raise GovernanceError("ruleset.rules must be a list", EXIT_INVALID_POLICY)

    normalized: List[Dict[str, Any]] = []
    for entry in rules:
        if not isinstance(entry, dict):
            raise GovernanceError("ruleset.rules entries must be objects", EXIT_INVALID_POLICY)
        r_type = entry.get("type")
        if not isinstance(r_type, str) or not r_type:
            raise GovernanceError("ruleset.rules[].type must be non-empty string", EXIT_INVALID_POLICY)
        params = canonicalize(entry.get("parameters", {}))

        if r_type == "required_status_checks":
            checks = params.get("required_status_checks", [])
            if checks and isinstance(checks, list):
                checks = sorted(
                    [canonicalize(check) for check in checks],
                    key=lambda c: str(c.get("context", "")),
                )
                params["required_status_checks"] = checks

        normalized.append({"type": r_type, "parameters": params})

    return sorted(normalized, key=lambda r: r["type"])


def extract_required_checks(ruleset: Dict[str, Any]) -> List[str]:
    checks: List[str] = []
    for rule in ruleset.get("rules", []):
        if rule.get("type") != "required_status_checks":
            continue
        params = rule.get("parameters", {})
        for check in params.get("required_status_checks", []):
            context = check.get("context")
            if isinstance(context, str) and context.strip():
                checks.append(context.strip())
    return checks


def desired_rulesets_from_policy(policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    custom = {ruleset["name"]: ruleset for ruleset in policy.get("rulesets", [])}

    managed_name = policy["options"]["managedRulesetName"]
    if managed_name in custom:
        managed = dict(custom[managed_name])
    else:
        managed = {
            "name": managed_name,
            "target": "branch",
            "enforcement": "active",
            "conditions": {
                "ref_name": {
                    "include": [f"refs/heads/{policy['repository']['defaultBranch']}"],
                    "exclude": [],
                }
            },
            "rules": [],
            "bypass_actors": [],
        }

    managed["bypass_actors"] = sorted(
        [canonicalize(actor) for actor in policy.get("bypass", [])],
        key=lambda a: (str(a.get("actor_type", "")), int(a.get("actor_id", -1)), str(a.get("bypass_mode", ""))),
    )

    managed = inject_review_rule(managed, policy)
    managed = inject_required_checks_rule(managed, policy["requiredChecks"])
    managed = inject_boolean_rules(managed, policy)

    custom[managed_name] = normalize_ruleset(managed)
    return sorted(custom.values(), key=lambda r: r["name"])


def inject_review_rule(ruleset: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    options = policy["options"]
    new_rules = [rule for rule in ruleset.get("rules", []) if rule.get("type") != "pull_request"]
    new_rules.append(
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": options["requiredApprovingReviewCount"],
                "dismiss_stale_reviews_on_push": options["dismissStaleReviews"],
                "require_code_owner_review": options["requireCodeOwnerReview"],
                "require_last_push_approval": options["requireLastPushApproval"],
                "required_review_thread_resolution": True,
            },
        }
    )
    ruleset["rules"] = new_rules
    return ruleset


def inject_required_checks_rule(ruleset: Dict[str, Any], checks: List[str]) -> Dict[str, Any]:
    filtered = [rule for rule in ruleset.get("rules", []) if rule.get("type") != "required_status_checks"]
    filtered.append(
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [
                    {"context": check, "integration_id": None} for check in sorted(set(checks))
                ],
            },
        }
    )
    ruleset["rules"] = filtered
    return ruleset


def inject_boolean_rules(ruleset: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    options = policy["options"]
    boolean_types = {
        "required_linear_history": options["requireLinearHistory"],
        "required_signatures": options["requireSignedCommits"],
        # If blockForcePushes=True, enforce the non_fast_forward rule.
        "non_fast_forward": options["blockForcePushes"],
    }
    existing = [rule for rule in ruleset.get("rules", []) if rule.get("type") not in boolean_types]
    for rule_type, enabled in boolean_types.items():
        if enabled:
            existing.append({"type": rule_type, "parameters": {}})
    ruleset["rules"] = existing
    return ruleset


def legacy_branch_protection_from_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    options = policy["options"]
    checks = sorted(set(policy["requiredChecks"]))
    return {
        "required_status_checks": {
            "strict": True,
            "checks": [{"context": check} for check in checks],
        },
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "required_approving_review_count": options["requiredApprovingReviewCount"],
            "dismiss_stale_reviews": options["dismissStaleReviews"],
            "require_code_owner_reviews": options["requireCodeOwnerReview"],
            "require_last_push_approval": options["requireLastPushApproval"],
        },
        "required_conversation_resolution": True,
        "restrictions": None,
        "allow_force_pushes": {"enabled": not options["blockForcePushes"]},
        "allow_deletions": {"enabled": False},
        "required_linear_history": {"enabled": options["requireLinearHistory"]},
    }


def normalize_legacy_branch_protection(payload: Dict[str, Any]) -> Dict[str, Any]:
    checks = payload.get("required_status_checks", {}).get("checks", [])
    normalized_checks = sorted(
        [{"context": c.get("context", "")} for c in checks if isinstance(c, dict) and c.get("context")],
        key=lambda c: c["context"],
    )
    return {
        "required_status_checks": {
            "strict": bool(payload.get("required_status_checks", {}).get("strict", False)),
            "checks": normalized_checks,
        },
        "enforce_admins": bool(payload.get("enforce_admins", False)),
        "required_pull_request_reviews": {
            "required_approving_review_count": int(
                payload.get("required_pull_request_reviews", {}).get("required_approving_review_count", 0)
            ),
            "dismiss_stale_reviews": bool(payload.get("required_pull_request_reviews", {}).get("dismiss_stale_reviews", False)),
            "require_code_owner_reviews": bool(
                payload.get("required_pull_request_reviews", {}).get("require_code_owner_reviews", False)
            ),
            "require_last_push_approval": bool(
                payload.get("required_pull_request_reviews", {}).get("require_last_push_approval", False)
            ),
        },
        "required_conversation_resolution": bool(payload.get("required_conversation_resolution", False)),
        "allow_force_pushes": {
            "enabled": bool(payload.get("allow_force_pushes", {}).get("enabled", False)),
        },
        "allow_deletions": {
            "enabled": bool(payload.get("allow_deletions", {}).get("enabled", False)),
        },
        "required_linear_history": {
            "enabled": bool(payload.get("required_linear_history", {}).get("enabled", False)),
        },
    }


def render_codeowners(entries: List[Dict[str, Any]]) -> str:
    lines = ["# Managed by repo-governance.py", ""]
    for entry in sorted(entries, key=lambda e: e["pattern"]):
        owner_text = " ".join(sorted(set(entry["owners"])))
        lines.append(f"{entry['pattern']} {owner_text}")
    return "\n".join(lines).rstrip()


def parse_codeowners_file(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    entries: List[Dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        entries.append({"pattern": parts[0], "owners": sorted(parts[1:])})

    seen = {}
    for entry in entries:
        seen[entry["pattern"]] = entry
    return sorted(seen.values(), key=lambda e: e["pattern"])


def load_policy(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise GovernanceError(f"Policy file not found: {path}", EXIT_INVALID_POLICY)
    except json.JSONDecodeError as exc:
        raise GovernanceError(f"Invalid JSON in policy file {path}: {exc}", EXIT_INVALID_POLICY)
    return validate_policy(data)


def print_markdown_audit(report: Dict[str, Any]) -> None:
    print(f"# Governance Audit: {report['repo']}")
    print("")
    if not report["drift"]:
        print("No drift detected.")
        return

    print(f"Detected {len(report['drift'])} drift item(s).")
    print("")
    for item in report["drift"]:
        print(f"- [{item['resourceType']}] `{item['resourceId']}` -> `{item['action']}`")


def cmd_validate(args: argparse.Namespace) -> int:
    load_policy(Path(args.policy))
    print("Policy valid")
    return EXIT_OK


def cmd_plan(args: argparse.Namespace, manager: GovernanceManager) -> int:
    policy = load_policy(Path(args.policy))
    report = manager.plan(policy, repo=args.repo)
    print(json.dumps(canonicalize(report), indent=2, sort_keys=True))
    return EXIT_DRIFT if report["hasDrift"] else EXIT_OK


def cmd_apply(args: argparse.Namespace, manager: GovernanceManager) -> int:
    policy = load_policy(Path(args.policy))
    result = manager.apply(policy, repo=args.repo, write_codeowners=args.write_codeowners)
    print(json.dumps(canonicalize(result), indent=2, sort_keys=True))
    return EXIT_OK


def cmd_audit(args: argparse.Namespace, manager: GovernanceManager) -> int:
    policy = load_policy(Path(args.policy))
    report = manager.audit(policy, repo=args.repo)
    if args.format == "json":
        print(json.dumps(canonicalize(report), indent=2, sort_keys=True))
    else:
        print_markdown_audit(report)
    return EXIT_DRIFT if report["hasDrift"] else EXIT_OK


def cmd_export(args: argparse.Namespace, manager: GovernanceManager) -> int:
    policy = manager.export(args.repo)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(canonicalize(policy), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Exported policy to {output_path}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic GitHub governance policy reconciliation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate governance policy schema and invariants.")
    validate.add_argument("--policy", default=DEFAULT_POLICY_PATH)

    plan = sub.add_parser("plan", help="Compute deterministic drift without mutating state.")
    plan.add_argument("--policy", default=DEFAULT_POLICY_PATH)
    plan.add_argument("--repo", default=None, help="owner/name override; defaults to policy.repository")

    apply = sub.add_parser("apply", help="Reconcile governance state to desired policy.")
    apply.add_argument("--policy", default=DEFAULT_POLICY_PATH)
    apply.add_argument("--repo", default=None, help="owner/name override; defaults to policy.repository")
    apply.add_argument(
        "--write-codeowners",
        action="store_true",
        help="Allow local .github/CODEOWNERS file mutation when drift exists.",
    )

    audit = sub.add_parser("audit", help="Report governance drift in json or markdown.")
    audit.add_argument("--policy", default=DEFAULT_POLICY_PATH)
    audit.add_argument("--repo", default=None, help="owner/name override; defaults to policy.repository")
    audit.add_argument("--format", choices=["json", "md"], default="json")

    export = sub.add_parser("export", help="Export current governance settings into policy file.")
    export.add_argument("--repo", required=True, help="owner/name")
    export.add_argument("--out", required=True)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    manager = GovernanceManager(client=GitHubClient())

    try:
        if args.command == "validate":
            return cmd_validate(args)
        if args.command == "plan":
            return cmd_plan(args, manager)
        if args.command == "apply":
            return cmd_apply(args, manager)
        if args.command == "audit":
            return cmd_audit(args, manager)
        if args.command == "export":
            return cmd_export(args, manager)
        raise GovernanceError(f"Unknown command: {args.command}", EXIT_INVALID_POLICY)
    except GovernanceError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
