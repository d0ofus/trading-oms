param([switch]$SkipBuild)
$ErrorActionPreference = "Stop"
# Compatibility launcher: one paper engine, address and authentication session.
& (Join-Path $PSScriptRoot "start-workspace.ps1") -SkipBuild:$SkipBuild
