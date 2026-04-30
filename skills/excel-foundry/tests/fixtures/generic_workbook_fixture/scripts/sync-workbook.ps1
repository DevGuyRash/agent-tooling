param(
    [string]$WorkbookPath,
    [ValidateSet("push", "pull", "roundtrip")]
    [string]$Direction = "push",
    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$manifestPath = Join-Path (Split-Path -Parent $PSScriptRoot) "excel-foundry.manifest.json"
$genericScript = Join-Path (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "scripts") "sync-excel.ps1"

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
