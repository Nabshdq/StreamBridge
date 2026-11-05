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
. (Join-Path $PSScriptRoot "version.ps1")
Assert-StreamBridgeCheckout -Python $Python -Repo $repo

& $Python -c "import nuitka" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Nuitka is not installed in $Python (pip install nuitka==4.3.4)" }

$output = Join-Path $PSScriptRoot "output\$OutputName"
$consoleMode = if ($Console) { "force" } else { "disable" }
$resources = Join-Path $repo "src\streambridge\resources"
$qml = Join-Path $repo "src\streambridge\ui\qml"

# The YouTube client only ever loads the youtube v3 description. Ship just that file
# (the whole package data is 600+ JSON files, about 107 MB). Take the path from the
# build Python so no venv location is hard-coded.
# --include-qt-plugins=qml pulls in EVERY QML module Qt ships (125 DLLs, about 316 MB,
# of which QtWebEngine alone is 195 MB). The app imports only QtQuick, QtQuick.Controls
# and QtQuick.Layouts, so drop the modules it can never load. Kept on purpose: Quick,
# Controls Basic, Templates, Layouts, Shapes, Effects, Svg, Widgets, and
# opengl32sw.dll (software rendering fallback for PCs without a good GPU driver).
$unusedQt = @(
    "qt6webengine*", "qt6webview*", "qt6webchannel*", "qt63d*", "qt6quick3d*",
    "qt6charts*", "qt6datavisualization*", "qt6graphs*", "qt6multimedia*",
    "qt6spatialaudio*", "qt6location*", "qt6positioning*", "qt6pdf*",
    "qt6virtualkeyboard*", "qt6texttospeech*", "qt6sensors*", "qt6remoteobjects*",
    "qt6scxml*", "qt6statemachine*", "qt6sql*", "qt6test*", "qt6quicktest*",
    "qt6labs*", "qt6quickcontrols2fusion*", "qt6quickcontrols2material*",
    "qt6quickcontrols2universal*", "qt6quickcontrols2imagine*",
    "qt6quickcontrols2fluentwinui3*", "qt6quickcontrols2windows*",
    "qt6quickcontrols2native*"
)
$qtExcludes = $unusedQt | ForEach-Object { "--noinclude-dlls=$_" }

# One version source: __version__ in src/streambridge/__init__.py. Nuitka only accepts up
# to 4 plain numbers for the Windows version resource, so "0.1.0b0" becomes "0.1.0.0".
# $version keeps the full text. Because "0.1.0.dev0" and "0.1.0b0" both give "0.1.0.0",
# the full text is ALSO written into the file description: installer.ps1 reads it back to
# refuse packing a stale build.
$v = Get-StreamBridgeVersion -Python $Python
$version = $v.Full
$winVersion = $v.Windows
Write-Host "Version: $version (Windows file version $winVersion)"

$youtubeJson = (& $Python -c "import googleapiclient, pathlib; print(pathlib.Path(googleapiclient.__file__).resolve().parent / 'discovery_cache' / 'documents' / 'youtube.v3.json')") | Select-Object -Last 1
if (-not (Test-Path $youtubeJson)) { throw "youtube.v3.json not found at '$youtubeJson'" }

& $Python -m nuitka `
    --mode=standalone `
    --mingw64 `
    --assume-yes-for-downloads `
    --enable-plugins=pyside6 `
    --include-qt-plugins=qml `
    @qtExcludes `
    --windows-console-mode=$consoleMode `
    --include-package=streambridge `
    "--include-data-files=$youtubeJson=googleapiclient/discovery_cache/documents/youtube.v3.json" `
    "--include-data-dir=$resources=streambridge/resources" `
    "--include-data-dir=$qml=streambridge/ui/qml" `
    --output-filename=StreamBridge.exe `
    --output-folder-name=StreamBridge `
    --product-name=StreamBridge `
    "--file-description=StreamBridge $version" `
    "--file-version=$winVersion" `
    "--product-version=$winVersion" `
    "--output-dir=$output" `
    (Join-Path $repo "src\streambridge\__main__.py")
if ($LASTEXITCODE -ne 0) { throw "Nuitka failed with exit code $LASTEXITCODE" }

Write-Host "Built: $output\StreamBridge.dist\StreamBridge.exe"
