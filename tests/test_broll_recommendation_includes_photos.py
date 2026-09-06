"""사진이 장면 후보에 아예 안 들어갔다 — owner 요청 2026-09-06.

> "사진을 넣는것도 우리 자산으로 만들어서 영상으로 천천히 슬로우 모션같은
> 효과로 만들어도 되는거지? 그럼 사진 자산도 만들어야겠네"

owner가 사진 56장을 자료실에 넣었고, 렌더러는 사진을 장면으로 읽을 수 있게
됐다(`_looks_like_image`). 그런데 **그 사진이 장면에 배정되는 길이 없었다** --
추천기에게 자산을 건네는 두 자리가 `AssetType.BROLL_VIDEO`만 조회한다.

추천기 자체(`KeywordBrollRecommender`)는 종류를 안 본다. 막힌 곳은 호출부다.

**사진은 길이가 없다.** 영상은 원본 길이만큼만 쓸 수 있지만 사진은 장면이
요구하는 만큼 늘릴 수 있다 -- 렌더러가 `-loop 1`로 그렇게 한다.
"""

from __future__ import annotations

from pathlib import Path

from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore


def _project_with(store: LocalProjectStore, tmp_path: Path) -> str:
    project = store.bootstrap_project("사진 후보")
    video = tmp_path / "clip.mp4"
    video.write_bytes(bytes(64))
    photo = tmp_path / "shot.jpg"
    photo.write_bytes(bytes(64))
    store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)
    store.register_asset(project_id=project.project_id, asset_type=AssetType.IMAGE, source_path=photo)
    return project.project_id


def test_the_pipeline_offers_photos_as_scene_candidates(tmp_path: Path) -> None:
    """추천기에게 건네는 자산 목록에 사진이 들어간다."""
    from videobox_core_engine.broll_scene_candidates import list_scene_candidate_assets

    store = LocalProjectStore(tmp_path / "projects")
    project_id = _project_with(store, tmp_path)

    assets = list_scene_candidate_assets(store=store, project_id=project_id)

    kinds = {str(item.get("asset_type")) for item in assets}
    assert AssetType.BROLL_VIDEO.value in kinds
    assert AssetType.IMAGE.value in kinds, f"사진이 후보에 없다: {kinds}"


def test_a_project_without_photos_is_unchanged(tmp_path: Path) -> None:
    """사진이 없으면 예전과 똑같다 -- 영상만 후보로 간다."""
    from videobox_core_engine.broll_scene_candidates import list_scene_candidate_assets

    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("영상만")
    video = tmp_path / "only.mp4"
    video.write_bytes(bytes(64))
    store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=video)

    assets = list_scene_candidate_assets(store=store, project_id=project.project_id)

    assert [str(item.get("asset_type")) for item in assets] == [AssetType.BROLL_VIDEO.value]


def test_generated_scene_clips_are_not_offered_twice(tmp_path: Path) -> None:
    """AI가 만든 장면 그림은 **사진과 영상 두 벌**로 등록된다
    (`scene_image_service`: 그림 하나가 자산 둘이 된다). 둘 다 후보에 넣으면
    같은 그림이 두 번 뽑힐 수 있다 -- 영상 쪽만 남긴다.
    """
    from videobox_core_engine.broll_scene_candidates import list_scene_candidate_assets

    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("AI 그림")
    still = tmp_path / "gen.png"
    still.write_bytes(bytes(64))
    clip = tmp_path / "gen.mp4"
    clip.write_bytes(bytes(64))
    store.register_asset(
        project_id=project.project_id, asset_type=AssetType.IMAGE,
        source_path=still, source_kind="generated_image",
    )
    store.register_asset(
        project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO,
        source_path=clip, source_kind="generated_image",
    )

    assets = list_scene_candidate_assets(store=store, project_id=project.project_id)

    assert [str(item.get("asset_type")) for item in assets] == [AssetType.BROLL_VIDEO.value]
