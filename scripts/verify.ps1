$ErrorActionPreference = "Stop"

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
  )

  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
  }
}

function New-PytestBaseTemp {
  Join-Path ([System.IO.Path]::GetTempPath()) ("trading-oms-pytest-" + [System.Guid]::NewGuid().ToString("N"))
}

Write-Host "Running scaffold verification..."

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  throw "Python was not found. Install Python 3 or run this check from an environment with Python available."
}

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) {
  throw "npm.cmd was not found. Install Node.js or run this check from an environment with npm available."
}

Invoke-Checked python scripts/verify_repo.py

Invoke-Checked python -m ruff format --check backend/src backend/tests
Invoke-Checked python -m ruff check backend/src backend/tests
Invoke-Checked python -m compileall -q backend/src backend/tests
Invoke-Checked python -m pytest "-p" no:cacheprovider --basetemp (New-PytestBaseTemp) backend/tests
Invoke-Checked npm.cmd --prefix frontend run lint
Invoke-Checked npm.cmd --prefix frontend run typecheck
Invoke-Checked npm.cmd --prefix frontend run test

Write-Host "test-integration: placeholder until integration tests exist"
Write-Host "test-replay: placeholder until replay engine exists"
Invoke-Checked python -m pytest "-p" no:cacheprovider --basetemp (New-PytestBaseTemp) backend/tests/test_resilience.py
Write-Host "test-e2e: placeholder until e2e tests exist"
Write-Host "verify: ok"
