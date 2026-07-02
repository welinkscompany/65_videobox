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
