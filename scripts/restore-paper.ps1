param(
    [Parameter(Mandatory=$true)][string]$Backup,
    [Parameter(Mandatory=$true)][string]$RecoveryDirectory
)
$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $workspaceRoot 'backend/src'
python -m trading_oms_backend.workspace.recovery $Backup $RecoveryDirectory
if ($LASTEXITCODE -ne 0) { throw 'Restore validation failed; the active workspace was not overwritten.' }
