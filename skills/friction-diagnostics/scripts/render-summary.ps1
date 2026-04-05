param(
    [string]$EventsFile = '',
    [string]$After = '',
    [string]$Before = '',
    [string]$DateFrom = '',
    [ValidateSet('auto', 'table', 'markdown', 'list')]
    [string]$OutputFormat = '',
    [int]$MaxWidth = 0,
    [switch]$NoFit,
    [int]$MaxColWidth = 40,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Show-Help {
@"
render-summary.ps1 - Render a friction session summary table

Usage:
  .\render-summary.ps1 -EventsFile PATH [-After TIMESTAMP] [options]

Queries friction events, flattens source anchors, and renders a Unicode
box-drawing summary table. Produces a ready-to-paste block with header,
table, events file path, and a re-query command.

Required:
  -EventsFile PATH        Path to events.jsonl

Time filters:
  -After ISO-TIMESTAMP    Events after this timestamp
  -Before ISO-TIMESTAMP   Events before this timestamp
  -DateFrom YYYY-MM-DD    Events on or after this date

Display:
  -OutputFormat F         auto|table|markdown|list (default: auto)
  -MaxWidth N             Override terminal width detection (0 = unlimited)
  -NoFit                  Ignore terminal width; unlimited table width
  -MaxColWidth N          Max column content width before wrapping (default: 40)
  -Help                   Show this help
"@
}

function Get-TerminalWidth {
    if ($NoFit) { return 0 }
    if ($MaxWidth -gt 0) { return $MaxWidth }
    $columns = $env:COLUMNS
    if (-not [string]::IsNullOrWhiteSpace($columns)) {
        $parsed = 0
        if ([int]::TryParse($columns, [ref]$parsed) -and $parsed -gt 0) {
            return $parsed
        }
    }
    if ([Console]::IsOutputRedirected) { return 120 }
    try {
        return [Console]::WindowWidth
    }
    catch {
        return 120
    }
}

function Quote-ForPowerShell {
    param([string]$Value)
    return "'" + ($Value -replace "'", "''") + "'"
}

function Emit-Line {
    param([string]$Line)
    Write-Output $Line
}

function Escape-MarkdownCell {
    param([string]$Value)
    return (($Value -replace "`r", ' ' -replace "`n", ' ' -replace '\|', '\|').Trim())
}

function Get-SourceAnchor {
    param($Source)

    $typeProp = $Source.PSObject.Properties['type']
    $refProp = $Source.PSObject.Properties['ref']
    $lineProp = $Source.PSObject.Properties['line']
    $endLineProp = $Source.PSObject.Properties['end_line']

    $type = if ($null -ne $typeProp) { [string]$typeProp.Value } else { '' }
    $ref = if ($null -ne $refProp) { [string]$refProp.Value } else { '' }
    $anchor = "$type`:$ref"
    if ($null -ne $lineProp -and [string]$lineProp.Value -ne '') {
        $anchor += ":$([string]$lineProp.Value)"
        if ($null -ne $endLineProp -and [string]$endLineProp.Value -ne '') {
            $anchor += "-$([string]$endLineProp.Value)"
        }
    }
    return $anchor
}

if ($Help) {
    Show-Help
    exit 0
}

if ([string]::IsNullOrWhiteSpace($EventsFile)) {
    throw 'render-summary.ps1: -EventsFile is required'
}
if (-not (Test-Path -LiteralPath $EventsFile -PathType Leaf)) {
    throw "render-summary.ps1: events file not found: $EventsFile"
}

$queryScript = Join-Path $PSScriptRoot 'query-friction.ps1'
$renderScript = Join-Path $PSScriptRoot 'render-table.ps1'

if (-not (Test-Path -LiteralPath $queryScript -PathType Leaf)) {
    throw "render-summary.ps1: missing query-friction.ps1 at $queryScript"
}
if (-not (Test-Path -LiteralPath $renderScript -PathType Leaf)) {
    throw "render-summary.ps1: missing render-table.ps1 at $renderScript"
}

$resolvedOutputFormat = $OutputFormat
if ([string]::IsNullOrWhiteSpace($resolvedOutputFormat)) {
    $resolvedOutputFormat = [string]$env:FRICTION_SUMMARY_FORMAT
}
if ([string]::IsNullOrWhiteSpace($resolvedOutputFormat)) {
    $resolvedOutputFormat = 'auto'
}
if ($resolvedOutputFormat -notin @('auto', 'table', 'markdown', 'list')) {
    throw "render-summary.ps1: invalid -OutputFormat: $resolvedOutputFormat"
}
$renderMode = if ($resolvedOutputFormat -eq 'auto') { 'table' } else { $resolvedOutputFormat }
$resolvedMaxWidth = if ($renderMode -eq 'table') { Get-TerminalWidth } else { 0 }
$effectiveDateFrom = $DateFrom
if ([string]::IsNullOrWhiteSpace($After) -and [string]::IsNullOrWhiteSpace($Before) -and [string]::IsNullOrWhiteSpace($DateFrom)) {
    $effectiveDateFrom = [DateTime]::UtcNow.ToString('yyyy-MM-dd')
}

function Invoke-QueryScript {
    if (-not [string]::IsNullOrWhiteSpace($After)) {
        if (-not [string]::IsNullOrWhiteSpace($Before)) {
            if (-not [string]::IsNullOrWhiteSpace($effectiveDateFrom)) {
                return & $queryScript -EventsFile $EventsFile -After $After -Before $Before -DateFrom $effectiveDateFrom -Format json
            }
            return & $queryScript -EventsFile $EventsFile -After $After -Before $Before -Format json
        }
        if (-not [string]::IsNullOrWhiteSpace($effectiveDateFrom)) {
            return & $queryScript -EventsFile $EventsFile -After $After -DateFrom $effectiveDateFrom -Format json
        }
        return & $queryScript -EventsFile $EventsFile -After $After -Format json
    }

    if (-not [string]::IsNullOrWhiteSpace($Before)) {
        if (-not [string]::IsNullOrWhiteSpace($effectiveDateFrom)) {
            return & $queryScript -EventsFile $EventsFile -Before $Before -DateFrom $effectiveDateFrom -Format json
        }
        return & $queryScript -EventsFile $EventsFile -Before $Before -Format json
    }

    if (-not [string]::IsNullOrWhiteSpace($effectiveDateFrom)) {
        return & $queryScript -EventsFile $EventsFile -DateFrom $effectiveDateFrom -Format json
    }

    return & $queryScript -EventsFile $EventsFile -Format json
}

$queryJson = Invoke-QueryScript
$events = @()
if (-not [string]::IsNullOrWhiteSpace([string]$queryJson)) {
    $events = @($queryJson | ConvertFrom-Json -Depth 16)
}
if ($events.Count -eq 0) {
    exit 0
}

$flattened = foreach ($event in $events) {
    $sources = @()
    foreach ($source in @($event.sources)) {
        if ($null -eq $source) { continue }
        $sources += (Get-SourceAnchor $source)
    }
    $tags = if ($null -eq $event.tags) { @() } else { @($event.tags) }
    [pscustomobject]@{
        event_id = [string]$event.event_id
        recorded_at = [string]$event.recorded_at
        title = [string]$event.title
        impact = [string]$event.impact
        tags = $tags
        sources_flat = ($sources -join ' | ')
    }
}

$lastEventTime = [string]$flattened[-1].recorded_at
$requeryBefore = ''
if (-not [string]::IsNullOrWhiteSpace($lastEventTime)) {
    try {
        $dt = [DateTimeOffset]::Parse($lastEventTime, [System.Globalization.CultureInfo]::InvariantCulture)
        $requeryBefore = $dt.AddSeconds(1).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    }
    catch {
        $requeryBefore = $lastEventTime
    }
}

Emit-Line ("Friction Summary — {0} event(s) this session" -f $flattened.Count)

switch ($renderMode) {
    'table' {
        $flattenedJson = $flattened | ConvertTo-Json -Depth 8
        if ($resolvedMaxWidth -gt 0) {
            $flattenedJson | & $renderScript -Json -Fields 'event_id,recorded_at,title,impact,tags,sources_flat' -Headers 'ID,Time,Title,Impact,Tags,Sources' -MaxColWidth $MaxColWidth -FitMode 'drop-last-then-shrink' -MinColumns 3 -MaxWidth $resolvedMaxWidth
        } else {
            $flattenedJson | & $renderScript -Json -Fields 'event_id,recorded_at,title,impact,tags,sources_flat' -Headers 'ID,Time,Title,Impact,Tags,Sources' -MaxColWidth $MaxColWidth -FitMode 'drop-last-then-shrink' -MinColumns 3
        }
    }
    'markdown' {
        Emit-Line '| ID | Time | Title | Impact | Tags | Sources |'
        Emit-Line '| --- | --- | --- | --- | --- | --- |'
        foreach ($event in $flattened) {
            $cells = @(
                Escape-MarkdownCell ([string]$event.event_id),
                Escape-MarkdownCell ([string]$event.recorded_at),
                Escape-MarkdownCell ([string]$event.title),
                Escape-MarkdownCell ([string]$event.impact),
                Escape-MarkdownCell ((@($event.tags) | ForEach-Object { [string]$_ }) -join ', '),
                Escape-MarkdownCell ([string]$event.sources_flat)
            )
            Emit-Line ("| {0} |" -f ($cells -join ' | '))
        }
    }
    'list' {
        foreach ($event in $flattened) {
            Emit-Line ("[{0}]" -f [string]$event.event_id)
            Emit-Line ("Time: {0}" -f [string]$event.recorded_at)
            Emit-Line ("Title: {0}" -f [string]$event.title)
            Emit-Line ("Impact: {0}" -f [string]$event.impact)
            Emit-Line ("Tags: {0}" -f ((@($event.tags) | ForEach-Object { [string]$_ }) -join ', '))
            Emit-Line ("Sources: {0}" -f [string]$event.sources_flat)
            Emit-Line ''
        }
    }
}

$footerParts = [System.Collections.Generic.List[string]]::new()
$footerParts.Add('&')
$footerParts.Add((Quote-ForPowerShell $queryScript))
$footerParts.Add('-EventsFile')
$footerParts.Add((Quote-ForPowerShell $EventsFile))
if (-not [string]::IsNullOrWhiteSpace($After)) {
    $footerParts.Add('-After')
    $footerParts.Add((Quote-ForPowerShell $After))
}
if (-not [string]::IsNullOrWhiteSpace($effectiveDateFrom)) {
    $footerParts.Add('-DateFrom')
    $footerParts.Add((Quote-ForPowerShell $effectiveDateFrom))
}
if (-not [string]::IsNullOrWhiteSpace($requeryBefore)) {
    $footerParts.Add('-Before')
    $footerParts.Add((Quote-ForPowerShell $requeryBefore))
}
elseif (-not [string]::IsNullOrWhiteSpace($Before)) {
    $footerParts.Add('-Before')
    $footerParts.Add((Quote-ForPowerShell $Before))
}
$footerParts.Add('-Format')
$footerParts.Add('md')

Emit-Line ''
Emit-Line "Events: $EventsFile"
Emit-Line ("Query:  {0}" -f ($footerParts -join ' '))
