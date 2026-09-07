"""유진이 사진을 장면에 놓지 못했다 — owner 요청 2026-09-06.

> "유진이 사진 고르는것도 하고"

owner의 사진 56장이 자료실에 있고, 추천기는 이미 사진을 장면 후보로 준다
(`list_scene_candidate_assets`), 렌더러도 사진을 장면으로 읽고 움직인다
(`_looks_like_image`, `_photo_motion_chain`). **유진 경로만 막혀 있었다.**

막힌 자리는 둘이다:

1. `apply_media`의 `media_type` enum이 `broll`/`bgm`/`sfx`뿐이라 사진을 지목할
   말 자체가 없다
2. 검증기의 종류 매핑에 사진 자리가 없다

**사진도 장면이다.** 영상과 같은 자리에 놓이고 같은 `broll_override`에 실린다 --
다른 점은 렌더러가 `-loop 1`로 늘리고 움직임을 얹는다는 것뿐이다. 그래서 새 칸을
만들지 않고 `broll`이 사진도 받게 한다: 창작자가 "이 사진 깔아줘"라고 할 때
유진이 굳이 다른 낱말을 골라야 할 이유가 없다.
"""

from __future__ import annotations

from videobox_core_engine.yujin_editing_proposal_service import (
    YujinEditingContext,
    interpret_yujin_editing_request,
)


def _context() -> YujinEditingContext:
    return YujinEditingContext(
        session_id="session-1",
        session_revision=3,
        segment_ids=("seg-1",),
        approved_asset_ids=("asset-photo", "asset-video", "asset-music"),
        approved_asset_types=(
            ("asset-photo", "image"),
            ("asset-video", "broll_video"),
            ("asset-music", "bgm"),
        ),
    )


def _response(*, asset_id: str, media_type: str = "broll") -> dict[str, object]:
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "그 사진을 장면에 깔았어요.",
        "proposal": {
            "proposal_id": "candidate",
            "base_session_revision": 3,
            "operations": [{
                "intent": "apply_media", "segment_id": "seg-1",
                "media_type": media_type, "asset_id": asset_id,
            }],
        },
    }


def test_yujin_can_put_a_photo_in_a_scene() -> None:
    accepted = interpret_yujin_editing_request(_response(asset_id="asset-photo"), _context())

    assert accepted.reason is None, accepted.reason
    assert accepted.proposal is not None
    assert accepted.proposal.operations[0].asset_id == "asset-photo"


def test_a_video_still_works_in_the_same_slot() -> None:
    """사진을 받게 하면서 영상이 막히면 안 된다."""
    accepted = interpret_yujin_editing_request(_response(asset_id="asset-video"), _context())

    assert accepted.reason is None, accepted.reason


def test_music_in_a_scene_slot_is_still_refused() -> None:
    """느슨하게 풀지 않는다 -- 음악을 화면 자리에 놓으면 여전히 막힌다."""
    refused = interpret_yujin_editing_request(_response(asset_id="asset-music"), _context())

    assert refused.reason == "media_asset_type_mismatch"


def test_a_photo_in_the_music_slot_is_refused() -> None:
    """반대 방향도 막는다."""
    refused = interpret_yujin_editing_request(
        _response(asset_id="asset-photo", media_type="bgm"), _context()
    )

    assert refused.reason == "media_asset_type_mismatch"
