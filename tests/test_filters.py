"""색감 필터 계약. 캡컷 필터 탭의 우리 쪽 대응물."""
from __future__ import annotations

import pytest

from videobox_core_engine.filters import (
    FILTER_CATALOG,
    FILTER_TYPES,
    filter_chain,
    normalize_filter,
)
from videobox_core_engine.media_controls import normalize_media_controls


def test_absent_filter_normalizes_to_nothing() -> None:
    # 껐다 켜는 길이 있어야 하고, 끌 때 보내는 값이 무엇이든 같은 뜻이어야 한다.
    assert normalize_filter(None) is None
    assert normalize_filter({"type": "none"}) is None
    assert normalize_filter({"type": ""}) is None


def test_keeps_the_chosen_look_and_who_chose_it() -> None:
    assert normalize_filter({"type": "mono"}) == {"type": "mono", "chosen_by": "owner"}
    assert normalize_filter({"type": "warm", "chosen_by": "yujin"}) == {"type": "warm", "chosen_by": "yujin"}


@pytest.mark.parametrize("value", [{"type": "sepia"}, {"type": "mono", "chosen_by": "someone"}, "mono", 3])
def test_rejects_what_it_cannot_draw_or_attribute(value: object) -> None:
    # 이 값은 필터 그래프 문자열에 그대로 들어간다 -- 모르는 값이 흘러가면 안 된다.
    with pytest.raises(ValueError):
        normalize_filter(value)


def test_every_catalog_entry_carries_a_label_and_a_drawable_chain() -> None:
    for key, entry in FILTER_CATALOG.items():
        assert entry["label"].strip(), key
        assert entry["family"].strip(), key
        assert entry["ffmpeg"].strip(), key
        assert filter_chain({"type": key}) == entry["ffmpeg"]


def test_no_chain_when_nothing_was_chosen() -> None:
    assert filter_chain(None) == ""
    assert filter_chain({"type": "none"}) == ""


def test_looks_do_not_secretly_repeat_each_other() -> None:
    # 갈래가 겹치면 고르는 사람에게 선택지가 느는 게 아니라 고민만 는다.
    chains = [entry["ffmpeg"] for entry in FILTER_CATALOG.values()]
    assert len(set(chains)) == len(chains)


def test_broll_controls_accept_and_keep_a_filter() -> None:
    # 색감은 클립에 붙는다 -- `media_controls`를 지나 렌더러까지 가야 한다.
    controls = normalize_media_controls({"fit": "crop", "filter": {"type": "vintage"}}, media_kind="broll", duration_sec=4.0)

    assert controls["filter"] == {"type": "vintage", "chosen_by": "owner"}


def test_broll_controls_without_a_filter_stay_exactly_as_before() -> None:
    # 안 고른 클립의 저장 모양이 바뀌면 옛 저장분과 어긋난다.
    controls = normalize_media_controls({"fit": "crop"}, media_kind="broll", duration_sec=4.0)

    assert "filter" not in controls


def test_broll_controls_reject_a_look_that_is_not_in_the_catalog() -> None:
    with pytest.raises(ValueError):
        normalize_media_controls({"fit": "crop", "filter": {"type": "nope"}}, media_kind="broll", duration_sec=4.0)


def test_catalog_keys_are_the_allowlist() -> None:
    assert FILTER_TYPES == frozenset(FILTER_CATALOG)


def test_the_look_reaches_the_picture_and_survives_a_transition() -> None:
    # 색감이 저장만 되고 그림에는 안 닿으면 "저장은 됐는데 결과는 그대로"다.
    # 전환 양쪽도 **같은 변형**을 써야 한다 -- 아니면 전환 1초 동안만 색이 튄다.
    from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer

    renderer = FfmpegFinalRenderer.__new__(FfmpegFinalRenderer)
    renderer.video_width, renderer.video_height = 1920, 1080

    plain = renderer._broll_fit_transform({"fit": "crop"})
    tinted = renderer._broll_fit_transform({"fit": "crop", "filter": {"type": "mono", "chosen_by": "owner"}})

    assert "hue=s=0" not in plain
    assert tinted.startswith(plain)
    assert tinted.endswith(",hue=s=0")
