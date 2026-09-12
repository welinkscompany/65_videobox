"""Pure operations for linked output variants.

This module deliberately has no store, renderer, filesystem, network, or
process dependency.  It only interprets immutable models and plain segment
records, leaving approval and materialization persistence to later layers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass

from videobox_domain_models.output_variants import (
    OutputVariant,
    VariantConflict,
    VariantLock,
    VariantOverride,
)


class VariantInvariantError(ValueError):
    """Raised when a variant operation would break its linked invariants."""


_OVERRIDE_FIELDS = frozenset({"crop", "focal", "caption", "safe_area", "audio"})
_STRUCTURAL_FIELDS = frozenset({"story", "segment_order"})
_PATCH_FIELDS = frozenset(
    {"overrides", "lock_fields", "unlock_fields", "selected_segment_ids", "resolve_conflicts"}
)


#: 저장소 행에는 있지만 변형본 모델에는 없는 키. 모델이 `extra="forbid"`라
#: 그냥 넘기면 검증이 깨진다.
_STORE_ONLY_VARIANT_KEYS = frozenset({"project_id", "created_at", "updated_at"})


def output_variant_from_row(row: Mapping[str, object]) -> OutputVariant:
    """저장소가 돌려준 변형본 한 줄을 도메인 모델로 바꾼다. **이 함수가 유일한 자리다.**

    같은 변환이 두 곳에 있었고 한쪽(유진 제안 적용 경로)은 키를 안 걸러
    `extra_forbidden`으로 항상 죽었다 -- 유진이 변형본을 고쳐 주면 화면에는
    "적용하지 못했어요"만 떴다. 이 저장소는 같은 로직이 둘로 갈라져 한쪽만
    고쳐지는 함정에 전에도 걸렸다(`build_variant_timeline_payload` 머리말).
    """
    return OutputVariant.model_validate(
        {key: value for key, value in row.items() if key not in _STORE_ONLY_VARIANT_KEYS}
    )


@dataclass(frozen=True)
class MaterializedVariant:
    source_session_id: str
    source_session_revision: int
    source_variant_id: str
    source_variant_revision: int
    segments: tuple[dict[str, object], ...]


def _segment_id(segment: Mapping[str, object] | object) -> str:
    if isinstance(segment, Mapping):
        value = segment.get("segment_id")
    else:
        value = getattr(segment, "segment_id", None)
    if not isinstance(value, str) or not value.strip():
        raise VariantInvariantError("segment_id_required")
    return value


def _copy_segments(segments: Sequence[Mapping[str, object] | object]) -> tuple[dict[str, object], ...]:
    copied: list[dict[str, object]] = []
    for segment in segments:
        if not isinstance(segment, Mapping):
            raise VariantInvariantError("segments_must_be_mappings")
        copied.append(dict(segment))
    return tuple(copied)


def _check_expected_revision(variant: OutputVariant, expected: int | None) -> None:
    if expected is not None and expected != variant.variant_revision:
        raise VariantInvariantError("stale_variant_revision")


def _merged_overrides(
    current: VariantOverride, patch: Mapping[str, object]
) -> VariantOverride:
    unknown = set(patch) - _OVERRIDE_FIELDS
    if unknown:
        raise VariantInvariantError(f"forbidden_override_fields:{','.join(sorted(unknown))}")
    values = current.model_dump(mode="python")
    for field, value in patch.items():
        if value is not None and not isinstance(value, Mapping):
            raise VariantInvariantError(f"override_must_be_mapping:{field}")
        values[field] = None if value is None else dict(value)
    try:
        return VariantOverride.model_validate(values)
    except ValueError as exc:
        raise VariantInvariantError(str(exc)) from exc


def apply_variant_patch(
    variant: OutputVariant,
    patch: Mapping[str, object],
    *,
    expected_variant_revision: int | None = None,
) -> OutputVariant:
    """Apply only render overrides and, for highlight, segment selection/order."""

    if not isinstance(patch, Mapping):
        raise VariantInvariantError("patch_must_be_mapping")
    _check_expected_revision(variant, expected_variant_revision)
    unknown = set(patch) - _PATCH_FIELDS
    if unknown:
        raise VariantInvariantError(f"forbidden_variant_patch:{','.join(sorted(unknown))}")

    overrides = variant.overrides
    if "overrides" in patch:
        raw_overrides = patch["overrides"]
        if not isinstance(raw_overrides, Mapping):
            raise VariantInvariantError("overrides_must_be_mapping")
        overrides = _merged_overrides(overrides, raw_overrides)

    lock_fields = patch.get("lock_fields", ())
    unlock_fields = patch.get("unlock_fields", ())
    if not isinstance(lock_fields, (list, tuple)) or not isinstance(
        unlock_fields, (list, tuple)
    ):
        raise VariantInvariantError("lock_fields_must_be_lists")
    if any(field not in (*_OVERRIDE_FIELDS, *_STRUCTURAL_FIELDS) for field in (*lock_fields, *unlock_fields)):
        raise VariantInvariantError("invalid_lock_field")
    if set(lock_fields) & set(unlock_fields):
        raise VariantInvariantError("lock_and_unlock_overlap")
    locks_by_field = {lock.field: lock for lock in variant.locks}
    for field in unlock_fields:
        locks_by_field.pop(field, None)
    for field in lock_fields:
        locks_by_field[field] = VariantLock(
            field=field,
            base_master_revision=variant.source_session_revision,
        )

    selected = variant.selected_segment_ids
    if "selected_segment_ids" in patch:
        if variant.kind != "vertical_highlight":
            raise VariantInvariantError("only_vertical_highlight_can_select_segments")
        raw_selected = patch["selected_segment_ids"]
        if not isinstance(raw_selected, (list, tuple)) or not raw_selected:
            raise VariantInvariantError("selected_segment_ids_required")
        selected = tuple(raw_selected)
        if any(not isinstance(item, str) or not item.strip() for item in selected):
            raise VariantInvariantError("invalid_selected_segment_id")
        if len(set(selected)) != len(selected):
            raise VariantInvariantError("duplicate_selected_segment_ids")

    conflicts_by_field = {conflict.field: conflict for conflict in variant.conflicts}
    resolution = patch.get("resolve_conflicts", {})
    if not isinstance(resolution, Mapping):
        raise VariantInvariantError("resolve_conflicts_must_be_mapping")
    for field, decision in resolution.items():
        if field not in conflicts_by_field:
            raise VariantInvariantError(f"unknown_variant_conflict:{field}")
        if decision not in {"keep_local", "rebase_master"}:
            raise VariantInvariantError("invalid_conflict_resolution")
        conflicts_by_field.pop(field, None)
        if decision == "rebase_master":
            locks_by_field.pop(field, None)

    changed = (
        overrides != variant.overrides
        or tuple(locks_by_field.values()) != variant.locks
        or selected != variant.selected_segment_ids
        or tuple(conflicts_by_field.values()) != variant.conflicts
    )
    if not changed:
        return variant
    return variant.model_copy(
        update={
            "overrides": overrides,
            "locks": tuple(locks_by_field.values()),
            "conflicts": tuple(conflicts_by_field.values()),
            "selected_segment_ids": selected,
            "variant_revision": variant.variant_revision + 1,
        }
    )


def rebase_variant(
    variant: OutputVariant,
    *,
    new_master_revision: int,
    changed_fields: Sequence[str],
) -> OutputVariant:
    """Move a variant to a newer master revision and retain conflicts explicitly."""

    if new_master_revision <= variant.source_session_revision:
        raise VariantInvariantError("master_revision_must_advance")
    unknown = set(changed_fields) - (_OVERRIDE_FIELDS | _STRUCTURAL_FIELDS)
    if unknown:
        raise VariantInvariantError(f"unknown_master_change:{','.join(sorted(unknown))}")

    overridden = {
        name
        for name, value in variant.overrides.model_dump(mode="python").items()
        if value is not None
    }
    locked = {lock.field for lock in variant.locks}
    conflicts: list[VariantConflict] = list(variant.conflicts)
    for field in dict.fromkeys(changed_fields):
        if field in _STRUCTURAL_FIELDS or field in overridden or field in locked:
            reason = (
                "master_changed_while_locked"
                if field in locked or field in _STRUCTURAL_FIELDS
                else "master_changed_while_overridden"
            )
            conflicts.append(
                VariantConflict(
                    field=field,  # type: ignore[arg-type]
                    base_master_revision=variant.source_session_revision,
                    current_master_revision=new_master_revision,
                    reason=reason,
                )
            )
    return variant.model_copy(
        update={
            "source_session_revision": new_master_revision,
            "variant_revision": variant.variant_revision + 1,
            "conflicts": tuple(conflicts),
        }
    )


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _retimed_from_zero(
    segments: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """장면들을 0초부터 빈틈 없이 이어 붙인다. **길이는 하나도 안 바꾼다.**

    장면에 **절대 시각**을 들고 있는 칸은 `start_sec`·`end_sec` 둘뿐이다.
    나머지 시간 칸은 전부 상대값이라 장면을 옮겨도 그대로 따라온다:

    - `source_offset_sec`·`source_slices[].source_offset_sec`/`duration_sec`,
      `source_slice_window_start_sec` -- **원본 소재 안의 좌표**다. 옮기면
      다른 장면이 나온다.
    - `media_windows[].start_offset_sec`·`content_windows[].start_offset_sec`와
      그 `duration_sec` -- **장면 시작으로부터의 상대값**이다(B-roll·음악·
      효과음 교체 구간, 자막·오버레이 구간). `materialize_editing_session_timeline`이
      `start + start_offset_sec`로 다시 놓으므로 저절로 따라온다.
    - `transition_in`의 길이 -- 경계에 붙는 값이라 절대 시각이 아니다.

    그래서 `reorder_segments`(사람이 장면을 끌어 옮길 때 쓰는 길)도 여기와
    똑같이 bounds 둘만 다시 쓴다.
    """
    retimed: list[dict[str, object]] = []
    cursor = 0.0
    for segment in segments:
        moved = dict(segment)
        if "start_sec" not in moved or "end_sec" not in moved:
            # 자리를 안 밝힌 장면에 자리를 지어내지 않는다(시간 없는 fixture 등).
            retimed.append(moved)
            continue
        duration = max(0.0, _number(segment.get("end_sec")) - _number(segment.get("start_sec")))
        moved["start_sec"] = cursor
        moved["end_sec"] = cursor + duration
        cursor += duration
        retimed.append(moved)
    return tuple(retimed)


def materialize_variant(
    variant: OutputVariant,
    master_segments: Sequence[Mapping[str, object] | object],
    *,
    master_session_revision: int | None = None,
) -> MaterializedVariant:
    """Return a derived, identity-bearing segment view without mutating the master."""

    if variant.conflicts:
        raise VariantInvariantError("unresolved_variant_conflicts")
    if (
        master_session_revision is not None
        and master_session_revision != variant.source_session_revision
    ):
        raise VariantInvariantError("stale_master_revision")
    segments = _copy_segments(master_segments)
    ids = tuple(_segment_id(segment) for segment in segments)
    if len(set(ids)) != len(ids):
        raise VariantInvariantError("duplicate_master_segment_id")

    if variant.master_segment_ids is not None and variant.kind == "vertical_full":
        if ids != variant.master_segment_ids:
            raise VariantInvariantError("vertical_full_segment_order_or_membership_changed")

    if variant.kind == "vertical_highlight":
        if variant.selected_segment_ids is None:
            # **조용히 원본 전체 길이로 내보내지 않는다.** 옛 변형본 행은 이 칸이
            # 비어 있고, 예전에는 그럴 때 마스터를 그대로 써서 "숏폼"이 원본과
            # 같은 길이로 나왔다 -- 그리고 아무도 그 사실을 말하지 않았다.
            # 빈 판(장면 0개)은 속일 것이 없으니 그대로 통과시킨다.
            if segments:
                raise VariantInvariantError("vertical_highlight_missing_selected_segments")
        else:
            by_id = {segment_id: segment for segment_id, segment in zip(ids, segments)}
            missing = set(variant.selected_segment_ids) - set(by_id)
            if missing:
                raise VariantInvariantError("selected_segment_not_in_master")
            segments = tuple(by_id[segment_id] for segment_id in variant.selected_segment_ids)
            # **뺀 장면에는 자리를 내주지 않는다.** `composition_plan`이
            # `cut_action="remove"` 클립을 버리므로, 자리만 내주면 그 길이만큼
            # 숏폼 한가운데에 죽은 시간이 생긴다. 고르는 쪽에서도 막지만
            # (`short_form_scene_pick`), 채팅으로 고른 목록과 옛 변형본 행은
            # 그 문을 지나지 않는다 -- 구멍이 실제로 생기는 자리는 여기다.
            playable = tuple(
                segment
                for segment in segments
                if str(segment.get("cut_action") or "keep") != "remove"
            )
            if not playable:
                raise VariantInvariantError("short_form_has_no_playable_segment")
            segments = playable
        # **고른 장면만 남기고 끝이 아니다 -- 앞으로 당겨 이어 붙여야 한다.**
        #
        # 2026-09-11 실물 측정(project-e6c75c36): 유진이 3장면 중 2개를 골랐는데
        # 나온 mp4가 **15.000초, 완성본과 똑같았다.** 고른 장면이 원본 좌표
        # (5->10, 10->15)를 그대로 들고 있어서 0->5가 비었고, 그 빈 자리를
        # **버린 도입부가 그대로 채우고 있었다**(픽셀로 확인). 안 짧아진 숏폼은
        # 숏폼이 아니다.
        #
        # 여기서 하는 이유: 이 함수가 "이 변형본의 장면은 무엇인가"를 정하는
        # 유일한 자리이고, 그 목록이 payload(`build_variant_timeline_payload`)와
        # 렌더 세션(`variant_render_session`)으로 그대로 흘러간다. 조립 쪽이나
        # 합성 계획 쪽에서 당기면 장면에 붙은 것들(자막·B-roll·음악·효과음·
        # 오버레이)을 옮기는 로직을 한 벌 더 짓게 된다 -- 그 일은 이미
        # `materialize_editing_session_timeline`이 장면의 `start_sec` 하나로 한다.
        segments = _retimed_from_zero(segments)

    return MaterializedVariant(
        source_session_id=variant.source_session_id,
        source_session_revision=variant.source_session_revision,
        source_variant_id=variant.variant_id,
        source_variant_revision=variant.variant_revision,
        segments=segments,
    )


#: 변형본이 쓸 캔버스 크기. `local_pipeline._ORIENTATION_OUTPUT_SIZES`와 같은
#: 값이며, 그쪽은 `build_timeline`의 `orientation` 이름(`landscape`/`vertical`)을
#: 쓰고 여기는 변형본의 `kind`를 쓴다.
_VARIANT_OUTPUT_SIZES: dict[str, dict[str, int]] = {
    "horizontal": {"width": 1920, "height": 1080},
    "vertical_full": {"width": 1080, "height": 1920},
    "vertical_highlight": {"width": 1080, "height": 1920},
}

#: 마스터 타임라인에서 **베끼면 안 되는** 키.
#:
#: `output`(캔버스 크기)과 `output_mode`가 여기 있는 이유는 2026-09-11에 실물에서
#: 잡힌 결함 때문이다 -- 마스터를 통째로 베끼는 바람에 세로 변형본이 마스터와
#: 같은 1920×1080으로 렌더됐고(완성본·가로·세로 md5가 전부 같았다),
#: `output_mode`는 payload 쪽이 `save_timeline_run`의 인자를 덮어 늘 `review`로
#: 저장됐다.
_MASTER_ONLY_TIMELINE_KEYS = frozenset(
    {"timeline_id", "project_id", "file_uri", "created_at", "summary", "output", "output_mode"}
)

#: 세로 변형본 두 종류. 가로(`horizontal`)는 마스터와 캔버스 비율이 같으므로
#: 여기서 건드릴 이유가 없다.
_VERTICAL_VARIANT_KINDS = frozenset({"vertical_full", "vertical_highlight"})


def _filled_broll_controls(raw_controls: object) -> dict[str, object]:
    """화면 채우기로 고친 `media_controls` 사본. 채우기 판단은 **여기 한 곳**이다."""
    controls = dict(raw_controls) if isinstance(raw_controls, dict) else {}
    controls["fit"] = "crop"
    return controls


def _is_vertical_output(timeline: Mapping[str, object]) -> bool:
    """이 타임라인의 캔버스가 세로인가.

    `variant_render_session`은 변형본의 `kind`를 받지 않는다 -- 렌더가 들고 오는
    것은 타임라인뿐이다. 그 타임라인의 `output`은 `build_variant_timeline_payload`가
    변형본 종류에 맞춰 박아 넣은 값이므로(마스터 값은 `_MASTER_ONLY_TIMELINE_KEYS`가
    막는다) 여기서 세로인지 가로인지 읽을 수 있다.
    """
    output = timeline.get("output")
    if not isinstance(output, Mapping):
        return False
    try:
        return int(output["height"]) > int(output["width"])
    except (KeyError, TypeError, ValueError):
        return False


def _fill_frame_for_vertical_session(session: dict[str, object]) -> dict[str, object]:
    """세로 변형본의 **세션 선택 b-roll**도 화면을 채우게 한다.

    2026-09-12 대표님 실제 영상 실측에서 `_fill_frame_for_vertical_variant`(아래)를
    통과하고도 숏폼의 68.3%가 검은 띠였다. 이유: 그 함수는 **마스터 타임라인의
    트랙 클립**만 고친다. 그런데 자료실 영상을 장면에 까는 화면 경로는 트랙이
    아니라 편집 세션의 `broll_override`이고, 그 클립은 렌더 때
    `materialize_editing_session_timeline`이 **payload를 만든 뒤에** 만들어낸다 --
    고쳐 놓은 트랙 목록을 아예 안 지나간다. 대표님 편집본은 트랙이 비어 있었으므로
    화면 전체가 이 경로였다.

    그래서 렌더용 세션을 만드는 **한 자리**(`variant_render_session`)에서 같이
    고친다. 직접 선택과 창 선택 둘 다 본다 -- 렌더는 직접 선택을 먼저 읽고,
    합친 장면은 창에 권한이 있다.
    """
    segments = session.get("segments")
    if not isinstance(segments, list):
        return session
    filled: list[object] = []
    for segment in segments:
        if not isinstance(segment, dict):
            filled.append(segment)
            continue
        updated = dict(segment)
        override = updated.get("broll_override")
        if isinstance(override, dict):
            updated["broll_override"] = {**override, "media_controls": _filled_broll_controls(override.get("media_controls"))}
        for key in ("media_windows", "media_window_basis"):
            windows = updated.get(key)
            if not isinstance(windows, list):
                continue
            updated[key] = [
                {**window, "broll_override": {
                    **window["broll_override"],
                    "media_controls": _filled_broll_controls(window["broll_override"].get("media_controls")),
                }}
                if isinstance(window, dict) and isinstance(window.get("broll_override"), dict)
                else window
                for window in windows
            ]
        filled.append(updated)
    return {**session, "segments": filled}


def _fill_frame_for_vertical_variant(
    raw_tracks: object, *, variant_kind: str
) -> list[dict[str, object]]:
    """세로 변형본의 화면 클립은 **기본이 화면 채우기(crop)여야 한다.**

    2026-09-11 실측(`task-2-brief`): 마스터는 가로 캔버스에서 만들어졌고, 화면
    맞춤(`media_controls.fit`)의 기본값은 `fit`(=패딩)이다. 그 값을 그대로
    베끼면 1920×1080 원본을 1080×1920에 `scale=decrease,pad`로 넣게 되고,
    실측으로 위아래 68%가 검은 띠였다 -- 세로 영상으로 못 쓴다.

    변형본에는 `overrides.crop`·`overrides.focal`(`output_variants.py`
    domain model)이 있어 나중에 창작자가 자를 자리·중심을 직접 고를 수
    있지만, **지금은 그 둘을 넣는 화면이 없다.** 그래서 "안 고른 기본값"이
    실제로 owner가 보는 유일한 경우이고, 그 기본값이 화면 채우기여야 한다 --
    캡컷 같은 세로 변환 도구들도 기본은 잘라서 채우기다. `overrides.crop`에
    실제 화면이 생기면, 거기서 고른 자르는 위치·초점을 여기 대신(또는
    함께) 넣어야 한다 -- 지금은 클립마다 다른 자르는 위치를 표현할 수단이
    없어 넣지 않는다.

    마스터가 이미 명시적으로 `crop`을 골랐어도 다시 쓰는 것은 안전하다
    (같은 값). `fit`을 일부러 고른 경우(패딩을 원한 경우)까지는 구분하지
    않는다 -- 저장된 값만으로는 "창작자가 골랐다"와 "기본값이라 안 보였다"를
    구분할 수 없고, 세로 변환의 기본 기대는 채우기 쪽이다.
    """
    tracks = deepcopy(raw_tracks) if isinstance(raw_tracks, list) else []
    if variant_kind not in _VERTICAL_VARIANT_KINDS:
        return tracks
    for track in tracks:
        if not isinstance(track, dict):
            continue
        if str(track.get("track_type") or "").strip().lower() != "broll":
            continue
        clips = track.get("clips")
        if not isinstance(clips, list):
            continue
        for clip in clips:
            if not isinstance(clip, dict):
                continue
            clip["media_controls"] = _filled_broll_controls(clip.get("media_controls"))
    return tracks


def build_variant_timeline_payload(
    *,
    master_timeline: Mapping[str, object],
    variant_kind: str,
    derived: MaterializedVariant,
) -> dict[str, object]:
    """변형본 타임라인의 payload를 만든다. **이 함수가 유일한 자리다.**

    변형본을 만드는 입구가 둘이다 -- 출력 화면의 `가로·세로 출력 만들기`
    (`local_pipeline._materialize_variant_for_output`)와 편집기의 `가로·세로 비교`
    준비(`routers/output_variants.materialize_variant_route`). 둘이 같은 복사
    로직을 따로 들고 있었고, 2026-09-11에 크기 결함을 한쪽만 고쳤다가 **다른
    쪽이 먼저 돌면 틀린 타임라인이 캐시되어 고친 것이 건너뛰어지는** 상태가
    됐다(`save_variant_materialization`을 나중 호출자가 재사용한다).

    이 저장소는 같은 함정에 전에도 걸렸다 -- 렌더 경로가 둘이라 필터를 한 곳만
    고쳤던 일이 있다. 그래서 두 입구가 이 함수를 부르게 묶는다.
    """
    payload: dict[str, object] = {
        key: value
        for key, value in master_timeline.items()
        if key not in _MASTER_ONLY_TIMELINE_KEYS
    }
    payload.update(
        {
            "output": dict(_VARIANT_OUTPUT_SIZES[variant_kind]),
            "source_variant_id": derived.source_variant_id,
            "source_variant_revision": derived.source_variant_revision,
            "source_session_id": derived.source_session_id,
            "source_session_revision": derived.source_session_revision,
            "segments": list(derived.segments),
            "tracks": _fill_frame_for_vertical_variant(
                master_timeline.get("tracks", []), variant_kind=variant_kind
            ),
        }
    )
    return payload


def variant_render_session(
    *,
    master_session: Mapping[str, object] | None,
    variant_timeline: Mapping[str, object],
) -> dict[str, object] | None:
    """변형본 타임라인을 렌더할 때 쓸 편집 세션.

    두 가지를 한다: 장면 목록을 변형본에 맞춰 **투영**하고(아래 본문),
    세로 캔버스면 세션 선택 b-roll을 **화면 채우기**로 바꾼다
    (`_fill_frame_for_vertical_session`). 후자는 전체본(`vertical_full`)에도
    걸려야 한다 -- 투영이 아무것도 안 바꾸는 경우에도 검은 띠는 생긴다.
    """
    projected = _projected_variant_session(
        master_session=master_session, variant_timeline=variant_timeline
    )
    if projected is None or not _is_vertical_output(variant_timeline):
        return projected
    return _fill_frame_for_vertical_session(projected)


def _projected_variant_session(
    *,
    master_session: Mapping[str, object] | None,
    variant_timeline: Mapping[str, object],
) -> dict[str, object] | None:
    """변형본 타임라인을 렌더할 때 쓸 편집 세션. **마스터를 그대로 쓰면 안 된다.**

    2026-09-11 실물 측정에서 숏폼이 완성본과 똑같은 15초로 나온 진짜 원인이
    여기다. 렌더는 변형본 타임라인을 **마스터 편집 세션으로 다시 반영해서**
    (`run_final_render_job` -> `materialize_editing_session_timeline`) 화면
    클립과 자막을 만드는데, 그 세션에는 **버린 장면이 그대로 있다.** 그래서
    고른 장면은 마스터 좌표로 되돌려지고 버린 장면은 자기 자리에 그대로
    남는다 -- `payload["segments"]`(고른 장면 목록)를 렌더 경로에서 읽는 곳이
    한 곳도 없었다. 목록을 적는 것과 결과가 그렇게 되는 것은 다른 주장이다.

    그래서 마스터 세션을 이 변형본의 장면 목록에 맞춰 **투영**한다:

    - 고른 장면: 변형본이 정한 자리(`start_sec`/`end_sec`)로 옮긴다.
    - 안 고른 장면: `cut_action="remove"`로 표시한다.

    새 기계를 만들지 않고 **편집기의 `장면 빼기`가 이미 쓰는 길**을 그대로
    쓴다. 그 길이 장면 하나를 뺄 때 거기 붙은 것(자막·B-roll·음악·효과음·
    오버레이·빈 구간·전환)을 같이 빼고, 남은 장면의 `start_sec`로 전부 다시
    놓는 일을 이미 한다.

    **전체본(`vertical_full`)은 여기 안 걸린다.** 전체본의 장면 목록은 마스터와
    구성·순서·시각이 전부 같고(`materialize_variant`가 다르면 거부한다),
    그러면 아래 대조에서 바뀐 것이 하나도 없어 마스터 세션을 **그대로**
    돌려준다 -- 같은 이야기, 다른 화면비라는 뜻이 유지된다.
    """
    if not isinstance(master_session, Mapping):
        return None
    raw_variant_segments = variant_timeline.get("segments")
    if not isinstance(raw_variant_segments, list) or not raw_variant_segments:
        return dict(master_session)
    bounds_by_id: dict[str, tuple[float, float]] = {}
    order: list[str] = []
    for segment in raw_variant_segments:
        if not isinstance(segment, Mapping):
            return dict(master_session)
        segment_id = str(segment.get("segment_id") or "").strip()
        if not segment_id:
            return dict(master_session)
        bounds_by_id[segment_id] = (_number(segment.get("start_sec")), _number(segment.get("end_sec")))
        order.append(segment_id)

    master_segments = master_session.get("segments")
    if not isinstance(master_segments, list) or not master_segments:
        return dict(master_session)
    by_id: dict[str, Mapping[str, object]] = {}
    for segment in master_segments:
        if not isinstance(segment, Mapping):
            return dict(master_session)
        segment_id = str(segment.get("segment_id") or "").strip()
        if not segment_id or segment_id in by_id:
            return dict(master_session)
        by_id[segment_id] = segment
    if any(segment_id not in by_id for segment_id in bounds_by_id):
        return dict(master_session)

    changed = False
    kept: list[dict[str, object]] = []
    for segment_id in order:
        source = deepcopy(dict(by_id[segment_id]))
        start, end = bounds_by_id[segment_id]
        if _number(source.get("start_sec")) != start or _number(source.get("end_sec")) != end:
            changed = True
        source["start_sec"] = start
        source["end_sec"] = end
        kept.append(source)
    dropped: list[dict[str, object]] = []
    for segment_id, segment in by_id.items():
        if segment_id in bounds_by_id:
            continue
        changed = True
        dropped.append({**deepcopy(dict(segment)), "cut_action": "remove"})
    if not changed:
        return dict(master_session)
    projected = dict(master_session)
    projected["segments"] = [*kept, *dropped]
    # 손으로 끌어다 놓은 자리(`timeline_placement_overrides`)는 **마스터 좌표의
    # 절대 시각**이고 클립 이름으로 걸린다. 짧아진 판에서는 그 자리가 더 이상
    # 없다 -- 버린 장면의 클립을 가리키는 항목은 `timeline_placement_unknown`으로
    # 렌더를 통째로 죽이고, 남은 클립을 가리키는 항목은 당겨 놓은 클립을 도로
    # 마스터 자리로 되돌린다. 파생본에서는 걷어 낸다. 마스터 편집본의 값은
    # 그대로 남아 있다.
    projected.pop("timeline_placement_overrides", None)
    return projected


#: 펼치면 원본과의 줄이 끊긴다는 **규칙 한 문장.** 화면과 유진 안내문이 같은
#: 문장을 쓰게 여기 한 곳에 둔다 -- 두 곳에 적으면 한쪽만 고쳐진다.
UNFOLD_INDEPENDENCE_RULE = "펼치면 독립된 편집본이 되고, 그 뒤 원본을 고쳐도 따라오지 않아요."

#: 펼친 편집본이 원본에서 **그대로 가져오는** 칸. 여기 없는 것은 새로 시작한다.
#:
#: `history`·`undo_stack`·`redo_stack`이 빠져 있는 것이 이 목록의 요점이다 --
#: 되돌리기는 세션 안에만 있으므로(`editing_transactions.apply_user_transaction`),
#: 비워서 시작하면 펼친 판의 되돌리기가 원본 이력과 섞이지 않는다. 원본에서
#: `Ctrl+Z`를 눌러도 펼친 판은 움직이지 않고, 그 반대도 같다.
#:
#: `timeline_placement_overrides`도 빠져 있다 -- `_projected_variant_session`이
#: 이미 걷어 낸다(마스터 절대 시각이라 짧아진 판에서는 그 자리가 없다).
_UNFOLD_CARRIED_SESSION_KEYS = (
    "caption_style",
    "caption_language",
    # 자유 멀티트랙의 트랙 목록과 눈·음소거 상태. **지금 숏폼 렌더가 쓰는 값을
    # 그대로 가져온다**(`variant_render_session`은 마스터의 이 둘을 손대지 않는다).
    # 펼치기는 그릇을 옮기는 일이라 결과가 바뀌면 안 되므로, 값 판단을 여기서
    # 새로 하지 않는다.
    "tracks",
    "track_states",
)


def unfolded_short_form_session(
    *,
    master_session: Mapping[str, object] | None,
    variant_timeline: Mapping[str, object],
    project_id: str,
    timeline_id: str,
) -> dict[str, object]:
    """숏폼을 **독립된 편집본**으로 펼친다. 원본 세션은 손대지 않는다.

    왜 장면별 덮어쓰기(`VariantOverride`에 장면 자리를 더하는 길)를 고르지
    않았는가. 덮어쓰기를 더하면 **편집 표면이 두 벌**이 된다 -- 자막·확대·전환·
    효과음·오버레이의 문을 숏폼용으로 한 번 더 만들어야 하고, 유진의 편집 의도
    16개(`yujin_editing_proposal_service`)도 두 경로가 된다. 펼치면 그 전부가
    이미 있는 세션 도구로 그대로 돈다 -- 되돌리기까지.

    **대신 원본과의 줄이 끊긴다**(`UNFOLD_INDEPENDENCE_RULE`). 끊는 것이 맞는
    이유: 파생 기계(`rebase_variant`·`VariantConflict`·`materialize_variant`의
    낡음 검사)는 "마스터가 유일한 진실"을 지키는 장치다. 펼친 판에는 마스터에
    없는 편집이 들어가므로 그 전제가 깨진다. 줄을 남기면 원본을 고칠 때마다
    풀 수 없는 충돌이 쌓이고, 대표님은 숏폼을 고칠 때마다 그 충돌을 봐야 한다.

    투영은 **새로 짜지 않고** `variant_render_session`을 그대로 쓴다 -- 지금
    숏폼을 렌더할 때 쓰는 바로 그 세션이다. 그래서 펼치기 전후의 완성본이 같다.
    """
    projected = variant_render_session(
        master_session=master_session, variant_timeline=variant_timeline
    )
    if projected is None:
        raise VariantInvariantError("unfold_requires_master_session")
    # 버린 장면은 `cut_action="remove"` 표시만 달고 남아 있다(투영이 하는 일).
    # 펼친 판에서는 **아예 뺀다.** 남기면 마스터 절대 시각을 들고 있어서 당겨
    # 놓은 장면과 구간이 겹치고, 다음 편집이 `Segment bounds overlap`으로
    # 죽는다. 합성 계획은 `remove` 클립을 버리므로 결과는 같다.
    segments = [
        segment
        for segment in projected.get("segments", [])  # type: ignore[union-attr]
        if isinstance(segment, Mapping)
        and str(segment.get("cut_action") or "keep") != "remove"
    ]
    if not segments:
        raise VariantInvariantError("unfold_has_no_playable_segment")
    session: dict[str, object] = {
        key: deepcopy(projected[key])
        for key in _UNFOLD_CARRIED_SESSION_KEYS
        if key in projected
    }
    session.update(
        {
            "project_id": project_id,
            "timeline_id": timeline_id,
            "segments": [deepcopy(dict(segment)) for segment in segments],
            "history": [],
            "undo_stack": [],
            "redo_stack": [],
            "session_revision": 1,
        }
    )
    return session


def variant_timeline_needs_rebuild(
    *,
    cached_timeline: Mapping[str, object] | None,
    fresh_payload: Mapping[str, object],
) -> bool:
    """캐시된 변형본 타임라인이 **지금** `build_variant_timeline_payload`가 만드는
    값과 같은지 본다. 다르면(또는 캐시가 아예 없으면) 다시 만들어야 한다.

    2026-09-11에 실물로 잡힌 결함: `source_variant_revision`이 같으면 캐시를
    무조건 재사용했다. 그런데 그 캐시는 **조립 로직이 바뀌기 전에** 만들어진
    타임라인이었다 -- 세로 변형본을 다시 만들어도 옛 1920x1080 타임라인을 계속
    물고 나왔다(대표님이 `가로·세로 출력 만들기`를 눌러도 안 고쳐지는 걸로
    보였다).

    "스키마 버전 번호"를 따로 관리하는 대신, **이 함수가 지금 만드는 payload
    전체**를 캐시된 타임라인과 키 단위로 대조한다. 버전 번호 방식은 다음에
    `build_variant_timeline_payload`를 고치는 사람이 번호 올리는 걸 잊으면
    조용히 다시 새는데, 이 방식은 그 사람이 번호를 신경 쓸 필요가 없다 --
    payload가 만드는 값(`output`·`tracks`·`segments`·식별자 전부)이 뭐든
    바뀌면 대조에서 자동으로 걸린다. 대가는 매 materialize 호출마다 마스터
    타임라인을 한 번 더 읽고 payload를 다시 조립하는 것뿐이고, 둘 다 순수
    계산이라 싸다. 비싼 부분(`save_timeline_run`으로 새 타임라인 행을 쓰는 것,
    타임라인 빌드 job을 새로 만드는 것)은 여기서 같다고 판정될 때 그대로
    건너뛴다 -- caching의 실제 값은 그쪽에 있다.
    """
    if cached_timeline is None:
        return True
    return any(cached_timeline.get(key) != value for key, value in fresh_payload.items())
