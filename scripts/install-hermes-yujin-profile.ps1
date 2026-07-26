[CmdletBinding()]
param(
    [string]$EnvFile,
    [string]$ComposeFile,
    [string]$OverlayFile,
    [string]$DockerExecutable = "docker",
    [string]$InstallerContainerName
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $repositoryRoot ".env.container"
}
if ([string]::IsNullOrWhiteSpace($ComposeFile)) {
    $ComposeFile = Join-Path $repositoryRoot "compose.yaml"
}
if ([string]::IsNullOrWhiteSpace($OverlayFile)) {
    $OverlayFile = Join-Path $repositoryRoot "compose.hermes-yujin.yaml"
}
$usesGeneratedContainerName = [string]::IsNullOrWhiteSpace($InstallerContainerName)
if ($usesGeneratedContainerName) {
    $InstallerContainerName = (
        "videobox-hermes-yujin-profile-installer-" +
        [Guid]::NewGuid().ToString("N")
    )
}
if ($InstallerContainerName -cnotmatch '^[a-z0-9][a-z0-9_.-]{0,127}$') {
    throw "The Hermes Yujin installer container name is invalid."
}
foreach ($requiredFile in @($EnvFile, $ComposeFile, $OverlayFile)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "A required container configuration file is missing."
    }
}
$resolvedEnvFile = (Resolve-Path -LiteralPath $EnvFile).Path
$resolvedComposeFile = (Resolve-Path -LiteralPath $ComposeFile).Path
$resolvedOverlayFile = (Resolve-Path -LiteralPath $OverlayFile).Path

$installArguments = @(
    "compose"
    "-f", $resolvedComposeFile
    "-f", $resolvedOverlayFile
    "--profile", "hermes-yujin"
    "--env-file", $resolvedEnvFile
    "run"
    "--rm"
    "--no-deps"
    "-T"
    "--name", $InstallerContainerName
    "--entrypoint", "hermes"
    "videobox-hermes-yujin"
    "profile"
    "install"
    "/opt/videobox-yujin-profile"
    "--name"
    "videobox-yujin"
    "--force"
    "-y"
)

$partialProfileState = (
    "Profile install may have left a partial profile in the " +
    "videobox_hermes_oauth_state named volume at /opt/data; " +
    "recovery is service-only; do not delete that volume. " +
    "Rerun uses --force idempotently."
)
$safeRerunRecovery = "Recovery: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-hermes-yujin.ps1 -EnvFile <approved-env-file>"

function Remove-GeneratedInstallerResidue {
    if (-not $usesGeneratedContainerName) {
        return
    }
    try {
        & $DockerExecutable "rm" "-f" $InstallerContainerName 2>$null | Out-Null
    }
    catch {
        # Best effort only; the thrown install error remains authoritative.
    }
}

function Stop-InstallerWithRedactedRecovery {
    param([string]$FailureMessage)

    [Console]::Error.WriteLine(
        $FailureMessage + " " +
        $partialProfileState + " " +
        $safeRerunRecovery
    )
    exit 1
}

try {
    & $DockerExecutable @installArguments
    $installExitCode = $LASTEXITCODE
}
catch {
    Remove-GeneratedInstallerResidue
    Stop-InstallerWithRedactedRecovery `
        "The Hermes Yujin profile installer container could not run."
}
if ($installExitCode -ne 0) {
    Remove-GeneratedInstallerResidue
    Stop-InstallerWithRedactedRecovery `
        "The Hermes Yujin profile installation failed in its container."
}

Write-Output "Hermes Yujin profile installed in a one-off named installer container."
