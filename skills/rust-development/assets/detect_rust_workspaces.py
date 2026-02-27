#!/usr/bin/env python3
"""Detect Rust workspaces/crates and emit a CI matrix for GitHub Actions."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

repo = Path(".").resolve()
default_excluded_dirs = {
    ".git",
    ".github",
    ".local",
    "target",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "out",
    "tests",
    "test",
    "testdata",
    "fixtures",
    "fixture",
    "examples",
    "benches",
}
exclude_mode = os.environ.get("CI_MANIFEST_EXCLUDE_MODE", "append").strip().lower()
if exclude_mode not in {"append", "replace"}:
    print(
        (
            f"Unknown CI_MANIFEST_EXCLUDE_MODE='{exclude_mode}' "
            "(expected append|replace); treating as append"
        ),
        file=sys.stderr,
    )
    exclude_mode = "append"
excluded_raw = os.environ.get("CI_MANIFEST_EXCLUDE_DIRS", "").strip()
user_excluded_dirs = set()
if excluded_raw:
    user_excluded_dirs = {
        item.strip().replace("\\", "/")
        for item in excluded_raw.split(",")
        if item.strip()
    }

if exclude_mode == "replace":
    excluded_dirs = user_excluded_dirs
else:
    excluded_dirs = default_excluded_dirs | user_excluded_dirs


def _is_excluded_manifest(manifest_path: Path) -> bool:
    try:
        rel_dir = manifest_path.parent.relative_to(repo)
    except ValueError:
        return True
    rel_dir_posix = rel_dir.as_posix()
    for pattern in excluded_dirs:
        normalized = pattern.strip("/").replace("\\", "/")
        if not normalized:
            continue
        if "/" in normalized:
            if rel_dir_posix == normalized or rel_dir_posix.startswith(f"{normalized}/"):
                return True
            continue
        if normalized in rel_dir.parts:
            return True
    return False


all_manifests = sorted(repo.rglob("Cargo.toml"))
ws_re = re.compile(r"^\s*\[\s*workspace\s*\]", re.MULTILINE)
workspace_manifests = []
for manifest in all_manifests:
    try:
        txt = manifest.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(
            f"warning: skipping unreadable manifest {manifest}: {exc}",
            file=sys.stderr,
        )
        continue
    if ws_re.search(txt):
        workspace_manifests.append(manifest)

workspace_manifest_set = {manifest.resolve() for manifest in workspace_manifests}
manifests = [
    manifest
    for manifest in all_manifests
    if manifest.resolve() in workspace_manifest_set or not _is_excluded_manifest(manifest)
]

github_output = os.environ.get("GITHUB_OUTPUT")
if not github_output:
    # When running outside CI (e.g. local testing), print the matrix to stdout
    # instead of failing.  Set GITHUB_OUTPUT to a file path to capture output.
    print("GITHUB_OUTPUT is not set — printing matrix to stdout", file=sys.stderr)
    github_output = None  # sentinel: write to stdout later

if not manifests:
    _no_rust = "has_rust=false\nmatrix={\"include\":[]}\n"
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(_no_rust)
    else:
        sys.stdout.write(_no_rust)
    raise SystemExit(0)

mode = os.environ.get("CI_USE_CARGO_METADATA", "auto").strip().lower()
if mode not in {"auto", "true", "false"}:
    print(
        f"Unknown CI_USE_CARGO_METADATA='{mode}' (expected auto|true|false); treating as auto",
        file=sys.stderr,
    )
    mode = "auto"

cargo_available = shutil.which("cargo") is not None
use_cargo_metadata = mode in {"auto", "true"} and cargo_available
if mode == "true" and not cargo_available:
    print(
        "CI_USE_CARGO_METADATA=true but cargo not found; falling back to manifest parsing",
        file=sys.stderr,
    )

metadata_timeout_raw = os.environ.get("CI_CARGO_METADATA_TIMEOUT_SECONDS", "20").strip()
try:
    metadata_timeout_seconds = max(1, int(metadata_timeout_raw))
except ValueError:
    print(
        (
            f"Invalid CI_CARGO_METADATA_TIMEOUT_SECONDS='{metadata_timeout_raw}', "
            "defaulting to 20"
        ),
        file=sys.stderr,
    )
    metadata_timeout_seconds = 20

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - best-effort fallback
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        tomllib = None  # type: ignore

workspace_roots = sorted({manifest.parent for manifest in workspace_manifests})


def _dir_str(path: Path) -> str:
    try:
        rel = path.relative_to(repo)
    except ValueError:
        return str(path)
    rel_str = str(rel)
    return "." if rel_str in {"", "."} else rel_str


def _validate_matrix_dir(dir_str: str) -> None:
    # NOTE: Validates paths derived from pathlib traversal (_dir_str output),
    # not arbitrary external user-provided strings.
    if dir_str == ".":
        return
    normalized = dir_str.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("../"):
        raise SystemExit(
            f"Unsafe matrix directory '{dir_str}': expected a relative repository path"
        )
    if "/../" in normalized or normalized.endswith("/.."):
        raise SystemExit(f"Unsafe matrix directory '{dir_str}': parent traversal is forbidden")
    segments = normalized.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise SystemExit(f"Unsafe matrix directory '{dir_str}': invalid path segment")
    for ch in dir_str:
        code = ord(ch)
        if code < 32 or code == 127:
            raise SystemExit(
                f"Unsafe matrix directory '{dir_str}': control characters are forbidden"
            )


def _add_include(path: Path, is_workspace: bool, include: list, included_dirs: set) -> None:
    dir_str = _dir_str(path)
    _validate_matrix_dir(dir_str)
    if dir_str in included_dirs:
        return
    include.append({"dir": dir_str, "is_workspace": is_workspace})
    included_dirs.add(dir_str)


def _normalize_patterns(raw):
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    out = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip().replace("\\", "/"))
    return out


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _literal_prefix_for_anchor(pattern: str) -> str:
    """Return the literal path prefix before any glob meta characters."""
    prefix = []
    escape = False
    for ch in pattern:
        if escape:
            prefix.append(ch)
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch in {"*", "?", "["}:
            break
        prefix.append(ch)
    return "".join(prefix)


def _matches_any(rel: str, patterns) -> bool:
    rel_norm = rel.replace("\\", "/")
    rel_path = Path(rel_norm if rel_norm else ".")
    for pat in patterns:
        pat_norm = pat.replace("\\", "/").strip()
        if not pat_norm:
            continue
        if pat_norm in {".", "./"}:
            if rel_norm in {"", ".", "./"}:
                return True
            continue
        while pat_norm.startswith("./"):
            pat_norm = pat_norm[2:]
        literal_prefix = _literal_prefix_for_anchor(pat_norm).lstrip("/")
        if literal_prefix:
            anchored_prefix = literal_prefix.rstrip("/")
            if not (
                rel_norm == anchored_prefix or rel_norm.startswith(f"{anchored_prefix}/")
            ):
                continue
        try:
            if rel_path.match(pat_norm):
                return True
        except ValueError:
            continue
    return False


def _cargo_metadata(manifest_path: Path):
    if not use_cargo_metadata:
        return None
    try:
        proc = subprocess.run(
            [
                "cargo",
                "metadata",
                "--format-version",
                "1",
                "--no-deps",
                "--manifest-path",
                str(manifest_path),
            ],
            text=True,
            capture_output=True,
            timeout=metadata_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        print(
            (
                f"cargo metadata timed out after {metadata_timeout_seconds}s for "
                f"{manifest_path}"
            ),
            file=sys.stderr,
        )
        return None
    except Exception as exc:
        print(f"cargo metadata failed for {manifest_path}: {exc}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        err = proc.stderr.strip()
        msg = f"cargo metadata failed for {manifest_path}"
        if err:
            msg = f"{msg}: {err}"
        print(msg, file=sys.stderr)
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"cargo metadata output was not valid JSON for {manifest_path}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        return None
    packages = data.get("packages")
    workspace_members = data.get("workspace_members")
    workspace_root = data.get("workspace_root")
    if not isinstance(packages, list) or not isinstance(workspace_members, list):
        return None
    if not isinstance(workspace_root, str):
        return None
    member_ids = {member for member in workspace_members if isinstance(member, str)}
    member_manifests = set()
    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        if pkg.get("id") not in member_ids:
            continue
        package_manifest_path = pkg.get("manifest_path")
        if isinstance(package_manifest_path, str):
            member_manifests.add(Path(package_manifest_path).resolve())
    return {"root": Path(workspace_root).resolve(), "members": member_manifests}


include = []
included_dirs = set()

if not workspace_roots:
    roots = sorted({manifest.parent for manifest in manifests})
    for root in roots:
        _add_include(root, False, include, included_dirs)
else:
    workspaces = []
    for root in workspace_roots:
        members = []
        exclude = []
        member_manifests = None

        metadata = _cargo_metadata(root / "Cargo.toml")
        if metadata is not None:
            member_manifests = metadata["members"]

        if member_manifests is None and tomllib is not None:
            try:
                with open(root / "Cargo.toml", "rb") as f:
                    data = tomllib.load(f)
                ws = data.get("workspace", {}) if isinstance(data, dict) else {}
                members = _normalize_patterns(ws.get("members"))
                exclude = _normalize_patterns(ws.get("exclude"))
            except Exception:
                pass

        workspaces.append(
            {
                "root": root,
                "members": members,
                "exclude": exclude,
                "member_manifests": member_manifests,
            }
        )

        _add_include(root, True, include, included_dirs)

    for manifest in manifests:
        manifest_resolved = manifest.resolve()
        if manifest_resolved in workspace_manifest_set:
            continue

        is_member = False
        for ws in workspaces:
            member_set = ws["member_manifests"]
            if member_set is not None:
                if manifest_resolved in member_set:
                    is_member = True
                    break
                continue

            if not _is_under(manifest.parent, ws["root"]):
                continue
            rel = manifest.parent.relative_to(ws["root"]).as_posix()
            if rel == ".":
                rel = ""
            if ws["members"] and _matches_any(rel, ws["members"]):
                if not _matches_any(rel, ws["exclude"]):
                    is_member = True
                    break

        if not is_member:
            _add_include(manifest.parent, False, include, included_dirs)

matrix = {"include": include}

max_entries_raw = os.environ.get("CI_MAX_MATRIX_ENTRIES", "128").strip()
try:
    max_entries = int(max_entries_raw)
except ValueError:
    print(
        f"Invalid CI_MAX_MATRIX_ENTRIES='{max_entries_raw}', defaulting to 128",
        file=sys.stderr,
    )
    max_entries = 128
if max_entries < 1:
    max_entries = 128
if len(include) > max_entries:
    print(
        (
            f"Detected {len(include)} Rust targets, exceeding "
            f"CI_MAX_MATRIX_ENTRIES={max_entries}. "
            "Set CI_MANIFEST_EXCLUDE_DIRS or CI_MAX_MATRIX_ENTRIES "
            "to tune detection."
        ),
        file=sys.stderr,
    )
    raise SystemExit(1)

_output = f"has_rust={'true' if include else 'false'}\nmatrix={json.dumps(matrix, separators=(',', ':'))}\n"
if github_output:
    with open(github_output, "a", encoding="utf-8") as f:
        f.write(_output)
else:
    sys.stdout.write(_output)
