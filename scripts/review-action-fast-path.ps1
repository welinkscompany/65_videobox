param(
    [ValidateSet("backend-red", "backend-focused", "frontend-focused", "broader", "all", "status")]
    [string]$Mode = "backend-focused",
    [string]$BackendPattern = "",
    [string]$FrontendPattern = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot "apps\web"

$backendFocusedExpr = if ($BackendPattern) {
    $BackendPattern
}
else {
    'approve_pending_recommendation or approve_preserves_non_target_review_items_and_blocked_status or reject_pending_recommendation or timeline_local_when_another_timeline_mutates_shared_recommendation_state or rejecting_one_duplicate_pending_recommendation_keeps_shared_review_flag'
}
$frontendFocusedName = 'src/app.test.tsx'
$frontendFocusedExpr = if ($FrontendPattern) {
    $FrontendPattern
}
else {
    'approves a pending recommendation through the review action and refreshes the review snapshot|opens the actionable pending recommendation in the editing session when marked for manual edit'
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory
    )

    Write-Host ""
    Write-Host "==> $Label" -ForegroundColor Cyan
    Push-Location $WorkingDirectory
    try {
        Invoke-Expression $Command
    }
    finally {
        Pop-Location
    }
}

switch ($Mode) {
    "backend-red" {
        Invoke-Step `
            -Label "Backend review-action red/focused slice" `
            -Command "pytest tests/test_api.py -k `"$backendFocusedExpr`" -q" `
            -WorkingDirectory $repoRoot
    }
    "backend-focused" {
        Invoke-Step `
            -Label "Backend review-action focused slice" `
            -Command "pytest tests/test_api.py -k `"$backendFocusedExpr`" -q" `
            -WorkingDirectory $repoRoot
    }
    "frontend-focused" {
        Invoke-Step `
            -Label "Frontend focused review shell tests" `
            -Command "npm test -- --run $frontendFocusedName -t `"$frontendFocusedExpr`"" `
            -WorkingDirectory $frontendRoot
    }
    "broader" {
        Invoke-Step `
            -Label "Frontend production build" `
            -Command "npm run build" `
            -WorkingDirectory $frontendRoot
        Invoke-Step `
            -Label "Full backend regression" `
            -Command "pytest -q" `
            -WorkingDirectory $repoRoot
    }
    "all" {
        Invoke-Step `
            -Label "Backend review-action focused slice" `
            -Command "pytest tests/test_api.py -k `"$backendFocusedExpr`" -q" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Frontend focused review shell tests" `
            -Command "npm test -- --run $frontendFocusedName -t `"$frontendFocusedExpr`"" `
            -WorkingDirectory $frontendRoot
        Invoke-Step `
            -Label "Frontend production build" `
            -Command "npm run build" `
            -WorkingDirectory $frontendRoot
        Invoke-Step `
            -Label "Full backend regression" `
            -Command "pytest -q" `
            -WorkingDirectory $repoRoot
    }
    "status" {
        Write-Host ""
        Write-Host "Review action fast path status" -ForegroundColor Cyan
        Write-Host "Repo root: $repoRoot"
        Write-Host "Frontend root: $frontendRoot"
        Write-Host ""
        Write-Host "Backend focused pattern:"
        Write-Host "  $backendFocusedExpr"
        Write-Host ""
        Write-Host "Frontend focused pattern:"
        Write-Host "  $frontendFocusedExpr"
        Write-Host ""
        Write-Host "Recommended loop:"
        Write-Host "  1. Add one failing test"
        Write-Host "  2. ./scripts/review-action-fast-path.ps1 -Mode backend-focused"
        Write-Host "  3. Apply minimal GREEN"
        Write-Host "  4. ./scripts/review-action-fast-path.ps1 -Mode frontend-focused"
        Write-Host "  5. ./scripts/review-action-fast-path.ps1 -Mode broader"
        Write-Host ""
        Write-Host "Use overrides when the next slice needs a narrower test target:"
        Write-Host "  ./scripts/review-action-fast-path.ps1 -Mode backend-focused -BackendPattern 'reject_pending_recommendation'"
        Write-Host "  ./scripts/review-action-fast-path.ps1 -Mode frontend-focused -FrontendPattern 'marked for manual edit'"
    }
}
