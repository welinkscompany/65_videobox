"""마음에 든 영상의 '만드는 방식'을 다음 영상으로 옮긴다.

owner가 좋은 영상을 하나 만들면 그 구성(자막 모양, 화면 크기, 장면 호흡, 음악)을
저장해 두고 다음 영상에서 불러 쓴다. 자동 제작이 "어떻게 만들지"를 여기서 가져간다 —
규격 없이 자동화하면 매번 다른 물건이 나온다.

**템플릿은 내용을 나르지 않는다.** 장면·대본·촬영본은 그 영상의 것이다.
그것까지 옮기면 다음 영상이 지난 영상의 내용을 물려받는다.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class FormatTemplateError(ValueError):
    """포맷 템플릿을 만들거나 적용할 수 없을 때."""


def _segments(session: dict[str, Any]) -> list[dict[str, Any]]:
    raw = session.get("segments")
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _average_scene_sec(segments: list[dict[str, Any]]) -> float:
    lengths = []
    for segment in segments:
        start, end = segment.get("start_sec"), segment.get("end_sec")
        if isinstance(start, int | float) and isinstance(end, int | float) and end > start:
            lengths.append(float(end) - float(start))
    return round(sum(lengths) / len(lengths), 3) if lengths else 0.0


def _single_music_asset_id(segments: list[dict[str, Any]]) -> str | None:
    """구간마다 음악이 다르면 하나로 줄이지 않는다. 아무거나 고르면 거짓말이 된다."""
    chosen = {
        str(segment.get("music_asset_id")).strip()
        for segment in segments
        if str(segment.get("music_asset_id") or "").strip()
    }
    return chosen.pop() if len(chosen) == 1 else None


def format_template_from_session(*, name: str, session: dict[str, Any]) -> dict[str, Any]:
    """이 편집본이 '어떻게 보이는지'만 뽑아낸다."""
    label = (name or "").strip()
    if not label:
        raise FormatTemplateError("포맷 이름을 지어 주세요.")
    segments = _segments(session)
    output = session.get("output") if isinstance(session.get("output"), dict) else {}
    return {
        "name": label,
        "caption_style": deepcopy(session.get("caption_style") or {}),
        "width": output.get("width"),
        "height": output.get("height"),
        # 호흡은 참고값이다. 다음 영상의 장면을 이 길이로 강제하지 않는다 —
        # 내용이 다른데 길이를 맞추면 말이 잘린다.
        "average_scene_sec": _average_scene_sec(segments),
        "scene_count": len(segments),
        "music_asset_id": _single_music_asset_id(segments),
    }


def apply_format_template(
    *,
    session: dict[str, Any],
    template: dict[str, Any],
    keep_output_size: bool = False,
) -> dict[str, Any]:
    """포맷을 다른 편집본에 입힌다. 원본은 건드리지 않는다.

    `keep_output_size`는 가로 포맷을 세로 영상에 쓸 때를 위한 것이다. 그게 없으면
    세로 영상이 조용히 가로가 된다.
    """
    if not isinstance(template, dict) or not str(template.get("name") or "").strip():
        raise FormatTemplateError("쓸 수 있는 포맷이 아니에요.")
    # 되돌릴 수 있어야 한다. 원본을 그 자리에서 고치면 되돌릴 것이 없다.
    applied = deepcopy(session)
    applied["caption_style"] = deepcopy(template.get("caption_style") or {})
    if not keep_output_size:
        width, height = template.get("width"), template.get("height")
        if isinstance(width, int) and isinstance(height, int):
            applied["output"] = {"width": width, "height": height}
    return applied
