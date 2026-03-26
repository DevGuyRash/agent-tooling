param(
    [string]$TaskSummary = $env:FRICTION_TASK_SUMMARY,
    [string]$TaskId = "",
    [string]$Agent = "orchestrator",
    [string]$Role = "",
    [string]$SkillPath = "",
    [string]$BaseDir = $(if ($env:FRICTION_BASE_DIR) { $env:FRICTION_BASE_DIR } else { Join-Path ([System.IO.Path]::GetTempPath()) 'agent-friction' }),
    [string]$ContextPath = "",
    [string]$StorageMode = "handoff",
    [string]$CaptureMode = "explicit",
    [string]$PrivacyTier = "private",
    [string]$ExportDir = "",
    [switch]$NoReuse,
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/init-log.ps1 -TaskSummary "..." -Agent orchestrator -SkillPath `$PWD

Options:
  -TaskSummary TEXT
  -TaskId TEXT
  -Agent TEXT
  -Role TEXT
  -SkillPath TEXT
  -BaseDir PATH
  -ContextPath PATH
  -StorageMode MODE     handoff | artifact | telemetry
  -CaptureMode MODE     explicit | threshold | synthesis
  -PrivacyTier TIER     private | shared
  -ExportDir PATH
  -NoReuse      Skip session reuse; always create a new session directory
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

if ([string]::IsNullOrWhiteSpace($TaskSummary)) { throw "-TaskSummary is required" }
if ([string]::IsNullOrWhiteSpace($SkillPath)) { throw "-SkillPath is required" }

$StorageMode = ConvertTo-NormalizedStorageMode $StorageMode
$CaptureMode = ConvertTo-NormalizedCaptureMode $CaptureMode
$PrivacyTier = ConvertTo-NormalizedPrivacyTier $PrivacyTier

if ([string]::IsNullOrWhiteSpace($ExportDir) -and $StorageMode -eq 'telemetry') {
    $ExportDir = Join-Path $BaseDir 'telemetry'
}

$now = [System.DateTimeOffset]::UtcNow
$dateDir = $now.ToString('yyyy-MM-dd')
$stamp = $now.ToString('yyyy-MM-ddTHH:mm:ssZ')
$taskAutoSlugLimit = 80
$taskIdLimit = 255
New-Item -ItemType Directory -Force -Path $BaseDir | Out-Null

if ([string]::IsNullOrWhiteSpace($TaskId)) {
    $today = $now.ToString('yyyyMMdd')
    $slug = Get-BoundedSlug -Text $TaskSummary -Limit $taskAutoSlugLimit
    $lockDir = Join-Path $BaseDir ".create-lock-${slug}"

    # Helper: find an existing session directory for today
    function Find-ExistingSession {
        if (Test-Path $BaseDir) {
            $match = Get-ChildItem -Path $BaseDir -Directory -Filter "${slug}-${today}-*" -ErrorAction SilentlyContinue |
                Sort-Object Name | Select-Object -Last 1
            if ($match -and (Test-Path (Join-Path $match.FullName 'SESSION.txt'))) {
                return $match.FullName
            }
        }
        return $null
    }

    # Helper: create a new session directory (race-safe GUID loop)
    function New-SessionDir {
        $timestamp = $now.ToString('yyyyMMdd-HHmmss')
        while ($true) {
            $candidateTaskId = "{0}-{1}-{2}" -f $slug, $timestamp, ([System.Guid]::NewGuid().ToString('N').Substring(0, 8))
            $candidateTaskDir = Join-Path $BaseDir $candidateTaskId
            try {
                New-Item -ItemType Directory -Path $candidateTaskDir -ErrorAction Stop | Out-Null
                return $candidateTaskDir
            }
            catch [System.IO.IOException] {
                continue
            }
        }
    }

    $existingDir = $null
    if (-not $NoReuse) {
        $existingDir = Find-ExistingSession
    }

    if ($existingDir) {
        $taskDir = $existingDir
        $TaskId = Split-Path -Leaf $taskDir
    } else {
        # Clean up stale lock older than 60 seconds
        if (Test-Path $lockDir) {
            if ((Get-Item $lockDir).LastWriteTimeUtc -lt [DateTime]::UtcNow.AddSeconds(-60)) {
                Remove-Item -Path $lockDir -Force -ErrorAction SilentlyContinue
            }
        }
        # Race-safe lock acquisition
        try {
            New-Item -ItemType Directory -Path $lockDir -ErrorAction Stop | Out-Null
            # Won the lock — create new session
            $newDir = New-SessionDir
            Remove-Item -Path $lockDir -Force -ErrorAction SilentlyContinue
            $taskDir = $newDir
            $TaskId = Split-Path -Leaf $taskDir
        }
        catch [System.IO.IOException] {
            # Lost the lock — wait and retry discovery
            Start-Sleep -Seconds 1
            $existingDir = Find-ExistingSession
            if ($existingDir) {
                $taskDir = $existingDir
                $TaskId = Split-Path -Leaf $taskDir
            } else {
                $newDir = New-SessionDir
                $taskDir = $newDir
                $TaskId = Split-Path -Leaf $taskDir
            }
            Remove-Item -Path $lockDir -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    $candidateDir = Join-Path $BaseDir $TaskId
    if (Test-Path $candidateDir) {
        $taskDir = $candidateDir
    } else {
        $TaskId = Get-BoundedSlug -Text $TaskId -Limit $taskIdLimit
        $taskDir = Join-Path $BaseDir $TaskId
        New-Item -ItemType Directory -Force -Path $taskDir | Out-Null
    }
}

$indexFile = Join-Path $taskDir 'INDEX.md'
$sessionFile = Join-Path $taskDir 'SESSION.txt'
$taskSummaryFile = Join-Path $taskDir 'TASK_SUMMARY.txt'
$taskJsonFile = Join-Path $taskDir 'task.json'
$eventsFile = Join-Path $taskDir 'events.jsonl'
$incidentsFile = Join-Path $taskDir 'incidents.json'
$exportsDir = Join-Path $taskDir 'exports'
$sanitizedExportFile = Join-Path $exportsDir 'sanitized-incidents.json'

if (-not (Test-Path $taskSummaryFile)) {
    [System.IO.File]::WriteAllText($taskSummaryFile, $TaskSummary, [System.Text.UTF8Encoding]::new($false))
}

if (-not (Test-Path $taskJsonFile)) {
    $taskJsonContent = '{' +
        (ConvertTo-JsonString 'schema_version' $script:SCHEMA_VERSION) + ',' +
        (ConvertTo-JsonString 'task_id' $TaskId) + ',' +
        (ConvertTo-JsonString 'created_at' $stamp) + ',' +
        (ConvertTo-JsonString 'task_summary' $TaskSummary) + ',' +
        (ConvertTo-JsonString 'task_summary_first_line' (Get-TruncatedLine $TaskSummary 120)) + ',' +
        (ConvertTo-JsonString 'storage_mode' $StorageMode) + ',' +
        (ConvertTo-JsonString 'capture_mode' $CaptureMode) + ',' +
        (ConvertTo-JsonString 'privacy_tier' $PrivacyTier) + ',' +
        (ConvertTo-JsonString 'platform' (Get-PlatformName)) + ',' +
        (ConvertTo-JsonString 'skill_path' $SkillPath) + ',' +
        (ConvertTo-JsonString 'task_dir' $taskDir) + ',' +
        (ConvertTo-JsonBool 'artifacts_materialized' $false) + ',' +
        (ConvertTo-JsonString 'export_dir' $ExportDir)
    if (-not [string]::IsNullOrWhiteSpace($ContextPath)) {
        $taskJsonContent += ',' + (ConvertTo-JsonString 'context_path' $ContextPath)
    }
    $taskJsonContent += '}'
    [System.IO.File]::WriteAllText($taskJsonFile, "$taskJsonContent`n", [System.Text.UTF8Encoding]::new($false))
}

@(
    "FRICTION_BASE_DIR=$BaseDir"
    "FRICTION_TASK_ID=$TaskId"
    "FRICTION_TASK_DIR=$taskDir"
    "FRICTION_TASK_SUMMARY_FILE=$taskSummaryFile"
    "FRICTION_INDEX_FILE=$indexFile"
    "FRICTION_TASK_JSON=$taskJsonFile"
    "FRICTION_EVENTS_FILE=$eventsFile"
    "FRICTION_INCIDENTS_FILE=$incidentsFile"
    "FRICTION_STORAGE_MODE=$StorageMode"
    "FRICTION_CAPTURE_MODE=$CaptureMode"
    "FRICTION_PRIVACY_TIER=$PrivacyTier"
    "FRICTION_EXPORT_DIR=$ExportDir"
    "FRICTION_SANITIZED_EXPORT=$sanitizedExportFile"
    "FRICTION_SKILL_PATH=$SkillPath"
    "FRICTION_CONTEXT_PATH=$ContextPath"
) | Set-Content -Path $sessionFile -Encoding UTF8

$env:FRICTION_BASE_DIR = $BaseDir
$env:FRICTION_TASK_ID = $TaskId
$env:FRICTION_TASK_DIR = $taskDir
$env:FRICTION_TASK_SUMMARY = $TaskSummary
$env:FRICTION_TASK_SUMMARY_FILE = $taskSummaryFile
$env:FRICTION_TASK_JSON = $taskJsonFile
$env:FRICTION_EVENTS_FILE = $eventsFile
$env:FRICTION_INCIDENTS_FILE = $incidentsFile
$env:FRICTION_STORAGE_MODE = $StorageMode
$env:FRICTION_CAPTURE_MODE = $CaptureMode
$env:FRICTION_PRIVACY_TIER = $PrivacyTier
$env:FRICTION_EXPORT_DIR = $ExportDir
$env:FRICTION_SANITIZED_EXPORT = $sanitizedExportFile

@(
    "FRICTION_BASE_DIR=$BaseDir"
    "FRICTION_TASK_ID=$TaskId"
    "FRICTION_TASK_DIR=$taskDir"
    "FRICTION_TASK_SUMMARY=$TaskSummary"
    "FRICTION_TASK_SUMMARY_FILE=$taskSummaryFile"
    "FRICTION_LOG_FILE="
    "FRICTION_INDEX_FILE=$indexFile"
    "FRICTION_TASK_DESCRIPTOR="
    "FRICTION_TASK_JSON=$taskJsonFile"
    "FRICTION_EVENTS_FILE=$eventsFile"
    "FRICTION_INCIDENTS_FILE=$incidentsFile"
    "FRICTION_SKILL_PATH=$SkillPath"
    "FRICTION_CONTEXT_PATH=$ContextPath"
    "FRICTION_STORAGE_MODE=$StorageMode"
    "FRICTION_CAPTURE_MODE=$CaptureMode"
    "FRICTION_PRIVACY_TIER=$PrivacyTier"
    "FRICTION_EXPORT_DIR=$ExportDir"
    "FRICTION_SANITIZED_EXPORT=$sanitizedExportFile"
)
