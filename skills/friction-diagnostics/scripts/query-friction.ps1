param(
    [string]$EventsFile = $env:FRICTION_EVENTS_FILE,
    [string]$RepoRoot = $env:FRICTION_REPO_ROOT,
    [string]$Category = '',
    [string]$Fingerprint = '',
    [string]$AgentKind = '',
    [string]$Role = '',
    [string]$Date = '',
    [string]$DateFrom = '',
    [string]$DateTo = '',
    [string]$SourceRef = '',
    [string]$AnchorPath = '',  # hidden backward-compat alias for SourceRef
    [ValidateSet('jsonl', 'json', 'md')][string]$Format = 'jsonl',
    [string]$Output = '',
    [switch]$SuggestTags,
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/query-friction.ps1 [-EventsFile PATH | -RepoRoot PATH] [filters]

Filters:
  -Category VALUE
  -Fingerprint VALUE
  -AgentKind VALUE
  -Role VALUE
  -Date YYYY-MM-DD
  -DateFrom YYYY-MM-DD
  -DateTo YYYY-MM-DD
  -SourceRef PATH

Output:
  -Format jsonl|json|md
  -Output PATH
  -SuggestTags
  -Help
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

# Resolve backward-compat alias: if AnchorPath provided but SourceRef not, use AnchorPath
if ([string]::IsNullOrWhiteSpace($SourceRef) -and -not [string]::IsNullOrWhiteSpace($AnchorPath)) {
    $SourceRef = $AnchorPath
}

$paths = Resolve-FrictionPaths -RepoRoot $RepoRoot -EventsFile $EventsFile
$EventsFile = $paths.EventsFile
if (-not (Test-Path -LiteralPath $EventsFile)) {
    throw "Events file not found: $EventsFile"
}

$events = Import-Events $EventsFile

# Helper: get tags from an event, handling v3 (array) and v2 (tags_csv string)
function Get-EventTags {
    param($event)
    $tagsV3 = $event.tags
    if ($null -ne $tagsV3 -and $tagsV3 -is [System.Array]) {
        return @($tagsV3 | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { [string]$_ })
    }
    $tagsCsv = [string]$event.tags_csv
    if (-not [string]::IsNullOrWhiteSpace($tagsCsv)) {
        return @($tagsCsv.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }
    return @()
}

# Helper: check if an event matches a source ref (v3 sources, v2 anchors, legacy instruction_source)
function Test-SourceRefMatch {
    param($event, [string]$ref)
    # v3: sources[].ref
    $sources = $event.sources
    if ($null -ne $sources -and $sources -is [System.Array]) {
        foreach ($s in $sources) {
            if ($null -ne $s -and [string]$s.ref -eq $ref) { return $true }
        }
    }
    # v2: anchors[].path
    $anchors = $event.anchors
    if ($null -ne $anchors -and $anchors -is [System.Array]) {
        foreach ($a in $anchors) {
            if ($null -ne $a -and [string]$a.path -eq $ref) { return $true }
        }
    }
    # legacy scalar field
    if ([string]$event.instruction_source -eq $ref) { return $true }
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
    $eventDate = ''
    if (-not [string]::IsNullOrWhiteSpace([string]$event.recorded_at) -and [string]$event.recorded_at.Length -ge 10) {
        $eventDate = [string]$event.recorded_at.Substring(0, 10)
    }

    if (-not [string]::IsNullOrWhiteSpace($Category) -and [string]$event.derived_category -ne $Category) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Fingerprint) -and [string]$event.fingerprint -ne $Fingerprint) { continue }
    if (-not [string]::IsNullOrWhiteSpace($AgentKind) -and [string]$event.agent_kind -ne $AgentKind) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Role) -and [string]$event.role -ne $Role) { continue }
    if (-not [string]::IsNullOrWhiteSpace($Date) -and $eventDate -ne $Date) { continue }
    if (-not [string]::IsNullOrWhiteSpace($DateFrom) -and -not [string]::IsNullOrWhiteSpace($eventDate) -and $eventDate -lt $DateFrom) { continue }
    if (-not [string]::IsNullOrWhiteSpace($DateTo) -and -not [string]::IsNullOrWhiteSpace($eventDate) -and $eventDate -gt $DateTo) { continue }

    if (-not [string]::IsNullOrWhiteSpace($SourceRef)) {
        if (-not (Test-SourceRefMatch $event $SourceRef)) { continue }
    }

    $event
}

switch ($Format) {
    'jsonl' {
        $result = @($filtered | ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 8 }) -join [Environment]::NewLine
    }
    'json' {
        $result = @($filtered) | ConvertTo-Json -Depth 8
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
            # Display sources (v3) or anchors (v2) if present
            $sources = $event.sources
            if ($null -ne $sources -and $sources -is [System.Array] -and $sources.Count -gt 0) {
                $refs = @($sources | Where-Object { $null -ne $_ } | ForEach-Object { [string]$_.ref } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
                if ($refs.Count -gt 0) {
                    $lines.Add("- Sources: $($refs -join ', ')")
                }
            }
            else {
                $anchors = $event.anchors
                if ($null -ne $anchors -and $anchors -is [System.Array] -and $anchors.Count -gt 0) {
                    $paths = @($anchors | Where-Object { $null -ne $_ } | ForEach-Object { [string]$_.path } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
                    if ($paths.Count -gt 0) {
                        $lines.Add("- Sources: $($paths -join ', ')")
                    }
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
