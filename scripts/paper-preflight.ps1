$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repoRoot
$env:PYTHONPATH = Join-Path $repoRoot "backend/src"
& python -m trading_oms_backend.workspace.preflight
if ($LASTEXITCODE -ne 0) { throw "Paper preflight found unresolved prerequisites. See the checks above." }
