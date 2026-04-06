#!/usr/bin/env pwsh
#Requires -Version 5.1

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'ExcelSync.Common.ps1')

function Show-ExcelWorkbookSyncUsage {
    @"
Usage:
  excel-workbook-sync.ps1 <inspect|query|push|pull|roundtrip|smoke|refresh|bootstrap> [options]
  excel-workbook-sync.ps1 [options]

Options:
  --manifest-path PATH | -ManifestPath PATH
  --workbook-path PATH | -WorkbookPath PATH
  --output-dir PATH    | -OutputDir PATH
  --query-name NAME    | -QueryName NAME
  --surface LIST       | -Surface LIST
  --backend NAME       | -Backend NAME
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
        OutputDir = $null
        QueryName = @()
        Surface = 'vba,tables,names,cf,project,references,pq,connections,model'
        Backend = 'auto'
        Visible = $false
        ShowHelp = $false
    }

    $validCommands = @('inspect', 'query', 'push', 'pull', 'roundtrip', 'smoke', 'refresh', 'bootstrap')
    $index = 0
    if ($Tokens.Count -gt 0) {
        $first = [string]$Tokens[0]
        if (Test-IsHelpToken -Token $first) {
            $result.ShowHelp = $true
            return [pscustomobject]$result
        }

        if ($first -in $validCommands) {
            $result.Command = $first
            $index = 1
            if ($Tokens.Count -gt $index -and (Test-IsHelpToken -Token ([string]$Tokens[$index]))) {
                $result.ShowHelp = $true
                return [pscustomobject]$result
            }
        }
        elseif (-not $first.StartsWith('-')) {
            Throw-CliError -Message ("error: unknown subcommand: {0}`nhint: use one of inspect, query, push, pull, roundtrip, smoke, refresh, bootstrap" -f $first)
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
            { $_ -in @('--surface', '-Surface', '-surface') } {
                if ($index -ge $Tokens.Count) {
                    Throw-CliError -Message "error: missing value for $token"
                }
                $result.Surface = [string]$Tokens[$index]
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
            { $_ -in @('--visible', '-Visible', '-visible') } {
                $result.Visible = $true
                continue
            }
            default {
                Throw-CliError -Message ("error: unknown flag or argument: {0}`nhint: run 'excel-workbook-sync.ps1 --help' for the supported CLI surface" -f $token)
            }
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
    $resolved = if ($parsed.Command -eq 'bootstrap') {
        Resolve-ExcelSyncManifest -WorkbookPathOverride $parsed.WorkbookPath -AllowMissingManifestForInspectQuery
    }
    else {
        Resolve-ExcelSyncManifest `
            -ManifestPath $parsed.ManifestPath `
            -WorkbookPathOverride $parsed.WorkbookPath `
            -AllowMissingManifestForInspectQuery:($parsed.Command -in @('inspect', 'query'))
    }

    switch ($parsed.Command) {
        'push' {
            & (Join-Path $PSScriptRoot 'sync-excel.ps1') -ManifestPath $resolved.ManifestPath -Direction 'push' -WorkbookPath $resolved.WorkbookPath -Visible:$parsed.Visible
            break
        }
        'pull' {
            & (Join-Path $PSScriptRoot 'sync-excel.ps1') -ManifestPath $resolved.ManifestPath -Direction 'pull' -WorkbookPath $resolved.WorkbookPath -Visible:$parsed.Visible
            break
        }
        'roundtrip' {
            & (Join-Path $PSScriptRoot 'sync-excel.ps1') -ManifestPath $resolved.ManifestPath -Direction 'roundtrip' -WorkbookPath $resolved.WorkbookPath -Visible:$parsed.Visible
            break
        }
        'refresh' {
            & (Join-Path $PSScriptRoot 'sync-excel.ps1') -ManifestPath $resolved.ManifestPath -Direction 'refresh' -WorkbookPath $resolved.WorkbookPath -QueryName $parsed.QueryName -Visible:$parsed.Visible
            break
        }
        'smoke' {
            Invoke-ExcelSyncSmoke -ManifestPath $resolved.ManifestPath -WorkbookPath $resolved.WorkbookPath -Surface $surfaceNames -Visible:$parsed.Visible
            break
        }
        'inspect' {
            $payload = Get-ExcelWorkbookInspection -WorkbookPath $resolved.WorkbookPath -Visible:$parsed.Visible -Surface $surfaceNames -Backend $parsed.Backend
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
