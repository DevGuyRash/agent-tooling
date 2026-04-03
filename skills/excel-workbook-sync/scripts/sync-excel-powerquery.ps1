param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [ValidateSet("push", "pull", "roundtrip", "refresh")]
    [string]$Direction = "pull",
    [string]$WorkbookPath,
    [string[]]$QueryName = @(),
    [switch]$Visible
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot 'ExcelSync.Common.ps1')

$resolved = Resolve-ExcelSyncManifest -ManifestPath $ManifestPath -WorkbookPathOverride $WorkbookPath
$powerQuery = $resolved.PowerQuery
if ($null -eq $powerQuery -or (
    [string]::IsNullOrWhiteSpace($powerQuery.QueriesDirectory) -and
    [string]::IsNullOrWhiteSpace($powerQuery.QueriesPath) -and
    [string]::IsNullOrWhiteSpace($powerQuery.ConnectionsPath) -and
    [string]::IsNullOrWhiteSpace($powerQuery.ModelPath) -and
    [string]::IsNullOrWhiteSpace($powerQuery.RefreshPath)
)) {
    return
}

$saveChanges = $Direction -in @('push', 'roundtrip', 'refresh')
$context = Open-ExcelWorkbook -WorkbookPath $resolved.WorkbookPath -Visible:$Visible
try {
    switch ($Direction) {
        'push' {
            Ensure-PowerQueryArtifacts -Workbook $context.Workbook -ResolvedManifest $resolved
            foreach ($query in (Read-PowerQueryArtifacts -ResolvedManifest $resolved).queries) {
                Write-Output ("PUSH PQ {0}" -f $query.name)
            }
            break
        }
        'pull' {
            Export-PowerQueryArtifacts -Workbook $context.Workbook -ResolvedManifest $resolved
            foreach ($query in (Get-WorkbookPowerQueryArtifacts -Workbook $context.Workbook).queries) {
                Write-Output ("PULL PQ {0}" -f $query.name)
            }
            break
        }
        'roundtrip' {
            Ensure-PowerQueryArtifacts -Workbook $context.Workbook -ResolvedManifest $resolved
            foreach ($query in (Read-PowerQueryArtifacts -ResolvedManifest $resolved).queries) {
                Write-Output ("PUSH PQ {0}" -f $query.name)
            }
            Export-PowerQueryArtifacts -Workbook $context.Workbook -ResolvedManifest $resolved
            foreach ($query in (Get-WorkbookPowerQueryArtifacts -Workbook $context.Workbook).queries) {
                Write-Output ("PULL PQ {0}" -f $query.name)
            }
            break
        }
        'refresh' {
            $results = @(Invoke-WorkbookPowerQueryRefresh -Workbook $context.Workbook -QueryNames $QueryName)
            foreach ($result in $results) {
                if ($result.success) {
                    Write-Output ("REFRESH PQ {0} OK {1}s" -f $result.name, $result.elapsedSeconds)
                }
                else {
                    Write-Output ("REFRESH PQ {0} FAIL {1}" -f $result.name, $result.error)
                }
            }
            break
        }
    }
}
finally {
    Close-ExcelWorkbook -Context $context -SaveChanges:$saveChanges
}
