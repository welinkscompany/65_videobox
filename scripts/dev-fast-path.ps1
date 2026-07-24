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
        "media-director-focused",
        "media-director-live-smoke",
        "media-director-release",
        "broader",
        "all",
        "smoke",
        "long-form-capcut-qa"
    )]
    [string]$Mode = "current-focused",
    [string]$BackendPattern = "",
    [string]$FrontendPattern = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot "apps\web"
$backendPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $backendPython)) {
    throw "VideoBox backend venv Python not found: $backendPython"
}
$pytestCommand = "& `"$backendPython`" -m pytest"

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
    'loads read-only current review data and links an exact segment to the pinned editor|keeps an already approved review read-only and calls no mutation endpoint'
}

$preflightFrontendExpr = if ($FrontendPattern -and $Mode -eq "preflight-frontend") {
    $FrontendPattern
}
else {
    'requires impact preflight before one explicit partial run, then resumes only from an explicit result read|recovers the latest succeeded same-session result after a fresh route mount|fails closed when a preflight response does not match the prepared segment|invalidates an unresolved A partial preflight after route navigation to B|ignores an old A partial run completion after route navigation to B'
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
        if ($LASTEXITCODE -ne 0) {
            throw "Step failed: $Label (exit code $LASTEXITCODE)"
        }
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
            -Command "$pytestCommand tests/test_api.py -q -k `"$reviewActionBackendExpr`"" `
            -WorkingDirectory $repoRoot
    }
    "review-action-frontend" {
        Invoke-Step `
            -Label "Frontend review-action maintenance slice" `
            -Command "npm test -- --run src/features/review/TimelineReviewPage.test.tsx -t `"$reviewActionFrontendExpr`"" `
            -WorkingDirectory $frontendRoot
    }
    "output-gating" {
        Invoke-Step `
            -Label "Backend output gating slice" `
            -Command "$pytestCommand tests/test_api.py -q -k `"$outputGatingExpr`"" `
            -WorkingDirectory $repoRoot
    }
    "preflight-backend" {
        Invoke-Step `
            -Label "Backend preflight slice" `
            -Command "$pytestCommand tests/test_api.py -q -k `"$preflightBackendExpr`"" `
            -WorkingDirectory $repoRoot
    }
    "preflight-frontend" {
        Invoke-Step `
            -Label "Frontend preflight slice" `
            -Command "npm test -- --run src/features/editor/workbench/editor-workbench-route.test.tsx -t `"$preflightFrontendExpr`"" `
            -WorkingDirectory $frontendRoot
    }
    "current-focused" {
        Invoke-Step `
            -Label "Backend output gating slice" `
            -Command "$pytestCommand tests/test_api.py -q -k `"$outputGatingExpr`"" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Backend preflight slice" `
            -Command "$pytestCommand tests/test_api.py -q -k `"$preflightBackendExpr`"" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Frontend preflight slice" `
            -Command "npm test -- --run src/features/editor/workbench/editor-workbench-route.test.tsx -t `"$preflightFrontendExpr`"" `
            -WorkingDirectory $frontendRoot
    }
    "current-focused-parallel" {
        Invoke-ParallelSteps -Steps @(
            @{
                Label = "Backend output gating slice"
                Command = "$pytestCommand tests/test_api.py -q -k `"$outputGatingExpr`""
                WorkingDirectory = $repoRoot
            },
            @{
                Label = "Backend preflight slice"
                Command = "$pytestCommand tests/test_api.py -q -k `"$preflightBackendExpr`""
                WorkingDirectory = $repoRoot
            },
            @{
                Label = "Frontend preflight slice"
                Command = "npm test -- --run src/features/editor/workbench/editor-workbench-route.test.tsx -t `"$preflightFrontendExpr`""
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
            -Command "$pytestCommand -q" `
            -WorkingDirectory $repoRoot
    }
    "all" {
        Invoke-Step `
            -Label "Backend output gating slice" `
            -Command "$pytestCommand tests/test_api.py -q -k `"$outputGatingExpr`"" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Backend preflight slice" `
            -Command "$pytestCommand tests/test_api.py -q -k `"$preflightBackendExpr`"" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Frontend preflight slice" `
            -Command "npm test -- --run src/features/editor/workbench/editor-workbench-route.test.tsx -t `"$preflightFrontendExpr`"" `
            -WorkingDirectory $frontendRoot
        Invoke-Step `
            -Label "Frontend production build" `
            -Command "npm run build" `
            -WorkingDirectory $frontendRoot
        Invoke-Step `
            -Label "Full backend regression" `
            -Command "$pytestCommand -q" `
            -WorkingDirectory $repoRoot
    }
    "media-director-focused" {
        Invoke-Step `
            -Label "Media Director backend contracts" `
            -Command "$pytestCommand tests/test_api_media_director.py tests/test_director_conversation.py tests/test_director_commands.py -q" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Media Director frontend features" `
            -Command "npm test -- --run src/features/editor/workbench/editor-workbench-route.test.tsx src/features/director src/features/media" `
            -WorkingDirectory $frontendRoot
    }
    "media-director-live-smoke" {
        # This is deliberately opt-in.  pytest reports SKIPPED when no local
        # LM Studio is available; the mode never treats that as live evidence.
        Invoke-Step `
            -Label "LM Studio media capability smoke (skips when unavailable)" `
            -Command "try { `$env:VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE='1'; $pytestCommand tests/test_lm_studio_media_smoke.py tests/test_lm_studio_smoke_evidence.py -q } finally { Remove-Item Env:VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE -ErrorAction SilentlyContinue }" `
            -WorkingDirectory $repoRoot
    }
    "media-director-release" {
        Invoke-Step `
            -Label "Media Director focused gate" `
            -Command "& `"$PSCommandPath`" -Mode media-director-focused" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Full backend regression" `
            -Command "$pytestCommand -q" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Full frontend regression" `
            -Command "npm test -- --run" `
            -WorkingDirectory $frontendRoot
        Invoke-Step `
            -Label "Frontend production build" `
            -Command "npm run build" `
            -WorkingDirectory $frontendRoot
        Invoke-Step `
            -Label "Deterministic local-runtime media E2E" `
            -Command "try { `$env:VIDEOBOX_RUN_REAL_MEDIA_DIRECTOR_E2E='1'; $pytestCommand tests/test_real_local_media_director_e2e.py -q } finally { Remove-Item Env:VIDEOBOX_RUN_REAL_MEDIA_DIRECTOR_E2E -ErrorAction SilentlyContinue }" `
            -WorkingDirectory $repoRoot
        Invoke-Step `
            -Label "Real Starter Media Pack E2E" `
            -Command "try { `$env:VIDEOBOX_RUN_REAL_STARTER_PACK_E2E='1'; $pytestCommand tests/test_real_starter_media_pack_e2e.py -q } finally { Remove-Item Env:VIDEOBOX_RUN_REAL_STARTER_PACK_E2E -ErrorAction SilentlyContinue }" `
            -WorkingDirectory $repoRoot
        Invoke-Step -Label "600-second Korean production readiness smoke" -Command "& `"$backendPython`" scripts/verify-production-readiness-smoke.py --narration artifacts/task5-korean-600.wav --work-root artifacts/task5-smoke" -WorkingDirectory $repoRoot
        Invoke-Step -Label "Three-fixture long-form CapCut draft QA" -Command "& `"$backendPython`" scripts/verify-long-form-capcut-draft-qa.py --narration artifacts/task5-korean-600.wav --work-root artifacts/long-form-capcut-qa" -WorkingDirectory $repoRoot
    }
    "smoke" {
        $artifactRoot = Join-Path $repoRoot "artifacts"
        $samplePath = Join-Path $artifactRoot "task5-korean-600.wav"
        if (-not (Test-Path -LiteralPath $samplePath)) {
            New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
            & (Join-Path $PSScriptRoot "New-ProductionReadinessKoreanSample.ps1") -OutputPath $samplePath
            if ($LASTEXITCODE -ne 0) {
                throw "Could not generate the required 600-second Korean smoke narration."
            }
        }
        Invoke-Step `
            -Label "600-second Korean production readiness smoke" `
            -Command "& `"$backendPython`" scripts/verify-production-readiness-smoke.py --narration `"$samplePath`" --work-root artifacts/task5-smoke" `
            -WorkingDirectory $repoRoot
    }
    "long-form-capcut-qa" {
        $artifactRoot = Join-Path $repoRoot "artifacts"
        $samplePath = Join-Path $artifactRoot "task5-korean-600.wav"
        if (-not (Test-Path -LiteralPath $samplePath)) {
            New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
            & (Join-Path $PSScriptRoot "New-ProductionReadinessKoreanSample.ps1") -OutputPath $samplePath
            if ($LASTEXITCODE -ne 0) {
                throw "Could not generate the required 600-second Korean long-form QA narration."
            }
        }
        Invoke-Step `
            -Label "Three-fixture long-form CapCut draft QA" `
            -Command "& `"$backendPython`" scripts/verify-long-form-capcut-draft-qa.py --narration `"$samplePath`" --work-root artifacts/long-form-capcut-qa" `
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
