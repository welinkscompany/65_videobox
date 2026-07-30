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
. (Join-Path $PSScriptRoot "hermes-yujin-environment-contract.ps1")
$expectedImage = "nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787"
$gatewayApiNetwork = "videobox-agent-gateway-api-network"
$hermesNetwork = "videobox-agent-gateway-network"
$providerNetwork = "videobox-hermes-provider-egress"
$memoryNetwork = "videobox-hermes-memory-network"
$memoryAdapterService = "videobox-hermes-memory-adapter"

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

function Invoke-CapturedProcess {
    param([System.Diagnostics.ProcessStartInfo]$ProcessInfo)

    $capturedProcess = New-Object System.Diagnostics.Process
    $capturedProcess.StartInfo = $ProcessInfo
    [void]$capturedProcess.Start()
    $stdoutTask = $capturedProcess.StandardOutput.ReadToEndAsync()
    $stderrTask = $capturedProcess.StandardError.ReadToEndAsync()
    $capturedProcess.WaitForExit()
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    [void]$stderrTask.GetAwaiter().GetResult()
    return [pscustomobject]@{
        ExitCode = $capturedProcess.ExitCode
        StdOut = $stdout
    }
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
    '${VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN:?set in .env.container}'
    '${VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64:?set in .env.container}'
    '${VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64:?set in .env.container}'
    '${VIDEOBOX_HERMES_CAPABILITY_KEY_ID:?set in .env.container}'
    '${VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN:?set in .env.container}'
    '${MEM0_API_KEY:-}'
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
    "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN"
    "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64"
    "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64"
    "VIDEOBOX_HERMES_CAPABILITY_KEY_ID"
    "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"
    "MEM0_API_KEY"
)) {
    [void]$baseProcessInfo.EnvironmentVariables.Remove($name)
}
$baseResult = Invoke-CapturedProcess -ProcessInfo $baseProcessInfo
$baseJson = $baseResult.StdOut
Assert-True ($baseResult.ExitCode -eq 0) "Base Compose static render failed."
$baseRendered = $baseJson | ConvertFrom-Json
Assert-True (
    $null -eq $baseRendered.services.PSObject.Properties["videobox-agent-gateway"] -and
    $null -eq $baseRendered.services.PSObject.Properties["videobox-hermes-yujin"] -and
    $null -eq $baseRendered.services.PSObject.Properties[$memoryAdapterService]
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
    "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN" = "static-service-token-at-least-32-bytes"
    "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64" = "ERERERERERERERERERERERERERERERERERERERERERE"
    "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64" = "0EqyMnQrtKs6E2i9RhXk5tAiSrcaAWuvhSCjMsl3hzc"
    "VIDEOBOX_HERMES_CAPABILITY_KEY_ID" = "c3-static-key-2026-07"
    "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN" = "static-memory-token-at-least-32-bytes"
    "MEM0_API_KEY" = ""
}
foreach ($name in $dummyEnvironment.Keys) {
    $processInfo.EnvironmentVariables[$name] = $dummyEnvironment[$name]
}

$configResult = Invoke-CapturedProcess -ProcessInfo $processInfo
$renderedJson = $configResult.StdOut
Assert-True ($configResult.ExitCode -eq 0) "docker compose config failed in the isolated static child process."
$rendered = $renderedJson | ConvertFrom-Json

$hermes = $rendered.services.'videobox-hermes-yujin'
$gateway = $rendered.services.'videobox-agent-gateway'
$workspace = $rendered.services.'videobox-workspace'
$memoryAdapter = $rendered.services.$memoryAdapterService
Assert-True ($null -ne $hermes) "Rendered Hermes Yujin service is missing."
Assert-True ($null -ne $gateway) "Rendered agent gateway service is missing."
Assert-True ($null -ne $memoryAdapter) "Rendered Hermes memory adapter service is missing."
Assert-True (($hermes.profiles -join "|") -ceq "hermes-yujin") "Hermes profile is invalid."
Assert-True (($gateway.profiles -join "|") -ceq "hermes-yujin") "Gateway profile is invalid."
Assert-True (($memoryAdapter.profiles -join "|") -ceq "hermes-yujin") "Memory adapter profile is invalid."

Assert-True ($hermes.image -ceq $expectedImage) "Hermes image digest does not match the pin."
Assert-True ($hermes.container_name -ceq "videobox-hermes-yujin") "Hermes container name must match the container-only installer target."
Assert-True (
    (($hermes.command -join "|") -ceq "-p|videobox-yujin|serve|--host|0.0.0.0|--port|9120")
) "Hermes serve command does not match the pinned CLI contract."
Assert-True (
    $hermes.environment.HERMES_TUI_TOOLSETS -ceq "context_engine"
) "Hermes must use the pinned zero-schema context_engine toolset."
Assert-Networks $hermes @($hermesNetwork, $providerNetwork) "videobox-hermes-yujin"
Assert-Networks $gateway @($gatewayApiNetwork, $hermesNetwork, $memoryNetwork) "videobox-agent-gateway"
Assert-Networks $memoryAdapter @($memoryNetwork, $providerNetwork) $memoryAdapterService
Assert-Networks $workspace @("videobox-edge", "videobox-internal", $gatewayApiNetwork) "videobox-workspace"

Assert-True ($rendered.networks.$gatewayApiNetwork.internal -eq $true) "Gateway API network must be internal."
Assert-True ($rendered.networks.$hermesNetwork.internal -eq $true) "Hermes-facing network must be internal."
Assert-True ($rendered.networks.$memoryNetwork.internal -eq $true) "Memory adapter network must be internal."
Assert-NoProperty $hermes "ports" "Hermes must not publish a host port."
Assert-NoProperty $gateway "ports" "Agent gateway must not publish a host port."
Assert-NoProperty $memoryAdapter "ports" "Memory adapter must not publish a host port."
Assert-NoProperty $memoryAdapter "expose" "Memory adapter must not expose a host port."
Assert-NoProperty $gateway "volumes" "Agent gateway must not have mounts."
Assert-NoProperty $memoryAdapter "volumes" "Memory adapter must not have mounts."
Assert-NoProperty $memoryAdapter "depends_on" "Memory adapter must not depend on chat services."
Assert-True (
    $null -eq $gateway.depends_on.PSObject.Properties[$memoryAdapterService]
) "Gateway must not hard-depend on the optional memory adapter."
Assert-NoProperty $hermes "depends_on" "Hermes chat must not depend on the optional memory adapter."
foreach ($service in @($gateway, $hermes, $memoryAdapter)) {
    Assert-NoProperty $service "privileged" "A1 services must not be privileged."
    Assert-NoProperty $service "extra_hosts" "A1 services must not have extra hosts."
    Assert-NoProperty $service "dns" "A1 services must not override DNS."
}
Assert-NoProperty $gateway "cap_add" "Agent gateway must not add capabilities."
Assert-NoProperty $memoryAdapter "cap_add" "Memory adapter must not add capabilities."
Assert-True (
    $memoryAdapter.build.dockerfile -ceq "docker/hermes-memory-adapter.Dockerfile"
) "Memory adapter Dockerfile selection is invalid."

$gatewayEnvironmentNames = @($gateway.environment.PSObject.Properties.Name | Sort-Object)
Assert-True (
    ($gatewayEnvironmentNames -join "|") -ceq (
        @(
            "HERMES_MEMORY_ADAPTER_URL"
            "HERMES_YUJIN_GATEWAY_PASSWORD"
            "HERMES_YUJIN_GATEWAY_USERNAME"
            "HERMES_YUJIN_URL"
            "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN"
            "VIDEOBOX_HERMES_CAPABILITY_KEY_ID"
            "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64"
            "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"
        ) -join "|"
    )
) "Gateway environment contract is invalid."
Assert-True (
    $gateway.environment.HERMES_MEMORY_ADAPTER_URL -ceq
    "http://videobox-hermes-memory-adapter:8082"
) "Gateway memory adapter URL is invalid."
$memoryAdapterEnvironmentNames = @(
    $memoryAdapter.environment.PSObject.Properties.Name | Sort-Object
)
Assert-True (
    ($memoryAdapterEnvironmentNames -join "|") -ceq (
        @(
            "MEM0_API_KEY"
            "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"
        ) -join "|"
    )
) "Memory adapter environment contract is invalid."
Assert-True (
    $memoryAdapter.environment.MEM0_API_KEY -ceq ""
) "Static verification must leave the optional Mem0 credential empty."
Assert-True (
    $memoryAdapter.environment.VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN -ceq
    $dummyEnvironment["VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"] -and
    $gateway.environment.VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN -ceq
    $dummyEnvironment["VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"]
) "Memory adapter service credentials do not match."
Assert-True (
    $workspace.environment.VIDEOBOX_AGENT_GATEWAY_URL -ceq
    "http://videobox-agent-gateway:8081"
) "Workspace gateway URL is invalid."
Assert-True (
    $workspace.environment.VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN -ceq
    $dummyEnvironment["VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN"]
) "Workspace gateway service credential does not match the gateway."
Assert-True (
    $workspace.environment.VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64 -ceq
    $dummyEnvironment["VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64"]
) "Workspace capability public key does not match the deployment contract."
Assert-True (
    $workspace.environment.VIDEOBOX_HERMES_CAPABILITY_KEY_ID -ceq
    $gateway.environment.VIDEOBOX_HERMES_CAPABILITY_KEY_ID
) "Capability key IDs do not match."
Assert-NoProperty $gateway.environment `
    "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64" `
    "Gateway received the capability public key."
Assert-NoProperty $workspace.environment `
    "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64" `
    "Workspace received the capability private key."
Assert-NoProperty $gateway.environment `
    "MEM0_API_KEY" `
    "Gateway received the Mem0 credential."
Assert-NoProperty $workspace.environment `
    "MEM0_API_KEY" `
    "Workspace received the Mem0 credential."
Assert-NoProperty $workspace.environment `
    "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN" `
    "Workspace received the memory adapter credential."
Assert-NoProperty $hermes.environment `
    "MEM0_API_KEY" `
    "Interactive Hermes received the Mem0 credential."
Assert-NoProperty $hermes.environment `
    "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN" `
    "Interactive Hermes received the memory adapter credential."
foreach ($name in @($hermes.environment.PSObject.Properties.Name)) {
    Assert-True (
        $name -notmatch '^VIDEOBOX_HERMES_CAPABILITY_'
    ) "Hermes received forbidden capability key material."
}
foreach ($name in @($workspace.environment.PSObject.Properties.Name)) {
    Assert-True (
        $name -notmatch '^HERMES(?:_YUJIN|_DASHBOARD)'
    ) "Workspace received a forbidden Hermes environment value."
}
Assert-NoHermesYujinCredentialValueAliases `
    -Environment $workspace.environment `
    -ExactCredentialValues @(
        $dummyEnvironment["HERMES_YUJIN_GATEWAY_USERNAME"]
    ) `
    -SecretSubstringValues @(
        $dummyEnvironment["HERMES_YUJIN_GATEWAY_PASSWORD"]
        $dummyEnvironment["HERMES_YUJIN_GATEWAY_PASSWORD_HASH"]
    ) `
    -FailureMessage "Workspace resolved environment contains a forbidden dummy Hermes credential value."

$hermesMounts = @($hermes.volumes)
Assert-True ($hermesMounts.Count -eq 2) "Hermes must have exactly the OAuth state and read-only Yujin profile mounts."
Assert-True (
    @(
        $hermesMounts | Where-Object {
            $_.source -ceq "videobox_hermes_oauth_state" -and
            $_.target -ceq "/opt/data" -and
            $_.type -ceq "volume"
        }
    ).Count -eq 1
) "Hermes must retain the isolated OAuth state at /opt/data."
$profileSource = [IO.Path]::GetFullPath((Join-Path $RepositoryRoot "config/hermes/yujin"))
Assert-True (
    @(
        $hermesMounts | Where-Object {
            $_.source -ceq $profileSource -and
            $_.target -ceq "/opt/videobox-yujin-profile" -and
            $_.type -ceq "bind" -and
            $_.read_only -eq $true
        }
    ).Count -eq 1
) "Hermes must mount only the versioned Yujin profile source read-only."

$hermesHealth = $hermes.healthcheck.test -join " "
$gatewayHealth = $gateway.healthcheck.test -join " "
Assert-True ($hermesHealth.Contains("http://127.0.0.1:9120/api/status")) "Hermes HTTP readiness probe is missing."
Assert-True ($gatewayHealth.Contains("http://127.0.0.1:8081/health")) "Gateway HTTP readiness probe is missing."
Assert-True (-not $hermesHealth.Contains("PASSWORD")) "Hermes healthcheck must not contain credentials."
$memoryAdapterHealth = $memoryAdapter.healthcheck.test -join " "
Assert-True ($memoryAdapterHealth.Contains("http://127.0.0.1:8082/health")) "Memory adapter HTTP readiness probe is missing."
Assert-True (-not $memoryAdapterHealth.Contains("MEM0_API_KEY")) "Memory adapter healthcheck must not contain credentials."

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

$forbiddenMemoryAdapterText = @(
    $memoryAdapter | ConvertTo-Json -Depth 20 -Compress
) -join ""
foreach ($forbidden in @(
    $gatewayApiNetwork
    $hermesNetwork
    "videobox-edge"
    "videobox-internal"
    "videobox-postgres"
    "/videobox-data"
    "/videobox-snapshot"
    "/opt/data"
    "docker.sock"
)) {
    Assert-True (
        -not $forbiddenMemoryAdapterText.Contains($forbidden)
    ) "Memory adapter contains a forbidden D2 boundary."
}

Write-Output "Hermes Yujin D2 static topology verified: exact chat, gateway, and optional memory adapter boundaries."
