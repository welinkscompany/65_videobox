"""대표님 결재 결과가 VideoBox로 돌아오는 길 (AK W1215-2, 2026-09-28).

VideoBox는 기획서 승인 때 대본 확정·제목 후보를, 완성본에서 업로드 승인을
AK-System 결재함(127.0.0.1:19680)에 **올리기만** 했다. 대표님이 결재함에서
고르고 누른 결과를 다시 읽는 코드가 0곳이었다 -- AK 쪽 apply 워커 머리말도
"videobox 가 status 를 듣고 있는지는 모른다"고 적어 두었다.

AK 계약은 결과를 세 레지스트리 파일(`videobox-*-approval-registry.json`)의
`status`·`selected_*`·`decided_at` 에 남기는 것이다. 그래서 돌아오는 길은 둘로 나뉜다.

1. VideoBox API가 결정 하나를 받아 **한 번만** 반영한다
   (`POST /api/projects/{id}/founder-approval-decisions`). 같은 결정이 다시 와도
   아무것도 바뀌지 않고, 같은 결정 번호에 다른 결과가 오면 거절한다.
2. 호스트에서 도는 동기화(`videobox_mcp.ak_decision_sync`)가 AK 레지스트리를
   **읽기만** 해서 결정이 난 항목을 1로 보낸다. AK 파일은 절대 안 고친다.

반영의 효과: 대본이 반려되면 그 기획서로 초안을 더 만들지 않는다. 업로드가
결정된 완성본은 다시 승인을 요청하지 않는다(같은 결정 번호는 AK도 거절한다).
고른 제목과 확정 여부는 목록으로 읽힌다.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _approved_brief(client: TestClient, project_id: str) -> dict[str, Any]:
    base = f"/api/projects/{project_id}"
    brief = client.post(
        f"{base}/creation-briefs",
        json={"script_filename": "a.txt", "script_text": "소개", "idempotency_key": "brief", "capability_profile": {}},
    ).json()
    brief = client.post(f"{base}/creation-briefs/{brief['brief_id']}/bypass", json={"expected_revision": brief["revision"]}).json()
    brief = client.patch(f"{base}/creation-briefs/{brief['brief_id']}", json={"summary": "소개", "expected_revision": brief["revision"]}).json()
    brief = client.post(f"{base}/creation-briefs/{brief['brief_id']}/approve", json={"expected_revision": brief["revision"]}).json()
    assert brief["status"] == "approved"
    return brief


def _decision(project_id: str, kind: str, cycle_id: str, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "decision_id": f"vb-{kind}-{project_id}-{cycle_id}",
        "kind": kind,
        "cycle_id": cycle_id,
        "status": status,
        "decided_at": "2026-09-28T09:00:00+09:00",
        "decided_via": "telegram",
        **extra,
    }


def _project(client: TestClient, name: str = "결재 되읽기") -> str:
    return client.post("/api/projects", json={"name": name}).json()["project_id"]


def test_a_founder_decision_is_applied_once_and_a_repeat_changes_nothing(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = _project(client)
    url = f"/api/projects/{project_id}/founder-approval-decisions"
    payload = _decision(project_id, "title", "brief_1", "title_selected", selected_index=2, selected_text="두 번째 제목")

    first = client.post(url, json=payload)
    again = client.post(url, json=payload)

    assert first.status_code == 200, first.text
    assert first.json()["applied"] is True
    assert again.status_code == 200, again.text
    assert again.json()["applied"] is False
    listed = client.get(url).json()["decisions"]
    assert len(listed) == 1
    assert listed[0]["decision_id"] == payload["decision_id"]
    assert listed[0]["outcome"] == "approved"
    assert listed[0]["selected_text"] == "두 번째 제목"


def test_a_different_answer_under_the_same_decision_id_is_refused(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = _project(client)
    url = f"/api/projects/{project_id}/founder-approval-decisions"
    assert client.post(url, json=_decision(project_id, "upload", "job_1", "upload_approved")).status_code == 200

    flipped = client.post(url, json=_decision(project_id, "upload", "job_1", "upload_rejected"))

    assert flipped.status_code == 409
    assert "founder_decision_conflict" in flipped.text
    assert client.get(url).json()["decisions"][0]["status"] == "upload_approved"


def test_a_decision_id_that_is_not_about_this_project_and_cycle_is_refused(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = _project(client)
    url = f"/api/projects/{project_id}/founder-approval-decisions"
    payload = _decision(project_id, "title", "brief_1", "title_selected", selected_index=1, selected_text="t")
    payload["decision_id"] = "vb-title-someone_else-brief_1"

    response = client.post(url, json=payload)

    assert response.status_code == 400
    assert "founder_decision_id_mismatch" in response.text
    assert client.get(url).json()["decisions"] == []


def test_a_status_from_another_gate_is_refused(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = _project(client)
    url = f"/api/projects/{project_id}/founder-approval-decisions"

    response = client.post(url, json=_decision(project_id, "title", "brief_1", "upload_approved"))

    assert response.status_code == 400
    assert "founder_decision_status_invalid" in response.text


def test_a_rejected_script_stops_that_brief_from_making_a_draft(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = _project(client)
    brief = _approved_brief(client, project_id)
    base = f"/api/projects/{project_id}"
    assert client.post(
        f"{base}/founder-approval-decisions",
        json=_decision(project_id, "script", brief["brief_id"], "script_rejected"),
    ).status_code == 200

    response = client.post(
        f"{base}/draft-readiness",
        json={"brief_id": brief["brief_id"], "narration_choice": {"kind": "silent"}, "idempotency_key": "ready", "expected_brief_revision": brief["revision"]},
    )

    assert response.status_code == 400
    assert "founder_rejected_script" in response.text


def test_a_confirmed_script_lets_the_brief_go_on(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))
    project_id = _project(client)
    brief = _approved_brief(client, project_id)
    base = f"/api/projects/{project_id}"
    assert client.post(
        f"{base}/founder-approval-decisions",
        json=_decision(project_id, "script", brief["brief_id"], "script_confirmed", selected_index=1, selected_text="소개"),
    ).status_code == 200

    response = client.post(
        f"{base}/draft-readiness",
        json={"brief_id": brief["brief_id"], "narration_choice": {"kind": "silent"}, "idempotency_key": "ready", "expected_brief_revision": brief["revision"]},
    )

    assert response.status_code in {200, 201, 202}, response.text


def test_an_unknown_project_is_a_404_not_a_silent_write(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_root=tmp_path))

    response = client.post(
        "/api/projects/project_nope/founder-approval-decisions",
        json=_decision("project_nope", "upload", "job_1", "upload_approved"),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Host-side sync: reads the AK registries (never writes them) and posts decided
# entries to the API above.
# ---------------------------------------------------------------------------

_AK_CONFIG = {
    "schema_version": "ak-system-videobox-mcp-connector-config/v1",
    "tools": [
        {"tool_name": "submit_title_candidates", "kind": "title", "registry_filename": "videobox-title-approval-registry.json"},
        {"tool_name": "submit_script_confirmation", "kind": "script", "registry_filename": "videobox-script-approval-registry.json"},
        {"tool_name": "submit_upload_request", "kind": "upload", "registry_filename": "videobox-upload-approval-registry.json"},
    ],
}

_ALLOWED = {
    "title": ["pending_title_selection", "title_selected", "title_rejected"],
    "script": ["pending_script_confirmation", "script_confirmed", "script_rejected"],
    "upload": ["pending_upload_approval", "upload_approved", "upload_rejected"],
}


def _write_registries(root: Path, entries: dict[str, list[dict[str, Any]]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "videobox-mcp-connector-config.json").write_text(json.dumps(_AK_CONFIG), encoding="utf-8")
    for tool in _AK_CONFIG["tools"]:
        kind = tool["kind"]
        (root / tool["registry_filename"]).write_text(
            json.dumps({"allowed_statuses": _ALLOWED[kind], "entries": entries.get(kind, [])}, ensure_ascii=False),
            encoding="utf-8",
        )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(root.iterdir())}


def _run_sync(app: Any, registry_dir: Path) -> dict[str, Any]:
    from videobox_mcp.ak_decision_sync import sync_founder_decisions_once
    from videobox_mcp.api_client import VideoBoxApiClient

    client = VideoBoxApiClient(base_url="http://videobox.test", transport=httpx.ASGITransport(app=app))
    return asyncio.run(sync_founder_decisions_once(client, registry_dir=registry_dir))


def test_the_sync_applies_decided_entries_once_and_never_touches_the_ak_files(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = _project(client)
    brief = _approved_brief(client, project_id)
    registry_dir = tmp_path / "ak-data"
    _write_registries(
        registry_dir,
        {
            "title": [
                {"decision_id": f"vb-title-{project_id}-{brief['brief_id']}", "project_id": project_id, "cycle_id": brief["brief_id"],
                 "status": "title_selected", "selected_index": 3, "selected_title": "세 번째", "decided_at": "2026-09-28T09:00:00+09:00", "decided_via": "dashboard"},
            ],
            "script": [
                {"decision_id": f"vb-script-{project_id}-{brief['brief_id']}", "project_id": project_id, "cycle_id": brief["brief_id"],
                 "status": "script_rejected", "selected_index": None, "selected_script": None, "decided_at": "2026-09-28T09:01:00+09:00", "decided_via": "telegram"},
            ],
            "upload": [
                {"decision_id": f"vb-upload-{project_id}-job_waiting", "project_id": project_id, "cycle_id": "job_waiting",
                 "status": "pending_upload_approval", "decided_at": None, "decided_via": None, "upload_confirmed_at": None},
                {"decision_id": "vb-upload-project_elsewhere-job_1", "project_id": "project_elsewhere", "cycle_id": "job_1",
                 "status": "upload_approved", "decided_at": "2026-09-28T09:02:00+09:00", "decided_via": "telegram", "upload_confirmed_at": "2026-09-28T09:02:00+09:00"},
            ],
        },
    )
    before = _snapshot(registry_dir)

    first = _run_sync(app, registry_dir)
    second = _run_sync(app, registry_dir)

    assert first["applied"] == 2
    assert first["pending"] == 1
    assert first["unknown_project"] == 1
    assert first["conflicts"] == []
    assert second["applied"] == 0
    assert second["already_applied"] == 2
    assert _snapshot(registry_dir) == before, "the sync wrote into an AK registry"

    decisions = {d["kind"]: d for d in client.get(f"/api/projects/{project_id}/founder-approval-decisions").json()["decisions"]}
    assert decisions["title"]["selected_text"] == "세 번째"
    assert decisions["script"]["outcome"] == "rejected"
    stopped = client.post(
        f"/api/projects/{project_id}/draft-readiness",
        json={"brief_id": brief["brief_id"], "narration_choice": {"kind": "silent"}, "idempotency_key": "ready", "expected_brief_revision": brief["revision"]},
    )
    assert "founder_rejected_script" in stopped.text


def test_the_sync_refuses_a_registry_whose_statuses_drifted_from_what_it_understands(tmp_path: Path) -> None:
    from videobox_mcp.ak_decision_sync import AkRegistryContractError

    app = create_app(projects_root=tmp_path / "projects")
    registry_dir = tmp_path / "ak-data"
    _write_registries(registry_dir, {})
    title_path = registry_dir / "videobox-title-approval-registry.json"
    drifted = json.loads(title_path.read_text(encoding="utf-8"))
    drifted["allowed_statuses"] = ["pending_title_selection", "title_chosen", "title_rejected"]
    title_path.write_text(json.dumps(drifted), encoding="utf-8")

    with pytest.raises(AkRegistryContractError, match="title_selected"):
        _run_sync(app, registry_dir)


def test_the_sync_reports_an_unrecognised_status_instead_of_skipping_it_silently(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    registry_dir = tmp_path / "ak-data"
    _write_registries(
        registry_dir,
        {"upload": [{"decision_id": "vb-upload-p-j", "project_id": "p", "cycle_id": "j", "status": "upload_maybe"}]},
    )

    result = _run_sync(app, registry_dir)

    assert result["unrecognised"] == ["vb-upload-p-j"]
    assert result["applied"] == 0
