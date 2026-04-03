@echo off
setlocal

where bash >nul 2>nul
if not errorlevel 1 (
    bash "%~dp0excel-workbook-sync" %*
    set "BASH_EXIT=%ERRORLEVEL%"
    if "%BASH_EXIT%"=="0" exit /b 0
)

where pwsh >nul 2>nul
if not errorlevel 1 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0excel-workbook-sync.ps1" %*
    exit /b %ERRORLEVEL%
)

where powershell >nul 2>nul
if not errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0excel-workbook-sync.ps1" %*
    exit /b %ERRORLEVEL%
)

echo error: neither bash nor PowerShell found in PATH. 1>&2
exit /b 127
