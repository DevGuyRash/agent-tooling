#!/usr/bin/env pwsh
#Requires -Version 5.1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Split-Path -Parent $ScriptDir
$PlatformId = 'windows-x86_64'
$Bin = Join-Path (Join-Path $SkillRoot 'dist') (Join-Path $PlatformId 'mpcr.exe')

if (-not (Test-Path -LiteralPath $Bin -PathType Leaf)) {
    Write-Error "error: missing packaged mpcr binary at $Bin`nhint: run 'just dist-host' from the repo root or fetch refreshed dist outputs from CI"
    exit 127
}

if ([System.Console]::IsOutputRedirected -or -not [Environment]::UserInteractive) {
    $env:PAGER = 'cat'
    $env:GIT_PAGER = 'cat'
    $env:NO_PAGER = '1'
}

if (-not $env:RUST_BACKTRACE) {
    $env:RUST_BACKTRACE = '0'
}

& $Bin @args
exit $LASTEXITCODE
