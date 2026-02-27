#!/usr/bin/env sh
# rust-development skill — Phase 2 verification script.
#
# Usage:
#   verify.sh [--dir <path>]
#
# Runs all Phase 2 checks: banned-pattern scan, fmt, clippy, tests,
# complexity audit, and dependency count. Returns non-zero on any failure.
#
# Options:
#   --dir <path>   Workspace or crate root to check (default: current directory)
#
# Environment:
#   FILE_SIZE_THRESHOLD   Max lines before warning (default: 300)
#   ENTRYPOINT_THRESHOLD  Max entrypoint lines before warning (default: 100)
#   VERIFY_RUN_FMT        Run fmt gate in Phase 2.3 (default: true)
#   VERIFY_RUN_CLIPPY     Run clippy gate in Phase 2.3 (default: true)
#   VERIFY_RUN_TESTS      Run test gate in Phase 2.3 (default: true)
#
# Requires: rg (ripgrep). grep fallback is provided but limited.

set -eu

# Resolve script location so helper sourcing works regardless of cwd.
script_path="$0"
case "$script_path" in
  */*) : ;;
  *)
    resolved="$(command -v -- "$script_path" 2>/dev/null || true)"
    case "$resolved" in
      */*) script_path="$resolved" ;;
    esac
    ;;
esac

if command -v readlink >/dev/null 2>&1; then
  while [ -L "$script_path" ]; do
    link="$(readlink "$script_path" 2>/dev/null || true)"
    [ -n "$link" ] || break
    case "$link" in
      /*) script_path="$link" ;;
      *) script_path="$(dirname -- "$script_path")/$link" ;;
    esac
  done
fi

script_dir="$(CDPATH='' cd -- "$(dirname -- "$script_path")" && pwd)"
workspace_members_lib="${script_dir}/workspace-members.sh"
if [ ! -f "$workspace_members_lib" ]; then
  echo "error: helper library not found: $workspace_members_lib" >&2
  exit 1
fi
# shellcheck source=workspace-members.sh
. "$workspace_members_lib"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
target_dir="."
while [ $# -gt 0 ]; do
  case "$1" in
    --dir)
      shift
      if [ $# -eq 0 ]; then
        echo "error: --dir requires a path argument" >&2
        exit 2
      fi
      target_dir="$1"
      ;;
    -h|--help)
      sed -n '2,/^$/s/^# \{0,1\}//p' "$0"
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

cd "$target_dir"
echo "Scanning: $(pwd)"

FILE_SIZE_THRESHOLD="${FILE_SIZE_THRESHOLD:-300}"
ENTRYPOINT_THRESHOLD="${ENTRYPOINT_THRESHOLD:-100}"
VERIFY_RUN_FMT="${VERIFY_RUN_FMT:-true}"
VERIFY_RUN_CLIPPY="${VERIFY_RUN_CLIPPY:-true}"
VERIFY_RUN_TESTS="${VERIFY_RUN_TESTS:-true}"

_require_non_negative_int() {
  _name="$1"
  _value="$2"
  case "$_value" in
    ''|*[!0-9]*)
      echo "error: ${_name} must be a non-negative integer (got '${_value}')" >&2
      exit 2
      ;;
  esac
}

_require_non_negative_int "FILE_SIZE_THRESHOLD" "$FILE_SIZE_THRESHOLD"
_require_non_negative_int "ENTRYPOINT_THRESHOLD" "$ENTRYPOINT_THRESHOLD"

_require_bool_flag() {
  _name="$1"
  _value="$2"
  case "$_value" in
    true|false) ;;
    *)
      echo "error: ${_name} must be true|false (got '${_value}')" >&2
      exit 2
      ;;
  esac
}

_require_bool_flag "VERIFY_RUN_FMT" "$VERIFY_RUN_FMT"
_require_bool_flag "VERIFY_RUN_CLIPPY" "$VERIFY_RUN_CLIPPY"
_require_bool_flag "VERIFY_RUN_TESTS" "$VERIFY_RUN_TESTS"

# Counters are written to temp files so they survive subshells.
_fail_file="$(mktemp "${TMPDIR:-/tmp}/rust-verify-fail.XXXXXX")"
_warn_file="$(mktemp "${TMPDIR:-/tmp}/rust-verify-warn.XXXXXX")"
echo 0 > "$_fail_file"
echo 0 > "$_warn_file"
# Accumulate per-call temp files so _cleanup can remove them.
_tmp_files=""
_register_tmp() {
  if [ -z "$_tmp_files" ]; then
    _tmp_files="$1"
  else
    _tmp_files="$_tmp_files
$1"
  fi
}
# shellcheck disable=SC2329 # Invoked via trap on EXIT.
_cleanup() {
  rm -f "$_fail_file" "$_warn_file"
  if [ -n "$_tmp_files" ]; then
    printf '%s\n' "$_tmp_files" | while IFS= read -r _tmp; do
      [ -n "$_tmp" ] && rm -f -- "$_tmp"
    done
  fi
}
trap '_cleanup' EXIT

pass() { printf '  ✓ %s\n' "$1"; }
fail() {
  printf '  ✗ %s\n' "$1"
  n=$(cat "$_fail_file"); echo $((n + 1)) > "$_fail_file"
}
warn() {
  printf '  ⚠ %s\n' "$1"
  n=$(cat "$_warn_file"); echo $((n + 1)) > "$_warn_file"
}

add_warning_count_from_file() {
  count_file="$1"
  [ -f "$count_file" ] || return 0

  count=$(wc -l < "$count_file")
  n=$(cat "$_warn_file")
  echo $((n + count)) > "$_warn_file"
}

_has_candidate_rust_files() {
  skip_tests="${1:-}"
  skip_entry="${2:-}"
  set -- . -name '*.rs' -not -path '*/target/*'
  if [ "$skip_tests" = "exclude_tests" ]; then
    set -- "$@" \
      -not -path '*/test/*' \
      -not -path '*/tests/*' \
      -not -path '*/testdata/*' \
      -not -path '*/bench/*' \
      -not -path '*/benches/*' \
      -not -path '*/example/*' \
      -not -path '*/examples/*' \
      -not -path '*/fixture/*' \
      -not -path '*/fixtures/*' \
      -not -name '*_test.rs' \
      -not -name 'tests.rs'
  fi
  if [ "$skip_entry" = "exclude_entrypoints" ]; then
    set -- "$@" -not -path '*/src/main.rs' -not -path '*/src/bin/*'
  fi
  _first_match="$(find "$@" -print -quit)"
  [ -n "$_first_match" ]
}

# ---------------------------------------------------------------------------
# Search helper — uses rg when available, grep -rn -E otherwise.
# Arguments:
#   $1  regex pattern (ERE-compatible)
#   $2  extra filter description (human-readable, for context)
#   $3  label for pass/fail output
#   $4  (optional) "exclude_tests" to skip test-only files and directories
#   $5  (optional) "exclude_entrypoints" to skip main.rs / bin/*.rs
# ---------------------------------------------------------------------------
_search() {
  pattern="$1"
  _label="$3"
  skip_tests="${4:-}"
  skip_entry="${5:-}"

  if command -v rg >/dev/null 2>&1; then
    if ! _has_candidate_rust_files "$skip_tests" "$skip_entry"; then
      pass "$_label"
      return 0
    fi
    set -- --type rust
    if [ "$skip_tests" = "exclude_tests" ]; then
      set -- "$@" \
        -g '!**/test/**' \
        -g '!**/tests/**' \
        -g '!**/testdata/**' \
        -g '!**/bench/**' \
        -g '!**/benches/**' \
        -g '!**/example/**' \
        -g '!**/examples/**' \
        -g '!**/fixture/**' \
        -g '!**/fixtures/**' \
        -g '!**/*_test.rs' \
        -g '!**/tests.rs'
    fi
    if [ "$skip_entry" = "exclude_entrypoints" ]; then
      set -- "$@" -g '!**/src/main.rs' -g '!**/src/bin/*.rs'
    fi
    _rg_tmp="$(mktemp "${TMPDIR:-/tmp}/rust-verify-rg.XXXXXX")"
    _register_tmp "$_rg_tmp"
    if rg "$@" -- "$pattern" >"$_rg_tmp" 2>/dev/null; then
      _rg_status=0
    else
      _rg_status=$?
    fi
    if [ "$_rg_status" -gt 1 ]; then
      rm -f "$_rg_tmp"
      fail "$_label (search failed)"
      return 1
    fi
    _matches="$(sed -n '1,5p' "$_rg_tmp")"
    rm -f "$_rg_tmp"
    if [ -n "$_matches" ]; then
      printf '%s\n' "$_matches"
      fail "$_label"
      return 1
    fi
  else
    # grep -E fallback: build find + grep pipeline
    set -- . -name '*.rs' -not -path '*/target/*'
    if [ "$skip_tests" = "exclude_tests" ]; then
      set -- "$@" \
        -not -path '*/test/*' \
        -not -path '*/tests/*' \
        -not -path '*/testdata/*' \
        -not -path '*/bench/*' \
        -not -path '*/benches/*' \
        -not -path '*/example/*' \
        -not -path '*/examples/*' \
        -not -path '*/fixture/*' \
        -not -path '*/fixtures/*' \
        -not -name '*_test.rs' \
        -not -name 'tests.rs'
    fi
    if [ "$skip_entry" = "exclude_entrypoints" ]; then
      set -- "$@" -not -path '*/src/main.rs' -not -path '*/src/bin/*'
    fi
    _matches=$(find "$@" -exec grep -nE -- "$pattern" {} + 2>/dev/null | head -5)
    if [ -n "$_matches" ]; then
      printf '%s\n' "$_matches"
      fail "$_label"
      return 1
    fi
  fi
  pass "$_label"
  return 0
}

# Variant that pipes through an additional inverse-grep (for INVARIANT checks)
_search_excluding() {
  pattern="$1"
  exclude_pattern="$2"
  _label="$3"
  skip_tests="${4:-}"

  if command -v rg >/dev/null 2>&1; then
    if ! _has_candidate_rust_files "$skip_tests" ""; then
      pass "$_label"
      return 0
    fi
    set -- --type rust
    if [ "$skip_tests" = "exclude_tests" ]; then
      set -- "$@" \
        -g '!**/test/**' \
        -g '!**/tests/**' \
        -g '!**/testdata/**' \
        -g '!**/bench/**' \
        -g '!**/benches/**' \
        -g '!**/example/**' \
        -g '!**/examples/**' \
        -g '!**/fixture/**' \
        -g '!**/fixtures/**' \
        -g '!**/*_test.rs' \
        -g '!**/tests.rs'
    fi
    _rg_tmp="$(mktemp "${TMPDIR:-/tmp}/rust-verify-rg.XXXXXX")"
    _register_tmp "$_rg_tmp"
    _filtered_tmp="$(mktemp "${TMPDIR:-/tmp}/rust-verify-filtered.XXXXXX")"
    _register_tmp "$_filtered_tmp"
    if rg "$@" -- "$pattern" >"$_rg_tmp" 2>/dev/null; then
      _rg_status=0
    else
      _rg_status=$?
    fi
    if [ "$_rg_status" -gt 1 ]; then
      rm -f "$_rg_tmp" "$_filtered_tmp"
      fail "$_label (search failed)"
      return 1
    fi
    if grep -Ev "$exclude_pattern" "$_rg_tmp" >"$_filtered_tmp"; then
      :
    else
      _grep_status=$?
      if [ "$_grep_status" -gt 1 ]; then
        rm -f "$_rg_tmp" "$_filtered_tmp"
        fail "$_label (filter failed)"
        return 1
      fi
    fi
    _matches="$(sed -n '1,5p' "$_filtered_tmp")"
    rm -f "$_rg_tmp" "$_filtered_tmp"
    if [ -n "$_matches" ]; then
      printf '%s\n' "$_matches"
      fail "$_label"
      return 1
    fi
  else
    set -- . -name '*.rs' -not -path '*/target/*'
    if [ "$skip_tests" = "exclude_tests" ]; then
      set -- "$@" \
        -not -path '*/test/*' \
        -not -path '*/tests/*' \
        -not -path '*/testdata/*' \
        -not -path '*/bench/*' \
        -not -path '*/benches/*' \
        -not -path '*/example/*' \
        -not -path '*/examples/*' \
        -not -path '*/fixture/*' \
        -not -path '*/fixtures/*' \
        -not -name '*_test.rs' \
        -not -name 'tests.rs'
    fi
    _matches=$(find "$@" -exec grep -nE -- "$pattern" {} + 2>/dev/null \
       | grep -Ev "$exclude_pattern" | head -5)
    if [ -n "$_matches" ]; then
      printf '%s\n' "$_matches"
      fail "$_label"
      return 1
    fi
  fi
  pass "$_label"
  return 0
}

# Resolve git root for CI file detection.
git_root_dir=""
if command -v git >/dev/null 2>&1; then
  git_root_dir="$(git rev-parse --show-toplevel 2>/dev/null || true)"
fi

# ---------------------------------------------------------------------------
# Phase 2.0: Installation checks — verify skill artifacts are present
# ---------------------------------------------------------------------------
echo ""
echo "═══ Phase 2.0: Installation checks ═══"
echo ""

_install_ok=1

# Check 1: banned_family.rs test harness
_found_banned="$(find . -name 'banned_family.rs' -path '*/tests/*' -not -path '*/target/*' -print -quit 2>/dev/null || true)"
if [ -n "$_found_banned" ]; then
  pass "banned_family.rs installed: $_found_banned"
else
  warn "banned_family.rs not found (run scaffold.sh --banned-test)"
  _install_ok=0
fi

# Check 2: CI workflow
_ci_yml=""
_ci_script=""
if [ -f ".github/workflows/ci.yml" ]; then
  _ci_yml=".github/workflows/ci.yml"
elif [ -n "$git_root_dir" ] && [ -f "$git_root_dir/.github/workflows/ci.yml" ]; then
  _ci_yml="$git_root_dir/.github/workflows/ci.yml"
fi
if [ -f ".github/scripts/detect_rust_workspaces.py" ]; then
  _ci_script=".github/scripts/detect_rust_workspaces.py"
elif [ -n "$git_root_dir" ] && [ -f "$git_root_dir/.github/scripts/detect_rust_workspaces.py" ]; then
  _ci_script="$git_root_dir/.github/scripts/detect_rust_workspaces.py"
fi
if [ -n "$_ci_yml" ]; then
  pass "CI workflow installed: $_ci_yml"
else
  warn "CI workflow not found (run scaffold.sh --ci)"
  _install_ok=0
fi
if [ -n "$_ci_script" ]; then
  pass "CI detector script installed: $_ci_script"
else
  warn "CI detector script not found (run scaffold.sh --ci)"
  _install_ok=0
fi

# Check 3: Clippy lint config in Cargo.toml
_root_manifest="$(pwd)/Cargo.toml"
if [ -f "$_root_manifest" ]; then
  if grep -qE '^\[workspace\.lints|^\[lints' "$_root_manifest" 2>/dev/null; then
    pass "clippy lint config present in Cargo.toml"
  else
    warn "no [workspace.lints] or [lints] section in Cargo.toml (run scaffold.sh --clippy)"
    _install_ok=0
  fi
fi

# Check 4: [lints] workspace = true in member crates (workspace only)
if [ -f "$_root_manifest" ] && grep -qF '[workspace]' "$_root_manifest" 2>/dev/null; then
  _member_source=""
  _member_manifest_list=""
  _member_manifest_tmp="$(mktemp "${TMPDIR:-/tmp}/rust-verify-members.XXXXXX")"
  _register_tmp "$_member_manifest_tmp"
  if list_workspace_member_manifests "$_root_manifest" >"$_member_manifest_tmp"; then
    _member_source="$WORKSPACE_MEMBERS_LAST_SOURCE"
    _member_manifest_list="$(cat "$_member_manifest_tmp")"
  fi

  if [ -z "$_member_source" ]; then
    warn "unable to resolve workspace members for lint inheritance check"
    _install_ok=0
  elif [ -z "$_member_manifest_list" ]; then
    pass "workspace has no member crates requiring lint inheritance"
  else
    _members_missing_tmp="$(mktemp "${TMPDIR:-/tmp}/rust-verify-missing-members.XXXXXX")"
    _register_tmp "$_members_missing_tmp"
    while IFS= read -r _member_toml; do
      [ -n "$_member_toml" ] || continue
      [ -f "$_member_toml" ] || continue
      if ! grep -qF '[package]' "$_member_toml" 2>/dev/null; then
        continue
      fi
      if ! awk '
        BEGIN { in_lints = 0; ok = 0 }
        /^\[lints\]/ { in_lints = 1; next }
        /^\[/ { in_lints = 0 }
        in_lints && /^[[:space:]]*workspace[[:space:]]*=[[:space:]]*true([[:space:]]*(#.*)?)?$/ { ok = 1 }
        END { exit ok ? 0 : 1 }
      ' "$_member_toml" 2>/dev/null; then
        printf '%s\n' "$_member_toml" >> "$_members_missing_tmp"
      fi
    done <<MEMBER_MANIFEST_EOF
$_member_manifest_list
MEMBER_MANIFEST_EOF

    _members_missing_lints="$(tr '\n' ' ' < "$_members_missing_tmp" | sed 's/[[:space:]]\+$//')"
    if [ -z "$_members_missing_lints" ]; then
      pass "all member crates inherit workspace lints"
    else
      warn "member crates missing [lints] workspace = true:${_members_missing_lints}"
      _install_ok=0
    fi
  fi
fi

if [ "$_install_ok" -eq 0 ]; then
  echo ""
  echo "  hint: run scaffold.sh --all to install missing artifacts"
fi

echo ""
echo "═══ Phase 2.1: Banned pattern scan ═══"
echo ""
# ---------------------------------------------------------------------------

echo "Panic-inducing patterns:"
# NOTE: exclude_tests is path-based and excludes conventional test-only dirs.
# Keep banned_family.rs as the stricter parser-aware backstop for cfg(test) masking.
# unwrap family: .unwrap(), .unwrap_err(), .unwrap_unchecked() — but NOT .unwrap_or*()
_search_excluding '\.unwrap(_err|_unchecked)?[[:space:]]*\(' '// INVARIANT:' "no panic-inducing unwrap family" "exclude_tests" || true
# expect family: .expect(), .expect_err() — but NOT .expectation(...)
_search_excluding '\.expect(_err)?[[:space:]]*\(' '// INVARIANT:' "no panic-inducing expect family" "exclude_tests" || true
# panic macros
_search 'panic!\(' "" "no panic!()" "exclude_tests" || true
_search 'unimplemented!\(' "" "no unimplemented!()" "exclude_tests" || true
_search_excluding 'unreachable!\(' '// INVARIANT:' "no bare unreachable!()" "exclude_tests" || true
# assert macros outside tests (debug_assert is intentionally excluded)
_search_excluding '(^|[^[:alnum:]_])assert(_eq|_ne)?![[:space:]]*\(' '// INVARIANT:' "no assert macros outside tests" "exclude_tests" || true
# process exit
_search 'std::process::exit\(' "" "no exit() outside entrypoints" "exclude_tests" "exclude_entrypoints" || true

echo ""
echo "Placeholders:"
_search 'todo!\(' "" "no todo!()" "exclude_tests" || true

echo ""
echo "Non-idiomatic patterns:"
_search '\.map\(\|.*\|.*\.clone\(\)\)' "" "no .map(|x| x.clone())" || true
_search '\.map\(\|.*\|.*\.to_owned\(\)\)' "" "no .map(|x| x.to_owned())" || true
_search '\.iter\(\)\.count\(\)' "" "no .iter().count()" || true
_search_excluding '\.iter\(\)[[:space:]]*\.next\(\)' '// ALLOW: non-slice-next' "no disallowed .iter().next()" || true
# ERE-compatible: \s → [[:space:]], \w → [[:alnum:]_]
_search_excluding 'for[[:space:]]+[[:alnum:]_]+[[:space:]]+in[[:space:]]+0\.\..*\.len[[:space:]]*\(' '// ALLOW:' "no index loops" || true
_search '==[[:space:]]*true|==[[:space:]]*false|!=[[:space:]]*true|!=[[:space:]]*false' "" "no verbose bool comparisons" || true

echo ""
echo "Debug artifacts:"
_search 'dbg!\(' "" "no dbg!()" "exclude_tests" || true
_search 'println!\(' "" "no println!() outside entrypoints" "exclude_tests" "exclude_entrypoints" || true
_search 'eprintln!\(' "" "no eprintln!() outside entrypoints" "exclude_tests" "exclude_entrypoints" || true
_search 'static[[:space:]]+mut([[:space:]]|$)' "" "no static mut" "exclude_tests" || true

echo ""
echo "Import anti-patterns:"
_search '^[[:space:]]*use[[:space:]]+(crate|super)::\*;' "" "no glob crate/super imports" "exclude_tests" || true
_search_excluding '^[[:space:]]*use[[:space:]]+[^;]+::\*;' 'prelude' "no wildcard imports outside tests" "exclude_tests" || true

echo ""
echo "Parameter anti-patterns:"
_search 'fn.*\(&String' "" "no &String params" || true
_search 'fn.*\(&Vec<' "" "no &Vec<T> params" || true
_search 'fn.*\(&Box<' "" "no &Box<T> params" || true

echo ""
echo "Public API anti-patterns:"
_search 'pub[[:space:]]+fn.*->[[:space:]]*anyhow::Result' "" "no anyhow::Result in pub API" || true
_search 'pub[[:space:]]+fn.*->[[:space:]]*Result<.*,[[:space:]]*anyhow::Error' "" "no anyhow::Error in pub API" || true
_search 'pub[[:space:]]+fn.*->[[:space:]]*Result<.*,[[:space:]]*Box<dyn[[:space:]]+' "" "no Box<dyn Error> in pub API" || true

echo ""
echo "Security:"
_search 'Command::new\([[:space:]]*"(sh|bash|cmd)"[[:space:]]*\)' "" "no shell injection via Command" || true
_search 'unsafe[[:space:]]+impl[[:space:]]+(Send|Sync)' "" "no unsafe impl Send/Sync" "exclude_tests" || true

echo ""
echo "String allocation:"
_search 'String::from\(""\)' "" 'no String::from("")' || true
_search '"".to_string\(\)' "" 'no "".to_string()' || true

echo ""
echo "Resource safety:"
_search_excluding 'mem::forget\(' '// ALLOW:' "no mem::forget()" "exclude_tests" || true
_search_excluding 'Box::leak\(' '// ALLOW:' "no Box::leak()" "exclude_tests" || true
# Check unsafe blocks: // SAFETY: may be on the same line OR the preceding line
{
  _unsafe_label="no unsafe block without // SAFETY:"
  _unsafe_violations_tmp="$(mktemp "${TMPDIR:-/tmp}/rust-verify-unsafe.XXXXXX")"
  _register_tmp "$_unsafe_violations_tmp"
  _unsafe_files=""
  if command -v rg >/dev/null 2>&1; then
    _unsafe_files="$(rg -l --type rust \
      -g '!**/test/**' -g '!**/tests/**' -g '!**/testdata/**' \
      -g '!**/bench/**' -g '!**/benches/**' \
      -g '!**/example/**' -g '!**/examples/**' \
      -g '!**/fixture/**' -g '!**/fixtures/**' \
      -g '!**/*_test.rs' -g '!**/tests.rs' \
      -- 'unsafe[[:space:]]*\{' 2>/dev/null)" || true
  else
    _unsafe_files="$(find . -name '*.rs' -not -path '*/target/*' \
      -not -path '*/test/*' -not -path '*/tests/*' \
      -not -path '*/testdata/*' -not -path '*/bench/*' \
      -not -path '*/benches/*' -not -path '*/example/*' \
      -not -path '*/examples/*' -not -path '*/fixture/*' \
      -not -path '*/fixtures/*' -not -name '*_test.rs' \
      -not -name 'tests.rs' \
      -exec grep -lE 'unsafe[[:space:]]*\{' {} + 2>/dev/null)" || true
  fi
  if [ -n "$_unsafe_files" ]; then
    while IFS= read -r _unsafe_file; do
      [ -n "$_unsafe_file" ] || continue
      [ -f "$_unsafe_file" ] || continue
      awk '
        function make_raw_term(hash_count,    k, term) {
          term = "\""
          for (k = 1; k <= hash_count; k++) {
            term = term "#"
          }
          return term
        }
        function detect_raw_start(line, pos,    j) {
          j = pos + 1
          if (substr(line, pos, 1) == "b" && substr(line, pos + 1, 1) == "r") {
            j = pos + 2
          } else if (substr(line, pos, 1) != "r") {
            return 0
          }

          raw_hash_count = 0
          while (j <= length(line) && substr(line, j, 1) == "#") {
            raw_hash_count++
            j++
          }
          if (j <= length(line) && substr(line, j, 1) == "\"") {
            raw_term = make_raw_term(raw_hash_count)
            raw_term_len = length(raw_term)
            in_raw = 1
            return j - pos + 1
          }
          raw_hash_count = 0
          return 0
        }
        BEGIN {
          prev_is_safety_comment = 0
          in_block_comment = 0
          in_double = 0
          in_single = 0
          escaped = 0
          in_raw = 0
          raw_hash_count = 0
          raw_term = ""
          raw_term_len = 0
          _scan_code = ""
          _scan_comment = ""
        }
        {
          line = $0
          _scan_code = ""
          _scan_comment = ""
          i = 1
          while (i <= length(line)) {
            c = substr(line, i, 1)
            nextc = (i < length(line) ? substr(line, i + 1, 1) : "")

            if (in_block_comment > 0) {
              if (c == "/" && nextc == "*") {
                in_block_comment++
                i += 2
                continue
              }
              if (c == "*" && nextc == "/") {
                in_block_comment--
                i += 2
                continue
              }
              i++
              continue
            }

            if (in_raw) {
              if (substr(line, i, raw_term_len) == raw_term) {
                close_len = raw_term_len
                in_raw = 0
                raw_hash_count = 0
                raw_term = ""
                raw_term_len = 0
                i += close_len
                continue
              }
              i++
              continue
            }

            if (in_double) {
              if (escaped) {
                escaped = 0
                i++
                continue
              }
              if (c == "\\") {
                escaped = 1
                i++
                continue
              }
              if (c == "\"") {
                in_double = 0
              }
              i++
              continue
            }

            if (in_single) {
              if (escaped) {
                escaped = 0
                i++
                continue
              }
              if (c == "\\") {
                escaped = 1
                i++
                continue
              }
              if (c == "'\''") {
                in_single = 0
              }
              i++
              continue
            }

            raw_consumed = 0
            if (c == "r" || c == "b") {
              raw_consumed = detect_raw_start(line, i)
              if (raw_consumed > 0) {
                i += raw_consumed
                continue
              }
            }

            if (c == "/" && nextc == "/") {
              _scan_comment = substr(line, i)
              break
            }
            if (c == "/" && nextc == "*") {
              in_block_comment = 1
              i += 2
              continue
            }
            if (c == "\"") {
              in_double = 1
              i++
              continue
            }
            if (c == "'\''") {
              in_single = 1
              i++
              continue
            }

            _scan_code = _scan_code c
            i++
          }

          cur_has_inline_safety = (_scan_comment ~ /^\/\/[[:space:]]*SAFETY:/)
          cur_is_safety_comment = (_scan_code ~ /^[[:space:]]*$/) && (_scan_comment ~ /^\/\/[[:space:]]*SAFETY:/)
          if (_scan_code ~ /unsafe[[:space:]]*\{/) {
            if (!(cur_has_inline_safety || prev_is_safety_comment)) {
              printf "%s:%d:%s\n", FILENAME, NR, line
            }
          }
          prev_is_safety_comment = cur_is_safety_comment
        }
      ' "$_unsafe_file" >> "$_unsafe_violations_tmp"
    done <<UNSAFE_FILES_EOF
$_unsafe_files
UNSAFE_FILES_EOF
  fi
  _unsafe_violations="$(sed -n '1,5p' "$_unsafe_violations_tmp")"
  if [ -n "$_unsafe_violations" ]; then
    printf '%s\n' "$_unsafe_violations"
    fail "$_unsafe_label"
  else
    pass "$_unsafe_label"
  fi
} || true

echo ""
echo "Idiomatic checks:"
_search '\.len\(\)[[:space:]]*(==|!=)[[:space:]]*0' "" "use .is_empty() instead of .len() == 0" || true
_search 'format![[:space:]]*\([[:space:]]*"\{\}"[[:space:]]*,[[:space:]]*' "" "use .to_string() or variable directly instead of format!(\"{}\", x)" || true
_search_excluding '#\[allow\(' '// Reason:' "no #[allow] without justification" "exclude_tests" || true

echo ""
echo "Meta:"
if command -v rg >/dev/null 2>&1; then
  if rg 'TODO' --type rust 2>/dev/null | rg -v '#[0-9]+' | rg -v 'https\?://' | head -5 | grep -q .; then
    fail "orphan TODOs found"
  else
    pass "no orphan TODOs"
  fi
  if rg '#\[allow\(' --type rust 2>/dev/null | rg -v '// Reason:' | head -5 | grep -q .; then
    fail "unjustified #[allow] found"
  else
    pass "all #[allow] justified"
  fi
else
  if find . -name '*.rs' -not -path '*/target/*' -exec grep -nE 'TODO' {} + 2>/dev/null \
     | grep -vE '#[0-9]+' | grep -v 'http' | head -5 | grep -q .; then
    fail "orphan TODOs found"
  else
    pass "no orphan TODOs"
  fi
  if find . -name '*.rs' -not -path '*/target/*' -exec grep -nE '#\[allow\(' {} + 2>/dev/null \
     | grep -v '// Reason:' | head -5 | grep -q .; then
    fail "unjustified #[allow] found"
  else
    pass "all #[allow] justified"
  fi
fi

# ---------------------------------------------------------------------------
echo ""
echo "═══ Phase 2.2: Complexity check ═══"
echo ""
# ---------------------------------------------------------------------------

echo "Large files (threshold: ${FILE_SIZE_THRESHOLD} lines):"
# Exclude generated banned_family harness; it is intentionally large and portable.
find . -name '*.rs' -not -path '*/target/*' -exec sh -c '
  threshold="$1"
  warn_file="$2"
  shift 2
  for f do
    case "$f" in
      */tests/banned_family.rs|./tests/banned_family.rs)
        # Generated harness is intentionally verbose for portability.
        continue
        ;;
    esac
    count=$(wc -l < "$f")
    if [ "$count" -gt "$threshold" ]; then
      printf "  ⚠ %s: %s lines\n" "$f" "$count"
      echo 1 >> "$warn_file"
    fi
  done
' sh "$FILE_SIZE_THRESHOLD" "$_warn_file.large" {} +
if [ -f "$_warn_file.large" ]; then
  add_warning_count_from_file "$_warn_file.large"
  rm -f "$_warn_file.large"
else
  pass "no notably large files"
fi

echo ""
echo "Binary entrypoints (threshold: ${ENTRYPOINT_THRESHOLD} lines):"
find . \( -path '*/src/main.rs' -o -path '*/src/bin/*.rs' \) -not -path '*/target/*' -exec sh -c '
  threshold="$1"
  warn_file="$2"
  shift 2
  for f do
    lines=$(wc -l < "$f")
    if [ "$lines" -gt "$threshold" ]; then
      printf "  ⚠ %s has %s lines — consider extracting logic\n" "$f" "$lines"
      echo 1 >> "$warn_file"
    fi
  done
' sh "$ENTRYPOINT_THRESHOLD" "$_warn_file.entry" {} +
if [ -f "$_warn_file.entry" ]; then
  add_warning_count_from_file "$_warn_file.entry"
  rm -f "$_warn_file.entry"
else
  pass "entrypoints are thin"
fi

# ---------------------------------------------------------------------------
echo ""
echo "═══ Phase 2.3: Build, lint, and test ═══"
echo ""
# ---------------------------------------------------------------------------

echo "Format check:"
if [ "$VERIFY_RUN_FMT" = "true" ]; then
  if command -v rustfmt >/dev/null 2>&1; then
    if cargo fmt --all --check 2>&1; then
      pass "cargo fmt --all --check"
    else
      fail "cargo fmt --all --check"
    fi
  else
    fail "rustfmt not installed (rustup component add rustfmt)"
  fi
else
  pass "cargo fmt --all --check (skipped: VERIFY_RUN_FMT=false)"
fi

echo ""
echo "Clippy:"
if [ "$VERIFY_RUN_CLIPPY" = "true" ]; then
  if cargo clippy --version >/dev/null 2>&1; then
    if cargo clippy --workspace --all-targets -- -D warnings 2>&1; then
      pass "cargo clippy --workspace --all-targets -- -D warnings"
    else
      fail "cargo clippy --workspace --all-targets -- -D warnings"
    fi
  else
    fail "clippy not installed (rustup component add clippy)"
  fi
else
  pass "cargo clippy --workspace --all-targets -- -D warnings (skipped: VERIFY_RUN_CLIPPY=false)"
fi

echo ""
echo "Tests:"
if [ "$VERIFY_RUN_TESTS" = "true" ]; then
  if cargo test --workspace 2>&1; then
    pass "cargo test --workspace"
  else
    fail "cargo test --workspace"
  fi
else
  pass "cargo test --workspace (skipped: VERIFY_RUN_TESTS=false)"
fi

echo ""
echo "Dependency audit:"
if cargo tree --version >/dev/null 2>&1; then
  echo "  Duplicate dependencies:"
  cargo tree -d 2>/dev/null || true
  dep_count=$(cargo tree --depth 1 2>/dev/null | wc -l)
  echo "  Direct dependencies: $dep_count"
else
  warn "cargo-tree not installed"
fi

# ---------------------------------------------------------------------------
echo ""
echo "═══ Summary ═══"
echo ""
# ---------------------------------------------------------------------------

failures=$(cat "$_fail_file")
warnings=$(cat "$_warn_file")

if [ "$failures" -gt 0 ]; then
  echo "FAILED: $failures failure(s), $warnings warning(s)"
  exit 1
elif [ "$warnings" -gt 0 ]; then
  echo "PASSED with $warnings warning(s)"
  exit 0
else
  echo "ALL CHECKS PASSED"
  exit 0
fi
