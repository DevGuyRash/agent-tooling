Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
. "$root/scripts/_Common.ps1"

$repoDir = Join-Path ([System.IO.Path]::GetTempPath()) ("agent-friction-ps-smoke-{0}" -f [System.Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $repoDir -Force
$null = New-Item -ItemType Directory -Path (Join-Path $repoDir '.git') -Force
$null = New-Item -ItemType Directory -Path (Join-Path $repoDir '.local/context') -Force

try {
    if ((Get-ShortSha256 'abc') -ne 'ba7816bf') { throw 'Get-ShortSha256 should return the first 8 hex chars of the SHA256 digest' }

    $eventsFile = Join-Path $repoDir '.local/context/friction/events.jsonl'
    $indexFile = Join-Path $repoDir '.local/context/friction/INDEX.md'

    $stdinJson = @'
{"title":"stdin ingest smoke","instruction_source":"test","instruction_text":"Load event fields from stdin with sk-live-123 and shell-sensitive punctuation like \"quotes\".","action_taken":"Reported friction with -FromJson -.","expected_outcome":"PowerShell should accept stdin JSON without shell-escaping payload text.","actual_outcome":"The event was streamed from stdin and recorded.","interpretation":"stdin JSON is the safe transport for shell-sensitive structured input.","surface":"workflow","mode":"ambiguity","impact":"confusing","tags":"from-json,json,stdin"}
'@

    $reportOutput = $stdinJson | & "$root/scripts/report-friction.ps1" `
        -RepoRoot $repoDir `
        -FromJson '-'

    if (-not ($reportOutput -match '^event_id=')) { throw 'report-friction.ps1 should emit the new event id' }
    if (-not (Test-Path $eventsFile)) { throw "events.jsonl missing: $eventsFile" }
    if (-not (Test-Path $indexFile)) { throw "INDEX.md missing: $indexFile" }
    if (Test-Path (Join-Path $repoDir 'incidents.json')) { throw 'report-friction.ps1 should not materialize incidents.json in the repo root' }
    if (Get-ChildItem -Path $repoDir -Recurse -Filter '*.descriptor.json' -ErrorAction SilentlyContinue) { throw 'report-friction.ps1 should not create descriptor files' }

    $events = Import-Events $eventsFile
    if ($events.Count -ne 1) { throw 'events.jsonl should contain exactly one event after the first append' }
    if ($events[0].title -ne 'stdin ingest smoke') { throw 'events.jsonl should store plain title strings' }
    if ($events[0].instruction_text -notmatch '\[REDACTED_API_TOKEN\]') { throw 'report-friction.ps1 should always sanitize API tokens' }
    if ($events[0].provenance_source -ne 'unspecified') { throw 'events.jsonl should mark omitted provenance as unspecified' }
    if ($events[0].agent_name -ne '') { throw 'events.jsonl should store blank agent_name when provenance is unspecified' }
    if ($events[0].agent_kind -ne '') { throw 'events.jsonl should store blank agent_kind when provenance is unspecified' }
    if ($events[0].role -ne '') { throw 'events.jsonl should store blank role when provenance is unspecified' }
    if ($events[0].events_file -ne '.local/context/friction/events.jsonl') { throw 'events.jsonl should store the repo-relative events file path' }

    $indexText = [System.IO.File]::ReadAllText($indexFile)
    if ($indexText -notmatch '\*\*Entries:\*\* 1') { throw 'INDEX.md should count entries from events.jsonl' }
    if ($indexText -notmatch '- ``workflow/ambiguity/continued`` - 1') { throw 'INDEX.md should aggregate categories from events.jsonl' }
    if ($indexText -notmatch '_No explicit provenance recorded._') { throw 'INDEX.md should state when no explicit provenance is recorded' }

    & "$root/scripts/report-friction.ps1" `
        -RepoRoot $repoDir `
        -Agent 'subagent' `
        -AgentKind 'subagent' `
        -Role 'parallel' `
        -Title 'Follow-on entry' `
        -InstructionSource 'test' `
        -InstructionText 'Exercise the direct parameter path.' `
        -ActionTaken 'Recorded a second event.' `
        -ExpectedOutcome 'The repo-scoped log should roll forward.' `
        -ActualOutcome 'A second event was recorded.' `
        -Interpretation 'The repo-scoped design should aggregate multiple agents without task directories.' `
        -Surface 'skill' `
        -Mode 'ambiguity' `
        -Impact 'confusing' | Out-Null

    $events = Import-Events $eventsFile
    if ($events.Count -ne 2) { throw 'events.jsonl should contain two events after the second append' }

    & "$root/scripts/build-index.ps1" -RepoRoot $repoDir | Out-Null
    $indexText = [System.IO.File]::ReadAllText($indexFile)
    if ($indexText -notmatch '\*\*Entries:\*\* 2') { throw 'INDEX.md should report two entries after rebuild' }
    if ($indexText -notmatch '- ``skill/ambiguity/continued`` - 1') { throw 'INDEX.md should include the second category count' }
    if ($indexText -notmatch '## Agent counts') { throw 'INDEX.md should include agent counts after explicit provenance is recorded' }
    if ($indexText -notmatch '- ``subagent`` - 1') { throw 'INDEX.md should aggregate explicit provenance only' }
    if ($indexText -notmatch 'Follow-on entry') { throw 'INDEX.md recent events should include the second title' }

    $queryMd = & "$root/scripts/query-friction.ps1" -RepoRoot $repoDir -Category 'workflow/ambiguity/continued' -Format md
    if ($queryMd -notmatch 'stdin ingest smoke') { throw 'query-friction.ps1 should print filtered event titles' }
    if ($queryMd -match '- Agent:') { throw 'query-friction.ps1 markdown should omit provenance lines when provenance is unspecified' }

    $queryJson = & "$root/scripts/query-friction.ps1" -RepoRoot $repoDir -AgentKind 'subagent' -Format json
    $queryEvents = $queryJson | ConvertFrom-Json
    if (@($queryEvents).Count -ne 1) { throw 'query-friction.ps1 should filter rows by agent kind' }
    if ([string]$queryEvents[0].title -ne 'Follow-on entry') { throw 'query-friction.ps1 should return matching event objects' }

    $invalidJsonPath = Join-Path $repoDir 'invalid-event.json'
    [System.IO.File]::WriteAllText($invalidJsonPath, '{bad json}', [System.Text.UTF8Encoding]::new($false))
    try {
        & "$root/scripts/report-friction.ps1" -RepoRoot $repoDir -FromJson $invalidJsonPath | Out-Null
        throw 'report-friction.ps1 should reject invalid JSON payloads'
    }
    catch {
        if ($_.Exception.Message -notmatch 'Invalid JSON in -FromJson') {
            throw 'report-friction.ps1 should emit a concise parse diagnostic for invalid -FromJson payloads'
        }
    }

    $wrongEventsJsonPath = Join-Path $repoDir 'wrong-events.json'
    [System.IO.File]::WriteAllText($wrongEventsJsonPath, @'
{"title":"Wrong events file","instruction_source":"test","instruction_text":"Carry an events_file override.","action_taken":"Attempted to report friction.","expected_outcome":"The script rejects mismatched events_file values.","actual_outcome":"The script should stop with a concise schema diagnostic.","interpretation":"The explicit or canonical events file is authoritative.","events_file":"/tmp/not-the-selected-events.jsonl"}
'@, [System.Text.UTF8Encoding]::new($false))
    try {
        & "$root/scripts/report-friction.ps1" -RepoRoot $repoDir -FromJson $wrongEventsJsonPath | Out-Null
        throw 'report-friction.ps1 should reject mismatched events_file values'
    }
    catch {
        if ($_.Exception.Message -notmatch 'events_file .* must match the selected events file') {
            throw 'report-friction.ps1 should emit a concise schema diagnostic for mismatched events_file'
        }
    }

    Write-Output 'smoke-powershell: ok'
}
finally {
    if (Test-Path $repoDir) {
        Remove-Item -Recurse -Force $repoDir
    }
}
