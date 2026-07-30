[CmdletBinding()]
param(
    [string]$EnvFile = "",
    [string]$DockerExecutable = "docker",
    [ValidateRange(1, 120)]
    [int]$TimeoutSec = 30,
    [ValidateRange(10, 5000)]
    [int]$PollIntervalMs = 250
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$resolvedEnvFileInput = if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    Join-Path $repositoryRoot ".env.container"
}
else {
    $EnvFile
}
$composeFile = Join-Path $repositoryRoot "compose.yaml"
$overlayFile = Join-Path $repositoryRoot "compose.hermes-yujin.yaml"
$targetService = "videobox-hermes-yujin"

function Quote-ProcessArgument {
    param([string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Invoke-CapturedDocker {
    param([string[]]$Arguments)
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $DockerExecutable
    $processInfo.Arguments = (
        $Arguments | ForEach-Object { Quote-ProcessArgument $_ }
    ) -join " "
    $processInfo.WorkingDirectory = $repositoryRoot
    $processInfo.UseShellExecute = $false
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.CreateNoWindow = $true
    try {
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $processInfo
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSec * 1000)) {
            try {
                $process.Kill()
            }
            catch {
                # The caller reports only a fixed redacted marker.
            }
            return [pscustomobject]@{
                ExitCode = 124
                StdOut = ""
            }
        }
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        [void]$stderrTask.GetAwaiter().GetResult()
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            StdOut = $stdout
        }
    }
    catch {
        return [pscustomobject]@{
            ExitCode = 127
            StdOut = ""
        }
    }
}

function New-ComposeArguments {
    param([string[]]$Tail)
    $arguments = @(
        "compose"
        "-f", $composeFile
        "-f", $overlayFile
        "--profile", "hermes-yujin"
        "--env-file", $resolvedEnvFile
    )
    $arguments += $Tail
    return $arguments
}

function Get-ExactContainerId {
    $result = Invoke-CapturedDocker -Arguments (
        New-ComposeArguments -Tail @("ps", "--all", "-q", $targetService)
    )
    if ($result.ExitCode -ne 0) {
        throw "HERMES_YUJIN_RESTART_FAILED:container_state"
    }
    $ids = @(
        $result.StdOut -split "`r?`n" |
            ForEach-Object { $_.Trim() } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    if ($ids.Count -eq 0) {
        throw "HERMES_YUJIN_RESTART_FAILED:container_missing"
    }
    if (
        $ids.Count -ne 1 -or
        $ids[0] -notmatch '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'
    ) {
        throw "HERMES_YUJIN_RESTART_FAILED:container_state"
    }
    return $ids[0]
}

function Test-TargetHealthy {
    $result = Invoke-CapturedDocker -Arguments (
        New-ComposeArguments -Tail @(
            "ps", "--all", "--format", "json", $targetService
        )
    )
    if ($result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($result.StdOut)) {
        return $false
    }
    try {
        $parsed = $result.StdOut | ConvertFrom-Json
        $rows = @($parsed)
    }
    catch {
        return $false
    }
    if ($rows.Count -ne 1) {
        return $false
    }
    return (
        [string]$rows[0].Service -ceq $targetService -and
        [string]$rows[0].ID -ceq $beforeId -and
        ([string]$rows[0].State).ToLowerInvariant() -ceq "running" -and
        ([string]$rows[0].Health).ToLowerInvariant() -ceq "healthy"
    )
}

if (-not (Test-Path -LiteralPath $resolvedEnvFileInput -PathType Leaf)) {
    throw "HERMES_YUJIN_RESTART_FAILED:configuration_missing"
}
$resolvedEnvFile = (Resolve-Path -LiteralPath $resolvedEnvFileInput).Path
$beforeId = Get-ExactContainerId

$restartResult = Invoke-CapturedDocker -Arguments (
    New-ComposeArguments -Tail @("restart", $targetService)
)
if ($restartResult.ExitCode -ne 0) {
    throw "HERMES_YUJIN_RESTART_FAILED:restart_command"
}

$afterId = Get-ExactContainerId
if ($afterId -cne $beforeId) {
    throw "HERMES_YUJIN_RESTART_FAILED:container_replaced"
}

$deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSec)
while ([DateTimeOffset]::UtcNow -lt $deadline) {
    if (Test-TargetHealthy) {
        Write-Output "HERMES_YUJIN_RESTARTED"
        exit 0
    }
    Start-Sleep -Milliseconds $PollIntervalMs
}
throw "HERMES_YUJIN_RESTART_FAILED:health_timeout"
