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

Write-Host "Running offline application verification. Broker order submission is disabled in tests."

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
Invoke-Checked npm.cmd --prefix frontend run format:check
Invoke-Checked npm.cmd --prefix frontend run test

Write-Host "Backend gate includes API integration, deterministic replay, resilience, execution and crash/recovery tests."
Invoke-Checked npm.cmd --prefix frontend run build
Invoke-Checked npm.cmd --prefix frontend run test:e2e
Invoke-Checked python scripts/secret_scan.py
Invoke-Checked python -m pip_audit --disable-pip --no-deps -r backend/requirements-lock.txt
Invoke-Checked npm.cmd --prefix frontend audit --audit-level=low
Invoke-Checked python -m trading_oms_backend.workspace.verification
Write-Host "verify: ok"
