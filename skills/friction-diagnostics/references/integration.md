# Integration patterns

## Paste-ready `AGENTS.md` snippet

```markdown
## Friction diagnostics
WHEN durable troubleshooting evidence would help later, OR when the run uses unfamiliar skills, MCP servers, tools, or multi-agent handoffs, THEN you SHALL use the `friction-diagnostics` skill.
WHEN you encounter friction caused by instructions, skills, tools, MCP servers, code, logic, data contracts, environment, or workflow, THEN you SHALL record it.
WHEN the issue is solely a user-project failure and the agent's instructions, tools, skills, or workflow did not contribute, THEN you SHALL NOT record it.
WHEN the same issue repeats without materially new evidence, THEN you SHALL NOT create a duplicate entry.
```

## Unix-like bootstrap

```sh
eval "$(sh scripts/init-log.sh \
  --task-summary "Investigate build-routing failures" \
  --agent orchestrator \
  --skill-path "$(pwd)")"
```

The script exports:

- `FRICTION_BASE_DIR`
- `FRICTION_TASK_ID`
- `FRICTION_TASK_DIR`
- `FRICTION_TASK_SUMMARY`
- `FRICTION_TASK_SUMMARY_FILE`
- `FRICTION_LOG_FILE`
- `FRICTION_INDEX_FILE`

## PowerShell bootstrap

```powershell
scripts/init-log.ps1 `
  -TaskSummary "Investigate build-routing failures" `
  -Agent orchestrator `
  -SkillPath $PWD
```

The script sets the same environment variables via `$env:`.

Task metadata is persisted in a line-oriented `SESSION.txt` file. The full task summary lives in `TASK_SUMMARY.txt`, and `SESSION.txt` points to it with `FRICTION_TASK_SUMMARY_FILE=...`.
When you need multiline-safe reuse across isolated PowerShell invocations, read the summary back from `FRICTION_TASK_SUMMARY_FILE` instead of reparsing the line-oriented `FRICTION_TASK_SUMMARY=...` output.

## Subagent pattern

Orchestrator:

```sh
eval "$(sh scripts/init-log.sh \
  --task-summary "Investigate build-routing failures" \
  --agent orchestrator \
  --skill-path "$(pwd)")"
task_id=$FRICTION_TASK_ID
task_dir=$FRICTION_TASK_DIR
task_summary_file=$FRICTION_TASK_SUMMARY_FILE
base_dir=$FRICTION_BASE_DIR
```

Subagent:

```sh
task_summary=$(cat "$task_summary_file")

eval "$(sh scripts/init-log.sh \
  --task-id "$task_id" \
  --task-summary "$task_summary" \
  --agent subagent \
  --role research \
  --skill-path "$(pwd)")"
```

Pass `task_id`, `task_dir`, and `task_summary_file` explicitly in the subagent launch payload. Separate agent invocations usually run in isolated processes, so do not rely on exported shell variables surviving the handoff.

This creates a second log file in the same task directory rather than overwriting the orchestrator log.

## Refreshing the summary

`report-friction.*` already refreshes `INDEX.md` after each appended entry. If the rebuild fails, the command now exits non-zero instead of silently leaving a stale or missing index. Running `build-index.*` manually is still useful after bulk edits, if you moved files around, or to recover after a surfaced rebuild failure.

## End-to-end workflow example

A narrative walkthrough showing multi-agent friction logging across a build investigation task. The exact heuristic results depend on the full entry text — this narrative shows the workflow, not the categorization details.

### Step 1: Orchestrator initializes

The orchestrator starts a task to investigate CI build failures.

```sh
eval "$(sh scripts/init-log.sh \
  --task-summary "Investigate CI build failures" \
  --agent orchestrator \
  --skill-path "$(pwd)")"
```

The orchestrator reads AGENTS.md, which says: "Run `scripts/ci-check.sh` to see the current build status." The script does not exist — `find scripts/ -name 'ci-check.sh'` returns nothing.

```sh
sh scripts/report-friction.sh \
  --log-file "$FRICTION_LOG_FILE" \
  --title "Referenced CI check script does not exist" \
  --instruction-source "AGENTS.md:18" \
  --instruction-text "Run scripts/ci-check.sh to see the current build status." \
  --action-taken "Searched for the script with find and grep." \
  --expected-outcome "The script exists and produces build status output." \
  --actual-outcome "scripts/ci-check.sh was not found. The scripts/ directory contains only build.sh and test.sh." \
  --interpretation "AGENTS.md references a script that does not exist in the repository."
```

This entry is categorized as `instructions/missing/blocked` — "not found" triggers `missing` mode, "AGENTS.md" triggers `instructions` surface.

### Step 2: Orchestrator dispatches subagent

The orchestrator delegates container inspection to a subagent, passing the task ID and task dir.

```sh
task_id=$FRICTION_TASK_ID
task_dir=$FRICTION_TASK_DIR
task_summary_file=$FRICTION_TASK_SUMMARY_FILE
task_summary=$(cat "$task_summary_file")

eval "$(sh scripts/init-log.sh \
  --task-id "$task_id" \
  --task-summary "$task_summary" \
  --agent subagent \
  --role container-inspection \
  --skill-path "$(pwd)")"
```

This creates a second log file in the same task directory.

### Step 3: Subagent encounters MCP friction

The subagent calls the `docker_inspect` MCP tool expecting a `healthcheck` key in the response. The tool returns container metadata without it.

```sh
sh scripts/report-friction.sh \
  --log-file "$FRICTION_LOG_FILE" \
  --title "MCP docker_inspect omits healthcheck data" \
  --instruction-source "MCP tool description for docker_inspect" \
  --instruction-text "Inspect a running container and return its full configuration." \
  --action-taken "Called docker_inspect with container ID abc123." \
  --expected-outcome "Response includes healthcheck configuration as part of full container config." \
  --actual-outcome "Response contained 14 top-level keys but no healthcheck field. The tool description says full configuration but the response is a curated subset." \
  --interpretation "I expected full configuration to include healthcheck. The tool returns a subset without documenting which fields are included."
```

With the current wording, this lands on `mcp/other/degraded`. If you want the stricter `mcp/output-mismatch/degraded` label, add output-mismatch language or override `--mode output-mismatch`. The subagent works around it by running `docker inspect` directly via the CLI.

### Step 4: Subagent encounters performance friction

The build runbook says `npm run verify` completes in under 30 seconds, but the process hung for 120 seconds then was OOM-killed.

```sh
sh scripts/report-friction.sh \
  --log-file "$FRICTION_LOG_FILE" \
  --title "Verify step hung and was OOM-killed" \
  --instruction-source "docs/runbooks/build-verification.md:12" \
  --instruction-text "Run npm run verify. This should complete in under 30 seconds." \
  --action-taken "Ran npm run verify in the build container." \
  --expected-outcome "Completes within 30 seconds with a pass/fail result." \
  --actual-outcome "Process hung for 120 seconds consuming increasing memory, then was killed by the OOM killer. Exit code 137." \
  --interpretation "The runbook's time estimate was wrong by 4x and the process was ultimately killed. The instruction did not mention memory requirements or OOM risk."
```

With the current wording, this lands on `instructions/other/degraded`. If you want `instructions/performance/blocked`, say so explicitly in the entry text or override `--mode performance --impact blocked`.

### Step 5: Orchestrator rebuilds INDEX.md

After both agents finish, the orchestrator rebuilds the summary.

```sh
sh scripts/build-index.sh --task-dir "$FRICTION_TASK_DIR"
```

The resulting INDEX.md shows:

```markdown
# Friction Index: inv-ci-build

**Generated:** 2026-03-14 17:00:00 UTC
**Task dir:** /tmp/agent-friction/inv-ci-build
**Task summary:** Investigate CI build failures
**Log files:** 2
**Entries:** 3

## Category counts

- `instructions/missing/blocked` - 1
- `instructions/other/degraded` - 1
- `mcp/other/degraded` - 1

## Log files

- `2026-03-14/16-30-00_orchestrator.md` - 1 entries
- `2026-03-14/16-35-00_subagent.md` - 2 entries
```

### Step 6: Human reviews

Later, a human points a fresh agent at the task directory. The agent reads INDEX.md, sees 3 entries across 2 categories of `instructions` friction and 1 of `mcp` friction, and can trace each to its root cause:

- The missing CI check script needs to be created or the AGENTS.md reference removed
- The verify step's memory and time requirements need documenting in the runbook
- The docker_inspect MCP tool description needs to specify which fields are included
