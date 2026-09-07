from __future__ import annotations

import pytest
from pydantic import ValidationError

from videobox_core_engine.output_variants import (
    VariantInvariantError,
    apply_variant_patch,
    materialize_variant,
    rebase_variant,
)
from videobox_domain_models.output_variants import OutputVariant, VariantOverride


def _variant(kind: str = "horizontal") -> OutputVariant:
    return OutputVariant(
        variant_id=f"variant-{kind}",
        kind=kind,
        source_session_id="session-1",
        source_session_revision=7,
        variant_revision=3,
        master_segment_ids=["seg-a", "seg-b", "seg-c"],
    )


def _master_segments() -> list[dict[str, object]]:
    return [
        {"segment_id": "seg-a", "story": "hook"},
        {"segment_id": "seg-b", "story": "proof"},
        {"segment_id": "seg-c", "story": "close"},
    ]


def test_variant_model_is_strict_and_accepts_only_render_overrides() -> None:
    override = VariantOverride(
        crop={"mode": "cover", "aspect_ratio": "9:16"},
        focal={"x": 0.5, "y": 0.25},
        caption={"position": "bottom", "max_lines": 2},
        safe_area={"top": 0.08, "bottom": 0.12},
        audio={"gain_db": -2.0, "mute": False},
    )

    assert override.crop["aspect_ratio"] == "9:16"
    with pytest.raises(ValidationError):
        VariantOverride(story="rewrite")  # type: ignore[call-arg]


@pytest.mark.parametrize("kind", ["horizontal", "vertical_full", "vertical_highlight"])
def test_all_supported_variant_kinds_materialize_with_master_identity(kind: str) -> None:
    variant = _variant(kind)

    materialized = materialize_variant(variant, _master_segments())

    assert materialized.source_session_id == "session-1"
    assert materialized.source_session_revision == 7
    assert materialized.source_variant_id == variant.variant_id
    assert materialized.source_variant_revision == 3
    assert [item["segment_id"] for item in materialized.segments] == [
        "seg-a",
        "seg-b",
        "seg-c",
    ]


def test_vertical_highlight_can_select_and_reorder_master_segments() -> None:
    variant = _variant("vertical_highlight")

    updated = apply_variant_patch(
        variant,
        {"selected_segment_ids": ["seg-c", "seg-a"]},
        expected_variant_revision=3,
    )

    materialized = materialize_variant(updated, _master_segments())
    assert [item["segment_id"] for item in materialized.segments] == ["seg-c", "seg-a"]
    assert updated.variant_revision == 4


@pytest.mark.parametrize("kind", ["horizontal", "vertical_full"])
@pytest.mark.parametrize(
    "patch",
    [
        {"selected_segment_ids": ["seg-b", "seg-a"]},
        {"delete_segment_ids": ["seg-b"]},
        {"reorder_segment_ids": ["seg-c", "seg-a", "seg-b"]},
        {"story": {"seg-a": "rewritten"}},
    ],
)
def test_non_highlight_variants_fail_closed_on_story_or_segment_mutations(
    kind: str, patch: dict[str, object]
) -> None:
    with pytest.raises(VariantInvariantError):
        apply_variant_patch(_variant(kind), patch, expected_variant_revision=3)


def test_vertical_full_never_materializes_a_different_segment_order() -> None:
    variant = _variant("vertical_full")

    with pytest.raises(VariantInvariantError, match="segment_order"):
        materialize_variant(
            variant,
            [
                {"segment_id": "seg-b"},
                {"segment_id": "seg-a"},
                {"segment_id": "seg-c"},
            ],
        )


def test_allowed_overrides_are_revisioned_without_mutating_the_input() -> None:
    variant = _variant("vertical_full")

    updated = apply_variant_patch(
        variant,
        {
            "overrides": {
                "crop": {"mode": "cover"},
                "focal": {"x": 0.4, "y": 0.6},
                "caption": {"position": "top"},
                "safe_area": {"bottom": 0.1},
                "audio": {"gain_db": -1.5},
            }
        },
        expected_variant_revision=3,
    )

    assert updated.variant_revision == 4
    assert updated.overrides.audio == {"gain_db": -1.5}
    assert variant.overrides.audio is None


def test_stale_variant_revision_is_rejected() -> None:
    with pytest.raises(VariantInvariantError, match="stale_variant_revision"):
        apply_variant_patch(
            _variant(),
            {"overrides": {"crop": {"mode": "cover"}}},
            expected_variant_revision=2,
        )


def test_rebase_inherits_locks_and_records_master_conflicts() -> None:
    variant = apply_variant_patch(
        _variant("vertical_full"),
        {
            "overrides": {"crop": {"mode": "cover"}},
            "lock_fields": ["crop", "story"],
        },
        expected_variant_revision=3,
    )

    rebased = rebase_variant(
        variant,
        new_master_revision=8,
        changed_fields=["crop", "story"],
    )

    assert {lock.field for lock in rebased.locks} == {"crop", "story"}
    assert rebased.source_session_revision == 8
    assert rebased.variant_revision == 5
    assert {conflict.field for conflict in rebased.conflicts} == {"crop", "story"}


def test_rebase_rejects_non_forward_master_revision() -> None:
    with pytest.raises(VariantInvariantError, match="master_revision"):
        rebase_variant(_variant(), new_master_revision=7, changed_fields=[])


def test_conflict_resolution_is_explicit_and_preserves_or_releases_lock() -> None:
    variant = rebase_variant(
        apply_variant_patch(
            _variant(),
            {"overrides": {"crop": {"mode": "cover"}}, "lock_fields": ["crop"]},
            expected_variant_revision=3,
        ),
        new_master_revision=8,
        changed_fields=["crop"],
    )

    kept = apply_variant_patch(
        variant,
        {"resolve_conflicts": {"crop": "keep_local"}},
        expected_variant_revision=variant.variant_revision,
    )
    assert kept.conflicts == ()
    assert [lock.field for lock in kept.locks] == ["crop"]

    rebased = apply_variant_patch(
        variant,
        {"resolve_conflicts": {"crop": "rebase_master"}},
        expected_variant_revision=variant.variant_revision,
    )
    assert rebased.conflicts == ()
    assert rebased.locks == ()

    with pytest.raises(VariantInvariantError, match="unknown_variant_conflict"):
        apply_variant_patch(variant, {"resolve_conflicts": {"caption": "keep_local"}}, expected_variant_revision=variant.variant_revision)
    with pytest.raises(VariantInvariantError, match="invalid_conflict_resolution"):
        apply_variant_patch(variant, {"resolve_conflicts": {"crop": "silent"}}, expected_variant_revision=variant.variant_revision)


@pytest.mark.parametrize(
    "segments",
    [
        [{"segment_id": "seg-a"}, {"segment_id": "seg-a"}],
        [{"segment_id": "seg-a"}, {"segment_id": "seg-unknown"}],
    ],
)
def test_highlight_materialization_rejects_duplicate_or_unknown_segment_ids(
    segments: list[dict[str, object]],
) -> None:
    variant = apply_variant_patch(
        _variant("vertical_highlight"),
        {"selected_segment_ids": ["seg-a", "seg-b"]},
        expected_variant_revision=3,
    )

    with pytest.raises(VariantInvariantError):
        materialize_variant(variant, segments)


def test_materialization_rejects_unresolved_master_conflicts() -> None:
    rebased = rebase_variant(
        _variant("horizontal"),
        new_master_revision=8,
        changed_fields=["story"],
    )

    with pytest.raises(VariantInvariantError, match="unresolved_variant_conflicts"):
        materialize_variant(rebased, _master_segments())
