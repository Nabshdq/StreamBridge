<#
.SYNOPSIS
    Builds the StreamBridge Windows installer (Inno Setup 7) from a finished program build.

.DESCRIPTION
    Run build\build.ps1 first. This script packs build\output\<OutputName>\StreamBridge.dist
    into build\output\installer\StreamBridge-Setup-<version>.exe.

    It refuses to pack a program that was built from a different version than the current
    __version__ (for example a stale build made before the beta version bump).

.PARAMETER Python
    The python.exe that has streambridge installed (same one as for build.ps1).
    Default: the repo's .venv.

.PARAMETER OutputName
    The folder name under build\output\ that build.ps1 wrote to. Default: release.

.PARAMETER Iscc
    Path to ISCC.exe (Inno Setup 7). Default: searched in the usual places and on PATH.
#>
param(
    [string]$Python = "",
    [string]$OutputName = "release",
    [string]$Iscc = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $repo ".venv\Scripts\python.exe" }
if (-not (Test-Path $Python)) { throw "Python not found: $Python (use -Python)" }

# Same version source and derivation as build.ps1.
. (Join-Path $PSScriptRoot "version.ps1")
Assert-StreamBridgeCheckout -Python $Python -Repo $repo
$v = Get-StreamBridgeVersion -Python $Python
Write-Host "Version: $($v.Full) (Windows file version $($v.Windows))"

# Find the compiler.
if (-not $Iscc) {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe"
    )
    $Iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Iscc) {
        $onPath = Get-Command iscc -ErrorAction SilentlyContinue
        if ($onPath) { $Iscc = $onPath.Source }
    }
}
if (-not $Iscc -or -not (Test-Path $Iscc)) {
    throw "ISCC.exe not found. Install Inno Setup 7 from https://jrsoftware.org/isdl.php or pass -Iscc."
}

# The program build must exist and match the current version.
$dist = Join-Path $PSScriptRoot "output\$OutputName\StreamBridge.dist"
$exe = Join-Path $dist "StreamBridge.exe"
if (-not (Test-Path $exe)) { throw "Program not built: $exe. Run build\build.ps1 first." }

$info = (Get-Item $exe).VersionInfo
$expectedDescription = "StreamBridge $($v.Full)"
if ($info.FileDescription -ne $expectedDescription) {
    throw "Stale build: the program says '$($info.FileDescription)' but __version__ is '$($v.Full)'. Run build\build.ps1 again."
}
if ($info.FileVersion -ne $v.Windows) {
    throw "Stale build: file version '$($info.FileVersion)' differs from '$($v.Windows)'. Run build\build.ps1 again."
}

# ISCC writes warnings to stderr; do not let PowerShell 5.1 treat that as a failure.
$ErrorActionPreference = "Continue"
& $Iscc `
    "/DAppVersion=$($v.Full)" `
    "/DWinVersion=$($v.Windows)" `
    "/DDistDir=$dist" `
    "/DRepoDir=$repo" `
    (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed with exit code $LASTEXITCODE" }

$setup = Join-Path $PSScriptRoot "output\installer\StreamBridge-Setup-$($v.Full).exe"
if (-not (Test-Path $setup)) { throw "Installer was not written: $setup" }
Write-Host ("Built: {0} ({1:N1} MB)" -f $setup, ((Get-Item $setup).Length / 1MB))
