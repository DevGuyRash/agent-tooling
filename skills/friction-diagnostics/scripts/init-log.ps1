param(
    [string]$TaskSummary = $env:FRICTION_TASK_SUMMARY,
    [string]$TaskId = "",
    [string]$Agent = "orchestrator",
    [string]$Role = "",
    [string]$SkillPath = "",
    [string]$BaseDir = $(if ($env:FRICTION_BASE_DIR) { $env:FRICTION_BASE_DIR } else { Join-Path ([System.IO.Path]::GetTempPath()) 'agent-friction' }),
    [string]$ContextPath = "",
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/init-log.ps1 -TaskSummary "..." -Agent orchestrator -SkillPath $PWD

Options:
  -TaskSummary TEXT
  -TaskId TEXT
  -Agent TEXT
  -Role TEXT
  -SkillPath TEXT
  -BaseDir PATH
  -ContextPath PATH
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

if ([string]::IsNullOrWhiteSpace($TaskSummary)) { throw "-TaskSummary is required" }
if ([string]::IsNullOrWhiteSpace($SkillPath)) { throw "-SkillPath is required" }

$dateDir = Get-Date -Format 'yyyy-MM-dd'
$timePart = Get-Date -Format 'HH-mm-ss'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'
$taskAutoSlugLimit = 232
$taskIdLimit = 255
$logSlugLimit = 240
New-Item -ItemType Directory -Force -Path $BaseDir | Out-Null

if ([string]::IsNullOrWhiteSpace($TaskId)) {
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
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
    $TaskId = Get-BoundedSlug -Text $TaskId -Limit $taskIdLimit
    $taskDir = Join-Path $BaseDir $TaskId
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

$headerLines = @(
    "# Friction Log: $TaskId"
)
$headerLines += Write-MarkdownField -Label 'Date' -Value $stamp
$headerLines += Write-MarkdownField -Label 'Agent' -Value $agentDisplay
$headerLines += Write-MarkdownField -Label 'Skill path' -Value $SkillPath
$headerLines += Write-MarkdownField -Label 'Task ID' -Value $TaskId
$headerLines += Write-MarkdownField -Label 'Task summary' -Value $TaskSummary
if (-not [string]::IsNullOrWhiteSpace($ContextPath)) {
    $headerLines += Write-MarkdownField -Label 'Context path' -Value $ContextPath
}
$headerLines += Write-MarkdownField -Label 'Platform' -Value (Get-PlatformName)
$headerLines += Write-MarkdownField -Label 'Convention version' -Value '1.0.0'
$headerLines += '---'
Set-Content -Path $logFile -Value $headerLines -Encoding UTF8

if (-not (Test-Path $sessionFile)) {
    [System.IO.File]::WriteAllText($taskSummaryFile, $TaskSummary, [System.Text.UTF8Encoding]::new($false))
    @(
        "FRICTION_BASE_DIR=$BaseDir"
        "FRICTION_TASK_ID=$TaskId"
        "FRICTION_TASK_DIR=$taskDir"
        "FRICTION_TASK_SUMMARY_FILE=$taskSummaryFile"
        "FRICTION_INDEX_FILE=$indexFile"
    ) | Set-Content -Path $sessionFile -Encoding UTF8
}

$env:FRICTION_BASE_DIR = $BaseDir
$env:FRICTION_TASK_ID = $TaskId
$env:FRICTION_TASK_DIR = $taskDir
$env:FRICTION_TASK_SUMMARY = $TaskSummary
$env:FRICTION_TASK_SUMMARY_FILE = $taskSummaryFile
$env:FRICTION_LOG_FILE = $logFile
$env:FRICTION_INDEX_FILE = $indexFile

& "$PSScriptRoot/build-index.ps1" -TaskDir $taskDir | Out-Null

@(
    "FRICTION_BASE_DIR=$BaseDir"
    "FRICTION_TASK_ID=$TaskId"
    "FRICTION_TASK_DIR=$taskDir"
    "FRICTION_TASK_SUMMARY=$TaskSummary"
    "FRICTION_TASK_SUMMARY_FILE=$taskSummaryFile"
    "FRICTION_LOG_FILE=$logFile"
    "FRICTION_INDEX_FILE=$indexFile"
)
