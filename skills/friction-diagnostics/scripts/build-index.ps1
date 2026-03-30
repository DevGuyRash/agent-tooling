param(
    [string]$EventsFile = $env:FRICTION_EVENTS_FILE,
    [string]$IndexFile = $env:FRICTION_INDEX_FILE,
    [string]$RepoRoot = $env:FRICTION_REPO_ROOT,
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/build-index.ps1
  scripts/build-index.ps1 -RepoRoot <repo>
  scripts/build-index.ps1 -EventsFile /path/to/events.jsonl [-IndexFile /path/to/INDEX.md]
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

$paths = Resolve-FrictionPaths -RepoRoot $RepoRoot -EventsFile $EventsFile -IndexFile $IndexFile
$EventsFile = $paths.EventsFile
$IndexFile = $paths.IndexFile
$RepoRoot = $paths.RepoRoot

$indexTempFile = $null
Invoke-WithFileLock -LockRoot $IndexFile -ScriptBlock {
    if (-not (Test-Path -LiteralPath $EventsFile)) {
        Remove-Item -Force -ErrorAction SilentlyContinue $IndexFile
        return
    }

    $events = @(Import-Events $EventsFile)
    if ($events.Count -eq 0) {
        Remove-Item -Force -ErrorAction SilentlyContinue $IndexFile
        return
    }

    $rendered = & "$PSScriptRoot/generate-report.ps1" `
        -EventsFile $EventsFile `
        -RepoRoot $RepoRoot `
        -ReportType index `
        -Format md

    $indexTempFile = Join-Path (Split-Path -Parent $IndexFile) (".index.{0}.tmp" -f [System.IO.Path]::GetRandomFileName())
    [System.IO.File]::WriteAllText($indexTempFile, $rendered + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    Move-Item -Force -Path $indexTempFile -Destination $IndexFile
    $indexTempFile = $null
}

if ($null -ne $indexTempFile -and (Test-Path -LiteralPath $indexTempFile)) {
    Remove-Item -Force -ErrorAction SilentlyContinue $indexTempFile
}

if (Test-Path -LiteralPath $IndexFile) {
    $IndexFile
}
