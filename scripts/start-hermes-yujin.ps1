[CmdletBinding()]
param(
    [string]$EnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) ".env.container")
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repositoryRoot "compose.yaml"
$overlayFile = Join-Path $repositoryRoot "compose.hermes-yujin.yaml"

if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    throw "A real container environment file is required."
}

$requiredNames = @(
    "POSTGRES_PASSWORD"
    "VIDEOBOX_CONTAINER_DATA_ROOT"
    "HERMES_YUJIN_GATEWAY_USERNAME"
    "HERMES_YUJIN_GATEWAY_PASSWORD"
    "HERMES_YUJIN_GATEWAY_PASSWORD_HASH"
)
$values = @{}
foreach ($line in [IO.File]::ReadAllLines((Resolve-Path -LiteralPath $EnvFile))) {
    if ($line -match '^\s*#' -or [string]::IsNullOrWhiteSpace($line)) {
        continue
    }
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
        $values[$Matches[1]] = $Matches[2].Trim()
    }
}

foreach ($name in $requiredNames) {
    $value = $values[$name]
    if (
        [string]::IsNullOrWhiteSpace($value) -or
        $value -match '(?i)replace-before-starting|placeholder|change-me'
    ) {
        throw "Required container variable '$name' is missing or still a placeholder."
    }
}

Push-Location $repositoryRoot
try {
    docker compose -f $composeFile -f $overlayFile --profile hermes-yujin --env-file $EnvFile up -d --build videobox-hermes-yujin videobox-agent-gateway
    if ($LASTEXITCODE -ne 0) {
        throw "Targeted Hermes Yujin startup failed."
    }
}
finally {
    Pop-Location
}

Write-Output "Hermes Yujin and its agent gateway were targeted for startup."
