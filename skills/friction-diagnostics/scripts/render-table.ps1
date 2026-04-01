param(
    [Parameter(ValueFromPipeline = $true)]
    [string]$InputObject,
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
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:PipelineLines = [System.Collections.Generic.List[string]]::new()

function Write-Hint {
    param([string]$Message)
    [Console]::Error.WriteLine("render-table.ps1: $Message")
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

    if ($script:PipelineLines.Count -gt 0) {
        return ($script:PipelineLines -join [Environment]::NewLine)
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

    $headerOverride = Split-CommaList $Headers
    $fieldList = Split-CommaList $Fields

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
            $rows = foreach ($row in $parsed) {
                @($fieldsResolved | ForEach-Object { ConvertTo-CompactJson $row.$_ })
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
            $rows = foreach ($row in $parsed) {
                @($fieldsResolved | ForEach-Object { ConvertTo-CompactJson $row.$_ })
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
            $rows = foreach ($obj in $objects) {
                @($fieldList | ForEach-Object { ConvertTo-CompactJson $obj.$_ })
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
            $rows = foreach ($obj in $objects) {
                @($fieldList | ForEach-Object { ConvertTo-CompactJson $obj.$_ })
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
            $rows = foreach ($obj in $objects) {
                @($fieldList | ForEach-Object { ConvertTo-CompactJson $obj.$_ })
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

function Get-ColumnWidths {
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
                $explicit[$i] = [int]$trimmed
            }
        }
    }

    $widths = New-Object int[] $columnCount
    for ($i = 0; $i -lt $columnCount; $i++) {
        if ($explicit.ContainsKey($i)) {
            $widths[$i] = [Math]::Max(1, [int]$explicit[$i])
            continue
        }

        $max = Get-DisplayWidth $HeadersResolved[$i]
        foreach ($row in $RowsResolved) {
            $cell = if ($i -lt $row.Count) { [string]$row[$i] } else { '' }
            $cellWidth = Get-DisplayWidth $cell
            if ($cellWidth -gt $max) {
                $max = $cellWidth
            }
        }
        if ($MaxColWidth -gt 0 -and $max -gt $MaxColWidth) {
            $max = $MaxColWidth
        }
        $widths[$i] = [Math]::Max(1, $max)
    }

    if ($MaxWidth -gt 0) {
        $overhead = 1 + (3 * $columnCount)
        $budget = $MaxWidth - $overhead
        if ($budget -lt $columnCount) { $budget = $columnCount }
        $total = 0
        foreach ($w in $widths) { $total += $w }
        if ($total -gt $budget) {
            $ratio = $budget / [double]$total
            for ($i = 0; $i -lt $widths.Length; $i++) {
                if (-not $explicit.ContainsKey($i)) {
                    $widths[$i] = [Math]::Max(1, [int][Math]::Floor($widths[$i] * $ratio))
                }
            }
        }
    }

    return $widths
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
    [Console]::WriteLine(($parts -join ''))
}

function Write-RenderedRow {
    param(
        [string[]]$Row,
        [int[]]$Widths
    )

    $wrapped = @()
    for ($i = 0; $i -lt $Widths.Length; $i++) {
        $cell = if ($i -lt $Row.Count) { [string]$Row[$i] } else { '' }
        $wrapped += ,(Split-DisplayText -Text $cell -Width $Widths[$i])
    }

    $maxLines = 1
    foreach ($cellLines in $wrapped) {
        if ($cellLines.Count -gt $maxLines) {
            $maxLines = $cellLines.Count
        }
    }

    for ($lineIndex = 0; $lineIndex -lt $maxLines; $lineIndex++) {
        $parts = [System.Collections.Generic.List[string]]::new()
        $parts.Add('│')
        for ($i = 0; $i -lt $Widths.Length; $i++) {
            $segment = if ($lineIndex -lt $wrapped[$i].Count) { [string]$wrapped[$i][$lineIndex] } else { '' }
            $parts.Add((' ' + (Pad-DisplayText -Text $segment -Width $Widths[$i]) + ' │'))
        }
        [Console]::WriteLine(($parts -join ''))
    }
}

process {
    if ($null -ne $InputObject) {
        $script:PipelineLines.Add([string]$InputObject)
    }
}

end {
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

    $widths = Get-ColumnWidths -HeadersResolved $headersResolved -RowsResolved $rowsResolved
    Write-Border -Position top -Widths $widths
    Write-RenderedRow -Row $headersResolved -Widths $widths
    Write-Border -Position mid -Widths $widths
    for ($i = 0; $i -lt $rowsResolved.Count; $i++) {
        Write-RenderedRow -Row @($rowsResolved[$i]) -Widths $widths
        if ($i -lt ($rowsResolved.Count - 1)) {
            Write-Border -Position mid -Widths $widths
        }
    }
    Write-Border -Position bot -Widths $widths
}
