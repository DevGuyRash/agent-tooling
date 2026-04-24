#!/usr/bin/env pwsh
#Requires -Version 5.1

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'ExcelFoundry.Common.ps1')

function Show-ExcelWorkbookSyncUsage {
    @"
Usage:
  excel-foundry.ps1 <inspect|query|push|pull|roundtrip|smoke|refresh|bootstrap|plan|compare|sync> [options]
  excel-foundry.ps1 <workbook|manifest|sheet|name|table|query|connection|chart|pivot|slicer|timeline|model|measure|relationship|hierarchy|kpi|perspective|automation|cell|range> <action> [options]
  excel-foundry.ps1 [options]

Options:
  --manifest-path PATH | -ManifestPath PATH
  --workbook-path PATH | -WorkbookPath PATH
  --other-workbook-path PATH | -OtherWorkbookPath PATH
  --output-dir PATH    | -OutputDir PATH
  --query-name NAME    | -QueryName NAME
  --surface LIST       | -Surface LIST
  --backend NAME       | -Backend NAME
  --mode NAME          | -Mode NAME
  --sheet NAME         | -Sheet NAME
  --table NAME         | -Table NAME
  --name NAME          | -Name NAME
  --name-prefix NAME   | -NamePrefix NAME
  --connection NAME    | -Connection NAME
  --chart NAME         | -Chart NAME
  --pivot NAME         | -Pivot NAME
  --slicer NAME        | -Slicer NAME
  --timeline NAME      | -Timeline NAME
  --automation-type NAME | -AutomationType NAME
  --address A1         | -Address A1
  --range-ref A1:B2    | -RangeRef A1:B2
  --value-json JSON    | -ValueJson JSON
  --values-json JSON   | -ValuesJson JSON
  --target-path PATH   | -TargetPath PATH
  --target-format EXT  | -TargetFormat EXT
  --spec-json JSON     | -SpecJson JSON
  --spec-file PATH     | -SpecFile PATH
  --refers-to FORMULA  | -RefersTo FORMULA
  --hidden             | -Hidden
  --state-root PATH    | -StateRoot PATH
  --apply              | -Apply
  --destructive        | -Destructive
  --deep               | -Deep
  --visible            | -Visible
  --help | -help | -h | -? 

Notes:
  When the subcommand is omitted, the default is inspect.
  bootstrap writes a starter manifest plus workbook_structure artifacts.
  GNU-style and native PowerShell flags are both accepted.
"@
}

function Test-IsHelpToken {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Token
    )

    return $Token -in @('help', '--help', '-help', '-h', '-?')
}

function Throw-CliError {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    throw $Message
}

function Parse-ExcelWorkbookSyncArgs {
    param(
        [string[]]$Tokens = @()
    )

    $result = [ordered]@{
        Command = 'inspect'
        ManifestPath = $null
        WorkbookPath = $null
        OtherWorkbookPath = $null
        OutputDir = $null
        QueryName = @()
        Sheet = @()
        Table = @()
        Name = @()
        NamePrefix = @()
        Connection = @()
        Chart = @()
        Pivot = @()
        Slicer = @()
        Timeline = @()
        Address = $null
        RangeRef = $null
        ValueJson = $null
        ValuesJson = $null
        TargetPath = $null
        TargetFormat = $null
        SpecJson = $null
        SpecFile = $null
        RefersTo = $null
        AutomationType = $null
        Hidden = $false
        Surface = @()
        Backend = 'auto'
        Mode = 'push'
        StateRoot = $null
        Apply = $false
        Destructive = $false
        Deep = $false
        Visible = $false
        ShowHelp = $false
    }
    $surfaceExplicit = $false

    $validCommands = @('inspect', 'query', 'push', 'pull', 'roundtrip', 'smoke', 'refresh', 'bootstrap', 'plan', 'compare', 'sync', 'workbook-inspect', 'workbook-capabilities', 'workbook-create', 'workbook-diff', 'workbook-save-as', 'workbook-convert', 'workbook-repair', 'workbook-compatibility', 'workbook-document-inspect', 'workbook-links', 'workbook-break-links', 'workbook-repoint-links', 'workbook-safe-export', 'manifest-validate', 'manifest-doctor', 'manifest-migrate', 'sheet-list', 'sheet-create', 'sheet-hide', 'sheet-unhide', 'sheet-very-hide', 'sheet-reorder', 'sheet-delete', 'name-list', 'name-set', 'name-delete', 'dimension-get', 'hyperlink-list', 'comment-list', 'print-get', 'formula-list', 'validation-list', 'protection-get', 'table-list', 'table-read', 'table-get', 'table-create', 'table-update', 'table-delete', 'query-list', 'query-get', 'query-set', 'query-delete', 'query-refresh', 'connection-list', 'connection-get', 'chart-list', 'chart-get', 'chart-create', 'chart-update', 'chart-delete', 'pivot-list', 'pivot-get', 'pivot-create', 'pivot-update', 'pivot-delete', 'pivot-refresh', 'slicer-list', 'slicer-get', 'slicer-create', 'slicer-update', 'slicer-delete', 'slicer-clear', 'slicer-set-filter', 'timeline-list', 'timeline-get', 'timeline-create', 'timeline-update', 'timeline-delete', 'timeline-clear', 'timeline-set-range', 'model-inspect', 'measure-list', 'measure-get', 'measure-set', 'measure-delete', 'relationship-list', 'relationship-get', 'relationship-set', 'relationship-delete', 'hierarchy-list', 'hierarchy-get', 'hierarchy-set', 'hierarchy-delete', 'kpi-list', 'kpi-get', 'kpi-set', 'kpi-delete', 'perspective-list', 'perspective-get', 'perspective-set', 'perspective-delete', 'automation-inspect', 'automation-generate', 'automation-run', 'cell-get', 'cell-set', 'range-get', 'range-set')
    $resourceCommands = @{
        'workbook' = @('inspect', 'capabilities', 'create', 'diff', 'save-as', 'convert', 'repair', 'compatibility', 'document-inspect', 'links', 'break-links', 'repoint-links', 'safe-export')
        'manifest' = @('validate', 'doctor', 'migrate')
        'sheet' = @('list', 'create', 'hide', 'unhide', 'very-hide', 'reorder', 'delete')
        'name' = @('list', 'set', 'delete')
        'table' = @('list', 'read', 'get', 'create', 'update', 'delete')
        'query' = @('list', 'get', 'set', 'delete', 'refresh')
        'connection' = @('list', 'get')
        'chart' = @('list', 'get', 'create', 'update', 'delete')
        'pivot' = @('list', 'get', 'create', 'update', 'delete', 'refresh')
        'slicer' = @('list', 'get', 'create', 'update', 'delete', 'clear', 'set-filter')
        'timeline' = @('list', 'get', 'create', 'update', 'delete', 'clear', 'set-range')
        'model' = @('inspect')
        'measure' = @('list', 'get', 'set', 'delete')
        'relationship' = @('list', 'get', 'set', 'delete')
        'hierarchy' = @('list', 'get', 'set', 'delete')
        'kpi' = @('list', 'get', 'set', 'delete')
        'perspective' = @('list', 'get', 'set', 'delete')
        'automation' = @('inspect', 'generate', 'run')
        'cell' = @('get', 'set')
        'range' = @('get', 'set')
    }
    $index = 0
    if ($Tokens.Count -gt 0) {
        $first = [string]$Tokens[0]
        if (Test-IsHelpToken -Token $first) {
            $result.ShowHelp = $true
            return [pscustomobject]$result
        }

        if ($first -eq 'query' -and $Tokens.Count -ge 2 -and [string]$Tokens[1] -eq 'list') {
            $result.Command = 'query-list'
            $index = 2
        }
        elseif ($resourceCommands.ContainsKey($first) -and $Tokens.Count -ge 2 -and -not ([string]$Tokens[1]).StartsWith('-')) {
            if ($Tokens.Count -lt 2) {
                Throw-CliError -Message ("error: missing action for resource command: {0}" -f $first)
            }
            $action = [string]$Tokens[1]
            if ($action -notin $resourceCommands[$first]) {
                Throw-CliError -Message ("error: unknown action '{0}' for resource '{1}'" -f $action, $first)
            }
            $result.Command = "$first-$action"
            $index = 2
        }
        elseif ($first -in $validCommands) {
            $result.Command = $first
            $index = 1
            if ($Tokens.Count -gt $index -and (Test-IsHelpToken -Token ([string]$Tokens[$index]))) {
                $result.ShowHelp = $true
                return [pscustomobject]$result
            }
        }
        elseif (-not $first.StartsWith('-')) {
            Throw-CliError -Message ("error: unknown subcommand: {0}`nhint: use one of inspect, query, push, pull, roundtrip, smoke, refresh, bootstrap, plan, compare, sync, or resource commands like 'sheet list'" -f $first)
        }
    }

    while ($index -lt $Tokens.Count) {
        $token = [string]$Tokens[$index]
        $index++

        if (Test-IsHelpToken -Token $token) {
            $result.ShowHelp = $true
            return [pscustomobject]$result
        }

        switch ($token) {
            { $_ -in @('--manifest-path', '-ManifestPath', '-manifest-path') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.ManifestPath = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--workbook-path', '-WorkbookPath', '-workbook-path') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.WorkbookPath = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--other-workbook-path', '-OtherWorkbookPath', '-other-workbook-path') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.OtherWorkbookPath = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--output-dir', '-OutputDir', '-output-dir') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.OutputDir = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--query-name', '-QueryName', '-query-name') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.QueryName += [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--sheet', '-Sheet', '-sheet') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Sheet += [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--table', '-Table', '-table') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Table += [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--name', '-Name', '-name') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Name += [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--name-prefix', '-NamePrefix', '-name-prefix') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.NamePrefix += [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--connection', '-Connection', '-connection') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Connection += [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--chart', '-Chart', '-chart') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Chart += [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--pivot', '-Pivot', '-pivot') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Pivot += [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--slicer', '-Slicer', '-slicer') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Slicer += [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--timeline', '-Timeline', '-timeline') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Timeline += [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--address', '-Address', '-address') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Address = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--range-ref', '-RangeRef', '-range-ref') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.RangeRef = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--value-json', '-ValueJson', '-value-json') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.ValueJson = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--values-json', '-ValuesJson', '-values-json') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.ValuesJson = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--target-path', '-TargetPath', '-target-path') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.TargetPath = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--target-format', '-TargetFormat', '-target-format') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.TargetFormat = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--spec-json', '-SpecJson', '-spec-json') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.SpecJson = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--spec-file', '-SpecFile', '-spec-file') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.SpecFile = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--refers-to', '-RefersTo', '-refers-to') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.RefersTo = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--automation-type', '-AutomationType', '-automation-type') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.AutomationType = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--surface', '-Surface', '-surface') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Surface += [string]$Tokens[$index]
                $surfaceExplicit = $true
                $index++
                continue
            }
            { $_ -in @('--backend', '-Backend', '-backend') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Backend = [string]$Tokens[$index].Trim().ToLowerInvariant()
                $index++
                continue
            }
            { $_ -in @('--mode', '-Mode', '-mode') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Mode = [string]$Tokens[$index].Trim().ToLowerInvariant()
                $index++
                continue
            }
            { $_ -in @('--state-root', '-StateRoot', '-state-root') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.StateRoot = [string]$Tokens[$index]
                $index++
                continue
            }
            { $_ -in @('--apply', '-Apply', '-apply') } {
                $result.Apply = $true
                continue
            }
            { $_ -in @('--destructive', '-Destructive', '-destructive') } {
                $result.Destructive = $true
                continue
            }
            { $_ -in @('--deep', '-Deep', '-deep') } {
                $result.Deep = $true
                continue
            }
            { $_ -in @('--hidden', '-Hidden', '-hidden') } {
                $result.Hidden = $true
                continue
            }
            { $_ -in @('--visible', '-Visible', '-visible') } {
                $result.Visible = $true
                continue
            }
            default {
                Throw-CliError -Message ("error: unknown flag or argument: {0}`nhint: run 'excel-foundry.ps1 --help' for the supported CLI surface" -f $token)
            }
        }
    }

    if (-not $surfaceExplicit) {
        $result.Surface += switch ($result.Command) {
            'inspect' { '' }
            'plan' { 'all-supported' }
            'compare' { 'all-supported' }
            'sync' { 'all-supported' }
            'workbook-inspect' { '' }
            'workbook-capabilities' { '' }
            'workbook-create' { '' }
            'workbook-diff' { 'workbook,sheets,tables,names,formulas,data-validation,protection,cf,pivots,hyperlinks,comments,print,dimensions,pq,connections,model' }
            'workbook-save-as' { '' }
            'workbook-convert' { '' }
            'workbook-repair' { '' }
            'workbook-compatibility' { '' }
            'workbook-document-inspect' { '' }
            'workbook-links' { '' }
            'workbook-break-links' { '' }
            'workbook-repoint-links' { '' }
            'workbook-safe-export' { '' }
            'manifest-validate' { '' }
            'manifest-doctor' { '' }
            'manifest-migrate' { '' }
            'sheet-list' { 'sheets' }
            'sheet-create' { 'sheets' }
            'sheet-hide' { 'sheets' }
            'sheet-unhide' { 'sheets' }
            'sheet-very-hide' { 'sheets' }
            'sheet-reorder' { 'sheets' }
            'sheet-delete' { 'sheets' }
            'table-list' { 'tables' }
            'table-read' { 'tables' }
            'table-get' { 'tables' }
            'name-list' { 'names' }
            'query-list' { 'pq,connections,model' }
            'connection-list' { 'connections' }
            'chart-list' { 'charts' }
            'chart-get' { 'charts' }
            'chart-create' { 'charts' }
            'chart-update' { 'charts' }
            'chart-delete' { 'charts' }
            'pivot-list' { 'pivots' }
            'pivot-get' { 'pivots' }
            'pivot-create' { 'pivots' }
            'pivot-update' { 'pivots' }
            'pivot-delete' { 'pivots' }
            'pivot-refresh' { 'pivots' }
            'slicer-list' { 'slicers' }
            'slicer-get' { 'slicers' }
            'slicer-create' { 'slicers' }
            'slicer-update' { 'slicers' }
            'slicer-delete' { 'slicers' }
            'slicer-clear' { 'slicers' }
            'slicer-set-filter' { 'slicers' }
            'timeline-list' { 'timelines' }
            'timeline-get' { 'timelines' }
            'timeline-create' { 'timelines' }
            'timeline-update' { 'timelines' }
            'timeline-delete' { 'timelines' }
            'timeline-clear' { 'timelines' }
            'timeline-set-range' { 'timelines' }
            'model-inspect' { 'model' }
            'measure-list' { 'model' }
            'measure-get' { 'model' }
            'measure-set' { 'model' }
            'measure-delete' { 'model' }
            'relationship-list' { 'model' }
            'relationship-get' { 'model' }
            'relationship-set' { 'model' }
            'relationship-delete' { 'model' }
            'hierarchy-list' { 'model' }
            'hierarchy-get' { 'model' }
            'hierarchy-set' { 'model' }
            'hierarchy-delete' { 'model' }
            'kpi-list' { 'model' }
            'kpi-get' { 'model' }
            'kpi-set' { 'model' }
            'kpi-delete' { 'model' }
            'perspective-list' { 'model' }
            'perspective-get' { 'model' }
            'perspective-set' { 'model' }
            'perspective-delete' { 'model' }
            'automation-inspect' { '' }
            'automation-generate' { '' }
            'automation-run' { '' }
            default { 'vba,tables,names,cf,project,references,pq,connections,model' }
        }
    }

    return [pscustomobject]$result
}

try {
    $parsed = Parse-ExcelWorkbookSyncArgs -Tokens @($CliArgs)
    if ($parsed.ShowHelp) {
        Show-ExcelWorkbookSyncUsage
        exit 0
    }

    $surfaceNames = @(Get-NormalizedSurfaceNames -Surface $parsed.Surface)
    if ($parsed.Command -in @('workbook-inspect', 'workbook-capabilities', 'workbook-create', 'workbook-diff', 'manifest-validate', 'manifest-doctor', 'manifest-migrate', 'sheet-list', 'sheet-create', 'sheet-hide', 'sheet-unhide', 'sheet-very-hide', 'sheet-reorder', 'sheet-delete', 'name-list', 'name-set', 'name-delete', 'dimension-get', 'hyperlink-list', 'comment-list', 'print-get', 'formula-list', 'validation-list', 'protection-get', 'table-list', 'table-read', 'query-list', 'cell-get', 'cell-set', 'range-get', 'range-set')) {
        if ($parsed.Command -in @('workbook-inspect', 'workbook-capabilities', 'workbook-create', 'workbook-diff', 'sheet-list', 'sheet-create', 'sheet-hide', 'sheet-unhide', 'sheet-very-hide', 'sheet-reorder', 'sheet-delete', 'name-list', 'name-set', 'name-delete', 'dimension-get', 'hyperlink-list', 'comment-list', 'print-get', 'formula-list', 'validation-list', 'protection-get', 'table-list', 'table-read', 'query-list', 'cell-get', 'cell-set', 'range-get', 'range-set') -and [string]::IsNullOrWhiteSpace($parsed.WorkbookPath)) {
            Throw-CliError -Message "error: direct workbook commands require --workbook-path"
        }
        if ($parsed.Command -eq 'workbook-diff' -and [string]::IsNullOrWhiteSpace($parsed.OtherWorkbookPath)) {
            Throw-CliError -Message "error: workbook diff requires --other-workbook-path"
        }
        if ($parsed.Command -like 'manifest-*' -and [string]::IsNullOrWhiteSpace($parsed.ManifestPath)) {
            Throw-CliError -Message "error: manifest commands require --manifest-path"
        }
        $packageSurface = @()
        if ($parsed.Command -in @('workbook-inspect', 'workbook-diff')) {
            $packageSurface = $surfaceNames
        }
        $payload = Invoke-PackageWorkbookHelper `
            -Command $parsed.Command `
            -WorkbookPath $parsed.WorkbookPath `
            -OtherWorkbookPath $parsed.OtherWorkbookPath `
            -ManifestPath $parsed.ManifestPath `
            -Surface $packageSurface `
            -Sheet $parsed.Sheet `
            -Table $parsed.Table `
            -Name $parsed.Name `
            -QueryName $parsed.QueryName `
            -Address $parsed.Address `
            -RangeRef $parsed.RangeRef `
            -ValueJson $parsed.ValueJson `
            -ValuesJson $parsed.ValuesJson `
            -SpecJson $parsed.SpecJson `
            -SpecFile $parsed.SpecFile `
            -RefersTo $parsed.RefersTo `
            -Hidden:$parsed.Hidden `
            -Apply:$parsed.Apply `
            -Destructive:$parsed.Destructive `
            -Deep:$parsed.Deep
        $payload | ConvertTo-Json -Depth 100
        exit 0
    }
    if ($parsed.Command -in @('workbook-save-as', 'workbook-convert', 'workbook-repair', 'workbook-compatibility', 'workbook-document-inspect', 'workbook-links', 'workbook-break-links', 'workbook-repoint-links', 'workbook-safe-export', 'table-get', 'table-create', 'table-update', 'table-delete', 'query-get', 'query-set', 'query-delete', 'query-refresh', 'connection-list', 'connection-get', 'chart-list', 'chart-get', 'chart-create', 'chart-update', 'chart-delete', 'pivot-list', 'pivot-get', 'pivot-create', 'pivot-update', 'pivot-delete', 'pivot-refresh', 'slicer-list', 'slicer-get', 'slicer-create', 'slicer-update', 'slicer-delete', 'slicer-clear', 'slicer-set-filter', 'timeline-list', 'timeline-get', 'timeline-create', 'timeline-update', 'timeline-delete', 'timeline-clear', 'timeline-set-range', 'model-inspect', 'measure-list', 'measure-get', 'measure-set', 'measure-delete', 'relationship-list', 'relationship-get', 'relationship-set', 'relationship-delete', 'hierarchy-list', 'hierarchy-get', 'hierarchy-set', 'hierarchy-delete', 'kpi-list', 'kpi-get', 'kpi-set', 'kpi-delete', 'perspective-list', 'perspective-get', 'perspective-set', 'perspective-delete')) {
        if ([string]::IsNullOrWhiteSpace($parsed.WorkbookPath)) {
            Throw-CliError -Message "error: direct workbook commands require --workbook-path"
        }
        $directMode = if ($parsed.Command -eq 'workbook-repair' -and $parsed.Mode -in @('repair', 'extract')) { $parsed.Mode } else { 'repair' }
        $payload = Invoke-DirectExcelWorkbookCommand `
            -Command $parsed.Command `
            -WorkbookPath $parsed.WorkbookPath `
            -Table $parsed.Table `
            -QueryName $parsed.QueryName `
            -Connection $parsed.Connection `
            -Chart $parsed.Chart `
            -Pivot $parsed.Pivot `
            -Slicer $parsed.Slicer `
            -Timeline $parsed.Timeline `
            -Name $parsed.Name `
            -TargetPath $parsed.TargetPath `
            -TargetFormat $parsed.TargetFormat `
            -SpecJson $parsed.SpecJson `
            -SpecFile $parsed.SpecFile `
            -Mode $directMode `
            -Apply:$parsed.Apply `
            -Visible:$parsed.Visible
        $payload | ConvertTo-Json -Depth 100
        exit 0
    }
    if ($parsed.Command -in @('automation-inspect', 'automation-generate', 'automation-run')) {
        if ($parsed.Command -eq 'automation-inspect' -and [string]::IsNullOrWhiteSpace($parsed.WorkbookPath)) {
            Throw-CliError -Message "error: automation inspect requires --workbook-path"
        }
        if ($parsed.Command -eq 'automation-generate' -and [string]::IsNullOrWhiteSpace($parsed.TargetPath)) {
            Throw-CliError -Message "error: automation generate requires --target-path"
        }
        $payload = Invoke-ExcelAutomationCommand `
            -Command $parsed.Command `
            -WorkbookPath $parsed.WorkbookPath `
            -TargetPath $parsed.TargetPath `
            -AutomationType $parsed.AutomationType `
            -SpecJson $parsed.SpecJson `
            -SpecFile $parsed.SpecFile `
            -Backend $parsed.Backend `
            -Visible:$parsed.Visible
        $payload | ConvertTo-Json -Depth 100
        exit 0
    }

    $resolved = if ($parsed.Command -eq 'bootstrap') {
        Resolve-ExcelFoundryManifest -WorkbookPathOverride $parsed.WorkbookPath -AllowMissingManifestForInspectQuery
    }
    else {
        Resolve-ExcelFoundryManifest `
            -ManifestPath $parsed.ManifestPath `
            -WorkbookPathOverride $parsed.WorkbookPath `
            -AllowMissingManifestForInspectQuery:($parsed.Command -in @('inspect', 'query'))
    }

    switch ($parsed.Command) {
        'push' {
            & (Join-Path $PSScriptRoot 'sync-foundry.ps1') -ManifestPath $resolved.ManifestPath -Direction 'push' -WorkbookPath $resolved.WorkbookPath -Visible:$parsed.Visible
            break
        }
        'pull' {
            & (Join-Path $PSScriptRoot 'sync-foundry.ps1') -ManifestPath $resolved.ManifestPath -Direction 'pull' -WorkbookPath $resolved.WorkbookPath -Visible:$parsed.Visible
            break
        }
        'roundtrip' {
            & (Join-Path $PSScriptRoot 'sync-foundry.ps1') -ManifestPath $resolved.ManifestPath -Direction 'roundtrip' -WorkbookPath $resolved.WorkbookPath -Visible:$parsed.Visible
            break
        }
        'refresh' {
            & (Join-Path $PSScriptRoot 'sync-foundry.ps1') -ManifestPath $resolved.ManifestPath -Direction 'refresh' -WorkbookPath $resolved.WorkbookPath -QueryName $parsed.QueryName -Visible:$parsed.Visible
            break
        }
        'plan' {
            $payload = Invoke-PackageWorkbookHelper `
                -Command 'plan' `
                -ManifestPath $resolved.ManifestPath `
                -WorkbookPath $resolved.WorkbookPath `
                -Surface $surfaceNames `
                -Mode $parsed.Mode `
                -Sheet $parsed.Sheet `
                -Table $parsed.Table `
                -Name $parsed.Name `
                -NamePrefix $parsed.NamePrefix `
                -QueryName $parsed.QueryName `
                -StateRoot $parsed.StateRoot
            $payload | ConvertTo-Json -Depth 100
            break
        }
        'compare' {
            $payload = Invoke-PackageWorkbookHelper `
                -Command 'compare' `
                -ManifestPath $resolved.ManifestPath `
                -WorkbookPath $resolved.WorkbookPath `
                -Surface $surfaceNames `
                -Sheet $parsed.Sheet `
                -Table $parsed.Table `
                -Name $parsed.Name `
                -NamePrefix $parsed.NamePrefix `
                -QueryName $parsed.QueryName `
                -StateRoot $parsed.StateRoot
            $payload | ConvertTo-Json -Depth 100
            break
        }
        'sync' {
            $payload = Invoke-PackageWorkbookHelper `
                -Command 'sync' `
                -ManifestPath $resolved.ManifestPath `
                -WorkbookPath $resolved.WorkbookPath `
                -Surface $surfaceNames `
                -Mode $parsed.Mode `
                -Sheet $parsed.Sheet `
                -Table $parsed.Table `
                -Name $parsed.Name `
                -NamePrefix $parsed.NamePrefix `
                -QueryName $parsed.QueryName `
                -StateRoot $parsed.StateRoot `
                -Apply:$parsed.Apply
            $payload | ConvertTo-Json -Depth 100
            break
        }
        'smoke' {
            Invoke-ExcelSyncSmoke -ManifestPath $resolved.ManifestPath -WorkbookPath $resolved.WorkbookPath -Surface $surfaceNames -Visible:$parsed.Visible
            break
        }
        'inspect' {
            if (@($surfaceNames).Count -eq 0) {
                $payload = Get-ExcelWorkbookLifecycleInspection -WorkbookPath $resolved.WorkbookPath -Visible:$parsed.Visible -Backend $parsed.Backend
            }
            else {
                $payload = Get-ExcelWorkbookInspection -WorkbookPath $resolved.WorkbookPath -Visible:$parsed.Visible -Surface $surfaceNames -Backend $parsed.Backend
            }
            $payload | ConvertTo-Json -Depth 100
            break
        }
        'query' {
            $payload = Get-ExcelWorkbookQuery -WorkbookPath $resolved.WorkbookPath -Visible:$parsed.Visible -Surface $surfaceNames -Backend $parsed.Backend
            $payload | ConvertTo-Json -Depth 100
            break
        }
        'bootstrap' {
            if ([string]::IsNullOrWhiteSpace($parsed.OutputDir)) {
                Throw-CliError -Message "error: bootstrap requires --output-dir"
            }
            $payload = Invoke-ExcelWorkbookBootstrap `
                -WorkbookPath $resolved.WorkbookPath `
                -OutputDir $parsed.OutputDir `
                -ManifestPath $parsed.ManifestPath `
                -Surface $surfaceNames `
                -Visible:$parsed.Visible `
                -Backend $parsed.Backend
            $payload | ConvertTo-Json -Depth 100
            break
        }
    }
}
catch {
    Write-Error $_
    exit 1
}
