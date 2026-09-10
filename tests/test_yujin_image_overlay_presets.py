"""유진이 사진 오버레이의 자리·크기·움직임을 걸 수 있다 — 2026-09-06.

프리셋 넷(`vertical`, `horizontal`, `size`, `motion`)이 백엔드와 렌더러까지
닿았지만(a52b47cc2) **유진 경로는 통째로 비어 있었다.** 세어 보니 유진이 아는
편집 명령 열셋 중 오버레이를 다루는 것은 하나도 없다 -- 사진을 장면에 *깔* 수는
있어도(`apply_media`) 영상 *위에 얹을* 말이 없었다.

빠져 있던 층은 셋이다.

1. 명령 자체(`yujin_editing_proposals.py`의 union)
2. 안내문(`yujin_editing_proposal_service.py`) -- 고를 수 있는 값 목록
3. 검증·전달(`yujin_editing_proposal_adapter.py`, `_apply_yujin_editing_operations`)

**목록과 지금 걸린 값은 한 쌍이다.** 고를 수 있는 것만 알려 주면 "사진 좀 위로
올려줘"·"사진 빼줘"에 유진이 "얹은 사진이 없습니다"라고 답한다 -- 전환과 색감이
정확히 그렇게 틀렸다(2026-09-06 실측). 그래서 둘 다 프롬프트에 싣는다.

승인 범위는 도형·사진 오버레이와 같다(2026-08-20 승인 5항): 이름 붙은 프리셋만.
좌표(px/%)·초 단위·드래그·키프레임은 밖이다.
"""

from __future__ import annotations

from videobox_core_engine.editing_session import (
    _apply_yujin_editing_operations,
    build_editing_session,
    update_segment_image_overlay,
)
from videobox_core_engine.overlay_shapes import (
    SHAPE_OVERLAY_HORIZONTALS,
    SHAPE_OVERLAY_MOTIONS,
    SHAPE_OVERLAY_SIZES,
    SHAPE_OVERLAY_VERTICALS,
)
from videobox_core_engine.yujin_editing_proposal_service import (
    YujinEditingContext,
    _editing_prompt,
    interpret_yujin_editing_request,
)


def _context(**overrides: object) -> YujinEditingContext:
    defaults: dict[str, object] = {
        "session_id": "session-1",
        "session_revision": 3,
        "segment_ids": ("seg-1", "seg-2"),
        "segment_ids_with_broll": ("seg-1",),
        "approved_asset_ids": ("asset-photo", "asset-music"),
        "approved_asset_types": (("asset-photo", "image"), ("asset-music", "bgm")),
        "approved_asset_labels": (("asset-photo", "바다 사진"),),
    }
    return YujinEditingContext(**{**defaults, **overrides})  # type: ignore[arg-type]


def _response(**operation: object) -> dict[str, object]:
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "사진을 얹는 편집안을 만들었어요.",
        "proposal": {
            "proposal_id": "candidate",
            "base_session_revision": 3,
            "operations": [{"intent": "set_image_overlay", "segment_id": "seg-1", **operation}],
        },
    }


def _session() -> dict:
    return build_editing_session(
        project_id="project-1",
        timeline={"timeline_id": "timeline-1", "tracks": []},
        segments=[{"segment_id": "seg-1", "start_sec": 0.0, "end_sec": 5.0, "text": "첫 장면"}],
    )


def test_yujin_can_place_a_photo_over_the_video_with_all_four_presets() -> None:
    accepted = interpret_yujin_editing_request(
        _response(
            asset_id="asset-photo",
            vertical="bottom",
            horizontal="right",
            size="small",
            motion="fade_in",
        ),
        _context(),
    )

    assert accepted.status == "candidate_only"
    assert accepted.proposal is not None
    operation = accepted.proposal.operations[0]
    assert (operation.vertical, operation.horizontal, operation.size, operation.motion) == (
        "bottom",
        "right",
        "small",
        "fade_in",
    )


def test_presets_are_optional_so_a_plain_photo_still_goes_on() -> None:
    """넷 다 안 실어도 된다 -- 화면의 `ImageOverlayRequest`와 같은 규칙이다.

    빈칸을 기본값으로 채우면 프리셋 없이 얹어 둔 옛 오버레이와 자국이 달라진다.
    """
    accepted = interpret_yujin_editing_request(_response(asset_id="asset-photo"), _context())

    assert accepted.status == "candidate_only"
    assert accepted.proposal is not None
    operation = accepted.proposal.operations[0]
    assert (operation.vertical, operation.horizontal, operation.size, operation.motion) == (None,) * 4


def test_a_preset_nobody_defined_is_refused_before_it_reaches_the_render() -> None:
    """지어낸 이름은 여기서 막는다 -- 전환·색감과 같은 자리다.

    조용히 기본값으로 좁히면 창작자는 고른 것이 왜 안 되는지 알 수 없다.
    """
    refused = interpret_yujin_editing_request(
        _response(asset_id="asset-photo", motion="spin_around"), _context()
    )

    assert refused.reason == "image_overlay_preset_not_available"


def test_a_video_can_be_laid_over_the_scene_too() -> None:
    """**영상 위에 영상**(2026-09-10). 여태 이 자리는 사진만 받았다.

    막아 둔 근거는 "영상을 실으면 렌더러가 한 장짜리 그림으로 읽는다"였는데
    **사실이 아니다.** 렌더러는 `_looks_like_image`로 갈라서 사진에만
    `-loop 1`을 붙이고(`ffmpeg_final_renderer.py:1692`) 영상은 구간 전체를
    흘린다(`:1206-1233`). 처음부터 영상을 받을 수 있었다.
    """
    accepted = interpret_yujin_editing_request(
        _response(asset_id="asset-clip", size="small", vertical="top", horizontal="right"),
        _context(
            approved_asset_ids=("asset-photo", "asset-music", "asset-clip"),
            approved_asset_types=(
                ("asset-photo", "image"), ("asset-music", "bgm"), ("asset-clip", "broll_video"),
            ),
        ),
    )

    assert accepted.status == "candidate_only", accepted.reason
    assert accepted.proposal is not None
    assert accepted.proposal.operations[0].asset_id == "asset-clip"


def test_the_asset_list_tells_yujin_which_ones_can_be_laid_over() -> None:
    """목록과 안내문은 한 쌍이다. 영상을 받게 해 놓고 안내문이 "`·사진`이
    붙은 것만"이라고 말하면 유진은 영상을 안 고른다 -- 이 저장소가 자산
    목록 때문에 이미 두 번 겪은 모양이다."""
    from videobox_core_engine.yujin_editing_proposal_service import _approved_asset_catalogue

    catalogue = _approved_asset_catalogue(
        _context(
            approved_asset_ids=("asset_photo", "asset_clip", "asset_music"),
            approved_asset_types=(
                ("asset_photo", "image"), ("asset_clip", "broll_video"), ("asset_music", "bgm"),
            ),
            approved_asset_labels=(),
        )
    )

    assert "`·사진`이 붙은 것만" not in catalogue, catalogue
    assert "소리" in catalogue, "소리만 있는 자산은 못 얹는다는 것을 말해야 한다"


def test_music_cannot_be_pasted_on_the_screen_as_a_photo() -> None:
    refused = interpret_yujin_editing_request(
        _response(asset_id="asset-music", vertical="top"), _context()
    )

    assert refused.reason == "media_asset_type_mismatch"


def test_a_photo_nobody_approved_is_refused() -> None:
    refused = interpret_yujin_editing_request(_response(asset_id="asset-nowhere"), _context())

    assert refused.reason == "media_asset_not_approved"


def test_applying_the_proposal_actually_puts_the_presets_on_the_segment() -> None:
    proposal = interpret_yujin_editing_request(
        _response(
            asset_id="asset-photo",
            vertical="top",
            horizontal="left",
            size="large",
            motion="slide_in_left",
        ),
        _context(),
    ).proposal
    assert proposal is not None

    applied = _apply_yujin_editing_operations(session=_session(), operations=tuple(proposal.operations))

    overlay = next(
        item
        for item in applied["segments"][0]["visual_overlays"]
        if item.get("overlay_type") == "image_overlay"
    )
    assert overlay["asset_id"] == "asset-photo"
    assert (overlay["vertical"], overlay["horizontal"], overlay["size"], overlay["motion"]) == (
        "top",
        "left",
        "large",
        "slide_in_left",
    )


def test_yujin_can_take_the_photo_back_off() -> None:
    """"사진 빼줘"가 통해야 되돌릴 수 있다. 거는 말만 만들면 외길이 된다."""
    session = update_segment_image_overlay(
        session=_session(), segment_id="seg-1", asset_id="asset-photo", text="", vertical="top",
    )
    removal = {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "얹은 사진을 뺐어요.",
        "proposal": {
            "proposal_id": "candidate",
            "base_session_revision": 3,
            "operations": [{"intent": "remove_image_overlay", "segment_id": "seg-1"}],
        },
    }
    proposal = interpret_yujin_editing_request(removal, _context()).proposal
    assert proposal is not None

    applied = _apply_yujin_editing_operations(session=session, operations=tuple(proposal.operations))

    assert not [
        item
        for item in applied["segments"][0]["visual_overlays"]
        if item.get("overlay_type") == "image_overlay"
    ]


def test_the_prompt_tells_yujin_which_preset_values_exist() -> None:
    """목록을 안 주면 유진은 지어내고, 지어낸 값은 항상 거절된다.

    자산·색감·전환·글꼴에서 이미 네 번 치른 값이다.
    """
    prompt = _editing_prompt(instruction="사진 좀 오른쪽 아래에 작게 얹어줘", context=_context())

    assert "set_image_overlay" in prompt
    assert "remove_image_overlay" in prompt
    for value in (
        *sorted(SHAPE_OVERLAY_VERTICALS),
        *sorted(SHAPE_OVERLAY_HORIZONTALS),
        *sorted(SHAPE_OVERLAY_SIZES),
        *SHAPE_OVERLAY_MOTIONS,
    ):
        assert value in prompt, f"고를 수 있는 값 {value!r}이 안내문에 없다"


def test_the_prompt_also_tells_yujin_what_is_on_the_screen_right_now() -> None:
    """목록과 **지금 걸린 값**은 한 쌍이다.

    지금 걸린 것을 안 주면 "사진 좀 위로 올려줘"에 유진이 "얹은 사진이 없다"고
    답한다 -- 전환·색감이 똑같이 틀렸다.
    """
    prompt = _editing_prompt(
        instruction="사진 좀 위로 올려줘",
        context=_context(
            image_overlays_by_segment=(("seg-1", "asset-photo(bottom/right/small/fade_in)"),),
        ),
    )

    assert "asset-photo(bottom/right/small/fade_in)" in prompt


def test_the_api_actually_reads_what_is_on_the_screen_into_that_field() -> None:
    """윗 시험은 **값을 손으로 넣어** 확인한 것이라, 실제로 읽어 오는지는 못 잰다.

    이 저장소가 반복해서 겪은 함정이다: 부품은 있는데 부르는 자리가 없다.
    """
    from videobox_api.routers.director_proposals import _image_overlays_by_segment

    session = update_segment_image_overlay(
        session=_session(),
        segment_id="seg-1",
        asset_id="asset-photo",
        text="",
        vertical="bottom",
        horizontal="right",
        size="small",
        motion="fade_in",
    )

    assert _image_overlays_by_segment(session) == (
        ("seg-1", "asset-photo(bottom/right/small/fade_in)"),
    )


def test_a_photo_placed_without_presets_shows_up_as_blanks_not_as_defaults() -> None:
    """프리셋 없이 얹은 사진을 '가운데·안 움직임'으로 적으면, 유진은 창작자가
    고른 적 없는 자리를 고른 것으로 읽는다."""
    from videobox_api.routers.director_proposals import _image_overlays_by_segment

    session = update_segment_image_overlay(
        session=_session(), segment_id="seg-1", asset_id="asset-photo", text="",
    )

    assert _image_overlays_by_segment(session) == (("seg-1", "asset-photo(-/-/-/-)"),)


def test_yujin_can_tell_a_photo_from_a_video_in_the_asset_list() -> None:
    """유진이 사진을 **가려낼 신호**가 없었다 — 코드리뷰 2026-09-06.

    안내문은 "사진만 얹어라"라고 하는데 자산 목록은 사진을 영상과 똑같이
    `broll`로 적었다. 고를 근거를 안 주고 틀리면 `media_asset_type_mismatch`로
    거절하는 꼴이다 -- 이 저장소가 자산 목록 때문에 이미 두 번 겪은 모양이다.

    `apply_media`에 쓸 이름(`broll`)은 그대로 둔다. 그 이름을 바꾸면 2026-09-05에
    고친 것이 도로 깨진다. 사진이라는 것만 덧붙인다.
    """
    from videobox_core_engine.yujin_editing_proposal_service import _approved_asset_catalogue

    catalogue = _approved_asset_catalogue(
        _context(
            approved_asset_ids=("asset_photo", "asset_clip"),
            approved_asset_types=(("asset_photo", "image"), ("asset_clip", "broll_video")),
            approved_asset_labels=(("asset_photo", "20241208_121938.jpg"), ("asset_clip", "거리 걷기")),
        )
    )

    assert "asset_photo(broll·사진" in catalogue, catalogue
    assert "asset_clip(broll," in catalogue, catalogue


def test_yujin_is_told_whether_the_thing_on_screen_is_a_photo_or_a_video() -> None:
    """대표님 상시 지시: 화면에 열면 유진도 같이 연다.

    얹는 것은 이미 열렸다(`_OVERLAYABLE_ASSET_TYPES`). 그런데 유진에게
    "지금 얹혀 있는 것"을 알려 주는 줄(`image_overlays_by_segment`)은 사진과
    영상을 구별하지 않는다 -- "얹은 영상 작게 해줘"에 유진은 무엇이 얹혀
    있는지 모른 채 답한다. 목록과 지금 걸린 값은 한 쌍이라는 것을 이
    저장소는 전환·색감에서 이미 두 번 배웠다.

    판단 근거는 세션이 이미 들고 있는 값 두 개를 맞대는 것뿐이다 --
    `image_overlays_by_segment`의 asset_id와 `approved_asset_types`.
    새 저장 칸은 만들지 않는다.
    """
    prompt = _editing_prompt(
        instruction="얹은 영상 좀 작게 해줘",
        context=_context(
            approved_asset_ids=("asset-photo", "asset-music", "asset-clip"),
            approved_asset_types=(
                ("asset-photo", "image"), ("asset-music", "bgm"), ("asset-clip", "broll_video"),
            ),
            image_overlays_by_segment=(("seg-1", "asset-clip(bottom/right/small/fade_in)"),),
        ),
    )

    assert "asset-clip(video, bottom/right/small/fade_in)" in prompt, prompt


def test_a_photo_overlay_keeps_the_old_wording_with_no_video_signal() -> None:
    """사진을 얹었을 때는 예전 문구가 그대로다 -- 신호는 영상에만 붙는다."""
    prompt = _editing_prompt(
        instruction="사진 좀 위로 올려줘",
        context=_context(
            image_overlays_by_segment=(("seg-1", "asset-photo(bottom/right/small/fade_in)"),),
        ),
    )

    assert "asset-photo(bottom/right/small/fade_in)" in prompt
    assert "asset-photo(video," not in prompt


def test_the_full_prompt_does_not_contradict_itself_about_what_can_be_laid_over() -> None:
    """유진이 한 번에 읽는 프롬프트 안에 서로 반대되는 두 문장이 있었다 (Task 4).

    `_approved_asset_catalogue`(먼저 실린다)는 "얹을 수 있는 것은 보이는 자산
    (사진·영상)뿐"이라 하고, 바로 뒤에 실리는 `_image_overlay_catalogue`는
    여전히 "asset_id는 승인된 자산 중 **사진**만 쓴다"고 했다. 영상 오버레이는
    `c43abf4b1`로 이미 열렸는데(`_OVERLAYABLE_ASSET_TYPES`) 이 줄만 안 따라간
    것이다 -- 유진이 뒤 문장을 믿으면 백엔드는 받아 주는데도 영상을 얹어
    달라는 말을 거절한다.

    두 함수를 따로 재면 이 결함은 안 잡힌다 -- 각자는 자기 안에서 일관되기
    때문이다. 그래서 `_editing_prompt`가 실제로 만드는 **프롬프트 전체**로
    잰다.
    """
    prompt = _editing_prompt(
        instruction="영상 하나 오른쪽 아래에 작게 얹어줘",
        context=_context(
            approved_asset_ids=("asset-photo", "asset-music", "asset-clip"),
            approved_asset_types=(
                ("asset-photo", "image"), ("asset-music", "bgm"), ("asset-clip", "broll_video"),
            ),
        ),
    )

    # 옛 문구("승인된 자산 중 **사진**만 쓴다")가 남아 있으면 유진은 영상
    # 오버레이 요청을 스스로 거절한다 -- 검증(_OVERLAYABLE_ASSET_TYPES)은
    # 영상을 받아 주는데도.
    assert "승인된 자산 중 **사진**만 쓴다" not in prompt, prompt
    # **개수 세기(`count("사진·영상") == 2`)는 최종 리뷰에서 깨졌다** -- 빼는
    # 문장("얹은 사진을 빼는 것은 remove_image_overlay다")에도 같은 말을
    # 넣어 고치면서 등장 횟수가 그냥 늘었다. 문구가 하나 더 늘 때마다 다시
    # 깨지는 숫자 대신, set_image_overlay·remove_image_overlay 두 동작을
    # 설명하는 문장 중 어느 것도 "사진만" 받는다고 말하지 않는다는 **규칙
    # 자체**로 잰다.
    assert "얹는" in prompt and "얹은" in prompt, prompt  # 두 문장 다 실렸는지 먼저 확인
    for sentence in prompt.split(". "):
        if "set_image_overlay" in sentence or "remove_image_overlay" in sentence:
            assert "사진만" not in sentence, sentence
            assert "얹은 사진을" not in sentence, sentence
