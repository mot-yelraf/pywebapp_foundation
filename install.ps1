# Install into a user-owned directory without changing execution policy or elevating.
[CmdletBinding()]
param([string]$Destination = "", [switch]$Desktop, [switch]$BrowserOnly, [switch]$AdoptLegacyInstall)
$ErrorActionPreference = "Stop"
if ($Desktop -and $BrowserOnly) { throw "Choose Desktop or BrowserOnly, not both." }
$installerArgs = @((Join-Path $PSScriptRoot "scripts/install_runtime.py"))
if ($Destination) { $installerArgs += @("--destination", $Destination) }
if ($Desktop) { $installerArgs += "--desktop" }
if ($AdoptLegacyInstall) { $installerArgs += "--adopt-legacy-install" }
if ($BrowserOnly) { $installerArgs += "--browser-only" }
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 @installerArgs
} else {
    & python @installerArgs
}
if ($LASTEXITCODE -ne 0) { throw "PWAF installation failed (exit $LASTEXITCODE)." }
