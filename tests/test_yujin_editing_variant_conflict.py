"""유진 편집 채팅으로 변형본 충돌(예: 세로 전체본의 스토리 충돌)을 풀 수 있는지.

**직전 세션(task_99becf89, 2026-09-18)이 "채팅에서도 된다"고 주장했지만 실물로는
안 됐다**(`docs/handoffs/2026-09-18-variant-conflict-resolution-via-chat.ko.md`).
원인은 컨텍스트가 모자란 것만이 아니라 더 근본적이었다: `resolve_variant_conflict`가
`yujin_creator_proposals.py`(자율 루프·`director/proposals/.../batch-apply` 전용 --
`test_yujin_editing_short_form.py` 머리말이 이미 "화면 어디서도 안 부른다"고
경고한 바로 그 시스템)에만 있었고, 화면이 실제로 쓰는
`YujinEditingProposalService`(`api.createYujinEditingProposal` ->
`POST .../yujin-editing-proposals`)의 20개 intent 안에는 애초에 없었다 --
컨텍스트를 아무리 채워도 모델이 낼 수 있는 값 자체가 없었다는 뜻이다.

이 시험은 `resolve_variant_conflict`를 그 20개 intent 옆에 추가한 뒤, **화면이
실제로 쓰는 경로**(create -> apply, `test_yujin_editing_short_form.py`와 같은
harness)로 잰다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from test_api_output_variants import _offline_app
from videobox_provider_interfaces.llm import (
    LLMTaskType,
    StructuredLLMRequest,
    StructuredLLMResponse,
)


@dataclass
class _VariantConflictChatProvider:
    """편집 채팅 의도 판단만 받는 가짜 유진.

    실제로 프롬프트에 무엇이 왔는지도 같이 남긴다(`prompts`) -- 이 시험의
    목적 하나가 "충돌 목록이 실제로 프롬프트에 실리는가"이므로, 응답만 보고는
    잴 수 없다.
    """

    variant_id: str
    field_name: str
    decision: str
    prompts: list[str] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        assert request.task_type == LLMTaskType.YUJIN_CONVERSATION
        self.prompts.append(request.prompt)
        revision = 1
        marker = "현재 revision: "
        if marker in request.prompt:
            revision = int(request.prompt.split(marker, 1)[1].split(".", 1)[0].strip())
        output_data = {
            "schema_version": "videobox.yujin-editing-response.v1",
            "reply_text": "변형본 충돌을 마스터 기준으로 맞췄어요.",
            "proposal": {
                "proposal_id": "proposal-variant-conflict",
                "base_session_revision": revision,
                "operations": [{
                    "intent": "resolve_variant_conflict",
                    "variant_id": self.variant_id,
                    "field": self.field_name,
                    "decision": self.decision,
                }],
            },
        }
        return StructuredLLMResponse(
            provider_name="local_qwen", model_name="Qwen3-32B",
            output_data=output_data, raw_text="{}", metadata={},
        )


def _client_with_provider(tmp_path: Path, provider: object):
    app = _offline_app(tmp_path, provider=provider)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "유진 채팅 변형본 충돌"}).json()
    session = app.state.store.save_editing_session(
        project_id=project["project_id"],
        timeline_id="timeline-source",
        session_payload={
            "segments": [
                {"segment_id": "seg-a", "text": "a"},
                {"segment_id": "seg-b", "text": "b"},
            ],
            "history": [],
        },
    )
    return app, client, project["project_id"], session


def _make_vertical_full_story_conflict(app, client: TestClient, project_id: str, session: dict) -> tuple[dict, dict]:
    """가로/세로 전체 변형본을 만들고, 세로 전체본에 `story` 충돌 하나를 만든다.

    `test_api_output_variants.py`의
    `test_yujin_resolves_a_vertical_full_story_conflict_through_chat_and_unblocks_materialize`
    (옛 -- 화면이 안 쓰는 경로를 잰 시험)가 쓰던 것과 같은 절차다: 세션을 바꿔
    리비전을 올리고, `rebase`로 옛 변형본이 새 마스터를 따라잡게 하면 그 결과로
    `story` 충돌이 생긴다.
    """
    variants = client.get(f"/api/projects/{project_id}/output-variants").json()["variants"]
    vertical = next(item for item in variants if item["kind"] == "vertical_full")
    bumped = app.state.store.update_editing_session(
        project_id=project_id,
        session_id=session["session_id"],
        session_payload={
            "segments": [
                {"segment_id": "seg-a", "text": "a"},
                {"segment_id": "seg-new", "text": "new"},
                {"segment_id": "seg-b", "text": "b"},
            ],
            "history": [],
        },
    )
    assert bumped["session_revision"] == 2
    rebased = client.post(
        f"/api/projects/{project_id}/output-variants/{vertical['variant_id']}/rebase",
        json={"new_master_revision": 2, "changed_fields": ["story"]},
    ).json()["variant"]
    assert rebased["conflicts"][0]["field"] == "story"
    return rebased, bumped


def test_variant_conflict_catalogue_reaches_the_real_editing_prompt(tmp_path: Path) -> None:
    """실제 API 요청 한 번(`create_yujin_editing_proposal`)이 지금 충돌 중인
    변형본 목록을 실제로 프롬프트에 싣는지를 잰다(단위 시험이 아니라 배선 시험).

    이 field(`YujinEditingContext.variant_conflicts`)가 없던 이전 상태에서는
    이 문자열들이 프롬프트에 전혀 없었다 -- 유진이 어느 변형본이 충돌 중인지
    알 방법이 없었다는 뜻이다.
    """
    provider = _VariantConflictChatProvider(variant_id="", field_name="story", decision="rebase_master")
    app, client, project_id, session = _client_with_provider(tmp_path, provider)
    variant, _bumped = _make_vertical_full_story_conflict(app, client, project_id, session)
    provider.variant_id = variant["variant_id"]

    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    response = client.post(
        f"{root}/yujin-editing-proposals", json={"instruction": "세로 전체 변형 충돌 마스터 기준으로 맞춰줘"}
    )

    assert response.status_code == 201, response.text
    assert provider.prompts, "유진에게 프롬프트가 한 번도 안 갔다"
    prompt = provider.prompts[-1]
    assert variant["variant_id"] in prompt
    assert "스토리(장면 구성) 충돌" in prompt
    assert "resolve_variant_conflict" in prompt


def test_yujin_resolves_a_variant_conflict_from_the_real_chat_and_clears_it(tmp_path: Path) -> None:
    """`interpretAndApplySpokenEdit`가 실제로 부르는 두 요청(create -> apply) 그대로
    변형본 충돌을 지운다. 마스터 장면 스냅샷도 같이 갱신돼 렌더가 막히지 않는지까지
    잰다(2026-09-17에 단추 경로가 겪은 함정과 같은 자리 -- 채팅 경로에서 다시
    안 걸리는지 확인한다).
    """
    provider = _VariantConflictChatProvider(variant_id="", field_name="story", decision="rebase_master")
    app, client, project_id, session = _client_with_provider(tmp_path, provider)
    variant, bumped = _make_vertical_full_story_conflict(app, client, project_id, session)
    provider.variant_id = variant["variant_id"]

    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    proposal = client.post(
        f"{root}/yujin-editing-proposals",
        json={"instruction": "세로 전체 변형에서 스토리 충돌이 있는데, 마스터 기준으로 다시 맞춰줘"},
    ).json()
    assert "proposal_id" in proposal, proposal
    apply_response = client.post(
        f"{root}/yujin-editing-proposals/{proposal['proposal_id']}/apply",
        json={"expected_revision": int(bumped["session_revision"])},
    )

    assert apply_response.status_code == 200, apply_response.text
    body = apply_response.json()
    assert body["status"] == "variant_conflict_resolved"
    resolved_variant = body["variant"]
    assert resolved_variant["conflicts"] == []
    assert resolved_variant["variant_revision"] == int(variant["variant_revision"]) + 1
    # **이 줄이 2026-09-17에 단추 경로에서 빠져 있던 자리다.** 빠지면 딱지만
    # 지워지고 마스터 장면 스냅샷은 옛날 것이라 materialize가 여전히 막힌다.
    assert resolved_variant["master_segment_ids"] == ["seg-a", "seg-new", "seg-b"]

    materialized = client.post(
        f"/api/projects/{project_id}/output-variants/{variant['variant_id']}/materialize",
        json={"expected_master_session_revision": int(bumped["session_revision"])},
    )
    assert materialized.status_code == 201, materialized.text


def test_yujin_declines_to_invent_a_conflict_when_there_is_none(tmp_path: Path) -> None:
    """충돌이 없는데 유진이 지어낸 `variant_id`/`field`로 답하면 후보가 안 만들어진다
    (`variant_conflict_not_current`) -- 색감·전환이 지어낸 이름을 막는 것과 같은 자리다.
    """
    provider = _VariantConflictChatProvider(variant_id="variant-made-up", field_name="story", decision="rebase_master")
    app, client, project_id, session = _client_with_provider(tmp_path, provider)
    client.get(f"/api/projects/{project_id}/output-variants")  # 변형본은 만들어 두되 충돌은 없다.

    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    proposal = client.post(
        f"{root}/yujin-editing-proposals", json={"instruction": "세로 전체 변형 충돌 마스터 기준으로 맞춰줘"}
    ).json()

    assert proposal.get("proposal") is None, proposal
