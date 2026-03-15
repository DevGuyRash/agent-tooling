#!/bin/sh
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
BASE_DIR=/tmp/agent-friction-smoke-$$
AUTO_ID_BASE_DIR=
FAKE_DATE_DIR=
SPACE_BASE_DIR=
CONCURRENT_BASE_DIR=
FAIL_BASE_DIR=
FAIL_FAKE_BIN=
FAIL_INIT_STDOUT=
FAIL_INIT_STDERR=
FAIL_REPORT_STDOUT=
FAIL_REPORT_STDERR=
trap 'rm -rf "$BASE_DIR" "${AUTO_ID_BASE_DIR:-}" "${FAKE_DATE_DIR:-}" "${SPACE_BASE_DIR:-}" "${CONCURRENT_BASE_DIR:-}" "${FAIL_BASE_DIR:-}" "${FAIL_FAKE_BIN:-}"; rm -f "${FAIL_INIT_STDOUT:-}" "${FAIL_INIT_STDERR:-}" "${FAIL_REPORT_STDOUT:-}" "${FAIL_REPORT_STDERR:-}"' EXIT INT TERM

eval "$(FRICTION_BASE_DIR="$BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-id smoke-task \
  --task-summary "Smoke test for friction diagnostics" \
  --agent orchestrator \
  --skill-path "$ROOT")"

case $FRICTION_TASK_ID in
  *'
'*) printf '%s\n' 'smoke-posix: multiline task summary leaked newline into task id' >&2; exit 1 ;;
esac

ORCH_LOG=$FRICTION_LOG_FILE
ORCH_TASK_DIR=$FRICTION_TASK_DIR
ORCH_INDEX=$FRICTION_INDEX_FILE

"$ROOT/scripts/report-friction.sh" \
  --log-file "$ORCH_LOG" \
  --title "Dispatch role slug mismatch" \
  --instruction-source "SKILL.md:160" \
  --instruction-text "Use mpcr protocol dispatch --role <ROLE> to get the domain-specific prompt." \
  --action-taken "Ran mpcr protocol dispatch --role architecture" \
  --expected-outcome "The CLI returns the architecture prompt." \
  --actual-outcome "error: unknown dispatch role: architecture" \
  --interpretation "I treated the domain table label as the CLI role slug."

AUTO_ID_BASE_DIR=$(mktemp -d "/tmp/agent-friction-auto-id.XXXXXX")
FAKE_DATE_DIR=$(mktemp -d "/tmp/agent-friction-date.XXXXXX")
NAME_MAX_VALUE=$(getconf NAME_MAX "$AUTO_ID_BASE_DIR" 2>/dev/null || printf '%s\n' 255)
printf '%s\n' '#!/bin/sh' >"$FAKE_DATE_DIR/date"
printf '%s\n' 'case "$1" in' >>"$FAKE_DATE_DIR/date"
printf '%s\n' "  '+%Y-%m-%d') printf '%s\n' '2026-03-14' ;;" >>"$FAKE_DATE_DIR/date"
printf '%s\n' "  '+%H-%M-%S') printf '%s\n' '17-00-00' ;;" >>"$FAKE_DATE_DIR/date"
printf '%s\n' "  '+%Y-%m-%d %H:%M:%S %Z') printf '%s\n' '2026-03-14 17:00:00 UTC' ;;" >>"$FAKE_DATE_DIR/date"
printf '%s\n' "  '+%Y%m%d-%H%M%S') printf '%s\n' '20260314-170000' ;;" >>"$FAKE_DATE_DIR/date"
printf '%s\n' '  *) /bin/date "$@" ;;' >>"$FAKE_DATE_DIR/date"
printf '%s\n' 'esac' >>"$FAKE_DATE_DIR/date"
chmod +x "$FAKE_DATE_DIR/date"

eval "$(PATH="$FAKE_DATE_DIR:$PATH" FRICTION_BASE_DIR="$AUTO_ID_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-summary "Review the current code changes" \
  --agent orchestrator \
  --skill-path "$ROOT")"
AUTO_ID_ONE=$FRICTION_TASK_ID
AUTO_DIR_ONE=$FRICTION_TASK_DIR
AUTO_LOG_ONE=$FRICTION_LOG_FILE
AUTO_INDEX_ONE=$FRICTION_INDEX_FILE

eval "$(PATH="$FAKE_DATE_DIR:$PATH" FRICTION_BASE_DIR="$AUTO_ID_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-summary "Review the current code changes" \
  --agent orchestrator \
  --skill-path "$ROOT")"
AUTO_ID_TWO=$FRICTION_TASK_ID
AUTO_DIR_TWO=$FRICTION_TASK_DIR
AUTO_LOG_TWO=$FRICTION_LOG_FILE
AUTO_INDEX_TWO=$FRICTION_INDEX_FILE

[ "$AUTO_ID_ONE" != "$AUTO_ID_TWO" ]
[ "$AUTO_DIR_ONE" != "$AUTO_DIR_TWO" ]
[ -f "$AUTO_DIR_ONE/SESSION.txt" ]
[ -f "$AUTO_DIR_TWO/SESSION.txt" ]

LONG_TASK_SUMMARY=$(printf 'This is a deliberately long natural language task summary %.0s' $(seq 1 20))
eval "$(PATH="$FAKE_DATE_DIR:$PATH" FRICTION_BASE_DIR="$AUTO_ID_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-summary "$LONG_TASK_SUMMARY" \
  --agent orchestrator \
  --skill-path "$ROOT")"
LONG_AUTO_ID_ONE=$FRICTION_TASK_ID
LONG_AUTO_DIR_ONE=$FRICTION_TASK_DIR
LONG_AUTO_LOG_ONE=$FRICTION_LOG_FILE

eval "$(PATH="$FAKE_DATE_DIR:$PATH" FRICTION_BASE_DIR="$AUTO_ID_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-summary "$LONG_TASK_SUMMARY" \
  --agent orchestrator \
  --skill-path "$ROOT")"
LONG_AUTO_ID_TWO=$FRICTION_TASK_ID
LONG_AUTO_DIR_TWO=$FRICTION_TASK_DIR

[ "$LONG_AUTO_ID_ONE" != "$LONG_AUTO_ID_TWO" ]
[ "$LONG_AUTO_DIR_ONE" != "$LONG_AUTO_DIR_TWO" ]
[ -d "$LONG_AUTO_DIR_ONE" ]
[ -d "$LONG_AUTO_DIR_TWO" ]
[ -f "$LONG_AUTO_DIR_ONE/SESSION.txt" ]
[ -f "$LONG_AUTO_DIR_TWO/SESSION.txt" ]
[ "$(printf '%s' "$(basename "$LONG_AUTO_DIR_ONE")" | wc -c | tr -d ' ')" -le "$NAME_MAX_VALUE" ]
[ "$(printf '%s' "$(basename "$LONG_AUTO_DIR_TWO")" | wc -c | tr -d ' ')" -le "$NAME_MAX_VALUE" ]
[ "$(printf '%s' "$(basename "$LONG_AUTO_LOG_ONE")" | wc -c | tr -d ' ')" -le "$NAME_MAX_VALUE" ]

LONG_EXPLICIT_TASK_ID=$(printf 'explicit task id component %.0s' $(seq 1 20))
eval "$(FRICTION_BASE_DIR="$AUTO_ID_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-id "$LONG_EXPLICIT_TASK_ID" \
  --task-summary "Explicit task id length smoke test" \
  --agent orchestrator \
  --skill-path "$ROOT")"
LONG_EXPLICIT_ID=$FRICTION_TASK_ID
LONG_EXPLICIT_DIR=$FRICTION_TASK_DIR
[ -d "$LONG_EXPLICIT_DIR" ]
[ -f "$LONG_EXPLICIT_DIR/SESSION.txt" ]
[ "$(printf '%s' "$LONG_EXPLICIT_ID" | wc -c | tr -d ' ')" -le "$NAME_MAX_VALUE" ]

LONG_AGENT_NAME=$(printf 'very long agent name %.0s' $(seq 1 20))
eval "$(FRICTION_BASE_DIR="$AUTO_ID_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-id long-agent-task \
  --task-summary "Long agent name smoke test" \
  --agent "$LONG_AGENT_NAME" \
  --skill-path "$ROOT")"
LONG_AGENT_LOG=$FRICTION_LOG_FILE
[ -f "$LONG_AGENT_LOG" ]
[ "$(printf '%s' "$(basename "$LONG_AGENT_LOG")" | wc -c | tr -d ' ')" -le "$NAME_MAX_VALUE" ]

LONG_ROLE_NAME=$(printf 'very long role name %.0s' $(seq 1 20))
eval "$(FRICTION_BASE_DIR="$AUTO_ID_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-id long-role-task \
  --task-summary "Long role name smoke test" \
  --agent subagent \
  --role "$LONG_ROLE_NAME" \
  --skill-path "$ROOT")"
LONG_ROLE_LOG=$FRICTION_LOG_FILE
[ -f "$LONG_ROLE_LOG" ]
[ "$(printf '%s' "$(basename "$LONG_ROLE_LOG")" | wc -c | tr -d ' ')" -le "$NAME_MAX_VALUE" ]

"$ROOT/scripts/report-friction.sh" \
  --log-file "$AUTO_LOG_ONE" \
  --title "Auto id uniqueness one" \
  --instruction-source "test" \
  --instruction-text "Ensure auto-generated task IDs isolate unrelated runs." \
  --action-taken "Initialized the first task with a fixed timestamp." \
  --expected-outcome "The first task keeps its own directory." \
  --actual-outcome "A distinct task directory was created for the first run." \
  --interpretation "Auto-generated IDs should remain unique even with the same summary and second."

"$ROOT/scripts/report-friction.sh" \
  --log-file "$AUTO_LOG_TWO" \
  --title "Auto id uniqueness two" \
  --instruction-source "test" \
  --instruction-text "Ensure auto-generated task IDs isolate unrelated runs." \
  --action-taken "Initialized the second task with the same fixed timestamp." \
  --expected-outcome "The second task keeps its own directory." \
  --actual-outcome "A distinct task directory was created for the second run." \
  --interpretation "A second run with identical summary text should not reuse the prior task directory."

grep -q '\*\*Log files:\*\* 1' "$AUTO_INDEX_ONE"
grep -q '\*\*Entries:\*\* 1' "$AUTO_INDEX_ONE"
grep -q '\*\*Log files:\*\* 1' "$AUTO_INDEX_TWO"
grep -q '\*\*Entries:\*\* 1' "$AUTO_INDEX_TWO"

eval "$(FRICTION_BASE_DIR="$BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-id smoke-task \
  --task-summary "Smoke test for friction diagnostics" \
  --agent subagent \
  --role research \
  --skill-path "$ROOT")"

SUB_LOG=$FRICTION_LOG_FILE

"$ROOT/scripts/report-friction.sh" \
  --log-file "$SUB_LOG" \
  --title "MCP call timed out" \
  --instruction-source "MCP server build-inspector" \
  --instruction-text "Use inspect_build to fetch the latest build metadata." \
  --action-taken "Called inspect_build with the requested build ID." \
  --expected-outcome "The MCP server returns build metadata." \
  --actual-outcome "The tool call timed out after 30 seconds with no payload." \
  --interpretation "I treated the documented MCP method as ready for interactive use."

"$ROOT/scripts/report-friction.sh" \
  --log-file "$SUB_LOG" \
  --title "Second dispatch role slug mismatch" \
  --instruction-source "SKILL.md:160" \
  --instruction-text "Use mpcr protocol dispatch --role <ROLE> to get the domain-specific prompt." \
  --action-taken "Ran mpcr protocol dispatch --role architecture again from the subagent." \
  --expected-outcome "The CLI returns the architecture prompt." \
  --actual-outcome "error: unknown dispatch role: architecture" \
  --interpretation "The subagent made the same visible-label to slug assumption."

"$ROOT/scripts/report-friction.sh" \
  --log-file "$SUB_LOG" \
  --title "Rate limit is not auth" \
  --instruction-source "CI pipeline step fetch-pr-status" \
  --instruction-text "Query the GitHub API for the PR merge status." \
  --action-taken "Called GET /repos/org/repo/pulls/142 with the configured token." \
  --expected-outcome "A 200 response with the PR status object." \
  --actual-outcome "HTTP 403 with body {\"message\":\"API rate limit exceeded\"} and X-RateLimit-Remaining: 0 header." \
  --interpretation "The 403 would normally look auth-related, but the body and headers show quota exhaustion." \
  --surface "external-service" \
  --mode "other" \
  --impact "blocked"

"$ROOT/scripts/build-index.sh" --task-dir "$ORCH_TASK_DIR" >/dev/null

FAIL_BASE_DIR=$(mktemp -d "/tmp/agent-friction-fail.XXXXXX")
FAIL_FAKE_BIN=$(mktemp -d "/tmp/agent-friction-fakebin.XXXXXX")
FAIL_INIT_STDOUT=$(mktemp /tmp/friction-init-stdout.XXXXXX)
FAIL_INIT_STDERR=$(mktemp /tmp/friction-init-stderr.XXXXXX)
FAIL_REPORT_STDOUT=$(mktemp /tmp/friction-report-stdout.XXXXXX)
FAIL_REPORT_STDERR=$(mktemp /tmp/friction-report-stderr.XXXXXX)

printf '%s\n' '#!/bin/sh' >"$FAIL_FAKE_BIN/mktemp"
printf '%s\n' 'exit 1' >>"$FAIL_FAKE_BIN/mktemp"
chmod +x "$FAIL_FAKE_BIN/mktemp"

set +e
PATH="$FAIL_FAKE_BIN:$PATH" FRICTION_BASE_DIR="$FAIL_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-id failing-smoke-task \
  --task-summary "Failure path smoke test" \
  --agent orchestrator \
  --skill-path "$ROOT" \
  >"$FAIL_INIT_STDOUT" 2>"$FAIL_INIT_STDERR"
FAIL_INIT_RC=$?
set -e

[ "$FAIL_INIT_RC" -ne 0 ]
[ ! -s "$FAIL_INIT_STDOUT" ]
FAIL_TASK_DIR=$FAIL_BASE_DIR/failing-smoke-task
[ -f "$FAIL_TASK_DIR/SESSION.txt" ]
[ -f "$FAIL_TASK_DIR/TASK_SUMMARY.txt" ]
[ ! -f "$FAIL_TASK_DIR/INDEX.md" ]
FAIL_INIT_LOG=$(find "$FAIL_TASK_DIR" -type f -name '*.md' ! -name 'INDEX.md' | sort | head -n 1)
[ -n "$FAIL_INIT_LOG" ]
[ -f "$FAIL_INIT_LOG" ]
grep -q '^# Friction Log: failing-smoke-task$' "$FAIL_INIT_LOG"

set +e
PATH="$FAIL_FAKE_BIN:$PATH" "$ROOT/scripts/report-friction.sh" \
  --log-file "$FAIL_INIT_LOG" \
  --title "Forced index rebuild failure" \
  --instruction-source "test" \
  --instruction-text "Force build-index failure through mktemp." \
  --action-taken "Appended an entry while mktemp was overridden to fail." \
  --expected-outcome "The append reports the index rebuild failure." \
  --actual-outcome "build-index.sh could not create temp files." \
  --interpretation "The append should surface index rebuild failure without losing the entry." \
  >"$FAIL_REPORT_STDOUT" 2>"$FAIL_REPORT_STDERR"
FAIL_REPORT_RC=$?
set -e

[ "$FAIL_REPORT_RC" -ne 0 ]
[ ! -s "$FAIL_REPORT_STDOUT" ]
[ ! -f "$FAIL_TASK_DIR/INDEX.md" ]
grep -q '## Entry 1: Forced index rebuild failure' "$FAIL_INIT_LOG"
"$ROOT/scripts/build-index.sh" --task-dir "$FAIL_TASK_DIR" >/dev/null
[ -f "$FAIL_TASK_DIR/INDEX.md" ]
grep -q '\*\*Entries:\*\* 1' "$FAIL_TASK_DIR/INDEX.md"
grep -q '\*\*Log files:\*\* 1' "$FAIL_TASK_DIR/INDEX.md"

MULTILINE_BASE_DIR="/tmp/agent friction multiline $$"
mkdir -p "$MULTILINE_BASE_DIR"
MULTILINE_TASK_SUMMARY=$(printf 'Multiline task summary\nsecond line')
MULTILINE_TASK_ID=$(printf 'Multi line task id\nsecond line')
MULTILINE_AGENT=$(printf 'subagent\nworker')
MULTILINE_ROLE=$(printf 'research\nnotes')
eval "$(FRICTION_BASE_DIR="$MULTILINE_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-id "$MULTILINE_TASK_ID" \
  --task-summary "$MULTILINE_TASK_SUMMARY" \
  --agent "$MULTILINE_AGENT" \
  --role "$MULTILINE_ROLE" \
  --skill-path "$ROOT")"

MULTILINE_INDEX=$FRICTION_INDEX_FILE
MULTILINE_TASK_DIR=$FRICTION_TASK_DIR

case $FRICTION_TASK_ID in
  *'
'*) printf '%s\n' 'smoke-posix: multiline task id leaked newline' >&2; exit 1 ;;
esac
case $FRICTION_TASK_DIR in
  *'
'*) printf '%s\n' 'smoke-posix: multiline task dir leaked newline' >&2; exit 1 ;;
esac
case $FRICTION_LOG_FILE in
  *'
'*) printf '%s\n' 'smoke-posix: multiline log file leaked newline' >&2; exit 1 ;;
esac

[ -d "$FRICTION_TASK_DIR" ]
[ -f "$FRICTION_LOG_FILE" ]
[ -f "$FRICTION_TASK_DIR/TASK_SUMMARY.txt" ]
[ "$FRICTION_TASK_SUMMARY_FILE" = "$FRICTION_TASK_DIR/TASK_SUMMARY.txt" ]

grep -q '^FRICTION_TASK_SUMMARY_FILE=' "$FRICTION_TASK_DIR/SESSION.txt"
if grep -q '^FRICTION_TASK_SUMMARY=' "$FRICTION_TASK_DIR/SESSION.txt"; then
  printf '%s\n' 'smoke-posix: SESSION.txt still contains inline task summary' >&2
  exit 1
fi
[ "$(wc -l <"$FRICTION_TASK_DIR/SESSION.txt" | tr -d ' ')" -eq 5 ]
grep -qx 'FRICTION_BASE_DIR=.*' "$FRICTION_TASK_DIR/SESSION.txt"
grep -qx 'FRICTION_TASK_ID=.*' "$FRICTION_TASK_DIR/SESSION.txt"
grep -qx 'FRICTION_TASK_DIR=.*' "$FRICTION_TASK_DIR/SESSION.txt"
grep -qx 'FRICTION_TASK_SUMMARY_FILE=.*' "$FRICTION_TASK_DIR/SESSION.txt"
grep -qx 'FRICTION_INDEX_FILE=.*' "$FRICTION_TASK_DIR/SESSION.txt"

SKILL_SURFACE_OUTPUT=$(sh "$ROOT/scripts/categorize.sh" \
  --instruction-source 'SKILL.md:12' \
  --instruction-text 'Use the MCP tool foo')
printf '%s\n' "$SKILL_SURFACE_OUTPUT" | grep -qx 'surface=skill'

INSTRUCTIONS_SURFACE_OUTPUT=$(sh "$ROOT/scripts/categorize.sh" \
  --instruction-source 'AGENTS.md:7' \
  --instruction-text 'Prompt says to use the MCP tool foo')
printf '%s\n' "$INSTRUCTIONS_SURFACE_OUTPUT" | grep -qx 'surface=instructions'

RATE_LIMIT_OUTPUT=$(sh "$ROOT/scripts/categorize.sh" \
  --instruction-source 'CI pipeline step fetch-pr-status' \
  --instruction-text 'Query the GitHub API for the PR merge status.' \
  --action-taken 'Called GET /repos/org/repo/pulls/142 with the configured token.' \
  --expected-outcome 'A 200 response with the PR status object.' \
  --actual-outcome 'HTTP 403 with body {"message":"API rate limit exceeded"} and X-RateLimit-Remaining: 0 header.' \
  --interpretation 'The 403 would normally look auth-related, but the body and headers show quota exhaustion.')
printf '%s\n' "$RATE_LIMIT_OUTPUT" | grep -qx 'surface=external-service'
printf '%s\n' "$RATE_LIMIT_OUTPUT" | grep -qx 'mode=other'
printf '%s\n' "$RATE_LIMIT_OUTPUT" | grep -qx 'impact=blocked'

CONTEXT_LOSS_OUTPUT=$(sh "$ROOT/scripts/categorize.sh" \
  --instruction-source 'Orchestrator handoff message' \
  --instruction-text 'Continue the review of the remaining files.' \
  --action-taken 'Started the delegated review after receiving the handoff.' \
  --expected-outcome 'The handoff would include the file list needed to continue.' \
  --actual-outcome 'The handoff was missing context about which files were already reviewed, so I re-scanned the repository.' \
  --interpretation 'The subagent lacked context it needed to continue from the prior step.')
printf '%s\n' "$CONTEXT_LOSS_OUTPUT" | grep -qx 'surface=workflow'
printf '%s\n' "$CONTEXT_LOSS_OUTPUT" | grep -qx 'mode=context-loss'
printf '%s\n' "$CONTEXT_LOSS_OUTPUT" | grep -qx 'impact=confusing'

MISSING_OUTPUT=$(sh "$ROOT/scripts/categorize.sh" \
  --instruction-source 'scripts/build.sh' \
  --instruction-text 'Open the generated manifest file.' \
  --action-taken 'Tried to read ./build/manifest.json.' \
  --expected-outcome 'The manifest file exists and can be read.' \
  --actual-outcome 'The manifest file was missing, so the step could not continue.' \
  --interpretation 'The expected artifact was absent and blocked the next step.')
printf '%s\n' "$MISSING_OUTPUT" | grep -qx 'mode=missing'
printf '%s\n' "$MISSING_OUTPUT" | grep -qx 'impact=blocked'

"$ROOT/scripts/report-friction.sh" \
  --log-file "$FRICTION_LOG_FILE" \
  --title "Multiline slug test" \
  --instruction-source "test" \
  --instruction-text "Ensure multiline task metadata normalizes cleanly." \
  --action-taken "Initialized the log with multiline task and agent metadata." \
  --expected-outcome "The generated task and log paths remain single-line and usable." \
  --actual-outcome "The log file is writable and the task directory exists." \
  --interpretation "Slug generation should normalize embedded newlines before building paths."

SPACE_BASE_DIR=$(mktemp -d "/tmp/agent friction spaced.XXXXXX")
eval "$(FRICTION_BASE_DIR="$SPACE_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-id spaced-smoke-task \
  --task-summary "Smoke test under base dir with spaces" \
  --agent orchestrator \
  --skill-path "$ROOT")"

SPACE_LOG_ONE=$FRICTION_LOG_FILE
SPACE_TASK_DIR=$FRICTION_TASK_DIR
SPACE_INDEX=$FRICTION_INDEX_FILE

"$ROOT/scripts/report-friction.sh" \
  --log-file "$SPACE_LOG_ONE" \
  --title "Spaced path first entry" \
  --instruction-source "test" \
  --instruction-text "Ensure build-index handles directories with spaces." \
  --action-taken "Logged the first entry under a spaced base dir." \
  --expected-outcome "The index rebuild succeeds." \
  --actual-outcome "The first entry was recorded." \
  --interpretation "This should remain readable when the task dir path contains spaces."

eval "$(FRICTION_BASE_DIR="$SPACE_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-id spaced-smoke-task \
  --task-summary "Smoke test under base dir with spaces" \
  --agent subagent \
  --role spaced \
  --skill-path "$ROOT")"

SPACE_LOG_TWO=$FRICTION_LOG_FILE

"$ROOT/scripts/report-friction.sh" \
  --log-file "$SPACE_LOG_TWO" \
  --title "Spaced path second entry" \
  --instruction-source "test" \
  --instruction-text "Create a second log so build-index must traverse multiple files." \
  --action-taken "Logged a second entry under the same spaced base dir." \
  --expected-outcome "The index aggregates both log files." \
  --actual-outcome "The second entry was recorded." \
  --interpretation "Iteration over log files must preserve spaces in paths."

"$ROOT/scripts/build-index.sh" --task-dir "$SPACE_TASK_DIR" >/dev/null

CONCURRENT_BASE_DIR=$(mktemp -d "/tmp/agent-friction-concurrent.XXXXXX")
eval "$(FRICTION_BASE_DIR="$CONCURRENT_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-id concurrent-smoke-task \
  --task-summary "Concurrent index rebuild smoke test" \
  --agent orchestrator \
  --skill-path "$ROOT")"

CONCURRENT_LOG_ONE=$FRICTION_LOG_FILE
CONCURRENT_TASK_DIR=$FRICTION_TASK_DIR
CONCURRENT_INDEX=$FRICTION_INDEX_FILE

eval "$(FRICTION_BASE_DIR="$CONCURRENT_BASE_DIR" "$ROOT/scripts/init-log.sh" \
  --task-id concurrent-smoke-task \
  --task-summary "Concurrent index rebuild smoke test" \
  --agent subagent \
  --role parallel \
  --skill-path "$ROOT")"

CONCURRENT_LOG_TWO=$FRICTION_LOG_FILE

"$ROOT/scripts/report-friction.sh" \
  --log-file "$CONCURRENT_LOG_ONE" \
  --title "Concurrent log one entry" \
  --instruction-source "test" \
  --instruction-text "Record the first concurrent entry." \
  --action-taken "Appended the orchestrator entry." \
  --expected-outcome "The shared index remains consistent." \
  --actual-outcome "The first entry was recorded." \
  --interpretation "The first writer should not leave shared rebuild artifacts behind." &
pid_one=$!

"$ROOT/scripts/report-friction.sh" \
  --log-file "$CONCURRENT_LOG_TWO" \
  --title "Concurrent log two entry" \
  --instruction-source "test" \
  --instruction-text "Record the second concurrent entry." \
  --action-taken "Appended the subagent entry." \
  --expected-outcome "The shared index remains consistent." \
  --actual-outcome "The second entry was recorded." \
  --interpretation "Concurrent writers should serialize index rebuilds cleanly." &
pid_two=$!

wait "$pid_one"
wait "$pid_two"
"$ROOT/scripts/build-index.sh" --task-dir "$CONCURRENT_TASK_DIR" >/dev/null

[ -f "$ORCH_LOG" ]
[ -f "$SUB_LOG" ]
[ -f "$ORCH_INDEX" ]
[ -f "$SPACE_LOG_ONE" ]
[ -f "$SPACE_LOG_TWO" ]
[ -f "$SPACE_INDEX" ]
[ -f "$CONCURRENT_LOG_ONE" ]
[ -f "$CONCURRENT_LOG_TWO" ]
[ -f "$CONCURRENT_INDEX" ]

grep -q '## Entry 1: Dispatch role slug mismatch' "$ORCH_LOG"
grep -q '\*\*Category:\*\* skill/name-resolution/blocked' "$ORCH_LOG"
grep -q '## Entry 1: MCP call timed out' "$SUB_LOG"
grep -q '\*\*Category:\*\* mcp/timeout/blocked' "$SUB_LOG"
grep -q '## Entry 2: Second dispatch role slug mismatch' "$SUB_LOG"
grep -q '\*\*Category:\*\* skill/name-resolution/blocked' "$SUB_LOG"
grep -q '## Entry 3: Rate limit is not auth' "$SUB_LOG"
grep -q '\*\*Category:\*\* external-service/other/blocked' "$SUB_LOG"
grep -q '\*\*Tags:\*\* external-service,other,blocked,token,api,rate-limit' "$SUB_LOG"
if grep -q '\*\*Tags:\*\* .*auth' "$SUB_LOG"; then
  printf '%s\n' 'smoke-posix: stale auth tag survived override' >&2
  exit 1
fi

grep -q '\*\*Log files:\*\* 2' "$ORCH_INDEX"
grep -q '\*\*Entries:\*\* 4' "$ORCH_INDEX"
grep -q -- "- \`skill/name-resolution/blocked\` - 2" "$ORCH_INDEX"
grep -q 'mcp/timeout/blocked' "$ORCH_INDEX"
grep -q 'external-service/other/blocked' "$ORCH_INDEX"
SKILL_CATEGORY_LINE=$(grep -n -- '- `skill/name-resolution/blocked` - 2' "$ORCH_INDEX" | cut -d: -f1)
MCP_CATEGORY_LINE=$(grep -n -- '- `mcp/timeout/blocked` - 1' "$ORCH_INDEX" | cut -d: -f1)
[ -n "$SKILL_CATEGORY_LINE" ]
[ -n "$MCP_CATEGORY_LINE" ]
[ "$SKILL_CATEGORY_LINE" -lt "$MCP_CATEGORY_LINE" ]
grep -q '\*\*Log files:\*\* 2' "$SPACE_INDEX"
grep -q '\*\*Entries:\*\* 2' "$SPACE_INDEX"
grep -q 'orchestrator' "$SPACE_INDEX"
grep -q 'subagent-spaced' "$SPACE_INDEX"
SPACE_ORCH_LINE=$(grep -n 'orchestrator' "$SPACE_INDEX" | cut -d: -f1)
SPACE_SUBAGENT_LINE=$(grep -n 'subagent-spaced' "$SPACE_INDEX" | cut -d: -f1)
[ -n "$SPACE_ORCH_LINE" ]
[ -n "$SPACE_SUBAGENT_LINE" ]
[ "$SPACE_ORCH_LINE" -lt "$SPACE_SUBAGENT_LINE" ]
grep -q '\*\*Log files:\*\* 2' "$CONCURRENT_INDEX"
grep -q '\*\*Entries:\*\* 2' "$CONCURRENT_INDEX"
grep -q 'orchestrator' "$CONCURRENT_INDEX"
grep -q 'subagent-parallel' "$CONCURRENT_INDEX"
CONCURRENT_ORCH_LINE=$(grep -n 'orchestrator' "$CONCURRENT_INDEX" | cut -d: -f1)
CONCURRENT_SUBAGENT_LINE=$(grep -n 'subagent-parallel' "$CONCURRENT_INDEX" | cut -d: -f1)
[ -n "$CONCURRENT_ORCH_LINE" ]
[ -n "$CONCURRENT_SUBAGENT_LINE" ]
[ "$CONCURRENT_ORCH_LINE" -lt "$CONCURRENT_SUBAGENT_LINE" ]
grep -q '^\*\*Task summary:\*\*$' "$MULTILINE_INDEX"
grep -q '^> Multiline task summary$' "$MULTILINE_INDEX"
grep -q '^> second line$' "$MULTILINE_INDEX"
[ "$(cat "$MULTILINE_TASK_DIR/TASK_SUMMARY.txt")" = "$MULTILINE_TASK_SUMMARY" ]

ORCH_INDEX_SNAPSHOT=$(mktemp /tmp/friction-index-snapshot.XXXXXX)
PATH="$FAKE_DATE_DIR:$PATH" "$ROOT/scripts/build-index.sh" --task-dir "$ORCH_TASK_DIR" >/dev/null
cp "$ORCH_INDEX" "$ORCH_INDEX_SNAPSHOT"
PATH="$FAKE_DATE_DIR:$PATH" "$ROOT/scripts/build-index.sh" --task-dir "$ORCH_TASK_DIR" >/dev/null
cmp -s "$ORCH_INDEX_SNAPSHOT" "$ORCH_INDEX"
rm -f "$ORCH_INDEX_SNAPSHOT"

if find "$CONCURRENT_TASK_DIR" -maxdepth 1 \
  \( -name '.build-index.lock' -o -name '.log-files.*.tmp' -o -name '.category-counts.*.tmp' -o -name '.log-counts.*.tmp' -o -name '.index.*.tmp' \) \
  | grep -q .
then
  printf '%s\n' 'smoke-posix: concurrent rebuild left temporary files behind' >&2
  exit 1
fi

printf '%s\n' 'smoke-posix: ok'
