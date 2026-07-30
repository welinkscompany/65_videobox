[CmdletBinding()]
param(
    [string]$EnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) ".env.container"),
    [switch]$ValidateOnly,
    [string]$DockerExecutable = "docker",
    [string]$ProfileRoot
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repositoryRoot "compose.yaml"
$overlayFile = Join-Path $repositoryRoot "compose.hermes-yujin.yaml"
$canonicalProfileRoot = Join-Path $repositoryRoot "config/hermes/yujin"
if ([string]::IsNullOrWhiteSpace($ProfileRoot)) {
    $ProfileRoot = $canonicalProfileRoot
}
. (Join-Path $PSScriptRoot "hermes-yujin-environment-contract.ps1")
$pinnedHermesImage = "nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787"
$pinnedCryptographyRequirement = "cryptography==45.0.6"
$pythonExecutable = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
$credentialNames = @(
    "HERMES_YUJIN_GATEWAY_USERNAME"
    "HERMES_YUJIN_GATEWAY_PASSWORD"
    "HERMES_YUJIN_GATEWAY_PASSWORD_HASH"
    "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN"
    "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64"
    "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64"
    "VIDEOBOX_HERMES_CAPABILITY_KEY_ID"
    "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"
)

if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    throw "A real container environment file is required."
}
$resolvedEnvFile = (Resolve-Path -LiteralPath $EnvFile).Path

function Quote-ProcessArgument {
    param([string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Invoke-CapturedDocker {
    param(
        [string[]]$DockerArguments,
        [hashtable]$EnvironmentOverrides = @{},
        [string[]]$EnvironmentRemovals = @()
    )

    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $DockerExecutable
    $processInfo.Arguments = (
        $DockerArguments | ForEach-Object { Quote-ProcessArgument $_ }
    ) -join " "
    $processInfo.WorkingDirectory = $repositoryRoot
    $processInfo.UseShellExecute = $false
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.CreateNoWindow = $true
    foreach ($name in $EnvironmentRemovals) {
        [void]$processInfo.EnvironmentVariables.Remove($name)
    }
    foreach ($name in $EnvironmentOverrides.Keys) {
        $processInfo.EnvironmentVariables[$name] = $EnvironmentOverrides[$name]
    }

    try {
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $processInfo
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        [void]$stderrTask.GetAwaiter().GetResult()
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            StdOut = $stdout
        }
    }
    catch {
        throw "Docker validation process could not be executed."
    }
}

function Assert-ResolvedCredential {
    param(
        [string]$Name,
        [object]$Value
    )
    $text = if ($null -eq $Value) { "" } else { ([string]$Value).Replace('$$', '$') }
    if (
        [string]::IsNullOrWhiteSpace($text) -or
        $text -match '\$\{[^}]+\}' -or
        $text -match (
            '(?i)replace-before-starting|replace_me|placeholder|' +
            'change-me|changeme|sentinel'
        )
    ) {
        throw "Resolved container credential '$Name' is invalid."
    }
    return $text
}

function Assert-MatchedCapabilityKeyPair {
    param(
        [string]$PrivateKeyB64,
        [string]$PublicKeyB64
    )

    if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
        throw "Pinned capability validation runtime is unavailable."
    }
    $requirementsPath = Join-Path $repositoryRoot "requirements-dev.txt"
    if (
        -not (Test-Path -LiteralPath $requirementsPath -PathType Leaf) -or
        -not ((Get-Content -LiteralPath $requirementsPath) -ccontains $pinnedCryptographyRequirement)
    ) {
        throw "Pinned capability validation dependency is unavailable."
    }
    $validationCode = (
        "import base64, os; from importlib.metadata import version; " +
        "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; " +
        "from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat; " +
        "private_text=os.environ['VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64']; " +
        "public_text=os.environ['VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64']; " +
        "private=base64.b64decode(private_text+'='*(-len(private_text)%4),altchars=b'-_',validate=True); " +
        "public=base64.b64decode(public_text+'='*(-len(public_text)%4),altchars=b'-_',validate=True); " +
        "canonical_private=base64.urlsafe_b64encode(private).rstrip(b'=').decode('ascii'); " +
        "canonical_public=base64.urlsafe_b64encode(public).rstrip(b'=').decode('ascii'); " +
        "derived=Ed25519PrivateKey.from_private_bytes(private).public_key().public_bytes(Encoding.Raw,PublicFormat.Raw); " +
        "raise SystemExit(0 if version('cryptography')=='45.0.6' and len(private)==32 and len(public)==32 and canonical_private==private_text and canonical_public==public_text and derived==public else 1)"
    )
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $pythonExecutable
    $processInfo.Arguments = (
        @("-c", $validationCode) |
            ForEach-Object { Quote-ProcessArgument $_ }
    ) -join " "
    $processInfo.WorkingDirectory = $repositoryRoot
    $processInfo.UseShellExecute = $false
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.CreateNoWindow = $true
    $processInfo.EnvironmentVariables[
        "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64"
    ] = $PrivateKeyB64
    $processInfo.EnvironmentVariables[
        "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64"
    ] = $PublicKeyB64
    try {
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $processInfo
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        [void]$stdoutTask.GetAwaiter().GetResult()
        [void]$stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw "invalid"
        }
    }
    catch {
        throw "Resolved Hermes capability key pair is invalid."
    }
}

$configArguments = @(
    "compose"
    "-f", $composeFile
    "-f", $overlayFile
    "--profile", "hermes-yujin"
    "--env-file", $resolvedEnvFile
    "config"
    "--format", "json"
)
$configResult = Invoke-CapturedDocker `
    -DockerArguments $configArguments `
    -EnvironmentRemovals @(
        "POSTGRES_PASSWORD"
        "VIDEOBOX_CONTAINER_DATA_ROOT"
        "HERMES_YUJIN_GATEWAY_USERNAME"
        "HERMES_YUJIN_GATEWAY_PASSWORD"
        "HERMES_YUJIN_GATEWAY_PASSWORD_HASH"
        "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN"
        "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64"
        "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64"
        "VIDEOBOX_HERMES_CAPABILITY_KEY_ID"
        "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"
        "MEM0_API_KEY"
        "MISSING"
    )
if ($configResult.ExitCode -ne 0) {
    throw "Container configuration validation failed."
}
try {
    $rendered = $configResult.StdOut | ConvertFrom-Json
}
catch {
    throw "Container configuration validation returned an invalid model."
}

$gateway = $rendered.services.'videobox-agent-gateway'
$hermes = $rendered.services.'videobox-hermes-yujin'
$workspace = $rendered.services.'videobox-workspace'
$memoryAdapter = $rendered.services.'videobox-hermes-memory-adapter'
if (
    $null -eq $gateway -or
    $null -eq $hermes -or
    $null -eq $workspace -or
    $null -eq $memoryAdapter
) {
    throw "Container configuration validation is incomplete."
}

$gatewayEnvironmentNames = @($gateway.environment.PSObject.Properties.Name | Sort-Object)
$expectedGatewayEnvironmentNames = @(
    "HERMES_MEMORY_ADAPTER_URL"
    "HERMES_YUJIN_GATEWAY_PASSWORD"
    "HERMES_YUJIN_GATEWAY_USERNAME"
    "HERMES_YUJIN_URL"
    "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN"
    "VIDEOBOX_HERMES_CAPABILITY_KEY_ID"
    "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64"
    "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"
)
if (($gatewayEnvironmentNames -join "|") -cne ($expectedGatewayEnvironmentNames -join "|")) {
    throw "Agent gateway environment contract is invalid."
}
$hermesEnvironmentNames = @($hermes.environment.PSObject.Properties.Name | Sort-Object)
$expectedHermesEnvironmentNames = @(
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH"
    "HERMES_DASHBOARD_BASIC_AUTH_USERNAME"
    "HERMES_TUI_TOOLSETS"
)
if (($hermesEnvironmentNames -join "|") -cne ($expectedHermesEnvironmentNames -join "|")) {
    throw "Hermes environment contract is invalid."
}
$memoryAdapterEnvironmentNames = @(
    $memoryAdapter.environment.PSObject.Properties.Name | Sort-Object
)
$expectedMemoryAdapterEnvironmentNames = @(
    "MEM0_API_KEY"
    "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"
)
if (
    ($memoryAdapterEnvironmentNames -join "|") -cne
    ($expectedMemoryAdapterEnvironmentNames -join "|")
) {
    throw "Hermes memory adapter environment contract is invalid."
}

$gatewayUsername = Assert-ResolvedCredential `
    "HERMES_YUJIN_GATEWAY_USERNAME" `
    $gateway.environment.HERMES_YUJIN_GATEWAY_USERNAME
$gatewayPassword = Assert-ResolvedCredential `
    "HERMES_YUJIN_GATEWAY_PASSWORD" `
    $gateway.environment.HERMES_YUJIN_GATEWAY_PASSWORD
$hermesUsername = Assert-ResolvedCredential `
    "HERMES_DASHBOARD_BASIC_AUTH_USERNAME" `
    $hermes.environment.HERMES_DASHBOARD_BASIC_AUTH_USERNAME
$hermesPasswordHash = Assert-ResolvedCredential `
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH" `
    $hermes.environment.HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH
$gatewayServiceToken = Assert-ResolvedCredential `
    "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN" `
    $gateway.environment.VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN
$capabilityPrivateKeyB64 = Assert-ResolvedCredential `
    "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64" `
    $gateway.environment.VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64
$capabilityPublicKeyB64 = Assert-ResolvedCredential `
    "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64" `
    $workspace.environment.VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64
$gatewayCapabilityKeyId = Assert-ResolvedCredential `
    "VIDEOBOX_HERMES_CAPABILITY_KEY_ID" `
    $gateway.environment.VIDEOBOX_HERMES_CAPABILITY_KEY_ID
$workspaceCapabilityKeyId = Assert-ResolvedCredential `
    "VIDEOBOX_HERMES_CAPABILITY_KEY_ID" `
    $workspace.environment.VIDEOBOX_HERMES_CAPABILITY_KEY_ID
$memoryAdapterToken = Assert-ResolvedCredential `
    "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN" `
    $memoryAdapter.environment.VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN
$memoryApiKey = [string]$memoryAdapter.environment.MEM0_API_KEY
if ($gatewayPassword.Length -lt 12) {
    throw "Resolved container credential 'HERMES_YUJIN_GATEWAY_PASSWORD' is invalid."
}
if (
    $gatewayServiceToken.Length -lt 32 -or
    @($gatewayServiceToken.ToCharArray() | Select-Object -Unique).Count -lt 8 -or
    $gatewayServiceToken -match '(?i)changeme|replace_me|placeholder'
) {
    throw "Resolved container credential 'VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN' is invalid."
}
if (
    $memoryAdapterToken.Length -lt 32 -or
    @($memoryAdapterToken.ToCharArray() | Select-Object -Unique).Count -lt 8 -or
    $memoryAdapterToken -match '(?i)changeme|replace_me|placeholder'
) {
    throw "Resolved container credential 'VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN' is invalid."
}
if (
    $gatewayCapabilityKeyId -cne $workspaceCapabilityKeyId -or
    $gatewayCapabilityKeyId -notmatch '^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$'
) {
    throw "Resolved Hermes capability key ID is invalid."
}
Assert-MatchedCapabilityKeyPair `
    -PrivateKeyB64 $capabilityPrivateKeyB64 `
    -PublicKeyB64 $capabilityPublicKeyB64
if ($hermes.environment.HERMES_TUI_TOOLSETS -cne "context_engine") {
    throw "Hermes toolset contract is invalid."
}
if ($gatewayUsername -cne $hermesUsername) {
    throw "Gateway and Hermes usernames do not match."
}
if ($gateway.environment.HERMES_YUJIN_URL -cne "http://videobox-hermes-yujin:9120") {
    throw "Agent gateway Hermes URL is invalid."
}
if (
    $gateway.environment.HERMES_MEMORY_ADAPTER_URL -cne
    "http://videobox-hermes-memory-adapter:8082" -or
    $gateway.environment.VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN -cne
    $memoryAdapterToken
) {
    throw "Hermes memory adapter gateway configuration is invalid."
}
if (
    $workspace.environment.VIDEOBOX_AGENT_GATEWAY_URL -cne
    "http://videobox-agent-gateway:8081" -or
    $workspace.environment.VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN -cne
    $gatewayServiceToken
) {
    throw "Workspace agent gateway configuration is invalid."
}
foreach ($name in @($workspace.environment.PSObject.Properties.Name)) {
    if ($name -match '^HERMES(?:_YUJIN|_DASHBOARD)') {
        throw "Workspace received a forbidden Hermes credential."
    }
}
if (
    $null -ne $workspace.environment.PSObject.Properties["MEM0_API_KEY"] -or
    $null -ne $workspace.environment.PSObject.Properties[
        "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"
    ] -or
    $null -ne $hermes.environment.PSObject.Properties["MEM0_API_KEY"] -or
    $null -ne $hermes.environment.PSObject.Properties[
        "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"
    ] -or
    $null -ne $gateway.environment.PSObject.Properties["MEM0_API_KEY"]
) {
    throw "Hermes memory credential ownership is invalid."
}
if (
    $null -ne $gateway.environment.PSObject.Properties[
        "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64"
    ] -or
    $null -ne $workspace.environment.PSObject.Properties[
        "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64"
    ]
) {
    throw "Hermes capability key ownership is invalid."
}
foreach ($name in @($hermes.environment.PSObject.Properties.Name)) {
    if ($name -match '^VIDEOBOX_HERMES_CAPABILITY_') {
        throw "Hermes received forbidden capability key material."
    }
}
Assert-NoHermesYujinCredentialValueAliases `
    -Environment $workspace.environment `
    -ExactCredentialValues @($gatewayUsername) `
    -SecretSubstringValues @(
        $gatewayPassword
        $hermesPasswordHash
    ) `
    -FailureMessage "Workspace received a forbidden Hermes credential."

$passwordCheckCode = (
    "import os; from plugins.dashboard_auth.basic import _verify_password; " +
    "raise SystemExit(0 if _verify_password(" +
    "os.environ['HERMES_YUJIN_GATEWAY_PASSWORD'], " +
    "os.environ['HERMES_YUJIN_GATEWAY_PASSWORD_HASH']) else 1)"
)
$passwordCheck = Invoke-CapturedDocker `
    -DockerArguments @(
        "run"
        "--rm"
        "--network", "none"
        "-e", "HERMES_YUJIN_GATEWAY_PASSWORD"
        "-e", "HERMES_YUJIN_GATEWAY_PASSWORD_HASH"
        "--entrypoint", "python"
        $pinnedHermesImage
        "-c", $passwordCheckCode
    ) `
    -EnvironmentOverrides @{
        "HERMES_YUJIN_GATEWAY_PASSWORD" = $gatewayPassword
        "HERMES_YUJIN_GATEWAY_PASSWORD_HASH" = $hermesPasswordHash
    }
if ($passwordCheck.ExitCode -ne 0) {
    throw "Hermes gateway password and hash validation failed."
}

& (Join-Path $PSScriptRoot "verify-hermes-yujin-profile.ps1") `
    -StaticOnly `
    -ProfileRoot $ProfileRoot

if ($ValidateOnly) {
    Write-Output (
        "Hermes Yujin container configuration, credential relationship, " +
        "and static profile contents verified."
    )
    exit 0
}

$resolvedProfileRoot = (Resolve-Path -LiteralPath $ProfileRoot).Path
$resolvedCanonicalProfileRoot = (Resolve-Path -LiteralPath $canonicalProfileRoot).Path
if (
    -not [string]::Equals(
        $resolvedProfileRoot,
        $resolvedCanonicalProfileRoot,
        [StringComparison]::OrdinalIgnoreCase
    )
) {
    throw "Runtime startup requires the canonical mounted Yujin profile source."
}

if ([string]::IsNullOrWhiteSpace($memoryApiKey)) {
    try {
        $memoryDisableResult = Invoke-CapturedDocker -DockerArguments @(
            "compose"
            "-f", $composeFile
            "-f", $overlayFile
            "--profile", "hermes-yujin"
            "--env-file", $resolvedEnvFile
            "stop"
            "videobox-hermes-memory-adapter"
        )
    }
    catch {
        throw (
            "Memory storage disable failed; " +
            "existing chat services were left unchanged."
        )
    }
    if ($memoryDisableResult.ExitCode -ne 0) {
        throw (
            "Memory storage disable failed; " +
            "existing chat services were left unchanged."
        )
    }
}

function Invoke-TargetedComposeUp {
    param(
        [string]$ServiceName,
        [string]$FailureMessage,
        [string[]]$AdditionalArguments = @()
    )

    $upArguments = @(
        "compose"
        "-f", $composeFile
        "-f", $overlayFile
        "--profile", "hermes-yujin"
        "--env-file", $resolvedEnvFile
        "up"
        "-d"
        "--build"
    )
    $upArguments += $AdditionalArguments
    $upArguments += $ServiceName
    $upExitCode = 1
    Push-Location $repositoryRoot
    try {
        & $DockerExecutable @upArguments
        $upExitCode = $LASTEXITCODE
    }
    catch {
        throw $FailureMessage
    }
    finally {
        Pop-Location
    }
    if ($upExitCode -ne 0) {
        throw $FailureMessage
    }
}

$stateArguments = @(
    "compose"
    "-f", $composeFile
    "-f", $overlayFile
    "--profile", "hermes-yujin"
    "--env-file", $resolvedEnvFile
    "ps"
    "--status", "running"
    "--services"
    "videobox-hermes-yujin"
)
$stateResult = Invoke-CapturedDocker -DockerArguments $stateArguments
if ($stateResult.ExitCode -ne 0) {
    throw "Existing Hermes Yujin runtime state could not be determined."
}
$hermesWasRunning = @(
    $stateResult.StdOut -split "`r?`n" |
        Where-Object { $_.Trim() -ceq "videobox-hermes-yujin" }
).Count -gt 0

$persistentProfileState = (
    "Profile install persists in the videobox_hermes_oauth_state named volume " +
    "at /opt/data; service cleanup does not delete that volume. " +
    "Rerun uses --force idempotently."
)
$partialProfileState = (
    "Profile install may have left a partial profile in the " +
    "videobox_hermes_oauth_state named volume at /opt/data; " +
    "recovery is service-only; do not delete that volume. " +
    "Rerun uses --force idempotently."
)
$safeRerunRecovery = "Recovery: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-hermes-yujin.ps1 -EnvFile <approved-env-file>"

try {
    & (Join-Path $PSScriptRoot "install-hermes-yujin-profile.ps1") `
        -EnvFile $resolvedEnvFile `
        -ComposeFile $composeFile `
        -OverlayFile $overlayFile `
        -DockerExecutable $DockerExecutable
}
catch {
    throw (
        "The Hermes Yujin profile installation failed. " +
        $partialProfileState + " " +
        $safeRerunRecovery
    )
}
if ($LASTEXITCODE -ne 0) {
    throw (
        "The Hermes Yujin profile installation failed. " +
        $partialProfileState + " " +
        $safeRerunRecovery
    )
}

if (-not $hermesWasRunning) {
    try {
        Invoke-TargetedComposeUp `
            -ServiceName "videobox-hermes-yujin" `
            -FailureMessage "Targeted Hermes Yujin runtime startup failed." `
            -AdditionalArguments @("--wait")
    }
    catch {
        throw (
            "Targeted Hermes Yujin runtime startup failed. " +
            $persistentProfileState + " " +
            $safeRerunRecovery
        )
    }
}

$quiesceResult = Invoke-CapturedDocker -DockerArguments @(
    "compose"
    "-f", $composeFile
    "-f", $overlayFile
    "--profile", "hermes-yujin"
    "--env-file", $resolvedEnvFile
    "stop"
    "videobox-agent-gateway"
    "videobox-workspace"
)
if ($quiesceResult.ExitCode -ne 0) {
    if ($hermesWasRunning) {
        throw (
            "Coordinated capability admission quiesce failed. " +
            "Pre-existing Hermes service was left running. " +
            $persistentProfileState + " " +
            $safeRerunRecovery
        )
    }
    $quiesceFailureStopResult = Invoke-CapturedDocker -DockerArguments @(
        "compose"
        "-f", $composeFile
        "-f", $overlayFile
        "--profile", "hermes-yujin"
        "--env-file", $resolvedEnvFile
        "stop"
        "videobox-hermes-yujin"
    )
    if ($quiesceFailureStopResult.ExitCode -eq 0) {
        throw (
            "Coordinated capability admission quiesce failed; the " +
            "newly started Hermes service was stopped. " +
            $persistentProfileState + " " +
            $safeRerunRecovery
        )
    }
    throw (
        "Coordinated capability admission quiesce failed and automatic " +
        "stop failed. " +
        $persistentProfileState + " " +
        $safeRerunRecovery
    )
}

try {
    Invoke-TargetedComposeUp `
        -ServiceName "videobox-workspace" `
        -FailureMessage "Targeted VideoBox workspace restart failed." `
        -AdditionalArguments @("--force-recreate", "--wait")
}
catch {
    if ($hermesWasRunning) {
        throw (
            "Targeted VideoBox workspace restart failed; " +
            "Hermes capability admission remains quiesced. " +
            "Pre-existing Hermes service was left running. " +
            $persistentProfileState + " " +
            $safeRerunRecovery
        )
    }

    $workspaceFailureStopResult = Invoke-CapturedDocker -DockerArguments @(
        "compose"
        "-f", $composeFile
        "-f", $overlayFile
        "--profile", "hermes-yujin"
        "--env-file", $resolvedEnvFile
        "stop"
        "videobox-hermes-yujin"
    )
    if ($workspaceFailureStopResult.ExitCode -eq 0) {
        throw (
            "Targeted VideoBox workspace restart failed; " +
            "Hermes capability admission remains quiesced and the " +
            "newly started Hermes service was stopped. " +
            $persistentProfileState + " " +
            $safeRerunRecovery
        )
    }
    throw (
        "Targeted VideoBox workspace restart failed and automatic stop failed; " +
        "Hermes capability admission remains quiesced. " +
        $persistentProfileState + " " +
        $safeRerunRecovery
    )
}

try {
    Invoke-TargetedComposeUp `
        -ServiceName "videobox-agent-gateway" `
        -FailureMessage "Targeted Hermes Yujin gateway startup failed." `
        -AdditionalArguments @("--force-recreate", "--wait")
}
catch {
    $gatewayStopArguments = @(
        "compose"
        "-f", $composeFile
        "-f", $overlayFile
        "--profile", "hermes-yujin"
        "--env-file", $resolvedEnvFile
        "stop"
        "videobox-agent-gateway"
    )
    $gatewayStopSucceeded = $false
    try {
        $gatewayStopResult = Invoke-CapturedDocker `
            -DockerArguments $gatewayStopArguments
        $gatewayStopSucceeded = $gatewayStopResult.ExitCode -eq 0
    }
    catch {
        $gatewayStopSucceeded = $false
    }

    if ($hermesWasRunning) {
        if (-not $gatewayStopSucceeded) {
            throw (
                "Targeted Hermes Yujin gateway startup failed and gateway " +
                "stop failed; admission quiescence could not be confirmed. " +
                "Pre-existing Hermes service was left running. " +
                $persistentProfileState + " " +
                $safeRerunRecovery
            )
        }
        throw (
            "Targeted Hermes Yujin gateway startup failed. " +
            "The failed gateway was stopped. " +
            "Pre-existing Hermes service was left running. " +
            $persistentProfileState + " " +
            $safeRerunRecovery
        )
    }

    $stopArguments = @(
        "compose"
        "-f", $composeFile
        "-f", $overlayFile
        "--profile", "hermes-yujin"
        "--env-file", $resolvedEnvFile
        "stop"
        "videobox-hermes-yujin"
    )
    $stopSucceeded = $false
    try {
        $stopResult = Invoke-CapturedDocker -DockerArguments $stopArguments
        $stopSucceeded = $stopResult.ExitCode -eq 0
    }
    catch {
        $stopSucceeded = $false
    }
    if ($stopSucceeded) {
        if (-not $gatewayStopSucceeded) {
            throw (
                "Targeted Hermes Yujin gateway startup failed and gateway " +
                "stop failed; admission quiescence could not be confirmed. " +
                "The newly started Hermes service was stopped. " +
                $persistentProfileState + " " +
                $safeRerunRecovery
            )
        }
        throw (
            "Targeted Hermes Yujin gateway startup failed. " +
            "The failed gateway was stopped. " +
            "The newly started Hermes service was stopped. " +
            $persistentProfileState + " " +
            $safeRerunRecovery
        )
    }
    if (-not $gatewayStopSucceeded) {
        throw (
            "Targeted Hermes Yujin gateway startup failed and gateway stop " +
            "failed; admission quiescence could not be confirmed and " +
            "automatic Hermes stop failed. " +
            "Recovery: docker compose -f compose.yaml -f compose.hermes-yujin.yaml " +
            "--profile hermes-yujin --env-file <approved-env-file> " +
            "stop videobox-hermes-yujin. " +
            $persistentProfileState + " " +
            $safeRerunRecovery
        )
    }
    throw (
        "Targeted Hermes Yujin gateway startup failed and automatic stop failed. " +
        "The failed gateway was stopped. " +
        "Recovery: docker compose -f compose.yaml -f compose.hermes-yujin.yaml " +
        "--profile hermes-yujin --env-file <approved-env-file> " +
        "stop videobox-hermes-yujin. " +
        $persistentProfileState + " " +
        $safeRerunRecovery
    )
}

if ([string]::IsNullOrWhiteSpace($memoryApiKey)) {
    Write-Output (
        "Memory storage is disabled; interactive Yujin chat remains available."
    )
}
else {
    try {
        Invoke-TargetedComposeUp `
            -ServiceName "videobox-hermes-memory-adapter" `
            -FailureMessage "Optional Hermes memory adapter startup failed." `
            -AdditionalArguments @("--force-recreate", "--wait")
    }
    catch {
        Write-Warning (
            "Optional Hermes memory adapter startup failed; " +
            "chat remains available."
        )
        $memoryStopSucceeded = $false
        try {
            $memoryStopResult = Invoke-CapturedDocker -DockerArguments @(
                "compose"
                "-f", $composeFile
                "-f", $overlayFile
                "--profile", "hermes-yujin"
                "--env-file", $resolvedEnvFile
                "stop"
                "videobox-hermes-memory-adapter"
            )
            $memoryStopSucceeded = $memoryStopResult.ExitCode -eq 0
        }
        catch {
            $memoryStopSucceeded = $false
        }
        if (-not $memoryStopSucceeded) {
            Write-Warning (
                "Optional Hermes memory adapter startup failed; " +
                "stale memory adapter could not be stopped; " +
                "chat remains available."
            )
        }
    }
}

Write-Output (
    "Hermes Yujin and its agent gateway were targeted for startup."
)
