# Build the packaged app and (re)start it. Output stays outside OneDrive:
#   %USERPROFILE%\.instantdic\build\dist\InstantDic\InstantDic.exe
# Usage: scripts\build.ps1            build + restart
#        scripts\build.ps1 -NoLaunch  build only
param([switch]$NoLaunch)
# No "Stop" preference: Windows PowerShell treats PyInstaller's stderr warnings as errors. Exit codes are checked instead.
$root = "$env:USERPROFILE\.instantdic"
$repo = Split-Path $PSScriptRoot -Parent
$exe = "$root\build\dist\InstantDic\InstantDic.exe"

# The running exe locks its folder; dev (pythonw) instances would hold the hotkey.
Get-Process InstantDic -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "name='pythonw.exe' or name='python.exe'" |
    Where-Object { $_.CommandLine -match '-m app|instantdic\.pyw' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Milliseconds 500

Push-Location $repo
try {
    & "$root\venv\Scripts\pyinstaller.exe" packaging\instantdic.spec --noconfirm --log-level WARN `
        --distpath "$root\build\dist" --workpath "$root\build\work"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
} finally { Pop-Location }

Write-Host "Built $exe"
# Launch through Explorer so the app runs as if double-clicked: a process started from another
# app's sandbox (e.g. a packaged app's terminal) would inherit its file-system virtualization.
if (-not $NoLaunch) { Start-Process explorer.exe -ArgumentList "`"$exe`"" }
