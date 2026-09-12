"""빈 편집판 -- 기획을 통과하지 않고 편집기를 여는 길.

편집 세션을 만드는 길은 둘뿐이었고 **둘 다 기획을 먼저 통과해야 했다**:
기획 산출물(`timeline_job_id`)이거나 대본(`script_asset_id`). 영상 편집 프로그램인데
편집기가 설문 뒤에 잠겨 있었다(2026-08-17 owner 지시로 착수).

**완전히 빈 세션은 만들지 않는다.** 장면이 하나도 없으면 타임라인에 그릴 것도,
고를 것도, 나눌 것도 없어서 "편집판이 열렸다"고 할 수 없다. 대신 **비어 있는 장면
하나**로 연다 -- 캡컷에서 새 프로젝트를 열면 보이는 그 빈 트랙과 같다.

그리고 그 장면은 `review_required`로 표시한다. 아직 아무것도 안 들어 있으므로,
채우기 전에 조용히 완성본으로 나가면 안 된다.
"""

from __future__ import annotations

import uuid
from typing import Any

# 처음 열었을 때 타임라인에 눈에 보이는 폭을 주는 길이. 사용자가 재료를 넣으면
# 그 길이로 맞춰진다.
BLANK_SCENE_SECONDS = 5.0


# 길이를 안 적으므로 `scene_seconds`를 받지 않는다. 인자로 남겨 두면 "여기에도
# 길이가 실린다"고 읽히고, 그 오해가 이 결함의 시작이었다.
def build_blank_timeline_payload() -> dict[str, Any]:
    """빈 편집판이 딛고 설 타임라인.

    편집기는 세션만으로는 못 연다 -- 재생 목록을 만들려면 **짝이 되는 타임라인**이
    있어야 한다(2026-08-17에 세션만 만들었더니 화면이 `재생 내용을 불러오지
    못했어요`만 띄웠다). 트랙은 비워 두고 화면 크기와 프레임만 정해 준다.

    **길이는 여기 안 적는다.** 예전에는 `output.duration_sec`에 5.0을 적어 뒀는데,
    그 값을 고쳐 주는 편집 문이 하나도 없어서(편집은 전부 세션에만 쌓인다) 그걸
    읽는 자리마다 결함이 났다 -- 눈금자가 120초 영상을 5초로 그렸고, 조각을 옮길
    때의 상한이 5초로 잠겼다(2026-09-12). 길이는 한 자리에서 조각을 보고 잰다
    (`composition_plan.materialized_timeline_duration_sec`). 기획을 통과한
    타임라인도 이 칸을 안 적는다. **되살리지 마라.**

    갓 연 편집판의 길이는 그래도 5초다 -- 0~5초 장면이 그 값을 들고 있고, 장면을
    늘리면 길이도 따라온다.
    """
    return {
        "version": "blank-v1",
        "timebase": "seconds",
        "fps_num": 30,
        "fps_den": 1,
        "output": {"width": 1920, "height": 1080},
        "tracks": [],
    }


def build_blank_editing_session(
    *, project_id: str, timeline_id: str | None = None, scene_seconds: float = BLANK_SCENE_SECONDS
) -> dict[str, Any]:
    """재료가 하나도 없는 상태로 편집기를 열 수 있는 세션을 만든다."""
    if not str(project_id).strip():
        raise ValueError("project_id must not be empty.")
    if scene_seconds <= 0:
        raise ValueError("scene_seconds must be positive.")

    # 같은 프로젝트에서 여러 번 열 수 있어야 한다. timeline_id가 겹치면 새로 연
    # 편집판이 먼저 것을 덮어쓴다.
    timeline_id = timeline_id or f"blank:{uuid.uuid4().hex}"
    segment_id = f"{timeline_id}:001"
    return {
        "project_id": str(project_id).strip(),
        "timeline_id": timeline_id,
        "timing_source": "blank",
        "segments": [
            {
                "segment_id": segment_id,
                "caption_text": "",
                "start_sec": 0.0,
                "end_sec": float(scene_seconds),
                "cut_action": "keep",
                # 안전장치: 빈 편집판은 내보낼 수 있는 물건이 아니다.
                "review_required": True,
                "broll_override": None,
                "visual_overlays": [],
                "music_override": None,
                "sfx_override": None,
                "tts_replacement": None,
            }
        ],
        "history": [],
        "undo_stack": [],
        "redo_stack": [],
        "session_revision": 1,
    }
