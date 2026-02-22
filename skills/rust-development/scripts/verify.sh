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
#
# Requires: rg (ripgrep). grep fallback is provided but limited.

set -eu

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

# Counters are written to temp files so they survive subshells.
_fail_file="$(mktemp)"
_warn_file="$(mktemp)"
echo 0 > "$_fail_file"
echo 0 > "$_warn_file"
trap 'rm -f "$_fail_file" "$_warn_file"' EXIT

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
    _matches=$(rg "$@" -- "$pattern" 2>/dev/null | head -5)
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
    _matches=$(rg "$@" -- "$pattern" 2>/dev/null | grep -v "$exclude_pattern" | head -5)
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
       | grep -v "$exclude_pattern" | head -5)
    if [ -n "$_matches" ]; then
      printf '%s\n' "$_matches"
      fail "$_label"
      return 1
    fi
  fi
  pass "$_label"
  return 0
}

# ---------------------------------------------------------------------------
echo "═══ Phase 2.1: Banned pattern scan ═══"
echo ""
# ---------------------------------------------------------------------------

echo "Panic-inducing patterns:"
# NOTE: exclude_tests is path-based and excludes conventional test-only dirs.
# Keep banned_family.rs as the stricter parser-aware backstop for cfg(test) masking.
_search_excluding '\.unwrap[[:space:]]*\(' '// INVARIANT:' "no bare .unwrap()" "exclude_tests" || true
_search_excluding '\.expect[[:space:]]*\(' '// INVARIANT:' "no bare .expect()" "exclude_tests" || true
_search 'panic!\(' "" "no panic!()" "exclude_tests" || true
_search 'unimplemented!\(' "" "no unimplemented!()" "exclude_tests" || true
_search_excluding 'unreachable!\(' '// INVARIANT:' "no bare unreachable!()" "exclude_tests" || true
_search 'std::process::exit\(' "" "no exit() outside entrypoints" "exclude_tests" "exclude_entrypoints" || true

echo ""
echo "Placeholders:"
_search 'todo!\(' "" "no todo!()" "exclude_tests" || true

echo ""
echo "Non-idiomatic patterns:"
_search '\.map\(\|.*\|.*\.clone\(\)\)' "" "no .map(|x| x.clone())" || true
_search '\.map\(\|.*\|.*\.to_owned\(\)\)' "" "no .map(|x| x.to_owned())" || true
_search '\.iter\(\)\.count\(\)' "" "no .iter().count()" || true
_search '\.iter\(\)\.next\(\)' "" "no .iter().next()" || true
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
if command -v rustfmt >/dev/null 2>&1; then
  if cargo fmt --all --check 2>&1; then
    pass "cargo fmt --all --check"
  else
    fail "cargo fmt --all --check"
  fi
else
  warn "rustfmt not installed (rustup component add rustfmt)"
fi

echo ""
echo "Clippy:"
if cargo clippy --version >/dev/null 2>&1; then
  if cargo clippy --workspace --all-targets -- -D warnings 2>&1; then
    pass "cargo clippy --workspace --all-targets -- -D warnings"
  else
    fail "cargo clippy --workspace --all-targets -- -D warnings"
  fi
else
  warn "clippy not installed (rustup component add clippy)"
fi

echo ""
echo "Tests:"
if cargo test --workspace 2>&1; then
  pass "cargo test --workspace"
else
  fail "cargo test --workspace"
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
