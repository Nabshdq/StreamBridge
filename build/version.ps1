# Shared by build.ps1 and installer.ps1 (dot-source it): the ONE place that turns
# __version__ (src/streambridge/__init__.py) into the values the build tools need.

function Assert-StreamBridgeCheckout {
    <#
    .SYNOPSIS
        Throws unless the build Python imports streambridge from THIS checkout.
        (A copy in site-packages could carry another version, or other code.)
    #>
    param([Parameter(Mandatory)][string]$Python, [Parameter(Mandatory)][string]$Repo)

    $package = (& $Python -c "import streambridge, pathlib; print(pathlib.Path(streambridge.__file__).resolve())") | Select-Object -Last 1
    $expected = Join-Path $Repo "src\streambridge"
    if (-not $package.StartsWith($expected, [StringComparison]::OrdinalIgnoreCase)) {
        throw "streambridge is imported from '$package', not from '$expected'. Run: pip install -e `"$Repo`""
    }
}

function Get-StreamBridgeVersion {
    <#
    .SYNOPSIS
        Reads __version__ from the build Python and derives the Windows file version.
    .OUTPUTS
        A hashtable: Full (e.g. "0.1.0b0") and Windows (4 plain numbers, e.g. "0.1.0.0").
        Windows file versions only allow numbers, so "dev0" / "b0" are dropped from Windows.
    #>
    param([Parameter(Mandatory)][string]$Python)

    $full = (& $Python -c "import streambridge; print(streambridge.__version__)") | Select-Object -Last 1
    $numeric = (& $Python -c "import re, streambridge; m = re.match(r'\d+(?:\.\d+){0,3}', streambridge.__version__); print(m.group(0) if m else '')") | Select-Object -Last 1
    if (-not $numeric) { throw "Cannot read a numeric version from '$full'" }
    $parts = @($numeric -split '\.')
    while ($parts.Count -lt 4) { $parts += '0' }
    return @{ Full = $full; Windows = ($parts -join '.') }
}
