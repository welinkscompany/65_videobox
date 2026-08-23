"""우리 색감을 캡컷 쪽 이름표로 옮긴다.

**같은 그림이 나오지 않는다.** 우리 렌더러는 ffmpeg 필터로 직접 그리고
(`videobox_core_engine/filters.py`), 캡컷은 자기 서버에서 받아 두는 자원을
이름으로 가리킨다. 두 그림이 일치할 방법이 없다.

그래도 옮기는 이유는, 안 옮기면 **아예 사라지기 때문**이다. 대표가 흑백을
걸어 두고 캡컷을 열었는데 원래 색이 그대로 나오는 것보다, 캡컷의 흑백이
나오는 쪽이 덜 틀린다. 대신 내보내기 안내문에 "비슷한 것으로 옮겼다"고
적어 둔다 -- 조용히 다른 그림을 주지 않는다.

**표를 늘리면 여기도 늘려야 한다.** `test_capcut_export_looks.py`가 두 표를
맞대어 보므로, 색감을 새로 만들고 이 자리를 빠뜨리면 시험이 붉어진다.
"""
from __future__ import annotations


# 우리 색감 -> 캡컷 `FilterType` 이름. 454개 중에서 뜻이 가장 가까운 것을
# 2026-08-23에 골랐다.
CAPCUT_FILTER_BY_LOOK: dict[str, str] = {
    "mono": "BW_2",            # 깔끔한 흑백
    "vintage": "复古2",         # 옛날 필름
    "warm": "暖黄",             # 따뜻한 노랑
    "cool": "冷调",             # 차가운 톤
    "vivid": "鲜艳_I",          # 선명하게
    "faded": "淡彩",            # 옅은 색
    "bright": "磨砂肌",          # 뽀샤시 -- 피부를 부드럽게 눕히는 그 필터다
    "sepia": "深褐",            # 짙은 갈색
    "cinematic": "橙蓝",         # 주황-파랑, 영화에서 흔한 그 나뉨
}


def capcut_filter_name(controls: dict[str, object] | None) -> str | None:
    """정규화된 media_controls에서 캡컷 필터 이름을 꺼낸다. 없으면 ``None``."""
    if not controls:
        return None
    chosen = controls.get("filter")
    if not isinstance(chosen, dict):
        return None
    look = str(chosen.get("type") or "").strip()
    return CAPCUT_FILTER_BY_LOOK.get(look)
