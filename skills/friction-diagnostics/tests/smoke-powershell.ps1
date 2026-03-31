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
{"title":"stdin ingest smoke","instruction_text":"Load event fields from stdin with sk-live-123 and shell-sensitive punctuation like \"quotes\".","action_taken":"Reported friction with -FromJson - to test the JSON input path.","expected_outcome":"PowerShell should accept stdin JSON without shell-escaping payload text.","actual_outcome":"The event was streamed from stdin and recorded successfully.","reading":"stdin JSON is the safe transport for shell-sensitive structured input, avoiding escaping issues with special characters.","hindsight":"Use -FromJson - for all payloads containing special characters or multiline text.","surface":"workflow","mode":"ambiguity","sources":[{"type":"documentation","ref":"test","label":"smoke test source"}]}
'@

    $reportOutput = $stdinJson | & "$root/scripts/report-friction.ps1" `
        -RepoRoot $repoDir `
        -FromJson '-'

    if (-not ($reportOutput -match '^event_id=')) { throw 'report-friction.ps1 should emit the new event id' }
    if (-not (Test-Path $eventsFile)) { throw "events.jsonl missing: $eventsFile" }
    if (-not (Test-Path $indexFile)) { throw "INDEX.md missing: $indexFile" }

    $events = @(Import-Events $eventsFile)
    if ($events.Count -ne 1) { throw 'events.jsonl should contain exactly one event after the first append' }
    if ($events[0].title -ne 'stdin ingest smoke') { throw 'events.jsonl should store plain title strings' }
    if ($events[0].schema_version -ne '3.0.0') { throw 'events.jsonl should use schema version 3.0.0' }
    if ($events[0].instruction_text -notmatch '\[REDACTED_API_TOKEN\]') { throw 'report-friction.ps1 should always sanitize API tokens' }
    # provenance_source removed — identity fields are shown when non-empty
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
    if ($indexText -notmatch '\*\*Index rebuilt:\*\*') { throw 'INDEX.md should use the rebuilt label' }
    if ($indexText -notmatch '\*\*Earliest event:\*\*') { throw 'INDEX.md should include earliest event label' }
    if ($indexText -notmatch '\*\*Latest event:\*\*') { throw 'INDEX.md should include latest event label' }

    # --- Test 2: Direct parameters with --source-type/--source-ref ---
    & "$root/scripts/report-friction.ps1" `
        -RepoRoot $repoDir `
        -Agent 'subagent' `
        -Role 'parallel' `
        -Title 'Follow-on entry' `
        -SourceType 'file' `
        -SourceRef 'AGENTS.md' `
        -SourceLine 18 `
        -InstructionText 'Exercise the direct parameter path with the new source fields.' `
        -ActionTaken 'Recorded a second event using the direct parameter interface.' `
        -ExpectedOutcome 'The repo-scoped log should roll forward.' `
        -ActualOutcome 'A second event was recorded successfully.' `
        -Reading 'The repo-scoped design should aggregate multiple agents without task directories or session files.' `
        -Hindsight 'Pre-confirm the events file path before recording to avoid misdirected writes.' `
        -Surface 'skill' `
        -Mode 'ambiguity' | Out-Null

    $events = @(Import-Events $eventsFile)
    if ($events.Count -ne 2) { throw 'events.jsonl should contain two events after the second append' }

    & "$root/scripts/build-index.ps1" -RepoRoot $repoDir | Out-Null
    $indexText = [System.IO.File]::ReadAllText($indexFile)
    if ($indexText -notmatch '\*\*Entries:\*\* 2') { throw 'INDEX.md should report two entries after rebuild' }
    if ($indexText -notmatch '## Top Sources') { throw 'INDEX.md should include top sources from the enhanced index report' }

    # --- Test 3: AddTags rewrites safely and preserves array tags ---
    & "$root/scripts/report-friction.ps1" -EventsFile $eventsFile -IndexFile $indexFile -RepoRoot $repoDir -AddTags 'evt-0001' -AddTagsCsv 'powershell,smoke' | Out-Null
    $events = @(Import-Events $eventsFile)
    if (@($events[0].tags).Count -ne 2) { throw 'AddTags should preserve tags as an array' }
    if (@($events[0].tags) -notcontains 'powershell') { throw 'AddTags should add requested tags' }

    # --- Test 4: Query by role ---
    $queryJson = & "$root/scripts/query-friction.ps1" -RepoRoot $repoDir -Role 'parallel' -Format json
    $queryEvents = $queryJson | ConvertFrom-Json
    if (@($queryEvents).Count -ne 1) { throw 'query-friction.ps1 should filter rows by role' }
    if ([string]$queryEvents[0].title -ne 'Follow-on entry') { throw 'query-friction.ps1 should return matching event objects' }

    # --- Test 5: Expanded filters + report generator ---
    $filterOutput = & "$root/scripts/report-friction.ps1" `
        -RepoRoot $repoDir `
        -Title 'PowerShell filter coverage' `
        -SourceType 'documentation' `
        -SourceRef 'test' `
        -InstructionText 'Use the structured jq report path for diagnostics.' `
        -ActionTaken 'Recorded a filter-focused event with tool metadata and a workaround so the expanded query filters have one deterministic target.' `
        -ExpectedOutcome 'The event would persist tool name, owner, component, exit code, confidence, guidance, and workaround metadata.' `
        -ActualOutcome 'The command degraded but continued, and the workaround left the run at exit code 7.' `
        -Reading 'This event exists to verify the expanded query filters. The phrase structured payload appears here so the text filter can match deterministically.' `
        -Hindsight 'Use purpose-built events when validating filter dimensions.' `
        -Surface 'skill' `
        -Mode 'schema' `
        -RunEffect 'degraded' `
        -ToolName 'jq' `
        -OwnerHint 'skill-owner' `
        -ComponentHint 'query-engine' `
        -WorkaroundUsed 'true' `
        -ExitCode '7' `
        -Confidence 'high' `
        -GuidanceQuality 'partial'
    $filterEventId = ($filterOutput | Where-Object { $_ -like 'event_id=*' }) -replace '^event_id=', ''
    if ([string]::IsNullOrWhiteSpace($filterEventId)) { throw 'filter coverage event should emit an event id' }
    & "$root/scripts/report-friction.ps1" -EventsFile $eventsFile -IndexFile $indexFile -RepoRoot $repoDir -AddTags $filterEventId -AddTagsCsv 'jq,report,filter-smoke' | Out-Null

    $filterJson = & "$root/scripts/query-friction.ps1" `
        -RepoRoot $repoDir `
        -Surface 'skill' `
        -Mode 'schema' `
        -RunEffect 'degraded' `
        -ToolName 'jq' `
        -OwnerHint 'skill-owner' `
        -ComponentHint 'query-engine' `
        -Workaround `
        -ExitCode '7' `
        -ConfidenceMin '4' `
        -ConfidenceMax '4' `
        -GuidanceMin '3' `
        -GuidanceMax '3' `
        -Text 'structured payload' `
        -Tag 'report' `
        -Format json
    $filterEvents = $filterJson | ConvertFrom-Json
    if (@($filterEvents).Count -ne 1) { throw 'expanded filters should isolate the filter coverage event' }
    if ([string]$filterEvents[0].title -ne 'PowerShell filter coverage') { throw 'expanded filters should return the filter coverage event' }

    $indexReport = & "$root/scripts/generate-report.ps1" -RepoRoot $repoDir -ReportType index -Format md
    if ($indexReport -notmatch '## Top Sources') { throw 'generate-report.ps1 index should include top sources' }
    if ($indexReport -notmatch '## Run Effect Summary') { throw 'generate-report.ps1 index should include run effect summary' }
    $indexJson = & "$root/scripts/generate-report.ps1" -RepoRoot $repoDir -ReportType index -Format json | ConvertFrom-Json
    if ([string]$indexJson.report_type -ne 'index') { throw 'index json should label the report type' }
    if (@($indexJson.top_sources).Count -lt 1) { throw 'index json should include structured top_sources rows' }

    $timeseriesJson = & "$root/scripts/generate-report.ps1" -RepoRoot $repoDir -ReportType timeseries -GroupBy surface -Format json
    $timeseries = $timeseriesJson | ConvertFrom-Json
    if ([string]$timeseries.group_by -ne 'surface') { throw 'timeseries report should record the group-by dimension' }
    if (@($timeseries.rows).Count -lt 1) { throw 'timeseries report should include at least one row' }
    if (@($timeseries.columns).Count -lt 1) { throw 'timeseries report should include grouped columns' }

    $emptyCross = & "$root/scripts/generate-report.ps1" -RepoRoot $repoDir -ReportType cross-repo -Tag 'does-not-exist' -Format json | ConvertFrom-Json
    if ([int]$emptyCross.total_entries -ne 0) { throw 'empty cross-repo json should report zero entries' }
    if ([int]$emptyCross.repos_scanned -ne 0) { throw 'empty cross-repo json should report zero repos scanned' }
    if (@($emptyCross.repos).Count -ne 0) { throw 'empty cross-repo json should emit an empty repos array' }

    $emptyPerRepo = & "$root/scripts/generate-report.ps1" -RepoRoot $repoDir -ReportType per-repo -Tag 'does-not-exist' -Format md
    if ($emptyPerRepo -notmatch '_No repos matched the selected filters._') { throw 'empty per-repo report should render a clear empty-state message' }

    $emptyTimeseries = & "$root/scripts/generate-report.ps1" -RepoRoot $repoDir -ReportType timeseries -Tag 'does-not-exist' -Format md
    if ($emptyTimeseries -notmatch '_No dated events matched the selected filters._') { throw 'empty timeseries report should render a clear empty-state message' }

    try {
        & "$root/scripts/generate-report.ps1" -RepoRoot $repoDir -ReportType cross-repo -GroupBy surface | Out-Null
        throw 'generate-report.ps1 should reject -GroupBy outside the timeseries report type'
    }
    catch {
        if ($_.Exception.Message -notmatch 'only supported with -ReportType timeseries') {
            throw 'generate-report.ps1 should emit a focused diagnostic for invalid -GroupBy usage'
        }
    }

    $spaceRepoDir = Join-Path ([System.IO.Path]::GetTempPath()) ("agent friction ps spaces {0}" -f [System.Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $spaceRepoDir -Force
    & git init -q $spaceRepoDir
    try {
        & "$root/scripts/report-friction.ps1" `
            -RepoRoot $spaceRepoDir `
            -Title 'Space path repo' `
            -SourceType 'documentation' `
            -SourceRef 'test' `
            -InstructionText 'Use scan-dirs with paths that may contain spaces.' `
            -ActionTaken 'Recorded an event in a repo whose path contains spaces so discovery paths can be validated with a real quoting fixture.' `
            -ExpectedOutcome 'The generated events file would live under a path containing spaces and later -ScanDirs calls would still discover it correctly.' `
            -ActualOutcome 'The reporter wrote the event under the space-containing repo path.' `
            -Reading 'Space-containing paths are a common quoting failure mode for shell and script wrappers. A real repo fixture catches these regressions more reliably than synthetic string-only checks.' `
            -Hindsight 'Keep one path-with-spaces fixture in the smoke suite whenever discovery or path passing changes.' | Out-Null

        $spaceCross = & "$root/scripts/generate-report.ps1" -ScanDirs @($spaceRepoDir) -ReportType cross-repo -Format json | ConvertFrom-Json
        if ([int]$spaceCross.repos_scanned -ne 1) { throw 'space-path scan should discover one repo' }
        if ([string]$spaceCross.repos[0].repo_root -ne $spaceRepoDir) { throw 'space-path scan should preserve the full repo path' }

    try {
        & "$root/scripts/generate-report.ps1" -ScanDirs @($repoDir, $spaceRepoDir) -ReportType index | Out-Null
        throw 'generate-report.ps1 index should reject multi-file scan input'
        }
        catch {
            if ($_.Exception.Message -notmatch 'exactly one events file') {
                throw 'generate-report.ps1 should emit a focused diagnostic when index input resolves to multiple event files'
            }
        }
    }
    finally {
        if (Test-Path $spaceRepoDir) {
            Remove-Item -Recurse -Force $spaceRepoDir
        }
    }

    $malformedEventsFile = Join-Path $repoDir 'malformed-events.jsonl'
    [System.IO.File]::WriteAllText($malformedEventsFile, "{""title"":""ok""}$([Environment]::NewLine)not-json$([Environment]::NewLine)", [System.Text.UTF8Encoding]::new($false))
    try {
        & "$root/scripts/query-friction.ps1" -EventsFile $malformedEventsFile -Format json | Out-Null
        throw 'query-friction.ps1 should reject malformed events.jsonl input'
    }
    catch {
        if ($_.Exception.Message -notmatch 'Invalid JSON in events file at line 2') {
            throw 'query-friction.ps1 should report the malformed line number'
        }
    }
    try {
        & "$root/scripts/generate-report.ps1" -EventsFile $malformedEventsFile -ReportType index -Format json | Out-Null
        throw 'generate-report.ps1 should reject malformed events.jsonl input'
    }
    catch {
        if ($_.Exception.Message -notmatch 'Invalid JSON in events file at line 2') {
            throw 'generate-report.ps1 should report the malformed line number'
        }
    }
    try {
        & "$root/scripts/build-index.ps1" -EventsFile $malformedEventsFile -IndexFile (Join-Path $repoDir 'bad-index.md') -RepoRoot $repoDir | Out-Null
        throw 'build-index.ps1 should reject malformed events.jsonl input'
    }
    catch {
        if ($_.Exception.Message -notmatch 'Invalid JSON in events file at line 2') {
            throw 'build-index.ps1 should report the malformed line number'
        }
    }

    $partialEventsFile = Join-Path $repoDir 'partial-events.jsonl'
    [System.IO.File]::WriteAllText($partialEventsFile, "{""title"":""partial row""}$([Environment]::NewLine)", [System.Text.UTF8Encoding]::new($false))
    $partialQuery = & "$root/scripts/query-friction.ps1" -EventsFile $partialEventsFile -Format json | ConvertFrom-Json
    if (@($partialQuery).Count -ne 1 -or [string]$partialQuery[0].title -ne 'partial row') { throw 'query-friction.ps1 should tolerate sparse but valid event rows' }
    $partialIndex = & "$root/scripts/generate-report.ps1" -EventsFile $partialEventsFile -ReportType index -Format json | ConvertFrom-Json
    if ([int]$partialIndex.entries -ne 1) { throw 'generate-report.ps1 should count sparse but valid event rows' }
    if (@($partialIndex.category_counts).Count -ne 0) { throw 'sparse rows should not fabricate category counts' }

    $futureRunEffectEventsFile = Join-Path $repoDir 'future-run-effect-events.jsonl'
    [System.IO.File]::WriteAllText($futureRunEffectEventsFile, "{""title"":""future run effect"",""derived_category"":""skill/schema/future-state""}$([Environment]::NewLine)", [System.Text.UTF8Encoding]::new($false))
    $futureIndex = & "$root/scripts/generate-report.ps1" -EventsFile $futureRunEffectEventsFile -ReportType index -Format json | ConvertFrom-Json
    if (@($futureIndex.run_effect_summary).Count -ne 1) { throw 'index report should preserve nonstandard run_effect values' }
    if ([string]$futureIndex.run_effect_summary[0].value -ne 'future-state') { throw 'index report should include the nonstandard run_effect value' }
    $futureCross = & "$root/scripts/generate-report.ps1" -EventsFile $futureRunEffectEventsFile -ReportType cross-repo -Format json | ConvertFrom-Json
    if (@($futureCross.run_effect_summary).Count -ne 1) { throw 'cross-repo report should preserve nonstandard run_effect values' }
    if ([string]$futureCross.run_effect_summary[0].value -ne 'future-state') { throw 'cross-repo report should include the nonstandard run_effect value' }

    $bulkEventsFile = Join-Path $repoDir 'bulk-events.jsonl'
    $builder = [System.Text.StringBuilder]::new()
    foreach ($i in 1..250) {
        $minute = $i % 60
        $bulkEventJson = [pscustomobject]@{
            title = "bulk event $i"
            recorded_at = ('2026-03-30T00:{0:00}:00Z' -f $minute)
            event_id = ('evt-{0:0000}' -f $i)
            derived_category = 'skill/schema/continued'
            fingerprint = ('fp-{0:0000}' -f $i)
            tags = @('bulk', 'load')
            sources = @(@{ ref = 'bulk' })
            repo_root = '/tmp/bulk'
            events_file = '/tmp/bulk/events.jsonl'
        } | ConvertTo-Json -Compress
        $null = $builder.AppendLine([string]$bulkEventJson)
    }
    [System.IO.File]::WriteAllText($bulkEventsFile, $builder.ToString(), [System.Text.UTF8Encoding]::new($false))
    $bulkQuery = & "$root/scripts/query-friction.ps1" -EventsFile $bulkEventsFile -Tag 'bulk' -Format json | ConvertFrom-Json
    if (@($bulkQuery).Count -ne 250) { throw 'query-friction.ps1 bulk probe should return every tagged synthetic event' }
    $bulkTimeseries = & "$root/scripts/generate-report.ps1" -EventsFile $bulkEventsFile -ReportType timeseries -GroupBy tag -Format json | ConvertFrom-Json
    if ([string]$bulkTimeseries.group_by -ne 'tag') { throw 'bulk timeseries should preserve the tag grouping' }
    if (@($bulkTimeseries.rows).Count -ne 1) { throw 'bulk timeseries should collapse to one dated row for a single date' }
    if ([int]$bulkTimeseries.rows[0].bulk -ne 250 -or [int]$bulkTimeseries.rows[0].load -ne 250) { throw 'bulk timeseries should aggregate grouped tag counts correctly' }

    # --- Test 6: Categorizer catches common missing/name-resolution phrasing ---
    $categorizeOutput = & "$root/scripts/categorize.ps1" `
        -SourceRef 'AGENTS.md' `
        -InstructionText 'Run the staging profile from the deployment helper.' `
        -ActionTaken 'I ran the documented deployment command and checked the repo configuration.' `
        -ExpectedOutcome 'The staging profile would be defined and selectable.' `
        -ActualOutcome 'The config does not define profile staging and the command reported an unsupported role slug.' `
        -Reading 'I treated the profile and slug names as valid identifiers because the wording was imperative and concrete.'
    if ($categorizeOutput -notcontains 'mode=name-resolution') { throw 'categorize.ps1 should classify unsupported slug / not-defined profile wording as name-resolution' }
    if ($categorizeOutput -notcontains 'run_effect=blocked') { throw 'categorize.ps1 should classify unsupported resource wording as blocked' }
    $reviewRegressionOutput = & "$root/scripts/categorize.ps1" `
        -SourceRef 'AGENTS.md' `
        -InstructionText 'Run the lint recipe for the architecture role.' `
        -ActionTaken 'I ran the documented command from the helper wrapper.' `
        -ExpectedOutcome 'The architecture role and lint recipe would both be available.' `
        -ActualOutcome 'role architecture not defined and recipe lint not found' `
        -Reading 'I treated the named role and recipe as concrete identifiers because the instructions presented them as existing names.'
    if ($reviewRegressionOutput -notcontains 'mode=name-resolution') { throw 'categorize.ps1 should preserve name-resolution for role <name> not defined phrasing' }
    if ($reviewRegressionOutput -notcontains 'run_effect=blocked') { throw 'categorize.ps1 should preserve blocked for recipe <name> not found phrasing' }

    # --- Test 7: Invalid JSON diagnostics ---
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

    # --- Test 8: Alternate .local* directory ---
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
            -Reading 'An existing .local* directory should win over creating a new .local, preserving the existing local state layout.' `
            -Hindsight 'Document the .local* precedence rule in the skill so agents do not create a redundant .local directory.' | Out-Null
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
