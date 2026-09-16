$ErrorActionPreference = "Stop"
$ProgressPreference = 'SilentlyContinue'
$repoRoot = Split-Path $PSScriptRoot -Parent
$sdkDirectory = Join-Path $repoRoot ".tmp/ibkr-sdk"
New-Item -ItemType Directory -Path $sdkDirectory -Force | Out-Null
$archive = Join-Path $sdkDirectory "twsapi_macunix.1050.02.zip"
$source = "https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip"
$expectedHash = "673129E5CBA58C4D77BC40647265F84EA42F605ECCF88FA4C1221D62D12454F3"
if (-not (Test-Path -LiteralPath $archive)) { Invoke-WebRequest -Uri $source -OutFile $archive }
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expectedHash) {
    throw "The official SDK archive checksum differs. Do not install it."
}
Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $sdkDirectory "source") -Force
$package = Join-Path $sdkDirectory "source/IBJts/source/pythonclient"
$setupFile = Join-Path $package 'setup.py'
$setupText = [System.IO.File]::ReadAllText($setupFile)
if (-not $setupText.Contains('protobuf==5.29.5')) { throw 'Unexpected SDK packaging metadata; review before installation.' }
# Packaging-only security patch for CVE-2026-0994; SDK protocol sources stay unchanged.
[System.IO.File]::WriteAllText($setupFile, $setupText.Replace('protobuf==5.29.5', 'protobuf==5.29.6'), [System.Text.UTF8Encoding]::new($false))
& python -m pip install --force-reinstall $package
if ($LASTEXITCODE -ne 0) { throw "Official SDK installation failed." }
Write-Host "IBKR API 10.50.2 installed from its verified archive, with packaging-only Protobuf 5.29.6 pin."
Write-Host "The licensed SDK remains outside repository history. No Gateway connection was opened."
