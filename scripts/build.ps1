# Build the packaged app and (re)start it. Output stays outside OneDrive:
#   %USERPROFILE%\.customdic\build\dist\CustomDic\CustomDic.exe
# Usage: scripts\build.ps1            build + restart
#        scripts\build.ps1 -NoLaunch  build only
param([switch]$NoLaunch)
$ErrorActionPreference = "Stop"
$root = "$env:USERPROFILE\.customdic"
$repo = Split-Path $PSScriptRoot -Parent
$exe = "$root\build\dist\CustomDic\CustomDic.exe"

# The running exe locks its folder; dev (pythonw) instances would hold the hotkey.
Get-Process CustomDic -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "name='pythonw.exe' or name='python.exe'" |
    Where-Object { $_.CommandLine -match '-m app|customdic\.pyw' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Milliseconds 500

Push-Location $repo
try {
    & "$root\venv\Scripts\pyinstaller.exe" packaging\customdic.spec --noconfirm --log-level WARN `
        --distpath "$root\build\dist" --workpath "$root\build\work"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
} finally { Pop-Location }

Write-Host "Built $exe"
if (-not $NoLaunch) { Start-Process $exe }
