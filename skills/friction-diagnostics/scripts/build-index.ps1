param(
    [string]$TaskDir = $env:FRICTION_TASK_DIR,
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/build-index.ps1 -TaskDir `$env:FRICTION_TASK_DIR
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

if ([string]::IsNullOrWhiteSpace($TaskDir)) { throw "-TaskDir is required" }
if (-not (Test-Path $TaskDir)) { throw "Task directory not found: $TaskDir" }

$indexFile = Join-Path $TaskDir 'INDEX.md'
$sessionFile = Join-Path $TaskDir 'SESSION.txt'
$lockDir = Join-Path $TaskDir '.build-index.lock'
$taskId = Split-Path -Leaf $TaskDir
$indexTempFile = $null

function Test-ActiveProcess {
    param([string]$ProcessId)
    if ([string]::IsNullOrWhiteSpace($ProcessId)) { return $false }
    if ($ProcessId -notmatch '^\d+$') { return $false }
    try {
        Get-Process -Id ([int]$ProcessId) -ErrorAction Stop | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Acquire-IndexLock {
    while ($true) {
        try {
            New-Item -ItemType Directory -Path $lockDir -ErrorAction Stop | Out-Null
            [System.IO.File]::WriteAllText((Join-Path $lockDir 'pid'), [string]$PID, [System.Text.UTF8Encoding]::new($false))
            return
        }
        catch [System.IO.IOException] {
            $pidFile = Join-Path $lockDir 'pid'
            $lockPid = $null
            if (Test-Path $pidFile) {
                try {
                    $lockPid = [System.IO.File]::ReadAllText($pidFile).Trim()
                }
                catch {
                    $lockPid = $null
                }
            }

            if (-not (Test-ActiveProcess $lockPid)) {
                Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
                Remove-Item -Force -Recurse -ErrorAction SilentlyContinue $lockDir
                continue
            }

            Start-Sleep -Seconds 1
        }
    }
}

Acquire-IndexLock
try {
    $generated = [System.DateTimeOffset]::UtcNow.ToString('yyyy-MM-dd HH:mm:ss') + ' UTC'
    $taskSummary = ""
    if (Test-Path $sessionFile) {
        $sessionLines = Get-Content $sessionFile
        $taskSummaryFile = (($sessionLines | Where-Object { $_ -like 'FRICTION_TASK_SUMMARY_FILE=*' }) -replace '^FRICTION_TASK_SUMMARY_FILE=', '')
        if (-not [string]::IsNullOrWhiteSpace($taskSummaryFile) -and (Test-Path $taskSummaryFile)) {
            $taskSummary = [System.IO.File]::ReadAllText($taskSummaryFile)
        } else {
            $taskSummary = (($sessionLines | Where-Object { $_ -like 'FRICTION_TASK_SUMMARY=*' }) -replace '^FRICTION_TASK_SUMMARY=', '')
        }
    }

    $eventsJsonl = Join-Path $TaskDir 'events.jsonl'
    $logFiles = Get-ChildItem -Path $TaskDir -Recurse -Filter '*.md' -File | Where-Object { $_.Name -ne 'INDEX.md' } | Sort-Object FullName
    $logFileCount = $logFiles.Count
    $totalEntries = 0

    if (Test-Path $eventsJsonl) {
        $totalEntries = @([System.IO.File]::ReadAllLines($eventsJsonl) | Where-Object { $_ }).Count
    }
    if ($totalEntries -eq 0) {
        foreach ($file in $logFiles) {
            $content = Get-Content -Path $file.FullName -Raw
            $totalEntries += ([regex]::Matches($content, '^## Event \d+:', [System.Text.RegularExpressions.RegexOptions]::Multiline)).Count
        }
    }

    $categoryCounts = @{}
    $logLines = @()
    foreach ($file in $logFiles) {
        $content = Get-Content -Path $file.FullName -Raw
        $entryCount = ([regex]::Matches($content, '^## Event \d+:', [System.Text.RegularExpressions.RegexOptions]::Multiline)).Count
        $relativePath = $file.FullName.Substring($TaskDir.Length).TrimStart('\','/')
        $logLines += [PSCustomObject]@{ Count = $entryCount; Path = $relativePath }

        foreach ($line in (Get-Content $file.FullName)) {
            if ($line -match '^\*\*Derived category:\*\* (?<category>.+)$') {
                $category = $matches['category']
                if (-not $categoryCounts.ContainsKey($category)) { $categoryCounts[$category] = 0 }
                $categoryCounts[$category]++
            }
        }
    }

    $lines = @(
        "# Friction Index: $taskId"
    )
    $lines += Write-MarkdownField -Label 'Generated' -Value $generated
    $lines += Write-MarkdownField -Label 'Task dir' -Value $TaskDir
    if (-not [string]::IsNullOrWhiteSpace($taskSummary)) {
        $lines += Write-MarkdownField -Label 'Task summary' -Value $taskSummary
    }
    $lines += Write-MarkdownField -Label 'Log files' -Value ([string]$logFileCount)
    $lines += Write-MarkdownField -Label 'Entries' -Value ([string]$totalEntries)
    $lines += ""
    $lines += "## Category counts"
    $lines += ""

    if ($categoryCounts.Count -gt 0) {
        $sortedCategoryCounts = $categoryCounts.GetEnumerator() | Sort-Object -Property @(
            @{ Expression = { $_.Value }; Descending = $true }
            @{ Expression = { $_.Name }; Descending = $false }
        )
        foreach ($item in $sortedCategoryCounts) {
            $lines += "- ``$($item.Key)`` - $($item.Value)"
        }
    } else {
        $lines += "_No categorized entries yet._"
    }

    $lines += ""
    $lines += "## Log files"
    $lines += ""

    if ($logLines.Count -gt 0) {
        $sortedLogLines = $logLines | Sort-Object -Property @(
            @{ Expression = { $_.Count }; Descending = $true }
            @{ Expression = { $_.Path }; Descending = $false }
        )
        foreach ($item in $sortedLogLines) {
            $lines += "- ``$($item.Path)`` - $($item.Count) entries"
        }
    } else {
        $lines += "_No log files yet._"
    }

    $indexTempFile = Join-Path $TaskDir (".index.{0}.tmp" -f [System.IO.Path]::GetRandomFileName())
    Set-Content -Path $indexTempFile -Value $lines -Encoding UTF8
    Move-Item -Force -Path $indexTempFile -Destination $indexFile
    $indexTempFile = $null
}
finally {
    if ($null -ne $indexTempFile -and (Test-Path $indexTempFile)) {
        Remove-Item -Force -ErrorAction SilentlyContinue $indexTempFile
    }
    $pidFile = Join-Path $lockDir 'pid'
    Remove-Item -Force -ErrorAction SilentlyContinue $pidFile
    Remove-Item -Force -Recurse -ErrorAction SilentlyContinue $lockDir
}

$indexFile
