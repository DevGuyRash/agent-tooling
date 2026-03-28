#!/bin/sh
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
REPO_ROOT=$(CDPATH='' cd -- "$ROOT/../.." && pwd)

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

assert_file() {
  [ -f "$1" ] || fail "missing file: $1"
}

assert_contains() {
  needle=$1
  haystack=$2
  grep -Fq "$needle" "$haystack" || fail "expected '$needle' in $haystack"
}

assert_equals() {
  expected=$1
  actual=$2
  [ "$expected" = "$actual" ] || fail "expected '$expected' but got '$actual'"
}

DEFAULT_EVENTS=$REPO_ROOT/.local/reports/friction/events.jsonl
DEFAULT_INDEX=$REPO_ROOT/.local/reports/friction/INDEX.md
rm -rf "$REPO_ROOT/.local/reports/friction"

cd "$REPO_ROOT"

OUTPUT=$("$ROOT/scripts/report-friction.sh" \
  --title "Dispatch role slug mismatch" \
  --instruction-source "SKILL.md:160" \
  --instruction-text "Use the documented dispatch role slug from the skill table." \
  --action-taken "Ran mpcr protocol dispatch --role architecture with Bearer ghp_leakedtoken1234567890abcdef12345678." \
  --expected-outcome "The CLI returns the architecture prompt." \
  --actual-outcome "error: unknown dispatch role: architecture" \
  --interpretation "I treated the visible table label as the CLI slug." \
  --anchor-kind file \
  --anchor-path "$ROOT/SKILL.md" \
  --anchor-line 160)

printf '%s\n' "$OUTPUT" | grep -q "^FRICTION_EVENTS_FILE=$DEFAULT_EVENTS$" || fail "unexpected default events file output"
printf '%s\n' "$OUTPUT" | grep -q "^FRICTION_INDEX_FILE=$DEFAULT_INDEX$" || fail "unexpected default index file output"

assert_file "$DEFAULT_EVENTS"
assert_file "$DEFAULT_INDEX"
assert_contains '"event_id":"evt-0001"' "$DEFAULT_EVENTS"
assert_contains '"agent_name":""' "$DEFAULT_EVENTS"
assert_contains '"agent_kind":""' "$DEFAULT_EVENTS"
assert_contains '"role":""' "$DEFAULT_EVENTS"
assert_contains '"provenance_source":"unspecified"' "$DEFAULT_EVENTS"
assert_contains '"anchors":[{' "$DEFAULT_EVENTS"
assert_contains '"path":"'"$ROOT"'/SKILL.md"' "$DEFAULT_EVENTS"
if grep -q 'ghp_leakedtoken' "$DEFAULT_EVENTS"; then
  fail "token leaked into events.jsonl"
fi
assert_contains '"redaction_applied":true' "$DEFAULT_EVENTS"
assert_contains 'Bearer [REDACTED]' "$DEFAULT_EVENTS"
assert_contains '**Entries:** 1' "$DEFAULT_INDEX"
assert_contains '_No explicit provenance recorded._' "$DEFAULT_INDEX"

# A second event from another agent should append to the same repo-scoped file.
"$ROOT/scripts/report-friction.sh" \
  --agent subagent-a \
  --agent-kind subagent \
  --role research \
  --title "Missing CI helper" \
  --instruction-source "AGENTS.md:18" \
  --instruction-text "Run scripts/ci-check.sh to inspect current status." \
  --action-taken "Ran rg --files scripts and confirmed ci-check.sh does not exist." \
  --expected-outcome "The repository contains scripts/ci-check.sh." \
  --actual-outcome "No such script exists in the repository." \
  --interpretation "The instruction looked like a direct path to an existing helper."

[ "$(wc -l <"$DEFAULT_EVENTS" | tr -d ' ')" -eq 2 ] || fail "expected two events in default file"
assert_contains '**Entries:** 2' "$DEFAULT_INDEX"
assert_contains '`instructions/missing/continued` - 1' "$DEFAULT_INDEX"

# Query filters should work directly against the canonical event file.
QUERY_JSON=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --agent-kind subagent --format json)
printf '%s\n' "$QUERY_JSON" | grep -q '"agent_kind": "subagent"' || fail "query should return subagent event"
printf '%s\n' "$QUERY_JSON" | grep -q '"title": "Missing CI helper"' || fail "query should include matching title"

QUERY_MD=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --anchor-path "$ROOT/SKILL.md" --format md)
printf '%s\n' "$QUERY_MD" | grep -q 'Dispatch role slug mismatch' || fail "anchor-path query should match first event"

# JSON via stdin remains supported, but it is not the primary path.
cat <<'EOF' | "$ROOT/scripts/report-friction.sh" --events-file "$DEFAULT_EVENTS" --from-json -
{
  "title": "stdin ingest smoke",
  "instruction_source": "test",
  "instruction_text": "Load event fields from stdin exactly once.",
  "action_taken": "Reported friction with --from-json -.",
  "expected_outcome": "The tool accepts structured input over stdin.",
  "actual_outcome": "The event was loaded from stdin and recorded.",
  "interpretation": "stdin is the safest structured path when JSON is needed.",
  "agent_name": "subagent-b",
  "agent_kind": "subagent",
  "role": "verification"
}
EOF
[ "$(wc -l <"$DEFAULT_EVENTS" | tr -d ' ')" -eq 3 ] || fail "stdin JSON should append a third event"
assert_contains '"title":"stdin ingest smoke"' "$DEFAULT_EVENTS"

# stdin JSON should preserve shell-sensitive text literally.
cat <<'EOF' | "$ROOT/scripts/report-friction.sh" --events-file "$DEFAULT_EVENTS" --from-json -
{
  "title": "shell-sensitive payload smoke",
  "instruction_source": "test",
  "instruction_text": "Record literal shell-sensitive content safely.",
  "action_taken": "Passed `ghost-router` and $(whoami) through stdin JSON instead of direct shell flags.",
  "expected_outcome": "The stored event preserves literal backticks and dollar-paren text.",
  "actual_outcome": "The event preserved `ghost-router` and $(whoami) verbatim.",
  "interpretation": "stdin JSON is the safe path when payload text would otherwise trigger shell parsing."
}
EOF
[ "$(wc -l <"$DEFAULT_EVENTS" | tr -d ' ')" -eq 4 ] || fail "shell-sensitive stdin JSON should append a fourth event"
assert_contains '`ghost-router`' "$DEFAULT_EVENTS"
assert_contains '$(whoami)' "$DEFAULT_EVENTS"

# Invalid JSON should produce concise diagnostics with no stack trace.
INVALID_STDERR=$(mktemp)
INVALID_JSON=$(mktemp)
printf '%s\n' '{"title":"bad",}' >"$INVALID_JSON"
set +e
"$ROOT/scripts/report-friction.sh" --events-file "$DEFAULT_EVENTS" --from-json "$INVALID_JSON" > /dev/null 2>"$INVALID_STDERR"
STATUS=$?
set -e
[ "$STATUS" -ne 0 ] || fail "invalid JSON should fail"
assert_contains 'Invalid JSON input for --from-json' "$INVALID_STDERR"
assert_contains 'Line 1, column' "$INVALID_STDERR"
if grep -qi 'traceback' "$INVALID_STDERR"; then
  fail "invalid JSON should not emit a stack trace"
fi

# Missing required narrative fields should fail cleanly.
SCHEMA_STDERR=$(mktemp)
SCHEMA_JSON=$(mktemp)
cat <<'EOF' >"$SCHEMA_JSON"
{
  "title": "schema fail",
  "instruction_source": "test",
  "instruction_text": "   ",
  "action_taken": "did something",
  "expected_outcome": "expected",
  "actual_outcome": "actual",
  "interpretation": "interp"
}
EOF
set +e
"$ROOT/scripts/report-friction.sh" --events-file "$DEFAULT_EVENTS" --from-json "$SCHEMA_JSON" > /dev/null 2>"$SCHEMA_STDERR"
STATUS=$?
set -e
[ "$STATUS" -ne 0 ] || fail "invalid schema should fail"
assert_contains 'Invalid friction payload for --from-json' "$SCHEMA_STDERR"
assert_contains 'field must not be blank: instruction_text' "$SCHEMA_STDERR"

# Explicit non-repo target should be honored.
EXPLICIT_DIR=$(mktemp -d)
EXPLICIT_EVENTS=$EXPLICIT_DIR/events.jsonl
"$ROOT/scripts/report-friction.sh" \
  --events-file "$EXPLICIT_EVENTS" \
  --agent external \
  --agent-kind agent \
  --role isolated \
  --title "Explicit file target" \
  --instruction-source "test" \
  --instruction-text "Use the explicitly provided file path." \
  --action-taken "Passed --events-file to the reporter." \
  --expected-outcome "The event is written to the explicit path." \
  --actual-outcome "The event was written to the explicit path." \
  --interpretation "Explicit file targets should override repo defaults."
assert_file "$EXPLICIT_EVENTS"
assert_file "$EXPLICIT_DIR/INDEX.md"
assert_contains '"provenance_source":"explicit"' "$EXPLICIT_EVENTS"

QUERY_NO_PROVENANCE=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --anchor-path "$ROOT/SKILL.md" --format md)
if printf '%s\n' "$QUERY_NO_PROVENANCE" | grep -q '^- Agent:'; then
  fail "query markdown should omit provenance lines when provenance is unspecified"
fi

# If .local is absent, an existing .local* directory should be used.
ALT_REPO=$(mktemp -d)
git init -q "$ALT_REPO"
mkdir -p "$ALT_REPO/.local-test"
ALT_OUTPUT=$(cd "$ALT_REPO" && "$ROOT/scripts/report-friction.sh" \
  --title "Alternate local dir" \
  --instruction-source "test" \
  --instruction-text "Use an existing .local* directory when .local is absent." \
  --action-taken "Reported friction from a repo containing only .local-test." \
  --expected-outcome "The default events file lands under .local-test/reports/friction." \
  --actual-outcome "The tool selected the existing .local-test directory." \
  --interpretation "An existing .local* directory should win over creating a new .local.")
assert_equals "FRICTION_EVENTS_FILE=$ALT_REPO/.local-test/reports/friction/events.jsonl" "$(printf '%s\n' "$ALT_OUTPUT" | sed -n '1p')"
assert_file "$ALT_REPO/.local-test/reports/friction/events.jsonl"

# Outside a repo, the default should use the system temp root.
TEMP_ROOT=$(python3 - <<'PY'
import tempfile
print(tempfile.gettempdir())
PY
)
NON_REPO_DIR=$(mktemp -d)
NON_REPO_OUTPUT=$(cd "$NON_REPO_DIR" && "$ROOT/scripts/report-friction.sh" \
  --title "Non-repo fallback" \
  --instruction-source "test" \
  --instruction-text "Use the system temp root outside git repos." \
  --action-taken "Reported friction from a directory without .git." \
  --expected-outcome "The default events file lands under the system temp directory." \
  --actual-outcome "The tool selected a deterministic system-temp path." \
  --interpretation "Outside git, the temp-root fallback should be used.")
printf '%s\n' "$NON_REPO_OUTPUT" | grep -q "^FRICTION_EVENTS_FILE=$TEMP_ROOT/agent-friction/" || fail "non-repo fallback should use the system temp root"

rm -f "$INVALID_STDERR" "$INVALID_JSON" "$SCHEMA_STDERR" "$SCHEMA_JSON"
rm -rf "$EXPLICIT_DIR" "$ALT_REPO" "$NON_REPO_DIR"
