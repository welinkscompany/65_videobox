[CmdletBinding()]
param(
    [string]$EnvFile = (Join-Path (Split-Path -Parent $PSScriptRoot) ".env.container"),
    [switch]$ValidateOnly,
    [string]$DockerExecutable = "docker"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repositoryRoot "compose.yaml"
$overlayFile = Join-Path $repositoryRoot "compose.hermes-yujin.yaml"
$pinnedHermesImage = "nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787"
$credentialNames = @(
    "HERMES_YUJIN_GATEWAY_USERNAME"
    "HERMES_YUJIN_GATEWAY_PASSWORD"
    "HERMES_YUJIN_GATEWAY_PASSWORD_HASH"
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
        $text -match '(?i)replace-before-starting|placeholder|change-me|sentinel'
    ) {
        throw "Resolved container credential '$Name' is invalid."
    }
    return $text
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
if ($null -eq $gateway -or $null -eq $hermes -or $null -eq $workspace) {
    throw "Container configuration validation is incomplete."
}

$gatewayEnvironmentNames = @($gateway.environment.PSObject.Properties.Name | Sort-Object)
$expectedGatewayEnvironmentNames = @(
    "HERMES_YUJIN_GATEWAY_PASSWORD"
    "HERMES_YUJIN_GATEWAY_USERNAME"
    "HERMES_YUJIN_URL"
)
if (($gatewayEnvironmentNames -join "|") -cne ($expectedGatewayEnvironmentNames -join "|")) {
    throw "Agent gateway environment contract is invalid."
}
$hermesEnvironmentNames = @($hermes.environment.PSObject.Properties.Name | Sort-Object)
$expectedHermesEnvironmentNames = @(
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH"
    "HERMES_DASHBOARD_BASIC_AUTH_USERNAME"
)
if (($hermesEnvironmentNames -join "|") -cne ($expectedHermesEnvironmentNames -join "|")) {
    throw "Hermes environment contract is invalid."
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
if ($gatewayUsername -cne $hermesUsername) {
    throw "Gateway and Hermes usernames do not match."
}
if ($gateway.environment.HERMES_YUJIN_URL -cne "http://videobox-hermes-yujin:9120") {
    throw "Agent gateway Hermes URL is invalid."
}
foreach ($name in @($workspace.environment.PSObject.Properties.Name)) {
    if ($name -match '^HERMES(?:_YUJIN|_DASHBOARD)') {
        throw "Workspace received a forbidden Hermes credential."
    }
}
$workspaceEnvironmentJson = (
    $workspace.environment | ConvertTo-Json -Depth 20 -Compress
).Replace('$$', '$')
foreach ($credentialValue in @(
    $gatewayUsername
    $gatewayPassword
    $hermesPasswordHash
)) {
    if ($workspaceEnvironmentJson.Contains([string]$credentialValue)) {
        throw "Workspace received a forbidden Hermes credential."
    }
}

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

if ($ValidateOnly) {
    Write-Output "Hermes Yujin container configuration and credential relationship verified."
    exit 0
}

$upArguments = @(
    "compose"
    "-f", $composeFile
    "-f", $overlayFile
    "--profile", "hermes-yujin"
    "--env-file", $resolvedEnvFile
    "up"
    "-d"
    "--build"
    "videobox-hermes-yujin"
    "videobox-agent-gateway"
)
$upExitCode = 1
Push-Location $repositoryRoot
try {
    & $DockerExecutable @upArguments
    $upExitCode = $LASTEXITCODE
}
catch {
    throw "Targeted Hermes Yujin startup could not be executed."
}
finally {
    Pop-Location
}
if ($upExitCode -ne 0) {
    throw "Targeted Hermes Yujin startup failed."
}

Write-Output "Hermes Yujin and its agent gateway were targeted for startup."
