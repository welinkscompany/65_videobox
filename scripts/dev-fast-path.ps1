param(
    [ValidateSet(
        "status",
        "review-action-backend",
        "review-action-frontend",
        "output-gating",
        "preflight-backend",
        "preflight-frontend",
        "current-focused",
        "current-focused-parallel",
        "broader",
        "all"
    )]
    [string]$Mode = "current-focused",
    [string]$BackendPattern = "",
    [string]$FrontendPattern = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot "apps\web"

$reviewActionBackendExpr = if ($BackendPattern -and $Mode -eq "review-action-backend") {
    $BackendPattern
}
else {
    'approve_pending_recommendation or approve_preserves_non_target_review_items_and_blocked_status or approve_tts_replacement_updates_target_narration_clip_and_keeps_other_blockers or approving_last_pending_recommendation_ignores_stale_non_dict_review_flags_before_output_approval or reject_pending_recommendation or timeline_local_when_another_timeline_mutates_shared_recommendation_state or rejecting_one_duplicate_pending_recommendation_keeps_shared_review_flag'
}

$outputGatingExpr = if ($BackendPattern -and $Mode -eq "output-gating") {
    $BackendPattern
}
else {
    'approved_review_state_still_blocks_outputs_when_timeline_has_residual_review_blockers or approved_review_state_still_blocks_outputs_when_only_review_flags_remain or approved_review_state_still_blocks_outputs_when_only_pending_recommendations_remain or approved_review_state_still_blocks_outputs_when_segment_review_required_remains_without_snapshot_blockers or output_blocker_synthesis_deduplicates_repeated_segment_review_required_entries or output_jobs_ignore_stale_truthy_blocker_shapes_on_approved_timeline or output_jobs_ignore_unknown_dict_shaped_review_flag_on_approved_timeline or output_jobs_ignore_stale_non_bool_segment_review_required_on_approved_timeline or reopening_approved_review_ignores_stale_truthy_blocker_shapes_and_returns_draft or timeline_and_review_snapshot_read_paths_normalize_stale_truthy_blocker_shapes_after_reopen or review_snapshot_ignores_persisted_approved_guidance_when_synthetic_segment_blocker_makes_status_blocked or preview_export_and_subtitles_require_explicit_approval_even_without_blockers or approving_last_pending_recommendation_ignores_stale_non_dict_review_flags_before_output_approval or approving_last_pending_recommendation_keeps_review_blocked_when_segment_review_required_remains or approving_last_pending_recommendation_keeps_outputs_blocked_by_remaining_segment_review_required or approving_one_of_multiple_pending_recommendations_keeps_output_blocked_by_remaining_detail or review_snapshot_api_rejects_tts_approval_without_selected_asset_uri or review_snapshot_api_rejects_tts_approval_without_matching_target_narration_clip or review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths or review_approval_persists_tts_narration_asset_uri_before_preview_and_export_read_timeline or review_approval_duplicate_tts_narration_clips_flow_through_preview_and_export_outputs or reopening_approved_review_reblocks_outputs_until_reapproved or reopening_approved_review_with_residual_blockers_returns_blocked_status or approved_timeline_can_generate_subtitles_preview_and_export'
}

$preflightBackendExpr = if ($BackendPattern -and $Mode -eq "preflight-backend") {
    $BackendPattern
}
else {
    'test_editing_session_api_marks_preflight_ or test_editing_session_api_normalizes_ or test_editing_session_api_filters_stale_non_dict_visual_overlay_entries_in_preflight_targeted_segments or test_editing_session_api_filters_empty_visual_overlay_dict_entries_in_preflight_targeted_segments or test_editing_session_api_filters_stale_minimal_dict_visual_overlay_entries_in_preflight_targeted_segments or test_editing_session_api_filters_overlay_type_only_visual_overlay_entries_in_preflight_targeted_segments or test_editing_session_api_filters_unknown_overlay_type_entries_in_preflight_targeted_segments or test_editing_session_api_preserves_legacy_hook_title_overlay_in_preflight_targeted_segments or test_editing_session_api_preserves_canonical_visual_overlay_in_preflight_targeted_segments or test_editing_session_api_preserves_canonical_image_overlay_in_preflight_targeted_segments or test_editing_session_api_preserves_canonical_table_overlay_in_preflight_targeted_segments or test_editing_session_api_filters_stale_non_dict_source_review_flag_entries_from_preflight_prediction or test_editing_session_api_filters_stale_minimal_dict_source_review_flag_entries_from_preflight_prediction or test_editing_session_api_filters_code_only_source_review_flag_entries_from_preflight_prediction or test_editing_session_api_filters_unknown_code_source_review_flag_entries_from_preflight_prediction or test_editing_session_api_filters_nested_segment_id_source_review_flag_entries_from_preflight_prediction or test_editing_session_api_filters_stale_non_dict_source_pending_recommendation_entries_from_preflight_prediction or test_editing_session_api_filters_stale_minimal_dict_source_pending_recommendation_entries_from_preflight_prediction or test_editing_session_api_filters_recommendation_id_only_source_pending_recommendation_entries_from_preflight_prediction or test_editing_session_api_filters_unknown_type_source_pending_recommendation_entries_from_preflight_prediction or test_editing_session_api_filters_nested_target_segment_id_source_pending_recommendation_from_preflight_prediction or test_editing_session_api_ignores_stale_minimal_dict_source_pending_recommendation_entries_when_running_partial_regeneration or test_editing_session_api_normalizes_string_false_review_required_when_running_partial_regeneration or test_editing_session_api_normalizes_invalid_cut_action_when_running_partial_regeneration or test_editing_session_api_normalizes_invalid_target_cut_action_when_running_partial_regeneration or test_editing_session_api_matches_trimmed_session_segment_ids_when_running_partial_regeneration or test_editing_session_api_filters_unknown_overlay_type_when_running_partial_regeneration or test_editing_session_api_preserves_canonical_table_overlay_when_running_partial_regeneration or test_editing_session_api_does_not_preserve_unknown_existing_overlay_type_on_targeted_overlay_rerun or test_editing_session_api_matches_trimmed_session_segment_ids_in_preflight_targeted_segments or test_editing_session_api_preserves_request_segment_order_in_preflight_targeted_segments or test_editing_session_api_deduplicates_repeated_segment_ids_in_preflight_scope or test_editing_session_api_deduplicates_repeated_fields_in_preflight_scope or test_editing_session_api_rejects_preflight_for_unsupported_field_scope_without_creating_jobs'
}

$reviewActionFrontendExpr = if ($FrontendPattern -and $Mode -eq "review-action-frontend") {
    $FrontendPattern
}
else {
    'approves a pending recommendation through the review action and refreshes the review snapshot|opens the actionable pending recommendation in the editing session when marked for manual edit'
}

$preflightFrontendExpr = if ($FrontendPattern -and $Mode -eq "preflight-frontend") {
    $FrontendPattern
}
else {
    'shows a blocked preflight warning before execution when the rerun preserves existing review blockers|shows a limited restore warning when resumed preflight interpretation cannot be restored|clears resumed candidate restore warnings when the operator changes the rerun target|clears resumed candidate restore warnings when the operator changes the rerun fields|clears resumed candidate restore warnings when the operator reopens review|clears resumed candidate restore warnings when the operator approves the active candidate timeline|clears resumed candidate restore warnings when the operator requests a fresh preflight|reuses blocked preflight interpretation on refresh-resume for the latest fresh candidate|aligns the selected rerun scope with the resumed candidate before reusing preflight interpretation|does not reuse resumed preflight interpretation when the restored preflight scope differs from the resumed candidate|does not reuse resumed preflight interpretation when the restored preflight session_id differs from the resumed candidate session|does not reuse resumed preflight interpretation when the restored preflight fields include duplicates|does not reuse resumed preflight interpretation when restored targeted segments differ from the resumed candidate scope|does not reuse resumed preflight interpretation when restored targeted segment review state differs from the editing session|does not reuse resumed preflight interpretation when restored targeted segment tts replacement differs from the editing session|does not reuse resumed preflight interpretation when restored targeted segment visual overlays differ from the editing session|does not reuse resumed preflight interpretation when restored targeted segment broll override differs from the editing session|does not reuse resumed preflight interpretation when restored targeted segment music override differs from the editing session|does not reuse preflight interpretation for a resumed multi-segment candidate that the current editor cannot represent|clears resumed multi-segment scope when the operator changes the rerun target|clears resumed multi-segment scope when the operator changes the rerun fields|maps a backend image_card overlay into the image overlay preflight field|maps a backend legacy image overlay into the image overlay preflight field|maps a backend hook_title overlay into the visual overlay preflight field|maps a backend canonical visual_overlay into the visual overlay preflight field'
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

function Invoke-ParallelSteps {
    param(
        [Parameter(Mandatory = $true)]
        [array]$Steps
    )

    $jobs = @()
    try {
        foreach ($step in $Steps) {
            $jobs += Start-Job -ScriptBlock {
                param($Label, $Command, $WorkingDirectory)
                Set-StrictMode -Version Latest
                $ErrorActionPreference = "Stop"
                Push-Location $WorkingDirectory
                try {
                    $output = Invoke-Expression $Command 2>&1 | Out-String
                    [pscustomobject]@{
                        Label = $Label
                        Output = $output.TrimEnd()
                        Failed = $false
                    }
                }
                catch {
                    [pscustomobject]@{
                        Label = $Label
                        Output = (($_ | Out-String).TrimEnd())
                        Failed = $true
                    }
                }
                finally {
                    Pop-Location
                }
            } -ArgumentList $step.Label, $step.Command, $step.WorkingDirectory
        }

        Wait-Job -Job $jobs | Out-Null
        $results = $jobs | Receive-Job
        foreach ($result in $results) {
            Write-Host ""
            Write-Host "==> $($result.Label)" -ForegroundColor Cyan
            if ($result.Output) {
                Write-Host $result.Output
            }
            if ($result.Failed) {
                throw "Parallel step failed: $($result.Label)"
            }
        }
    }
    finally {
        foreach ($job in $jobs) {
            Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        }
    }
}

switch ($Mode) {
    "review-action-backend" {
        Invoke-Step `
            -Label "Backend review-action maintenance slice" `
            -Command "pytest tests/test_api.py -q -k `"$reviewActionBackendExpr`"" `
            -WorkingDirectory $repoRoot
    }
    "review-action-frontend" {
        Invoke-Step `
            -Label "Frontend review-action maintenance slice" `
            -Command "npm test -- --run src/app.test.tsx -t `"$reviewActionFrontendExpr`"" `
            -WorkingDirectory $frontendRoot
    }
    "output-gating" {
        Invoke-Step `
            -Label "Backend output gating slice" `
            -Command "pytest tests/test_api.py -q -k `"$outputGatingExpr`"" `
            -WorkingDirectory $repoRoot
    }
    "preflight-backend" {
        Invoke-Step `
            -Label "Backend preflight slice" `
            -Command "pytest tests/test_api.py -q -k `"$preflightBackendExpr`"" `
            -WorkingDirectory $repoRoot
    }
    "preflight-frontend" {
        Invoke-Step `
            -Label "Frontend preflight slice" `
            -Command "npm test -- --run src/app.test.tsx -t `"$preflightFrontendExpr`"" `
            -WorkingDirectory $frontendRoot
    }
    "current-focused" {
        Invoke-Step `
            -Label "Backend output gating slice" `
            -Command "pytest tests/test_api.py -q -k `"$outputGatingExpr`"" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Backend preflight slice" `
            -Command "pytest tests/test_api.py -q -k `"$preflightBackendExpr`"" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Frontend preflight slice" `
            -Command "npm test -- --run src/app.test.tsx -t `"$preflightFrontendExpr`"" `
            -WorkingDirectory $frontendRoot
    }
    "current-focused-parallel" {
        Invoke-ParallelSteps -Steps @(
            @{
                Label = "Backend output gating slice"
                Command = "pytest tests/test_api.py -q -k `"$outputGatingExpr`""
                WorkingDirectory = $repoRoot
            },
            @{
                Label = "Backend preflight slice"
                Command = "pytest tests/test_api.py -q -k `"$preflightBackendExpr`""
                WorkingDirectory = $repoRoot
            },
            @{
                Label = "Frontend preflight slice"
                Command = "npm test -- --run src/app.test.tsx -t `"$preflightFrontendExpr`""
                WorkingDirectory = $frontendRoot
            }
        )
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
            -Label "Backend output gating slice" `
            -Command "pytest tests/test_api.py -q -k `"$outputGatingExpr`"" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Backend preflight slice" `
            -Command "pytest tests/test_api.py -q -k `"$preflightBackendExpr`"" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Frontend preflight slice" `
            -Command "npm test -- --run src/app.test.tsx -t `"$preflightFrontendExpr`"" `
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
        Write-Host "VideoBox current fast path status" -ForegroundColor Cyan
        Write-Host "Repo root: $repoRoot"
        Write-Host "Frontend root: $frontendRoot"
        Write-Host ""
        Write-Host "Current-priority loop:" -ForegroundColor Yellow
        Write-Host "  1. Add one failing test"
        Write-Host "  2. Run one exact test first with pytest -k / npm test -t"
        Write-Host "  3. Apply minimal GREEN"
        Write-Host "  4. ./scripts/dev-fast-path.ps1 -Mode output-gating   or preflight-backend / preflight-frontend"
        Write-Host "  5. ./scripts/dev-fast-path.ps1 -Mode current-focused-parallel"
        Write-Host "  6. ./scripts/dev-fast-path.ps1 -Mode broader"
        Write-Host ""
        Write-Host "Compatibility loop (sequential):" -ForegroundColor Yellow
        Write-Host "  1. Add one failing test"
        Write-Host "  2. ./scripts/dev-fast-path.ps1 -Mode output-gating   or preflight-backend / preflight-frontend"
        Write-Host "  3. Apply minimal GREEN"
        Write-Host "  4. ./scripts/dev-fast-path.ps1 -Mode current-focused"
        Write-Host "  5. ./scripts/dev-fast-path.ps1 -Mode broader"
        Write-Host ""
        Write-Host "Current backend output-gating pattern:"
        Write-Host "  $outputGatingExpr"
        Write-Host ""
        Write-Host "Current backend preflight pattern:"
        Write-Host "  $preflightBackendExpr"
        Write-Host ""
        Write-Host "Current frontend preflight pattern:"
        Write-Host "  $preflightFrontendExpr"
        Write-Host ""
        Write-Host "Review-action maintenance helper remains available:"
        Write-Host "  ./scripts/review-action-fast-path.ps1 -Mode status"
    }
}
