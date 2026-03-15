param(
    [string]$InstructionSource = "",
    [string]$InstructionText = "",
    [string]$ActionTaken = "",
    [string]$ExpectedOutcome = "",
    [string]$ActualOutcome = "",
    [string]$Interpretation = "",
    [string]$Surface = "",
    [string]$Mode = "",
    [string]$Impact = "",
    [switch]$Help
)

if ($Help) {
@"
Usage:
  scripts/categorize.ps1 -InstructionSource TEXT -InstructionText TEXT -ActionTaken TEXT -ActualOutcome TEXT -Interpretation TEXT [-Surface VALUE] [-Mode VALUE] [-Impact VALUE]

Output:
  surface=<value>
  mode=<value>
  impact=<value>
  tags=<comma-separated tags>
"@
    exit 0
}

. "$PSScriptRoot/_Common.ps1"

$text = @(
    $InstructionSource
    $InstructionText
    $ActionTaken
    $ExpectedOutcome
    $ActualOutcome
    $Interpretation
) -join "`n"
$textLower = $text.ToLowerInvariant()

$surface = "unknown"
if ($textLower -match 'skill\.md|\.agents/skills| skill |skill path') { $surface = "skill" }
elseif ($textLower -match 'agents\.md|instruction|prompt|dispatch') { $surface = "instructions" }
elseif ($textLower -match 'mcp|model context protocol') { $surface = "mcp" }
elseif ($textLower -match '\.ps1|\.sh|script |scripts/') { $surface = "script" }
elseif ($textLower -match 'http|api |endpoint|server returned|rate limit|webhook') { $surface = "external-service" }
elseif ($textLower -match 'sandbox|dependency|filesystem|permission|path|cwd|env |environment') { $surface = "environment" }
elseif ($textLower -match 'json|yaml|schema|field|csv|deserialize|serialize|payload|contract') { $surface = "data" }
elseif ($textLower -match 'subagent|handoff|routing|delegat|context window|compaction|lost context|workflow') { $surface = "workflow" }
elseif ($textLower -match 'algorithm|reasoning|logic|assumption|misread|interpreted|interpretation') { $surface = "logic" }
elseif ($textLower -match 'traceback|stacktrace|exception|module|compile|test |runtime|code |function') { $surface = "code" }
elseif ($textLower -match 'cli|command |executable|subcommand|flag |option ') { $surface = "tool" }

$mode = "other"
if ($textLower -match 'rate limit|quota|too many requests|x-ratelimit-|retry-after') { $mode = "other" }
elseif ($textLower -match 'ambiguous|unclear|underspecified|vague|not sure|uncertain') { $mode = "ambiguity" }
elseif ($textLower -match 'contradict|inconsistent|does not match docs|did not match docs|differs from docs') { $mode = "contradiction" }
elseif ($textLower -match 'unknown dispatch role|unknown |unrecognized|invalid choice|could not resolve|cannot resolve|no command named|no such subcommand') { $mode = "name-resolution" }
elseif ($textLower -match 'lost context|missing context|lacked context|forgot|compaction') { $mode = "context-loss" }
elseif ($textLower -match 'not found|no such file|missing|does not exist|absent') { $mode = "missing" }
elseif ($textLower -match 'permission denied|operation not permitted') { $mode = "permission" }
elseif ($textLower -match 'unauthorized|forbidden|401|403|token|credential|authentication') { $mode = "auth" }
elseif ($textLower -match 'timed out|timeout|deadline exceeded') { $mode = "timeout" }
elseif ($textLower -match 'traceback|stacktrace|stack backtrace|panic|segmentation fault|crash|exception') { $mode = "crash" }
elseif ($textLower -match 'json|yaml|schema|parse error|type mismatch|deserialize|serialize|shape mismatch') { $mode = "schema" }
elseif ($textLower -match 'validation|invalid|required|assertion failed|failed validation') { $mode = "validation" }
elseif ($textLower -match 'wrong output|unexpected output|output mismatch|did not match|rendered incorrectly|misleading output') { $mode = "output-mismatch" }
elseif ($textLower -match 'flaky|sometimes|intermittent|nondetermin|non-determin') { $mode = "nondeterminism" }
elseif ($textLower -match 'slow|performance|hang|thrash|looped|repeated retries') { $mode = "performance" }

$impact = "degraded"
if ($textLower -match 'rate limit|quota|too many requests|x-ratelimit-|retry-after|429|http 403') { $impact = "blocked" }
elseif ($textLower -match 'ambiguous|unclear|underspecified|uncertain|missing context|lacked context|lost context') { $impact = "confusing" }
elseif ($textLower -match 'unknown dispatch role|timed out|timeout|not found|missing|permission denied|unauthorized|forbidden|traceback|stacktrace|panic|crash|error:|failed|cannot |could not |unable to |blocked') { $impact = "blocked" }
elseif ($textLower -match 'contradict|inconsistent|wrong output|unexpected output|output mismatch|misleading|did not match docs') { $impact = "misleading" }
elseif ($textLower -match 'retry|retries|thrash|looped|repeated|extra steps') { $impact = "noisy" }
elseif ($textLower -match 'partial|workaround|degraded|succeeded but|continued') { $impact = "degraded" }

if (-not [string]::IsNullOrWhiteSpace($Surface)) { $surface = $Surface }
if (-not [string]::IsNullOrWhiteSpace($Mode)) { $mode = $Mode }
if (-not [string]::IsNullOrWhiteSpace($Impact)) { $impact = $Impact }

$tags = Get-CategoryTags -Surface $surface -Mode $mode -Impact $impact -TextLower $textLower

"surface=$surface"
"mode=$mode"
"impact=$impact"
"tags=$tags"
