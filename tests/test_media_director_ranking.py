from __future__ import annotations

from videobox_core_engine.media_ranking import rank_candidates


def test_user_owned_unknown_rights_broll_is_eligible_with_warning_provenance() -> None:
    ranked = rank_candidates(
        {"text": "여행"},
        [{"asset_id": "mine", "media_type": "broll", "tags": ["여행"], "source_kind": "user_owned", "license": "unknown", "availability": "available", "review_status": "approved"}],
    )
    assert [candidate.asset_id for candidate in ranked] == ["mine"]
    assert ranked[0].canonical_metadata["copyright_warning"] == "rights_unknown_user_owned"


def test_unknown_starter_asset_remains_ineligible() -> None:
    assert not rank_candidates({"text": "여행"}, [{"asset_id": "starter", "media_type": "broll", "tags": ["여행"], "source_kind": "starter_pack", "license": "unknown", "availability": "available", "review_status": "approved"}])


SEGMENT = {"segment_id": "script:s:001", "text": "차분한 여행 장면", "duration_sec": 5}


def asset(asset_id: str, **overrides: object) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "media_type": "broll",
        "tags": ["여행", "차분한"],
        "duration_sec": 5,
        "aspect_ratio": "16:9",
        "availability": "available",
        "license": "valid",
        "review_status": "approved",
        **overrides,
    }


def test_equal_scores_use_stable_asset_id_tie_break() -> None:
    ranked = rank_candidates(SEGMENT, [asset("z"), asset("a")])
    assert [item.asset_id for item in ranked] == ["a", "z"]


def test_excluded_creator_is_ineligible_even_when_favorite() -> None:
    ranked = rank_candidates(
        SEGMENT,
        [asset("a", creator="제외 제작자", favorite=True), asset("b")],
        preferences={"exclude_creator": ["제외 제작자"]},
    )
    assert [item.asset_id for item in ranked] == ["b"]


def test_pin_cannot_bypass_license_and_lexical_korean_fallback_is_named() -> None:
    ranked = rank_candidates(
        SEGMENT,
        [asset("bad", license="invalid", pinned=True), asset("good", tags=["여행", "평온"] )],
        preferences={"pin_asset": ["bad"]},
    )
    assert [item.asset_id for item in ranked] == ["good"]
    assert ranked[0].scores["semantic_similarity"] == 0.0
    assert ranked[0].scores["lexical_fallback"] > 0
    assert ranked[0].scores["structured_tag_match"] > 0


def test_explicit_conditions_are_a_named_nonzero_score_component() -> None:
    ranked = rank_candidates(
        {"segment_id": "s", "text": "여행", "duration_sec": 3, "explicit_conditions": ["no_vocals"]},
        [asset("a", explicit_conditions=["no_vocals"])],
    )
    assert ranked[0].scores["explicit_conditions"] > 0


def test_rejected_review_status_is_ineligible_even_when_favorite_and_pinned() -> None:
    ranked = rank_candidates(
        SEGMENT,
        [asset("rejected", review_status="rejected", favorite=True), asset("approved")],
        preferences={"pin_asset": ["rejected"]},
    )
    assert [item.asset_id for item in ranked] == ["approved"]


def test_music_alias_uses_bgm_metadata_and_per_media_reference_numbering() -> None:
    ranked = rank_candidates(
        {"text": "여행", "duration_sec": 3},
        [asset("b2"), asset("music", media_type="music", mood="calm", energy="low", genre="ambient", vocal_presence="none", recommended_use="bed"), asset("s", media_type="sfx"), asset("b1")],
    )
    codes = {item.asset_id: item.visible_reference_code for item in ranked}
    assert codes == {"b1": "P01-B-01", "b2": "P01-B-02", "music": "P01-M-01", "s": "P01-S-01"}
    music = next(item for item in ranked if item.asset_id == "music")
    assert music.media_type == "bgm"
    assert set(music.canonical_metadata) >= {"mood", "energy", "genre", "vocal_presence", "recommended_use"}


def test_audio_candidates_preserve_default_gain_control_for_output_lineage() -> None:
    ranked = rank_candidates(
        {"text": "여행", "duration_sec": 3},
        [
            asset("music", media_type="music", mood="calm", energy="low", genre="ambient", recommended_use="bed"),
            asset("sfx", media_type="sfx", action_event="whoosh", intensity="low", recommended_use="accent"),
        ],
    )

    assert {candidate.media_type: candidate.controls["gain_db"] for candidate in ranked} == {
        "bgm": 0.0,
        "sfx": 0.0,
    }


def test_explicit_semantic_score_is_used_and_lexical_fallback_has_provenance() -> None:
    semantic = rank_candidates({"text": "unrelated", "duration_sec": 1}, [asset("a", tags=[], semantic_score=0.8)])[0]
    lexical = rank_candidates({"text": "여행", "duration_sec": 1}, [asset("b", tags=["휴가"])])[0]
    assert semantic.scores["semantic_similarity"] == 0.8
    assert semantic.canonical_metadata["semantic_provenance"] == "asset_semantic_score"
    assert lexical.scores["semantic_similarity"] == 0.0
    assert lexical.scores["lexical_fallback"] > 0
    assert lexical.canonical_metadata["semantic_provenance"] == "lexical_korean_synonym_fallback"
