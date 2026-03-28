param(
    [string]$EventsFile = $env:FRICTION_EVENTS_FILE,
    [string]$IndexFile = $env:FRICTION_INDEX_FILE,
    [string]$RepoRoot = $env:FRICTION_REPO_ROOT,
    [string]$FromJson = '',
    [string]$Title = '',
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
    [string]$Command = '',
    [string]$ToolName = '',
    [string]$ExitCode = '',
    [string]$Stderr = '',
    [string]$StdoutExcerpt = '',
    [string]$OwnerHint = '',
    [string]$ComponentHint = '',
    [string]$WorkaroundUsed = 'false',
    [string]$WorkaroundNote = '',
    [string]$RetriesLost = '0',
    [string]$MinutesLost = '0',
    [string]$FingerprintKey = '',
    [string]$Tags = '',
    [Alias('Agent')][string]$AgentName = $(if ($env:FRICTION_AGENT_NAME) { $env:FRICTION_AGENT_NAME } else { '' }),
    [string]$AgentKind = $(if ($env:FRICTION_AGENT_KIND) { $env:FRICTION_AGENT_KIND } else { '' }),
    [string]$Role = $(if ($env:FRICTION_ROLE) { $env:FRICTION_ROLE } else { '' }),
    [string]$SourceType = '',
    [string]$SourceRef = '',
    [string]$SourceLine = '',
    [string]$SourceEndLine = '',
    [string]$SourceSymbol = '',
    [string]$SourceExcerpt = '',
    [string]$SourceSelector = '',
    [string]$SourceLabel = '',
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/report-friction.ps1 -Title "..." [fields]
  scripts/report-friction.ps1 -RepoRoot <repo> -FromJson event.json
  scripts/report-friction.ps1 -EventsFile /path/to/events.jsonl -FromJson event.json

Normal path:
  Appends one sanitized event to the repo-scoped rolling events file under
  .local/reports/friction (or another existing .local*/reports/friction when
  .local is absent), then rebuilds INDEX.md automatically. Outside a git repo,
  it falls back to the system temp directory.

Selection:
  -RepoRoot PATH      Resolve the canonical repo-scoped events.jsonl and INDEX.md for PATH.
  -EventsFile PATH    Override the canonical storage file directly.
  -IndexFile PATH     Override the generated INDEX.md path.
  -FromJson PATH|-    Load event fields from a JSON object on disk or stdin.
                      Prefer stdin for shell-sensitive or multiline payloads.

Source fields (single source via CLI; use -FromJson for multiple):
  -SourceType TYPE    One of: file, url, system-instruction, conversation,
                      audio, visual, documentation, other
  -SourceRef TEXT     Primary reference (filepath, URL, description)
  -SourceLine INT     Start line (for files)
  -SourceEndLine INT  End line (for file ranges)
  -SourceSymbol TEXT  Function, class, section, or heading name
  -SourceExcerpt TEXT Relevant quoted text from the source
  -SourceSelector TEXT CSS/XPath selector or similar
  -SourceLabel TEXT   Human-readable description of this source's role

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

$superprojectRoot = Get-GitSuperprojectRoot
$submodulePath = ''
if ($superprojectRoot -and $RepoRoot) {
    $submodulePath = Get-GitSubmodulePath -SuperprojectRoot $superprojectRoot -RepoRoot $RepoRoot
}

# --- Sources array: resolved from -FromJson or CLI flags ---
$fromJsonSources = $null   # $null means not yet resolved from JSON

$fromJsonPayload = $null
if (-not [string]::IsNullOrWhiteSpace($FromJson)) {
    $fromJsonPayload = Import-EventJsonObject $FromJson
    $diagnosticPath = Get-JsonDiagnosticLabel $FromJson

    $Title = Get-JsonFieldValue $fromJsonPayload 'title' $Title ''
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
    $Command = Get-JsonFieldValue $fromJsonPayload 'command' $Command ''
    $ToolName = Get-JsonFieldValue $fromJsonPayload 'tool_name' $ToolName ''
    $ExitCode = Get-JsonFieldValue $fromJsonPayload 'exit_code' $ExitCode ''
    $Stderr = Get-JsonFieldValue $fromJsonPayload 'stderr' $Stderr ''
    $StdoutExcerpt = Get-JsonFieldValue $fromJsonPayload 'stdout_excerpt' $StdoutExcerpt ''
    $OwnerHint = Get-JsonFieldValue $fromJsonPayload 'owner_hint' $OwnerHint ''
    $ComponentHint = Get-JsonFieldValue $fromJsonPayload 'component_hint' $ComponentHint ''
    $WorkaroundUsed = Get-JsonFieldValue $fromJsonPayload 'workaround_used' $WorkaroundUsed 'false'
    $WorkaroundNote = Get-JsonFieldValue $fromJsonPayload 'workaround_note' $WorkaroundNote ''
    $RetriesLost = Get-JsonFieldValue $fromJsonPayload 'retries_lost' $RetriesLost '0'
    $MinutesLost = Get-JsonFieldValue $fromJsonPayload 'minutes_lost' $MinutesLost '0'
    $FingerprintKey = Get-JsonFieldValue $fromJsonPayload 'fingerprint_key' $FingerprintKey ''
    $Tags = Get-JsonFieldValue $fromJsonPayload 'tags' $Tags ''
    $AgentName = Get-JsonFieldValue $fromJsonPayload 'agent_name' $AgentName ''
    $AgentKind = Get-JsonFieldValue $fromJsonPayload 'agent_kind' $AgentKind ''
    $Role = Get-JsonFieldValue $fromJsonPayload 'role' $Role ''

    # --- Resolve sources array (v3 native or backward compat from v2) ---
    $sourcesProperty = $fromJsonPayload.PSObject.Properties['sources']
    if ($null -ne $sourcesProperty -and $null -ne $sourcesProperty.Value) {
        # v3: native sources array
        $candidateSources = @($sourcesProperty.Value)
        $errors = [System.Collections.Generic.List[string]]::new()
        $resolvedSources = [System.Collections.Generic.List[object]]::new()
        $i = 0
        foreach ($src in $candidateSources) {
            if ($src -isnot [pscustomobject] -and $src -isnot [hashtable]) {
                $errors.Add("sources[$i] must be an object")
                $i++
                continue
            }
            $typeProp = $src.PSObject.Properties['type']
            $refProp = $src.PSObject.Properties['ref']
            $srcValid = $true
            if ($null -eq $typeProp -or [string]::IsNullOrWhiteSpace([string]$typeProp.Value)) {
                $errors.Add("sources[$i].type is required")
                $srcValid = $false
            } elseif ($script:VALID_SOURCE_TYPES -notcontains [string]$typeProp.Value) {
                $errors.Add("sources[$i].type must be one of: $($script:VALID_SOURCE_TYPES -join ', ') (got '$($typeProp.Value)')")
                $srcValid = $false
            }
            if ($null -eq $refProp -or [string]::IsNullOrWhiteSpace([string]$refProp.Value)) {
                $errors.Add("sources[$i].ref is required")
                $srcValid = $false
            }
            if ($srcValid) {
                $srcMap = [ordered]@{}
                $srcMap['type'] = [string]$typeProp.Value
                $srcMap['ref'] = Protect-Text ([string]$refProp.Value)
                foreach ($optKey in @('line', 'end_line', 'symbol', 'excerpt', 'selector', 'label')) {
                    $optProp = $src.PSObject.Properties[$optKey]
                    if ($null -ne $optProp -and $null -ne $optProp.Value) {
                        if ($optKey -in @('line', 'end_line')) {
                            $numVal = ConvertTo-SafeInt ([string]$optProp.Value)
                            if ($numVal -gt 0) { $srcMap[$optKey] = $numVal }
                        } else {
                            $textVal = Protect-Text ([string]$optProp.Value)
                            if (-not [string]::IsNullOrWhiteSpace($textVal)) { $srcMap[$optKey] = $textVal }
                        }
                    }
                }
                $resolvedSources.Add([pscustomobject]$srcMap)
            }
            $i++
        }
        if ($errors.Count -gt 0) {
            throw "Invalid sources in -FromJson $diagnosticPath:`n" + ($errors -join "`n")
        }
        $fromJsonSources = $resolvedSources.ToArray()
    } else {
        # v2 backward compat: build sources from instruction_source and/or anchors
        $backCompatSources = [System.Collections.Generic.List[object]]::new()
        $instrSrcProp = $fromJsonPayload.PSObject.Properties['instruction_source']
        if ($null -ne $instrSrcProp -and -not [string]::IsNullOrWhiteSpace([string]$instrSrcProp.Value)) {
            $srcMap = [ordered]@{ type = 'documentation'; ref = Protect-Text ([string]$instrSrcProp.Value) }
            $backCompatSources.Add([pscustomobject]$srcMap)
        }
        $anchorsProp = $fromJsonPayload.PSObject.Properties['anchors']
        if ($null -ne $anchorsProp -and $null -ne $anchorsProp.Value) {
            foreach ($anc in @($anchorsProp.Value)) {
                if ($anc -isnot [pscustomobject] -and $anc -isnot [hashtable]) { continue }
                $srcMap = [ordered]@{}
                $urlProp = $anc.PSObject.Properties['url']
                $pathProp = $anc.PSObject.Properties['path']
                if ($null -ne $urlProp -and -not [string]::IsNullOrWhiteSpace([string]$urlProp.Value)) {
                    $srcMap['type'] = 'url'
                    $srcMap['ref'] = Protect-Text ([string]$urlProp.Value)
                } elseif ($null -ne $pathProp -and -not [string]::IsNullOrWhiteSpace([string]$pathProp.Value)) {
                    $srcMap['type'] = 'file'
                    $srcMap['ref'] = Protect-Text ([string]$pathProp.Value)
                } else {
                    $labelProp = $anc.PSObject.Properties['label']
                    $sectionProp = $anc.PSObject.Properties['section']
                    $fallbackRef = if ($null -ne $labelProp) { [string]$labelProp.Value } elseif ($null -ne $sectionProp) { [string]$sectionProp.Value } else { 'unknown' }
                    $srcMap['type'] = 'other'
                    $srcMap['ref'] = Protect-Text $fallbackRef
                }
                foreach ($optKey in @('line', 'end_line', 'symbol', 'section', 'selector', 'label')) {
                    $optProp = $anc.PSObject.Properties[$optKey]
                    if ($null -ne $optProp -and $null -ne $optProp.Value) {
                        if ($optKey -in @('line', 'end_line')) {
                            $numVal = ConvertTo-SafeInt ([string]$optProp.Value)
                            if ($numVal -gt 0) { $srcMap[$optKey] = $numVal }
                        } else {
                            $textVal = Protect-Text ([string]$optProp.Value)
                            if (-not [string]::IsNullOrWhiteSpace($textVal)) { $srcMap[$optKey] = $textVal }
                        }
                    }
                }
                # Deduplicate: skip if same ref already present
                $thisRef = $srcMap['ref']
                $alreadyPresent = $false
                foreach ($existing in $backCompatSources) {
                    if ($existing.PSObject.Properties['ref'].Value -eq $thisRef) { $alreadyPresent = $true; break }
                }
                if (-not $alreadyPresent) {
                    $backCompatSources.Add([pscustomobject]$srcMap)
                }
            }
        }
        if ($backCompatSources.Count -gt 0) {
            $fromJsonSources = $backCompatSources.ToArray()
        }
        # If still no sources, we'll catch that in the required-source validation below
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

# --- Sanitize text fields ---
$Title = Protect-Text $Title
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
$AgentName = Protect-Text $AgentName
$AgentKind = Protect-Text $AgentKind
$Role = Protect-Text $Role
$RepoRoot = Protect-Text $RepoRoot

# --- Validate required narrative fields ---
foreach ($field in @(
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

# --- Validate narrative depth ---
Test-NarrativeLength 'instruction_text' $InstructionText 20
Test-NarrativeLength 'action_taken' $ActionTaken 30
Test-NarrativeLength 'expected_outcome' $ExpectedOutcome 20
Test-NarrativeLength 'actual_outcome' $ActualOutcome 20
Test-NarrativeLength 'interpretation' $Interpretation 40

# --- Build sources array ---
$sources = @()
if ($null -ne $fromJsonSources) {
    $sources = $fromJsonSources
} elseif (-not [string]::IsNullOrWhiteSpace($SourceRef)) {
    # CLI single-source path
    $resolvedSourceType = if ([string]::IsNullOrWhiteSpace($SourceType)) { 'documentation' } else { $SourceType }
    Test-SourceType $resolvedSourceType
    $srcMap = [ordered]@{
        type = $resolvedSourceType
        ref  = Protect-Text $SourceRef
    }
    $srcLineInt = ConvertTo-SafeInt $SourceLine
    $srcEndLineInt = ConvertTo-SafeInt $SourceEndLine
    if ($srcLineInt -gt 0) { $srcMap['line'] = $srcLineInt }
    if ($srcEndLineInt -gt 0) { $srcMap['end_line'] = $srcEndLineInt }
    $sanitizedSymbol = Protect-Text $SourceSymbol
    $sanitizedExcerpt = Protect-Text $SourceExcerpt
    $sanitizedSelector = Protect-Text $SourceSelector
    $sanitizedLabel = Protect-Text $SourceLabel
    if (-not [string]::IsNullOrWhiteSpace($sanitizedSymbol)) { $srcMap['symbol'] = $sanitizedSymbol }
    if (-not [string]::IsNullOrWhiteSpace($sanitizedExcerpt)) { $srcMap['excerpt'] = $sanitizedExcerpt }
    if (-not [string]::IsNullOrWhiteSpace($sanitizedSelector)) { $srcMap['selector'] = $sanitizedSelector }
    if (-not [string]::IsNullOrWhiteSpace($sanitizedLabel)) { $srcMap['label'] = $sanitizedLabel }
    $sources = @([pscustomobject]$srcMap)
} else {
    throw "Missing required source: provide -SourceRef (and optionally -SourceType) or use -FromJson with a sources array"
}

# Extract primary source ref for fingerprinting and categorizer
$primarySourceRef = if ($sources.Count -gt 0) { [string]($sources[0].PSObject.Properties['ref'].Value) } else { '' }

# Extract source types CSV for tag generation
$sourceTypeCsv = ($sources | ForEach-Object {
    $tp = $_.PSObject.Properties['type']
    if ($null -ne $tp) { [string]$tp.Value } else { '' }
} | Where-Object { $_ }) -join ','

# --- Run categorizer ---
$auto = & "$PSScriptRoot/categorize.ps1" `
    -SourceRef $primarySourceRef `
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
    -SourceTypeCsv $sourceTypeCsv

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
$ObservedSurface = $autoMap['observed_surface']
$derivedCategory = $autoMap['derived_category']
$taxonomyVersion = $autoMap['taxonomy_version']

# --- Merge user-supplied tags with auto-generated tags ---
$mergedTags = $autoMap['tags']
if (-not [string]::IsNullOrWhiteSpace($Tags)) {
    foreach ($item in ($Tags -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
        $mergedTags = Add-CsvItem $mergedTags $item
    }
}
$Tags = $mergedTags

# --- Normalize numeric/bool fields ---
$workaroundUsedBool = ConvertTo-NormalizedBool $WorkaroundUsed
$retriesLostInt = ConvertTo-SafeInt $RetriesLost
$minutesLostInt = ConvertTo-SafeInt $MinutesLost
$exitCodeInt = ConvertTo-SafeInt $ExitCode
$guidanceQualityInt = ConvertTo-NormalizedGuidanceQuality $GuidanceQuality
$confidenceInt = ConvertTo-NormalizedConfidence $Confidence

# --- Auto-title: [surface/mode] actual_outcome_excerpt ---
if ([string]::IsNullOrWhiteSpace($Title)) {
    $titleBody = Get-TruncatedLine -Text (Get-FirstLine $ActualOutcome) -Limit 60
    $Title = "[$Surface/$Mode] $titleBody"
}

# --- Owner hint default ---
if ([string]::IsNullOrWhiteSpace($OwnerHint)) {
    $OwnerHint = Get-DefaultOwnerForSurface $Surface
}

$fingerprint = Get-EventFingerprint -RootSurface $Surface -Mode $Mode -SourceRef $primarySourceRef -ActualOutcome $ActualOutcome -ActionTaken $ActionTaken -Title $Title -CustomKey $FingerprintKey
$incidentId = "inc-$fingerprint"
$recorded = [System.DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
$provenanceSource = if (-not [string]::IsNullOrWhiteSpace($AgentName) -or -not [string]::IsNullOrWhiteSpace($AgentKind) -or -not [string]::IsNullOrWhiteSpace($Role)) { 'explicit' } else { 'unspecified' }
$repoRelativeEventsFile = ''
if (-not [string]::IsNullOrWhiteSpace($RepoRoot) -and $EventsFile.StartsWith($RepoRoot)) {
    $repoRelativeEventsFile = $EventsFile.Substring($RepoRoot.Length).TrimStart('\', '/')
}
if ([string]::IsNullOrWhiteSpace($repoRelativeEventsFile)) {
    $repoRelativeEventsFile = $EventsFile
}

# Build sources JSON array
$sourcesJson = @($sources) | ConvertTo-Json -Compress -Depth 8
if ([string]::IsNullOrWhiteSpace($sourcesJson) -or $sourcesJson -eq 'null') {
    $sourcesJson = '[]'
}

# Build tags JSON array
$tagsArray = ConvertTo-JsonTagArray $Tags

$eventOutput = Invoke-WithFileLock -LockRoot $EventsFile -ScriptBlock {
    $existingEvents = Import-Events $EventsFile

    $eventId = 'evt-{0:d4}' -f ($existingEvents.Count + 1)

    $eventFields = [System.Collections.Generic.List[string]]::new()
    # Always-present metadata
    $eventFields.Add((ConvertTo-JsonString 'schema_version' $script:SCHEMA_VERSION))
    $eventFields.Add((ConvertTo-JsonString 'taxonomy_version' $taxonomyVersion))
    $eventFields.Add((ConvertTo-JsonString 'event_id' $eventId))
    $eventFields.Add((ConvertTo-JsonString 'incident_id' $incidentId))
    $eventFields.Add((ConvertTo-JsonString 'fingerprint' $fingerprint))
    $eventFields.Add((ConvertTo-JsonString 'recorded_at' $recorded))
    $eventFields.Add((ConvertTo-JsonString 'events_file' $repoRelativeEventsFile))
    $eventFields.Add((ConvertTo-JsonString 'repo_root' $RepoRoot))
    if (-not [string]::IsNullOrEmpty($superprojectRoot)) { $eventFields.Add((ConvertTo-JsonString 'superproject_root' $superprojectRoot)) }
    if (-not [string]::IsNullOrEmpty($submodulePath)) { $eventFields.Add((ConvertTo-JsonString 'submodule_path' $submodulePath)) }
    # Identity (agent_name/agent_kind always present; role sparse)
    $eventFields.Add((ConvertTo-JsonString 'agent_name' $AgentName))
    $eventFields.Add((ConvertTo-JsonString 'agent_kind' $AgentKind))
    if (-not [string]::IsNullOrEmpty($Role)) {
        $eventFields.Add((ConvertTo-JsonString 'role' $Role))
    }
    $eventFields.Add((ConvertTo-JsonString 'provenance_source' $provenanceSource))
    # Core narrative (always present)
    $eventFields.Add((ConvertTo-JsonString 'title' $Title))
    $eventFields.Add((ConvertTo-JsonString 'instruction_text' $InstructionText))
    $eventFields.Add((ConvertTo-JsonString 'action_taken' $ActionTaken))
    $eventFields.Add((ConvertTo-JsonString 'expected_outcome' $ExpectedOutcome))
    $eventFields.Add((ConvertTo-JsonString 'actual_outcome' $ActualOutcome))
    $eventFields.Add((ConvertTo-JsonString 'interpretation' $Interpretation))
    # Sparse optional context
    if (-not [string]::IsNullOrEmpty($Command)) { $eventFields.Add((ConvertTo-JsonString 'command' $Command)) }
    if (-not [string]::IsNullOrEmpty($ToolName)) { $eventFields.Add((ConvertTo-JsonString 'tool_name' $ToolName)) }
    if (-not [string]::IsNullOrEmpty($Stderr)) { $eventFields.Add((ConvertTo-JsonString 'stderr' $Stderr)) }
    if (-not [string]::IsNullOrEmpty($StdoutExcerpt)) { $eventFields.Add((ConvertTo-JsonString 'stdout_excerpt' $StdoutExcerpt)) }
    if (-not [string]::IsNullOrEmpty($OwnerHint)) { $eventFields.Add((ConvertTo-JsonString 'owner_hint' $OwnerHint)) }
    if (-not [string]::IsNullOrEmpty($ComponentHint)) { $eventFields.Add((ConvertTo-JsonString 'component_hint' $ComponentHint)) }
    if (-not [string]::IsNullOrEmpty($WorkaroundNote)) { $eventFields.Add((ConvertTo-JsonString 'workaround_note' $WorkaroundNote)) }
    # Classification (always present, numeric)
    $eventFields.Add((ConvertTo-JsonString 'observed_surface' $ObservedSurface))
    $eventFields.Add((ConvertTo-JsonString 'surface' $Surface))
    $eventFields.Add((ConvertTo-JsonString 'mode' $Mode))
    $eventFields.Add((ConvertTo-JsonString 'run_effect' $RunEffect))
    if ($null -ne $guidanceQualityInt) { $eventFields.Add((ConvertTo-JsonNumber 'guidance_quality' $guidanceQualityInt)) }
    if ($null -ne $confidenceInt) { $eventFields.Add((ConvertTo-JsonNumber 'confidence' $confidenceInt)) }
    $eventFields.Add((ConvertTo-JsonString 'derived_category' $derivedCategory))
    $tagsJson = ($tagsArray | ConvertTo-Json -Compress)
    if ([string]::IsNullOrWhiteSpace($tagsJson) -or $tagsJson -eq 'null') { $tagsJson = '[]' }
    $eventFields.Add('"tags":' + $tagsJson)
    # Sparse impact fields
    if ($workaroundUsedBool) { $eventFields.Add((ConvertTo-JsonBool 'workaround_used' $workaroundUsedBool)) }
    if ($exitCodeInt -ne 0) { $eventFields.Add((ConvertTo-JsonNumber 'exit_code' $exitCodeInt)) }
    if ($retriesLostInt -ne 0) { $eventFields.Add((ConvertTo-JsonNumber 'retries_lost' $retriesLostInt)) }
    if ($minutesLostInt -ne 0) { $eventFields.Add((ConvertTo-JsonNumber 'minutes_lost' $minutesLostInt)) }
    # Sources array (always present, replaces anchors + instruction_source)
    $eventFields.Add('"sources":' + $sourcesJson)

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
