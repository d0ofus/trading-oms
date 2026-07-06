$ErrorActionPreference = "Stop"

Write-Host "Running scaffold verification..."

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  throw "Python was not found. Install Python 3 or run this check from an environment with Python available."
}

python scripts/verify_repo.py

Write-Host "format: placeholder until backend/frontend skeleton exists"
Write-Host "typecheck: placeholder until backend/frontend skeleton exists"
Write-Host "test: placeholder until backend/frontend skeleton exists"
Write-Host "test-integration: placeholder until integration tests exist"
Write-Host "test-replay: placeholder until replay engine exists"
Write-Host "test-chaos: placeholder until chaos tests exist"
Write-Host "test-e2e: placeholder until e2e tests exist"
Write-Host "verify: ok"
