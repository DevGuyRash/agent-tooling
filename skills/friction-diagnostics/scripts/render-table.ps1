param(
    [switch]$Tsv,
    [switch]$Csv,
    [switch]$Jsonl,
    [switch]$Json,
    [switch]$Yaml,
    [string]$File = '',
    [string]$Fields = '',
    [string]$Headers = '',
    [int]$MaxColWidth = 0,
    [int]$MaxWidth = 0,
    [string]$ColWidths = '',
    [ValidateSet('drop-last-then-shrink', 'shrink')][string]$FitMode = 'drop-last-then-shrink',
    [int]$MinColWidth = 12,
    [int]$MinColumns = 1,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Hint {
    param([string]$Message)
    [Console]::Error.WriteLine("render-table.ps1: $Message")
}

function Emit-Line {
    param([string]$Line)
    Write-Output $Line
}

function Show-Help {
@"
render-table.ps1 - Unicode box-drawing table renderer

Usage:
  .\render-table.ps1 [-Tsv|-Csv|-Jsonl|-Json|-Yaml] [-File PATH]
  ... | .\render-table.ps1 [options]

Renders tabular data as a Unicode box-drawing table. Reads from -File or
pipeline input. Auto-detects input format when no mode switch is given.

Input formats:
  -Tsv             TSV - tab-separated values (first line = headers)
  -Csv             CSV - RFC 4180 via ConvertFrom-Csv
  -Jsonl           JSONL - one JSON object per line
  -Json            JSON - array of objects
  -Yaml            YAML - list of objects (requires python3 + PyYAML)

Options:
  -File PATH       Read input from PATH instead of pipeline
  -Fields A,B,...  Select and order fields (JSON/JSONL/YAML)
  -Headers A,B,... Display headers (overrides field names / first row)
  -MaxColWidth N   Max display columns per column before wrapping (0 = no limit)
  -MaxWidth N      Max total table width in display columns (0 = no limit)
  -ColWidths W,..  Per-column widths (e.g. "10,,30"); empty = auto
  -FitMode MODE    Width fit strategy: drop-last-then-shrink (default) or shrink
  -MinColWidth N   Minimum width to preserve for auto-sized columns before
                   columns start dropping (default: 12)
  -MinColumns N    Minimum number of leading columns to keep visible when
                   dropping columns to fit width (default: 1)
  -Help            Show this help
"@
}

function Get-Mode {
    $enabled = @()
    if ($Tsv) { $enabled += 'tsv' }
    if ($Csv) { $enabled += 'csv' }
    if ($Jsonl) { $enabled += 'jsonl' }
    if ($Json) { $enabled += 'json' }
    if ($Yaml) { $enabled += 'yaml' }
    if ($enabled.Count -gt 1) {
        throw 'render-table.ps1: choose only one input format switch'
    }
    if ($enabled.Count -eq 1) {
        return $enabled[0]
    }
    return 'auto'
}

function Get-InputText {
    if (-not [string]::IsNullOrWhiteSpace($File)) {
        if (-not (Test-Path -LiteralPath $File -PathType Leaf)) {
            throw "render-table.ps1: file not found: $File"
        }
        return [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $File).Path, [System.Text.UTF8Encoding]::new($false))
    }

    if ($script:PipelineTextLines.Count -gt 0) {
        return ($script:PipelineTextLines -join [Environment]::NewLine)
    }

    return ''
}

function Split-CommaList {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return @()
    }
    return @($Value.Split(',') | ForEach-Object { $_.Trim() })
}

function ConvertTo-CompactJson {
    param($Value)

    if ($null -eq $Value) { return '' }
    if ($Value -is [string]) { return [string]$Value }
    if ($Value -is [bool]) { return ([string]$Value).ToLowerInvariant() }
    if ($Value -is [ValueType]) { return [string]$Value }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        $items = @($Value)
        if ($items.Count -eq 0) { return '' }
        $scalarOnly = $true
        foreach ($item in $items) {
            if ($null -eq $item) { continue }
            if ($item -is [string] -or $item -is [ValueType]) { continue }
            $scalarOnly = $false
            break
        }
        if ($scalarOnly) {
            return (($items | ForEach-Object { if ($null -eq $_) { '' } else { [string]$_ } }) -join ',')
        }
    }
    return ($Value | ConvertTo-Json -Compress -Depth 8)
}

function Get-ObjectPropertyNames {
    param($Object)
    if ($null -eq $Object) { return @() }
    return @($Object.PSObject.Properties | ForEach-Object { $_.Name })
}

function ConvertFrom-YamlText {
    param([string]$Text)

    $python = Get-Command python3 -ErrorAction SilentlyContinue
    if ($null -eq $python) {
        throw 'render-table.ps1: -Yaml requires python3. Install Python 3 from https://python.org'
    }

    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        [System.IO.File]::WriteAllText($tmp, $Text, [System.Text.UTF8Encoding]::new($false))
        $json = & $python.Source -c @'
import json, sys
try:
    import yaml
except Exception:
    sys.stderr.write("missing-pyyaml")
    sys.exit(3)
with open(sys.argv[1], encoding="utf-8") as f:
    data = yaml.safe_load(f)
print(json.dumps(data, ensure_ascii=False))
'@ $tmp 2>&1
        if ($LASTEXITCODE -eq 3) {
            throw 'render-table.ps1: -Yaml requires PyYAML. Install: pip install pyyaml'
        }
        if ($LASTEXITCODE -ne 0) {
            throw "render-table.ps1: failed to parse YAML input: $json"
        }
        if ([string]::IsNullOrWhiteSpace([string]$json)) {
            return $null
        }
        return ($json | ConvertFrom-Json -Depth 16)
    }
    finally {
        Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
    }
}

function Get-DetectedMode {
    param([string]$Text)

    $firstLine = (($Text -split "`r?`n") | Select-Object -First 1).TrimStart()
    if ($firstLine.StartsWith('[')) {
        Write-Hint 'auto-detected JSON array input'
        return 'json'
    }
    if ($firstLine.StartsWith('{')) {
        Write-Hint 'auto-detected JSONL input'
        return 'jsonl'
    }
    if ($firstLine.StartsWith('---') -or $firstLine.StartsWith('- ')) {
        Write-Hint 'auto-detected YAML input'
        return 'yaml'
    }
    if ($firstLine.Contains("`t")) {
        return 'tsv'
    }
    if ($firstLine.Contains(',')) {
        return 'csv'
    }
    return 'tsv'
}

function Get-NormalizedData {
    param(
        [string]$Text,
        [string]$Mode
    )

    $headerOverride = @(Split-CommaList $Headers)
    $fieldList = @(Split-CommaList $Fields)

    switch ($Mode) {
        'tsv' {
            $lines = @($Text -split "`r?`n")
            if ($lines.Count -gt 0 -and $lines[-1] -eq '') {
                $lines = @($lines[0..($lines.Count - 2)])
            }
            if ($lines.Count -eq 0) {
                return [pscustomobject]@{ Headers = @(); Rows = @() }
            }
            $parsed = @($lines | ConvertFrom-Csv -Delimiter "`t")
            if ($parsed.Count -eq 0) {
                return [pscustomobject]@{ Headers = @(); Rows = @() }
            }
            $fieldsResolved = Get-ObjectPropertyNames $parsed[0]
            $displayHeaders = if ($headerOverride.Count -gt 0) { $headerOverride } else { $fieldsResolved }
            $rows = [System.Collections.Generic.List[object]]::new()
            foreach ($row in $parsed) {
                $rows.Add(@($fieldsResolved | ForEach-Object { ConvertTo-CompactJson $row.$_ }))
            }
            return [pscustomobject]@{ Headers = $displayHeaders; Rows = @($rows) }
        }
        'csv' {
            $parsed = @($Text | ConvertFrom-Csv)
            if ($parsed.Count -eq 0) {
                return [pscustomobject]@{ Headers = @(); Rows = @() }
            }
            $fieldsResolved = Get-ObjectPropertyNames $parsed[0]
            $displayHeaders = if ($headerOverride.Count -gt 0) { $headerOverride } else { $fieldsResolved }
            $rows = [System.Collections.Generic.List[object]]::new()
            foreach ($row in $parsed) {
                $rows.Add(@($fieldsResolved | ForEach-Object { ConvertTo-CompactJson $row.$_ }))
            }
            return [pscustomobject]@{ Headers = $displayHeaders; Rows = @($rows) }
        }
        'jsonl' {
            $objects = @()
            foreach ($line in ($Text -split "`r?`n")) {
                if ([string]::IsNullOrWhiteSpace($line)) { continue }
                $objects += ,($line | ConvertFrom-Json -Depth 16)
            }
            if ($objects.Count -eq 0) {
                return [pscustomobject]@{ Headers = @(); Rows = @() }
            }
            if ($fieldList.Count -eq 0) {
                $fieldList = Get-ObjectPropertyNames $objects[0]
                if ($fieldList.Count -gt 0) {
                    Write-Hint ("auto-discovered fields: {0}" -f ($fieldList -join ','))
                }
            }
            if ($fieldList.Count -eq 0) {
                return [pscustomobject]@{ Headers = @(); Rows = @() }
            }
            $displayHeaders = if ($headerOverride.Count -gt 0) { $headerOverride } else { $fieldList }
            $rows = [System.Collections.Generic.List[object]]::new()
            foreach ($obj in $objects) {
                $rows.Add(@($fieldList | ForEach-Object { ConvertTo-CompactJson $obj.$_ }))
            }
            return [pscustomobject]@{ Headers = $displayHeaders; Rows = @($rows) }
        }
        'json' {
            $parsed = $Text | ConvertFrom-Json -Depth 16
            $objects = @($parsed)
            if ($objects.Count -eq 0) {
                return [pscustomobject]@{ Headers = @(); Rows = @() }
            }
            if ($fieldList.Count -eq 0) {
                $fieldList = Get-ObjectPropertyNames $objects[0]
                if ($fieldList.Count -gt 0) {
                    Write-Hint ("auto-discovered fields: {0}" -f ($fieldList -join ','))
                }
            }
            if ($fieldList.Count -eq 0) {
                return [pscustomobject]@{ Headers = @(); Rows = @() }
            }
            $displayHeaders = if ($headerOverride.Count -gt 0) { $headerOverride } else { $fieldList }
            $rows = [System.Collections.Generic.List[object]]::new()
            foreach ($obj in $objects) {
                $rows.Add(@($fieldList | ForEach-Object { ConvertTo-CompactJson $obj.$_ }))
            }
            return [pscustomobject]@{ Headers = $displayHeaders; Rows = @($rows) }
        }
        'yaml' {
            $parsed = ConvertFrom-YamlText $Text
            $objects = @($parsed)
            if ($objects.Count -eq 1 -and $objects[0] -is [System.Collections.IEnumerable] -and $objects[0] -isnot [string]) {
                $objects = @($objects[0])
            }
            if ($objects.Count -eq 0) {
                return [pscustomobject]@{ Headers = @(); Rows = @() }
            }
            if ($fieldList.Count -eq 0) {
                $fieldList = Get-ObjectPropertyNames $objects[0]
                if ($fieldList.Count -gt 0) {
                    Write-Hint ("auto-discovered fields: {0}" -f ($fieldList -join ','))
                }
            }
            if ($fieldList.Count -eq 0) {
                return [pscustomobject]@{ Headers = @(); Rows = @() }
            }
            $displayHeaders = if ($headerOverride.Count -gt 0) { $headerOverride } else { $fieldList }
            $rows = [System.Collections.Generic.List[object]]::new()
            foreach ($obj in $objects) {
                $rows.Add(@($fieldList | ForEach-Object { ConvertTo-CompactJson $obj.$_ }))
            }
            return [pscustomobject]@{ Headers = $displayHeaders; Rows = @($rows) }
        }
        default {
            throw "render-table.ps1: unsupported mode: $Mode"
        }
    }
}

function Get-DisplayWidth {
    param([string]$Text)

    if ($null -eq $Text) { return 0 }
    $width = 0
    foreach ($char in $Text.ToCharArray()) {
        $code = [int][char]$char
        if (
            ($code -ge 0x1100 -and $code -le 0x115F) -or
            ($code -ge 0x2E80 -and $code -le 0xA4CF) -or
            ($code -ge 0xAC00 -and $code -le 0xD7A3) -or
            ($code -ge 0xF900 -and $code -le 0xFAFF) -or
            ($code -ge 0xFE10 -and $code -le 0xFE19) -or
            ($code -ge 0xFE30 -and $code -le 0xFE6F) -or
            ($code -ge 0xFF00 -and $code -le 0xFF60) -or
            ($code -ge 0xFFE0 -and $code -le 0xFFE6)
        ) {
            $width += 2
        }
        else {
            $width += 1
        }
    }
    return $width
}

function Split-DisplayText {
    param(
        [string]$Text,
        [int]$Width
    )

    if ($Width -le 0 -or (Get-DisplayWidth $Text) -le $Width) {
        return @($Text)
    }

    $words = @($Text.Split(' '))
    $lines = [System.Collections.Generic.List[string]]::new()
    $current = ''

    foreach ($word in $words) {
        if ($current.Length -eq 0) {
            if ((Get-DisplayWidth $word) -le $Width) {
                $current = $word
                continue
            }

            $remaining = $word
            while ((Get-DisplayWidth $remaining) -gt $Width) {
                $cut = ''
                foreach ($ch in $remaining.ToCharArray()) {
                    if ((Get-DisplayWidth ($cut + $ch)) -gt $Width) { break }
                    $cut += $ch
                }
                if ($cut.Length -eq 0) {
                    $cut = $remaining.Substring(0, 1)
                }
                $lines.Add($cut)
                $remaining = $remaining.Substring($cut.Length)
            }
            $current = $remaining
            continue
        }

        $candidate = "$current $word"
        if ((Get-DisplayWidth $candidate) -le $Width) {
            $current = $candidate
            continue
        }

        $lines.Add($current)
        $current = ''

        if ((Get-DisplayWidth $word) -le $Width) {
            $current = $word
            continue
        }

        $remaining = $word
        while ((Get-DisplayWidth $remaining) -gt $Width) {
            $cut = ''
            foreach ($ch in $remaining.ToCharArray()) {
                if ((Get-DisplayWidth ($cut + $ch)) -gt $Width) { break }
                $cut += $ch
            }
            if ($cut.Length -eq 0) {
                $cut = $remaining.Substring(0, 1)
            }
            $lines.Add($cut)
            $remaining = $remaining.Substring($cut.Length)
        }
        $current = $remaining
    }

    if ($current.Length -gt 0 -or $lines.Count -eq 0) {
        $lines.Add($current)
    }

    return @($lines)
}

function Pad-DisplayText {
    param(
        [string]$Text,
        [int]$Width
    )
    return $Text + (' ' * [Math]::Max(0, $Width - (Get-DisplayWidth $Text)))
}

function Get-Budget {
    param(
        [int]$VisibleCount,
        [int]$TableMaxWidth
    )

    $overhead = 1 + (3 * $VisibleCount)
    $budget = $TableMaxWidth - $overhead
    if ($budget -lt $VisibleCount) {
        $budget = $VisibleCount
    }
    return $budget
}

function Get-ColumnMetadata {
    param(
        [string[]]$HeadersResolved,
        [object[]]$RowsResolved
    )

    $columnCount = $HeadersResolved.Count
    $explicit = @{}
    if (-not [string]::IsNullOrWhiteSpace($ColWidths)) {
        $parts = $ColWidths.Split(',')
        for ($i = 0; $i -lt $parts.Count; $i++) {
            $trimmed = $parts[$i].Trim()
            if ($trimmed.Length -gt 0) {
                $explicit[$i] = [Math]::Max(1, [int]$trimmed)
            }
        }
    }

    $naturalWidths = New-Object int[] $columnCount
    for ($i = 0; $i -lt $columnCount; $i++) {
        if ($explicit.ContainsKey($i)) {
            $naturalWidths[$i] = [int]$explicit[$i]
            continue
        }

        $max = Get-DisplayWidth $HeadersResolved[$i]
        foreach ($row in $RowsResolved) {
            $rowCells = @($row)
            $cell = if ($i -lt $rowCells.Count) { [string]$rowCells[$i] } else { '' }
            $cellWidth = Get-DisplayWidth $cell
            if ($cellWidth -gt $max) {
                $max = $cellWidth
            }
        }
        if ($MaxColWidth -gt 0 -and $max -gt $MaxColWidth) {
            $max = $MaxColWidth
        }
        $naturalWidths[$i] = [Math]::Max(1, $max)
    }

    return [pscustomobject]@{
        NaturalWidths = $naturalWidths
        Explicit = $explicit
    }
}

function Invoke-ShrinkWidths {
    param(
        [int[]]$Visible,
        [int[]]$NaturalWidths,
        [hashtable]$ExplicitWidths,
        [int]$Budget,
        [int]$ColumnFloor,
        [switch]$Emergency
    )

    $widths = @{}
    $floors = @{}
    $effectiveFloor = [Math]::Max(1, $ColumnFloor)

    foreach ($idx in $Visible) {
        $widths[$idx] = [int]$NaturalWidths[$idx]
        if ($Emergency) {
            $floors[$idx] = 1
        }
        elseif ($ExplicitWidths.ContainsKey($idx)) {
            $floors[$idx] = [int]$NaturalWidths[$idx]
        }
        else {
            $floors[$idx] = [Math]::Min([int]$NaturalWidths[$idx], $effectiveFloor)
        }
    }

    $total = 0
    foreach ($idx in $Visible) {
        $total += [int]$widths[$idx]
    }

    while ($total -gt $Budget) {
        $candidates = @(
            $Visible |
                Where-Object { [int]$widths[$_] -gt [int]$floors[$_] } |
                Sort-Object -Property @{ Expression = { [int]$widths[$_] }; Descending = $true }, @{ Expression = { $_ }; Descending = $true }
        )
        if ($candidates.Count -eq 0) {
            return [pscustomobject]@{
                Widths = $widths
                Fits = $false
            }
        }

        foreach ($idx in $candidates) {
            if ($total -le $Budget) { break }
            if ([int]$widths[$idx] -gt [int]$floors[$idx]) {
                $widths[$idx] = [int]$widths[$idx] - 1
                $total--
            }
        }
    }

    return [pscustomobject]@{
        Widths = $widths
        Fits = $true
    }
}

function Get-FitLayout {
    param(
        [string[]]$HeadersResolved,
        [object[]]$RowsResolved
    )

    $columnCount = $HeadersResolved.Count
    $metadata = Get-ColumnMetadata -HeadersResolved $HeadersResolved -RowsResolved $RowsResolved
    $naturalWidths = [int[]]$metadata.NaturalWidths
    $explicitWidths = [hashtable]$metadata.Explicit

    $visible = [System.Collections.Generic.List[int]]::new()
    for ($i = 0; $i -lt $columnCount; $i++) {
        $visible.Add($i)
    }

    $dropped = [System.Collections.Generic.List[string]]::new()
    $widthMap = @{}
    foreach ($idx in $visible) {
        $widthMap[$idx] = [int]$naturalWidths[$idx]
    }

    if ($MaxWidth -gt 0 -and $visible.Count -gt 0) {
        if ($FitMode -eq 'shrink') {
            $budget = Get-Budget -VisibleCount $visible.Count -TableMaxWidth $MaxWidth
            $fitResult = Invoke-ShrinkWidths -Visible @($visible) -NaturalWidths $naturalWidths -ExplicitWidths $explicitWidths -Budget $budget -ColumnFloor $MinColWidth
            if (-not $fitResult.Fits) {
                $fitResult = Invoke-ShrinkWidths -Visible @($visible) -NaturalWidths $naturalWidths -ExplicitWidths $explicitWidths -Budget $budget -ColumnFloor 1 -Emergency
            }
            $widthMap = $fitResult.Widths
        }
        else {
            while ($true) {
                $budget = Get-Budget -VisibleCount $visible.Count -TableMaxWidth $MaxWidth
                $fitResult = Invoke-ShrinkWidths -Visible @($visible) -NaturalWidths $naturalWidths -ExplicitWidths $explicitWidths -Budget $budget -ColumnFloor $MinColWidth
                if ($fitResult.Fits) {
                    $widthMap = $fitResult.Widths
                    break
                }

                if ($visible.Count -gt [Math]::Max(1, $MinColumns)) {
                    $dropIndex = $visible[$visible.Count - 1]
                    $dropped.Add([string]$HeadersResolved[$dropIndex])
                    $visible.RemoveAt($visible.Count - 1)
                    continue
                }

                $fitResult = Invoke-ShrinkWidths -Visible @($visible) -NaturalWidths $naturalWidths -ExplicitWidths $explicitWidths -Budget $budget -ColumnFloor 1 -Emergency
                $widthMap = $fitResult.Widths
                break
            }
        }
    }

    $visibleHeaders = [System.Collections.Generic.List[string]]::new()
    $visibleWidths = [System.Collections.Generic.List[int]]::new()
    $visibleRows = [System.Collections.Generic.List[object]]::new()

    foreach ($idx in $visible) {
        $visibleHeaders.Add([string]$HeadersResolved[$idx])
        $visibleWidths.Add([int]$widthMap[$idx])
    }

    foreach ($row in $RowsResolved) {
        $rowCells = @($row)
        $newRow = [System.Collections.Generic.List[string]]::new()
        foreach ($idx in $visible) {
            $cell = if ($idx -lt $rowCells.Count) { [string]$rowCells[$idx] } else { '' }
            $newRow.Add($cell)
        }
        $visibleRows.Add(@($newRow))
    }

    return [pscustomobject]@{
        Headers = @($visibleHeaders)
        Widths = @($visibleWidths)
        Rows = @($visibleRows)
        Dropped = @($dropped)
    }
}

function Write-Border {
    param(
        [string]$Position,
        [int[]]$Widths
    )

    switch ($Position) {
        'top' { $left = '┌'; $fill = '─'; $mid = '┬'; $right = '┐' }
        'mid' { $left = '├'; $fill = '─'; $mid = '┼'; $right = '┤' }
        'bot' { $left = '└'; $fill = '─'; $mid = '┴'; $right = '┘' }
        default { throw "render-table.ps1: unknown border position: $Position" }
    }

    $parts = [System.Collections.Generic.List[string]]::new()
    $parts.Add($left)
    for ($i = 0; $i -lt $Widths.Length; $i++) {
        $parts.Add($fill * ($Widths[$i] + 2))
        if ($i -lt ($Widths.Length - 1)) {
            $parts.Add($mid)
        }
        else {
            $parts.Add($right)
        }
    }
    Emit-Line ($parts -join '')
}

function Write-RenderedRow {
    param(
        [string[]]$Row,
        [int[]]$Widths
    )

    $rowCells = @($Row)
    $wrapped = @()
    for ($i = 0; $i -lt $Widths.Length; $i++) {
        $cell = if ($i -lt $rowCells.Count) { [string]$rowCells[$i] } else { '' }
        $wrapped += ,(@(Split-DisplayText -Text $cell -Width $Widths[$i]))
    }

    $maxLines = 1
    foreach ($cellLines in $wrapped) {
        $cellSegments = @($cellLines)
        if ($cellSegments.Count -gt $maxLines) {
            $maxLines = $cellSegments.Count
        }
    }

    for ($lineIndex = 0; $lineIndex -lt $maxLines; $lineIndex++) {
        $parts = [System.Collections.Generic.List[string]]::new()
        $parts.Add('│')
        for ($i = 0; $i -lt $Widths.Length; $i++) {
            $wrappedSegments = @($wrapped[$i])
            $segment = if ($lineIndex -lt $wrappedSegments.Count) { [string]$wrappedSegments[$lineIndex] } else { '' }
            $parts.Add((' ' + (Pad-DisplayText -Text $segment -Width $Widths[$i]) + ' │'))
        }
        Emit-Line ($parts -join '')
    }
}

$script:PipelineTextLines = @($input | ForEach-Object { [string]$_ })

if ($Help) {
    Show-Help
    return
}

$mode = Get-Mode
$text = Get-InputText
if ([string]::IsNullOrEmpty($text)) {
    return
}

if ($mode -eq 'auto') {
    $mode = Get-DetectedMode $text
}

$normalized = Get-NormalizedData -Text $text -Mode $mode
$headersResolved = @($normalized.Headers)
$rowsResolved = @($normalized.Rows)
if ($headersResolved.Count -eq 0 -or $rowsResolved.Count -eq 0) {
    return
}

$layout = Get-FitLayout -HeadersResolved $headersResolved -RowsResolved $rowsResolved
$finalHeaders = @($layout.Headers)
$finalWidths = [int[]]@($layout.Widths)
$finalRows = @($layout.Rows)
$droppedHeaders = @($layout.Dropped)

if ($droppedHeaders.Count -gt 0) {
    Emit-Line ("Columns omitted to fit width: {0}" -f ($droppedHeaders -join ', '))
}

Write-Border -Position top -Widths $finalWidths
Write-RenderedRow -Row $finalHeaders -Widths $finalWidths
Write-Border -Position mid -Widths $finalWidths
for ($i = 0; $i -lt $finalRows.Count; $i++) {
    Write-RenderedRow -Row @($finalRows[$i]) -Widths $finalWidths
    if ($i -lt ($finalRows.Count - 1)) {
        Write-Border -Position mid -Widths $finalWidths
    }
}
Write-Border -Position bot -Widths $finalWidths
