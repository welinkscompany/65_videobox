[CmdletBinding()]
param(
    [switch]$Live,
    [switch]$ConfirmLive,
    [string]$BaseUri = "http://127.0.0.1:8000",
    [string]$ProjectId,
    [string]$SessionId,
    [string]$DisposableProjectRoot,
    [string]$SampleAssetPath,
    [ValidateRange(1, 60)]
    [int]$TimeoutSec = 20
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$runner = Join-Path $PSScriptRoot "smoke_hermes_yujin_creator_flow.py"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    [Console]::Error.WriteLine(
        "HERMES_YUJIN_CREATOR_SMOKE_FAILED:python_runtime_missing"
    )
    exit 1
}

if ($Live) {
    if (-not $ConfirmLive) {
        [Console]::Error.WriteLine(
            "HERMES_YUJIN_CREATOR_LIVE_BLOCKED:confirmation_required"
        )
        exit 1
    }
    if (
        [string]::IsNullOrWhiteSpace($ProjectId) -or
        [string]::IsNullOrWhiteSpace($SessionId) -or
        [string]::IsNullOrWhiteSpace($DisposableProjectRoot) -or
        [string]::IsNullOrWhiteSpace($SampleAssetPath) -or
        $env:VIDEOBOX_HERMES_YUJIN_LIVE_SMOKE -cne "1"
    ) {
        [Console]::Error.WriteLine(
            "HERMES_YUJIN_CREATOR_LIVE_BLOCKED:disposable_runtime_configuration_required"
        )
        exit 1
    }
    & $python $runner --live `
        --base-uri $BaseUri `
        --project-id $ProjectId `
        --session-id $SessionId `
        --disposable-project-root $DisposableProjectRoot `
        --sample-asset-path $SampleAssetPath `
        --timeout-sec $TimeoutSec
    exit $LASTEXITCODE
}

& $python $runner
exit $LASTEXITCODE
