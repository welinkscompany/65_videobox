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

import logging
from typing import Any

from videobox_domain_models.assets import AssetType

#: AI가 만든 장면 그림은 **자산 둘**로 등록된다 -- 그림(`image`)과 그것을 움직여
#: 만든 클립(`broll_video`)이다(`scene_image_service`). 둘 다 후보에 넣으면 같은
#: 그림이 한 편집본에 두 번 뽑힐 수 있다. 움직이는 쪽이 이미 있으므로 그림은 뺀다.
_GENERATED_IMAGE_SOURCE = "generated_image"

_LOGGER = logging.getLogger(__name__)


def list_scene_candidate_assets(
    *, store: Any, project_id: str, library_store: Any | None = None
) -> list[dict[str, Any]]:
    """이 프로젝트에서 장면에 놓을 수 있는 자산 전부.

    `library_store`를 주면 자료실 색인이 적어 둔 설명을 후보에 실어 준다.
    추천기는 자산의 `title`·`tags`와 대본 낱말이 겹치는지만 보는데, owner 사진
    이름(`20241208_121938.jpg`)에는 뜻이 없어 **늘 겹침 0**이었다 -- 뜻과 상관없이
    돌려쓰기 차례로만 뽑혔다는 뜻이다. 색인은 그 사진을 이미 한국어로 설명해 두었다.

    자료실을 못 읽어도 후보는 그대로 나온다. 설명이 없을 뿐이다.
    """
    videos = list(store.list_assets(project_id=project_id, asset_type=AssetType.BROLL_VIDEO))
    photos = [
        asset for asset in store.list_assets(project_id=project_id, asset_type=AssetType.IMAGE)
        if str(asset.get("source_kind") or "") != _GENERATED_IMAGE_SOURCE
    ]
    return _with_library_descriptions(videos + photos, library_store=library_store)


def _library_asset_id(asset: dict[str, Any]) -> str:
    metadata = asset.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("source_library_asset_id") or "")


def _with_library_descriptions(
    assets: list[dict[str, Any]], *, library_store: Any | None
) -> list[dict[str, Any]]:
    if library_store is None:
        return assets
    wanted = [asset_id for asset_id in (_library_asset_id(item) for item in assets) if asset_id]
    if not wanted:
        return assets
    try:
        descriptions = library_store.describe_assets(library_asset_ids=wanted)
    except Exception:  # pragma: no cover - 설명은 거들 뿐, 없다고 편집을 멈추지 않는다
        _LOGGER.warning("자료실 설명을 못 읽었다 -- 이름만으로 고른다", exc_info=True)
        return assets

    enriched: list[dict[str, Any]] = []
    for asset in assets:
        description = descriptions.get(_library_asset_id(asset), "")
        if not description:
            enriched.append(asset)
            continue
        item = dict(asset)
        metadata = dict(item.get("metadata") or {})
        tags = [str(tag) for tag in (metadata.get("tags") or [])]
        # 설명 문장을 그대로 태그 한 칸에 넣는다. 추천기가 낱말 단위로 쪼개
        # 대본과 견주므로 미리 쪼갤 필요가 없다.
        metadata["tags"] = [*tags, description]
        item["metadata"] = metadata
        enriched.append(item)
    return enriched


__all__ = ["list_scene_candidate_assets"]
