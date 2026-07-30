from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from videobox_api.main import create_app


def _seed(app, client: TestClient):
    project_id = client.post("/api/projects", json={"name": "memory"}).json()[
        "project_id"
    ]
    session = app.state.store.save_editing_session(
        project_id=project_id,
        timeline_id="timeline",
        session_payload={"segments": [], "history": []},
    )
    conversation = client.post(
        f"/api/projects/{project_id}/director/conversations",
        json={"session_id": session["session_id"]},
    ).json()
    first = app.state.store.append_director_message(
        project_id=project_id,
        session_id=session["session_id"],
        conversation_id=conversation["conversation_id"],
        role="user",
        text="영상 템포를 조금 빠르게 해줘.",
    )
    second = app.state.store.append_director_message(
        project_id=project_id,
        session_id=session["session_id"],
        conversation_id=conversation["conversation_id"],
        role="assistant",
        text="빠른 컷과 짧은 호흡을 제안합니다.",
    )
    return project_id, session, conversation["conversation_id"], first, second


def _payload(conversation_id: str, *message_ids: str) -> dict[str, object]:
    return {
        "conversation_id": conversation_id,
        "client_request_id": "request-1",
        "source_message_ids": list(message_ids),
        "memory_scope": "creator",
        "category": "pacing",
        "proposed_text": "빠른 컷과 짧은 호흡을 선호합니다.",
    }


def test_create_and_list_are_pending_only_with_zero_external_calls_or_edit_mutation(
    tmp_path: Path,
) -> None:
    network_calls = 0

    def forbidden_network(*_args, **_kwargs):
        nonlocal network_calls
        network_calls += 1
        raise AssertionError("D1 must not call a network/provider/gateway")

    with patch("videobox_api.main.urlopen", forbidden_network):
        app = create_app(projects_root=tmp_path)
        with TestClient(app) as client:
            project_id, session, conversation_id, first, second = _seed(app, client)
            before = app.state.store.get_editing_session(
                project_id=project_id,
                session_id=session["session_id"],
            )
            response = client.post(
                f"/api/projects/{project_id}/director/memory-candidates",
                json=_payload(
                    conversation_id,
                    first["message_id"],
                    second["message_id"],
                ),
            )
            listed = client.get(
                f"/api/projects/{project_id}/director/memory-candidates"
            )
            after = app.state.store.get_editing_session(
                project_id=project_id,
                session_id=session["session_id"],
            )

    assert response.status_code == 201
    candidate = response.json()
    assert set(candidate) == {
        "candidate_id",
        "project_id",
        "conversation_id",
        "client_request_id",
        "source_message_ids",
        "memory_scope",
        "category",
        "proposed_text",
        "status",
        "created_at",
        "updated_at",
    }
    assert candidate["candidate_id"].startswith("memory-candidate-")
    assert candidate["status"] == "pending"
    assert listed.json() == {"candidates": [candidate]}
    assert before == after
    assert network_calls == 0
    assert app.state.hermes_run_service is None


def test_approve_reject_are_explicit_idempotent_and_never_schedule_write(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        approved_candidate = client.post(
            base,
            json=_payload(conversation_id, first["message_id"]),
        ).json()
        rejected_candidate = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "client_request_id": "request-2",
                "proposed_text": "짧은 인트로를 선호합니다.",
                "category": "tone",
            },
        ).json()

        approved = client.post(
            f"{base}/{approved_candidate['candidate_id']}/approve"
        )
        approved_again = client.post(
            f"{base}/{approved_candidate['candidate_id']}/approve"
        )
        approve_conflict = client.post(
            f"{base}/{approved_candidate['candidate_id']}/reject"
        )
        rejected = client.post(
            f"{base}/{rejected_candidate['candidate_id']}/reject"
        )
        rejected_again = client.post(
            f"{base}/{rejected_candidate['candidate_id']}/reject"
        )
        reject_conflict = client.post(
            f"{base}/{rejected_candidate['candidate_id']}/approve"
        )

    assert approved.json()["status"] == "approved"
    assert approved_again.json() == approved.json()
    assert rejected.json()["status"] == "rejected"
    assert rejected_again.json() == rejected.json()
    assert approve_conflict.status_code == 409
    assert approve_conflict.json() == {
        "detail": "memory_candidate_terminal_conflict"
    }
    assert reject_conflict.status_code == 409
    assert not hasattr(app.state, "memory_provider")
    assert not hasattr(app.state, "memory_write_queue")


def test_request_is_strict_and_scope_failures_do_not_leak(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        sentinel = "SENTINEL-DO-NOT-ECHO"
        extra = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "private_extra": sentinel,
            },
        )
        duplicate = client.post(
            base,
            json=_payload(
                conversation_id,
                first["message_id"],
                first["message_id"],
            ),
        )
        missing_conversation = client.post(
            base,
            json=_payload("missing", first["message_id"]),
        )
        missing_message = client.post(
            base,
            json=_payload(conversation_id, "missing"),
        )
        unknown_candidate = client.post(f"{base}/missing/approve")
        invalid_request_id = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "client_request_id": "../escape",
            },
        )
        invalid_scope = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "memory_scope": "project",
            },
        )
        invalid_text_type = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "proposed_text": {"private": sentinel},
            },
        )

    assert extra.status_code == 422
    assert extra.json() == {"detail": "memory_candidate_request_invalid"}
    assert sentinel not in extra.text
    assert duplicate.status_code == 422
    assert invalid_request_id.status_code == 422
    assert invalid_scope.status_code == 422
    assert invalid_text_type.status_code == 422
    assert invalid_text_type.json() == {
        "detail": "memory_candidate_request_invalid"
    }
    assert sentinel not in invalid_text_type.text
    assert missing_conversation.status_code == 404
    assert missing_message.status_code == 404
    assert missing_conversation.json() == missing_message.json() == {
        "detail": "memory_candidate_source_missing"
    }
    assert unknown_candidate.status_code == 404
    assert unknown_candidate.json() == {"detail": "memory_candidate_missing"}


def test_api_policy_rejects_full_source_and_sensitive_text(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        full_source = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "proposed_text": "영상 템포를 조금 빠르게 해줘.",
            },
        )
        sensitive = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "client_request_id": "request-2",
                "proposed_text": "API_KEY=secret",
            },
        )
        control_sentinel = "SENTINEL-CONTROL"
        control = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "client_request_id": "request-3",
                "proposed_text": f"safe\u0000{control_sentinel}",
            },
        )
        provider_token = "sk-proj-abcdefghijklmnopqrstuvwxyz"
        unlabeled_secret = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "client_request_id": "request-4",
                "proposed_text": provider_token,
            },
        )

    assert full_source.status_code == 422
    assert full_source.json() == {
        "detail": "memory_candidate_full_source_message_forbidden"
    }
    assert sensitive.status_code == 422
    assert sensitive.json() == {
        "detail": "memory_candidate_sensitive_text_forbidden"
    }
    assert control.status_code == 422
    assert control.json() == {
        "detail": "memory_candidate_control_character_forbidden"
    }
    assert unlabeled_secret.status_code == 422
    assert unlabeled_secret.json() == {
        "detail": "memory_candidate_sensitive_text_forbidden"
    }
    assert "API_KEY" not in sensitive.text
    assert control_sentinel not in control.text
    assert provider_token not in unlabeled_secret.text
    connection = app.state.store._connection(project_id)
    try:
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM yujin_memory_candidates"
        ).fetchone()["count"] == 0
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM yujin_memory_candidate_audit"
        ).fetchone()["count"] == 0
    finally:
        connection.close()


def test_create_request_idempotency_and_conflict_are_stable(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path)
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        payload = _payload(conversation_id, first["message_id"])
        created = client.post(base, json=payload)
        repeated = client.post(base, json=payload)
        conflict = client.post(
            base,
            json={**payload, "category": "tone"},
        )

    assert created.status_code == 201
    assert repeated.status_code == 201
    assert repeated.json() == created.json()
    assert conflict.status_code == 409
    assert conflict.json() == {
        "detail": "memory_candidate_request_conflict"
    }


def test_configured_gateway_is_never_called_by_d1_endpoints(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    class TrapGateway:
        def __getattr__(self, name: str):
            def trap(*_args, **_kwargs):
                calls.append(name)
                raise AssertionError("D1 external call")

            return trap

    with patch(
        "videobox_api.main._hermes_capability_verifier_from_environment",
        return_value=SimpleNamespace(),
    ):
        app = create_app(
            projects_root=tmp_path,
            agent_gateway_url="http://videobox-agent-gateway:8081",
            agent_gateway_service_token="service-token-that-is-at-least-thirty-two",
            agent_gateway_http_client_factory=lambda **_: TrapGateway(),
        )
    app.state.hermes_run_service.gateway_client = TrapGateway()
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"
        created = client.post(
            base,
            json=_payload(conversation_id, first["message_id"]),
        )
        candidate_id = created.json()["candidate_id"]
        assert client.get(base).status_code == 200
        assert client.post(f"{base}/{candidate_id}/approve").status_code == 200
        rejected = client.post(
            base,
            json={
                **_payload(conversation_id, first["message_id"]),
                "client_request_id": "request-2",
                "proposed_text": "차분한 도입을 선호합니다.",
                "category": "tone",
            },
        )
        assert client.post(
            f"{base}/{rejected.json()['candidate_id']}/reject"
        ).status_code == 200

    assert calls == []


def test_unknown_store_errors_are_fixed_and_never_echoed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sentinel = "SENTINEL-PRIVATE-STORE-ERROR"
    app = create_app(projects_root=tmp_path)
    with TestClient(app) as client:
        project_id, _, conversation_id, first, _ = _seed(app, client)
        base = f"/api/projects/{project_id}/director/memory-candidates"

        monkeypatch.setattr(
            app.state.store,
            "create_yujin_memory_candidate",
            lambda **_: (_ for _ in ()).throw(ValueError(sentinel)),
        )
        create = client.post(
            base,
            json=_payload(conversation_id, first["message_id"]),
        )

        monkeypatch.setattr(
            app.state.store,
            "transition_yujin_memory_candidate",
            lambda **_: (_ for _ in ()).throw(ValueError(sentinel)),
        )
        transition = client.post(f"{base}/candidate/approve")

    assert create.status_code == 503
    assert transition.status_code == 503
    assert create.json() == transition.json() == {
        "detail": "memory_candidate_unavailable"
    }
    assert sentinel not in create.text
    assert sentinel not in transition.text
