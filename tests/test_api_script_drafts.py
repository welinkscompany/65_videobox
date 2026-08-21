"""화면이 부를 수 있는 문인가.

첫 화면의 네 번째 길(대본도 영상도 없는 사람)이 여기로 온다. 문이 열리는지를
여기서 재고, 화면이 실제로 부르는지는 `yujin-script-start.test.tsx`가 잰다.

**이 문은 아무것도 저장하지 않는다.** 초안은 제안이고, owner가 고쳐 확인해야
기획(`/creation-briefs`)으로 넘어간다 -- 사람 게이트 `대본 확정`이 그 자리다
(`decisions/2026-08-16-autonomous-creator-loop-scope-expansion.ko.md`).
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.script_draft_writer import (
    ScriptDraft,
    ScriptDraftScene,
    ScriptDraftUnavailable,
)


class _Writer:
    """여기서 재는 것은 글 품질이 아니라 **문이 열리고 요청이 그대로 닿는가**이다."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def write(self, *, project_id: str, topic: str, duration_sec: int, scene_count: int) -> ScriptDraft:
        self.calls.append(
            {"project_id": project_id, "topic": topic, "duration_sec": duration_sec, "scene_count": scene_count}
        )
        return ScriptDraft(
            title="라면 세 가지",
            script_text="첫 줄입니다.\n둘째 줄입니다.",
            scenes=(
                ScriptDraftScene(scene_number=1, narration="첫 줄입니다.", visual="끓는 냄비"),
                ScriptDraftScene(scene_number=2, narration="둘째 줄입니다."),
            ),
        )


class _RefusingWriter:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def write(self, **_kwargs: object) -> ScriptDraft:
        raise ScriptDraftUnavailable(self.reason)


def _client(tmp_path: Path, writer: object | None = None) -> tuple[TestClient, str]:
    client = TestClient(create_app(projects_root=tmp_path / "data", script_draft_writer=writer))
    project_id = client.post("/api/projects", json={"name": "대본"}).json()["project_id"]
    return client, project_id


def test_it_gives_back_one_script_and_the_scene_lines(tmp_path: Path) -> None:
    writer = _Writer()
    client, project_id = _client(tmp_path, writer)

    response = client.post(
        f"/api/projects/{project_id}/script-drafts",
        json={"topic": "집에서 라면 맛있게 끓이는 법", "duration_sec": 60, "scene_count": 5},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "라면 세 가지"
    # 화면은 둘 다 쓴다 -- owner는 글을 고치고, 장면 줄은 무엇을 보여 줄지 말한다.
    assert body["script_text"] == "첫 줄입니다.\n둘째 줄입니다."
    assert [scene["scene_number"] for scene in body["scenes"]] == [1, 2]
    assert body["scenes"][0]["visual"] == "끓는 냄비"
    assert body["scenes"][1]["visual"] == ""

    assert writer.calls == [
        {"project_id": project_id, "topic": "집에서 라면 맛있게 끓이는 법", "duration_sec": 60, "scene_count": 5}
    ]


def test_length_and_scene_count_have_defaults_so_the_screen_can_stay_simple(tmp_path: Path) -> None:
    writer = _Writer()
    client, project_id = _client(tmp_path, writer)

    response = client.post(f"/api/projects/{project_id}/script-drafts", json={"topic": "라면"})

    assert response.status_code == 201, response.text
    assert writer.calls[0]["duration_sec"] == 60
    assert writer.calls[0]["scene_count"] == 5


def test_an_empty_topic_is_refused_before_the_model_is_woken(tmp_path: Path) -> None:
    writer = _Writer()
    client, project_id = _client(tmp_path, writer)

    response = client.post(f"/api/projects/{project_id}/script-drafts", json={"topic": "   "})

    assert response.status_code == 422, response.text
    assert writer.calls == []


def test_a_silent_model_says_so_instead_of_returning_an_empty_draft(tmp_path: Path) -> None:
    """**꺼진 것과 고장 난 것과 빈 답은 서로 다른 말이다.** 하나로 뭉치면 화면이
    owner에게 무엇을 하라고 말할지 정할 수 없다."""
    client, project_id = _client(tmp_path, _RefusingWriter("script_draft_writer_unavailable"))

    response = client.post(f"/api/projects/{project_id}/script-drafts", json={"topic": "라면"})

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "script_draft_writer_unavailable"


def test_an_unusable_answer_is_reported_with_its_own_reason(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path, _RefusingWriter("script_draft_not_korean"))

    response = client.post(f"/api/projects/{project_id}/script-drafts", json={"topic": "라면"})

    assert response.status_code == 502, response.text
    assert response.json()["detail"] == "script_draft_not_korean"


def test_running_out_of_time_gets_its_own_status_so_the_screen_can_say_shorten_it(tmp_path: Path) -> None:
    """2026-08-21 실측: 5분·12장면이 28.7초였고 로컬 상한이 30초다. 같은 길이로
    다시 누르면 같은 결과이므로, 화면이 "짧게"라고 말할 수 있어야 한다."""
    client, project_id = _client(tmp_path, _RefusingWriter("script_draft_took_too_long"))

    response = client.post(
        f"/api/projects/{project_id}/script-drafts",
        json={"topic": "홈트레이닝", "duration_sec": 300, "scene_count": 12},
    )

    assert response.status_code == 504, response.text
    assert response.json()["detail"] == "script_draft_took_too_long"


def test_without_a_live_local_brain_the_door_still_answers_a_reason(tmp_path: Path) -> None:
    """테스트 하네스의 런타임은 응답하지 않는다. 그래도 500이 아니라 **이유**가
    나와야 화면이 owner에게 할 말을 고를 수 있다."""
    client, project_id = _client(tmp_path)

    response = client.post(f"/api/projects/{project_id}/script-drafts", json={"topic": "라면"})

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "script_draft_writer_unavailable"


def test_it_stores_nothing_because_a_draft_is_a_proposal(tmp_path: Path) -> None:
    """대본을 여기서 확정해 버리면 owner가 고칠 자리가 없어진다."""
    client, project_id = _client(tmp_path, _Writer())

    client.post(f"/api/projects/{project_id}/script-drafts", json={"topic": "라면"})

    listed = client.get(f"/api/projects/{project_id}/creation-briefs")
    assert listed.status_code == 200, listed.text
    assert listed.json() == {"briefs": []}
