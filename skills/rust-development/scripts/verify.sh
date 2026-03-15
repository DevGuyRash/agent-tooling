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
# Optional tooling: `python3` enables full parser-aware banned-family scans;
# `rg` and `git` improve ignore-aware Rust file discovery. Fallbacks are
# provided when they are unavailable.

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

_banned_family_supports_assert_macros() {
  _harness_path="$1"
  [ -f "$_harness_path" ] || return 1
  grep -qF '("assert_eq", MatchKind::MacroOnly),' "$_harness_path" &&
    grep -qF '("assert_ne", MatchKind::MacroOnly),' "$_harness_path" &&
    grep -qF '("assert", MatchKind::MacroOnly),' "$_harness_path"
}

_can_delegate_assert_checks_to_banned_family() {
  [ "${VERIFY_RUN_TESTS:-true}" = "true" ] || return 1
  _banned_family_supports_assert_macros "$1"
}

_write_parser_aware_rust_candidates() {
  _output_file="$1"

  if command -v rg >/dev/null 2>&1; then
    if rg --files --hidden -0 -g '*.rs' >"$_output_file" 2>/dev/null; then
      return 0
    fi
  fi

  if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git ls-files -z --cached --others --exclude-standard -- '*.rs' ':(glob)**/*.rs' >"$_output_file" 2>/dev/null; then
      return 0
    fi
  fi

  find . -name '*.rs' -not -path '*/target/*' -print0 >"$_output_file" 2>/dev/null
}

_is_generated_banned_family_harness_path() {
  case "$1" in
    */tests/banned_family.rs|./tests/banned_family.rs)
      return 0
      ;;
  esac
  return 1
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

_parser_aware_scan_excluding_inline_tests() {
  _pattern="$1"
  _exclude_pattern="${2:-}"
  _label="$3"

  if ! command -v python3 >/dev/null 2>&1; then
    warn "$_label (skipped: python3 not installed; parser-aware scan unavailable)"
    return 0
  fi

  _candidates_tmp="$(mktemp "${TMPDIR:-/tmp}/rust-verify-parser-aware-candidates.XXXXXX")"
  _matches_tmp="$(mktemp "${TMPDIR:-/tmp}/rust-verify-parser-aware.XXXXXX")"
  _register_tmp "$_candidates_tmp"
  _register_tmp "$_matches_tmp"
  if ! _write_parser_aware_rust_candidates "$_candidates_tmp"; then
    rm -f "$_candidates_tmp" "$_matches_tmp"
    fail "$_label (candidate discovery failed)"
    return 1
  fi

  if VERIFY_PATTERN="$_pattern" VERIFY_EXCLUDE_PATTERN="$_exclude_pattern" VERIFY_CANDIDATES_FILE="$_candidates_tmp" python3 - <<'PY' >"$_matches_tmp"
from pathlib import Path
import os
import re
import sys

SKIP_DIRS = {"target", "test", "tests", "testdata", "bench", "benches", "example", "examples", "fixture", "fixtures"}
TEST_MODULE_PREFIXES = ("mod tests", "pub mod tests", "pub(crate) mod tests")

try:
    pattern = os.environ["VERIFY_PATTERN"]
    pattern = pattern.replace("[^[:alnum:]_#]", "[^A-Za-z0-9_#]")
    pattern = pattern.replace("[^[:alnum:]_]", "[^A-Za-z0-9_]")
    pattern = pattern.replace("[[:alnum:]_]", "[A-Za-z0-9_]")
    pattern = pattern.replace("[[:space:]]", r"\s")
    token = re.compile(pattern)
except re.error as exc:
    print(f"error: invalid VERIFY_PATTERN: {exc}", file=sys.stderr)
    raise SystemExit(2)

exclude_pattern = os.environ.get("VERIFY_EXCLUDE_PATTERN", "")
try:
    exclude = re.compile(exclude_pattern) if exclude_pattern else None
except re.error as exc:
    print(f"error: invalid VERIFY_EXCLUDE_PATTERN: {exc}", file=sys.stderr)
    raise SystemExit(2)

candidates_file = os.environ.get("VERIFY_CANDIDATES_FILE")
if not candidates_file:
    print("error: VERIFY_CANDIDATES_FILE is required", file=sys.stderr)
    raise SystemExit(2)


def should_skip(path):
    if path.name == "tests.rs" or path.name.endswith("_test.rs"):
        return True
    return any(part in SKIP_DIRS for part in path.parts)


def strip_comments_and_strings(source: str) -> str:
    out = []
    i = 0
    block_depth = 0
    in_line_comment = False
    in_string = False
    in_char = False
    raw_hashes = None

    def is_lifetime_start(idx: int) -> bool:
        if idx + 1 >= len(source):
            return False
        next_ch = source[idx + 1]
        if not (next_ch.isalpha() or next_ch == "_"):
            return False
        j = idx + 2
        while j < len(source) and (source[j].isalnum() or source[j] == "_"):
            j += 1
        return not (j < len(source) and source[j] == "'")

    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else "\0"

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue

        if block_depth:
            if ch == "/" and nxt == "*":
                block_depth += 1
                i += 2
                continue
            if ch == "*" and nxt == "/":
                block_depth -= 1
                i += 2
                continue
            if ch == "\n":
                out.append(ch)
            i += 1
            continue

        if raw_hashes is not None:
            if ch == '"':
                if raw_hashes == 0:
                    raw_hashes = None
                else:
                    matched = 0
                    j = i + 1
                    while matched < raw_hashes and j < len(source) and source[j] == "#":
                        matched += 1
                        j += 1
                    if matched == raw_hashes:
                        raw_hashes = None
                        i = j
                        continue
            if ch == "\n":
                out.append(ch)
            i += 1
            continue

        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
            if ch == "\n":
                out.append(ch)
            i += 1
            continue

        if in_char:
            if ch == "\\":
                i += 2
                continue
            if ch == "\n":
                in_char = False
                out.append(ch)
                i += 1
                continue
            if ch == "'":
                in_char = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            block_depth = 1
            i += 2
            continue
        if ch in {"r", "b"}:
            j = i + 1
            if ch == "b":
                if j >= len(source) or source[j] != "r":
                    out.append(ch)
                    i += 1
                    continue
                j += 1
            while j < len(source) and source[j] == "#":
                j += 1
            if j < len(source) and source[j] == '"':
                raw_hashes = j - (i + 1 if ch == "r" else i + 2)
                i = j + 1
                continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "'":
            if is_lifetime_start(i):
                out.append(ch)
                i += 1
                continue
            in_char = True
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def has_non_negated_test_token(expr):
    compact = "".join(ch for ch in expr if not ch.isspace())
    idx = 0
    in_string = False
    stack = []

    def is_ident_char(ch):
        return ch.isalnum() or ch == "_"

    while idx < len(compact):
        ch = compact[idx]
        if in_string:
            if ch == "\\" and idx + 1 < len(compact):
                idx += 2
                continue
            if ch == '"':
                in_string = False
            idx += 1
            continue

        if ch == '"':
            in_string = True
            idx += 1
            continue

        if is_ident_char(ch):
            start = idx
            idx += 1
            while idx < len(compact) and is_ident_char(compact[idx]):
                idx += 1
            ident = compact[start:idx]
            if idx < len(compact) and compact[idx] == "(":
                stack.append((ident == "not", ident == "any"))
                idx += 1
                continue
            if ident == "test":
                negated = any(is_not for is_not, _ in stack)
                inside_any = any(is_any for _, is_any in stack)
                if not negated and not inside_any:
                    return True
            continue

        if ch == "(":
            stack.append((False, False))
        elif ch == ")":
            if stack:
                stack.pop()
        idx += 1

    return False


def parse_cfg_test_attribute_at(lines, start_idx):
    idx = start_idx
    remainder = lines[start_idx].strip()
    while True:
        parsed = parse_outer_attribute_at(lines, idx, remainder)
        if parsed is None:
            return None
        attr, attr_end_idx, trailing = parsed
        attr_name = attr.split("(", 1)[0].strip()
        if attr_name == "cfg":
            if "(" not in attr:
                return None
            expr = attr.split("(", 1)[1].rstrip().rstrip(")").strip()
            return (expr, attr_end_idx, trailing)
        remainder = trailing.lstrip()
        if not remainder.startswith("#["):
            return None
        idx = attr_end_idx


def is_test_item_attr(line):
    parsed = parse_test_item_attribute_at([line], 0)
    return parsed is not None


def find_top_level_attr_closing_bracket(segment):
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    in_string = False
    in_char = False
    escaped = False
    raw_hashes = None
    idx = 0

    while idx < len(segment):
        ch = segment[idx]

        if raw_hashes is not None:
            if ch == '"':
                matched = 0
                j = idx + 1
                while matched < raw_hashes and j < len(segment) and segment[j] == "#":
                    matched += 1
                    j += 1
                if matched == raw_hashes:
                    raw_hashes = None
                    idx = j
                    continue
            idx += 1
            continue

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            idx += 1
            continue

        if in_char:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_char = False
            idx += 1
            continue

        if ch in {"r", "b"}:
            j = idx + 1
            if ch == "b":
                if j >= len(segment) or segment[j] != "r":
                    idx += 1
                    continue
                j += 1
            while j < len(segment) and segment[j] == "#":
                j += 1
            if j < len(segment) and segment[j] == '"':
                raw_hashes = j - (idx + 1 if ch == "r" else idx + 2)
                idx = j + 1
                continue
        elif ch == '"':
            in_string = True
        elif ch == "'":
            in_char = True
        elif ch == "(":
            paren_depth += 1
        elif ch == ")":
            if paren_depth > 0:
                paren_depth -= 1
        elif ch == "[":
            bracket_depth += 1
        elif ch == "]":
            if paren_depth == 0 and brace_depth == 0 and bracket_depth == 0:
                return idx
            if bracket_depth > 0:
                bracket_depth -= 1
        elif ch == "{":
            brace_depth += 1
        elif ch == "}":
            if brace_depth > 0:
                brace_depth -= 1

        idx += 1

    return None


def parse_test_item_attribute_at(lines, start_idx):
    idx = start_idx
    remainder = lines[start_idx].strip()
    while True:
        parsed = parse_outer_attribute_at(lines, idx, remainder)
        if parsed is None:
            return None
        attr, attr_end_idx, trailing = parsed
        if not attr:
            return None
        attr_name = attr.split("(", 1)[0].strip()
        terminal = attr_name.rsplit("::", 1)[-1]
        if terminal == "test":
            return (attr, attr_end_idx, trailing)
        remainder = trailing.lstrip()
        if not remainder.startswith("#["):
            return None
        idx = attr_end_idx


def parse_outer_attribute_at(lines, start_idx, initial_remainder):
    if not initial_remainder.startswith("#["):
        return None
    remainder = initial_remainder[2:]
    attr_parts = []
    idx = start_idx

    while True:
        end_idx = find_top_level_attr_closing_bracket(remainder)
        if end_idx is not None:
            before_end = remainder[:end_idx].strip()
            if before_end:
                attr_parts.append(before_end)
            trailing = remainder[end_idx + 1:].lstrip()
            return (" ".join(attr_parts), idx, trailing)

        chunk = remainder.strip()
        if chunk:
            attr_parts.append(chunk)

        idx += 1
        if idx >= len(lines):
            return None
        remainder = lines[idx].strip()


def is_tests_module_decl(line):
    trimmed = line.lstrip()
    for prefix in TEST_MODULE_PREFIXES:
        if not trimmed.startswith(prefix):
            continue
        remainder = trimmed[len(prefix):]
        if not remainder:
            return True
        next_ch = remainder[0]
        if next_ch in "{;" or next_ch.isspace():
            return True
    return False


def brace_delta(line):
    delta = 0
    for ch in line:
        if ch == "{":
            delta += 1
        elif ch == "}":
            delta -= 1
    return delta


def cfg_annotated_item_state(line):
    if "{" in line:
        delta = brace_delta(line)
        if delta > 0:
            return ("block", delta)
        return ("complete", 0)
    if ";" in line:
        return ("complete", 0)
    return ("pending", 0)


def cfg_attr_state_from_trailing(trailing):
    trimmed = trailing.strip()
    if not trimmed:
        return ("pending", 0)
    return cfg_annotated_item_state(trimmed)


def attribute_stack_start(lines, idx):
    start = idx
    while start > 0:
        previous = lines[start - 1].strip()
        if not previous.startswith("#["):
            break
        start -= 1
    return start


def compute_test_line_mask(lines, sanitized_lines):
    mask = [False] * len(lines)
    pending_test_item = False
    in_test_item_block = False
    test_item_depth = 0

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        sanitized_line = sanitized_lines[idx]

        if in_test_item_block:
            mask[idx] = True
            test_item_depth += brace_delta(sanitized_line)
            if test_item_depth <= 0:
                in_test_item_block = False
                test_item_depth = 0
            idx += 1
            continue

        if pending_test_item:
            mask[idx] = True
            trimmed = line.strip()
            if not trimmed or trimmed.startswith("#["):
                idx += 1
                continue
            state, delta = cfg_annotated_item_state(sanitized_line)
            if state == "block":
                in_test_item_block = True
                test_item_depth = delta
                pending_test_item = False
            elif state == "complete":
                pending_test_item = False
            idx += 1
            continue

        parsed = parse_cfg_test_attribute_at(lines, idx)
        if parsed is not None:
            expr, attr_end_idx, trailing = parsed
            if has_non_negated_test_token(expr):
                attr_start_idx = attribute_stack_start(lines, idx)
                for mark_idx in range(attr_start_idx, attr_end_idx + 1):
                    mask[mark_idx] = True
                attr_line = sanitized_lines[attr_end_idx]
                delta = brace_delta(attr_line)
                if delta != 0:
                    in_test_item_block = True
                    test_item_depth = delta
                    pending_test_item = False
                else:
                    state, inner_delta = cfg_attr_state_from_trailing(trailing)
                    if state == "block":
                        in_test_item_block = True
                        test_item_depth = inner_delta
                        pending_test_item = False
                    elif state == "pending":
                        pending_test_item = True
                    else:
                        pending_test_item = False
                idx = attr_end_idx + 1
                continue

        parsed = parse_test_item_attribute_at(lines, idx)
        if parsed is not None:
            _, attr_end_idx, trailing = parsed
            attr_start_idx = attribute_stack_start(lines, idx)
            for mark_idx in range(attr_start_idx, attr_end_idx + 1):
                mask[mark_idx] = True
            state, delta = cfg_attr_state_from_trailing(trailing)
            if state == "block":
                in_test_item_block = True
                test_item_depth = delta
                pending_test_item = False
            elif state == "complete":
                pending_test_item = False
            else:
                pending_test_item = True
            idx = attr_end_idx + 1
            continue

        if is_tests_module_decl(line):
            mask[idx] = True
            delta = brace_delta(sanitized_line)
            if delta != 0:
                in_test_item_block = True
                test_item_depth = delta

        idx += 1

    return mask


def load_candidate_paths(filename):
    try:
        payload = Path(filename).read_bytes()
    except OSError as exc:
        print(f"error: failed to read VERIFY_CANDIDATES_FILE: {exc}", file=sys.stderr)
        raise SystemExit(2)

    seen = set()
    paths = []
    for raw_path in payload.split(b"\0"):
        if not raw_path:
            continue
        try:
            decoded = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            decoded = raw_path.decode("utf-8", errors="surrogateescape")
        path = Path(decoded)
        if not path.is_file():
            continue
        normalized = str(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        paths.append(path)
    return sorted(paths)


violations = []

for path in load_candidate_paths(candidates_file):
    if should_skip(path):
        continue
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        continue

    raw_lines = source.splitlines()
    sanitized_lines = strip_comments_and_strings(source).splitlines()
    if len(sanitized_lines) < len(raw_lines):
        sanitized_lines.extend([""] * (len(raw_lines) - len(sanitized_lines)))
    mask = compute_test_line_mask(raw_lines, sanitized_lines)

    for line_no, (raw_line, sanitized_line) in enumerate(zip(raw_lines, sanitized_lines), start=1):
        if mask[line_no - 1]:
            continue
        if exclude is not None and exclude.search(raw_line):
            continue
        if token.search(sanitized_line):
            violations.append(f"{path}:{line_no}:{raw_line}")
if violations:
    for line in violations[:5]:
        print(line)
    raise SystemExit(1)
PY
  then
    _status=0
  else
    _status=$?
  fi

  _matches="$(sed -n '1,5p' "$_matches_tmp" 2>/dev/null || true)"
  rm -f "$_matches_tmp"
  if [ "$_status" -eq 0 ]; then
    pass "$_label"
    return 0
  fi

  if [ "$_status" -eq 1 ] && [ -n "$_matches" ]; then
    printf '%s\n' "$_matches"
    fail "$_label"
    return 1
  fi

  fail "$_label (parser-aware scan failed)"
  return 1
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
_found_banned_assert_capable=0
_delegate_assert_checks=0
if [ -n "$_found_banned" ]; then
  if _banned_family_supports_assert_macros "$_found_banned"; then
    pass "banned_family.rs installed with assert coverage: $_found_banned"
    _found_banned_assert_capable=1
    if _can_delegate_assert_checks_to_banned_family "$_found_banned"; then
      _delegate_assert_checks=1
    fi
  else
    warn "banned_family.rs lacks assert coverage: $_found_banned (re-run scaffold.sh --banned-test)"
    _install_ok=0
  fi
else
  warn "banned_family.rs not found (run scaffold.sh --banned-test)"
  _install_ok=0
fi

# Check 2: CI workflow
_ci_yml=""
_ci_script=""
_ci_verify=""
_ci_workspace_members=""
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
if [ -f ".github/scripts/verify.sh" ]; then
  _ci_verify=".github/scripts/verify.sh"
elif [ -n "$git_root_dir" ] && [ -f "$git_root_dir/.github/scripts/verify.sh" ]; then
  _ci_verify="$git_root_dir/.github/scripts/verify.sh"
fi
if [ -f ".github/scripts/workspace-members.sh" ]; then
  _ci_workspace_members=".github/scripts/workspace-members.sh"
elif [ -n "$git_root_dir" ] && [ -f "$git_root_dir/.github/scripts/workspace-members.sh" ]; then
  _ci_workspace_members="$git_root_dir/.github/scripts/workspace-members.sh"
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
if [ -n "$_ci_verify" ]; then
  pass "CI verify script installed: $_ci_verify"
else
  warn "CI verify script not found (run scaffold.sh --ci)"
  _install_ok=0
fi
if [ -n "$_ci_workspace_members" ]; then
  pass "CI workspace helper installed: $_ci_workspace_members"
else
  warn "CI workspace helper not found (run scaffold.sh --ci)"
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

_macro_invocation_pattern() {
  _macro_name="$1"
  printf '(^|[^[:alnum:]_])%s[[:space:]]*![[:space:]]*\\(' "$_macro_name"
}

_panic_macro_pattern="$(_macro_invocation_pattern 'panic')"
_unimplemented_macro_pattern="$(_macro_invocation_pattern 'unimplemented')"
_unreachable_macro_pattern="$(_macro_invocation_pattern 'unreachable')"
_assert_macro_pattern="$(_macro_invocation_pattern 'assert(_eq|_ne)?')"
_todo_macro_pattern="$(_macro_invocation_pattern 'todo')"
_dbg_macro_pattern="$(_macro_invocation_pattern 'dbg')"

echo "Panic-inducing patterns:"
# NOTE: exclude_tests is path-based and excludes conventional test-only dirs.
# For inline-test-sensitive banned-family checks, use the parser-aware helper
# so #[cfg(test)] blocks and test-annotated items inside src/*.rs are masked
# consistently with banned_family.rs. Keep assert-family delegated to
# banned_family.rs only when the installed harness includes assert coverage and
# Phase 2.4 test execution is enabled.
# unwrap family: .unwrap(), .unwrap_err(), .unwrap_unchecked() — but NOT .unwrap_or*()
_parser_aware_scan_excluding_inline_tests '\.unwrap(_err|_unchecked)?[[:space:]]*\(' '// INVARIANT:' "no panic-inducing unwrap family" || true
# expect family: .expect(), .expect_err() — but NOT .expectation(...)
_parser_aware_scan_excluding_inline_tests '\.expect(_err)?[[:space:]]*\(' '// INVARIANT:' "no panic-inducing expect family" || true
# panic macros
_parser_aware_scan_excluding_inline_tests "$_panic_macro_pattern" "" "no panic!()" || true
_parser_aware_scan_excluding_inline_tests "$_unimplemented_macro_pattern" "" "no unimplemented!()" || true
_parser_aware_scan_excluding_inline_tests "$_unreachable_macro_pattern" '// INVARIANT:' "no bare unreachable!()" || true
if [ "$_delegate_assert_checks" -eq 1 ]; then
  pass "no assert macros outside tests (delegated to banned_family.rs)"
else
  _parser_aware_scan_excluding_inline_tests "$_assert_macro_pattern" '// INVARIANT:' "no assert macros outside tests" || true
fi
# process exit
_search 'std::process::exit\(' "" "no exit() outside entrypoints" "exclude_tests" "exclude_entrypoints" || true

echo ""
echo "Placeholders:"
_parser_aware_scan_excluding_inline_tests "$_todo_macro_pattern" "" "no todo!()" || true

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
_parser_aware_scan_excluding_inline_tests "$_dbg_macro_pattern" "" "no dbg!()" || true
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
echo ""
echo "String allocation:"
_search 'String::from\(""\)' "" 'no String::from("")' || true
_search '"".to_string\(\)' "" 'no "".to_string()' || true

echo ""
echo "Resource safety:"
_search_excluding 'mem::forget\(' '// ALLOW:' "no mem::forget()" "exclude_tests" || true
_search_excluding 'Box::leak\(' '// ALLOW:' "no Box::leak()" "exclude_tests" || true

echo ""
echo "Unsafe code:"
_parser_aware_scan_excluding_inline_tests '(^|[^[:alnum:]_#])unsafe([^[:alnum:]_]|$)' "" "no unsafe code in non-test files" || true

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
  if rg '#\[allow\(' --type rust 2>/dev/null \
     | rg -v '(^|/|\.)tests/banned_family\.rs:' \
     | rg -v '// Reason:' | head -5 | grep -q .; then
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
     | grep -vE '(^|/|\.)tests/banned_family\.rs:' \
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
