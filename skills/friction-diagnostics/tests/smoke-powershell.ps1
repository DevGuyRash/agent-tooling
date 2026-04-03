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

    # --- Test 1b: JSON helper preserves shell-sensitive payloads ---
    $helperJson = @'
{"title":"powershell helper shell-sensitive payload","instruction_text":"WHEN payload text is shell-sensitive THEN the JSON helper SHOULD route it through -FromJson safely.","action_taken":"I piped a JSON payload containing \"quotes\", backticks, and dollar-paren text $(whoami) through report-friction-json.ps1.","expected_outcome":"The helper would forward the payload through the safe JSON path without any quoting damage.","actual_outcome":"The event preserved the shell-sensitive text verbatim and was appended successfully.","reading":"The helper exists to remove manual quoting from the complex-payload path. Using it should be equivalent to invoking report-friction.ps1 -FromJson - directly, while keeping the caller away from shell-sensitive argument assembly.","hindsight":"Use the JSON helper for payloads containing shell-sensitive text instead of building direct flags.","sources":[{"type":"documentation","ref":"test"}]}
'@
    $helperOutput = $helperJson | & "$root/scripts/report-friction-json.ps1" -RepoRoot $repoDir
    if (-not ($helperOutput -match '^FRICTION_EVENT_ID=')) { throw 'report-friction-json.ps1 should emit the underlying report output' }
    $events = @(Import-Events $eventsFile)
    if ($events.Count -ne 2) { throw 'report-friction-json.ps1 should append a second event' }
    if ([string]$events[1].title -ne 'powershell helper shell-sensitive payload') { throw 'report-friction-json.ps1 should preserve the helper payload title' }

    $indexText = [System.IO.File]::ReadAllText($indexFile)
    if ($indexText -notmatch '\*\*Entries:\*\* 2') { throw 'INDEX.md should count entries from events.jsonl' }
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
    if ($events.Count -ne 3) { throw 'events.jsonl should contain three events after the second append' }

    & "$root/scripts/build-index.ps1" -RepoRoot $repoDir | Out-Null
    $indexText = [System.IO.File]::ReadAllText($indexFile)
    if ($indexText -notmatch '\*\*Entries:\*\* 3') { throw 'INDEX.md should report three entries after rebuild' }
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
        -SourceLine '10' `
        -SourceEndLine '14' `
        -SourceSymbol 'query_filter_fixture' `
        -SourceExcerpt 'Use the structured jq report path for diagnostics.' `
        -SourceLabel 'filter coverage fixture' `
        -InstructionText 'Use the structured jq report path for diagnostics.' `
        -ActionTaken 'Recorded a filter-focused event with tool metadata, stdout and stderr excerpts, and a workaround so the expanded query filters have one deterministic target.' `
        -ExpectedOutcome 'The event would persist tool name, owner, component, exit code, confidence, guidance, and workaround metadata.' `
        -ActualOutcome 'The command degraded but continued, and the workaround left the run at exit code 7.' `
        -Reading 'This event exists to verify the expanded query filters. The phrase structured payload appears here so the text filter can match deterministically.' `
        -Hindsight 'Use purpose-built events when validating filter dimensions.' `
        -Surface 'skill' `
        -Mode 'schema' `
        -RunEffect 'degraded' `
        -Command "jq -s '.' report.jsonl" `
        -ToolName 'jq' `
        -Stderr 'jq: warning: synthetic filter coverage stderr' `
        -StdoutExcerpt 'synthetic filter coverage stdout' `
        -OwnerHint 'skill-owner' `
        -ComponentHint 'query-engine' `
        -WorkaroundUsed 'true' `
        -RetriesLost '2' `
        -MinutesLost '11' `
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
    if ([int]$filterEvents[0].sources[0].end_line -ne 14) { throw 'expanded filters should preserve source end_line' }
    if ([string]$filterEvents[0].sources[0].symbol -ne 'query_filter_fixture') { throw 'expanded filters should preserve source symbol' }
    if ([string]$filterEvents[0].sources[0].excerpt -ne 'Use the structured jq report path for diagnostics.') { throw 'expanded filters should preserve source excerpt' }
    if ([string]$filterEvents[0].sources[0].label -ne 'filter coverage fixture') { throw 'expanded filters should preserve source label' }
    if ([string]$filterEvents[0].command -ne "jq -s '.' report.jsonl") { throw 'expanded filters should preserve command' }
    if ([string]$filterEvents[0].stderr -ne 'jq: warning: synthetic filter coverage stderr') { throw 'expanded filters should preserve stderr' }
    if ([string]$filterEvents[0].stdout_excerpt -ne 'synthetic filter coverage stdout') { throw 'expanded filters should preserve stdout_excerpt' }
    if ([int]$filterEvents[0].retries_lost -ne 2) { throw 'expanded filters should preserve retries_lost' }
    if ([int]$filterEvents[0].minutes_lost -ne 11) { throw 'expanded filters should preserve minutes_lost' }

    $filterFingerprint = [string]$filterEvents[0].fingerprint
    if ([string]::IsNullOrWhiteSpace($filterFingerprint)) { throw 'expanded filters should expose a fingerprint' }
    $categoryJson = & "$root/scripts/query-friction.ps1" -RepoRoot $repoDir -Category 'skill/schema/degraded' -Text 'structured payload' -Format json
    $categoryEvents = $categoryJson | ConvertFrom-Json
    if (@($categoryEvents).Count -ne 1) { throw 'category filter should isolate the filter coverage event' }
    if ([string]$categoryEvents[0].event_id -ne $filterEventId) { throw 'category filter should return the filter coverage event' }

    $fingerprintJson = & "$root/scripts/query-friction.ps1" -RepoRoot $repoDir -Fingerprint $filterFingerprint -Format json
    $fingerprintEvents = $fingerprintJson | ConvertFrom-Json
    if (@($fingerprintEvents).Count -ne 1) { throw 'fingerprint filter should isolate the filter coverage event' }
    if ([string]$fingerprintEvents[0].event_id -ne $filterEventId) { throw 'fingerprint filter should return the filter coverage event' }

    $compactJson = & "$root/scripts/query-friction.ps1" -RepoRoot $repoDir -Fingerprint $filterFingerprint -Format json -Compact
    $compactEvents = $compactJson | ConvertFrom-Json
    if (@($compactEvents).Count -ne 1) { throw 'compact query should still return one event' }
    if ($compactEvents[0].PSObject.Properties.Name -contains 'role') { throw 'compact query should remove empty role fields' }
    if ($compactEvents[0].PSObject.Properties.Name -notcontains 'command') { throw 'compact query should keep populated command fields' }
    if ($compactEvents[0].PSObject.Properties.Name -notcontains 'stderr') { throw 'compact query should keep populated stderr fields' }

    $queryMd = & "$root/scripts/query-friction.ps1" -RepoRoot $repoDir -Fingerprint $filterFingerprint -Format md
    if ($queryMd -notmatch 'Retries lost: 2') { throw 'markdown query output should render retries_lost' }
    if ($queryMd -notmatch 'Minutes lost: 11') { throw 'markdown query output should render minutes_lost' }
    if ($queryMd -notmatch 'Sources: test:10-14') { throw 'markdown query output should render source line ranges' }

    $suggestTagsOutput = & "$root/scripts/query-friction.ps1" -RepoRoot $repoDir -SuggestTags
    $suggestedTags = @($suggestTagsOutput -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $sortedSuggestedTags = @($suggestedTags | Sort-Object -Unique)
    if (($suggestedTags -join ',') -ne ($sortedSuggestedTags -join ',')) { throw 'suggest-tags should return sorted unique tags' }
    if ($suggestedTags -notcontains 'filter-smoke') { throw 'suggest-tags should include filter-smoke' }

    $indexReport = & "$root/scripts/generate-report.ps1" -RepoRoot $repoDir -ReportType index -Format md
    if ($indexReport -notmatch '## Top Sources') { throw 'generate-report.ps1 index should include top sources' }
    if ($indexReport -notmatch '## Run Effect Summary') { throw 'generate-report.ps1 index should include run effect summary' }
    if ($indexReport -notmatch '## Top Tools') { throw 'generate-report.ps1 index should include top tools' }
    $indexJson = & "$root/scripts/generate-report.ps1" -RepoRoot $repoDir -ReportType index -Format json | ConvertFrom-Json
    if ([string]$indexJson.report_type -ne 'index') { throw 'index json should label the report type' }
    if (@($indexJson.top_sources).Count -lt 1) { throw 'index json should include structured top_sources rows' }
    if (@($indexJson.tool_counts).Count -lt 1) { throw 'index json should include structured tool counts' }

    $reportTextJson = & "$root/scripts/generate-report.ps1" -RepoRoot $repoDir -ReportType cross-repo -Text 'structured jq report path' -Format json
    $reportText = $reportTextJson | ConvertFrom-Json
    if ([int]$reportText.total_entries -ne 1) { throw 'generate-report.ps1 text filtering should match instruction_text fields' }

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

    $missingEventsFile = Join-Path $repoDir 'missing-events.jsonl'
    try {
        & "$root/scripts/query-friction.ps1" -EventsFile $missingEventsFile -Format json | Out-Null
        throw 'query-friction.ps1 should reject missing events files'
    }
    catch {
        if ($_.Exception.Message -notmatch 'Events file not found:') {
            throw 'query-friction.ps1 should emit a focused diagnostic for missing events files'
        }
    }

    $emptyEventsFile = Join-Path $repoDir 'empty-events.jsonl'
    [System.IO.File]::WriteAllText($emptyEventsFile, '', [System.Text.UTF8Encoding]::new($false))
    $emptyQuery = & "$root/scripts/query-friction.ps1" -EventsFile $emptyEventsFile -Format json | ConvertFrom-Json
    if (@($emptyQuery).Count -ne 0) { throw 'query-friction.ps1 should return zero events for an empty events file' }
    $emptyIndex = & "$root/scripts/generate-report.ps1" -EventsFile $emptyEventsFile -ReportType index -Format json | ConvertFrom-Json
    if ([int]$emptyIndex.entries -ne 0) { throw 'generate-report.ps1 should report zero entries for an empty events file' }

    $dateEventsFile = Join-Path $repoDir 'date-events.jsonl'
    [System.IO.File]::WriteAllText($dateEventsFile, @'
{"title":"dated early","recorded_at":"2026-03-29T08:00:00Z","event_id":"evt-0001","derived_category":"skill/schema/continued","fingerprint":"fp-early","tags":["alpha"],"sources":[{"ref":"date-fixture"}],"repo_root":"/tmp/date","events_file":"/tmp/date/events.jsonl"}
{"title":"dated middle","recorded_at":"2026-03-30T09:30:00Z","event_id":"evt-0002","derived_category":"skill/schema/continued","fingerprint":"fp-middle","tags":["beta"],"sources":[{"ref":"date-fixture"}],"repo_root":"/tmp/date","events_file":"/tmp/date/events.jsonl"}
{"title":"dated late","recorded_at":"2026-03-31T10:45:00Z","event_id":"evt-0003","derived_category":"skill/schema/continued","fingerprint":"fp-late","tags":["gamma"],"sources":[{"ref":"date-fixture"}],"repo_root":"/tmp/date","events_file":"/tmp/date/events.jsonl"}
{"title":"undated row","event_id":"evt-0004","derived_category":"skill/schema/continued","fingerprint":"fp-undated","tags":["undated"],"sources":[{"ref":"date-fixture"}],"repo_root":"/tmp/date","events_file":"/tmp/date/events.jsonl"}
'@, [System.Text.UTF8Encoding]::new($false))
    $dateExact = & "$root/scripts/query-friction.ps1" -EventsFile $dateEventsFile -Date '2026-03-30' -Format json | ConvertFrom-Json
    if (@($dateExact).Count -ne 1 -or [string]$dateExact[0].title -ne 'dated middle') { throw 'query-friction.ps1 should isolate exact date matches' }
    $dateRange = & "$root/scripts/query-friction.ps1" -EventsFile $dateEventsFile -DateFrom '2026-03-30' -DateTo '2026-03-31' -Format json | ConvertFrom-Json
    if (@($dateRange).Count -ne 2) { throw 'query-friction.ps1 should return only the dated in-range rows' }
    if ((@($dateRange | ForEach-Object { [string]$_.title })) -contains 'undated row') { throw 'query-friction.ps1 should exclude undated rows from date ranges' }
    $afterDate = & "$root/scripts/query-friction.ps1" -EventsFile $dateEventsFile -After '2026-03-30T12:00:00Z' -Format json | ConvertFrom-Json
    if (@($afterDate).Count -ne 1 -or [string]$afterDate[0].title -ne 'dated late') { throw 'query-friction.ps1 should exclude undated and earlier rows from -After filters' }
    $dateReport = & "$root/scripts/generate-report.ps1" -EventsFile $dateEventsFile -ReportType cross-repo -DateFrom '2026-03-30' -Format json | ConvertFrom-Json
    if ([int]$dateReport.total_entries -ne 2) { throw 'generate-report.ps1 date filtering should match query semantics and exclude undated rows' }

    # --- Test 5b: render-table.ps1 basic coverage ---
    $tableOutput = (("Name`tAge`nAlice`t30`nBob`t25" | & "$root/scripts/render-table.ps1") -join "`n")
    if ($tableOutput -notmatch '┌') { throw 'render-table.ps1 should emit a top border for TSV input' }
    if ($tableOutput -notmatch 'Alice') { throw 'render-table.ps1 should render TSV data rows' }
    $headerOverrideOutput = (("old`n1" | & "$root/scripts/render-table.ps1" -Headers 'New') -join "`n")
    if ($headerOverrideOutput -notmatch 'New') { throw 'render-table.ps1 should honor -Headers overrides' }
    if ($headerOverrideOutput -match 'old') { throw 'render-table.ps1 should replace TSV header text when -Headers is provided' }
    $jsonlRow = '{"a":"foo","b":"bar","tags":["x","y"]}'
    $jsonlOutput = (($jsonlRow | & "$root/scripts/render-table.ps1" -Jsonl -Fields 'a,tags') -join "`n")
    if ($jsonlOutput -notmatch 'foo') { throw 'render-table.ps1 should render JSONL field selections' }
    if ($jsonlOutput -notmatch 'x,y') { throw 'render-table.ps1 should join scalar arrays in JSONL output' }
    $emptyTable = (('' | & "$root/scripts/render-table.ps1") -join "`n")
    if (-not [string]::IsNullOrWhiteSpace($emptyTable)) { throw 'render-table.ps1 should emit nothing for empty input' }
    $narrowTableInput = @"
ID`tTime`tTitle`tCategory`tTags`tSources
evt-0018`t04/02/2026 21:45:31`tPlaywright CLI arguments split badly on Windows cmd`tscript/other/blocked`tplaywright,windows,argument-parsing,jira,cli`tfile:C:/Users/E135328/.codex/skills/playwright/references/cli.md
"@
    $droppedTableOutput = (($narrowTableInput | & "$root/scripts/render-table.ps1" -MaxWidth 50) -join "`n")
    if ($droppedTableOutput -notmatch 'Columns omitted to fit width: Sources, Tags, Category') { throw 'render-table.ps1 should drop trailing columns by default on narrow widths' }
    if ($droppedTableOutput -notmatch 'Title') { throw 'render-table.ps1 should keep the Title column visible on narrow widths' }
    if ($droppedTableOutput -match 'Sources\s+│') { throw 'render-table.ps1 should omit the Sources header after dropping that column' }
    $shrinkTableOutput = (($narrowTableInput | & "$root/scripts/render-table.ps1" -MaxWidth 50 -FitMode shrink) -join "`n")
    if ($shrinkTableOutput -match 'Columns omitted to fit width:') { throw 'render-table.ps1 shrink mode should not drop columns' }
    if ($shrinkTableOutput -notmatch 'Sources') { throw 'render-table.ps1 shrink mode should keep all columns visible' }
    $minColumnsOutput = (("A`tB`tC`tD`nalpha`tbravo`tcharlie`tdelta" | & "$root/scripts/render-table.ps1" -MaxWidth 20 -MinColumns 2) -join "`n")
    if ($minColumnsOutput -notmatch 'Columns omitted to fit width: D, C') { throw 'render-table.ps1 should stop dropping columns at the configured minimum' }
    $emergencyShrinkOutput = (("A`tB`tC`nabcdefghijk`tlmnopqrstuv`twxyz" | & "$root/scripts/render-table.ps1" -MaxWidth 10 -MinColumns 2) -join "`n")
    if ($emergencyShrinkOutput -notmatch 'Columns omitted to fit width: C') { throw 'render-table.ps1 should still emit the omission note before emergency shrink' }

    # --- Test 5c: render-summary.ps1 parity coverage ---
    $summaryOutput = ((& "$root/scripts/render-summary.ps1" -EventsFile $eventsFile -After '2020-01-01T00:00:00Z' -NoFit) -join "`n")
    if ($summaryOutput -notmatch 'Friction Summary') { throw 'render-summary.ps1 should emit the summary header line' }
    if ($summaryOutput -notmatch '┌') { throw 'render-summary.ps1 should render a box-drawing table' }
    if ($summaryOutput -notmatch 'ID') { throw 'render-summary.ps1 should include the ID header' }
    if ($summaryOutput -notmatch 'Title') { throw 'render-summary.ps1 should include the Title header' }
    if ($summaryOutput -notmatch 'Sources') { throw 'render-summary.ps1 should include the Sources header' }
    if ($summaryOutput -notmatch 'evt-') { throw 'render-summary.ps1 should include event rows' }
    if ($summaryOutput -notmatch 'file:') { throw 'render-summary.ps1 should flatten source refs into the Sources column' }
    if ($summaryOutput -notmatch '-After') { throw 'render-summary.ps1 footer should preserve the lower-bound window' }
    if ($summaryOutput -notmatch '-Before') { throw 'render-summary.ps1 footer should compute an upper-bound re-query window' }
    if ($summaryOutput -notmatch 'query-friction.ps1') { throw 'render-summary.ps1 footer should reference query-friction.ps1' }
    $emptySummary = ((& "$root/scripts/render-summary.ps1" -EventsFile $eventsFile -After '2099-01-01T00:00:00Z' -NoFit) -join "`n")
    if ($emptySummary -match '┌') { throw 'render-summary.ps1 should emit no table for zero-event sessions' }
    $dateSummary = ((& "$root/scripts/render-summary.ps1" -EventsFile $eventsFile -DateFrom '2020-01-01' -NoFit) -join "`n")
    if ($dateSummary -notmatch '-DateFrom') { throw 'render-summary.ps1 footer should preserve the -DateFrom fallback path' }
    $narrowSummary = ((& "$root/scripts/render-summary.ps1" -EventsFile $eventsFile -After '2020-01-01T00:00:00Z' -MaxWidth 50) -join "`n")
    if ($narrowSummary -notmatch 'Columns omitted to fit width: Sources, Tags, Category') { throw 'render-summary.ps1 should omit trailing summary columns on narrow widths' }
    if ($narrowSummary -notmatch 'ID') { throw 'render-summary.ps1 should keep the ID column visible on narrow widths' }
    if ($narrowSummary -notmatch 'Time') { throw 'render-summary.ps1 should keep the Time column visible on narrow widths' }
    if ($narrowSummary -notmatch 'Title') { throw 'render-summary.ps1 should keep the Title column visible on narrow widths' }
    if ($narrowSummary -match 'Sources\s+│') { throw 'render-summary.ps1 should drop Sources before protected leading columns' }
    $mediumSummary = ((& "$root/scripts/render-summary.ps1" -EventsFile $eventsFile -After '2020-01-01T00:00:00Z' -MaxWidth 80) -join "`n")
    if ($mediumSummary -notmatch 'Columns omitted to fit width: Sources') { throw 'render-summary.ps1 should reduce columns progressively as width tightens' }

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

    $emptyScanDir = Join-Path ([System.IO.Path]::GetTempPath()) ("agent-friction-ps-empty-scan-{0}" -f [System.Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $emptyScanDir -Force
    try {
        & "$root/scripts/query-friction.ps1" -ScanDirs @($emptyScanDir) -Format json | Out-Null
        throw 'query-friction.ps1 should reject scan roots with no matching events files'
    }
    catch {
        if ($_.Exception.Message -notmatch 'No events.jsonl files found under:') {
            throw 'query-friction.ps1 should emit a focused diagnostic when scan roots contain no events files'
        }
    }
    finally {
        if (Test-Path $emptyScanDir) {
            Remove-Item -Recurse -Force $emptyScanDir
        }
    }

    $nestedScanRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("agent-friction-ps-nested-scan-{0}" -f [System.Guid]::NewGuid().ToString('N'))
    $nestedRepoDir = Join-Path $nestedScanRoot 'level-one/level-two/deep-repo'
    $null = New-Item -ItemType Directory -Path $nestedRepoDir -Force
    & git init -q $nestedRepoDir
    try {
        & "$root/scripts/report-friction.ps1" `
            -RepoRoot $nestedRepoDir `
            -Title 'Nested scan repo' `
            -SourceType 'documentation' `
            -SourceRef 'test' `
            -InstructionText 'Recursively discover deeply nested repos under scan roots.' `
            -ActionTaken 'Recorded an event in a repo nested two levels below the scan root so recursive discovery has to traverse beyond immediate children.' `
            -ExpectedOutcome 'The nested repo event stream would be discovered under the higher-level scan root.' `
            -ActualOutcome 'The nested repo event stream was written successfully.' `
            -Reading 'This fixture proves the PowerShell discovery path is recursive rather than flat-child only.' `
            -Hindsight 'Keep one deeply nested repo fixture in the smoke suite whenever recursive discovery changes.' | Out-Null
        $nestedCross = & "$root/scripts/generate-report.ps1" -ScanDirs @($nestedScanRoot) -ReportType cross-repo -Format json | ConvertFrom-Json
        if ([int]$nestedCross.repos_scanned -ne 1) { throw 'generate-report.ps1 should discover one deeply nested repo' }
        if ([string]$nestedCross.repos[0].repo_root -ne $nestedRepoDir) { throw 'generate-report.ps1 should preserve the deeply nested repo path' }
    }
    finally {
        if (Test-Path $nestedScanRoot) {
            Remove-Item -Recurse -Force $nestedScanRoot
        }
    }

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

    # --- Test 7b: Invalid stdin JSON preserves payload for replay ---
    $badStdinJson = '{"title":"bad stdin",}'
    try {
        $badStdinJson | & "$root/scripts/report-friction.ps1" -RepoRoot $repoDir -FromJson '-' | Out-Null
        throw 'report-friction.ps1 should reject invalid stdin JSON payloads'
    }
    catch {
        if ($_.Exception.Message -notmatch 'Invalid JSON in -FromJson stdin') {
            throw 'report-friction.ps1 should identify stdin parse failures clearly'
        }
        if ($_.Exception.Message -notmatch 'Saved invalid stdin payload to:') {
            throw 'report-friction.ps1 should report the saved invalid stdin payload path'
        }
        $savedPath = [regex]::Match($_.Exception.Message, 'Saved invalid stdin payload to: ([^\r\n]+)').Groups[1].Value
        if ([string]::IsNullOrWhiteSpace($savedPath)) { throw 'report-friction.ps1 should include a concrete saved stdin payload path' }
        if (-not (Test-Path -LiteralPath $savedPath)) { throw 'report-friction.ps1 should save the invalid stdin payload for replay' }
        if ($savedPath -notmatch '[\\/]\.local[\\/]tmp[\\/]friction-diagnostics[\\/]') { throw 'report-friction.ps1 should save invalid stdin payloads under repo-local .local/tmp/friction-diagnostics' }
        $savedPayload = [System.IO.File]::ReadAllText($savedPath)
        if ($savedPayload.TrimEnd("`r", "`n") -ne $badStdinJson) { throw 'saved invalid stdin payload should match the original input' }
    }

    # --- Test 7c: Repo-local scratch save failure preserves parse diagnostics ---
    $saveFailRepo = Join-Path ([System.IO.Path]::GetTempPath()) ("agent-friction-ps-savefail-{0}" -f [System.Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $saveFailRepo -Force
    & git init -q $saveFailRepo
    try {
        $null = New-Item -ItemType Directory -Path (Join-Path $saveFailRepo '.local') -Force
        [System.IO.File]::WriteAllText((Join-Path $saveFailRepo '.local/tmp'), 'block', [System.Text.UTF8Encoding]::new($false))
        try {
            $badStdinJson | & "$root/scripts/report-friction.ps1" -RepoRoot $saveFailRepo -FromJson '-' | Out-Null
            throw 'report-friction.ps1 should reject invalid stdin JSON when repo-local scratch is blocked'
        }
        catch {
            if ($_.Exception.Message -notmatch 'Invalid JSON in -FromJson stdin') {
                throw 'report-friction.ps1 should preserve the parse diagnostic when repo-local scratch is blocked'
            }
            if ($_.Exception.Message -notmatch 'Unable to save invalid stdin payload to repo-local scratch:') {
                throw 'report-friction.ps1 should report repo-local scratch save failures clearly'
            }
        }
    }
    finally {
        if (Test-Path $saveFailRepo) {
            Remove-Item -Recurse -Force $saveFailRepo
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
