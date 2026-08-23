"""**대표가 실제로 여는 캡컷 초안**이 꺼 둔 것을 되살리지 않는가.

캡컷으로 나가는 길이 둘이다.

- `CapCutExportAdapter.build_payload` -- 매니페스트 JSON. UI는 더 이상 이 길을
  부르지 않는다(`task22-parity-owners.test.ts`가 `/jobs/capcut-export`가 화면
  코드에서 사라진 것을 지킨다).
- `PyCapCutRealExportAdapter.export_timeline` -- **캡컷에서 열리는 실제 초안.**
  `run_capcut_draft_export_job`이 부르고, 그 앞에서 타임라인을
  `materialize_editing_session_timeline`으로 만든다.

2026-08-23에 앞의 길만 고쳐 놓고 "캡컷이 지운 것을 되살리지 않는다"고 적었다.
그런데 그 길은 **저장된** 타임라인을 받아 `track_states`가 아예 없고, 실제
초안을 만드는 이 길은 손대지 않았다. 시험이 통과한 이유는 시험이 그 칸을 손으로
넣었기 때문이다 -- 같은 실패를 세 번째로 낸 것이라 여기서 못을 박는다.
"""
from __future__ import annotations

from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter


def _timeline(states: dict | None = None) -> dict:
    timeline: dict = {
        "timeline_id": "timeline_001",
        "tracks": [
            {"track_type": "narration", "clips": [
                {"clip_id": "c-n", "segment_id": "seg_001", "start_sec": 0.0, "end_sec": 4.0},
            ]},
            {"track_type": "broll", "clips": [
                {"clip_id": "c-b", "segment_id": "seg_001", "start_sec": 0.0, "end_sec": 4.0},
            ]},
            {"track_type": "bgm", "clips": [
                {"clip_id": "c-m", "segment_id": "seg_001", "start_sec": 0.0, "end_sec": 4.0},
            ]},
            {"track_type": "sfx", "clips": [
                {"clip_id": "c-s", "segment_id": "seg_001", "start_sec": 0.0, "end_sec": 1.0},
            ]},
        ],
    }
    if states is not None:
        timeline["track_states"] = states
    return timeline


def _collected(states: dict | None = None) -> dict[str, list]:
    narration, broll, bgm, sfx = PyCapCutRealExportAdapter(store=None)._collect_clips(_timeline(states))
    return {"narration": narration, "broll": broll, "bgm": bgm, "sfx": sfx}


def test_without_state_every_lane_reaches_the_draft() -> None:
    collected = _collected()

    assert all(collected[lane] for lane in ("narration", "broll", "bgm", "sfx"))


def test_a_hidden_video_lane_does_not_reach_the_draft() -> None:
    # 화면에서 뺀 영상이 캡컷 초안에 살아 있으면, 지운 줄 알고 넘긴 대표가
    # 캡컷에서 그대로 마주친다.
    collected = _collected({"broll": {"hidden": True}})

    assert collected["broll"] == []
    assert collected["narration"], "나머지 레인은 그대로여야 한다"


def test_a_muted_sound_lane_does_not_reach_the_draft() -> None:
    # 이 만듦새에도 음소거 칸이 없다 -- 넣으면 지운 소리가 되살아난다.
    assert _collected({"bgm": {"muted": True}})["bgm"] == []
    assert _collected({"sfx": {"muted": True}})["sfx"] == []
    assert _collected({"narration": {"muted": True}})["narration"] == []


def test_muting_the_video_lane_keeps_its_picture_in_the_draft() -> None:
    # 영상 음소거는 소리만 끈다. 트랙을 빼면 그림까지 사라진다.
    assert _collected({"broll": {"muted": True}})["broll"]


def test_state_that_is_all_off_changes_nothing() -> None:
    assert _collected({}) == _collected()
