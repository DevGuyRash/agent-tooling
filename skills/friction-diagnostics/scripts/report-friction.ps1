param(
    [string]$LogFile = $env:FRICTION_LOG_FILE,
    [string]$Title = "",
    [string]$InstructionSource = "",
    [string]$InstructionText = "",
    [string]$ActionTaken = "",
    [string]$ExpectedOutcome = "",
    [string]$ActualOutcome = "",
    [string]$Interpretation = "",
    [string]$ObservedSurface = "",
    [string]$Surface = "",
    [string]$Mode = "",
    [string]$RunEffect = "",
    [string]$GuidanceQuality = "",
    [string]$Impact = "",
    [string]$Confidence = "",
    [string]$EvidenceType = "",
    [string]$Command = "",
    [string]$ToolName = "",
    [string]$ExitCode = "",
    [string]$Stderr = "",
    [string]$StdoutExcerpt = "",
    [string]$OwnerHint = "",
    [string]$ComponentHint = "",
    [string]$IncidentStatus = "",
    [string]$WorkaroundUsed = "false",
    [string]$WorkaroundNote = "",
    [string]$RetriesLost = "0",
    [string]$MinutesLost = "0",
    [string]$FingerprintKey = "",
    [string]$Tags = "",
    [string]$TaskSummary = "",
    [string]$Agent = "orchestrator",
    [string]$SkillPathInit = "",
    [string]$RoleInit = "",
    [string]$BaseDirInit = "",
    [switch]$Quick,
    [switch]$Force,
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/report-friction.ps1 -LogFile `$env:FRICTION_LOG_FILE -Title "..." [fields]
  scripts/report-friction.ps1 -TaskSummary "..." -SkillPathInit "..." -Title "..." [fields]

Auto-init: omit -LogFile and supply -TaskSummary plus -SkillPathInit to bootstrap
a session via init-log.ps1 before reporting. Optional: -Agent, -RoleInit, -BaseDirInit.
Set `$env:FRICTION_TASK_ID to inherit a task ID from a parent agent.
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

# Auto-init: if no log file is set, bootstrap a session via init-log.ps1
if ([string]::IsNullOrWhiteSpace($LogFile)) {
    if ([string]::IsNullOrWhiteSpace($TaskSummary)) { throw "-LogFile or -TaskSummary is required" }
    if ([string]::IsNullOrWhiteSpace($SkillPathInit)) { throw "-SkillPathInit is required for auto-init" }
    $initArgs = @{
        TaskSummary = $TaskSummary
        Agent = $Agent
        SkillPath = $SkillPathInit
    }
    # Prefer inherited task ID from parent agent over slug-based discovery
    if (-not [string]::IsNullOrWhiteSpace($env:FRICTION_TASK_ID)) {
        $initArgs['TaskId'] = $env:FRICTION_TASK_ID
    }
    if (-not [string]::IsNullOrWhiteSpace($RoleInit)) {
        $initArgs['Role'] = $RoleInit
    }
    if (-not [string]::IsNullOrWhiteSpace($BaseDirInit)) {
        $initArgs['BaseDir'] = $BaseDirInit
    }
    $initOutput = & "$PSScriptRoot/init-log.ps1" @initArgs
    # Parse FRICTION_LOG_FILE from init output
    foreach ($line in $initOutput) {
        if ($line -match '^FRICTION_LOG_FILE=(.+)$') {
            $LogFile = $matches[1]
            break
        }
    }
}

if ([string]::IsNullOrWhiteSpace($LogFile)) { throw "-LogFile is required" }
if (-not (Test-Path $LogFile)) { throw "Log file not found: $LogFile" }

$taskDir = Split-Path -Parent (Split-Path -Parent $LogFile)
$sessionFile = Join-Path $taskDir 'SESSION.txt'
if (-not (Test-Path $sessionFile)) { throw "SESSION.txt not found for task dir: $taskDir" }

$eventsFile = Get-SessionValue $sessionFile 'FRICTION_EVENTS_FILE'
$captureMode = Get-SessionValue $sessionFile 'FRICTION_CAPTURE_MODE'
$privacyTier = Get-SessionValue $sessionFile 'FRICTION_PRIVACY_TIER'
if ([string]::IsNullOrWhiteSpace($eventsFile)) { throw "FRICTION_EVENTS_FILE missing from SESSION.txt" }
if ([string]::IsNullOrWhiteSpace($captureMode)) { $captureMode = 'explicit' }
if ([string]::IsNullOrWhiteSpace($privacyTier)) { $privacyTier = 'private' }

# Sanitize inputs
$titleOrig = $Title
$Title = Protect-Text $Title
$InstructionSource = Protect-Text $InstructionSource
$InstructionText = Protect-Text $InstructionText
$ActionTaken = Protect-Text $ActionTaken
$ExpectedOutcome = Protect-Text $ExpectedOutcome
$ActualOutcome = Protect-Text $ActualOutcome
$Interpretation = Protect-Text $Interpretation
$Command = Protect-Text $Command
$ToolName = Protect-Text $ToolName
$Stderr = Protect-Excerpt $Stderr 500
$StdoutExcerpt = Protect-Excerpt $StdoutExcerpt 500
$OwnerHint = Protect-Text $OwnerHint
$ComponentHint = Protect-Text $ComponentHint
$WorkaroundNote = Protect-Text $WorkaroundNote

$redactionApplied = ($Title -ne $titleOrig)

$auto = & "$PSScriptRoot/categorize.ps1" `
    -InstructionSource $InstructionSource `
    -InstructionText $InstructionText `
    -ActionTaken $ActionTaken `
    -ExpectedOutcome $ExpectedOutcome `
    -ActualOutcome $ActualOutcome `
    -Interpretation $Interpretation `
    -ToolName $ToolName `
    -Command $Command `
    -Stderr $Stderr `
    -StdoutExcerpt $StdoutExcerpt `
    -ObservedSurface $ObservedSurface `
    -Surface $Surface `
    -Mode $Mode `
    -RunEffect $RunEffect `
    -GuidanceQuality $GuidanceQuality `
    -Impact $Impact `
    -Confidence $Confidence `
    -EvidenceType $EvidenceType

$autoMap = @{}
foreach ($line in $auto) {
    if ($line -match '^(?<key>[^=]+)=(?<value>.*)$') {
        $autoMap[$matches.key] = $matches.value
    }
}

$Surface = $autoMap['surface']
$Mode = $autoMap['mode']
$RunEffect = $autoMap['run_effect']
$GuidanceQuality = $autoMap['guidance_quality']
$Confidence = $autoMap['confidence']
$EvidenceType = $autoMap['evidence_type']
$ObservedSurface = $autoMap['observed_surface']
$derivedCategory = $autoMap['derived_category']
$taxonomyVersion = $autoMap['taxonomy_version']

$mergedTags = $autoMap['tags']
if (-not [string]::IsNullOrWhiteSpace($Tags)) {
    foreach ($item in ($Tags -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
        $mergedTags = Add-CsvItem $mergedTags $item
    }
}
$Tags = $mergedTags

if ([string]::IsNullOrWhiteSpace($Title)) {
    $sourceTitle = Get-FirstLine $ActualOutcome
    if ([string]::IsNullOrWhiteSpace($sourceTitle)) { $sourceTitle = $Mode }
    $Title = Get-TruncatedLine -Text $sourceTitle -Limit 72
}

$workaroundUsedBool = ConvertTo-NormalizedBool $WorkaroundUsed
$retriesLostInt = ConvertTo-SafeInt $RetriesLost
$minutesLostInt = ConvertTo-SafeInt $MinutesLost
$exitCodeInt = ConvertTo-SafeInt $ExitCode
$quickCapture = [bool]$Quick
$forceCapture = [bool]$Force

if ([string]::IsNullOrWhiteSpace($IncidentStatus)) {
    if ($workaroundUsedBool) { $IncidentStatus = 'mitigated' } else { $IncidentStatus = 'open' }
}

$fingerprint = Get-EventFingerprint -RootSurface $Surface -Mode $Mode -InstructionSource $InstructionSource -ActualOutcome $ActualOutcome -ActionTaken $ActionTaken -Title $Title -CustomKey $FingerprintKey
$incidentId = "inc-$fingerprint"

$eventsContent = ''
if (Test-Path $eventsFile) { $eventsContent = [System.IO.File]::ReadAllText($eventsFile) }
$repeatCount = ([regex]::Matches($eventsContent, [regex]::Escape("`"fingerprint`":`"$fingerprint`""))).Count

$shouldSkip = $false
if ($captureMode -eq 'threshold' -and -not $forceCapture -and $repeatCount -eq 0 -and $RunEffect -ne 'blocked' -and $GuidanceQuality -ne 'misleading' -and -not $workaroundUsedBool -and $minutesLostInt -lt 5 -and $retriesLostInt -le 0) {
    $shouldSkip = $true
}
if ($shouldSkip) { exit 0 }

$entryNumber = 0
if (Test-Path $eventsFile) {
    $entryNumber = @([System.IO.File]::ReadAllLines($eventsFile) | Where-Object { $_ }).Count
}
$entryNumber++
$eventId = 'evt-{0:d4}' -f $entryNumber
$recorded = [System.DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
$agentDisplay = ''
$logContent = Get-Content -Path $LogFile -Raw
if ($logContent -match '\*\*Agent:\*\* ([^\r\n]+)') { $agentDisplay = $matches[1] }
$relativeLogFile = $LogFile.Substring($taskDir.Length).TrimStart('\', '/')
$titleLine = Get-TruncatedLine $Title 120

# Write event to events.jsonl
$eventJson = '{' +
    (ConvertTo-JsonString 'schema_version' $script:SCHEMA_VERSION) + ',' +
    (ConvertTo-JsonString 'taxonomy_version' $taxonomyVersion) + ',' +
    (ConvertTo-JsonString 'event_id' $eventId) + ',' +
    (ConvertTo-JsonString 'incident_id' $incidentId) + ',' +
    (ConvertTo-JsonString 'fingerprint' $fingerprint) + ',' +
    (ConvertTo-JsonString 'recorded_at' $recorded) + ',' +
    (ConvertTo-JsonString 'agent' $agentDisplay) + ',' +
    (ConvertTo-JsonString 'log_file' $relativeLogFile) + ',' +
    (ConvertTo-JsonBool 'quick_capture' $quickCapture) + ',' +
    (ConvertTo-JsonBool 'redaction_applied' $redactionApplied) + ',' +
    (ConvertTo-JsonString 'title_b64' (ConvertTo-Base64 $Title)) + ',' +
    (ConvertTo-JsonString 'title_line' $titleLine) + ',' +
    (ConvertTo-JsonString 'instruction_source_b64' (ConvertTo-Base64 $InstructionSource)) + ',' +
    (ConvertTo-JsonString 'instruction_text_b64' (ConvertTo-Base64 $InstructionText)) + ',' +
    (ConvertTo-JsonString 'action_taken_b64' (ConvertTo-Base64 $ActionTaken)) + ',' +
    (ConvertTo-JsonString 'expected_outcome_b64' (ConvertTo-Base64 $ExpectedOutcome)) + ',' +
    (ConvertTo-JsonString 'actual_outcome_b64' (ConvertTo-Base64 $ActualOutcome)) + ',' +
    (ConvertTo-JsonString 'interpretation_b64' (ConvertTo-Base64 $Interpretation)) + ',' +
    (ConvertTo-JsonString 'command_b64' (ConvertTo-Base64 $Command)) + ',' +
    (ConvertTo-JsonString 'tool_name_b64' (ConvertTo-Base64 $ToolName)) + ',' +
    (ConvertTo-JsonString 'stderr_b64' (ConvertTo-Base64 $Stderr)) + ',' +
    (ConvertTo-JsonString 'stdout_excerpt_b64' (ConvertTo-Base64 $StdoutExcerpt)) + ',' +
    (ConvertTo-JsonString 'owner_hint_b64' (ConvertTo-Base64 $OwnerHint)) + ',' +
    (ConvertTo-JsonString 'component_hint_b64' (ConvertTo-Base64 $ComponentHint)) + ',' +
    (ConvertTo-JsonString 'workaround_note_b64' (ConvertTo-Base64 $WorkaroundNote)) + ',' +
    (ConvertTo-JsonString 'observed_surface' $ObservedSurface) + ',' +
    (ConvertTo-JsonString 'surface' $Surface) + ',' +
    (ConvertTo-JsonString 'mode' $Mode) + ',' +
    (ConvertTo-JsonString 'run_effect' $RunEffect) + ',' +
    (ConvertTo-JsonString 'guidance_quality' $GuidanceQuality) + ',' +
    (ConvertTo-JsonString 'confidence' $Confidence) + ',' +
    (ConvertTo-JsonString 'evidence_type' $EvidenceType) + ',' +
    (ConvertTo-JsonString 'derived_category' $derivedCategory) + ',' +
    (ConvertTo-JsonString 'tags_csv' $Tags) + ',' +
    (ConvertTo-JsonString 'incident_status' $IncidentStatus) + ',' +
    (ConvertTo-JsonBool 'workaround_used' $workaroundUsedBool) + ',' +
    (ConvertTo-JsonNumber 'exit_code' $exitCodeInt) + ',' +
    (ConvertTo-JsonNumber 'retries_lost' $retriesLostInt) + ',' +
    (ConvertTo-JsonNumber 'minutes_lost' $minutesLostInt) + ',' +
    (ConvertTo-JsonString 'privacy_tier' $privacyTier) +
    '}'
[System.IO.File]::AppendAllText($eventsFile, "$eventJson`n", [System.Text.UTF8Encoding]::new($false))

# Append markdown entry
if ($captureMode -ne 'synthesis' -or $forceCapture) {
    $lines = @(
        ""
        "## Event $entryNumber`: $Title"
    )
    $lines += Write-MarkdownField -Label 'Incident' -Value $incidentId
    $lines += Write-MarkdownField -Label 'Recorded' -Value $recorded
    $lines += Write-MarkdownField -Label 'Derived category' -Value $derivedCategory
    $lines += Write-MarkdownField -Label 'Guidance quality' -Value $GuidanceQuality
    $lines += Write-MarkdownField -Label 'Observed surface' -Value $ObservedSurface
    $lines += Write-MarkdownField -Label 'Confidence' -Value $Confidence
    $lines += Write-MarkdownField -Label 'Evidence type' -Value $EvidenceType
    $lines += Write-MarkdownField -Label 'Status' -Value $IncidentStatus
    $lines += Write-MarkdownField -Label 'Tags' -Value $Tags
    $lines += Write-MarkdownField -Label 'Instruction source' -Value $InstructionSource
    $lines += Write-MarkdownField -Label 'Instruction text' -Value $InstructionText
    $lines += Write-MarkdownField -Label 'Action taken' -Value $ActionTaken
    $lines += Write-MarkdownField -Label 'Expected outcome' -Value $ExpectedOutcome
    $lines += Write-MarkdownField -Label 'Actual outcome' -Value $ActualOutcome
    $lines += Write-MarkdownField -Label 'Interpretation' -Value $Interpretation
    $lines += Write-MarkdownField -Label 'Command' -Value $Command
    $lines += Write-MarkdownField -Label 'Tool name' -Value $ToolName
    if ($exitCodeInt -ne 0) {
        $lines += Write-MarkdownField -Label 'Exit code' -Value ([string]$exitCodeInt)
    }
    $lines += Write-MarkdownField -Label 'stderr excerpt' -Value $Stderr
    $lines += Write-MarkdownField -Label 'stdout excerpt' -Value $StdoutExcerpt
    $lines += Write-MarkdownField -Label 'Owner hint' -Value $OwnerHint
    $lines += Write-MarkdownField -Label 'Component hint' -Value $ComponentHint
    $lines += Write-MarkdownField -Label 'Retries lost' -Value ([string]$retriesLostInt)
    $lines += Write-MarkdownField -Label 'Minutes lost' -Value ([string]$minutesLostInt)
    $lines += Write-MarkdownField -Label 'Workaround used' -Value ([string]$workaroundUsedBool).ToLower()
    $lines += Write-MarkdownField -Label 'Workaround note' -Value $WorkaroundNote
    $lines += Write-MarkdownField -Label 'Quick capture' -Value ([string]$quickCapture).ToLower()
    $lines += '---'

    Add-Content -Path $LogFile -Value $lines -Encoding UTF8
}

# Update incidents.json with current event/incident counts
$incidentsFile = Get-SessionValue $sessionFile 'FRICTION_INCIDENTS_FILE'
if (-not [string]::IsNullOrWhiteSpace($incidentsFile) -and (Test-Path $eventsFile)) {
    $evtLines = @([System.IO.File]::ReadAllLines($eventsFile) | Where-Object { $_ })
    $totalEvents = $evtLines.Count
    $incidentMap = @{}
    # Regex handles escaped quotes inside JSON string values (e.g. \"hello\").
    $jsonValPat = '([^"\\]*(?:\\.[^"\\]*)*)'
    foreach ($evtLine in $evtLines) {
        if ($evtLine -match """incident_id"":""$jsonValPat""") {
            $iid = $matches[1]
            if (-not $incidentMap.ContainsKey($iid)) {
                $iid_title = ''
                $iid_cat = ''
                if ($evtLine -match """title_line"":""$jsonValPat""") { $iid_title = $matches[1] }
                if ($evtLine -match """derived_category"":""$jsonValPat""") { $iid_cat = $matches[1] }
                $incidentMap[$iid] = @{ Title = $iid_title; Category = $iid_cat; Status = 'open'; Count = 0 }
            }
            $incidentMap[$iid].Count++
            if ($evtLine -match """incident_status"":""$jsonValPat""") {
                $incidentMap[$iid].Status = $matches[1]
            }
        }
    }
    $incArray = [System.Collections.Generic.List[string]]::new()
    foreach ($entry in $incidentMap.GetEnumerator()) {
        $incArray.Add(('{' +
            (ConvertTo-JsonString 'incident_id' $entry.Key) + ',' +
            (ConvertTo-JsonString 'title' $entry.Value.Title) + ',' +
            (ConvertTo-JsonString 'derived_category' $entry.Value.Category) + ',' +
            (ConvertTo-JsonString 'status' $entry.Value.Status) + ',' +
            (ConvertTo-JsonNumber 'event_count' $entry.Value.Count) +
            '}'))
    }
    $taskIdForIncidents = Split-Path -Leaf $taskDir
    $incUpdated = [System.DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    $incContent = '{' +
        (ConvertTo-JsonString 'schema_version' $script:SCHEMA_VERSION) + ',' +
        (ConvertTo-JsonString 'generated_at' $incUpdated) + ',' +
        (ConvertTo-JsonString 'task_id' $taskIdForIncidents) + ',' +
        (ConvertTo-JsonNumber 'event_count' $totalEvents) + ',' +
        (ConvertTo-JsonNumber 'incident_count' $incidentMap.Count) + ',' +
        '"incidents":[' + ($incArray -join ',') + ']}'
    [System.IO.File]::WriteAllText($incidentsFile, "$incContent`n", [System.Text.UTF8Encoding]::new($false))
}

& "$PSScriptRoot/build-index.ps1" -TaskDir $taskDir | Out-Null
