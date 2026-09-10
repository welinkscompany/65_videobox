"""자유 멀티트랙의 첫 조각 -- 트랙을 "고정 이름 다섯 개"가 아니라 목록으로 다룬다.

`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §3 Phase 1.
**아직 아무도 이 모델을 안 읽는다** -- 완전히 덧붙이기만 하는 단계다. 기존
`editing_session.py`의 `FIXED_TIMELINE_TRACK_ROLES`(다섯 고정 역할)와
`composition_plan.py`의 렌더 경로는 이 파일이 생겨도 그대로 돈다.

**타이밍 기준 설계** (§3의 핵심 결정): 내레이션 트랙이 여러 개가 되면
"무엇이 세그먼트 시간을 정하는 기준인가"를 명시적으로 표시해야 한다 --
만든 순서로 암묵적으로 정하면(옵션 A, 계획서에서 기각) 트랙을 지우거나
순서를 바꿀 때 기준이 조용히 바뀐다. `is_timing_anchor` 하나만 true일 수
있다. 자막 트랙의 `source_track_id`는 어느 내레이션의 글을 옮기는지
가리키는데, **지금 마이그레이션 대상(다섯 고정 역할)에는 자막이 트랙으로
없다**(자막은 `segment.caption_text` 필드다, `composition_plan.py`가
따로 다룬다) -- 그래서 필드는 만들어 두되 이번 마이그레이션은 안 채운다.
"""

from __future__ import annotations

from dataclasses import dataclass

#: 지금까지 렌더·세션이 실제로 아는 트랙 종류. `canonical_track.py`(4개, 내보내기
#: 대상만)보다 넓고 `track_states.py`(6개, caption·overlay 포함)와 같다 --
#: 트랙 레지스트리는 "화면에 줄로 보이는 것" 전부를 다뤄야 하기 때문이다.
VALID_TRACK_KINDS = frozenset({"narration", "broll", "bgm", "sfx", "overlay", "caption"})


class TrackRegistryError(ValueError):
    """트랙 목록 자체가 앞뒤가 안 맞을 때(기준 둘·순서 중복 등)."""


@dataclass(frozen=True, slots=True)
class Track:
    track_id: str
    label: str
    kind: str
    order: int
    is_timing_anchor: bool = False
    source_track_id: str | None = None

    def __post_init__(self) -> None:
        if not self.track_id or not self.track_id.strip():
            raise TrackRegistryError("track_registry_track_id_required")
        if self.kind not in VALID_TRACK_KINDS:
            raise TrackRegistryError("track_registry_kind_unsupported")
        if self.is_timing_anchor and self.kind != "narration":
            raise TrackRegistryError("track_registry_anchor_must_be_narration")
        if self.source_track_id is not None and self.kind != "caption":
            raise TrackRegistryError("track_registry_source_track_only_for_caption")


def validate_tracks(tracks: list[Track]) -> None:
    """트랙 목록 전체의 앞뒤가 맞는지 -- 개별 트랙이 아니라 관계를 본다."""
    if len({t.track_id for t in tracks}) != len(tracks):
        raise TrackRegistryError("track_registry_duplicate_track_id")
    if len({t.order for t in tracks}) != len(tracks):
        raise TrackRegistryError("track_registry_duplicate_order")

    narration_tracks = [t for t in tracks if t.kind == "narration"]
    anchors = [t for t in narration_tracks if t.is_timing_anchor]
    if narration_tracks and len(anchors) != 1:
        # 내레이션 트랙이 있는데 기준이 0개거나 2개 이상이면 앞뒤가 안 맞는다.
        # 내레이션 트랙 자체가 없는 세션(예: 대본만 있는 초안)은 아직 기준을
        # 못 정하는 게 정상이라 여기 안 걸린다.
        raise TrackRegistryError("track_registry_anchor_count_invalid")

    narration_ids = {t.track_id for t in narration_tracks}
    for track in tracks:
        if track.kind == "caption" and track.source_track_id is not None:
            if track.source_track_id not in narration_ids:
                raise TrackRegistryError("track_registry_source_track_missing")


def migrate_legacy_tracks_to_registry(
    legacy_roles: tuple[str, ...],
) -> list[Track]:
    """옛 고정 다섯 역할을 트랙 레지스트리 항목으로 그대로 옮긴다.

    렌더·세션에 아무 영향이 없다 -- 순서(`order`)는 옛 배열 순서 그대로,
    `narration`만 `is_timing_anchor=True`(§3이 정한 기준: 옛 구조는 항상
    내레이션 하나가 세그먼트 시간을 정했으니, 마이그레이션 뒤에도 그 사실은
    그대로 보존돼야 한다).
    """
    tracks = [
        Track(
            track_id=f"track-{role}",
            label=role,
            kind=role,
            order=index,
            is_timing_anchor=(role == "narration"),
        )
        for index, role in enumerate(legacy_roles)
    ]
    validate_tracks(tracks)
    return tracks
