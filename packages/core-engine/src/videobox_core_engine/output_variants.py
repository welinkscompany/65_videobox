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
    {"overrides", "lock_fields", "unlock_fields", "selected_segment_ids"}
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

    changed = (
        overrides != variant.overrides
        or tuple(locks_by_field.values()) != variant.locks
        or selected != variant.selected_segment_ids
    )
    if not changed:
        return variant
    return variant.model_copy(
        update={
            "overrides": overrides,
            "locks": tuple(locks_by_field.values()),
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
