"""캡컷 초안이 **꺼 둔 것을 되살리지 않는가.**

`track_states.py`의 눈·음소거는 완성본에서는 지켜진다. 캡컷 내보내기는 그것을
읽지 않고 있었다 -- 화면에서 뺀 영상이 캡컷 초안에는 그대로 들어갔다
(2026-08-23 갭검증에서 발견).

**내용이 들어오는 길이 셋이다**: `tracks`, 자막 파일, `export_overlays`.
완성본에서 자막만 고치고 오버레이를 놓쳐 같은 실패를 두 번 냈으므로, 여기서는
셋을 한꺼번에 본다.

**표현할 수 없는 것도 있다.** 이 어댑터가 내보내는 트랙에는 음소거 칸이 없다
(`track_name`·`track_role`·`source_uri`·`segments`뿐). 그래서 "있는데 꺼짐"을
만들 수 없고 넣거나 빼는 선택뿐이다. 소리만 내는 레인(내레이션·배경음악·
효과음)은 꺼 두었으면 빼는 쪽이 맞다 -- 넣으면 지운 소리가 되살아난다.
**영상은 다르다**: 음소거해도 그림은 남겨야 하므로 트랙을 빼지 않는다.
"""
from __future__ import annotations

from videobox_capcut_export.adapter import CapCutExportAdapter
from videobox_core_engine.composition_plan import materialize_editing_session_timeline


def _timeline(states: dict | None = None) -> dict:
    timeline = {
        "timeline_id": "timeline_001",
        "project_id": "p",
        "narration_source_uri": "local://projects/p/inputs/narration/source.wav",
        "tracks": [
            {
                "track_id": "narration_primary",
                "track_type": "narration",
                "clips": [{"clip_id": "c-n", "segment_id": "seg_001",
                           "asset_uri": "local://projects/p/segments/seg_001",
                           "start_sec": 0.0, "end_sec": 4.0}],
            },
            {
                "track_id": "broll_main",
                "track_type": "broll",
                "clips": [{"clip_id": "c-b", "segment_id": "seg_001",
                           "asset_uri": "local://projects/p/assets/b",
                           "start_sec": 0.0, "end_sec": 4.0}],
            },
            {
                "track_id": "bgm_main",
                "track_type": "bgm",
                "clips": [{"clip_id": "c-m", "segment_id": "seg_001",
                           "asset_uri": "local://projects/p/assets/m",
                           "start_sec": 0.0, "end_sec": 4.0}],
            },
        ],
        "export_overlays": [
            {"clip_id": "eo1", "overlay_type": "explanation_card", "text": "핵심",
             "start_sec": 0.0, "end_sec": 2.0},
        ],
    }
    session = {
        "session_id": "session_001",
        "project_id": "p",
        "timeline_id": "timeline_001",
        "session_revision": 1,
        "segments": [{
            "segment_id": "seg_001",
            "caption_text": "캡컷 초안 자막",
            "start_sec": 0.0,
            "end_sec": 4.0,
            "cut_action": "keep",
            "review_required": False,
        }],
        "history": [],
        "track_states": states or {},
    }
    return materialize_editing_session_timeline(
        timeline=timeline,
        editing_session=session,
        project_id="p",
    )


def _payload(states: dict | None = None) -> dict:
    return CapCutExportAdapter().build_payload(
        project_id="p",
        timeline=_timeline(states),
        subtitle_file_uri="local://projects/p/subtitles/s.srt",
    )


def _track_types(payload: dict) -> set[str]:
    return {str(track.get("track_type")) for track in payload["tracks"]}


def _capcut_names(payload: dict) -> set[str]:
    return {str(track.get("track_name")) for track in payload["capcut_tracks"]}


def test_without_any_state_everything_is_handed_off() -> None:
    payload = _payload()

    assert _track_types(payload) == {"narration", "broll", "bgm"}
    assert "subtitle" in _capcut_names(payload)
    # 글자 오버레이 트랙은 종류 이름을 그대로 쓴다(`explanation_card`).
    assert "explanation_card" in _capcut_names(payload)


def test_a_hidden_video_lane_does_not_come_back_in_the_capcut_draft() -> None:
    # 화면에서 뺀 영상이 캡컷 초안에 그대로 들어가면, 대표는 지운 줄 알고
    # 넘겼는데 결과물에 살아 있다.
    payload = _payload({"broll": {"hidden": True}})

    assert "broll" not in _track_types(payload)
    assert "broll" not in _capcut_names(payload)
    # 나머지는 그대로다.
    assert {"narration", "bgm"} <= _track_types(payload)


def test_a_hidden_caption_lane_drops_the_subtitle_handoff() -> None:
    # 자막은 트랙이 아니라 **파일 하나로** 넘어간다. 트랙만 보면 못 잡는다.
    payload = _payload({"caption": {"hidden": True}})

    assert payload["subtitle_file_uri"] is None
    assert "subtitle" not in _capcut_names(payload)


def test_a_hidden_overlay_lane_drops_the_text_overlays() -> None:
    # 글자 오버레이는 `export_overlays`에 있다 -- 셋째 길이다.
    payload = _payload({"overlay": {"hidden": True}})

    assert "explanation_card" not in _capcut_names(payload)


def test_a_muted_sound_lane_is_left_out_rather_than_handed_over_loud() -> None:
    # 이 만듦새에는 음소거 칸이 없다. 넣으면 지운 소리가 캡컷에서 되살아난다.
    assert "bgm" not in _track_types(_payload({"bgm": {"muted": True}}))
    assert "narration" not in _track_types(_payload({"narration": {"muted": True}}))
    assert "voiceover" not in _capcut_names(_payload({"narration": {"muted": True}}))


def test_muting_the_video_lane_keeps_its_picture() -> None:
    # 영상 음소거는 **소리만** 끄는 것이다. 트랙을 빼면 그림까지 사라진다 --
    # 대표가 요청하지 않은 일이다.
    payload = _payload({"broll": {"muted": True}})

    assert "broll" in _track_types(payload)


def test_states_that_are_all_off_change_nothing() -> None:
    assert _payload({}) == _payload()


def test_the_export_decides_about_the_subtitle_once_for_both_consumers() -> None:
    """payload와 안내문이 자막을 두고 서로 다른 말을 하지 않는가.

    `start_capcut_export`는 자막을 **두 곳**에 넘긴다: 어댑터(payload의
    `subtitle_file_uri`)와 안내문 작성기(`Subtitle attached: yes/no`). 자막
    레인을 숨겼을 때 어댑터만 걸러 두면 payload는 "없음"인데 안내문은 "붙음"이
    된다 -- 같은 내보내기 안에서 두 곳이 어긋난다(2026-08-23 코드리뷰 지적).

    이 저장소가 이미 쓰는 방식대로(전환·색감 목록 대조) 원본을 맞대어 본다.
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "packages" / "core-engine" / "src" / "videobox_core_engine" / "local_pipeline.py"
    ).read_text(encoding="utf-8")
    body = source.split("def start_capcut_export(", 1)[1].split(chr(10) + "    def ", 1)[0]

    # 한 번 정하고 두 번 쓴다.
    assert body.count("capcut_subtitle_file_uri = (") == 1
    assert body.count("subtitle_file_uri=capcut_subtitle_file_uri") == 2
    # 원래 값을 두 번째 소비자에게 직접 넘기는 길이 남아 있으면 안 된다.
    assert 'subtitle_file_uri=latest_subtitle["file_uri"] if latest_subtitle else None' not in body
