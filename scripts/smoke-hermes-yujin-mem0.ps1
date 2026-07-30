[CmdletBinding()]
param(
    [switch]$Live,
    [switch]$ApproveDisposableAdd,
    [string]$BaseUri = "http://127.0.0.1:8000",
    [string]$AgentGatewayUri = "http://127.0.0.1:8081",
    [string]$ProjectId,
    [string]$ConversationId,
    [string]$SourceMessageId,
    [ValidateRange(1, 30)]
    [int]$TimeoutSec = 10
)

$ErrorActionPreference = "Stop"
$networkCalls = 0
$candidateId = $null
$stored = $false
$deleted = $false

function Assert-Canary {
    param([bool]$Condition, [string]$Marker)
    if (-not $Condition) {
        throw "HERMES_YUJIN_MEM0_CANARY_FAILED:$Marker"
    }
}

function Resolve-LoopbackBaseUri {
    param([string]$Value, [string]$Marker)
    $parsed = $null
    Assert-Canary (
        [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$parsed)
    ) $Marker
    Assert-Canary ($parsed.Scheme -in @("http", "https")) $Marker
    Assert-Canary (
        $parsed.Host.ToLowerInvariant() -in @(
            "127.0.0.1", "localhost", "::1", "[::1]"
        )
    ) $Marker
    Assert-Canary (
        [string]::IsNullOrEmpty($parsed.UserInfo) -and
        [string]::IsNullOrEmpty($parsed.Query) -and
        [string]::IsNullOrEmpty($parsed.Fragment)
    ) $Marker
    return $parsed
}

function Invoke-CanaryJson {
    param(
        [Uri]$Uri,
        [ValidateSet("GET", "POST", "DELETE")]
        [string]$Method,
        [object]$Body,
        [hashtable]$Headers = @{},
        [int[]]$ExpectedStatus,
        [string]$Marker
    )
    $script:networkCalls += 1
    try {
        $parameters = @{
            Uri = $Uri
            Method = $Method
            Headers = $Headers
            TimeoutSec = $TimeoutSec
            MaximumRedirection = 0
            ErrorAction = "Stop"
        }
        if ($null -ne $Body) {
            $parameters.ContentType = "application/json; charset=utf-8"
            $parameters.Body = $Body | ConvertTo-Json -Compress -Depth 5
        }
        $response = Invoke-WebRequest @parameters
        Assert-Canary (
            [int]$response.StatusCode -in $ExpectedStatus
        ) $Marker
        Assert-Canary (
            [Text.Encoding]::UTF8.GetByteCount([string]$response.Content) -le
            65536
        ) $Marker
        return ([string]$response.Content | ConvertFrom-Json)
    }
    catch {
        throw "HERMES_YUJIN_MEM0_CANARY_FAILED:$Marker"
    }
}

if (-not $Live) {
    Write-Output (
        "HERMES_YUJIN_MEM0_NON_LIVE " +
        "network_calls=0 provider_calls=0 credentials_printed=false"
    )
    exit 0
}

Assert-Canary $ApproveDisposableAdd.IsPresent "explicit_add_approval_required"
Assert-Canary (
    $env:VIDEOBOX_HERMES_YUJIN_MEM0_LIVE_SMOKE -ceq "1"
) "live_environment_gate_required"
Assert-Canary (
    -not [string]::IsNullOrWhiteSpace(
        $env:VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN
    )
) "gateway_token_required"
Assert-Canary (-not [string]::IsNullOrWhiteSpace($ProjectId)) "project_required"
Assert-Canary (
    -not [string]::IsNullOrWhiteSpace($ConversationId)
) "conversation_required"
Assert-Canary (
    -not [string]::IsNullOrWhiteSpace($SourceMessageId)
) "source_message_required"

$apiBase = Resolve-LoopbackBaseUri $BaseUri "api_base_invalid"
$gatewayBase = Resolve-LoopbackBaseUri (
    $AgentGatewayUri
) "gateway_base_invalid"
$escapedProject = [Uri]::EscapeDataString($ProjectId)
$candidateBase = [Uri]::new(
    $apiBase,
    "/api/projects/$escapedProject/director/memory-candidates"
)
$tag = [guid]::NewGuid().ToString("N")
$candidateText = "일회용 D4 검증 $tag 작업 흐름을 선호합니다."
$gatewayHeaders = @{
    Authorization = (
        "Bearer " + $env:VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN
    )
}

try {
    $created = Invoke-CanaryJson `
        -Uri $candidateBase `
        -Method POST `
        -Body @{
            conversation_id = $ConversationId
            client_request_id = "mem0-canary-create-$tag"
            source_message_ids = @($SourceMessageId)
            memory_scope = "creator"
            category = "workflow"
            proposed_text = $candidateText
        } `
        -ExpectedStatus @(201) `
        -Marker "candidate_create"
    $candidateId = [string]$created.candidate_id
    Assert-Canary (-not [string]::IsNullOrWhiteSpace($candidateId)) (
        "candidate_id_missing"
    )
    $escapedCandidate = [Uri]::EscapeDataString($candidateId)

    $approved = Invoke-CanaryJson `
        -Uri ([Uri]::new(
            $candidateBase,
            "$($candidateBase.AbsolutePath)/$escapedCandidate/approve"
        )) `
        -Method POST `
        -Body $null `
        -ExpectedStatus @(200) `
        -Marker "candidate_approve"
    Assert-Canary ([string]$approved.status -ceq "approved") (
        "candidate_not_approved"
    )

    $saved = Invoke-CanaryJson `
        -Uri ([Uri]::new(
            $candidateBase,
            "$($candidateBase.AbsolutePath)/$escapedCandidate/store"
        )) `
        -Method POST `
        -Body @{ client_request_id = "mem0-canary-store-$tag" } `
        -ExpectedStatus @(200) `
        -Marker "candidate_store"
    Assert-Canary ([string]$saved.storage_status -ceq "stored") (
        "candidate_not_stored"
    )
    $stored = $true

    $searchUri = [Uri]::new(
        $gatewayBase,
        "/internal/hermes/memory/search"
    )
    $retrieved = Invoke-CanaryJson `
        -Uri $searchUri `
        -Method POST `
        -Headers $gatewayHeaders `
        -Body @{ query = $candidateText; limit = 5 } `
        -ExpectedStatus @(200) `
        -Marker "memory_retrieve"
    $matches = @($retrieved.memories | Where-Object {
        [string]$_.text -ceq $candidateText
    })
    Assert-Canary ($matches.Count -eq 1) "memory_retrieve_match"

    $removed = Invoke-CanaryJson `
        -Uri ([Uri]::new(
            $candidateBase,
            "$($candidateBase.AbsolutePath)/$escapedCandidate/stored-memory"
        )) `
        -Method DELETE `
        -Body $null `
        -ExpectedStatus @(200) `
        -Marker "memory_delete"
    Assert-Canary ([string]$removed.storage_status -ceq "deleted") (
        "memory_not_deleted"
    )
    $deleted = $true

    $afterDelete = Invoke-CanaryJson `
        -Uri $searchUri `
        -Method POST `
        -Headers $gatewayHeaders `
        -Body @{ query = $candidateText; limit = 5 } `
        -ExpectedStatus @(200) `
        -Marker "memory_confirm_absent"
    Assert-Canary (
        @($afterDelete.memories | Where-Object {
            [string]$_.text -ceq $candidateText
        }).Count -eq 0
    ) "memory_still_present"

    Write-Output (
        "HERMES_YUJIN_MEM0_LIVE_PASS " +
        "candidate_id=$candidateId approved=true stored=true " +
        "retrieved=true deleted=true absent=true " +
        "network_calls=$networkCalls credentials_printed=false"
    )
}
finally {
    if ($stored -and -not $deleted -and $null -ne $candidateId) {
        try {
            $escapedCandidate = [Uri]::EscapeDataString($candidateId)
            [void](Invoke-CanaryJson `
                -Uri ([Uri]::new(
                    $candidateBase,
                    "$($candidateBase.AbsolutePath)/$escapedCandidate/stored-memory"
                )) `
                -Method DELETE `
                -Body $null `
                -ExpectedStatus @(200) `
                -Marker "cleanup_delete")
        }
        catch {
            [Console]::Error.WriteLine(
                "HERMES_YUJIN_MEM0_CANARY_FAILED:cleanup_delete"
            )
        }
    }
}
