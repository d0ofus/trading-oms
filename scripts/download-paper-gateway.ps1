$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$dependencyRecord = Get-Content -LiteralPath (Join-Path $workspaceRoot 'docs/PAPER_DEPENDENCIES.json') -Raw | ConvertFrom-Json
$downloadDirectory = Join-Path $workspaceRoot '.tmp'
New-Item -ItemType Directory -Path $downloadDirectory -Force | Out-Null
$gatewayPackage = Join-Path $downloadDirectory 'ibgateway-latest-standalone-windows-x64.exe'
if (-not (Test-Path -LiteralPath $gatewayPackage)) {
    Invoke-WebRequest -Uri $dependencyRecord.ib_gateway.url -OutFile $gatewayPackage -UseBasicParsing
}
if ((Get-FileHash -LiteralPath $gatewayPackage -Algorithm SHA256).Hash.ToLowerInvariant() -ne $dependencyRecord.ib_gateway.sha256) {
    throw 'Gateway package differs from the qualified download record. Keep the existing installation and review the new build.'
}
$gatewaySignature = Get-AuthenticodeSignature -LiteralPath $gatewayPackage
if ($gatewaySignature.Status -ne 'Valid' -or $gatewaySignature.SignerCertificate.Subject -notmatch 'Interactive Brokers Group') {
    throw 'Gateway publisher signature could not be verified.'
}
Write-Host "Verified offline Gateway $($dependencyRecord.ib_gateway.selected_build): $gatewayPackage"
Write-Host 'The installer has not been run. Use this verified file for supervised paper setup.'
