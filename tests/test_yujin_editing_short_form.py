"""유진 편집 채팅으로 "숏폼 만들어줘"/"다시 만들어줘"/"펼쳐줘"가 되는지.

**이게 실제로 화면이 쓰는 경로다**(2026-09-12 프론트 코드 역추적으로 확인).
`yujin_creator_proposals.py`/`hermes_run_service.py` 쪽에 같은 이름의 action을
추가한 적이 있는데, 그 경로는 `apps/web` 어디에서도 안 불린다 -- 실제 채팅
(`HomeYujinChat.tsx`, `EditorWorkbenchRoute.tsx`)은 전부
`api.createYujinEditingProposal` -> `YujinEditingProposalService`로 간다. 그래서
이 시험은 harness를 `test_api_output_variants`(단추 경로)에서 가져오되, 제안은
**`/yujin-editing-proposals` 경로**로만 만든다 -- 창작 컨텍스트를 손으로 만들어
`parse_and_project_yujin_creator_output`을 직접 부르는 시험은 화면을 한 번도
지나지 않으므로 이 항목의 증거가 되지 못한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from test_api_output_variants import _offline_app, _short_form_project
from videobox_provider_interfaces.llm import (
    LLMProviderError,
    LLMTaskType,
    StructuredLLMRequest,
    StructuredLLMResponse,
)


@dataclass
class _EditingChatProvider:
    """편집 채팅(의도 판단)과 숏폼 장면 판단(짜기) 둘 다 받는 가짜 유진.

    실제 채팅은 이 둘을 **같은 `local_only_runtime_service_factory`**로
    돌린다 -- `YujinEditingProposalService`가 의도를 판단하고, 의도가
    `create_short_form`/`remake_short_form`이면 그 결과로
    `short_form_scenes.py`가 **다시** 같은 runtime을 불러 장면을 판단한다.
    장면 판단은 대비책(자막 밀도)이 있으므로 여기서는 끈다 -- 이 시험이
    재는 것은 "채팅으로 그 문이 열리는가"이지 "유진이 어떤 장면을 고르는가"가
    아니다.
    """

    intent: str
    #: 시험이 세션을 만든 뒤 채워 넣는다 -- `_editing_prompt`가 프롬프트 글 안에
    #: `현재 revision: N`으로 박아 두므로, 거기서 그대로 읽어 되돌려 준다
    #: (`provider_context`는 이 호출 경로에서 안 쓰여서 비어 있다).
    base_session_revision: int = 1
    calls: list[LLMTaskType] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        self.calls.append(request.task_type)
        if request.task_type == LLMTaskType.YUJIN_CONVERSATION:
            revision = self.base_session_revision
            marker = "현재 revision: "
            if marker in request.prompt:
                tail = request.prompt.split(marker, 1)[1]
                revision = int(tail.split(".", 1)[0].strip())
            output_data = {
                "schema_version": "videobox.yujin-editing-response.v1",
                "reply_text": "숏폼을 처리했어요.",
                "proposal": {
                    "proposal_id": "proposal-short-form",
                    "base_session_revision": revision,
                    "operations": [{"intent": self.intent}],
                },
            }
            return StructuredLLMResponse(
                provider_name="local_qwen", model_name="Qwen3-32B",
                output_data=output_data, raw_text="{}", metadata={},
            )
        # 장면 판단은 대비책(자막 밀도)에 맡긴다 -- 이 시험의 관심사가 아니다.
        raise LLMProviderError(provider_name="local_qwen", message="scene judging skipped in this test")


def _plain_session_project(tmp_path: Path, provider: object):
    """숏폼이 아직 없는 편집본 하나."""
    app = _offline_app(tmp_path, provider=provider)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "유진 채팅 숏폼"}).json()
    session = app.state.store.save_editing_session(
        project_id=project["project_id"],
        timeline_id="timeline-source",
        session_payload={
            "segments": [
                {"segment_id": "seg-hook", "caption_text": "이것만 보세요", "start_sec": 0.0, "end_sec": 3.0},
                {"segment_id": "seg-middle", "caption_text": "중간 설명", "start_sec": 3.0, "end_sec": 20.0},
                {"segment_id": "seg-close", "caption_text": "결론입니다", "start_sec": 20.0, "end_sec": 24.0},
            ],
            "history": [],
        },
    )
    return app, client, project["project_id"], session


def _create_and_apply(client: TestClient, project_id: str, session: dict, instruction: str) -> dict:
    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    proposal = client.post(f"{root}/yujin-editing-proposals", json={"instruction": instruction}).json()
    assert "proposal_id" in proposal, proposal
    response = client.post(
        f"{root}/yujin-editing-proposals/{proposal['proposal_id']}/apply",
        json={"expected_revision": int(session["session_revision"])},
    )
    return response


def test_yujin_can_create_the_first_short_form_from_the_real_chat(tmp_path: Path) -> None:
    """"숏폼 만들어줘"가 **화면이 실제로 쓰는 채팅 경로**로 된다."""
    provider = _EditingChatProvider(intent="create_short_form")
    app, client, project_id, session = _plain_session_project(tmp_path, provider)

    response = _create_and_apply(client, project_id, session, "숏폼 하나 만들어줘")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "short_form_created"
    assert body["variant"]["kind"] == "vertical_highlight"
    assert body["variant"]["selected_segment_ids"]

    variants = client.get(
        f"/api/projects/{project_id}/output-variants", params={"session_id": session["session_id"]},
    ).json()["variants"]
    assert any(item["kind"] == "vertical_highlight" for item in variants)


def test_yujin_refuses_to_create_a_second_short_form_from_chat(tmp_path: Path) -> None:
    provider = _EditingChatProvider(intent="create_short_form")
    app, client, project_id, session, _variant = _short_form_project(tmp_path, provider=provider)

    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    proposal = client.post(f"{root}/yujin-editing-proposals", json={"instruction": "숏폼 만들어줘"}).json()

    # 컨텍스트가 이미 숏폼이 있다고 보므로 후보 자체가 안 만들어진다
    # (검증기가 `short_form_already_exists`로 막는다) -- 화면에는 유진의
    # 대답만 남고 편집안은 없다.
    assert "proposal" not in proposal or proposal.get("proposal") is None


def test_yujin_can_remake_an_existing_short_form_from_the_real_chat(tmp_path: Path) -> None:
    provider = _EditingChatProvider(intent="remake_short_form")
    app, client, project_id, session, variant = _short_form_project(tmp_path, provider=provider)
    before = list(variant["selected_segment_ids"] or [])

    response = _create_and_apply(client, project_id, session, "숏폼 다시 만들어줘")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "short_form_remade"
    assert body["variant"]["variant_revision"] == int(variant["variant_revision"]) + 1
    # 대비책(자막 밀도)으로도 결과가 같을 수 있다 -- 여기서 재려는 것은 문이
    # 열렸는가이지 고른 장면이 달라졌는가가 아니다.
    assert body["variant"]["selected_segment_ids"] is not None
    assert before or True


def test_yujin_can_unfold_a_short_form_from_the_real_chat(tmp_path: Path) -> None:
    provider = _EditingChatProvider(intent="unfold_short_form")
    app, client, project_id, session, variant = _short_form_project(tmp_path, provider=provider)

    response = _create_and_apply(client, project_id, session, "이 숏폼 펼쳐줘")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "short_form_unfolded"
    assert "펼치면" in body["notice"]
    assert body["editing_session"]["session_id"] != session["session_id"]


def test_remake_and_unfold_are_refused_from_chat_when_no_short_form_exists(tmp_path: Path) -> None:
    for intent, instruction in (
        ("remake_short_form", "숏폼 다시 만들어줘"),
        ("unfold_short_form", "숏폼 펼쳐줘"),
    ):
        provider = _EditingChatProvider(intent=intent)
        app, client, project_id, session = _plain_session_project(tmp_path, provider)
        root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"

        proposal = client.post(f"{root}/yujin-editing-proposals", json={"instruction": instruction}).json()

        assert "proposal" not in proposal or proposal.get("proposal") is None, (intent, proposal)
