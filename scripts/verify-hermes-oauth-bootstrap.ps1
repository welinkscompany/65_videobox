[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $containerId = (& docker compose -p 65_videobox ps -q videobox-hermes-oauth-bootstrap).Trim()
    if (-not $containerId) {
        throw "VideoBox Hermes OAuth bootstrap container is not running."
    }

    $image = (& docker inspect --format '{{.Config.Image}}' $containerId).Trim()
    $mounts = (& docker inspect --format '{{range .Mounts}}{{.Destination}} {{end}}' $containerId).Trim()
    $networks = (& docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' $containerId).Trim()
    $ports = (& docker inspect --format '{{json .NetworkSettings.Ports}}' $containerId).Trim()

    if ($image -ne 'nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787') {
        throw "Unexpected VideoBox OAuth bootstrap image."
    }
    if ($mounts -ne '/opt/data') {
        throw "OAuth bootstrap must mount only its isolated state volume."
    }
    if ($networks -notmatch '65_videobox_videobox-hermes-egress' -or $networks -match 'videobox-internal|videobox-edge') {
        throw "OAuth bootstrap network isolation check failed."
    }
    if ($ports -ne 'null' -and $ports -ne '{}') {
        throw "OAuth bootstrap must not publish a host port."
    }

    Write-Host "OAuth bootstrap boundary verified: pinned image, isolated state mount, egress-only network, no host port."
    Write-Host "Credential contents, device codes, account identity, and model selection are intentionally not inspected or printed."
}
finally {
    Pop-Location
}
