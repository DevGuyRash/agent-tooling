param(
    [string]$EventsFile = $env:FRICTION_EVENTS_FILE,
    [string]$RepoRoot = $env:FRICTION_REPO_ROOT,
    [string[]]$ScanDirs = @(),
    [string]$Category = '',
    [string]$Surface = '',
    [string]$Mode = '',
    [string]$RunEffect = '',
    [string]$Fingerprint = '',
    [string]$Role = '',
    [string]$Tag = '',
    [string]$Text = '',
    [string]$ConfidenceMin = '',
    [string]$ConfidenceMax = '',
    [string]$GuidanceMin = '',
    [string]$GuidanceMax = '',
    [string]$ExitCode = '',
    [string]$ToolName = '',
    [string]$OwnerHint = '',
    [string]$ComponentHint = '',
    [switch]$Workaround,
    [string]$Date = '',
    [string]$DateFrom = '',
    [string]$DateTo = '',
    [string]$After = '',
    [string]$Before = '',
    [string]$SourceRef = '',
    [ValidateSet('jsonl', 'json', 'md')][string]$Format = 'jsonl',
    [string]$Output = '',
    [switch]$Compact,
    [switch]$SuggestTags,
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/query-friction.ps1 [-EventsFile PATH | -ScanDirs DIR [DIR...]] [filters]

Input:
  -EventsFile PATH          Single events file (default: auto-detected)
  -ScanDirs DIR [DIR...]    Recursively discover all events.jsonl files under
                            the given directories matching
                            */.local*/reports/friction/events.jsonl

Filters:
  -Category VALUE
  -Surface VALUE
  -Mode VALUE
  -RunEffect VALUE
  -Fingerprint VALUE
  -Role VALUE
  -Tag VALUE               Single tag filter; repeat support is not implemented
  -Text PATTERN            Case-insensitive substring search across narrative fields
  -ConfidenceMin N
  -ConfidenceMax N
  -GuidanceMin N
  -GuidanceMax N
  -ExitCode N
  -ToolName VALUE
  -OwnerHint VALUE
  -ComponentHint VALUE
  -Workaround              Only include events with workaround_used=true
  -Date YYYY-MM-DD
  -DateFrom YYYY-MM-DD
  -DateTo YYYY-MM-DD
  -After ISO-TIMESTAMP      Filter events with recorded_at > TIMESTAMP
  -Before ISO-TIMESTAMP     Filter events with recorded_at < TIMESTAMP
  -SourceRef PATH

Output:
  -Format jsonl|json|md
  -Output PATH
  -Compact                  Strip empty-string and null fields (json/jsonl only)
  -SuggestTags
  -Help
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

function Remove-EmptyFields {
    param($event)
    $toRemove = @($event.PSObject.Properties | Where-Object {
        $null -eq $_.Value -or ([string]$_.Value -eq '' -and $_.Value -isnot [System.Array] -and $_.Value -isnot [PSCustomObject])
    } | ForEach-Object { $_.Name })
    foreach ($name in $toRemove) {
        $event.PSObject.Properties.Remove($name)
    }
    return $event
}

function Import-MultipleEvents {
    param([string[]]$FilePaths)
    $allEvents = [System.Collections.Generic.List[object]]::new()
    foreach ($fp in $FilePaths) {
        if (-not (Test-Path -LiteralPath $fp)) { continue }
        foreach ($ev in @(Import-Events $fp)) {
            $null = $allEvents.Add($ev)
        }
    }
    # Sort by recorded_at
    return @($allEvents | Sort-Object { [string](Get-EventFieldValue -event $_ -Name 'recorded_at' -Default '') })
}

# Resolve input files
if ($ScanDirs.Count -gt 0) {
    $discovered = @()
    foreach ($dir in $ScanDirs) {
        $found = Get-ChildItem -Path $dir -Recurse -Filter 'events.jsonl' -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '[/\\]\.local[^/\\]*[/\\]reports[/\\]friction[/\\]events\.jsonl$' } |
            ForEach-Object { $_.FullName }
        $discovered += $found
    }
    if ($discovered.Count -eq 0) {
        throw "No events.jsonl files found under: $($ScanDirs -join ', ')"
    }
    $events = Import-MultipleEvents -FilePaths $discovered
} else {
    $paths = Resolve-FrictionPaths -RepoRoot $RepoRoot -EventsFile $EventsFile
    $EventsFile = $paths.EventsFile
    if (-not (Test-Path -LiteralPath $EventsFile)) {
        throw "Events file not found: $EventsFile"
    }
    $events = Import-MultipleEvents -FilePaths @($EventsFile)
}

# Helper: get tags from an event
function Get-EventTags {
    param($event)
    $tags = Get-EventFieldValue -event $event -Name 'tags'
    if ($null -eq $tags) { return @() }
    return @(@($tags) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | ForEach-Object { [string]$_ })
}

# Helper: check if an event matches a source ref
function Test-SourceRefMatch {
    param($event, [string]$ref)
    $sources = Get-EventFieldValue -event $event -Name 'sources'
    if ($null -ne $sources) {
        foreach ($s in @($sources)) {
            if ($null -ne $s -and [string]$s.ref -eq $ref) { return $true }
        }
    }
    return $false
}

if ($SuggestTags) {
    $tagsSet = [System.Collections.Generic.SortedSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($event in $events) {
        foreach ($tag in (Get-EventTags $event)) {
            $null = $tagsSet.Add($tag)
        }
    }
    $result = $tagsSet -join [Environment]::NewLine
    if (-not [string]::IsNullOrWhiteSpace($Output)) {
        [System.IO.File]::WriteAllText([System.IO.Path]::GetFullPath($Output), $result + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    }
    else {
        Write-Output $result
    }
    exit 0
}

$filtered = foreach ($event in $events) {
    $ts = [string](Get-EventFieldValue -event $event -Name 'recorded_at' -Default '')
    $eventDate = ''
    if (-not [string]::IsNullOrWhiteSpace($ts) -and $ts.Length -ge 10) {
        $eventDate = $ts.Substring(0, 10)
    }
    $categoryParts = Get-DerivedCategoryParts $event
    $confidenceValue = Get-NullableInt (Get-EventFieldValue -event $event -Name 'confidence')
    $guidanceValue = Get-NullableInt (Get-EventFieldValue -event $event -Name 'guidance_quality')
    $exitCodeValue = Get-NullableInt (Get-EventFieldValue -event $event -Name 'exit_code')

    if (-not [string]::IsNullOrWhiteSpace($Category) -and [string](Get-EventFieldValue -event $event -Name 'derived_category' -Default '') -ne $Category) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Surface) -and $categoryParts[0] -ne $Surface) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Mode) -and $categoryParts[1] -ne $Mode) { continue }
    if (-not [string]::IsNullOrWhiteSpace($RunEffect) -and $categoryParts[2] -ne $RunEffect) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Fingerprint) -and [string](Get-EventFieldValue -event $event -Name 'fingerprint' -Default '') -ne $Fingerprint) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Role) -and [string](Get-EventFieldValue -event $event -Name 'role' -Default '') -ne $Role) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Tag) -and (Get-EventTags $event) -notcontains $Tag) { continue }
    if (-not (Test-EventTextMatch -Event $event -Query $Text)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($ConfidenceMin) -and ($null -eq $confidenceValue -or $confidenceValue -lt [int]$ConfidenceMin)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($ConfidenceMax) -and ($null -eq $confidenceValue -or $confidenceValue -gt [int]$ConfidenceMax)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($GuidanceMin) -and ($null -eq $guidanceValue -or $guidanceValue -lt [int]$GuidanceMin)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($GuidanceMax) -and ($null -eq $guidanceValue -or $guidanceValue -gt [int]$GuidanceMax)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($ExitCode) -and ($null -eq $exitCodeValue -or $exitCodeValue -ne [int]$ExitCode)) { continue }
    if (-not [string]::IsNullOrWhiteSpace($ToolName) -and [string](Get-EventFieldValue -event $event -Name 'tool_name' -Default '') -ne $ToolName) { continue }
    if (-not [string]::IsNullOrWhiteSpace($OwnerHint) -and [string](Get-EventFieldValue -event $event -Name 'owner_hint' -Default '') -ne $OwnerHint) { continue }
    if (-not [string]::IsNullOrWhiteSpace($ComponentHint) -and [string](Get-EventFieldValue -event $event -Name 'component_hint' -Default '') -ne $ComponentHint) { continue }
    if ($Workaround -and -not [bool](Get-EventFieldValue -event $event -Name 'workaround_used' -Default $false)) { continue }
    if (-not (Test-EventTimestampFilters -RecordedAt $ts -Date $Date -DateFrom $DateFrom -DateTo $DateTo -After $After -Before $Before)) { continue }

    if (-not [string]::IsNullOrWhiteSpace($SourceRef)) {
        if (-not (Test-SourceRefMatch $event $SourceRef)) { continue }
    }

    $event
}

switch ($Format) {
    'jsonl' {
        $result = @($filtered | ForEach-Object {
            $ev = $_
            if ($Compact) { $ev = Remove-EmptyFields $ev }
            $ev | ConvertTo-Json -Compress -Depth 8
        }) -join [Environment]::NewLine
    }
    'json' {
        if ($Compact) {
            $compacted = @($filtered | ForEach-Object { Remove-EmptyFields $_ })
            $result = $compacted | ConvertTo-Json -Depth 8
        } else {
            $result = @($filtered) | ConvertTo-Json -Depth 8
        }
    }
    'md' {
        $lines = [System.Collections.Generic.List[string]]::new()
        $lines.Add('# Friction Query Results')
        $lines.Add('')
        $lines.Add("- Entries: $(@($filtered).Count)")
        $lines.Add('')
        foreach ($event in $filtered) {
            $lines.Add("## $([string](Get-EventFieldValue -event $event -Name 'event_id' -Default '')): $([string](Get-EventFieldValue -event $event -Name 'title' -Default ''))")
            $lines.Add('')
            $lines.Add("- Recorded: $([string](Get-EventFieldValue -event $event -Name 'recorded_at' -Default ''))")
            $lines.Add("- Category: $([string](Get-EventFieldValue -event $event -Name 'derived_category' -Default ''))")
            $lines.Add("- Fingerprint: $([string](Get-EventFieldValue -event $event -Name 'fingerprint' -Default ''))")
            $incidentIdVal = [string](Get-EventFieldValue -event $event -Name 'incident_id' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($incidentIdVal)) { $lines.Add("- Incident: $incidentIdVal") }
            $agentNameVal = [string](Get-EventFieldValue -event $event -Name 'agent_name' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($agentNameVal)) { $lines.Add("- Agent: $agentNameVal") }
            $roleVal = [string](Get-EventFieldValue -event $event -Name 'role' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($roleVal)) { $lines.Add("- Role: $roleVal") }
            $confVal = Get-NullableInt (Get-EventFieldValue -event $event -Name 'confidence')
            $guidVal = Get-NullableInt (Get-EventFieldValue -event $event -Name 'guidance_quality')
            if (($null -ne $confVal -and $confVal -ne 0) -or ($null -ne $guidVal -and $guidVal -ne 0)) {
                $confDisplay = if ($null -ne $confVal) { $confVal } else { 0 }
                $guidDisplay = if ($null -ne $guidVal) { $guidVal } else { 0 }
                $lines.Add("- Confidence: $confDisplay | Guidance: $guidDisplay")
            }
            $exitCodeVal = Get-NullableInt (Get-EventFieldValue -event $event -Name 'exit_code')
            if ($null -ne $exitCodeVal) { $lines.Add("- Exit code: $exitCodeVal") }
            $toolNameVal = [string](Get-EventFieldValue -event $event -Name 'tool_name' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($toolNameVal)) { $lines.Add("- Tool: $toolNameVal") }
            $commandVal = [string](Get-EventFieldValue -event $event -Name 'command' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($commandVal)) { $lines.Add("- Command: $commandVal") }
            $ownerHintVal = [string](Get-EventFieldValue -event $event -Name 'owner_hint' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($ownerHintVal)) { $lines.Add("- Owner: $ownerHintVal") }
            $componentHintVal = [string](Get-EventFieldValue -event $event -Name 'component_hint' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($componentHintVal)) { $lines.Add("- Component: $componentHintVal") }
            $workaroundUsedVal = [bool](Get-EventFieldValue -event $event -Name 'workaround_used' -Default $false)
            if ($workaroundUsedVal) { $lines.Add("- Workaround used: yes") }
            $workaroundNoteVal = [string](Get-EventFieldValue -event $event -Name 'workaround_note' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($workaroundNoteVal)) { $lines.Add("- Workaround: $workaroundNoteVal") }
            $retriesLostVal = Get-NullableInt (Get-EventFieldValue -event $event -Name 'retries_lost')
            if ($null -ne $retriesLostVal -and $retriesLostVal -gt 0) { $lines.Add("- Retries lost: $retriesLostVal") }
            $minutesLostVal = Get-NullableInt (Get-EventFieldValue -event $event -Name 'minutes_lost')
            if ($null -ne $minutesLostVal -and $minutesLostVal -gt 0) { $lines.Add("- Minutes lost: $minutesLostVal") }
            $superprojectRootVal = [string](Get-EventFieldValue -event $event -Name 'superproject_root' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($superprojectRootVal)) { $lines.Add("- Superproject: $superprojectRootVal") }
            $submodulePathVal = [string](Get-EventFieldValue -event $event -Name 'submodule_path' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($submodulePathVal)) { $lines.Add("- Submodule: $submodulePathVal") }
            $sources = Get-EventFieldValue -event $event -Name 'sources'
            if ($null -ne $sources -and $sources -is [System.Array] -and $sources.Count -gt 0) {
                $sourceEntries = @($sources | Where-Object { $null -ne $_ } | ForEach-Object {
                    $ref = [string]$_.ref
                    if ([string]::IsNullOrWhiteSpace($ref)) { return }
                    $lineNum = $null
                    $endLineNum = $null
                    if ($null -ne $_.line) { $lineNum = $_.line }
                    if ($null -ne $_.end_line) { $endLineNum = $_.end_line }
                    if ($null -ne $lineNum) {
                        $ref += ':' + $lineNum
                        if ($null -ne $endLineNum) { $ref += '-' + $endLineNum }
                    }
                    $ref
                } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
                if ($sourceEntries.Count -gt 0) {
                    $lines.Add("- Sources: $($sourceEntries -join ', ')")
                }
            }
            $tags = Get-EventTags $event
            if ($tags.Count -gt 0) {
                $lines.Add("- Tags: $($tags -join ', ')")
            }
            $stderrVal = [string](Get-EventFieldValue -event $event -Name 'stderr' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($stderrVal)) {
                $lines.Add("- Stderr: $($stderrVal.Split([Environment]::NewLine)[0])")
            }
            $stdoutExcerptVal = [string](Get-EventFieldValue -event $event -Name 'stdout_excerpt' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($stdoutExcerptVal)) {
                $lines.Add("- Stdout excerpt: $($stdoutExcerptVal.Split([Environment]::NewLine)[0])")
            }
            $instructionTextVal = [string](Get-EventFieldValue -event $event -Name 'instruction_text' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($instructionTextVal)) {
                $lines.Add('')
                $lines.Add("**Instruction:** $instructionTextVal")
            }
            $actionTakenVal = [string](Get-EventFieldValue -event $event -Name 'action_taken' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($actionTakenVal)) {
                $lines.Add('')
                $lines.Add("**Action taken:** $actionTakenVal")
            }
            $expectedOutcomeVal = [string](Get-EventFieldValue -event $event -Name 'expected_outcome' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($expectedOutcomeVal)) {
                $lines.Add('')
                $lines.Add("**Expected:** $expectedOutcomeVal")
            }
            $actualOutcomeVal = [string](Get-EventFieldValue -event $event -Name 'actual_outcome' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($actualOutcomeVal)) {
                $lines.Add('')
                $lines.Add("**Actual:** $actualOutcomeVal")
            }
            $readingVal = [string](Get-EventFieldValue -event $event -Name 'reading' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($readingVal)) {
                $lines.Add('')
                $lines.Add("**Reading:** $readingVal")
            }
            $hindsightVal = [string](Get-EventFieldValue -event $event -Name 'hindsight' -Default '')
            if (-not [string]::IsNullOrWhiteSpace($hindsightVal)) {
                $lines.Add('')
                $lines.Add("**Hindsight:** $hindsightVal")
            }
            $lines.Add('')
        }
        $result = $lines -join [Environment]::NewLine
    }
}

if (-not [string]::IsNullOrWhiteSpace($Output)) {
    [System.IO.File]::WriteAllText([System.IO.Path]::GetFullPath($Output), $result + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}
else {
    Write-Output $result
}
