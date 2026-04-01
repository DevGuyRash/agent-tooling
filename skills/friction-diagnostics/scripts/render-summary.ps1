param(
    [string]$EventsFile = '',
    [string]$After = '',
    [string]$Before = '',
    [string]$DateFrom = '',
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
  -MaxWidth N             Override terminal width detection (0 = unlimited)
  -NoFit                  Ignore terminal width; unlimited table width
  -MaxColWidth N          Max column content width before wrapping (default: 40)
  -Help                   Show this help
"@
}

function Get-TerminalWidth {
    if ($NoFit) { return 0 }
    if ($MaxWidth -gt 0) { return $MaxWidth }
    if ([Console]::IsOutputRedirected) { return 0 }
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

$resolvedMaxWidth = Get-TerminalWidth
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
        derived_category = [string]$event.derived_category
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

[Console]::WriteLine(("Friction Summary — {0} event(s) this session" -f $flattened.Count))

$flattenedJson = $flattened | ConvertTo-Json -Depth 8
if ($resolvedMaxWidth -gt 0) {
    $flattenedJson | & $renderScript -Json -Fields 'event_id,recorded_at,title,derived_category,tags,sources_flat' -Headers 'ID,Time,Title,Category,Tags,Sources' -MaxColWidth $MaxColWidth -MaxWidth $resolvedMaxWidth
} else {
    $flattenedJson | & $renderScript -Json -Fields 'event_id,recorded_at,title,derived_category,tags,sources_flat' -Headers 'ID,Time,Title,Category,Tags,Sources' -MaxColWidth $MaxColWidth
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

[Console]::WriteLine('')
[Console]::WriteLine("Events: $EventsFile")
[Console]::WriteLine(("Query:  {0}" -f ($footerParts -join ' ')))
