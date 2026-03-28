Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
. "$root/scripts/_Common.ps1"

$repoDir = Join-Path ([System.IO.Path]::GetTempPath()) ("agent-friction-ps-smoke-{0}" -f [System.Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $repoDir -Force
& git init -q $repoDir
$null = New-Item -ItemType Directory -Path (Join-Path $repoDir '.local') -Force

try {
    if ((Get-ShortSha256 'abc') -ne 'ba7816bf') { throw 'Get-ShortSha256 should return the first 8 hex chars of the SHA256 digest' }

    $eventsFile = Join-Path $repoDir '.local/reports/friction/events.jsonl'
    $indexFile = Join-Path $repoDir '.local/reports/friction/INDEX.md'

    # --- Test 1: stdin JSON with v3 sources array ---
    $stdinJson = @'
{"title":"stdin ingest smoke","instruction_text":"Load event fields from stdin with sk-live-123 and shell-sensitive punctuation like \"quotes\".","action_taken":"Reported friction with -FromJson - to test the JSON input path.","expected_outcome":"PowerShell should accept stdin JSON without shell-escaping payload text.","actual_outcome":"The event was streamed from stdin and recorded successfully.","interpretation":"stdin JSON is the safe transport for shell-sensitive structured input, avoiding escaping issues with special characters.","surface":"workflow","mode":"ambiguity","impact":"confusing","tags":"from-json,json,stdin","sources":[{"type":"documentation","ref":"test","label":"smoke test source"}]}
'@

    $reportOutput = $stdinJson | & "$root/scripts/report-friction.ps1" `
        -RepoRoot $repoDir `
        -FromJson '-'

    if (-not ($reportOutput -match '^event_id=')) { throw 'report-friction.ps1 should emit the new event id' }
    if (-not (Test-Path $eventsFile)) { throw "events.jsonl missing: $eventsFile" }
    if (-not (Test-Path $indexFile)) { throw "INDEX.md missing: $indexFile" }

    $events = Import-Events $eventsFile
    if ($events.Count -ne 1) { throw 'events.jsonl should contain exactly one event after the first append' }
    if ($events[0].title -ne 'stdin ingest smoke') { throw 'events.jsonl should store plain title strings' }
    if ($events[0].schema_version -ne '3.0.0') { throw 'events.jsonl should use schema version 3.0.0' }
    if ($events[0].instruction_text -notmatch '\[REDACTED_API_TOKEN\]') { throw 'report-friction.ps1 should always sanitize API tokens' }
    if ($events[0].provenance_source -ne 'unspecified') { throw 'events.jsonl should mark omitted provenance as unspecified' }
    # v3: sources array present, no anchors or instruction_source
    $raw = [System.IO.File]::ReadAllLines($eventsFile)[0]
    if ($raw -notmatch '"sources":\[') { throw 'events.jsonl should contain sources array' }
    if ($raw -match '"anchors"') { throw 'events.jsonl should NOT contain anchors field' }
    if ($raw -match '"instruction_source"') { throw 'events.jsonl should NOT contain instruction_source field' }
    if ($raw -match '"title_line"') { throw 'events.jsonl should NOT contain title_line field' }
    if ($raw -match '"quick_capture"') { throw 'events.jsonl should NOT contain quick_capture field' }
    if ($raw -match '"privacy_tier"') { throw 'events.jsonl should NOT contain privacy_tier field' }
    if ($raw -match '"tags_csv"') { throw 'events.jsonl should NOT contain tags_csv field' }
    # Tags as JSON array
    if ($raw -notmatch '"tags":\[') { throw 'events.jsonl should contain tags as JSON array' }
    # Numeric confidence and guidance_quality
    if ($raw -notmatch '"confidence":\d') { throw 'confidence should be numeric' }
    if ($raw -notmatch '"guidance_quality":\d') { throw 'guidance_quality should be numeric' }

    $indexText = [System.IO.File]::ReadAllText($indexFile)
    if ($indexText -notmatch '\*\*Entries:\*\* 1') { throw 'INDEX.md should count entries from events.jsonl' }

    # --- Test 2: Direct parameters with --source-type/--source-ref ---
    & "$root/scripts/report-friction.ps1" `
        -RepoRoot $repoDir `
        -Agent 'subagent' `
        -AgentKind 'subagent' `
        -Role 'parallel' `
        -Title 'Follow-on entry' `
        -SourceType 'file' `
        -SourceRef 'AGENTS.md' `
        -SourceLine 18 `
        -InstructionText 'Exercise the direct parameter path with the new source fields.' `
        -ActionTaken 'Recorded a second event using the direct parameter interface.' `
        -ExpectedOutcome 'The repo-scoped log should roll forward.' `
        -ActualOutcome 'A second event was recorded successfully.' `
        -Interpretation 'The repo-scoped design should aggregate multiple agents without task directories or session files.' `
        -Surface 'skill' `
        -Mode 'ambiguity' `
        -Impact 'confusing' | Out-Null

    $events = Import-Events $eventsFile
    if ($events.Count -ne 2) { throw 'events.jsonl should contain two events after the second append' }

    & "$root/scripts/build-index.ps1" -RepoRoot $repoDir | Out-Null
    $indexText = [System.IO.File]::ReadAllText($indexFile)
    if ($indexText -notmatch '\*\*Entries:\*\* 2') { throw 'INDEX.md should report two entries after rebuild' }

    # --- Test 3: Query by agent-kind ---
    $queryJson = & "$root/scripts/query-friction.ps1" -RepoRoot $repoDir -AgentKind 'subagent' -Format json
    $queryEvents = $queryJson | ConvertFrom-Json
    if (@($queryEvents).Count -ne 1) { throw 'query-friction.ps1 should filter rows by agent kind' }
    if ([string]$queryEvents[0].title -ne 'Follow-on entry') { throw 'query-friction.ps1 should return matching event objects' }

    # --- Test 4: v2 backward compat via stdin ---
    $v2Json = @'
{"title":"v2 backward compat","instruction_source":"SKILL.md:160","instruction_text":"Use the documented dispatch role slug from the skill table.","action_taken":"Passed a v2-format payload with instruction_source and anchors to test backward compatibility.","expected_outcome":"The tool auto-converts instruction_source and anchors to sources array.","actual_outcome":"The event was recorded with a properly converted sources array.","interpretation":"v2 payloads should be accepted and automatically migrated to v3 sources format for backward compatibility.","anchors":[{"kind":"file","path":"/abs/path/SKILL.md","line":160}]}
'@
    $v2Json | & "$root/scripts/report-friction.ps1" -RepoRoot $repoDir -FromJson '-' | Out-Null
    $events = Import-Events $eventsFile
    if ($events.Count -ne 3) { throw 'v2 compat JSON should append a third event' }
    $lastRaw = [System.IO.File]::ReadAllLines($eventsFile)[2]
    if ($lastRaw -notmatch '"sources":\[') { throw 'v2 compat: should have sources array' }
    if ($lastRaw -match '"anchors"') { throw 'v2 compat: should NOT have anchors in output' }

    # --- Test 5: Invalid JSON diagnostics ---
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

    # --- Test 6: Alternate .local* directory ---
    $altRepoDir = Join-Path ([System.IO.Path]::GetTempPath()) ("agent-friction-ps-alt-{0}" -f [System.Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $altRepoDir -Force
    & git init -q $altRepoDir
    $null = New-Item -ItemType Directory -Path (Join-Path $altRepoDir '.local-test') -Force
    try {
        & "$root/scripts/report-friction.ps1" `
            -RepoRoot $altRepoDir `
            -Title 'Alternate local dir' `
            -SourceType 'documentation' `
            -SourceRef 'test' `
            -InstructionText 'Use an existing .local* directory when .local is absent.' `
            -ActionTaken 'Reported friction from a repo containing only .local-test to test fallback.' `
            -ExpectedOutcome 'The default events file lands under .local-test/reports/friction.' `
            -ActualOutcome 'The tool selected the existing .local-test directory.' `
            -Interpretation 'An existing .local* directory should win over creating a new .local, preserving the existing local state layout.' | Out-Null
        $altEventsFile = Join-Path $altRepoDir '.local-test/reports/friction/events.jsonl'
        if (-not (Test-Path $altEventsFile)) { throw 'report-friction.ps1 should use an existing .local* directory when .local is absent' }
    }
    finally {
        if (Test-Path $altRepoDir) {
            Remove-Item -Recurse -Force $altRepoDir
        }
    }

    Write-Output 'smoke-powershell: ok'
}
finally {
    if (Test-Path $repoDir) {
        Remove-Item -Recurse -Force $repoDir
    }
}
