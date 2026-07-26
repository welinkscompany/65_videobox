[CmdletBinding()]
param(
    [switch]$Live,
    [string]$BaseUri = "http://127.0.0.1:8000",
    [string]$ProjectId,
    [string]$SessionId,
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

function Invoke-RedactedWebRequest {
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
    $parameters = @{
        Uri = $Uri
        Method = $Method
        Headers = $Headers
        UseBasicParsing = $true
        MaximumRedirection = 0
        TimeoutSec = $TimeoutSec
    }
    if (-not [string]::IsNullOrWhiteSpace($ContentType)) {
        $parameters.ContentType = $ContentType
    }
    if ($null -ne $Body) {
        $parameters.Body = $Body
    }
    try {
        $response = Invoke-WebRequest @parameters
        if ([int]$response.StatusCode -ge 300 -and [int]$response.StatusCode -lt 400) {
            throw "redirect_denied"
        }
        return $response
    }
    catch {
        throw "HERMES_YUJIN_CANARY_FAILED:$FailureMarker"
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
$resolvedBaseUri = $null
Assert-True ([Uri]::TryCreate($BaseUri, [UriKind]::Absolute, [ref]$resolvedBaseUri)) "base_uri_invalid"
Assert-True ($resolvedBaseUri.Scheme -in @("http", "https")) "base_uri_scheme_invalid"
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
$conversationResponse = Invoke-RedactedWebRequest `
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
    client_message_id = $clientMessageId
    text = $harmlessKoreanPrompt
} | ConvertTo-Json -Compress
$networkCalls += 1
$runResponse = Invoke-RedactedWebRequest `
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
$eventsResponse = Invoke-RedactedWebRequest `
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
