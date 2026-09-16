param([switch]$SkipBuild)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repoRoot
if (-not $SkipBuild -and -not (Test-Path -LiteralPath (Join-Path $repoRoot 'frontend/dist/index.html'))) {
    & npm.cmd --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
}
$env:PYTHONPATH = Join-Path $repoRoot "backend/src"
Write-Host "Starting the local paper workspace. Keep this process running during a session."
Write-Host "The launcher opens an authenticated local browser session. Broker login stays in Gateway."
& python -m trading_oms_backend.workspace.serve --open
if ($LASTEXITCODE -ne 0) { throw "The paper workspace could not start." }
