"""대화에서 청한 **종류**가 추천에 반영되는지.

2026-08-19 owner: "음악 추천해 줘"라고 했더니 유진이 'Lo-fi Hip Hop 장르를
추천합니다' 같은 일반론을 답했고, 정작 후보에는 영상만 왔다. 말과 후보가
따로 놀면 대화로 편집한다는 말이 성립하지 않는다.

종류를 고르는 것은 **결정적 규칙**이어야 한다 -- 모델이 고르면 같은 말에
다른 결과가 나오고, 왜 그렇게 골랐는지 설명할 수 없다.
"""

from __future__ import annotations

import pytest

from videobox_core_engine.director_media_focus import media_focus_for_request


@pytest.mark.parametrize(
    ("request_text", "expected"),
    [
        ("영상 전체에 잔잔하게 깔릴 배경 음악을 추천해 줘", ("bgm",)),
        ("BGM 하나 골라 줘", ("bgm",)),
        ("여기에 어울리는 효과음 있을까?", ("sfx",)),
        ("이 구간에 맞는 B-roll 추천해 줘", ("broll",)),
        ("이 장면에 쓸 영상 좀 찾아 줘", ("broll",)),
    ],
)
def test_the_kind_the_creator_asked_for_decides_the_candidates(request_text: str, expected: tuple[str, ...]) -> None:
    assert media_focus_for_request(request_text) == expected


def test_a_request_naming_two_kinds_keeps_both() -> None:
    assert media_focus_for_request("음악이랑 효과음 같이 추천해 줘") == ("bgm", "sfx")


def test_a_request_that_names_no_kind_does_not_narrow_anything() -> None:
    # 종류를 말하지 않았으면 좁히지 않는다. 넘겨짚어 거르면 있는 후보가 사라진다.
    assert media_focus_for_request("이 장면 분위기 어떻게 잡을까?") is None
    assert media_focus_for_request("") is None


def test_the_service_only_ranks_the_kinds_that_were_asked_for(tmp_path) -> None:
    """규칙이 **실제로 후보를 거르는지**. 규칙만 맞고 안 쓰이면 아무것도 아니다."""
    from videobox_core_engine.director_proposal_service import DirectorProposalService

    kept: list[dict] = []

    class _Store:
        def read_director_proposal_snapshot(self, *, project_id: str, session_id: str) -> dict:
            return {
                "session": {"session_revision": 1, "segments": [{"segment_id": "s1", "caption_text": "바다", "start_sec": 0.0, "end_sec": 3.0}]},
                "assets": [
                    {"asset_id": "a_video", "asset_type": "broll_video", "storage_uri": "local://v.mp4", "project_id": project_id, "metadata": {}},
                    {"asset_id": "a_music", "asset_type": "music", "storage_uri": "local://m.mp3", "project_id": project_id, "metadata": {}},
                ],
                "analyses": [{"asset_id": "a_video", "status": "succeeded"}],
                "preferences": {},
                "asset_index_revision": "index_1",
            }

    service = DirectorProposalService(store=_Store())  # type: ignore[arg-type]
    assert hasattr(service, "create"), "create가 있어야 한다"
    import inspect
    assert "media_types" in inspect.signature(service.create).parameters, (
        "create가 청한 종류를 받아야 후보를 거를 수 있다"
    )


def test_asking_for_a_kind_the_project_does_not_have_is_not_an_analysis_failure() -> None:
    """없는 것을 청한 것과 **분석이 깨진 것**은 다르다.

    2026-08-19에 음악이 없는 프로젝트에 "배경 음악 추천해 줘"를 넣었더니
    409 `director_analysis_blocked`가 났다. 분석은 멀쩡했다 -- 그 종류가
    없었을 뿐이고, 화면은 "아직 추천이 없어요"라고 말하면 된다.
    """
    from videobox_core_engine.director_proposal_service import DirectorProposalService

    class _Store:
        def read_director_proposal_snapshot(self, *, project_id: str, session_id: str) -> dict:
            return {
                "session": {"session_revision": 1, "segments": [{"segment_id": "s1", "caption_text": "바다", "start_sec": 0.0, "end_sec": 3.0}]},
                "assets": [{"asset_id": "a_video", "asset_type": "broll_video", "storage_uri": "local://v.mp4", "project_id": project_id, "metadata": {}}],
                "analyses": [{"asset_id": "a_video", "status": "succeeded"}],
                "preferences": {},
                "asset_index_revision": "index_1",
            }

    service = DirectorProposalService(store=_Store())  # type: ignore[arg-type]
    source = inspect.getsource(service.create)
    blocked_at = source.index("DirectorProposalBlockedError")
    narrowed_at = source.index("wanted = set(media_types)")
    assert blocked_at < narrowed_at, "종류 좁히기는 blocked 검사 뒤여야 한다"


import inspect  # noqa: E402  (테스트 끝에서만 쓴다)
