param(
    [string]$SourceRef = "",
    [string]$InstructionText = "",
    [string]$ActionTaken = "",
    [string]$ExpectedOutcome = "",
    [string]$ActualOutcome = "",
    [string]$Hindsight = "",
    [string]$Reading = "",
    [string]$ToolName = "",
    [string]$Command = "",
    [string]$Stderr = "",
    [string]$StdoutExcerpt = "",
    [string]$ObservedSurface = "",
    [string]$Surface = "",
    [string]$Mode = "",
    [string]$RunEffect = "",
    [string]$GuidanceQuality = "",
    [string]$Confidence = "",
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/categorize.ps1 [options]

Output:
  observed_surface=<value>
  surface=<value>
  mode=<value>
  run_effect=<value>
  guidance_quality=<value>
  confidence=<value>
  derived_category=<surface/mode/run_effect>
  taxonomy_version=<value>
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

$rulesFile = if ($env:RULES_FILE) { $env:RULES_FILE } else {
    Join-Path (Split-Path -Parent (Split-Path -Parent $PSCommandPath)) 'data/categorization-rules.json'
}
if (-not (Test-Path -LiteralPath $rulesFile)) { throw "Categorization rules file not found: $rulesFile" }
$rules = Get-Content -LiteralPath $rulesFile -Raw | ConvertFrom-Json -ErrorAction Stop

# Normalize error message boilerplate and synonyms before pattern matching.
# This reduces wording-dependent classification variance for the same error class.
function Normalize-CategorizerText {
    param([string]$Text)
    $Text = $Text -replace '(?i)^(error|fatal|warning)\s*:\s*', 'error: '
    $Text = $Text -replace '(?i)\bno such file or directory\b', 'file not found'
    $Text = $Text -replace '\bENOENT\b', 'file not found'
    $Text = $Text -replace '(?i)\bcannot find\b', 'file not found'
    $Text = $Text -replace '(?i)\bcould not (find|locate)\b', 'file not found'
    $Text = $Text -replace '(?i)\bpermission denied\b', 'permission denied'
    $Text = $Text -replace '\bEACCES\b', 'permission denied'
    $Text = $Text -replace '(?i)\baccess denied\b', 'permission denied'
    $Text = $Text -replace '(?i)\bconnection refused\b', 'connection refused'
    $Text = $Text -replace '\bECONNREFUSED\b', 'connection refused'
    $Text = $Text -replace '(?i)\btimed? ?out\b', 'timeout'
    $Text = $Text -replace '\bETIMEDOUT\b', 'timeout'
    $Text = $Text -replace '(?i)\bdeadline exceeded\b', 'timeout'
    $Text = $Text -replace '\b(the|a|an) ', ''
    return $Text
}

$observationText = @($ActionTaken, $ActualOutcome, $ToolName, $Command, $Stderr) -join "`n"
$observationText = Normalize-CategorizerText $observationText
$observationText = $observationText.ToLowerInvariant()

$sourceText = @($SourceRef, $InstructionText, $ExpectedOutcome, $Hindsight, $Reading, $StdoutExcerpt) -join "`n"
$sourceText = Normalize-CategorizerText $sourceText
$sourceText = $sourceText.ToLowerInvariant()

$fullText = "$observationText`n$sourceText"

function Detect-Surface {
    param([string]$text)
    foreach ($entry in $rules.surface_patterns.PSObject.Properties) {
        foreach ($keyword in $entry.Value) {
            if ($text.Contains($keyword)) { return $entry.Name }
        }
    }
    return $rules.defaults.surface
}

$detectedObservedSurface = Detect-Surface $observationText
$detectedSurface = Detect-Surface $sourceText
if ($detectedSurface -eq 'unknown') { $detectedSurface = $detectedObservedSurface }
if ($detectedObservedSurface -eq 'unknown' -and $detectedSurface -ne 'unknown') { $detectedObservedSurface = $detectedSurface }

$detectedMode = $rules.defaults.mode
foreach ($entry in $rules.mode_patterns.PSObject.Properties) {
    $matched = $false
    foreach ($keyword in $entry.Value) {
        if ($fullText.Contains($keyword)) { $matched = $true; break }
    }
    if ($matched) { $detectedMode = $entry.Name; break }
}

$detectedRunEffect = $rules.defaults.run_effect
foreach ($entry in $rules.run_effect_patterns.PSObject.Properties) {
    $matched = $false
    foreach ($keyword in $entry.Value) {
        if ($fullText.Contains($keyword)) { $matched = $true; break }
    }
    if ($matched) { $detectedRunEffect = $entry.Name; break }
}

if ([string]::IsNullOrWhiteSpace($sourceText)) {
    $detectedGuidanceQuality = 0
} else {
    $detectedGuidanceQuality = $rules.defaults.guidance_quality
    foreach ($entry in $rules.guidance_quality_patterns.PSObject.Properties) {
        $matched = $false
        foreach ($keyword in $entry.Value) {
            if ($sourceText.Contains($keyword)) { $matched = $true; break }
        }
        if ($matched) { $detectedGuidanceQuality = [int]$entry.Name; break }
    }
}

if (-not [string]::IsNullOrWhiteSpace($ObservedSurface)) { $detectedObservedSurface = $ObservedSurface }
if (-not [string]::IsNullOrWhiteSpace($Surface)) { $detectedSurface = $Surface }
if (-not [string]::IsNullOrWhiteSpace($Mode)) { $detectedMode = $Mode }
if (-not [string]::IsNullOrWhiteSpace($RunEffect)) { $detectedRunEffect = ConvertTo-NormalizedRunEffect $RunEffect }
if (-not [string]::IsNullOrWhiteSpace($GuidanceQuality)) { $detectedGuidanceQuality = ConvertTo-NormalizedGuidanceQuality $GuidanceQuality }

# Confidence
if (-not [string]::IsNullOrWhiteSpace($Confidence)) {
    $detectedConfidence = ConvertTo-NormalizedConfidence $Confidence
} else {
    $detectedConfidence = 3
    if ($detectedSurface -eq 'unknown' -or $detectedMode -eq 'other') {
        $detectedConfidence = 2
    } elseif (($detectedGuidanceQuality -le 1 -and $detectedGuidanceQuality -gt 0) -or $detectedRunEffect -eq 'blocked') {
        $detectedConfidence = 4
    }
}

$derivedCategory = "$detectedSurface/$detectedMode/$detectedRunEffect"

"observed_surface=$detectedObservedSurface"
"surface=$detectedSurface"
"mode=$detectedMode"
"run_effect=$detectedRunEffect"
"guidance_quality=$detectedGuidanceQuality"
"confidence=$detectedConfidence"
"derived_category=$derivedCategory"
"taxonomy_version=$($script:TAXONOMY_VERSION)"
