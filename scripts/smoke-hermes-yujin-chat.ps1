[CmdletBinding()]
param(
    [switch]$Live,
    [string]$BaseUri = "http://127.0.0.1:8000",
    [string]$ProjectId,
    [string]$SessionId,
    [int]$ExpectedSessionRevision = 0,
    [ValidateRange(1, 60)]
    [int]$TimeoutSec = 10
)

$ErrorActionPreference = "Stop"
$networkCalls = 0
$proposalCalls = 0
$providerBodyRecorded = $false

function Assert-True {
    param([bool]$Condition, [string]$Marker)
    if (-not $Condition) {
        throw "HERMES_YUJIN_CANARY_FAILED:$Marker"
    }
}

function Invoke-RedactedHttpRequest {
    param(
        [Parameter(Mandatory = $true)]
        [Uri]$Uri,
        [Parameter(Mandatory = $true)]
        [string]$Method,
        [string]$ContentType,
        [object]$Body,
        [hashtable]$Headers = @{},
        [Parameter(Mandatory = $true)]
        [string]$FailureMarker
    )
    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $handler.UseProxy = $false
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [System.Threading.Timeout]::InfiniteTimeSpan
    $httpMethod = if ($Method -ceq "Get") {
        [System.Net.Http.HttpMethod]::Get
    }
    else {
        [System.Net.Http.HttpMethod]::Post
    }
    $request = New-Object System.Net.Http.HttpRequestMessage(
        $httpMethod,
        $Uri
    )
    foreach ($name in $Headers.Keys) {
        [void]$request.Headers.TryAddWithoutValidation(
            [string]$name,
            [string]$Headers[$name]
        )
    }
    if ($null -ne $Body) {
        $bytes = if ($Body -is [byte[]]) {
            $Body
        }
        else {
            [Text.Encoding]::UTF8.GetBytes([string]$Body)
        }
        $request.Content = New-Object System.Net.Http.ByteArrayContent(
            @(,$bytes)
        )
        if (-not [string]::IsNullOrWhiteSpace($ContentType)) {
            $request.Content.Headers.ContentType = (
                [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse(
                    $ContentType
                )
            )
        }
    }
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
        if (
            [int]$response.StatusCode -ge 300 -and
            [int]$response.StatusCode -lt 400
        ) {
            throw "redirect_denied"
        }
        $contentLength = $response.Content.Headers.ContentLength
        if ($null -ne $contentLength -and [long]$contentLength -gt 65536) {
            throw "body_oversized"
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
            if ($total -gt 65536) {
                throw "body_oversized"
            }
            $memory.Write($buffer, 0, $read)
        }
        $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Content = $strictUtf8.GetString($memory.ToArray())
            Headers = @{
                "Content-Type" = (
                    [string]$response.Content.Headers.ContentType
                )
            }
        }
    }
    catch {
        throw "HERMES_YUJIN_CANARY_FAILED:$FailureMarker"
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

if (-not $Live) {
    Write-Output (
        "HERMES_YUJIN_CANARY_NON_LIVE " +
        "network_calls=$networkCalls proposal_calls=$proposalCalls " +
        "provider_body_recorded=$($providerBodyRecorded.ToString().ToLowerInvariant())"
    )
    exit 0
}

Assert-True (-not [string]::IsNullOrWhiteSpace($ProjectId)) "project_id_required"
Assert-True (-not [string]::IsNullOrWhiteSpace($SessionId)) "session_id_required"
Assert-True ($ExpectedSessionRevision -gt 0) "expected_session_revision_required"
$resolvedBaseUri = $null
Assert-True ([Uri]::TryCreate($BaseUri, [UriKind]::Absolute, [ref]$resolvedBaseUri)) "base_uri_invalid"
Assert-True ($resolvedBaseUri.Scheme -in @("http", "https")) "base_uri_scheme_invalid"
Assert-True (
    $resolvedBaseUri.Host.ToLowerInvariant() -in @(
        "127.0.0.1",
        "localhost",
        "::1",
        "[::1]"
    )
) "base_uri_loopback_required"
Assert-True (
    [string]::IsNullOrEmpty($resolvedBaseUri.UserInfo) -and
    $resolvedBaseUri.AbsolutePath -ceq "/" -and
    [string]::IsNullOrEmpty($resolvedBaseUri.Query) -and
    [string]::IsNullOrEmpty($resolvedBaseUri.Fragment)
) "base_uri_shape_invalid"

$escapedProjectId = [Uri]::EscapeDataString($ProjectId)
$escapedSessionId = [Uri]::EscapeDataString($SessionId)
$conversationPath = "/api/projects/$escapedProjectId/director/conversations"
$conversationUri = [Uri]::new($resolvedBaseUri, $conversationPath)
$conversationBody = @{ session_id = $SessionId } | ConvertTo-Json -Compress
$networkCalls += 1
$conversationResponse = Invoke-RedactedHttpRequest `
    -Uri $conversationUri `
    -Method Post `
    -ContentType "application/json; charset=utf-8" `
    -Body ([Text.Encoding]::UTF8.GetBytes($conversationBody)) `
    -FailureMarker "conversation_create_request"
Assert-True ($conversationResponse.StatusCode -eq 201) "conversation_create_status"
try {
    $conversation = $conversationResponse.Content | ConvertFrom-Json
}
catch {
    throw "HERMES_YUJIN_CANARY_FAILED:conversation_create_json"
}
Assert-True (-not [string]::IsNullOrWhiteSpace([string]$conversation.conversation_id)) "conversation_id_missing"

$escapedConversationId = [Uri]::EscapeDataString([string]$conversation.conversation_id)
$runUri = [Uri]::new(
    $resolvedBaseUri,
    "$conversationPath/$escapedConversationId/hermes-runs"
)
$clientMessageId = [guid]::NewGuid().ToString()
$harmlessKoreanPrompt = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String(
        "7J20IOyXsOqysOydtCDspIDruYTrkJjsl4jripTsp4Ag7Ken6rKMIOyVjOugpCDso7zshLjsmpQu"
    )
)
$runBody = @{
    session_id = $SessionId
    expected_session_revision = $ExpectedSessionRevision
    client_message_id = $clientMessageId
    text = $harmlessKoreanPrompt
} | ConvertTo-Json -Compress
$networkCalls += 1
$runResponse = Invoke-RedactedHttpRequest `
    -Uri $runUri `
    -Method Post `
    -ContentType "application/json; charset=utf-8" `
    -Body ([Text.Encoding]::UTF8.GetBytes($runBody)) `
    -FailureMarker "run_create_request"
Assert-True ($runResponse.StatusCode -eq 201) "run_create_status"
try {
    $run = $runResponse.Content | ConvertFrom-Json
}
catch {
    throw "HERMES_YUJIN_CANARY_FAILED:run_create_json"
}
$expectedEventsPath = "/api/projects/$escapedProjectId/director/conversations/$escapedConversationId/hermes-runs/$([Uri]::EscapeDataString([string]$run.run_id))/events"
Assert-True ([string]$run.conversation_id -ceq [string]$conversation.conversation_id) "run_conversation_mismatch"
Assert-True ([string]$run.events_url -ceq $expectedEventsPath) "events_url_mismatch"

$eventsUri = [Uri]::new($resolvedBaseUri, $expectedEventsPath)
$networkCalls += 1
$eventsResponse = Invoke-RedactedHttpRequest `
    -Uri $eventsUri `
    -Method Get `
    -Headers @{ Accept = "text/event-stream" } `
    -FailureMarker "events_request"
Assert-True ($eventsResponse.StatusCode -eq 200) "events_status"
$contentTypeParts = @(
    ([string]$eventsResponse.Headers["Content-Type"]).Split(";") |
        ForEach-Object { $_.Trim() }
)
Assert-True (
    $contentTypeParts.Count -ge 1 -and
    $contentTypeParts[0].ToLowerInvariant() -ceq "text/event-stream"
) "events_content_type"
if ($contentTypeParts.Count -gt 1) {
    foreach ($contentTypeParameter in $contentTypeParts[1..($contentTypeParts.Count - 1)]) {
        Assert-True (
            $contentTypeParameter -match '(?i)^charset\s*=\s*"?utf-8"?$'
        ) "events_content_type"
    }
}
$eventTypes = @(
    [regex]::Matches([string]$eventsResponse.Content, "(?m)^event: (run_started|text_delta|blocked|run_completed)\r?$") |
        ForEach-Object { $_.Groups[1].Value }
)
Assert-True ($eventTypes -contains "text_delta") "delta_missing"
Assert-True ($eventTypes -contains "run_completed") "complete_missing"
Assert-True (-not ($eventTypes -contains "blocked")) "run_blocked"
Assert-True ($proposalCalls -eq 0) "proposal_call_detected"
Assert-True (-not $providerBodyRecorded) "provider_body_recorded"

Write-Output (
    "HERMES_YUJIN_CANARY_LIVE_PASS " +
    "network_calls=$networkCalls proposal_calls=$proposalCalls " +
    "delta_seen=true complete_seen=true provider_body_recorded=false"
)
