from videobox_core_engine.library_usage import scan_library_asset_usage


def test_scans_sessions_timelines_variants_and_derived_sequences_with_navigation_context():
    asset_id = "user_asset_123"
    locations = scan_library_asset_usage(
        asset_id,
        editing_sessions=[
            {
                "project_id": "project-a",
                "session_id": "session-1",
                "segments": [
                    {"segment_id": "segment-2", "broll_override": {"library_asset_id": asset_id}},
                    {"segment_id": "segment-3", "music_override": {"source_library_asset_id": asset_id}},
                ],
            }
        ],
        timelines=[
            {
                "project_id": "project-a",
                "timeline_id": "timeline-1",
                "tracks": [{"clips": [{"asset_id": asset_id}]}],
            }
        ],
        variants=[
            {
                "project_id": "project-a",
                "timeline_id": "timeline-1",
                "variant_id": "vertical",
                "asset_ids": ["other", asset_id],
            }
        ],
        derived_sequences=[
            {
                "project_id": "project-a",
                "sequence_id": "sequence-1",
                "source_library_asset_ids": [asset_id],
            }
        ],
    )

    assert [(item["kind"], item["field"]) for item in locations] == [
        ("editing_session", "library_asset_id"),
        ("editing_session", "source_library_asset_id"),
        ("timeline", "asset_id"),
        ("variant", "asset_ids"),
        ("derived_sequence", "source_library_asset_ids"),
    ]
    assert locations[0]["project_id"] == "project-a"
    assert locations[0]["session_id"] == "session-1"
    assert locations[0]["path"].endswith("['library_asset_id']") is False
    assert locations[0]["path"].endswith(".library_asset_id")
    assert locations[3]["path"].endswith(".asset_ids[1]")


def test_accepts_one_mapping_and_ignores_malformed_or_unrelated_values():
    asset_id = "pack:starter:music-001"
    locations = scan_library_asset_usage(
        asset_id,
        projects={
            "project_id": "project-a",
            "metadata": {"source_path": asset_id},
            "assets": [{"asset_id": "project-local"}, {"source_library_asset_id": asset_id}],
        },
        editing_sessions=[None, "not-a-snapshot", {"segments": [{"library_asset_id": {"id": asset_id}}]}],
    )

    assert len(locations) == 1
    assert locations[0]["kind"] == "project"
    assert locations[0]["project_id"] == "project-a"
    assert locations[0]["field"] == "source_library_asset_id"


def test_duplicate_sightings_at_same_path_are_stable_and_empty_id_is_rejected():
    asset_id = "user_asset_123"
    payload = {"project_id": "p", "library_asset_id": asset_id}
    first = scan_library_asset_usage(asset_id, projects=[payload, payload])
    second = scan_library_asset_usage(asset_id, projects=[payload, payload])

    assert first == second
    # Distinct snapshots remain distinct locations, even if their content is
    # identical, because each may be a separate project-store record.
    assert len(first) == 2
    try:
        scan_library_asset_usage("  ", projects=[payload])
    except ValueError as exc:
        assert str(exc) == "library_asset_id is required"
    else:
        raise AssertionError("empty asset IDs must fail closed")
