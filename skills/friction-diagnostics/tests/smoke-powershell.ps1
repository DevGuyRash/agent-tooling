Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
. "$root/scripts/_Common.ps1"
$baseDir = Join-Path ([System.IO.Path]::GetTempPath()) ("agent-friction-ps-smoke-{0}" -f [System.Guid]::NewGuid().ToString('N'))
$taskId = 'smoke-task'
$taskSummary = "PowerShell multiline summary`nsecond line"

try {
    if ((Get-ShortSha256 'abc') -ne 'ba7816bf') { throw 'Get-ShortSha256 should return the first 8 hex chars of the SHA256 digest' }

    & "$root/scripts/init-log.ps1" `
        -BaseDir $baseDir `
        -TaskId $taskId `
        -TaskSummary $taskSummary `
        -Agent 'orchestrator' `
        -SkillPath $root | Tee-Object -Variable initOutput | Out-Null

    $outputMap = @{}
    $initOutput | ForEach-Object {
        if ($_ -match '^(FRICTION_[A-Z_]+)=(.*)$') {
            $outputMap[$matches[1]] = $matches[2]
        }
    }

    $taskDir = Join-Path $baseDir $taskId
    $sessionFile = Join-Path $taskDir 'SESSION.txt'
    $summaryFile = Join-Path $taskDir 'TASK_SUMMARY.txt'
    $indexFile = Join-Path $taskDir 'INDEX.md'

    if (-not (Test-Path $sessionFile)) { throw "SESSION.txt missing: $sessionFile" }
    if (-not (Test-Path $summaryFile)) { throw "TASK_SUMMARY.txt missing: $summaryFile" }

    $sessionLines = Get-Content $sessionFile
    if ($sessionLines.Count -ne 15) { throw "SESSION.txt should contain 15 task-scoped records, found $($sessionLines.Count)" }
    if (-not ($sessionLines -match '^FRICTION_TASK_SUMMARY_FILE=')) { throw 'SESSION.txt missing FRICTION_TASK_SUMMARY_FILE' }
    if ($sessionLines -match '^FRICTION_TASK_SUMMARY=') { throw 'SESSION.txt still contains inline task summary' }
    if ($sessionLines -match '^FRICTION_TASK_DESCRIPTOR=') { throw 'SESSION.txt should not contain FRICTION_TASK_DESCRIPTOR' }
    if (-not ($sessionLines -match '^FRICTION_TASK_JSON=')) { throw 'SESSION.txt missing FRICTION_TASK_JSON' }
    if (-not ($sessionLines -match '^FRICTION_EVENTS_FILE=')) { throw 'SESSION.txt missing FRICTION_EVENTS_FILE' }
    if (-not ($sessionLines -match '^FRICTION_INCIDENTS_FILE=')) { throw 'SESSION.txt missing FRICTION_INCIDENTS_FILE' }
    if (-not ($sessionLines -match '^FRICTION_STORAGE_MODE=')) { throw 'SESSION.txt missing FRICTION_STORAGE_MODE' }
    if (-not ($sessionLines -match '^FRICTION_CAPTURE_MODE=')) { throw 'SESSION.txt missing FRICTION_CAPTURE_MODE' }
    if (-not ($sessionLines -match '^FRICTION_PRIVACY_TIER=')) { throw 'SESSION.txt missing FRICTION_PRIVACY_TIER' }
    if (-not ($sessionLines -match '^FRICTION_EXPORT_DIR=')) { throw 'SESSION.txt missing FRICTION_EXPORT_DIR' }
    if (-not ($sessionLines -match '^FRICTION_SANITIZED_EXPORT=')) { throw 'SESSION.txt missing FRICTION_SANITIZED_EXPORT' }
    if (-not ($sessionLines -match '^FRICTION_SKILL_PATH=')) { throw 'SESSION.txt missing FRICTION_SKILL_PATH' }
    if (-not ($sessionLines -match '^FRICTION_CONTEXT_PATH=')) { throw 'SESSION.txt missing FRICTION_CONTEXT_PATH' }
    if ($outputMap['FRICTION_TASK_SUMMARY_FILE'] -ne $summaryFile) { throw 'init-log.ps1 did not emit FRICTION_TASK_SUMMARY_FILE' }
    if ($outputMap['FRICTION_TASK_SUMMARY'] -ne 'PowerShell multiline summary') { throw 'line-oriented output should expose only the first summary line when parsed this way' }
    if ($outputMap['FRICTION_LOG_FILE'] -ne '') { throw 'init-log.ps1 should not emit a log file before the first event' }
    if ($outputMap['FRICTION_TASK_DESCRIPTOR'] -ne '') { throw 'init-log.ps1 should not emit a descriptor before the first event' }

    # Verify manifest-only init artifacts
    $eventsFile = Join-Path $taskDir 'events.jsonl'
    $taskJsonFile = Join-Path $taskDir 'task.json'
    $incidentsFile = Join-Path $taskDir 'incidents.json'
    $exportsDir = Join-Path $taskDir 'exports'
    if (-not (Test-Path $taskJsonFile)) { throw "task.json missing: $taskJsonFile" }
    if (Test-Path $eventsFile) { throw 'events.jsonl should not exist immediately after init' }
    if (Test-Path $incidentsFile) { throw 'incidents.json should not exist immediately after init' }
    if (Test-Path $exportsDir) { throw 'exports/ should not exist immediately after init' }
    if (Test-Path $indexFile) { throw 'INDEX.md should not exist immediately after init' }

    $summaryText = [System.IO.File]::ReadAllText($summaryFile)
    if ($summaryText -ne $taskSummary) { throw 'TASK_SUMMARY.txt did not preserve the multiline summary' }
    $taskJsonText = [System.IO.File]::ReadAllText($taskJsonFile)
    if ($taskJsonText -notmatch '"task_summary":"PowerShell multiline summary\\nsecond line"') { throw 'task.json should store the plain multiline task_summary field' }
    if ($taskJsonText -notmatch '"artifacts_materialized":false') { throw 'task.json should record artifacts_materialized=false before the first event' }
    if ($taskJsonText -match '_b64"') { throw 'task.json should not store base64 summary fields' }

    $categorizeLines = & "$root/scripts/categorize.ps1" `
        -InstructionSource 'SKILL.md:12' `
        -InstructionText 'Use the MCP tool foo'
    if (-not ($categorizeLines -contains 'surface=skill')) { throw 'categorize.ps1 should prefer skill when SKILL.md text mentions MCP' }

    $categorizeLines = & "$root/scripts/categorize.ps1" `
        -InstructionSource 'AGENTS.md:7' `
        -InstructionText 'Prompt says to use the MCP tool foo'
    if (-not ($categorizeLines -contains 'surface=instructions')) { throw 'categorize.ps1 should prefer instructions when AGENTS.md text mentions MCP' }

    $categorizeLines = & "$root/scripts/categorize.ps1" `
        -InstructionSource 'Orchestrator handoff message' `
        -InstructionText 'Continue the review of the remaining files.' `
        -ActionTaken 'Started the delegated review after receiving the handoff.' `
        -ExpectedOutcome 'The handoff would include the file list needed to continue.' `
        -ActualOutcome 'The handoff was missing context about which files were already reviewed, so I re-scanned the repository.' `
        -Interpretation 'The subagent lacked context it needed to continue from the prior step.'
    if (-not ($categorizeLines -contains 'surface=workflow')) { throw 'categorize.ps1 should classify handoff context loss as workflow surface' }
    if (-not ($categorizeLines -contains 'mode=context-loss')) { throw 'categorize.ps1 should classify missing context as context-loss mode' }
    if (-not ($categorizeLines -contains 'run_effect=blocked')) { throw 'categorize.ps1 should classify missing context as blocked run_effect' }
    if (-not ($categorizeLines -contains 'guidance_quality=clear')) { throw 'categorize.ps1 should classify missing context as clear guidance_quality' }

    $categorizeLines = & "$root/scripts/categorize.ps1" `
        -InstructionSource 'scripts/build.sh' `
        -InstructionText 'Open the generated manifest file.' `
        -ActionTaken 'Tried to read ./build/manifest.json.' `
        -ExpectedOutcome 'The manifest file exists and can be read.' `
        -ActualOutcome 'The manifest file was missing, so the step could not continue.' `
        -Interpretation 'The expected artifact was absent and blocked the next step.'
    if (-not ($categorizeLines -contains 'mode=missing')) { throw 'categorize.ps1 should keep generic missing cases as missing mode' }
    if (-not ($categorizeLines -contains 'run_effect=blocked')) { throw 'categorize.ps1 should keep generic missing cases as blocked run_effect' }

    & "$root/scripts/build-index.ps1" -TaskDir $taskDir | Out-Null
    if (Test-Path $indexFile) { throw 'build-index.ps1 should remove INDEX.md when no events exist' }

    $eventJsonPath = Join-Path $taskDir 'event-input.json'
    [System.IO.File]::WriteAllText($eventJsonPath, @'
{"title":"Path ingest smoke","instruction_source":"test","instruction_text":"Load event fields from a JSON file path.","action_taken":"Reported friction with -FromJson.","expected_outcome":"PowerShell should accept a JSON file path without shell-escaping payload text.","actual_outcome":"The event was loaded from disk and recorded.","interpretation":"A file path is a shell-safe transport for structured input.","surface":"workflow","mode":"ambiguity","impact":"confusing","tags":"from-json"}
'@, [System.Text.UTF8Encoding]::new($false))

    & "$root/scripts/report-friction.ps1" `
        -TaskDir $taskDir `
        -Agent 'orchestrator' `
        -FromJson $eventJsonPath | Out-Null

    $logFile = Get-ChildItem -Path $taskDir -Recurse -Filter '*.md' -File | Where-Object { $_.Name -ne 'INDEX.md' } | Select-Object -First 1
    if ($null -eq $logFile) { throw "log file missing under $taskDir after first event" }
    $descriptorFile = [System.IO.Path]::ChangeExtension($logFile.FullName, 'descriptor.json')
    if (-not (Test-Path $descriptorFile)) { throw "per-agent descriptor missing after first event: $descriptorFile" }
    if (-not (Test-Path $eventsFile)) { throw "events.jsonl missing after first event: $eventsFile" }
    if (-not (Test-Path $incidentsFile)) { throw "incidents.json missing after first event: $incidentsFile" }
    if (-not (Test-Path $exportsDir)) { throw "exports/ missing after first event: $exportsDir" }
    if (-not (Test-Path $indexFile)) { throw "INDEX.md missing after first event: $indexFile" }

    $logText = [System.IO.File]::ReadAllText($logFile.FullName)
    if ($logText -notmatch '\*\*Platform:\*\* [^\r\n]+') { throw 'log header missing platform field' }
    if ($logText -notmatch '## Event 1: Path ingest smoke') { throw 'log file should contain the first recorded event' }

    $eventsText = [System.IO.File]::ReadAllText($eventsFile)
    if ($eventsText -notmatch '"title":"Path ingest smoke"') { throw 'events.jsonl should store plain title strings' }
    if ($eventsText -notmatch '"instruction_text":"Load event fields from a JSON file path\."') { throw 'events.jsonl should store plain instruction_text strings' }
    if ($eventsText -match '_b64"') { throw 'events.jsonl should not store base64 payload fields' }

    $taskJsonText = [System.IO.File]::ReadAllText($taskJsonFile)
    if ($taskJsonText -notmatch '"artifacts_materialized":true') { throw 'task.json should flip artifacts_materialized after first-event materialization' }

    $indexText = [System.IO.File]::ReadAllText($indexFile)
    if ($indexText -notmatch '\*\*Entries:\*\* 1') { throw 'INDEX.md should count entries from events.jsonl' }
    if ($indexText -notmatch '- ``workflow/ambiguity/continued`` - 1') { throw 'INDEX.md should aggregate categories from events.jsonl' }
    if ($indexText -notmatch '- ``[^`]+orchestrator[^`]*`` - 1 entries') { throw 'INDEX.md should aggregate log counts from events.jsonl' }

    & "$root/scripts/report-friction.ps1" `
        -TaskDir $taskDir `
        -Agent 'orchestrator' `
        -Title 'Category sort alpha one' `
        -InstructionSource 'test' `
        -InstructionText 'Exercise alphabetical category ordering for tied counts.' `
        -ActionTaken 'Recorded a skill classification entry.' `
        -ExpectedOutcome 'The category list sorts tied counts by name.' `
        -ActualOutcome 'A skill entry was recorded.' `
        -Interpretation 'Skill categories should sort ahead of workflow when counts tie.' `
        -Surface 'skill' `
        -Mode 'ambiguity' `
        -Impact 'confusing' | Out-Null

    & "$root/scripts/report-friction.ps1" `
        -TaskDir $taskDir `
        -Agent 'orchestrator' `
        -Title 'Category sort alpha two' `
        -InstructionSource 'test' `
        -InstructionText 'Exercise alphabetical category ordering for tied counts.' `
        -ActionTaken 'Recorded a workflow classification entry.' `
        -ExpectedOutcome 'The category list sorts tied counts by name.' `
        -ActualOutcome 'A workflow entry was recorded.' `
        -Interpretation 'Workflow categories should sort after skill when counts tie.' `
        -Surface 'workflow' `
        -Mode 'ambiguity' `
        -Impact 'confusing' | Out-Null

    & "$root/scripts/report-friction.ps1" `
        -TaskDir $taskDir `
        -Agent 'orchestrator' `
        -Title 'Category sort primary count' `
        -InstructionSource 'test' `
        -InstructionText 'Exercise primary count ordering for category totals.' `
        -ActionTaken 'Recorded another skill classification entry.' `
        -ExpectedOutcome 'The highest-count category appears first.' `
        -ActualOutcome 'A second skill entry was recorded.' `
        -Interpretation 'Count ordering should outrank alphabetical ordering.' `
        -Surface 'skill' `
        -Mode 'ambiguity' `
        -Impact 'confusing' | Out-Null

    & "$root/scripts/report-friction.ps1" `
        -TaskDir $taskDir `
        -Agent 'orchestrator' `
        -Title 'Inline category prose should not aggregate' `
        -InstructionSource 'test' `
        -InstructionText 'Keep inline category text inside other fields from affecting category totals.' `
        -ActionTaken 'Recorded a workflow classification entry with inline category prose in the actual outcome.' `
        -ExpectedOutcome 'Only the real category field should contribute to category aggregates.' `
        -ActualOutcome 'The generated note quoted **Derived category:** skill/ambiguity/continued inside the prose, but this line is not a category field.' `
        -Interpretation 'Index rebuild should count only lines that start with the category field marker.' `
        -Surface 'workflow' `
        -Mode 'ambiguity' `
        -Impact 'confusing' | Out-Null

    & "$root/scripts/build-index.ps1" -TaskDir $taskDir | Out-Null
    $indexText = [System.IO.File]::ReadAllText($indexFile)
    $skillCategoryIndex = $indexText.IndexOf('- ``skill/ambiguity/continued`` - 2')
    $workflowCategoryIndex = $indexText.IndexOf('- ``workflow/ambiguity/continued`` - 2')
    if ($skillCategoryIndex -lt 0) { throw 'INDEX.md missing the expected skill category aggregate' }
    if ($workflowCategoryIndex -lt 0) { throw 'INDEX.md missing the expected workflow category aggregate' }
    if ($skillCategoryIndex -ge $workflowCategoryIndex) { throw 'INDEX.md should sort categories by descending count before name' }
    if ($indexText -match '(?m)^- ``The generated note quoted \*\*Derived category:\*\* skill/ambiguity/continued inside the prose, but this line is not a category field\.`` - ') {
        throw 'INDEX.md should not aggregate inline category prose as its own category'
    }

    $autoBaseDir = Join-Path ([System.IO.Path]::GetTempPath()) ("agent-friction-ps-auto-{0}" -f [System.Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $autoBaseDir | Out-Null
    $nameMax = 255
    try {
        $autoInitOne = & "$root/scripts/init-log.ps1" `
            -BaseDir $autoBaseDir `
            -TaskSummary 'Review the current code changes' `
            -Agent 'orchestrator' `
            -SkillPath $root
        $autoInitTwo = & "$root/scripts/init-log.ps1" `
            -BaseDir $autoBaseDir `
            -TaskSummary 'Review the current code changes' `
            -Agent 'orchestrator' `
            -SkillPath $root

        $autoMapOne = @{}
        $autoInitOne | ForEach-Object {
            if ($_ -match '^(FRICTION_[A-Z_]+)=(.*)$') {
                $autoMapOne[$matches[1]] = $matches[2]
            }
        }
        $autoMapTwo = @{}
        $autoInitTwo | ForEach-Object {
            if ($_ -match '^(FRICTION_[A-Z_]+)=(.*)$') {
                $autoMapTwo[$matches[1]] = $matches[2]
            }
        }

        if ($autoMapOne['FRICTION_TASK_ID'] -ne $autoMapTwo['FRICTION_TASK_ID']) { throw 'matching task summaries should reuse the existing task id by default' }
        if ($autoMapOne['FRICTION_TASK_DIR'] -ne $autoMapTwo['FRICTION_TASK_DIR']) { throw 'matching task summaries should reuse the existing task directory by default' }
        if (-not (Test-Path (Join-Path $autoMapOne['FRICTION_TASK_DIR'] 'SESSION.txt'))) { throw 'first auto-id task is missing SESSION.txt' }
        if (-not (Test-Path (Join-Path $autoMapTwo['FRICTION_TASK_DIR'] 'SESSION.txt'))) { throw 'second auto-id task is missing SESSION.txt' }
        if ($autoMapOne['FRICTION_LOG_FILE'] -ne '') { throw 'auto-init should remain manifest-only before the first event' }
        if ($autoMapTwo['FRICTION_LOG_FILE'] -ne '') { throw 'reused auto-init should remain manifest-only before the first event' }

        & "$root/scripts/report-friction.ps1" `
            -TaskDir $autoMapOne['FRICTION_TASK_DIR'] `
            -Agent 'orchestrator' `
            -Title 'Auto id uniqueness one' `
            -InstructionSource 'test' `
            -InstructionText 'Ensure auto-generated task IDs isolate unrelated runs.' `
            -ActionTaken 'Initialized the first task without an explicit task id.' `
            -ExpectedOutcome 'The first task reuses its session directory.' `
            -ActualOutcome 'The shared task directory was reused for the first run.' `
            -Interpretation 'Repeated generic summaries should converge on the same session unless -NoReuse is set.' | Out-Null
        & "$root/scripts/report-friction.ps1" `
            -TaskDir $autoMapTwo['FRICTION_TASK_DIR'] `
            -Agent 'subagent' `
            -Title 'Auto id uniqueness two' `
            -InstructionSource 'test' `
            -InstructionText 'Ensure auto-generated task IDs isolate unrelated runs.' `
            -ActionTaken 'Initialized the second task with the same summary.' `
            -ExpectedOutcome 'The second task joins the existing directory with its own lazy log.' `
            -ActualOutcome 'A second agent log was created inside the reused task directory.' `
            -Interpretation 'A matching summary should cause reuse of the prior session.' | Out-Null

        $autoIndexOne = [System.IO.File]::ReadAllText($autoMapOne['FRICTION_INDEX_FILE'])
        if ($autoIndexOne -notmatch '\*\*Log files:\*\* 2') { throw 'reused auto-id index should report two log files after two agents log' }
        if ($autoIndexOne -notmatch '\*\*Entries:\*\* 2') { throw 'reused auto-id index should report two entries after two agents log' }

        $longTaskSummary = ((1..20 | ForEach-Object { 'This is a deliberately long natural language task summary' }) -join ' ')
        $longInitOne = & "$root/scripts/init-log.ps1" `
            -BaseDir $autoBaseDir `
            -TaskSummary $longTaskSummary `
            -Agent 'orchestrator' `
            -SkillPath $root
        $longInitTwo = & "$root/scripts/init-log.ps1" `
            -BaseDir $autoBaseDir `
            -TaskSummary $longTaskSummary `
            -Agent 'orchestrator' `
            -SkillPath $root

        $longMapOne = @{}
        $longInitOne | ForEach-Object {
            if ($_ -match '^(FRICTION_[A-Z_]+)=(.*)$') {
                $longMapOne[$matches[1]] = $matches[2]
            }
        }
        $longMapTwo = @{}
        $longInitTwo | ForEach-Object {
            if ($_ -match '^(FRICTION_[A-Z_]+)=(.*)$') {
                $longMapTwo[$matches[1]] = $matches[2]
            }
        }

        if ($longMapOne['FRICTION_TASK_ID'] -ne $longMapTwo['FRICTION_TASK_ID']) { throw 'long matching summaries should still reuse the same task id' }
        if (-not (Test-Path $longMapOne['FRICTION_TASK_DIR'])) { throw 'first long-summary task directory is missing' }
        if (-not (Test-Path $longMapTwo['FRICTION_TASK_DIR'])) { throw 'second long-summary task directory is missing' }
        if ([System.IO.Path]::GetFileName($longMapOne['FRICTION_TASK_DIR']).Length -gt $nameMax) { throw 'first long-summary task directory component exceeded NAME_MAX' }
        if ([System.IO.Path]::GetFileName($longMapTwo['FRICTION_TASK_DIR']).Length -gt $nameMax) { throw 'second long-summary task directory component exceeded NAME_MAX' }
        if ($longMapOne['FRICTION_LOG_FILE'] -ne '') { throw 'long-summary init should remain manifest-only before the first event' }

        $longTaskId = ((1..20 | ForEach-Object { 'explicit task id component' }) -join ' ')
        $explicitInit = & "$root/scripts/init-log.ps1" `
            -BaseDir $autoBaseDir `
            -TaskId $longTaskId `
            -TaskSummary 'Explicit task id length smoke test' `
            -Agent 'orchestrator' `
            -SkillPath $root
        $explicitMap = @{}
        $explicitInit | ForEach-Object {
            if ($_ -match '^(FRICTION_[A-Z_]+)=(.*)$') {
                $explicitMap[$matches[1]] = $matches[2]
            }
        }
        if (-not (Test-Path $explicitMap['FRICTION_TASK_DIR'])) { throw 'long explicit task id directory is missing' }
        if ($explicitMap['FRICTION_TASK_ID'].Length -gt $nameMax) { throw 'long explicit task id exceeded NAME_MAX' }

        $longAgent = ((1..20 | ForEach-Object { 'very long agent name' }) -join ' ')
        $longAgentInit = & "$root/scripts/init-log.ps1" `
            -BaseDir $autoBaseDir `
            -TaskId 'long-agent-task' `
            -TaskSummary 'Long agent name smoke test' `
            -Agent $longAgent `
            -SkillPath $root
        $longAgentMap = @{}
        $longAgentInit | ForEach-Object {
            if ($_ -match '^(FRICTION_[A-Z_]+)=(.*)$') {
                $longAgentMap[$matches[1]] = $matches[2]
            }
        }
        if ($longAgentMap['FRICTION_LOG_FILE'] -ne '') { throw 'long agent init should remain manifest-only before the first event' }
        & "$root/scripts/report-friction.ps1" `
            -TaskDir $longAgentMap['FRICTION_TASK_DIR'] `
            -Agent $longAgent `
            -Title 'Long agent log path' `
            -InstructionSource 'test' `
            -InstructionText 'Materialize a lazy log for a long agent name.' `
            -ActionTaken 'Recorded one friction entry.' `
            -ExpectedOutcome 'The lazy-created log filename stays within NAME_MAX.' `
            -ActualOutcome 'The long-agent entry was recorded.' `
            -Interpretation 'Lazy materialization should still respect filename limits.' | Out-Null
        $longAgentLog = Get-ChildItem -Path $longAgentMap['FRICTION_TASK_DIR'] -Recurse -Filter '*.md' -File | Where-Object { $_.Name -ne 'INDEX.md' } | Select-Object -First 1
        if ($null -eq $longAgentLog) { throw 'long agent log file is missing after report-friction' }
        if ([System.IO.Path]::GetFileName($longAgentLog.FullName).Length -gt $nameMax) { throw 'long agent log filename exceeded NAME_MAX' }

        $longRole = ((1..20 | ForEach-Object { 'very long role name' }) -join ' ')
        $longRoleInit = & "$root/scripts/init-log.ps1" `
            -BaseDir $autoBaseDir `
            -TaskId 'long-role-task' `
            -TaskSummary 'Long role name smoke test' `
            -Agent 'subagent' `
            -Role $longRole `
            -SkillPath $root
        $longRoleMap = @{}
        $longRoleInit | ForEach-Object {
            if ($_ -match '^(FRICTION_[A-Z_]+)=(.*)$') {
                $longRoleMap[$matches[1]] = $matches[2]
            }
        }
        if ($longRoleMap['FRICTION_LOG_FILE'] -ne '') { throw 'long role init should remain manifest-only before the first event' }
        & "$root/scripts/report-friction.ps1" `
            -TaskDir $longRoleMap['FRICTION_TASK_DIR'] `
            -Agent 'subagent' `
            -RoleInit $longRole `
            -Title 'Long role log path' `
            -InstructionSource 'test' `
            -InstructionText 'Materialize a lazy log for a long role name.' `
            -ActionTaken 'Recorded one friction entry.' `
            -ExpectedOutcome 'The lazy-created log filename stays within NAME_MAX.' `
            -ActualOutcome 'The long-role entry was recorded.' `
            -Interpretation 'Lazy materialization should still respect filename limits.' | Out-Null
        $longRoleLog = Get-ChildItem -Path $longRoleMap['FRICTION_TASK_DIR'] -Recurse -Filter '*.md' -File | Where-Object { $_.Name -ne 'INDEX.md' } | Select-Object -First 1
        if ($null -eq $longRoleLog) { throw 'long role log file is missing after report-friction' }
        if ([System.IO.Path]::GetFileName($longRoleLog.FullName).Length -gt $nameMax) { throw 'long role log filename exceeded NAME_MAX' }
    }
    finally {
        if (Test-Path $autoBaseDir) {
            Remove-Item -Recurse -Force $autoBaseDir
        }
    }

    $concurrentBaseDir = Join-Path ([System.IO.Path]::GetTempPath()) ("agent-friction-ps-concurrent-{0}" -f [System.Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $concurrentBaseDir | Out-Null
    try {
        $sharedTaskId = 'concurrent-smoke-task'
        $concurrentInitOne = & "$root/scripts/init-log.ps1" `
            -BaseDir $concurrentBaseDir `
            -TaskId $sharedTaskId `
            -TaskSummary 'Concurrent index rebuild smoke test' `
            -Agent 'orchestrator' `
            -SkillPath $root
        $concurrentInitTwo = & "$root/scripts/init-log.ps1" `
            -BaseDir $concurrentBaseDir `
            -TaskId $sharedTaskId `
            -TaskSummary 'Concurrent index rebuild smoke test' `
            -Agent 'subagent' `
            -Role 'parallel' `
            -SkillPath $root

        $concurrentMapOne = @{}
        $concurrentInitOne | ForEach-Object {
            if ($_ -match '^(FRICTION_[A-Z_]+)=(.*)$') {
                $concurrentMapOne[$matches[1]] = $matches[2]
            }
        }
        $concurrentMapTwo = @{}
        $concurrentInitTwo | ForEach-Object {
            if ($_ -match '^(FRICTION_[A-Z_]+)=(.*)$') {
                $concurrentMapTwo[$matches[1]] = $matches[2]
            }
        }

        $jobScript = {
            param($rootPath, $taskDirPath, $agentName, $roleName, $title, $actualOutcome, $interpretation)
            & "$rootPath/scripts/report-friction.ps1" `
                -TaskDir $taskDirPath `
                -Agent $agentName `
                -RoleInit $roleName `
                -Title $title `
                -InstructionSource 'test' `
                -InstructionText 'Record a concurrent PowerShell entry.' `
                -ActionTaken 'Appended an entry during a concurrent rebuild scenario.' `
                -ExpectedOutcome 'The shared index remains consistent.' `
                -ActualOutcome $actualOutcome `
                -Interpretation $interpretation | Out-Null
        }

        $jobOne = Start-Job -ScriptBlock $jobScript -ArgumentList $root, $concurrentMapOne['FRICTION_TASK_DIR'], 'orchestrator', '', 'Concurrent log one entry', 'The first entry was recorded.', 'Concurrent PowerShell writers should not leave a stale index.'
        $jobTwo = Start-Job -ScriptBlock $jobScript -ArgumentList $root, $concurrentMapTwo['FRICTION_TASK_DIR'], 'subagent', 'parallel', 'Concurrent log two entry', 'The second entry was recorded.', 'Concurrent PowerShell writers should serialize index rebuilds cleanly.'
        Wait-Job -Job $jobOne, $jobTwo | Out-Null
        Receive-Job -Job $jobOne, $jobTwo | Out-Null
        Remove-Job -Job $jobOne, $jobTwo

        & "$root/scripts/build-index.ps1" -TaskDir $concurrentMapOne['FRICTION_TASK_DIR'] | Out-Null
        $concurrentIndexText = [System.IO.File]::ReadAllText($concurrentMapOne['FRICTION_INDEX_FILE'])
        if ($concurrentIndexText -notmatch '\*\*Log files:\*\* 2') { throw 'concurrent PowerShell index should report two log files' }
        if ($concurrentIndexText -notmatch '\*\*Entries:\*\* 2') { throw 'concurrent PowerShell index should report two entries' }
        if ($concurrentIndexText -notmatch 'orchestrator') { throw 'concurrent PowerShell index should include the orchestrator log' }
        if ($concurrentIndexText -notmatch 'subagent-parallel') { throw 'concurrent PowerShell index should include the subagent log' }
        $orchestratorLogIndex = $concurrentIndexText.IndexOf('orchestrator')
        $subagentLogIndex = $concurrentIndexText.IndexOf('subagent-parallel')
        if ($orchestratorLogIndex -lt 0 -or $subagentLogIndex -lt 0) { throw 'concurrent PowerShell index missing expected log entries' }
        if ($orchestratorLogIndex -ge $subagentLogIndex) { throw 'concurrent PowerShell index should sort tied log counts by path name' }

        $staleArtifacts = Get-ChildItem -Path $concurrentMapOne['FRICTION_TASK_DIR'] -Force | Where-Object {
            $_.Name -eq '.build-index.lock' -or $_.Name -like '.index.*.tmp'
        }
        if ($staleArtifacts.Count -ne 0) { throw 'concurrent PowerShell rebuild left temporary lock or index artifacts behind' }
    }
    finally {
        if (Test-Path $concurrentBaseDir) {
            Remove-Item -Recurse -Force $concurrentBaseDir
        }
    }

    Write-Output 'smoke-powershell: ok'
}
finally {
    if (Test-Path $baseDir) {
        Remove-Item -Recurse -Force $baseDir
    }
}
