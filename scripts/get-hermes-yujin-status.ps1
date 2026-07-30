[CmdletBinding()]
param(
    [string]$EnvFile = "",
    [string]$DockerExecutable = "docker",
    [string]$StatusApiUri = "",
    [ValidateRange(1, 15)]
    [int]$TimeoutSec = 3
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
$serviceNames = @(
    "videobox-workspace"
    "videobox-agent-gateway"
    "videobox-hermes-yujin"
)

function Quote-ProcessArgument {
    param([string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

function New-ServiceRow {
    param(
        [string]$Name,
        [bool]$Present = $false,
        [bool]$Running = $false,
        [string]$Health = "unknown",
        [Nullable[int]]$ExitCode = $null
    )
    return [ordered]@{
        name = $Name
        present = $Present
        running = $Running
        health = $Health
        exit_code = $ExitCode
    }
}

function New-StatusPayload {
    param(
        [string]$State,
        [object[]]$Services,
        [bool]$HttpReady = $false,
        [bool]$ProviderReady = $false,
        [bool]$ChatVerified = $false,
        [object]$LastChatVerifiedAt = $null,
        [bool]$ApplicationStatusChecked = $false
    )
    return [ordered]@{
        schema_version = "v1"
        state = $State
        status_basis = "docker_compose"
        checked_at = [DateTimeOffset]::UtcNow.ToString("o")
        http_ready = $HttpReady
        provider_ready = $ProviderReady
        chat_verified = $ChatVerified
        last_chat_verified_at = $LastChatVerifiedAt
        application_status_checked = $ApplicationStatusChecked
        services = $Services
    }
}

function Write-StatusPayload {
    param([hashtable]$Payload)
    Write-Output ($Payload | ConvertTo-Json -Depth 6 -Compress)
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
                # The caller emits only a fixed sanitized status.
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

function ConvertFrom-ComposeRows {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return @()
    }
    try {
        $parsed = $Text | ConvertFrom-Json
        return @($parsed)
    }
    catch {
        $rows = @()
        foreach ($line in ($Text -split "`r?`n")) {
            if ([string]::IsNullOrWhiteSpace($line)) {
                continue
            }
            try {
                $rows += ,($line | ConvertFrom-Json)
            }
            catch {
                return @()
            }
        }
        return @($rows)
    }
}

function Resolve-Health {
    param([object]$Value)
    $health = ([string]$Value).Trim().ToLowerInvariant()
    if ($health -in @("healthy", "starting", "unhealthy")) {
        return $health
    }
    return "unknown"
}

function Assert-StatusApiUri {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }
    $uri = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri)) {
        throw "HERMES_YUJIN_STATUS_FAILED:status_api_uri_invalid"
    }
    if (
        $uri.Scheme -notin @("http", "https") -or
        $uri.Host.ToLowerInvariant() -notin @("127.0.0.1", "localhost", "::1", "[::1]") -or
        -not [string]::IsNullOrEmpty($uri.UserInfo) -or
        $uri.AbsolutePath -cne "/api/hermes-yujin/status" -or
        -not [string]::IsNullOrEmpty($uri.Query) -or
        -not [string]::IsNullOrEmpty($uri.Fragment)
    ) {
        throw "HERMES_YUJIN_STATUS_FAILED:status_api_uri_invalid"
    }
    return $uri
}

function Invoke-StatusApi {
    param([Uri]$Uri)
    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $handler.UseProxy = $false
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [System.Threading.Timeout]::InfiniteTimeSpan
    $request = New-Object System.Net.Http.HttpRequestMessage(
        [System.Net.Http.HttpMethod]::Get,
        $Uri
    )
    [void]$request.Headers.TryAddWithoutValidation(
        "Accept",
        "application/json"
    )
    $cancellation = New-Object System.Threading.CancellationTokenSource
    $cancellation.CancelAfter([TimeSpan]::FromSeconds($TimeoutSec))
    $response = $null
    $stream = $null
    $memory = $null
    try {
        $response = $client.SendAsync(
            $request,
            [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead,
            $cancellation.Token
        ).GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            return $null
        }
        $mediaType = [string]$response.Content.Headers.ContentType.MediaType
        if ($mediaType.ToLowerInvariant() -cne "application/json") {
            return $null
        }
        $contentLength = $response.Content.Headers.ContentLength
        if ($null -ne $contentLength -and [long]$contentLength -gt 16384) {
            return $null
        }
        $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $memory = New-Object System.IO.MemoryStream
        $buffer = New-Object byte[] 4096
        $total = 0
        while ($true) {
            $read = $stream.ReadAsync(
                $buffer,
                0,
                $buffer.Length,
                $cancellation.Token
            ).GetAwaiter().GetResult()
            if ($read -eq 0) {
                break
            }
            $total += $read
            if ($total -gt 16384) {
                return $null
            }
            $memory.Write($buffer, 0, $read)
        }
        $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
        $body = $strictUtf8.GetString($memory.ToArray())
        $payload = $body | ConvertFrom-Json
        $expected = @(
            "state",
            "http_ready",
            "provider_ready",
            "chat_verified",
            "checked_at",
            "last_chat_verified_at",
            "restart_available",
            "status_basis"
        )
        $actual = @($payload.PSObject.Properties.Name | Sort-Object)
        if (($actual -join "|") -cne (($expected | Sort-Object) -join "|")) {
            return $null
        }
        if (
            [string]$payload.status_basis -cne "application_path" -or
            [string]$payload.state -notin @(
                "not_configured", "stopped", "starting", "http_ready",
                "provider_ready", "chat_verified", "degraded"
            ) -or
            $payload.http_ready -isnot [bool] -or
            $payload.provider_ready -isnot [bool] -or
            $payload.chat_verified -isnot [bool] -or
            $payload.restart_available -ne $false
        ) {
            return $null
        }
        $checkedAt = ConvertFrom-StrictUtcTimestamp $payload.checked_at
        if ($null -eq $checkedAt) {
            return $null
        }
        $lastChatVerifiedAt = $null
        if ($null -ne $payload.last_chat_verified_at) {
            $lastChatVerifiedAt = ConvertFrom-StrictUtcTimestamp (
                $payload.last_chat_verified_at
            )
            if (
                $null -eq $lastChatVerifiedAt -or
                $lastChatVerifiedAt -gt $checkedAt
            ) {
                return $null
            }
        }
        $readiness = @(
            [bool]$payload.http_ready,
            [bool]$payload.provider_ready,
            [bool]$payload.chat_verified
        )
        $expectedReadiness = switch ([string]$payload.state) {
            "not_configured" { @($false, $false, $false); break }
            "stopped" { @($false, $false, $false); break }
            "starting" { @($false, $false, $false); break }
            "http_ready" { @($true, $false, $false); break }
            "provider_ready" { @($true, $true, $false); break }
            "chat_verified" { @($true, $true, $true); break }
            "degraded" { $null; break }
        }
        if (
            $null -ne $expectedReadiness -and
            ($readiness -join "|") -cne ($expectedReadiness -join "|")
        ) {
            return $null
        }
        if (
            [string]$payload.state -ceq "degraded" -and
            (
                [bool]$payload.provider_ready -or
                [bool]$payload.chat_verified
            )
        ) {
            return $null
        }
        return $payload
    }
    catch {
        return $null
    }
    finally {
        if ($null -ne $memory) {
            $memory.Dispose()
        }
        if ($null -ne $stream) {
            $stream.Dispose()
        }
        if ($null -ne $response) {
            $response.Dispose()
        }
        $cancellation.Dispose()
        $request.Dispose()
        $client.Dispose()
        $handler.Dispose()
    }
}

function ConvertFrom-StrictUtcTimestamp {
    param([object]$Value)
    if (
        $Value -isnot [string] -or
        [string]$Value -notmatch (
            '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}' +
            '(?:\.\d+)?(?:Z|\+00:00)$'
        )
    ) {
        return $null
    }
    $parsed = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse(
        [string]$Value,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::None,
        [ref]$parsed
    )) {
        return $null
    }
    if ($parsed.Offset -ne [TimeSpan]::Zero) {
        return $null
    }
    return $parsed
}

$statusUri = Assert-StatusApiUri -Value $StatusApiUri
$emptyRows = @($serviceNames | ForEach-Object { New-ServiceRow -Name $_ })
if (-not (Test-Path -LiteralPath $resolvedEnvFileInput -PathType Leaf)) {
    Write-StatusPayload (New-StatusPayload -State "not_configured" -Services $emptyRows)
    exit 0
}

$resolvedEnvFile = (Resolve-Path -LiteralPath $resolvedEnvFileInput).Path
$dockerResult = Invoke-CapturedDocker -Arguments @(
    "compose"
    "-f", $composeFile
    "-f", $overlayFile
    "--profile", "hermes-yujin"
    "--env-file", $resolvedEnvFile
    "ps"
    "--all"
    "--format", "json"
    "videobox-workspace"
    "videobox-agent-gateway"
    "videobox-hermes-yujin"
)
if ($dockerResult.ExitCode -ne 0) {
    Write-StatusPayload (New-StatusPayload -State "degraded" -Services $emptyRows)
    exit 0
}

$rawRows = @(ConvertFrom-ComposeRows -Text $dockerResult.StdOut)
$services = @()
foreach ($serviceName in $serviceNames) {
    $matches = @(
        $rawRows | Where-Object {
            [string]$_.Service -ceq $serviceName
        }
    )
    if ($matches.Count -ne 1) {
        $services += ,(New-ServiceRow -Name $serviceName)
        continue
    }
    $row = $matches[0]
    $state = ([string]$row.State).Trim().ToLowerInvariant()
    $running = $state -ceq "running"
    $exitCode = $null
    if ($null -ne $row.ExitCode -and [string]$row.ExitCode -match '^-?\d+$') {
        $exitCode = [int]$row.ExitCode
    }
    $services += ,(New-ServiceRow `
        -Name $serviceName `
        -Present $true `
        -Running $running `
        -Health (Resolve-Health $row.Health) `
        -ExitCode $exitCode)
}

$yujin = @($services | Where-Object { $_.name -ceq "videobox-hermes-yujin" })[0]
if (-not $yujin.present -or -not $yujin.running) {
    Write-StatusPayload (New-StatusPayload -State "stopped" -Services $services)
    exit 0
}
$allHealthy = @(
    $services | Where-Object {
        -not $_.present -or -not $_.running -or $_.health -cne "healthy"
    }
).Count -eq 0
if (-not $allHealthy) {
    Write-StatusPayload (New-StatusPayload -State "starting" -Services $services)
    exit 0
}

if ($null -eq $statusUri) {
    Write-StatusPayload (
        New-StatusPayload -State "http_ready" -Services $services -HttpReady $true
    )
    exit 0
}

$applicationStatus = Invoke-StatusApi -Uri $statusUri
if ($null -eq $applicationStatus) {
    Write-StatusPayload (
        New-StatusPayload `
            -State "degraded" `
            -Services $services `
            -HttpReady $true `
            -ApplicationStatusChecked $true
    )
    exit 0
}
Write-StatusPayload (
    New-StatusPayload `
        -State ([string]$applicationStatus.state) `
        -Services $services `
        -HttpReady ([bool]$applicationStatus.http_ready) `
        -ProviderReady ([bool]$applicationStatus.provider_ready) `
        -ChatVerified ([bool]$applicationStatus.chat_verified) `
        -LastChatVerifiedAt $applicationStatus.last_chat_verified_at `
        -ApplicationStatusChecked $true
)
