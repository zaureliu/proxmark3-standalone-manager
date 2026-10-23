# Instala dependências, roda os testes, reconstrói o executável one-dir e o atalho.
# Não publica o zip e não grava firmware.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    py -3.11 -m venv (Join-Path $Root ".venv")
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
}

& $Python -m pip install -r (Join-Path $Root "requirements.txt")
& $Python -m pytest (Join-Path $Root "tests")
& (Join-Path $Root "scripts\build_exe.ps1")
& $Python (Join-Path $Root "scripts\create_shortcut.py")
$Exe = Join-Path $Root "dist\Proxmark3StandaloneManager\Proxmark3StandaloneManager.exe"
$Check = Start-Process -FilePath $Exe -ArgumentList "--self-check" -WorkingDirectory (Split-Path -Parent $Exe) -Wait -PassThru -WindowStyle Hidden
if ($Check.ExitCode -ne 0) {
    throw "self-check failed with exit code $($Check.ExitCode)"
}
Write-Host "Instalação local concluída. O zip não foi publicado."
