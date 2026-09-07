"""추천 후보 카드가 **무엇을 고르는 것인지** 말하는지.

2026-08-19 owner 지적: 후보가 7개 떴는데 전부 `P08-B-01 · 미디어`,
설명은 전부 `metadata`였다. 실제로 재 보니 일곱 개가 **같은 자산**이었고,
각자 다른 장면을 겨냥하는데도 그 장면이 payload에 실리지 않았다.
고를 수 없는 추천은 없는 추천과 같다.
"""

from __future__ import annotations

from videobox_core_engine.director_proposals import proposal_to_payload
from videobox_core_engine.media_ranking import rank_candidates
from videobox_domain_models.director_proposals import DirectorProposal


def _asset(asset_id: str, **extra: object) -> dict[str, object]:
    return {"asset_id": asset_id, "media_type": "broll", "duration_sec": 12.0, "license": "valid", **extra}


def test_a_candidate_carries_the_name_a_person_can_read() -> None:
    # 코드(`P01-B-01`)는 사람이 고르는 근거가 못 된다. 자산 이름이 있어야 한다.
    ranked = rank_candidates({"text": "바다 풍경", "duration_sec": 10.0}, [_asset("asset_sea", display_name="제주 바다 드론")])

    assert ranked[0].canonical_metadata.get("display_name") == "제주 바다 드론"


def test_a_candidate_without_a_name_falls_back_to_something_nameable() -> None:
    # 이름이 없으면 빈칸 대신 파일 이름이라도 준다. 빈칸은 고를 수 없다.
    ranked = rank_candidates({"text": "바다", "duration_sec": 10.0}, [_asset("asset_sea", storage_uri="local://projects/p/assets/imported/sunset.mp4")])

    assert ranked[0].canonical_metadata.get("display_name") == "sunset.mp4"


def test_each_candidate_says_which_scene_it_is_for() -> None:
    # 같은 자산이 여러 장면에 추천될 수 있다. 어느 장면인지 없으면 일곱 개가
    # 똑같아 보인다 -- 실제로 owner 화면이 그랬다.
    ranked = rank_candidates({"text": "바다", "duration_sec": 10.0}, [_asset("asset_sea", display_name="바다")])
    scoped = ranked[0].__class__(**{**ranked[0].__dict__, "candidate_id": "candidate:segment_two:asset_sea"})
    proposal = DirectorProposal(
        proposal_id="proposal_1", revision_code="P01", revision=1, base_session_revision=1,
        asset_index_revision="index_1", source_session_id="session_1",
        target_segment_ids=("segment_two",), source_script_segment_ids=("segment_two",),
        status="ready", candidates=(scoped,),
        diff={"placements": [{"target_segment_id": "segment_two", "candidate_id": "candidate:segment_two:asset_sea", "asset_id": "asset_sea"}]},
        expires_at=None,
    )

    payload = proposal_to_payload(proposal)

    assert payload["candidates"][0]["target_segment_id"] == "segment_two"
