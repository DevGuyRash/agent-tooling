#!/bin/sh
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
REPO_ROOT=$(CDPATH='' cd -- "$ROOT/../.." && pwd)
TEST_REPO=$(mktemp -d "${TMPDIR:-/tmp}/friction-smoke-posix.XXXXXX")

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_file() {
  [ -f "$1" ] || fail "missing file: $1"
}

assert_contains() {
  needle=$1
  haystack=$2
  grep -Fq -- "$needle" "$haystack" || fail "expected '$needle' in $haystack"
}

assert_not_contains() {
  needle=$1
  haystack=$2
  if grep -Fq -- "$needle" "$haystack"; then
    fail "did NOT expect '$needle' in $haystack"
  fi
}

assert_equals() {
  expected=$1
  actual=$2
  [ "$expected" = "$actual" ] || fail "expected '$expected' but got '$actual'"
}

DEFAULT_EVENTS=$TEST_REPO/.local/reports/friction/events.jsonl
DEFAULT_INDEX=$TEST_REPO/.local/reports/friction/INDEX.md

cleanup() {
  rm -rf "$TEST_REPO"
}

trap cleanup EXIT

git init -q "$TEST_REPO"
mkdir -p "$TEST_REPO/.local"

cd "$TEST_REPO"

# ═══════════════════════════════════════════════════════════════════════
# Test 1: Basic event filing with direct flags
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 1: Basic event filing ... '

OUTPUT=$("$ROOT/scripts/report-friction.sh" \
  --title "Dispatch role slug mismatch" \
  --source-type file \
  --source-ref "$ROOT/SKILL.md" \
  --source-line 160 \
  --source-excerpt "Use mpcr protocol dispatch --role <ROLE> to get the architecture prompt." \
  --expected-outcome "The CLI would resolve 'architecture' as a valid dispatch role slug." \
  --actual-outcome "The command exited with: error: unknown dispatch role: architecture. Bearer ghp_leakedtoken1234567890abcdef12345678." \
  --reading "The dispatch table had a column called 'Role' with 'Architecture' in it, and the instruction said 'Use --role <ROLE>'. I plugged in 'architecture' — seemed like a direct substitution. The CLI rejected it immediately." \
  --hindsight "I should have run the CLI's own discovery command first." \
  --impact blocked \
  --tags "dispatch,slug-mismatch,mpcr" \
  --aliases "instructions")

printf '%s\n' "$OUTPUT" | grep -q "^FRICTION_EVENTS_FILE=$DEFAULT_EVENTS$" || fail "unexpected default events file output"
printf '%s\n' "$OUTPUT" | grep -q "^FRICTION_INDEX_FILE=$DEFAULT_INDEX$" || fail "unexpected default index file output"
printf '%s\n' "$OUTPUT" | grep -q "^FRICTION_EVENT_ID=evt-0001$" || fail "should output event_id"

assert_file "$DEFAULT_EVENTS"
assert_file "$DEFAULT_INDEX"
assert_contains '"event_id":"evt-0001"' "$DEFAULT_EVENTS"
# New schema fields present
assert_contains '"impact":"blocked"' "$DEFAULT_EVENTS"
assert_contains '"tags":["dispatch","slug-mismatch","mpcr"]' "$DEFAULT_EVENTS"
assert_contains '"aliases":["instructions"]' "$DEFAULT_EVENTS"
# Sources array with excerpt
assert_contains '"sources":[{' "$DEFAULT_EVENTS"
assert_contains '"type":"file"' "$DEFAULT_EVENTS"
assert_contains '"line":160' "$DEFAULT_EVENTS"
assert_contains '"excerpt":"Use mpcr protocol dispatch' "$DEFAULT_EVENTS"
# Token redaction
if grep -q 'ghp_leakedtoken' "$DEFAULT_EVENTS"; then
  fail "token leaked into events.jsonl"
fi
assert_contains '[REDACTED]' "$DEFAULT_EVENTS"
# Old schema fields should NOT be present
assert_not_contains '"schema_version"' "$DEFAULT_EVENTS"
assert_not_contains '"taxonomy_version"' "$DEFAULT_EVENTS"
assert_not_contains '"instruction_text"' "$DEFAULT_EVENTS"
assert_not_contains '"action_taken"' "$DEFAULT_EVENTS"
assert_not_contains '"surface"' "$DEFAULT_EVENTS"
assert_not_contains '"mode"' "$DEFAULT_EVENTS"
assert_not_contains '"derived_category"' "$DEFAULT_EVENTS"
assert_not_contains '"observed_surface"' "$DEFAULT_EVENTS"
assert_not_contains '"confidence"' "$DEFAULT_EVENTS"
assert_not_contains '"guidance_quality"' "$DEFAULT_EVENTS"
assert_not_contains '"incident_id"' "$DEFAULT_EVENTS"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 2: JSON stdin filing with tags, aliases, and multiple sources
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 2: JSON stdin filing ... '

OUTPUT2=$(cat <<'EOF' | "$ROOT/scripts/report-friction.sh" --from-json -
{
  "title": "SSH signing agent unavailable",
  "expected_outcome": "Git would create the commit object.",
  "actual_outcome": "error: 1Password: Could not connect to socket specified by SSH_AUTH_SOCK.",
  "reading": "I had staged the files and passed the leak scan. The commit failed during signing because SSH_AUTH_SOCK had no socket available. This was purely an environment issue.",
  "hindsight": "I should have checked whether this repo enforces commit signing.",
  "impact": "blocked",
  "tags": ["ssh-auth-sock", "git-signing", "1password"],
  "aliases": ["auth", "git"],
  "sources": [
    {"type": "file", "ref": "functions.exec_command", "excerpt": "git commit -m 'docs: add skill'"},
    {"type": "documentation", "ref": "repo-config", "excerpt": "commit.gpgsign = true"}
  ]
}
EOF
)

printf '%s\n' "$OUTPUT2" | grep -q "^FRICTION_EVENT_ID=evt-0002$" || fail "should be evt-0002"
# Verify multiple sources
LINE2=$(sed -n '2p' "$DEFAULT_EVENTS")
printf '%s\n' "$LINE2" | grep -q '"sources":\[{' || fail "missing sources array in event 2"
printf '%s\n' "$LINE2" | grep -q '"auth"' || fail "missing auth alias"
printf '%s\n' "$LINE2" | grep -q '"git"' || fail "missing git alias"
# Tags should be lowercase
printf '%s\n' "$LINE2" | grep -q '"ssh-auth-sock"' || fail "missing ssh-auth-sock tag"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 3: --add-tags on an existing event
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 3: --add-tags ... '

"$ROOT/scripts/report-friction.sh" --add-tags evt-0001 "cli,testing" >/dev/null 2>&1
LINE1=$(sed -n '1p' "$DEFAULT_EVENTS")
printf '%s\n' "$LINE1" | grep -q '"dispatch"' || fail "original tags missing after --add-tags"
printf '%s\n' "$LINE1" | grep -q '"cli"' || fail "--add-tags didn't add 'cli'"
printf '%s\n' "$LINE1" | grep -q '"testing"' || fail "--add-tags didn't add 'testing'"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 4: --add-aliases on an existing event
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 4: --add-aliases ... '

"$ROOT/scripts/report-friction.sh" --add-aliases evt-0002 "environment" >/dev/null 2>&1
LINE2_UPDATED=$(sed -n '2p' "$DEFAULT_EVENTS")
printf '%s\n' "$LINE2_UPDATED" | grep -q '"auth"' || fail "original aliases missing after --add-aliases"
printf '%s\n' "$LINE2_UPDATED" | grep -q '"environment"' || fail "--add-aliases didn't add 'environment'"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 5: Query by impact
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 5: Query by impact ... '

QUERY_BLOCKED=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --impact blocked --format json)
BLOCKED_COUNT=$(printf '%s\n' "$QUERY_BLOCKED" | jq 'length')
assert_equals "2" "$BLOCKED_COUNT"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 6: Query by tag (fuzzy substring match)
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 6: Query by tag (fuzzy) ... '

QUERY_AUTH=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --tag auth --format json)
AUTH_COUNT=$(printf '%s\n' "$QUERY_AUTH" | jq 'length')
# "ssh-auth-sock" contains "auth", so event 2 should match
assert_equals "1" "$AUTH_COUNT"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 7: Query by alias (fuzzy substring match)
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 7: Query by alias (fuzzy) ... '

QUERY_ALIAS=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --alias instruct --format json)
ALIAS_COUNT=$(printf '%s\n' "$QUERY_ALIAS" | jq 'length')
# "instructions" contains "instruct", so event 1 should match
assert_equals "1" "$ALIAS_COUNT"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 8: Query by text search
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 8: Query by text ... '

QUERY_TEXT=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --text "SSH_AUTH_SOCK" --format json)
TEXT_COUNT=$(printf '%s\n' "$QUERY_TEXT" | jq 'length')
assert_equals "1" "$TEXT_COUNT"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 9: Query by source-ref
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 9: Query by source-ref ... '

QUERY_SRC=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --source-ref "functions.exec_command" --format json)
SRC_COUNT=$(printf '%s\n' "$QUERY_SRC" | jq 'length')
assert_equals "1" "$SRC_COUNT"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 10: INDEX structure
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 10: INDEX structure ... '

assert_file "$DEFAULT_INDEX"
assert_contains "# Friction Index" "$DEFAULT_INDEX"
assert_contains "**Created:**" "$DEFAULT_INDEX"
assert_contains "**Last event:**" "$DEFAULT_INDEX"
assert_contains "**Index rebuilt:**" "$DEFAULT_INDEX"
assert_contains "**Events:**" "$DEFAULT_INDEX"
assert_contains "**Blocked:**" "$DEFAULT_INDEX"
assert_contains "## Events" "$DEFAULT_INDEX"
assert_contains "## By Alias" "$DEFAULT_INDEX"
assert_contains "## By Source" "$DEFAULT_INDEX"
assert_contains "## Tags" "$DEFAULT_INDEX"
assert_contains "## Date Distribution" "$DEFAULT_INDEX"
# Should contain event titles
assert_contains "Dispatch role slug mismatch" "$DEFAULT_INDEX"
assert_contains "SSH signing agent" "$DEFAULT_INDEX"
# Should contain impact column
assert_contains "blocked" "$DEFAULT_INDEX"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 11: Add a continued event and verify mixed impact in INDEX
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 11: Mixed impact events ... '

"$ROOT/scripts/report-friction.sh" \
  --title "Repo-wide rustfmt spillover" \
  --source-type file \
  --source-ref "chatmux-ui/Cargo.toml" \
  --expected-outcome "Only the touched file would be formatted." \
  --actual-outcome "rustfmt reformatted many unrelated files." \
  --reading "I used the crate-level formatter for convenience but it covered many files beyond the bounded fix surface." \
  --impact continued \
  --tags "rustfmt,formatting" \
  --aliases "tool" >/dev/null 2>&1

TOTAL_EVENTS=$(jq -s 'length' "$DEFAULT_EVENTS")
assert_equals "3" "$TOTAL_EVENTS"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 12: Markdown query output
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 12: Markdown query output ... '

MD_OUTPUT=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --format md)
printf '%s\n' "$MD_OUTPUT" | grep -q "# Friction Query Results" || fail "missing md header"
printf '%s\n' "$MD_OUTPUT" | grep -q "Impact:" || fail "missing Impact in md output"
printf '%s\n' "$MD_OUTPUT" | grep -q "Aliases:" || fail "missing Aliases in md output"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 13: Fingerprint grouping (same source + date = same fingerprint)
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 13: Fingerprint grouping ... '

FP1=$(jq -r '.fingerprint' "$DEFAULT_EVENTS" | sed -n '1p')
# Event 1 and 3 have different source_refs, so different fingerprints
FP3=$(jq -r '.fingerprint' "$DEFAULT_EVENTS" | sed -n '3p')
if [ "$FP1" = "$FP3" ]; then
  fail "events with different sources should have different fingerprints"
fi

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 14: Cross-repo report
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 14: Cross-repo report ... '

CROSS_OUTPUT=$("$ROOT/scripts/generate-report.sh" --scan-dirs "$TEST_REPO" --report-type cross-repo --format md)
printf '%s\n' "$CROSS_OUTPUT" | grep -q "Cross-Repo Friction Index" || fail "missing cross-repo header"
printf '%s\n' "$CROSS_OUTPUT" | grep -q "Impact Summary" || fail "missing Impact Summary section"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════
printf '\nAll smoke tests passed.\n'
