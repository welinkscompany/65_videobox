"""자유 멀티트랙 Phase 2 -- 놓인 클립을 세그먼트 정체성에서 떼어낸다.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §3 Phase 2.
**아직 아무도 이 모델을 안 읽는다** -- Phase 1(`track_registry.py`)과 똑같이
완전히 덧붙이기만 하는 단계다. 렌더 경로(`composition_plan.py`)는 지금도
세그먼트의 `broll_override`/`music_override`/`sfx_override`를 직접 읽고,
이 파일이 생겨도 그대로 돈다.

**왜 필요한가**: 지금 구조에서 브롤·음악·효과음은 "트랙에 놓인 클립"이
아니라 **내레이션 세그먼트에 달린 필드**다(`editing_session.py`의
`broll_override` 등). 트랙을 자유화하려면(같은 종류 트랙 여럿, 순서 변경,
추가·삭제) 클립이 세그먼트 정체성 없이도 혼자 설 수 있어야 한다.

**세 종류는 대칭이 아니다.** 효과음만 `source_action_id`를 갖는다 --
유진이 추천한 그 삽입을 owner가 거절했는지 되짚는 열쇠라
(`composition_plan.py`가 `rejected_sfx_action_ids_by_segment`로 거른다),
셋을 똑같이 다루는 모델은 이 값을 조용히 흘린다. 그래서 선택 필드로
명시해 둔다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from videobox_core_engine.track_registry import Track

#: 이번 단계에서 트랙에 놓을 수 있는 클립 종류. `track_registry.VALID_TRACK_KINDS`
#: (6개)보다 좁다 -- 내레이션은 타이밍 기준이라 Phase 3, 자막·오버레이는
#: 세그먼트에 얹히는 부가물이라 Phase 3/7에서 다룬다.
VALID_CLIP_PLACEMENT_KINDS = frozenset({"broll", "bgm", "sfx"})

#: 세그먼트의 어느 필드가 어느 트랙 종류로 가는가. `composition_plan.py`의
#: `(("broll", "broll_override"), ("bgm", "music_override"), ("sfx", "sfx_override"))`와
#: 같은 짝이다 -- 이 짝이 어긋나면 음악이 효과음 트랙으로 간다.
SEGMENT_MEDIA_FIELD_BY_KIND: Mapping[str, str] = {
    "broll": "broll_override",
    "bgm": "music_override",
    "sfx": "sfx_override",
}


class ClipPlacementError(ValueError):
    """놓인 클립 하나 또는 그 목록의 앞뒤가 안 맞을 때."""


@dataclass(frozen=True, slots=True)
class PlacedClip:
    clip_id: str
    track_id: str
    kind: str
    asset_id: str
    #: **세션 타임라인의 절대 시각**이다. 지금은 이 값이 세그먼트에서
    #: 계산돼 나오지만(`migrate_segment_media_to_placed_clips`), 계산된
    #: 뒤에는 세그먼트를 다시 안 봐도 된다 -- 그게 이 단계의 목적이다.
    start_sec: float
    end_sec: float
    #: 어느 내레이션 세그먼트에서 나왔는지. 타이밍 기준은 아직 세그먼트가
    #: 쥐고 있으므로(Phase 3에서 일반화) 출처를 잃지 않는다.
    source_segment_id: str | None = None
    asset_uri: str | None = None
    media_controls: Mapping[str, Any] = field(default_factory=dict)
    expected_content_sha256: str | None = None
    media_revision: str | None = None
    #: 효과음 전용. 위 모듈 주석 참고.
    source_action_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in VALID_CLIP_PLACEMENT_KINDS:
            raise ClipPlacementError("clip_placement_kind_unsupported")
        for value, code in (
            (self.clip_id, "clip_placement_clip_id_required"),
            (self.track_id, "clip_placement_track_id_required"),
            (self.asset_id, "clip_placement_asset_id_required"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ClipPlacementError(code)
        if not math.isfinite(self.start_sec) or not math.isfinite(self.end_sec):
            raise ClipPlacementError("clip_placement_window_not_finite")
        if self.end_sec <= self.start_sec:
            raise ClipPlacementError("clip_placement_window_empty")


def validate_placed_clips(clips: list[PlacedClip], *, tracks: list[Track]) -> None:
    """클립 목록과 트랙 목록의 관계를 본다 -- 클립 하나하나가 아니라 사이를.

    겹침은 **같은 트랙 안에서만** 따진다. 브롤이 도는 동안 음악이 깔리는 것은
    정상이고(다른 트랙), 한 트랙에서 두 클립이 같은 시각을 덮으면 어느 쪽이
    이기는지 정해진 바가 없다 -- 렌더가 조용히 하나를 버리기 전에 여기서
    막는다.
    """
    if len({clip.clip_id for clip in clips}) != len(clips):
        raise ClipPlacementError("clip_placement_duplicate_clip_id")

    track_kind_by_id = {track.track_id: track.kind for track in tracks}
    for clip in clips:
        if clip.track_id not in track_kind_by_id:
            raise ClipPlacementError("clip_placement_track_missing")
        if track_kind_by_id[clip.track_id] != clip.kind:
            raise ClipPlacementError("clip_placement_track_kind_mismatch")

    by_track: dict[str, list[PlacedClip]] = {}
    for clip in clips:
        by_track.setdefault(clip.track_id, []).append(clip)
    for track_clips in by_track.values():
        ordered = sorted(track_clips, key=lambda item: (item.start_sec, item.end_sec))
        for earlier, later in zip(ordered, ordered[1:]):
            if later.start_sec < earlier.end_sec:
                raise ClipPlacementError("clip_placement_overlaps_on_track")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def migrate_segment_media_to_placed_clips(
    *,
    segments: list[dict[str, Any]],
    tracks: list[Track],
) -> list[PlacedClip]:
    """지금 세그먼트에 달려 있는 미디어 선택을 놓인 클립으로 **읽어만** 낸다.

    아무것도 안 고친다 -- 세그먼트는 그대로고, 렌더도 그대로 세그먼트를
    읽는다(`track_registry.migrate_legacy_tracks_to_registry`와 같은 자리).

    **판정 규칙은 `composition_plan.py`가 정본이다**(:526-583). 여기서 다시
    지으면 두 벌이 되어 Phase 4에서 갈아탈 때 어긋난다. 그래서 그 파일의
    분기를 그대로 옮긴다:

    - 종류마다 따로 푼다. 어느 한 종류에 **직접 선택**(`segment[field]`가
      dict)이 있으면 그 종류만 창을 통째로 건너뛴다.
    - 창의 시각은 `세그먼트 시작 + start_offset_sec`, 끝은 세그먼트 끝을
      넘지 않는다.
    - 자산 이름도 주소도 없는 선택은 클립이 아니다.
    - 잘라낸 장면(`cut_action == "remove"`)은 통째로 뺀다.

    거절된 효과음(`rejected_recommendations`)은 여기서 **안 거른다** -- 그
    판단은 타임라인 쪽 상태라 세그먼트만 보고는 알 수 없다. 대신
    `source_action_id`를 그대로 들고 나가서 부르는 쪽이 거를 수 있게 한다.
    """
    track_id_by_kind = {track.kind: track.track_id for track in tracks}
    placed: list[PlacedClip] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        if str(segment.get("cut_action") or "keep") == "remove":
            continue
        segment_id = str(segment.get("segment_id") or "").strip()
        start, end = _number(segment.get("start_sec")), _number(segment.get("end_sec"))
        if end <= start:
            continue
        raw_windows = segment.get("media_windows")
        windows = raw_windows if isinstance(raw_windows, list) and raw_windows else [{
            "start_offset_sec": 0.0,
            "duration_sec": end - start,
            **{field: segment.get(field) for field in SEGMENT_MEDIA_FIELD_BY_KIND.values()},
        }]
        for kind, field_name in SEGMENT_MEDIA_FIELD_BY_KIND.items():
            track_id = track_id_by_kind.get(kind)
            if track_id is None:
                continue
            direct_override = segment.get(field_name)
            field_windows = [{
                "start_offset_sec": 0.0, "duration_sec": end - start, field_name: direct_override,
            }] if isinstance(direct_override, dict) else windows
            for window_index, window in enumerate(field_windows):
                if not isinstance(window, dict):
                    continue
                window_start = start + _number(window.get("start_offset_sec"))
                window_end = min(end, window_start + _number(window.get("duration_sec")))
                if window_end <= window_start:
                    continue
                override = window.get(field_name)
                if not isinstance(override, dict):
                    continue
                asset_id = str(override.get("asset_id") or "").strip()
                asset_uri = str(override.get("asset_uri") or "").strip()
                if not asset_id and not asset_uri:
                    continue
                placed.append(PlacedClip(
                    # `composition_plan.py`의 클립 이름과 같은 규칙이다 --
                    # Phase 4에서 맞대 볼 때 이름으로 짝지을 수 있어야 한다.
                    clip_id=f"session-{kind}-{segment_id}-{window_index}",
                    track_id=track_id,
                    kind=kind,
                    # 주소만 있고 이름이 없는 선택도 렌더는 받아 준다.
                    asset_id=asset_id or asset_uri,
                    start_sec=window_start,
                    end_sec=window_end,
                    source_segment_id=segment_id or None,
                    asset_uri=asset_uri or None,
                    media_controls=dict(override.get("media_controls") or {}),
                    expected_content_sha256=str(override.get("expected_content_sha256") or "") or None,
                    media_revision=str(override.get("media_revision") or "") or None,
                    source_action_id=str(override.get("source_action_id") or "") or None,
                ))
    return placed


def build_track_registry_snapshot(
    session: Mapping[str, Any],
) -> tuple[list[Track], list[PlacedClip]]:
    """세션 하나를 Phase 1+2 모델로 **읽어만** 낸 한 쌍.

    Phase 4·5·6·7이 실제로 부를 자리다. 트랙과 클립을 따로 만들면 서로 안
    맞는 짝이 생기는데, 그건 렌더를 갈아탄 뒤에야 드러난다 -- 그래서 한 번에
    만든다. 여기서도 아무것도 안 고친다.
    """
    from videobox_core_engine.editing_session import FIXED_TIMELINE_TRACK_ROLES
    from videobox_core_engine.track_registry import migrate_legacy_tracks_to_registry

    tracks = migrate_legacy_tracks_to_registry(FIXED_TIMELINE_TRACK_ROLES)
    raw_segments = session.get("segments")
    segments = [item for item in raw_segments if isinstance(item, dict)] if isinstance(raw_segments, list) else []
    return tracks, migrate_segment_media_to_placed_clips(segments=segments, tracks=tracks)


__all__ = [
    "ClipPlacementError",
    "PlacedClip",
    "SEGMENT_MEDIA_FIELD_BY_KIND",
    "VALID_CLIP_PLACEMENT_KINDS",
    "build_track_registry_snapshot",
    "migrate_segment_media_to_placed_clips",
    "validate_placed_clips",
]
