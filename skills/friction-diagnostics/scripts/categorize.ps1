param(
    [string]$InstructionSource = "",
    [string]$InstructionText = "",
    [string]$ActionTaken = "",
    [string]$ExpectedOutcome = "",
    [string]$ActualOutcome = "",
    [string]$Interpretation = "",
    [string]$ToolName = "",
    [string]$Command = "",
    [string]$Stderr = "",
    [string]$StdoutExcerpt = "",
    [string]$ObservedSurface = "",
    [string]$Surface = "",
    [string]$Mode = "",
    [string]$RunEffect = "",
    [string]$GuidanceQuality = "",
    [string]$Impact = "",
    [string]$EvidenceType = "",
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
  evidence_type=<value>
  derived_category=<surface/mode/run_effect>
  tags=<comma-separated tags>
  taxonomy_version=<value>
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

$observationText = @($ActionTaken, $ActualOutcome, $ToolName, $Command, $Stderr) -join "`n"
$observationText = $observationText.ToLowerInvariant()

$sourceText = @($InstructionSource, $InstructionText, $ExpectedOutcome, $Interpretation, $StdoutExcerpt) -join "`n"
$sourceText = $sourceText.ToLowerInvariant()

$fullText = "$observationText`n$sourceText"

function Detect-Surface {
    param([string]$text)
    if ($text -match 'skill\.md|\.agents/skills| skill |skill path') { return 'skill' }
    if ($text -match 'agents\.md|instruction|prompt|dispatch|runbook') { return 'instructions' }
    if ($text -match 'mcp|model context protocol') { return 'mcp' }
    if ($text -match '\.ps1|\.sh|script |scripts/') { return 'script' }
    if ($text -match 'http|api |endpoint|server returned|rate limit|retry-after|webhook') { return 'external-service' }
    if ($text -match 'sandbox|dependency|filesystem|permission|cwd|env |environment') { return 'environment' }
    if ($text -match 'json|yaml|schema|field|csv|deserialize|serialize|payload|contract') { return 'data' }
    if ($text -match 'subagent|handoff|delegat|context window|compaction|lost context|workflow') { return 'workflow' }
    if ($text -match 'algorithm|reasoning|logic|assumption|misread|interpreted|interpretation') { return 'logic' }
    if ($text -match 'traceback|stacktrace|exception|module|compile|test |runtime|function|code ') { return 'code' }
    if ($text -match 'cli|command |subcommand|flag |option |executable') { return 'tool' }
    return 'unknown'
}

$detectedObservedSurface = Detect-Surface $observationText
$detectedSurface = Detect-Surface $sourceText
if ($detectedSurface -eq 'unknown') { $detectedSurface = $detectedObservedSurface }
if ($detectedObservedSurface -eq 'unknown' -and $detectedSurface -ne 'unknown') { $detectedObservedSurface = $detectedSurface }

$detectedMode = 'other'
if ($fullText -match 'ambiguous|unclear|underspecified|vague|not sure|uncertain') { $detectedMode = 'ambiguity' }
elseif ($fullText -match 'contradict|inconsistent|does not match docs|did not match docs|differs from docs') { $detectedMode = 'contradiction' }
elseif ($fullText -match 'unknown dispatch role|unknown |unrecognized|invalid choice|could not resolve|cannot resolve|no command named|no such subcommand') { $detectedMode = 'name-resolution' }
elseif ($fullText -match 'lost context|missing context|lacked context|forgot|compaction') { $detectedMode = 'context-loss' }
elseif ($fullText -match 'not found|no such file|missing|does not exist|absent') { $detectedMode = 'missing' }
elseif ($fullText -match 'permission denied|operation not permitted') { $detectedMode = 'permission' }
elseif ($fullText -match 'unauthorized|authentication|invalid token') { $detectedMode = 'auth' }
elseif ($fullText -match 'timed out|timeout|deadline exceeded') { $detectedMode = 'timeout' }
elseif ($fullText -match 'traceback|stacktrace|stack backtrace|panic|segmentation fault|crash|exception') { $detectedMode = 'crash' }
elseif ($fullText -match 'json|yaml|schema|parse error|type mismatch|deserialize|serialize|shape mismatch') { $detectedMode = 'schema' }
elseif ($fullText -match 'validation|invalid|required|assertion failed') { $detectedMode = 'validation' }
elseif ($fullText -match 'wrong output|unexpected output|output mismatch|did not match|rendered incorrectly|misleading output') { $detectedMode = 'output-mismatch' }
elseif ($fullText -match 'flaky|sometimes|intermittent|nondetermin|non-determin') { $detectedMode = 'nondeterminism' }
elseif ($fullText -match 'slow|performance|hang|thrash|looped|repeated retries') { $detectedMode = 'performance' }

$detectedRunEffect = 'continued'
if ($fullText -match 'rate limit|quota|too many requests|retry-after|http 403|timed out|timeout|not found|missing|permission denied|unauthorized|forbidden|traceback|stacktrace|panic|crash|error:|failed|cannot |could not |unable to |blocked') { $detectedRunEffect = 'blocked' }
elseif ($fullText -match 'retry|retries|thrash|looped|repeated|extra steps|flaky') { $detectedRunEffect = 'noisy' }
elseif ($fullText -match 'partial|workaround|fallback|degraded|succeeded but|continued') { $detectedRunEffect = 'degraded' }

$detectedGuidanceQuality = 'clear'
if ([string]::IsNullOrWhiteSpace($sourceText)) { $detectedGuidanceQuality = 'not-applicable' }
elseif ($sourceText -match 'ambiguous|unclear|underspecified|uncertain') { $detectedGuidanceQuality = 'ambiguous' }
elseif ($sourceText -match 'contradict|inconsistent|wrong output|unexpected output|output mismatch|misleading|did not match docs') { $detectedGuidanceQuality = 'misleading' }

# Legacy --Impact mapping
switch ($Impact) {
    { $_ -in 'blocked', 'degraded', 'noisy', 'continued' } { $RunEffect = $Impact }
    'confusing' {
        $GuidanceQuality = 'ambiguous'
        if ([string]::IsNullOrWhiteSpace($RunEffect)) { $RunEffect = 'continued' }
    }
    'misleading' {
        $GuidanceQuality = 'misleading'
        if ([string]::IsNullOrWhiteSpace($RunEffect)) { $RunEffect = 'degraded' }
    }
}

if (-not [string]::IsNullOrWhiteSpace($ObservedSurface)) { $detectedObservedSurface = $ObservedSurface }
if (-not [string]::IsNullOrWhiteSpace($Surface)) { $detectedSurface = $Surface }
if (-not [string]::IsNullOrWhiteSpace($Mode)) { $detectedMode = $Mode }
if (-not [string]::IsNullOrWhiteSpace($RunEffect)) { $detectedRunEffect = ConvertTo-NormalizedRunEffect $RunEffect }
if (-not [string]::IsNullOrWhiteSpace($GuidanceQuality)) { $detectedGuidanceQuality = ConvertTo-NormalizedGuidanceQuality $GuidanceQuality }

# Evidence type inference
if (-not [string]::IsNullOrWhiteSpace($EvidenceType)) {
    if ($EvidenceType -in 'execution', 'instruction', 'handoff', 'mixed') {
        $detectedEvidenceType = $EvidenceType
    } else {
        $detectedEvidenceType = 'mixed'
    }
} elseif ($fullText -match 'handoff|delegat|remaining files') {
    $detectedEvidenceType = 'handoff'
} elseif (-not [string]::IsNullOrWhiteSpace("$ActualOutcome$ActionTaken$ToolName$Command$Stderr")) {
    $detectedEvidenceType = 'execution'
} elseif (-not [string]::IsNullOrWhiteSpace("$InstructionSource$InstructionText$ExpectedOutcome")) {
    $detectedEvidenceType = 'instruction'
} else {
    $detectedEvidenceType = 'mixed'
}

# Confidence
if (-not [string]::IsNullOrWhiteSpace($Confidence)) {
    $detectedConfidence = $Confidence
} else {
    $detectedConfidence = 'medium'
    if ($detectedSurface -eq 'unknown' -or $detectedObservedSurface -eq 'unknown' -or $detectedMode -eq 'other') {
        $detectedConfidence = 'low'
    } elseif ($detectedGuidanceQuality -eq 'misleading' -or $detectedRunEffect -eq 'blocked') {
        $detectedConfidence = 'high'
    }
}

$tagText = "$fullText`n$ToolName`n$Command".ToLowerInvariant()
$tags = Get-CategoryTags -Surface $detectedSurface -Mode $detectedMode -RunEffect $detectedRunEffect -GuidanceQuality $detectedGuidanceQuality -TextLower $tagText
$derivedCategory = "$detectedSurface/$detectedMode/$detectedRunEffect"

"observed_surface=$detectedObservedSurface"
"surface=$detectedSurface"
"mode=$detectedMode"
"run_effect=$detectedRunEffect"
"guidance_quality=$detectedGuidanceQuality"
"confidence=$detectedConfidence"
"evidence_type=$detectedEvidenceType"
"derived_category=$derivedCategory"
"tags=$tags"
"taxonomy_version=$($script:TAXONOMY_VERSION)"
