#!/usr/bin/env sh
# Shared workspace member manifest helpers for rust-development scripts.

WORKSPACE_MEMBERS_LAST_SOURCE=""

_workspace_members_debug_enabled() {
  case "${RUST_WORKSPACE_MEMBERS_DEBUG:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

_workspace_members_prefix_stderr() {
  _label="$1"
  _err_file="$2"
  [ -s "$_err_file" ] || return 0
  while IFS= read -r _line; do
    [ -n "$_line" ] || continue
    printf 'workspace-members (%s): %s\n' "$_label" "$_line" >&2
  done < "$_err_file"
}

list_workspace_member_manifests_from_metadata() {
  root_manifest="$1"
  command -v cargo >/dev/null 2>&1 || return 1
  command -v python3 >/dev/null 2>&1 || return 1

  _metadata_tmp="$(mktemp "${TMPDIR:-/tmp}/rust-workspace-metadata.XXXXXX")"
  if ! cargo metadata --format-version 1 --no-deps --manifest-path "$root_manifest" >"$_metadata_tmp" 2>/dev/null; then
    rm -f -- "$_metadata_tmp"
    return 1
  fi

  if ! python3 - "$root_manifest" "$_metadata_tmp" <<'PY'
import json
import sys
from pathlib import Path

root_manifest = Path(sys.argv[1]).resolve()
workspace_root = root_manifest.parent
metadata_path = Path(sys.argv[2])

try:
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
except OSError as exc:
    print(f"failed to read metadata file {metadata_path}: {exc}", file=sys.stderr)
    sys.exit(1)
except json.JSONDecodeError as exc:
    print(f"failed to parse metadata JSON {metadata_path}: {exc}", file=sys.stderr)
    sys.exit(1)

workspace_members = payload.get("workspace_members")
packages = payload.get("packages")
if not isinstance(workspace_members, list) or not isinstance(packages, list):
    print("metadata JSON missing workspace_members/packages arrays", file=sys.stderr)
    sys.exit(1)

member_ids = {value for value in workspace_members if isinstance(value, str)}
member_paths = set()
for pkg in packages:
    if not isinstance(pkg, dict):
        continue
    if pkg.get("id") not in member_ids:
        continue
    manifest_path = pkg.get("manifest_path")
    if not isinstance(manifest_path, str):
        continue
    candidate = Path(manifest_path).resolve()
    if candidate == root_manifest:
        continue
    try:
        candidate.relative_to(workspace_root)
    except ValueError:
        # Reject manifests that resolve outside the workspace root.
        continue
    member_paths.add(str(candidate))

for manifest_path in sorted(member_paths):
    print(manifest_path)
PY
  then
    rm -f -- "$_metadata_tmp"
    return 1
  fi

  rm -f -- "$_metadata_tmp"
}

list_workspace_member_manifests_from_manifest() {
  root_manifest="$1"
  command -v python3 >/dev/null 2>&1 || return 1

  python3 - "$root_manifest" <<'PY'
import fnmatch
import sys
from pathlib import Path

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[assignment]
    except ModuleNotFoundError:
        sys.exit(1)

root_manifest = Path(sys.argv[1]).resolve()
workspace_root = root_manifest.parent

try:
    data = tomllib.loads(root_manifest.read_text(encoding="utf-8"))
except OSError as exc:
    print(f"failed to read workspace manifest {root_manifest}: {exc}", file=sys.stderr)
    sys.exit(1)
except tomllib.TOMLDecodeError as exc:
    print(f"failed to parse TOML in {root_manifest}: {exc}", file=sys.stderr)
    sys.exit(1)

workspace = data.get("workspace") if isinstance(data, dict) else None
if not isinstance(workspace, dict):
    print(f"{root_manifest} has no [workspace] table", file=sys.stderr)
    sys.exit(1)

raw_members = workspace.get("members")
if raw_members is None:
    # [workspace] without explicit members is valid; treat as no member manifests.
    sys.exit(0)
if isinstance(raw_members, str):
    raw_members = [raw_members]
if not isinstance(raw_members, list):
    print(f"{root_manifest} has invalid [workspace].members", file=sys.stderr)
    sys.exit(1)
members = []
for value in raw_members:
    if not isinstance(value, str):
        print(f"{root_manifest} has non-string [workspace].members entry", file=sys.stderr)
        sys.exit(1)
    normalized = value.strip().replace("\\", "/")
    if normalized:
        members.append(normalized)
if not members:
    # Empty members list is valid and means no additional member manifests.
    sys.exit(0)

raw_exclude = workspace.get("exclude")
if isinstance(raw_exclude, str):
    raw_exclude = [raw_exclude]
exclude = []
if isinstance(raw_exclude, list):
    exclude = [value.strip().replace("\\", "/") for value in raw_exclude if isinstance(value, str) and value.strip()]

def _matches_any(rel_path: str, patterns):
    rel_norm = rel_path.replace("\\", "/")
    for pattern in patterns:
        normalized = pattern.replace("\\", "/").strip()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if not normalized:
            continue
        if fnmatch.fnmatch(rel_norm, normalized):
            return True
    return False

manifests = set()
for pattern in members:
    normalized = pattern
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        continue

    has_glob = any(ch in normalized for ch in "*?[")
    matched_any = False
    for candidate in workspace_root.glob(normalized):
        matched_any = True
        manifest_path = candidate if candidate.name == "Cargo.toml" else candidate / "Cargo.toml"
        if manifest_path.is_file():
            manifests.add(manifest_path.resolve())

    if not has_glob and not matched_any:
        manifest_path = workspace_root / normalized / "Cargo.toml"
        if manifest_path.is_file():
            manifests.add(manifest_path.resolve())

filtered = []
for manifest_path in sorted(manifests):
    if manifest_path == root_manifest:
        continue
    try:
        rel = manifest_path.parent.relative_to(workspace_root).as_posix()
    except ValueError:
        continue
    if exclude and _matches_any(rel, exclude):
        continue
    filtered.append(manifest_path)

for manifest_path in filtered:
    print(manifest_path)
PY
}

list_workspace_member_manifests() {
  root_manifest="$1"
  WORKSPACE_MEMBERS_LAST_SOURCE=""

  _metadata_out="$(mktemp "${TMPDIR:-/tmp}/workspace-members.meta.out.XXXXXX")"
  _metadata_err="$(mktemp "${TMPDIR:-/tmp}/workspace-members.meta.err.XXXXXX")"
  _manifest_out="$(mktemp "${TMPDIR:-/tmp}/workspace-members.manifest.out.XXXXXX")"
  _manifest_err="$(mktemp "${TMPDIR:-/tmp}/workspace-members.manifest.err.XXXXXX")"

  if list_workspace_member_manifests_from_metadata "$root_manifest" >"$_metadata_out" 2>"$_metadata_err"; then
    WORKSPACE_MEMBERS_LAST_SOURCE="cargo metadata"
    cat "$_metadata_out"
    rm -f -- "$_metadata_out" "$_metadata_err" "$_manifest_out" "$_manifest_err"
    return 0
  fi

  if list_workspace_member_manifests_from_manifest "$root_manifest" >"$_manifest_out" 2>"$_manifest_err"; then
    WORKSPACE_MEMBERS_LAST_SOURCE="workspace.members"
    if _workspace_members_debug_enabled; then
      _workspace_members_prefix_stderr "cargo metadata fallback" "$_metadata_err"
    fi
    cat "$_manifest_out"
    rm -f -- "$_metadata_out" "$_metadata_err" "$_manifest_out" "$_manifest_err"
    return 0
  fi

  _workspace_members_prefix_stderr "cargo metadata" "$_metadata_err"
  _workspace_members_prefix_stderr "workspace.members" "$_manifest_err"
  if [ ! -s "$_metadata_err" ] && [ ! -s "$_manifest_err" ]; then
    printf 'workspace-members: unable to resolve members for %s\n' "$root_manifest" >&2
  fi
  rm -f -- "$_metadata_out" "$_metadata_err" "$_manifest_out" "$_manifest_err"
  return 1
}
