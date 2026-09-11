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
    if kind == "vertical_highlight":
        # 숏폼은 장면 목록 없이는 만들어지지 않는다 -- 목록이 없으면 원본
        # 전체 길이로 조용히 나가기 때문이다. 신원 확인은 목록을 채워서 한다.
        variant = apply_variant_patch(
            variant,
            {"selected_segment_ids": ["seg-a", "seg-b", "seg-c"]},
            expected_variant_revision=3,
        ).model_copy(update={"variant_revision": 3})

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


def test_yujin_short_form_cut_is_undone_by_resending_the_previous_whole_list() -> None:
    """유진 편집은 확인 클릭 없이 바로 적용된다 -- 안전장치는 되돌리기 하나다.

    (`docs/decisions/2026-09-01-yujin-chat-applies-edits-directly.ko.md`)
    그래서 **되돌리기가 깨끗이 되는 모양**으로 장면을 받는다. 통째 목록은
    이전 목록을 그대로 다시 보내면 장면 구성과 **순서까지** 원래대로 돌아온다.
    "이 장면 빼"라는 델타였다면 역연산이 "몇 번째 자리에 다시 넣기"인데 그
    자리 정보가 델타에 없다.
    """
    from videobox_core_engine.yujin_creator_proposal_adapter import (
        variant_patch_from_yujin_candidate,
    )
    from videobox_domain_models.director_proposals import DirectorCandidate

    def _yujin_candidate(segment_ids: list[str]) -> DirectorCandidate:
        return DirectorCandidate(
            candidate_id="yujin-candidate-short",
            visible_reference_code="P01-01",
            media_type="output_variant",
            asset_id="yujin-candidate-short",
            library_asset_id=None,
            reason_chips=("숏폼 장면 고르기",),
            scores={},
            availability="actionable",
            review_status="approved",
            preview_uri=None,
            controls={
                "kind": "output_variant",
                "target": {"variant_id": "variant-vertical_highlight", "track_id": "output-variant"},
                "parameters": {"action": "select_segments", "segment_ids": segment_ids},
                "requires_materialization": False,
                "preview_summary": "숏폼에 넣을 장면 목록",
            },
            expected_content_sha256=None,
            media_revision="session:session-1:revision:7:assets:3",
            canonical_metadata={},
        )

    variant = _variant("vertical_highlight")
    before = variant.selected_segment_ids or tuple(variant.master_segment_ids or ())

    cut = apply_variant_patch(
        variant,
        variant_patch_from_yujin_candidate(_yujin_candidate(["seg-c", "seg-a"])),
        expected_variant_revision=3,
    )
    assert cut.selected_segment_ids == ("seg-c", "seg-a")
    assert [item["segment_id"] for item in materialize_variant(cut, _master_segments()).segments] == [
        "seg-c",
        "seg-a",
    ]

    restored = apply_variant_patch(
        cut,
        {"selected_segment_ids": list(before)},
        expected_variant_revision=cut.variant_revision,
    )

    assert restored.selected_segment_ids == before
    assert [
        item["segment_id"] for item in materialize_variant(restored, _master_segments()).segments
    ] == list(before)
    assert restored.variant_revision == 5


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


def _timed_master_segments() -> list[dict[str, object]]:
    """장면 셋, 마지막 장면 앞에 **일부러 둔 1초 빈 구간**."""
    return [
        {"segment_id": "seg-a", "start_sec": 0.0, "end_sec": 5.0, "source_offset_sec": 0.0},
        {"segment_id": "seg-b", "start_sec": 5.0, "end_sec": 10.0, "source_offset_sec": 0.0},
        {"segment_id": "seg-c", "start_sec": 11.0, "end_sec": 16.0, "source_offset_sec": 0.0},
    ]


def test_short_form_picks_are_pulled_forward_into_one_continuous_clip() -> None:
    """고른 장면을 원본 좌표 그대로 두면 숏폼이 안 짧아진다(2026-09-11 실측).

    길이는 하나도 바뀌지 않고 자리만 앞으로 온다. **원본 좌표
    (`source_offset_sec`)는 손대지 않는다** -- 그걸 옮기면 같은 자리에서
    다른 그림이 나온다.
    """
    variant = apply_variant_patch(
        _variant("vertical_highlight"),
        {"selected_segment_ids": ["seg-b", "seg-c"]},
        expected_variant_revision=3,
    )

    materialized = materialize_variant(variant, _timed_master_segments())

    assert [
        (item["segment_id"], item["start_sec"], item["end_sec"]) for item in materialized.segments
    ] == [("seg-b", 0.0, 5.0), ("seg-c", 5.0, 10.0)]
    assert all(item["source_offset_sec"] == 0.0 for item in materialized.segments)


def test_reordered_short_form_picks_are_laid_out_in_the_chosen_order() -> None:
    variant = apply_variant_patch(
        _variant("vertical_highlight"),
        {"selected_segment_ids": ["seg-c", "seg-a"]},
        expected_variant_revision=3,
    )

    materialized = materialize_variant(variant, _timed_master_segments())

    assert [
        (item["segment_id"], item["start_sec"], item["end_sec"]) for item in materialized.segments
    ] == [("seg-c", 0.0, 5.0), ("seg-a", 5.0, 10.0)]


def test_a_scene_the_owner_cut_never_takes_time_in_the_short_form() -> None:
    """뺀 장면이 목록에 들어와도 **자리를 내주지 않는다.**

    `composition_plan`이 `cut_action="remove"` 클립을 버리므로, 자리만 내주면
    그 길이만큼 숏폼 한가운데에 죽은 시간이 생긴다.
    """
    master = [
        {"segment_id": "seg-a", "start_sec": 0.0, "end_sec": 5.0},
        {"segment_id": "seg-b", "start_sec": 5.0, "end_sec": 10.0, "cut_action": "remove"},
        {"segment_id": "seg-c", "start_sec": 10.0, "end_sec": 15.0},
    ]
    variant = apply_variant_patch(
        _variant("vertical_highlight"),
        {"selected_segment_ids": ["seg-a", "seg-b", "seg-c"]},
        expected_variant_revision=3,
    )

    materialized = materialize_variant(variant, master)

    assert [
        (item["segment_id"], item["start_sec"], item["end_sec"]) for item in materialized.segments
    ] == [("seg-a", 0.0, 5.0), ("seg-c", 5.0, 10.0)]


def test_a_short_form_with_no_scene_list_is_refused_instead_of_running_full_length() -> None:
    """장면 목록이 없는 숏폼은 **조용히 원본 전체 길이로 나가면 안 된다.**

    옛 변형본 행은 `selected_segment_ids`가 비어 있다. 그대로 두면 "숏폼"이
    원본과 같은 길이로 나오고 아무도 그 사실을 말하지 않는다.
    """
    with pytest.raises(VariantInvariantError, match="vertical_highlight_missing_selected_segments"):
        materialize_variant(_variant("vertical_highlight"), _master_segments())


def test_a_short_form_whose_every_picked_scene_was_cut_is_refused() -> None:
    master = [{"segment_id": "seg-a", "start_sec": 0.0, "end_sec": 5.0, "cut_action": "remove"}]
    variant = apply_variant_patch(
        OutputVariant(
            variant_id="variant-short",
            kind="vertical_highlight",
            source_session_id="session-1",
            source_session_revision=7,
            variant_revision=3,
            master_segment_ids=["seg-a"],
        ),
        {"selected_segment_ids": ["seg-a"]},
        expected_variant_revision=3,
    )

    with pytest.raises(VariantInvariantError, match="short_form_has_no_playable_segment"):
        materialize_variant(variant, master)


@pytest.mark.parametrize("kind", ["horizontal", "vertical_full"])
def test_full_length_variants_keep_every_master_time_including_gaps(kind: str) -> None:
    """전체본은 **당겨 붙이지 않는다** -- 같은 이야기, 다른 화면비다.

    빈 구간까지 마스터와 같아야 한다. 당겨 붙이면 11초에서 시작하던 마지막
    장면이 10초로 와서 마스터와 다른 이야기가 된다.
    """
    materialized = materialize_variant(_variant(kind), _timed_master_segments())

    assert [
        (item["segment_id"], item["start_sec"], item["end_sec"]) for item in materialized.segments
    ] == [("seg-a", 0.0, 5.0), ("seg-b", 5.0, 10.0), ("seg-c", 11.0, 16.0)]


def test_variant_render_session_drops_unpicked_scenes_and_moves_the_kept_ones() -> None:
    """렌더가 쓰는 편집 세션이 **숏폼의 장면 목록을 따라야** 한다.

    이 투영이 없으면 마스터 세션이 클립·자막을 원본 좌표로 되돌리고 버린
    장면도 그대로 남는다 -- 2026-09-11에 숏폼이 15.000초로 나온 원인이다.
    """
    from videobox_core_engine.output_variants import variant_render_session

    master_session = {
        "session_id": "session-1",
        "session_revision": 7,
        "segments": _timed_master_segments(),
    }
    variant = apply_variant_patch(
        _variant("vertical_highlight"),
        {"selected_segment_ids": ["seg-b", "seg-c"]},
        expected_variant_revision=3,
    )
    derived = materialize_variant(variant, _timed_master_segments())

    projected = variant_render_session(
        master_session=master_session,
        variant_timeline={"segments": list(derived.segments)},
    )

    assert projected is not None
    assert projected["session_id"] == "session-1"
    assert projected["session_revision"] == 7
    by_id = {str(item["segment_id"]): item for item in projected["segments"]}
    assert by_id["seg-b"]["start_sec"] == 0.0 and by_id["seg-b"]["end_sec"] == 5.0
    assert by_id["seg-c"]["start_sec"] == 5.0 and by_id["seg-c"]["end_sec"] == 10.0
    assert by_id["seg-a"]["cut_action"] == "remove"
    assert by_id["seg-b"].get("cut_action") != "remove"
    # 마스터 세션은 건드리지 않는다.
    assert master_session["segments"][1]["start_sec"] == 5.0
    assert "cut_action" not in master_session["segments"][0]


def test_variant_render_session_returns_the_master_untouched_for_a_full_variant() -> None:
    """전체본은 목록이 마스터와 같아 투영이 **아무것도 바꾸지 않는다.**"""
    from videobox_core_engine.output_variants import variant_render_session

    master_session = {
        "session_id": "session-1",
        "session_revision": 7,
        "segments": _timed_master_segments(),
        "timeline_placement_overrides": {
            "broll:clip-a": {"placement_id": "broll:clip-a", "kind": "broll", "start_sec": 0.0, "end_sec": 5.0},
        },
    }
    derived = materialize_variant(_variant("vertical_full"), _timed_master_segments())

    projected = variant_render_session(
        master_session=master_session,
        variant_timeline={"segments": list(derived.segments)},
    )

    assert projected == master_session
    # 손으로 끌어 놓은 자리도 전체본에서는 그대로 살아 있다.
    assert "timeline_placement_overrides" in (projected or {})


def test_short_form_render_session_drops_hand_dragged_master_placements() -> None:
    """마스터 좌표의 절대 시각은 짧아진 판에서 쓸 수 없다.

    버린 장면의 클립을 가리키는 항목은 `apply_timeline_placement_overrides`가
    `timeline_placement_unknown`으로 렌더를 통째로 죽이고, 남은 클립을 가리키는
    항목은 당겨 놓은 클립을 도로 마스터 자리로 되돌린다.
    """
    from videobox_core_engine.output_variants import variant_render_session

    master_session = {
        "session_id": "session-1",
        "session_revision": 7,
        "segments": _timed_master_segments(),
        "timeline_placement_overrides": {
            "broll:clip-a": {"placement_id": "broll:clip-a", "kind": "broll", "start_sec": 0.0, "end_sec": 5.0},
        },
    }
    variant = apply_variant_patch(
        _variant("vertical_highlight"),
        {"selected_segment_ids": ["seg-b", "seg-c"]},
        expected_variant_revision=3,
    )
    derived = materialize_variant(variant, _timed_master_segments())

    projected = variant_render_session(
        master_session=master_session,
        variant_timeline={"segments": list(derived.segments)},
    )

    assert projected is not None
    assert "timeline_placement_overrides" not in projected
    assert "timeline_placement_overrides" in master_session
