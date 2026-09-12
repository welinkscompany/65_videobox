"""세로 숏폼이 원본의 **좌우를 잘라 먹었다** — 대표님 실물 2026-09-12.

> 대표님: "방금 너가 쪼갠 영상을 봤는데, 배경 좌우가 짤려서 글자가 양쪽
> 사이드가 안보여."

원본(1920×1080)은 이미 유튜브에 올린 영상이라 **자막이 그림에 구워져 있다.**
그 자막 띠가 화면 폭을 거의 다 쓴다. 9:16 캔버스(1080×1920)에 `crop`으로 채우면
가운데 607픽셀만 남아서 구워진 자막이 양쪽에서 잘린다 -- 자막 렌더링 결함이
아니라 16:9를 9:16으로 잘라 채우면 반드시 생기는 결과다.

되돌려 `fit`을 쓰면 위아래가 검은 띠 68.3%다(2026-09-11 실측으로 이미 버린 값).
**두 값으로는 답이 없다.** 그래서 세 번째 값 `blur`(화면 이름 `전체 담기`)를
만든다: 원본 전체를 비율 그대로 담고, 남는 위아래는 같은 그림을 확대해 흐리게
깔아 채운다. 잘리는 것도 없고 검은 띠도 없다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.ffmpeg_final_renderer import FfmpegFinalRenderer
from videobox_core_engine.media_controls import normalize_media_controls
from videobox_storage.local_project_store import LocalProjectStore
from videobox_storage.timeline_clip_source_resolution import ResolvedClipSource

FIT_KEEPS_EVERYTHING = "blur"


def _controls(**payload: object) -> dict:
    return normalize_media_controls(payload, media_kind="broll", duration_sec=4.0)


# --- 엔진 -------------------------------------------------------------------


def test_the_engine_accepts_the_third_way() -> None:
    assert _controls(fit=FIT_KEEPS_EVERYTHING)["fit"] == FIT_KEEPS_EVERYTHING


def test_a_made_up_fit_is_still_refused() -> None:
    """허용값을 넓히는 것이 아무 값이나 받는다는 뜻은 아니다."""
    with pytest.raises(ValueError, match="fit"):
        _controls(fit="stretch")


def test_the_blurred_backdrop_keeps_the_whole_picture() -> None:
    """보이는 그림은 **줄여서 담는다**(`decrease`) -- 잘라내지 않는다.

    잘라내는 `crop`은 뒤에 깔 흐린 배경에만 쓴다. 여기서 `decrease`가 빠지면
    대표님이 본 그 결함(구워진 자막이 양쪽에서 잘림)이 그대로 남는다.
    """
    renderer = FfmpegFinalRenderer(store=None, video_width=1080, video_height=1920)

    chain = renderer._broll_fit_transform({"fit": FIT_KEEPS_EVERYTHING})

    assert "split" in chain, "같은 그림을 둘로 나누지 않으면 배경을 깔 수 없다"
    assert "gblur" in chain, "배경을 흐리게 하지 않으면 잘린 그림이 두 겹으로 보인다"
    assert "overlay=" in chain, "배경 위에 원본을 얹지 않으면 배경만 남는다"
    assert "force_original_aspect_ratio=decrease" in chain, "보이는 그림이 잘리고 있다"
    # 검은 띠를 깔던 `pad`는 이제 필요 없다 -- 흐린 배경이 그 자리를 채운다.
    assert "pad=" not in chain


def test_the_two_old_ways_did_not_move() -> None:
    """새 값을 더하면서 옛 두 값의 사슬이 바뀌면, 아무것도 안 바꾼 편집본의
    완성본이 달라진다. 이 저장소가 색감 칸에서 이미 겪은 함정이다.
    """
    renderer = FfmpegFinalRenderer(store=None, video_width=1080, video_height=1920)

    assert renderer._broll_fit_transform({"fit": "crop"}) == (
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    )
    assert renderer._broll_fit_transform({"fit": "fit"}) == (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    )


def test_two_clips_do_not_collide_on_the_same_label() -> None:
    """흐린 배경은 필터 그래프에 **이름 붙은 갈래**를 만든다. 한 편집본에
    클립이 둘이면 같은 이름이 두 번 나와 ffmpeg가 통째로 거절한다.
    """
    renderer = FfmpegFinalRenderer(store=None, video_width=1080, video_height=1920)

    first = renderer._broll_fit_transform({"fit": FIT_KEEPS_EVERYTHING}, tag="v_clip_a")
    second = renderer._broll_fit_transform({"fit": FIT_KEEPS_EVERYTHING}, tag="v_clip_b")

    assert "v_clip_a" in first and "v_clip_b" in second
    assert first != second


def test_the_finished_file_path_gets_the_same_backdrop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**렌더 경로가 둘이다.** 그래프(`build_plan_filter_graph`)는 미리보기 쪽이고
    완성본 mp4는 `_extract_segment`로 나온다. 한 곳만 고치면 화면에서는 살아
    있는 좌우가 파일에서는 잘린다 -- 이 저장소가 두 번 걸린 함정이다.
    """
    store = LocalProjectStore(tmp_path)
    renderer = FfmpegFinalRenderer(store=store, video_width=1080, video_height=1920)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        FfmpegFinalRenderer,
        "_run",
        lambda _self, command: (commands.append(command) or subprocess.CompletedProcess(command, 0, "", "")),
    )
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_media_duration", lambda _self, _path: 10.0)

    renderer._extract_segment(
        source=ResolvedClipSource(path=tmp_path / "wide.mp4", trim_start_sec=0.0, trim_duration_sec=4.0),
        output_path=tmp_path / "segment.mp4",
        video=True,
        media_controls={"fit": FIT_KEEPS_EVERYTHING},
    )

    video_filter = commands[0][commands[0].index("-vf") + 1]
    assert "split" in video_filter
    assert "gblur" in video_filter
    assert "overlay=" in video_filter
    assert "force_original_aspect_ratio=decrease" in video_filter


def test_the_finished_file_path_caps_its_threads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**컨테이너에서 실측한 결함이다(2026-09-12).** 흐린 배경은 갈래가 둘이라
    필터·인코더 스레드를 더 잡는데, 이 경로는 상한을 한 번도 안 걸고 있었다.
    컨테이너의 `pids.max`는 128이고 ffmpeg는 호스트 CPU 16을 보고 스레드를
    잡는다 -- 그래서 같은 원본·같은 명령이 이렇게 끝났다:

        [png] ff_frame_thread_encoder_init failed
        Error while opening encoder - maybe incorrect parameters ...

    `-threads 8`(`encoder_thread_limit`)을 걸면 통과한다. 옛 `crop` 사슬은
    상한 없이도 통과해서 **새 값에서만** 터진다 -- 그래프 쪽은 이미 이 상한을
    걸고 있었고(`:1766`), 이 경로만 빠져 있었다.
    """
    store = LocalProjectStore(tmp_path)
    renderer = FfmpegFinalRenderer(store=store, video_width=1080, video_height=1920)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        FfmpegFinalRenderer,
        "_run",
        lambda _self, command: (commands.append(command) or subprocess.CompletedProcess(command, 0, "", "")),
    )
    monkeypatch.setattr(FfmpegFinalRenderer, "_probe_media_duration", lambda _self, _path: 10.0)

    renderer._extract_segment(
        source=ResolvedClipSource(path=tmp_path / "wide.mp4", trim_start_sec=0.0, trim_duration_sec=4.0),
        output_path=tmp_path / "segment.mp4",
        video=True,
        media_controls={"fit": FIT_KEEPS_EVERYTHING},
    )

    command = commands[0]
    cap = str(renderer.encoder_thread_limit())
    assert command[command.index("-threads") + 1] == cap
    assert command[command.index("-filter_threads") + 1] == cap


# --- 세로 변형본의 기본값 ---------------------------------------------------


def test_a_vertical_short_now_defaults_to_keeping_the_sides() -> None:
    """2026-09-11에 정한 기본값(`crop`)을 뒤집는다. 근거는 대표님 실물이다."""
    from videobox_core_engine.output_variants import _filled_broll_controls

    assert _filled_broll_controls({})["fit"] == FIT_KEEPS_EVERYTHING


def test_the_master_tracks_of_a_vertical_variant_keep_the_sides() -> None:
    from videobox_core_engine.output_variants import _fill_frame_for_vertical_variant

    tracks = _fill_frame_for_vertical_variant(
        [{"track_id": "t", "track_type": "broll", "clips": [{"clip_id": "c1", "media_controls": {"fit": "fit"}}]}],
        variant_kind="vertical_highlight",
    )

    assert tracks[0]["clips"][0]["media_controls"]["fit"] == FIT_KEEPS_EVERYTHING


def test_the_session_chosen_broll_of_a_vertical_variant_keeps_the_sides() -> None:
    """화면 경로는 트랙이 아니라 세션의 `broll_override`다(2026-09-12 실측).
    대표님 편집본은 트랙이 비어 있었으므로 화면 전체가 이 경로였다.
    """
    from videobox_core_engine.output_variants import _fill_frame_for_vertical_session

    filled = _fill_frame_for_vertical_session({
        "segments": [{
            "segment_id": "seg_001",
            "broll_override": {"asset_id": "a1", "media_controls": {}},
            "media_windows": [{"broll_override": {"asset_id": "a1", "media_controls": {}}}],
        }],
    })

    segment = filled["segments"][0]
    assert segment["broll_override"]["media_controls"]["fit"] == FIT_KEEPS_EVERYTHING
    assert segment["media_windows"][0]["broll_override"]["media_controls"]["fit"] == FIT_KEEPS_EVERYTHING


# --- 엔진 위 층: API·미리보기 지문·캡컷 -------------------------------------


def test_the_editor_screen_can_read_a_clip_that_chose_it() -> None:
    """응답 모델은 `extra="forbid"`이고 `fit`은 `Literal`이다. 엔진만 넓히고
    여기를 빼먹으면 화면 저장이 422로 거절된다(이 저장소의 전례).
    """
    from videobox_api.models import EditorMediaControlsResponse

    assert EditorMediaControlsResponse(fit=FIT_KEEPS_EVERYTHING).fit == FIT_KEEPS_EVERYTHING


def test_changing_the_fit_moves_the_preview_fingerprint() -> None:
    """지문이 안 움직이면 **캐시된 미리보기가 그대로 나온다** -- 고쳐 놓고도
    대표님은 잘린 화면을 계속 본다.
    """
    from videobox_core_engine.exact_preview import fingerprint_exact_preview

    renderer = FfmpegFinalRenderer(store=None, video_width=1080, video_height=1920)

    def _fingerprint(fit: str) -> str:
        plan = renderer.extract_composition_plan(timeline={
            "timeline_id": "t", "project_id": "p", "output": {"width": 1080, "height": 1920},
            "tracks": [{"track_id": "tr", "track_type": "broll", "clips": [{
                "clip_id": "c1", "clip_type": "broll", "asset_id": "a1", "asset_uri": "u",
                "segment_id": "seg_001", "start_sec": 0.0, "end_sec": 4.0,
                "media_controls": {"fit": fit},
            }]}],
        })
        return fingerprint_exact_preview(plan=plan, session_captions=[], used_asset_sha256={})

    assert _fingerprint("crop") != _fingerprint(FIT_KEEPS_EVERYTHING)
    # 옛 표기(`contain`)는 예전대로 `fit`으로 정규화된다 -- 새 값을 더하면서 그
    # 길이 막히면 옛 저장분의 지문이 통째로 움직여 캐시가 전부 무효가 된다.
    assert _fingerprint("contain") == _fingerprint("fit")


def test_capcut_export_does_not_silently_crop_the_sides() -> None:
    """캡컷 초안은 흐린 배경을 표현할 수 없다. 그때 **조용히 `crop`으로
    떨어지면** 내보낸 초안에서 좌우가 다시 잘린다 -- 값을 잃는 것은 남긴다.
    """
    from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter

    warnings: list[str] = []
    settings = PyCapCutRealExportAdapter._broll_crop_settings(
        object.__new__(PyCapCutRealExportAdapter), path=Path("unused.mp4"),
        fit=FIT_KEEPS_EVERYTHING, warnings=warnings,
    )

    assert settings.upper_left_x == 0.0 and settings.upper_right_x == 1.0
    assert settings.upper_left_y == 0.0 and settings.lower_left_y == 1.0
    assert any("blur" in note or "backdrop" in note for note in warnings), warnings


# --- 화면 -------------------------------------------------------------------


SCREEN_CATALOG = (
    Path(__file__).resolve().parents[1]
    / "apps" / "web" / "src" / "features" / "editor" / "inspector" / "frameFits.ts"
)


def test_the_screen_offers_exactly_the_three_ways() -> None:
    """**두 벌을 두면 반드시 어긋난다.** 화면에만 있는 값은 422로 거절되고,
    엔진에만 있는 값은 대표님이 영영 고를 수 없다(색감·사진 움직임과 같은 방식).
    """
    import re

    from videobox_core_engine.media_controls import BROLL_FIT_LABELS

    source = SCREEN_CATALOG.read_text(encoding="utf-8")
    block = source.split("FRAME_FIT_CHOICES", 1)[1].split("];", 1)[0]
    choices = re.findall(r'\{\s*value:\s*"([^"]+)",\s*label:\s*"([^"]+)"', block)

    assert dict(choices) == BROLL_FIT_LABELS
    assert FIT_KEEPS_EVERYTHING in dict(choices)


def test_the_screen_never_shows_the_internal_words() -> None:
    """§10.13 -- `crop`·`blur`는 대표님 화면에 쓰지 않는다."""
    from videobox_core_engine.media_controls import BROLL_FIT_LABELS

    for label in BROLL_FIT_LABELS.values():
        assert "crop" not in label and "blur" not in label and "fit" not in label


# --- 유진 -------------------------------------------------------------------


def _yujin_payload(fit: str, segment_id: str = "seg_001") -> dict:
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "화면 맞춤을 바꿔 볼게요.",
        "proposal": {
            "proposal_id": "fit",
            "base_session_revision": 1,
            "operations": [{"intent": "set_scene_transform", "segment_id": segment_id, "fit": fit}],
        },
    }


def _yujin_context():
    from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext

    return YujinEditingContext(
        session_id="s", session_revision=1, segment_ids=("seg_001",),
        segment_ids_with_broll=("seg_001",),
    )


def test_yujin_can_ask_to_keep_the_sides() -> None:
    """화면으로 되는 것은 유진에게 말해서도 돼야 한다(상시 지시)."""
    from videobox_core_engine.yujin_editing_proposal_adapter import interpret_yujin_editing_request

    result = interpret_yujin_editing_request(_yujin_payload(FIT_KEEPS_EVERYTHING), _yujin_context())

    assert result.status == "candidate_only"
    assert result.proposal is not None
    assert result.proposal.operations[0].fit == FIT_KEEPS_EVERYTHING


def test_yujin_cannot_make_up_a_fit() -> None:
    from videobox_core_engine.yujin_editing_proposal_adapter import interpret_yujin_editing_request

    result = interpret_yujin_editing_request(_yujin_payload("stretch"), _yujin_context())

    assert result.status != "candidate_only"


def test_what_yujin_asked_for_reaches_the_clip() -> None:
    """적용기 층. 값을 받아 놓고 저장에 안 닿으면 "바꿨어요"만 남는다."""
    from videobox_core_engine.editing_session import apply_yujin_editing_proposal
    from videobox_core_engine.yujin_editing_proposal_adapter import interpret_yujin_editing_request

    session = {
        "session_id": "s", "session_revision": 1,
        "segments": [{
            "segment_id": "seg_001", "start_sec": 0.0, "end_sec": 4.0,
            "broll_override": {"asset_id": "broll_001", "media_controls": {"fit": "crop"}},
        }],
    }
    result = interpret_yujin_editing_request(_yujin_payload(FIT_KEEPS_EVERYTHING), _yujin_context())
    assert result.proposal is not None

    applied = apply_yujin_editing_proposal(session=session, proposal=result.proposal)

    assert applied["segments"][0]["broll_override"]["media_controls"]["fit"] == FIT_KEEPS_EVERYTHING


def test_the_prompt_gives_both_the_list_and_what_is_already_on() -> None:
    """**목록과 "지금 걸린 값"은 한 쌍이다.** 지금 값을 빼면 되돌리기가 막힌다."""
    from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext
    from videobox_core_engine.yujin_editing_proposal_service import _editing_prompt

    prompt = _editing_prompt(
        instruction="좌우 안 잘리게 해줘",
        context=YujinEditingContext(
            session_id="s", session_revision=1, segment_ids=("seg_001",),
            segment_ids_with_broll=("seg_001",),
            fits_by_segment=(("seg_001", "crop"),),
        ),
    )

    assert FIT_KEEPS_EVERYTHING in prompt
    assert "전체 담기" in prompt, "코드만 주면 '좌우 안 잘리게'를 못 옮긴다"
    assert "지금 화면 맞춤이 걸린 장면: seg_001(crop)" in prompt


def test_the_creator_path_can_also_keep_the_sides() -> None:
    """유진에게 가는 길이 둘이다 -- 편집 명령과 창작 추천. 추천 쪽에서 새 값이
    조용히 `crop`으로 떨어지면 자료실 영상을 깔 때마다 좌우가 잘린다.
    """
    from videobox_core_engine.yujin_creator_proposal_adapter import _supported_media_controls

    assert _supported_media_controls(kind="broll", parameters={"fit": "contain_blur"}) == {
        "fit": FIT_KEEPS_EVERYTHING
    }
    assert _supported_media_controls(kind="broll", parameters={"fit": "contain"}) == {"fit": "fit"}
    assert _supported_media_controls(kind="broll", parameters={"fit": "cover"}) == {"fit": "crop"}


def test_the_creator_skill_tells_yujin_the_third_token() -> None:
    """유진 프로필 안내문에 없으면 받을 수 있어도 유진은 고르지 않는다."""
    skill = (
        Path(__file__).resolve().parents[1]
        / "config" / "hermes" / "yujin" / "skills" / "videobox-creator" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "contain_blur" in skill
