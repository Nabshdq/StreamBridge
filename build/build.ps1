<#
.SYNOPSIS
    Builds the StreamBridge Windows program with Nuitka (standalone folder).

.DESCRIPTION
    Needs a Python 3.12 environment that has StreamBridge installed in editable
    mode (pip install -e .) and Nuitka (pip install nuitka==4.3.4). The first run
    lets Nuitka download its own MinGW64 compiler.

    The result is build\output\<OutputName>\StreamBridge.dist\StreamBridge.exe. That folder is
    what the installer will pack. build\output\ is ignored by git.

.PARAMETER Python
    The python.exe of the build environment (needs streambridge installed with
    pip install -e, plus nuitka). Default: the repo's .venv.

.PARAMETER OutputName
    Folder name under build\output\ (use a new one to be sure nothing stale is reused).

.PARAMETER Console
    Keep a console window (for debugging the built program). Default: no console.
#>
param(
    [string]$Python = "",
    [string]$OutputName = "release",
    [switch]$Console
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $repo ".venv\Scripts\python.exe" }
if (-not (Test-Path $Python)) { throw "Python not found: $Python (use -Python)" }

# Native programs write to stderr; do not let PowerShell 5.1 treat that as a failure.
$ErrorActionPreference = "Continue"

# The build must compile THIS checkout, not a copy in site-packages.
$package = (& $Python -c "import streambridge, pathlib; print(pathlib.Path(streambridge.__file__).resolve())") | Select-Object -Last 1
$expected = Join-Path $repo "src\streambridge"
if (-not $package.StartsWith($expected, [StringComparison]::OrdinalIgnoreCase)) {
    throw "streambridge is imported from '$package', not from '$expected'. Run: pip install -e `"$repo`""
}

& $Python -c "import nuitka" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Nuitka is not installed in $Python (pip install nuitka==4.3.4)" }

$output = Join-Path $PSScriptRoot "output\$OutputName"
$consoleMode = if ($Console) { "force" } else { "disable" }
$resources = Join-Path $repo "src\streambridge\resources"
$qml = Join-Path $repo "src\streambridge\ui\qml"

# The YouTube client only ever loads the youtube v3 description. Ship just that file
# (the whole package data is 600+ JSON files, about 107 MB). Take the path from the
# build Python so no venv location is hard-coded.
$youtubeJson = (& $Python -c "import googleapiclient, pathlib; print(pathlib.Path(googleapiclient.__file__).resolve().parent / 'discovery_cache' / 'documents' / 'youtube.v3.json')") | Select-Object -Last 1
if (-not (Test-Path $youtubeJson)) { throw "youtube.v3.json not found at '$youtubeJson'" }

& $Python -m nuitka `
    --mode=standalone `
    --mingw64 `
    --assume-yes-for-downloads `
    --enable-plugins=pyside6 `
    --include-qt-plugins=qml `
    --windows-console-mode=$consoleMode `
    --include-package=streambridge `
    "--include-data-files=$youtubeJson=googleapiclient/discovery_cache/documents/youtube.v3.json" `
    "--include-data-dir=$resources=streambridge/resources" `
    "--include-data-dir=$qml=streambridge/ui/qml" `
    --output-filename=StreamBridge.exe `
    --output-folder-name=StreamBridge `
    --product-name=StreamBridge `
    --file-description="StreamBridge" `
    --file-version=0.1.0.0 `
    --product-version=0.1.0.0 `
    "--output-dir=$output" `
    (Join-Path $repo "src\streambridge\__main__.py")
if ($LASTEXITCODE -ne 0) { throw "Nuitka failed with exit code $LASTEXITCODE" }

Write-Host "Built: $output\StreamBridge.dist\StreamBridge.exe"
