# =============================================================================
# Pack the project into a deployable tarball (Windows PowerShell 5.1 compatible).
#
#   .\deployment\pack.ps1                        # write to %TEMP%, print scp commands
#   .\deployment\pack.ps1 -Out D:\bundle.tar.gz  # custom output path
#   .\deployment\pack.ps1 -IncludeEnv            # also include deployment\.env.production
#
# Excludes .git / node_modules / dist / __pycache__ / .venv / docs, so the
# archive is usually tens of MB. On the server: extract, then run bash deploy.sh
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads scripts without
# a BOM using the system ANSI codepage, so non-ASCII text breaks parsing.
# =============================================================================
[CmdletBinding()]
param(
    [string]$Out,
    [switch]$IncludeEnv
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $Out) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmm'
    $Out = Join-Path $env:TEMP ("agent-trading-" + $stamp + ".tar.gz")
}
$Out = [System.IO.Path]::GetFullPath($Out)

if (-not (Get-Command tar.exe -ErrorAction SilentlyContinue)) {
    throw 'tar.exe not found (Windows 10 1803+ ships it). Use 7-Zip instead.'
}
if (-not (Test-Path (Join-Path $root 'docker-compose.yml'))) {
    throw "docker-compose.yml not found under $root - run this script from the repository."
}

$excludes = @(
    '--exclude=.git'
    '--exclude=.idea'
    '--exclude=.vscode'
    '--exclude=.cursor'
    '--exclude=.codex-tmp'
    '--exclude=.runtime'
    '--exclude=.pytest_cache'
    '--exclude=node_modules'
    '--exclude=dist'
    '--exclude=__pycache__'
    '--exclude=*.pyc'
    '--exclude=.venv'
    '--exclude=venv'
    '--exclude=*.log'
    '--exclude=.env'
    '--exclude=doc'
    '--exclude=tmp-*'
    '--exclude=*.tar.gz'
)
if (-not $IncludeEnv) {
    $excludes += '--exclude=deployment/.env.production'
}

Write-Host ("[pack] source : " + $root)
Write-Host ("[pack] output : " + $Out)
Write-Host '[pack] packing ...'

if (Test-Path $Out) { Remove-Item $Out -Force }

& tar.exe -czf $Out @excludes -C $root .
if ($LASTEXITCODE -ne 0) { throw ("pack failed, tar exit code " + $LASTEXITCODE) }

$size = [math]::Round((Get-Item $Out).Length / 1MB, 1)
Write-Host ("[pack] done   : " + $Out + " (" + $size + " MB)") -ForegroundColor Green
if ($IncludeEnv) {
    Write-Host '[pack] WARNING: deployment/.env.production (real secrets) is inside the archive.' -ForegroundColor Yellow
}

$name = Split-Path $Out -Leaf
Write-Host ''
Write-Host '---- run this locally (replace user@server-ip) ----' -ForegroundColor Cyan
Write-Host ('scp "' + $Out + '" user@server-ip:/opt/')
Write-Host ''
Write-Host '---- then run this on the server ----' -ForegroundColor Cyan
Write-Host ('mkdir -p /opt/agent_trading && tar -xzf /opt/' + $name + ' -C /opt/agent_trading && cd /opt/agent_trading && bash deploy.sh')
Write-Host ''
Write-Host 'If the archive has no deployment/.env.production, the first deploy.sh run' -ForegroundColor Gray
Write-Host 'generates the template and exits; fill it in and run deploy.sh again.' -ForegroundColor Gray
