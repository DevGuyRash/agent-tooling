#!/bin/sh
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
MEND_ROOT=$(CDPATH='' cd -- "$ROOT/../friction-mend" && pwd)
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

assert_output_contains() {
  needle=$1
  output=$2
  printf '%s\n' "$output" | grep -Fq -- "$needle" || fail "expected '$needle' in output"
}

without_session_env() {
  env -u FRICTION_SESSION_REF -u CLAUDE_SESSION_ID -u CODEX_SESSION_ID -u CODEX_THREAD_ID "$@"
}

DEFAULT_EVENTS=$TEST_REPO/.local/reports/friction/events.jsonl
DEFAULT_INDEX=$TEST_REPO/.local/reports/friction/INDEX.md
DEFAULT_TRAPS=$TEST_REPO/.local/reports/friction/known-traps.md
QUARANTINE_DIR=$TEST_REPO/.local/tmp/friction-diagnostics

cleanup() {
  rm -rf "$TEST_REPO"
}

trap cleanup EXIT

# Initialize from the unmanaged fixture directory so the global Git dispatcher
# can use the ordinary human Git lane without a repository-path override.
cd "$TEST_REPO"
git init -q
mkdir -p .local

# ═══════════════════════════════════════════════════════════════════════
# Test 1: v5 filing with flags — stored shape, key order, talkback
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 1: v5 filing, key order, talkback ... '

OUTPUT=$(without_session_env "$ROOT/scripts/report-friction.sh" \
  --actual-outcome "error: unknown dispatch role: architecture. Bearer ghp_leakedtoken1234567890abcdef12345678." \
  --expected-outcome "The CLI would resolve 'architecture' as a valid dispatch role slug from the table." \
  --reading "The dispatch table had a column called 'Role' with 'Architecture' in it, and the instruction said 'Use --role <ROLE>'. I plugged in 'architecture' as a direct substitution. The CLI rejected it immediately, so the divergence was between the display label and the CLI slug." \
  --decision "I saw two options: guess other casings of the label, or run the CLI discovery command. I set guessing aside and ran discovery, then used the slug it returned." \
  --pivot-information "The mapping from display labels to CLI slugs; it lives in the CLI's own discovery command output, not in the table." \
  --source-kind artifact \
  --source-ref "$ROOT/SKILL.md" \
  --source-line 160 \
  --source-claim "Use example-tool protocol dispatch --role <ROLE> to get the architecture prompt." \
  --impact blocked \
  --tags "dispatch,slug-mismatch,example-tool" \
  --recurrence-key "dispatch-label-vs-slug" 2>/dev/null)

printf '%s\n' "$OUTPUT" | grep -q "^FRICTION_EVENTS_FILE=$DEFAULT_EVENTS$" || fail "unexpected default events file output"
printf '%s\n' "$OUTPUT" | grep -q "^FRICTION_EVENT_ID=evt-0001$" || fail "should output event_id"
printf '%s\n' "$OUTPUT" | grep -q "^FRICTION_RECURRENCE_KEY=dispatch-label-vs-slug$" || fail "should output recurrence key"
assert_output_contains "known traps:" "$OUTPUT"
assert_output_contains "--recur evt-0001" "$OUTPUT"

assert_file "$DEFAULT_EVENTS"
assert_file "$DEFAULT_INDEX"
# v5 system fields present
assert_contains '"schema_version":"5.1.0"' "$DEFAULT_EVENTS"
assert_contains '"kind":"friction"' "$DEFAULT_EVENTS"
assert_contains '"recurrence_key":"dispatch-label-vs-slug"' "$DEFAULT_EVENTS"
assert_contains '"decision":"' "$DEFAULT_EVENTS"
assert_contains '"pivot_information":"' "$DEFAULT_EVENTS"
# no note supplied: the free slot is omitted, not stored empty
assert_not_contains '"note":' "$DEFAULT_EVENTS"
# v5 stored key order: evidence first, title last
KEY_ORDER=$(jq -r 'keys_unsorted | join(",")' "$DEFAULT_EVENTS")
assert_equals "event_id,recorded_at,schema_version,kind,events_file,repo_root,actual_outcome,expected_outcome,reading,decision,pivot_information,sources,impact,recurrence_key,tags,title" "$KEY_ORDER"
# sources use kind/claim, not type/excerpt
assert_contains '"kind":"artifact"' "$DEFAULT_EVENTS"
assert_contains '"claim":"Use example-tool protocol dispatch' "$DEFAULT_EVENTS"
assert_not_contains '"excerpt":' "$DEFAULT_EVENTS"
# deprecated fields absent on v5 records
assert_not_contains '"fingerprint":' "$DEFAULT_EVENTS"
assert_not_contains '"aliases":' "$DEFAULT_EVENTS"
assert_not_contains '"hindsight":' "$DEFAULT_EVENTS"
# token redaction still active
if grep -q 'ghp_leakedtoken' "$DEFAULT_EVENTS"; then
  fail "token leaked into events.jsonl"
fi
# title auto-derived from actual_outcome
assert_contains '"title":"error: unknown dispatch role' "$DEFAULT_EVENTS"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 2: session_ref present when env set, absent otherwise
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 2: session_ref env probe ... '

assert_not_contains '"session_ref":' "$DEFAULT_EVENTS"

without_session_env env FRICTION_SESSION_REF=sess-abc123 "$ROOT/scripts/report-friction.sh" \
  --actual-outcome "zsh: read-only variable: status" \
  --expected-outcome "Assigning to a shell variable named status would work like any other name." \
  --reading "I picked 'status' as a scratch variable while composing a probe under zsh. The assignment failed because zsh reserves status as a read-only parameter mirroring the last exit code, which I only learned from the rejection message." \
  --decision "I renamed the variable to probe_status and reran; the only other option I saw was quoting tricks, which I set aside as noise." \
  --pivot-information "That zsh treats status as read-only; it lives in the zsh Parameters Set By The Shell doc section." \
  --source-kind memory \
  --source-ref "shell variable naming habits" \
  --source-claim "any short lowercase name is safe for a scratch variable" \
  --impact noisy \
  --recurrence-key "zsh-status-readonly" >/dev/null 2>&1

LINE2=$(sed -n '2p' "$DEFAULT_EVENTS")
printf '%s\n' "$LINE2" | grep -q '"session_ref":"sess-abc123"' || fail "session_ref missing when env set"
KEY_ORDER2=$(printf '%s\n' "$LINE2" | jq -r 'keys_unsorted | join(",")')
assert_equals "event_id,recorded_at,schema_version,kind,session_ref,events_file,repo_root,actual_outcome,expected_outcome,reading,decision,pivot_information,sources,impact,recurrence_key,tags,title" "$KEY_ORDER2"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 3: legacy v4 payload via JSON stdin — coerced, never rejected
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 3: legacy payload coercion ... '

COERCE_ERR=$(mktemp "$TEST_REPO/.coerce-err.XXXXXX")
cat <<'EOF' | "$ROOT/scripts/report-friction.sh" --from-json - >/dev/null 2>"$COERCE_ERR"
{
  "expected_outcome": "Git would create the commit object for the staged files.",
  "actual_outcome": "error: 1Password: Could not connect to socket specified by SSH_AUTH_SOCK.",
  "reading": "I had staged the files and passed the leak scan. The commit failed during signing because SSH_AUTH_SOCK had no socket available in this terminal session, which I only discovered from the 1Password error text.",
  "decision": "I retried once with signing disabled for that single commit; the alternative of fixing the agent socket mid-task I set aside as out of scope.",
  "hindsight": "The fact that this repo enforces signing through an external agent; it lives in .gitconfig gpgsign settings.",
  "impact": "blocked",
  "tags": "ssh-auth-sock,git-signing",
  "aliases": ["auth", "git"],
  "sources": {"type": "documentation", "ref": "repo-config", "excerpt": "commit.gpgsign = true"},
  "note": "The socket failure only happens in this terminal multiplexer pane; a fresh terminal signs fine."
}
EOF

assert_contains "coerced deprecated 'hindsight' to pivot_information" "$COERCE_ERR"
assert_contains "coerced tags string to array" "$COERCE_ERR"
assert_contains "folded deprecated 'aliases' into tags" "$COERCE_ERR"
assert_contains "wrapped single sources object in an array" "$COERCE_ERR"
assert_contains "coerced sources[0].type to kind 'artifact'" "$COERCE_ERR"
assert_contains "coerced sources[0].excerpt to claim" "$COERCE_ERR"
rm -f "$COERCE_ERR"

LINE3=$(sed -n '3p' "$DEFAULT_EVENTS")
printf '%s\n' "$LINE3" | grep -q '"pivot_information":"The fact that this repo enforces signing' || fail "hindsight not stored as pivot_information"
printf '%s\n' "$LINE3" | grep -q '"auth"' || fail "aliases not folded into tags"
printf '%s\n' "$LINE3" | grep -q '"kind":"artifact"' || fail "source type not coerced to kind"
printf '%s\n' "$LINE3" | grep -q '"note":"The socket failure only happens' || fail "note free slot not stored on friction record"
printf '%s\n' "$LINE3" | grep -qv '"aliases":' || fail "aliases field should not be stored on v5 records"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 4: duplicate soft-stop — exit 3, no write, escapes work
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 4: duplicate soft-stop and escapes ... '

LINES_BEFORE=$(wc -l <"$DEFAULT_EVENTS" | tr -d ' ')
set +e
DUP_OUTPUT=$("$ROOT/scripts/report-friction.sh" \
  --actual-outcome "zsh: read-only variable: status (again, in a different script)" \
  --expected-outcome "The scratch assignment would work in this second probe script too." \
  --reading "Same trap as before: composed a zsh probe with a variable named status and the shell rejected the assignment as read-only, exactly like the earlier event in this stream." \
  --decision "I renamed the variable again and continued; no other options seemed worth weighing for a known trap." \
  --pivot-information "That zsh reserves status; documented in the zsh parameters section." \
  --source-kind memory \
  --source-ref "shell variable naming habits" \
  --source-claim "any short lowercase name is safe" \
  --impact noisy \
  --recurrence-key "zsh-status-readonly" 2>/dev/null)
DUP_STATUS=$?
set -e
assert_equals "3" "$DUP_STATUS"
LINES_AFTER=$(wc -l <"$DEFAULT_EVENTS" | tr -d ' ')
assert_equals "$LINES_BEFORE" "$LINES_AFTER"
assert_output_contains "Similar open event: evt-0002" "$DUP_OUTPUT"
assert_output_contains "--recur evt-0002" "$DUP_OUTPUT"
assert_output_contains "--distinct" "$DUP_OUTPUT"
assert_output_contains "NO event was filed" "$DUP_OUTPUT"

# --recur escape writes a recurrence record with running count
RECUR_OUTPUT=$("$ROOT/scripts/report-friction.sh" --recur evt-0002 \
  --actual-outcome "zsh: read-only variable: status (in the deploy helper)" 2>/dev/null)
assert_output_contains "FRICTION_RECURS=evt-0002" "$RECUR_OUTPUT"
assert_output_contains "now x2" "$RECUR_OUTPUT"
LINE4=$(sed -n '4p' "$DEFAULT_EVENTS")
printf '%s\n' "$LINE4" | grep -q '"kind":"recurrence"' || fail "recurrence record missing"
printf '%s\n' "$LINE4" | grep -q '"recurs":"evt-0002"' || fail "recurs anchor missing"
printf '%s\n' "$LINE4" | grep -q '"impact":"noisy"' || fail "recurrence should inherit anchor impact"

# --distinct escape writes a full event despite the key match
"$ROOT/scripts/report-friction.sh" \
  --actual-outcome "zsh: read-only variable: status (third variation, genuinely distinct context)" \
  --expected-outcome "The assignment would work because this script declares emulate sh first." \
  --reading "This one differed: the script emulates sh, so I expected zsh parameter rules not to apply. The assignment still failed, which means emulate sh does not lift the read-only status parameter." \
  --decision "I filed as distinct because the emulation angle was new evidence, then renamed the variable and moved on." \
  --pivot-information "That emulate sh does not unreserve status; lives in zsh emulation docs." \
  --source-kind assumption \
  --source-ref "emulate sh lifts zsh reserved parameters" \
  --source-claim "emulation resets special parameter behavior" \
  --impact noisy \
  --recurrence-key "zsh-status-readonly" \
  --distinct >/dev/null 2>&1
LINES_FINAL=$(wc -l <"$DEFAULT_EVENTS" | tr -d ' ')
assert_equals "5" "$LINES_FINAL"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 5: empty stdin — exit 2, loud, NO quarantine file
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 5: empty stdin handling ... '

set +e
EMPTY_ERR=$(printf '' | "$ROOT/scripts/report-friction.sh" --from-json - 2>&1)
EMPTY_STATUS=$?
set -e
assert_equals "2" "$EMPTY_STATUS"
assert_output_contains "NO event was filed" "$EMPTY_ERR"
QUARANTINE_COUNT=$(find "$QUARANTINE_DIR" -name 'invalid-stdin.*' 2>/dev/null | wc -l | tr -d ' ')
assert_equals "0" "$QUARANTINE_COUNT"

# malformed non-empty stdin still quarantines, with a replay hint
set +e
BAD_ERR=$(printf '{"actual_outcome": "broken json,}' | "$ROOT/scripts/report-friction.sh" --from-json - 2>&1)
BAD_STATUS=$?
set -e
assert_equals "2" "$BAD_STATUS"
assert_output_contains "Edit and re-file" "$BAD_ERR"
QUARANTINE_COUNT2=$(find "$QUARANTINE_DIR" -name 'invalid-stdin.*' 2>/dev/null | wc -l | tr -d ' ')
assert_equals "1" "$QUARANTINE_COUNT2"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 6: narrative cap — 25k reading stored at 20k with marker
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 6: narrative size cap ... '

LONG_READING=$(python3 -I -c 'print("consulted the doc and acted on it " * 800)')
"$ROOT/scripts/report-friction.sh" \
  --actual-outcome "verbose failure output for the cap test with enough length" \
  --expected-outcome "The capped field would store at most twenty thousand characters." \
  --reading "$LONG_READING" \
  --decision "I continued unchanged; this synthetic run offered no real options to weigh." \
  --pivot-information "none - the outcome was unknowable in advance, because this is a synthetic cap test." \
  --source-kind tool \
  --source-ref "cap-test" \
  --impact continued \
  --recurrence-key "cap-test-trap" >/dev/null 2>&1

CAP_LINE=$(grep '"recurrence_key":"cap-test-trap"' "$DEFAULT_EVENTS")
READING_LEN=$(printf '%s\n' "$CAP_LINE" | jq -r '.reading | length')
[ "$READING_LEN" -le 20100 ] || fail "reading not capped: $READING_LEN chars"
printf '%s\n' "$CAP_LINE" | jq -r '.reading' | grep -q 'truncated .* chars at filing' || fail "missing truncation marker"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 7: required narrative errors carry their eliciting questions
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 7: required-field errors teach ... '

# flags path missing --decision: exit 1, error carries the question
set +e
DEC_ERR=$("$ROOT/scripts/report-friction.sh" \
  --actual-outcome "some failure output long enough to pass floors" \
  --expected-outcome "something else entirely was predicted here" \
  --reading "an account of the reasoning long enough to pass the minimum floor" \
  --pivot-information "none - unknowable, because synthetic" \
  --source-kind tool --source-ref "x" --impact noisy 2>&1)
DEC_STATUS=$?
set -e
assert_equals "1" "$DEC_STATUS"
assert_output_contains "decision" "$DEC_ERR"
assert_output_contains "permitted" "$DEC_ERR"
assert_output_contains "history" "$DEC_ERR"

# JSON path missing decision: exit 2, same teaching error
set +e
JSON_DEC_ERR=$(printf '%s' '{"actual_outcome":"a failure long enough to pass","expected_outcome":"a prediction long enough to pass","reading":"an account long enough to pass the reading floor easily","pivot_information":"none - unknowable, because synthetic","impact":"noisy","sources":[{"kind":"tool","ref":"x"}]}' | "$ROOT/scripts/report-friction.sh" --from-json - 2>&1)
JSON_DEC_STATUS=$?
set -e
assert_equals "2" "$JSON_DEC_STATUS"
assert_output_contains "missing required field: decision" "$JSON_DEC_ERR"

# flags path missing pivot_information: exit 1 with its question
set +e
PIVOT_ERR=$("$ROOT/scripts/report-friction.sh" \
  --actual-outcome "some failure output long enough to pass floors" \
  --expected-outcome "something else entirely was predicted here" \
  --reading "an account of the reasoning long enough to pass the minimum floor" \
  --decision "I continued unchanged after weighing nothing; synthetic run." \
  --source-kind tool --source-ref "x" --impact noisy 2>&1)
PIVOT_STATUS=$?
set -e
assert_equals "1" "$PIVOT_STATUS"
assert_output_contains "pivot_information" "$PIVOT_ERR"
assert_output_contains "unknowable" "$PIVOT_ERR"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 8: --interview rotates
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 8: interview rotation ... '

IV1=$("$ROOT/scripts/report-friction.sh" --interview)
IV_LINES=$(printf '%s\n' "$IV1" | grep -c '^\[') || true
[ "$IV_LINES" -ge 2 ] || fail "interview should print at least 2 questions (got $IV_LINES)"
printf '%s\n' "$IV1" | grep -q '^\[decision\]' || fail "interview missing decision questions"
ROTATED=0
for attempt in 1 2 3; do
  IV2=$("$ROOT/scripts/report-friction.sh" --interview)
  if [ "$IV1" != "$IV2" ]; then
    ROTATED=1
    break
  fi
done
[ "$ROTATED" -eq 1 ] || fail "interview output identical across 4 runs; rotation broken"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 9: query lifecycle filters — --kind, --key, --recurs, --open
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 9: query lifecycle filters ... '

KIND_COUNT=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --kind recurrence --format json | jq 'length')
assert_equals "1" "$KIND_COUNT"
KEY_COUNT=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --key zsh-status-readonly --kind friction --format json | jq 'length')
assert_equals "2" "$KEY_COUNT"
RECURS_COUNT=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --recurs evt-0002 --format json | jq 'length')
assert_equals "1" "$RECURS_COUNT"
OPEN_BEFORE=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --open --kind friction --format json | jq 'length')
assert_equals "5" "$OPEN_BEFORE"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 10: resolution lifecycle — record, derive open set, dashboard
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 10: resolution lifecycle ... '

RES_OUTPUT=$("$MEND_ROOT/scripts/record-resolution.sh" \
  --events-file "$DEFAULT_EVENTS" \
  --resolves "evt-0002,evt-0005" \
  --action "Documented the zsh status reservation in the repo shell style guide" \
  --ref "commit:deadbee" 2>/dev/null)
assert_output_contains "FRICTION_RESOLVED=evt-0002,evt-0005" "$RES_OUTPUT"

OPEN_AFTER=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --open --kind friction --format json | jq 'length')
assert_equals "3" "$OPEN_AFTER"
# recurrence of evt-0002 inherits closure
OPEN_RECUR=$("$ROOT/scripts/query-friction.sh" --events-file "$DEFAULT_EVENTS" --open --kind recurrence --format json | jq 'length')
assert_equals "0" "$OPEN_RECUR"

# dashboard shows the resolution action and non-empty cluster titles
assert_contains "# Friction Dashboard" "$DEFAULT_INDEX"
assert_contains "Documented the zsh status reservation" "$DEFAULT_INDEX"
assert_contains "## Open Clusters" "$DEFAULT_INDEX"
CLUSTER_ROW=$(grep 'dispatch-label-vs-slug' "$DEFAULT_INDEX" | head -1)
printf '%s\n' "$CLUSTER_ROW" | grep -q 'error: unknown dispatch role' || fail "cluster row missing anchor title (jq scoping regression)"

# refiling the resolved key soft-stops with the resolver named
set +e
RESOLVED_STOP=$("$ROOT/scripts/report-friction.sh" \
  --actual-outcome "zsh: read-only variable: status happened once more after the mend" \
  --expected-outcome "The documented reservation would have prevented this recurrence entirely." \
  --reading "Hit the same reserved-parameter rejection after the style guide was updated, on a script written before the guide changed, so the mend had not propagated to it." \
  --decision "I renamed the variable in the old script and continued; refreshing every legacy script I set aside as mend-session work." \
  --pivot-information "Which scripts predate the style-guide mend; discoverable from git log on the guide." \
  --source-kind memory --source-ref "shell variable naming habits" \
  --impact noisy --recurrence-key "zsh-status-readonly" 2>/dev/null)
RESOLVED_STATUS=$?
set -e
assert_equals "3" "$RESOLVED_STATUS"
assert_output_contains "previously resolved by" "$RESOLVED_STOP"
assert_output_contains "reopens the cluster" "$RESOLVED_STOP"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 11: traps publisher — grounded pointers, caps, atomicity
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 11: traps publisher ... '

# Grounded publish: the model supplies anchor + avoidance; key, sighting
# count, and last-seen are derived from the store.
printf '%s' '{"traps":[{"anchor":"evt-0001","avoid":"Dispatch table shows display labels, not CLI slugs; run the discovery command instead."}]}' \
  | "$MEND_ROOT/scripts/update-traps.sh" --events-file "$DEFAULT_EVENTS" >/dev/null
assert_file "$DEFAULT_TRAPS"
assert_contains "Known traps" "$DEFAULT_TRAPS"
assert_contains "dispatch-label-vs-slug" "$DEFAULT_TRAPS"
grep -q '(evt-0001 x[0-9]*, last 20' "$DEFAULT_TRAPS" || fail "trap line should carry store-derived anchor, count, and date"

# identical content is a no-op
NOOP_OUTPUT=$(printf '%s' '{"traps":[{"anchor":"evt-0001","avoid":"Dispatch table shows display labels, not CLI slugs; run the discovery command instead."}]}' \
  | "$MEND_ROOT/scripts/update-traps.sh" --events-file "$DEFAULT_EVENTS")
assert_output_contains "Unchanged" "$NOOP_OUTPUT"

# fabricated anchors are rejected and the file is untouched
set +e
FABRICATED=$(printf '%s' '{"traps":[{"anchor":"evt-9999","avoid":"Fabricated pointer that must not publish."}]}' \
  | "$MEND_ROOT/scripts/update-traps.sh" --events-file "$DEFAULT_EVENTS" 2>&1)
FABRICATED_STATUS=$?
set -e
[ "$FABRICATED_STATUS" -ne 0 ] || fail "fabricated anchor should be rejected"
assert_output_contains "does not exist in the store" "$FABRICATED"
assert_contains "dispatch-label-vs-slug" "$DEFAULT_TRAPS"
assert_not_contains "evt-9999" "$DEFAULT_TRAPS"

# legacy free-markdown stdin gets a teaching error
set +e
LEGACY=$(printf '%s\n' '- [old-format] Free markdown is no longer accepted.' \
  | "$MEND_ROOT/scripts/update-traps.sh" --events-file "$DEFAULT_EVENTS" 2>&1)
LEGACY_STATUS=$?
set -e
[ "$LEGACY_STATUS" -ne 0 ] || fail "legacy markdown stdin should be rejected"
assert_output_contains "grounded JSON" "$LEGACY"

# oversize rejected (byte cap applies to the rendered file)
set +e
BIG_AVOID=$(python3 -I -c 'print("{\"traps\":[{\"anchor\":\"evt-0001\",\"avoid\":\"" + "x" * 9000 + "\"}]}")')
printf '%s' "$BIG_AVOID" | "$MEND_ROOT/scripts/update-traps.sh" --events-file "$DEFAULT_EVENTS" >/dev/null 2>&1
SIZE_STATUS=$?
set -e
[ "$SIZE_STATUS" -ne 0 ] || fail "oversize traps file should be rejected"
assert_contains "dispatch-label-vs-slug" "$DEFAULT_TRAPS"

# talkback reports the traps count on the next filing
TB_OUTPUT=$("$ROOT/scripts/report-friction.sh" \
  --actual-outcome "connection reset while fetching the release notes page" \
  --expected-outcome "The fetch would return the page as it had moments earlier in the session." \
  --reading "Fetched the same URL that worked a minute before and the connection reset mid-transfer; retrying succeeded, so the divergence was transient network state rather than anything I consulted." \
  --decision "I retried once and it went through; filing a minimal anchor was the only other option I weighed, and I took it." \
  --pivot-information "none - the outcome was unknowable in advance, because the reset was transient network state." \
  --source-kind tool \
  --source-ref "web fetch" \
  --impact continued \
  --recurrence-key "transient-fetch-reset" 2>/dev/null)
assert_output_contains "known traps: 1" "$TB_OUTPUT"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 12: cluster hints — key groups and open scope
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 12: cluster hints ... '

HINTS=$("$MEND_ROOT/scripts/cluster-hints.sh" --events-file "$DEFAULT_EVENTS")
printf '%s\n' "$HINTS" | jq -e '.key_groups | length >= 1' >/dev/null || fail "no key groups"
printf '%s\n' "$HINTS" | jq -e '.scope == "open-only"' >/dev/null || fail "default scope should be open-only"
printf '%s\n' "$HINTS" | jq -e '[.key_groups[].key] | index("zsh-status-readonly") == null' >/dev/null || fail "resolved cluster should not appear open"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 13: stats report — convergence table and collision integrity
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 13: stats report ... '

STATS=$("$ROOT/scripts/generate-report.sh" --events-file "$DEFAULT_EVENTS" --report-type stats --format md)
assert_output_contains "# Friction Stats" "$STATS"
assert_output_contains "Convergence" "$STATS"
assert_output_contains "pivot_information" "$STATS"
assert_output_contains "hindsight_v4" "$STATS"
assert_output_contains "Distinct openers" "$STATS"
printf '%s\n' "$STATS" | grep -q '^| decision ' || fail "stats missing decision convergence row"
assert_output_contains "semantic monoculture" "$STATS"
# key collisions: zsh-status-readonly has 2 friction events (one via --distinct)
printf '%s\n' "$STATS" | grep -q 'Key collisions.*: 1' || fail "expected exactly 1 deliberate key collision from --distinct"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 14: legacy v4 record compatibility on the read side
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 14: v4 record compat ... '

V4_DIR=$TEST_REPO/.local/reports/friction-v4
mkdir -p "$V4_DIR"
V4_EVENTS=$V4_DIR/events.jsonl
cat >"$V4_EVENTS" <<'EOF'
{"event_id":"evt-0001","recorded_at":"2026-05-01T10:00:00Z","fingerprint":"aabbccddeeff","title":"Legacy v4 event about a stale doc","events_file":"/x/events.jsonl","repo_root":"/x","expected_outcome":"The doc path would exist as written.","actual_outcome":"ls: cannot access 'docs/setup.md': No such file or directory","reading":"I followed the README link to docs/setup.md and it does not exist.","hindsight":"I should have listed the docs directory first.","sources":[{"type":"file","ref":"README.md","line":12,"excerpt":"See docs/setup.md"}],"impact":"degraded","tags":["missing-file"],"aliases":["docs"]}
{"event_id":"evt-0002","recorded_at":"2026-05-02T10:00:00Z","fingerprint":"aabbccddeeff","title":"Second legacy event same fingerprint","events_file":"/x/events.jsonl","repo_root":"/x","expected_outcome":"The second doc path would exist as written.","actual_outcome":"ls: cannot access 'docs/usage.md': No such file or directory","reading":"Another dead doc link from the same README section.","hindsight":"I should have checked the docs directory listing.","sources":[{"type":"file","ref":"README.md","line":14,"excerpt":"See docs/usage.md"}],"impact":"noisy","tags":["missing-file"],"aliases":["docs"]}
EOF

V4_DASH=$("$ROOT/scripts/generate-report.sh" --events-file "$V4_EVENTS" --report-type index --format md)
assert_output_contains "aabbccddeeff" "$V4_DASH"
assert_output_contains "Second legacy event same fingerprint" "$V4_DASH"
V4_ALIAS=$("$ROOT/scripts/query-friction.sh" --events-file "$V4_EVENTS" --alias docs --format json | jq 'length')
assert_equals "2" "$V4_ALIAS"
V4_KEY=$("$ROOT/scripts/query-friction.sh" --events-file "$V4_EVENTS" --key aabbccddeeff --format json | jq 'length')
assert_equals "2" "$V4_KEY"

# v5.0 record (no decision) stays readable: renders without error, no Decision line
RECURRENCE_FIELD='"recurrence_key"'
cat >>"$V4_EVENTS" <<EOF
{"event_id":"evt-0003","recorded_at":"2026-07-01T10:00:00Z","schema_version":"5.0.0","kind":"friction","events_file":"/x/events.jsonl","repo_root":"/x","actual_outcome":"ls: cannot access 'docs/extra.md': No such file or directory","expected_outcome":"The third doc path would exist as written in the README.","reading":"A v5.0-era record filed before the decision field existed; used here to prove read-side tolerance.","pivot_information":"none - unknowable, because synthetic tolerance fixture.","sources":[{"kind":"artifact","ref":"README.md","claim":"See docs/extra.md"}],"impact":"noisy",$RECURRENCE_FIELD:"v50-tolerance-fixture","tags":["missing-file"],"title":"v5.0 tolerance fixture"}
EOF
V50_MD=$("$ROOT/scripts/query-friction.sh" --events-file "$V4_EVENTS" --key v50-tolerance-fixture --format md)
assert_output_contains "v5.0 tolerance fixture" "$V50_MD"
printf '%s\n' "$V50_MD" | grep -q '\*\*Decision:\*\*' && fail "v5.0 record should render without a Decision line"
"$ROOT/scripts/generate-report.sh" --events-file "$V4_EVENTS" --report-type stats --format md >/dev/null || fail "stats failed on mixed v4/v5.0 store"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 15: statelessness — isolated environments, correct dedup
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 15: statelessness across isolated shells ... '

ISO_DIR=$TEST_REPO/.local/reports/friction-iso
mkdir -p "$ISO_DIR"
ISO_EVENTS=$ISO_DIR/events.jsonl
env -i PATH="$PATH" HOME="$TEST_REPO" sh "$ROOT/scripts/report-friction.sh" \
  --events-file "$ISO_EVENTS" --repo-root "$TEST_REPO" \
  --actual-outcome "isolated shell one filed this event with no inherited state" \
  --expected-outcome "Filing works identically with a clean environment and no shared shell state." \
  --reading "First isolated invocation: composed the record entirely from arguments, relying on the store rather than any session memory, to prove the door needs no context." \
  --decision "I filed and continued; a synthetic probe offers nothing else to weigh." \
  --pivot-information "none - the outcome was unknowable in advance, because this is a synthetic statelessness probe." \
  --source-kind tool --source-ref "statelessness-test" \
  --impact continued --recurrence-key "iso-shell-trap" >/dev/null 2>&1 || fail "isolated filing failed"

set +e
env -i PATH="$PATH" HOME="$TEST_REPO" sh "$ROOT/scripts/report-friction.sh" \
  --events-file "$ISO_EVENTS" --repo-root "$TEST_REPO" \
  --actual-outcome "isolated shell two hit the same trap and must be told about shell one" \
  --expected-outcome "The second isolated shell would be briefed by the store, not by memory." \
  --reading "Second isolated invocation from a fresh environment: the store must surface the first filing because nothing else can — no env vars, no shared shell, no session context." \
  --decision "I attempted a duplicate filing on purpose; the store had to stop me because no memory could." \
  --pivot-information "none - the outcome was unknowable in advance, because this is a synthetic statelessness probe." \
  --source-kind tool --source-ref "statelessness-test" \
  --impact continued --recurrence-key "iso-shell-trap" >/dev/null 2>&1
ISO_STATUS=$?
set -e
assert_equals "3" "$ISO_STATUS"
ISO_LINES=$(wc -l <"$ISO_EVENTS" | tr -d ' ')
assert_equals "1" "$ISO_LINES"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 16: --add-tags still works on v5 records
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 16: --add-tags ... '

"$ROOT/scripts/report-friction.sh" --add-tags evt-0001 "cli,testing" >/dev/null 2>&1
LINE1=$(sed -n '1p' "$DEFAULT_EVENTS")
printf '%s\n' "$LINE1" | grep -q '"dispatch"' || fail "original tags missing after --add-tags"
printf '%s\n' "$LINE1" | grep -q '"cli"' || fail "--add-tags didn't add 'cli'"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 17: cross-repo report over mixed v4/v5 stores
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 17: cross-repo report ... '

CROSS_OUTPUT=$("$ROOT/scripts/generate-report.sh" --scan-dirs "$TEST_REPO" --report-type cross-repo --format md)
printf '%s\n' "$CROSS_OUTPUT" | grep -q "Cross-Repo Friction Index" || fail "missing cross-repo header"
printf '%s\n' "$CROSS_OUTPUT" | grep -q "Top Keys" || fail "missing Top Keys section"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 18: session hook — sidecar, boundary presence, env dedupe, fail-open
# ═══════════════════════════════════════════════════════════════════════
HOOK_SCRIPT=$(CDPATH='' cd -- "$ROOT/../.." && pwd)/hooks/friction-session-env.sh
if [ -x "$HOOK_SCRIPT" ]; then
  printf 'Test 18: session hook ... '

  HOOK_ENV=$TEST_REPO/.hook-env
  rm -f "$HOOK_ENV"
  HOOK_OUT=$(printf '%s' '{"session_id":"abc-123","transcript_path":"/tmp/x y.jsonl"}' | CLAUDE_ENV_FILE=$HOOK_ENV sh "$HOOK_SCRIPT")
  # boundary presence: the store has open anchors, so derived facts appear
  assert_output_contains "friction:" "$HOOK_OUT"
  assert_output_contains "open anchor" "$HOOK_OUT"
  assert_output_contains "known-traps:" "$HOOK_OUT"
  assert_file "$HOOK_ENV"
  assert_contains "export FRICTION_SESSION_REF='abc-123'" "$HOOK_ENV"
  assert_contains "export FRICTION_TRANSCRIPT_PATH='/tmp/x y.jsonl'" "$HOOK_ENV"

  # sidecar written into the existing store, and a fresh sidecar outranks a
  # stale env-file ref when a record is filed
  SIDECAR=$TEST_REPO/.local/reports/friction/session-ref.json
  assert_file "$SIDECAR"
  assert_contains "abc-123" "$SIDECAR"
  without_session_env env FRICTION_SESSION_REF=stale-env-ref sh "$ROOT/scripts/report-friction.sh" \
    --events-file "$DEFAULT_EVENTS" --recur evt-0001 \
    --actual-outcome "sidecar precedence probe occurrence" >/dev/null 2>&1
  LAST_REF=$(tail -1 "$DEFAULT_EVENTS" | jq -r '.session_ref')
  assert_equals "abc-123" "$LAST_REF"

  # rerunning the hook dedupes env exports: exactly one line per var, newest wins
  printf '%s' '{"session_id":"def-456"}' | CLAUDE_ENV_FILE=$HOOK_ENV sh "$HOOK_SCRIPT" >/dev/null
  REF_COUNT=$(grep -c '^export FRICTION_SESSION_REF=' "$HOOK_ENV")
  assert_equals "1" "$REF_COUNT"
  assert_contains "export FRICTION_SESSION_REF='def-456'" "$HOOK_ENV"

  # storeless repo: silent stdout, no sidecar, no directories created
  BARE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/friction-hook-bare.XXXXXX")
  git -C "$BARE_DIR" init -q
  BARE_OUT=$(printf '%s' "{\"session_id\":\"abc-123\",\"cwd\":\"$BARE_DIR\"}" | env -u CLAUDE_ENV_FILE sh "$HOOK_SCRIPT")
  assert_equals "" "$BARE_OUT"
  [ ! -e "$BARE_DIR/.local" ] || fail "hook must not create .local in a storeless repo"
  rm -rf "$BARE_DIR"

  # no env file: exit 0
  printf '%s' '{"session_id":"abc-123"}' | env -u CLAUDE_ENV_FILE sh "$HOOK_SCRIPT" >/dev/null || fail "hook must exit 0 without CLAUDE_ENV_FILE"

  # garbage stdin: exit 0, nothing harmful written
  HOOK_ENV2=$TEST_REPO/.hook-env2
  rm -f "$HOOK_ENV2"
  printf 'not json at all' | CLAUDE_ENV_FILE=$HOOK_ENV2 sh "$HOOK_SCRIPT" >/dev/null || fail "hook must exit 0 on garbage stdin"
  if [ -f "$HOOK_ENV2" ] && grep -q 'FRICTION_SESSION_REF' "$HOOK_ENV2"; then
    fail "garbage stdin must not export a session ref"
  fi

  # injection attempt: sanitizer rejects a shell-hostile session id
  HOOK_ENV3=$TEST_REPO/.hook-env3
  rm -f "$HOOK_ENV3"
  printf '%s' '{"session_id":"abc; rm -rf /"}' | CLAUDE_ENV_FILE=$HOOK_ENV3 sh "$HOOK_SCRIPT" >/dev/null || fail "hook must exit 0 on hostile session id"
  if [ -f "$HOOK_ENV3" ] && grep -q 'FRICTION_SESSION_REF' "$HOOK_ENV3"; then
    fail "hostile session id must not be exported"
  fi

  printf 'OK\n'
else
  printf 'Test 18: session hook ... SKIPPED (hook not present in standalone skill install)\n'
fi

# ═══════════════════════════════════════════════════════════════════════
# Test 19: lifecycle reopen — state agrees across every consumer
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 19: lifecycle reopen across consumers ... '

REOPEN_DIR=$TEST_REPO/reopen-store
mkdir -p "$REOPEN_DIR"
REOPEN_EVENTS=$REOPEN_DIR/events.jsonl

"$ROOT/scripts/report-friction.sh" --events-file "$REOPEN_EVENTS" \
  --actual-outcome "reopen probe outcome text" \
  --expected-outcome "the trap would stay fixed after the first mend" \
  --reading "hit the same divergence again after the source had been mended once, proving the mend did not hold" \
  --decision "filed and continued" \
  --pivot-information "none - probe" \
  --source-kind assumption --source-ref reopen-probe --source-claim "mend holds" \
  --impact noisy --recurrence-key reopen-probe-trap >/dev/null 2>&1

"$MEND_ROOT/scripts/record-resolution.sh" --events-file "$REOPEN_EVENTS" \
  --resolves evt-0001 --action "first mend of the reopen probe" >/dev/null 2>&1
OPEN_CLOSED=$("$ROOT/scripts/query-friction.sh" --events-file "$REOPEN_EVENTS" --open --kind friction --format json | jq 'length')
assert_equals "0" "$OPEN_CLOSED"

RECUR_OUT=$("$ROOT/scripts/report-friction.sh" --events-file "$REOPEN_EVENTS" \
  --recur evt-0001 --actual-outcome "reopen probe bit again after the mend" 2>/dev/null)
assert_output_contains "reopens it" "$RECUR_OUT"
assert_output_contains "open anchors: 1" "$RECUR_OUT"

# every consumer agrees the anchor is open again
OPEN_REOPENED=$("$ROOT/scripts/query-friction.sh" --events-file "$REOPEN_EVENTS" --open --kind friction --format json | jq 'length')
assert_equals "1" "$OPEN_REOPENED"
assert_contains "**Open:** 1" "$REOPEN_DIR/INDEX.md"
STATS_OPEN=$("$ROOT/scripts/generate-report.sh" --events-file "$REOPEN_EVENTS" --report-type stats --format json | jq '.totals.open')
assert_equals "1" "$STATS_OPEN"
HINTS_OPEN=$("$MEND_ROOT/scripts/cluster-hints.sh" --events-file "$REOPEN_EVENTS" | jq -r '.key_groups[0].open')
assert_equals "true" "$HINTS_OPEN"

# a second resolution closes it again, without an already-resolved warning
RERESOLVE_ERR=$("$MEND_ROOT/scripts/record-resolution.sh" --events-file "$REOPEN_EVENTS" \
  --resolves evt-0001 --action "second mend after the regression" 2>&1 >/dev/null)
printf '%s' "$RERESOLVE_ERR" | grep -q "already resolved" && fail "re-resolving a reopened anchor must not warn"
OPEN_FINAL=$("$ROOT/scripts/query-friction.sh" --events-file "$REOPEN_EVENTS" --open --kind friction --format json | jq 'length')
assert_equals "0" "$OPEN_FINAL"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 20: cross-store identity — one repo's resolution cannot close another's
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 20: cross-store identity ... '

ISO_A=$(mktemp -d "${TMPDIR:-/tmp}/friction-iso-a.XXXXXX")
ISO_B=$(mktemp -d "${TMPDIR:-/tmp}/friction-iso-b.XXXXXX")
mkdir -p "$ISO_A/.local/reports/friction" "$ISO_B/.local/reports/friction"
printf '%s\n%s\n' \
  '{"event_id":"evt-0001","recorded_at":"2026-07-01T00:00:00Z","kind":"friction","actual_outcome":"store A outcome","recurrence_key":"trap-a","impact":"noisy"}' \
  '{"event_id":"evt-0002","recorded_at":"2026-07-02T00:00:00Z","kind":"resolution","resolves":["evt-0001"],"action":"fixed in A"}' \
  >"$ISO_A/.local/reports/friction/events.jsonl"
printf '%s\n' \
  '{"event_id":"evt-0001","recorded_at":"2026-07-01T00:00:00Z","kind":"friction","actual_outcome":"store B unrelated outcome","recurrence_key":"trap-b","impact":"blocked"}' \
  >"$ISO_B/.local/reports/friction/events.jsonl"

CROSS_OPEN=$("$ROOT/scripts/query-friction.sh" --scan-dirs "$ISO_A" "$ISO_B" --open --kind friction --format json)
CROSS_COUNT=$(printf '%s\n' "$CROSS_OPEN" | jq 'length')
assert_equals "1" "$CROSS_COUNT"
assert_output_contains "store B unrelated outcome" "$CROSS_OPEN"
rm -rf "$ISO_A" "$ISO_B"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 21: read-only commands create nothing in a clean repository
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 21: read-only commands are non-mutating ... '

CLEAN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/friction-clean.XXXXXX")
git -C "$CLEAN_DIR" init -q
(
  cd "$CLEAN_DIR"
  set +e
  "$ROOT/scripts/query-friction.sh" --open --format json >/dev/null 2>&1
  "$ROOT/scripts/generate-report.sh" --report-type stats --format json >/dev/null 2>&1
  "$MEND_ROOT/scripts/cluster-hints.sh" >/dev/null 2>&1
  set -e
)
LEFTOVER=$(find "$CLEAN_DIR" -mindepth 1 -maxdepth 1 -not -name '.git' | wc -l | tr -d ' ')
assert_equals "0" "$LEFTOVER"
rm -rf "$CLEAN_DIR"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 22: short exact evidence files on both ingress paths
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 22: short exact evidence ... '

SHORT_DIR=$TEST_REPO/short-store
mkdir -p "$SHORT_DIR"
SHORT_EVENTS=$SHORT_DIR/events.jsonl

"$ROOT/scripts/report-friction.sh" --events-file "$SHORT_EVENTS" \
  --actual-outcome "EPIPE" \
  --expected-outcome "the pipe would stay open through the read" \
  --reading "streamed output into a consumer that had already exited, so the write failed at the pipe" \
  --decision "buffered to a file and reran" \
  --pivot-information "consumer lifetime, visible via ps" \
  --source-kind assumption --source-ref pipe-lifetime --source-claim "consumer outlives producer" \
  --impact noisy --recurrence-key pipe-consumer-died-flags >/dev/null 2>&1 || fail "5-char evidence must file via flags"

printf '%s' '{"actual_outcome":"ENOSPC","expected_outcome":"the write would succeed on a disk with visible free space","reading":"wrote to a tmpfs whose quota was exhausted even though df showed free space on the parent mount","decision":"moved the output to the repo tree","pivot_information":"tmpfs quota, visible via df on the exact mountpoint","sources":[{"kind":"assumption","ref":"disk-space","claim":"df free space applies to this path"}],"impact":"noisy","recurrence_key":"tmpfs-quota-vs-df"}' \
  | "$ROOT/scripts/report-friction.sh" --events-file "$SHORT_EVENTS" --from-json - >/dev/null 2>&1 || fail "6-char evidence must file via --from-json"

SHORT_COUNT=$(jq -s 'length' "$SHORT_EVENTS")
assert_equals "2" "$SHORT_COUNT"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 23: committed receipt survives index failure; redaction parity; modes
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 23: receipt, redaction parity, private modes ... '

HARDEN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/friction-harden.XXXXXX")
git -C "$HARDEN_DIR" init -q
HARDEN_EVENTS=$HARDEN_DIR/.local/reports/friction/events.jsonl

# modes under a permissive umask
(
  umask 022
  "$ROOT/scripts/report-friction.sh" --events-file "$HARDEN_EVENTS" \
    --actual-outcome "modes probe outcome with Bearer sk-modesprobe123 token" \
    --expected-outcome "artifacts land user-only regardless of umask" \
    --reading "filed under umask 022 to prove the writer enforces private modes itself" \
    --decision "checked the mode bits after filing" \
    --pivot-information "none - probe" \
    --source-kind assumption --source-ref umask-probe --source-claim "sk-parityprobe999 lives here" \
    --impact continued --recurrence-key modes-probe >/dev/null 2>&1
)
EVENTS_MODE=$(ls -l "$HARDEN_EVENTS" | cut -c1-10)
assert_equals "-rw-------" "$EVENTS_MODE"
DIR_MODE=$(ls -ld "$HARDEN_DIR/.local/reports/friction" | cut -c1-10)
assert_equals "drwx------" "$DIR_MODE"

# redaction parity: the same fixture is redacted on the flags path (above)
# and the JSON path (below), in narratives and sources alike
printf '%s' '{"actual_outcome":"json probe outcome with Bearer sk-modesprobe123 token","expected_outcome":"both ingress paths redact identically","reading":"filed the same secret fixture through the JSON path to compare against the flags filing","decision":"compared the stored records","pivot_information":"none - probe","sources":[{"kind":"assumption","ref":"umask-probe","claim":"sk-parityprobe999 lives here"}],"impact":"continued","recurrence_key":"json-parity-probe"}' \
  | "$ROOT/scripts/report-friction.sh" --events-file "$HARDEN_EVENTS" --from-json - >/dev/null 2>&1
grep -q "sk-modesprobe123\|sk-parityprobe999" "$HARDEN_EVENTS" && fail "secret fixtures must not reach the store on either path"
PARITY=$(jq -rs 'map(.sources[0].claim) | unique | length' "$HARDEN_EVENTS")
assert_equals "1" "$PARITY"

# forced index failure: receipt still printed, exit 0, record committed
mkdir "$HARDEN_DIR/.local/reports/friction/INDEX.md.blocker" 2>/dev/null || true
rm -rf "$HARDEN_DIR/.local/reports/friction/INDEX.md"
mkdir "$HARDEN_DIR/.local/reports/friction/INDEX.md"
chmod 555 "$HARDEN_DIR/.local/reports/friction/INDEX.md"
set +e
RECEIPT_OUT=$("$ROOT/scripts/report-friction.sh" --events-file "$HARDEN_EVENTS" \
  --recur evt-0001 --actual-outcome "receipt probe occurrence after forced index failure" 2>&1)
RECEIPT_STATUS=$?
set -e
assert_equals "0" "$RECEIPT_STATUS"
assert_output_contains "FRICTION_EVENT_ID=evt-0003" "$RECEIPT_OUT"
assert_output_contains "warning: index rebuild failed" "$RECEIPT_OUT"
chmod 755 "$HARDEN_DIR/.local/reports/friction/INDEX.md"
rm -rf "$HARDEN_DIR"

printf 'OK\n'

# ═══════════════════════════════════════════════════════════════════════
# Test 24: lock bounds — ownerless reclaim and live-lock timeout
# ═══════════════════════════════════════════════════════════════════════
printf 'Test 24: lock bounds ... '

LOCK_DIR_ROOT=$TEST_REPO/lock-store
mkdir -p "$LOCK_DIR_ROOT"
LOCK_EVENTS=$LOCK_DIR_ROOT/events.jsonl

# ownerless lock (writer died before publishing its pid): reclaimed, filing succeeds
mkdir -p "$LOCK_DIR_ROOT/.report-friction.lock"
"$ROOT/scripts/report-friction.sh" --events-file "$LOCK_EVENTS" \
  --actual-outcome "ownerless lock reclaim probe outcome" \
  --expected-outcome "the bounded lock reclaims an ownerless directory instead of waiting forever" \
  --reading "seeded a bare lock directory with no pid file to simulate a writer killed before publication" \
  --decision "let the grace-window reclaim run" \
  --pivot-information "none - probe" \
  --source-kind assumption --source-ref lock-probe --source-claim "ownerless locks reclaim" \
  --impact continued --recurrence-key ownerless-lock-reclaim >/dev/null 2>&1 || fail "ownerless lock must be reclaimed"

# live foreign lock: bounded timeout names the owner instead of hanging
mkdir -p "$LOCK_DIR_ROOT/.report-friction.lock"
printf '%s\n' "$$" >"$LOCK_DIR_ROOT/.report-friction.lock/pid"
set +e
TIMEOUT_OUT=$(FRICTION_LOCK_TIMEOUT=2 "$ROOT/scripts/report-friction.sh" --events-file "$LOCK_EVENTS" \
  --recur evt-0001 --actual-outcome "live lock timeout probe occurrence" 2>&1)
TIMEOUT_STATUS=$?
set -e
[ "$TIMEOUT_STATUS" -ne 0 ] || fail "live lock must time out, not file"
assert_output_contains "Could not acquire lock" "$TIMEOUT_OUT"
rm -rf "$LOCK_DIR_ROOT/.report-friction.lock"

printf 'OK\n'

printf '\nAll smoke tests passed.\n'
