"""응답 모델 전체에서 "초과 필드를 조용히 버리는" 것이 몇 개나 남았는지 잰다.

2026-09-20에 `EditorCaptionResponse`가 `owning_segment_id`를 조용히 버려서
검토 화면이 실제로 뭘 받는지 아무도 몰랐던 실측 결함이 나왔다. 원인은
Pydantic의 기본 동작(`extra="ignore"`) -- 모델에 없는 키는 에러 없이 그냥
버려진다. `EditorMediaControlsResponse`/`EditorCaptionStyleResponse`처럼
이미 `extra="forbid"`로 잠근 모델은 내부 dict가 새 필드를 만들었는데 모델에
안 적으면 그 자리에서 검증 에러로 바로 터진다 -- 조용히 사라지지 않는다.

이 저장소엔 응답 모델이 100개 가깝다. 전부를 오늘 한 번에 `forbid`로
바꾸는 건 검증 안 된 위험이다(그중엔 정말로 초과 필드를 허용해야 하는
모델이 섞여 있을 수 있다). 그래서 이 시험은 **강제하지 않고 잰다** --
지금 잠그지 않은 모델 수를 기준선으로 박아 두고, 그 수가 **늘어나면**
막는다(ratchet). 새 응답 모델을 만들 때 `extra="forbid"`를 깜빡하면 여기서
걸린다. 기존 모델을 하나씩 잠그면 기준선을 그만큼 낮춰서 되돌아가지
못하게 한다.
"""

from __future__ import annotations

import inspect

from videobox_api import models


def _response_model_classes() -> list[type]:
    return [
        obj
        for obj in vars(models).values()
        if inspect.isclass(obj)
        and issubclass(obj, models.BaseModel)
        and obj.__module__ == models.__name__
        and obj.__name__.endswith("Response")
    ]


def _forbids_extra(model_class: type) -> bool:
    config = model_class.model_config
    extra = config.get("extra") if isinstance(config, dict) else None
    return extra == "forbid"


# 2026-09-20 실측: 이 숫자 위로 늘리지 않는다. 새 `*Response` 모델을 만들면
# 기본으로 `extra="forbid"`를 넣어라 -- 이 표는 "아직 못 잠근 것"의 기록이지
# "이래도 된다"는 허락이 아니다.
_BASELINE_UNLOCKED_COUNT = 97


def test_response_models_without_extra_forbid_do_not_grow() -> None:
    unlocked = sorted(
        model.__name__ for model in _response_model_classes() if not _forbids_extra(model)
    )

    assert len(unlocked) <= _BASELINE_UNLOCKED_COUNT, (
        f"'*Response' 모델 중 extra='forbid'가 없는 게 {len(unlocked)}개로 늘었습니다"
        f"(기준선 {_BASELINE_UNLOCKED_COUNT}개). 새 응답 모델엔"
        " model_config = ConfigDict(extra=\"forbid\")를 기본으로 넣으세요.\n"
        + "\n".join(unlocked)
    )


def test_the_editor_manifest_family_stays_locked() -> None:
    """2026-09-20에 실제로 사고가 난 자리 -- 여기가 다시 풀리면 바로 걸린다."""

    locked_names = {
        "EditorPlaybackManifestResponse",
        "EditorTrackResponse",
        "EditorClipResponse",
        "EditorCaptionResponse",
        "EditorGapSlotResponse",
        "EditorSourceStatusResponse",
        "EditorAuditionResponse",
        "EditorExactPreviewResponse",
        "EditorFpsResponse",
        "EditorOutputResponse",
        "EditorMediaControlsResponse",
        "EditorCaptionStyleResponse",
    }

    by_name = {model.__name__: model for model in _response_model_classes()}
    still_locked = {name for name in locked_names if _forbids_extra(by_name[name])}

    assert still_locked == locked_names
