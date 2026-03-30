param(
    [string]$EventsFile = $env:FRICTION_EVENTS_FILE,
    [string]$RepoRoot = $env:FRICTION_REPO_ROOT,
    [string[]]$ScanDirs = @(),
    [string]$Category = '',
    [string]$Fingerprint = '',
    [string]$AgentKind = '',
    [string]$Role = '',
    [string]$Date = '',
    [string]$DateFrom = '',
    [string]$DateTo = '',
    [string]$After = '',
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
  -Fingerprint VALUE
  -AgentKind VALUE
  -Role VALUE
  -Date YYYY-MM-DD
  -DateFrom YYYY-MM-DD
  -DateTo YYYY-MM-DD
  -After ISO-TIMESTAMP      Filter events with recorded_at > TIMESTAMP
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
        $lines = [System.IO.File]::ReadAllLines($fp, [System.Text.UTF8Encoding]::new($false))
        foreach ($line in $lines) {
            $trimmed = $line.Trim()
            if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
            try {
                $ev = $trimmed | ConvertFrom-Json
                $null = $allEvents.Add($ev)
            } catch { }
        }
    }
    # Sort by recorded_at
    return @($allEvents | Sort-Object { [string]$_.recorded_at })
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
    $tags = $event.tags
    if ($null -ne $tags -and $tags -is [System.Array]) {
        return @($tags | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { [string]$_ })
    }
    return @()
}

# Helper: check if an event matches a source ref
function Test-SourceRefMatch {
    param($event, [string]$ref)
    $sources = $event.sources
    if ($null -ne $sources -and $sources -is [System.Array]) {
        foreach ($s in $sources) {
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
    $ts = [string]$event.recorded_at
    $eventDate = ''
    if (-not [string]::IsNullOrWhiteSpace($ts) -and $ts.Length -ge 10) {
        $eventDate = $ts.Substring(0, 10)
    }

    if (-not [string]::IsNullOrWhiteSpace($Category) -and [string]$event.derived_category -ne $Category) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Fingerprint) -and [string]$event.fingerprint -ne $Fingerprint) { continue }
    if (-not [string]::IsNullOrWhiteSpace($AgentKind) -and [string]$event.agent_kind -ne $AgentKind) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Role) -and [string]$event.role -ne $Role) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Date) -and $eventDate -ne $Date) { continue }
    if (-not [string]::IsNullOrWhiteSpace($DateFrom) -and -not [string]::IsNullOrWhiteSpace($eventDate) -and $eventDate -lt $DateFrom) { continue }
    if (-not [string]::IsNullOrWhiteSpace($DateTo) -and -not [string]::IsNullOrWhiteSpace($eventDate) -and $eventDate -gt $DateTo) { continue }
    if (-not [string]::IsNullOrWhiteSpace($After) -and -not [string]::IsNullOrWhiteSpace($ts) -and $ts -le $After) { continue }

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
            $lines.Add("## $([string]$event.event_id): $([string]$event.title)")
            $lines.Add('')
            $lines.Add("- Recorded: $([string]$event.recorded_at)")
            $lines.Add("- Category: $([string]$event.derived_category)")
            $lines.Add("- Fingerprint: $([string]$event.fingerprint)")
            if ([string]$event.provenance_source -eq 'explicit') {
                $lines.Add("- Agent: $([string]$event.agent_name)")
                $lines.Add("- Agent kind: $([string]$event.agent_kind)")
                $lines.Add("- Role: $([string]$event.role)")
            }
            $sources = $event.sources
            if ($null -ne $sources -and $sources -is [System.Array] -and $sources.Count -gt 0) {
                $refs = @($sources | Where-Object { $null -ne $_ } | ForEach-Object { [string]$_.ref } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
                if ($refs.Count -gt 0) {
                    $lines.Add("- Sources: $($refs -join ', ')")
                }
            }
            $tags = Get-EventTags $event
            if ($tags.Count -gt 0) {
                $lines.Add("- Tags: $($tags -join ', ')")
            }
            $lines.Add("- Actual outcome: $([string]$event.actual_outcome)")
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
