<#
  Build Zuqongtech Daily Planner -> dist\installer\ZuqongtechPlanner-Setup-<version>.exe

  .\build.ps1                       full build (PyInstaller + Inno Setup)
  .\build.ps1 -Compiler nuitka      compile to native code with Nuitka (harder to reverse engineer)
  .\build.ps1 -SkipInstaller        only the app folder, no installer
  .\build.ps1 -Python "py -3.12"    choose the Python used for the build venv

  Both compilers emit the same dist\ZuqongtechPlanner folder, so the installer step
  is identical either way. Nuitka needs a C compiler; on Windows it offers to download
  a bundled MinGW the first time (allowed automatically here).
#>
param(
    [ValidateSet("pyinstaller", "nuitka")]
    [string]$Compiler = "pyinstaller",
    [switch]$SkipInstaller,
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venv = ".venv-build"
$py = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "==> Creating build venv ($venv)" -ForegroundColor Cyan
    $parts = $Python.Split(" ")
    & $parts[0] @($parts[1..($parts.Length)] | Where-Object { $_ }) -m venv $venv
}

$reqs = if ($Compiler -eq "nuitka") { "requirements-build-nuitka.txt" } else { "requirements-build.txt" }
Write-Host "==> Installing build requirements ($reqs)" -ForegroundColor Cyan
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r $reqs --quiet

$version = (& $py -c "import planner; print(planner.__version__)").Trim()
Write-Host "==> Version $version   compiler: $Compiler" -ForegroundColor Cyan

if (Test-Path dist\ZuqongtechPlanner) { Remove-Item dist\ZuqongtechPlanner -Recurse -Force }
if ($Compiler -eq "nuitka") {
    Write-Host "==> Nuitka (compiling to native code)" -ForegroundColor Cyan
    & $py packaging\build_nuitka.py
    if ($LASTEXITCODE -ne 0) { throw "Nuitka build failed" }
} else {
    Write-Host "==> PyInstaller" -ForegroundColor Cyan
    if (Test-Path build) { Remove-Item build -Recurse -Force }
    & $py -m PyInstaller packaging\planner.spec --noconfirm --clean --distpath dist --workpath build
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
}

$exe = "dist\ZuqongtechPlanner\ZuqongtechPlanner.exe"
if (-not (Test-Path $exe)) { throw "Expected $exe was not produced" }
Write-Host "    built $exe" -ForegroundColor Green

if ($SkipInstaller) { return }

Write-Host "==> Inno Setup" -ForegroundColor Cyan
$candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source }
if (-not $iscc) {
    Write-Warning "Inno Setup 6 not found. Install it with:  winget install JRSoftware.InnoSetup"
    Write-Warning "The app itself is ready in dist\ZuqongtechPlanner\ (you can run the .exe directly)."
    exit 1
}
if (Test-Path dist\installer) { Remove-Item dist\installer -Recurse -Force }
& $iscc "/DMyAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

$setup = "dist\installer\ZuqongtechPlanner-Setup-$version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
"$hash  $(Split-Path $setup -Leaf)" | Set-Content "$setup.sha256" -Encoding ascii -NoNewline
Write-Host "==> Done: $setup" -ForegroundColor Green
Write-Host "    sha256 $hash"
