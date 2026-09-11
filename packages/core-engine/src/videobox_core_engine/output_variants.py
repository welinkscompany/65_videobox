"""Pure operations for linked output variants.

This module deliberately has no store, renderer, filesystem, network, or
process dependency.  It only interprets immutable models and plain segment
records, leaving approval and materialization persistence to later layers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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

    if variant.kind == "vertical_highlight" and variant.selected_segment_ids is not None:
        by_id = {segment_id: segment for segment_id, segment in zip(ids, segments)}
        missing = set(variant.selected_segment_ids) - set(by_id)
        if missing:
            raise VariantInvariantError("selected_segment_not_in_master")
        segments = tuple(by_id[segment_id] for segment_id in variant.selected_segment_ids)

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
            "tracks": list(master_timeline.get("tracks", []) or []),
        }
    )
    return payload
