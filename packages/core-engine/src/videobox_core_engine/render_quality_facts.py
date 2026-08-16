"""완성본이 어땠는지 숫자로 남긴다.

렌더가 성공했다는 것과 결과물이 쓸 만하다는 것은 다르다. 2026-08-16까지 이 저장소는
완성본이 좋았는지 나빴는지 **아무 데도 기록하지 않았다** — 20초 영상에 5초 소리만 담긴
완성본도, 완전 무음 완성본도 성공으로만 남았다.

여기서 재는 것은 합성 계획에서 바로 나오는 사실들이라 추가 디코딩이 들지 않는다.
소리가 실렸는지는 만들어진 파일을 봐야 알 수 있어서 `ffmpeg_final_renderer`가 따로 잰다.

이 기록이 쌓여야 나중에 "지난 영상들보다 나은가"를 물을 수 있다.
"""

from __future__ import annotations

from typing import Any

from videobox_core_engine.composition_plan import CompositionPlan

# 화면에 보이는 것만 장면으로 센다. 음악 한 곡을 장면으로 세면 숫자가 뜻을 잃는다.
VISUAL_TRACK_TYPES = frozenset({"broll", "narration", "overlay"})


def _overlapping_caption_count(plan: CompositionPlan) -> int:
    """서로를 가리는 자막의 수.

    앞 자막이 끝나는 순간 다음이 시작하는 것은 정상이라 겹침으로 세지 않는다.
    그걸 세면 멀쩡한 영상이 전부 문제로 보인다.
    """
    cues = sorted(plan.captions, key=lambda cue: (cue.start_sec, cue.end_sec))
    overlaps = 0
    for index, cue in enumerate(cues):
        for later in cues[index + 1:]:
            if later.start_sec >= cue.end_sec:
                break
            overlaps += 1
    return overlaps


def composition_quality_facts(plan: CompositionPlan) -> dict[str, Any]:
    """이 완성본을 나중에 되돌아볼 수 있게 하는 사실들."""
    scenes = [item for item in plan.items if item.track_type in VISUAL_TRACK_TYPES]
    scene_seconds = [max(0.0, item.end_sec - item.start_sec) for item in scenes]
    return {
        "duration_sec": round(plan.duration_sec, 3),
        "scene_count": len(scenes),
        "average_scene_sec": round(sum(scene_seconds) / len(scene_seconds), 3) if scene_seconds else 0.0,
        "caption_count": len(plan.captions),
        "caption_overlap_count": _overlapping_caption_count(plan),
        "width": plan.width,
        "height": plan.height,
    }
