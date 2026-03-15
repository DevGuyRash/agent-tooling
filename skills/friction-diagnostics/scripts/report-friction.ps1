param(
    [string]$LogFile = $env:FRICTION_LOG_FILE,
    [string]$Title = "",
    [string]$InstructionSource = "",
    [string]$InstructionText = "",
    [string]$ActionTaken = "",
    [string]$ExpectedOutcome = "",
    [string]$ActualOutcome = "",
    [string]$Interpretation = "",
    [string]$Surface = "",
    [string]$Mode = "",
    [string]$Impact = "",
    [string]$Tags = "",
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/report-friction.ps1 -LogFile $env:FRICTION_LOG_FILE -Title "..." [fields]
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

if ([string]::IsNullOrWhiteSpace($LogFile)) { throw "-LogFile is required" }
if (-not (Test-Path $LogFile)) { throw "Log file not found: $LogFile" }

$auto = & "$PSScriptRoot/categorize.ps1" `
    -InstructionSource $InstructionSource `
    -InstructionText $InstructionText `
    -ActionTaken $ActionTaken `
    -ExpectedOutcome $ExpectedOutcome `
    -ActualOutcome $ActualOutcome `
    -Interpretation $Interpretation `
    -Surface $Surface `
    -Mode $Mode `
    -Impact $Impact

$autoMap = @{}
foreach ($line in $auto) {
    if ($line -match '^(?<key>[^=]+)=(?<value>.*)$') {
        $autoMap[$matches.key] = $matches.value
    }
}

$Surface = $autoMap['surface']
$Mode = $autoMap['mode']
$Impact = $autoMap['impact']

$mergedTags = $autoMap['tags']
if (-not [string]::IsNullOrWhiteSpace($Tags)) {
    foreach ($item in ($Tags -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
        $mergedTags = Add-CsvItem $mergedTags $item
    }
}
$Tags = $mergedTags

if ([string]::IsNullOrWhiteSpace($Title)) {
    $sourceTitle = Get-FirstLine $ActualOutcome
    if ([string]::IsNullOrWhiteSpace($sourceTitle)) { $sourceTitle = $Mode }
    $Title = Get-TruncatedLine -Text $sourceTitle -Limit 72
}

$content = Get-Content -Path $LogFile -Raw
$entryCount = ([regex]::Matches($content, '^## Entry \d+:', [System.Text.RegularExpressions.RegexOptions]::Multiline)).Count
$entryNumber = $entryCount + 1
$recorded = Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'

$lines = @(
    ""
    "## Entry $entryNumber: $Title"
)
$lines += Write-MarkdownField -Label 'Recorded' -Value $recorded
$lines += Write-MarkdownField -Label 'Category' -Value "$Surface/$Mode/$Impact"
$lines += Write-MarkdownField -Label 'Tags' -Value $Tags
$lines += Write-MarkdownField -Label 'Instruction source' -Value $InstructionSource
$lines += Write-MarkdownField -Label 'Instruction text' -Value $InstructionText
$lines += Write-MarkdownField -Label 'Action taken' -Value $ActionTaken
$lines += Write-MarkdownField -Label 'Expected outcome' -Value $ExpectedOutcome
$lines += Write-MarkdownField -Label 'Actual outcome' -Value $ActualOutcome
$lines += Write-MarkdownField -Label 'Interpretation' -Value $Interpretation
$lines += '---'

Add-Content -Path $LogFile -Value $lines -Encoding UTF8

$taskDir = Split-Path -Parent (Split-Path -Parent $LogFile)
& "$PSScriptRoot/build-index.ps1" -TaskDir $taskDir | Out-Null
