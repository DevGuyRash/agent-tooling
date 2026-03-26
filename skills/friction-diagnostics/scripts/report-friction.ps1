param(
    [string]$LogFile = $env:FRICTION_LOG_FILE,
    [string]$TaskDir = $env:FRICTION_TASK_DIR,
    [string]$FromJson = "",
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
    [Alias('Role')][string]$RoleInit = "",
    [string]$BaseDirInit = "",
    [switch]$Quick,
    [switch]$Force,
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/report-friction.ps1 -LogFile `$env:FRICTION_LOG_FILE -Title "..." [fields]
  scripts/report-friction.ps1 -TaskDir `$env:FRICTION_TASK_DIR -FromJson event.json -Agent orchestrator [fields]
  scripts/report-friction.ps1 -TaskSummary "..." -SkillPathInit "..." -Title "..." [fields]

Auto-init: omit -LogFile and -TaskDir, then supply -TaskSummary plus -SkillPathInit to bootstrap
a session via init-log.ps1 before reporting. Optional: -Agent, -RoleInit, -BaseDirInit.
Set `$env:FRICTION_TASK_ID to inherit a task ID from a parent agent.
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

function Load-JsonField {
    param(
        [string]$Key,
        [string]$Current,
        [string]$Path,
        [string]$Default
    )
    if ($Current -ne $Default) {
        return $Current
    }
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $Current
    }

    if ($Path -eq '-') {
        if (-not $script:FromJsonObjectLoaded) {
            $script:FromJsonObject = [Console]::In.ReadToEnd() | ConvertFrom-Json
            $script:FromJsonObjectLoaded = $true
        }
    } else {
        if (-not (Test-Path $Path)) {
            throw "JSON input not found: $Path"
        }
        if (-not $script:FromJsonCache.ContainsKey($Path)) {
            $script:FromJsonCache[$Path] = (Get-Content -Path $Path -Raw | ConvertFrom-Json)
        }
        $script:FromJsonObject = $script:FromJsonCache[$Path]
    }

    $property = $script:FromJsonObject.PSObject.Properties[$Key]
    if ($null -eq $property) {
        return $Current
    }
    $value = $property.Value
    if ($null -eq $value) {
        return $Current
    }
    if ($value -is [bool]) {
        if ($value) {
            return 'true'
        }
        return 'false'
    }
    return [string]$value
}

function Materialize-AgentArtifacts {
    param(
        [string]$TargetTaskDir,
        [string]$TargetAgent,
        [string]$TargetRole
    )

    $targetSessionFile = Join-Path $TargetTaskDir 'SESSION.txt'
    if (-not (Test-Path $targetSessionFile)) { throw "SESSION.txt not found for task dir: $TargetTaskDir" }

    $taskSummaryFile = Get-SessionValue $targetSessionFile 'FRICTION_TASK_SUMMARY_FILE'
    $taskJsonFile = Get-SessionValue $targetSessionFile 'FRICTION_TASK_JSON'
    $targetEventsFile = Get-SessionValue $targetSessionFile 'FRICTION_EVENTS_FILE'
    $targetIncidentsFile = Get-SessionValue $targetSessionFile 'FRICTION_INCIDENTS_FILE'
    $indexFile = Get-SessionValue $targetSessionFile 'FRICTION_INDEX_FILE'
    $storageMode = Get-SessionValue $targetSessionFile 'FRICTION_STORAGE_MODE'
    $targetCaptureMode = Get-SessionValue $targetSessionFile 'FRICTION_CAPTURE_MODE'
    $targetPrivacyTier = Get-SessionValue $targetSessionFile 'FRICTION_PRIVACY_TIER'
    $exportDir = Get-SessionValue $targetSessionFile 'FRICTION_EXPORT_DIR'
    $skillPath = Get-SessionValue $targetSessionFile 'FRICTION_SKILL_PATH'
    $contextPath = Get-SessionValue $targetSessionFile 'FRICTION_CONTEXT_PATH'
    $targetExportsDir = Join-Path $TargetTaskDir 'exports'

    New-Item -ItemType Directory -Force -Path $targetExportsDir | Out-Null
    if (-not (Test-Path $targetEventsFile)) {
        [System.IO.File]::WriteAllText($targetEventsFile, '', [System.Text.UTF8Encoding]::new($false))
    }
    if (-not (Test-Path $targetIncidentsFile)) {
        $generatedAt = [System.DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
        $incidentsContent = '{' +
            (ConvertTo-JsonString 'schema_version' $script:SCHEMA_VERSION) + ',' +
            (ConvertTo-JsonString 'generated_at' $generatedAt) + ',' +
            (ConvertTo-JsonString 'task_id' (Split-Path -Leaf $TargetTaskDir)) + ',' +
            (ConvertTo-JsonNumber 'event_count' 0) + ',' +
            (ConvertTo-JsonNumber 'incident_count' 0) + ',' +
            '"incidents":[]}'
        [System.IO.File]::WriteAllText($targetIncidentsFile, "$incidentsContent`n", [System.Text.UTF8Encoding]::new($false))
    }

    if (Test-Path $taskJsonFile) {
        $taskJson = Get-Content -Path $taskJsonFile -Raw | ConvertFrom-Json
        $taskJson | Add-Member -NotePropertyName artifacts_materialized -NotePropertyValue $true -Force
        [System.IO.File]::WriteAllText($taskJsonFile, (($taskJson | ConvertTo-Json -Depth 8 -Compress) + "`n"), [System.Text.UTF8Encoding]::new($false))
    }

    $agentSlug = Get-Slug $TargetAgent
    $agentDisplay = $TargetAgent
    if (-not [string]::IsNullOrWhiteSpace($TargetRole)) {
        $agentSlug = "$agentSlug-$(Get-Slug $TargetRole)"
        $agentDisplay = "$TargetAgent ($TargetRole)"
    }
    $agentSlug = Get-BoundedSlug -Text $agentSlug -Limit 227

    $existingLog = Get-ChildItem -Path $TargetTaskDir -Recurse -Filter '*.md' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne 'INDEX.md' } |
        Sort-Object FullName |
        Where-Object {
            $content = Get-Content -Path $_.FullName -Raw
            $content -match [regex]::Escape("**Agent:** $agentDisplay")
        } |
        Select-Object -Last 1
    if ($existingLog) {
        return $existingLog.FullName
    }

    $dateDir = [System.DateTimeOffset]::UtcNow.ToString('yyyy-MM-dd')
    $timePart = [System.DateTimeOffset]::UtcNow.ToString('HH-mm-ss')
    $stamp = [System.DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    $datedDir = Join-Path $TargetTaskDir $dateDir
    New-Item -ItemType Directory -Force -Path $datedDir | Out-Null

    $newLog = Join-Path $datedDir "${timePart}_${agentSlug}.md"
    $suffix = 1
    while (Test-Path $newLog) {
        $newLog = Join-Path $datedDir ("{0}_{1}_{2:d2}.md" -f $timePart, $agentSlug, $suffix)
        $suffix++
    }
    $descriptorFile = [System.IO.Path]::ChangeExtension($newLog, 'descriptor.json')
    $taskSummaryText = if (Test-Path $taskSummaryFile) { [System.IO.File]::ReadAllText($taskSummaryFile) } else { '' }

    $headerLines = @(
        "# Friction Evidence Log: $(Split-Path -Leaf $TargetTaskDir)"
    )
    $headerLines += Write-MarkdownField -Label 'Created' -Value $stamp
    $headerLines += Write-MarkdownField -Label 'Agent' -Value $agentDisplay
    $headerLines += Write-MarkdownField -Label 'Task ID' -Value (Split-Path -Leaf $TargetTaskDir)
    $headerLines += Write-MarkdownField -Label 'Task summary' -Value $taskSummaryText
    $headerLines += Write-MarkdownField -Label 'Storage mode' -Value $storageMode
    $headerLines += Write-MarkdownField -Label 'Capture mode' -Value $targetCaptureMode
    $headerLines += Write-MarkdownField -Label 'Privacy tier' -Value $targetPrivacyTier
    $headerLines += Write-MarkdownField -Label 'Skill path' -Value $skillPath
    if (-not [string]::IsNullOrWhiteSpace($contextPath)) {
        $headerLines += Write-MarkdownField -Label 'Context path' -Value $contextPath
    }
    if (-not [string]::IsNullOrWhiteSpace($exportDir)) {
        $headerLines += Write-MarkdownField -Label 'Export dir' -Value $exportDir
    }
    $headerLines += Write-MarkdownField -Label 'Platform' -Value (Get-PlatformName)
    $headerLines += Write-MarkdownField -Label 'Schema version' -Value $script:SCHEMA_VERSION
    $headerLines += '---'
    Set-Content -Path $newLog -Value $headerLines -Encoding UTF8

    $descriptorContent = '{' +
        (ConvertTo-JsonString 'schema_version' $script:SCHEMA_VERSION) + ',' +
        (ConvertTo-JsonString 'task_id' (Split-Path -Leaf $TargetTaskDir)) + ',' +
        (ConvertTo-JsonString 'task_dir' $TargetTaskDir) + ',' +
        (ConvertTo-JsonString 'log_file' $newLog) + ',' +
        (ConvertTo-JsonString 'task_json' $taskJsonFile) + ',' +
        (ConvertTo-JsonString 'events_file' $targetEventsFile) + ',' +
        (ConvertTo-JsonString 'incidents_file' $targetIncidentsFile) + ',' +
        (ConvertTo-JsonString 'index_file' $indexFile) + ',' +
        (ConvertTo-JsonString 'task_summary_file' $taskSummaryFile) + ',' +
        (ConvertTo-JsonString 'storage_mode' $storageMode) + ',' +
        (ConvertTo-JsonString 'capture_mode' $targetCaptureMode) + ',' +
        (ConvertTo-JsonString 'privacy_tier' $targetPrivacyTier) + ',' +
        (ConvertTo-JsonString 'export_dir' $exportDir) +
        '}'
    [System.IO.File]::WriteAllText($descriptorFile, "$descriptorContent`n", [System.Text.UTF8Encoding]::new($false))

    return $newLog
}

$script:FromJsonCache = @{}
$script:FromJsonObjectLoaded = $false
$script:FromJsonObject = $null

if (-not [string]::IsNullOrWhiteSpace($FromJson)) {
    $Title = Load-JsonField 'title' $Title $FromJson ''
    $InstructionSource = Load-JsonField 'instruction_source' $InstructionSource $FromJson ''
    $InstructionText = Load-JsonField 'instruction_text' $InstructionText $FromJson ''
    $ActionTaken = Load-JsonField 'action_taken' $ActionTaken $FromJson ''
    $ExpectedOutcome = Load-JsonField 'expected_outcome' $ExpectedOutcome $FromJson ''
    $ActualOutcome = Load-JsonField 'actual_outcome' $ActualOutcome $FromJson ''
    $Interpretation = Load-JsonField 'interpretation' $Interpretation $FromJson ''
    $ObservedSurface = Load-JsonField 'observed_surface' $ObservedSurface $FromJson ''
    $Surface = Load-JsonField 'surface' $Surface $FromJson ''
    $Mode = Load-JsonField 'mode' $Mode $FromJson ''
    $RunEffect = Load-JsonField 'run_effect' $RunEffect $FromJson ''
    $GuidanceQuality = Load-JsonField 'guidance_quality' $GuidanceQuality $FromJson ''
    $Impact = Load-JsonField 'impact' $Impact $FromJson ''
    $Confidence = Load-JsonField 'confidence' $Confidence $FromJson ''
    $EvidenceType = Load-JsonField 'evidence_type' $EvidenceType $FromJson ''
    $Command = Load-JsonField 'command' $Command $FromJson ''
    $ToolName = Load-JsonField 'tool_name' $ToolName $FromJson ''
    $ExitCode = Load-JsonField 'exit_code' $ExitCode $FromJson ''
    $Stderr = Load-JsonField 'stderr' $Stderr $FromJson ''
    $StdoutExcerpt = Load-JsonField 'stdout_excerpt' $StdoutExcerpt $FromJson ''
    $OwnerHint = Load-JsonField 'owner_hint' $OwnerHint $FromJson ''
    $ComponentHint = Load-JsonField 'component_hint' $ComponentHint $FromJson ''
    $IncidentStatus = Load-JsonField 'incident_status' $IncidentStatus $FromJson ''
    $WorkaroundUsed = Load-JsonField 'workaround_used' $WorkaroundUsed $FromJson 'false'
    $WorkaroundNote = Load-JsonField 'workaround_note' $WorkaroundNote $FromJson ''
    $RetriesLost = Load-JsonField 'retries_lost' $RetriesLost $FromJson '0'
    $MinutesLost = Load-JsonField 'minutes_lost' $MinutesLost $FromJson '0'
    $FingerprintKey = Load-JsonField 'fingerprint_key' $FingerprintKey $FromJson ''
    $Tags = Load-JsonField 'tags' $Tags $FromJson ''
    $Quick = [bool](ConvertTo-NormalizedBool (Load-JsonField 'quick' ([string]$Quick).ToLowerInvariant() $FromJson 'false'))
    $Force = [bool](ConvertTo-NormalizedBool (Load-JsonField 'force' ([string]$Force).ToLowerInvariant() $FromJson 'false'))
}

if ([string]::IsNullOrWhiteSpace($TaskDir) -and -not [string]::IsNullOrWhiteSpace($LogFile)) {
    if (-not (Test-Path $LogFile)) { throw "Log file not found: $LogFile" }
    $TaskDir = Split-Path -Parent (Split-Path -Parent $LogFile)
}

if ([string]::IsNullOrWhiteSpace($TaskDir)) {
    if ([string]::IsNullOrWhiteSpace($TaskSummary)) { throw "-LogFile, -TaskDir, or -TaskSummary is required" }
    if ([string]::IsNullOrWhiteSpace($SkillPathInit)) { throw "-SkillPathInit is required for auto-init" }
    $initArgs = @{
        TaskSummary = $TaskSummary
        Agent = $Agent
        SkillPath = $SkillPathInit
    }
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
    foreach ($line in $initOutput) {
        if ($line -match '^FRICTION_TASK_DIR=(.*)$') {
            $TaskDir = $matches[1]
            break
        }
    }
}

if ([string]::IsNullOrWhiteSpace($TaskDir)) { throw "-TaskDir is required" }
if (-not (Test-Path $TaskDir)) { throw "Task directory not found: $TaskDir" }

$taskDir = $TaskDir
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

if ([string]::IsNullOrWhiteSpace($LogFile) -or -not (Test-Path $LogFile)) {
    $LogFile = Materialize-AgentArtifacts -TargetTaskDir $taskDir -TargetAgent $Agent -TargetRole $RoleInit
}

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
    (ConvertTo-JsonString 'title' $Title) + ',' +
    (ConvertTo-JsonString 'title_line' $titleLine) + ',' +
    (ConvertTo-JsonString 'instruction_source' $InstructionSource) + ',' +
    (ConvertTo-JsonString 'instruction_text' $InstructionText) + ',' +
    (ConvertTo-JsonString 'action_taken' $ActionTaken) + ',' +
    (ConvertTo-JsonString 'expected_outcome' $ExpectedOutcome) + ',' +
    (ConvertTo-JsonString 'actual_outcome' $ActualOutcome) + ',' +
    (ConvertTo-JsonString 'interpretation' $Interpretation) + ',' +
    (ConvertTo-JsonString 'command' $Command) + ',' +
    (ConvertTo-JsonString 'tool_name' $ToolName) + ',' +
    (ConvertTo-JsonString 'stderr' $Stderr) + ',' +
    (ConvertTo-JsonString 'stdout_excerpt' $StdoutExcerpt) + ',' +
    (ConvertTo-JsonString 'owner_hint' $OwnerHint) + ',' +
    (ConvertTo-JsonString 'component_hint' $ComponentHint) + ',' +
    (ConvertTo-JsonString 'workaround_note' $WorkaroundNote) + ',' +
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
