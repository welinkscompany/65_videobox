from __future__ import annotations

from videobox_domain_models.assets import AssetRecord, AssetType
from videobox_domain_models.projects import ProjectRecord, ProjectStatus
from videobox_domain_models.recommendations import (
    RecommendationRecord,
    RecommendationType,
)


def test_project_record_uses_local_first_defaults() -> None:
    project = ProjectRecord.create(name="Demo Project")

    assert project.status is ProjectStatus.DRAFT
    # 식별자 뒤에는 짧은 무작위가 항상 붙는다. 이름만으로 만들면 이름이 다른
    # 프로젝트끼리 겹쳐 조용히 섞였다 (`tests/test_project_id_never_collides.py`).
    assert project.project_id.startswith("demo-project-")
    assert project.root_storage_uri == f"local://projects/{project.project_id}"


def test_asset_record_supports_voice_sample_audio() -> None:
    asset = AssetRecord.create(
        project_id="proj_001",
        asset_type=AssetType.VOICE_SAMPLE_AUDIO,
        storage_uri="local://projects/proj_001/inputs/voice_samples/voice_001.wav",
    )

    assert asset.asset_type is AssetType.VOICE_SAMPLE_AUDIO


def test_recommendation_record_disables_auto_apply_for_tts() -> None:
    recommendation = RecommendationRecord.create(
        project_id="proj_001",
        target_segment_id="seg_001",
        recommendation_type=RecommendationType.TTS_REPLACEMENT,
        reason="Pronunciation cleanup candidate",
        score=0.82,
    )

    assert recommendation.auto_apply_allowed is False
    assert recommendation.review_required is True
