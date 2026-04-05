param(
    [string]$EventsFile = $env:FRICTION_EVENTS_FILE,
    [string]$IndexFile = $env:FRICTION_INDEX_FILE,
    [string]$RepoRoot = $env:FRICTION_REPO_ROOT,
    [string]$FromJson = '',
    [string]$Title = '',
    [string]$ExpectedOutcome = '',
    [string]$ActualOutcome = '',
    [string]$Reading = '',
    [string]$Hindsight = '',
    [ValidateSet('blocked', 'degraded', 'noisy', 'continued')]
    [string]$Impact = '',
    [string]$Tags = '',
    [string]$Aliases = '',
    [string]$FingerprintKey = '',
    [string]$AddTags = '',
    [string]$AddTagsCsv = '',
    [string]$AddAliases = '',
    [string]$AddAliasesCsv = '',
    [string]$SourceType = '',
    [string]$SourceRef = '',
    [string]$SourceLine = '',
    [string]$SourceEndLine = '',
    [string]$SourceExcerpt = '',
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

Core fields:
  -Title TEXT
  -ExpectedOutcome TEXT
  -ActualOutcome TEXT
  -Reading TEXT
  -Hindsight TEXT

Classification:
  -Impact VALUE       blocked | degraded | noisy | continued (required)
  -Tags TEXT          Comma-separated specific tags (normalized to lowercase)
  -Aliases TEXT       Comma-separated broader groupings (normalized to lowercase)

Source fields (single source via CLI; use -FromJson for multiple):
  -SourceType TYPE    One of: file, url, conversation, audio, visual,
                      documentation, other
  -SourceRef TEXT     Primary reference (filepath, URL, description)
  -SourceLine INT     Start line (for files)
  -SourceEndLine INT  End line (for file ranges)
  -SourceExcerpt TEXT Verbatim quote from the source

Fingerprint:
  -FingerprintKey TEXT  Override the default fingerprint seed

Tag/alias management (run after initial event creation):
  -AddTags EVENT_ID -AddTagsCsv "tag1,tag2"
                      Add tags to an existing event by event_id.
  -AddAliases EVENT_ID -AddAliasesCsv "alias1,alias2"
                      Add aliases to an existing event by event_id.
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

$paths = Resolve-FrictionPaths -RepoRoot $RepoRoot -EventsFile $EventsFile -IndexFile $IndexFile
$EventsFile = $paths.EventsFile
$IndexFile = $paths.IndexFile
$RepoRoot = $paths.RepoRoot

# --- --AddTags mode: patch tags on an existing event ---
if (-not [string]::IsNullOrWhiteSpace($AddTags)) {
    if ([string]::IsNullOrWhiteSpace($AddTagsCsv)) {
        throw "-AddTags requires both EVENT_ID (via -AddTags) and tags (via -AddTagsCsv)"
    }
    if (-not (Test-Path -LiteralPath $EventsFile)) {
        throw "Events file not found: $EventsFile"
    }
    $newTags = @($AddTagsCsv.Split(',') | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    if ($newTags.Count -eq 0) { throw "No tags provided" }
    Invoke-WithFileLock -LockRoot $EventsFile -ScriptBlock {
        $lines = [System.Collections.Generic.List[string]]::new()
        $found = $false
        foreach ($line in [System.IO.File]::ReadLines($EventsFile)) {
            $stripped = $line.Trim()
            if ([string]::IsNullOrWhiteSpace($stripped)) { $lines.Add($line); continue }
            $event = $stripped | ConvertFrom-Json -DateKind String -ErrorAction Stop
            if ($event.PSObject.Properties['event_id'].Value -eq $AddTags) {
                $found = $true
                $existing = @()
                $tagsProp = $event.PSObject.Properties['tags']
                if ($null -ne $tagsProp) {
                    if ($tagsProp.Value -is [System.Array]) {
                        $existing = @($tagsProp.Value | ForEach-Object { [string]$_ } | Where-Object { $_ })
                    } elseif (-not [string]::IsNullOrWhiteSpace([string]$tagsProp.Value)) {
                        $existing = @(([string]$tagsProp.Value).Split(',') | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
                    }
                }
                $merged = [System.Collections.Generic.List[string]]::new()
                $seen = [System.Collections.Generic.HashSet[string]]::new()
                foreach ($t in ($existing + $newTags)) { if ($seen.Add($t)) { $merged.Add($t) } }
                $event.tags = $merged.ToArray()
                $lines.Add(($event | ConvertTo-Json -Compress -Depth 8))
            } else {
                $lines.Add($line.TrimEnd("`r", "`n"))
            }
        }
        if (-not $found) { throw "Event not found: $AddTags" }
        $tempFile = Join-Path ([System.IO.Path]::GetDirectoryName($EventsFile)) ([System.IO.Path]::GetRandomFileName() + '.tmp')
        try {
            [System.IO.File]::WriteAllLines($tempFile, $lines.ToArray(), [System.Text.UTF8Encoding]::new($false))
            Move-Item -LiteralPath $tempFile -Destination $EventsFile -Force
        }
        finally {
            if (Test-Path -LiteralPath $tempFile) {
                Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
            }
        }
    } | Out-Null
    & "$PSScriptRoot/build-index.ps1" -EventsFile $EventsFile -IndexFile $IndexFile -RepoRoot $RepoRoot | Out-Null
    Write-Output "FRICTION_TAGS_UPDATED=$AddTags"
    exit 0
}

# --- --AddAliases mode: patch aliases on an existing event ---
if (-not [string]::IsNullOrWhiteSpace($AddAliases)) {
    if ([string]::IsNullOrWhiteSpace($AddAliasesCsv)) {
        throw "-AddAliases requires both EVENT_ID (via -AddAliases) and aliases (via -AddAliasesCsv)"
    }
    if (-not (Test-Path -LiteralPath $EventsFile)) {
        throw "Events file not found: $EventsFile"
    }
    $newAliases = @($AddAliasesCsv.Split(',') | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    if ($newAliases.Count -eq 0) { throw "No aliases provided" }
    Invoke-WithFileLock -LockRoot $EventsFile -ScriptBlock {
        $lines = [System.Collections.Generic.List[string]]::new()
        $found = $false
        foreach ($line in [System.IO.File]::ReadLines($EventsFile)) {
            $stripped = $line.Trim()
            if ([string]::IsNullOrWhiteSpace($stripped)) { $lines.Add($line); continue }
            $event = $stripped | ConvertFrom-Json -DateKind String -ErrorAction Stop
            if ($event.PSObject.Properties['event_id'].Value -eq $AddAliases) {
                $found = $true
                $existing = @()
                $aliasesProp = $event.PSObject.Properties['aliases']
                if ($null -ne $aliasesProp) {
                    if ($aliasesProp.Value -is [System.Array]) {
                        $existing = @($aliasesProp.Value | ForEach-Object { [string]$_ } | Where-Object { $_ })
                    } elseif (-not [string]::IsNullOrWhiteSpace([string]$aliasesProp.Value)) {
                        $existing = @(([string]$aliasesProp.Value).Split(',') | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
                    }
                }
                $merged = [System.Collections.Generic.List[string]]::new()
                $seen = [System.Collections.Generic.HashSet[string]]::new()
                foreach ($a in ($existing + $newAliases)) { if ($seen.Add($a)) { $merged.Add($a) } }
                $event.aliases = $merged.ToArray()
                $lines.Add(($event | ConvertTo-Json -Compress -Depth 8))
            } else {
                $lines.Add($line.TrimEnd("`r", "`n"))
            }
        }
        if (-not $found) { throw "Event not found: $AddAliases" }
        $tempFile = Join-Path ([System.IO.Path]::GetDirectoryName($EventsFile)) ([System.IO.Path]::GetRandomFileName() + '.tmp')
        try {
            [System.IO.File]::WriteAllLines($tempFile, $lines.ToArray(), [System.Text.UTF8Encoding]::new($false))
            Move-Item -LiteralPath $tempFile -Destination $EventsFile -Force
        }
        finally {
            if (Test-Path -LiteralPath $tempFile) {
                Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
            }
        }
    } | Out-Null
    & "$PSScriptRoot/build-index.ps1" -EventsFile $EventsFile -IndexFile $IndexFile -RepoRoot $RepoRoot | Out-Null
    Write-Output "FRICTION_ALIASES_UPDATED=$AddAliases"
    exit 0
}

# --- Sources array: resolved from -FromJson or CLI flags ---
$fromJsonSources = $null   # $null means not yet resolved from JSON
$stdinJsonText = ''
if ($FromJson -eq '-') {
    $stdinJsonText = (@($input) | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
}

$fromJsonPayload = $null
if (-not [string]::IsNullOrWhiteSpace($FromJson)) {
    $fromJsonPayload = Import-EventJsonObject -Path $FromJson -StdinText $stdinJsonText -RepoRoot $RepoRoot
    $diagnosticPath = Get-JsonDiagnosticLabel $FromJson

    $Title = Get-JsonFieldValue $fromJsonPayload 'title' $Title ''
    $ExpectedOutcome = Get-JsonFieldValue $fromJsonPayload 'expected_outcome' $ExpectedOutcome ''
    $ActualOutcome = Get-JsonFieldValue $fromJsonPayload 'actual_outcome' $ActualOutcome ''
    $Reading = Get-JsonFieldValue $fromJsonPayload 'reading' $Reading ''
    $Hindsight = Get-JsonFieldValue $fromJsonPayload 'hindsight' $Hindsight ''
    $Impact = Get-JsonFieldValue $fromJsonPayload 'impact' $Impact ''
    $FingerprintKey = Get-JsonFieldValue $fromJsonPayload 'fingerprint_key' $FingerprintKey ''

    # Resolve tags from JSON (array -> csv)
    $tagsProperty = $fromJsonPayload.PSObject.Properties['tags']
    if ($null -ne $tagsProperty -and $null -ne $tagsProperty.Value -and $tagsProperty.Value -is [System.Array] -and $Tags -eq '') {
        $Tags = ($tagsProperty.Value | ForEach-Object { [string]$_ } | Where-Object { $_ }) -join ','
    }

    # Resolve aliases from JSON (array -> csv)
    $aliasesProperty = $fromJsonPayload.PSObject.Properties['aliases']
    if ($null -ne $aliasesProperty -and $null -ne $aliasesProperty.Value -and $aliasesProperty.Value -is [System.Array] -and $Aliases -eq '') {
        $Aliases = ($aliasesProperty.Value | ForEach-Object { [string]$_ } | Where-Object { $_ }) -join ','
    }

    # --- Resolve sources array ---
    $sourcesProperty = $fromJsonPayload.PSObject.Properties['sources']
    if ($null -ne $sourcesProperty -and $null -ne $sourcesProperty.Value) {
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
                foreach ($optKey in @('line', 'end_line', 'excerpt')) {
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
            throw "Invalid sources in -FromJson ${diagnosticPath}:`n" + ($errors -join "`n")
        }
        $fromJsonSources = $resolvedSources.ToArray()
    }

    # Validate known keys only (v4 schema)
    $v4KnownKeys = @(
        'title', 'expected_outcome', 'actual_outcome', 'reading', 'hindsight',
        'impact', 'tags', 'aliases', 'fingerprint_key', 'sources', 'events_file'
    )
    foreach ($property in $fromJsonPayload.PSObject.Properties.Name) {
        if ($v4KnownKeys -contains $property) { continue }
        throw "Unsupported key in -FromJson ${diagnosticPath}: $property"
    }

    $payloadEventsFile = Get-JsonFieldValue $fromJsonPayload 'events_file' '' ''
    if (-not [string]::IsNullOrWhiteSpace($payloadEventsFile)) {
        $resolvedPayloadEventsFile = Test-EventFileField -Path $payloadEventsFile -FieldName 'events_file' -DiagnosticPath $diagnosticPath
        if ($resolvedPayloadEventsFile -ne $EventsFile) {
            throw "events_file from -FromJson $diagnosticPath must match the selected events file"
        }
    }
}

# --- Sanitize text fields ---
$Title = Protect-Text $Title
$ExpectedOutcome = Protect-Text $ExpectedOutcome
$ActualOutcome = Protect-Text $ActualOutcome
$Reading = Protect-Text $Reading
$Hindsight = Protect-Text $Hindsight
$RepoRoot = Protect-Text $RepoRoot

# --- Validate required narrative fields ---
foreach ($field in @(
    @{ Label = 'expected_outcome'; Value = $ExpectedOutcome },
    @{ Label = 'actual_outcome'; Value = $ActualOutcome },
    @{ Label = 'reading'; Value = $Reading }
)) {
    if ([string]::IsNullOrWhiteSpace([string]$field.Value)) {
        throw "Missing required field: $($field.Label)"
    }
}

# --- Validate impact ---
if ([string]::IsNullOrWhiteSpace($Impact)) {
    throw "Missing required field: -Impact (blocked, degraded, noisy, or continued)"
}
$validImpactValues = @('blocked', 'degraded', 'noisy', 'continued')
if ($validImpactValues -notcontains $Impact) {
    throw "impact must be one of: blocked, degraded, noisy, continued (got '$Impact')"
}

# --- Validate narrative depth ---
Test-NarrativeLength 'expected_outcome' $ExpectedOutcome 15
Test-NarrativeLength 'actual_outcome' $ActualOutcome 15
Test-NarrativeLength 'reading' $Reading 30

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
    $sanitizedExcerpt = Protect-Text $SourceExcerpt
    if (-not [string]::IsNullOrWhiteSpace($sanitizedExcerpt)) { $srcMap['excerpt'] = $sanitizedExcerpt }
    $sources = @([pscustomobject]$srcMap)
} else {
    throw "Missing required source: provide -SourceRef (and optionally -SourceType) or use -FromJson with a sources array"
}

# Extract primary source ref for fingerprinting
$primarySourceRef = if ($sources.Count -gt 0) { [string]($sources[0].PSObject.Properties['ref'].Value) } else { '' }

# --- Build tags and aliases JSON arrays (normalized to lowercase) ---
function ConvertTo-NormalizedJsonArray {
    param([string]$CsvInput)
    if ([string]::IsNullOrWhiteSpace($CsvInput)) { return '[]' }
    $items = @($CsvInput.Split(',') | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    if ($items.Count -eq 0) { return '[]' }
    $escaped = $items | ForEach-Object { "`"$(ConvertTo-JsonEscape $_)`"" }
    return '[' + ($escaped -join ',') + ']'
}

$tagsJson = ConvertTo-NormalizedJsonArray $Tags
$aliasesJson = ConvertTo-NormalizedJsonArray $Aliases

# --- Auto-title from actual_outcome if not provided ---
if ([string]::IsNullOrWhiteSpace($Title)) {
    $Title = Get-TruncatedLine -Text (Get-FirstLine $ActualOutcome) -Limit 80
}

$recorded = [System.DateTimeOffset]::UtcNow
$eventDate = $recorded.ToString('yyyy-MM-dd')

# Fingerprint: hash(source_ref|date) — no surface/mode
$fingerprintSeed = if (-not [string]::IsNullOrWhiteSpace($FingerprintKey)) {
    $FingerprintKey.ToLowerInvariant() -replace '[^a-z0-9]+', ' ' | ForEach-Object { $_.Trim() }
} else {
    $normalizedRef = $primarySourceRef.ToLowerInvariant() -replace '[^a-z0-9]+', ' '
    ($normalizedRef.Trim()) + '|' + $eventDate
}
$bytes = [System.Text.Encoding]::UTF8.GetBytes($fingerprintSeed)
$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
    $hashBytes = $sha256.ComputeHash($bytes)
} finally {
    $sha256.Dispose()
}
$fingerprint = (-join ($hashBytes[0..5] | ForEach-Object { $_.ToString('x2') })).Substring(0, 12)

$recorded = $recorded.ToString('yyyy-MM-ddTHH:mm:ssZ')
$repoRelativeEventsFile = $EventsFile
if (-not [string]::IsNullOrWhiteSpace($RepoRoot) -and $EventsFile.StartsWith($RepoRoot)) {
    $rel = $EventsFile.Substring($RepoRoot.Length).TrimStart('\', '/')
    if (-not [string]::IsNullOrWhiteSpace($rel)) {
        $repoRelativeEventsFile = $rel
    }
}

# Build sources JSON array
$sourcesJson = @($sources) | ConvertTo-Json -Compress -Depth 8 -AsArray
if ([string]::IsNullOrWhiteSpace($sourcesJson) -or $sourcesJson -eq 'null') {
    $sourcesJson = '[]'
}

$eventOutput = Invoke-WithFileLock -LockRoot $EventsFile -ScriptBlock {
    $existingEvents = @(Import-Events $EventsFile)

    $eventId = 'evt-{0:d4}' -f ($existingEvents.Count + 1)

    $eventFields = [System.Collections.Generic.List[string]]::new()
    $eventFields.Add((ConvertTo-JsonString 'event_id' $eventId))
    $eventFields.Add((ConvertTo-JsonString 'recorded_at' $recorded))
    $eventFields.Add((ConvertTo-JsonString 'fingerprint' $fingerprint))
    $eventFields.Add((ConvertTo-JsonString 'title' $Title))
    $eventFields.Add((ConvertTo-JsonString 'events_file' $repoRelativeEventsFile))
    $eventFields.Add((ConvertTo-JsonString 'repo_root' $RepoRoot))
    $eventFields.Add((ConvertTo-JsonString 'expected_outcome' $ExpectedOutcome))
    $eventFields.Add((ConvertTo-JsonString 'actual_outcome' $ActualOutcome))
    $eventFields.Add((ConvertTo-JsonString 'reading' $Reading))
    if (-not [string]::IsNullOrEmpty($Hindsight)) {
        $eventFields.Add((ConvertTo-JsonString 'hindsight' $Hindsight))
    }
    $eventFields.Add('"sources":' + $sourcesJson)
    $eventFields.Add((ConvertTo-JsonString 'impact' $Impact))
    $eventFields.Add('"tags":' + $tagsJson)
    $eventFields.Add('"aliases":' + $aliasesJson)

    $eventJson = '{' + ($eventFields -join ',') + '}'

    [System.IO.File]::AppendAllText($EventsFile, "$eventJson`n", [System.Text.UTF8Encoding]::new($false))
    return [pscustomobject]@{
        EventId    = $eventId
        EventCount = $existingEvents.Count + 1
    }
}

& "$PSScriptRoot/build-index.ps1" -EventsFile $EventsFile -IndexFile $IndexFile -RepoRoot $RepoRoot | Out-Null

Write-Output "FRICTION_EVENTS_FILE=$EventsFile"
Write-Output "FRICTION_INDEX_FILE=$IndexFile"
Write-Output "FRICTION_EVENT_ID=$($eventOutput.EventId)"
if (-not [string]::IsNullOrWhiteSpace($RepoRoot)) {
    Write-Output "FRICTION_REPO_ROOT=$RepoRoot"
}

# Show existing tags and aliases for reference
$existingTags = Get-AllTags $EventsFile
Write-Output ""
if (-not [string]::IsNullOrWhiteSpace($existingTags)) {
    Write-Output "All tags in this stream: $existingTags"
}
Write-Output "To add tags:    scripts/report-friction.ps1 -AddTags $($eventOutput.EventId) -AddTagsCsv `"tag1,tag2`""
Write-Output "To add aliases: scripts/report-friction.ps1 -AddAliases $($eventOutput.EventId) -AddAliasesCsv `"alias1,alias2`""
