[CmdletBinding()]
param(
    [switch]$StaticOnly,
    [switch]$Live,
    [switch]$ConfirmServiceStop,
    [switch]$ConfirmConversationWrite,
    [switch]$ConfirmDisposableProject,
    [string]$EnvFile = "",
    [string]$ProjectId,
    [string]$SessionId,
    [int]$ExpectedSessionRevision = 0,
    [string]$BaseUri = "http://127.0.0.1:8000",
    [string]$DockerExecutable = "docker",
    [string]$PythonExecutable = "",
    [string]$NpmExecutable = "npm.cmd",
    [string]$PowerShellExecutable = "powershell",
    [ValidateRange(10, 600)]
    [int]$StaticTimeoutSec = 120,
    [ValidateRange(1, 60)]
    [int]$TimeoutSec = 10
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$targetService = "videobox-hermes-yujin"
$composeFile = Join-Path $repositoryRoot "compose.yaml"
$overlayFile = Join-Path $repositoryRoot "compose.hermes-yujin.yaml"

if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $PythonExecutable = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
}
$restartScript = Join-Path $PSScriptRoot "restart-hermes-yujin.ps1"
$smokeScript = Join-Path $PSScriptRoot "smoke-hermes-yujin-chat.ps1"

$backendNodeIds = @(
    "tests/test_agent_gateway_hermes_rpc_client.py::test_expired_ticket_before_prompt_acceptance_is_refreshed_once"
    "tests/test_agent_gateway_hermes_rpc_client.py::test_connection_loss_after_prompt_acceptance_is_never_retried"
    "tests/test_hermes_run_store.py::test_run_events_are_atomic_ordered_and_restart_replayable"
    "tests/test_hermes_run_store.py::test_recovery_interrupts_orphans_once_without_provider_redispatch"
    "tests/test_hermes_run_service.py::test_closing_one_subscription_does_not_cancel_provider_run"
    "tests/test_api_hermes_conversation.py::test_startup_interrupts_orphan_without_gateway_dispatch"
    "tests/test_hermes_yujin_capability_lifecycle.py::test_sqlite_recover_interrupted_coordinated_restart_revokes_active_capabilities"
)
$frontendFiles = @(
    "src/features/editor/workbench/hermesSseClient.test.ts"
    "src/features/editor/workbench/editor-workbench-route.test.tsx"
)

function ConvertTo-ProcessArgument {
    param([string]$Value)
    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Invoke-CapturedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [int]$ProcessTimeoutSec = 0
    )
    if ($ProcessTimeoutSec -le 0) {
        $ProcessTimeoutSec = $TimeoutSec
    }
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $FilePath
    $processInfo.Arguments = (
        $Arguments | ForEach-Object { ConvertTo-ProcessArgument $_ }
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
        if (-not $process.WaitForExit($ProcessTimeoutSec * 1000)) {
            try {
                $process.Kill()
            }
            catch {
                # The bounded caller reports only a fixed marker.
            }
            return [pscustomobject]@{
                ExitCode = 124
                StdOut = ""
                StdErr = ""
            }
        }
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            StdOut = $stdout
            StdErr = $stderr
        }
    }
    catch {
        return [pscustomobject]@{
            ExitCode = 127
            StdOut = ""
            StdErr = ""
        }
    }
}

function Test-ApprovedEnvironmentFile {
    param([string]$Path)
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' (
        [StringComparer]::Ordinal
    )
    $assignments = 0
    foreach ($line in (Get-Content -LiteralPath $Path)) {
        $trimmed = ([string]$line).Trim()
        if (
            [string]::IsNullOrWhiteSpace($trimmed) -or
            $trimmed.StartsWith("#")
        ) {
            continue
        }
        if ($trimmed -notmatch '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            return $false
        }
        $key = [string]$Matches[1]
        $value = ([string]$Matches[2]).Trim()
        if (
            -not $seen.Add($key) -or
            [string]::IsNullOrWhiteSpace($value)
        ) {
            return $false
        }
        if (
            ($value.StartsWith('"') -and $value -notmatch '^"[^"]*"$') -or
            (-not $value.StartsWith('"') -and $value.Contains('"')) -or
            ($value.StartsWith("'") -and $value -notmatch "^'[^']*'$") -or
            (-not $value.StartsWith("'") -and $value.Contains("'")) -or
            $value -match '(?i)(replace-before|change-?me|placeholder)'
        ) {
            return $false
        }
        $assignments += 1
    }
    return $assignments -gt 0
}

function Throw-PreflightFailure {
    param([string]$Marker)
    throw (
        "HERMES_YUJIN_FAILURE_DRILL_PREFLIGHT_FAILED:$Marker " +
        "docker_reads=$script:dockerReads api_reads=$script:apiReads " +
        "docker_mutations=0 conversation_writes=0"
    )
}

function Resolve-RestartRecoveryMarker {
    param([object]$Result)
    $captured = (
        [string]$Result.StdOut + "`n" + [string]$Result.StdErr
    )
    if (
        $captured -match (
            'HERMES_YUJIN_RESTART_FAILED:' +
            '(restart_command|health_timeout|container_replaced)'
        )
    ) {
        switch ([string]$Matches[1]) {
            "health_timeout" { return "health_timeout" }
            "container_replaced" { return "container_identity" }
            default { return "restart_command" }
        }
    }
    return "restart_command"
}

function New-ComposeArguments {
    param([string[]]$Tail)
    $arguments = @(
        "compose"
        "-f", $composeFile
        "-f", $overlayFile
        "--profile", "hermes-yujin"
        "--env-file", $script:resolvedEnvFile
    )
    $arguments += $Tail
    return $arguments
}

function Get-ExactHealthyContainer {
    $result = Invoke-CapturedProcess `
        -FilePath $DockerExecutable `
        -Arguments (
            New-ComposeArguments -Tail @(
                "ps", "--all", "--format", "json", $targetService
            )
        )
    if ($result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($result.StdOut)) {
        return $null
    }
    try {
        $rows = @($result.StdOut | ConvertFrom-Json)
    }
    catch {
        return $null
    }
    if (
        $rows.Count -ne 1 -or
        [string]$rows[0].Service -cne $targetService -or
        ([string]$rows[0].State).ToLowerInvariant() -cne "running" -or
        ([string]$rows[0].Health).ToLowerInvariant() -cne "healthy" -or
        [string]::IsNullOrWhiteSpace([string]$rows[0].ID)
    ) {
        return $null
    }
    return [pscustomobject]@{ Id = [string]$rows[0].ID }
}

function Invoke-RedactedJsonRequest {
    param(
        [Parameter(Mandatory = $true)]
        [Uri]$Uri,
        [Parameter(Mandatory = $true)]
        [string]$Method,
        [object]$Body
    )
    $handler = $null
    $client = $null
    $content = $null
    $response = $null
    try {
        $handler = New-Object System.Net.Http.HttpClientHandler
        $handler.AllowAutoRedirect = $false
        $handler.UseProxy = $false
        $client = New-Object System.Net.Http.HttpClient($handler)
        $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSec)
        [void]$client.DefaultRequestHeaders.TryAddWithoutValidation(
            "Accept",
            "application/json"
        )
        if ($Method -ceq "Get") {
            $response = $client.GetAsync($Uri).GetAwaiter().GetResult()
        }
        elseif ($Method -ceq "Post") {
            $json = $Body | ConvertTo-Json -Compress
            $content = New-Object System.Net.Http.StringContent(
                $json,
                [Text.Encoding]::UTF8,
                "application/json"
            )
            $response = $client.PostAsync(
                $Uri,
                $content
            ).GetAwaiter().GetResult()
        }
        else {
            return $null
        }
        if (
            [int]$response.StatusCode -ge 300 -or
            [int]$response.StatusCode -lt 200
        ) {
            return $null
        }
        $responseBody = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $parsed = $responseBody | ConvertFrom-Json
        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Json = $parsed
        }
    }
    catch {
        return $null
    }
    finally {
        foreach ($disposable in @($response, $content, $client, $handler)) {
            if ($null -ne $disposable) {
                try {
                    $disposable.Dispose()
                }
                catch {
                    # Only the fixed request marker may cross this boundary.
                }
            }
        }
    }
}

function Open-RedactedEventStream {
    param([Parameter(Mandatory = $true)][Uri]$Uri)
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $handler.UseProxy = $false
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [System.Threading.Timeout]::InfiniteTimeSpan
    $request = New-Object System.Net.Http.HttpRequestMessage(
        [System.Net.Http.HttpMethod]::Get,
        $Uri
    )
    [void]$request.Headers.TryAddWithoutValidation("Accept", "text/event-stream")
    $cancellation = New-Object System.Threading.CancellationTokenSource
    $cancellation.CancelAfter([TimeSpan]::FromSeconds($TimeoutSec))
    try {
        $response = $client.SendAsync(
            $request,
            [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead,
            $cancellation.Token
        ).GetAwaiter().GetResult()
        if ([int]$response.StatusCode -ne 200) {
            throw "status"
        }
        $mediaType = [string]$response.Content.Headers.ContentType.MediaType
        if ($mediaType.ToLowerInvariant() -cne "text/event-stream") {
            throw "content_type"
        }
        $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $reader = New-Object System.IO.StreamReader(
            $stream,
            (New-Object System.Text.UTF8Encoding($false, $true)),
            $true
        )
        return [pscustomobject]@{
            Client = $client
            Handler = $handler
            Request = $request
            Response = $response
            Cancellation = $cancellation
            Reader = $reader
        }
    }
    catch {
        $cancellation.Dispose()
        $request.Dispose()
        $client.Dispose()
        $handler.Dispose()
        return $null
    }
}

function Close-EventStream {
    param([object]$Context)
    if ($null -eq $Context) {
        return
    }
    foreach ($name in @(
        "Reader", "Response", "Request", "Cancellation", "Client", "Handler"
    )) {
        try {
            $Context.$name.Dispose()
        }
        catch {
            # Disposal cannot change the public failure marker.
        }
    }
}

function Read-BoundedLine {
    param([System.IO.StreamReader]$Reader)
    $task = $Reader.ReadLineAsync()
    if (-not $task.Wait($TimeoutSec * 1000)) {
        throw "stream_timeout"
    }
    return $task.GetAwaiter().GetResult()
}

if ($StaticOnly -and $Live) {
    throw "HERMES_YUJIN_FAILURE_DRILL_GATE_FAILED:mode_ambiguous"
}
if (-not $StaticOnly -and -not $Live) {
    throw "HERMES_YUJIN_FAILURE_DRILL_GATE_FAILED:mode_required"
}

if ($StaticOnly) {
    if ($NpmExecutable -in @("npm", "npm.cmd")) {
        $resolvedNpmCommand = Get-Command `
            $NpmExecutable `
            -ErrorAction SilentlyContinue
        if ($null -ne $resolvedNpmCommand) {
            $NpmExecutable = $resolvedNpmCommand.Source
        }
    }
    $backendResult = Invoke-CapturedProcess `
        -FilePath $PythonExecutable `
        -Arguments (@("-m", "pytest", "-q") + $backendNodeIds) `
        -ProcessTimeoutSec $StaticTimeoutSec
    if ($backendResult.ExitCode -ne 0) {
        throw "HERMES_YUJIN_FAILURE_DRILL_FAILED:backend_regression"
    }
    $frontendResult = Invoke-CapturedProcess `
        -FilePath $NpmExecutable `
        -Arguments (
            @("--prefix", "apps/web", "test", "--", "--run") + $frontendFiles
        ) `
        -ProcessTimeoutSec $StaticTimeoutSec
    if ($frontendResult.ExitCode -ne 0) {
        throw "HERMES_YUJIN_FAILURE_DRILL_FAILED:frontend_regression"
    }
    Write-Output (
        "HERMES_YUJIN_FAILURE_DRILLS_STATIC_PASS " +
        "backend_nodes=7 frontend_files=2 docker_calls=0 " +
        "network_calls=0 provider_calls=0"
    )
    exit 0
}

# Stage 1 is a pure gate. Keep every process and network call below this block.
if (
    -not $ConfirmServiceStop -or
    -not $ConfirmConversationWrite -or
    -not $ConfirmDisposableProject
) {
    throw "HERMES_YUJIN_FAILURE_DRILL_GATE_FAILED:confirmation_required"
}
if (
    [string]::IsNullOrWhiteSpace($ProjectId) -or
    [string]::IsNullOrWhiteSpace($SessionId) -or
    $ExpectedSessionRevision -le 0
) {
    throw "HERMES_YUJIN_FAILURE_DRILL_GATE_FAILED:disposable_session_required"
}
$resolvedBaseUri = $null
if (-not [Uri]::TryCreate($BaseUri, [UriKind]::Absolute, [ref]$resolvedBaseUri)) {
    throw "HERMES_YUJIN_FAILURE_DRILL_GATE_FAILED:base_uri_invalid"
}
if (
    $resolvedBaseUri.Scheme -notin @("http", "https") -or
    $resolvedBaseUri.Host.ToLowerInvariant() -notin @(
        "127.0.0.1", "localhost", "::1", "[::1]"
    ) -or
    -not [string]::IsNullOrEmpty($resolvedBaseUri.UserInfo) -or
    $resolvedBaseUri.AbsolutePath -cne "/" -or
    -not [string]::IsNullOrEmpty($resolvedBaseUri.Query) -or
    -not [string]::IsNullOrEmpty($resolvedBaseUri.Fragment)
) {
    throw "HERMES_YUJIN_FAILURE_DRILL_GATE_FAILED:base_uri_not_exact_loopback"
}
$resolvedEnvFileInput = if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    Join-Path $repositoryRoot ".env.container"
}
else {
    $EnvFile
}
if (-not (Test-Path -LiteralPath $resolvedEnvFileInput -PathType Leaf)) {
    throw "HERMES_YUJIN_FAILURE_DRILL_GATE_FAILED:environment_required"
}
$resolvedEnvFile = (Resolve-Path -LiteralPath $resolvedEnvFileInput).Path
if (-not (Test-ApprovedEnvironmentFile -Path $resolvedEnvFile)) {
    throw "HERMES_YUJIN_FAILURE_DRILL_GATE_FAILED:environment_not_approved"
}
foreach ($requiredPath in @($restartScript, $smokeScript)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "HERMES_YUJIN_FAILURE_DRILL_GATE_FAILED:recovery_script_missing"
    }
}
try {
    Add-Type -AssemblyName System.Net.Http
}
catch {
    throw "HERMES_YUJIN_FAILURE_DRILL_GATE_FAILED:http_runtime_missing"
}

# Stage 2 performs only read-only Docker and API preflight checks.
$dockerReads = 1
$apiReads = 0
$beforeContainer = Get-ExactHealthyContainer
if ($null -eq $beforeContainer) {
    Throw-PreflightFailure -Marker "service_not_healthy"
}
$escapedProjectId = [Uri]::EscapeDataString($ProjectId)
$escapedSessionId = [Uri]::EscapeDataString($SessionId)
$sessionUri = [Uri]::new(
    $resolvedBaseUri,
    "/api/projects/$escapedProjectId/editing-sessions/$escapedSessionId"
)
$apiReads += 1
$sessionResult = Invoke-RedactedJsonRequest -Uri $sessionUri -Method Get
if ($null -eq $sessionResult -or $sessionResult.StatusCode -ne 200) {
    Throw-PreflightFailure -Marker "session_read"
}
$session = $sessionResult.Json
if (
    [string]$session.project_id -cne $ProjectId -or
    [string]$session.session_id -cne $SessionId -or
    [int]$session.session_revision -ne $ExpectedSessionRevision
) {
    Throw-PreflightFailure -Marker "session_mismatch"
}

$conversationPath = "/api/projects/$escapedProjectId/director/conversations"
$conversationUri = [Uri]::new($resolvedBaseUri, $conversationPath)
$conversationResult = Invoke-RedactedJsonRequest `
    -Uri $conversationUri `
    -Method Post `
    -Body @{ session_id = $SessionId }
if (
    $null -eq $conversationResult -or
    $conversationResult.StatusCode -ne 201 -or
    [string]::IsNullOrWhiteSpace(
        [string]$conversationResult.Json.conversation_id
    )
) {
    throw "HERMES_YUJIN_FAILURE_DRILL_FAILED:conversation_create"
}
$conversationId = [string]$conversationResult.Json.conversation_id
$escapedConversationId = [Uri]::EscapeDataString($conversationId)
$runUri = [Uri]::new(
    $resolvedBaseUri,
    "$conversationPath/$escapedConversationId/hermes-runs"
)
$runResult = Invoke-RedactedJsonRequest `
    -Uri $runUri `
    -Method Post `
    -Body @{
        session_id = $SessionId
        expected_session_revision = $ExpectedSessionRevision
        client_message_id = [guid]::NewGuid().ToString()
        text = "장애 복구 드릴을 위한 짧은 공개 응답을 주세요."
    }
if (
    $null -eq $runResult -or
    $runResult.StatusCode -ne 201 -or
    [string]::IsNullOrWhiteSpace([string]$runResult.Json.run_id)
) {
    throw "HERMES_YUJIN_FAILURE_DRILL_FAILED:run_create"
}
$runId = [string]$runResult.Json.run_id
$expectedEventsPath = (
    "$conversationPath/$escapedConversationId/hermes-runs/" +
    "$([Uri]::EscapeDataString($runId))/events"
)
if (
    [string]$runResult.Json.conversation_id -cne $conversationId -or
    [string]$runResult.Json.events_url -cne $expectedEventsPath
) {
    throw "HERMES_YUJIN_FAILURE_DRILL_FAILED:run_identity"
}

$eventContext = $null
$stopAttempted = $false
$drillFailureMarker = $null
$recoveryFailureMarker = $null
try {
    $eventContext = Open-RedactedEventStream -Uri (
        [Uri]::new($resolvedBaseUri, $expectedEventsPath)
    )
    if ($null -eq $eventContext) {
        throw "events_request"
    }
    $currentEvent = ""
    $currentData = ""
    $barrierSeen = $false
    $terminalSeen = $false
    $terminalStatus = ""
    while (-not $terminalSeen) {
        $line = Read-BoundedLine -Reader $eventContext.Reader
        if ($null -eq $line) {
            if (-not $barrierSeen) {
                throw "provider_active_barrier_missing"
            }
            throw "stream_ended_after_stop"
        }
        if ($line.StartsWith("event:")) {
            $currentEvent = $line.Substring(6).Trim()
            continue
        }
        if ($line.StartsWith("data:")) {
            $currentData = $line.Substring(5).Trim()
            continue
        }
        if (-not [string]::IsNullOrEmpty($line)) {
            continue
        }
        $eventType = $currentEvent
        $eventText = ""
        if (-not [string]::IsNullOrWhiteSpace($currentData)) {
            try {
                $eventPayload = $currentData | ConvertFrom-Json
                if (-not [string]::IsNullOrWhiteSpace(
                    [string]$eventPayload.event_type
                )) {
                    $eventType = [string]$eventPayload.event_type
                }
                $eventText = [string]$eventPayload.text
            }
            catch {
                throw "events_json"
            }
        }
        $currentEvent = ""
        $currentData = ""
        if (-not $barrierSeen) {
            if ($eventType -ceq "run_completed") {
                throw "fast_complete"
            }
            if (
                ($eventType -ceq "text_delta" -and
                    -not [string]::IsNullOrWhiteSpace($eventText)) -or
                $eventType -ceq "prompt_accepted_active"
            ) {
                $barrierSeen = $true
                $stopAttempted = $true
                $stopResult = Invoke-CapturedProcess `
                    -FilePath $DockerExecutable `
                    -Arguments (
                        New-ComposeArguments -Tail @(
                            "stop", $targetService
                        )
                    )
                if ($stopResult.ExitCode -ne 0) {
                    throw "service_stop"
                }
            }
            continue
        }
        if ($eventType -in @("blocked", "interrupted")) {
            $terminalStatus = $eventType
            $terminalSeen = $true
            continue
        }
        if ($eventType -ceq "run_completed") {
            throw "terminal_after_stop"
        }
    }
    Close-EventStream -Context $eventContext
    $eventContext = $null
    $eventContext = Open-RedactedEventStream -Uri (
        [Uri]::new($resolvedBaseUri, $expectedEventsPath)
    )
    if ($null -eq $eventContext) {
        throw "durable_replay"
    }
    $replayEvent = ""
    $replayData = ""
    $durableTerminalSeen = $false
    while (-not $durableTerminalSeen) {
        $line = Read-BoundedLine -Reader $eventContext.Reader
        if ($null -eq $line) {
            throw "durable_replay"
        }
        if ($line.StartsWith("event:")) {
            $replayEvent = $line.Substring(6).Trim()
            continue
        }
        if ($line.StartsWith("data:")) {
            $replayData = $line.Substring(5).Trim()
            continue
        }
        if (-not [string]::IsNullOrEmpty($line)) {
            continue
        }
        $replayType = $replayEvent
        if (-not [string]::IsNullOrWhiteSpace($replayData)) {
            try {
                $replayPayload = $replayData | ConvertFrom-Json
                if (-not [string]::IsNullOrWhiteSpace(
                    [string]$replayPayload.event_type
                )) {
                    $replayType = [string]$replayPayload.event_type
                }
            }
            catch {
                throw "durable_replay"
            }
        }
        $replayEvent = ""
        $replayData = ""
        if ($replayType -in @("blocked", "interrupted")) {
            $durableTerminalSeen = $true
            continue
        }
        if ($replayType -ceq "run_completed") {
            throw "durable_status"
        }
    }
    $manualUri = [Uri]::new(
        $resolvedBaseUri,
        "$conversationPath/$escapedConversationId/messages"
    )
    $manualResult = Invoke-RedactedJsonRequest `
        -Uri $manualUri `
        -Method Post `
        -Body @{
            session_id = $SessionId
            client_message_id = [guid]::NewGuid().ToString()
            text = "Hermes가 중단되었습니다. Director에서 수동으로 계속해 주세요."
        }
    if (
        $null -eq $manualResult -or
        $manualResult.StatusCode -ne 200
    ) {
        throw "manual_director"
    }
}
catch {
    $caughtMarker = [string]$_.Exception.Message
    if ($caughtMarker -in @(
        "fast_complete",
        "provider_active_barrier_missing"
    )) {
        $drillFailureMarker = "UNRUN:$caughtMarker"
    }
    elseif ($caughtMarker -in @(
        "events_request",
        "events_json",
        "stream_timeout",
        "stream_ended_after_stop",
        "durable_replay",
        "durable_status",
        "service_stop",
        "terminal_after_stop",
        "manual_director"
    )) {
        $drillFailureMarker = "FAILED:$caughtMarker"
    }
    else {
        $drillFailureMarker = "FAILED:unexpected"
    }
}
finally {
    Close-EventStream -Context $eventContext
    if ($stopAttempted) {
        $restartResult = Invoke-CapturedProcess `
            -FilePath $PowerShellExecutable `
            -Arguments @(
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", $restartScript,
                "-EnvFile", $resolvedEnvFile,
                "-DockerExecutable", $DockerExecutable,
                "-TimeoutSec", ([string]$TimeoutSec)
            )
        if ($restartResult.ExitCode -ne 0) {
            $recoveryFailureMarker = Resolve-RestartRecoveryMarker (
                $restartResult
            )
        }
        if ($null -eq $recoveryFailureMarker) {
            $afterContainer = Get-ExactHealthyContainer
            if ($null -eq $afterContainer) {
                $recoveryFailureMarker = "health_timeout"
            }
            elseif ($afterContainer.Id -cne $beforeContainer.Id) {
                $recoveryFailureMarker = "container_identity"
            }
        }
        if ($null -eq $recoveryFailureMarker) {
            $smokeResult = Invoke-CapturedProcess `
                -FilePath $PowerShellExecutable `
                -Arguments @(
                    "-NoProfile",
                    "-ExecutionPolicy", "Bypass",
                    "-File", $smokeScript,
                    "-Live",
                    "-BaseUri", $BaseUri,
                    "-ProjectId", $ProjectId,
                    "-SessionId", $SessionId,
                    "-ExpectedSessionRevision",
                    ([string]$ExpectedSessionRevision),
                    "-TimeoutSec", ([string]$TimeoutSec)
                )
            if ($smokeResult.ExitCode -ne 0) {
                $recoveryFailureMarker = "canary"
            }
        }
    }
}

if ($null -ne $recoveryFailureMarker) {
    throw (
        "HERMES_YUJIN_FAILURE_DRILL_RECOVERY_FATAL:" +
        $recoveryFailureMarker
    )
}
if ($null -ne $drillFailureMarker) {
    if ($drillFailureMarker.StartsWith("UNRUN:")) {
        throw (
            "HERMES_YUJIN_FAILURE_DRILL_UNRUN:" +
            $drillFailureMarker.Substring(6)
        )
    }
    throw (
        "HERMES_YUJIN_FAILURE_DRILL_FAILED:" +
        $drillFailureMarker.Substring(7)
    )
}

# A hard process termination cannot execute PowerShell finally; operators must
# run the exact restart script before any subsequent live drill.
Write-Output (
    "HERMES_YUJIN_FAILURE_DRILL_LIVE_PASS " +
    "simulation=stop_during_stream service=$targetService " +
    "terminal=$terminalStatus manual_director=true auto_apply_calls=0"
)
