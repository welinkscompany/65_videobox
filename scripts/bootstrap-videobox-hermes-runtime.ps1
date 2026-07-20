[CmdletBinding()]
param(
    [switch]$SeedModels
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
$composeBase = @("compose", "-p", "65_videobox")

# Build the unprivileged runtime image, then run the sole root-scoped durable
# state initializer before starting any Hermes process.  No VideoBox API,
# workspace, PostgreSQL, host bridge, OAuth, or model download is started here.
& docker @composeBase build videobox-hermes-runtime
if ($LASTEXITCODE -ne 0) {
    throw "VideoBox Hermes runtime image build failed."
}

# The canonical assets are baked into the image.  Verify them before touching
# durable state, preserve a user's existing USER.md, and configure the built-in
# Hermes memory provider for local Mem0 OSS.  No cloud key is read or written.
$bootstrapCommand = @'
set -eu
python /opt/videobox-yujin/verify_assets.py
mkdir -p /opt/data/memories
# SOUL/AGENTS/mem0.json are versioned VideoBox runtime policy assets.  Replace
# them after source hash verification so an image upgrade cannot silently keep
# stale policy.  USER.md is personal context and is only seeded when absent.
install -m 0644 /opt/videobox-yujin/SOUL.md /opt/data/SOUL.md
install -m 0644 /opt/videobox-yujin/AGENTS.md /opt/data/AGENTS.md
if [ ! -e /opt/data/memories/USER.md ]; then
  cp /opt/videobox-yujin/USER.md.seed /opt/data/memories/USER.md
fi
install -m 0644 /opt/videobox-yujin/mem0.json /opt/data/mem0.json
chown -R 10000:10000 /opt/data
python /opt/videobox-yujin/verify_assets.py --target /opt/data
s6-setuidgid hermes sh -c 'test -r /opt/data/SOUL.md && test -r /opt/data/AGENTS.md && test -r /opt/data/mem0.json && test -r /opt/data/memories/USER.md && test -w /opt/data && test -w /opt/data/memories'
hermes config set memory.provider mem0
'@

& docker @composeBase run --rm --no-deps --user root --entrypoint /bin/sh videobox-hermes-runtime -lc $bootstrapCommand
if ($LASTEXITCODE -ne 0) {
    throw "VideoBox Hermes runtime bootstrap failed."
}

& docker @composeBase --profile hermes-runtime up -d `
    videobox-hermes-local-ollama videobox-hermes-runtime
if ($LASTEXITCODE -ne 0) {
    throw "VideoBox Hermes runtime did not start."
}

if ($SeedModels) {
    $ollamaReady = $false
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        & docker @composeBase exec -T videobox-hermes-local-ollama /bin/sh -lc "ollama list >/dev/null 2>&1"
        if ($LASTEXITCODE -eq 0) {
            $ollamaReady = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $ollamaReady) {
        throw "VideoBox Hermes local Ollama did not become healthy before model seed."
    }
    # This is the sole model-downloader.  It has the model egress network;
    # the long-running Ollama service remains on the private memory network.
    & docker @composeBase --profile hermes-model-seed run --rm videobox-hermes-model-seed
    if ($LASTEXITCODE -ne 0) {
        throw "VideoBox Hermes local model seed failed."
    }
}

Write-Host "VideoBox Hermes runtime is configured: local Mem0 OSS uses qwen3:4b, nomic-embed-text, and /opt/data/mem0-qdrant."
}
finally {
    Pop-Location
}
