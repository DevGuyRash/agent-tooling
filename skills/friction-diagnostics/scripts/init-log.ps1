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
$timePart = $now.ToString('HH-mm-ss')
$stamp = $now.ToString('yyyy-MM-ddTHH:mm:ssZ')
$taskAutoSlugLimit = 80
$taskIdLimit = 255
$logSlugLimit = 240
New-Item -ItemType Directory -Force -Path $BaseDir | Out-Null
if (-not [string]::IsNullOrWhiteSpace($ExportDir)) {
    New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null
}

if ([string]::IsNullOrWhiteSpace($TaskId)) {
    $timestamp = $now.ToString('yyyyMMdd-HHmmss')
    $slug = Get-BoundedSlug -Text $TaskSummary -Limit $taskAutoSlugLimit
    while ($true) {
        $candidateTaskId = "{0}-{1}-{2}" -f $slug, $timestamp, ([System.Guid]::NewGuid().ToString('N').Substring(0, 8))
        $candidateTaskDir = Join-Path $BaseDir $candidateTaskId
        try {
            New-Item -ItemType Directory -Path $candidateTaskDir -ErrorAction Stop | Out-Null
            $TaskId = $candidateTaskId
            $taskDir = $candidateTaskDir
            break
        }
        catch [System.IO.IOException] {
            continue
        }
    }
} else {
    $candidateDir = Join-Path $BaseDir $TaskId
    if (Test-Path $candidateDir) {
        $taskDir = $candidateDir
    } else {
        $TaskId = Get-BoundedSlug -Text $TaskId -Limit $taskIdLimit
        $taskDir = Join-Path $BaseDir $TaskId
    }
}

$agentSlug = Get-Slug $Agent
$agentDisplay = $Agent
if (-not [string]::IsNullOrWhiteSpace($Role)) {
    $agentSlug = "$agentSlug-$(Get-Slug $Role)"
    $agentDisplay = "$Agent ($Role)"
}
$agentSlug = Get-BoundedSlug -Text $agentSlug -Limit $logSlugLimit

$datedDir = Join-Path $taskDir $dateDir
New-Item -ItemType Directory -Force -Path $datedDir | Out-Null

$logFile = Join-Path $datedDir "${timePart}_${agentSlug}.md"
$suffix = 1
while (Test-Path $logFile) {
    $logFile = Join-Path $datedDir ("{0}_{1}_{2:d2}.md" -f $timePart, $agentSlug, $suffix)
    $suffix++
}

$indexFile = Join-Path $taskDir 'INDEX.md'
$sessionFile = Join-Path $taskDir 'SESSION.txt'
$taskSummaryFile = Join-Path $taskDir 'TASK_SUMMARY.txt'
$descriptorFile = Join-Path $taskDir 'TASK_DESCRIPTOR.json'
$taskJsonFile = Join-Path $taskDir 'task.json'
$eventsFile = Join-Path $taskDir 'events.jsonl'
$incidentsFile = Join-Path $taskDir 'incidents.json'
$exportsDir = Join-Path $taskDir 'exports'
$sanitizedExportFile = Join-Path $exportsDir 'sanitized-incidents.json'

New-Item -ItemType Directory -Force -Path $exportsDir | Out-Null

$headerLines = @(
    "# Friction Evidence Log: $TaskId"
)
$headerLines += Write-MarkdownField -Label 'Created' -Value $stamp
$headerLines += Write-MarkdownField -Label 'Agent' -Value $agentDisplay
$headerLines += Write-MarkdownField -Label 'Task ID' -Value $TaskId
$headerLines += Write-MarkdownField -Label 'Task summary' -Value $TaskSummary
$headerLines += Write-MarkdownField -Label 'Storage mode' -Value $StorageMode
$headerLines += Write-MarkdownField -Label 'Capture mode' -Value $CaptureMode
$headerLines += Write-MarkdownField -Label 'Privacy tier' -Value $PrivacyTier
$headerLines += Write-MarkdownField -Label 'Skill path' -Value $SkillPath
if (-not [string]::IsNullOrWhiteSpace($ContextPath)) {
    $headerLines += Write-MarkdownField -Label 'Context path' -Value $ContextPath
}
if (-not [string]::IsNullOrWhiteSpace($ExportDir)) {
    $headerLines += Write-MarkdownField -Label 'Export dir' -Value $ExportDir
}
$headerLines += Write-MarkdownField -Label 'Platform' -Value (Get-PlatformName)
$headerLines += Write-MarkdownField -Label 'Schema version' -Value $script:SCHEMA_VERSION
$headerLines += '---'
Set-Content -Path $logFile -Value $headerLines -Encoding UTF8

if (-not (Test-Path $taskSummaryFile)) {
    [System.IO.File]::WriteAllText($taskSummaryFile, $TaskSummary, [System.Text.UTF8Encoding]::new($false))
}

if (-not (Test-Path $taskJsonFile)) {
    $taskJsonContent = '{' +
        (ConvertTo-JsonString 'schema_version' $script:SCHEMA_VERSION) + ',' +
        (ConvertTo-JsonString 'task_id' $TaskId) + ',' +
        (ConvertTo-JsonString 'created_at' $stamp) + ',' +
        (ConvertTo-JsonString 'task_summary_b64' (ConvertTo-Base64 $TaskSummary)) + ',' +
        (ConvertTo-JsonString 'task_summary_first_line' (Get-TruncatedLine $TaskSummary 120)) + ',' +
        (ConvertTo-JsonString 'storage_mode' $StorageMode) + ',' +
        (ConvertTo-JsonString 'capture_mode' $CaptureMode) + ',' +
        (ConvertTo-JsonString 'privacy_tier' $PrivacyTier) + ',' +
        (ConvertTo-JsonString 'platform' (Get-PlatformName)) + ',' +
        (ConvertTo-JsonString 'skill_path' $SkillPath) + ',' +
        (ConvertTo-JsonString 'task_dir' $taskDir) + ',' +
        (ConvertTo-JsonString 'export_dir' $ExportDir)
    if (-not [string]::IsNullOrWhiteSpace($ContextPath)) {
        $taskJsonContent += ',' + (ConvertTo-JsonString 'context_path' $ContextPath)
    }
    $taskJsonContent += '}'
    [System.IO.File]::WriteAllText($taskJsonFile, "$taskJsonContent`n", [System.Text.UTF8Encoding]::new($false))
}

$descriptorContent = '{' +
    (ConvertTo-JsonString 'schema_version' $script:SCHEMA_VERSION) + ',' +
    (ConvertTo-JsonString 'task_id' $TaskId) + ',' +
    (ConvertTo-JsonString 'task_dir' $taskDir) + ',' +
    (ConvertTo-JsonString 'log_file' $logFile) + ',' +
    (ConvertTo-JsonString 'task_json' $taskJsonFile) + ',' +
    (ConvertTo-JsonString 'events_file' $eventsFile) + ',' +
    (ConvertTo-JsonString 'incidents_file' $incidentsFile) + ',' +
    (ConvertTo-JsonString 'index_file' $indexFile) + ',' +
    (ConvertTo-JsonString 'task_summary_file' $taskSummaryFile) + ',' +
    (ConvertTo-JsonString 'storage_mode' $StorageMode) + ',' +
    (ConvertTo-JsonString 'capture_mode' $CaptureMode) + ',' +
    (ConvertTo-JsonString 'privacy_tier' $PrivacyTier) + ',' +
    (ConvertTo-JsonString 'export_dir' $ExportDir) +
    '}'
[System.IO.File]::WriteAllText($descriptorFile, "$descriptorContent`n", [System.Text.UTF8Encoding]::new($false))

if (-not (Test-Path $eventsFile)) {
    [System.IO.File]::WriteAllText($eventsFile, '', [System.Text.UTF8Encoding]::new($false))
}

if (-not (Test-Path $incidentsFile)) {
    $incidentsContent = '{' +
        (ConvertTo-JsonString 'schema_version' $script:SCHEMA_VERSION) + ',' +
        (ConvertTo-JsonString 'generated_at' $stamp) + ',' +
        (ConvertTo-JsonString 'task_id' $TaskId) + ',' +
        (ConvertTo-JsonNumber 'event_count' 0) + ',' +
        (ConvertTo-JsonNumber 'incident_count' 0) + ',' +
        '"incidents":[]}'
    [System.IO.File]::WriteAllText($incidentsFile, "$incidentsContent`n", [System.Text.UTF8Encoding]::new($false))
}

@(
    "FRICTION_BASE_DIR=$BaseDir"
    "FRICTION_TASK_ID=$TaskId"
    "FRICTION_TASK_DIR=$taskDir"
    "FRICTION_TASK_SUMMARY_FILE=$taskSummaryFile"
    "FRICTION_INDEX_FILE=$indexFile"
    "FRICTION_TASK_DESCRIPTOR=$descriptorFile"
    "FRICTION_TASK_JSON=$taskJsonFile"
    "FRICTION_EVENTS_FILE=$eventsFile"
    "FRICTION_INCIDENTS_FILE=$incidentsFile"
    "FRICTION_STORAGE_MODE=$StorageMode"
    "FRICTION_CAPTURE_MODE=$CaptureMode"
    "FRICTION_PRIVACY_TIER=$PrivacyTier"
    "FRICTION_EXPORT_DIR=$ExportDir"
    "FRICTION_SANITIZED_EXPORT=$sanitizedExportFile"
) | Set-Content -Path $sessionFile -Encoding UTF8

$env:FRICTION_BASE_DIR = $BaseDir
$env:FRICTION_TASK_ID = $TaskId
$env:FRICTION_TASK_DIR = $taskDir
$env:FRICTION_TASK_SUMMARY = $TaskSummary
$env:FRICTION_TASK_SUMMARY_FILE = $taskSummaryFile
$env:FRICTION_LOG_FILE = $logFile
$env:FRICTION_INDEX_FILE = $indexFile
$env:FRICTION_TASK_DESCRIPTOR = $descriptorFile
$env:FRICTION_TASK_JSON = $taskJsonFile
$env:FRICTION_EVENTS_FILE = $eventsFile
$env:FRICTION_INCIDENTS_FILE = $incidentsFile
$env:FRICTION_STORAGE_MODE = $StorageMode
$env:FRICTION_CAPTURE_MODE = $CaptureMode
$env:FRICTION_PRIVACY_TIER = $PrivacyTier
$env:FRICTION_EXPORT_DIR = $ExportDir
$env:FRICTION_SANITIZED_EXPORT = $sanitizedExportFile

& "$PSScriptRoot/build-index.ps1" -TaskDir $taskDir | Out-Null

@(
    "FRICTION_BASE_DIR=$BaseDir"
    "FRICTION_TASK_ID=$TaskId"
    "FRICTION_TASK_DIR=$taskDir"
    "FRICTION_TASK_SUMMARY=$TaskSummary"
    "FRICTION_TASK_SUMMARY_FILE=$taskSummaryFile"
    "FRICTION_LOG_FILE=$logFile"
    "FRICTION_INDEX_FILE=$indexFile"
    "FRICTION_TASK_DESCRIPTOR=$descriptorFile"
    "FRICTION_TASK_JSON=$taskJsonFile"
    "FRICTION_EVENTS_FILE=$eventsFile"
    "FRICTION_INCIDENTS_FILE=$incidentsFile"
    "FRICTION_STORAGE_MODE=$StorageMode"
    "FRICTION_CAPTURE_MODE=$CaptureMode"
    "FRICTION_PRIVACY_TIER=$PrivacyTier"
    "FRICTION_EXPORT_DIR=$ExportDir"
    "FRICTION_SANITIZED_EXPORT=$sanitizedExportFile"
)
