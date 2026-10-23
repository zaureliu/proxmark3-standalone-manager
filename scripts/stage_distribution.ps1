# Copies license notices into the one-dir folder, writes checksums, and
# builds a local zip. Does not upload the zip. Publication stays blocked
# until DISTRIBUTION-STATUS.txt says otherwise.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv. Run scripts\build_exe.ps1 first."
}
$Version = (& $Python -c "import pm3manager; print(pm3manager.__version__)").Trim()
if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
    throw "Unexpected version: $Version"
}

$Dist = Join-Path $Root "dist"
$FolderName = "Proxmark3StandaloneManager"
$AppDir = Join-Path $Dist $FolderName
$Exe = Join-Path $AppDir "$FolderName.exe"
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
    throw "One-dir executable not found. Run scripts\build_exe.ps1 first."
}

$Stale = Join-Path $Dist "$FolderName.exe"
if (Test-Path -LiteralPath $Stale -PathType Leaf) {
    Remove-Item -LiteralPath $Stale -Force
}

$Marker = Join-Path $AppDir ".pm3manager-root"
if (Test-Path -LiteralPath $Marker) {
    throw "Refusing to stage a folder that contains the development marker."
}

foreach ($Relative in @(
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "DISTRIBUTION-STATUS.txt",
    "licenses",
    "docs\corresponding-source.md",
    "packaging\README-DISTRIBUTION.txt"
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $Root $Relative))) {
        throw "Missing $Relative"
    }
}

Copy-Item -LiteralPath (Join-Path $Root "LICENSE") -Destination (Join-Path $AppDir "LICENSE") -Force
Copy-Item -LiteralPath (Join-Path $Root "THIRD_PARTY_NOTICES.md") -Destination (Join-Path $AppDir "THIRD_PARTY_NOTICES.md") -Force
Copy-Item -LiteralPath (Join-Path $Root "DISTRIBUTION-STATUS.txt") -Destination (Join-Path $AppDir "DISTRIBUTION-STATUS.txt") -Force
Copy-Item -LiteralPath (Join-Path $Root "docs\corresponding-source.md") -Destination (Join-Path $AppDir "CORRESPONDING-SOURCE.md") -Force
Copy-Item -LiteralPath (Join-Path $Root "packaging\README-DISTRIBUTION.txt") -Destination (Join-Path $AppDir "README.txt") -Force

$LicenseDest = Join-Path $AppDir "licenses"
if (Test-Path -LiteralPath $LicenseDest) {
    Remove-Item -LiteralPath $LicenseDest -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $Root "licenses") -Destination $LicenseDest -Recurse -Force
$Inventory = Join-Path $LicenseDest "QT-FILES.txt"
$InventoryLines = New-Object System.Collections.Generic.List[string]
$InventoryLines.Add("DLLs and Python extension modules in this folder.")
$InventoryLines.Add("Paths are relative to Proxmark3StandaloneManager.exe.")
$InventoryLines.Add("Replace a Qt or Shiboken library at the path listed here.")
$InventoryLines.Add("")
Get-ChildItem -LiteralPath $AppDir -Recurse -File | Where-Object {
    $_.Extension -in ".dll", ".pyd"
} | Sort-Object FullName | ForEach-Object {
    $RelativePath = $_.FullName.Substring($AppDir.Length).TrimStart("\", "/") -replace "\\", "/"
    $InventoryLines.Add($RelativePath)
}
Set-Content -LiteralPath $Inventory -Value $InventoryLines -Encoding ascii

$InnerSums = Join-Path $AppDir "SHA256SUMS.txt"
if (Test-Path -LiteralPath $InnerSums) {
    Remove-Item -LiteralPath $InnerSums -Force
}
$Lines = New-Object System.Collections.Generic.List[string]
Get-ChildItem -LiteralPath $AppDir -Recurse -File | Sort-Object FullName | ForEach-Object {
    $Hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $RelativePath = $_.FullName.Substring($AppDir.Length).TrimStart("\", "/") -replace "\\", "/"
    $Lines.Add("$Hash  $RelativePath")
}
Set-Content -LiteralPath $InnerSums -Value $Lines -Encoding ascii

$ZipName = "Proxmark3StandaloneManager-v$Version-windows-x64.zip"
$ZipPath = Join-Path $Dist $ZipName
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $AppDir,
    $ZipPath,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $true
)

$ZipHash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$ExeHash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant()
$Outer = @(
    "$ZipHash  $ZipName",
    "$ExeHash  $FolderName/$FolderName.exe"
)
$OuterPath = Join-Path $Dist "SHA256SUMS.txt"
Set-Content -LiteralPath $OuterPath -Value $Outer -Encoding ascii
Write-Host "Folder: $AppDir"
Write-Host "Zip: $ZipPath"
Write-Host ($Outer -join [Environment]::NewLine)
Write-Host "Publication remains blocked. See DISTRIBUTION-STATUS.txt."
