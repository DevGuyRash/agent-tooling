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

DEFAULT_EVENTS=$REPO_ROOT/.local/reports/friction/events.jsonl
DEFAULT_INDEX=$REPO_ROOT/.local/reports/friction/INDEX.md
rm -rf "$REPO_ROOT/.local/reports/friction"

cd "$REPO_ROOT"

# --- Test 1: Basic event with source fields and token redaction ---
OUTPUT=$("$ROOT/scripts/report-friction.sh" \
  --title "Dispatch role slug mismatch" \
  --source-type file \
  --source-ref "$ROOT/SKILL.md" \
  --source-line 160 \
  --instruction-text "Use mpcr protocol dispatch --role <ROLE> to get the architecture prompt." \
  --action-taken "I opened SKILL.md at line 160 and found the dispatch table. I ran: mpcr protocol dispatch --role architecture with Bearer ghp_leakedtoken1234567890abcdef12345678." \
  --expected-outcome "The CLI would resolve 'architecture' as a valid dispatch role slug and return the architecture prompt text." \
  --actual-outcome "The command exited with: error: unknown dispatch role: architecture. No prompt text was returned and the process exited non-zero." \
  --reading "The dispatch table lists 'Architecture' in the Role column. I read that label as the literal CLI slug because the instruction used '<ROLE>' as a placeholder and the column header was 'Role'. Given no separate mapping between display labels and CLI slugs, inferring label-equals-slug was the natural reading." \
  --hindsight "Confirm the exact CLI slug via --list-roles or similar before invoking a dispatch role from a display-name table.")

printf '%s\n' "$OUTPUT" | grep -q "^FRICTION_EVENTS_FILE=$DEFAULT_EVENTS$" || fail "unexpected default events file output"
printf '%s\n' "$OUTPUT" | grep -q "^FRICTION_INDEX_FILE=$DEFAULT_INDEX$" || fail "unexpected default index file output"
printf '%s\n' "$OUTPUT" | grep -q "^FRICTION_EVENT_ID=evt-0001$" || fail "should output event_id"
printf '%s\n' "$OUTPUT" | grep -q "add-tags evt-0001" || fail "should include --add-tags helper in output"

assert_file "$DEFAULT_EVENTS"
assert_file "$DEFAULT_INDEX"
assert_contains '"event_id":"evt-0001"' "$DEFAULT_EVENTS"
assert_contains '"schema_version":"3.0.0"' "$DEFAULT_EVENTS"
assert_contains '"provenance_source":"unspecified"' "$DEFAULT_EVENTS"
# Sources array replaces anchors + instruction_source
assert_contains '"sources":[{' "$DEFAULT_EVENTS"
assert_contains '"type":"file"' "$DEFAULT_EVENTS"
assert_contains '"ref":"'"$ROOT"'/SKILL.md"' "$DEFAULT_EVENTS"
assert_contains '"line":160' "$DEFAULT_EVENTS"
# Token redaction still works
if grep -q 'ghp_leakedtoken' "$DEFAULT_EVENTS"; then
  fail "token leaked into events.jsonl"
fi
assert_contains 'Bearer [REDACTED]' "$DEFAULT_EVENTS"
# Removed fields should NOT be present
assert_not_contains '"title_line"' "$DEFAULT_EVENTS"
assert_not_contains '"quick_capture"' "$DEFAULT_EVENTS"
assert_not_contains '"force_capture"' "$DEFAULT_EVENTS"
assert_not_contains '"redaction_applied"' "$DEFAULT_EVENTS"
assert_not_contains '"privacy_tier"' "$DEFAULT_EVENTS"
assert_not_contains '"incident_status"' "$DEFAULT_EVENTS"
assert_not_contains '"evidence_type"' "$DEFAULT_EVENTS"
assert_not_contains '"instruction_source"' "$DEFAULT_EVENTS"
assert_not_contains '"anchors"' "$DEFAULT_EVENTS"
assert_not_contains '"tags_csv"' "$DEFAULT_EVENTS"
# Tags start empty (agent-curated via --add-tags)
assert_contains '"tags":[]' "$DEFAULT_EVENTS"
# Numeric confidence and guidance_quality
assert_contains '"confidence":' "$DEFAULT_EVENTS"
assert_contains '"guidance_quality":' "$DEFAULT_EVENTS"
assert_contains '**Entries:** 1' "$DEFAULT_INDEX"
assert_contains '**Index rebuilt:**' "$DEFAULT_INDEX"
assert_contains '**Earliest event:**' "$DEFAULT_INDEX"
assert_contains '**Latest event:**' "$DEFAULT_INDEX"
assert_not_contains '**Generated:**' "$DEFAULT_INDEX"

# --- Test 2: Multi-agent convergence ---
"$ROOT/scripts/report-friction.sh" \
  --agent subagent-a \
  --agent-kind subagent \
  --role research \
  --title "Missing CI helper" \
  --source-type file \
  --source-ref "AGENTS.md" \
  --source-line 18 \
  --instruction-text "Run scripts/ci-check.sh to inspect current status." \
  --action-taken "I read AGENTS.md line 18 which directed me to run scripts/ci-check.sh. I searched using rg --files scripts and found no match for ci-check.sh or any variant." \
  --expected-outcome "The scripts/ directory would contain ci-check.sh as an executable helper, consistent with the imperative instruction." \
  --actual-outcome "rg --files scripts returned no match for ci-check.sh or any variant. The file is completely absent from the repository." \
  --reading "The instruction at line 18 uses a concrete path in imperative form: 'Run scripts/ci-check.sh'. There is no conditional qualifier or note about generating the script first. Imperative instructions with literal paths normally refer to existing artifacts, so I treated this as a pre-existing helper." \
  --hindsight "Before running any imperative script path, verify the file exists with ls or find rather than assuming it pre-exists."

[ "$(wc -l <"$DEFAULT_EVENTS" | tr -d ' ')" -eq 2 ] || fail "expected two events in default file"
assert_contains '**Entries:** 2' "$DEFAULT_INDEX"

# --- Test 3: Sparse output — optional empty fields omitted ---
# The second event has no command, tool_name, stderr, etc. — these should be absent
SECOND_EVENT=$(sed -n '2p' "$DEFAULT_EVENTS")
case "$SECOND_EVENT" in
  *'"command":'*) fail "sparse output: empty command should be omitted" ;;
  *'"tool_name":'*) fail "sparse output: empty tool_name should be omitted" ;;
  *'"stderr":'*) fail "sparse output: empty stderr should be omitted" ;;
  *'"stdout_excerpt":'*) fail "sparse output: empty stdout_excerpt should be omitted" ;;
  *'"workaround_used":'*) fail "sparse output: false workaround_used should be omitted" ;;
  *'"exit_code":'*) fail "sparse output: zero exit_code should be omitted" ;;
  *'"retries_lost":'*) fail "sparse output: zero retries_lost should be omitted" ;;
  *'"minutes_lost":'*) fail "sparse output: zero minutes_lost should be omitted" ;;
esac

# --- Test 4: Query by source-ref ---
QUERY_JSON=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --agent-kind subagent --format json)
printf '%s\n' "$QUERY_JSON" | grep -q '"agent_kind": "subagent"' || printf '%s\n' "$QUERY_JSON" | grep -q '"agent_kind":"subagent"' || fail "query should return subagent event"

QUERY_MD=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --source-ref "$ROOT/SKILL.md" --format md)
printf '%s\n' "$QUERY_MD" | grep -q 'Dispatch role slug mismatch' || fail "source-ref query should match first event"

# --- Test 5: JSON stdin with v3 sources array ---
cat <<'EOF' | "$ROOT/scripts/report-friction.sh" --events-file "$DEFAULT_EVENTS" --from-json -
{
  "title": "stdin ingest smoke",
  "instruction_text": "WHEN payload text contains shell-sensitive content THEN you SHOULD prefer stdin JSON.",
  "action_taken": "I constructed a JSON payload containing multiple sources and piped it to report-friction.sh via --from-json - to test the structured input path.",
  "expected_outcome": "The tool would accept the JSON payload over stdin, parse the sources array, and append a valid event to events.jsonl.",
  "actual_outcome": "The event was loaded from stdin, all fields were parsed correctly, and the event was appended to the canonical events.jsonl file.",
  "reading": "The SKILL.md documentation recommends stdin JSON for shell-sensitive text. I tested this path to verify it handles multi-source payloads correctly. The documentation's recommendation is accurate: stdin avoids shell-escaping hazards that affect direct flags.",
  "hindsight": "Use --from-json - as the default path for any payload with special characters, multiline text, or multiple sources.",
  "agent_name": "subagent-b",
  "agent_kind": "subagent",
  "role": "verification",
  "sources": [
    {"type": "documentation", "ref": "test", "label": "smoke test source"},
    {"type": "url", "ref": "https://example.com/docs", "selector": "#section-3"}
  ]
}
EOF
[ "$(wc -l <"$DEFAULT_EVENTS" | tr -d ' ')" -eq 3 ] || fail "stdin JSON should append a third event"
assert_contains '"title":"stdin ingest smoke"' "$DEFAULT_EVENTS"
# Multiple sources preserved
THIRD_EVENT=$(sed -n '3p' "$DEFAULT_EVENTS")
# Sources from --from-json come through Python json.dumps which may add spaces
printf '%s\n' "$THIRD_EVENT" | grep -q 'url' || fail "second source should be preserved"
printf '%s\n' "$THIRD_EVENT" | grep -q 'https://example.com/docs' || fail "url source ref should be preserved"

# --- Test 7: Shell-sensitive stdin JSON ---
cat <<'EOF' | "$ROOT/scripts/report-friction.sh" --events-file "$DEFAULT_EVENTS" --from-json -
{
  "title": "shell-sensitive payload smoke",
  "instruction_text": "WHEN payload text contains backticks or dollar-paren THEN you SHOULD prefer stdin JSON.",
  "action_taken": "I constructed a JSON payload containing shell-sensitive characters: backtick-quoted `ghost-router` and dollar-paren $(whoami). I piped this to report-friction.sh via --from-json - instead of using direct flags.",
  "expected_outcome": "The stored event would preserve the literal backtick and dollar-paren text verbatim, without any shell expansion or escaping damage.",
  "actual_outcome": "The event preserved `ghost-router` and $(whoami) verbatim in the stored JSONL. No shell expansion occurred on either construct.",
  "reading": "The SKILL.md documentation recommends stdin JSON for shell-sensitive text. Direct shell flags would have expanded $(whoami) to the current username and potentially mishandled backticks. The stdin path bypasses shell parsing entirely, confirming the documentation's recommendation.",
  "hindsight": "Default to --from-json - whenever the payload contains backticks, dollar-paren constructs, or other shell-special characters.",
  "sources": [{"type": "documentation", "ref": "test"}]
}
EOF
[ "$(wc -l <"$DEFAULT_EVENTS" | tr -d ' ')" -eq 4 ] || fail "shell-sensitive stdin JSON should append a fourth event"
assert_contains '`ghost-router`' "$DEFAULT_EVENTS"
assert_contains '$(whoami)' "$DEFAULT_EVENTS"

# --- Test 8: Invalid JSON diagnostics ---
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

# --- Test 9: Missing required fields fail cleanly ---
SCHEMA_STDERR=$(mktemp)
SCHEMA_JSON=$(mktemp)
cat <<'EOF' >"$SCHEMA_JSON"
{
  "title": "schema fail",
  "instruction_text": "   ",
  "action_taken": "I attempted to report a friction event with a blank instruction_text to test the schema validation enforcement.",
  "expected_outcome": "The tool would reject the payload because instruction_text is blank (whitespace only), violating the required-field constraint.",
  "actual_outcome": "The tool rejected the payload with a clear error message identifying instruction_text as the problem field.",
  "reading": "Required narrative fields must contain substantive text, not just whitespace. The validator correctly catches blank values before the event reaches the canonical file, preventing noise entries from polluting the event stream.",
  "hindsight": "Always supply substantive text for all required narrative fields before invoking the reporter.",
  "sources": [{"type": "documentation", "ref": "test"}]
}
EOF
set +e
"$ROOT/scripts/report-friction.sh" --events-file "$DEFAULT_EVENTS" --from-json "$SCHEMA_JSON" > /dev/null 2>"$SCHEMA_STDERR"
STATUS=$?
set -e
[ "$STATUS" -ne 0 ] || fail "blank instruction_text should fail"
assert_contains 'field must not be blank: instruction_text' "$SCHEMA_STDERR"

# --- Test 10: Narrative minimum length validation ---
SHORT_STDERR=$(mktemp)
SHORT_JSON=$(mktemp)
cat <<'EOF' >"$SHORT_JSON"
{
  "instruction_text": "Use the slug.",
  "action_taken": "Ran the command.",
  "expected_outcome": "It worked.",
  "actual_outcome": "Error happened.",
  "reading": "It was wrong.",
  "hindsight": "Fix it.",
  "sources": [{"type": "documentation", "ref": "test"}]
}
EOF
set +e
"$ROOT/scripts/report-friction.sh" --events-file "$DEFAULT_EVENTS" --from-json "$SHORT_JSON" > /dev/null 2>"$SHORT_STDERR"
STATUS=$?
set -e
[ "$STATUS" -ne 0 ] || fail "short narrative fields should fail length validation"
assert_contains 'must be at least' "$SHORT_STDERR"

# --- Test 11: Auto-title includes [surface/mode] prefix ---
"$ROOT/scripts/report-friction.sh" \
  --events-file "$DEFAULT_EVENTS" \
  --source-type documentation \
  --source-ref "test" \
  --instruction-text "Use mpcr protocol dispatch --role <ROLE> to get the architecture prompt." \
  --action-taken "I opened SKILL.md and found the dispatch table. I ran: mpcr protocol dispatch --role architecture from the repo root." \
  --expected-outcome "The CLI would resolve 'architecture' as a valid dispatch role slug and return the architecture prompt text." \
  --actual-outcome "The command exited with: error: unknown dispatch role: architecture. No prompt text was returned and the process exited non-zero." \
  --reading "The dispatch table lists 'Architecture' in the Role column. I read that label as the literal CLI slug because the instruction used '<ROLE>' as a placeholder. Given no separate mapping between display labels and CLI slugs, inferring label-equals-slug was the natural reading." \
  --hindsight "Confirm the exact CLI slug via --list-roles or similar before invoking a dispatch role from a display-name table."

LAST_EVENT=$(tail -1 "$DEFAULT_EVENTS")
printf '%s\n' "$LAST_EVENT" | grep -q '"title":"\[' || fail "auto-title should start with [surface/mode] prefix"

# --- Test 12: Expanded query filters ---
FILTER_OUTPUT=$("$ROOT/scripts/report-friction.sh" \
  --events-file "$DEFAULT_EVENTS" \
  --title "filter coverage event" \
  --source-type documentation \
  --source-ref "test" \
  --instruction-text "Use the structured jq report path for diagnostics." \
  --action-taken "I ran the query path with a structured payload, attached tool metadata, and used a temporary workaround so each expanded filter had one deterministic target event." \
  --expected-outcome "The event would be written with explicit tool, owner, component, exit-code, confidence, guidance, and workaround metadata for query validation." \
  --actual-outcome "The command degraded but continued, and the workaround let the run finish with exit code 7." \
  --reading "I used this event to verify the expanded query filters. The wording includes the phrase structured payload so the text search can match it directly." \
  --hindsight "Use a purpose-built event when validating filter dimensions so each flag has one deterministic target." \
  --surface skill \
  --mode schema \
  --run-effect degraded \
  --tool-name jq \
  --owner-hint skill-owner \
  --component-hint query-engine \
  --workaround-used true \
  --exit-code 7 \
  --confidence high \
  --guidance-quality partial)
FILTER_EVENT_ID=$(printf '%s\n' "$FILTER_OUTPUT" | sed -n 's/^FRICTION_EVENT_ID=//p' | sed -n '1p')
[ -n "$FILTER_EVENT_ID" ] || fail "filter coverage event should return an event id"
"$ROOT/scripts/report-friction.sh" --add-tags "$FILTER_EVENT_ID" "jq,report,filter-smoke" --events-file "$DEFAULT_EVENTS" >/dev/null
FILTER_QUERY=$("$ROOT/scripts/query-friction.sh" \
  --events-file "$DEFAULT_EVENTS" \
  --surface skill \
  --mode schema \
  --run-effect degraded \
  --tool-name jq \
  --owner-hint skill-owner \
  --component-hint query-engine \
  --workaround \
  --exit-code 7 \
  --confidence-min 4 \
  --confidence-max 4 \
  --guidance-min 3 \
  --guidance-max 3 \
  --text "structured payload" \
  --tag report \
  --format json)
printf '%s\n' "$FILTER_QUERY" | jq -e 'length == 1' >/dev/null || fail "expanded query filters should isolate one matching event"
printf '%s\n' "$FILTER_QUERY" | grep -q 'filter coverage event' || fail "expanded query filters should return the filter coverage event"
EMPTY_QUERY_MD=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --tag tag-that-will-never-match --format md)
printf '%s\n' "$EMPTY_QUERY_MD" | grep -q '^- Entries: 0$' || fail "empty query markdown should report zero entries"

# --- Test 13: Explicit non-repo target ---
EXPLICIT_DIR=$(mktemp -d)
EXPLICIT_EVENTS=$EXPLICIT_DIR/events.jsonl
"$ROOT/scripts/report-friction.sh" \
  --events-file "$EXPLICIT_EVENTS" \
  --agent external \
  --agent-kind agent \
  --role isolated \
  --title "Explicit file target" \
  --source-type documentation \
  --source-ref "test" \
  --instruction-text "Use the explicitly provided --events-file path for the events output." \
  --action-taken "I passed --events-file with an explicit temporary directory path to the reporter to verify that explicit targets override repo defaults." \
  --expected-outcome "The event would be written to the explicit path rather than the default repo-scoped location, and INDEX.md would be created adjacent to it." \
  --actual-outcome "The event was written to the explicit path and INDEX.md was created in the same directory as expected." \
  --reading "The --events-file flag is documented as an explicit override for the canonical target resolution. I used it to write to a temporary directory to confirm that the override mechanism works. The flag takes precedence over git-repo-root detection and .local directory scanning." \
  --hindsight "Use --events-file explicitly in CI or isolated test contexts to prevent accidental writes to the repo default stream."
assert_file "$EXPLICIT_EVENTS"
assert_file "$EXPLICIT_DIR/INDEX.md"
assert_contains '"provenance_source":"explicit"' "$EXPLICIT_EVENTS"

# --- Test 14: Alternate .local* directory ---
ALT_REPO=$(mktemp -d)
git init -q "$ALT_REPO"
mkdir -p "$ALT_REPO/.local-test"
ALT_OUTPUT=$(cd "$ALT_REPO" && "$ROOT/scripts/report-friction.sh" \
  --title "Alternate local dir" \
  --source-type documentation \
  --source-ref "test" \
  --instruction-text "WHEN .local is absent but another .local* directory exists THEN use the existing local area." \
  --action-taken "I created a git repo with only .local-test (no .local) and ran report-friction.sh from inside it to verify the fallback path resolution." \
  --expected-outcome "The tool would detect the existing .local-test directory and write events.jsonl under .local-test/reports/friction/ rather than creating a new .local directory." \
  --actual-outcome "The tool correctly selected .local-test as the local area and wrote the event to .local-test/reports/friction/events.jsonl." \
  --reading "The canonical target resolution docs specify that if .local is absent, the tool should use the first existing .local* directory. This preserves the repo's existing local state layout rather than creating a competing .local directory alongside an existing .local-test." \
  --hindsight "Document the .local* precedence rule clearly so agents do not create a redundant .local alongside an existing .local-test.")
assert_equals "FRICTION_EVENTS_FILE=$ALT_REPO/.local-test/reports/friction/events.jsonl" "$(printf '%s\n' "$ALT_OUTPUT" | sed -n '1p')"
assert_file "$ALT_REPO/.local-test/reports/friction/events.jsonl"

# --- Test 15: Path-with-spaces discovery ---
SPACE_PARENT=$(mktemp -d)
SPACE_REPO="$SPACE_PARENT/repo with spaces"
mkdir -p "$SPACE_REPO"
git init -q "$SPACE_REPO"
SPACE_OUTPUT=$(cd "$SPACE_REPO" && "$ROOT/scripts/report-friction.sh" \
  --title "Space path repo" \
  --source-type documentation \
  --source-ref "test" \
  --instruction-text "Use scan-dirs with paths that may contain spaces." \
  --action-taken "I created a git repo whose path contains spaces and ran report-friction.sh inside it so the generated events file would live under a space-containing path." \
  --expected-outcome "The reporter and later scan-dirs queries would preserve the path as a single argument and discover the resulting events file without splitting on whitespace." \
  --actual-outcome "The reporter wrote the event under the repo path containing spaces and the later scan-dirs tests can use that repo as a quoting fixture." \
  --reading "Space-containing paths are a common shell quoting failure mode. I used a real repo path with spaces so the smoke test exercises the exact discovery path rather than a synthetic unit-level approximation." \
  --hindsight "Keep at least one path-with-spaces fixture in the smoke suite because quoting regressions tend to reappear when argument parsing changes.")
assert_equals "FRICTION_EVENTS_FILE=$SPACE_REPO/.local/reports/friction/events.jsonl" "$(printf '%s\n' "$SPACE_OUTPUT" | sed -n '1p')"
assert_file "$SPACE_REPO/.local/reports/friction/events.jsonl"

# --- Test 15b: Path-with-quote discovery ---
QUOTE_PARENT=$(mktemp -d)
QUOTE_REPO="$QUOTE_PARENT/repo with 'quote"
mkdir -p "$QUOTE_REPO"
git init -q "$QUOTE_REPO"
QUOTE_OUTPUT=$(cd "$QUOTE_REPO" && "$ROOT/scripts/report-friction.sh" \
  --title "Quote path repo" \
  --source-type documentation \
  --source-ref "test" \
  --instruction-text "Use scan-dirs with paths that may contain shell-sensitive quote characters." \
  --action-taken "I created a git repo whose path contains a literal single quote and ran report-friction.sh inside it so generate-report.sh has to pass the path through without eval-based shell reconstruction." \
  --expected-outcome "The reporter and later scan-dirs report generation would preserve the quoted path as data, not shell syntax, and discover the resulting events file correctly." \
  --actual-outcome "The reporter wrote the event under the repo path containing a single quote so the later scan-dirs report tests can verify the hardened invocation path." \
  --reading "A single quote in a filesystem path is the sharpest edge for shell-constructed command strings. This fixture exists specifically to verify that generate-report.sh now passes arguments directly instead of rebuilding them with eval." \
  --hindsight "Keep one quote-containing path fixture in the smoke suite whenever shell argument passing changes around the report generator.")
assert_equals "FRICTION_EVENTS_FILE=$QUOTE_REPO/.local/reports/friction/events.jsonl" "$(printf '%s\n' "$QUOTE_OUTPUT" | sed -n '1p')"
assert_file "$QUOTE_REPO/.local/reports/friction/events.jsonl"

# --- Test 16: Report generator ---
INDEX_REPORT=$("$ROOT/scripts/generate-report.sh" --events-file "$DEFAULT_EVENTS" --report-type index)
printf '%s\n' "$INDEX_REPORT" | grep -q '\*\*Index rebuilt:\*\*' || fail "index report should show the rebuilt label"
printf '%s\n' "$INDEX_REPORT" | grep -q '## Top Sources' || fail "index report should include top sources"
printf '%s\n' "$INDEX_REPORT" | grep -q '## Run Effect Summary' || fail "index report should include run effect summary"
INDEX_JSON=$("$ROOT/scripts/generate-report.sh" --events-file "$DEFAULT_EVENTS" --report-type index --format json)
printf '%s\n' "$INDEX_JSON" | jq -e '.report_type == "index" and .entries >= 1 and (.top_sources | length) >= 1' >/dev/null || fail "index json should include structured counts and sources"

CROSS_REPORT=$("$ROOT/scripts/generate-report.sh" --scan-dirs "$REPO_ROOT" "$ALT_REPO" "$SPACE_PARENT" "$QUOTE_PARENT" --report-type cross-repo)
printf '%s\n' "$CROSS_REPORT" | grep -q '\*\*Repos scanned:\*\* 4' || fail "cross-repo report should include all discovered repos"
printf '%s\n' "$CROSS_REPORT" | grep -q "$ALT_REPO" || fail "cross-repo report should list the alternate repo"
printf '%s\n' "$CROSS_REPORT" | grep -q "$SPACE_REPO" || fail "cross-repo report should preserve repos with spaces in their path"
printf '%s\n' "$CROSS_REPORT" | grep -q "$QUOTE_REPO" || fail "cross-repo report should preserve repos with quote characters in their path"
CROSS_JSON=$("$ROOT/scripts/generate-report.sh" --scan-dirs "$REPO_ROOT" "$ALT_REPO" "$SPACE_PARENT" "$QUOTE_PARENT" --report-type cross-repo --format json)
printf '%s\n' "$CROSS_JSON" | jq -e '.repos_scanned == 4 and (.repos | length) == 4 and .total_entries >= 4' >/dev/null || fail "cross-repo json should report all discovered repos"

PER_REPO_REPORT=$("$ROOT/scripts/generate-report.sh" --scan-dirs "$REPO_ROOT" "$ALT_REPO" "$SPACE_PARENT" "$QUOTE_PARENT" --report-type per-repo)
printf '%s\n' "$PER_REPO_REPORT" | grep -q '# Per-Repo Friction Report' || fail "per-repo report should render markdown"
printf '%s\n' "$PER_REPO_REPORT" | grep -q "$ALT_REPO" || fail "per-repo report should include the alternate repo section"
printf '%s\n' "$PER_REPO_REPORT" | grep -q "$SPACE_REPO" || fail "per-repo report should include the repo with spaces"
printf '%s\n' "$PER_REPO_REPORT" | grep -q "$QUOTE_REPO" || fail "per-repo report should include the repo with quote characters"
PER_REPO_JSON=$("$ROOT/scripts/generate-report.sh" --scan-dirs "$REPO_ROOT" "$ALT_REPO" "$SPACE_PARENT" "$QUOTE_PARENT" --report-type per-repo --format json)
printf '%s\n' "$PER_REPO_JSON" | jq -e '.repos == 4 and (.repo_summaries | length) == 4 and all(.repo_summaries[]; (.entries | type) == "number")' >/dev/null || fail "per-repo json should include one structured summary per repo"

TIMESERIES_JSON=$("$ROOT/scripts/generate-report.sh" --scan-dirs "$REPO_ROOT" "$ALT_REPO" "$SPACE_PARENT" "$QUOTE_PARENT" --report-type timeseries --group-by surface --format json)
printf '%s\n' "$TIMESERIES_JSON" | jq -e '.group_by == "surface"' >/dev/null || fail "timeseries json should record the group-by dimension"
printf '%s\n' "$TIMESERIES_JSON" | jq -e '(.rows | length) > 0' >/dev/null || fail "timeseries json should include at least one row"
printf '%s\n' "$TIMESERIES_JSON" | jq -e '(.columns | length) > 0' >/dev/null || fail "timeseries json should expose grouped columns"

EMPTY_CROSS_REPORT=$("$ROOT/scripts/generate-report.sh" --events-file "$DEFAULT_EVENTS" --report-type cross-repo --tag tag-that-will-never-match)
printf '%s\n' "$EMPTY_CROSS_REPORT" | grep -q '_No repos matched the selected filters._' || fail "empty cross-repo report should render a clear empty-state message"
EMPTY_PER_REPO_REPORT=$("$ROOT/scripts/generate-report.sh" --events-file "$DEFAULT_EVENTS" --report-type per-repo --tag tag-that-will-never-match)
printf '%s\n' "$EMPTY_PER_REPO_REPORT" | grep -q '_No repos matched the selected filters._' || fail "empty per-repo report should render a clear empty-state message"
EMPTY_TIMESERIES_REPORT=$("$ROOT/scripts/generate-report.sh" --events-file "$DEFAULT_EVENTS" --report-type timeseries --tag tag-that-will-never-match)
printf '%s\n' "$EMPTY_TIMESERIES_REPORT" | grep -q '_No dated events matched the selected filters._' || fail "empty timeseries report should render a clear empty-state message"
EMPTY_CROSS_JSON=$("$ROOT/scripts/generate-report.sh" --events-file "$DEFAULT_EVENTS" --report-type cross-repo --tag tag-that-will-never-match --format json)
printf '%s\n' "$EMPTY_CROSS_JSON" | jq -e '.repos_scanned == 0 and .total_entries == 0 and (.repos | length) == 0' >/dev/null || fail "empty cross-repo json should report zero totals"

REPORT_TYPE_STDERR=$(mktemp)
GROUP_BY_STDERR=$(mktemp)
MULTI_INDEX_STDERR=$(mktemp)
QUERY_FORMAT_STDERR=$(mktemp)
MALFORMED_QUERY_STDERR=$(mktemp)
MALFORMED_REPORT_STDERR=$(mktemp)
MALFORMED_INDEX_STDERR=$(mktemp)
MALFORMED_EVENTS=$(mktemp)
PARTIAL_EVENTS=$(mktemp)
BULK_EVENTS=$(mktemp)
SPARSE_SCAN_ROOT=$(mktemp -d)
SPARSE_SCAN_A="$SPARSE_SCAN_ROOT/sparse-a"
SPARSE_SCAN_B="$SPARSE_SCAN_ROOT/sparse-b"

set +e
"$ROOT/scripts/generate-report.sh" --events-file "$DEFAULT_EVENTS" --report-type nonsense >/dev/null 2>"$REPORT_TYPE_STDERR"
RC=$?
set -e
[ "$RC" -ne 0 ] || fail "invalid report type should fail"
assert_contains 'Unsupported report type: nonsense' "$REPORT_TYPE_STDERR"

set +e
"$ROOT/scripts/generate-report.sh" --events-file "$DEFAULT_EVENTS" --report-type cross-repo --group-by surface >/dev/null 2>"$GROUP_BY_STDERR"
RC=$?
set -e
[ "$RC" -ne 0 ] || fail "group-by outside timeseries should fail"
assert_contains '--group-by is only supported with --report-type timeseries' "$GROUP_BY_STDERR"

set +e
"$ROOT/scripts/generate-report.sh" --scan-dirs "$REPO_ROOT" "$ALT_REPO" --report-type index >/dev/null 2>"$MULTI_INDEX_STDERR"
RC=$?
set -e
[ "$RC" -ne 0 ] || fail "index report across multiple files should fail"
assert_contains '--report-type index requires exactly one events file' "$MULTI_INDEX_STDERR"

set +e
"$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --format nope >/dev/null 2>"$QUERY_FORMAT_STDERR"
RC=$?
set -e
[ "$RC" -ne 0 ] || fail "invalid query format should fail"
assert_contains 'Unsupported format: nope' "$QUERY_FORMAT_STDERR"

mkdir -p "$SPARSE_SCAN_A/.local/reports/friction" "$SPARSE_SCAN_B/.local/reports/friction"
cat <<'EOF' >"$SPARSE_SCAN_A/.local/reports/friction/events.jsonl"
{"title":"sparse a"}
EOF
cat <<'EOF' >"$SPARSE_SCAN_B/.local/reports/friction/events.jsonl"
{"title":"sparse b"}
EOF
set +e
"$ROOT/scripts/generate-report.sh" --scan-dirs "$SPARSE_SCAN_ROOT" --report-type index >/dev/null 2>"$MULTI_INDEX_STDERR"
RC=$?
set -e
[ "$RC" -ne 0 ] || fail "index report should fail when multiple sparse input files are resolved"
assert_contains '--report-type index requires exactly one events file' "$MULTI_INDEX_STDERR"

# --- Test 17: Malformed and partial events files ---
cat <<'EOF' >"$MALFORMED_EVENTS"
{"title":"ok"}
not-json
EOF

set +e
"$ROOT/scripts/query-friction.sh" --events-file "$MALFORMED_EVENTS" --format json >/dev/null 2>"$MALFORMED_QUERY_STDERR"
RC=$?
set -e
[ "$RC" -ne 0 ] || fail "malformed events file should fail query-friction.sh"
assert_contains 'Invalid JSON in events file at line 2' "$MALFORMED_QUERY_STDERR"

set +e
"$ROOT/scripts/generate-report.sh" --events-file "$MALFORMED_EVENTS" --report-type index >/dev/null 2>"$MALFORMED_REPORT_STDERR"
RC=$?
set -e
[ "$RC" -ne 0 ] || fail "malformed events file should fail generate-report.sh"
assert_contains 'Invalid JSON in events file at line 2' "$MALFORMED_REPORT_STDERR"

set +e
"$ROOT/scripts/build-index.sh" --events-file "$MALFORMED_EVENTS" >/dev/null 2>"$MALFORMED_INDEX_STDERR"
RC=$?
set -e
[ "$RC" -ne 0 ] || fail "malformed events file should fail build-index.sh"
assert_contains 'Invalid JSON in events file at line 2' "$MALFORMED_INDEX_STDERR"

cat <<'EOF' >"$PARTIAL_EVENTS"
{"title":"partial row"}
EOF
PARTIAL_QUERY=$("$ROOT/scripts/query-friction.sh" --events-file "$PARTIAL_EVENTS" --format json)
printf '%s\n' "$PARTIAL_QUERY" | jq -e 'length == 1 and .[0].title == "partial row"' >/dev/null || fail "partial valid rows should still be queryable"
PARTIAL_INDEX_JSON=$("$ROOT/scripts/generate-report.sh" --events-file "$PARTIAL_EVENTS" --report-type index --format json)
printf '%s\n' "$PARTIAL_INDEX_JSON" | jq -e '.entries == 1 and (.category_counts | length) == 0 and (.top_sources | length) == 0' >/dev/null || fail "partial valid rows should still produce a sparse index report"

# --- Test 18: Light larger-stream probe ---
i=1
while [ "$i" -le 250 ]; do
  minute=$((i % 60))
  printf '{"title":"bulk event %s","recorded_at":"2026-03-30T00:%02d:00Z","event_id":"evt-%04d","derived_category":"skill/schema/continued","fingerprint":"fp-%04d","tags":["bulk","load"],"sources":[{"ref":"bulk"}],"repo_root":"/tmp/bulk","events_file":"/tmp/bulk/events.jsonl"}\n' \
    "$i" "$minute" "$i" "$i" >>"$BULK_EVENTS"
  i=$((i + 1))
done
BULK_QUERY=$("$ROOT/scripts/query-friction.sh" --events-file "$BULK_EVENTS" --tag bulk --format json)
printf '%s\n' "$BULK_QUERY" | jq -e 'length == 250' >/dev/null || fail "bulk query should return every tagged synthetic event"
BULK_TIMESERIES=$("$ROOT/scripts/generate-report.sh" --events-file "$BULK_EVENTS" --report-type timeseries --group-by tag --format json)
printf '%s\n' "$BULK_TIMESERIES" | jq -e '.group_by == "tag" and (.columns | index("bulk")) != null and (.columns | index("load")) != null and (.rows | length) == 1 and .rows[0].bulk == 250 and .rows[0].load == 250' >/dev/null || fail "bulk timeseries report should aggregate grouped tag counts correctly"

# --- Test 19: Non-repo temp fallback ---
TEMP_PROBE_DIR=$(mktemp -d)
TEMP_ROOT=$(dirname "$TEMP_PROBE_DIR")
rmdir "$TEMP_PROBE_DIR"
NON_REPO_DIR=$(mktemp -d)
NON_REPO_OUTPUT=$(cd "$NON_REPO_DIR" && "$ROOT/scripts/report-friction.sh" \
  --title "Non-repo fallback" \
  --source-type documentation \
  --source-ref "test" \
  --instruction-text "WHEN outside a git repo THEN fall back to a deterministic system-temp path." \
  --action-taken "I created a non-git temporary directory, changed into it, and ran report-friction.sh without --events-file to verify the temp-root fallback path." \
  --expected-outcome "The tool would detect the absence of a .git directory and fall back to writing events under the system temp directory with a CWD-based hash." \
  --actual-outcome "The tool correctly fell back to a system-temp path under agent-friction/ with a deterministic hash derived from the CWD." \
  --reading "The canonical target resolution docs specify that outside a git repo, the tool uses a deterministic temp-root path based on a hash of the CWD. This ensures events are still written to a stable location even without git context, and that different directories get isolated event streams." \
  --hindsight "When testing outside a git repo, verify the temp fallback path matches expectations before relying on it for event isolation.")
printf '%s\n' "$NON_REPO_OUTPUT" | grep -q "^FRICTION_EVENTS_FILE=$TEMP_ROOT/agent-friction/" || fail "non-repo fallback should use the system temp root"

# --- Test 20: --add-tags patches tags on existing event ---
"$ROOT/scripts/report-friction.sh" --add-tags evt-0001 "instructions,missing,deploy,skaffold" --events-file "$DEFAULT_EVENTS"
FIRST_EVENT=$(sed -n '1p' "$DEFAULT_EVENTS")
printf '%s\n' "$FIRST_EVENT" | grep -q 'instructions' || fail "--add-tags should add tags to evt-0001"
printf '%s\n' "$FIRST_EVENT" | grep -q 'skaffold' || fail "--add-tags should add all specified tags"

# --- Test 20b: --add-tags preserves non-zero failures ---
set +e
"$ROOT/scripts/report-friction.sh" --add-tags evt-9999 "missing-event" --events-file "$DEFAULT_EVENTS" >/dev/null 2>&1
STATUS=$?
set -e
[ "$STATUS" -ne 0 ] || fail "--add-tags should exit non-zero when the event does not exist"

# --- Test 21: Deterministic fingerprints — same source+day = same fingerprint ---
FP_EVENTS=$(mktemp)
"$ROOT/scripts/report-friction.sh" \
  --events-file "$FP_EVENTS" \
  --title "First report" \
  --source-type file \
  --source-ref "AGENTS.md" \
  --instruction-text "Use skaffold run --profile staging to deploy." \
  --action-taken "I ran skaffold run --profile staging from the repo root as directed by AGENTS.md." \
  --expected-outcome "Skaffold would resolve the staging profile and deploy to the staging namespace." \
  --actual-outcome "FATA[0003] profile staging not found in skaffold.yaml" \
  --reading "AGENTS.md names the profile 'staging' with confident imperative wording. I took this as a definitive reference. Only dev and prod profiles exist. The instruction was factually wrong." \
  --hindsight "Cross-check profile names in skaffold.yaml before running any profile-targeted deploy command." \
  >/dev/null
"$ROOT/scripts/report-friction.sh" \
  --events-file "$FP_EVENTS" \
  --title "Second report, different wording" \
  --source-type file \
  --source-ref "AGENTS.md" \
  --instruction-text "Use skaffold run --profile staging to deploy." \
  --action-taken "Following AGENTS.md, I executed skaffold run --profile staging. It failed with a profile-not-found error immediately." \
  --expected-outcome "The staging profile would be found in skaffold.yaml and the deployment would proceed." \
  --actual-outcome "skaffold exited with error: profile staging not found. Only dev and prod are defined." \
  --reading "The instruction named a specific profile that does not exist. I had no reason to doubt it since the wording was imperative and unqualified. The root cause is a documentation error in AGENTS.md." \
  --hindsight "Verify all named profiles exist in skaffold.yaml before trusting an imperative instruction referencing them." \
  >/dev/null
FP1=$(sed -n '1p' "$FP_EVENTS" | jq -r '.fingerprint')
FP2=$(sed -n '2p' "$FP_EVENTS" | jq -r '.fingerprint')
[ "$FP1" = "$FP2" ] || fail "same source+surface+mode+day should produce same fingerprint (got $FP1 vs $FP2)"

# --- Test 22: Different source = different fingerprint ---
"$ROOT/scripts/report-friction.sh" \
  --events-file "$FP_EVENTS" \
  --title "Different source" \
  --source-type file \
  --source-ref "skaffold.yaml" \
  --instruction-text "profiles: [dev, prod] in skaffold.yaml" \
  --action-taken "I inspected skaffold.yaml to find the staging profile. Only dev and prod were defined." \
  --expected-outcome "skaffold.yaml would contain a staging profile matching the AGENTS.md instruction." \
  --actual-outcome "skaffold.yaml defines only dev and prod profiles. No staging profile exists." \
  --reading "The AGENTS.md instruction referenced a profile by name. I checked skaffold.yaml to verify it exists. The discrepancy confirms the instruction is wrong, not the config." \
  --hindsight "Treat any discrepancy between instruction-named profiles and skaffold.yaml content as a documentation bug to escalate." \
  >/dev/null
FP3=$(sed -n '3p' "$FP_EVENTS" | jq -r '.fingerprint')
[ "$FP1" != "$FP3" ] || fail "different source should produce different fingerprint"

# --- Test 23: Categorizer catches common missing/name-resolution phrasing ---
CATEGORIZE_OUTPUT=$("$ROOT/scripts/categorize.sh" \
  --source-ref "AGENTS.md" \
  --instruction-text "Run the staging profile from the deployment helper." \
  --action-taken "I ran the documented deployment command and checked the repo configuration." \
  --expected-outcome "The staging profile would be defined and selectable." \
  --actual-outcome "The config does not define profile staging and the command reported an unsupported role slug." \
  --reading "The instructions referenced a specific profile and slug. I treated those names as valid identifiers because the wording was imperative and concrete.")
printf '%s\n' "$CATEGORIZE_OUTPUT" | grep -q '^mode=name-resolution$' || fail "categorizer should classify unsupported slug / not-defined profile wording as name-resolution"
printf '%s\n' "$CATEGORIZE_OUTPUT" | grep -q '^run_effect=blocked$' || fail "categorizer should classify missing/unsupported resource wording as blocked"

# --- Test 24: --from-json spaced sources still drive primary source classification ---
cat <<'EOF' | "$ROOT/scripts/report-friction.sh" --events-file "$DEFAULT_EVENTS" --from-json - >/dev/null
{
  "title": "spaced json source ref",
  "instruction_text": "Follow the guidance exactly as written.",
  "action_taken": "I followed the documented guidance exactly as written in the referenced source.",
  "expected_outcome": "The guidance would resolve cleanly without ambiguity.",
  "actual_outcome": "The guidance used a role slug that was not defined by the system.",
  "reading": "I treated the named slug as authoritative because the instruction source was explicit and concrete.",
  "hindsight": "Verify slug availability before treating any instruction-provided slug as definitive.",
  "sources": [
    { "type": "file", "ref": "AGENTS.md", "line": 1 }
  ]
}
EOF
LAST_EVENT=$(tail -1 "$DEFAULT_EVENTS")
printf '%s\n' "$LAST_EVENT" | grep -q '"surface":"instructions"' || fail "--from-json spaced sources should preserve primary source ref for categorization"

# --- Test 25: Positive submodule metadata ---
SUBMODULE_FIXTURE=$(mktemp -d)
SUBMODULE_REMOTE=$(mktemp -d)
git init -q "$SUBMODULE_FIXTURE"
git -C "$SUBMODULE_FIXTURE" config user.name "Smoke Test"
git -C "$SUBMODULE_FIXTURE" config user.email "smoke@example.com"
printf '%s\n' "fixture" >"$SUBMODULE_FIXTURE/README.md"
git -C "$SUBMODULE_FIXTURE" add README.md
git -C "$SUBMODULE_FIXTURE" -c commit.gpgsign=false commit -qm "fixture"

git init -q "$SUBMODULE_REMOTE"
git -C "$SUBMODULE_REMOTE" config user.name "Smoke Test"
git -C "$SUBMODULE_REMOTE" config user.email "smoke@example.com"
git -C "$SUBMODULE_REMOTE" -c protocol.file.allow=always submodule add -q "$SUBMODULE_FIXTURE" deps/fixture
git -C "$SUBMODULE_REMOTE" -c commit.gpgsign=false commit -qam "add submodule" >/dev/null

SUBMODULE_OUTPUT=$(cd "$SUBMODULE_REMOTE/deps/fixture" && "$ROOT/scripts/report-friction.sh" \
  --title "submodule metadata" \
  --source-type documentation \
  --source-ref "test" \
  --instruction-text "Report friction from inside a real submodule checkout." \
  --action-taken "I changed into the checked-out git submodule and ran report-friction.sh without overriding repo-root detection." \
  --expected-outcome "The event would include superproject_root and the submodule_path relative to the superproject." \
  --actual-outcome "The event was recorded from inside the submodule checkout with git metadata available." \
  --reading "A real submodule checkout exposes both the submodule repo root and the superproject working tree. The reporter should preserve both so downstream queries can distinguish submodule-local context from the parent repository." \
  --hindsight "When reporting from a submodule, confirm that superproject_root and submodule_path are present in the recorded event before relying on them for queries.")
SUBMODULE_EVENTS=$(printf '%s\n' "$SUBMODULE_OUTPUT" | sed -n 's/^FRICTION_EVENTS_FILE=//p' | sed -n '1p')
assert_file "$SUBMODULE_EVENTS"
assert_contains '"superproject_root":"'"$SUBMODULE_REMOTE"'"' "$SUBMODULE_EVENTS"
assert_contains '"submodule_path":"deps/fixture"' "$SUBMODULE_EVENTS"

# --- Cleanup ---
rm -f "$INVALID_STDERR" "$INVALID_JSON" "$SCHEMA_STDERR" "$SCHEMA_JSON" "$SHORT_STDERR" "$SHORT_JSON" "$FP_EVENTS" \
  "$REPORT_TYPE_STDERR" "$GROUP_BY_STDERR" "$MULTI_INDEX_STDERR" "$QUERY_FORMAT_STDERR" \
  "$MALFORMED_QUERY_STDERR" "$MALFORMED_REPORT_STDERR" "$MALFORMED_INDEX_STDERR" \
  "$MALFORMED_EVENTS" "$PARTIAL_EVENTS" "$BULK_EVENTS"
rm -rf "$EXPLICIT_DIR" "$ALT_REPO" "$SPACE_PARENT" "$QUOTE_PARENT" "$SPARSE_SCAN_ROOT" "$NON_REPO_DIR" "$SUBMODULE_REMOTE" "$SUBMODULE_FIXTURE"

printf 'All smoke tests passed.\n'
