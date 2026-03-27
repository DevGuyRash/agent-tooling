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
    [string]$AnchorPath = '',
    [ValidateSet('jsonl', 'json', 'md')][string]$Format = 'jsonl',
    [string]$Output = '',
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
  -AnchorPath PATH

Output:
  -Format jsonl|json|md
  -Output PATH
  -Help
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

$paths = Resolve-FrictionPaths -RepoRoot $RepoRoot -EventsFile $EventsFile
$EventsFile = $paths.EventsFile
if (-not (Test-Path -LiteralPath $EventsFile)) {
    throw "Events file not found: $EventsFile"
}

$events = Import-Events $EventsFile
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

    if (-not [string]::IsNullOrWhiteSpace($AnchorPath)) {
        $anchors = @($event.anchors)
        $matchedAnchor = $false
        foreach ($anchor in $anchors) {
            if ($null -ne $anchor -and [string]$anchor.path -eq $AnchorPath) {
                $matchedAnchor = $true
                break
            }
        }
        if (-not $matchedAnchor) { continue }
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
            $lines.Add("- Source: $([string]$event.instruction_source)")
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
