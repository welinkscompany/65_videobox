[CmdletBinding()]
param(
    [switch]$StaticOnly,
    [string]$RepositoryRoot
)

$ErrorActionPreference = "Stop"
if (-not $StaticOnly) {
    throw "A1 verification supports -StaticOnly only; no live services are inspected."
}
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}

$composePath = Join-Path $RepositoryRoot "compose.yaml"
$overlayPath = Join-Path $RepositoryRoot "compose.hermes-yujin.yaml"
$expectedImage = "nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787"
$gatewayApiNetwork = "videobox-agent-gateway-api-network"
$hermesNetwork = "videobox-agent-gateway-network"
$providerNetwork = "videobox-hermes-provider-egress"

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

function Get-NetworkNames {
    param([object]$Service)
    return @($Service.networks.PSObject.Properties.Name | Sort-Object)
}

function Assert-Networks {
    param(
        [object]$Service,
        [string[]]$Expected,
        [string]$ServiceName
    )
    $actual = @(Get-NetworkNames $Service)
    $wanted = @($Expected | Sort-Object)
    Assert-True (($actual -join "|") -ceq ($wanted -join "|")) (
        "$ServiceName network topology is not the exact A1 contract."
    )
}

function Assert-NoProperty {
    param(
        [object]$Value,
        [string]$PropertyName,
        [string]$Message
    )
    Assert-True ($null -eq $Value.PSObject.Properties[$PropertyName]) $Message
}

Assert-True (Test-Path -LiteralPath $composePath -PathType Leaf) "compose.yaml is missing."
Assert-True (Test-Path -LiteralPath $overlayPath -PathType Leaf) "Yujin Compose overlay is missing."
$baseSource = [IO.File]::ReadAllText($composePath)
Assert-True (-not $baseSource.Contains("HERMES_YUJIN")) "Base Compose must not contain Yujin services."
$source = [IO.File]::ReadAllText($overlayPath)
foreach ($requiredTemplate in @(
    '${HERMES_YUJIN_GATEWAY_USERNAME:?set in .env.container}'
    '${HERMES_YUJIN_GATEWAY_PASSWORD:?set in .env.container}'
    '${HERMES_YUJIN_GATEWAY_PASSWORD_HASH:?set in .env.container}'
)) {
    Assert-True ($source.Contains($requiredTemplate)) "A required secret template is missing."
}

$baseProcessInfo = New-Object System.Diagnostics.ProcessStartInfo
$baseProcessInfo.FileName = "docker"
$baseProcessInfo.Arguments = "compose -f `"$composePath`" config --format json"
$baseProcessInfo.WorkingDirectory = $RepositoryRoot
$baseProcessInfo.UseShellExecute = $false
$baseProcessInfo.RedirectStandardOutput = $true
$baseProcessInfo.RedirectStandardError = $true
$baseProcessInfo.CreateNoWindow = $true
$baseProcessInfo.EnvironmentVariables["POSTGRES_PASSWORD"] = "static-postgres-value"
$baseProcessInfo.EnvironmentVariables["VIDEOBOX_CONTAINER_DATA_ROOT"] = "D:/videobox-static-data"
foreach ($name in @(
    "HERMES_YUJIN_GATEWAY_USERNAME"
    "HERMES_YUJIN_GATEWAY_PASSWORD"
    "HERMES_YUJIN_GATEWAY_PASSWORD_HASH"
)) {
    [void]$baseProcessInfo.EnvironmentVariables.Remove($name)
}
$baseProcess = New-Object System.Diagnostics.Process
$baseProcess.StartInfo = $baseProcessInfo
[void]$baseProcess.Start()
$baseJson = $baseProcess.StandardOutput.ReadToEnd()
[void]$baseProcess.StandardError.ReadToEnd()
$baseProcess.WaitForExit()
Assert-True ($baseProcess.ExitCode -eq 0) "Base Compose static render failed."
$baseRendered = $baseJson | ConvertFrom-Json
Assert-True (
    $null -eq $baseRendered.services.PSObject.Properties["videobox-agent-gateway"] -and
    $null -eq $baseRendered.services.PSObject.Properties["videobox-hermes-yujin"]
) "Base Compose must not contain Yujin services."
Assert-Networks $baseRendered.services.'videobox-workspace' @(
    "videobox-edge"
    "videobox-internal"
) "base videobox-workspace"

$processInfo = New-Object System.Diagnostics.ProcessStartInfo
$processInfo.FileName = "docker"
$processInfo.Arguments = "compose -f `"$composePath`" -f `"$overlayPath`" --profile hermes-yujin config --format json"
$processInfo.WorkingDirectory = $RepositoryRoot
$processInfo.UseShellExecute = $false
$processInfo.RedirectStandardOutput = $true
$processInfo.RedirectStandardError = $true
$processInfo.CreateNoWindow = $true

# Static, non-secret values exist only in this child process. No environment
# file is created or loaded by this verifier.
$dummyEnvironment = @{
    "POSTGRES_PASSWORD" = "static-postgres-value"
    "VIDEOBOX_CONTAINER_DATA_ROOT" = "D:/videobox-static-data"
    "HERMES_YUJIN_GATEWAY_USERNAME" = "static-gateway-user"
    "HERMES_YUJIN_GATEWAY_PASSWORD" = "static-gateway-password"
    "HERMES_YUJIN_GATEWAY_PASSWORD_HASH" = "static-gateway-password-hash"
}
foreach ($name in $dummyEnvironment.Keys) {
    $processInfo.EnvironmentVariables[$name] = $dummyEnvironment[$name]
}

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $processInfo
[void]$process.Start()
$renderedJson = $process.StandardOutput.ReadToEnd()
[void]$process.StandardError.ReadToEnd()
$process.WaitForExit()
Assert-True ($process.ExitCode -eq 0) "docker compose config failed in the isolated static child process."
$rendered = $renderedJson | ConvertFrom-Json

$hermes = $rendered.services.'videobox-hermes-yujin'
$gateway = $rendered.services.'videobox-agent-gateway'
$workspace = $rendered.services.'videobox-workspace'
Assert-True ($null -ne $hermes) "Rendered Hermes Yujin service is missing."
Assert-True ($null -ne $gateway) "Rendered agent gateway service is missing."
Assert-True (($hermes.profiles -join "|") -ceq "hermes-yujin") "Hermes profile is invalid."
Assert-True (($gateway.profiles -join "|") -ceq "hermes-yujin") "Gateway profile is invalid."

Assert-True ($hermes.image -ceq $expectedImage) "Hermes image digest does not match the pin."
Assert-True (
    (($hermes.command -join "|") -ceq "serve|--host|0.0.0.0|--port|9120")
) "Hermes serve command does not match the pinned CLI contract."
Assert-Networks $hermes @($hermesNetwork, $providerNetwork) "videobox-hermes-yujin"
Assert-Networks $gateway @($gatewayApiNetwork, $hermesNetwork) "videobox-agent-gateway"
Assert-Networks $workspace @("videobox-edge", "videobox-internal", $gatewayApiNetwork) "videobox-workspace"

Assert-True ($rendered.networks.$gatewayApiNetwork.internal -eq $true) "Gateway API network must be internal."
Assert-True ($rendered.networks.$hermesNetwork.internal -eq $true) "Hermes-facing network must be internal."
Assert-NoProperty $hermes "ports" "Hermes must not publish a host port."
Assert-NoProperty $gateway "ports" "Agent gateway must not publish a host port."
Assert-NoProperty $gateway "volumes" "Agent gateway must not have mounts."
foreach ($service in @($gateway, $hermes)) {
    Assert-NoProperty $service "privileged" "A1 services must not be privileged."
    Assert-NoProperty $service "extra_hosts" "A1 services must not have extra hosts."
    Assert-NoProperty $service "dns" "A1 services must not override DNS."
}
Assert-NoProperty $gateway "cap_add" "Agent gateway must not add capabilities."

$gatewayEnvironmentNames = @($gateway.environment.PSObject.Properties.Name | Sort-Object)
Assert-True (
    ($gatewayEnvironmentNames -join "|") -ceq (
        @(
            "HERMES_YUJIN_GATEWAY_PASSWORD"
            "HERMES_YUJIN_GATEWAY_USERNAME"
            "HERMES_YUJIN_URL"
        ) -join "|"
    )
) "Gateway environment contract is invalid."
foreach ($name in @($workspace.environment.PSObject.Properties.Name)) {
    Assert-True (
        $name -notmatch '^HERMES(?:_YUJIN|_DASHBOARD)'
    ) "Workspace received a forbidden Hermes environment value."
}

$hermesMounts = @($hermes.volumes)
Assert-True ($hermesMounts.Count -eq 1) "Hermes must have exactly one mount in A1."
Assert-True (
    $hermesMounts[0].source -ceq "videobox_hermes_oauth_state" -and
    $hermesMounts[0].target -ceq "/opt/data"
) "Hermes A1 mount must be only the isolated OAuth state at /opt/data."

$hermesHealth = $hermes.healthcheck.test -join " "
$gatewayHealth = $gateway.healthcheck.test -join " "
Assert-True ($hermesHealth.Contains("http://127.0.0.1:9120/api/status")) "Hermes HTTP readiness probe is missing."
Assert-True ($gatewayHealth.Contains("http://127.0.0.1:8081/health")) "Gateway HTTP readiness probe is missing."
Assert-True (-not $hermesHealth.Contains("PASSWORD")) "Hermes healthcheck must not contain credentials."

$forbiddenHermesText = @(
    $hermes | ConvertTo-Json -Depth 20 -Compress
) -join ""
foreach ($forbidden in @(
    $gatewayApiNetwork
    "videobox-edge"
    "videobox-internal"
    "videobox-postgres"
    "/videobox-data"
    "/videobox-snapshot"
)) {
    Assert-True (-not $forbiddenHermesText.Contains($forbidden)) "Hermes contains a forbidden A1 boundary."
}

Write-Output "Hermes Yujin A1 static topology verified: rendered config, exact networks, mounts, and HTTP-only readiness."
