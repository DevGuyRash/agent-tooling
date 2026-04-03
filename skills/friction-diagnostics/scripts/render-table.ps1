param(
    [switch]$Tsv,
    [switch]$Csv,
    [switch]$Jsonl,
    [switch]$Json,
    [switch]$Yaml,
    [string]$File = '',
    [string]$Fields = '',
    [string]$Headers = '',
    [int]$MaxColWidth = 0,
    [int]$MaxWidth = 0,
    [string]$ColWidths = '',
    [ValidateSet('drop-last-then-shrink', 'shrink')][string]$FitMode = 'drop-last-then-shrink',
    [int]$MinColWidth = 12,
    [int]$MinColumns = 1,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Split-Path -Parent $ScriptDir
$Bin = Join-Path (Join-Path $SkillRoot 'dist') (Join-Path 'windows-x86_64' 'render-table.exe')

if (-not (Test-Path -LiteralPath $Bin -PathType Leaf)) {
    throw "render-table.ps1: missing packaged renderer at $Bin`nhint: run 'just dist-host' from the repo root or fetch refreshed dist outputs from CI"
}

$nativeArgs = [System.Collections.Generic.List[string]]::new()
if ($Tsv) { $nativeArgs.Add('--tsv') }
if ($Csv) { $nativeArgs.Add('--csv') }
if ($Jsonl) { $nativeArgs.Add('--jsonl') }
if ($Json) { $nativeArgs.Add('--json') }
if ($Yaml) { $nativeArgs.Add('--yaml') }
if (-not [string]::IsNullOrWhiteSpace($File)) {
    $nativeArgs.Add('--file')
    $nativeArgs.Add($File)
}
if (-not [string]::IsNullOrWhiteSpace($Fields)) {
    $nativeArgs.Add('--fields')
    $nativeArgs.Add($Fields)
}
if (-not [string]::IsNullOrWhiteSpace($Headers)) {
    $nativeArgs.Add('--headers')
    $nativeArgs.Add($Headers)
}
if ($MaxColWidth -gt 0) {
    $nativeArgs.Add('--max-col-width')
    $nativeArgs.Add([string]$MaxColWidth)
}
if ($MaxWidth -gt 0) {
    $nativeArgs.Add('--max-width')
    $nativeArgs.Add([string]$MaxWidth)
}
if (-not [string]::IsNullOrWhiteSpace($ColWidths)) {
    $nativeArgs.Add('--col-widths')
    $nativeArgs.Add($ColWidths)
}
$nativeArgs.Add('--fit-mode')
$nativeArgs.Add($FitMode)
$nativeArgs.Add('--min-col-width')
$nativeArgs.Add([string]$MinColWidth)
$nativeArgs.Add('--min-columns')
$nativeArgs.Add([string]$MinColumns)
if ($Help) {
    $nativeArgs.Add('--help')
}

$pipelineText = @($input | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
if ([string]::IsNullOrEmpty($pipelineText)) {
    & $Bin @nativeArgs
    exit $LASTEXITCODE
}

$pipelineText | & $Bin @nativeArgs
exit $LASTEXITCODE
