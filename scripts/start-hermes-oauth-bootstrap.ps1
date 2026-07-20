[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $composeBase = @("compose", "-p", "65_videobox")
    & docker @composeBase --profile hermes-oauth-bootstrap up -d videobox-hermes-oauth-bootstrap
    if ($LASTEXITCODE -ne 0) {
        throw "VideoBox Hermes OAuth bootstrap service did not start."
    }

    Write-Host "The isolated VideoBox OAuth bootstrap is running."
    Write-Host "Run these two owner-operated commands in this terminal; do not paste any code, account identity, or credential into chat or a file:"
    Write-Host 'docker compose -p 65_videobox exec -it videobox-hermes-oauth-bootstrap hermes auth add openai-codex --type oauth'
    Write-Host 'docker compose -p 65_videobox exec -it videobox-hermes-oauth-bootstrap hermes model'
    Write-Host "Choose openai-codex and gpt-5.5 in the official Hermes UI. This script never invokes either command."
}
finally {
    Pop-Location
}
