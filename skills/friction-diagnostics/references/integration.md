# Integration patterns

## Paste-ready `AGENTS.md` snippet

```markdown
## Friction diagnostics
WHEN any error, failure, unexpected outcome, code bug, test failure, compilation error, runtime exception, or friction of any kind occurs THEN you SHALL immediately log it using the `friction-diagnostics` skill. There is no threshold for "important enough to log" — if it went wrong, log it.
WHEN the same issue repeats without materially new evidence, THEN you SHALL NOT create a duplicate entry.
WHEN no friction is encountered THEN you SHALL NOT initialize a friction session.
```

## Unix-like bootstrap

```sh
eval "$(sh scripts/init-log.sh \
  --task-summary "Investigate build-routing failures — deploy step exits 1 after PR merge with no diagnostic output" \
  --agent orchestrator \
  --skill-path "$(pwd)")"
```

`init-log.*` is optional. When you call it, it emits the task manifest and creates only:

- `SESSION.txt`
- `TASK_SUMMARY.txt`
- `task.json`

The script emits task-scoped values such as:

- `FRICTION_BASE_DIR`
- `FRICTION_TASK_ID`
- `FRICTION_TASK_DIR`
- `FRICTION_TASK_SUMMARY`
- `FRICTION_TASK_SUMMARY_FILE`
- `FRICTION_TASK_JSON`
- `FRICTION_STORAGE_MODE`
- `FRICTION_CAPTURE_MODE`
- `FRICTION_PRIVACY_TIER`
- `FRICTION_LOG_FILE=''`
- `FRICTION_TASK_DESCRIPTOR=''`

No markdown log, descriptor, `events.jsonl`, `incidents.json`, `INDEX.md`, or `exports/` artifact exists until the first reported event.

## Preferred reporting path

Use `report-friction.* --from-json` as the primary integration surface. Hand it a plain sanitized JSON document and let the script materialize the agent log, descriptor, and shared task artifacts on demand.

Unix-like systems:

```sh
cat <<'EOF' >/tmp/friction-event.json
{
  "title": "Referenced CI check script does not exist",
  "instruction_source": "AGENTS.md:18, under '## Build verification'",
  "instruction_text": "Run scripts/ci-check.sh to see the current build status. This appears as a direct instruction, not a conditional or example. No alternative path is mentioned.",
  "action_taken": "Ran find scripts/ -name 'ci-check.sh' — no results. Ran grep -r 'ci-check' scripts/ — no results.",
  "expected_outcome": "The file scripts/ci-check.sh exists and produces build status output.",
  "actual_outcome": "scripts/ci-check.sh does not exist and has never existed in the repository's git history.",
  "interpretation": "I understood 'Run scripts/ci-check.sh' as a direct instruction to execute an existing file because AGENTS.md presents it as a concrete path in imperative form with no qualifiers like 'if available' or 'create if missing'."
}
EOF

sh scripts/report-friction.sh \
  --task-summary "Investigate build-routing failures — deploy step exits 1 after PR merge with no diagnostic output" \
  --agent orchestrator \
  --skill-path "$(pwd)" \
  --from-json /tmp/friction-event.json
```

## PowerShell bootstrap

```powershell
scripts/init-log.ps1 `
  -TaskSummary "Investigate build-routing failures — deploy step exits 1 after PR merge with no diagnostic output" `
  -Agent orchestrator `
  -SkillPath $PWD
```

PowerShell follows the same manifest-only contract. Task metadata is persisted in a line-oriented `SESSION.txt` file. `SESSION.txt` is task-scoped, so it excludes `FRICTION_TASK_DESCRIPTOR`; that pointer belongs to the current agent and is empty until the first logged event creates a descriptor JSON next to the agent's markdown log. The full task summary lives in `TASK_SUMMARY.txt`, and `SESSION.txt` points to it with `FRICTION_TASK_SUMMARY_FILE=...`.
When you need multiline-safe reuse across isolated PowerShell invocations, read the summary back from `FRICTION_TASK_SUMMARY_FILE` instead of reparsing the line-oriented `FRICTION_TASK_SUMMARY=...` output.

```powershell
$payload = @{
  title = "Referenced CI check script does not exist"
  instruction_source = "AGENTS.md:18, under '## Build verification'"
  instruction_text = "Run scripts/ci-check.sh to see the current build status. This appears as a direct instruction, not a conditional or example. No alternative path is mentioned."
  action_taken = "Ran find scripts/ -name 'ci-check.sh' — no results. Ran grep -r 'ci-check' scripts/ — no results."
  expected_outcome = "The file scripts/ci-check.sh exists and produces build status output."
  actual_outcome = "scripts/ci-check.sh does not exist and has never existed in the repository's git history."
  interpretation = "I understood 'Run scripts/ci-check.sh' as a direct instruction to execute an existing file because AGENTS.md presents it as a concrete path in imperative form with no qualifiers like 'if available' or 'create if missing'."
} | ConvertTo-Json -Depth 4
$payloadPath = Join-Path $env:TEMP "friction-event.json"
[System.IO.File]::WriteAllText($payloadPath, $payload)

scripts/report-friction.ps1 `
  -TaskSummary "Investigate build-routing failures — deploy step exits 1 after PR merge with no diagnostic output" `
  -Agent orchestrator `
  -SkillPath $PWD `
  -FromJson $payloadPath
```

The JSON payload uses plain sanitized string fields such as `title`, `instruction_source`, and `actual_outcome`. Do not send Base64-encoded `*_b64` fields.

## Subagent pattern

With session auto-discovery, subagents no longer need explicit `--task-id` plumbing. When a subagent uses the same task summary, it automatically finds and joins the orchestrator's session:

Orchestrator logs friction:

```sh
cat <<'EOF' >/tmp/friction-event.json
{
  "title": "Referenced CI check script does not exist",
  "instruction_source": "AGENTS.md:18",
  "instruction_text": "Run scripts/ci-check.sh to see the current build status.",
  "action_taken": "Ran find scripts/ -name 'ci-check.sh' — no results.",
  "expected_outcome": "The file scripts/ci-check.sh exists and produces build status output.",
  "actual_outcome": "scripts/ci-check.sh does not exist.",
  "interpretation": "I understood the instruction as pointing to an existing repository script because it uses an imperative command with a concrete path."
}
EOF

sh scripts/report-friction.sh \
  --task-summary "Investigate build-routing failures" \
  --agent orchestrator \
  --skill-path "$(pwd)" \
  --from-json /tmp/friction-event.json
```

Subagent logs friction (auto-joins the same session):

```sh
cat <<'EOF' >/tmp/friction-subagent.json
{
  "title": "MCP docker_inspect omits healthcheck data",
  "instruction_source": "MCP tool description for docker_inspect",
  "instruction_text": "Inspect a running container and return its full configuration.",
  "action_taken": "Called docker_inspect with {\"container_id\": \"abc123\"}.",
  "expected_outcome": "A JSON object containing the container's full configuration, including a healthcheck key.",
  "actual_outcome": "Response omitted any Healthcheck field.",
  "interpretation": "I understood 'full configuration' to mean the complete container config as Docker defines it."
}
EOF

sh scripts/report-friction.sh \
  --task-summary "Investigate build-routing failures" \
  --agent subagent \
  --role research \
  --skill-path "$(pwd)" \
  --from-json /tmp/friction-subagent.json
```

Both agents write to the same task directory. Each gets its own log file and descriptor. Event numbering is global across the shared `events.jsonl`.

For explicit init, the orchestrator can still call `init-log.sh` first to create the manifest before any event exists. Subagents will auto-discover and join that session, and the first call to `report-friction.*` will materialize the log artifacts.

**Legacy pattern**: Passing `--task-id` explicitly still works for cases where you need deterministic session naming or are joining from a different base directory.

## Refreshing the summary

`report-friction.*` already refreshes `INDEX.md` after each appended entry. If the rebuild fails, the command now exits non-zero instead of silently leaving a stale or missing index. Running `build-index.*` manually is still useful after bulk edits, if you moved files around, or to recover after a surfaced rebuild failure.

## End-to-end workflow example

A narrative walkthrough showing multi-agent friction logging across a build investigation task. The exact heuristic results depend on the full entry text — this narrative shows the workflow, not the categorization details.

### Step 1: Orchestrator initializes the manifest

The orchestrator starts a task to investigate CI build failures.

```sh
eval "$(sh scripts/init-log.sh \
  --task-summary "Investigate CI build failures in staging pipeline — PR #247 merged but deploy step reports exit 1 with no useful error message" \
  --agent orchestrator \
  --skill-path "$(pwd)")"
```

At this point only `SESSION.txt`, `TASK_SUMMARY.txt`, and `task.json` exist. No markdown log, descriptor, `events.jsonl`, `incidents.json`, `INDEX.md`, or `exports/` artifact exists yet.

The orchestrator reads AGENTS.md, which says: "Run `scripts/ci-check.sh` to see the current build status." The script does not exist — `find scripts/ -name 'ci-check.sh'` returns nothing.

```sh
cat <<'EOF' >/tmp/orchestrator-friction.json
{
  "title": "Referenced CI check script does not exist",
  "instruction_source": "AGENTS.md:18, under '## Build verification'",
  "instruction_text": "Run scripts/ci-check.sh to see the current build status. This appears as a direct instruction, not a conditional or example. No alternative path is mentioned.",
  "action_taken": "Ran find scripts/ -name 'ci-check.sh' — no results. Ran grep -r 'ci-check' scripts/ — no results. Ran ls scripts/ — found only build.sh and test.sh. Checked git log --all --diff-filter=D -- scripts/ci-check.sh — no history of deletion.",
  "expected_outcome": "The file scripts/ci-check.sh exists and produces build status output. AGENTS.md presents it as a concrete instruction with a specific path, implying the file is present and ready to run.",
  "actual_outcome": "scripts/ci-check.sh does not exist and has never existed in the repository's git history. The scripts/ directory contains build.sh and test.sh but nothing matching ci-check. No alternative build-status command is documented.",
  "interpretation": "I understood 'Run scripts/ci-check.sh' as a direct instruction to execute an existing file, because AGENTS.md presents it as a concrete path in imperative form with no qualifiers like 'if available' or 'create if missing'. The scripts/ directory is real and contains other scripts, which reinforced my expectation that this one should also be present."
}
EOF

sh scripts/report-friction.sh \
  --task-dir "$FRICTION_TASK_DIR" \
  --from-json /tmp/orchestrator-friction.json
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

This creates a second log file in the same task directory. The subagent shares `events.jsonl`, `incidents.json`, and `INDEX.md` with the orchestrator — event numbering continues globally from where the orchestrator left off.

### Step 3: Subagent encounters MCP friction

The subagent calls the `docker_inspect` MCP tool expecting a `healthcheck` key in the response. The tool returns container metadata without it.

```sh
cat <<'EOF' >/tmp/subagent-friction.json
{
  "title": "MCP docker_inspect omits healthcheck data",
  "instruction_source": "MCP tool description for docker_inspect, field: description",
  "instruction_text": "Inspect a running container and return its full configuration. The parameter schema lists one required field: container_id (string). The description says 'full configuration' without qualifying which fields are included or excluded.",
  "action_taken": "Called docker_inspect with {\"container_id\": \"abc123\"}. The task required checking the container's healthcheck interval, so I expected the healthcheck block in the response.",
  "expected_outcome": "A JSON object containing the container's full configuration, including a healthcheck key with interval, timeout, retries, and test command — consistent with what 'full configuration' means in Docker's own API.",
  "actual_outcome": "Response contained 14 top-level keys: Id, Name, Image, State, NetworkSettings, Mounts, Config, HostConfig, Platform, Driver, RestartCount, Created, Path, Args. No Healthcheck field at any level. The response is a curated subset, not the full configuration the description promises.",
  "interpretation": "I understood 'full configuration' to mean the complete container config as Docker defines it, because that phrase has a specific meaning in the Docker API — it includes healthcheck, resource limits, and all other config blocks. The tool description uses Docker's own terminology without scoping it down, so I had no reason to expect a filtered subset.",
  "workaround_used": true,
  "workaround_note": "Ran docker inspect abc123 directly via CLI to get the healthcheck block.",
  "minutes_lost": 4
}
EOF

sh scripts/report-friction.sh \
  --task-dir "$FRICTION_TASK_DIR" \
  --from-json /tmp/subagent-friction.json
```

With the current wording, this lands on `mcp/other/degraded`. If you want the stricter `mcp/output-mismatch/degraded` label, add output-mismatch language or override `--mode output-mismatch`.

### Step 4: Subagent encounters performance friction

The build runbook says `npm run verify` completes in under 30 seconds, but the process hung for 120 seconds then was OOM-killed.

```sh
cat <<'EOF' >/tmp/verify-friction.json
{
  "title": "Verify step hung and was OOM-killed",
  "instruction_source": "docs/runbooks/build-verification.md:12, under '## Quick verification'",
  "instruction_text": "Run npm run verify. This should complete in under 30 seconds. The runbook does not mention memory requirements, container resource limits, or OOM risk. No --max-old-space-size or ulimit guidance.",
  "action_taken": "Ran npm run verify in the build container (node:20-slim, 512MB memory limit). The container's resource constraints are set in docker-compose.yaml:45 but not referenced in the runbook. I used the command exactly as documented.",
  "expected_outcome": "The process completes within 30 seconds and exits 0 (pass) or 1 (fail). The runbook's 30-second estimate implies this is a lightweight check.",
  "actual_outcome": "Process ran for 120 seconds with monotonically increasing RSS. At ~490MB it was killed by the OOM killer — exit code 137 (SIGKILL). dmesg shows: 'Out of memory: Killed process 4821 (node)'. No partial output was produced before the kill.",
  "interpretation": "I understood 'should complete in under 30 seconds' as a reliable time estimate for the verification step. The word 'should' and the specific '30 seconds' figure made it sound like a measured expectation, not a hope. I did not check container memory limits because the runbook frames this as a quick, lightweight step. Nothing in the runbook or the npm script's package.json entry warned about memory-intensive behavior.",
  "retries_lost": 1,
  "minutes_lost": 5
}
EOF

sh scripts/report-friction.sh \
  --task-dir "$FRICTION_TASK_DIR" \
  --from-json /tmp/verify-friction.json
```

With the current wording, this lands on `instructions/other/degraded`. If you want `instructions/performance/blocked`, say so explicitly in the entry text or override `--mode performance --run-effect blocked`.

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
**Task summary:** Investigate CI build failures in staging pipeline — PR #247 merged but deploy step reports exit 1 with no useful error message
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
