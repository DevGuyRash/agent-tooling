param(
    [string]$WorkbookPath,
    [string[]]$ComponentMap,
    [switch]$UseDefaultTrUploadMap,
    [ValidateSet("push", "pull")]
    [string]$Direction = "push",
    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$manifestPath = Join-Path (Split-Path -Parent $PSScriptRoot) "excel-foundry.manifest.json"
$genericScript = Join-Path (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "scripts") "sync-excel-vba.ps1"

if ($ComponentMap.Count -gt 0) {
    throw "Custom -ComponentMap is no longer supported here. Update the workbook manifest or use excel/scripts/sync-excel-vba.ps1 directly."
}

$params = @{
    ManifestPath = $manifestPath
    Direction = $Direction
}

if (-not [string]::IsNullOrWhiteSpace($WorkbookPath)) {
    $params.WorkbookPath = $WorkbookPath
}
if ($Visible) {
    $params.Visible = $true
}

& $genericScript @params
