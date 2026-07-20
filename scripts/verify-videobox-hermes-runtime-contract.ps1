[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $imageId = (& docker compose -p 65_videobox images -q videobox-hermes-runtime).Trim()
    if (-not $imageId) {
        throw "VideoBox Hermes runtime image is not built. Run bootstrap-videobox-hermes-runtime.ps1 first."
    }
    $imageUser = (& docker image inspect --format '{{.Config.User}}' $imageId).Trim()
    if ($imageUser -ne 'hermes') {
        throw "VideoBox Hermes runtime image must run as the hermes user."
    }

    # This opt-in source-to-runtime verifier has no network and no durable
    # state mount; it proves only the pinned image's local dependencies.
    & docker run --rm --network none --read-only --entrypoint python $imageId -c 'import mem0, qdrant_client, ollama; print("local Hermes memory dependencies available")'
    if ($LASTEXITCODE -ne 0) {
        throw "VideoBox Hermes runtime dependency verification failed."
    }
}
finally {
    Pop-Location
}
