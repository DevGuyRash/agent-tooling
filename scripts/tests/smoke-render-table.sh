#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
RENDER="$SCRIPT_DIR/render-table.sh"

pass_count=0
fail_count=0

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  fail_count=$((fail_count + 1))
}

pass() {
  printf 'PASS: %s\n' "$1"
  pass_count=$((pass_count + 1))
}

assert_contains() {
  label=$1
  needle=$2
  haystack=$3
  if printf '%s' "$haystack" | grep -Fq -- "$needle"; then
    return 0
  fi
  fail "$label: expected to find '$needle'"
  return 1
}

assert_not_contains() {
  label=$1
  needle=$2
  haystack=$3
  if printf '%s' "$haystack" | grep -Fq -- "$needle"; then
    fail "$label: did NOT expect to find '$needle'"
    return 1
  fi
  return 0
}

assert_exit_zero() {
  label=$1
  code=$2
  if [ "$code" -ne 0 ]; then
    fail "$label: expected exit 0 but got $code"
    return 1
  fi
  return 0
}

# ── Test 1: TSV basic ──

out=$(printf 'Name\tAge\nAlice\t30\nBob\t25' | sh "$RENDER" 2>&1) || true
assert_contains "tsv_basic: top-left corner" "┌" "$out" &&
assert_contains "tsv_basic: bottom-right corner" "┘" "$out" &&
assert_contains "tsv_basic: header Name" "Name" "$out" &&
assert_contains "tsv_basic: cell Alice" "Alice" "$out" &&
assert_contains "tsv_basic: cell 25" "25" "$out" &&
assert_contains "tsv_basic: vertical border" "│" "$out" &&
pass "tsv_basic"

# ── Test 2: CSV basic ──

out=$(printf 'Name,Age\nAlice,30\nBob,25' | sh "$RENDER" --csv 2>&1) || true
assert_contains "csv_basic: top border" "┌" "$out" &&
assert_contains "csv_basic: cell Alice" "Alice" "$out" &&
assert_contains "csv_basic: cell 30" "30" "$out" &&
pass "csv_basic"

# ── Test 3: CSV quoted fields with embedded commas ──

out=$(printf 'Name,Desc\nAlice,"Has a, comma"\nBob,Simple' | sh "$RENDER" --csv 2>&1) || true
assert_contains "csv_quoted: comma in cell" "Has a, comma" "$out" &&
assert_contains "csv_quoted: simple cell" "Simple" "$out" &&
pass "csv_quoted"

# ── Test 4: CSV escaped quotes ──

out=$(printf 'Name,Desc\nAlice,"Says ""hello"""\nBob,Normal' | sh "$RENDER" --csv 2>&1) || true
assert_contains "csv_escaped_quotes: unescaped in output" 'Says "hello"' "$out" &&
pass "csv_escaped_quotes"

# ── Test 5: JSONL basic with --fields ──

out=$(printf '{"a":"foo","b":"bar","c":"baz"}\n{"a":"1","b":"2","c":"3"}' | sh "$RENDER" --jsonl --fields "a,b" 2>&1) || true
assert_contains "jsonl_basic: field a header" "a" "$out" &&
assert_contains "jsonl_basic: cell foo" "foo" "$out" &&
assert_contains "jsonl_basic: cell 2" "2" "$out" &&
assert_not_contains "jsonl_basic: excluded field" "baz" "$out" &&
pass "jsonl_basic"

# ── Test 6: JSONL custom headers ──

out=$(printf '{"x":"1","y":"2"}' | sh "$RENDER" --jsonl --fields "x,y" --headers "Alpha,Beta" 2>&1) || true
assert_contains "jsonl_headers: Alpha" "Alpha" "$out" &&
assert_contains "jsonl_headers: Beta" "Beta" "$out" &&
assert_not_contains "jsonl_headers: raw field x as header" "│ x " "$out" &&
pass "jsonl_headers"

# ── Test 7: Empty input ──

out=$(printf '' | sh "$RENDER" 2>&1)
rc=$?
assert_exit_zero "empty_input" "$rc" &&
pass "empty_input"

# ── Test 8: Single row (header + 1 data row) ──

out=$(printf 'Col\nVal' | sh "$RENDER" 2>&1) || true
assert_contains "single_row: header" "Col" "$out" &&
assert_contains "single_row: value" "Val" "$out" &&
assert_contains "single_row: mid border" "├" "$out" &&
pass "single_row"

# ── Test 9: Max col width wrapping ──

out=$(printf 'ID\tDesc\nA\tThis should wrap at fifteen chars' | sh "$RENDER" --max-col-width 15 2>&1) || true
# The cell should have wrapped lines — look for continuation (empty ID cell)
assert_contains "wrap: has content" "This should" "$out" &&
# The table should have multiple lines for the same row (│    │ continuation │)
lines=$(printf '%s' "$out" | grep -c '│' || true)
if [ "$lines" -lt 4 ]; then
  fail "wrap: expected at least 4 lines with │ (got $lines)"
else
  pass "wrap"
fi

# ── Test 10: Unicode content ──

out=$(printf 'Name\tCity\nAlice\tTokyo\nBob\tParis' | sh "$RENDER" 2>&1) || true
assert_contains "unicode: Tokyo" "Tokyo" "$out" &&
assert_contains "unicode: Paris" "Paris" "$out" &&
pass "unicode"

# ── Test 11: Help flag ──

out=$(sh "$RENDER" --help 2>&1)
rc=$?
assert_exit_zero "help_flag" "$rc" &&
assert_contains "help_flag: usage text" "Usage" "$out" &&
assert_contains "help_flag: mentions csv" "--csv" "$out" &&
pass "help_flag"

# ── Test 12: Box-drawing characters only (no ASCII table chars) ──

out=$(printf 'A\tB\n1\t2' | sh "$RENDER" 2>&1) || true
assert_not_contains "box_chars: no plus" "+" "$out" &&
assert_not_contains "box_chars: no pipe as border" "| " "$out" &&
assert_contains "box_chars: uses ─" "─" "$out" &&
assert_contains "box_chars: uses │" "│" "$out" &&
pass "box_drawing_chars_only"

# ── Test 13: TSV with header override ──

out=$(printf 'old_a\told_b\n1\t2' | sh "$RENDER" --headers "New A,New B" 2>&1) || true
assert_contains "tsv_header_override: New A" "New A" "$out" &&
assert_contains "tsv_header_override: New B" "New B" "$out" &&
assert_not_contains "tsv_header_override: old header gone" "old_a" "$out" &&
pass "tsv_header_override"

# ── Test 14: Positional file input ──

tmp_tsv=$(mktemp)
printf 'X\tY\n1\t2' > "$tmp_tsv"
out=$(sh "$RENDER" "$tmp_tsv" 2>/dev/null) || true
rm -f "$tmp_tsv"
assert_contains "file_positional: cell 1" "1" "$out" &&
assert_contains "file_positional: cell 2" "2" "$out" &&
assert_contains "file_positional: border" "┌" "$out" &&
pass "file_positional"

# ── Test 15: --file flag ──

tmp_tsv=$(mktemp)
printf 'X\tY\n3\t4' > "$tmp_tsv"
out=$(sh "$RENDER" --file "$tmp_tsv" 2>/dev/null) || true
rm -f "$tmp_tsv"
assert_contains "file_flag: cell 3" "3" "$out" &&
pass "file_flag"

# ── Test 16: Auto-detect JSON array ──

out=$(printf '[{"a":"foo"},{"a":"bar"}]' | sh "$RENDER" 2>/dev/null) || true
assert_contains "auto_json: cell foo" "foo" "$out" &&
assert_contains "auto_json: cell bar" "bar" "$out" &&
pass "auto_detect_json"

# ── Test 17: Auto-detect JSONL (no flags) ──

out=$(printf '{"x":"1","y":"2"}\n{"x":"3","y":"4"}' | sh "$RENDER" 2>/dev/null) || true
assert_contains "auto_jsonl: cell 1" "1" "$out" &&
assert_contains "auto_jsonl: cell 4" "4" "$out" &&
pass "auto_detect_jsonl"

# ── Test 18: JSON nested object → stringified ──

out=$(printf '{"name":"Alice","info":{"age":30}}' | sh "$RENDER" 2>/dev/null) || true
assert_contains "json_nested: stringified" '{"age":30}' "$out" &&
pass "json_nested_stringify"

# ── Test 19: YAML input ──

if command -v python3 >/dev/null 2>&1 && python3 -c "import yaml" 2>/dev/null; then
  out=$(printf -- '- name: Alice\n  age: 30\n- name: Bob\n  age: 25' | sh "$RENDER" --yaml 2>/dev/null) || true
  assert_contains "yaml: cell Alice" "Alice" "$out" &&
  assert_contains "yaml: cell 30" "30" "$out" &&
  pass "yaml_basic"
else
  printf 'SKIP: yaml_basic (PyYAML not available)\n'
fi

# ── Test 20: --col-widths per-column override ──

out=$(printf 'A\tB\tC\nfoo\tbar\tbaz' | sh "$RENDER" --col-widths "6,,6" 2>/dev/null) || true
assert_contains "col_widths: border" "┌" "$out" &&
assert_contains "col_widths: cell foo" "foo" "$out" &&
pass "col_widths"

# ── Test 21: CJK display width alignment ──

if command -v python3 >/dev/null 2>&1; then
  out=$(printf 'Name\tCity\nAlice\tTokyo\nBob\t東京' | sh "$RENDER" 2>/dev/null) || true
  # All lines must be the same display width
  unique_widths=$(printf '%s' "$out" | python3 -c "
import sys, unicodedata
widths = set()
for line in sys.stdin:
    line = line.rstrip('\n')
    if line:
        widths.add(sum(2 if unicodedata.east_asian_width(c) in ('F','W') else 1 for c in line))
print(len(widths))
")
  if [ "$unique_widths" = "1" ]; then
    pass "cjk_display_width"
  else
    fail "cjk_display_width: lines have $unique_widths different display widths (expected 1)"
  fi
else
  printf 'SKIP: cjk_display_width (python3 not available)\n'
fi

# ── Test 22: Error hint quality ──

err=$(sh "$RENDER" --bogus 2>&1) || true
assert_contains "error_hint: has help pointer" "--help" "$err" &&
pass "error_hint_quality"

# ── Test 23: File not found error ──

err=$(sh "$RENDER" --file /nonexistent/path 2>&1) || true
assert_contains "file_not_found: has path" "/nonexistent/path" "$err" &&
pass "file_not_found_error"

# ── Summary ──

printf '\n─── Results: %d passed, %d failed ───\n' "$pass_count" "$fail_count"
if [ "$fail_count" -gt 0 ]; then
  exit 1
fi
