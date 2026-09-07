"""자막 번역 엔드포인트 -- 화면이 밟을 경로를 그대로 밟는다.

`docs/decisions/2026-09-01-capcut-ai-feature-triage.ko.md`가 다음 큰 것으로
지목한 동영상 번역기의 1단계다. 1단계는 **자막만** 옮긴다(목소리 더빙은 별개).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_api.orchestration import LocalOnlyRuntimeService
from videobox_core_engine.settings import LocalOpenAICompatibleRuntimeConfig
from videobox_provider_interfaces.llm import StructuredLLMRequest, StructuredLLMResponse
from videobox_storage.local_project_store import LocalProjectStore


@dataclass
class _Provider:
    """받은 번호를 그대로 되돌려주는 가짜 번역기."""

    calls: list[StructuredLLMRequest] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        self.calls.append(request)
        block = request.prompt.split("옮길 자막:", 1)[1]
        numbers = [
            int(line.split(".", 1)[0]) for line in block.splitlines() if line.strip()[:1].isdigit()
        ]
        output_data = {
            "schema_version": "videobox.caption-translation.v1",
            "translations": [{"scene": number, "text": f"EN {number}"} for number in numbers],
        }
        return StructuredLLMResponse(
            provider_name="local_qwen",
            model_name="Qwen3-32B",
            output_data=output_data,
            raw_text=json.dumps(output_data, ensure_ascii=False),
            metadata={},
        )


def _client(tmp_path: Path) -> tuple[TestClient, str, str, _Provider]:
    provider = _Provider()

    def factory(_: LocalProjectStore) -> LocalOnlyRuntimeService:
        return LocalOnlyRuntimeService(
            local_provider=provider,
            local_runtime_config=LocalOpenAICompatibleRuntimeConfig(
                enabled=True, base_url="http://127.0.0.1:1234/v1",
                model_name="Qwen3-32B", timeout_seconds=42,
            ),
        )

    app = create_app(projects_root=tmp_path / "projects", local_only_runtime_service_factory=factory)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "번역"}).json()["project_id"]
    session_id = client.post(f"/api/projects/{project_id}/editing-sessions/blank").json()["session_id"]
    return client, project_id, session_id, provider


def _session(client: TestClient, project_id: str, session_id: str) -> dict[str, Any]:
    response = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _write_caption(client: TestClient, project_id: str, session_id: str, text: str) -> dict[str, Any]:
    body = _session(client, project_id, session_id)
    segment_id = body["segments"][0]["segment_id"]
    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/caption",
        json={"caption_text": text, "expected_revision": body["session_revision"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_translating_keeps_the_korean_and_picks_the_new_language(tmp_path: Path) -> None:
    client, project_id, session_id, _ = _client(tmp_path)
    before = _write_caption(client, project_id, session_id, "안녕하세요")

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/caption-translations",
        json={"language": "en", "expected_revision": before["session_revision"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["caption_language"] == "en"
    segment = body["segments"][0]
    # 원본이 살아 있어야 되돌릴 수 있다.
    assert segment["caption_text"] == "안녕하세요"
    assert segment["caption_translations"]["en"] == "EN 1"


def test_the_choice_can_go_back_to_the_original(tmp_path: Path) -> None:
    """원본으로 되돌려도 **번역은 지우지 않는다** -- 다시 고르면 그대로 나온다."""
    client, project_id, session_id, _ = _client(tmp_path)
    before = _write_caption(client, project_id, session_id, "안녕하세요")
    translated = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/caption-translations",
        json={"language": "en", "expected_revision": before["session_revision"]},
    ).json()

    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/caption-language",
        json={"language": None, "expected_revision": translated["session_revision"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "caption_language" not in body or body["caption_language"] is None
    assert body["segments"][0]["caption_translations"]["en"].startswith("EN ")


def test_translating_twice_does_not_call_the_model_again(tmp_path: Path) -> None:
    """이미 옮겨 둔 장면은 다시 안 부른다 -- 기다림도 길고 손본 번역도 날아간다."""
    client, project_id, session_id, provider = _client(tmp_path)
    before = _write_caption(client, project_id, session_id, "안녕하세요")
    first = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/caption-translations",
        json={"language": "en", "expected_revision": before["session_revision"]},
    ).json()
    calls_after_first = len(provider.calls)

    client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/caption-translations",
        json={"language": "en", "expected_revision": first["session_revision"]},
    )

    assert len(provider.calls) == calls_after_first


def test_an_unknown_language_is_refused(tmp_path: Path) -> None:
    client, project_id, session_id, provider = _client(tmp_path)
    before = _write_caption(client, project_id, session_id, "안녕하세요")

    response = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/caption-translations",
        json={"language": "klingon", "expected_revision": before["session_revision"]},
    )

    assert response.status_code == 422, response.text
    assert provider.calls == []


def test_editing_while_viewing_english_does_not_destroy_the_korean(tmp_path: Path) -> None:
    """**화면에 보이는 것과 저장되는 곳이 같아야 한다.**

    2026-09-03 실측: 영어 자막을 보면서 고쳤더니 한국어 원본이 영어로 덮여
    사라졌고, 정작 완성본에 나가는 영어는 그대로였다. 두 겹으로 나빴다 --
    원본을 잃고, 고친 것은 반영도 안 됐다.
    """
    client, project_id, session_id = _client(tmp_path)[:3]
    before = _write_caption(client, project_id, session_id, "안녕하세요")
    translated = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/caption-translations",
        json={"language": "en", "expected_revision": before["session_revision"]},
    ).json()
    segment_id = translated["segments"][0]["segment_id"]

    edited = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/caption",
        json={
            "caption_text": "Hello there, friend.",
            "language": "en",
            "expected_revision": translated["session_revision"],
        },
    )

    assert edited.status_code == 200, edited.text
    segment = edited.json()["segments"][0]
    assert segment["caption_text"] == "안녕하세요", "한국어 원본이 사라졌다"
    assert segment["caption_translations"]["en"] == "Hello there, friend.", "고친 영어가 반영되지 않았다"


def test_editing_without_a_language_still_edits_the_original(tmp_path: Path) -> None:
    """유진이 고치는 길은 언어를 안 준다 -- 한국어 원문을 보고 말하기 때문이다."""
    client, project_id, session_id = _client(tmp_path)[:3]
    before = _write_caption(client, project_id, session_id, "안녕하세요")
    translated = client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/caption-translations",
        json={"language": "en", "expected_revision": before["session_revision"]},
    ).json()
    segment_id = translated["segments"][0]["segment_id"]

    edited = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/caption",
        json={"caption_text": "반갑습니다", "expected_revision": translated["session_revision"]},
    ).json()

    segment = edited["segments"][0]
    assert segment["caption_text"] == "반갑습니다"
    # 영어 번역은 그대로 남는다 -- 원본을 고쳤다고 번역이 사라지면 안 된다.
    assert segment["caption_translations"]["en"] == "EN 1"


def test_an_unknown_language_cannot_be_edited(tmp_path: Path) -> None:
    client, project_id, session_id = _client(tmp_path)[:3]
    before = _write_caption(client, project_id, session_id, "안녕하세요")
    segment_id = before["segments"][0]["segment_id"]

    response = client.patch(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/caption",
        json={"caption_text": "x", "language": "klingon", "expected_revision": before["session_revision"]},
    )

    assert response.status_code == 422, response.text
