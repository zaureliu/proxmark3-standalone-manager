# Rebuilds the Windows one-dir executable and the local validation zip.
# Does not change the user PATH, flash firmware, or publish the zip.
# Run from any working directory.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    py -3.11 -m venv (Join-Path $Root ".venv")
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
}
& $Python -m pip install -r (Join-Path $Root "requirements.txt")
$Version = (& $Python -c "import pm3manager; print(pm3manager.__version__)").Trim()
Write-Host "Version: $Version"
& $Python (Join-Path $Root "scripts\make_icon.py")
& $Python -m PyInstaller --noconfirm --clean (Join-Path $Root "Proxmark3StandaloneManager.spec")
& (Join-Path $Root "scripts\stage_distribution.ps1")
Write-Host "Executable: $(Join-Path $Root 'dist\Proxmark3StandaloneManager\Proxmark3StandaloneManager.exe')"
