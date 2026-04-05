[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$EventsFile = $env:FRICTION_EVENTS_FILE,
    [string]$RepoRoot = $env:FRICTION_REPO_ROOT,
    [string[]]$ScanDirs = @(),
    [string]$Impact = '',
    [string]$Fingerprint = '',
    [string]$Tag = '',
    [string]$TagExact = '',
    [string]$Alias = '',
    [string]$AliasExact = '',
    [string]$Text = '',
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
  -Impact VALUE             blocked | degraded | noisy | continued
  -Fingerprint VALUE
  -Tag VALUE                Substring match across tags (e.g. "auth" matches "ssh-auth-sock")
  -TagExact VALUE           Exact tag match
  -Alias VALUE              Substring match across aliases
  -AliasExact VALUE         Exact alias match
  -Text PATTERN             Case-insensitive substring search across narrative fields
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

# Helper: get aliases from an event
function Get-EventAliases {
    param($event)
    $aliases = Get-EventFieldValue -event $event -Name 'aliases'
    if ($null -eq $aliases) { return @() }
    return @(@($aliases) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | ForEach-Object { [string]$_ })
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

    if (-not [string]::IsNullOrWhiteSpace($Impact) -and [string](Get-EventFieldValue -event $event -Name 'impact' -Default '') -ne $Impact) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Fingerprint) -and [string](Get-EventFieldValue -event $event -Name 'fingerprint' -Default '') -ne $Fingerprint) { continue }

    # Tag substring filter
    if (-not [string]::IsNullOrWhiteSpace($Tag)) {
        $needle = $Tag.ToLowerInvariant()
        $matched = $false
        foreach ($t in (Get-EventTags $event)) {
            if ($t.ToLowerInvariant().Contains($needle)) { $matched = $true; break }
        }
        if (-not $matched) { continue }
    }
    # Tag exact filter
    if (-not [string]::IsNullOrWhiteSpace($TagExact)) {
        $needle = $TagExact.ToLowerInvariant()
        $matched = $false
        foreach ($t in (Get-EventTags $event)) {
            if ($t.ToLowerInvariant() -eq $needle) { $matched = $true; break }
        }
        if (-not $matched) { continue }
    }
    # Alias substring filter
    if (-not [string]::IsNullOrWhiteSpace($Alias)) {
        $needle = $Alias.ToLowerInvariant()
        $matched = $false
        foreach ($a in (Get-EventAliases $event)) {
            if ($a.ToLowerInvariant().Contains($needle)) { $matched = $true; break }
        }
        if (-not $matched) { continue }
    }
    # Alias exact filter
    if (-not [string]::IsNullOrWhiteSpace($AliasExact)) {
        $needle = $AliasExact.ToLowerInvariant()
        $matched = $false
        foreach ($a in (Get-EventAliases $event)) {
            if ($a.ToLowerInvariant() -eq $needle) { $matched = $true; break }
        }
        if (-not $matched) { continue }
    }

    if (-not (Test-EventTextMatch -Event $event -Query $Text)) { continue }
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
        if (@($filtered).Count -eq 0) {
            $result = '[]'
        } elseif ($Compact) {
            $compacted = @($filtered | ForEach-Object { Remove-EmptyFields $_ })
            $result = $compacted | ConvertTo-Json -Depth 8 -AsArray
        } else {
            $result = @($filtered) | ConvertTo-Json -Depth 8 -AsArray
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
            $lines.Add("- Impact: $([string](Get-EventFieldValue -event $event -Name 'impact' -Default ''))")
            $lines.Add("- Fingerprint: $([string](Get-EventFieldValue -event $event -Name 'fingerprint' -Default ''))")
            $sources = @(Get-EventFieldValue -event $event -Name 'sources')
            if ($sources.Count -gt 0) {
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
            $tags = @(Get-EventTags $event)
            if ($tags.Count -gt 0) {
                $lines.Add("- Tags: $($tags -join ', ')")
            }
            $aliases = @(Get-EventAliases $event)
            if ($aliases.Count -gt 0) {
                $lines.Add("- Aliases: $($aliases -join ', ')")
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
