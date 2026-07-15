from __future__ import annotations


def test_ambiguous_numeric_reference_returns_candidate_and_timeline_options() -> None:
    """Task 13 RED: display number is never silently linked to an immutable id."""
    from videobox_core_engine.director_commands import resolve_director_command

    result = resolve_director_command(
        "3번 영상 바꿔줘",
        open_proposal={"proposal_id": "proposal-12", "candidates": [
            {"candidate_id": "candidate-immutable", "visible_reference_code": "P12-B-03", "media_type": "broll"},
        ]},
        timeline={"segments": [
            {"segment_id": "segment-immutable", "reference_code": "B-03", "track_type": "broll"},
        ]},
    )
    assert result.status == "needs_disambiguation"
    assert [(item.reference_code, item.immutable_id) for item in result.options] == [
        ("P12-B-03", "candidate-immutable"),
        ("B-03", {"segment_id": "segment-immutable", "track_type": "broll"}),
    ]


def test_explicit_candidate_code_resolves_before_timeline_placement() -> None:
    from videobox_core_engine.director_commands import resolve_director_command

    result = resolve_director_command(
        "P12-B-03 바꿔줘",
        open_proposal={"proposal_id": "proposal-12", "candidates": [
            {"candidate_id": "candidate-immutable", "visible_reference_code": "P12-B-03", "media_type": "broll"},
        ]},
        timeline={"segments": [{"segment_id": "segment-immutable", "reference_code": "B-03", "track_type": "broll"}]},
    )
    assert result.status == "resolved"
    assert result.reference.immutable_id == "candidate-immutable"


def test_applied_override_derives_durable_bms_reference_without_synthetic_code() -> None:
    from videobox_core_engine.director_commands import director_timeline_references, resolve_director_command
    timeline = director_timeline_references({"segments": [
        {"segment_id": "actual-placement", "broll_override": {"asset_id": "materialized"}},
        {"segment_id": "music-placement", "music_override": {"asset_id": "music"}},
    ]})
    result = resolve_director_command("B-01 바꿔줘", open_proposal=None, timeline=timeline)
    assert result.status == "resolved"
    assert result.reference.immutable_id == {"segment_id": "actual-placement", "track_type": "broll"}


def test_same_segment_bms_tracks_resolve_to_distinct_typed_target_identities() -> None:
    """A segment can own more than one placement, so its ID alone is not a target."""
    from videobox_core_engine.director_commands import director_timeline_references, resolve_director_command

    timeline = director_timeline_references({"segments": [
        {
            "segment_id": "shared-segment",
            "broll_override": {"asset_id": "broll"},
            "music_override": {"asset_id": "music"},
            "sfx_override": {"asset_id": "sfx"},
        },
    ]})

    broll = resolve_director_command("B-01 바꿔줘", open_proposal=None, timeline=timeline)
    music = resolve_director_command("M-01 바꿔줘", open_proposal=None, timeline=timeline)
    sfx = resolve_director_command("S-01 바꿔줘", open_proposal=None, timeline=timeline)

    assert broll.reference.immutable_id == {"segment_id": "shared-segment", "track_type": "broll"}
    assert music.reference.immutable_id == {"segment_id": "shared-segment", "track_type": "bgm"}
    assert sfx.reference.immutable_id == {"segment_id": "shared-segment", "track_type": "sfx"}


def test_resolved_candidate_returns_typed_action_intent_with_immutable_preflight_binding() -> None:
    """A command acknowledgement is not an apply instruction without its frozen proposal binding."""
    from videobox_core_engine.director_commands import resolve_director_command

    result = resolve_director_command(
        "P12-B-03 바꿔줘",
        open_proposal={
            "proposal_id": "proposal-immutable",
            "base_session_revision": 7,
            "asset_index_revision": 11,
            "candidates": [{"candidate_id": "candidate-immutable", "visible_reference_code": "P12-B-03"}],
        },
        timeline={"segments": []},
    )

    assert result.status == "resolved"
    assert result.action_intent.action == "replace_media"
    assert result.action_intent.target == result.reference
    assert result.action_intent.proposal_preflight == {
        "proposal_id": "proposal-immutable",
        "base_session_revision": 7,
        "asset_index_revision": 11,
    }


def test_resolved_timeline_target_binds_the_current_session_revision_without_open_proposal() -> None:
    from videobox_core_engine.director_commands import resolve_director_command

    result = resolve_director_command(
        "B-01 바꿔줘",
        open_proposal=None,
        timeline={
            "session_id": "editing-session-immutable",
            "session_revision": 9,
            "segments": [{"segment_id": "placement-immutable", "reference_code": "B-01", "track_type": "broll"}],
        },
    )

    assert result.status == "resolved"
    assert result.action_intent.proposal_preflight == {
        "session_id": "editing-session-immutable",
        "session_revision": 9,
    }
