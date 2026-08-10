"""분석이 끝나려면 출력에 상한이 있어야 한다.

측정: 이 기기에서 13갈래 구조화 출력이 180~300초 걸리고 자주 300초도 넘긴다.
비전 타임아웃은 120초였으니 애초에 끝날 수 없었다. 영어 프롬프트가 더 빠를
거라 짐작했는데 재보니 **영어가 더 느렸다** -- 지시가 없으니 모델이 길게 쓴다.

목록 길이에 상한이 없어서 한 항목이 문장 두 개짜리로 나오기도 했다
("The images depict an outdoor or semi-outdoor seating area, likely part of...").
생성량이 곧 시간이다.
"""

from __future__ import annotations

from videobox_provider_interfaces.vision import FIXED_VISION_RESPONSE_SCHEMA


def test_every_layer_bounds_how_many_items_it_can_hold() -> None:
    layers = FIXED_VISION_RESPONSE_SCHEMA["properties"]["layers"]["properties"]
    assert layers, "갈래가 없다"
    for name, spec in layers.items():
        assert "maxItems" in spec, f"{name} 에 개수 상한이 없다"
        assert spec["maxItems"] <= 6, f"{name} 상한이 너무 크다"


def test_every_layer_bounds_how_long_one_item_can_be() -> None:
    # 한 항목이 문장이 되면 태그가 아니라 요약이다. 검색에도 화면에도 나쁘다.
    layers = FIXED_VISION_RESPONSE_SCHEMA["properties"]["layers"]["properties"]
    for name, spec in layers.items():
        item = spec["items"]
        assert "maxLength" in item, f"{name} 항목 길이에 상한이 없다"
        assert item["maxLength"] <= 40, f"{name} 항목이 문장만큼 길 수 있다"


def test_the_summary_is_bounded_too() -> None:
    summary = FIXED_VISION_RESPONSE_SCHEMA["properties"]["summary"]
    assert summary.get("maxLength", 10_000) <= 400


def test_the_vision_timeout_matches_what_the_call_actually_takes() -> None:
    """측정 없이 정한 120초로는 끝날 수 없었다. 이 기기에서 성공한 호출이
    180~300초였다. 분석은 배경에서 1분에 하나씩 도는 작업이라 기다리는 사람이
    없다 -- 넉넉히 주는 쪽의 대가가 작다."""
    from videobox_provider_interfaces.lm_studio import LMStudioVisionProvider

    import dataclasses

    field = {f.name: f for f in dataclasses.fields(LMStudioVisionProvider)}["timeout_seconds"]
    assert field.default >= 300


def test_the_schema_only_demands_what_the_search_sentence_uses() -> None:
    """갈래 수가 곧 시간이다. 재보니 3개 68초, 6개 132초, 9개 121초, 13개는
    200초에도 못 끝냈다. 검색 문장이 실제로 쓰는 것은 9갈래이고 나머지 넷은
    저장만 된다 -- 그것들을 필수로 두느라 분석이 통째로 실패했다.

    빼는 게 아니라 **필수에서 내리는 것**이다. 모델이 채우면 그대로 저장된다.
    """
    from videobox_core_engine.library_footage_indexer import _DESCRIBED_LAYERS

    schema = FIXED_VISION_RESPONSE_SCHEMA["properties"]["layers"]
    required = set(schema["required"])
    described = {layer for layer, _ in _DESCRIBED_LAYERS}

    assert required == described, "필수 갈래와 문장이 쓰는 갈래가 어긋난다"
    # 나머지도 받아들이기는 한다 -- 모델이 채우면 태그로 남는다.
    assert set(schema["properties"]) > required


def test_the_review_reasons_are_bounded_too() -> None:
    """마지막 구멍이었다. 갈래와 요약을 묶고도 360초에 실패했는데, 여기까지
    묶으니 252~280초로 통과했다. 실제 저장된 데이터에서도 이 자리에 긴 문장이
    네 개 들어 있었다."""
    reasons = FIXED_VISION_RESPONSE_SCHEMA["properties"]["review_reasons"]
    assert reasons.get("maxItems", 99) <= 3
    assert reasons["items"].get("maxLength", 9999) <= 100


def test_filling_an_optional_layer_is_not_treated_as_poor_quality() -> None:
    """필수를 9로 줄였는데 품질 판정은 `set(layers) != expected`로 **정확히
    일치**를 요구했다. 모델이 선택 갈래를 채우면 -- 스키마가 허용하는 일인데 --
    분석이 needs_review로 떨어진다.

    필수는 다 있어야 하고, 선택은 있어도 없어도 된다.
    """
    from videobox_core_engine.media_analysis import MediaAnalysisService
    from videobox_provider_interfaces.vision import REQUIRED_VISION_LAYERS

    class _Probe:
        duration_sec = 10.0
        scene_boundaries = (0.0, 10.0)

    def output(layers: dict[str, list[str]]) -> dict:
        return {"layers": layers, "summary": "요약", "confidence": 0.9, "review_reasons": ["이유"]}

    only_required = {layer: ["값"] for layer in REQUIRED_VISION_LAYERS}
    with_optional = {**only_required, "color_tone": ["파랑"], "camera": ["가까이"]}
    missing_required = {layer: ["값"] for layer in REQUIRED_VISION_LAYERS[:-1]}

    assert MediaAnalysisService._quality_ok(output(only_required), _Probe()) is True
    assert MediaAnalysisService._quality_ok(output(with_optional), _Probe()) is True
    assert MediaAnalysisService._quality_ok(output(missing_required), _Probe()) is False


def test_the_frame_count_matches_what_the_machine_can_finish() -> None:
    """재보니 이미지 한 장이 40~110초다. 여섯 장이면 이미지만으로 300초를 넘고,
    거기에 13갈래 출력이 얹히니 어떤 타임아웃으로도 끝나지 않았다.

    장면 경계는 ffmpeg가 따로 계산하므로 프레임을 줄여도 구간 추천은 그대로다.
    """
    from videobox_core_engine.media_probe import MAX_FRAMES

    assert MAX_FRAMES <= 3


def test_the_provider_accepts_a_response_that_omits_optional_layers() -> None:
    """품질 판정에서 고친 것과 같은 갭이 공급자 쪽에도 있었다. 응답 검사가
    13갈래 전부를 요구해서, 필수 9개만 채운 응답 -- 스키마가 정확히 그렇게
    하라고 시킨 응답 -- 을 "규격 위반"으로 버렸다. 실제로 그 오류를 봤다."""
    import json

    from videobox_provider_interfaces.lm_studio import LMStudioVisionProvider
    from videobox_provider_interfaces.vision import REQUIRED_VISION_LAYERS

    provider = LMStudioVisionProvider.__new__(LMStudioVisionProvider)
    payload = {"choices": [{"message": {"content": json.dumps({
        "layers": {layer: ["값"] for layer in REQUIRED_VISION_LAYERS},
        "summary": "요약", "confidence": 0.9, "review_reasons": ["이유"],
    })}}]}

    parsed = provider._parse_output(payload)

    assert set(parsed["layers"]) == set(REQUIRED_VISION_LAYERS)


def test_the_provider_still_rejects_a_layer_it_never_asked_for() -> None:
    import json

    import pytest

    from videobox_provider_interfaces.lm_studio import LMStudioProviderError, LMStudioVisionProvider
    from videobox_provider_interfaces.vision import REQUIRED_VISION_LAYERS

    provider = LMStudioVisionProvider.__new__(LMStudioVisionProvider)
    payload = {"choices": [{"message": {"content": json.dumps({
        "layers": {**{layer: ["값"] for layer in REQUIRED_VISION_LAYERS}, "made_up": ["x"]},
        "summary": "요약", "confidence": 0.9, "review_reasons": ["이유"],
    })}}]}

    with pytest.raises(LMStudioProviderError):
        provider._parse_output(payload)
