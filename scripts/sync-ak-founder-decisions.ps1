<#
Reads the founder's decisions from the AK-System approval registries (read-only)
and applies them to VideoBox once each (AK W1215-2). See
services/mcp/src/videobox_mcp/ak_decision_sync.py for the why.

Runs on the host: the containers cannot see the AK repository.
-IntervalSeconds 0 (default) runs once; a positive value keeps polling.
There is no scheduled task for this yet - creating one is the owner's call.
#>
param(
    [string]$RegistryDir = $env:VIDEOBOX_AK_APPROVAL_REGISTRY_DIR,
    [string]$VideoBoxApiBaseUrl = "http://127.0.0.1:5173",
    [double]$IntervalSeconds = 0
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Missing virtual environment: $venvPython"
}
if (-not $RegistryDir) {
    throw "Set VIDEOBOX_AK_APPROVAL_REGISTRY_DIR (or -RegistryDir) to the AK docs/ak-system/data folder."
}

$env:PYTHONPATH = (Join-Path $repoRoot "services\mcp\src") + ";" + (Join-Path $repoRoot "packages\domain-models\src")
& $venvPython -m videobox_mcp.ak_decision_sync --registry-dir $RegistryDir --api-base-url $VideoBoxApiBaseUrl --interval-seconds $IntervalSeconds
exit $LASTEXITCODE
