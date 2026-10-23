# Reprints SHA-256 checksums for the one-dir executable and, when present,
# the local zip. Does not rebuild the zip and does not upload it.
# scripts\stage_distribution.ps1 is what writes the sums inside the folder
# and creates the zip. Running this script afterwards only refreshes
# dist\SHA256SUMS.txt, which sits outside the zip.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Version = "1.0.0"
if (Test-Path -LiteralPath $Python) {
    $Version = (& $Python -c "import pm3manager; print(pm3manager.__version__)").Trim()
}
$Dist = Join-Path $Root "dist"
$Exe = Join-Path $Dist "Proxmark3StandaloneManager\Proxmark3StandaloneManager.exe"
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
    throw "One-dir executable not found. Run scripts\build_exe.ps1 first."
}
$ZipName = "Proxmark3StandaloneManager-v$Version-windows-x64.zip"
$ZipPath = Join-Path $Dist $ZipName
$ExeHash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant()
$Lines = New-Object System.Collections.Generic.List[string]
if (Test-Path -LiteralPath $ZipPath -PathType Leaf) {
    $ZipHash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $Lines.Add("$ZipHash  $ZipName")
}
$Lines.Add("$ExeHash  Proxmark3StandaloneManager/Proxmark3StandaloneManager.exe")
$Out = Join-Path $Dist "SHA256SUMS.txt"
Set-Content -LiteralPath $Out -Value $Lines -Encoding ascii
Write-Host ($Lines -join [Environment]::NewLine)
Write-Host "Checksum file: $Out"
