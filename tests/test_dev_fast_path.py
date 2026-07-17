from __future__ import annotations

from pathlib import Path


def test_output_gating_fast_path_includes_segment_review_required_transition_regression() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev-fast-path.ps1"
    script_text = script_path.read_text(encoding="utf-8")

    assert (
        "approving_last_pending_recommendation_keeps_outputs_blocked_by_remaining_segment_review_required"
        in script_text
    )


def test_output_gating_fast_path_includes_missing_selected_asset_uri_tts_approval_regression() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev-fast-path.ps1"
    script_text = script_path.read_text(encoding="utf-8")

    assert "review_snapshot_api_rejects_tts_approval_without_selected_asset_uri" in script_text


def test_output_gating_fast_path_includes_missing_target_narration_clip_tts_approval_regression() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev-fast-path.ps1"
    script_text = script_path.read_text(encoding="utf-8")

    assert "review_snapshot_api_rejects_tts_approval_without_matching_target_narration_clip" in script_text


def test_output_gating_fast_path_includes_tts_approval_decision_state_read_path_regression() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev-fast-path.ps1"
    script_text = script_path.read_text(encoding="utf-8")

    assert "review_snapshot_api_approve_tts_replacement_surfaces_approved_decision_state_in_read_paths" in script_text


def test_output_gating_fast_path_includes_tts_approval_persisted_timeline_output_read_regression() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev-fast-path.ps1"
    script_text = script_path.read_text(encoding="utf-8")

    assert "review_approval_persists_tts_narration_asset_uri_before_preview_and_export_read_timeline" in script_text


def test_output_gating_fast_path_includes_duplicate_tts_output_consumer_regression() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev-fast-path.ps1"
    script_text = script_path.read_text(encoding="utf-8")

    assert "review_approval_duplicate_tts_narration_clips_flow_through_preview_and_export_outputs" in script_text


def test_fast_path_exposes_the_600_second_release_smoke_mode() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev-fast-path.ps1"
    script_text = script_path.read_text(encoding="utf-8")

    assert '"smoke"' in script_text
    assert "verify-production-readiness-smoke.py" in script_text


def test_fast_path_exposes_the_three_fixture_long_form_capcut_qa_mode() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev-fast-path.ps1"
    script_text = script_path.read_text(encoding="utf-8")

    assert '"long-form-capcut-qa"' in script_text
    assert "verify-long-form-capcut-draft-qa.py" in script_text


def test_fast_path_exposes_media_director_release_lanes_without_claiming_live_availability() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev-fast-path.ps1"
    script_text = script_path.read_text(encoding="utf-8")

    for mode in ('"media-director-focused"', '"media-director-live-smoke"', '"media-director-release"'):
        assert mode in script_text
    assert "test_real_local_media_director_e2e.py" in script_text
    assert "VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE" in script_text
    assert "skips when unavailable" in script_text
    assert "LM Studio unavailable => skipped, not live PASS" not in script_text
    assert "Deterministic local-runtime media E2E" in script_text
    for name in ("VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE", "VIDEOBOX_RUN_REAL_MEDIA_DIRECTOR_E2E", "VIDEOBOX_RUN_REAL_STARTER_PACK_E2E"):
        assert f"`$env:{name}='1'" in script_text
        assert f"Remove-Item Env:{name} -ErrorAction SilentlyContinue" in script_text


def test_fast_path_propagates_native_command_failures() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "dev-fast-path.ps1"
    script_text = script_path.read_text(encoding="utf-8")

    assert 'if ($LASTEXITCODE -ne 0) {' in script_text
    assert 'throw "Step failed: $Label (exit code $LASTEXITCODE)"' in script_text
