param([switch]$SkipBuild)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repoRoot
$pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = 'python' }
if (-not $SkipBuild) {
    & npm.cmd --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
}
$env:PYTHONPATH = Join-Path $repoRoot 'backend/src'
Write-Host "IBKR Paper workspace at http://127.0.0.1:8000. Keep this process running."
Write-Host "Stop old workspaces first. You can open this app before logging into paper Gateway on localhost:4002."
& $pythonPath -m trading_oms_backend.workspace.serve --open
if ($LASTEXITCODE -ne 0) { throw "The unified workspace could not start. Review the migration or connection message above." }
