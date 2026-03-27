param(
    [string]$EventsFile = $env:FRICTION_EVENTS_FILE,
    [string]$IndexFile = $env:FRICTION_INDEX_FILE,
    [string]$RepoRoot = $env:FRICTION_REPO_ROOT,
    [string]$FromJson = '',
    [string]$Title = '',
    [string]$InstructionSource = '',
    [string]$InstructionText = '',
    [string]$ActionTaken = '',
    [string]$ExpectedOutcome = '',
    [string]$ActualOutcome = '',
    [string]$Interpretation = '',
    [string]$ObservedSurface = '',
    [string]$Surface = '',
    [string]$Mode = '',
    [string]$RunEffect = '',
    [string]$GuidanceQuality = '',
    [string]$Impact = '',
    [string]$Confidence = '',
    [string]$EvidenceType = '',
    [string]$Command = '',
    [string]$ToolName = '',
    [string]$ExitCode = '',
    [string]$Stderr = '',
    [string]$StdoutExcerpt = '',
    [string]$OwnerHint = '',
    [string]$ComponentHint = '',
    [string]$PrivacyTier = 'private',
    [string]$IncidentStatus = '',
    [string]$WorkaroundUsed = 'false',
    [string]$WorkaroundNote = '',
    [string]$RetriesLost = '0',
    [string]$MinutesLost = '0',
    [string]$FingerprintKey = '',
    [string]$Tags = '',
    [Alias('Agent')][string]$AgentName = $(if ($env:FRICTION_AGENT_NAME) { $env:FRICTION_AGENT_NAME } else { '' }),
    [string]$AgentKind = $(if ($env:FRICTION_AGENT_KIND) { $env:FRICTION_AGENT_KIND } else { '' }),
    [string]$Role = $(if ($env:FRICTION_ROLE) { $env:FRICTION_ROLE } else { '' }),
    [string]$AnchorKind = '',
    [string]$AnchorPath = '',
    [string]$AnchorLine = '',
    [string]$AnchorEndLine = '',
    [string]$AnchorSymbol = '',
    [string]$AnchorSection = '',
    [string]$AnchorUrl = '',
    [string]$AnchorSelector = '',
    [string]$AnchorLabel = '',
    [switch]$Quick,
    [switch]$Force,
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/report-friction.ps1 -Title "..." [fields]
  scripts/report-friction.ps1 -RepoRoot <repo> -FromJson event.json
  scripts/report-friction.ps1 -EventsFile /path/to/events.jsonl -FromJson event.json

Normal path:
  Appends one sanitized event to the repo-scoped rolling events file under the repo context
  directory, then rebuilds INDEX.md automatically.

Selection:
  -RepoRoot PATH      Resolve the canonical repo-scoped events.jsonl and INDEX.md for PATH.
  -EventsFile PATH    Override the canonical storage file directly.
  -IndexFile PATH     Override the generated INDEX.md path.
  -FromJson PATH|-    Load event fields from a JSON object on disk or stdin.
                      Prefer stdin for shell-sensitive or multiline payloads.

Provenance:
  -AgentName VALUE    Optional descriptive agent name. Alias: -Agent
  -AgentKind VALUE    Optional agent kind such as orchestrator or subagent.
  -Role VALUE         Optional descriptive role value.
                      If omitted, provenance is recorded as unspecified.
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

$paths = Resolve-FrictionPaths -RepoRoot $RepoRoot -EventsFile $EventsFile -IndexFile $IndexFile
$EventsFile = $paths.EventsFile
$IndexFile = $paths.IndexFile
$RepoRoot = $paths.RepoRoot
$fromJsonAnchors = @()

$fromJsonPayload = $null
if (-not [string]::IsNullOrWhiteSpace($FromJson)) {
    $fromJsonPayload = Import-EventJsonObject $FromJson
    $diagnosticPath = Get-JsonDiagnosticLabel $FromJson

    $Title = Get-JsonFieldValue $fromJsonPayload 'title' $Title ''
    $InstructionSource = Get-JsonFieldValue $fromJsonPayload 'instruction_source' $InstructionSource ''
    $InstructionText = Get-JsonFieldValue $fromJsonPayload 'instruction_text' $InstructionText ''
    $ActionTaken = Get-JsonFieldValue $fromJsonPayload 'action_taken' $ActionTaken ''
    $ExpectedOutcome = Get-JsonFieldValue $fromJsonPayload 'expected_outcome' $ExpectedOutcome ''
    $ActualOutcome = Get-JsonFieldValue $fromJsonPayload 'actual_outcome' $ActualOutcome ''
    $Interpretation = Get-JsonFieldValue $fromJsonPayload 'interpretation' $Interpretation ''
    $ObservedSurface = Get-JsonFieldValue $fromJsonPayload 'observed_surface' $ObservedSurface ''
    $Surface = Get-JsonFieldValue $fromJsonPayload 'surface' $Surface ''
    $Mode = Get-JsonFieldValue $fromJsonPayload 'mode' $Mode ''
    $RunEffect = Get-JsonFieldValue $fromJsonPayload 'run_effect' $RunEffect ''
    $GuidanceQuality = Get-JsonFieldValue $fromJsonPayload 'guidance_quality' $GuidanceQuality ''
    $Impact = Get-JsonFieldValue $fromJsonPayload 'impact' $Impact ''
    $Confidence = Get-JsonFieldValue $fromJsonPayload 'confidence' $Confidence ''
    $EvidenceType = Get-JsonFieldValue $fromJsonPayload 'evidence_type' $EvidenceType ''
    $Command = Get-JsonFieldValue $fromJsonPayload 'command' $Command ''
    $ToolName = Get-JsonFieldValue $fromJsonPayload 'tool_name' $ToolName ''
    $ExitCode = Get-JsonFieldValue $fromJsonPayload 'exit_code' $ExitCode ''
    $Stderr = Get-JsonFieldValue $fromJsonPayload 'stderr' $Stderr ''
    $StdoutExcerpt = Get-JsonFieldValue $fromJsonPayload 'stdout_excerpt' $StdoutExcerpt ''
    $OwnerHint = Get-JsonFieldValue $fromJsonPayload 'owner_hint' $OwnerHint ''
    $ComponentHint = Get-JsonFieldValue $fromJsonPayload 'component_hint' $ComponentHint ''
    $PrivacyTier = Get-JsonFieldValue $fromJsonPayload 'privacy_tier' $PrivacyTier 'private'
    $IncidentStatus = Get-JsonFieldValue $fromJsonPayload 'incident_status' $IncidentStatus ''
    $WorkaroundUsed = Get-JsonFieldValue $fromJsonPayload 'workaround_used' $WorkaroundUsed 'false'
    $WorkaroundNote = Get-JsonFieldValue $fromJsonPayload 'workaround_note' $WorkaroundNote ''
    $RetriesLost = Get-JsonFieldValue $fromJsonPayload 'retries_lost' $RetriesLost '0'
    $MinutesLost = Get-JsonFieldValue $fromJsonPayload 'minutes_lost' $MinutesLost '0'
    $FingerprintKey = Get-JsonFieldValue $fromJsonPayload 'fingerprint_key' $FingerprintKey ''
    $Tags = Get-JsonFieldValue $fromJsonPayload 'tags' $Tags ''
    $AgentName = Get-JsonFieldValue $fromJsonPayload 'agent_name' $AgentName ''
    $AgentKind = Get-JsonFieldValue $fromJsonPayload 'agent_kind' $AgentKind ''
    $Role = Get-JsonFieldValue $fromJsonPayload 'role' $Role ''
    $Quick = [bool](ConvertTo-NormalizedBool (Get-JsonFieldValue $fromJsonPayload 'quick' ([string]$Quick).ToLowerInvariant() 'false'))
    $Force = [bool](ConvertTo-NormalizedBool (Get-JsonFieldValue $fromJsonPayload 'force' ([string]$Force).ToLowerInvariant() 'false'))

    $anchorsProperty = $fromJsonPayload.PSObject.Properties['anchors']
    if ($null -ne $anchorsProperty) {
        if ($null -eq $anchorsProperty.Value) {
            $fromJsonAnchors = @()
        }
        else {
            $candidateAnchors = @($anchorsProperty.Value)
            foreach ($candidateAnchor in $candidateAnchors) {
                if ($candidateAnchor -isnot [pscustomobject] -and $candidateAnchor -isnot [hashtable]) {
                    throw "-FromJson field 'anchors' must contain only objects"
                }
                $anchorMap = [ordered]@{}
                foreach ($anchorKey in @('kind', 'path', 'line', 'end_line', 'symbol', 'section', 'url', 'selector', 'label')) {
                    $anchorProperty = $candidateAnchor.PSObject.Properties[$anchorKey]
                    if ($null -eq $anchorProperty -or $null -eq $anchorProperty.Value) {
                        continue
                    }
                    if ($anchorProperty.Value -isnot [string] -and $anchorProperty.Value -isnot [System.ValueType]) {
                        throw "-FromJson anchor field '$anchorKey' must be a scalar value"
                    }
                    $anchorMap[$anchorKey] = [string]$anchorProperty.Value
                }
                $fromJsonAnchors += [pscustomobject]$anchorMap
            }
        }
    }

    $payloadEventsFile = Get-JsonFieldValue $fromJsonPayload 'events_file' '' ''
    if (-not [string]::IsNullOrWhiteSpace($payloadEventsFile)) {
        $resolvedPayloadEventsFile = Test-EventFileField -Path $payloadEventsFile -FieldName 'events_file' -DiagnosticPath $diagnosticPath
        if ($resolvedPayloadEventsFile -ne $EventsFile) {
            throw "events_file from -FromJson $diagnosticPath must match the selected events file"
        }
    }

    foreach ($property in $fromJsonPayload.PSObject.Properties.Name) {
        if ($property -in $script:KNOWN_EVENT_KEYS) { continue }
        if ($property -eq 'events_file') { continue }
        throw "Unsupported key in -FromJson $diagnosticPath: $property"
    }
}

$titleOrig = $Title
$instructionSourceOrig = $InstructionSource
$instructionTextOrig = $InstructionText
$actionTakenOrig = $ActionTaken
$expectedOutcomeOrig = $ExpectedOutcome
$actualOutcomeOrig = $ActualOutcome
$interpretationOrig = $Interpretation
$commandOrig = $Command
$toolNameOrig = $ToolName
$stderrOrig = $Stderr
$stdoutExcerptOrig = $StdoutExcerpt
$ownerHintOrig = $OwnerHint
$componentHintOrig = $ComponentHint
$privacyTierOrig = $PrivacyTier
$workaroundNoteOrig = $WorkaroundNote
$agentNameOrig = $AgentName
$agentKindOrig = $AgentKind
$roleOrig = $Role

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
$PrivacyTier = Protect-Text $PrivacyTier
$WorkaroundNote = Protect-Text $WorkaroundNote
$AgentName = Protect-Text $AgentName
$AgentKind = Protect-Text $AgentKind
$Role = Protect-Text $Role
$AnchorKind = Protect-Text $AnchorKind
$AnchorPath = Protect-Text $AnchorPath
$AnchorSymbol = Protect-Text $AnchorSymbol
$AnchorSection = Protect-Text $AnchorSection
$AnchorUrl = Protect-Text $AnchorUrl
$AnchorSelector = Protect-Text $AnchorSelector
$AnchorLabel = Protect-Text $AnchorLabel
$RepoRoot = Protect-Text $RepoRoot

$redactionApplied = (
    $Title -ne $titleOrig -or
    $InstructionSource -ne $instructionSourceOrig -or
    $InstructionText -ne $instructionTextOrig -or
    $ActionTaken -ne $actionTakenOrig -or
    $ExpectedOutcome -ne $expectedOutcomeOrig -or
    $ActualOutcome -ne $actualOutcomeOrig -or
    $Interpretation -ne $interpretationOrig -or
    $Command -ne $commandOrig -or
    $ToolName -ne $toolNameOrig -or
    $Stderr -ne (Get-TruncatedText (Protect-Text $stderrOrig) 500) -or
    $StdoutExcerpt -ne (Get-TruncatedText (Protect-Text $stdoutExcerptOrig) 500) -or
    $OwnerHint -ne $ownerHintOrig -or
    $ComponentHint -ne $componentHintOrig -or
    $PrivacyTier -ne $privacyTierOrig -or
    $WorkaroundNote -ne $workaroundNoteOrig -or
    $AgentName -ne $agentNameOrig -or
    $AgentKind -ne $agentKindOrig -or
    $Role -ne $roleOrig
)

foreach ($field in @(
    @{ Label = 'instruction_source'; Value = $InstructionSource },
    @{ Label = 'instruction_text'; Value = $InstructionText },
    @{ Label = 'action_taken'; Value = $ActionTaken },
    @{ Label = 'expected_outcome'; Value = $ExpectedOutcome },
    @{ Label = 'actual_outcome'; Value = $ActualOutcome },
    @{ Label = 'interpretation'; Value = $Interpretation }
)) {
    if ([string]::IsNullOrWhiteSpace([string]$field.Value)) {
        throw "Missing required field: $($field.Label)"
    }
}

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
$PrivacyTier = if ([string]::IsNullOrWhiteSpace($PrivacyTier)) { 'private' } else { $PrivacyTier }

if ([string]::IsNullOrWhiteSpace($IncidentStatus)) {
    if ($workaroundUsedBool) { $IncidentStatus = 'mitigated' } else { $IncidentStatus = 'open' }
}
if ($IncidentStatus -notin @('open', 'mitigated', 'resolved', 'stale')) {
    throw "Unsupported incident status: $IncidentStatus"
}

if ([string]::IsNullOrWhiteSpace($OwnerHint)) {
    $OwnerHint = Get-DefaultOwnerForSurface $Surface
}

$fingerprint = Get-EventFingerprint -RootSurface $Surface -Mode $Mode -InstructionSource $InstructionSource -ActualOutcome $ActualOutcome -ActionTaken $ActionTaken -Title $Title -CustomKey $FingerprintKey
$incidentId = "inc-$fingerprint"
$recorded = [System.DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
$titleLine = Get-TruncatedLine $Title 120
$provenanceSource = if (-not [string]::IsNullOrWhiteSpace($AgentName) -or -not [string]::IsNullOrWhiteSpace($AgentKind) -or -not [string]::IsNullOrWhiteSpace($Role)) { 'explicit' } else { 'unspecified' }
$repoRelativeEventsFile = ''
if (-not [string]::IsNullOrWhiteSpace($RepoRoot) -and $EventsFile.StartsWith($RepoRoot)) {
    $repoRelativeEventsFile = $EventsFile.Substring($RepoRoot.Length).TrimStart('\', '/')
}
if ([string]::IsNullOrWhiteSpace($repoRelativeEventsFile)) {
    $repoRelativeEventsFile = $EventsFile
}

$anchors = @()
if ($fromJsonAnchors.Count -gt 0) {
    foreach ($anchor in $fromJsonAnchors) {
        $sanitizedAnchor = [ordered]@{}
        foreach ($anchorKey in @('kind', 'path', 'line', 'end_line', 'symbol', 'section', 'url', 'selector', 'label')) {
            $anchorValue = $anchor.PSObject.Properties[$anchorKey]
            if ($null -eq $anchorValue -or $null -eq $anchorValue.Value) {
                continue
            }
            $candidateValue = [string]$anchorValue.Value
            if ($anchorKey -in @('line', 'end_line')) {
                $numberValue = ConvertTo-SafeInt $candidateValue
                if ($numberValue -gt 0) {
                    $sanitizedAnchor[$anchorKey] = $numberValue
                }
            }
            else {
                $textValue = Protect-Text $candidateValue
                if (-not [string]::IsNullOrWhiteSpace($textValue)) {
                    $sanitizedAnchor[$anchorKey] = $textValue
                }
            }
        }
        if ($sanitizedAnchor.Count -gt 0) {
            $anchors += [pscustomobject]$sanitizedAnchor
        }
    }
}
elseif (
    -not [string]::IsNullOrWhiteSpace($AnchorKind) -or
    -not [string]::IsNullOrWhiteSpace($AnchorPath) -or
    -not [string]::IsNullOrWhiteSpace($AnchorSymbol) -or
    -not [string]::IsNullOrWhiteSpace($AnchorSection) -or
    -not [string]::IsNullOrWhiteSpace($AnchorUrl) -or
    -not [string]::IsNullOrWhiteSpace($AnchorSelector) -or
    -not [string]::IsNullOrWhiteSpace($AnchorLabel) -or
    (ConvertTo-SafeInt $AnchorLine) -gt 0 -or
    (ConvertTo-SafeInt $AnchorEndLine) -gt 0
) {
    $anchorMap = [ordered]@{}
    if (-not [string]::IsNullOrWhiteSpace($AnchorKind)) { $anchorMap.kind = $AnchorKind }
    if (-not [string]::IsNullOrWhiteSpace($AnchorPath)) { $anchorMap.path = $AnchorPath }
    if ((ConvertTo-SafeInt $AnchorLine) -gt 0) { $anchorMap.line = (ConvertTo-SafeInt $AnchorLine) }
    if ((ConvertTo-SafeInt $AnchorEndLine) -gt 0) { $anchorMap.end_line = (ConvertTo-SafeInt $AnchorEndLine) }
    if (-not [string]::IsNullOrWhiteSpace($AnchorSymbol)) { $anchorMap.symbol = $AnchorSymbol }
    if (-not [string]::IsNullOrWhiteSpace($AnchorSection)) { $anchorMap.section = $AnchorSection }
    if (-not [string]::IsNullOrWhiteSpace($AnchorUrl)) { $anchorMap.url = $AnchorUrl }
    if (-not [string]::IsNullOrWhiteSpace($AnchorSelector)) { $anchorMap.selector = $AnchorSelector }
    if (-not [string]::IsNullOrWhiteSpace($AnchorLabel)) { $anchorMap.label = $AnchorLabel }
    if ($anchorMap.Count -gt 0) {
        $anchors = @([pscustomobject]$anchorMap)
    }
}
$anchorsJson = @($anchors) | ConvertTo-Json -Compress -Depth 8
if ([string]::IsNullOrWhiteSpace($anchorsJson)) {
    $anchorsJson = '[]'
}

$eventOutput = Invoke-WithFileLock -LockRoot $EventsFile -ScriptBlock {
    $existingEvents = Import-Events $EventsFile

    $eventId = 'evt-{0:d4}' -f ($existingEvents.Count + 1)

    $eventFields = [System.Collections.Generic.List[string]]::new()
    $eventFields.Add((ConvertTo-JsonString 'schema_version' $script:SCHEMA_VERSION))
    $eventFields.Add((ConvertTo-JsonString 'taxonomy_version' $taxonomyVersion))
    $eventFields.Add((ConvertTo-JsonString 'event_id' $eventId))
    $eventFields.Add((ConvertTo-JsonString 'incident_id' $incidentId))
    $eventFields.Add((ConvertTo-JsonString 'fingerprint' $fingerprint))
    $eventFields.Add((ConvertTo-JsonString 'recorded_at' $recorded))
    $eventFields.Add((ConvertTo-JsonString 'repo_root' $RepoRoot))
    $eventFields.Add((ConvertTo-JsonString 'events_file' $repoRelativeEventsFile))
    $eventFields.Add((ConvertTo-JsonString 'provenance_source' $provenanceSource))
    $eventFields.Add((ConvertTo-JsonString 'agent_name' $AgentName))
    $eventFields.Add((ConvertTo-JsonString 'agent_kind' $AgentKind))
    $eventFields.Add((ConvertTo-JsonString 'role' $Role))
    $eventFields.Add((ConvertTo-JsonBool 'quick_capture' $quickCapture))
    $eventFields.Add((ConvertTo-JsonBool 'force_capture' $forceCapture))
    $eventFields.Add((ConvertTo-JsonBool 'redaction_applied' $redactionApplied))
    $eventFields.Add((ConvertTo-JsonString 'title' $Title))
    $eventFields.Add((ConvertTo-JsonString 'title_line' $titleLine))
    $eventFields.Add((ConvertTo-JsonString 'instruction_source' $InstructionSource))
    $eventFields.Add((ConvertTo-JsonString 'instruction_text' $InstructionText))
    $eventFields.Add((ConvertTo-JsonString 'action_taken' $ActionTaken))
    $eventFields.Add((ConvertTo-JsonString 'expected_outcome' $ExpectedOutcome))
    $eventFields.Add((ConvertTo-JsonString 'actual_outcome' $ActualOutcome))
    $eventFields.Add((ConvertTo-JsonString 'interpretation' $Interpretation))
    $eventFields.Add((ConvertTo-JsonString 'command' $Command))
    $eventFields.Add((ConvertTo-JsonString 'tool_name' $ToolName))
    $eventFields.Add((ConvertTo-JsonString 'stderr' $Stderr))
    $eventFields.Add((ConvertTo-JsonString 'stdout_excerpt' $StdoutExcerpt))
    $eventFields.Add((ConvertTo-JsonString 'owner_hint' $OwnerHint))
    $eventFields.Add((ConvertTo-JsonString 'component_hint' $ComponentHint))
    $eventFields.Add((ConvertTo-JsonString 'workaround_note' $WorkaroundNote))
    $eventFields.Add((ConvertTo-JsonString 'observed_surface' $ObservedSurface))
    $eventFields.Add((ConvertTo-JsonString 'surface' $Surface))
    $eventFields.Add((ConvertTo-JsonString 'mode' $Mode))
    $eventFields.Add((ConvertTo-JsonString 'run_effect' $RunEffect))
    $eventFields.Add((ConvertTo-JsonString 'guidance_quality' $GuidanceQuality))
    $eventFields.Add((ConvertTo-JsonString 'confidence' $Confidence))
    $eventFields.Add((ConvertTo-JsonString 'evidence_type' $EvidenceType))
    $eventFields.Add((ConvertTo-JsonString 'derived_category' $derivedCategory))
    $eventFields.Add((ConvertTo-JsonString 'tags_csv' $Tags))
    $eventFields.Add((ConvertTo-JsonString 'incident_status' $IncidentStatus))
    $eventFields.Add((ConvertTo-JsonBool 'workaround_used' $workaroundUsedBool))
    $eventFields.Add((ConvertTo-JsonNumber 'exit_code' $exitCodeInt))
    $eventFields.Add((ConvertTo-JsonNumber 'retries_lost' $retriesLostInt))
    $eventFields.Add((ConvertTo-JsonNumber 'minutes_lost' $minutesLostInt))
    $eventFields.Add((ConvertTo-JsonString 'privacy_tier' $PrivacyTier))
    $eventFields.Add('"anchors":' + $anchorsJson)

    $eventJson = '{' + ($eventFields -join ',') + '}'

    [System.IO.File]::AppendAllText($EventsFile, "$eventJson`n", [System.Text.UTF8Encoding]::new($false))
    return [pscustomobject]@{
        EventId = $eventId
        EventCount = $existingEvents.Count + 1
    }
}

& "$PSScriptRoot/build-index.ps1" -EventsFile $EventsFile -IndexFile $IndexFile -RepoRoot $RepoRoot | Out-Null

Write-Output "event_id=$($eventOutput.EventId)"
Write-Output "events_file=$EventsFile"
Write-Output "index_file=$IndexFile"
