# Downloads the Qt 6.12.0 and PySide6 6.12.0 source archives into
# third-party-source\ and checks the SHA-256 published for those file names.
# A matching local file is not an offer to recipients. This script does not
# copy the archives into dist\ and does not upload them.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $Root "third-party-source"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$Items = @(
    @{
        Name = "qt-everywhere-src-6.12.0.tar.xz"
        Url = "https://download.qt.io/official_releases/qt/6.12/6.12.0/single/qt-everywhere-src-6.12.0.tar.xz"
        Sha256 = "98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165"
        Size = 443394020
    },
    @{
        Name = "pyside-setup-everywhere-src-6.12.0.tar.xz"
        Url = "https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/pyside-setup-everywhere-src-6.12.0.tar.xz"
        Sha256 = "099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751"
        Size = 18211772
    }
)

foreach ($Item in $Items) {
    $Path = Join-Path $Dest $Item.Name
    $Valid = $false
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $Have = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        $Valid = ($Have -eq $Item.Sha256) -and ((Get-Item -LiteralPath $Path).Length -eq $Item.Size)
        if (-not $Valid) {
            Remove-Item -LiteralPath $Path -Force
        }
    }
    if (-not $Valid) {
        Write-Host "Downloading $($Item.Name)"
        & curl.exe -L --fail --retry 3 --retry-all-errors -o $Path $Item.Url
        if ($LASTEXITCODE -ne 0) {
            throw "Download failed for $($Item.Name)"
        }
        $Have = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($Have -ne $Item.Sha256) {
            Remove-Item -LiteralPath $Path -Force
            throw "SHA-256 mismatch for $($Item.Name): $Have"
        }
    }
    Write-Host "$($Item.Sha256)  $($Item.Name)"
}

Write-Host "Local archives: $Dest"
Write-Host "These files are not the application zip and are not a public offer."
