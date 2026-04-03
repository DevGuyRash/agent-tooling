#!/usr/bin/env pwsh
#Requires -Version 5.1

param(
    [Parameter(Position = 0)]
    [ValidateSet('inspect', 'query', 'push', 'pull', 'roundtrip', 'smoke', 'refresh')]
    [string]$Command = 'inspect',
    [Alias('manifest-path')]
    [string]$ManifestPath,
    [Alias('workbook-path')]
    [string]$WorkbookPath,
    [Alias('query-name')]
    [string[]]$QueryName = @(),
    [string]$Surface = 'vba,tables,names,cf,project,references,pq,connections,model',
    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'ExcelSync.Common.ps1')

$surfaceNames = @($Surface -split ',' | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
$resolved = Resolve-ExcelSyncManifest -ManifestPath $ManifestPath -WorkbookPathOverride $WorkbookPath -AllowMissingManifestForInspectQuery:($Command -in @('inspect', 'query'))

switch ($Command) {
    'push' {
        & (Join-Path $PSScriptRoot 'sync-excel.ps1') -ManifestPath $resolved.ManifestPath -Direction 'push' -WorkbookPath $resolved.WorkbookPath -Visible:$Visible
        break
    }
    'pull' {
        & (Join-Path $PSScriptRoot 'sync-excel.ps1') -ManifestPath $resolved.ManifestPath -Direction 'pull' -WorkbookPath $resolved.WorkbookPath -Visible:$Visible
        break
    }
    'roundtrip' {
        & (Join-Path $PSScriptRoot 'sync-excel.ps1') -ManifestPath $resolved.ManifestPath -Direction 'roundtrip' -WorkbookPath $resolved.WorkbookPath -Visible:$Visible
        break
    }
    'refresh' {
        & (Join-Path $PSScriptRoot 'sync-excel.ps1') -ManifestPath $resolved.ManifestPath -Direction 'refresh' -WorkbookPath $resolved.WorkbookPath -QueryName $QueryName -Visible:$Visible
        break
    }
    'smoke' {
        Invoke-ExcelSyncSmoke -ManifestPath $resolved.ManifestPath -WorkbookPath $resolved.WorkbookPath -Surface $surfaceNames -Visible:$Visible
        break
    }
    'inspect' {
        $payload = Get-ExcelWorkbookInspection -WorkbookPath $resolved.WorkbookPath -Visible:$Visible -Surface $surfaceNames
        $payload | ConvertTo-Json -Depth 100
        break
    }
    'query' {
        $payload = Get-ExcelWorkbookQuery -WorkbookPath $resolved.WorkbookPath -Visible:$Visible -Surface $surfaceNames
        $payload | ConvertTo-Json -Depth 100
        break
    }
}
