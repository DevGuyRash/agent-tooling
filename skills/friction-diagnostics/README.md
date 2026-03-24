# friction-diagnostics

`friction-diagnostics` is a reusable Agent Skill for preserving execution friction in a form that later agents can repair from a temp-directory handoff.

It is intentionally broad. The log can capture:

- skill and instruction mismatches
- MCP and server issues
- CLI and script failures
- code and logic missteps
- schema and data-contract problems
- environment and dependency surprises
- workflow, routing, and handoff gaps
- requirement ambiguity and contradictory guidance

## Design choices

### 1. Axis-based categories instead of a brittle flat enum

Each entry is categorized as:

- `surface` — where the friction showed up
- `mode` — what kind of breakdown happened
- `run_effect` — how it affected the run operationally (`blocked`, `degraded`, `noisy`, `continued`)
- `guidance_quality` — how clear or misleading the available guidance was (`clear`, `ambiguous`, `misleading`, `not-applicable`)

That yields compact categories like:

- `skill/name-resolution/blocked`
- `mcp/timeout/blocked`
- `instructions/ambiguity/continued`
- `data/schema/degraded`

This makes the skill broadly useful without needing to predeclare every failure mode in the world.

### 2. Report what happened, not how to fix it

The log is a field report, not a patch plan. It preserves the chain of interpretation that led to the friction so future agents can diagnose the real design problem instead of cargo-culting a one-off fix.

### 3. Deterministic helpers for the mechanical parts

The scripts handle path creation, file naming, entry numbering, category heuristics, and index rebuilding. The model supplies the contextual parts: what the agent read, how it interpreted it, and what actually happened.

## Temp-directory layout

Unix-like systems:

```text
/tmp/agent-friction/<task-id>/<yyyy-mm-dd>/<HH-MM-SS>_<agent>.md
```

Windows:

```text
%TEMP%\agent-friction\<task-id>\<yyyy-MM-dd>\<HH-mm-ss>_<agent>.md
```

Each task directory also gets:

- `INDEX.md` — aggregated category counts and log inventory
- `SESSION.txt` — task-scoped metadata for reuse, stored as one `KEY=value` record per line; it excludes the per-agent `FRICTION_TASK_DESCRIPTOR` pointer
- `TASK_SUMMARY.txt` — full task summary text for multiline-safe reuse
- `task.json` — task-level metadata in JSON
- a per-agent descriptor JSON next to each log file, surfaced as `FRICTION_TASK_DESCRIPTOR`
- `events.jsonl` — one structured JSON line per friction event; it may be empty immediately after init
- `incidents.json` — incident-level aggregation
- `exports/` — sanitized export artifacts

Task IDs and log filename slugs are normalized for filesystem safety. If a
task summary, explicit task ID, agent, or role is too long for a single path
component, the helpers deterministically truncate it and append a short hash.

## Included files

- `SKILL.md` — routing description and execution playbook
- `scripts/` — POSIX sh and PowerShell helpers
- `references/` — logging rules, taxonomy, examples, integration guidance
- `assets/` — paste-ready `AGENTS.md` snippet
- `evals/` — trigger prompts and output-quality scaffolding
- `tests/` — POSIX and PowerShell smoke tests

## Quick start

Unix-like systems:

```sh
SKILL_ROOT=/absolute/path/to/friction-diagnostics

INIT_OUTPUT="$(sh "$SKILL_ROOT/scripts/init-log.sh" \
  --task-summary "Investigate tool dispatch failures — mpcr protocol dispatch returns unknown role errors for documented domain labels" \
  --agent orchestrator \
  --skill-path "$SKILL_ROOT")"

eval "$INIT_OUTPUT"

LOG_FILE=$FRICTION_LOG_FILE
TASK_DIR=$FRICTION_TASK_DIR

sh "$SKILL_ROOT/scripts/report-friction.sh" \
  --log-file "$LOG_FILE" \
  --title "Dispatch role slug mismatch" \
  --instruction-source "SKILL.md:160, inside the Domain routing table" \
  --instruction-text "Use mpcr protocol dispatch --role <ROLE> to get the domain-specific prompt. The table above lists domains: Architecture, Security, Performance. No column distinguishes labels from CLI slugs." \
  --action-taken "Ran mpcr protocol dispatch --role architecture. I picked the label Architecture from the table, lowercased it, and passed it as the ROLE value." \
  --expected-outcome "The CLI prints the architecture domain prompt. The instruction says --role ROLE with the table labels listed directly above, so I expected the label to be the slug." \
  --actual-outcome "error: unknown dispatch role: architecture — exit code 1. The CLI does not list valid slugs in the error output or --help." \
  --interpretation "I understood ROLE to mean the domain labels from the table directly above the instruction, because nothing in SKILL.md distinguishes labels from slugs. The phrasing Use --role ROLE immediately follows the table, which made the labels look like the intended values."

sh "$SKILL_ROOT/scripts/build-index.sh" --task-dir "$TASK_DIR"
```

The helper prints shell exports for convenience, but agent tool invocations are usually isolated processes. Capture the emitted values and pass them back as explicit flags when later commands run in separate shells. `FRICTION_TASK_DESCRIPTOR` points to the current agent's descriptor next to its markdown log; task-scoped handoff data still comes from `SESSION.txt`.

Windows PowerShell:

```powershell
$SkillRoot = "C:\absolute\path\to\friction-diagnostics"
$initOutput = & "$SkillRoot\scripts\init-log.ps1" -TaskSummary "Investigate tool dispatch failures — mpcr protocol dispatch returns unknown role errors for documented domain labels" -Agent orchestrator -SkillPath $SkillRoot
$initMap = @{}
$initOutput | ForEach-Object {
  if ($_ -match '^(FRICTION_[A-Z_]+)=(.*)$') {
    $initMap[$matches[1]] = $matches[2]
  }
}

# For multiline-safe reuse across separate PowerShell invocations, prefer the
# persisted summary file over the line-oriented FRICTION_TASK_SUMMARY output.
$taskSummary = [System.IO.File]::ReadAllText($initMap["FRICTION_TASK_SUMMARY_FILE"])

& "$SkillRoot\scripts\report-friction.ps1" `
  -LogFile $initMap["FRICTION_LOG_FILE"] `
  -Title "Dispatch role slug mismatch" `
  -InstructionSource "SKILL.md:160, inside the Domain routing table" `
  -InstructionText "Use mpcr protocol dispatch --role <ROLE> to get the domain-specific prompt. The table above lists domains: Architecture, Security, Performance. No column distinguishes labels from CLI slugs." `
  -ActionTaken "Ran mpcr protocol dispatch --role architecture. I picked the label Architecture from the table, lowercased it, and passed it as the ROLE value." `
  -ExpectedOutcome "The CLI prints the architecture domain prompt. The instruction says --role ROLE with the table labels listed directly above, so I expected the label to be the slug." `
  -ActualOutcome "error: unknown dispatch role: architecture — exit code 1. The CLI does not list valid slugs in the error output or --help." `
  -Interpretation "I understood ROLE to mean the domain labels from the table directly above the instruction, because nothing in SKILL.md distinguishes labels from slugs."

& "$SkillRoot\scripts\build-index.ps1" -TaskDir $initMap["FRICTION_TASK_DIR"]
```

## Notes

- The POSIX helpers are smoke-tested on Linux in CI.
- The PowerShell helpers target both Windows PowerShell 5.1 and PowerShell 7+.
- The PowerShell helpers are smoke-tested on Windows in CI.
- For multiline-safe reuse across isolated invocations, prefer `FRICTION_TASK_SUMMARY_FILE` over parsing `FRICTION_TASK_SUMMARY` from line-oriented command output.
