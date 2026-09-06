"""장면에 놓을 수 있는 자산을 모은다.

**두 곳에 박혀 있던 것을 한 곳으로 모았다**(2026-09-06). 파이프라인의 B-roll
추천과 부분 재생성이 각각 `list_assets(asset_type=BROLL_VIDEO)`를 부르고 있었고,
그래서 owner가 자료실에 넣은 사진 56장이 **어느 쪽에서도 후보가 되지 못했다**.
한쪽만 고치면 다른 쪽이 조용히 예전대로 돈다 -- 이 저장소가 반복해서 겪은 모양이라
자리를 하나로 둔다.

**사진도 장면이 될 수 있다.** 영상은 원본 길이만큼만 쓸 수 있지만 사진은 장면이
요구하는 만큼 늘릴 수 있다 -- 렌더러가 `-loop 1`로 그렇게 한다
(`ffmpeg_final_renderer._looks_like_image`).
"""

from __future__ import annotations

from typing import Any

from videobox_domain_models.assets import AssetType

#: AI가 만든 장면 그림은 **자산 둘**로 등록된다 -- 그림(`image`)과 그것을 움직여
#: 만든 클립(`broll_video`)이다(`scene_image_service`). 둘 다 후보에 넣으면 같은
#: 그림이 한 편집본에 두 번 뽑힐 수 있다. 움직이는 쪽이 이미 있으므로 그림은 뺀다.
_GENERATED_IMAGE_SOURCE = "generated_image"


def list_scene_candidate_assets(*, store: Any, project_id: str) -> list[dict[str, Any]]:
    """이 프로젝트에서 장면에 놓을 수 있는 자산 전부."""
    videos = list(store.list_assets(project_id=project_id, asset_type=AssetType.BROLL_VIDEO))
    photos = [
        asset for asset in store.list_assets(project_id=project_id, asset_type=AssetType.IMAGE)
        if str(asset.get("source_kind") or "") != _GENERATED_IMAGE_SOURCE
    ]
    return videos + photos


__all__ = ["list_scene_candidate_assets"]
