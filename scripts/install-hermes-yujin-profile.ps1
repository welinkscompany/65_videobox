[CmdletBinding()]
param(
    [string]$EnvFile,
    [string]$ComposeFile,
    [string]$OverlayFile,
    [string]$DockerExecutable = "docker",
    [string]$InstallerContainerName = "videobox-hermes-yujin-profile-installer"
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

try {
    & $DockerExecutable @installArguments
    $installExitCode = $LASTEXITCODE
}
catch {
    throw "The Hermes Yujin profile installer container could not run."
}
if ($installExitCode -ne 0) {
    throw "The Hermes Yujin profile installation failed in its container."
}

Write-Output "Hermes Yujin profile installed in the named installer container."
